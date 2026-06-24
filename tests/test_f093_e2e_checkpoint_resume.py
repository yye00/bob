"""Tests for F093: End-to-end test - Checkpoint and resume.

End-to-end integration test that exercises the full checkpoint/resume flow:
Step 1: Start feature execution
Step 2: Create checkpoint mid-execution
Step 3: Simulate crash/interruption
Step 4: Resume from checkpoint
Step 5: Verify feature completes from checkpoint state
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob.db import (
    create_checkpoint,
    create_feature,
    create_project,
    create_task,
    find_resumable_checkpoints,
    get_checkpoint,
    get_feature,
    get_task,
    init_database,
    list_checkpoints,
    query_evidence,
    resume_from_checkpoint,
    update_feature,
    update_task,
)
from bob.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob.orchestrator.run_loop import (
    LoopTermination,
    OrchestrationLoop,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "test.db"
    init_database(db_path=db_path)
    with patch("bob.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def project(tmp_db):
    """Create a test project."""
    with patch("bob.db.get_database_path", return_value=tmp_db):
        return create_project(
            name="checkpoint-e2e-project",
            workspace_path="/tmp/checkpoint-e2e",
            max_cost_usd=100.0,
        )


@pytest.fixture
def ready_feature(tmp_db, project):
    """Create a feature in 'ready' state with high readiness."""
    with patch("bob.db.get_database_path", return_value=tmp_db):
        f = create_feature(
            project_id=project.id,
            name="Checkpoint E2E Feature",
            description="Feature for checkpoint/resume end-to-end testing",
            status="ready",
            priority=10,
            risk_category="low",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
            tasks_completed=2,
            tasks_total=5,
        )
        return get_feature(f.id)


class TestE2EStartExecution:
    """Step 1: Start feature execution."""

    @pytest.mark.asyncio
    async def test_feature_transitions_to_executing(self, tmp_db, project, ready_feature):
        """When the orchestration loop picks up a feature, it transitions to 'executing'."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/checkpoint-e2e",
            )

            execution_started = False

            async def mock_spawn(*args, **kwargs):
                nonlocal execution_started
                # At this point, the feature should be 'executing'
                mid_exec = get_feature(ready_feature.id)
                assert mid_exec.status == "executing"
                execution_started = True

                mock_result = ExecutionResult(
                    text="Feature implemented successfully",
                    is_error=False,
                    duration_ms=5000,
                    num_turns=10,
                    total_cost_usd=1.50,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                await loop.run()

            assert execution_started


class TestE2ECheckpointCreationDuringExecution:
    """Step 2: Create checkpoint mid-execution."""

    @pytest.mark.asyncio
    async def test_checkpoint_created_during_execution(self, tmp_db, project, ready_feature):
        """A checkpoint is created mid-execution, capturing feature state."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/checkpoint-e2e",
            )

            checkpoint_id = None

            async def mock_spawn(*args, **kwargs):
                nonlocal checkpoint_id
                # Simulate mid-execution: create a checkpoint as if the
                # sub-agent or orchestrator is saving progress
                feature = get_feature(ready_feature.id)

                state = {
                    "feature_id": feature.id,
                    "feature_status": "executing",
                    "tasks_completed": feature.tasks_completed,
                    "tasks_total": feature.tasks_total,
                    "confidence": {
                        "spec_understanding": feature.conf_spec_understanding,
                        "impl_correctness": feature.conf_impl_correctness,
                        "test_adequacy": feature.conf_test_adequacy,
                    },
                }
                cp = create_checkpoint(
                    project_id=project.id,
                    feature_id=feature.id,
                    checkpoint_type="task_completion",
                    state_snapshot=json.dumps(state),
                    cost_at_checkpoint=0.75,
                    duration_at_checkpoint_ms=3000,
                )
                checkpoint_id = cp.id

                mock_result = ExecutionResult(
                    text="Feature implemented successfully",
                    is_error=False,
                    duration_ms=5000,
                    num_turns=10,
                    total_cost_usd=1.50,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                await loop.run()

            # Verify checkpoint was created and persisted
            assert checkpoint_id is not None
            cp = get_checkpoint(checkpoint_id)
            assert cp is not None
            assert cp.feature_id == ready_feature.id
            assert cp.checkpoint_type == "task_completion"
            assert cp.cost_at_checkpoint == 0.75
            assert cp.can_resume is True  # Not yet resumed

            # Verify state snapshot content
            parsed_state = json.loads(cp.state_snapshot)
            assert parsed_state["feature_status"] == "executing"
            assert parsed_state["tasks_completed"] == 2
            assert parsed_state["tasks_total"] == 5


class TestE2ESimulateCrash:
    """Step 3: Simulate crash/interruption."""

    @pytest.mark.asyncio
    async def test_graceful_shutdown_creates_checkpoint(self, tmp_db, project, ready_feature):
        """Graceful shutdown (SIGINT) creates a checkpoint and interrupts the feature."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/checkpoint-e2e",
            )

            async def mock_spawn_with_shutdown(*args, **kwargs):
                # Simulate: the agent runs but returns an error because
                # shutdown was requested mid-execution
                loop.request_shutdown()

                mock_result = ExecutionResult(
                    text="Execution interrupted by shutdown",
                    is_error=True,
                    error_message="Shutdown requested",
                    duration_ms=3000,
                    num_turns=5,
                    total_cost_usd=0.80,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_with_shutdown,
            ), patch(
                "bob.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob.orchestrator.run_loop.stop_mcp_server",
            ):
                termination = await loop.run()

            # Loop should terminate with SHUTDOWN_REQUESTED
            assert termination == LoopTermination.SHUTDOWN_REQUESTED

            # Feature should be interrupted
            interrupted_feature = get_feature(ready_feature.id)
            assert interrupted_feature.status == "interrupted"

            # An interruption checkpoint should have been created
            checkpoints = list_checkpoints(feature_id=ready_feature.id)
            assert len(checkpoints) >= 1
            cp = checkpoints[-1]
            assert cp.checkpoint_type == "interruption"
            assert cp.can_resume is True

            # Verify checkpoint state captures useful info
            state = json.loads(cp.state_snapshot)
            assert state["feature_id"] == ready_feature.id
            assert state["reason"] == "graceful_shutdown"

    def test_simulate_hard_crash_feature_left_executing(self, tmp_db, project, ready_feature):
        """Simulate hard crash: feature left in 'executing' status with no checkpoint."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            # Simulate a crash by directly setting feature to 'executing'
            # (as if the process died mid-execution)
            update_feature(ready_feature.id, status="executing")

            stuck = get_feature(ready_feature.id)
            assert stuck.status == "executing"

            # No checkpoint exists (hard crash)
            checkpoints = list_checkpoints(feature_id=ready_feature.id)
            assert len(checkpoints) == 0

    def test_simulate_crash_with_checkpoint(self, tmp_db, project, ready_feature):
        """Simulate crash with a previously created checkpoint."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            # Feature was executing
            update_feature(
                ready_feature.id,
                status="executing",
                tasks_completed=3,
                tasks_total=5,
                conf_spec_understanding=0.85,
                conf_impl_correctness=0.7,
                conf_test_adequacy=0.5,
            )

            # Create checkpoint mid-execution (before crash)
            state = {
                "feature_id": ready_feature.id,
                "feature_status": "executing",
                "tasks_completed": 3,
                "tasks_total": 5,
                "confidence": {
                    "spec_understanding": 0.85,
                    "impl_correctness": 0.7,
                    "test_adequacy": 0.5,
                },
            }
            cp = create_checkpoint(
                project_id=project.id,
                feature_id=ready_feature.id,
                checkpoint_type="task_completion",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=1.50,
                duration_at_checkpoint_ms=30000,
            )

            # Simulate crash: feature stuck in 'executing'
            assert get_feature(ready_feature.id).status == "executing"
            assert cp.can_resume is True


