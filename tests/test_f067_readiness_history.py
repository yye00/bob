"""Tests for F067: Implement readiness history tracking.

Validates that:
- Step 1: record_readiness() function exists and creates entries
- Step 2: Stores readiness_score and component scores
- Step 3: Tracks change_reason and rules_applied
- Step 4: Update readiness multiple times, verify history captured
"""

import json
import pathlib

import pytest

from bob import db
from bob.models import ReadinessHistory

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
        name="F067 Test Project",
        workspace_path="/tmp/test-f067",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature."""
    return db.create_feature(
        project_id=project.id,
        name="Test Feature",
        description="A feature for readiness history tests",
    )


# ===================================================================
# Step 1: record_readiness() function exists and creates entries
# ===================================================================


class TestRecordReadinessExists:
    """Step 1: record_readiness() must exist and create readiness_history rows."""

    def test_function_exists(self):
        assert hasattr(db, "record_readiness")
        assert callable(db.record_readiness)

    def test_creates_readiness_entry(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.75,
            computed_by="orchestrator",
        )
        assert isinstance(entry, ReadinessHistory)
        assert entry.project_id == project.id
        assert entry.feature_id == feature.id

    def test_returns_entry_with_id(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.5,
            computed_by="orchestrator",
        )
        assert entry.id is not None
        assert len(entry.id) > 0

    def test_persisted_to_database(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.8,
            computed_by="agent-001",
        )
        retrieved = db.get_readiness_entry(entry.id)
        assert retrieved is not None
        assert retrieved.id == entry.id
        assert retrieved.project_id == project.id
        assert retrieved.feature_id == feature.id

    def test_has_created_at_timestamp(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.6,
            computed_by="orchestrator",
        )
        assert entry.created_at is not None

    def test_computed_by_is_required(self, project, feature):
        """computed_by must be provided - it's a required keyword argument."""
        with pytest.raises(TypeError):
            db.record_readiness(
                project_id=project.id,
                feature_id=feature.id,
                readiness_score=0.5,
            )


# ===================================================================
# Step 2: Stores readiness_score and component scores
# ===================================================================


class TestReadinessScoreAndComponents:
    """Step 2: record_readiness() must store readiness_score and component scores."""

    def test_stores_readiness_score(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.85,
            computed_by="orchestrator",
        )
        assert entry.readiness_score == 0.85

    def test_stores_opus_confidence_component(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.8,
            opus_confidence_component=0.9,
            computed_by="orchestrator",
        )
        assert entry.opus_confidence_component == 0.9

    def test_stores_test_pass_rate_component(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.7,
            test_pass_rate_component=0.95,
            computed_by="orchestrator",
        )
        assert entry.test_pass_rate_component == 0.95

    def test_stores_evidence_score_component(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.75,
            evidence_score_component=0.6,
            computed_by="orchestrator",
        )
        assert entry.evidence_score_component == 0.6

    def test_stores_diff_quality_component(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.8,
            diff_quality_component=0.7,
            computed_by="orchestrator",
        )
        assert entry.diff_quality_component == 0.7

    def test_stores_reviewer_adjustment_component(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.65,
            reviewer_adjustment_component=-0.1,
            computed_by="orchestrator",
        )
        assert entry.reviewer_adjustment_component == -0.1

    def test_all_components_persisted(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.82,
            opus_confidence_component=0.9,
            test_pass_rate_component=0.85,
            evidence_score_component=0.7,
            diff_quality_component=0.8,
            reviewer_adjustment_component=-0.05,
            computed_by="orchestrator",
        )
        retrieved = db.get_readiness_entry(entry.id)
        assert retrieved is not None
        assert retrieved.readiness_score == 0.82
        assert retrieved.opus_confidence_component == 0.9
        assert retrieved.test_pass_rate_component == 0.85
        assert retrieved.evidence_score_component == 0.7
        assert retrieved.diff_quality_component == 0.8
        assert retrieved.reviewer_adjustment_component == -0.05

    def test_components_are_optional(self, project, feature):
        """All component scores should default to None when not provided."""
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.5,
            computed_by="orchestrator",
        )
        assert entry.opus_confidence_component is None
        assert entry.test_pass_rate_component is None
        assert entry.evidence_score_component is None
        assert entry.diff_quality_component is None
        assert entry.reviewer_adjustment_component is None


# ===================================================================
# Step 3: Track change_reason and rules_applied
# ===================================================================


