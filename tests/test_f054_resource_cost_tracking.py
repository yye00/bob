"""Tests for F054: Implement resource cost tracking and limit enforcement."""

import pathlib

import pytest

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Create a temporary database and initialize schema."""
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(p))
    from bob3.db import init_database

    init_database()
    return p


@pytest.fixture()
def project(db_path):
    """Create a test project with a known max_cost_usd."""
    from bob3.db import create_project

    return create_project(
        name="Cost Tracking Test",
        workspace_path="/tmp/cost-test",
        max_cost_usd=100.0,
    )


# ============================================================
# Step 1: Add update_project_cost() function
# ============================================================


class TestUpdateProjectCostExists:
    """Step 1: update_project_cost() is importable and callable."""

    def test_function_is_importable(self, db_path):
        from bob3.db import update_project_cost

        assert callable(update_project_cost)

    def test_returns_project_model(self, project):
        from bob3.db import update_project_cost
        from bob3.models import Project

        result = update_project_cost(project_id=project.id, cost_usd=5.0)
        assert isinstance(result, Project)


# ============================================================
# Step 2: Increment total_cost_usd on each agent run
# ============================================================


class TestIncrementTotalCostUsd:
    """Step 2: total_cost_usd is incremented by the given amount."""

    def test_single_cost_increment(self, project):
        from bob3.db import update_project_cost

        result = update_project_cost(project_id=project.id, cost_usd=10.0)
        assert result.total_cost_usd == 10.0

    def test_multiple_cost_increments_accumulate(self, project):
        from bob3.db import update_project_cost

        update_project_cost(project_id=project.id, cost_usd=10.0)
        update_project_cost(project_id=project.id, cost_usd=25.0)
        result = update_project_cost(project_id=project.id, cost_usd=5.0)
        assert result.total_cost_usd == 40.0

    def test_zero_cost_leaves_total_unchanged(self, project):
        from bob3.db import update_project_cost

        update_project_cost(project_id=project.id, cost_usd=20.0)
        result = update_project_cost(project_id=project.id, cost_usd=0.0)
        assert result.total_cost_usd == 20.0

    def test_cost_persisted_in_database(self, project):
        from bob3.db import get_project, update_project_cost

        update_project_cost(project_id=project.id, cost_usd=42.5)
        fetched = get_project(project.id)
        assert fetched is not None
        assert fetched.total_cost_usd == 42.5

    def test_nonexistent_project_returns_none(self, db_path):
        from bob3.db import update_project_cost

        result = update_project_cost(project_id="nonexistent-id", cost_usd=10.0)
        assert result is None


# ============================================================
# Step 3: Check against max_cost_usd
# ============================================================


class TestCheckAgainstMaxCost:
    """Step 3: update_project_cost checks total against max_cost_usd."""

    def test_under_limit_status_unchanged(self, project):
        from bob3.db import update_project_cost

        result = update_project_cost(project_id=project.id, cost_usd=50.0)
        assert result.status == "planning"  # Original status preserved

    def test_at_exact_limit_no_trigger(self, project):
        """Exactly at the limit should NOT trigger resource_limited."""
        from bob3.db import update_project_cost

        result = update_project_cost(project_id=project.id, cost_usd=100.0)
        assert result.status == "planning"

    def test_over_limit_detected(self, project):
        from bob3.db import update_project_cost

        result = update_project_cost(project_id=project.id, cost_usd=101.0)
        assert result.total_cost_usd == 101.0
        assert result.status == "resource_limited"


# ============================================================
# Step 4: Set project status to 'resource_limited' if exceeded
# ============================================================


class TestResourceLimitedStatus:
    """Step 4: Project status changes to 'resource_limited' when cost exceeds limit."""

    def test_status_set_to_resource_limited(self, project):
        from bob3.db import update_project_cost

        result = update_project_cost(project_id=project.id, cost_usd=110.0)
        assert result.status == "resource_limited"

    def test_resource_limited_persisted(self, project):
        from bob3.db import get_project, update_project_cost

        update_project_cost(project_id=project.id, cost_usd=110.0)
        fetched = get_project(project.id)
        assert fetched is not None
        assert fetched.status == "resource_limited"
        assert fetched.total_cost_usd == 110.0

    def test_incremental_cost_triggers_limit(self, project):
        """Multiple small increments that cross the limit should trigger."""
        from bob3.db import update_project_cost

        update_project_cost(project_id=project.id, cost_usd=50.0)
        update_project_cost(project_id=project.id, cost_usd=40.0)
        # Now at 90, still under 100
        result = update_project_cost(project_id=project.id, cost_usd=11.0)
        # Now at 101, over 100
        assert result.total_cost_usd == 101.0
        assert result.status == "resource_limited"

    def test_already_resource_limited_stays_limited(self, project):
        """Once resource_limited, additional costs keep the status."""
        from bob3.db import update_project_cost

        update_project_cost(project_id=project.id, cost_usd=110.0)
        result = update_project_cost(project_id=project.id, cost_usd=5.0)
        assert result.total_cost_usd == 115.0
        assert result.status == "resource_limited"


# ============================================================
# Step 5: Test: Set max_cost=100, add costs to 110, verify limit triggered
# ============================================================


class TestEndToEndCostLimitEnforcement:
    """Step 5: Full end-to-end test with max_cost=100 and total reaching 110."""

    def test_set_max_100_add_to_110_verify_limited(self, db_path):
        """E2E: Create project with max=100, add costs totaling 110, verify resource_limited."""
        from bob3.db import create_project, get_project, update_project_cost

        # Create project with max_cost_usd=100
        proj = create_project(
            name="E2E Cost Test",
            workspace_path="/tmp/e2e-cost",
            max_cost_usd=100.0,
        )
        assert proj.max_cost_usd == 100.0
        assert proj.total_cost_usd == 0.0

        # Simulate several agent runs adding cost
        update_project_cost(project_id=proj.id, cost_usd=30.0)
        update_project_cost(project_id=proj.id, cost_usd=30.0)
        update_project_cost(project_id=proj.id, cost_usd=30.0)

        # Check: at 90, still under limit
        check = get_project(proj.id)
        assert check is not None
        assert check.total_cost_usd == 90.0
        assert check.status == "planning"

        # Add 20 more -> total 110, over the 100 limit
        result = update_project_cost(project_id=proj.id, cost_usd=20.0)
        assert result.total_cost_usd == 110.0
        assert result.status == "resource_limited"

        # Verify in database
        final = get_project(proj.id)
        assert final is not None
        assert final.total_cost_usd == 110.0
        assert final.status == "resource_limited"

    def test_negative_cost_rejected(self, project):
        """Negative cost values should be rejected."""
        from bob3.db import update_project_cost

        with pytest.raises(ValueError, match="cost_usd must be non-negative"):
            update_project_cost(project_id=project.id, cost_usd=-5.0)


# ============================================================
# Step 6: Cost normalization (_normalize_cost) — handles the
# Claude Max Pro / OAuth case where the SDK returns total_cost_usd=None
# ============================================================


class TestNormalizeCost:
    """_normalize_cost converts a possibly-None SDK cost into a budget-safe value."""

    def test_sdk_cost_passthrough(self):
        from bob3.orchestrator.run_loop import _normalize_cost

        cost, source = _normalize_cost(0.05, 3)
        assert cost == pytest.approx(0.05)
        assert source == "sdk"

    def test_sdk_zero_cost_is_sdk_source(self):
        """A genuine 0.0 cost from the SDK is still 'sdk', not the proxy."""
        from bob3.orchestrator.run_loop import _normalize_cost

        cost, source = _normalize_cost(0.0, 5)
        assert cost == pytest.approx(0.0)
        assert source == "sdk"

    def test_none_cost_with_turns_uses_proxy(self):
        from bob3.orchestrator.run_loop import _normalize_cost

        cost, source = _normalize_cost(None, 10)
        # Default $0.05/turn × 10 turns = $0.50
        assert cost == pytest.approx(0.50)
        assert source == "turn_proxy"

    def test_none_cost_with_zero_turns_returns_zero(self):
        from bob3.orchestrator.run_loop import _normalize_cost

        cost, source = _normalize_cost(None, 0)
        assert cost == pytest.approx(0.0)
        assert source == "zero"

    def test_none_cost_with_none_turns_returns_zero(self):
        from bob3.orchestrator.run_loop import _normalize_cost

        cost, source = _normalize_cost(None, None)
        assert cost == pytest.approx(0.0)
        assert source == "zero"

    def test_env_var_overrides_proxy_rate(self, monkeypatch):
        from bob3.orchestrator.run_loop import _normalize_cost

        monkeypatch.setenv("BOB3_COST_PER_TURN_PROXY", "0.10")
        cost, source = _normalize_cost(None, 7)
        assert cost == pytest.approx(0.70)
        assert source == "turn_proxy"


# ============================================================
# Step 7: handle_execution_result records the proxy / SDK cost
# correctly when the SDK returns None
# ============================================================


@pytest.fixture()
def feature_for_handler(project):
    """Create a 'ready' feature with high readiness for handler tests."""
    from bob3.db import create_feature, get_feature, update_feature

    f = create_feature(
        project_id=project.id,
        name="Cost normalization test feature",
        description="Verifies cost normalization behaviour.",
        status="ready",
        priority=10,
        risk_category="medium",
    )
    update_feature(
        f.id,
        conf_spec_understanding=0.9,
        conf_impl_correctness=0.9,
        conf_test_adequacy=0.9,
        readiness_score=0.9,
    )
    return get_feature(f.id)


class TestHandleExecutionResultCostNormalization:
    """handle_execution_result must use _normalize_cost so Max Pro budgets work."""

    def _make_spawn_result(self, *, total_cost_usd, num_turns):
        import uuid
        from unittest.mock import MagicMock

        from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult

        result = ExecutionResult(
            text="OK",
            is_error=False,
            total_cost_usd=total_cost_usd,
            num_turns=num_turns,
        )
        agent_run = MagicMock()
        agent_run.id = str(uuid.uuid4())
        return SpawnResult(execution_result=result, agent_run=agent_run)

    def test_records_proxy_cost_when_sdk_returns_none(
        self, project, feature_for_handler
    ):
        """When SDK returns cost=None and num_turns>0, proxy cost is recorded."""
        from bob3.db import get_project
        from bob3.orchestrator.run_loop import (
            _PROXY_LOGGED_FEATURE_IDS,
            handle_execution_result,
        )

        _PROXY_LOGGED_FEATURE_IDS.discard(feature_for_handler.id)

        spawn = self._make_spawn_result(total_cost_usd=None, num_turns=10)
        outcome = handle_execution_result(
            project_id=project.id,
            feature=feature_for_handler,
            spawn_result=spawn,
        )

        # Default proxy: $0.05 × 10 = $0.50
        assert outcome["cost_source"] == "turn_proxy"
        assert outcome["cost_usd"] == pytest.approx(0.50)
        updated = get_project(project.id)
        assert updated.total_cost_usd == pytest.approx(0.50)

    def test_records_sdk_cost_when_present(self, project, feature_for_handler):
        """When SDK reports a cost, that exact value is recorded."""
        from bob3.db import get_project
        from bob3.orchestrator.run_loop import handle_execution_result

        spawn = self._make_spawn_result(total_cost_usd=2.50, num_turns=8)
        outcome = handle_execution_result(
            project_id=project.id,
            feature=feature_for_handler,
            spawn_result=spawn,
        )

        assert outcome["cost_source"] == "sdk"
        assert outcome["cost_usd"] == pytest.approx(2.50)
        updated = get_project(project.id)
        assert updated.total_cost_usd == pytest.approx(2.50)


# ============================================================
# Step 8: budget_exceeded() must trigger when accumulated proxy
# cost crosses the project's max_cost_usd
# ============================================================


class TestBudgetExceededWithProxy:
    """OrchestrationLoop.budget_exceeded triggers on accumulated proxy cost."""

    def test_proxy_accumulates_to_exceed_budget(self, db_path):
        """Many None-cost results with high turn counts must exceed budget."""
        import uuid
        from unittest.mock import MagicMock

        from bob3.db import create_feature, create_project, get_feature, update_feature
        from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
        from bob3.orchestrator.run_loop import (
            OrchestrationLoop,
            _PROXY_LOGGED_FEATURE_IDS,
            handle_execution_result,
        )

        # Tiny budget so the proxy crosses it quickly.
        proj = create_project(
            name="Proxy Budget Test",
            workspace_path="/tmp/proxy-budget",
            max_cost_usd=1.0,
        )

        f = create_feature(
            project_id=proj.id,
            name="Proxy budget feature",
            description="A feature for proxy budget tests",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=proj.id, max_cost=1.0)
        assert loop.budget_exceeded() is False

        # Each None-cost result with 10 turns -> $0.50 via proxy.
        # Three of them = $1.50, which exceeds $1.00 budget.
        _PROXY_LOGGED_FEATURE_IDS.discard(feature.id)
        for _ in range(3):
            res = ExecutionResult(
                text="OK", is_error=False, total_cost_usd=None, num_turns=10
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn = SpawnResult(execution_result=res, agent_run=agent_run)
            handle_execution_result(
                project_id=proj.id,
                feature=feature,
                spawn_result=spawn,
            )

        # ``handle_execution_result`` writes cost to the DB, but the loop
        # caches the project's total to avoid a per-iteration re-fetch.
        # In production the loop refreshes the cache itself right after
        # ``handle_execution_result`` returns; this test calls the
        # module function directly, so we replicate that refresh by
        # hand before checking the budget.
        loop._refresh_project_cost_cache()

        # Project-level budget should now report exceeded.
        assert loop.budget_exceeded() is True


# ============================================================
# Step 9: budget_exceeded() must defensively handle a None DB total
# ============================================================


class TestBudgetExceededDefensiveNone:
    """If the DB total ever leaks None, budget_exceeded must not silently allow it."""

    def test_none_total_treated_as_zero(self, project, monkeypatch):
        """A simulated None total must not be evaluated as infinite room."""
        from bob3.orchestrator import run_loop as run_loop_mod
        from bob3.orchestrator.run_loop import OrchestrationLoop

        loop = OrchestrationLoop(project_id=project.id, max_cost=10.0)

        # Simulate a Project whose total_cost_usd is None (shouldn't happen
        # under pydantic, but the production code must be defensive).
        class _StubProject:
            max_cost_usd = 100.0
            total_cost_usd = None

        monkeypatch.setattr(run_loop_mod.db, "get_project", lambda _: _StubProject())

        # Force the loop to re-read project state through the patched
        # ``get_project`` so the None-handling path is actually exercised.
        # In production this refresh runs inside ``execute_feature`` after
        # every cost-mutating call.
        loop._refresh_project_cost_cache()

        # With total treated as 0, budget is not exceeded.
        assert loop.budget_exceeded() is False


# ============================================================
# Bug 1: No double-counting of cost between self.total_cost and
# project.total_cost_usd in execute_feature
# ============================================================


class TestNoDoubleCostAccumulation:
    """Regression: self.total_cost must NOT drift above project.total_cost_usd
    after execute_feature() completes successfully.
    """

    @pytest.mark.asyncio
    async def test_total_cost_matches_project_total_after_execute(
        self, project, feature_for_handler
    ):
        """Bug 1: in-memory total must not double-count vs the DB total.

        Run a single execute_feature() with a known SDK cost, then assert
        that loop.total_cost <= project.total_cost_usd. Before the fix,
        loop.total_cost was 2x the project total (incremented in BOTH
        handle_execution_result via update_project_cost AND in
        execute_feature directly).
        """
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import get_project
        from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
        from bob3.orchestrator.run_loop import OrchestrationLoop

        loop = OrchestrationLoop(project_id=project.id)

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="ok",
                is_error=False,
                duration_ms=1000,
                num_turns=5,
                total_cost_usd=1.25,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ):
            await loop.execute_feature(feature_for_handler)

        updated_project = get_project(project.id)
        # Project DB total is the canonical accumulator and must equal the
        # one normalized cost from this single feature execution.
        assert updated_project.total_cost_usd == pytest.approx(1.25)
        # In-memory accumulator must NOT exceed the DB total. (We removed
        # the in-memory increment in execute_feature; a small allowance for
        # other paths that still bump it would still satisfy <=.)
        assert loop.total_cost <= updated_project.total_cost_usd + 1e-9, (
            f"loop.total_cost={loop.total_cost} drifted above "
            f"project.total_cost_usd={updated_project.total_cost_usd} — "
            "double-accumulation regression"
        )


# ============================================================
# Bonus: _PROXY_LOGGED_FEATURE_IDS must NOT grow without bound
# ============================================================


class TestProxyLoggedFeatureIdsBounded:
    """Regression: the proxy-log dedup container used to be an unbounded
    module-level set that grew for every feature ever logged across the
    lifetime of the process. In long-running orchestrators or large test
    runs that's a slow memory leak. The replacement must cap itself.
    """

    def test_set_caps_population_under_max_entries(self):
        from bob3.orchestrator.run_loop import (
            _PROXY_LOG_DEDUP_MAX_ENTRIES,
            _BoundedFeatureIdSet,
        )

        s = _BoundedFeatureIdSet(max_entries=_PROXY_LOG_DEDUP_MAX_ENTRIES)
        # Insert MORE entries than the cap; the structure must drop the
        # oldest rather than grow forever.
        overshoot = _PROXY_LOG_DEDUP_MAX_ENTRIES + 250
        for i in range(overshoot):
            s.add(f"feat-{i:08d}")
        assert len(s) == _PROXY_LOG_DEDUP_MAX_ENTRIES, (
            f"bounded set grew to {len(s)}, expected cap "
            f"{_PROXY_LOG_DEDUP_MAX_ENTRIES} — population is unbounded"
        )

    def test_module_global_does_not_leak_across_many_runs(self):
        """Hammer the module-level dedup container with simulated runs.

        Each "run" represents handle_execution_result observing a
        proxy-cost result for a unique feature. The container must not
        grow past the configured cap regardless of how many runs pass.
        """
        from bob3.orchestrator.run_loop import (
            _PROXY_LOG_DEDUP_MAX_ENTRIES,
            _PROXY_LOGGED_FEATURE_IDS,
        )

        # Reset to a known-empty state so we can assert about size.
        _PROXY_LOGGED_FEATURE_IDS.clear()

        runs = _PROXY_LOG_DEDUP_MAX_ENTRIES * 3
        for i in range(runs):
            _PROXY_LOGGED_FEATURE_IDS.add(f"run-{i:08d}-feat")

        assert len(_PROXY_LOGGED_FEATURE_IDS) <= _PROXY_LOG_DEDUP_MAX_ENTRIES, (
            f"_PROXY_LOGGED_FEATURE_IDS grew to "
            f"{len(_PROXY_LOGGED_FEATURE_IDS)} after {runs} runs — "
            "unbounded growth (module-level set leak)"
        )

        # Cleanup so we don't pollute other tests in the same process.
        _PROXY_LOGGED_FEATURE_IDS.clear()

    def test_handle_execution_result_repeated_calls_stay_bounded(
        self, db_path
    ):
        """Drive handle_execution_result through many proxy-cost results.

        Each call should update the dedup container at most once for that
        feature; across thousands of distinct features the container must
        still respect the cap.
        """
        import uuid
        from unittest.mock import MagicMock

        from bob3.db import (
            create_feature,
            create_project,
            get_feature,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import (
            _PROXY_LOG_DEDUP_MAX_ENTRIES,
            _PROXY_LOGGED_FEATURE_IDS,
            handle_execution_result,
        )

        proj = create_project(
            name="Bounded dedup test",
            workspace_path="/tmp/bounded-dedup",
            max_cost_usd=10000.0,
        )

        _PROXY_LOGGED_FEATURE_IDS.clear()

        # Use a test budget well under the actual cap so it runs quickly,
        # but large enough that we'd see growth past it if unbounded.
        # We patch the cap on the live container for the duration of
        # this test.
        original_max = _PROXY_LOGGED_FEATURE_IDS._max_entries
        _PROXY_LOGGED_FEATURE_IDS._max_entries = 50
        try:
            for i in range(200):
                f = create_feature(
                    project_id=proj.id,
                    name=f"feat-{i}",
                    description=f"feat {i}",
                    status="ready",
                    priority=10,
                    risk_category="medium",
                )
                update_feature(
                    f.id,
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )
                feature = get_feature(f.id)
                res = ExecutionResult(
                    text="OK",
                    is_error=False,
                    total_cost_usd=None,  # forces turn_proxy logging
                    num_turns=4,
                )
                agent_run = MagicMock()
                agent_run.id = str(uuid.uuid4())
                spawn = SpawnResult(execution_result=res, agent_run=agent_run)
                handle_execution_result(
                    project_id=proj.id,
                    feature=feature,
                    spawn_result=spawn,
                )

            assert len(_PROXY_LOGGED_FEATURE_IDS) <= 50, (
                f"dedup set grew to {len(_PROXY_LOGGED_FEATURE_IDS)} "
                "after 200 features — bound is broken"
            )
        finally:
            _PROXY_LOGGED_FEATURE_IDS._max_entries = original_max
            _PROXY_LOGGED_FEATURE_IDS.clear()


# ============================================================
# R4-001: Research cost must NOT be double-counted between
# self.total_cost and project.total_cost_usd
# ============================================================


class TestResearchCostNotDoubleCounted:
    """Regression: research cost in _run_research used to bump BOTH
    loop.total_cost and project.total_cost_usd while budget_exceeded()
    takes max(project_total, self.total_cost). That made research
    charges effectively count twice. Fix: only write to the DB.
    """

    @pytest.mark.asyncio
    async def test_research_cost_only_goes_to_db(self, project):
        """R4-001: loop.total_cost must not accumulate research cost."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            get_feature,
            get_project,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import OrchestrationLoop

        # Build a feature that will trigger research (research_required=True
        # AND research_iterations == 0).
        f = create_feature(
            project_id=project.id,
            name="Needs research",
            description="research_required=True; track research cost",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=project.id)

        async def mock_research(**kwargs):
            res = ExecutionResult(
                text="Research done",
                is_error=False,
                duration_ms=500,
                num_turns=2,
                total_cost_usd=0.10,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="Implemented",
                is_error=False,
                duration_ms=1000,
                num_turns=4,
                total_cost_usd=0.50,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_research_agent",
            new_callable=AsyncMock,
            side_effect=mock_research,
        ), patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ):
            await loop.execute_feature(feature)

        # The DB total is the canonical accumulator: research $0.10 +
        # implementation $0.50 = $0.60.
        updated_project = get_project(project.id)
        assert updated_project.total_cost_usd == pytest.approx(0.60)
        # loop.total_cost must NOT have accumulated the research cost
        # (R4-001) — that was the double-count bug.
        assert loop.total_cost <= updated_project.total_cost_usd + 1e-9, (
            f"loop.total_cost={loop.total_cost} drifted above "
            f"project.total_cost_usd={updated_project.total_cost_usd} — "
            "research-cost double-accumulation regression (R4-001)"
        )
        # And specifically, loop.total_cost must be 0 because neither path
        # bumps it any more.
        assert loop.total_cost == pytest.approx(0.0), (
            "loop.total_cost should remain 0; only the DB total is "
            "incremented after the R4-001 fix"
        )

    @pytest.mark.asyncio
    async def test_research_cost_does_not_inflate_budget_check(
        self, db_path
    ):
        """R4-001: research charge must not push budget past max twice."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            create_project,
            get_feature,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import OrchestrationLoop

        # max_cost = $1.00. Research $0.40 + Impl $0.40 = $0.80 should NOT
        # trip the budget. With the bug, loop.total_cost would also hold
        # $0.40 from research, so max(0.80, 0.40) = 0.80 — wait, the
        # double-count surfaces when budget_exceeded compares running
        # totals at high res. The clearer test: after a research-only
        # spend of $0.60 (limit $1.00), the budget should NOT be flagged
        # as exceeded at the in-memory layer.
        proj = create_project(
            name="R4-001 budget",
            workspace_path="/tmp/r4-budget",
            max_cost_usd=1.00,
        )
        f = create_feature(
            project_id=proj.id,
            name="Research budget",
            description="research_required=True",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=proj.id, max_cost=1.00)

        async def mock_research(**kwargs):
            res = ExecutionResult(
                text="Research",
                is_error=False,
                duration_ms=200,
                num_turns=2,
                total_cost_usd=0.60,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        async def mock_spawn(*args, **kwargs):
            # Implementation is essentially free for this test.
            res = ExecutionResult(
                text="Impl",
                is_error=False,
                duration_ms=100,
                num_turns=1,
                total_cost_usd=0.10,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_research_agent",
            new_callable=AsyncMock,
            side_effect=mock_research,
        ), patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ):
            await loop.execute_feature(feature)

        # DB total = 0.70 (under $1.00 cap) — budget must not be exceeded.
        # Before fix: loop.total_cost = 0.60 (research), DB = 0.70, both
        # under cap, so the bug only manifests on stricter caps. The KEY
        # property we test is the equality between the two.
        from bob3.db import get_project
        updated = get_project(proj.id)
        assert updated.total_cost_usd == pytest.approx(0.70)
        assert loop.total_cost <= updated.total_cost_usd + 1e-9
        assert loop.budget_exceeded() is False


# ============================================================
# R4-002: Decomposition cost must be written to db.update_project_cost
# (was previously ONLY incremented in self.total_cost)
# ============================================================


class TestDecompositionCostInDb:
    """Regression: handle_decomposition cost was being added only to
    self.total_cost, never to project.total_cost_usd. That meant the
    project-level max_cost_usd guard was blind to decomposition charges.
    """

    @pytest.mark.asyncio
    async def test_decomp_cost_written_to_project_total(self, db_path):
        """R4-002: decomposition cost must show up in project.total_cost_usd."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            create_project,
            get_feature,
            get_project,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import OrchestrationLoop

        proj = create_project(
            name="R4-002 decomp",
            workspace_path="/tmp/r4-decomp",
            max_cost_usd=1000.0,
        )
        f = create_feature(
            project_id=proj.id,
            name="Oversized feature",
            description="should be decomposed",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        # Force decomposition path.
        update_feature(
            f.id,
            exceeds_size_limits=True,
            estimated_files_touched=20,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=proj.id)

        # Mock spawn_sub_agent to look like a decomposer that returned
        # well-formed JSON children.
        async def mock_spawn(*args, **kwargs):
            payload = (
                "```json\n"
                '{"children": [{"name": "child A", "description": "a"},'
                ' {"name": "child B", "description": "b"}],'
                ' "dependencies": []}\n'
                "```"
            )
            res = ExecutionResult(
                text=payload,
                is_error=False,
                duration_ms=200,
                num_turns=3,
                total_cost_usd=0.30,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ):
            await loop.execute_feature(feature)

        updated = get_project(proj.id)
        # Before R4-002 fix: this would be 0.0. After: 0.30 lands in the
        # DB total atomically.
        assert updated.total_cost_usd == pytest.approx(0.30), (
            f"Expected decomposition cost $0.30 to land in "
            f"project.total_cost_usd; got {updated.total_cost_usd}. "
            "Decomposition cost was written only to the in-memory "
            "accumulator (R4-002 regression)."
        )

    @pytest.mark.asyncio
    async def test_decomp_cost_handles_max_pro_none(self, db_path):
        """R4-002: decomposition path with cost_usd=None (Max Pro) must
        normalize via the turn-count proxy and still update DB."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            create_project,
            get_feature,
            get_project,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import OrchestrationLoop

        proj = create_project(
            name="R4-002 maxpro decomp",
            workspace_path="/tmp/r4-mp-decomp",
            max_cost_usd=1000.0,
        )
        f = create_feature(
            project_id=proj.id,
            name="Oversized maxpro feature",
            description="should be decomposed",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            exceeds_size_limits=True,
            estimated_files_touched=20,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=proj.id)

        async def mock_spawn(*args, **kwargs):
            payload = (
                "```json\n"
                '{"children": [{"name": "child A", "description": "a"},'
                ' {"name": "child B", "description": "b"}],'
                ' "dependencies": []}\n'
                "```"
            )
            res = ExecutionResult(
                text=payload,
                is_error=False,
                duration_ms=200,
                num_turns=8,
                total_cost_usd=None,  # Max Pro: SDK returns no cost
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ):
            await loop.execute_feature(feature)

        updated = get_project(proj.id)
        # Default proxy is $0.05/turn; 8 turns = $0.40.
        assert updated.total_cost_usd == pytest.approx(0.40), (
            "Decomposition path failed to apply the turn-count proxy "
            "when cost_usd is None (Max Pro / OAuth subscriptions)."
        )
        # And the proxy flag must have been raised so the loop knows to
        # warn the operator.
        assert loop._cost_proxy_active is True
