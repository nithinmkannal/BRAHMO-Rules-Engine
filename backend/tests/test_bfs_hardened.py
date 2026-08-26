"""
Tests: BFS Traversal — Hardened
=================================
Covers upward traversal, root-down traversal, multi-parent DAG,
cycle resistance, empty graph, single node, and distance accuracy.
"""

import pytest
from unittest.mock import MagicMock
from backend.pipeline.bfs_traversal import bfs_upward


def make_db(levels: list[dict]) -> MagicMock:
    """Build a mock DB whose hierarchy_levels table returns the given rows."""
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = levels
    return mock_db


# ── UPWARD TRAVERSAL ─────────────────────────────────────────────────────────

class TestUpwardTraversal:
    def test_single_node_no_parents(self):
        db = make_db([{"id": "HL-ONLY", "parent_ids": []}])
        result = bfs_upward("HL-ONLY", "supra", db)
        assert result == {"HL-ONLY": 0}

    def test_linear_chain_distances(self):
        db = make_db([
            {"id": "HL-10", "parent_ids": ["HL-08"]},
            {"id": "HL-08", "parent_ids": ["HL-05"]},
            {"id": "HL-05", "parent_ids": ["HL-03"]},
            {"id": "HL-03", "parent_ids": ["HL-01"]},
            {"id": "HL-01", "parent_ids": []},
        ])
        result = bfs_upward("HL-10", "supra", db)
        assert result["HL-10"] == 0
        assert result["HL-08"] == 1
        assert result["HL-05"] == 2
        assert result["HL-03"] == 3
        assert result["HL-01"] == 4

    def test_entry_node_always_at_distance_0(self):
        db = make_db([
            {"id": "HL-ENTRY", "parent_ids": ["HL-PARENT"]},
            {"id": "HL-PARENT", "parent_ids": []},
        ])
        result = bfs_upward("HL-ENTRY", "supra", db)
        assert result["HL-ENTRY"] == 0

    def test_sibling_not_reachable_upward(self):
        """Walking up from HL-10-ORTHO-W should NOT reach HL-10-MED-W (different branch)."""
        db = make_db([
            {"id": "HL-10-ORTHO-W", "parent_ids": ["HL-08-ORTHO-GEN"]},
            {"id": "HL-10-MED-W",   "parent_ids": ["HL-08-MED-GEN"]},
            {"id": "HL-08-ORTHO-GEN", "parent_ids": ["HL-05-ORTHO"]},
            {"id": "HL-08-MED-GEN",   "parent_ids": ["HL-05-MED"]},
            {"id": "HL-05-ORTHO", "parent_ids": ["HL-03-CLIN"]},
            {"id": "HL-05-MED",   "parent_ids": ["HL-03-CLIN"]},
            {"id": "HL-03-CLIN",  "parent_ids": ["HL-01"]},
            {"id": "HL-01",       "parent_ids": []},
        ])
        result = bfs_upward("HL-10-ORTHO-W", "supra", db)
        assert "HL-10-MED-W" not in result
        assert "HL-08-MED-GEN" not in result
        assert "HL-05-MED" not in result
        # Shared ancestors ARE reachable
        assert "HL-03-CLIN" in result
        assert "HL-01" in result

    def test_child_nodes_not_reachable_upward(self):
        """BFS from L10 should not descend into L12 patient nodes."""
        db = make_db([
            {"id": "HL-12-PATIENT", "parent_ids": ["HL-10"]},
            {"id": "HL-10",         "parent_ids": ["HL-08"]},
            {"id": "HL-08",         "parent_ids": []},
        ])
        result = bfs_upward("HL-10", "supra", db)
        assert "HL-12-PATIENT" not in result

    def test_all_reachable_ancestors_included(self):
        db = make_db([
            {"id": "HL-10", "parent_ids": ["HL-08"]},
            {"id": "HL-08", "parent_ids": ["HL-05"]},
            {"id": "HL-05", "parent_ids": ["HL-01"]},
            {"id": "HL-01", "parent_ids": []},
        ])
        result = bfs_upward("HL-10", "supra", db)
        assert set(result.keys()) == {"HL-10", "HL-08", "HL-05", "HL-01"}


