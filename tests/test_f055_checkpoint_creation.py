"""Tests for F055: Implement checkpoint creation for feature/task state."""

import hashlib
import json
import pathlib
import tempfile

import pytest

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Create a temporary database and initialize schema."""
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(p))
    from bob.db import init_database

    init_database()
    return p


@pytest.fixture()
def project(db_path):
    """Create a test project."""
    from bob.db import create_project

    return create_project(
        name="Checkpoint Test Project",
        workspace_path="/tmp/checkpoint-test",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature."""
    from bob.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Test Feature",
        description="A feature for checkpoint testing",
        status="executing",
    )


@pytest.fixture()
def task(feature):
    """Create a test task."""
    from bob.db import create_task

    return create_task(
        feature_id=feature.id,
        project_id=feature.project_id,
        type="implementation",
        title="Test Task",
        description="A task for checkpoint testing",
        status="executing",
    )


# ============================================================
# Step 1: Add create_checkpoint() function
# ============================================================


class TestCreateCheckpointExists:
    """Step 1: create_checkpoint() is importable and callable."""

    def test_function_is_importable(self, db_path):
        from bob.db import create_checkpoint

        assert callable(create_checkpoint)

    def test_returns_resource_checkpoint_model(self, feature):
        from bob.db import create_checkpoint
        from bob.models import ResourceCheckpoint

        result = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"status": "executing"}),
        )
        assert isinstance(result, ResourceCheckpoint)

    def test_generated_id_is_uuid(self, feature):
        from bob.db import create_checkpoint

        result = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"status": "executing"}),
        )
        assert len(result.id) == 36  # UUID format


# ============================================================
# Step 2: Capture state_snapshot (JSON of current feature/task state)
# ============================================================


class TestCaptureStateSnapshot:
    """Step 2: state_snapshot stores JSON of current feature/task state."""

    def test_state_snapshot_stored(self, feature):
        from bob.db import create_checkpoint, get_checkpoint

        state = {
            "feature_status": "executing",
            "tasks_completed": 2,
            "tasks_total": 5,
            "confidence": {"spec": 0.8, "impl": 0.6, "test": 0.4},
        }
        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps(state),
        )
        fetched = get_checkpoint(cp.id)
        assert fetched is not None
        parsed = json.loads(fetched.state_snapshot)
        assert parsed["feature_status"] == "executing"
        assert parsed["tasks_completed"] == 2
        assert parsed["tasks_total"] == 5
        assert parsed["confidence"]["impl"] == 0.6

    def test_state_snapshot_with_task_id(self, task):
        from bob.db import create_checkpoint, get_checkpoint

        state = {
            "task_status": "executing",
            "attempt": 1,
            "max_attempts": 5,
        }
        cp = create_checkpoint(
            project_id=task.project_id,
            feature_id=task.feature_id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps(state),
            task_id=task.id,
        )
        fetched = get_checkpoint(cp.id)
        assert fetched is not None
        assert fetched.task_id == task.id
        parsed = json.loads(fetched.state_snapshot)
        assert parsed["task_status"] == "executing"

    def test_state_snapshot_is_required(self, feature):
        """state_snapshot is a required parameter."""
        from bob.db import create_checkpoint

        with pytest.raises(TypeError):
            create_checkpoint(
                project_id=feature.project_id,
                feature_id=feature.id,
                checkpoint_type="task_completion",
                # Missing state_snapshot
            )


# ============================================================
# Step 3: Capture files_snapshot (list of files and hashes)
# ============================================================


class TestCaptureFilesSnapshot:
    """Step 3: files_snapshot stores list of files and their hashes."""

    def test_files_snapshot_stored(self, feature):
        from bob.db import create_checkpoint, get_checkpoint

        files = [
            {"path": "src/main.py", "hash": "abc123"},
            {"path": "tests/test_main.py", "hash": "def456"},
        ]
        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"status": "executing"}),
            files_snapshot=json.dumps(files),
        )
        fetched = get_checkpoint(cp.id)
        assert fetched is not None
        assert fetched.files_snapshot is not None
        parsed = json.loads(fetched.files_snapshot)
        assert len(parsed) == 2
        assert parsed[0]["path"] == "src/main.py"
        assert parsed[1]["hash"] == "def456"

    def test_files_snapshot_optional(self, feature):
        from bob.db import create_checkpoint, get_checkpoint

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"status": "executing"}),
        )
        fetched = get_checkpoint(cp.id)
        assert fetched is not None
        assert fetched.files_snapshot is None


# ============================================================
# Step 4: Store cost and duration at checkpoint
# ============================================================


class TestStoreCostAndDuration:
    """Step 4: cost_at_checkpoint and duration_at_checkpoint_ms are stored."""

    def test_cost_stored(self, feature):
        from bob.db import create_checkpoint, get_checkpoint

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"status": "executing"}),
            cost_at_checkpoint=1.25,
        )
        fetched = get_checkpoint(cp.id)
        assert fetched is not None
        assert fetched.cost_at_checkpoint == 1.25

    def test_duration_stored(self, feature):
        from bob.db import create_checkpoint, get_checkpoint

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"status": "executing"}),
            duration_at_checkpoint_ms=45000,
        )
        fetched = get_checkpoint(cp.id)
        assert fetched is not None
        assert fetched.duration_at_checkpoint_ms == 45000

    def test_cost_and_duration_together(self, feature):
        from bob.db import create_checkpoint, get_checkpoint

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="resource_limit",
            state_snapshot=json.dumps({"status": "resource_limited"}),
            cost_at_checkpoint=99.50,
            duration_at_checkpoint_ms=120000,
        )
        fetched = get_checkpoint(cp.id)
        assert fetched is not None
        assert fetched.cost_at_checkpoint == 99.50
        assert fetched.duration_at_checkpoint_ms == 120000
        assert fetched.checkpoint_type == "resource_limit"

    def test_cost_and_duration_optional(self, feature):
        from bob.db import create_checkpoint, get_checkpoint

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="manual",
            state_snapshot=json.dumps({"status": "executing"}),
        )
        fetched = get_checkpoint(cp.id)
        assert fetched is not None
        assert fetched.cost_at_checkpoint is None
        assert fetched.duration_at_checkpoint_ms is None


