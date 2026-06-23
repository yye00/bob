"""Tests for F056: Implement checkpoint resume functionality."""

import json
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
    """Create a test project."""
    from bob3.db import create_project

    return create_project(
        name="Resume Test Project",
        workspace_path="/tmp/resume-test",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature."""
    from bob3.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Test Feature",
        description="A feature for resume testing",
        status="executing",
    )


@pytest.fixture()
def task(feature):
    """Create a test task."""
    from bob3.db import create_task

    return create_task(
        feature_id=feature.id,
        project_id=feature.project_id,
        type="implementation",
        title="Test Task",
        description="A task for resume testing",
        status="executing",
    )


# ============================================================
# Step 1: Add resume_from_checkpoint() function
# ============================================================


class TestResumeFromCheckpointExists:
    """Step 1: resume_from_checkpoint() is importable and callable."""

    def test_function_is_importable(self, db_path):
        from bob3.db import resume_from_checkpoint

        assert callable(resume_from_checkpoint)

    def test_returns_resource_checkpoint_model(self, feature):
        from bob3.db import create_checkpoint, resume_from_checkpoint
        from bob3.models import ResourceCheckpoint

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"status": "executing"}),
        )
        result = resume_from_checkpoint(cp.id)
        assert isinstance(result, ResourceCheckpoint)

    def test_raises_on_nonexistent_checkpoint(self, db_path):
        from bob3.db import resume_from_checkpoint

        with pytest.raises(ValueError, match="not found"):
            resume_from_checkpoint("nonexistent-id")

    def test_raises_on_non_resumable_checkpoint(self, feature):
        """Cannot resume a checkpoint that has can_resume=False."""
        from bob3.db import create_checkpoint, resume_from_checkpoint

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"status": "executing"}),
        )
        # Resume it once
        resume_from_checkpoint(cp.id)
        # Trying to resume again should fail (already resumed)
        with pytest.raises(ValueError, match="already been resumed"):
            resume_from_checkpoint(cp.id)


# ============================================================
# Step 2: Load state_snapshot and restore feature/task state
# ============================================================


class TestRestoreFeatureTaskState:
    """Step 2: state_snapshot is loaded and feature/task state is restored."""

    def test_feature_status_restored(self, feature):
        """Resuming restores the feature status from the snapshot."""
        from bob3.db import (
            create_checkpoint,
            get_feature,
            resume_from_checkpoint,
            update_feature,
        )

        # Snapshot current state
        state = {
            "feature_status": "executing",
            "feature_id": feature.id,
        }
        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps(state),
        )

        # Simulate interruption: change feature status to "interrupted"
        update_feature(feature.id, status="interrupted")
        interrupted = get_feature(feature.id)
        assert interrupted.status == "interrupted"

        # Resume from checkpoint
        resume_from_checkpoint(cp.id)

        # Feature status should be restored
        restored = get_feature(feature.id)
        assert restored.status == "executing"

    def test_task_status_restored(self, task):
        """Resuming restores the task status from the snapshot."""
        from bob3.db import (
            create_checkpoint,
            get_task,
            resume_from_checkpoint,
            update_task,
        )

        state = {
            "feature_status": "executing",
            "feature_id": task.feature_id,
            "task_status": "executing",
            "task_id": task.id,
        }
        cp = create_checkpoint(
            project_id=task.project_id,
            feature_id=task.feature_id,
            task_id=task.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps(state),
        )

        # Simulate interruption
        update_task(task.id, status="interrupted")
        interrupted = get_task(task.id)
        assert interrupted.status == "interrupted"

        # Resume
        resume_from_checkpoint(cp.id)

        restored = get_task(task.id)
        assert restored.status == "executing"

    def test_feature_confidence_restored(self, feature):
        """Resuming restores confidence scores from the snapshot."""
        from bob3.db import (
            create_checkpoint,
            get_feature,
            resume_from_checkpoint,
            update_feature,
        )

        state = {
            "feature_status": "executing",
            "feature_id": feature.id,
            "confidence": {
                "spec_understanding": 0.8,
                "impl_correctness": 0.6,
                "test_adequacy": 0.4,
            },
        }
        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps(state),
        )

        # Simulate interruption - confidence gets reset
        update_feature(
            feature.id,
            status="interrupted",
            conf_spec_understanding=0.0,
            conf_impl_correctness=0.0,
            conf_test_adequacy=0.0,
        )

        # Resume
        resume_from_checkpoint(cp.id)

        restored = get_feature(feature.id)
        assert restored.status == "executing"
        assert restored.conf_spec_understanding == 0.8
        assert restored.conf_impl_correctness == 0.6
        assert restored.conf_test_adequacy == 0.4

    def test_task_completion_counts_restored(self, feature):
        """Resuming restores tasks_completed and tasks_total from snapshot."""
        from bob3.db import (
            create_checkpoint,
            get_feature,
            resume_from_checkpoint,
            update_feature,
        )

        state = {
            "feature_status": "executing",
            "feature_id": feature.id,
            "tasks_completed": 3,
            "tasks_total": 5,
        }
        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps(state),
        )

        # Simulate reset
        update_feature(feature.id, status="interrupted", tasks_completed=0)

        # Resume
        resume_from_checkpoint(cp.id)

        restored = get_feature(feature.id)
        assert restored.tasks_completed == 3
        assert restored.tasks_total == 5


# ============================================================
# Step 3: Set resumed_at timestamp
# ============================================================


class TestResumedAtTimestamp:
    """Step 3: resumed_at timestamp is set when checkpoint is resumed."""

    def test_resumed_at_set(self, feature):
        from bob3.db import create_checkpoint, get_checkpoint, resume_from_checkpoint

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"feature_status": "executing", "feature_id": feature.id}),
        )

        # Before resume, resumed_at should be None
        before = get_checkpoint(cp.id)
        assert before.resumed_at is None

        # Resume
        result = resume_from_checkpoint(cp.id)

        # After resume, resumed_at should be set
        assert result.resumed_at is not None

        # Verify in database too
        after = get_checkpoint(cp.id)
        assert after.resumed_at is not None

    def test_can_resume_set_to_false_after_resume(self, feature):
        from bob3.db import create_checkpoint, get_checkpoint, resume_from_checkpoint

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"feature_status": "executing", "feature_id": feature.id}),
        )

        assert cp.can_resume is True

        resume_from_checkpoint(cp.id)

        after = get_checkpoint(cp.id)
        assert after.can_resume is False


# ============================================================
# Step 4: Test: Create checkpoint, simulate interruption, resume, verify state restored
# ============================================================


class TestEndToEndResumeFlow:
    """Step 4: Full end-to-end test of checkpoint creation, interruption, and resume."""

    def test_full_checkpoint_resume_cycle(self, feature, task):
        """E2E: Create checkpoint, simulate interruption, resume, verify state restored."""
        from bob3.db import (
            create_checkpoint,
            get_checkpoint,
            get_feature,
            get_task,
            list_checkpoints,
            resume_from_checkpoint,
            update_feature,
            update_task,
        )

        # 1. Build realistic state snapshot during execution
        state = {
            "feature_id": feature.id,
            "feature_status": "executing",
            "task_id": task.id,
            "task_status": "executing",
            "tasks_completed": 2,
            "tasks_total": 5,
            "confidence": {
                "spec_understanding": 0.9,
                "impl_correctness": 0.7,
                "test_adequacy": 0.5,
            },
        }

        files = [
            {"path": "src/main.py", "hash": "abc123"},
            {"path": "tests/test_main.py", "hash": "def456"},
        ]

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            task_id=task.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps(state),
            files_snapshot=json.dumps(files),
            cost_at_checkpoint=3.50,
            duration_at_checkpoint_ms=90000,
        )

        # 2. Simulate interruption
        update_feature(
            feature.id,
            status="interrupted",
            tasks_completed=0,
            conf_spec_understanding=0.0,
            conf_impl_correctness=0.0,
            conf_test_adequacy=0.0,
        )
        update_task(task.id, status="interrupted")

        # Verify interrupted state
        assert get_feature(feature.id).status == "interrupted"
        assert get_task(task.id).status == "interrupted"

        # 3. Resume from checkpoint
        resumed_cp = resume_from_checkpoint(cp.id)

        # 4. Verify state restored
        restored_feature = get_feature(feature.id)
        assert restored_feature.status == "executing"
        assert restored_feature.tasks_completed == 2
        assert restored_feature.tasks_total == 5
        assert restored_feature.conf_spec_understanding == 0.9
        assert restored_feature.conf_impl_correctness == 0.7
        assert restored_feature.conf_test_adequacy == 0.5

        restored_task = get_task(task.id)
        assert restored_task.status == "executing"

        # 5. Verify checkpoint metadata updated
        assert resumed_cp.resumed_at is not None
        assert resumed_cp.can_resume is False

        # 6. Verify in database
        db_cp = get_checkpoint(cp.id)
        assert db_cp.can_resume is False
        assert db_cp.resumed_at is not None

    def test_resume_feature_only_checkpoint(self, feature):
        """Resume a feature-level checkpoint (no task_id)."""
        from bob3.db import (
            create_checkpoint,
            get_feature,
            resume_from_checkpoint,
            update_feature,
        )

        state = {
            "feature_id": feature.id,
            "feature_status": "executing",
            "tasks_completed": 1,
            "tasks_total": 3,
        }

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="manual",
            state_snapshot=json.dumps(state),
        )

        # Interrupt
        update_feature(feature.id, status="interrupted", tasks_completed=0)

        # Resume
        resume_from_checkpoint(cp.id)

        restored = get_feature(feature.id)
        assert restored.status == "executing"
        assert restored.tasks_completed == 1
        assert restored.tasks_total == 3

    def test_resume_picks_latest_resumable_checkpoint(self, feature):
        """Multiple checkpoints exist; only the latest resumable one is used."""
        from bob3.db import (
            create_checkpoint,
            get_feature,
            list_checkpoints,
            resume_from_checkpoint,
            update_feature,
        )

        # Create two checkpoints with different state
        cp1 = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({
                "feature_id": feature.id,
                "feature_status": "executing",
                "tasks_completed": 1,
                "tasks_total": 5,
            }),
        )

        cp2 = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({
                "feature_id": feature.id,
                "feature_status": "executing",
                "tasks_completed": 3,
                "tasks_total": 5,
            }),
        )

        # Interrupt
        update_feature(feature.id, status="interrupted", tasks_completed=0)

        # Resume from the second (latest) checkpoint
        resume_from_checkpoint(cp2.id)

        restored = get_feature(feature.id)
        assert restored.tasks_completed == 3

        # cp2 is no longer resumable, but cp1 still is
        checkpoints = list_checkpoints(feature_id=feature.id)
        cp1_after = next(c for c in checkpoints if c.id == cp1.id)
        cp2_after = next(c for c in checkpoints if c.id == cp2.id)
        assert cp1_after.can_resume is True
        assert cp2_after.can_resume is False
