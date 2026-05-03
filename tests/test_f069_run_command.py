"""Tests for F069: 'bob3 run' with continuous orchestration loop.

Tests the orchestration loop that continuously processes features
until all are completed, all remaining are blocked, or budget is exceeded.
"""

import asyncio
import os
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
            # ``self.total_cost`` was retired (recurring pattern
            # ``non-atomic-counter`` structural fix). Drive the cached
            # canonical value directly — that is what budget_exceeded()
            # actually consults.
            loop._project_total_cost = 50.0
            assert loop.budget_exceeded() is False

    def test_budget_exceeded_when_over_limit(self, tmp_db, project):
        """Step 2: Budget is exceeded when cost meets the limit."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id, max_cost=100.0)
            loop._project_total_cost = 100.0
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
        """Loop tracks cumulative cost across features.

        Cost is now tracked atomically in the DB (project.total_cost_usd)
        rather than in a separate in-memory accumulator that could drift.
        Bug 1 regression test: self.total_cost is no longer incremented in
        execute_feature; the canonical total lives in the DB.
        """
        from bob3.db import get_project

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

            # Project DB total is the canonical accumulator: 3 features * 1.25
            updated_project = get_project(project.id)
            assert updated_project.total_cost_usd == pytest.approx(3.75)


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


# ============================================================
# Bug 4: --feature truly scopes to a single feature
# ============================================================


class TestRunFeatureScoping:
    """'bob3 run --feature <id>' must run ONLY that feature."""

    def test_run_feature_only_runs_target(self, tmp_db, project, ready_features):
        """Bug 4 regression: --feature A must NOT run feature B.

        Set up two ready features A and B in the same project. Invoke
        'bob3 run --feature <A.id>' via CliRunner. Assert that A's status
        changed (was processed) AND B's status is unchanged. Assert
        exactly one spawn_sub_agent call.
        """
        feat_a = ready_features[0]
        feat_b = ready_features[1]

        async def mock_spawn(*args, **kwargs):
            mock_result = ExecutionResult(
                text="done",
                is_error=False,
                duration_ms=1000,
                num_turns=5,
                total_cost_usd=0.25,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())
            return SpawnResult(
                execution_result=mock_result,
                agent_run=mock_agent_run,
            )

        spawn_mock = AsyncMock(side_effect=mock_spawn)

        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.orchestrator.run_loop.spawn_sub_agent", spawn_mock
                ):
                    result = runner.invoke(main, ["run", "--feature", feat_a.id])
                    assert result.exit_code == 0, result.output

            # Exactly one spawn — only A.
            assert spawn_mock.call_count == 1, (
                f"Expected exactly 1 spawn for --feature scoping, "
                f"got {spawn_mock.call_count}"
            )

            # A was processed.
            updated_a = get_feature(feat_a.id)
            assert updated_a.status == "completed", (
                f"Feature A should be completed, got {updated_a.status}"
            )

            # B was NOT processed — still 'ready' from the fixture.
            updated_b = get_feature(feat_b.id)
            assert updated_b.status == "ready", (
                f"Feature B should be untouched (ready), got {updated_b.status}"
            )

    def test_run_feature_with_tiny_max_cost_returns_budget_exceeded(
        self, tmp_db, project, ready_features
    ):
        """Bug 3 regression: --feature must honour --max-cost.

        Pre-populate the project total_cost_usd above the max_cost so
        budget_exceeded() trips before the feature is spawned. Assert
        that no spawn occurred.
        """
        from bob3.db import update_project

        feat_a = ready_features[0]

        # Pre-populate so the budget is already exceeded.
        update_project(project.id, total_cost_usd=0.50)

        spawn_mock = AsyncMock()

        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.orchestrator.run_loop.spawn_sub_agent", spawn_mock
                ):
                    result = runner.invoke(
                        main,
                        [
                            "run",
                            "--feature",
                            feat_a.id,
                            "--max-cost",
                            "0.01",
                        ],
                    )
                    # R5-008: BUDGET_EXCEEDED must surface as exit code 3
                    # so 'bob3 run && deploy.sh' does not deploy on a
                    # partially-completed build.
                    assert result.exit_code == 3, result.output

            # Budget gate should have prevented any spawn.
            assert spawn_mock.call_count == 0, (
                f"Expected 0 spawns when budget already exceeded, "
                f"got {spawn_mock.call_count}"
            )
            # And the message should say budget exceeded.
            assert "Budget" in result.output or "budget" in result.output

    def test_run_feature_pending_with_unmet_deps_is_blocked(self, tmp_db, project):
        """Bug 5 regression: a 'pending' target whose deps are not all
        completed must NOT run; the loop returns ALL_BLOCKED.
        """
        from bob3.db import (
            add_feature_dependency,
            create_feature,
            update_feature,
        )

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Dependency that is NOT completed.
            dep = create_feature(
                project_id=project.id,
                name="Dep",
                status="pending",
                priority=10,
            )
            target = create_feature(
                project_id=project.id,
                name="Target",
                status="pending",
                priority=20,
            )
            update_feature(
                target.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            add_feature_dependency(
                feature_id=target.id, depends_on_feature_id=dep.id
            )

            spawn_mock = AsyncMock()

            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.orchestrator.run_loop.spawn_sub_agent", spawn_mock
                ):
                    runner = CliRunner()
                    result = runner.invoke(
                        main, ["run", "--feature", target.id]
                    )
                    # R5-008: ALL_BLOCKED must surface as exit code 2 so
                    # CI scripts (``bob3 run && deploy.sh``) do not
                    # deploy on a build whose work could not run.
                    assert result.exit_code == 2, result.output

            # No spawn should have happened.
            assert spawn_mock.call_count == 0
            # The CLI prints "Feature is blocked." for ALL_BLOCKED in
            # single-feature mode.
            assert "blocked" in result.output.lower()

            # Target stayed pending (its dep is not yet completed). The
            # dep itself was pending-with-no-declared-deps, so the
            # orchestrator's pending-no-deps recovery (commit 3d2e059)
            # legitimately promoted it to 'ready' — that's correct
            # behavior, just not what this test originally asserted.
            assert get_feature(target.id).status == "pending"
            assert get_feature(dep.id).status in ("pending", "ready")


# ============================================================
# Concurrency: per-project file lock prevents two concurrent
# bob3 run invocations from racing on the same project.
# ============================================================


class TestRunLockConcurrency:
    """Step: only one ``bob3 run`` at a time per project.

    With WAL + busy_timeout, two concurrent runs would no longer crash
    with ``database is locked``, but they'd interleave: both processes
    would pick "ready" features, both would write status='executing',
    and the resulting cascade order is whatever the OS scheduler
    decides. The fix is an exclusive advisory ``flock`` on
    ``<workspace>/.bob3.lock``; the second invocation must fail fast
    with :class:`AlreadyRunningError` and exit with code 1.
    """

    def test_acquire_run_lock_returns_handle(self, tmp_path):
        """First acquisition succeeds and creates the lock file."""
        from bob3.orchestrator.run_loop import (
            acquire_run_lock,
            release_run_lock,
        )

        handle = acquire_run_lock(tmp_path)
        try:
            assert handle is not None
            assert (tmp_path / ".bob3.lock").exists()
        finally:
            release_run_lock(handle)

    def test_second_concurrent_acquire_raises(self, tmp_path):
        """A second acquire while the lock is held raises AlreadyRunningError."""
        from bob3.orchestrator.run_loop import (
            AlreadyRunningError,
            acquire_run_lock,
            release_run_lock,
        )

        first = acquire_run_lock(tmp_path)
        try:
            with pytest.raises(AlreadyRunningError) as exc_info:
                acquire_run_lock(tmp_path)
            # Error message must be actionable for the user.
            msg = str(exc_info.value)
            assert "already in progress" in msg.lower()
            assert "refusing to start" in msg.lower()
        finally:
            release_run_lock(first)

    def test_lock_released_after_run_finishes(self, tmp_path):
        """Releasing the lock allows a fresh acquisition.

        Simulates: first ``bob3 run`` finishes (lock released), then a
        second ``bob3 run`` can proceed.
        """
        from bob3.orchestrator.run_loop import (
            acquire_run_lock,
            release_run_lock,
        )

        h1 = acquire_run_lock(tmp_path)
        release_run_lock(h1)
        h2 = acquire_run_lock(tmp_path)
        try:
            assert h2 is not None
        finally:
            release_run_lock(h2)

    def test_lock_released_via_subprocess_after_exit(self, tmp_path):
        """If the lock-holding process exits, the lock is freed.

        ``flock`` is held by the file descriptor; when the process dies
        the kernel cleans up its open files, dropping the lock. We
        simulate this by acquiring the lock in a child Python process
        that exits cleanly, and then verifying the parent can acquire.
        """
        import subprocess
        import sys
        import textwrap

        # Spawn a subprocess that acquires + releases (clean exit).
        script = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {repr(str(pathlib_root := __import__('pathlib').Path(__file__).resolve().parent.parent / 'src'))})
            from bob3.orchestrator.run_loop import acquire_run_lock
            h = acquire_run_lock({repr(str(tmp_path))})
            # Hold briefly, then exit (closes fd, releases lock).
        """)
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr

        # Now the parent can acquire.
        from bob3.orchestrator.run_loop import (
            acquire_run_lock,
            release_run_lock,
        )

        handle = acquire_run_lock(tmp_path)
        try:
            assert handle is not None
        finally:
            release_run_lock(handle)

    @pytest.mark.asyncio
    async def test_orchestration_loop_run_acquires_and_releases(
        self, tmp_db, project, ready_features, tmp_path
    ):
        """``OrchestrationLoop.run()`` must acquire-then-release the lock.

        Verifies the integration: after ``run()`` returns, the lock file
        should exist (created by the run) AND a fresh acquire from the
        same workspace must succeed (proving release happened).
        """
        from bob3.orchestrator.run_loop import (
            acquire_run_lock,
            release_run_lock,
        )

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
            )

            async def mock_spawn(*args, **kwargs):
                res = ExecutionResult(
                    text="ok",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=0.01,
                )
                agent_run = MagicMock()
                agent_run.id = str(uuid.uuid4())
                return SpawnResult(execution_result=res, agent_run=agent_run)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                await loop.run()

        # Lock file should exist (created during run).
        assert (workspace / ".bob3.lock").exists()
        # And we should be able to re-acquire (proves release happened).
        handle = acquire_run_lock(workspace)
        try:
            assert handle is not None
        finally:
            release_run_lock(handle)

    @pytest.mark.asyncio
    async def test_concurrent_run_rejected_when_lock_held(
        self, tmp_db, project, ready_features, tmp_path
    ):
        """Second ``OrchestrationLoop.run()`` is rejected while first holds lock."""
        from bob3.orchestrator.run_loop import (
            AlreadyRunningError,
            acquire_run_lock,
            release_run_lock,
        )

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Pre-acquire the lock to simulate "another bob3 run already
        # holds it". We don't release it inside the with-block.
        external_holder = acquire_run_lock(workspace)
        try:
            with patch("bob3.db.get_database_path", return_value=tmp_db):
                loop = OrchestrationLoop(
                    project_id=project.id,
                    workspace=str(workspace),
                )
                with pytest.raises(AlreadyRunningError):
                    await loop.run()
        finally:
            release_run_lock(external_holder)


