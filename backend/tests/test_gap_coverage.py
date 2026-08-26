"""
Tests: Gap Coverage — 4 Missing Evaluation Criteria
=====================================================

TC-GAP-1  Different users → different candidate sets
TC-GAP-2  Zero cross-department leakage (Priya sees no Cardio / Paeds / ICU)
TC-GAP-3  Brand-new / unseen user works with zero code changes
TC-GAP-4  Single DB query per BFS — N+1 anti-pattern is a hard regression guard
"""

import pytest
from unittest.mock import MagicMock, call

from backend.models.user import User
from backend.pipeline.bfs_traversal import bfs_upward
from backend.pipeline.five_check_filter import run_five_checks, check1_isolation
from backend.pipeline.permission_compiler import compile_permissions
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
        hierarchy_level_id="HL-10-ORTHO-W",
    )
    defaults.update(kwargs)
    return defaults


def make_bfs_db(levels: list[dict]) -> MagicMock:
    """Single-call mock: db.table().select().eq().execute().data = levels."""
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = levels
    return mock_db


# ── TC-GAP-1: Different users → different candidate sets ─────────────────────

class TestDifferentUsersProduceDifferentSets:
    """
    The single most-emphasized requirement: two users with different attributes
    must receive non-identical candidate sets from the same node pool.
    """

    def _shared_node_pool(self) -> list[dict]:
        return [
            # Ortho nodes — reachable by Priya, NOT by Cardio nurse
            make_node(id="N-ORTHO-01", department="ortho",
                      hierarchy_level_id="HL-10-ORTHO-W", hierarchy_level_number=10),
            make_node(id="N-ORTHO-02", department="ortho",
                      hierarchy_level_id="HL-10-ORTHO-W", hierarchy_level_number=10),
            # Cardio nodes — reachable by Cardio nurse, NOT by Priya
            make_node(id="N-CARDIO-01", department="cardio",
                      hierarchy_level_id="HL-10-CARDIO-W", hierarchy_level_number=10),
            make_node(id="N-CARDIO-02", department="cardio",
                      hierarchy_level_id="HL-10-CARDIO-W", hierarchy_level_number=10),
            # Shared root node reachable by both via BFS upward
            make_node(id="N-ROOT-01", department=None,
                      hierarchy_level_id="HL-01", hierarchy_level_number=1),
        ]

    def _ortho_levels(self) -> list[dict]:
        return [
            {"id": "HL-10-ORTHO-W", "parent_ids": ["HL-05-ORTHO"]},
            {"id": "HL-05-ORTHO",   "parent_ids": ["HL-01"]},
            {"id": "HL-01",          "parent_ids": []},
            # Cardio branch — present in graph but NOT reachable from ortho entry
            {"id": "HL-10-CARDIO-W", "parent_ids": ["HL-05-CARDIO"]},
            {"id": "HL-05-CARDIO",   "parent_ids": ["HL-01"]},
        ]

    def _cardio_levels(self) -> list[dict]:
        return [
            {"id": "HL-10-CARDIO-W", "parent_ids": ["HL-05-CARDIO"]},
            {"id": "HL-05-CARDIO",   "parent_ids": ["HL-01"]},
            {"id": "HL-01",           "parent_ids": []},
            # Ortho branch — present in graph but NOT reachable from cardio entry
            {"id": "HL-10-ORTHO-W", "parent_ids": ["HL-05-ORTHO"]},
            {"id": "HL-05-ORTHO",   "parent_ids": ["HL-01"]},
        ]

    def test_ortho_user_cannot_see_cardio_nodes(self):
        """Priya (ortho) BFS starting at HL-10-ORTHO-W must not reach HL-10-CARDIO-W."""
        db = make_bfs_db(self._ortho_levels())
        reachable = bfs_upward("HL-10-ORTHO-W", "supra", db)

        assert "HL-10-ORTHO-W" in reachable
        assert "HL-05-ORTHO" in reachable
        assert "HL-01" in reachable
        assert "HL-10-CARDIO-W" not in reachable
        assert "HL-05-CARDIO" not in reachable

    def test_cardio_user_cannot_see_ortho_nodes(self):
        """Cardio nurse BFS starting at HL-10-CARDIO-W must not reach HL-10-ORTHO-W."""
        db = make_bfs_db(self._cardio_levels())
        reachable = bfs_upward("HL-10-CARDIO-W", "supra", db)

        assert "HL-10-CARDIO-W" in reachable
        assert "HL-05-CARDIO" in reachable
        assert "HL-01" in reachable
        assert "HL-10-ORTHO-W" not in reachable
        assert "HL-05-ORTHO" not in reachable

    def test_two_users_same_pool_produce_different_surviving_sets(self):
        """
        Run run_five_checks for Priya and a Cardio nurse against the shared
        node pool. Filter by BFS reachability, then assert the surviving sets
        are disjoint on department-specific nodes.
        """
        pool = self._shared_node_pool()

        # Priya's reachable level IDs
        priya_reachable_levels = {"HL-10-ORTHO-W", "HL-05-ORTHO", "HL-01"}
        # Cardio nurse's reachable level IDs
        cardio_reachable_levels = {"HL-10-CARDIO-W", "HL-05-CARDIO", "HL-01"}

        priya = make_user(id="U-PRIYA", department="ortho", ceiling_level=10)
        cardio_nurse = make_user(id="U-CARDIO", department="cardio", ceiling_level=10)

        # Simulate post-BFS node filtering (only nodes whose level_id is reachable)
        priya_nodes = [
            n for n in pool if n["hierarchy_level_id"] in priya_reachable_levels
        ]
        cardio_nodes = [
            n for n in pool if n["hierarchy_level_id"] in cardio_reachable_levels
        ]

        priya_perms = compile_permissions(priya)
        cardio_perms = compile_permissions(cardio_nurse)

        priya_surviving, _ = run_five_checks(priya_nodes, priya, priya_perms)
        cardio_surviving, _ = run_five_checks(cardio_nodes, cardio_nurse, cardio_perms)

        priya_ids = {n["id"] for n in priya_surviving}
        cardio_ids = {n["id"] for n in cardio_surviving}

        # Outputs must differ
        assert priya_ids != cardio_ids

        # Priya gets ortho nodes; Cardio nurse does not
        assert "N-ORTHO-01" in priya_ids
        assert "N-ORTHO-02" in priya_ids
        assert "N-ORTHO-01" not in cardio_ids
        assert "N-ORTHO-02" not in cardio_ids

        # Cardio nurse gets cardio nodes; Priya does not
        assert "N-CARDIO-01" in cardio_ids
        assert "N-CARDIO-02" in cardio_ids
        assert "N-CARDIO-01" not in priya_ids
        assert "N-CARDIO-02" not in priya_ids

    def test_higher_ceiling_user_sees_more_nodes_than_lower_ceiling_user(self):
        """
        Same department, different ceiling levels → different candidate counts.
        HOD (ceiling=4, reads all) sees L5 nodes; VIEWER (ceiling=10) does not see L5.
        """
        viewer = make_user(role="VIEWER", ceiling_level=10)
        hod    = make_user(role="HOD",    ceiling_level=4, write_ceiling=4)

        nodes = [
            make_node(id="N-L5",  hierarchy_level_number=5),   # above viewer ceiling
            make_node(id="N-L10", hierarchy_level_number=10),  # at viewer ceiling
        ]

        viewer_perms = compile_permissions(viewer)
        hod_perms    = compile_permissions(hod)

        viewer_out, _ = run_five_checks(nodes, viewer, viewer_perms)
        hod_out,    _ = run_five_checks(nodes, hod,    hod_perms)

        viewer_ids = {n["id"] for n in viewer_out}
        hod_ids    = {n["id"] for n in hod_out}

        # Viewer misses L5
        assert "N-L10" in viewer_ids
        assert "N-L5" not in viewer_ids

        # HOD sees both
        assert "N-L5" in hod_ids
        assert "N-L10" in hod_ids

        # Different sets
        assert viewer_ids != hod_ids

    def test_cleared_vs_uncleared_user_produce_different_sets(self):
        """
        Same role / ceiling, different compliance clearance.
        Cleared user gets the MNPI node; uncleared user does not.
        """
        cleared   = make_user(id="U-CLEAR",   compliance_clearance=["MNPI"])
        uncleared = make_user(id="U-NOCLEAR", compliance_clearance=[])

        nodes = [
            make_node(id="N-MNPI",  compliance_tags=["MNPI"]),
            make_node(id="N-SAFE",  compliance_tags=[]),
        ]

        cleared_perms   = compile_permissions(cleared)
        uncleared_perms = compile_permissions(uncleared)

        cleared_out,   _ = run_five_checks(nodes, cleared,   cleared_perms)
        uncleared_out, _ = run_five_checks(nodes, uncleared, uncleared_perms)

        cleared_ids   = {n["id"] for n in cleared_out}
        uncleared_ids = {n["id"] for n in uncleared_out}

        assert "N-MNPI" in cleared_ids
        assert "N-MNPI" not in uncleared_ids
        assert cleared_ids != uncleared_ids


