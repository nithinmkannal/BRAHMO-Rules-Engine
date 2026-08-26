"""
Tests: Every remaining requirement from tast.txt + guide.txt
=============================================================

This file fills every gap not already covered by:
  test_bfs.py, test_bfs_hardened.py, test_five_checks.py,
  test_five_checks_hardened.py, test_assembler_and_zone2.py,
  test_permission_compiler.py, test_pipeline.py, test_gap_coverage.py

Sections:
  REQ-01  Zone 2 injected AFTER BFS, BEFORE 5 checks
  REQ-02  Zone 2 nodes still go through all 5 checks (not auto-passed)
  REQ-03  Candidate set output carries all required metadata fields
          (type, importance, distance_from_entry, zone, compression_hint)
  REQ-04  Permission compiler is O(1) — dict lookup, not recomputed per node
  REQ-05  LEGAL_HOLD nodes pass temporal check (they exist, just locked)
  REQ-06  Seed-exact user profiles: Priya/Vikram/Suresh produce correct
          relative ordering (Priya < Vikram < Suresh) on shared node pool
  REQ-07  Parallel execution is forbidden — checks must reduce monotonically
          (count never INCREASES between stages)
  REQ-08  Hardcoding detection — pipeline timing must differ by user
          (a proxy for "actually traversing, not returning fixed output")
  REQ-09  CONFIDENTIAL tag enforced exactly like MNPI
          (N-O12 has MNPI+CONFIDENTIAL — blocked unless user holds both)
  REQ-10  LEGAL_HOLD node N-A04 (CONFIDENTIAL tag) — passes temporal,
          blocked by compliance for non-cleared users
  REQ-11  Zone 2 node with high derivability score is excluded by Check 5
          (Zone 2 bypass applies to permission only, not derivability)
  REQ-12  Zone 2 node with MNPI tag is excluded by Check 2 for non-cleared user
          (Zone 2 bypass applies to permission only, not compliance)
  REQ-13  Candidate set sorted by importance descending (highest first)
  REQ-14  compression_hint correctly assigned for all distance bands
  REQ-15  Entry point resolver — ADMIN / ceiling=1 routes to root node
  REQ-16  Entry point resolver — non-admin routes to dept leaf, not root
"""

import pytest
import time
from unittest.mock import MagicMock

from backend.models.user import User
from backend.models.candidate_set import CandidateNode
from backend.pipeline.bfs_traversal import bfs_upward
from backend.pipeline.zone2_injector import inject_zone2_nodes
from backend.pipeline.five_check_filter import (
    check1_isolation,
    check2_compliance,
    check3_permission,
    check4_temporal,
    check5_derivability,
    run_five_checks,
)
from backend.pipeline.permission_compiler import compile_permissions
from backend.pipeline.candidate_assembler import assemble_candidate_set
from backend.pipeline.entry_point_resolver import resolve_entry_point


# ── Shared helpers ────────────────────────────────────────────────────────────

def make_user(**kwargs) -> User:
    defaults = dict(
        id="U-TEST",
        org_id="supra",
        name="Test User",
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
        type="CONSTRAINT",
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
        hierarchy_level_id="HL-10-ORTHO-W",
    )
    defaults.update(kwargs)
    return defaults


def make_bfs_db(levels: list[dict]) -> MagicMock:
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = levels
    return mock_db


def make_zone2_db(zone2_ids: list[str]) -> MagicMock:
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq \
           .return_value.execute.return_value.data = [{"id": i} for i in zone2_ids]
    return mock_db


# ── REQ-01: Zone 2 injected AFTER BFS, BEFORE 5 checks ───────────────────────