# ============================================================
# Security: lock-file symlink attack hardening (R5-002)
# ============================================================


class TestRunLockSymlinkHardening:
    """``acquire_run_lock`` must refuse a tampered ``.bob3.lock``.

    A sub-agent with workspace write access can replace ``.bob3.lock``
    with a symlink to ``/dev/null`` (or any non-regular file) before the
    next ``bob3 run``. ``flock`` on a non-regular file's fd succeeds
    trivially — two concurrent runs would both pass the lock check and
    race on the database.

    Defenses:
      1. ``os.open(..., O_NOFOLLOW)`` raises ``ELOOP`` if the path is a
         symlink at open time → ``AlreadyRunningError``.
      2. ``fstat`` + ``S_ISREG`` rejects fifos / devices / directories
         that slipped past O_NOFOLLOW (e.g. a fresh fifo created at the
         path) → ``AlreadyRunningError``.
    """

    def test_lock_path_as_symlink_to_dev_null_is_refused(self, tmp_path):
        """``.bob3.lock`` -> /dev/null must raise AlreadyRunningError.

        This is the exploit that motivated R5-002. Without O_NOFOLLOW,
        ``flock`` on /dev/null's fd succeeds and two concurrent runs
        both proceed.
        """
        from bob3.orchestrator.run_loop import (
            AlreadyRunningError,
            acquire_run_lock,
        )

        lock_path = tmp_path / ".bob3.lock"
        # Build the symlink pointing at /dev/null.
        os.symlink("/dev/null", lock_path)
        assert lock_path.is_symlink()

        with pytest.raises(AlreadyRunningError) as exc_info:
            acquire_run_lock(tmp_path)
        msg = str(exc_info.value).lower()
        # Tampering hint must be visible to the operator so they know
        # this isn't an ordinary "another bob3 run" collision.
        assert "tamper" in msg or "symlink" in msg

    def test_lock_path_as_symlink_to_other_file_is_refused(self, tmp_path):
        """A symlink to any other regular file must also be refused.

        The attacker doesn't have to point at /dev/null specifically —
        any indirection breaks the per-project lock invariant. Even a
        symlink to a real file lets the attacker hold the flock on the
        target without the orchestrator noticing.
        """
        from bob3.orchestrator.run_loop import (
            AlreadyRunningError,
            acquire_run_lock,
        )

        target = tmp_path / "real_target.txt"
        target.write_text("decoy")
        lock_path = tmp_path / ".bob3.lock"
        os.symlink(target, lock_path)
        assert lock_path.is_symlink()

        with pytest.raises(AlreadyRunningError):
            acquire_run_lock(tmp_path)

    def test_lock_path_as_regular_file_works(self, tmp_path):
        """Regression: a plain regular file is accepted (the happy path).

        The hardening must not break the ordinary acquire path.
        """
        from bob3.orchestrator.run_loop import (
            acquire_run_lock,
            release_run_lock,
        )

        # Pre-create the lock file as a regular file (this is what
        # acquire_run_lock would create on its own anyway).
        lock_path = tmp_path / ".bob3.lock"
        lock_path.write_bytes(b"")
        assert not lock_path.is_symlink()

        handle = acquire_run_lock(tmp_path)
        try:
            assert handle is not None
            assert lock_path.exists()
        finally:
            release_run_lock(handle)

    def test_lock_path_as_fifo_is_refused(self, tmp_path):
        """A fifo at .bob3.lock must be refused by the S_ISREG check.

        A fifo isn't a symlink, so O_NOFOLLOW lets it through, but it
        also isn't a regular file — flock on a fifo behaves differently
        and is not a sound concurrency primitive. The S_ISREG check is
        the second defense layer.
        """
        from bob3.orchestrator.run_loop import (
            AlreadyRunningError,
            acquire_run_lock,
        )

        lock_path = tmp_path / ".bob3.lock"
        os.mkfifo(lock_path)
        assert lock_path.is_fifo()

        with pytest.raises(AlreadyRunningError) as exc_info:
            acquire_run_lock(tmp_path)
        msg = str(exc_info.value).lower()
        assert "regular file" in msg or "tamper" in msg


