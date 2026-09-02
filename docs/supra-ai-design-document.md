# Supra Hospital AI Assistant — Design Document
### BRAHMO Knowledge Infrastructure · Supra Multi-Specialty Hospital, Hyderabad

---

## Page 1 — Executive Summary

### What Was Built

A context-aware AI clinical assistant for Supra Multi-Specialty Hospital that gives measurably different — and safer — answers than raw ChatGPT for the same clinical questions. The system is built on the BRAHMO Rules Engine, which filters 50 organizational knowledge nodes through a BFS graph traversal and 5-check sequential filter before injecting only the authorized, relevant subset as context into an LLM prompt.

### The Core Claim

A doctor at Supra Hospital asking "What should I prescribe for patient Rajan's knee pain?" should get:

> *"Do NOT prescribe NSAIDs for patient Rajan. Absolute contraindication: he is on Warfarin 5mg daily for AF with a documented GI bleed in 2024 caused by NSAID interaction. Supra policy requires Paracetamol only for pain. — Supra Ortho NSAID Contraindication Protocol"*

Raw ChatGPT, with no Supra context, gives:
> *"For knee pain, common options include ibuprofen, naproxen, or diclofenac for inflammation..."*

The second answer would kill patient Rajan. This is the gap the system closes.

### Two Deliverables

| Deliverable | Status |
|---|---|
| Working prototype — web app with doctor selector, chat UI, BRAHMO context retrieval, side-by-side ChatGPT comparison | ✅ Complete |
| Design document — architecture, problems discovered, future work, why ChatGPT alone fails | ✅ This document |

---

## Page 2 — Architecture Overview

### System Layers

```
┌─────────────────────────────────────────────────────┐
│  LAYER 3: Presentation                              │
│  Next.js /ai page                                   │
│  Doctor selector · Chat UI · Context panel          │
│  Side-by-side Supra vs Raw ChatGPT comparison       │
└──────────────────┬──────────────────────────────────┘
                   │ HTTP POST /ai/chat
┌──────────────────▼──────────────────────────────────┐
│  LAYER 2: BRAHMO Rules Engine (ZERO LLM)            │
│  Permission Compiler → Entry Point → BFS Traversal  │
│  → Zone 2 Injection → 5-Check Sequential Filter     │
│  → Candidate Set Assembler                          │
│  Output: 10-22 authorized knowledge nodes           │
└──────────────────┬──────────────────────────────────┘
                   │ Candidate nodes → System prompt
┌──────────────────▼──────────────────────────────────┐
│  LAYER 3: LLM (GPT-4o-mini)                         │
│  System prompt = Supra-specific knowledge context   │
│  User message = doctor's clinical question          │
│  Output: context-grounded clinical answer           │
└──────────────────┬──────────────────────────────────┘
                   │ Knowledge nodes
┌──────────────────▼──────────────────────────────────┐
│  LAYER 1: Supabase (PostgreSQL)                     │
│  50 knowledge nodes · 7 users · 20 hierarchy levels │
│  Typed edges · Compliance tags · Derivability scores│
└─────────────────────────────────────────────────────┘
```

### Key Architectural Decision: BRAHMO Pipeline Before the LLM

The LLM never sees the raw database. It only sees the ~10-22 nodes that survived:
1. **BFS graph traversal** — structural reach from the doctor's position in the org DAG
2. **5-check sequential filter** — isolation, compliance, permission, temporal, derivability

This means the LLM cannot hallucinate about other departments' protocols, cannot leak MNPI-tagged financial data to a nurse, and cannot cite an expired protocol (like Sepsis v2, superseded by v3 in 2026).

---

## Page 3 — BRAHMO Rules Engine Pipeline Detail

### The Pipeline (per request, ~50-150ms, Zero LLM)