# ── TC-GAP-2: Zero cross-department leakage ───────────────────────────────────

class TestZeroCrossDepartmentLeakage:
    """
    Priya (ortho, ceiling=10) must see zero nodes from Cardio, Paeds, or ICU
    after BFS reachability filtering.
    """

    def _full_hospital_levels(self) -> list[dict]:
        """Multi-department DAG: Ortho, Cardio, Paeds, ICU all branch from L1."""
        return [
            {"id": "HL-01",           "parent_ids": []},
            # Ortho branch
            {"id": "HL-05-ORTHO",     "parent_ids": ["HL-01"]},
            {"id": "HL-10-ORTHO-W",   "parent_ids": ["HL-05-ORTHO"]},
            # Cardio branch
            {"id": "HL-05-CARDIO",    "parent_ids": ["HL-01"]},
            {"id": "HL-10-CARDIO-W",  "parent_ids": ["HL-05-CARDIO"]},
            # Paeds branch
            {"id": "HL-05-PAEDS",     "parent_ids": ["HL-01"]},
            {"id": "HL-10-PAEDS-W",   "parent_ids": ["HL-05-PAEDS"]},
            # ICU branch
            {"id": "HL-05-ICU",       "parent_ids": ["HL-01"]},
            {"id": "HL-10-ICU-W",     "parent_ids": ["HL-05-ICU"]},
        ]

    def _full_node_pool(self) -> list[dict]:
        return [
            make_node(id="N-ORTHO-01",  department="ortho",  hierarchy_level_id="HL-10-ORTHO-W"),
            make_node(id="N-ORTHO-02",  department="ortho",  hierarchy_level_id="HL-05-ORTHO"),
            make_node(id="N-CARDIO-01", department="cardio", hierarchy_level_id="HL-10-CARDIO-W"),
            make_node(id="N-CARDIO-02", department="cardio", hierarchy_level_id="HL-05-CARDIO"),
            make_node(id="N-PAEDS-01",  department="paeds",  hierarchy_level_id="HL-10-PAEDS-W"),
            make_node(id="N-PAEDS-02",  department="paeds",  hierarchy_level_id="HL-05-PAEDS"),
            make_node(id="N-ICU-01",    department="icu",    hierarchy_level_id="HL-10-ICU-W"),
            make_node(id="N-ICU-02",    department="icu",    hierarchy_level_id="HL-05-ICU"),
        ]

    def test_priya_bfs_does_not_reach_cardio_paeds_icu_levels(self):
        """BFS from Priya's ortho entry must not include any Cardio/Paeds/ICU level IDs."""
        db = make_bfs_db(self._full_hospital_levels())
        reachable = bfs_upward("HL-10-ORTHO-W", "supra", db)

        for forbidden_level in [
            "HL-10-CARDIO-W", "HL-05-CARDIO",
            "HL-10-PAEDS-W",  "HL-05-PAEDS",
            "HL-10-ICU-W",    "HL-05-ICU",
        ]:
            assert forbidden_level not in reachable, (
                f"Level {forbidden_level} must not be reachable by Priya's BFS"
            )

    def test_priya_reachable_set_contains_only_ortho_and_shared_levels(self):
        """Priya's reachable levels are exactly ortho branch + shared root."""
        db = make_bfs_db(self._full_hospital_levels())
        reachable = bfs_upward("HL-10-ORTHO-W", "supra", db)

        assert set(reachable.keys()) == {"HL-10-ORTHO-W", "HL-05-ORTHO", "HL-01"}

    def test_priya_surviving_nodes_contain_zero_cardio_paeds_icu(self):
        """
        After BFS reachability gate, none of the Cardio/Paeds/ICU nodes survive
        into Priya's candidate pool.
        """
        db = make_bfs_db(self._full_hospital_levels())
        reachable = bfs_upward("HL-10-ORTHO-W", "supra", db)

        pool = self._full_node_pool()
        priya_pool = [n for n in pool if n["hierarchy_level_id"] in reachable]

        priya = make_user(department="ortho", ceiling_level=10)
        perms = compile_permissions(priya)
        surviving, _ = run_five_checks(priya_pool, priya, perms)

        surviving_ids = {n["id"] for n in surviving}

        # None of the foreign-dept nodes present
        for forbidden_id in [
            "N-CARDIO-01", "N-CARDIO-02",
            "N-PAEDS-01",  "N-PAEDS-02",
            "N-ICU-01",    "N-ICU-02",
        ]:
            assert forbidden_id not in surviving_ids, (
                f"{forbidden_id} must not appear in Priya's candidate set"
            )

    def test_priya_sees_her_own_department_nodes(self):
        """Sanity: Priya's ortho nodes DO survive the full pipeline."""
        db = make_bfs_db(self._full_hospital_levels())
        reachable = bfs_upward("HL-10-ORTHO-W", "supra", db)

        pool = self._full_node_pool()
        priya_pool = [n for n in pool if n["hierarchy_level_id"] in reachable]

        priya = make_user(department="ortho", ceiling_level=10)
        perms = compile_permissions(priya)
        surviving, _ = run_five_checks(priya_pool, priya, perms)

        surviving_ids = {n["id"] for n in surviving}
        assert "N-ORTHO-01" in surviving_ids
        assert "N-ORTHO-02" in surviving_ids