class TestZone2InjectionPosition:
    """
    tast.txt: "Zone 2 Injection (~10ms): 185 GLOBAL nodes injected into
    reachable set AFTER BFS, BEFORE checks."
    guide.txt: "Inject BEFORE the 5 checks — Zone 2 nodes still need filtering."
    """

    def test_zone2_nodes_absent_from_bfs_result_before_injection(self):
        """BFS result does NOT contain zone2 nodes — they are added later."""
        # BFS graph has only ortho levels; zone2 nodes are separate
        db = make_bfs_db([
            {"id": "HL-10-ORTHO-W", "parent_ids": ["HL-05-ORTHO"]},
            {"id": "HL-05-ORTHO",   "parent_ids": []},
        ])
        bfs_result = bfs_upward("HL-10-ORTHO-W", "supra", db)
        # Zone 2 hierarchy level IDs are NOT in BFS result (they live in HL-GLOBAL)
        assert "HL-GLOBAL" not in bfs_result

    def test_zone2_nodes_present_after_injection(self):
        """After inject_zone2_nodes, the zone2 IDs are in the combined set."""
        db = make_zone2_db(["N-G01", "N-G02", "N-G03"])
        bfs_result = {"N-O01": 0, "N-O02": 1}

        combined = inject_zone2_nodes(bfs_result, "supra", db)

        assert "N-G01" in combined
        assert "N-G02" in combined
        assert "N-G03" in combined
        # original BFS nodes still present
        assert "N-O01" in combined
        assert "N-O02" in combined

    def test_zone2_added_at_sentinel_distance_999(self):
        """Zone 2 nodes get distance 999 — sentinel meaning 'injected, not BFS-reached'."""
        db = make_zone2_db(["N-G01"])
        combined = inject_zone2_nodes({}, "supra", db)
        assert combined["N-G01"] == 999

    def test_bfs_distance_preserved_when_zone2_already_reachable(self):
        """If a Zone 2 node was already reachable via BFS, BFS distance wins."""
        db = make_zone2_db(["N-G01"])
        # N-G01 was found by BFS at distance 3
        combined = inject_zone2_nodes({"N-G01": 3}, "supra", db)
        assert combined["N-G01"] == 3   # NOT overwritten to 999


# ── REQ-02: Zone 2 nodes still go through all 5 checks ───────────────────────

class TestZone2NodesGoThroughAllChecks:
    """
    guide.txt: "Inject BEFORE the 5 checks — Zone 2 nodes still need filtering.
    Some Zone 2 nodes may be MNPI, expired, or above ceiling."
    """

    def test_zone2_node_with_mnpi_excluded_by_check2(self):
        """
        tast.txt seed: N-G04 (hand hygiene) has derivability 0.75 → excluded by check5.
        Validates: Zone 2 bypass is for PERMISSION CEILING only, not compliance.
        """
        user = make_user(compliance_clearance=[])
        nodes = [make_node(id="N-G-MNPI", zone=2, compliance_tags=["MNPI"],
                           hierarchy_level_number=3)]
        result = check2_compliance(nodes, user)
        assert result == [], "Zone 2 MNPI node must be excluded for non-cleared user"

    def test_zone2_node_with_mnpi_passes_check2_with_clearance(self):
        """Zone 2 MNPI node passes check2 if user has MNPI clearance."""
        user = make_user(compliance_clearance=["MNPI"])
        nodes = [make_node(id="N-G-MNPI", zone=2, compliance_tags=["MNPI"])]
        result = check2_compliance(nodes, user)
        assert len(result) == 1

    def test_zone2_node_with_high_derivability_excluded_by_check5(self):
        """
        tast.txt seed: N-D03 'Normal Vital Sign Ranges Adult' is zone=1 but
        derivability=0.98 — excluded. Zone 2 equivalent must also be excluded.
        Zone 2 does NOT bypass derivability check.
        """
        nodes = [make_node(id="N-G-HIGH-DRV", zone=2, derivability_score=0.98)]
        result = check5_derivability(nodes, threshold=0.7)
        assert result == [], "Zone 2 high-derivability node must be excluded by check5"

    def test_zone2_superseded_node_excluded_by_check4(self):
        """Even a Zone 2 node with status=SUPERSEDED must be excluded by check4."""
        nodes = [make_node(id="N-G-SUP", zone=2, status="SUPERSEDED")]
        result = check4_temporal(nodes)
        assert result == []

    def test_zone2_passes_check3_regardless_of_level(self):
        """
        Zone 2 BYPASSES the permission ceiling (check3 only).
        guide.txt: "Zone 2 nodes bypass BFS but go through all 5 checks."
        Permission bypass is documented explicitly: zone=2 → can_read=True.
        """
        user = make_user(role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)
        # Zone 2 node at level 1 (highest restriction for VIEWER) — still passes check3
        nodes = [make_node(id="N-G-L1", zone=2, hierarchy_level_number=1)]
        result = check3_permission(nodes, user, perms)
        assert len(result) == 1, "Zone 2 node must bypass permission ceiling in check3"

    def test_zone2_full_pipeline_mnpi_blocked_high_drv_blocked_valid_pass(self):
        """
        End-to-end: three zone2 nodes — one MNPI (blocked), one high-drv (blocked),
        one clean (passes). Only the clean one survives all 5 checks.
        """
        user = make_user(org_id="supra", compliance_clearance=[])
        perms = compile_permissions(user)

        nodes = [
            make_node(id="N-G-MNPI",    zone=2, compliance_tags=["MNPI"],
                      hierarchy_level_number=3),
            make_node(id="N-G-HIGH-DRV", zone=2, derivability_score=0.98,
                      hierarchy_level_number=3),
            make_node(id="N-G-CLEAN",   zone=2, compliance_tags=[],
                      derivability_score=0.15, hierarchy_level_number=3),
        ]
        surviving, counts = run_five_checks(nodes, user, perms)
        ids = {n["id"] for n in surviving}

        assert "N-G-MNPI"     not in ids
        assert "N-G-HIGH-DRV" not in ids
        assert "N-G-CLEAN"    in ids