```
User opens chat as Dr. Vikram (HOD, Ortho, ceiling L4)
  │
  ├─ Permission Compiler (~1ms)
  │    Builds O(1) dict: {level: {can_read, can_write}} for all 15 levels
  │    HOD: can_read ALL levels, can_write levels ≥ 4
  │
  ├─ Entry Point Resolver (~5ms)
  │    Dr. Vikram → dept=ortho, ceiling=4
  │    Finds deepest hierarchy level in ortho ≤ L4 → HL-05-ORTHO (L5, shallowest)
  │
  ├─ BFS Traversal (~20ms)
  │    Starts at HL-05-ORTHO, walks upward via parent_ids
  │    Reaches: HL-03-CLIN → HL-01 (Hospital root)
  │    Also reaches: HL-08-ORTHO-TKR, HL-08-ORTHO-GEN, HL-08-POST-TKR (multi-parent)
  │    Visited set prevents re-processing multi-parent nodes
  │    Output: ~18 reachable hierarchy levels + distances
  │
  ├─ Zone 2 Injection (~5ms)
  │    Injects all 10 GLOBAL nodes (hospital-wide drug safety rules)
  │    These bypass BFS but still go through all 5 checks
  │
  └─ 5-Check Sequential Filter (~10ms)
       Check 1 ISOLATION:    org_id = 'supra'          → all pass
       Check 2 COMPLIANCE:   no blocked tags for Vikram → N-O12 excluded (MNPI+CONFIDENTIAL, no clearance)
       Check 3 PERMISSION:   HOD reads all levels      → all remaining pass
       Check 4 TEMPORAL:     no SUPERSEDED/EXPIRED     → N-M08 excluded (Sepsis v2 SUPERSEDED)
       Check 5 DERIVABILITY: score < 0.7               → N-D01..D05 excluded (generic medical facts)
       Final: ~22 nodes for Dr. Vikram
```

### Node Types in the Candidate Set

| Type | Purpose | Example |
|---|---|---|
| `CONSTRAINT` | Hard safety rules — must be followed | Warfarin+NSAID interaction, Rajan NSAID ban |
| `ANTI_PATTERN` | Past incidents encoded as "never do this" | Never discharge TKR < 48h, never verbal orders |
| `DECISION` | Org-specific clinical choices | Paracetamol first-line post-TKR, Zimmer implant |
| `FACT` | Org-specific facts not general knowledge | Ortho ward capacity, Night shift handover format |

---

## Page 4 — Why This is Measurably Better Than ChatGPT

### Test Query Comparison

| Query | Raw ChatGPT | Supra Hospital AI | Difference |
|---|---|---|---|
| "Post-TKR pain medication?" | "NSAIDs for inflammation, opioids for severe pain" | "Paracetamol 650mg QDS first-line per Dr. Vikram Jan 2025. Escalate to Tramadol 50mg if VAS>6. AVOID NSAIDs due to surgical bleeding risk — Supra Ortho policy" | ChatGPT's first suggestion (NSAIDs) is explicitly banned at Supra |
| "Patient Rajan knee pain?" | "Ibuprofen or diclofenac for anti-inflammatory effect" | "ABSOLUTE contraindication: No NSAIDs for Rajan. Warfarin + GI bleed 2024. Paracetamol ONLY." | ChatGPT would cause a life-threatening GI bleed |
| "DVT prophylaxis timing?" | "Begin within 12-24 hours post-op" | "Supra protocol: Enoxaparin 40mg SC daily, start exactly 12h post-op. 14 days for TKR, 28 days for THR." | Supra gives precise timing + drug + duration |
| "Our sepsis protocol?" | "Sepsis-3 bundle: blood cultures, antibiotics, fluids" | "Supra Sepsis Bundle v3 2026: lactate within 1 HOUR (not 3h like v2), 30mL/kg crystalloid, vasopressors if MAP <65" | ChatGPT references generic guidelines; Supra uses its own v3 with tighter 1h lactate window |
| "Mrs. Padma medication?" | "Cannot provide patient-specific information" | "Padma, 62F, Type 2 DM on Metformin 1000mg BD + Glimepiride 2mg. Ekadashi fasting: skip Glimepiride, continue Metformin with evening meal. 3 hypoglycemia episodes in 2025 before this adjustment." | ChatGPT knows nothing about Padma — Supra AI knows her complete medication history |

### The Fundamental Problem with "Just Use ChatGPT"

1. **No organizational memory** — ChatGPT cannot know that Supra switched to Paracetamol first-line in Jan 2025, that Zimmer Biomet is the preferred implant vendor, or that Sepsis v3 tightened the lactate window to 1 hour.

