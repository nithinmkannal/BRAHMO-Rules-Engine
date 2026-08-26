"""
Tests: Five-Check Filter — Hardened
=====================================
Edge cases for all 5 checks: empty inputs, boundary values, mixed
compliance tags, zone 2 bypass, temporal edge cases, sequential ordering.
"""

import pytest
from datetime import datetime, timezone, timedelta
from backend.models.user import User
from backend.pipeline.five_check_filter import (
    check1_isolation,
    check2_compliance,
    check3_permission,
    check4_temporal,
    check5_derivability,
    run_five_checks,
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


# ── CHECK 1: ISOLATION ───────────────────────────────────────────────────────

class TestCheck1Isolation:
    def test_empty_input(self):
        assert check1_isolation([], make_user()) == []

    def test_all_same_org_pass(self):
        nodes = [make_node(id=f"N-{i}", org_id="supra") for i in range(5)]
        assert len(check1_isolation(nodes, make_user())) == 5

    def test_all_wrong_org_excluded(self):
        nodes = [make_node(org_id="other_hospital")]
        assert check1_isolation(nodes, make_user()) == []

    def test_mixed_orgs(self):
        nodes = [
            make_node(id="N-SUPRA", org_id="supra"),
            make_node(id="N-OTHER", org_id="apollo"),
            make_node(id="N-OTHER2", org_id="max_healthcare"),
        ]
        result = check1_isolation(nodes, make_user(org_id="supra"))
        assert len(result) == 1
        assert result[0]["id"] == "N-SUPRA"

    def test_isolation_uses_user_org_not_hardcoded(self):
        # User from a different org — only their org's nodes pass
        nodes = [
            make_node(id="N-APOLLO", org_id="apollo"),
            make_node(id="N-SUPRA", org_id="supra"),
        ]
        result = check1_isolation(nodes, make_user(org_id="apollo"))
        assert len(result) == 1
        assert result[0]["id"] == "N-APOLLO"

    def test_preserves_node_order(self):
        ids = ["N-3", "N-1", "N-2"]
        nodes = [make_node(id=i, org_id="supra") for i in ids]
        result = check1_isolation(nodes, make_user())
        assert [n["id"] for n in result] == ids


# ── CHECK 2: COMPLIANCE ──────────────────────────────────────────────────────

class TestCheck2Compliance:
    def test_empty_input(self):
        assert check2_compliance([], make_user()) == []

    def test_no_tags_always_passes(self):
        nodes = [make_node(compliance_tags=[]), make_node(compliance_tags=None)]
        result = check2_compliance(nodes, make_user(compliance_clearance=[]))
        assert len(result) == 2

    def test_single_tag_blocked_without_clearance(self):
        nodes = [make_node(compliance_tags=["MNPI"])]
        assert check2_compliance(nodes, make_user(compliance_clearance=[])) == []

    def test_single_tag_passes_with_clearance(self):
        nodes = [make_node(compliance_tags=["MNPI"])]
        assert len(check2_compliance(nodes, make_user(compliance_clearance=["MNPI"]))) == 1

    def test_multi_tag_requires_all_clearances(self):
        # Node has MNPI + CONFIDENTIAL → user needs BOTH
        nodes = [make_node(compliance_tags=["MNPI", "CONFIDENTIAL"])]
        # Only MNPI clearance → fail
        assert check2_compliance(nodes, make_user(compliance_clearance=["MNPI"])) == []
        # Both clearances → pass
        assert len(check2_compliance(
            nodes, make_user(compliance_clearance=["MNPI", "CONFIDENTIAL"]))) == 1

    def test_extra_clearance_does_not_hurt(self):
        nodes = [make_node(compliance_tags=["MNPI"])]
        # User has more clearance than needed
        result = check2_compliance(
            nodes, make_user(compliance_clearance=["MNPI", "PHI", "CONFIDENTIAL"]))
        assert len(result) == 1

    def test_phi_tag_blocked(self):
        nodes = [make_node(compliance_tags=["PHI"])]
        assert check2_compliance(nodes, make_user(compliance_clearance=[])) == []
        assert len(check2_compliance(nodes, make_user(compliance_clearance=["PHI"]))) == 1

    def test_three_tags_partial_clearance(self):
        nodes = [make_node(compliance_tags=["MNPI", "PHI", "CONFIDENTIAL"])]
        assert check2_compliance(nodes, make_user(compliance_clearance=["MNPI", "PHI"])) == []

    def test_admin_full_clearance_passes_all(self):
        nodes = [
            make_node(id="N-1", compliance_tags=["MNPI"]),
            make_node(id="N-2", compliance_tags=["PHI"]),
            make_node(id="N-3", compliance_tags=["MNPI", "CONFIDENTIAL"]),
            make_node(id="N-4", compliance_tags=[]),
        ]
        result = check2_compliance(
            nodes, make_user(compliance_clearance=["MNPI", "PHI", "CONFIDENTIAL"]))
        assert len(result) == 4

    def test_empty_clearance_blocks_any_tag(self):
        for tag in ["MNPI", "PHI", "CONFIDENTIAL"]:
            nodes = [make_node(compliance_tags=[tag])]
            assert check2_compliance(nodes, make_user(compliance_clearance=[])) == []

    def test_compliance_tags_none_treated_as_empty(self):
        nodes = [make_node(compliance_tags=None)]
        result = check2_compliance(nodes, make_user(compliance_clearance=[]))
        assert len(result) == 1


# ── CHECK 3: PERMISSION ──────────────────────────────────────────────────────

class TestCheck3Permission:
    def test_empty_input(self):
        user = make_user(role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)
        assert check3_permission([], user, perms) == []

    def test_viewer_sees_at_ceiling(self):
        user = make_user(role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)
        nodes = [make_node(id="N-10", hierarchy_level_number=10)]
        assert len(check3_permission(nodes, user, perms)) == 1

    def test_viewer_blocked_above_ceiling(self):
        user = make_user(role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)
        nodes = [make_node(id="N-5", hierarchy_level_number=5)]
        assert check3_permission(nodes, user, perms) == []

    def test_viewer_sees_deeper_levels(self):
        user = make_user(role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)
        nodes = [make_node(id="N-12", hierarchy_level_number=12),
                 make_node(id="N-15", hierarchy_level_number=15)]
        result = check3_permission(nodes, user, perms)
        assert len(result) == 2

    def test_hod_sees_all_levels(self):
        user = make_user(role="HOD", ceiling_level=4, write_ceiling=4)
        perms = compile_permissions(user)
        nodes = [make_node(id=f"N-{l}", hierarchy_level_number=l) for l in range(1, 16)]
        result = check3_permission(nodes, user, perms)
        assert len(result) == 15

    def test_admin_sees_all_levels(self):
        user = make_user(role="ADMIN", ceiling_level=1, write_ceiling=1)
        perms = compile_permissions(user)
        nodes = [make_node(id=f"N-{l}", hierarchy_level_number=l) for l in range(1, 16)]
        result = check3_permission(nodes, user, perms)
        assert len(result) == 15

    def test_zone2_node_bypasses_permission_ceiling(self):
        # Priya ceiling=10, but zone=2 node at level 3 should still pass
        user = make_user(role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)
        nodes = [make_node(id="N-GLOBAL", zone=2, hierarchy_level_number=3)]
        result = check3_permission(nodes, user, perms)
        assert len(result) == 1, "Zone 2 nodes must bypass permission ceiling"

    def test_zone2_bypass_applies_regardless_of_level(self):
        user = make_user(role="VIEWER", ceiling_level=12)
        perms = compile_permissions(user)
        # Zone 2 node at level 1 (most restricted) — still passes
        nodes = [make_node(id="N-G", zone=2, hierarchy_level_number=1)]
        assert len(check3_permission(nodes, user, perms)) == 1

    def test_none_hierarchy_level_passes(self):
        user = make_user(role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)
        nodes = [make_node(hierarchy_level_number=None)]
        result = check3_permission(nodes, user, perms)
        assert len(result) == 1

    def test_boundary_one_below_ceiling_blocked(self):
        user = make_user(role="VIEWER", ceiling_level=8)
        perms = compile_permissions(user)
        below = make_node(id="N-7",  hierarchy_level_number=7)
        at    = make_node(id="N-8",  hierarchy_level_number=8)
        above = make_node(id="N-9",  hierarchy_level_number=9)
        result = check3_permission([below, at, above], user, perms)
        ids = {n["id"] for n in result}
        assert "N-7" not in ids
        assert "N-8" in ids
        assert "N-9" in ids

    def test_mixed_zone_levels(self):
        user = make_user(role="VIEWER", ceiling_level=10)
        perms = compile_permissions(user)
        nodes = [
            make_node(id="N-Z2-LOW",  zone=2, hierarchy_level_number=3),   # zone2 → pass
            make_node(id="N-Z1-HIGH", zone=1, hierarchy_level_number=3),   # zone1 L3 → blocked
            make_node(id="N-Z1-OK",   zone=1, hierarchy_level_number=10),  # zone1 L10 → pass
        ]
        result = check3_permission(nodes, user, perms)
        ids = {n["id"] for n in result}
        assert "N-Z2-LOW" in ids
        assert "N-Z1-HIGH" not in ids
        assert "N-Z1-OK" in ids


# ── CHECK 4: TEMPORAL ────────────────────────────────────────────────────────

class TestCheck4Temporal:
    def test_empty_input(self):
        assert check4_temporal([]) == []

    def test_active_node_passes(self):
        assert len(check4_temporal([make_node(status="ACTIVE")])) == 1

    def test_superseded_excluded(self):
        assert check4_temporal([make_node(status="SUPERSEDED")]) == []

    def test_expired_status_excluded(self):
        assert check4_temporal([make_node(status="EXPIRED")]) == []

    def test_review_required_passes(self):
        # REVIEW_REQUIRED is not SUPERSEDED — still passes temporal check
        assert len(check4_temporal([make_node(status="REVIEW_REQUIRED")])) == 1

    def test_legal_hold_passes(self):
        assert len(check4_temporal([make_node(status="LEGAL_HOLD")])) == 1

    def test_valid_until_in_future_passes(self):
        future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        assert len(check4_temporal([make_node(valid_until=future)])) == 1

    def test_valid_until_in_past_excluded(self):
        past = "2020-06-01T00:00:00+00:00"
        assert check4_temporal([make_node(valid_until=past)]) == []

    def test_valid_until_exact_boundary_is_excluded(self):
        # A date well in the past
        ancient = "2000-01-01T00:00:00+00:00"
        assert check4_temporal([make_node(valid_until=ancient)]) == []

    def test_valid_until_none_passes(self):
        # None = no expiry = passes
        assert len(check4_temporal([make_node(valid_until=None)])) == 1

    def test_valid_until_Z_suffix_parsed_correctly(self):
        # Some Supabase responses use Z instead of +00:00
        past_z = "2020-01-01T00:00:00Z"
        future_z = (datetime.now(timezone.utc) + timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        assert check4_temporal([make_node(valid_until=past_z)]) == []
        assert len(check4_temporal([make_node(valid_until=future_z)])) == 1

    def test_superseded_overrides_valid_valid_until(self):
        # Even if valid_until is in the future, SUPERSEDED is still excluded
        future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        nodes = [make_node(status="SUPERSEDED", valid_until=future)]
        assert check4_temporal(nodes) == []

    def test_mixed_statuses(self):
        nodes = [
            make_node(id="N-ACTIVE",    status="ACTIVE"),
            make_node(id="N-SUP",       status="SUPERSEDED"),
            make_node(id="N-EXPIRED",   status="EXPIRED"),
            make_node(id="N-HOLD",      status="LEGAL_HOLD"),
            make_node(id="N-REVIEW",    status="REVIEW_REQUIRED"),
            make_node(id="N-PAST",      valid_until="2019-01-01T00:00:00+00:00"),
        ]
        result = check4_temporal(nodes)
        ids = {n["id"] for n in result}
        assert ids == {"N-ACTIVE", "N-HOLD", "N-REVIEW"}


# ── CHECK 5: DERIVABILITY ────────────────────────────────────────────────────

class TestCheck5Derivability:
    def test_empty_input(self):
        assert check5_derivability([]) == []

    def test_low_score_passes(self):
        nodes = [make_node(derivability_score=0.0),
                 make_node(derivability_score=0.69)]
        assert len(check5_derivability(nodes, threshold=0.7)) == 2

    def test_exact_threshold_excluded(self):
        # score must be STRICTLY LESS THAN threshold
        assert check5_derivability([make_node(derivability_score=0.70)], threshold=0.7) == []

    def test_above_threshold_excluded(self):
        nodes = [make_node(derivability_score=0.71),
                 make_node(derivability_score=0.99),
                 make_node(derivability_score=1.0)]
        assert check5_derivability(nodes, threshold=0.7) == []

    def test_custom_threshold(self):
        # Org with lower threshold (stricter)
        nodes = [make_node(id="N-LOW",  derivability_score=0.5),
                 make_node(id="N-HIGH", derivability_score=0.6)]
        result = check5_derivability(nodes, threshold=0.55)
        assert len(result) == 1
        assert result[0]["id"] == "N-LOW"

    def test_threshold_1_0_passes_everything(self):
        # Threshold of 1.0 means nothing is excluded (score is always < 1.0)
        nodes = [make_node(derivability_score=0.99)]
        assert len(check5_derivability(nodes, threshold=1.0)) == 1

    def test_threshold_0_0_excludes_everything_nonzero(self):
        nodes = [make_node(derivability_score=0.01)]
        assert check5_derivability(nodes, threshold=0.0) == []

    def test_missing_score_defaults_to_zero(self):
        # Node without derivability_score field → treated as 0.0 → passes
        node = {k: v for k, v in make_node().items() if k != "derivability_score"}
        result = check5_derivability([node], threshold=0.7)
        assert len(result) == 1

    def test_score_as_string_coerced(self):
        # Supabase may return decimals as strings
        nodes = [make_node(derivability_score="0.92")]
        assert check5_derivability(nodes, threshold=0.7) == []

    def test_score_zero_always_passes(self):
        nodes = [make_node(derivability_score=0.0)]
        assert len(check5_derivability(nodes, threshold=0.7)) == 1


# ── SEQUENTIAL ORDERING ──────────────────────────────────────────────────────

class TestSequentialOrdering:
    """Verifies that check N+1 receives the output of check N, not the original input."""

    def test_check2_does_not_see_nodes_excluded_by_check1(self):
        """A wrong-org MNPI node that slips to check2 should not be there at all."""
        user = make_user(org_id="supra", compliance_clearance=["MNPI"])
        perms = compile_permissions(user)
        nodes = [
            make_node(id="N-WRONG-ORG", org_id="other", compliance_tags=["MNPI"]),
            make_node(id="N-OK",        org_id="supra", compliance_tags=[]),
        ]
        surviving, counts = run_five_checks(nodes, user, perms)
        assert counts["after_check1"] == 1
        assert counts["after_check2"] == 1
        assert all(n["id"] == "N-OK" for n in surviving)

    def test_check3_does_not_see_nodes_excluded_by_check2(self):
        """MNPI-blocked node at readable level should not survive to check3."""
        user = make_user(role="ADMIN", ceiling_level=1, write_ceiling=1,
                         org_id="supra", compliance_clearance=[])
        perms = compile_permissions(user)
        nodes = [
            make_node(id="N-MNPI", org_id="supra", compliance_tags=["MNPI"],
                      hierarchy_level_number=1),
            make_node(id="N-SAFE", org_id="supra", compliance_tags=[],
                      hierarchy_level_number=1),
        ]
        surviving, counts = run_five_checks(nodes, user, perms)
        assert counts["after_check2"] == 1
        assert counts["after_check3"] == 1
        assert surviving[0]["id"] == "N-SAFE"

    def test_check4_does_not_see_nodes_excluded_by_check3(self):
        """Above-ceiling node should not reach temporal check even if ACTIVE."""
        user = make_user(role="VIEWER", ceiling_level=10, org_id="supra")
        perms = compile_permissions(user)
        nodes = [
            make_node(id="N-HIGH-LEVEL", org_id="supra", hierarchy_level_number=5,
                      status="ACTIVE", zone=1),
        ]
        surviving, counts = run_five_checks(nodes, user, perms)
        assert counts["after_check3"] == 0
        assert counts["after_check4"] == 0
        assert surviving == []

    def test_check5_does_not_see_nodes_excluded_by_check4(self):
        """Superseded node should not reach derivability check."""
        user = make_user(role="VIEWER", ceiling_level=10, org_id="supra")
        perms = compile_permissions(user)
        nodes = [
            make_node(id="N-SUP", org_id="supra", status="SUPERSEDED",
                      derivability_score=0.1, hierarchy_level_number=10),
        ]
        surviving, counts = run_five_checks(nodes, user, perms)
        assert counts["after_check4"] == 0
        assert counts["after_check5"] == 0
        assert surviving == []

    def test_all_five_checks_in_order_reduces_monotonically(self):
        user = make_user(role="VIEWER", ceiling_level=10, org_id="supra")
        perms = compile_permissions(user)
        nodes = [
            # passes all 5
            make_node(id="N-ALL-PASS",  org_id="supra", compliance_tags=[],
                      hierarchy_level_number=10, status="ACTIVE",
                      derivability_score=0.1, zone=1),
            # excluded by check1 (wrong org)
            make_node(id="N-WRONG-ORG", org_id="apollo", compliance_tags=[]),
            # excluded by check2 (MNPI)
            make_node(id="N-MNPI",      org_id="supra", compliance_tags=["MNPI"],
                      hierarchy_level_number=10),
            # excluded by check3 (above ceiling, zone=1)
            make_node(id="N-ABOVE",     org_id="supra", compliance_tags=[],
                      hierarchy_level_number=5, zone=1),
            # excluded by check4 (superseded)
            make_node(id="N-SUP",       org_id="supra", compliance_tags=[],
                      hierarchy_level_number=10, status="SUPERSEDED",
                      derivability_score=0.1),
            # excluded by check5 (high derivability)
            make_node(id="N-HIGH-DRV",  org_id="supra", compliance_tags=[],
                      hierarchy_level_number=10, status="ACTIVE",
                      derivability_score=0.95, zone=1),
        ]
        surviving, counts = run_five_checks(nodes, user, perms)
        assert counts["after_check1"] == 5   # wrong-org excluded
        assert counts["after_check2"] == 4   # MNPI excluded
        assert counts["after_check3"] == 3   # above-ceiling excluded
        assert counts["after_check4"] == 2   # superseded excluded
        assert counts["after_check5"] == 1   # high-drv excluded
        assert surviving[0]["id"] == "N-ALL-PASS"

    def test_run_five_checks_returns_stage_counts_and_survivors(self):
        user = make_user(org_id="supra")
        perms = compile_permissions(user)
        nodes = [make_node(org_id="supra")]
        surviving, counts = run_five_checks(nodes, user, perms)
        assert isinstance(surviving, list)
        assert isinstance(counts, dict)
        assert set(counts.keys()) == {
            "after_check1", "after_check2", "after_check3",
            "after_check4", "after_check5",
        }
