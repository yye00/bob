"""Tests for F066: Implement confidence history tracking.

Validates that:
- Step 1: record_confidence() function exists and creates entries
- Step 2: Stores conf_spec_understanding, conf_impl_correctness, conf_test_adequacy
- Step 3: Tracks rated_by (agent ID or 'human')
- Step 4: Stores rationale
- Step 5: Record confidence updates over time, verify history
"""

import pathlib
import time

import pytest

from bob import db
from bob.models import ConfidenceHistory

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project."""
    return db.create_project(
        name="F066 Test Project",
        workspace_path="/tmp/test-f066",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature."""
    return db.create_feature(
        project_id=project.id,
        name="Test Feature",
        description="A feature for confidence tracking tests",
    )


@pytest.fixture()
def task(project, feature):
    """Create a test task."""
    return db.create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="implementation",
        title="Test Task",
    )


# ===================================================================
# Step 1: record_confidence() function exists and creates entries
# ===================================================================


class TestRecordConfidenceExists:
    """Step 1: record_confidence() must exist and create confidence_history rows."""

    def test_function_exists(self):
        assert hasattr(db, "record_confidence")
        assert callable(db.record_confidence)

    def test_creates_confidence_entry_for_feature(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.8,
            conf_impl_correctness=0.6,
            conf_test_adequacy=0.7,
            rated_by="agent-001",
        )
        assert isinstance(entry, ConfidenceHistory)
        assert entry.project_id == project.id
        assert entry.feature_id == feature.id

    def test_returns_entry_with_id(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.5,
            conf_impl_correctness=0.5,
            conf_test_adequacy=0.5,
            rated_by="agent-001",
        )
        assert entry.id is not None
        assert len(entry.id) > 0

    def test_creates_confidence_entry_for_task(self, project, feature, task):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.75,
            rated_by="agent-002",
        )
        assert entry.task_id == task.id

    def test_persisted_to_database(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.8,
            conf_impl_correctness=0.6,
            conf_test_adequacy=0.7,
            rated_by="human",
        )
        retrieved = db.get_confidence_entry(entry.id)
        assert retrieved is not None
        assert retrieved.id == entry.id
        assert retrieved.project_id == project.id

    def test_has_created_at_timestamp(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.5,
            conf_impl_correctness=0.5,
            conf_test_adequacy=0.5,
            rated_by="agent-001",
        )
        assert entry.created_at is not None


# ===================================================================
# Step 2: Stores conf_spec_understanding, conf_impl_correctness, conf_test_adequacy
# ===================================================================


class TestConfidenceDimensions:
    """Step 2: record_confidence() must store all three confidence dimensions."""

    def test_stores_spec_understanding(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.95,
            conf_impl_correctness=0.0,
            conf_test_adequacy=0.0,
            rated_by="agent-001",
        )
        assert entry.conf_spec_understanding == 0.95

    def test_stores_impl_correctness(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.0,
            conf_impl_correctness=0.88,
            conf_test_adequacy=0.0,
            rated_by="agent-001",
        )
        assert entry.conf_impl_correctness == 0.88

    def test_stores_test_adequacy(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.0,
            conf_impl_correctness=0.0,
            conf_test_adequacy=0.72,
            rated_by="agent-001",
        )
        assert entry.conf_test_adequacy == 0.72

    def test_all_dimensions_persisted(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.70,
            conf_test_adequacy=0.60,
            rated_by="agent-001",
        )
        retrieved = db.get_confidence_entry(entry.id)
        assert retrieved is not None
        assert retrieved.conf_spec_understanding == 0.85
        assert retrieved.conf_impl_correctness == 0.70
        assert retrieved.conf_test_adequacy == 0.60

    def test_dimensions_can_be_none(self, project, feature):
        """Confidence dimensions can be None (e.g., only rating one aspect)."""
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.9,
            rated_by="agent-001",
        )
        assert entry.conf_spec_understanding == 0.9
        assert entry.conf_impl_correctness is None
        assert entry.conf_test_adequacy is None


# ===================================================================
# Step 3: Track rated_by (agent ID or 'human')
# ===================================================================


class TestRatedBy:
    """Step 3: record_confidence() must track who rated the confidence."""

    def test_rated_by_agent(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.8,
            conf_impl_correctness=0.7,
            conf_test_adequacy=0.6,
            rated_by="agent-sub-001",
        )
        assert entry.rated_by == "agent-sub-001"

    def test_rated_by_human(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.8,
            rated_by="human",
        )
        assert entry.rated_by == "human"

    def test_rated_by_persisted(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.5,
            conf_impl_correctness=0.5,
            conf_test_adequacy=0.5,
            rated_by="orchestrator-main",
        )
        retrieved = db.get_confidence_entry(entry.id)
        assert retrieved is not None
        assert retrieved.rated_by == "orchestrator-main"

    def test_rated_by_is_required(self, project, feature):
        """rated_by must be provided - it's a required field."""
        with pytest.raises(TypeError):
            db.record_confidence(
                project_id=project.id,
                feature_id=feature.id,
                conf_spec_understanding=0.5,
            )