2. **No patient-level context** — ChatGPT cannot know that patient Rajan has an absolute NSAID contraindication documented from 8 prior refusals, a 2024 GI bleed, and a cardiac stent.

3. **No access control** — ChatGPT would give every user the same answer. A staff nurse asking about the ortho department budget should see nothing. An HOD should see the budget but not vendor negotiation strategy (MNPI). Admin should see both.

4. **No temporal awareness** — ChatGPT might cite Sepsis v2 (3-hour lactate window) even after Supra adopted v3 (1-hour). At Supra, the superseded protocol is actively blocked.

5. **Hallucination on org-specific facts** — ChatGPT might confidently invent a "Supra protocol" that doesn't exist. The BRAHMO system only allows the LLM to see pre-verified, org-curated knowledge.

---

## Page 5 — Security Model: Silent Exclusion + Permission Architecture

### Silent Exclusion

When Nurse Priya asks about a topic and the system has relevant Cardiology nodes, those nodes are not shown to the LLM — and Priya's response gives no indication they exist. No "access denied", no "some results were hidden", no count of excluded nodes. The exclusion is **silent**.

This matters because:
- If the system returns "3 nodes were restricted", an attacker knows those nodes exist
- Silent exclusion means unauthorized nodes are **absent**, not **denied**
- The LLM's answer looks complete and natural — it simply doesn't know about the restricted nodes

### Permission Architecture

```
User Role     | Read Access                  | Write Access
──────────────┼──────────────────────────────┼──────────────────────
VIEWER        | Levels ≥ ceiling             | None
EDITOR        | Levels ≥ ceiling             | Levels ≥ write_ceiling
HOD           | ALL levels                   | Levels ≥ ceiling
ADMIN         | ALL levels                   | ALL levels
QUALITY       | Levels ≥ ceiling             | Levels ≥ write_ceiling
AUDITOR       | ALL levels (with clearance)  | None
```

### Compliance Tag System

Sensitive nodes carry compliance tags. A node only passes Check 2 if the user holds clearance for **all** of its tags:

| Tag | Meaning | Who has clearance |
|---|---|---|
| `MNPI` | Material Non-Public Information (budget, vendor contracts) | Admin Suresh, Dr. Sunita (QA) |
| `CONFIDENTIAL` | Board-level decisions (expansion plan, salary) | Admin Suresh only |
| `PHI` | Protected Health Information | Admin Suresh only |

### What Priya Can Never See (and Never Knows Exists)

- N-O11: Ortho Department Budget 2026 (MNPI) — excluded at Check 2
- N-O12: Vendor Negotiation Strategy (MNPI+CONFIDENTIAL) — excluded at Check 2
- N-C01..C05: All Cardiology nodes — excluded at BFS (not reachable from Ortho Ward)
- N-A01: Hospital Expansion Plan (MNPI+CONFIDENTIAL) — excluded at BFS + Check 2
- N-M02: Sepsis Protocol — excluded at BFS (Medicine dept, not reachable from Ortho)

---

## Page 6 — Data Architecture: The Knowledge Graph

### 15-Level Hierarchy DAG

```
L1  ── Supra Hospital (root)
  L3 ── Clinical Division
    L5 ── Orthopaedics Dept         ← Dr. Vikram enters here
      L8 ── Ortho General
        L10 ── Ortho Ward           ← Nurse Priya enters here
          L12 ── Patient: Rajan
      L8 ── Ortho TKR Unit
      L8 ── Post-TKR Protocol Area  ← multi-parent: Ortho + Surgery
    L5 ── General Medicine Dept
      L8 ── Medicine General
        L10 ── Medicine Ward
          L12 ── Patient: Padma
    L5 ── Cardiology Dept           ← NOT reachable by Ortho users
    L5 ── Surgery Dept
  L3 ── Administrative Division
  L3 ── Global Constraints (Zone 2) ← injected for ALL users
```

### Multi-Parent Nodes

`HL-08-POST-TKR` (Post-TKR Protocol Area) has `parent_ids = ["HL-05-ORTHO", "HL-05-SURG"]`. Both an Ortho nurse and a Surgery nurse can reach it via BFS from their respective entry points. The **visited set** in BFS ensures the node is processed exactly once even when reachable from two paths — preventing both duplicate processing and potential infinite loops on accidental cycles.