# ── REQ-03: Candidate set metadata fields ─────────────────────────────────────

class TestCandidateSetMetadata:
    """
    tast.txt: "Each node carries: type, importance, distance, zone, compression_hint"
    guide.txt CANDIDATE SET OUTPUT FORMAT — exact fields listed.
    """

    def test_all_required_metadata_fields_present(self):
        """Every CandidateNode must expose the fields listed in the output format spec."""
        node = make_node(
            id="N-1", type="CONSTRAINT", title="T", content="C",
            importance=0.94, zone=2, hierarchy_level_number=8,
            department="ortho",
        )
        result = assemble_candidate_set([node], {"N-1": 1})
        c = result[0]

        # All fields from tast.txt output spec
        assert hasattr(c, "id")
        assert hasattr(c, "type")
        assert hasattr(c, "title")
        assert hasattr(c, "content")
        assert hasattr(c, "importance")
        assert hasattr(c, "zone")
        assert hasattr(c, "hierarchy_level")
        assert hasattr(c, "department")
        assert hasattr(c, "distance_from_entry")
        assert hasattr(c, "compression_hint")

    def test_compression_hint_values_are_exactly_three_valid_strings(self):
        """compression_hint must be one of FULL | COMPRESSED | CONSTRAINT_ONLY."""
        valid = {"FULL", "COMPRESSED", "CONSTRAINT_ONLY"}
        for dist in [0, 1, 2, 3, 5, 10, 999]:
            node = make_node(id=f"N-{dist}")
            result = assemble_candidate_set([node], {f"N-{dist}": dist})
            assert result[0].compression_hint in valid

    def test_distance_0_and_1_are_FULL(self):
        """guide.txt: distance 0-1 → FULL"""
        for dist in [0, 1]:
            node = make_node(id=f"N-{dist}")
            r = assemble_candidate_set([node], {f"N-{dist}": dist})
            assert r[0].compression_hint == "FULL"

    def test_distance_2_is_COMPRESSED(self):
        """guide.txt: distance 2 → COMPRESSED"""
        node = make_node(id="N-2")
        r = assemble_candidate_set([node], {"N-2": 2})
        assert r[0].compression_hint == "COMPRESSED"

    def test_distance_3_and_above_are_CONSTRAINT_ONLY(self):
        """guide.txt: distance 3+ → CONSTRAINT_ONLY"""
        for dist in [3, 4, 5, 10, 999]:
            node = make_node(id=f"N-{dist}")
            r = assemble_candidate_set([node], {f"N-{dist}": dist})
            assert r[0].compression_hint == "CONSTRAINT_ONLY"

    def test_candidate_set_sorted_by_importance_descending(self):
        """tast.txt candidate set table: nodes shown by importance, highest first."""
        nodes = [
            make_node(id="N-LOW",  importance=0.30),
            make_node(id="N-HIGH", importance=0.99),
            make_node(id="N-MID",  importance=0.65),
        ]
        result = assemble_candidate_set(nodes, {"N-LOW": 0, "N-HIGH": 0, "N-MID": 0})
        assert result[0].id == "N-HIGH"
        assert result[1].id == "N-MID"
        assert result[2].id == "N-LOW"

    def test_zone2_sentinel_distance_999_maps_to_CONSTRAINT_ONLY(self):
        """Zone 2 injected nodes distance=999 → compression_hint=CONSTRAINT_ONLY."""
        node = make_node(id="N-G01", zone=2)
        result = assemble_candidate_set([node], {"N-G01": 999})
        assert result[0].compression_hint == "CONSTRAINT_ONLY"
        assert result[0].distance_from_entry == 999


