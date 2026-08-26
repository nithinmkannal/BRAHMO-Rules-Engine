"""
Tests: Permission Compiler
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


def test_viewer_can_read_at_and_above_ceiling():
    user = make_user(role="VIEWER", ceiling_level=10)
    perms = compile_permissions(user)
    assert perms[10]["can_read"] is True
    assert perms[11]["can_read"] is True
    assert perms[9]["can_read"] is False
    assert perms[1]["can_read"] is False


def test_viewer_cannot_write():
    user = make_user(role="VIEWER", ceiling_level=10)
    perms = compile_permissions(user)
    for level in range(1, 16):
        assert perms[level]["can_write"] is False


def test_hod_reads_all_levels():
    user = make_user(role="HOD", ceiling_level=4, write_ceiling=4)
    perms = compile_permissions(user)
    for level in range(1, 16):
        assert perms[level]["can_read"] is True


def test_hod_writes_at_and_above_ceiling():
    user = make_user(role="HOD", ceiling_level=4, write_ceiling=4)
    perms = compile_permissions(user)
    assert perms[4]["can_write"] is True
    assert perms[3]["can_write"] is False


def test_admin_reads_and_writes_everything():
    user = make_user(role="ADMIN", ceiling_level=1, write_ceiling=1)
    perms = compile_permissions(user)
    for level in range(1, 16):
        assert perms[level]["can_read"] is True
        assert perms[level]["can_write"] is True


def test_editor_reads_at_and_above_ceiling():
    user = make_user(role="EDITOR", ceiling_level=8, write_ceiling=8)
    perms = compile_permissions(user)
    assert perms[8]["can_read"] is True
    assert perms[7]["can_read"] is False


def test_auditor_reads_all_levels():
    user = make_user(role="AUDITOR", ceiling_level=5)
    perms = compile_permissions(user)
    for level in range(1, 16):
        assert perms[level]["can_read"] is True
        assert perms[level]["can_write"] is False
