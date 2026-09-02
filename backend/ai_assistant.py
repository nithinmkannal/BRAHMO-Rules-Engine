"""
Supra Hospital AI Assistant — FastAPI endpoints
=================================================
POST /ai/chat
  Body: { "user_id": str, "query": str }
  → Runs BRAHMO pipeline to get candidate nodes for this user,
    builds a system prompt with Supra-specific context,
    calls the LLM, returns the answer + which nodes were used.

POST /ai/chat/raw
  Body: { "query": str }
  → Same question to the LLM with ZERO Supra context (raw ChatGPT).
    Used for the side-by-side comparison demo.

GET /ai/users
  → List all users (convenience alias for the chat UI).
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client

from backend.models.candidate_set import CandidateSet, PipelineTiming, PipelineFunnel
from backend.models.user import User
from backend.pipeline.permission_compiler import compile_permissions
from backend.pipeline.entry_point_resolver import resolve_entry_point
from backend.pipeline.bfs_traversal import bfs_upward
from backend.pipeline.zone2_injector import inject_zone2_nodes
from backend.pipeline.five_check_filter import (
    check1_isolation, check2_compliance, check3_permission,
    check4_temporal, check5_derivability,
)
from backend.pipeline.candidate_assembler import assemble_candidate_set

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# The assistant uses GPT-4o-mini by default (cheap, fast)
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

app = FastAPI(title="Supra Hospital AI Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id: str
    query: str


class RawChatRequest(BaseModel):
    query: str


class ContextNode(BaseModel):
    id: str
    type: str
    title: str
    content: str
    importance: float
    zone: int
    department: Optional[str]


class ChatResponse(BaseModel):
    answer: str
    context_nodes_used: list[ContextNode]
    candidate_set_size: int
    pipeline_ms: float
    llm_ms: float
    model: str
    user_name: str
    user_role: str


class RawChatResponse(BaseModel):
    answer: str
    llm_ms: float
    model: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_db() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _row_to_user(row: dict) -> User:
    return User(
        id=row["id"],
        org_id=row["org_id"],
        name=row["name"],
        role=row["role"],
        department=row["department"],
        ceiling_level=row["ceiling_level"],
        write_ceiling=row.get("write_ceiling"),
        compliance_clearance=row.get("compliance_clearance") or [],
        status=row.get("status", "ACTIVE"),
    )


def _run_pipeline(user_id: str, db: Client) -> tuple[User, list[dict], float]:
    """
    Run the full BRAHMO pipeline for a user.
    Returns (user, candidate_nodes, pipeline_ms).
    """
    t_start = time.perf_counter()

    # Fetch user
    user_result = db.table("users").select("*").eq("id", user_id).limit(1).execute()
    if not user_result.data:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    user = _row_to_user(user_result.data[0])

    # Permission compiler
    permissions = compile_permissions(user)

    # Entry point + BFS
    entry_level_id, _ = resolve_entry_point(user, db)
    level_distances = bfs_upward(entry_level_id, user.org_id, db)
    reachable_level_ids = list(level_distances.keys())

    # Fetch reachable nodes
    nodes_result = (
        db.table("knowledge_nodes")
        .select("*, hierarchy_levels!inner(level_number)")
        .in_("hierarchy_level_id", reachable_level_ids)
        .eq("org_id", user.org_id)
        .execute()
    )
    raw_nodes = nodes_result.data or []
    for node in raw_nodes:
        hl = node.pop("hierarchy_levels", None)
        if hl:
            node["hierarchy_level_number"] = hl["level_number"]

    # Zone 2 injection
    existing_ids = {n["id"] for n in raw_nodes}
    zone2_result = (
        db.table("knowledge_nodes")
        .select("*, hierarchy_levels!inner(level_number)")
        .eq("org_id", user.org_id)
        .eq("zone", 2)
        .execute()
    )
    for node in zone2_result.data or []:
        if node["id"] not in existing_ids:
            hl = node.pop("hierarchy_levels", None)
            if hl:
                node["hierarchy_level_number"] = hl["level_number"]
            raw_nodes.append(node)
            existing_ids.add(node["id"])

    # Org config
    org_result = db.table("organizations").select("config").eq("id", user.org_id).limit(1).execute()
    derivability_threshold = 0.7
    if org_result.data:
        config = org_result.data[0].get("config") or {}
        derivability_threshold = float(config.get("derivability_threshold", 0.7))

    # Five-check filter
    nodes = raw_nodes[:]
    nodes = check1_isolation(nodes, user)
    nodes = check2_compliance(nodes, user)
    nodes = check3_permission(nodes, user, permissions)
    nodes = check4_temporal(nodes)
    nodes = check5_derivability(nodes, threshold=derivability_threshold)

    pipeline_ms = round((time.perf_counter() - t_start) * 1000, 2)
    return user, nodes, pipeline_ms


def _build_system_prompt(user: User, candidate_nodes: list[dict]) -> str:
    """
    Build the LLM system prompt from Supra Hospital's candidate knowledge nodes.
    Nodes are sorted by importance descending, constraints first.
    """
    # Sort: CONSTRAINT first, then by importance desc
    type_priority = {"CONSTRAINT": 0, "ANTI_PATTERN": 1, "DECISION": 2, "FACT": 3}
    sorted_nodes = sorted(
        candidate_nodes,
        key=lambda n: (type_priority.get(n.get("type", "FACT"), 3), -float(n.get("importance", 0)))
    )

    # Build context block
    context_parts = []
    for node in sorted_nodes:
        ntype = node.get("type", "FACT")
        title = node.get("title", "")
        content = node.get("content", "")
        importance = float(node.get("importance", 0))
        zone = node.get("zone", 1)
        zone_tag = " [GLOBAL POLICY]" if zone == 2 else ""

        context_parts.append(
            f"[{ntype}{zone_tag}] {title} (importance: {importance:.2f})\n{content}"
        )

    context_block = "\n\n---\n\n".join(context_parts)

    return f"""You are the AI clinical assistant for Supra Multi-Specialty Hospital, Hyderabad.

