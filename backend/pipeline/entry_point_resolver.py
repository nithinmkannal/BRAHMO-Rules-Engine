"""
Entry Point Resolver
====================
Maps a user's department to their DAG leaf node (their starting position for BFS).

Logic:
  - Entry point = the deepest hierarchy level in the user's dept whose level_number
    is <= user.ceiling_level. This is the leaf the user occupies in the DAG.
    (Priya: ceiling=10, ortho → finds HL-10-ORTHO-W at level 10, NOT HL-12-RAJAN)
  - For ADMIN (ceiling_level == 1), use the Hospital root node.
  - Returns (hierarchy_level_id, level_number).
"""

from supabase import Client

from backend.models.user import User


def resolve_entry_point(user: User, db: Client) -> tuple[str, int]:
    """
    Returns (hierarchy_level_id, level_number) for the user's entry point into the DAG.
    """
    if user.role == "ADMIN" or user.ceiling_level == 1:
        # ADMIN enters at hospital root
        result = (
            db.table("hierarchy_levels")
            .select("id, level_number")
            .eq("org_id", user.org_id)
            .eq("level_number", 1)
            .is_("department", None)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            return row["id"], row["level_number"]

    # Entry point = the level in user's dept whose level_number is closest to
    # ceiling_level from below (deepest level <= ceiling). If no such level exists
    # (ceiling is above all dept levels, e.g. HOD L4 in ortho which starts at L5),
    # use the shallowest dept level (dept root).
    #
    # Example: Priya (VIEWER L10, ortho) → HL-10-ORTHO-W (level 10, exactly at ceiling)
    # Example: Vikram (HOD L4, ortho)    → HL-05-ORTHO   (shallowest ortho level)

    # Try: deepest level in dept that is <= ceiling
    result = (
        db.table("hierarchy_levels")
        .select("id, level_number")
        .eq("org_id", user.org_id)
        .eq("department", user.department)
        .lte("level_number", user.ceiling_level)
        .order("level_number", desc=True)
        .limit(1)
        .execute()
    )

    if result.data:
        row = result.data[0]
        return row["id"], row["level_number"]

    # Fallback: shallowest (root) level of the dept (when ceiling < all dept levels)
    result = (
        db.table("hierarchy_levels")
        .select("id, level_number")
        .eq("org_id", user.org_id)
        .eq("department", user.department)
        .order("level_number", desc=False)
        .limit(1)
        .execute()
    )

    if result.data:
        row = result.data[0]
        return row["id"], row["level_number"]

    # Final fallback: root node
    result = (
        db.table("hierarchy_levels")
        .select("id, level_number")
        .eq("org_id", user.org_id)
        .eq("level_number", 1)
        .limit(1)
        .execute()
    )
    if not result.data:
        # No root node exists for this org — return a safe sentinel
        return "HL-01", 1
    row = result.data[0]
    return row["id"], row["level_number"]