# ── MULTI-PARENT (DAG) ───────────────────────────────────────────────────────

class TestMultiParent:
    def test_node_with_two_parents_visited_once(self):
        """Post-TKR protocol has Ortho + Surgery as parents — must not be counted twice."""
        db = make_db([
            {"id": "HL-POST-TKR", "parent_ids": ["HL-05-ORTHO", "HL-05-SURG"]},
            {"id": "HL-05-ORTHO", "parent_ids": ["HL-03-CLIN"]},
            {"id": "HL-05-SURG",  "parent_ids": ["HL-03-CLIN"]},
            {"id": "HL-03-CLIN",  "parent_ids": ["HL-01"]},
            {"id": "HL-01",       "parent_ids": []},
        ])
        result = bfs_upward("HL-POST-TKR", "supra", db)
        # Visited exactly once each
        assert result.get("HL-POST-TKR") == 0
        assert result.get("HL-05-ORTHO") == 1
        assert result.get("HL-05-SURG") == 1
        assert result.get("HL-03-CLIN") == 2   # reached via both, distance = 2
        assert result.get("HL-01") == 3

    def test_shortest_path_wins_for_shared_ancestor(self):
        """When a node is reachable via multiple paths, BFS assigns shortest distance."""
        db = make_db([
            {"id": "HL-ENTRY",  "parent_ids": ["HL-A"]},
            {"id": "HL-A",      "parent_ids": ["HL-ROOT"]},
            {"id": "HL-B",      "parent_ids": ["HL-ROOT"]},  # sibling of A
            {"id": "HL-ROOT",   "parent_ids": []},
        ])
        result = bfs_upward("HL-ENTRY", "supra", db)
        # HL-ROOT reachable at distance 2 via HL-A (not via HL-B which is not reachable from entry)
        assert result["HL-ROOT"] == 2
        assert "HL-B" not in result

    def test_diamond_dag_visited_once(self):
        """Classic diamond: ENTRY → A,B → ROOT. ROOT must be visited once."""
        db = make_db([
            {"id": "HL-ENTRY", "parent_ids": ["HL-A", "HL-B"]},
            {"id": "HL-A",     "parent_ids": ["HL-ROOT"]},
            {"id": "HL-B",     "parent_ids": ["HL-ROOT"]},
            {"id": "HL-ROOT",  "parent_ids": []},
        ])
        result = bfs_upward("HL-ENTRY", "supra", db)
        assert result["HL-ROOT"] == 2
        # Each key appears exactly once (dict guarantees this)
        assert len([k for k in result if k == "HL-ROOT"]) == 1


# ── ROOT-DOWN TRAVERSAL (ADMIN) ──────────────────────────────────────────────

class TestRootDownTraversal:
    def test_root_node_reaches_all_children(self):
        """ADMIN enters at HL-01 (no parents) → should reach all descendants."""
        db = make_db([
            {"id": "HL-01",         "parent_ids": []},
            {"id": "HL-03-CLIN",    "parent_ids": ["HL-01"]},
            {"id": "HL-03-ADMIN",   "parent_ids": ["HL-01"]},
            {"id": "HL-05-ORTHO",   "parent_ids": ["HL-03-CLIN"]},
            {"id": "HL-05-MED",     "parent_ids": ["HL-03-CLIN"]},
            {"id": "HL-10-ORTHO-W", "parent_ids": ["HL-05-ORTHO"]},
        ])
        result = bfs_upward("HL-01", "supra", db)
        assert set(result.keys()) == {
            "HL-01", "HL-03-CLIN", "HL-03-ADMIN",
            "HL-05-ORTHO", "HL-05-MED", "HL-10-ORTHO-W"
        }

    def test_root_at_distance_0(self):
        db = make_db([{"id": "HL-01", "parent_ids": []}])
        result = bfs_upward("HL-01", "supra", db)
        assert result["HL-01"] == 0

    def test_root_child_distances(self):
        db = make_db([
            {"id": "HL-01",  "parent_ids": []},
            {"id": "HL-L2",  "parent_ids": ["HL-01"]},
            {"id": "HL-L3",  "parent_ids": ["HL-L2"]},
        ])
        result = bfs_upward("HL-01", "supra", db)
        assert result["HL-01"] == 0
        assert result["HL-L2"] == 1
        assert result["HL-L3"] == 2

    def test_root_traversal_not_triggered_for_node_with_parents(self):
        """A non-root with parents must NOT walk downward."""
        db = make_db([
            {"id": "HL-PARENT",    "parent_ids": []},
            {"id": "HL-MID",       "parent_ids": ["HL-PARENT"]},
            {"id": "HL-CHILD",     "parent_ids": ["HL-MID"]},
            {"id": "HL-SIBLING",   "parent_ids": ["HL-PARENT"]},
        ])
        # Enter at HL-MID (has parent HL-PARENT) → upward only → should NOT reach HL-CHILD
        result = bfs_upward("HL-MID", "supra", db)
        assert "HL-CHILD" not in result
        assert "HL-PARENT" in result
        assert "HL-SIBLING" not in result


