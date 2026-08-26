"""
BFS Traversal
=============
Traverses the hierarchy DAG from a user's entry point. Uses a FIFO queue and
a visited set to prevent re-processing (handles multi-parent DAG nodes).

Direction strategy:
  - From a LEAF node (e.g. Ortho Ward L10): walk UPWARD via parent_ids.
    This reaches the user's dept → division → hospital root.
  - From the ROOT node (L1, e.g. ADMIN): walk DOWNWARD via children edges.
    This reaches the entire graph.
  - The BFS builds both parent and child adjacency in a single DB fetch,
    then explores whichever direction(s) reach more nodes from the entry point.
    In practice: leaf nodes have parents but no children; root has children.

Multi-parent: if a node has parent_ids = [A, B], it's reached from both paths
but processed ONLY ONCE (visited set).

Returns:
  - A dict mapping hierarchy_level_id → distance_from_entry (int, 0 = entry)
  - Does NOT fetch node content yet; just maps level IDs to distances.
"""

from collections import deque

from supabase import Client


def bfs_upward(entry_level_id: str, org_id: str, db: Client) -> dict[str, int]:
    """
    BFS through the hierarchy DAG from entry_level_id.

    - Non-root users (leaf entry): walk UPWARD only via parent_ids.
      Priya at L10 reaches L8 → L5 → L3 → L1, not L12 patient nodes.
    - Root user (ADMIN, entry = L1 with no parents): walk DOWNWARD via
      children edges so that the entire graph becomes reachable.

    Returns dict[hierarchy_level_id, distance_from_entry].
    """
    # Fetch all hierarchy levels for this org in one query (avoids N+1)
    result = (
        db.table("hierarchy_levels")
        .select("id, parent_ids")
        .eq("org_id", org_id)
        .execute()
    )

    # Build parent adjacency: level_id → list of parent_ids
    parent_adj: dict[str, list[str]] = {}
    # Build child adjacency: level_id → list of child_ids (reverse edges)
    child_adj: dict[str, list[str]] = {}

    for row in result.data:
        level_id = row["id"]
        parents = row["parent_ids"] or []
        parent_adj[level_id] = parents
        if level_id not in child_adj:
            child_adj[level_id] = []
        for pid in parents:
            if pid not in child_adj:
                child_adj[pid] = []
            child_adj[pid].append(level_id)

    # Determine traversal direction:
    # If entry has no parents (root node), walk downward to reach all levels.
    # Otherwise walk upward — the standard case for all non-admin users.
    entry_has_parents = bool(parent_adj.get(entry_level_id))

    visited: dict[str, int] = {}  # level_id → distance
    queue: deque[tuple[str, int]] = deque()

    queue.append((entry_level_id, 0))
    visited[entry_level_id] = 0

    while queue:
        current_id, distance = queue.popleft()

        if entry_has_parents:
            # Walk upward only (leaf → root path)
            for neighbor_id in parent_adj.get(current_id, []):
                if neighbor_id not in visited:
                    visited[neighbor_id] = distance + 1
                    queue.append((neighbor_id, distance + 1))
        else:
            # Walk downward only (root → all descendants)
            for neighbor_id in child_adj.get(current_id, []):
                if neighbor_id not in visited:
                    visited[neighbor_id] = distance + 1
                    queue.append((neighbor_id, distance + 1))

    return visited
