"""Tests for F034: Review verdict recording (approve/request_changes/block).

Tests record_verdict() function which records a reviewer's verdict on a
review, updates the verdict field, handles veto_active for blocks, and
updates the associated feature's status based on the verdict.
"""

import json
import pathlib
import tempfile

import pytest

from bob import db
from bob.models import ReviewHistory


@pytest.fixture()
def tmp_db(monkeypatch):
    """Create a temporary database for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test.db"
        monkeypatch.setattr(db, "get_database_path", lambda: db_path)
        db.init_database(db_path=db_path)
        with db.connect(db_path=db_path) as conn:
            conn.execute(
                "INSERT INTO projects (id, name, workspace_path) VALUES (?, ?, ?)",
                ("proj-1", "Test Project", "/tmp/ws"),
            )
            conn.execute(
                "INSERT INTO features (id, project_id, name, status) VALUES (?, ?, ?, ?)",
                ("feat-1", "proj-1", "Test Feature", "executing"),
            )
            conn.execute(
                "INSERT INTO features (id, project_id, name, status) VALUES (?, ?, ?, ?)",
                ("feat-2", "proj-1", "Another Feature", "executing"),
            )
        yield db_path


# ============================================================
# Step 1: Add record_verdict() function
# ============================================================


class TestRecordVerdictExists:
    def test_record_verdict_is_callable(self, tmp_db):
        assert callable(db.record_verdict)

    def test_returns_review_history(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        result = db.record_verdict(review.id, verdict="approve")
        assert isinstance(result, ReviewHistory)

    def test_returns_none_for_nonexistent_review(self, tmp_db):
        result = db.record_verdict("nonexistent-review", verdict="approve")
        assert result is None


# ============================================================
# Step 2: Update verdict field (approve|request_changes|block)
# ============================================================


class TestVerdictFieldUpdate:
    def test_sets_approve_verdict(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        result = db.record_verdict(review.id, verdict="approve")
        assert result.verdict == "approve"

    def test_sets_request_changes_verdict(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        result = db.record_verdict(review.id, verdict="request_changes")
        assert result.verdict == "request_changes"

    def test_sets_block_verdict(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        result = db.record_verdict(review.id, verdict="block")
        assert result.verdict == "block"

    def test_verdict_persisted_in_database(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        db.record_verdict(review.id, verdict="approve")
        fetched = db.get_review(review.id)
        assert fetched.verdict == "approve"

    def test_rejects_invalid_verdict(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        with pytest.raises(ValueError, match="[Ii]nvalid verdict"):
            db.record_verdict(review.id, verdict="maybe")

    def test_passes_optional_fields(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        issues = json.dumps(["Missing tests", "Incomplete docs"])
        result = db.record_verdict(
            review.id,
            verdict="request_changes",
            issues_flagged=issues,
            confidence_cap=0.6,
        )
        assert result.issues_flagged == issues
        assert result.confidence_cap == 0.6


# ============================================================
# Step 3: Handle veto_active flag for blocks
# ============================================================


class TestVetoActiveForBlocks:
    def test_block_sets_veto_active_true(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        result = db.record_verdict(review.id, verdict="block")
        assert result.veto_active is True

    def test_approve_does_not_set_veto_active(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        result = db.record_verdict(review.id, verdict="approve")
        assert result.veto_active is False

    def test_request_changes_does_not_set_veto_active(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        result = db.record_verdict(review.id, verdict="request_changes")
        assert result.veto_active is False

    def test_veto_active_persisted_in_database(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        db.record_verdict(review.id, verdict="block")
        fetched = db.get_review(review.id)
        assert fetched.veto_active is True


# ============================================================
# Step 4: Update feature status based on verdict
# ============================================================


class TestFeatureStatusUpdate:
    def test_approve_sets_feature_ready(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        db.record_verdict(review.id, verdict="approve")
        feature = db.get_feature("feat-1")
        assert feature.status == "ready"

    def test_block_sets_feature_blocked_by_reviewer(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        db.record_verdict(review.id, verdict="block")
        feature = db.get_feature("feat-1")
        assert feature.status == "blocked_by_reviewer"

    def test_request_changes_sets_feature_refining(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        db.record_verdict(review.id, verdict="request_changes")
        feature = db.get_feature("feat-1")
        assert feature.status == "refining"

    def test_feature_status_persisted_in_database(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        db.record_verdict(review.id, verdict="approve")
        feature = db.get_feature("feat-1")
        assert feature.status == "ready"


# ============================================================
# Step 5: Test: Approve review, verify feature moves to ready
# ============================================================


class TestApproveReviewFeatureReady:
    def test_full_approve_workflow(self, tmp_db):
        """End-to-end: create review, approve it, feature becomes ready."""
        # Feature starts as 'executing'
        feature = db.get_feature("feat-1")
        assert feature.status == "executing"

        # Create and approve review
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior-dev",
            reviewer_seniority=5,
        )
        assert review.verdict is None

        result = db.record_verdict(review.id, verdict="approve")
        assert result.verdict == "approve"
        assert result.veto_active is False

        # Feature should now be 'ready'
        feature = db.get_feature("feat-1")
        assert feature.status == "ready"

        # Review should no longer be pending
        pending = db.get_pending_reviews(project_id="proj-1", feature_id="feat-1")
        assert not any(r.id == review.id for r in pending)

    def test_approve_with_confidence_cap(self, tmp_db):
        """Approve with a confidence cap still moves feature to ready."""
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        result = db.record_verdict(
            review.id, verdict="approve", confidence_cap=0.85
        )
        assert result.verdict == "approve"
        assert result.confidence_cap == 0.85
        feature = db.get_feature("feat-1")
        assert feature.status == "ready"

    def test_approve_updates_reviewer_confidence_cap_on_feature(self, tmp_db):
        """Approving with confidence_cap updates the feature's reviewer_confidence_cap."""
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        db.record_verdict(review.id, verdict="approve", confidence_cap=0.75)
        feature = db.get_feature("feat-1")
        assert feature.reviewer_confidence_cap == 0.75