class TestE2EResumeFromCheckpoint:
    """Step 4: Resume from checkpoint."""

    @pytest.mark.asyncio
    async def test_auto_resume_on_startup(self, tmp_db, project, ready_feature):
        """OrchestrationLoop auto-resumes interrupted features on startup."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            # Setup: Feature was interrupted with a checkpoint
            update_feature(
                ready_feature.id,
                status="interrupted",
                tasks_completed=0,
                conf_spec_understanding=0.0,
                conf_impl_correctness=0.0,
                conf_test_adequacy=0.0,
            )

            state = {
                "feature_id": ready_feature.id,
                "feature_status": "executing",
                "tasks_completed": 3,
                "tasks_total": 5,
                "confidence": {
                    "spec_understanding": 0.85,
                    "impl_correctness": 0.7,
                    "test_adequacy": 0.5,
                },
            }
            cp = create_checkpoint(
                project_id=project.id,
                feature_id=ready_feature.id,
                checkpoint_type="task_completion",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=1.50,
            )

            # Create the loop (which calls _resume_interrupted_work on run())
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/checkpoint-e2e",
            )

            async def mock_spawn(*args, **kwargs):
                mock_result = ExecutionResult(
                    text="Feature completed after resume",
                    is_error=False,
                    duration_ms=3000,
                    num_turns=8,
                    total_cost_usd=1.00,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                termination = await loop.run()

            # Verify the checkpoint was consumed (can_resume=False)
            consumed_cp = get_checkpoint(cp.id)
            assert consumed_cp.can_resume is False
            assert consumed_cp.resumed_at is not None

            # Verify feature completed
            assert termination == LoopTermination.ALL_COMPLETED

    @pytest.mark.asyncio
    async def test_auto_resume_restores_state_then_completes(self, tmp_db, project, ready_feature):
        """Auto-resume restores confidence and task counts before re-executing."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            # Feature interrupted with zeroed-out state
            update_feature(
                ready_feature.id,
                status="interrupted",
                tasks_completed=0,
                tasks_total=0,
                conf_spec_understanding=0.0,
                conf_impl_correctness=0.0,
                conf_test_adequacy=0.0,
                readiness_score=0.9,
            )

            # Checkpoint preserves the real state
            state = {
                "feature_id": ready_feature.id,
                "feature_status": "executing",
                "tasks_completed": 3,
                "tasks_total": 5,
                "confidence": {
                    "spec_understanding": 0.85,
                    "impl_correctness": 0.7,
                    "test_adequacy": 0.5,
                },
            }
            cp = create_checkpoint(
                project_id=project.id,
                feature_id=ready_feature.id,
                checkpoint_type="task_completion",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=2.00,
                duration_at_checkpoint_ms=45000,
            )

            # Track state after resume but before execution
            state_after_resume = {}

            async def mock_spawn(*args, **kwargs):
                nonlocal state_after_resume
                # By this point, _resume_interrupted_work has already run
                # and then the feature was set to 'ready', and now it's 'executing'
                f = get_feature(ready_feature.id)
                state_after_resume = {
                    "tasks_completed": f.tasks_completed,
                    "tasks_total": f.tasks_total,
                    "conf_spec_understanding": f.conf_spec_understanding,
                    "conf_impl_correctness": f.conf_impl_correctness,
                    "conf_test_adequacy": f.conf_test_adequacy,
                }

                mock_result = ExecutionResult(
                    text="Feature completed",
                    is_error=False,
                    duration_ms=3000,
                    num_turns=8,
                    total_cost_usd=1.00,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/checkpoint-e2e",
            )

            with patch(
                "bob.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                await loop.run()

            # Verify that state was restored from checkpoint before execution
            assert state_after_resume["tasks_completed"] == 3
            assert state_after_resume["tasks_total"] == 5
            assert state_after_resume["conf_spec_understanding"] == 0.85
            assert state_after_resume["conf_impl_correctness"] == 0.7
            assert state_after_resume["conf_test_adequacy"] == 0.5

    def test_resume_directly_restores_feature_and_task_state(self, tmp_db, project, ready_feature):
        """Directly calling resume_from_checkpoint restores feature and task state."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            # Create a task associated with the feature
            task = create_task(
                feature_id=ready_feature.id,
                project_id=project.id,
                type="implementation",
                title="E2E Checkpoint Task",
                description="Task for checkpoint resume testing",
                status="executing",
            )

            # Create checkpoint with full state
            state = {
                "feature_id": ready_feature.id,
                "feature_status": "executing",
                "task_id": task.id,
                "task_status": "executing",
                "tasks_completed": 3,
                "tasks_total": 5,
                "confidence": {
                    "spec_understanding": 0.85,
                    "impl_correctness": 0.7,
                    "test_adequacy": 0.5,
                },
            }
            cp = create_checkpoint(
                project_id=project.id,
                feature_id=ready_feature.id,
                task_id=task.id,
                checkpoint_type="task_completion",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=2.50,
                duration_at_checkpoint_ms=60000,
            )

            # Simulate crash: corrupt the feature and task state
            update_feature(
                ready_feature.id,
                status="interrupted",
                tasks_completed=0,
                tasks_total=0,
                conf_spec_understanding=0.0,
                conf_impl_correctness=0.0,
                conf_test_adequacy=0.0,
            )
            update_task(task.id, status="interrupted")

            # Verify corrupted state
            assert get_feature(ready_feature.id).status == "interrupted"
            assert get_task(task.id).status == "interrupted"

            # Resume from checkpoint
            resumed_cp = resume_from_checkpoint(cp.id)

            # Verify checkpoint metadata updated
            assert resumed_cp.can_resume is False
            assert resumed_cp.resumed_at is not None

            # Verify feature state restored
            restored_feature = get_feature(ready_feature.id)
            assert restored_feature.status == "executing"
            assert restored_feature.tasks_completed == 3
            assert restored_feature.tasks_total == 5
            assert restored_feature.conf_spec_understanding == 0.85
            assert restored_feature.conf_impl_correctness == 0.7
            assert restored_feature.conf_test_adequacy == 0.5

            # Verify task state restored
            restored_task = get_task(task.id)
            assert restored_task.status == "executing"


class TestE2EFeatureCompletesFromCheckpoint:
    """Step 5: Verify feature completes from checkpoint state."""

    @pytest.mark.asyncio
    async def test_full_checkpoint_resume_to_completion(self, tmp_db, project, ready_feature):
        """Full E2E: execute -> checkpoint -> crash -> resume -> complete.

        This test exercises the entire lifecycle:
        1. Feature starts executing
        2. Checkpoint is created mid-execution
        3. Execution fails (simulating crash)
        4. Feature is left 'interrupted' with a checkpoint
        5. A new orchestration loop starts
        6. Auto-resume restores state from checkpoint
        7. Feature re-executes and completes successfully
        """
        with patch("bob.db.get_database_path", return_value=tmp_db):
            # ---- Phase 1: Initial execution that gets interrupted ----
            loop1 = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/checkpoint-e2e",
            )

            async def mock_spawn_interrupted(*args, **kwargs):
                # Create a checkpoint mid-execution
                feature = get_feature(ready_feature.id)
                state = {
                    "feature_id": feature.id,
                    "feature_status": "executing",
                    "tasks_completed": feature.tasks_completed,
                    "tasks_total": feature.tasks_total,
                    "confidence": {
                        "spec_understanding": feature.conf_spec_understanding,
                        "impl_correctness": feature.conf_impl_correctness,
                        "test_adequacy": feature.conf_test_adequacy,
                    },
                }
                create_checkpoint(
                    project_id=project.id,
                    feature_id=feature.id,
                    checkpoint_type="task_completion",
                    state_snapshot=json.dumps(state),
                    cost_at_checkpoint=1.00,
                    duration_at_checkpoint_ms=15000,
                )

                # Signal shutdown after checkpoint
                loop1.request_shutdown()

                mock_result = ExecutionResult(
                    text="Interrupted during execution",
                    is_error=True,
                    error_message="Shutdown requested",
                    duration_ms=15000,
                    num_turns=5,
                    total_cost_usd=1.00,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_interrupted,
            ), patch(
                "bob.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob.orchestrator.run_loop.stop_mcp_server",
            ):
                termination1 = await loop1.run()

            assert termination1 == LoopTermination.SHUTDOWN_REQUESTED

            # Feature should be interrupted
            interrupted = get_feature(ready_feature.id)
            assert interrupted.status == "interrupted"

            # There should be checkpoints (manual one + interruption one)
            checkpoints = list_checkpoints(feature_id=ready_feature.id)
            assert len(checkpoints) >= 1

            # At least one should be resumable
            resumable = find_resumable_checkpoints(project_id=project.id)
            assert len(resumable) >= 1

            # ---- Phase 2: New loop starts and resumes from checkpoint ----
            loop2 = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/checkpoint-e2e",
            )

            spawn_count = 0

            async def mock_spawn_success(*args, **kwargs):
                nonlocal spawn_count
                spawn_count += 1

                mock_result = ExecutionResult(
                    text="Feature completed after resume",
                    is_error=False,
                    duration_ms=4000,
                    num_turns=10,
                    total_cost_usd=1.50,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_success,
            ), patch(
                "bob.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob.orchestrator.run_loop.git_commit_feature",
                return_value="ghi789",
            ):
                termination2 = await loop2.run()

            # Feature should complete this time
            assert termination2 == LoopTermination.ALL_COMPLETED
            assert spawn_count == 1

            # Verify final feature state
            completed_feature = get_feature(ready_feature.id)
            assert completed_feature.status == "completed"

            # Verify evidence was created
            evidence = query_evidence(feature_id=ready_feature.id)
            assert len(evidence) >= 1

            # Verify the checkpoints from phase 1 are consumed
            all_checkpoints = list_checkpoints(feature_id=ready_feature.id)
            # The resumable checkpoints should now be consumed
            still_resumable = find_resumable_checkpoints(project_id=project.id)
            # We expect at least the one consumed by resume to be non-resumable
            consumed = [cp for cp in all_checkpoints if not cp.can_resume]
            assert len(consumed) >= 1

    @pytest.mark.asyncio
    async def test_fresh_mode_ignores_checkpoints(self, tmp_db, project, ready_feature):
        """In fresh mode, checkpoints are NOT consumed; features reset to 'ready'."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            # Setup: interrupted feature with a checkpoint
            update_feature(
                ready_feature.id,
                status="interrupted",
                tasks_completed=0,
                conf_spec_understanding=0.0,
                conf_impl_correctness=0.0,
                conf_test_adequacy=0.0,
            )

            state = {
                "feature_id": ready_feature.id,
                "feature_status": "executing",
                "tasks_completed": 3,
                "tasks_total": 5,
                "confidence": {
                    "spec_understanding": 0.85,
                    "impl_correctness": 0.7,
                    "test_adequacy": 0.5,
                },
            }
            cp = create_checkpoint(
                project_id=project.id,
                feature_id=ready_feature.id,
                checkpoint_type="task_completion",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=2.00,
            )

            # Create loop in fresh mode
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/checkpoint-e2e",
                fresh=True,
            )

            async def mock_spawn(*args, **kwargs):
                mock_result = ExecutionResult(
                    text="Feature completed from scratch",
                    is_error=False,
                    duration_ms=5000,
                    num_turns=12,
                    total_cost_usd=2.00,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED

            # The checkpoint should still be resumable (not consumed)
            preserved_cp = get_checkpoint(cp.id)
            assert preserved_cp.can_resume is True

            # Feature completed despite not using the checkpoint
            assert get_feature(ready_feature.id).status == "completed"

    @pytest.mark.asyncio
    async def test_multiple_features_one_interrupted_resumes(self, tmp_db, project):
        """Multiple features: one interrupted with checkpoint, others completed."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            # Feature 1: already completed
            f1 = create_feature(
                project_id=project.id,
                name="Already Completed",
                description="This feature was done before the crash",
                status="completed",
                priority=10,
                risk_category="low",
            )

            # Feature 2: interrupted with checkpoint
            f2 = create_feature(
                project_id=project.id,
                name="Interrupted Feature",
                description="This feature was interrupted",
                status="interrupted",
                priority=20,
                risk_category="low",
            )
            update_feature(
                f2.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )

            state = {
                "feature_id": f2.id,
                "feature_status": "executing",
                "tasks_completed": 1,
                "tasks_total": 3,
                "confidence": {
                    "spec_understanding": 0.9,
                    "impl_correctness": 0.8,
                    "test_adequacy": 0.6,
                },
            }
            cp = create_checkpoint(
                project_id=project.id,
                feature_id=f2.id,
                checkpoint_type="interruption",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=1.00,
            )

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/checkpoint-e2e",
            )

            async def mock_spawn(*args, **kwargs):
                mock_result = ExecutionResult(
                    text="Feature completed",
                    is_error=False,
                    duration_ms=3000,
                    num_turns=8,
                    total_cost_usd=1.00,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED

            # Both features should be completed
            assert get_feature(f1.id).status == "completed"
            assert get_feature(f2.id).status == "completed"

            # Checkpoint should be consumed
            consumed_cp = get_checkpoint(cp.id)
            assert consumed_cp.can_resume is False

    @pytest.mark.asyncio
    async def test_hard_crash_no_checkpoint_resets_to_ready(self, tmp_db, project, ready_feature):
        """Feature stuck in 'executing' with no checkpoint resets to 'ready'."""
        with patch("bob.db.get_database_path", return_value=tmp_db):
            # Simulate hard crash: feature left in 'executing', no checkpoint
            update_feature(ready_feature.id, status="executing")

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/checkpoint-e2e",
            )

            async def mock_spawn(*args, **kwargs):
                mock_result = ExecutionResult(
                    text="Feature completed from scratch after reset",
                    is_error=False,
                    duration_ms=5000,
                    num_turns=12,
                    total_cost_usd=2.00,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED
            assert get_feature(ready_feature.id).status == "completed"