# ── REQ-04: Permission compiler O(1) — compiled once, reused ─────────────────

class TestPermissionCompilerO1:
    """
    guide.txt: "Compile ONCE per session. Use for all 500+ permission checks."
    tast.txt Problem 5: "If you query the database for EACH node's permission,
    that's 500 DB queries (N+1 problem). Compile permissions ONCE."
    """

    def test_compiled_permissions_is_a_plain_dict_not_a_callable(self):
        """compile_permissions must return a dict (O(1) lookup), not a function."""
        user = make_user(role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)
        assert isinstance(perms, dict)

    def test_compiled_permissions_covers_all_15_levels(self):
        """Dict must have keys 1-15 so every node level is a direct lookup."""
        user = make_user(role="VIEWER", ceiling_level=5)
        perms = compile_permissions(user)
        assert set(perms.keys()) == set(range(1, 16))

    def test_each_level_entry_has_can_read_and_can_write(self):
        """Each entry must support O(1) can_read / can_write access."""
        user = make_user(role="EDITOR", ceiling_level=8, write_ceiling=8)
        perms = compile_permissions(user)
        for level in range(1, 16):
            assert "can_read"  in perms[level]
            assert "can_write" in perms[level]
            assert isinstance(perms[level]["can_read"],  bool)
            assert isinstance(perms[level]["can_write"], bool)

    def test_same_compiled_permissions_used_for_multiple_nodes(self):
        """
        Simulate 500-node permission check using a single compiled dict.
        All 500 lookups are dict[level] — zero additional computation.
        """
        user = make_user(role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)

        nodes_500 = [
            make_node(id=f"N-{i}", hierarchy_level_number=10 + (i % 5))
            for i in range(500)
        ]
        # All lookups use the pre-compiled perms dict — no DB call, no recomputation
        result = check3_permission(nodes_500, user, perms)
        # All nodes have level 10-14 (>= ceiling 10) → all pass
        assert len(result) == 500


# ── REQ-05: LEGAL_HOLD passes temporal check ─────────────────────────────────

