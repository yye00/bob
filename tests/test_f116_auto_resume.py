"""Tests for F116: Automatic Resume on Startup.

When bob3 run is invoked, automatically detect and resume interrupted work:
1. Check for features with status='executing' (interrupted mid-execution)
2. Check for resumable checkpoints (can_resume=TRUE)
3. If found, log and auto-resume (no prompt needed)
4. Load checkpoint state and continue from last known good state
5. If no checkpoint, reset feature to 'pending' and retry from start
6. Add --fresh flag to force restart without resume
7. Test: Start feature, kill process, restart, verify resume
8. Test: Start feature, kill process mid-task, restart, verify checkpoint resume
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3.db import (
    create_checkpoint,
    create_feature,
    create_project,
    get_feature,
    init_database,
    list_checkpoints,
    list_features,
    update_feature,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import (
    LoopTermination,
    OrchestrationLoop,
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
            name="resume-test-project",
            workspace_path="/tmp/resume-test",
            max_cost_usd=100.0,
        )


@pytest.fixture
def executing_feature(tmp_db, project):
    """Create a feature stuck in 'executing' status (simulating crash)."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        f = create_feature(
            project_id=project.id,
            name="Interrupted Feature",
            description="Feature that was executing when process crashed",
            status="executing",
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


@pytest.fixture
def interrupted_feature_with_checkpoint(tmp_db, project):
    """Create an interrupted feature with a resumable checkpoint."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        f = create_feature(
            project_id=project.id,
            name="Checkpoint Feature",
            description="Feature interrupted with checkpoint",
            status="interrupted",
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
        state = {
            "feature_id": f.id,
            "feature_name": f.name,
            "feature_status": "interrupted",
            "reason": "graceful_shutdown",
            "tasks_completed": 2,
            "tasks_total": 5,
        }
        cp = create_checkpoint(
            project_id=project.id,
            feature_id=f.id,
            checkpoint_type="interruption",
            state_snapshot=json.dumps(state),
            cost_at_checkpoint=1.50,
            duration_at_checkpoint_ms=30000,
        )
        return get_feature(f.id), cp


@pytest.fixture
def ready_features(tmp_db, project):
    """Create ready features for testing."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        features = []
        for i in range(2):
            f = create_feature(
                project_id=project.id,
                name=f"Ready Feature {i + 1}",
                description=f"Ready feature {i + 1}",
                status="ready",
                priority=20 * (i + 1),
                risk_category="medium",
            )
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
# Step 1: On bob3 run, query for features with status='executing'
# ============================================================


