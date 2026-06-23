"""Tests for F071: Orchestration loop retry logic for failed features.

Validates that:
- Step 1: On failure, refinement_attempts is checked
- Step 2: If under limit, a refiner sub-agent is spawned and feature retried
- Step 3: refinement_attempts counter is incremented on each failure
- Step 4: If over limit, status is set to needs_human
- Step 5: Fail feature 5 times, verify 6th triggers needs_human
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3.db import (
    create_feature,
    create_project,
    get_feature,
    init_database,
    update_feature,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import (
    LoopTermination,
    OrchestrationLoop,
    handle_execution_result,
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
def feature(tmp_db, project):
    """Create a single ready feature with max_refinement_attempts=5."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        f = create_feature(
            project_id=project.id,
            name="Retryable Feature",
            description="A feature that may fail and need retries",
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


def _make_spawn_result(*, is_error: bool, error_message: str = "") -> SpawnResult:
    """Helper to create a SpawnResult for testing."""
    result = ExecutionResult(
        text="error output" if is_error else "success output",
        is_error=is_error,
        error_message=error_message,
        duration_ms=2000,
        num_turns=5,
        total_cost_usd=0.50,
    )
    agent_run = MagicMock()
    agent_run.id = str(uuid.uuid4())
    return SpawnResult(execution_result=result, agent_run=agent_run)


# ============================================================
# Step 1: Check refinement_attempts on failure
# ============================================================


class TestCheckRefinementOnFailure:
    """Test that on failure, refinement_attempts is checked."""

    @pytest.mark.asyncio
    async def test_failure_increments_refinement_attempts(
        self, tmp_db, project, feature
    ):
        """Step 1: When a feature fails, refinement_attempts is incremented."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            fail_result = _make_spawn_result(
                is_error=True, error_message="Build failed"
            )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ):
                await loop.execute_feature(feature)

            updated = get_feature(feature.id)
            assert updated is not None
            assert updated.refinement_attempts == 1

    @pytest.mark.asyncio
    async def test_success_does_not_increment_refinement(
        self, tmp_db, project, feature
    ):
        """Step 1: When a feature succeeds, refinement_attempts is NOT changed."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            success_result = _make_spawn_result(is_error=False)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=success_result,
            ):
                await loop.execute_feature(feature)

            updated = get_feature(feature.id)
            assert updated is not None
            assert updated.refinement_attempts == 0


# ============================================================
# Step 2: If under limit, spawn refiner sub-agent
# ============================================================


class TestSpawnRefinerUnderLimit:
    """Test that a failed feature under the limit gets retried."""

    @pytest.mark.asyncio
    async def test_failure_under_limit_resets_to_ready(
        self, tmp_db, project, feature
    ):
        """Step 2: Feature that fails with attempts under limit is reset to 'ready'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            fail_result = _make_spawn_result(
                is_error=True, error_message="Test failure"
            )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ):
                await loop.execute_feature(feature)

            updated = get_feature(feature.id)
            assert updated is not None
            # Under limit: should be reset to 'ready' for retry
            assert updated.status == "ready"
            assert updated.refinement_attempts == 1

    @pytest.mark.asyncio
    async def test_failure_under_limit_does_not_count_as_failed(
        self, tmp_db, project, feature
    ):
        """Step 2: A retried feature should not increment features_failed."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            fail_result = _make_spawn_result(
                is_error=True, error_message="Test failure"
            )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ):
                await loop.execute_feature(feature)

            # Should not count as permanently failed since it's being retried
            assert loop.features_failed == 0


# ============================================================
# Step 3: Update refinement_attempts counter
# ============================================================


class TestRefinementCounterUpdates:
    """Test that the counter increments on each retry."""

    @pytest.mark.asyncio
    async def test_counter_increments_on_each_failure(
        self, tmp_db, project, feature
    ):
        """Step 3: Each failure increments the counter by 1."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            for expected_count in range(1, 4):
                # Re-fetch feature to get latest state
                current_feature = get_feature(feature.id)
                fail_result = _make_spawn_result(
                    is_error=True, error_message=f"Failure #{expected_count}"
                )

                with patch(
                    "bob3.orchestrator.run_loop.spawn_sub_agent",
                    new_callable=AsyncMock,
                    return_value=fail_result,
                ):
                    await loop.execute_feature(current_feature)

                updated = get_feature(feature.id)
                assert updated is not None
                assert updated.refinement_attempts == expected_count

    @pytest.mark.asyncio
    async def test_counter_persists_across_executions(
        self, tmp_db, project, feature
    ):
        """Step 3: Counter persists in the database across executions."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            # Fail twice
            for _ in range(2):
                current_feature = get_feature(feature.id)
                fail_result = _make_spawn_result(
                    is_error=True, error_message="failure"
                )
                with patch(
                    "bob3.orchestrator.run_loop.spawn_sub_agent",
                    new_callable=AsyncMock,
                    return_value=fail_result,
                ):
                    await loop.execute_feature(current_feature)

            # Create a new loop instance (simulating restart)
            loop2 = OrchestrationLoop(project_id=project.id)

            # Fail once more
            current_feature = get_feature(feature.id)
            fail_result = _make_spawn_result(
                is_error=True, error_message="failure again"
            )
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ):
                await loop2.execute_feature(current_feature)

            updated = get_feature(feature.id)
            assert updated is not None
            assert updated.refinement_attempts == 3


# ============================================================
# Step 4: If over limit, set status to needs_human
# ============================================================