# ============================================================
# Security: cost-tampering detection (R5-003)
# ============================================================


class TestCostTamperDetection:
    """Sub-agents have FS access to ``bob3.db``; if they ``UPDATE projects
    SET total_cost_usd = 0`` they can effectively reset the budget. The
    orchestrator can't prevent the write, but it can DETECT it: it
    maintains an in-memory ``_expected_total_cost`` and clamps
    ``_project_total_cost`` to that value on refresh whenever the DB
    total has gone DOWN beyond floating-point slack.
    """

    def test_expected_total_cost_initialized_from_db(self, tmp_db, project):
        """``__init__`` seeds ``_expected_total_cost`` from the DB total.

        A resumed run that already had cost on the books must not
        falsely trip the tamper detector — the floor starts at the
        DB value at construction time.
        """
        from bob3.db import update_project_cost

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            update_project_cost(project_id=project.id, cost_usd=12.34)

            loop = OrchestrationLoop(project_id=project.id)
            assert loop._project_total_cost == pytest.approx(12.34)
            assert loop._expected_total_cost == pytest.approx(12.34)

    def test_db_total_dropped_to_zero_is_clamped(self, tmp_db, project, caplog):
        """Direct ``UPDATE projects SET total_cost_usd = 0`` is refused.

        Mirrors the R5-003 exploit: a sub-agent with FS access mutates
        the DB to reset the running cost. The next ``_refresh_project_cost_cache``
        must keep ``_project_total_cost`` at ``_expected_total_cost``,
        not the attacker-supplied 0.
        """
        from bob3.db import connect, update_project_cost

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id, max_cost=10.0)

            # Loop legitimately records $5.00 of cost.
            update_project_cost(project_id=project.id, cost_usd=5.0)
            loop._increment_expected_total_cost(5.0)
            loop._refresh_project_cost_cache()
            assert loop._project_total_cost == pytest.approx(5.0)
            assert loop._expected_total_cost == pytest.approx(5.0)

            # Sub-agent zeroes out the DB column.
            with connect() as conn:
                conn.execute(
                    "UPDATE projects SET total_cost_usd = 0 WHERE id = ?",
                    (project.id,),
                )

            with caplog.at_level("WARNING"):
                loop._refresh_project_cost_cache()

            # Cache must NOT be 0 — clamped to the expected total.
            assert loop._project_total_cost == pytest.approx(5.0), (
                "tamper-detection failed: cache was lowered to attacker value"
            )
            # SECURITY warning emitted with both totals named.
            joined = " ".join(r.getMessage() for r in caplog.records)
            assert "SECURITY" in joined
            assert "tamper" in joined.lower() or "reduced unexpectedly" in joined.lower()

    def test_legit_db_increase_lifts_expected_total(self, tmp_db, project):
        """A peer process recording cost must not be flagged as tampering.

        If another orchestrator (or this one, via a path that mirrored
        correctly) raised ``total_cost_usd``, the next refresh should
        accept the new value AND lift ``_expected_total_cost`` so
        subsequent refreshes have a coherent floor.
        """
        from bob3.db import update_project_cost

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            # Peer process bumps DB without us calling _increment.
            update_project_cost(project_id=project.id, cost_usd=7.0)
            loop._refresh_project_cost_cache()
            assert loop._project_total_cost == pytest.approx(7.0)
            assert loop._expected_total_cost == pytest.approx(7.0)

            # Now a tamper attempt drops DB to 1.0 — must be refused.
            from bob3.db import connect

            with connect() as conn:
                conn.execute(
                    "UPDATE projects SET total_cost_usd = 1.0 WHERE id = ?",
                    (project.id,),
                )
            loop._refresh_project_cost_cache()
            assert loop._project_total_cost == pytest.approx(7.0)

    def test_negative_increment_is_refused(self, tmp_db, project, caplog):
        """``_increment_expected_total_cost`` rejects negative deltas.

        Cost is monotonic by contract; a negative delta would re-open
        the same hole the tamper detector closes.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            loop._increment_expected_total_cost(3.0)
            assert loop._expected_total_cost == pytest.approx(3.0)

            with caplog.at_level("ERROR"):
                loop._increment_expected_total_cost(-1.0)
            assert loop._expected_total_cost == pytest.approx(3.0)
            joined = " ".join(r.getMessage() for r in caplog.records)
            assert "SECURITY" in joined or "monotonic" in joined.lower()

    @pytest.mark.asyncio
    async def test_execute_feature_increments_expected_total_cost(
        self, tmp_db, project, ready_features
    ):
        """End-to-end: ``execute_feature`` must keep expected total in lockstep.

        After a successful execution that records $0.75 of cost, both
        ``_project_total_cost`` and ``_expected_total_cost`` should be
        $0.75 — the in-memory floor must mirror the DB write.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id, max_cost=100.0)

            async def mock_spawn(*args, **kwargs):
                res = ExecutionResult(
                    text="ok",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=3,
                    total_cost_usd=0.75,
                )
                agent_run = MagicMock()
                agent_run.id = str(uuid.uuid4())
                return SpawnResult(execution_result=res, agent_run=agent_run)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                await loop.execute_feature(ready_features[0])

            assert loop._project_total_cost == pytest.approx(0.75)
            assert loop._expected_total_cost == pytest.approx(0.75)