class TestChangeReasonAndRulesApplied:
    """Step 3: record_readiness() must track change_reason and rules_applied."""

    def test_stores_change_reason(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.85,
            change_reason="All tests passing after implementation",
            computed_by="orchestrator",
        )
        assert entry.change_reason == "All tests passing after implementation"

    def test_stores_rules_applied(self, project, feature):
        rules = ["risk_threshold_check", "reviewer_veto_check"]
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.75,
            rules_applied=json.dumps(rules),
            computed_by="orchestrator",
        )
        assert json.loads(entry.rules_applied) == rules

    def test_change_reason_persisted(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.9,
            change_reason="Manual override by reviewer",
            computed_by="human",
        )
        retrieved = db.get_readiness_entry(entry.id)
        assert retrieved is not None
        assert retrieved.change_reason == "Manual override by reviewer"

    def test_rules_applied_persisted(self, project, feature):
        rules = ["confidence_weighted_average", "evidence_quality_gate"]
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.7,
            rules_applied=json.dumps(rules),
            computed_by="orchestrator",
        )
        retrieved = db.get_readiness_entry(entry.id)
        assert retrieved is not None
        assert json.loads(retrieved.rules_applied) == rules

    def test_change_reason_is_optional(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.5,
            computed_by="orchestrator",
        )
        assert entry.change_reason is None

    def test_rules_applied_is_optional(self, project, feature):
        entry = db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.5,
            computed_by="orchestrator",
        )
        assert entry.rules_applied is None


# ===================================================================
# Step 4: Update readiness multiple times, verify history captured
# ===================================================================


class TestReadinessHistoryOverTime:
    """Step 4: Record multiple readiness updates and verify history is maintained."""

    def test_get_readiness_history_function_exists(self):
        assert hasattr(db, "get_readiness_history")
        assert callable(db.get_readiness_history)

    def test_multiple_entries_tracked(self, project, feature):
        """Record readiness at multiple points; all entries preserved."""
        db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.2,
            change_reason="Initial assessment",
            computed_by="orchestrator",
        )
        db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.5,
            change_reason="After spec clarification",
            computed_by="orchestrator",
        )
        db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.85,
            change_reason="After full implementation",
            computed_by="orchestrator",
        )

        history = db.get_readiness_history(feature_id=feature.id)
        assert len(history) == 3

    def test_history_ordered_by_time(self, project, feature):
        """History should be returned in chronological order (oldest first)."""
        db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.1,
            change_reason="First",
            computed_by="orchestrator",
        )
        db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.5,
            change_reason="Second",
            computed_by="orchestrator",
        )
        db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.9,
            change_reason="Third",
            computed_by="orchestrator",
        )

        history = db.get_readiness_history(feature_id=feature.id)
        assert history[0].change_reason == "First"
        assert history[1].change_reason == "Second"
        assert history[2].change_reason == "Third"

    def test_readiness_progression_visible(self, project, feature):
        """Verify that readiness progression can be tracked over time."""
        scores = [0.1, 0.3, 0.6, 0.85, 0.92]
        for score in scores:
            db.record_readiness(
                project_id=project.id,
                feature_id=feature.id,
                readiness_score=score,
                computed_by="orchestrator",
            )

        history = db.get_readiness_history(feature_id=feature.id)
        assert len(history) == 5
        recorded_scores = [h.readiness_score for h in history]
        assert recorded_scores == scores

    def test_history_tracks_different_computed_by(self, project, feature):
        """Multiple computers can contribute to the same feature's readiness history."""
        db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.6,
            computed_by="orchestrator",
            change_reason="Automated assessment",
        )
        db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.8,
            computed_by="human",
            change_reason="Manual review adjustment",
        )

        history = db.get_readiness_history(feature_id=feature.id)
        assert len(history) == 2
        computers = {entry.computed_by for entry in history}
        assert computers == {"orchestrator", "human"}

    def test_history_with_full_component_tracking(self, project, feature):
        """Full component scores should be preserved across multiple entries."""
        db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.3,
            opus_confidence_component=0.4,
            test_pass_rate_component=0.2,
            evidence_score_component=0.1,
            diff_quality_component=0.5,
            change_reason="Initial low readiness",
            rules_applied=json.dumps(["initial_assessment"]),
            computed_by="orchestrator",
        )
        db.record_readiness(
            project_id=project.id,
            feature_id=feature.id,
            readiness_score=0.85,
            opus_confidence_component=0.9,
            test_pass_rate_component=0.95,
            evidence_score_component=0.7,
            diff_quality_component=0.8,
            reviewer_adjustment_component=0.0,
            change_reason="After implementation and tests",
            rules_applied=json.dumps(["confidence_weighted_average", "evidence_gate"]),
            computed_by="orchestrator",
        )

        history = db.get_readiness_history(feature_id=feature.id)
        assert len(history) == 2

        first = history[0]
        assert first.readiness_score == 0.3
        assert first.opus_confidence_component == 0.4
        assert first.test_pass_rate_component == 0.2

        second = history[1]
        assert second.readiness_score == 0.85
        assert second.opus_confidence_component == 0.9
        assert second.test_pass_rate_component == 0.95
        assert second.reviewer_adjustment_component == 0.0

    def test_get_nonexistent_entry_returns_none(self):
        result = db.get_readiness_entry("nonexistent-id")
        assert result is None

    def test_empty_history_returns_empty_list(self, feature):
        history = db.get_readiness_history(feature_id=feature.id)
        assert history == []
