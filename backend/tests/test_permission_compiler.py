"""
Tests: Permission Compiler — Hardened
======================================
Covers every role, every boundary, and every edge case.
"""

import pytest
from backend.models.user import User
from backend.pipeline.permission_compiler import compile_permissions


def make_user(**kwargs) -> User:
    defaults = dict(
        id="U-TEST",
        org_id="supra",
        name="Test",
        role="VIEWER",
        department="ortho",
        ceiling_level=10,
        write_ceiling=None,
        compliance_clearance=[],
    )
    defaults.update(kwargs)
    return User(**defaults)


# ── VIEWER ──────────────────────────────────────────────────────────────────

class TestViewer:
    def test_reads_at_ceiling(self):
        perms = compile_permissions(make_user(role="VIEWER", ceiling_level=10))
        assert perms[10]["can_read"] is True

    def test_reads_below_ceiling_in_hierarchy(self):
        # level 11 and 12 are deeper (more specific) → readable
        perms = compile_permissions(make_user(role="VIEWER", ceiling_level=10))
        assert perms[11]["can_read"] is True
        assert perms[15]["can_read"] is True

    def test_cannot_read_above_ceiling(self):
        perms = compile_permissions(make_user(role="VIEWER", ceiling_level=10))
        for level in range(1, 10):
            assert perms[level]["can_read"] is False, f"level {level} should be unreadable"

    def test_cannot_write_any_level(self):
        perms = compile_permissions(make_user(role="VIEWER", ceiling_level=10))
        for level in range(1, 16):
            assert perms[level]["can_write"] is False

    def test_ceiling_at_level_1(self):
        # Edge: ceiling at root — reads everything
        perms = compile_permissions(make_user(role="VIEWER", ceiling_level=1))
        for level in range(1, 16):
            assert perms[level]["can_read"] is True

    def test_ceiling_at_max_level_15(self):
        # Edge: ceiling at deepest level — reads only level 15
        perms = compile_permissions(make_user(role="VIEWER", ceiling_level=15))
        assert perms[15]["can_read"] is True
        for level in range(1, 15):
            assert perms[level]["can_read"] is False

    def test_output_has_all_15_levels(self):
        perms = compile_permissions(make_user(role="VIEWER", ceiling_level=5))
        assert set(perms.keys()) == set(range(1, 16))

    def test_each_level_has_both_keys(self):
        perms = compile_permissions(make_user(role="VIEWER", ceiling_level=5))
        for level, v in perms.items():
            assert "can_read" in v and "can_write" in v, f"level {level} missing keys"


# ── HOD ─────────────────────────────────────────────────────────────────────

class TestHOD:
    def test_reads_all_levels(self):
        perms = compile_permissions(make_user(role="HOD", ceiling_level=4, write_ceiling=4))
        for level in range(1, 16):
            assert perms[level]["can_read"] is True

    def test_writes_at_and_deeper_than_ceiling(self):
        perms = compile_permissions(make_user(role="HOD", ceiling_level=4, write_ceiling=4))
        assert perms[4]["can_write"] is True
        assert perms[10]["can_write"] is True

    def test_cannot_write_above_ceiling(self):
        perms = compile_permissions(make_user(role="HOD", ceiling_level=4, write_ceiling=4))
        assert perms[3]["can_write"] is False
        assert perms[1]["can_write"] is False

    def test_boundary_level_4_write(self):
        perms = compile_permissions(make_user(role="HOD", ceiling_level=4, write_ceiling=4))
        assert perms[4]["can_write"] is True
        assert perms[5]["can_write"] is True

    def test_hod_ceiling_1_writes_everything(self):
        perms = compile_permissions(make_user(role="HOD", ceiling_level=1, write_ceiling=1))
        for level in range(1, 16):
            assert perms[level]["can_write"] is True


# ── ADMIN ────────────────────────────────────────────────────────────────────

class TestAdmin:
    def test_reads_all_levels(self):
        perms = compile_permissions(make_user(role="ADMIN", ceiling_level=1, write_ceiling=1))
        for level in range(1, 16):
            assert perms[level]["can_read"] is True

    def test_writes_all_levels(self):
        perms = compile_permissions(make_user(role="ADMIN", ceiling_level=1, write_ceiling=1))
        for level in range(1, 16):
            assert perms[level]["can_write"] is True

    def test_admin_ignores_write_ceiling(self):
        # ADMIN always writes everything regardless of write_ceiling value
        perms = compile_permissions(make_user(role="ADMIN", ceiling_level=5, write_ceiling=10))
        for level in range(1, 16):
            assert perms[level]["can_write"] is True


# ── EDITOR ───────────────────────────────────────────────────────────────────

class TestEditor:
    def test_reads_at_and_deeper_than_ceiling(self):
        perms = compile_permissions(make_user(role="EDITOR", ceiling_level=8, write_ceiling=8))
        assert perms[8]["can_read"] is True
        assert perms[15]["can_read"] is True

    def test_cannot_read_above_ceiling(self):
        perms = compile_permissions(make_user(role="EDITOR", ceiling_level=8, write_ceiling=8))
        for level in range(1, 8):
            assert perms[level]["can_read"] is False

    def test_writes_at_and_deeper_than_write_ceiling(self):
        perms = compile_permissions(make_user(role="EDITOR", ceiling_level=8, write_ceiling=10))
        assert perms[10]["can_write"] is True
        assert perms[15]["can_write"] is True

    def test_cannot_write_above_write_ceiling(self):
        perms = compile_permissions(make_user(role="EDITOR", ceiling_level=8, write_ceiling=10))
        for level in range(1, 10):
            assert perms[level]["can_write"] is False

    def test_editor_write_ceiling_none_defaults_no_write(self):
        # write_ceiling=None → sentinel 999 → no level <= 999 in range 1-15 is False... wait:
        # In compiler: write_ceiling = 999 → can_write = level >= 999 → always False for 1-15
        perms = compile_permissions(make_user(role="EDITOR", ceiling_level=8, write_ceiling=None))
        for level in range(1, 16):
            assert perms[level]["can_write"] is False


# ── QUALITY ──────────────────────────────────────────────────────────────────

class TestQuality:
    def test_reads_at_and_deeper_than_ceiling(self):
        perms = compile_permissions(make_user(role="QUALITY", ceiling_level=6, write_ceiling=8))
        for level in range(6, 16):
            assert perms[level]["can_read"] is True

    def test_cannot_read_above_ceiling(self):
        perms = compile_permissions(make_user(role="QUALITY", ceiling_level=6, write_ceiling=8))
        for level in range(1, 6):
            assert perms[level]["can_read"] is False

    def test_writes_at_and_deeper_than_write_ceiling(self):
        perms = compile_permissions(make_user(role="QUALITY", ceiling_level=6, write_ceiling=8))
        assert perms[8]["can_write"] is True
        assert perms[15]["can_write"] is True
        assert perms[7]["can_write"] is False


# ── AUDITOR ──────────────────────────────────────────────────────────────────

class TestAuditor:
    def test_reads_all_levels(self):
        perms = compile_permissions(make_user(role="AUDITOR", ceiling_level=5))
        for level in range(1, 16):
            assert perms[level]["can_read"] is True

    def test_cannot_write_any_level(self):
        perms = compile_permissions(make_user(role="AUDITOR", ceiling_level=5))
        for level in range(1, 16):
            assert perms[level]["can_write"] is False

    def test_auditor_ceiling_does_not_restrict_read(self):
        # Even if ceiling is 12, auditor reads level 1
        perms = compile_permissions(make_user(role="AUDITOR", ceiling_level=12))
        assert perms[1]["can_read"] is True
