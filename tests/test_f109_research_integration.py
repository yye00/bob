"""Tests for F109: Research mode in orchestration loop.

Validates that:
- Step 1: Check research_required before execution (research_iterations > 0 or RCA NEEDS_RESEARCH)
- Step 2: Spawn research agent when needed
- Step 3: Store results in research_results table
- Step 4: Mark research_complete (increment research_iterations)
- Step 5: Continue to implementation after research
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3 import db
from bob3.models import Feature, SubAgentRun
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import (
    OrchestrationLoop,
    LoopTermination,
    needs_research,
    count_feature_failures,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "test.db"
    db.init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def project(tmp_db):
    """Create a test project."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        return db.create_project(
            name="research-test-project",
            workspace_path="/tmp/test-research-project",
            max_cost_usd=100.0,
        )


@pytest.fixture
def ready_feature(tmp_db, project):
    """Create a single ready feature."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        f = db.create_feature(
            project_id=project.id,
            name="Research Feature",
            description="A feature that needs research",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        db.update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        return db.get_feature(f.id)


def _make_spawn_result(*, is_error=False, text="done", cost=0.50):
    """Helper to create a SpawnResult with mock agent_run."""
    mock_result = ExecutionResult(
        text=text,
        is_error=is_error,
        error_message="Error" if is_error else "",
        duration_ms=1000,
        num_turns=5,
        total_cost_usd=cost,
    )
    mock_agent_run = MagicMock()
    mock_agent_run.id = str(uuid.uuid4())
    return SpawnResult(execution_result=mock_result, agent_run=mock_agent_run)


# ===================================================================
# Step 1: Check research_required before execution
# ===================================================================


class TestNeedsResearch:
    """Step 1: needs_research() checks if a feature requires research."""

    def test_feature_with_zero_research_iterations_no_failures(self, tmp_db, ready_feature):
        """Feature with no research iterations and no failures doesn't need research."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            assert needs_research(ready_feature, ready_feature.project_id) is False

    def test_feature_with_description_containing_research_required(self, tmp_db, project):
        """Feature whose description flags research_required=True needs research."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Researchy Feature",
                description="research_required=True; Must investigate API compatibility",
                status="ready",
                priority=10,
            )
            db.update_feature(
                f.id,
                readiness_score=0.9,
            )
            feature = db.get_feature(f.id)
            assert needs_research(feature, project.id) is True

    def test_feature_with_research_iterations_already_done(self, tmp_db, project):
        """Feature that already has research_iterations >= 1 doesn't need more research."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Already Researched",
                description="research_required=True; Something to investigate",
                status="ready",
                priority=10,
            )
            db.update_feature(f.id, research_iterations=1, readiness_score=0.9)
            feature = db.get_feature(f.id)
            assert needs_research(feature, project.id) is False

    def test_feature_with_3_plus_failures_needs_research(self, tmp_db, project):
        """Feature that failed 3+ times triggers research."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Failing Feature",
                description="Keeps failing",
                status="ready",
                priority=10,
            )
            # Create 3 failed agent runs targeting this feature
            for _ in range(3):
                run = db.create_agent_run(
                    project_id=project.id,
                    purpose="implement_feature",
                    target_type="feature",
                    target_id=f.id,
                    status="running",
                )
                db.update_agent_run(run.id, status="failed")

            feature = db.get_feature(f.id)
            assert needs_research(feature, project.id) is True

    def test_feature_with_1_failure_no_research(self, tmp_db, project):
        """Feature with only 1 failure does not trigger Trigger 2 at the default threshold (2)."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Failing Feature",
                description="Failing",
                status="ready",
                priority=10,
            )
            # Set confidence scores above the 0.5 threshold so only
            # the failure-count trigger is being tested here.
            db.update_feature(
                f.id,
                conf_impl_correctness=0.8,
                conf_spec_understanding=0.8,
                readiness_score=0.8,
            )
            run = db.create_agent_run(
                project_id=project.id,
                purpose="implement_feature",
                target_type="feature",
                target_id=f.id,
                status="running",
            )
            db.update_agent_run(run.id, status="failed")

            feature = db.get_feature(f.id)
            # Default threshold is 2 (R10-010); 1 failure is below it.
            assert needs_research(feature, project.id) is False

    def test_feature_with_2_failures_triggers_research(self, tmp_db, project):
        """Feature with 2 failures triggers research at the new default threshold (R10-010)."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Failing Feature",
                description="Failing",
                status="ready",
                priority=10,
            )
            db.update_feature(
                f.id,
                conf_impl_correctness=0.8,
                conf_spec_understanding=0.8,
                readiness_score=0.8,
            )
            for _ in range(2):
                run = db.create_agent_run(
                    project_id=project.id,
                    purpose="implement_feature",
                    target_type="feature",
                    target_id=f.id,
                    status="running",
                )
                db.update_agent_run(run.id, status="failed")

            feature = db.get_feature(f.id)
            # Default threshold lowered from 3 → 2 in R10-010.
            assert needs_research(feature, project.id) is True

    def test_feature_with_3_failures_but_already_researched(self, tmp_db, project):
        """Feature that failed 3+ times but already has research_iterations >= 1 doesn't re-research."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Failing But Researched",
                description="Keeps failing",
                status="ready",
                priority=10,
            )
            db.update_feature(f.id, research_iterations=1)
            for _ in range(3):
                run = db.create_agent_run(
                    project_id=project.id,
                    purpose="implement_feature",
                    target_type="feature",
                    target_id=f.id,
                    status="running",
                )
                db.update_agent_run(run.id, status="failed")

            feature = db.get_feature(f.id)
            assert needs_research(feature, project.id) is False


