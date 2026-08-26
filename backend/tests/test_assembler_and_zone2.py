"""
Tests: Candidate Assembler + Zone 2 Injector — Hardened
=========================================================
Covers annotation, compression_hint logic, sort order, zone 2 deduplication,
and edge cases for both modules.
"""

import pytest
from unittest.mock import MagicMock
from backend.pipeline.candidate_assembler import assemble_candidate_set
from backend.pipeline.zone2_injector import inject_zone2_nodes
from backend.models.candidate_set import CandidateNode


def make_node(**kwargs) -> dict:
    defaults = dict(
        id="N-TEST",
        org_id="supra",
        type="CONSTRAINT",
        title="Test Node",
        content="Some content about hospital protocols.",
        importance=0.80,
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


# ── CANDIDATE ASSEMBLER ──────────────────────────────────────────────────────

class TestCandidateAssembler:
    def test_empty_input_returns_empty(self):
        assert assemble_candidate_set([], {}) == []

    def test_returns_list_of_candidate_nodes(self):
        node = make_node(id="N-1")
        result = assemble_candidate_set([node], {"N-1": 0})
        assert isinstance(result, list)
        assert isinstance(result[0], CandidateNode)

    def test_distance_from_entry_set_correctly(self):
        node = make_node(id="N-1")
        result = assemble_candidate_set([node], {"N-1": 2})
        assert result[0].distance_from_entry == 2

    def test_missing_distance_defaults_to_999(self):
        node = make_node(id="N-1")
        result = assemble_candidate_set([node], {})
        assert result[0].distance_from_entry == 999

    def test_compression_hint_full_at_distance_0(self):
        node = make_node(id="N-1")
        result = assemble_candidate_set([node], {"N-1": 0})
        assert result[0].compression_hint == "FULL"

    def test_compression_hint_full_at_distance_1(self):
        node = make_node(id="N-1")
        result = assemble_candidate_set([node], {"N-1": 1})
        assert result[0].compression_hint == "FULL"

    def test_compression_hint_compressed_at_distance_2(self):
        node = make_node(id="N-1")
        result = assemble_candidate_set([node], {"N-1": 2})
        assert result[0].compression_hint == "COMPRESSED"

    def test_compression_hint_constraint_only_at_distance_3(self):
        node = make_node(id="N-1")
        result = assemble_candidate_set([node], {"N-1": 3})
        assert result[0].compression_hint == "CONSTRAINT_ONLY"

    def test_compression_hint_constraint_only_at_distance_10(self):
        node = make_node(id="N-1")
        result = assemble_candidate_set([node], {"N-1": 10})
        assert result[0].compression_hint == "CONSTRAINT_ONLY"

    def test_compression_hint_constraint_only_at_sentinel_999(self):
        # Zone 2 injected nodes get distance=999
        node = make_node(id="N-G01", zone=2)
        result = assemble_candidate_set([node], {"N-G01": 999})
        assert result[0].compression_hint == "CONSTRAINT_ONLY"

    def test_compression_hint_boundary_exactly_2(self):
        """Boundary: distance==2 is COMPRESSED, not CONSTRAINT_ONLY."""
        node = make_node(id="N-1")
        r2 = assemble_candidate_set([node], {"N-1": 2})
        r3 = assemble_candidate_set([make_node(id="N-2")], {"N-2": 3})
        assert r2[0].compression_hint == "COMPRESSED"
        assert r3[0].compression_hint == "CONSTRAINT_ONLY"

    def test_sorted_by_importance_descending(self):
        nodes = [
            make_node(id="N-LOW",  importance=0.30),
            make_node(id="N-HIGH", importance=0.95),
            make_node(id="N-MID",  importance=0.60),
        ]
        distances = {"N-LOW": 0, "N-HIGH": 0, "N-MID": 0}
        result = assemble_candidate_set(nodes, distances)
        assert result[0].id == "N-HIGH"
        assert result[1].id == "N-MID"
        assert result[2].id == "N-LOW"

    def test_tie_on_importance_sorted_by_distance_ascending(self):
        nodes = [
            make_node(id="N-FAR",   importance=0.80),
            make_node(id="N-CLOSE", importance=0.80),
        ]
        distances = {"N-FAR": 5, "N-CLOSE": 1}
        result = assemble_candidate_set(nodes, distances)
        assert result[0].id == "N-CLOSE"
        assert result[1].id == "N-FAR"

    def test_all_metadata_fields_populated(self):
        node = make_node(
            id="N-1", type="DECISION", title="My Title",
            content="My content", importance=0.75, zone=2,
            hierarchy_level_number=8, department="ortho",
        )
        result = assemble_candidate_set([node], {"N-1": 1})
        c = result[0]
        assert c.id == "N-1"
        assert c.type == "DECISION"
        assert c.title == "My Title"
        assert c.content == "My content"
        assert c.importance == 0.75
        assert c.zone == 2
        assert c.hierarchy_level == 8
        assert c.department == "ortho"
        assert c.compression_hint == "FULL"

    def test_importance_coerced_to_float(self):
        node = make_node(id="N-1", importance="0.95")
        result = assemble_candidate_set([node], {"N-1": 0})
        assert isinstance(result[0].importance, float)
        assert result[0].importance == 0.95

    def test_hierarchy_level_none_preserved(self):
        node = make_node(id="N-1", hierarchy_level_number=None)
        result = assemble_candidate_set([node], {"N-1": 0})
        assert result[0].hierarchy_level is None

    def test_department_none_preserved(self):
        node = make_node(id="N-G01", department=None, zone=2)
        result = assemble_candidate_set([node], {"N-G01": 999})
        assert result[0].department is None

    def test_multiple_nodes_all_annotated(self):
        nodes = [make_node(id=f"N-{i}") for i in range(5)]
        distances = {f"N-{i}": i for i in range(5)}
        result = assemble_candidate_set(nodes, distances)
        assert len(result) == 5
        hints = {c.compression_hint for c in result}
        # distances 0,1 → FULL; 2 → COMPRESSED; 3,4 → CONSTRAINT_ONLY
        assert "FULL" in hints
        assert "COMPRESSED" in hints
        assert "CONSTRAINT_ONLY" in hints

    def test_zone1_and_zone2_nodes_assembled_together(self):
        nodes = [
            make_node(id="N-Z1", zone=1, importance=0.90),
            make_node(id="N-Z2", zone=2, importance=0.98),
        ]
        distances = {"N-Z1": 0, "N-Z2": 999}
        result = assemble_candidate_set(nodes, distances)
        assert len(result) == 2
        assert result[0].id == "N-Z2"   # higher importance first


# ── ZONE 2 INJECTOR ──────────────────────────────────────────────────────────

class TestZone2Injector:
    def _make_db(self, zone2_ids: list[str]) -> MagicMock:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq \
               .return_value.execute.return_value.data = [{"id": i} for i in zone2_ids]
        return mock_db

    def test_empty_zone2_returns_unchanged(self):
        db = self._make_db([])
        existing = {"N-O01": 0}
        result = inject_zone2_nodes(existing, "supra", db)
        assert result == {"N-O01": 0}

    def test_new_zone2_nodes_added_at_sentinel_999(self):
        db = self._make_db(["N-G01", "N-G02"])
        result = inject_zone2_nodes({}, "supra", db)
        assert result["N-G01"] == 999
        assert result["N-G02"] == 999

    def test_existing_node_distance_not_overwritten(self):
        db = self._make_db(["N-G01"])
        existing = {"N-G01": 2}  # reachable via BFS at distance 2
        result = inject_zone2_nodes(existing, "supra", db)
        assert result["N-G01"] == 2   # BFS distance preserved

    def test_existing_non_zone2_nodes_preserved(self):
        db = self._make_db(["N-G01"])
        existing = {"N-O01": 0, "N-O02": 1}
        result = inject_zone2_nodes(existing, "supra", db)
        assert result["N-O01"] == 0
        assert result["N-O02"] == 1
        assert result["N-G01"] == 999

    def test_does_not_mutate_input_dict(self):
        db = self._make_db(["N-G01"])
        existing = {"N-O01": 0}
        original_copy = dict(existing)
        inject_zone2_nodes(existing, "supra", db)
        assert existing == original_copy   # input unchanged

    def test_multiple_zone2_nodes_all_added(self):
        zone2 = [f"N-G{i:02}" for i in range(10)]
        db = self._make_db(zone2)
        result = inject_zone2_nodes({}, "supra", db)
        assert len(result) == 10
        assert all(result[nid] == 999 for nid in zone2)

    def test_returns_new_dict(self):
        db = self._make_db(["N-G01"])
        existing = {"N-O01": 0}
        result = inject_zone2_nodes(existing, "supra", db)
        assert result is not existing

    def test_no_duplicates_when_zone2_already_in_bfs(self):
        """Zone 2 node already reachable via BFS — must appear exactly once."""
        db = self._make_db(["N-G01", "N-G02"])
        existing = {"N-G01": 3}  # G01 already found by BFS
        result = inject_zone2_nodes(existing, "supra", db)
        # G01 keeps BFS distance 3, G02 added at 999
        assert result["N-G01"] == 3
        assert result["N-G02"] == 999
        assert len(result) == 2
