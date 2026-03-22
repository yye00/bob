"""Tests for F069: 'bob3 run' with continuous orchestration loop.

Tests the orchestration loop that continuously processes features
until all are completed, all remaining are blocked, or budget is exceeded.
"""

import asyncio
import signal
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from bob3.cli import main
from bob3.db import (
    connect,
    create_feature,
    create_project,
    get_feature,
    get_ready_features,
    init_database,
    list_features,
    update_feature,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import (
    OrchestrationLoop,
    LoopTermination,
    cascade_update_dependents,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "test.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def project(tmp_db):
    """Create a test project."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        return create_project(
            name="test-project",
            workspace_path="/tmp/test-project",
            max_cost_usd=100.0,
        )


@pytest.fixture
def ready_features(tmp_db, project):
    """Create multiple ready features with proper readiness scores."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        features = []
        for i in range(3):
            f = create_feature(
                project_id=project.id,
                name=f"Feature {i + 1}",
                description=f"Test feature {i + 1}",
                status="ready",
                priority=10 * (i + 1),
                risk_category="medium",
            )
            # Set confidence scores high enough to pass readiness
            update_feature(
                f.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            features.append(get_feature(f.id))
        return features


# ============================================================
# OrchestrationLoop unit tests
# ============================================================


class TestOrchestrationLoopInit:
    """Test OrchestrationLoop initialization."""

    def test_init_with_project_id(self, tmp_db, project):
        """Step 1: OrchestrationLoop can be initialized with a project_id."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            assert loop.project_id == project.id
            assert loop.max_cost is None

    def test_init_with_max_cost(self, tmp_db, project):
        """Step 2: OrchestrationLoop accepts a max_cost budget limit."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id, max_cost=50.0)
            assert loop.max_cost == 50.0


class TestBudgetCheck:
    """Test budget checking before each iteration."""

    def test_budget_not_exceeded_when_no_limit(self, tmp_db, project):
        """Step 2: No budget limit means budget is never exceeded."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            assert loop.budget_exceeded() is False

    def test_budget_not_exceeded_when_under_limit(self, tmp_db, project):
        """Step 2: Budget is not exceeded when cost is under the limit."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id, max_cost=100.0)
            loop.total_cost = 50.0
            assert loop.budget_exceeded() is False

    def test_budget_exceeded_when_over_limit(self, tmp_db, project):
        """Step 2: Budget is exceeded when cost meets the limit."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id, max_cost=100.0)
            loop.total_cost = 100.0
            assert loop.budget_exceeded() is True

    def test_budget_exceeded_when_project_cost_over_limit(self, tmp_db, project):
        """Step 2: Budget check also reads project's max_cost_usd."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import update_project
            update_project(project.id, total_cost_usd=110.0, max_cost_usd=100.0)
            loop = OrchestrationLoop(project_id=project.id)
            assert loop.budget_exceeded() is True


class TestFindNextReadyFeature:
    """Test querying features_ready view for the next feature."""

    def test_returns_none_when_no_ready_features(self, tmp_db, project):
        """Step 3: Returns None when no features are ready."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            assert loop.find_next_ready_feature() is None

    def test_returns_highest_priority_feature(self, tmp_db, project, ready_features):
        """Step 3: Returns the highest priority ready feature."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            feature = loop.find_next_ready_feature()
            assert feature is not None
            assert feature.name == "Feature 1"  # priority=10 is highest

    def test_skips_non_ready_features(self, tmp_db, project, ready_features):
        """Step 3: Does not return features with non-ready status."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Set first feature to executing
            update_feature(ready_features[0].id, status="executing")
            loop = OrchestrationLoop(project_id=project.id)
            feature = loop.find_next_ready_feature()
            assert feature is not None
            assert feature.name == "Feature 2"  # priority=20 is next


class TestAllFeaturesCompleted:
    """Test checking if all features are completed."""

    def test_returns_true_when_all_completed(self, tmp_db, project, ready_features):
        """Step 1: Returns True when all features have status 'completed'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            for f in ready_features:
                update_feature(f.id, status="completed")
            loop = OrchestrationLoop(project_id=project.id)
            assert loop.all_features_completed() is True

    def test_returns_false_when_some_pending(self, tmp_db, project, ready_features):
        """Step 1: Returns False when some features are not completed."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            update_feature(ready_features[0].id, status="completed")
            loop = OrchestrationLoop(project_id=project.id)
            assert loop.all_features_completed() is False


class TestAllRemainingBlocked:
    """Test checking if all remaining features are blocked."""

    def test_returns_true_when_all_remaining_are_blocked(self, tmp_db, project, ready_features):
        """Returns True when all non-completed features are in a blocked state."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            update_feature(ready_features[0].id, status="completed")
            update_feature(ready_features[1].id, status="failed")
            update_feature(ready_features[2].id, status="blocked_by_dependency")
            loop = OrchestrationLoop(project_id=project.id)
            assert loop.all_remaining_blocked() is True

    def test_returns_false_when_some_are_ready(self, tmp_db, project, ready_features):
        """Returns False when some features are still ready."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            update_feature(ready_features[0].id, status="completed")
            # Features 2 and 3 are still 'ready'
            loop = OrchestrationLoop(project_id=project.id)
            assert loop.all_remaining_blocked() is False


class TestCascadeUpdateDependents:
    """Test cascade update of dependent features after completion."""

    def test_cascade_updates_dependent_status(self, tmp_db, project):
        """Step 5: After completing a feature, its dependents become ready (F123)."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import add_feature_dependency

            # Feature A (dependency) and Feature B (depends on A)
            feat_a = create_feature(
                project_id=project.id,
                name="Feature A",
                status="completed",
                priority=10,
            )
            feat_b = create_feature(
                project_id=project.id,
                name="Feature B",
                status="pending",
                priority=20,
            )
            # Set readiness above medium threshold (0.80)
            update_feature(feat_b.id, readiness_score=0.85)
            add_feature_dependency(
                feature_id=feat_b.id,
                depends_on_feature_id=feat_a.id,
            )

            # Cascade update after A is completed
            cascade_update_dependents(feat_a.id)

            # Feature B should now be 'ready' (F123: pending -> ready)
            updated_b = get_feature(feat_b.id)
            assert updated_b.status == "ready"

    def test_cascade_does_not_unblock_if_other_deps_remain(self, tmp_db, project):
        """Step 5: Dependents stay pending if other dependencies are not completed (F123)."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import add_feature_dependency

            feat_a = create_feature(
                project_id=project.id, name="A", status="completed", priority=10,
            )
            feat_c = create_feature(
                project_id=project.id, name="C", status="pending", priority=10,
            )
            feat_b = create_feature(
                project_id=project.id, name="B", status="pending", priority=20,
            )
            update_feature(feat_b.id, readiness_score=0.85)
            add_feature_dependency(feature_id=feat_b.id, depends_on_feature_id=feat_a.id)
            add_feature_dependency(feature_id=feat_b.id, depends_on_feature_id=feat_c.id)

            cascade_update_dependents(feat_a.id)

            updated_b = get_feature(feat_b.id)
            assert updated_b.status == "pending"


class TestSpawnSubAgent:
    """Test spawning a sub-agent to implement a feature."""

    @pytest.mark.asyncio
    async def test_spawn_sets_feature_to_executing(self, tmp_db, project, ready_features):
        """Step 4: Feature status is set to 'executing' before spawning."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            feature = ready_features[0]

            mock_result = ExecutionResult(
                text="Feature implemented successfully",
                is_error=False,
                duration_ms=1000,
                num_turns=5,
                total_cost_usd=0.50,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                ),
            ):
                await loop.execute_feature(feature)

            updated = get_feature(feature.id)
            assert updated.status == "completed"

    @pytest.mark.asyncio
    async def test_spawn_failure_sets_feature_to_failed(self, tmp_db, project, ready_features):
        """Step 4: Feature status is 'failed' when sub-agent reports an error."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            feature = ready_features[0]

            mock_result = ExecutionResult(
                text="",
                is_error=True,
                error_message="Build failed",
                duration_ms=500,
                num_turns=3,
                total_cost_usd=0.25,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                ),
            ):
                await loop.execute_feature(feature)

            updated = get_feature(feature.id)
            # F071: First failure resets to 'ready' for retry (not permanently failed)
            assert updated.status == "ready"
            assert updated.refinement_attempts == 1


class TestGracefulShutdown:
    """Test graceful shutdown signal handling."""

    def test_shutdown_flag_set_on_signal(self, tmp_db, project):
        """Step 6: Setting shutdown flag stops the loop."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            assert loop.shutdown_requested is False
            loop.request_shutdown()
            assert loop.shutdown_requested is True


class TestContinuousLoop:
    """Test the continuous orchestration loop processes multiple features."""

    @pytest.mark.asyncio
    async def test_loop_processes_multiple_features(self, tmp_db, project, ready_features):
        """Step 7: Multiple features complete in sequence without manual restart."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            call_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                mock_result = ExecutionResult(
                    text=f"Implemented feature {call_count}",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=0.50,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            assert call_count == 3
            assert termination == LoopTermination.ALL_COMPLETED

            # Verify all features are completed
            for f in ready_features:
                updated = get_feature(f.id)
                assert updated.status == "completed"

    @pytest.mark.asyncio
    async def test_loop_stops_on_budget_exceeded(self, tmp_db, project, ready_features):
        """Step 2: Loop terminates when budget is exceeded."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id, max_cost=0.75)

            call_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                mock_result = ExecutionResult(
                    text=f"Implemented feature {call_count}",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=0.50,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            # Should have processed 1 feature (cost 0.50), then stopped on 2nd check (total 0.50 < 0.75, process 2nd -> total 1.0 > 0.75)
            assert call_count == 2
            assert termination == LoopTermination.BUDGET_EXCEEDED

    @pytest.mark.asyncio
    async def test_loop_stops_on_shutdown_signal(self, tmp_db, project, ready_features):
        """Step 6: Loop terminates on graceful shutdown signal."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            call_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                # After first feature, request shutdown
                if call_count >= 1:
                    loop.request_shutdown()
                mock_result = ExecutionResult(
                    text=f"Implemented feature {call_count}",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=0.50,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            assert call_count == 1
            assert termination == LoopTermination.SHUTDOWN_REQUESTED

    @pytest.mark.asyncio
    async def test_loop_stops_when_all_blocked(self, tmp_db, project):
        """Loop terminates when all remaining features are blocked."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Create features that are all blocked
            for i in range(2):
                f = create_feature(
                    project_id=project.id,
                    name=f"Blocked Feature {i + 1}",
                    status="failed",
                    priority=10 * (i + 1),
                )
            loop = OrchestrationLoop(project_id=project.id)
            termination = await loop.run()
            assert termination == LoopTermination.ALL_BLOCKED

    @pytest.mark.asyncio
    async def test_loop_stops_when_no_features(self, tmp_db, project):
        """Loop terminates immediately when project has no features."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            termination = await loop.run()
            assert termination == LoopTermination.ALL_COMPLETED

    @pytest.mark.asyncio
    async def test_loop_accumulates_cost(self, tmp_db, project, ready_features):
        """Loop tracks cumulative cost across features."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn(*args, **kwargs):
                mock_result = ExecutionResult(
                    text="done",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=1.25,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                await loop.run()

            assert loop.total_cost == pytest.approx(3.75)  # 3 features * 1.25


class TestCLIRunCommand:
    """Test the CLI 'bob3 run' command integration."""

    def test_run_all_invokes_loop(self, tmp_db, project, ready_features):
        """Step 1: 'bob3 run --all' starts the orchestration loop."""
        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.cli._run_orchestration_loop",
                    return_value=LoopTermination.ALL_COMPLETED,
                ) as mock_loop:
                    result = runner.invoke(main, ["run", "--all"])
                    assert result.exit_code == 0
                    mock_loop.assert_called_once()

    def test_run_with_max_cost(self, tmp_db, project):
        """Step 2: 'bob3 run --all --max-cost 50' passes budget to loop."""
        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.cli._run_orchestration_loop",
                    return_value=LoopTermination.ALL_COMPLETED,
                ) as mock_loop:
                    result = runner.invoke(main, ["run", "--all", "--max-cost", "50"])
                    assert result.exit_code == 0
                    mock_loop.assert_called_once()
                    # Verify max_cost was passed
                    call_kwargs = mock_loop.call_args
                    assert call_kwargs[1].get("max_cost") == 50.0 or (
                        len(call_kwargs[0]) > 1 and call_kwargs[0][1] == 50.0
                    )
