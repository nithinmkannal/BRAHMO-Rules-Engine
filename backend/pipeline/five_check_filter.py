"""
Five-Check Sequential Filter
=============================
Applies 5 sequential checks to the candidate node set.
Output of check N is the input to check N+1.

Check 1 — ISOLATION    : WHERE org_id = user.org_id
Check 2 — COMPLIANCE   : blocked compliance tags removed
Check 3 — PERMISSION   : uses compiled O(1) permission dict
Check 4 — TEMPORAL     : excludes SUPERSEDED / expired nodes
Check 5 — DERIVABILITY : excludes nodes AI can answer from general knowledge

Each check function:
  - Takes a list of node dicts + user/permissions context
  - Returns filtered list

Nodes are fetched from Supabase once (bulk fetch), then filtered in-memory
for checks 2-5. Check 1 (isolation) is pushed to the SQL query.
"""

from datetime import datetime, timezone
from typing import Any

from backend.models.user import User

DERIVABILITY_THRESHOLD = 0.7  # configurable per org


def check1_isolation(nodes: list[dict], user: User) -> list[dict]:
    """Org isolation: only nodes belonging to user's org pass."""
    return [n for n in nodes if n["org_id"] == user.org_id]


def check2_compliance(nodes: list[dict], user: User) -> list[dict]:
    """
    Compliance: exclude nodes whose compliance_tags overlap with user's blocked tags.

    A user's BLOCKED tags = all tags they DON'T have clearance for.
    If a node has a compliance tag that the user lacks clearance for → exclude.
    """
    clearance = set(user.compliance_clearance or [])

    def passes(node: dict) -> bool:
        tags = set(node.get("compliance_tags") or [])
        if not tags:
            return True
        # Node passes only if user has clearance for ALL its tags
        return tags.issubset(clearance)

    return [n for n in nodes if passes(n)]


def check3_permission(
    nodes: list[dict],
    user: User,
    permissions: dict[int, dict],
) -> list[dict]:
    """
    Permission: uses compiled O(1) lookup to check can_read for each node's level.

    Zone 2 (global) nodes bypass the permission ceiling — they are hospital-wide
    safety constraints that every user must see regardless of their role level.
    """
    def can_read(node: dict) -> bool:
        # Zone 2 nodes are globally visible — they bypass the permission ceiling.
        if node.get("zone") == 2:
            return True
        level = node.get("hierarchy_level_number")
        if level is None:
            return True
        perm = permissions.get(level, {"can_read": False})
        return perm["can_read"]

    return [n for n in nodes if can_read(n)]


def check4_temporal(nodes: list[dict]) -> list[dict]:
    """
    Temporal: exclude SUPERSEDED nodes and expired nodes (valid_until < NOW).
    LEGAL_HOLD nodes pass through (they exist but can't be modified).
    """
    now = datetime.now(timezone.utc)

    def passes(node: dict) -> bool:
        if node.get("status") in ("SUPERSEDED", "EXPIRED"):
            return False
        valid_until = node.get("valid_until")
        if valid_until:
            # Parse ISO string if needed
            if isinstance(valid_until, str):
                try:
                    dt = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
                    if dt < now:
                        return False
                except ValueError:
                    pass
        return True

    return [n for n in nodes if passes(n)]


def check5_derivability(nodes: list[dict], threshold: float = DERIVABILITY_THRESHOLD) -> list[dict]:
    """
    Derivability: exclude nodes where derivability_score >= threshold.
    These contain knowledge the AI can already answer from general training.
    """
    return [n for n in nodes if float(n.get("derivability_score", 0)) < threshold]


def run_five_checks(
    nodes: list[dict],
    user: User,
    permissions: dict[int, dict],
    derivability_threshold: float = DERIVABILITY_THRESHOLD,
) -> tuple[list[dict], dict[str, int]]:
    """
    Run all 5 checks sequentially. Returns (final_nodes, stage_counts).

    stage_counts = {
        "after_check1": N,
        "after_check2": N,
        "after_check3": N,
        "after_check4": N,
        "after_check5": N,
    }
    """
    stage_counts: dict[str, int] = {}

    nodes = check1_isolation(nodes, user)
    stage_counts["after_check1"] = len(nodes)

    nodes = check2_compliance(nodes, user)
    stage_counts["after_check2"] = len(nodes)

    nodes = check3_permission(nodes, user, permissions)
    stage_counts["after_check3"] = len(nodes)

    nodes = check4_temporal(nodes)
    stage_counts["after_check4"] = len(nodes)

    nodes = check5_derivability(nodes, threshold=derivability_threshold)
    stage_counts["after_check5"] = len(nodes)

    return nodes, stage_counts
