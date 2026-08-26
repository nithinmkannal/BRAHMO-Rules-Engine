"""
Zone 2 Injector
===============
After BFS, inject all nodes where zone = 2 (GLOBAL).

Zone 2 nodes are hospital-wide safety constraints that apply to ALL users
regardless of their traversal path. They are injected BEFORE the 5 checks
so they still go through all filtering.

Returns:
  - Updated dict[node_id, distance_from_entry] with Zone 2 nodes added at
    distance = 999 (sentinel value meaning "injected, not traversal-reached").
"""

from supabase import Client


ZONE2_DISTANCE_SENTINEL = 999


def inject_zone2_nodes(
    reachable_nodes: dict[str, int],
    org_id: str,
    db: Client,
) -> dict[str, int]:
    """
    Injects all Zone 2 (GLOBAL) node IDs into the reachable set.

    reachable_nodes: dict[node_id, distance_from_entry]
    Returns updated dict with Zone 2 nodes appended.
    """
    result = (
        db.table("knowledge_nodes")
        .select("id")
        .eq("org_id", org_id)
        .eq("zone", 2)
        .execute()
    )

    updated = dict(reachable_nodes)
    for row in result.data:
        node_id = row["id"]
        if node_id not in updated:
            updated[node_id] = ZONE2_DISTANCE_SENTINEL

    return updated