# ============================================================
# Step 6: Test: Block review, verify veto_active=TRUE
# ============================================================


class TestBlockReviewVetoActive:
    def test_full_block_workflow(self, tmp_db):
        """End-to-end: create review, block it, veto becomes active."""
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="security-reviewer",
            reviewer_seniority=7,
        )
        issues = json.dumps(["Critical security vulnerability"])
        result = db.record_verdict(
            review.id,
            verdict="block",
            issues_flagged=issues,
        )
        assert result.verdict == "block"
        assert result.veto_active is True

        # Feature should be blocked
        feature = db.get_feature("feat-1")
        assert feature.status == "blocked_by_reviewer"

        # Verify the veto is persisted
        fetched = db.get_review(review.id)
        assert fetched.veto_active is True

    def test_block_with_confidence_cap(self, tmp_db):
        """Block with a confidence cap sets both veto and cap."""
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        result = db.record_verdict(
            review.id, verdict="block", confidence_cap=0.2
        )
        assert result.veto_active is True
        assert result.confidence_cap == 0.2

    def test_multiple_reviews_block_overrides(self, tmp_db):
        """If one reviewer blocks, feature is blocked even if another approved."""
        r1 = db.create_review(
            project_id="proj-1",
            feature_id="feat-2",
            reviewer_id="reviewer-1",
            review_id="r1",
        )
        r2 = db.create_review(
            project_id="proj-1",
            feature_id="feat-2",
            reviewer_id="reviewer-2",
            review_id="r2",
        )
        # First reviewer approves
        db.record_verdict("r1", verdict="approve")
        feature = db.get_feature("feat-2")
        assert feature.status == "ready"

        # Second reviewer blocks - should override
        db.record_verdict("r2", verdict="block")
        feature = db.get_feature("feat-2")
        assert feature.status == "blocked_by_reviewer"