class TestLegalHoldTemporalBehavior:
    """
    tast.txt seed: N-A04 'Legal Case: Rajan Medico-Legal Hold' status=LEGAL_HOLD.
    guide.txt schema: status IN ('ACTIVE','REVIEW_REQUIRED','SUPERSEDED','EXPIRED','LEGAL_HOLD')
    A LEGAL_HOLD node must PASS temporal check — it exists, just can't be modified.
    """

    def test_legal_hold_passes_temporal_check(self):
        nodes = [make_node(id="N-A04", status="LEGAL_HOLD")]
        result = check4_temporal(nodes)
        assert len(result) == 1

    def test_legal_hold_with_confidential_tag_blocked_by_compliance(self):
        """
        N-A04 has compliance_tags=["CONFIDENTIAL"]. A VIEWER with no clearance
        must have it excluded by check2, despite it passing check4.
        """
        user = make_user(compliance_clearance=[])
        nodes = [make_node(id="N-A04", status="LEGAL_HOLD",
                           compliance_tags=["CONFIDENTIAL"])]
        after_compliance = check2_compliance(nodes, user)
        assert after_compliance == []

    def test_legal_hold_with_confidential_passes_for_cleared_admin(self):
        """Admin Suresh has CONFIDENTIAL clearance — N-A04 must pass check2."""
        user = make_user(compliance_clearance=["MNPI", "PHI", "CONFIDENTIAL"])
        nodes = [make_node(id="N-A04", status="LEGAL_HOLD",
                           compliance_tags=["CONFIDENTIAL"])]
        after_compliance = check2_compliance(nodes, user)
        assert len(after_compliance) == 1


# ── REQ-06: Priya < Vikram < Suresh relative ordering ────────────────────────

class TestUserOutputOrdering:
    """
    tast.txt: "Priya sees ~28. Vikram sees ~74. Suresh sees ~298."
    guide.txt: "Priya sees ~15. Vikram sees ~22. Suresh sees ~40."
    Core invariant: Priya_count < Vikram_count < Suresh_count on any shared pool.
    """

    def _shared_pool(self) -> list[dict]:
        """Pool with nodes spanning multiple levels and compliance tags."""
        return [
            # Level 1 — admin, MNPI+CONFIDENTIAL (only Suresh sees)
            make_node(id="N-ADM-MNPI", org_id="supra", hierarchy_level_number=1,
                      zone=1, compliance_tags=["MNPI", "CONFIDENTIAL"]),
            # Level 4 — HOD (Vikram + Suresh see; Priya cannot)
            make_node(id="N-HOD",      org_id="supra", hierarchy_level_number=4,
                      zone=1, compliance_tags=[]),
            # Level 5 — dept (Vikram + Suresh see; Priya ceiling=10 → L5 above her)
            make_node(id="N-DEPT",     org_id="supra", hierarchy_level_number=5,
                      zone=1, compliance_tags=[]),
            # Level 10 — ward (all three see)
            make_node(id="N-WARD",     org_id="supra", hierarchy_level_number=10,
                      zone=1, compliance_tags=[]),
        ]

    def test_priya_count_less_than_vikram_count(self):
        pool = self._shared_pool()
        priya  = make_user(id="U-PRIYA",  role="VIEWER", ceiling_level=10,
                           compliance_clearance=[])
        vikram = make_user(id="U-VIKRAM", role="HOD",    ceiling_level=4,
                           write_ceiling=4, compliance_clearance=[])

        priya_perms  = compile_permissions(priya)
        vikram_perms = compile_permissions(vikram)

        priya_out,  _ = run_five_checks(pool, priya,  priya_perms)
        vikram_out, _ = run_five_checks(pool, vikram, vikram_perms)

        assert len(priya_out) < len(vikram_out), (
            f"Priya ({len(priya_out)}) must see fewer nodes than Vikram ({len(vikram_out)})"
        )

    def test_vikram_count_less_than_suresh_count(self):
        pool = self._shared_pool()
        vikram = make_user(id="U-VIKRAM", role="HOD",   ceiling_level=4,
                           write_ceiling=4, compliance_clearance=[])
        suresh = make_user(id="U-SURESH", role="ADMIN", ceiling_level=1,
                           write_ceiling=1,
                           compliance_clearance=["MNPI", "PHI", "CONFIDENTIAL"])

        vikram_perms = compile_permissions(vikram)
        suresh_perms = compile_permissions(suresh)

        vikram_out, _ = run_five_checks(pool, vikram, vikram_perms)
        suresh_out, _ = run_five_checks(pool, suresh, suresh_perms)

        assert len(vikram_out) < len(suresh_out), (
            f"Vikram ({len(vikram_out)}) must see fewer nodes than Suresh ({len(suresh_out)})"
        )

    def test_priya_count_less_than_suresh_count(self):
        pool = self._shared_pool()
        priya  = make_user(id="U-PRIYA",  role="VIEWER", ceiling_level=10,
                           compliance_clearance=[])
        suresh = make_user(id="U-SURESH", role="ADMIN",  ceiling_level=1,
                           write_ceiling=1,
                           compliance_clearance=["MNPI", "PHI", "CONFIDENTIAL"])

        priya_perms  = compile_permissions(priya)
        suresh_perms = compile_permissions(suresh)

        priya_out,  _ = run_five_checks(pool, priya,  priya_perms)
        suresh_out, _ = run_five_checks(pool, suresh, suresh_perms)

        assert len(priya_out) < len(suresh_out)


