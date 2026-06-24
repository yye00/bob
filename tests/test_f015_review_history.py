"""Tests for F015: Database operations for review_history table.

Tests create_review(), get_review(), update_review_verdict(),
get_pending_reviews(), review lifecycle, and timeout tracking.
"""

import json
import pathlib
import tempfile
from datetime import datetime, timedelta

import pytest

from bob3 import db
from bob3.models import ReviewHistory


@pytest.fixture()
def tmp_db(monkeypatch):
    """Create a temporary database for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test.db"
        monkeypatch.setattr(db, "get_database_path", lambda: db_path)
        db.init_database(db_path=db_path)
        # Seed a project and feature for FK constraints
        with db.connect(db_path=db_path) as conn:
            conn.execute(
                "INSERT INTO projects (id, name, workspace_path) VALUES (?, ?, ?)",
                ("proj-1", "Test Project", "/tmp/ws"),
            )
            conn.execute(
                "INSERT INTO features (id, project_id, name) VALUES (?, ?, ?)",
                ("feat-1", "proj-1", "Test Feature"),
            )
            conn.execute(
                "INSERT INTO features (id, project_id, name) VALUES (?, ?, ?)",
                ("feat-2", "proj-1", "Another Feature"),
            )
        yield db_path


# ============================================================
# Step 1: create_review()
# ============================================================


class TestCreateReview:
    def test_creates_review_with_required_fields(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert isinstance(review, ReviewHistory)
        assert review.project_id == "proj-1"
        assert review.feature_id == "feat-1"
        assert review.reviewer_id == "reviewer-1"
        assert review.id  # Has a generated ID

    def test_creates_review_with_all_fields(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            reviewer_type="automated",
            reviewer_seniority=3,
            confidence_cap=0.85,
            notes="Initial review",
            review_timeout_hours=24,
        )
        assert review.reviewer_type == "automated"
        assert review.reviewer_seniority == 3
        assert review.confidence_cap == 0.85
        assert review.notes == "Initial review"
        assert review.review_timeout_hours == 24

    def test_creates_review_with_custom_id(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_id="custom-review-id",
        )
        assert review.id == "custom-review-id"

    def test_default_verdict_is_none(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert review.verdict is None

    def test_default_reviewer_type_is_human(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert review.reviewer_type == "human"

    def test_default_veto_active_is_false(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert review.veto_active is False

    def test_default_timeout_hours_is_48(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert review.review_timeout_hours == 48

    def test_created_at_is_set(self, tmp_db):
        before = datetime.now()
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        after = datetime.now()
        assert before <= review.created_at <= after

    def test_persists_to_database(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        fetched = db.get_review(review.id)
        assert fetched is not None
        assert fetched.id == review.id
        assert fetched.project_id == "proj-1"


# ============================================================
# Step 2: get_review()
# ============================================================


class TestGetReview:
    def test_returns_review_by_id(self, tmp_db):
        created = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_id="rev-get-1",
        )
        fetched = db.get_review("rev-get-1")
        assert fetched is not None
        assert fetched.id == "rev-get-1"
        assert fetched.reviewer_id == "reviewer-1"

    def test_returns_none_for_nonexistent(self, tmp_db):
        result = db.get_review("nonexistent-id")
        assert result is None

    def test_returns_all_fields(self, tmp_db):
        issues = json.dumps(["Issue 1", "Issue 2"])
        validations = json.dumps(["Check A"])
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_id="rev-full",
            reviewer_type="automated",
            reviewer_seniority=5,
            confidence_cap=0.9,
            notes="Detailed notes",
            review_timeout_hours=72,
        )
        fetched = db.get_review("rev-full")
        assert fetched.reviewer_type == "automated"
        assert fetched.reviewer_seniority == 5
        assert fetched.confidence_cap == 0.9
        assert fetched.notes == "Detailed notes"
        assert fetched.review_timeout_hours == 72


# ============================================================
# Step 3: update_review_verdict()
# ============================================================


class TestUpdateReviewVerdict:
    def test_sets_verdict_approve(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        updated = db.update_review_verdict(review.id, verdict="approve")
        assert updated is not None
        assert updated.verdict == "approve"

    def test_sets_verdict_request_changes(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        updated = db.update_review_verdict(review.id, verdict="request_changes")
        assert updated is not None
        assert updated.verdict == "request_changes"

    def test_sets_verdict_block(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        updated = db.update_review_verdict(review.id, verdict="block")
        assert updated is not None
        assert updated.verdict == "block"

    def test_sets_veto_active(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        updated = db.update_review_verdict(
            review.id, verdict="block", veto_active=True
        )
        assert updated.veto_active is True

    def test_sets_issues_flagged(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        issues = json.dumps(["Missing error handling", "No tests"])
        updated = db.update_review_verdict(
            review.id, verdict="request_changes", issues_flagged=issues
        )
        assert updated.issues_flagged == issues

    def test_sets_confidence_cap(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        updated = db.update_review_verdict(
            review.id, verdict="approve", confidence_cap=0.75
        )
        assert updated.confidence_cap == 0.75

    def test_returns_none_for_nonexistent(self, tmp_db):
        result = db.update_review_verdict("nonexistent", verdict="approve")
        assert result is None

    def test_persists_verdict(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        db.update_review_verdict(review.id, verdict="approve")
        fetched = db.get_review(review.id)
        assert fetched.verdict == "approve"


# ============================================================
# Step 4: get_pending_reviews()
# ============================================================


class TestGetPendingReviews:
    def test_returns_reviews_with_null_verdict(self, tmp_db):
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_id="pending-1",
        )
        db.create_review(
            project_id="proj-1",
            feature_id="feat-2",
            reviewer_id="reviewer-2",
            review_id="pending-2",
        )
        pending = db.get_pending_reviews(project_id="proj-1")
        assert len(pending) == 2

    def test_excludes_reviews_with_verdict(self, tmp_db):
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_id="decided-1",
        )
        db.update_review_verdict("decided-1", verdict="approve")
        db.create_review(
            project_id="proj-1",
            feature_id="feat-2",
            reviewer_id="reviewer-2",
            review_id="still-pending",
        )
        pending = db.get_pending_reviews(project_id="proj-1")
        assert len(pending) == 1
        assert pending[0].id == "still-pending"

    def test_returns_empty_list_when_none_pending(self, tmp_db):
        pending = db.get_pending_reviews(project_id="proj-1")
        assert pending == []

    def test_filters_by_project_id(self, tmp_db):
        # Create a second project
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, workspace_path) VALUES (?, ?, ?)",
                ("proj-2", "Other Project", "/tmp/ws2"),
            )
            conn.execute(
                "INSERT INTO features (id, project_id, name) VALUES (?, ?, ?)",
                ("feat-3", "proj-2", "Other Feature"),
            )
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        db.create_review(
            project_id="proj-2",
            feature_id="feat-3",
            reviewer_id="reviewer-2",
        )
        pending = db.get_pending_reviews(project_id="proj-1")
        assert len(pending) == 1
        assert pending[0].project_id == "proj-1"

    def test_filters_by_feature_id(self, tmp_db):
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        db.create_review(
            project_id="proj-1",
            feature_id="feat-2",
            reviewer_id="reviewer-2",
        )
        pending = db.get_pending_reviews(project_id="proj-1", feature_id="feat-1")
        assert len(pending) == 1
        assert pending[0].feature_id == "feat-1"


# ============================================================
# Step 5: Review lifecycle (create, update verdict)
# ============================================================


class TestReviewLifecycle:
    def test_create_then_approve(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert review.verdict is None

        updated = db.update_review_verdict(review.id, verdict="approve")
        assert updated.verdict == "approve"

        # Should no longer be in pending list
        pending = db.get_pending_reviews(project_id="proj-1")
        assert len(pending) == 0

    def test_create_then_block_with_issues(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior-reviewer",
            reviewer_seniority=5,
        )
        issues = json.dumps(["Critical security flaw", "Missing input validation"])
        updated = db.update_review_verdict(
            review.id,
            verdict="block",
            veto_active=True,
            issues_flagged=issues,
            confidence_cap=0.3,
        )
        assert updated.verdict == "block"
        assert updated.veto_active is True
        assert updated.issues_flagged == issues
        assert updated.confidence_cap == 0.3

    def test_multiple_reviews_for_same_feature(self, tmp_db):
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_id="rev-1",
        )
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-2",
            review_id="rev-2",
        )
        # Both pending
        pending = db.get_pending_reviews(project_id="proj-1")
        assert len(pending) == 2

        # Approve one
        db.update_review_verdict("rev-1", verdict="approve")
        pending = db.get_pending_reviews(project_id="proj-1")
        assert len(pending) == 1
        assert pending[0].id == "rev-2"


# ============================================================
# Step 6: Timeout tracking
# ============================================================


class TestTimeoutTracking:
    def test_review_requested_at_is_set(self, tmp_db):
        before = datetime.now()
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        after = datetime.now()
        assert before <= review.review_requested_at <= after

    def test_timeout_hours_custom_value(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_timeout_hours=24,
        )
        assert review.review_timeout_hours == 24

    def test_get_timed_out_reviews(self, tmp_db):
        """Reviews past their timeout should be findable via get_timed_out_reviews."""
        # Create a review with a very short timeout
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_id="timeout-rev",
            review_timeout_hours=0,  # Zero hour timeout = immediately timed out
        )
        timed_out = db.get_timed_out_reviews(project_id="proj-1")
        assert len(timed_out) >= 1
        assert any(r.id == "timeout-rev" for r in timed_out)

    def test_non_timed_out_reviews_excluded(self, tmp_db):
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_timeout_hours=9999,  # Very long timeout
        )
        timed_out = db.get_timed_out_reviews(project_id="proj-1")
        assert len(timed_out) == 0

    def test_reviews_with_verdict_excluded_from_timeout(self, tmp_db):
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_timeout_hours=0,
        )
        db.update_review_verdict(review.id, verdict="approve")
        timed_out = db.get_timed_out_reviews(project_id="proj-1")
        assert len(timed_out) == 0

    def test_update_timeout_action(self, tmp_db):
        """Can update the timeout_action_taken field via update_review_verdict."""
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_timeout_hours=0,
        )
        updated = db.update_review_verdict(
            review.id,
            verdict="approve",
            timeout_action_taken="auto_approved_after_timeout",
        )
        assert updated.timeout_action_taken == "auto_approved_after_timeout"