# ============================================================
# Step 5: Test: Create checkpoint during feature execution, verify snapshot stored
# ============================================================


class TestEndToEndCheckpointCreation:
    """Step 5: Full end-to-end test of checkpoint creation during execution."""

    def test_create_checkpoint_during_execution_verify_stored(self, feature, task):
        """E2E: Create checkpoint during feature execution, verify all fields stored."""
        from bob.db import create_checkpoint, get_checkpoint, list_checkpoints

        # Build a realistic state snapshot
        state = {
            "feature_id": feature.id,
            "feature_status": "executing",
            "task_id": task.id,
            "task_status": "executing",
            "tasks_completed": 1,
            "tasks_total": 3,
            "confidence": {
                "spec_understanding": 0.9,
                "impl_correctness": 0.5,
                "test_adequacy": 0.3,
            },
        }

        # Build a files snapshot
        files = [
            {"path": "src/bob/db.py", "hash": hashlib.sha256(b"db content").hexdigest()},
            {"path": "src/bob/models.py", "hash": hashlib.sha256(b"models content").hexdigest()},
            {"path": "tests/test_f055.py", "hash": hashlib.sha256(b"test content").hexdigest()},
        ]

        # Create checkpoint
        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            task_id=task.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps(state),
            files_snapshot=json.dumps(files),
            cost_at_checkpoint=2.50,
            duration_at_checkpoint_ms=60000,
        )

        # Verify the returned model
        assert cp.project_id == feature.project_id
        assert cp.feature_id == feature.id
        assert cp.task_id == task.id
        assert cp.checkpoint_type == "task_completion"
        assert cp.can_resume is True

        # Verify stored in database
        fetched = get_checkpoint(cp.id)
        assert fetched is not None

        # Verify state snapshot
        parsed_state = json.loads(fetched.state_snapshot)
        assert parsed_state["feature_status"] == "executing"
        assert parsed_state["tasks_completed"] == 1
        assert parsed_state["confidence"]["spec_understanding"] == 0.9

        # Verify files snapshot
        parsed_files = json.loads(fetched.files_snapshot)
        assert len(parsed_files) == 3
        assert parsed_files[0]["path"] == "src/bob/db.py"

        # Verify cost and duration
        assert fetched.cost_at_checkpoint == 2.50
        assert fetched.duration_at_checkpoint_ms == 60000

    def test_list_checkpoints_for_feature(self, feature):
        """Verify that checkpoints can be listed for a feature."""
        from bob.db import create_checkpoint, list_checkpoints

        # Create multiple checkpoints
        create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"step": 1}),
            cost_at_checkpoint=1.0,
        )
        create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"step": 2}),
            cost_at_checkpoint=2.0,
        )
        create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="resource_limit",
            state_snapshot=json.dumps({"step": 3}),
            cost_at_checkpoint=3.0,
        )

        checkpoints = list_checkpoints(feature_id=feature.id)
        assert len(checkpoints) == 3
        # Ordered by creation time
        costs = [cp.cost_at_checkpoint for cp in checkpoints]
        assert costs == [1.0, 2.0, 3.0]

    def test_list_checkpoints_empty(self, feature):
        """Listing checkpoints for a feature with none returns empty list."""
        from bob.db import list_checkpoints

        checkpoints = list_checkpoints(feature_id=feature.id)
        assert checkpoints == []

    def test_get_nonexistent_checkpoint_returns_none(self, db_path):
        """Getting a nonexistent checkpoint returns None."""
        from bob.db import get_checkpoint

        result = get_checkpoint("nonexistent-id")
        assert result is None

    def test_checkpoint_can_resume_default_true(self, feature):
        """New checkpoints have can_resume=True by default."""
        from bob.db import create_checkpoint

        cp = create_checkpoint(
            project_id=feature.project_id,
            feature_id=feature.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"status": "executing"}),
        )
        assert cp.can_resume is True

    def test_multiple_features_isolated(self, project):
        """Checkpoints from different features don't mix."""
        from bob.db import create_checkpoint, create_feature, list_checkpoints

        f1 = create_feature(
            project_id=project.id, name="Feature A", status="executing"
        )
        f2 = create_feature(
            project_id=project.id, name="Feature B", status="executing"
        )

        create_checkpoint(
            project_id=project.id,
            feature_id=f1.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"feature": "A"}),
        )
        create_checkpoint(
            project_id=project.id,
            feature_id=f2.id,
            checkpoint_type="task_completion",
            state_snapshot=json.dumps({"feature": "B"}),
        )

        cp1 = list_checkpoints(feature_id=f1.id)
        cp2 = list_checkpoints(feature_id=f2.id)
        assert len(cp1) == 1
        assert len(cp2) == 1
        assert json.loads(cp1[0].state_snapshot)["feature"] == "A"
        assert json.loads(cp2[0].state_snapshot)["feature"] == "B"