# ── CYCLE RESISTANCE ─────────────────────────────────────────────────────────

class TestCycleResistance:
    def test_no_infinite_loop_on_accidental_cycle(self):
        """Visited set must prevent infinite loop even if a cycle exists in data."""
        db = make_db([
            {"id": "HL-A", "parent_ids": ["HL-B"]},
            {"id": "HL-B", "parent_ids": ["HL-C"]},
            {"id": "HL-C", "parent_ids": ["HL-A"]},  # cycle: A→B→C→A
        ])
        # This must terminate; result contains all three
        result = bfs_upward("HL-A", "supra", db)
        assert set(result.keys()) == {"HL-A", "HL-B", "HL-C"}

    def test_self_loop_does_not_cause_infinite_loop(self):
        db = make_db([
            {"id": "HL-SELF", "parent_ids": ["HL-SELF"]},  # self-loop
        ])
        result = bfs_upward("HL-SELF", "supra", db)
        assert "HL-SELF" in result

    def test_longer_cycle_terminates(self):
        db = make_db([
            {"id": f"HL-{i}", "parent_ids": [f"HL-{(i+1) % 10}"]}
            for i in range(10)
        ])
        result = bfs_upward("HL-0", "supra", db)
        assert len(result) == 10


# ── EMPTY / EDGE CASES ───────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_graph_returns_entry_only(self):
        db = make_db([])
        result = bfs_upward("HL-MISSING", "supra", db)
        # entry node is always added to visited even if not in adjacency
        assert result == {"HL-MISSING": 0}

    def test_entry_not_in_graph(self):
        """Entry node ID that doesn't exist in DB — should still return {entry: 0}."""
        db = make_db([
            {"id": "HL-OTHER", "parent_ids": []},
        ])
        result = bfs_upward("HL-UNKNOWN", "supra", db)
        assert result["HL-UNKNOWN"] == 0
        assert "HL-OTHER" not in result

    def test_node_with_empty_parent_ids(self):
        db = make_db([{"id": "HL-ROOT", "parent_ids": []}])
        result = bfs_upward("HL-ROOT", "supra", db)
        assert result == {"HL-ROOT": 0}

    def test_node_with_null_parent_ids(self):
        db = make_db([{"id": "HL-ROOT", "parent_ids": None}])
        result = bfs_upward("HL-ROOT", "supra", db)
        assert result == {"HL-ROOT": 0}

    def test_returns_dict(self):
        db = make_db([{"id": "HL-01", "parent_ids": []}])
        result = bfs_upward("HL-01", "supra", db)
        assert isinstance(result, dict)

    def test_large_linear_chain_terminates(self):
        """15-level linear chain must complete without recursion errors."""
        levels = [{"id": f"HL-{i:02}", "parent_ids": [f"HL-{i-1:02}"] if i > 0 else []}
                  for i in range(15)]
        db = make_db(levels)
        result = bfs_upward("HL-14", "supra", db)
        assert len(result) == 15
        assert result["HL-14"] == 0
        assert result["HL-00"] == 14