# ============================================================
# Performance: budget_exceeded() must NOT re-fetch the project
# from the DB on every loop iteration.
# ============================================================


class TestBudgetExceededCachesProjectCost:
    """``budget_exceeded`` is checked once per loop iteration. Reading
    the project row out of SQLite each time is wasteful: with 200+
    features × N retries it adds 1000+ throwaway connections to the
    hot path. The fix caches ``total_cost_usd`` and refreshes only
    after a cost-mutating call.
    """

    def test_repeated_budget_check_uses_one_db_read(self, tmp_db, project):
        """100 budget_exceeded() calls must hit get_project at most once.

        The single allowed read is the cache priming inside
        ``__init__``; subsequent calls should be served entirely from
        the cached values.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.orchestrator import run_loop as run_loop_mod

            loop = OrchestrationLoop(project_id=project.id, max_cost=100.0)

            # Now wrap db.get_project to count post-init reads only.
            real_get_project = run_loop_mod.db.get_project
            calls = {"n": 0}

            def counting_get_project(pid):
                calls["n"] += 1
                return real_get_project(pid)

            with patch.object(
                run_loop_mod.db, "get_project", side_effect=counting_get_project
            ):
                for _ in range(100):
                    loop.budget_exceeded()

            # budget_exceeded should NOT fetch the project each time.
            assert calls["n"] == 0, (
                f"budget_exceeded triggered {calls['n']} get_project calls "
                f"over 100 iterations; expected 0 (cache hit only)"
            )

    @pytest.mark.asyncio
    async def test_cost_cache_refreshed_after_execute_feature(
        self, tmp_db, project, ready_features
    ):
        """After ``execute_feature`` returns, ``budget_exceeded`` must see
        the latest project total without forcing the caller to refresh
        manually. This is the production contract: the loop refreshes
        the cache itself right after ``handle_execution_result``.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id, max_cost=100.0)
            assert loop._project_total_cost == 0.0

            async def mock_spawn(*args, **kwargs):
                res = ExecutionResult(
                    text="ok",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=2.50,
                )
                agent_run = MagicMock()
                agent_run.id = str(uuid.uuid4())
                return SpawnResult(execution_result=res, agent_run=agent_run)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                await loop.execute_feature(ready_features[0])

            # The cache must reflect the project's new total.
            assert loop._project_total_cost == pytest.approx(2.50)