class TestNeedsHumanOnExceededLimit:
    """Test that exceeding the limit sets needs_human."""

    @pytest.mark.asyncio
    async def test_at_limit_sets_needs_human(self, tmp_db, project, feature):
        """Step 4: When refinement_attempts reaches max, status becomes needs_human."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            # Fail max_refinement_attempts (5) times
            for i in range(5):
                current_feature = get_feature(feature.id)
                fail_result = _make_spawn_result(
                    is_error=True, error_message=f"Failure #{i + 1}"
                )
                with patch(
                    "bob3.orchestrator.run_loop.spawn_sub_agent",
                    new_callable=AsyncMock,
                    return_value=fail_result,
                ):
                    await loop.execute_feature(current_feature)

            updated = get_feature(feature.id)
            assert updated is not None
            assert updated.status == "needs_human"
            assert updated.refinement_attempts == 5

    @pytest.mark.asyncio
    async def test_needs_human_feature_counts_as_failed(
        self, tmp_db, project, feature
    ):
        """Step 4: A feature that reaches needs_human IS counted as failed."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            # Fail 5 times to reach the limit
            for i in range(5):
                current_feature = get_feature(feature.id)
                fail_result = _make_spawn_result(
                    is_error=True, error_message=f"Failure #{i + 1}"
                )
                with patch(
                    "bob3.orchestrator.run_loop.spawn_sub_agent",
                    new_callable=AsyncMock,
                    return_value=fail_result,
                ):
                    await loop.execute_feature(current_feature)

            # The final failure (5th) should have incremented features_failed
            assert loop.features_failed == 1


# ============================================================
# Step 5: Fail 5 times, verify 6th triggers needs_human
# ============================================================


class TestFullRetryCycle:
    """End-to-end test: fail 5 times, verify the transition to needs_human."""

    @pytest.mark.asyncio
    async def test_fail_5_times_6th_triggers_needs_human(
        self, tmp_db, project, feature
    ):
        """Step 5: Fail feature 5 times, verify 6th (attempt to check) triggers needs_human.

        With max_refinement_attempts=5:
        - Failures 1-4: feature is reset to 'ready' for retry
        - Failure 5: refinement_attempts reaches limit, status set to 'needs_human'
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            for i in range(5):
                current_feature = get_feature(feature.id)
                fail_result = _make_spawn_result(
                    is_error=True, error_message=f"Failure #{i + 1}"
                )
                with patch(
                    "bob3.orchestrator.run_loop.spawn_sub_agent",
                    new_callable=AsyncMock,
                    return_value=fail_result,
                ):
                    await loop.execute_feature(current_feature)

                updated = get_feature(feature.id)
                if i < 4:
                    # Failures 1-4: should be reset to ready
                    assert updated.status == "ready", (
                        f"After failure {i + 1}, expected 'ready' but got '{updated.status}'"
                    )
                else:
                    # Failure 5: should be needs_human
                    assert updated.status == "needs_human", (
                        f"After failure {i + 1}, expected 'needs_human' but got '{updated.status}'"
                    )

            final = get_feature(feature.id)
            assert final.refinement_attempts == 5
            assert final.status == "needs_human"

    @pytest.mark.asyncio
    async def test_retry_loop_terminates_when_all_needs_human(
        self, tmp_db, project, feature
    ):
        """Step 5: Loop terminates with ALL_BLOCKED when feature reaches needs_human."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            call_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return _make_spawn_result(
                    is_error=True, error_message=f"Failure #{call_count}"
                )

            loop = OrchestrationLoop(project_id=project.id)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            # Should have been called 5 times (retried 4 times, then needs_human)
            assert call_count == 5

            # Loop should terminate because the only feature is now blocked
            assert termination == LoopTermination.ALL_BLOCKED

            # Feature should be needs_human
            final = get_feature(feature.id)
            assert final.status == "needs_human"
            assert final.refinement_attempts == 5

    @pytest.mark.asyncio
    async def test_custom_max_attempts_respected(self, tmp_db, project):
        """Step 5: Custom max_refinement_attempts is respected."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = create_feature(
                project_id=project.id,
                name="Custom Limit Feature",
                description="Feature with custom max attempts",
                status="ready",
                priority=10,
                risk_category="medium",
            )
            update_feature(
                f.id,
                max_refinement_attempts=2,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            feature = get_feature(f.id)

            loop = OrchestrationLoop(project_id=project.id)

            for i in range(2):
                current = get_feature(feature.id)
                fail_result = _make_spawn_result(
                    is_error=True, error_message=f"Failure #{i + 1}"
                )
                with patch(
                    "bob3.orchestrator.run_loop.spawn_sub_agent",
                    new_callable=AsyncMock,
                    return_value=fail_result,
                ):
                    await loop.execute_feature(current)

            final = get_feature(feature.id)
            assert final.status == "needs_human"
            assert final.refinement_attempts == 2

    @pytest.mark.asyncio
    async def test_interrupted_feature_not_retried(self, tmp_db, project, feature):
        """Interrupted features (shutdown) should NOT be retried or increment counter."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            loop.shutdown_requested = True

            fail_result = _make_spawn_result(
                is_error=True, error_message="Shutdown"
            )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ):
                await loop.execute_feature(feature)

            updated = get_feature(feature.id)
            assert updated is not None
            # Interrupted: should NOT have been retried
            assert updated.status == "interrupted"
            assert updated.refinement_attempts == 0