You have been loaded with ONLY the knowledge protocols, decisions, and constraints that are relevant and authorized for {user.name} ({user.role}, {user.department} department).

CRITICAL RULES:
1. Always prioritize CONSTRAINT and ANTI_PATTERN nodes — these are hard safety rules.
2. Refer to specific Supra protocols by name (e.g., "Supra Ortho policy", "Supra Sepsis Bundle v3").
3. If a protocol says to avoid something, refuse and explain why using the exact Supra reason.
4. Never make up information not present in the provided context.
5. Be concise and clinically precise — this is a busy hospital setting.

=== SUPRA HOSPITAL KNOWLEDGE CONTEXT FOR {user.name.upper()} ===

{context_block}

=== END OF CONTEXT ===

Answer questions using ONLY the above Supra Hospital protocols. When you cite a rule, mention it is a Supra Hospital policy. If the question is outside the provided context, say so and advise consulting the relevant department HOD."""


def _call_llm(system_prompt: str, user_query: str) -> tuple[str, float]:
    """
    Call the OpenAI API. Returns (answer_text, latency_ms).
    Falls back to a helpful error message if API key is missing.
    """
    if not OPENAI_API_KEY:
        return (
            "⚠️  OPENAI_API_KEY not configured. Add it to your .env file to enable AI responses.\n\n"
            "The BRAHMO pipeline ran successfully and retrieved the context nodes shown below. "
            "Once you add an API key, the AI will use these Supra-specific protocols to answer.",
            0.0,
        )

    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=0.2,  # low temperature for clinical accuracy
            max_tokens=600,
        )
        llm_ms = round((time.perf_counter() - t0) * 1000, 2)
        answer = response.choices[0].message.content or ""
        return answer, llm_ms

    except Exception as exc:
        return f"LLM error: {exc}", 0.0


def _call_llm_raw(user_query: str) -> tuple[str, float]:
    """Call LLM with zero hospital context (raw mode for comparison)."""
    if not OPENAI_API_KEY:
        return (
            "⚠️  OPENAI_API_KEY not configured. Raw comparison unavailable.",
            0.0,
        )

    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        system = (
            "You are a helpful medical AI assistant. Answer the following clinical question "
            "based on your general medical knowledge."
        )

        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_query},
            ],
            temperature=0.2,
            max_tokens=600,
        )
        llm_ms = round((time.perf_counter() - t0) * 1000, 2)
        answer = response.choices[0].message.content or ""
        return answer, llm_ms

    except Exception as exc:
        return f"LLM error: {exc}", 0.0


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/ai/users")
def list_users():
    db = get_db()
    result = db.table("users").select("*").eq("status", "ACTIVE").execute()
    return result.data


@app.post("/ai/chat")
def chat_with_context(req: ChatRequest) -> dict:
    """
    Context-aware chat: runs BRAHMO pipeline, injects Supra knowledge, calls LLM.
    """
    db = get_db()

    # Step 1: Run BRAHMO pipeline to get authorized knowledge for this user
    user, candidate_nodes, pipeline_ms = _run_pipeline(req.user_id, db)

    # Step 2: Build system prompt from candidate nodes
    system_prompt = _build_system_prompt(user, candidate_nodes)

    # Step 3: Call LLM with context
    answer, llm_ms = _call_llm(system_prompt, req.query)

    # Step 4: Build response — include which nodes were used as context
    context_nodes = [
        {
            "id": n["id"],
            "type": n.get("type", "FACT"),
            "title": n.get("title", ""),
            "content": n.get("content", ""),
            "importance": float(n.get("importance", 0)),
            "zone": n.get("zone", 1),
            "department": n.get("department"),
        }
        for n in candidate_nodes
    ]

    return {
        "answer": answer,
        "context_nodes_used": context_nodes,
        "candidate_set_size": len(candidate_nodes),
        "pipeline_ms": pipeline_ms,
        "llm_ms": llm_ms,
        "model": LLM_MODEL,
        "user_name": user.name,
        "user_role": user.role,
    }


@app.post("/ai/chat/raw")
def chat_raw(req: RawChatRequest) -> dict:
    """
    Raw chat: same question with ZERO Supra Hospital context.
    Used to demonstrate why a hospital can't just use ChatGPT.
    """
    answer, llm_ms = _call_llm_raw(req.query)

    return {
        "answer": answer,
        "llm_ms": llm_ms,
        "model": LLM_MODEL,
    }