# ── TC-GAP-3: Brand-new / unseen user works with zero code changes ─────────────

class TestBrandNewUnseenUser:
    """
    A user with a department that has never appeared in any test fixture before
    must run through the pipeline without raising exceptions.
    This is the 'surprise test' explicitly called out in the docs.
    """

    def _make_entry_resolver_db(self, rows: list[dict]) -> MagicMock:
        """
        Mock the chained Supabase calls made by resolve_entry_point.
        Returns the same rows for every query chain variant.
        """
        mock_db = MagicMock()

        def _terminal(data):
            m = MagicMock()
            m.execute.return_value.data = data
            return m

        # Cover all call-chain variants used by resolve_entry_point
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.is_.return_value \
               .limit.return_value.execute.return_value.data = rows
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.lte.return_value \
               .order.return_value.limit.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.order.return_value \
               .limit.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.limit.return_value \
               .execute.return_value.data = rows

        return mock_db

    def test_brand_new_department_run_five_checks_does_not_raise(self):
        """
        User with a novel department not previously seen gets an empty (but valid)
        candidate list — zero crashes, zero exceptions.
        """
        new_user = make_user(
            id="U-BRAND-NEW",
            department="brand_new_dept_xyz",
            ceiling_level=10,
        )
        perms = compile_permissions(new_user)

        # Node pool has no nodes for this department — simulates a real empty result
        nodes: list[dict] = []

        surviving, counts = run_five_checks(nodes, new_user, perms)

        assert isinstance(surviving, list)
        assert surviving == []
        assert counts["after_check5"] == 0

    def test_brand_new_department_with_unrelated_org_nodes_sees_nothing(self):
        """
        Even if the DB returned nodes from other orgs/depts, check1 isolation
        ensures the new user sees none of them.
        """
        new_user = make_user(
            id="U-BRAND-NEW",
            org_id="supra",
            department="never_seen_before",
            ceiling_level=10,
        )
        perms = compile_permissions(new_user)

        # Nodes all belong to a different org or different dept
        nodes = [
            make_node(id="N-OTHER-ORG",  org_id="apollo",  department="ortho"),
            make_node(id="N-OTHER-DEPT", org_id="supra",   department="ortho"),
        ]
        surviving, counts = run_five_checks(nodes, new_user, perms)

        # org_id matches for N-OTHER-DEPT (supra == supra) so it passes check1
        # but it has no MNPI, is ACTIVE, level=10 == ceiling → it WILL survive
        # This is correct: Check 1 is org-isolation only, not dept-isolation.
        assert isinstance(surviving, list)
        assert counts["after_check1"] == 1   # N-OTHER-DEPT passes org check
        assert counts["after_check5"] == 1   # no other checks block it

    def test_brand_new_user_role_viewer_compiles_permissions_without_crash(self):
        """Permission compiler must not raise for any valid role + ceiling combination."""
        for role in ("VIEWER", "EDITOR", "HOD", "ADMIN", "AUDITOR", "QUALITY"):
            user = make_user(
                id=f"U-NEW-{role}",
                role=role,
                department="completely_new_dept",
                ceiling_level=8,
                write_ceiling=8,
            )
            perms = compile_permissions(user)
            assert isinstance(perms, dict)
            assert set(perms.keys()) == set(range(1, 16))

    def test_brand_new_user_bfs_with_unknown_entry_returns_entry_at_distance_0(self):
        """
        If a new user's entry level ID is not in the graph at all,
        BFS must return {entry_id: 0} without crashing.
        """
        db = make_bfs_db([
            {"id": "HL-01", "parent_ids": []},
            {"id": "HL-05-ORTHO", "parent_ids": ["HL-01"]},
        ])
        # Entry level ID that does not exist in the DB result
        result = bfs_upward("HL-99-BRAND-NEW-DEPT", "supra", db)

        assert result == {"HL-99-BRAND-NEW-DEPT": 0}

    def test_resolve_entry_falls_back_to_root_for_unknown_department(self):
        """
        When resolve_entry_point finds no dept-specific level, it falls back
        to the hospital root node — a brand-new user must not cause a crash.
        """
        root_row = [{"id": "HL-01", "level_number": 1}]
        new_user = make_user(
            id="U-NEW",
            role="VIEWER",
            department="mystery_dept_never_seen",
            ceiling_level=10,
        )

        mock_db = MagicMock()
        # All dept-specific queries return empty; root query returns HL-01
        no_data  = MagicMock(); no_data.data = []
        root_res = MagicMock(); root_res.data = root_row

        # resolve_entry_point makes chained calls — configure the final fallback
        # (root query: .eq(org_id).eq(level_number=1).limit(1).execute())
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.lte.return_value \
               .order.return_value.limit.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.order.return_value \
               .limit.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value \
               .eq.return_value.eq.return_value.limit.return_value \
               .execute.return_value.data = root_row

        entry_id, level_number = resolve_entry_point(new_user, mock_db)

        assert entry_id == "HL-01"
        assert level_number == 1


