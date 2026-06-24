"""Tests for F037: Reviewer seniority and senior_wins conflict resolution.

Tests that reviewer_seniority is stored on review records, that
get_feature_reviews() retrieves all reviews for a feature, and that
resolve_conflicting_reviews() applies the senior_wins policy where
the highest-seniority reviewer's verdict wins.
"""

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
# Step 1: Add reviewer_seniority field to review records
# ============================================================


class TestReviewerSeniorityField:
    def test_seniority_stored_on_creation(self, tmp_db):
        """reviewer_seniority is stored when creating a review."""
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior-dev",
            reviewer_seniority=5,
        )
        assert review.reviewer_seniority == 5

    def test_seniority_persisted_in_database(self, tmp_db):
        """reviewer_seniority is persisted and retrievable from the database."""
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior-dev",
            reviewer_seniority=8,
        )
        fetched = db.get_review(review.id)
        assert fetched.reviewer_seniority == 8

    def test_default_seniority_is_zero(self, tmp_db):
        """Default reviewer_seniority is 0."""
        review = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="junior-dev",
        )
        assert review.reviewer_seniority == 0

    def test_seniority_via_request_review(self, tmp_db):
        """reviewer_seniority is passed through request_review()."""
        review = db.request_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="lead-dev",
            reviewer_seniority=7,
        )
        assert review.reviewer_seniority == 7
        fetched = db.get_review(review.id)
        assert fetched.reviewer_seniority == 7


# ============================================================
# Step 2: Implement senior_wins conflict resolution
# ============================================================


class TestSeniorWinsFunction:
    def test_resolve_conflicting_reviews_exists(self, tmp_db):
        """resolve_conflicting_reviews is callable."""
        assert callable(db.resolve_conflicting_reviews)

    def test_returns_winning_review(self, tmp_db):
        """Returns the ReviewHistory of the winning (highest seniority) review."""
        r1 = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="junior",
            reviewer_seniority=1,
            review_id="r1",
        )
        db.record_verdict("r1", verdict="request_changes")

        r2 = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior",
            reviewer_seniority=5,
            review_id="r2",
        )
        db.record_verdict("r2", verdict="approve")

        winner = db.resolve_conflicting_reviews(feature_id="feat-1")
        assert isinstance(winner, ReviewHistory)
        assert winner.id == "r2"
        assert winner.verdict == "approve"

    def test_returns_none_when_no_reviews(self, tmp_db):
        """Returns None when no reviews exist for the feature."""
        result = db.resolve_conflicting_reviews(feature_id="feat-1")
        assert result is None

    def test_returns_none_when_no_verdicts(self, tmp_db):
        """Returns None when reviews exist but none have verdicts."""
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-1",
            reviewer_seniority=3,
        )
        result = db.resolve_conflicting_reviews(feature_id="feat-1")
        assert result is None


# ============================================================
# Step 3: When multiple reviews exist, highest seniority wins
# ============================================================


class TestHighestSeniorityWins:
    def test_highest_seniority_verdict_applied(self, tmp_db):
        """The verdict from the highest-seniority reviewer is applied."""
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="junior",
            reviewer_seniority=1,
            review_id="r-junior",
        )
        db.record_verdict("r-junior", verdict="approve")

        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior",
            reviewer_seniority=5,
            review_id="r-senior",
        )
        db.record_verdict("r-senior", verdict="block")

        winner = db.resolve_conflicting_reviews(feature_id="feat-1")
        assert winner.reviewer_seniority == 5
        assert winner.verdict == "block"

    def test_three_reviewers_highest_wins(self, tmp_db):
        """With three reviewers, the one with highest seniority wins."""
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="junior",
            reviewer_seniority=1,
            review_id="r1",
        )
        db.record_verdict("r1", verdict="approve")

        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="mid",
            reviewer_seniority=3,
            review_id="r2",
        )
        db.record_verdict("r2", verdict="request_changes")

        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior",
            reviewer_seniority=7,
            review_id="r3",
        )
        db.record_verdict("r3", verdict="approve")

        winner = db.resolve_conflicting_reviews(feature_id="feat-1")
        assert winner.reviewer_seniority == 7
        assert winner.verdict == "approve"

    def test_feature_status_updated_to_winner_verdict(self, tmp_db):
        """Feature status is updated to match the winning reviewer's verdict."""
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="junior",
            reviewer_seniority=1,
            review_id="r-junior",
        )
        db.record_verdict("r-junior", verdict="approve")

        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior",
            reviewer_seniority=5,
            review_id="r-senior",
        )
        db.record_verdict("r-senior", verdict="request_changes")

        db.resolve_conflicting_reviews(feature_id="feat-1")
        feature = db.get_feature("feat-1")
        assert feature.status == "refining"

    def test_ignores_reviews_without_verdict(self, tmp_db):
        """Reviews without a verdict are ignored in conflict resolution."""
        # Pending review (no verdict) with high seniority
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="pending-senior",
            reviewer_seniority=10,
            review_id="r-pending",
        )
        # Completed review with lower seniority
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="decided-junior",
            reviewer_seniority=2,
            review_id="r-decided",
        )
        db.record_verdict("r-decided", verdict="approve")

        winner = db.resolve_conflicting_reviews(feature_id="feat-1")
        assert winner.id == "r-decided"
        assert winner.verdict == "approve"

    def test_equal_seniority_latest_wins(self, tmp_db):
        """When seniority is tied, the most recently created review wins."""
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-a",
            reviewer_seniority=5,
            review_id="r-a",
        )
        db.record_verdict("r-a", verdict="approve")

        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="reviewer-b",
            reviewer_seniority=5,
            review_id="r-b",
        )
        db.record_verdict("r-b", verdict="block")

        winner = db.resolve_conflicting_reviews(feature_id="feat-1")
        # Both seniority=5, so most recently created wins
        assert winner.id == "r-b"
        assert winner.verdict == "block"