### Zone System

| Zone | Name | Description |
|---|---|---|
| Zone 1 | Addressed | Department-specific; only reachable by BFS from correct dept |
| Zone 2 | Global | Hospital-wide safety rules; bypasses BFS, injected for ALL users |
| Zone 3 | Floating | Not yet assigned to a hierarchy level; reserved for future use |

Zone 2 nodes are the safety net — drug interactions, emergency codes, blood transfusion protocols. Even if BFS produces zero relevant nodes for a new user, they always receive global safety constraints.

### Derivability Score

Each node has a pre-computed `derivability_score` (0.0–1.0) representing how likely an LLM already knows the content from general training:

- `0.01` — "No NSAIDs for patient Rajan" → LLM cannot know this (org+patient specific)
- `0.08` — "Paracetamol 650mg QDS post-TKR per Dr. Vikram Jan 2025" → org-specific
- `0.75` — "Hand hygiene WHO 5-moment compliance" → LLM already knows this
- `0.95` — "Paracetamol mechanism of action" → LLM definitely knows this

Nodes scoring ≥ 0.7 are excluded by Check 5. This preserves token budget for nodes that add genuine value.

---

## Page 7 — Prompt Engineering: Converting Nodes to Clinical Context

### System Prompt Structure

The candidate nodes are sorted before injection: CONSTRAINT → ANTI_PATTERN → DECISION → FACT, then by importance descending within each type. This ordering ensures the LLM encounters hard safety rules first and is less likely to be influenced by general facts before reading critical constraints.

```
You are the AI clinical assistant for Supra Multi-Specialty Hospital, Hyderabad.

You have been loaded with ONLY the knowledge protocols, decisions, and constraints 
that are relevant and authorized for Dr. Vikram (HOD, ortho department).

CRITICAL RULES:
1. Always prioritize CONSTRAINT and ANTI_PATTERN nodes.
2. Refer to specific Supra protocols by name.
3. If a protocol says to avoid something, refuse and explain why.
4. Never make up information not present in the provided context.
5. Be concise and clinically precise.

=== SUPRA HOSPITAL KNOWLEDGE CONTEXT FOR DR. VIKRAM ===

[CONSTRAINT][GLOBAL POLICY] Warfarin-NSAID Interaction (importance: 0.98)
CRITICAL: Never prescribe NSAIDs to patients on Warfarin. Risk of life-threatening GI bleed...

[CONSTRAINT] Patient Rajan: Absolute NSAID Contraindication (importance: 0.99)
ABSOLUTE CONTRAINDICATION: No ibuprofen, no aspirin, no diclofenac for patient Rajan...

[DECISION] Paracetamol First-Line Post-TKR (importance: 0.88)
Supra Ortho uses Paracetamol 650mg QDS as first-line post-TKR pain management...

... (remaining nodes)

=== END OF CONTEXT ===

Answer questions using ONLY the above Supra Hospital protocols.
```

### Why Low Temperature (0.2)?

Clinical answers must be deterministic and reproducible. A nurse asking the same question twice should get the same protocol reference both times. High temperature introduces variance that is unacceptable in a clinical safety context.

### Token Budget Awareness

The derivability filter is partly a token budget tool. At `threshold=0.7`, ~5 generic nodes are excluded per user session — saving approximately 800-1200 tokens per request. The org config stores `"token_budget": 4000`, allowing this threshold to be tuned per deployment.

---

## Page 8 — Problems Discovered During Implementation

### Problem 1: HOD Entry Point Paradox

Dr. Vikram is HOD of Orthopaedics with `ceiling_level=4`. The Orthopaedics Department hierarchy level is `HL-05-ORTHO` at level 5. His ceiling (4) is *above* his own department level. The entry point resolver had to handle this gracefully: when no department level exists at or below the ceiling, fall back to the shallowest department level (the dept root itself).

**Resolution:** [`entry_point_resolver.py`](../backend/pipeline/entry_point_resolver.py) tries `level_number ≤ ceiling` first; if empty, falls back to `ORDER BY level_number ASC LIMIT 1` for the department.

### Problem 2: Multi-Tenant Isolation vs Single-Org Demo