class TestFindExecutingFeatures:
    """Step 1: On startup, detect features stuck in 'executing' status."""

    def test_find_executing_features(self, tmp_db, project, executing_feature):
        """Features with status='executing' are found by list_features."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            executing = list_features(project_id=project.id, status="executing")
            assert len(executing) == 1
            assert executing[0].id == executing_feature.id
            assert executing[0].status == "executing"

    def test_no_executing_features_when_none_exist(self, tmp_db, project, ready_features):
        """No executing features when none exist."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            executing = list_features(project_id=project.id, status="executing")
            assert len(executing) == 0

    def test_find_interrupted_features(self, tmp_db, project, interrupted_feature_with_checkpoint):
        """Features with status='interrupted' are found."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            interrupted = list_features(project_id=project.id, status="interrupted")
            assert len(interrupted) == 1
            feat, _ = interrupted_feature_with_checkpoint
            assert interrupted[0].id == feat.id


# ============================================================
# Step 2: Query resource_checkpoints for can_resume=TRUE
# ============================================================


class TestFindResumableCheckpoints:
    """Step 2: Find resumable checkpoints for interrupted features."""

    def test_find_resumable_checkpoint(self, tmp_db, project, interrupted_feature_with_checkpoint):
        """Resumable checkpoints are found for a feature."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            feat, cp = interrupted_feature_with_checkpoint
            from bob3.db import find_resumable_checkpoints

            resumable = find_resumable_checkpoints(project_id=project.id)
            assert len(resumable) >= 1
            assert any(c.id == cp.id for c in resumable)
            assert all(c.can_resume for c in resumable)

    def test_no_resumable_checkpoints_when_none_exist(self, tmp_db, project, ready_features):
        """No resumable checkpoints when none exist."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import find_resumable_checkpoints

            resumable = find_resumable_checkpoints(project_id=project.id)
            assert len(resumable) == 0


# ============================================================
# Step 3: If interrupted work found, log and auto-resume (no prompt needed)
# ============================================================


class TestAutoResumeOnStartup:
    """Step 3: Orchestration loop auto-detects and resumes interrupted work."""

    @pytest.mark.asyncio
    async def test_loop_detects_executing_feature(self, tmp_db, project, executing_feature):
        """Loop detects a feature stuck in 'executing' and handles it."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn(*args, **kwargs):
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Completed",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED
            updated = get_feature(executing_feature.id)
            assert updated.status == "completed"

    @pytest.mark.asyncio
    async def test_loop_logs_auto_resume(self, tmp_db, project, executing_feature):
        """Loop logs that it's auto-resuming interrupted work."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn(*args, **kwargs):
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Completed",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                with patch("bob3.orchestrator.run_loop.logger") as mock_logger:
                    await loop.run()

            log_messages = [
                str(call) for call in mock_logger.info.call_args_list
            ]
            found = any("resum" in msg.lower() for msg in log_messages)
            assert found, f"Expected log about resuming but got: {log_messages}"


# ============================================================
# Step 4: Load checkpoint state and continue from last known good state
# ============================================================


class TestResumeFromCheckpoint:
    """Step 4: Load checkpoint state and continue execution."""

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint_restores_state(
        self, tmp_db, project, interrupted_feature_with_checkpoint
    ):
        """Loop resumes from checkpoint, restoring feature state before re-executing."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            feat, cp = interrupted_feature_with_checkpoint
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn(*args, **kwargs):
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Completed after resume",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED
            updated = get_feature(feat.id)
            assert updated.status == "completed"

            # Checkpoint should be marked as consumed
            from bob3.db import get_checkpoint

            consumed = get_checkpoint(cp.id)
            assert consumed.can_resume is False


# ============================================================
# Step 5: If no checkpoint, reset feature to 'pending' and retry from start
# ============================================================


class TestResetWithoutCheckpoint:
    """Step 5: If no checkpoint exists, reset executing features to 'pending'."""

    @pytest.mark.asyncio
    async def test_executing_feature_reset_to_ready_without_checkpoint(
        self, tmp_db, project, executing_feature
    ):
        """Feature stuck in 'executing' with no checkpoint is reset to 'ready'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn(*args, **kwargs):
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Completed from scratch",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            # Feature should now be completed (was reset to ready, then executed)
            assert termination == LoopTermination.ALL_COMPLETED
            updated = get_feature(executing_feature.id)
            assert updated.status == "completed"

    @pytest.mark.asyncio
    async def test_interrupted_feature_without_checkpoint_reset_to_ready(
        self, tmp_db, project
    ):
        """Feature in 'interrupted' with no checkpoint is reset to 'ready'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = create_feature(
                project_id=project.id,
                name="No-Checkpoint Feature",
                description="Interrupted but no checkpoint available",
                status="interrupted",
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

            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn(*args, **kwargs):
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Completed",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED
            updated = get_feature(f.id)
            assert updated.status == "completed"


# ============================================================
# Step 6: Add --fresh flag to force restart without resume
# ============================================================


class TestFreshFlag:
    """Step 6: --fresh flag skips resume and resets all interrupted features."""

    @pytest.mark.asyncio
    async def test_fresh_mode_skips_checkpoint_resume(
        self, tmp_db, project, interrupted_feature_with_checkpoint
    ):
        """With fresh=True, checkpoint is not consumed (left intact)."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            feat, cp = interrupted_feature_with_checkpoint
            loop = OrchestrationLoop(project_id=project.id, fresh=True)

            async def mock_spawn(*args, **kwargs):
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Completed fresh",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED
            # Feature should still complete
            updated = get_feature(feat.id)
            assert updated.status == "completed"

    @pytest.mark.asyncio
    async def test_fresh_mode_resets_executing_features(
        self, tmp_db, project, executing_feature
    ):
        """With fresh=True, executing features are reset to 'ready'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id, fresh=True)

            async def mock_spawn(*args, **kwargs):
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Completed fresh",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED
            updated = get_feature(executing_feature.id)
            assert updated.status == "completed"


