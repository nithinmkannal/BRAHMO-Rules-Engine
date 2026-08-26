"""
Permission Compiler
===================
Compiles a user's permissions into an O(1) lookup dictionary at session start.
Called ONCE per session. Result is reused for all 500+ permission checks.

Output: dict[int, dict] where key = level_number
  {
    1: {"can_read": True, "can_write": True},
    2: {"can_read": True, "can_write": False},
    ...
  }
"""

from backend.models.user import User


def compile_permissions(user: User, max_levels: int = 15) -> dict[int, dict]:
    """
    Compile user permissions into an O(1) lookup structure.

    Rules:
      VIEWER  : can_read levels >= ceiling_level, can_write nothing
      EDITOR  : can_read levels >= ceiling_level, can_write levels >= write_ceiling
      HOD     : can_read ALL levels, can_write levels >= ceiling_level
      ADMIN   : can_read and can_write ALL levels
      QUALITY : can_read levels >= ceiling_level, can_write levels >= write_ceiling
      AUDITOR : can_read ALL levels (with clearance), can_write nothing
    """
    permissions: dict[int, dict] = {}

    for level in range(1, max_levels + 1):
        can_read = False
        can_write = False

        role = user.role

        if role == "ADMIN":
            can_read = True
            can_write = True

        elif role == "HOD":
            can_read = True  # HOD sees all levels
            can_write = level >= user.ceiling_level

        elif role in ("EDITOR", "QUALITY"):
            can_read = level >= user.ceiling_level
            write_ceiling = user.write_ceiling if user.write_ceiling is not None else 999
            can_write = level >= write_ceiling

        elif role == "VIEWER":
            can_read = level >= user.ceiling_level
            can_write = False

        elif role == "AUDITOR":
            can_read = True  # auditors read everything (with compliance clearance)
            can_write = False

        permissions[level] = {"can_read": can_read, "can_write": can_write}

    return permissions