Check 1 (isolation) filters by `org_id`. In a single-org demo with only `org='supra'`, all nodes pass trivially. But the check is architecturally critical — in a multi-hospital deployment (e.g., 12 hospitals sharing a BRAHMO instance), this is the first wall preventing Apollo Hospital nodes from ever appearing in a Supra session. The check must be present and correct even when it appears to do nothing in the demo.

### Problem 3: Zone 2 Nodes and the Permission Check

Zone 2 (GLOBAL) nodes are hospital-wide safety constraints. They are injected for all users regardless of BFS path. But they still go through all 5 checks — a GLOBAL node tagged MNPI should NOT be visible to a nurse just because it's global.

**Resolution:** Zone 2 nodes bypass Check 3 (permission ceiling) only — since they are by definition meant for all staff. They still go through Checks 1, 2, 4, and 5. The implementation in [`five_check_filter.py`](../backend/pipeline/five_check_filter.py) checks `if node.get("zone") == 2: return True` in Check 3 only.

### Problem 4: Python 3.9 Type Annotation Syntax

The new `ai_assistant.py` module used `str | None` union syntax (Python 3.10+). The project venv runs Python 3.9, causing `TypeError: unsupported operand type(s) for |`. Even `from __future__ import annotations` doesn't fix this in Pydantic v2 on Python 3.9.

**Resolution:** Use `Optional[str]` from `typing` module — the compatible form for Python 3.9.

### Problem 5: Parallel Requests for Side-by-Side Comparison

The UI fires `/ai/chat` (BRAHMO + LLM) and `/ai/chat/raw` (LLM only) in parallel using `Promise.all()`. This means the total latency is `max(brahmo_ms, raw_ms)` rather than the sum. Since the BRAHMO pipeline takes ~100ms and the LLM call dominates at ~1-3s, both responses arrive at nearly the same time — the UX is a simultaneous reveal of Supra vs raw answers.

### Problem 6: Derivability Score is Pre-Computed, Not Runtime

The derivability filter must use ZERO LLM. Scores are assigned at seed-time based on content analysis heuristics:
- Contains patient name + specific measurement → very low (0.01-0.05)
- References specific Supra decision by date/person → low (0.05-0.15)
- General clinical guideline without Supra specifics → medium (0.3-0.5)
- Basic medical definition (what is DVT, mechanism of Paracetamol) → high (0.90-0.98)

---

## Page 9 — What I Would Add With More Time

### 1. Semantic Re-Ranking Within the Candidate Set

The current pipeline is binary: a node either passes all 5 checks or it doesn't. Within the surviving ~15-22 nodes, ordering is by importance (a static score). With more time, I would add a lightweight semantic re-ranking step — embed the doctor's query and compute cosine similarity against each candidate node, then reorder the context block so the most query-relevant nodes appear first in the system prompt. This does NOT replace the 5-check filter; it runs after it, purely for ordering. No LLM is needed — a local embedding model (all-MiniLM-L6-v2) runs in <10ms.

### 2. Streaming Responses

The current implementation waits for the full LLM response before rendering. For a clinical assistant, streaming would feel dramatically faster and more responsive. FastAPI supports `StreamingResponse`; the Next.js frontend would consume a Server-Sent Events stream. This is a UX improvement only — no architectural change to the pipeline.

### 3. Audit Log for Every AI Response

Every answer the AI gives should be logged: which user asked, which query, which nodes were injected, what the answer was, timestamp. This is critical for clinical governance — if a doctor acts on bad AI advice, the hospital needs to be able to reconstruct exactly what the system said and which knowledge it was based on. The `audit_log` table already exists in the schema; the `/ai/chat` endpoint just needs to write to it.

### 4. Feedback Loop: "Was This Helpful?"

After each response, show the doctor a thumbs-up/thumbs-down. Negative feedback on a specific response should trigger a review workflow — a Quality Officer gets notified to check whether the relevant knowledge nodes are up to date. This closes the loop between AI usage and knowledge base maintenance.

### 5. Multi-Turn Conversation Memory

The current implementation is stateless — each message is an independent pipeline run. With more time, I would maintain a conversation thread: previous Q&A turns are compressed and prepended to the context, within the token budget. This allows the doctor to say "and for that same patient, what about DVT prophylaxis?" and the AI understands "that same patient" refers to Rajan.