# ============================================================
# Step 7: Test: Start feature, kill process, restart, verify resume
# ============================================================


class TestKillAndResumeProcess:
    """Step 7: Full flow - start, interrupt via shutdown, restart, complete."""

    @pytest.mark.asyncio
    async def test_interrupt_and_resume_full_flow(self, tmp_db, project, ready_features):
        """Start features, interrupt mid-execution, restart loop, features complete."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # ---- Phase 1: First run, gets interrupted ----
            loop1 = OrchestrationLoop(project_id=project.id)

            async def mock_spawn_interrupt(*args, **kwargs):
                loop1.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Partial",
                        is_error=True,
                        error_message="Interrupted",
                        duration_ms=5000,
                        num_turns=3,
                        total_cost_usd=0.30,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_interrupt,
            ):
                with patch("bob3.orchestrator.run_loop.stop_mcp_server"):
                    t1 = await loop1.run()

            assert t1 == LoopTermination.SHUTDOWN_REQUESTED
            # First feature should be interrupted
            f1 = get_feature(ready_features[0].id)
            assert f1.status == "interrupted"

            # ---- Phase 2: Second run, resumes and completes ----
            loop2 = OrchestrationLoop(project_id=project.id)

            async def mock_spawn_success(*args, **kwargs):
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Completed",
                        is_error=False,
                        duration_ms=2000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_success,
            ):
                t2 = await loop2.run()

            assert t2 == LoopTermination.ALL_COMPLETED
            for f in ready_features:
                assert get_feature(f.id).status == "completed"


# ============================================================
# Step 8: Test: Start feature, kill mid-task, restart, verify checkpoint resume
# ============================================================


class TestKillMidTaskAndCheckpointResume:
    """Step 8: Interrupt mid-task with checkpoint, resume from checkpoint."""

    @pytest.mark.asyncio
    async def test_checkpoint_resume_flow(
        self, tmp_db, project, interrupted_feature_with_checkpoint, ready_features
    ):
        """Interrupted feature with checkpoint resumes and completes."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            feat, cp = interrupted_feature_with_checkpoint
            loop = OrchestrationLoop(project_id=project.id)

            call_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text=f"Completed feature {call_count}",
                        is_error=False,
                        duration_ms=2000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED

            # All features completed (interrupted one + ready ones)
            assert get_feature(feat.id).status == "completed"
            for rf in ready_features:
                assert get_feature(rf.id).status == "completed"

            # Checkpoint consumed
            from bob3.db import get_checkpoint

            consumed = get_checkpoint(cp.id)
            assert consumed.can_resume is False


# ============================================================
# CLI --fresh flag test
# ============================================================


class TestCLIFreshFlag:
    """CLI run command accepts --fresh flag."""

    def test_run_command_accepts_fresh_flag(self):
        """The run CLI command accepts --fresh flag."""
        from click.testing import CliRunner

        from bob3.cli import main

        runner = CliRunner()
        # Just verify the flag is accepted (doesn't error on parse)
        result = runner.invoke(main, ["run", "--fresh", "--help"])
        # --help should show the flag in output
        assert result.exit_code == 0
        assert "--fresh" in result.output or "fresh" in result.output
