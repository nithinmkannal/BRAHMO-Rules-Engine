"""
Tests: Five-Check Filter (unit tests, no DB required)
"""

import pytest
from backend.models.user import User
from backend.pipeline.five_check_filter import (
    check1_isolation,
    check2_compliance,
    check3_permission,
    check4_temporal,
    check5_derivability,
)
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


def make_node(**kwargs) -> dict:
    defaults = dict(
        id="N-TEST",
        org_id="supra",
        type="FACT",
        title="Test Node",
        content="content",
        importance=0.5,
        zone=1,
        status="ACTIVE",
        derivability_score=0.1,
        compliance_tags=[],
        valid_until=None,
        hierarchy_level_number=10,
        department="ortho",
    )
    defaults.update(kwargs)
    return defaults


# --- Check 1: Isolation ---

def test_check1_passes_same_org():
    user = make_user()
    nodes = [make_node(org_id="supra"), make_node(org_id="other")]
    result = check1_isolation(nodes, user)
    assert len(result) == 1
    assert result[0]["org_id"] == "supra"


# --- Check 2: Compliance ---

def test_check2_blocks_mnpi_without_clearance():
    user = make_user(compliance_clearance=[])
    nodes = [
        make_node(id="N-1", compliance_tags=["MNPI"]),
        make_node(id="N-2", compliance_tags=[]),
    ]
    result = check2_compliance(nodes, user)
    assert len(result) == 1
    assert result[0]["id"] == "N-2"


def test_check2_allows_mnpi_with_clearance():
    user = make_user(compliance_clearance=["MNPI"])
    nodes = [make_node(compliance_tags=["MNPI"])]
    result = check2_compliance(nodes, user)
    assert len(result) == 1


def test_check2_blocks_partial_clearance():
    user = make_user(compliance_clearance=["MNPI"])
    nodes = [make_node(compliance_tags=["MNPI", "CONFIDENTIAL"])]
    result = check2_compliance(nodes, user)
    assert len(result) == 0


def test_check2_admin_full_clearance():
    user = make_user(compliance_clearance=["MNPI", "PHI", "CONFIDENTIAL"])
    nodes = [make_node(compliance_tags=["MNPI", "CONFIDENTIAL"])]
    result = check2_compliance(nodes, user)
    assert len(result) == 1


# --- Check 3: Permission ---

def test_check3_viewer_cannot_read_above_ceiling():
    user = make_user(role="VIEWER", ceiling_level=10)
    perms = compile_permissions(user)
    nodes = [
        make_node(id="N-HIGH", hierarchy_level_number=5),   # above ceiling (lower number = higher up)
        make_node(id="N-LOW", hierarchy_level_number=10),   # at ceiling
        make_node(id="N-LOWER", hierarchy_level_number=12), # below ceiling
    ]
    result = check3_permission(nodes, user, perms)
    ids = {n["id"] for n in result}
    assert "N-LOW" in ids
    assert "N-LOWER" in ids
    assert "N-HIGH" not in ids


# --- Check 4: Temporal ---

def test_check4_excludes_superseded():
    nodes = [
        make_node(id="N-SUP", status="SUPERSEDED"),
        make_node(id="N-ACT", status="ACTIVE"),
    ]
    result = check4_temporal(nodes)
    assert len(result) == 1
    assert result[0]["id"] == "N-ACT"


def test_check4_excludes_expired():
    nodes = [make_node(valid_until="2020-01-01T00:00:00+00:00")]
    result = check4_temporal(nodes)
    assert len(result) == 0


def test_check4_keeps_legal_hold():
    nodes = [make_node(status="LEGAL_HOLD")]
    result = check4_temporal(nodes)
    assert len(result) == 1


# --- Check 5: Derivability ---

def test_check5_excludes_high_derivability():
    nodes = [
        make_node(id="N-HIGH", derivability_score=0.92),
        make_node(id="N-LOW", derivability_score=0.10),
    ]
    result = check5_derivability(nodes, threshold=0.7)
    assert len(result) == 1
    assert result[0]["id"] == "N-LOW"


def test_check5_threshold_boundary():
    nodes = [make_node(derivability_score=0.70)]
    result = check5_derivability(nodes, threshold=0.7)
    # score 0.70 is NOT < 0.70 → excluded
    assert len(result) == 0