class TestCountFeatureFailures:
    """Test count_feature_failures counts failed agent runs for a feature."""

    def test_zero_failures(self, tmp_db, project, ready_feature):
        """Returns 0 when no agent runs have failed for the feature."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            assert count_feature_failures(ready_feature.id, project.id) == 0

    def test_counts_failed_runs(self, tmp_db, project):
        """Counts only failed agent runs for the feature."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Fail Counter",
                description="test",
                status="ready",
                priority=10,
            )
            # 2 failed, 1 completed
            for status in ["failed", "failed", "completed"]:
                run = db.create_agent_run(
                    project_id=project.id,
                    purpose="implement_feature",
                    target_type="feature",
                    target_id=f.id,
                    status="running",
                )
                db.update_agent_run(run.id, status=status)

            assert count_feature_failures(f.id, project.id) == 2

    def test_only_counts_implement_feature_purpose(self, tmp_db, project):
        """Only counts runs with purpose='implement_feature'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Purpose Filter",
                description="test",
                status="ready",
                priority=10,
            )
            # 1 failed implement_feature, 1 failed rca_analyst (should not count)
            run1 = db.create_agent_run(
                project_id=project.id,
                purpose="implement_feature",
                target_type="feature",
                target_id=f.id,
                status="running",
            )
            db.update_agent_run(run1.id, status="failed")

            run2 = db.create_agent_run(
                project_id=project.id,
                purpose="rca_analyst",
                target_type="feature",
                target_id=f.id,
                status="running",
            )
            db.update_agent_run(run2.id, status="failed")

            assert count_feature_failures(f.id, project.id) == 1


# ===================================================================
# Step 2: Spawn research agent when needed
# ===================================================================


class TestResearchSpawning:
    """Step 2: The orchestration loop spawns a research agent when needed."""

    @pytest.mark.asyncio
    async def test_research_spawned_before_execution(self, tmp_db, project):
        """When needs_research is True, research agent is spawned before execution."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Research Then Implement",
                description="research_required=True; investigate the API",
                status="ready",
                priority=10,
            )
            db.update_feature(
                f.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            feature = db.get_feature(f.id)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            # Track which functions are called
            calls = []

            async def mock_research(*args, **kwargs):
                calls.append("research")
                return _make_spawn_result(text="Research findings: use XYZ library")

            async def mock_spawn(*args, **kwargs):
                calls.append("implement")
                return _make_spawn_result(text="Feature implemented")

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

            # Research should be called BEFORE implementation
            assert "research" in calls
            assert "implement" in calls
            assert calls.index("research") < calls.index("implement")

    @pytest.mark.asyncio
    async def test_no_research_when_not_needed(self, tmp_db, project, ready_feature):
        """When needs_research is False, no research agent is spawned."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            research_called = False

            async def mock_research(*args, **kwargs):
                nonlocal research_called
                research_called = True
                return _make_spawn_result()

            async def mock_spawn(*args, **kwargs):
                return _make_spawn_result(text="Feature done")

            with patch(
                "bob3.orchestrator.run_loop.spawn_research_agent",
                new_callable=AsyncMock,
                side_effect=mock_research,
            ), patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                await loop.execute_feature(ready_feature)

            assert research_called is False

    @pytest.mark.asyncio
    async def test_research_query_includes_feature_info(self, tmp_db, project):
        """The research query includes feature name and description."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="WebSocket Feature",
                description="research_required=True; Implement WebSocket support for real-time updates",
                status="ready",
                priority=10,
            )
            db.update_feature(f.id, readiness_score=0.9)
            feature = db.get_feature(f.id)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            captured_kwargs = {}

            async def mock_research(**kwargs):
                captured_kwargs.update(kwargs)
                return _make_spawn_result(text="Research results")

            async def mock_spawn(*args, **kwargs):
                return _make_spawn_result()

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

            assert "query" in captured_kwargs
            assert "WebSocket" in captured_kwargs["query"]