# ============================================================
# Step 4: Test: Create two reviews (seniority 1 and 5) with different verdicts
# Step 5: Verify seniority 5 verdict is applied
# ============================================================


class TestSeniorityConflictEndToEnd:
    def test_seniority_5_beats_seniority_1(self, tmp_db):
        """Create two reviews (seniority 1 and 5), verify seniority 5 wins."""
        # Junior reviewer (seniority 1) blocks
        r1 = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="junior-dev",
            reviewer_seniority=1,
            review_id="review-junior",
        )
        db.record_verdict("review-junior", verdict="block")

        # Senior reviewer (seniority 5) approves
        r2 = db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior-dev",
            reviewer_seniority=5,
            review_id="review-senior",
        )
        db.record_verdict("review-senior", verdict="approve")

        # Resolve conflict using senior_wins policy
        winner = db.resolve_conflicting_reviews(feature_id="feat-1")

        # Seniority 5 verdict should win
        assert winner.id == "review-senior"
        assert winner.reviewer_seniority == 5
        assert winner.verdict == "approve"

        # Feature status should reflect the winning verdict
        feature = db.get_feature("feat-1")
        assert feature.status == "ready"

    def test_seniority_5_request_changes_beats_seniority_1_approve(self, tmp_db):
        """Seniority 5 request_changes beats seniority 1 approve."""
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="junior-dev",
            reviewer_seniority=1,
            review_id="review-junior",
        )
        db.record_verdict("review-junior", verdict="approve")

        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="senior-dev",
            reviewer_seniority=5,
            review_id="review-senior",
        )
        db.record_verdict("review-senior", verdict="request_changes")

        winner = db.resolve_conflicting_reviews(feature_id="feat-1")

        assert winner.reviewer_seniority == 5
        assert winner.verdict == "request_changes"

        feature = db.get_feature("feat-1")
        assert feature.status == "refining"

    def test_single_review_returns_it(self, tmp_db):
        """With only one review, that review is the winner."""
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="only-reviewer",
            reviewer_seniority=3,
            review_id="only-review",
        )
        db.record_verdict("only-review", verdict="approve")

        winner = db.resolve_conflicting_reviews(feature_id="feat-1")
        assert winner.id == "only-review"
        assert winner.verdict == "approve"

    def test_get_feature_reviews_returns_all(self, tmp_db):
        """get_feature_reviews returns all reviews for a given feature."""
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="r1",
            reviewer_seniority=1,
            review_id="rev-1",
        )
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="r2",
            reviewer_seniority=5,
            review_id="rev-2",
        )
        # Different feature - should not appear
        db.create_review(
            project_id="proj-1",
            feature_id="feat-2",
            reviewer_id="r3",
            reviewer_seniority=3,
            review_id="rev-3",
        )

        reviews = db.get_feature_reviews(feature_id="feat-1")
        assert len(reviews) == 2
        ids = {r.id for r in reviews}
        assert ids == {"rev-1", "rev-2"}

    def test_block_verdict_veto_cleared_on_senior_approve(self, tmp_db):
        """When senior_wins resolves a conflict and the winner approves,
        veto_active should be cleared on the feature (it becomes ready)."""
        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="blocker",
            reviewer_seniority=2,
            review_id="r-block",
        )
        db.record_verdict("r-block", verdict="block")

        # Feature is now blocked
        feature = db.get_feature("feat-1")
        assert feature.status == "blocked_by_reviewer"

        db.create_review(
            project_id="proj-1",
            feature_id="feat-1",
            reviewer_id="approver",
            reviewer_seniority=8,
            review_id="r-approve",
        )
        db.record_verdict("r-approve", verdict="approve")

        # Resolve conflict - senior approver should win
        winner = db.resolve_conflicting_reviews(feature_id="feat-1")
        assert winner.verdict == "approve"

        feature = db.get_feature("feat-1")
        assert feature.status == "ready"