# ============================================================
# Reliability: sub-agent execution wall-clock timeout
# ============================================================


class TestSubAgentWallClockTimeout:
    """A stuck sub-agent (e.g. hung Puppeteer call) must NOT park the
    orchestrator forever. ``execute_feature`` wraps ``spawn_sub_agent``
    with ``asyncio.wait_for`` using ``BOB3_FEATURE_TIMEOUT_SECONDS``
    (default 3600s).
    """

    @pytest.mark.asyncio
    async def test_timeout_marks_feature_interrupted(
        self, tmp_db, project, ready_features, monkeypatch
    ):
        """On timeout the feature is marked 'interrupted', not 'failed'.

        This puts it on the F116 auto-resume path on the next ``bob3 run``
        rather than burning a refinement attempt on what is almost
        certainly an infrastructure-level hang.
        """
        # Ridiculously short timeout so the test never blocks.
        monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "0.05")

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def hanging_spawn(*args, **kwargs):
                # Sleep longer than the timeout to force wait_for() to fire.
                await asyncio.sleep(5)
                raise AssertionError("should never reach here")

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=hanging_spawn,
            ):
                spawn_result = await loop.execute_feature(ready_features[0])

            # Feature must be 'interrupted' (not 'failed' or 'completed').
            updated = get_feature(ready_features[0].id)
            assert updated.status == "interrupted", (
                f"timed-out feature ended in status={updated.status!r}; "
                f"expected 'interrupted' so F116 auto-resume picks it up"
            )

            # Synthetic SpawnResult must surface the timeout.
            assert spawn_result.execution_result.is_error is True
            assert "timed out" in spawn_result.execution_result.error_message.lower()

    @pytest.mark.asyncio
    async def test_timeout_does_not_cascade_dependents(
        self, tmp_db, project, monkeypatch
    ):
        """A timed-out feature must NOT cascade dependents to 'ready'.

        Otherwise a stuck implementation could unlock its downstream
        peers as if it had succeeded.
        """
        from bob3.db import add_feature_dependency, create_feature

        monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "0.05")

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            parent = create_feature(
                project_id=project.id,
                name="parent",
                description="parent feature that will time out",
                status="ready",
                priority=10,
                risk_category="medium",
            )
            update_feature(
                parent.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            child = create_feature(
                project_id=project.id,
                name="child",
                description="child depends on parent",
                status="pending",
                priority=20,
                risk_category="medium",
            )
            add_feature_dependency(
                feature_id=child.id, depends_on_feature_id=parent.id
            )

            parent = get_feature(parent.id)

            loop = OrchestrationLoop(project_id=project.id)

            async def hanging_spawn(*args, **kwargs):
                await asyncio.sleep(5)
                raise AssertionError("unreachable")

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=hanging_spawn,
            ):
                await loop.execute_feature(parent)

            # Parent timed out -> child must stay 'pending'.
            assert get_feature(parent.id).status == "interrupted"
            assert get_feature(child.id).status == "pending"


# ============================================================
# R5-007: SDK subprocess cleanup on timeout + SECURITY warning
# ============================================================


class TestSubAgentTimeoutCleanup:
    """R5-007: When ``asyncio.wait_for`` fires, the orchestrator must emit
    a SECURITY warning explaining that the underlying claude Node.js
    process may still be running, and ``spawn_sub_agent`` must attempt
    to close the SDK stream so the SDK's own cleanup runs.
    """

    @pytest.mark.asyncio
    async def test_timeout_emits_security_warning_with_pgrep_guidance(
        self, tmp_db, project, ready_features, monkeypatch, caplog
    ):
        """The TimeoutError handler must log a SECURITY warning that
        references ``pgrep -f claude`` so operators know how to inspect.
        """
        import logging

        monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "0.05")

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def hanging_spawn(*args, **kwargs):
                await asyncio.sleep(5)
                raise AssertionError("unreachable")

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=hanging_spawn,
            ):
                with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.run_loop"):
                    await loop.execute_feature(ready_features[0])

        security_records = [
            r for r in caplog.records
            if "SECURITY" in r.getMessage()
            and "pgrep -f claude" in r.getMessage()
        ]
        assert security_records, (
            "Expected a SECURITY warning mentioning `pgrep -f claude` after "
            "the sub-agent timed out so operators can clean up orphaned "
            f"processes; got log records: {[r.getMessage() for r in caplog.records]}"
        )

    @pytest.mark.asyncio
    async def test_spawn_sub_agent_closes_sdk_stream_on_cancellation(
        self, tmp_db, project
    ):
        """When the spawn_sub_agent coroutine is cancelled, the SDK
        async-generator stream must have ``aclose`` invoked so the SDK's
        own ``query.close()`` finally-block (which terminates the
        subprocess) runs.
        """
        from bob3.orchestrator import claude_executor

        aclose_called = False

        class FakeStream:
            def __init__(self):
                self._closed = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                # Simulate a hung SDK call by sleeping forever.
                await asyncio.sleep(60)
                raise StopAsyncIteration

            async def aclose(self):
                nonlocal aclose_called
                aclose_called = True
                self._closed = True

        def fake_stream_query(*args, **kwargs):
            return FakeStream()

        with patch("bob3.db.get_database_path", return_value=tmp_db), patch.object(
            claude_executor, "stream_query", side_effect=fake_stream_query
        ):
            task = asyncio.create_task(
                claude_executor.spawn_sub_agent(
                    project_id=project.id,
                    purpose="implement_feature",
                    prompt="hello",
                )
            )
            # Let the coroutine reach the await on FakeStream.
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert aclose_called, (
            "spawn_sub_agent must call aclose() on the SDK stream when "
            "cancelled, so the SDK can terminate the underlying claude "
            "Node.js subprocess (R5-007)."
        )