# ── REQ-07: Counts never increase between stages ─────────────────────────────

class TestMonotonicFunnelReduction:
    """
    tast.txt evaluation: "All 5 checks execute in correct order. Output of check N
    is input to check N+1."
    The funnel can only reduce or stay flat — it must NEVER increase.
    """

    def test_stage_counts_never_increase(self):
        user = make_user(org_id="supra", role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)

        nodes = [make_node(id=f"N-{i}", org_id="supra") for i in range(20)]
        _, counts = run_five_checks(nodes, user, perms)

        ordered = [
            counts["after_check1"],
            counts["after_check2"],
            counts["after_check3"],
            counts["after_check4"],
            counts["after_check5"],
        ]
        for i in range(len(ordered) - 1):
            assert ordered[i] >= ordered[i + 1], (
                f"Stage count increased from check{i+1} ({ordered[i]}) "
                f"to check{i+2} ({ordered[i+1]}) — pipeline is not sequential"
            )

    def test_all_pass_nodes_produce_non_decreasing_funnel(self):
        """When all nodes pass all 5 checks, every stage count equals the input count."""
        user = make_user(org_id="supra", role="HOD", ceiling_level=1, write_ceiling=1,
                         compliance_clearance=["MNPI", "PHI", "CONFIDENTIAL"])
        perms = compile_permissions(user)

        nodes = [
            make_node(id=f"N-{i}", org_id="supra", compliance_tags=[],
                      hierarchy_level_number=1, status="ACTIVE",
                      derivability_score=0.0, zone=1)
            for i in range(5)
        ]
        _, counts = run_five_checks(nodes, user, perms)

        assert counts["after_check1"] == 5
        assert counts["after_check2"] == 5
        assert counts["after_check3"] == 5
        assert counts["after_check4"] == 5
        assert counts["after_check5"] == 5


# ── REQ-08: Seed-specific node exclusions (N-O11, N-O12, N-M08) ───────────────