# ===================================================================
# Step 4: Store rationale
# ===================================================================


class TestRationale:
    """Step 4: record_confidence() must store the rationale for the rating."""

    def test_stores_rationale(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.7,
            conf_test_adequacy=0.5,
            rated_by="agent-001",
            rationale="Spec is clear, implementation has edge cases, tests cover happy path only",
        )
        assert entry.rationale == "Spec is clear, implementation has edge cases, tests cover happy path only"

    def test_rationale_persisted(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.8,
            conf_impl_correctness=0.8,
            conf_test_adequacy=0.8,
            rated_by="human",
            rationale="All looks good after manual review",
        )
        retrieved = db.get_confidence_entry(entry.id)
        assert retrieved is not None
        assert retrieved.rationale == "All looks good after manual review"

    def test_rationale_is_optional(self, project, feature):
        entry = db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.7,
            conf_impl_correctness=0.7,
            conf_test_adequacy=0.7,
            rated_by="agent-001",
        )
        assert entry.rationale is None


# ===================================================================
# Step 5: Record confidence updates over time, verify history
# ===================================================================


class TestConfidenceHistoryOverTime:
    """Step 5: Record multiple confidence updates and verify history is maintained."""

    def test_get_confidence_history_function_exists(self):
        assert hasattr(db, "get_confidence_history")
        assert callable(db.get_confidence_history)

    def test_multiple_entries_tracked(self, project, feature):
        """Record confidence at multiple points; all entries preserved."""
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.3,
            conf_impl_correctness=0.1,
            conf_test_adequacy=0.0,
            rated_by="agent-001",
            rationale="Initial assessment - spec unclear",
        )
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.7,
            conf_impl_correctness=0.4,
            conf_test_adequacy=0.2,
            rated_by="agent-001",
            rationale="After spec clarification",
        )
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.8,
            conf_test_adequacy=0.7,
            rated_by="agent-001",
            rationale="After implementation and tests",
        )

        history = db.get_confidence_history(feature_id=feature.id)
        assert len(history) == 3

    def test_history_ordered_by_time(self, project, feature):
        """History should be returned in chronological order (oldest first)."""
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.3,
            rated_by="agent-001",
            rationale="First",
        )
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.6,
            rated_by="agent-001",
            rationale="Second",
        )
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.9,
            rated_by="agent-001",
            rationale="Third",
        )

        history = db.get_confidence_history(feature_id=feature.id)
        assert history[0].rationale == "First"
        assert history[1].rationale == "Second"
        assert history[2].rationale == "Third"

    def test_history_by_task(self, project, feature, task):
        """History can be queried for a specific task."""
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            conf_spec_understanding=0.5,
            conf_impl_correctness=0.5,
            conf_test_adequacy=0.5,
            rated_by="agent-001",
        )
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            conf_spec_understanding=0.8,
            conf_impl_correctness=0.7,
            conf_test_adequacy=0.6,
            rated_by="agent-001",
        )
        # Entry for feature only (no task)
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.9,
            rated_by="human",
        )

        task_history = db.get_confidence_history(task_id=task.id)
        assert len(task_history) == 2

        feature_history = db.get_confidence_history(feature_id=feature.id)
        assert len(feature_history) == 3

    def test_history_tracks_different_raters(self, project, feature):
        """Multiple raters can contribute to the same feature's confidence history."""
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.7,
            conf_impl_correctness=0.5,
            conf_test_adequacy=0.4,
            rated_by="agent-builder",
            rationale="Agent assessment after build",
        )
        db.record_confidence(
            project_id=project.id,
            feature_id=feature.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.8,
            rated_by="human",
            rationale="Human reviewer assessment",
        )

        history = db.get_confidence_history(feature_id=feature.id)
        assert len(history) == 2
        raters = {entry.rated_by for entry in history}
        assert raters == {"agent-builder", "human"}

    def test_confidence_progression_visible(self, project, feature):
        """Verify that confidence progression can be tracked over time."""
        scores = [
            (0.2, 0.1, 0.0),
            (0.5, 0.3, 0.2),
            (0.7, 0.6, 0.5),
            (0.9, 0.85, 0.8),
        ]
        for spec, impl, test in scores:
            db.record_confidence(
                project_id=project.id,
                feature_id=feature.id,
                conf_spec_understanding=spec,
                conf_impl_correctness=impl,
                conf_test_adequacy=test,
                rated_by="agent-001",
            )

        history = db.get_confidence_history(feature_id=feature.id)
        assert len(history) == 4

        # Verify ascending confidence over time
        spec_scores = [h.conf_spec_understanding for h in history]
        assert spec_scores == [0.2, 0.5, 0.7, 0.9]

        impl_scores = [h.conf_impl_correctness for h in history]
        assert impl_scores == [0.1, 0.3, 0.6, 0.85]

    def test_get_nonexistent_entry_returns_none(self):
        result = db.get_confidence_entry("nonexistent-id")
        assert result is None

    def test_empty_history_returns_empty_list(self, feature):
        history = db.get_confidence_history(feature_id=feature.id)
        assert history == []
