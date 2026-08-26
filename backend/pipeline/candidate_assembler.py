"""
Candidate Set Assembler
========================
Takes surviving nodes (post-5-checks) and annotates each with:
  - type, importance, zone (already on node)
  - distance_from_entry (from BFS distances dict)
  - compression_hint: based on distance
      0-1  → FULL
      2    → COMPRESSED
      3+   → CONSTRAINT_ONLY

Returns a JSON-serialisable list of annotated candidate node dicts.
"""

from backend.models.candidate_set import CandidateNode


def _compression_hint(distance: int) -> str:
    if distance <= 1:
        return "FULL"
    elif distance == 2:
        return "COMPRESSED"
    else:
        return "CONSTRAINT_ONLY"


def assemble_candidate_set(
    nodes: list[dict],
    distances: dict[str, int],
) -> list[CandidateNode]:
    """
    Annotate each surviving node with distance + compression_hint.

    nodes     : list of node dicts (post-filter)
    distances : dict[node_id, distance_from_entry] (from BFS + zone2 injection)
    """
    candidates: list[CandidateNode] = []

    for node in nodes:
        node_id = node["id"]
        distance = distances.get(node_id, 999)

        candidate = CandidateNode(
            id=node_id,
            type=node["type"],
            title=node["title"],
            content=node["content"],
            importance=float(node["importance"]),
            zone=node["zone"],
            hierarchy_level=node.get("hierarchy_level_number"),
            department=node.get("department"),
            distance_from_entry=distance,
            compression_hint=_compression_hint(distance),
        )
        candidates.append(candidate)

    # Sort by importance descending, then distance ascending
    candidates.sort(key=lambda c: (-c.importance, c.distance_from_entry))

    return candidates