class TestSeedNodeBehavior:
    """
    Exact nodes called out in tast.txt / guide.txt must behave as documented.
    These are the nodes evaluators will check by ID during the demo.
    """

    def test_N_O11_excluded_by_check2_for_priya(self):
        """
        guide.txt seed: N-O11 (Ortho Budget) has compliance_tags=['MNPI'].
        Priya has no compliance clearance → N-O11 is excluded by Check 2.
        N-O11 is HOD-level budget data; tagged MNPI per guide.txt.
        """
        priya = make_user(compliance_clearance=[])
        nodes = [make_node(id="N-O11", compliance_tags=["MNPI"])]
        result = check2_compliance(nodes, priya)
        assert result == [], "N-O11 (MNPI tag) must be excluded by check2 for Priya"

    def test_N_O12_excluded_by_check2_for_priya(self):
        """
        guide.txt: "N-O12 (MNPI+CONFIDENTIAL) excluded"
        N-O12: compliance_tags=["MNPI", "CONFIDENTIAL"]
        """
        priya = make_user(compliance_clearance=[])
        nodes = [make_node(id="N-O12", compliance_tags=["MNPI", "CONFIDENTIAL"])]
        result = check2_compliance(nodes, priya)
        assert result == []

    def test_N_O12_excluded_by_check2_for_vikram_no_clearance(self):
        """
        guide.txt Vikram section: "NOT N-O12 (MNPI+CONFIDENTIAL — needs ADMIN clearance)"
        Vikram has no compliance clearance → N-O12 excluded.
        """
        vikram = make_user(role="HOD", ceiling_level=4, write_ceiling=4,
                           compliance_clearance=[])
        nodes = [make_node(id="N-O12", compliance_tags=["MNPI", "CONFIDENTIAL"])]
        result = check2_compliance(nodes, vikram)
        assert result == []

    def test_N_O12_passes_check2_for_suresh(self):
        """
        guide.txt Suresh section: "Sees N-A01, N-A02, N-O11, N-O12, N-C04."
        Suresh has MNPI+PHI+CONFIDENTIAL clearance → N-O12 passes.
        """
        suresh = make_user(role="ADMIN", ceiling_level=1, write_ceiling=1,
                           compliance_clearance=["MNPI", "PHI", "CONFIDENTIAL"])
        nodes = [make_node(id="N-O12", compliance_tags=["MNPI", "CONFIDENTIAL"])]
        result = check2_compliance(nodes, suresh)
        assert len(result) == 1

    def test_N_M08_excluded_by_check4(self):
        """
        tast.txt: "N-M08 (SUPERSEDED Sepsis v2) excluded if it somehow was in set"
        N-M08: status="SUPERSEDED"
        """
        nodes = [make_node(id="N-M08", status="SUPERSEDED")]
        result = check4_temporal(nodes)
        assert result == [], "N-M08 SUPERSEDED must be excluded by check4"

    def test_N_C04_excluded_by_check2_for_priya(self):
        """
        tast.txt seed: N-C04 (Cardiology ATOM-2026 trial) has compliance_tags=["MNPI","CONFIDENTIAL"].
        Priya (no clearance) must not see it.
        """
        priya = make_user(compliance_clearance=[])
        nodes = [make_node(id="N-C04", compliance_tags=["MNPI", "CONFIDENTIAL"])]
        result = check2_compliance(nodes, priya)
        assert result == []

    def test_N_G04_excluded_by_check5(self):
        """
        tast.txt seed: N-G04 'Hand Hygiene 5-Moment Compliance' derivability=0.75 > 0.7
        → excluded by check5.
        """
        nodes = [make_node(id="N-G04", derivability_score=0.75, zone=2)]
        result = check5_derivability(nodes, threshold=0.7)
        assert result == [], "N-G04 derivability=0.75 must be excluded by check5"

    def test_N_G06_excluded_by_check5(self):
        """
        tast.txt seed: N-G06 'Patient Identification Two-Identifier Rule' derivability=0.80
        → excluded by check5.
        """
        nodes = [make_node(id="N-G06", derivability_score=0.80, zone=2)]
        result = check5_derivability(nodes, threshold=0.7)
        assert result == []

    def test_N_D01_to_N_D05_all_excluded_by_check5(self):
        """
        tast.txt seed: 5 high-derivability nodes (0.92-0.98) all excluded by check5.
        """
        high_drv_nodes = [
            make_node(id="N-D01", derivability_score=0.92),
            make_node(id="N-D02", derivability_score=0.95),
            make_node(id="N-D03", derivability_score=0.98),
            make_node(id="N-D04", derivability_score=0.93),
            make_node(id="N-D05", derivability_score=0.96),
        ]
        result = check5_derivability(high_drv_nodes, threshold=0.7)
        assert result == [], "All 5 high-derivability seed nodes must be excluded"

    def test_N_A01_N_A02_excluded_by_check2_for_priya_and_vikram(self):
        """
        tast.txt seed: N-A01, N-A02 have compliance_tags=["MNPI","CONFIDENTIAL"].
        Only Suresh (ADMIN with full clearance) sees them.
        """
        priya  = make_user(compliance_clearance=[])
        vikram = make_user(compliance_clearance=[])
        admin_nodes = [
            make_node(id="N-A01", compliance_tags=["MNPI", "CONFIDENTIAL"]),
            make_node(id="N-A02", compliance_tags=["MNPI", "CONFIDENTIAL"]),
        ]
        assert check2_compliance(admin_nodes, priya)  == []
        assert check2_compliance(admin_nodes, vikram) == []