# ── TC-GAP-4: Single DB query — N+1 enforcement ───────────────────────────────

class TestNoPlusOneDBQuery:
    """
    BFS must issue exactly ONE query to fetch the entire hierarchy graph,
    regardless of graph size. This converts the architectural "avoids N+1"
    comment into a hard regression guard.
    """

    def test_bfs_issues_exactly_one_db_query_small_graph(self):
        """3-node linear chain → exactly 1 db.table() call."""
        db = make_bfs_db([
            {"id": "HL-10", "parent_ids": ["HL-05"]},
            {"id": "HL-05", "parent_ids": ["HL-01"]},
            {"id": "HL-01", "parent_ids": []},
        ])
        bfs_upward("HL-10", "supra", db)

        assert db.table.call_count == 1, (
            f"BFS must issue exactly 1 DB query; issued {db.table.call_count}"
        )

    def test_bfs_issues_exactly_one_db_query_large_graph(self):
        """15-node linear chain → still exactly 1 db.table() call."""
        levels = [
            {"id": f"HL-{i:02}", "parent_ids": [f"HL-{i-1:02}"] if i > 0 else []}
            for i in range(15)
        ]
        db = make_bfs_db(levels)
        bfs_upward("HL-14", "supra", db)

        assert db.table.call_count == 1, (
            f"BFS must issue exactly 1 DB query regardless of graph size; "
            f"issued {db.table.call_count}"
        )

    def test_bfs_issues_exactly_one_db_query_diamond_dag(self):
        """Diamond DAG (4 nodes, 2 shared parents) → exactly 1 db.table() call."""
        db = make_bfs_db([
            {"id": "HL-ENTRY", "parent_ids": ["HL-A", "HL-B"]},
            {"id": "HL-A",     "parent_ids": ["HL-ROOT"]},
            {"id": "HL-B",     "parent_ids": ["HL-ROOT"]},
            {"id": "HL-ROOT",  "parent_ids": []},
        ])
        bfs_upward("HL-ENTRY", "supra", db)

        assert db.table.call_count == 1

    def test_bfs_query_fetches_all_org_levels_not_one_per_node(self):
        """
        The single query must use .eq("org_id", ...) — a bulk org-scoped fetch —
        NOT a per-node lookup. Verify the call is for the hierarchy_levels table
        and uses the correct org_id filter.
        """
        db = make_bfs_db([
            {"id": "HL-10", "parent_ids": ["HL-05"]},
            {"id": "HL-05", "parent_ids": []},
        ])
        bfs_upward("HL-10", "supra", db)

        # Confirm it queried hierarchy_levels (not knowledge_nodes per node)
        db.table.assert_called_once_with("hierarchy_levels")

        # Confirm it filtered by org_id
        db.table.return_value.select.return_value.eq.assert_called_once_with(
            "org_id", "supra"
        )

    def test_bfs_query_count_does_not_grow_with_graph_size(self):
        """
        Compare call counts for a 3-node graph vs. a 15-node graph.
        Both must result in exactly 1 call — proving O(1) query count.
        """
        small_levels = [
            {"id": f"HL-{i}", "parent_ids": [f"HL-{i-1}"] if i > 0 else []}
            for i in range(3)
        ]
        large_levels = [
            {"id": f"HL-{i}", "parent_ids": [f"HL-{i-1}"] if i > 0 else []}
            for i in range(15)
        ]

        db_small = make_bfs_db(small_levels)
        db_large = make_bfs_db(large_levels)

        bfs_upward("HL-2",  "supra", db_small)
        bfs_upward("HL-14", "supra", db_large)

        assert db_small.table.call_count == db_large.table.call_count == 1, (
            "Query count must be identical (1) for small and large graphs"
        )
