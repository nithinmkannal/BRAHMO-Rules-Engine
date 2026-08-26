"""
BRAHMO Rules Engine — FastAPI Entry Point
==========================================
Endpoints:
  GET  /users              → list all users
  POST /pipeline/{user_id} → run full pipeline for a user
  POST /pipeline/compare   → run pipeline for multiple users side-by-side
"""

import time
from dataclasses import asdict

from dotenv import load_dotenv
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

from backend.models.user import User
from backend.models.candidate_set import CandidateSet, PipelineTiming, PipelineFunnel
from backend.pipeline.permission_compiler import compile_permissions
from backend.pipeline.entry_point_resolver import resolve_entry_point
from backend.pipeline.bfs_traversal import bfs_upward
from backend.pipeline.zone2_injector import inject_zone2_nodes
from backend.pipeline.five_check_filter import run_five_checks
from backend.pipeline.candidate_assembler import assemble_candidate_set

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

app = FastAPI(title="BRAHMO Rules Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/users")
def list_users():
    db = get_db()
    result = db.table("users").select("*").eq("status", "ACTIVE").execute()
    return result.data


@app.post("/pipeline/compare")
def compare_users(body: dict):
    """Run pipeline for multiple user IDs and return side-by-side results."""
    user_ids: list[str] = body.get("user_ids", [])
    if not user_ids or len(user_ids) > 5:
        raise HTTPException(status_code=400, detail="Provide 1-5 user_ids")
    return [run_pipeline(uid) for uid in user_ids]


@app.post("/pipeline/{user_id}")
def run_pipeline(user_id: str):
    db = get_db()
    timing = PipelineTiming()
    funnel = PipelineFunnel()

    # --- Fetch user ---
    user_result = db.table("users").select("*").eq("id", user_id).limit(1).execute()
    if not user_result.data:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    user = _row_to_user(user_result.data[0])

    # --- Total node count ---
    total_result = db.table("knowledge_nodes").select("id", count="exact").eq("org_id", user.org_id).execute()
    funnel.total_nodes = total_result.count or len(total_result.data)

    # --- Step 1: Permission Compiler ---
    t0 = time.perf_counter()
    permissions = compile_permissions(user)
    timing.permission_compile_ms = round((time.perf_counter() - t0) * 1000, 2)

    # --- Step 2: Entry Point Resolver ---
    entry_level_id, entry_level_number = resolve_entry_point(user, db)

    # --- Step 3: BFS Traversal ---
    t0 = time.perf_counter()
    level_distances = bfs_upward(entry_level_id, user.org_id, db)
    timing.bfs_ms = round((time.perf_counter() - t0) * 1000, 2)

    # Fetch all knowledge nodes whose hierarchy_level_id is in the reachable set
    # Join with hierarchy_levels to get level_number
    reachable_level_ids = list(level_distances.keys())

    # Fetch nodes in the reachable hierarchy levels
    nodes_result = (
        db.table("knowledge_nodes")
        .select("*, hierarchy_levels!inner(level_number)")
        .in_("hierarchy_level_id", reachable_level_ids)
        .eq("org_id", user.org_id)
        .execute()
    )
    raw_nodes = nodes_result.data or []

    # Flatten joined level_number onto each node dict
    for node in raw_nodes:
        hl = node.pop("hierarchy_levels", None)
        if hl:
            node["hierarchy_level_number"] = hl["level_number"]

    # Build node_id → distance mapping (via their hierarchy level distance)
    node_distances: dict[str, int] = {}
    for node in raw_nodes:
        node_distances[node["id"]] = level_distances.get(node["hierarchy_level_id"], 999)

    funnel.after_bfs = len(raw_nodes)

    # --- Step 4: Zone 2 Injection ---
    t0 = time.perf_counter()
    # Fetch Zone 2 nodes not already in the set
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
            node_distances[node["id"]] = 999  # sentinel: Zone 2 injected
            existing_ids.add(node["id"])
    timing.zone2_inject_ms = round((time.perf_counter() - t0) * 1000, 2)
    funnel.after_zone2 = len(raw_nodes)

    # Fetch org config for derivability threshold
    org_result = db.table("organizations").select("config").eq("id", user.org_id).limit(1).execute()
    derivability_threshold = 0.7
    if org_result.data:
        config = org_result.data[0].get("config") or {}
        derivability_threshold = float(config.get("derivability_threshold", 0.7))

    # --- Step 5: Five-Check Sequential Filter (with per-check timing) ---
    from backend.pipeline.five_check_filter import (
        check1_isolation, check2_compliance, check3_permission,
        check4_temporal, check5_derivability,
    )

    nodes = raw_nodes[:]

    t0 = time.perf_counter()
    nodes = check1_isolation(nodes, user)
    timing.check1_isolation_ms = round((time.perf_counter() - t0) * 1000, 2)
    funnel.after_check1 = len(nodes)

    t0 = time.perf_counter()
    nodes = check2_compliance(nodes, user)
    timing.check2_compliance_ms = round((time.perf_counter() - t0) * 1000, 2)
    funnel.after_check2 = len(nodes)

    t0 = time.perf_counter()
    nodes = check3_permission(nodes, user, permissions)
    timing.check3_permission_ms = round((time.perf_counter() - t0) * 1000, 2)
    funnel.after_check3 = len(nodes)

    t0 = time.perf_counter()
    nodes = check4_temporal(nodes)
    timing.check4_temporal_ms = round((time.perf_counter() - t0) * 1000, 2)
    funnel.after_check4 = len(nodes)

    t0 = time.perf_counter()
    nodes = check5_derivability(nodes, threshold=derivability_threshold)
    timing.check5_derivability_ms = round((time.perf_counter() - t0) * 1000, 2)
    funnel.after_check5 = len(nodes)

    timing.total_ms = round(
        timing.permission_compile_ms + timing.bfs_ms + timing.zone2_inject_ms +
        timing.check1_isolation_ms + timing.check2_compliance_ms +
        timing.check3_permission_ms + timing.check4_temporal_ms +
        timing.check5_derivability_ms,
        2,
    )

    # --- Step 6: Candidate Set Assembler ---
    candidates = assemble_candidate_set(nodes, node_distances)

    result = CandidateSet(
        user=user.id,
        user_name=user.name,
        role=user.role,
        ceiling_level=user.ceiling_level,
        entry_point=entry_level_id,
        pipeline_timing=timing,
        funnel=funnel,
        candidate_set=candidates,
    )

    return asdict(result)