# ============================================================
# R5-008: bob3 run exit codes reflect LoopTermination reason
# ============================================================


class TestRunExitCodes:
    """R5-008: ``bob3 run`` must exit non-zero on non-success terminations.

    Without these codes, ``bob3 run --all && deploy.sh`` would deploy after
    a BUDGET_EXCEEDED / ALL_BLOCKED run, shipping a partial build. We map:

        ALL_COMPLETED       -> 0
        ALL_BLOCKED         -> 2
        BUDGET_EXCEEDED     -> 3
        SHUTDOWN_REQUESTED  -> 130   (conventional 128+SIGINT)
    """

    @pytest.mark.parametrize(
        "termination,expected_code",
        [
            (LoopTermination.ALL_COMPLETED, 0),
            (LoopTermination.ALL_BLOCKED, 2),
            (LoopTermination.BUDGET_EXCEEDED, 3),
            (LoopTermination.SHUTDOWN_REQUESTED, 130),
        ],
    )
    def test_run_all_exit_code_matches_termination(
        self, tmp_db, project, ready_features, termination, expected_code
    ):
        """``bob3 run --all`` exit code must match the termination reason."""
        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.cli._run_orchestration_loop",
                    return_value=termination,
                ):
                    result = runner.invoke(main, ["run", "--all"])
                    assert result.exit_code == expected_code, (
                        f"termination={termination!r} expected exit "
                        f"{expected_code}, got {result.exit_code}\n"
                        f"output: {result.output}"
                    )

    @pytest.mark.parametrize(
        "termination,expected_code",
        [
            (LoopTermination.ALL_COMPLETED, 0),
            (LoopTermination.ALL_BLOCKED, 2),
            (LoopTermination.BUDGET_EXCEEDED, 3),
            (LoopTermination.SHUTDOWN_REQUESTED, 130),
        ],
    )
    def test_run_feature_exit_code_matches_termination(
        self, tmp_db, project, ready_features, termination, expected_code
    ):
        """``bob3 run --feature`` exit code must match the termination reason."""
        feat = ready_features[0]
        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.cli._run_orchestration_loop",
                    return_value=termination,
                ):
                    result = runner.invoke(
                        main, ["run", "--feature", feat.id]
                    )
                    assert result.exit_code == expected_code, (
                        f"termination={termination!r} expected exit "
                        f"{expected_code}, got {result.exit_code}\n"
                        f"output: {result.output}"
                    )

    def test_run_help_documents_exit_codes(self):
        """The ``--help`` epilog must document the exit-code contract.

        Without this, the CLI behaviour is invisible to operators
        wiring CI pipelines.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0, result.output
        out = result.output
        assert "Exit codes" in out, "help must mention 'Exit codes'"
        # Spot-check that each code appears in the help text.
        for code in ("0", "2", "3", "130"):
            assert code in out, f"exit code {code} missing from help"


# ============================================================
# R5-009: per-feature and per-run summary log lines
# ============================================================


class TestPerFeatureSummaryLog:
    """R5-009: after each feature, log a structured summary line with
    duration, cost, attempts, and final status. After the loop terminates,
    log a single run-level summary line.
    """

    @pytest.mark.asyncio
    async def test_feature_summary_log_after_successful_completion(
        self, tmp_db, project, ready_features, caplog
    ):
        """A successful feature must produce a single "Feature ... done:"
        line containing duration / cost / attempts / status fields."""
        import logging as _logging

        feat = ready_features[0]

        async def mock_spawn(*args, **kwargs):
            return SpawnResult(
                execution_result=ExecutionResult(
                    text="ok",
                    is_error=False,
                    duration_ms=2500,
                    num_turns=3,
                    total_cost_usd=0.42,
                ),
                agent_run=MagicMock(id=str(uuid.uuid4())),
            )

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            loop.target_feature_id = feat.id  # exercise single-feature path

            caplog.set_level(_logging.INFO, logger="bob3.orchestrator.run_loop")
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                await loop.run()

            summary_lines = [
                rec.getMessage()
                for rec in caplog.records
                if "done:" in rec.getMessage()
            ]
            assert summary_lines, (
                "expected a 'Feature ... done:' summary line "
                f"from execute_feature; got {[r.getMessage() for r in caplog.records]}"
            )
            line = summary_lines[-1]
            # Required structured fields:
            for token in (
                f"Feature {feat.id[:8]}",
                "status=",
                "duration=",
                "cost=$",
                "attempts=",
            ):
                assert token in line, (
                    f"summary line missing '{token}': {line}"
                )

    @pytest.mark.asyncio
    async def test_run_summary_log_on_termination(
        self, tmp_db, project, ready_features, caplog
    ):
        """After the loop terminates, a single 'Run finished:' summary log
        line must appear with termination, counts, cost, and duration."""
        import logging as _logging

        async def mock_spawn(*args, **kwargs):
            return SpawnResult(
                execution_result=ExecutionResult(
                    text="ok",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=2,
                    total_cost_usd=0.10,
                ),
                agent_run=MagicMock(id=str(uuid.uuid4())),
            )

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            caplog.set_level(_logging.INFO, logger="bob3.orchestrator.run_loop")
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            run_summaries = [
                rec.getMessage()
                for rec in caplog.records
                if rec.getMessage().startswith("Run finished:")
            ]
            assert len(run_summaries) == 1, (
                f"expected exactly one 'Run finished:' line, "
                f"got {len(run_summaries)}: {run_summaries}"
            )
            line = run_summaries[0]
            for token in (
                f"termination={termination.name}",
                "features_completed=",
                "features_failed=",
                "total_cost=$",
                "total_duration=",
            ):
                assert token in line, (
                    f"run summary missing '{token}': {line}"
                )


# ============================================================
# R5-010 / R7-004: interruption checkpoint records the project total cost
# ============================================================


class TestInterruptionCheckpointRecordsProjectCost:
    """R5-010 / R7-004: ``_create_interruption_checkpoint`` must record the
    actual project cost (the canonical DB total). The ``self.total_cost``
    in-memory accumulator was deleted entirely by the structural
    ``non-atomic-counter`` fix; cost is now written exclusively through
    ``OrchestrationLoop._increment_cost``.

    Before the fix, ``state_snapshot["total_cost_at_interrupt"]`` and
    ``cost_at_checkpoint`` were always 0.0 — useless for resume forensics
    because the project had spent N>0 dollars before the shutdown.
    """

    @pytest.mark.asyncio
    async def test_checkpoint_records_actual_project_cost(
        self, tmp_db, project, ready_features
    ):
        """After execute_feature interrupts during shutdown, the
        checkpoint's cost fields must reflect the project's DB total
        cost, not 0.0.
        """
        import json as _json

        from bob3.db import list_checkpoints, update_project

        feat = ready_features[0]

        # Pre-populate the project cost so we can assert that the
        # checkpoint sees the canonical DB total. The dead
        # ``self.total_cost`` in-memory mirror was removed by the
        # ``non-atomic-counter`` structural fix; the only writer is
        # now ``OrchestrationLoop._increment_cost``.
        update_project(project.id, total_cost_usd=2.50)

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            loop.target_feature_id = feat.id

            async def mock_spawn(*args, **kwargs):
                # Trip shutdown so handle_execution_result writes 'interrupted'
                # and execute_feature creates an interruption checkpoint.
                loop.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="partial",
                        is_error=True,
                        error_message="Interrupted",
                        duration_ms=5000,
                        num_turns=1,
                        total_cost_usd=0.30,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                await loop.run()

            checkpoints = list_checkpoints(feature_id=feat.id)
            interruption_cps = [
                cp for cp in checkpoints
                if cp.checkpoint_type == "interruption"
            ]
            assert interruption_cps, (
                "expected an interruption checkpoint after shutdown"
            )
            cp = interruption_cps[-1]
            # cost_at_checkpoint must reflect the actual project cost,
            # not the always-zero in-memory accumulator. We pre-loaded
            # 2.50 and the spawn added 0.30, so it must be > 2.0.
            assert cp.cost_at_checkpoint is not None
            assert cp.cost_at_checkpoint > 2.0, (
                f"cost_at_checkpoint must reflect project cost, "
                f"got {cp.cost_at_checkpoint}"
            )
            state = _json.loads(cp.state_snapshot)
            # The state-snapshot field must mirror the project total
            # (not 0.0). Allow a wide upper bound to cover any path
            # variations in cost normalisation.
            assert state["total_cost_at_interrupt"] >= 2.50, (
                f"total_cost_at_interrupt must mirror project total, "
                f"got {state['total_cost_at_interrupt']}"
            )


# ============================================================
# R7-003: below-threshold ready features must not burn refinement slots
# ============================================================


class TestBelowThresholdReadyFeature:
    """R7-003: when find_next_ready_feature() returns None but the loop
    falls back to the first 'ready' feature that is below threshold,
    repeat iterations would burn refinement slots once research had
    already run. The loop must instead mark the feature 'needs_human'
    and stop touching it.
    """

    @pytest.mark.asyncio
    async def test_below_threshold_with_research_marks_needs_human(
        self, tmp_db, project
    ):
        """A feature with research_iterations >= 1 and readiness below
        threshold must be marked 'needs_human' and NOT executed via
        spawn_sub_agent.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = create_feature(
                project_id=project.id,
                name="Stuck below threshold",
                description="research already ran but still below threshold",
                status="ready",
                priority=10,
                risk_category="medium",  # threshold = 0.80
            )
            # Below the medium threshold of 0.80, with research already done.
            update_feature(
                f.id,
                conf_spec_understanding=0.5,
                conf_impl_correctness=0.5,
                conf_test_adequacy=0.5,
                readiness_score=0.5,
                research_iterations=1,
            )

            loop = OrchestrationLoop(project_id=project.id, max_cost=10.0)

            async def boom_spawn(*args, **kwargs):
                raise AssertionError(
                    "spawn_sub_agent must not run for a below-threshold "
                    "feature whose research already completed (R7-003)"
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=boom_spawn,
            ), patch(
                "bob3.orchestrator.run_loop.acquire_run_lock",
                return_value=None,
            ), patch(
                "bob3.orchestrator.run_loop.release_run_lock",
                return_value=None,
            ):
                termination = await loop.run()

            # The loop should have terminated cleanly (ALL_BLOCKED or
            # ALL_COMPLETED). What matters is the feature got marked
            # needs_human, NOT executing or failed.
            assert termination in (
                LoopTermination.ALL_BLOCKED,
                LoopTermination.ALL_COMPLETED,
            ), f"unexpected termination={termination}"

            updated = get_feature(f.id)
            assert updated.status == "needs_human", (
                "below-threshold feature with research_iterations>0 must be "
                "marked needs_human (R7-003); got "
                f"status={updated.status!r}"
            )


