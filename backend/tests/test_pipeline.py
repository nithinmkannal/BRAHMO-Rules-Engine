"""
Tests: Full Pipeline Integration (mocked DB)
Tests the pipeline orchestration logic without requiring a real Supabase connection.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.models.user import User
from backend.pipeline.permission_compiler import compile_permissions
from backend.pipeline.bfs_traversal import bfs_upward
from backend.pipeline.zone2_injector import inject_zone2_nodes
from backend.pipeline.five_check_filter import run_five_checks
from backend.pipeline.candidate_assembler import assemble_candidate_set


def make_user(**kwargs) -> User:
    defaults = dict(
        id="U-PRIYA",
        org_id="supra",
        name="Nurse Priya",
        role="VIEWER",
        department="ortho",
        ceiling_level=10,
        write_ceiling=None,
        compliance_clearance=[],
    )
    defaults.update(kwargs)
    return User(**defaults)


# ---- BFS unit test with mock DB ----

def test_bfs_traversal_upward():
    """BFS should walk up parent_ids edges and return visited set with distances."""
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "HL-10-ORTHO-W", "parent_ids": ["HL-08-ORTHO-GEN"]},
        {"id": "HL-08-ORTHO-GEN", "parent_ids": ["HL-05-ORTHO"]},
        {"id": "HL-05-ORTHO", "parent_ids": ["HL-03-CLIN"]},
        {"id": "HL-03-CLIN", "parent_ids": ["HL-01"]},
        {"id": "HL-01", "parent_ids": []},
        # Unrelated nodes
        {"id": "HL-05-MED", "parent_ids": ["HL-03-CLIN"]},
    ]

    distances = bfs_upward("HL-10-ORTHO-W", "supra", mock_db)

    assert distances["HL-10-ORTHO-W"] == 0
    assert distances["HL-08-ORTHO-GEN"] == 1
    assert distances["HL-05-ORTHO"] == 2
    assert distances["HL-03-CLIN"] == 3
    assert distances["HL-01"] == 4
    # HL-05-MED is NOT reachable upward from HL-10-ORTHO-W
    assert "HL-05-MED" not in distances


def test_bfs_multi_parent_visited_once():
    """A node with multiple parents should be visited only once (shortest path wins)."""
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "HL-ENTRY", "parent_ids": ["HL-A", "HL-B"]},
        {"id": "HL-A", "parent_ids": ["HL-ROOT"]},
        {"id": "HL-B", "parent_ids": ["HL-ROOT"]},
        {"id": "HL-ROOT", "parent_ids": []},
    ]

    distances = bfs_upward("HL-ENTRY", "supra", mock_db)

    # HL-ROOT is reachable via both HL-A and HL-B but visited ONCE
    assert "HL-ROOT" in distances
    assert distances["HL-ROOT"] == 2


# ---- Zone 2 injection test ----

def test_zone2_injection_adds_global_nodes():
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "N-G01"},
        {"id": "N-G02"},
    ]

    existing = {"N-O01": 0, "N-O02": 1}
    updated = inject_zone2_nodes(existing, "supra", mock_db)

    assert "N-G01" in updated
    assert "N-G02" in updated
    assert updated["N-G01"] == 999  # sentinel distance


def test_zone2_injection_does_not_duplicate():
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "N-G01"},
    ]

    # N-G01 already in existing (e.g. reachable via BFS)
    existing = {"N-G01": 2}
    updated = inject_zone2_nodes(existing, "supra", mock_db)

    assert updated["N-G01"] == 2  # original distance preserved, not overwritten


# ---- Full pipeline smoke test ----

def test_full_pipeline_priya():
    """
    Smoke test: Nurse Priya should end up with candidate set significantly smaller
    than total node count. No DB — uses all in-memory.
    """
    user = make_user()
    permissions = compile_permissions(user)

    # Simulate a set of nodes that would survive or be excluded
    nodes = [
        # Should pass all checks
        {"id": "N-O01", "org_id": "supra", "type": "CONSTRAINT", "title": "Post-Op Vitals",
         "content": "...", "importance": 0.94, "zone": 1, "status": "ACTIVE",
         "derivability_score": 0.35, "compliance_tags": [], "valid_until": None,
         "hierarchy_level_number": 10, "department": "ortho", "hierarchy_level_id": "HL-05-ORTHO"},
        # Should be excluded by Check 2 (MNPI, no clearance)
        {"id": "N-O11", "org_id": "supra", "type": "DECISION", "title": "Budget",
         "content": "...", "importance": 0.70, "zone": 1, "status": "ACTIVE",
         "derivability_score": 0.05, "compliance_tags": ["MNPI"], "valid_until": None,
         "hierarchy_level_number": 5, "department": "ortho", "hierarchy_level_id": "HL-05-ORTHO"},
        # Should be excluded by Check 4 (SUPERSEDED)
        {"id": "N-M08", "org_id": "supra", "type": "DECISION", "title": "Old Sepsis",
         "content": "...", "importance": 0.95, "zone": 1, "status": "SUPERSEDED",
         "derivability_score": 0.25, "compliance_tags": [], "valid_until": None,
         "hierarchy_level_number": 10, "department": "medicine", "hierarchy_level_id": "HL-05-MED"},
        # Should be excluded by Check 5 (high derivability)
        {"id": "N-D01", "org_id": "supra", "type": "FACT", "title": "What is TKR",
         "content": "...", "importance": 0.40, "zone": 1, "status": "ACTIVE",
         "derivability_score": 0.92, "compliance_tags": [], "valid_until": None,
         "hierarchy_level_number": 10, "department": "ortho", "hierarchy_level_id": "HL-05-ORTHO"},
    ]

    surviving, stage_counts = run_five_checks(nodes, user, permissions)

    assert stage_counts["after_check1"] == 4  # all same org
    assert stage_counts["after_check2"] == 3  # MNPI excluded
    # N-M08 is level 10 >= Priya ceiling 10 → passes Check 3 (excluded later by Check 4 as SUPERSEDED)
    assert stage_counts["after_check3"] == 3
    assert stage_counts["after_check4"] == 2  # N-M08 (SUPERSEDED) excluded
    assert stage_counts["after_check5"] == 1  # N-D01 (derivability 0.92) excluded