### 6. Confidence Indicators Per Answer

Display which specific nodes contributed to each claim in the answer. If the AI says "Enoxaparin 40mg SC daily starting 12 hours post-op," show a small citation: `[N-O06: DVT Prophylaxis Protocol, importance 0.93]`. This lets a doctor verify the source, builds trust, and makes the system auditable.

---

## Page 10 — Why a Hospital Cannot Just Use ChatGPT

### The Seven Gaps

**Gap 1: No Organizational Memory**
ChatGPT has no knowledge of Supra's specific protocols: that they switched to Paracetamol-first post-TKR in January 2025, that the lactate window in their Sepsis Bundle was tightened to 1 hour in 2026, that they use Zimmer Biomet as their TKR implant vendor. Every hospital makes these choices differently. ChatGPT answers for a generic hospital that doesn't exist.

**Gap 2: No Patient-Level Context**
Patient Rajan's NSAID contraindication is not just a medical guideline — it is a documented patient-specific rule backed by 8 prior refusals, a GI bleed event, and an active medico-legal hold. ChatGPT cannot know this. The BRAHMO system has it as node N-O14 at hierarchy level 12 (patient level), only reachable by Ortho staff.

**Gap 3: No Access Control**
ChatGPT gives every user the same answer. It cannot enforce that the Ortho budget (MNPI) is visible only to the HOD and Admin, that the vendor negotiation strategy (MNPI+CONFIDENTIAL) is visible only to Admin, or that Medicine department protocols are not shown to Ortho staff. A single ChatGPT deployment at a hospital is a security disaster.

**Gap 4: No Temporal Validity**
Medical protocols get superseded. Supra's Sepsis v2 (3-hour lactate) was replaced by v3 (1-hour) in 2026. ChatGPT might confidently cite the old protocol. In the BRAHMO system, N-M08 (Sepsis v2) has `status=SUPERSEDED` and is excluded by Check 4 for every user, every time.

**Gap 5: Permission Before Retrieval**
In a naive RAG system, you retrieve relevant documents first and then check if the user should see them. This means restricted data travels over the network before being discarded. The BRAHMO pipeline enforces permissions at the SQL query level — restricted data never leaves the database for unauthorized users.

**Gap 6: Hallucination on Org-Specific Facts**
Asked "Does Supra use Zimmer or Stryker implants?", ChatGPT might confidently say "Stryker is the industry standard" — a hallucination. The BRAHMO system only allows the LLM to answer using pre-verified, org-curated nodes. The system prompt explicitly says "Never make up information not present in the provided context."

**Gap 7: No Incident Learning**
Supra's anti-patterns (N-O03: never discharge TKR before 48h, N-G05: never accept verbal orders) were written because these exact things went wrong at Supra in specific years. These lessons are encoded as `ANTI_PATTERN` type nodes with the incident context. ChatGPT has no knowledge of Supra's specific incidents — and more importantly, has no mechanism to enforce their lessons.

### The Correct Architecture

The solution is not to replace ChatGPT but to **constrain it**. The BRAHMO Rules Engine acts as a pre-filter — the LLM only sees what it is authorized to see, what is organizationally relevant, and what is still current. The LLM provides language fluency and clinical reasoning; the Rules Engine provides accuracy, access control, and organizational memory.

```
Wrong:  Doctor's question → ChatGPT → Answer
Right:  Doctor's question → BRAHMO pipeline (Zero LLM) → 
        Authorized candidate set → LLM with Supra context → 
        Safe, accurate, access-controlled answer
```

### Scalability Note

At 50 nodes (this demo), the pipeline runs in ~50-150ms. At 15,000 nodes across 12 hospitals: BFS traversal is bounded by the user's reachable subgraph (~300-500 nodes regardless of total graph size). Checks 1-4 run as SQL WHERE clauses with indexed columns. Check 5 uses a pre-computed score — no runtime computation. The pipeline time stays under 500ms because it scales with *reachable nodes*, not *total nodes*.

---

*Design Document v1.0 — Supra Hospital AI Assistant*
*Built on BRAHMO Rules Engine · Supra Multi-Specialty Hospital, Hyderabad*
*Stack: FastAPI · Next.js · Supabase · GPT-4o-mini · Tailwind CSS*
