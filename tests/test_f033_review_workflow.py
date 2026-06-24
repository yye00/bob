"""Tests for F033: Review creation and assignment workflow.

Tests request_review() function, which creates a review_history record
with verdict=NULL, sets review_requested_at timestamp, assigns reviewer_id
and reviewer_type, and starts timeout tracking.
"""

import pathlib
import tempfile
from datetime import datetime

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
                ("feat-1", "proj-1", "Test Feature", "ready"),
            )
            conn.execute(
                "INSERT INTO features (id, project_id, name, status) VALUES (?, ?, ?, ?)",
                ("feat-2", "proj-1", "Another Feature", "executing"),
            )
            conn.execute(
                "INSERT INTO features (id, project_id, name, status) VALUES (?, ?, ?, ?)",
                ("feat-3", "proj-1", "Completed Feature", "completed"),
            )
        yield db_path


# ============================================================
# Step 1: request_review() creates review record
# ============================================================


class TestRequestReviewCreatesRecord:
    def test_returns_review_history_instance(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert isinstance(review, ReviewHistory)

    def test_creates_record_with_required_fields(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert review.project_id == "proj-1"
        assert review.feature_id == "feat-1"
        assert review.reviewer_id == "reviewer-1"
        assert review.id  # Has a generated ID

    def test_persists_to_database(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        fetched = db.get_review(review.id)
        assert fetched is not None
        assert fetched.id == review.id
        assert fetched.project_id == "proj-1"
        assert fetched.feature_id == "feat-1"
        assert fetched.reviewer_id == "reviewer-1"


# ============================================================
# Step 2: verdict is NULL on creation
# ============================================================


class TestVerdictIsNull:
    def test_verdict_is_none_on_creation(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert review.verdict is None

    def test_verdict_null_in_database(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        fetched = db.get_review(review.id)
        assert fetched.verdict is None

    def test_appears_in_pending_reviews(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        pending = db.get_pending_reviews(project_id="proj-1")
        assert len(pending) >= 1
        assert any(r.id == review.id for r in pending)


# ============================================================
# Step 3: review_requested_at timestamp is set
# ============================================================


class TestReviewRequestedAtTimestamp:
    def test_review_requested_at_is_set(self, tmp_db):
        before = datetime.now()
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        after = datetime.now()
        assert review.review_requested_at is not None
        assert before <= review.review_requested_at <= after

    def test_review_requested_at_persisted(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        fetched = db.get_review(review.id)
        assert fetched.review_requested_at is not None
        assert abs((fetched.review_requested_at - review.review_requested_at).total_seconds()) < 1


# ============================================================
# Step 4: Assign reviewer_id and reviewer_type
# ============================================================


class TestReviewerAssignment:
    def test_assigns_reviewer_id(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="human-reviewer-42",
        )
        assert review.reviewer_id == "human-reviewer-42"

    def test_default_reviewer_type_is_human(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert review.reviewer_type == "human"

    def test_assigns_automated_reviewer_type(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="bot-1",
            reviewer_type="automated",
        )
        assert review.reviewer_type == "automated"

    def test_assigns_reviewer_seniority(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior-dev",
            reviewer_seniority=5,
        )
        assert review.reviewer_seniority == 5

    def test_reviewer_fields_persisted(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="bot-2",
            reviewer_type="automated",
            reviewer_seniority=3,
        )
        fetched = db.get_review(review.id)
        assert fetched.reviewer_id == "bot-2"
        assert fetched.reviewer_type == "automated"
        assert fetched.reviewer_seniority == 3


# ============================================================
# Step 5: Request review for feature, verify record created
# ============================================================


class TestRequestReviewIntegration:
    def test_full_review_request_workflow(self, tmp_db):
        """End-to-end: request a review and verify the full record."""
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            reviewer_type="human",
            reviewer_seniority=2,
            review_timeout_hours=24,
            notes="Please check error handling",
        )

        # Verify returned model
        assert isinstance(review, ReviewHistory)
        assert review.verdict is None
        assert review.veto_active is False
        assert review.review_timeout_hours == 24
        assert review.notes == "Please check error handling"

        # Verify database persistence
        fetched = db.get_review(review.id)
        assert fetched is not None
        assert fetched.verdict is None
        assert fetched.reviewer_id == "reviewer-1"
        assert fetched.review_timeout_hours == 24

        # Verify it appears in pending reviews
        pending = db.get_pending_reviews(project_id="proj-1")
        assert any(r.id == review.id for r in pending)

    def test_multiple_reviewers_for_same_feature(self, tmp_db):
        """Multiple reviewers can be assigned to the same feature."""
        r1 = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        r2 = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-2",
            reviewer_type="automated",
        )
        assert r1.id != r2.id
        pending = db.get_pending_reviews(project_id="proj-1", feature_id="feat-1")
        assert len(pending) == 2

    def test_review_for_different_features(self, tmp_db):
        """Reviews can be requested for different features independently."""
        r1 = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        r2 = db.request_review(
            project_id="proj-1",
            feature_id="feat-2",
            reviewer_id="reviewer-1",
        )
        assert r1.feature_id == "feat-1"
        assert r2.feature_id == "feat-2"

    def test_raises_on_nonexistent_feature(self, tmp_db):
        """Requesting review for nonexistent feature raises ValueError."""
        with pytest.raises(ValueError, match="Feature .* not found"):
            db.request_review(
                project_id="proj-1",
                feature_id="nonexistent-feat",
                reviewer_id="reviewer-1",
            )

    def test_raises_on_nonexistent_project(self, tmp_db):
        """Requesting review for nonexistent project raises ValueError."""
        with pytest.raises(ValueError, match="Project .* not found"):
            db.request_review(
                project_id="nonexistent-proj",
                feature_id="feat-1",
                reviewer_id="reviewer-1",
            )

    def test_custom_review_id(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_id="custom-id-123",
        )
        assert review.id == "custom-id-123"


# ============================================================
# Step 6: Verify timeout tracking starts
# ============================================================


class TestTimeoutTrackingStarts:
    def test_default_timeout_hours_is_48(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
        )
        assert review.review_timeout_hours == 48

    def test_custom_timeout_hours(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_timeout_hours=72,
        )
        assert review.review_timeout_hours == 72

    def test_zero_timeout_immediately_detectable(self, tmp_db):
        """A review with 0 timeout should immediately appear as timed out."""
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_timeout_hours=0,
        )
        timed_out = db.get_timed_out_reviews(project_id="proj-1")
        assert any(r.id == review.id for r in timed_out)

    def test_long_timeout_not_timed_out(self, tmp_db):
        """A review with a long timeout should not appear in timed out list."""
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_timeout_hours=9999,
        )
        timed_out = db.get_timed_out_reviews(project_id="proj-1")
        assert not any(r.id == review.id for r in timed_out)

    def test_timeout_fields_persisted(self, tmp_db):
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            review_timeout_hours=36,
        )
        fetched = db.get_review(review.id)
        assert fetched.review_timeout_hours == 36
        assert fetched.review_requested_at is not None
        assert fetched.timeout_action_taken is None  # Not yet timed out