# ===================================================================
# Step 3: Store results in research_results table
# ===================================================================


class TestStoreResearchResults:
    """Step 3: Research results are stored in the database."""

    def test_create_research_result(self, tmp_db, project):
        """create_research_result stores findings in the database."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Test Feature",
                status="ready",
                priority=10,
            )
            result = db.create_research_result(
                feature_id=f.id,
                project_id=project.id,
                query="How to implement X?",
                findings="Use library Y with pattern Z",
            )
            assert result.id is not None
            assert result.feature_id == f.id
            assert result.project_id == project.id
            assert result.query == "How to implement X?"
            assert result.findings == "Use library Y with pattern Z"
            assert result.applied is False

    def test_get_research_results_for_feature(self, tmp_db, project):
        """list_research_results returns results for a given feature."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Test Feature",
                status="ready",
                priority=10,
            )
            db.create_research_result(
                feature_id=f.id,
                project_id=project.id,
                query="Query 1",
                findings="Finding 1",
            )
            db.create_research_result(
                feature_id=f.id,
                project_id=project.id,
                query="Query 2",
                findings="Finding 2",
            )
            results = db.list_research_results(feature_id=f.id)
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_research_results_stored_after_spawning(self, tmp_db, project):
        """After research agent completes, results are saved to research_results."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Store Results Feature",
                description="research_required=True; test storage",
                status="ready",
                priority=10,
            )
            db.update_feature(f.id, readiness_score=0.9)
            feature = db.get_feature(f.id)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            async def mock_research(**kwargs):
                return _make_spawn_result(text="Found: use asyncio.gather for concurrency")

            async def mock_spawn(*args, **kwargs):
                return _make_spawn_result()

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

            results = db.list_research_results(feature_id=f.id)
            assert len(results) == 1
            assert "asyncio.gather" in results[0].findings


# ===================================================================
# Step 4: Mark research_complete (increment research_iterations)
# ===================================================================


class TestMarkResearchComplete:
    """Step 4: research_iterations is incremented after research completes."""

    @pytest.mark.asyncio
    async def test_research_iterations_incremented(self, tmp_db, project):
        """After research, the feature's research_iterations is incremented."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Iterations Feature",
                description="research_required=True; test iterations",
                status="ready",
                priority=10,
            )
            db.update_feature(f.id, readiness_score=0.9)
            feature = db.get_feature(f.id)
            assert feature.research_iterations == 0

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            async def mock_research(**kwargs):
                return _make_spawn_result(text="Research findings")

            async def mock_spawn(*args, **kwargs):
                return _make_spawn_result()

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

            updated = db.get_feature(f.id)
            assert updated.research_iterations == 1

    @pytest.mark.asyncio
    async def test_no_increment_when_no_research(self, tmp_db, project, ready_feature):
        """When no research is needed, research_iterations stays at 0."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            async def mock_spawn(*args, **kwargs):
                return _make_spawn_result()

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                await loop.execute_feature(ready_feature)

            updated = db.get_feature(ready_feature.id)
            assert updated.research_iterations == 0


# ===================================================================
# Step 5: Continue to implementation after research
# ===================================================================


class TestContinueToImplementation:
    """Step 5: After research completes, implementation proceeds normally."""

    @pytest.mark.asyncio
    async def test_implementation_runs_after_research(self, tmp_db, project):
        """Implementation sub-agent is spawned after research completes."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Full Flow Feature",
                description="research_required=True; end to end",
                status="ready",
                priority=10,
            )
            db.update_feature(f.id, readiness_score=0.9)
            feature = db.get_feature(f.id)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            async def mock_research(**kwargs):
                return _make_spawn_result(text="Research done")

            async def mock_spawn(*args, **kwargs):
                return _make_spawn_result(text="Implementation complete")

            with patch(
                "bob3.orchestrator.run_loop.spawn_research_agent",
                new_callable=AsyncMock,
                side_effect=mock_research,
            ) as research_mock, patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ) as spawn_mock:
                result = await loop.execute_feature(feature)

            # Both were called
            research_mock.assert_called_once()
            spawn_mock.assert_called_once()

            # Feature ends up completed
            updated = db.get_feature(f.id)
            assert updated.status == "completed"

    @pytest.mark.asyncio
    async def test_implementation_still_runs_if_research_fails(self, tmp_db, project):
        """If research fails, implementation still proceeds (graceful degradation)."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Research Fails Feature",
                description="research_required=True; research will fail",
                status="ready",
                priority=10,
            )
            db.update_feature(f.id, readiness_score=0.9)
            feature = db.get_feature(f.id)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            async def mock_research(**kwargs):
                return _make_spawn_result(is_error=True, text="")

            async def mock_spawn(*args, **kwargs):
                return _make_spawn_result(text="Implemented anyway")

            with patch(
                "bob3.orchestrator.run_loop.spawn_research_agent",
                new_callable=AsyncMock,
                side_effect=mock_research,
            ), patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ) as spawn_mock:
                await loop.execute_feature(feature)

            # Implementation still runs even after research failure
            spawn_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_research_cost_tracked(self, tmp_db, project):
        """Research cost is added to the loop's total cost tracking."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Cost Tracking Feature",
                description="research_required=True; track costs",
                status="ready",
                priority=10,
            )
            db.update_feature(f.id, readiness_score=0.9)
            feature = db.get_feature(f.id)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            async def mock_research(**kwargs):
                return _make_spawn_result(cost=0.10, text="Research")

            async def mock_spawn(*args, **kwargs):
                return _make_spawn_result(cost=0.50, text="Impl")

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

            # Both research and implementation costs are tracked.
            # R4-001 (2026-04, follow-up): the research path used to bump
            # BOTH ``loop.total_cost`` and ``project.total_cost_usd``, while
            # ``budget_exceeded()`` took ``max(project_total, self.total_cost)``
            # — so the research charge was effectively double-counted
            # against the budget. The structural ``non-atomic-counter``
            # fix retired ``self.total_cost`` entirely; cost is now
            # written exclusively through ``OrchestrationLoop._increment_cost``.
            updated_project = db.get_project(project.id)
            assert updated_project.total_cost_usd == pytest.approx(0.60)
            # The canonical total lives only in the DB; the cached mirror
            # must equal it. ``self.total_cost`` no longer exists.
            assert loop._project_total_cost == pytest.approx(
                updated_project.total_cost_usd
            )
            assert not hasattr(loop, "total_cost")

    @pytest.mark.asyncio
    async def test_rca_needs_research_triggers_research(self, tmp_db, project):
        """When a feature has 3+ failures, research is triggered."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="RCA Triggered Research",
                description="Normal feature, no explicit research_required",
                status="ready",
                priority=10,
            )
            db.update_feature(f.id, readiness_score=0.9)

            # Create 3 failed runs
            for _ in range(3):
                run = db.create_agent_run(
                    project_id=project.id,
                    purpose="implement_feature",
                    target_type="feature",
                    target_id=f.id,
                    status="running",
                )
                db.update_agent_run(run.id, status="failed")

            feature = db.get_feature(f.id)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            research_called = False

            async def mock_research(**kwargs):
                nonlocal research_called
                research_called = True
                return _make_spawn_result(text="Research after failures")

            async def mock_spawn(*args, **kwargs):
                return _make_spawn_result()

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

            assert research_called is True


# ===================================================================
# Integration: Full loop with research
# ===================================================================


class TestFullLoopWithResearch:
    """Integration tests for the full orchestration loop with research mode."""

    @pytest.mark.asyncio
    async def test_loop_researches_and_completes(self, tmp_db, project):
        """Full loop: research-required feature gets researched then implemented."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = db.create_feature(
                project_id=project.id,
                name="Full Loop Research Feature",
                description="research_required=True; needs investigation",
                status="ready",
                priority=10,
            )
            db.update_feature(f.id, readiness_score=0.9)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            async def mock_research(**kwargs):
                return _make_spawn_result(text="Research complete")

            async def mock_spawn(*args, **kwargs):
                return _make_spawn_result(text="Implementation complete")

            with patch(
                "bob3.orchestrator.run_loop.spawn_research_agent",
                new_callable=AsyncMock,
                side_effect=mock_research,
            ), patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED

            updated = db.get_feature(f.id)
            assert updated.status == "completed"
            assert updated.research_iterations == 1