# ============================================================
# R10-006: Stale .bob3.lock recovery
# ============================================================


class TestR10006StaleLockRecovery:
    """R10-006: a SIGKILL/OOM-killed previous run can leave a stale
    .bob3.lock that the kernel didn't release because a still-running
    grandchild inherited the FD. We detect that case via PID probe and
    either give an actionable error or, with --force-unlock, recover.
    """

    def test_pid_written_to_lock_file_on_acquire(self, tmp_path):
        """After a successful acquire, the lock file contains our PID."""
        from bob3.orchestrator.run_loop import (
            _read_lock_pid,
            acquire_run_lock,
            release_run_lock,
        )

        h = acquire_run_lock(tmp_path)
        try:
            pid = _read_lock_pid(tmp_path / ".bob3.lock")
            assert pid == os.getpid()
        finally:
            release_run_lock(h)

    def test_stale_lock_with_dead_pid_gives_actionable_error(self, tmp_path):
        """If the lock file claims a dead PID and the flock blocks, the
        error must name the PID and tell the user how to recover.
        """
        from bob3.orchestrator.run_loop import (
            AlreadyRunningError,
            acquire_run_lock,
            release_run_lock,
        )

        external_holder = acquire_run_lock(tmp_path)
        try:
            # Overwrite PID in the file with a definitely-dead PID.
            dead_pid = 2**31 - 2  # near INT_MAX, almost certainly dead
            (tmp_path / ".bob3.lock").write_text(f"{dead_pid}\n")

            with pytest.raises(AlreadyRunningError) as exc_info:
                acquire_run_lock(tmp_path, force_unlock=False)
            msg = str(exc_info.value)
            assert (
                "stale" in msg.lower()
                or "not running" in msg.lower()
                or str(dead_pid) in msg
            ), f"Error must mention stale lock; got: {msg}"
            assert "force-unlock" in msg or "rm " in msg, (
                f"Error must point to recovery (--force-unlock or rm); "
                f"got: {msg}"
            )
        finally:
            release_run_lock(external_holder)

    def test_concurrent_run_error_points_to_recovery(self, tmp_path):
        """Even when the holder is alive, the error must include the
        ``rm <path>`` hint as a manual escape valve.
        """
        from bob3.orchestrator.run_loop import (
            AlreadyRunningError,
            acquire_run_lock,
            release_run_lock,
        )

        first = acquire_run_lock(tmp_path)
        try:
            with pytest.raises(AlreadyRunningError) as exc_info:
                acquire_run_lock(tmp_path)
            msg = str(exc_info.value)
            assert "rm " in msg, (
                f"Error must show manual rm path so an operator can recover "
                f"if they're sure no other run is active; got: {msg}"
            )
            assert ".bob3.lock" in msg
        finally:
            release_run_lock(first)