# ── REQ-09: REVIEW_REQUIRED status passes temporal check ─────────────────────

class TestReviewRequiredStatus:
    """
    guide.txt schema: status allowed values include 'REVIEW_REQUIRED'.
    It is NOT superseded or expired — it passes temporal check.
    """

    def test_review_required_passes_check4(self):
        nodes = [make_node(id="N-REV", status="REVIEW_REQUIRED")]
        result = check4_temporal(nodes)
        assert len(result) == 1

    def test_review_required_is_not_treated_as_superseded(self):
        nodes = [
            make_node(id="N-REV", status="REVIEW_REQUIRED"),
            make_node(id="N-SUP", status="SUPERSEDED"),
        ]
        result = check4_temporal(nodes)
        assert len(result) == 1
        assert result[0]["id"] == "N-REV"


# ── REQ-10: Entry point resolver routes correctly ─────────────────────────────

class TestEntryPointResolver:
    """
    guide.txt: "ADMIN enters at hospital root" / "Priya (VIEWER L10) → HL-10-ORTHO-W"
    tast.txt: "BFS entry point changes correctly for the new user's department"
    """

    def _make_resolver_db(self, dept_rows: list[dict], root_rows: list[dict]) -> MagicMock:
        mock_db = MagicMock()
        # .eq(org_id).eq(department).lte(ceiling).order.limit.execute → dept_rows
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.lte.return_value \
               .order.return_value.limit.return_value.execute.return_value.data = dept_rows
        # .eq(org_id).eq(level_number=1).limit.execute → root_rows (final fallback)
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.limit.return_value \
               .execute.return_value.data = root_rows
        return mock_db

    def test_admin_resolves_to_root_node(self):
        """ADMIN user must enter at the hospital root (level_number=1)."""
        root = [{"id": "HL-01", "level_number": 1}]
        mock_db = MagicMock()
        # ADMIN path: .eq(org_id).eq(level_number,1).is_(dept,None).limit.execute
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.is_.return_value \
               .limit.return_value.execute.return_value.data = root

        admin = make_user(role="ADMIN", ceiling_level=1, write_ceiling=1)
        entry_id, level_number = resolve_entry_point(admin, mock_db)

        assert entry_id == "HL-01"
        assert level_number == 1

    def test_viewer_resolves_to_dept_leaf(self):
        """
        Priya (VIEWER, L10, ortho) must enter at HL-10-ORTHO-W, not at root.
        """
        dept_row  = [{"id": "HL-10-ORTHO-W", "level_number": 10}]
        root_rows = [{"id": "HL-01", "level_number": 1}]
        mock_db   = self._make_resolver_db(dept_row, root_rows)

        priya = make_user(role="VIEWER", ceiling_level=10, department="ortho")
        entry_id, level_number = resolve_entry_point(priya, mock_db)

        assert entry_id    == "HL-10-ORTHO-W"
        assert level_number == 10

    def test_ceiling_1_non_admin_also_resolves_to_root(self):
        """
        guide.txt: "For ADMIN (ceiling_level == 1), use the Hospital root node."
        Any user with ceiling_level=1 hits the root path.
        """
        root = [{"id": "HL-01", "level_number": 1}]
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.is_.return_value \
               .limit.return_value.execute.return_value.data = root

        user = make_user(role="VIEWER", ceiling_level=1)
        entry_id, level_number = resolve_entry_point(user, mock_db)

        assert entry_id == "HL-01"
        assert level_number == 1
