# Architecture: BRAHMO Rules Engine Pipeline

## Overview

The BRAHMO Rules Engine implements a **BFS Traversal + 5-Check Sequential Filter** pipeline
for knowledge graph retrieval. The goal is to produce a minimal, relevant, permission-respecting
candidate set of knowledge nodes for a given user — without using any LLM anywhere in the pipeline.

---

## Module-by-Module Design

### 1. Permission Compiler

**Purpose:** Convert a user record into an O(1) lookup structure compiled *once* per session.

**Design decision:** Rather than checking role/ceiling_level on every node access (which would
require branching logic 500+ times per pipeline run), we pre-compute a flat dict keyed by
`level_number` at session start. Every subsequent permission check is a single dict lookup.

```python
permissions[level_number] = {"can_read": bool, "can_write": bool}
```

**Role semantics:**
- `VIEWER`: reads at/below their ceiling (high level number = closer to patient)
- `EDITOR`: reads and writes at/below their ceiling
- `HOD`: reads ALL levels (needs hospital-wide context), writes at/below ceiling
- `ADMIN`: reads and writes everything
- `AUDITOR`: reads everything (compliance role), writes nothing
- `QUALITY`: reads/writes at/below ceiling with optional MNPI clearance

---

### 2. Entry Point Resolver

**Purpose:** Map a user's department to their DAG starting position.

**Design decision:** BFS starts at the *deepest* level the user can reach in their department.
A nurse in Ortho Ward starts at `HL-10-ORTHO-W` (level 10). An HOD starts at their department
root (level 5). An Admin starts at hospital root (level 1).

The resolver queries `hierarchy_levels` for the deepest level ≥ `ceiling_level` for the user's
department. This ensures:
- Nurses don't accidentally see HOD-level decisions
- HODs get full departmental context upward
- Admin gets the whole hospital

---

### 3. BFS Traversal (Upward DAG Walk)

**Purpose:** Discover all hierarchy levels reachable from the entry point by walking UP parent_ids edges.

**Implementation:**
- Single bulk fetch of all hierarchy levels for the org (avoids N+1 queries)
- FIFO queue + visited set for correctness and cycle safety
- Multi-parent nodes processed *once* — the first (shortest) path wins

**Why upward?** The knowledge graph is structured as a DAG where child nodes inherit context
from their parents (more specific → more general). A nurse in the Ortho Ward needs to see
ward-level protocols, department-level constraints, division policies, and hospital-wide rules.
Walking upward naturally captures this inheritance.

**Output:** `dict[hierarchy_level_id → distance_from_entry]`
Distance = 0 means the entry point itself. Distance increases as we go higher (more general).

---

### 4. Zone 2 Injector

**Purpose:** Inject hospital-wide safety constraints that apply to ALL users regardless of BFS path.

**Placement: After BFS, before 5 checks.** Zone 2 nodes are NOT exempt from filtering —
they still go through all 5 checks. An MNPI-tagged Zone 2 node should still be blocked
from a user without MNPI clearance.

**Sentinel distance (999):** Zone 2 nodes injected this way get `distance_from_entry = 999`,
which maps to `compression_hint = CONSTRAINT_ONLY` in the assembler. This is intentional —
global constraints should always be surfaced in the most concise form.

---

### 5. Five-Check Sequential Filter

**Critical design principle:** Each check takes the *previous check's output* as its input.
This means failing early is free — a node that fails Check 2 never touches Check 3-5 logic.

**Check ordering rationale:**

| # | Check | Why this position |
|---|-------|-------------------|
| 1 | Isolation (org_id) | Cheapest — single equality check. Blocks cross-tenant data immediately. In single-org demo all pass, but essential for production. |
| 2 | Compliance (tag × clearance) | Tag overlap check. Must run before permission check because compliance tags can appear at any level — even public-level nodes can have MNPI tags. |
| 3 | Permission (level lookup) | O(1) dict lookup using compiled permissions. Runs after compliance so sensitive-tagged nodes are already removed. |
| 4 | Temporal (status + valid_until) | Runs late because superseded nodes might still have valid permissions — we want to count them in Check 3 stats, then remove stale ones. |
| 5 | Derivability (score threshold) | Most expensive conceptually (requires knowing what an AI knows). Runs last to minimize set size before this check. |

**Implementation note:** Checks 1-5 are all implemented as pure Python list filters
operating on in-memory node dicts. The alternative (pushing each check as a SQL WHERE clause)
is discussed in GAP 5 of the original spec — it would be more efficient for large graphs
but adds query complexity. For 50 nodes, in-memory filtering is fast enough.

---

### 6. Candidate Set Assembler

**Purpose:** Annotate surviving nodes with metadata useful for downstream LLM context construction.

**Compression hints** reflect retrieval priority based on distance from entry:
- `FULL` (distance 0-1): Most relevant — include complete content
- `COMPRESSED` (distance 2): Contextually relevant — include summary
- `CONSTRAINT_ONLY` (distance 3+, or Zone 2 injected): Cite rule only

**Sort order:** Importance (descending) → distance (ascending).
This ensures the most critical, most proximate nodes appear first in the candidate set.

---

## Key Design Decisions

### Why BFS instead of DFS?
BFS guarantees we find the *shortest path* to each reachable node. This matters for
distance_from_entry, which drives compression hints. DFS would give arbitrary distances
depending on traversal order.

### Why compile permissions once?
A typical pipeline run checks permissions for 30-50 nodes. With O(1) lookup, this is
negligible. Without pre-compilation, we'd evaluate role/ceiling/write_ceiling logic
50 times per run — wasteful and error-prone.

### Why not filter in SQL?
In-memory filtering (post-fetch) trades SQL round-trips for local computation.
For 50 nodes, this is clearly the right call. The code is more testable (no DB mock needed
for filter logic), more readable, and easier to extend. For graphs with 50,000+ nodes,
SQL WHERE clauses would be preferable.

### Silent exclusion
No check emits an error or "access denied" message. Excluded nodes simply don't appear
in the candidate set. This is a security requirement — users should not know what they
cannot see.

---

## Data Flow Diagram

```
DB: users                            DB: hierarchy_levels
     │                                        │
     ▼                                        ▼
Permission Compiler              Entry Point Resolver
     │                                        │
     │                             BFS Upward Traversal
     │                                        │
     │                              Zone 2 Injector
     │                                        │
     │                          Fetch reachable nodes
     │                          (knowledge_nodes JOIN
     │                           hierarchy_levels)
     │                                        │
     └──────────────────┬─────────────────────┘
                        ▼
              Check 1: Isolation
                        ▼
              Check 2: Compliance
                        ▼
              Check 3: Permission ←── compiled permissions (O(1))
                        ▼
              Check 4: Temporal
                        ▼
              Check 5: Derivability
                        ▼
              Candidate Set Assembler
                        ▼
                   JSON Response
```