# ============================================================
# R10-007: _run_single_feature returns ALL_BLOCKED on failure
# ============================================================


class TestR10007SingleFeatureTerminationReflectsStatus:
    """R10-007: ``_run_single_feature`` previously returned
    ALL_COMPLETED unconditionally — even when the sub-agent failed
    verification, hit a hook rejection, or otherwise ended
    ``needs_human``.
    """

    @pytest.mark.asyncio
    async def test_failed_feature_returns_all_blocked(
        self, tmp_db, project, ready_features
    ):
        """A sub-agent that errors out (is_error=True) must yield
        ALL_BLOCKED, not ALL_COMPLETED.
        """
        feat = ready_features[0]

        async def failing_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="error",
                is_error=True,
                duration_ms=1000,
                num_turns=2,
                total_cost_usd=0.01,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test-r10007",
                target_feature_id=feat.id,
            )
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=failing_spawn,
            ), patch(
                "bob3.orchestrator.run_loop.acquire_run_lock", return_value=None
            ), patch(
                "bob3.orchestrator.run_loop.release_run_lock", return_value=None
            ):
                termination = await loop.run()

            updated = get_feature(feat.id)
            assert updated.status != "completed", (
                f"Test setup invariant: failing sub-agent must not yield "
                f"status='completed'; got {updated.status}"
            )
            assert termination == LoopTermination.ALL_BLOCKED, (
                f"R10-007: a failed feature in single-feature mode must "
                f"return ALL_BLOCKED, not {termination}"
            )

    @pytest.mark.asyncio
    async def test_completed_feature_returns_all_completed(
        self, tmp_db, project, ready_features
    ):
        """Sanity check: a successful single-feature run still maps to
        ALL_COMPLETED (we did not regress the happy path).
        """
        feat = ready_features[0]

        async def ok_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="ok",
                is_error=False,
                duration_ms=1000,
                num_turns=5,
                total_cost_usd=0.01,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test-r10007-ok",
                target_feature_id=feat.id,
            )
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=ok_spawn,
            ), patch(
                "bob3.orchestrator.run_loop.acquire_run_lock", return_value=None
            ), patch(
                "bob3.orchestrator.run_loop.release_run_lock", return_value=None
            ):
                termination = await loop.run()

            updated = get_feature(feat.id)
            assert updated.status == "completed"
            assert termination == LoopTermination.ALL_COMPLETED


# ============================================================
# R10-008: bob3 run --feature exits non-zero when feature failed
# ============================================================


class TestR10008CliExitCodeOnFailure:
    """R10-008: with R10-007 fixed at the loop level, the CLI must
    correctly map ALL_BLOCKED to a non-zero exit and print a status
    that reflects what actually happened (not "Feature completed!").
    """

    def test_cli_exits_nonzero_when_feature_failed(
        self, tmp_db, project, ready_features
    ):
        """End-to-end: `bob3 run --feature <id>` with a failing
        sub-agent must yield exit_code != 0.
        """
        feat = ready_features[0]

        async def failing_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="error",
                is_error=True,
                duration_ms=1000,
                num_turns=2,
                total_cost_usd=0.01,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.orchestrator.run_loop.spawn_sub_agent",
                    new_callable=AsyncMock,
                    side_effect=failing_spawn,
                ):
                    result = runner.invoke(main, ["run", "--feature", feat.id])

        assert result.exit_code != 0, (
            f"R10-008: failed feature must yield non-zero exit; "
            f"got exit_code={result.exit_code}, output={result.output!r}"
        )
        # Message should NOT claim success.
        assert "Feature completed!" not in result.output, (
            "R10-008: must not say 'Feature completed!' when feature "
            f"failed; got: {result.output!r}"
        )
