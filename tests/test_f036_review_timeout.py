"""Tests for F036: Review timeout detection and handling.

Tests check_review_timeouts() function which:
- Queries reviews_pending view for timed-out reviews
- Calculates hours_waiting from review_requested_at
- Compares against review_timeout_hours
- For low/medium risk: auto-approves (timeout_action_taken='auto_approved')
- For high/critical risk: escalates to human (timeout_action_taken='escalated')
"""

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
        with db.connect(db_path=db_path) as conn:
            conn.execute(
                "INSERT INTO projects (id, name, workspace_path) VALUES (?, ?, ?)",
                ("proj-1", "Test Project", "/tmp/ws"),
            )
            # Features with different risk categories
            conn.execute(
                "INSERT INTO features (id, project_id, name, status, risk_category) VALUES (?, ?, ?, ?, ?)",
                ("feat-low", "proj-1", "Low Risk Feature", "ready", "low"),
            )
            conn.execute(
                "INSERT INTO features (id, project_id, name, status, risk_category) VALUES (?, ?, ?, ?, ?)",
                ("feat-med", "proj-1", "Medium Risk Feature", "ready", "medium"),
            )
            conn.execute(
                "INSERT INTO features (id, project_id, name, status, risk_category) VALUES (?, ?, ?, ?, ?)",
                ("feat-high", "proj-1", "High Risk Feature", "ready", "high"),
            )
            conn.execute(
                "INSERT INTO features (id, project_id, name, status, risk_category) VALUES (?, ?, ?, ?, ?)",
                ("feat-crit", "proj-1", "Critical Risk Feature", "ready", "critical"),
            )
        yield db_path


def _create_old_review(db_path, *, review_id, feature_id, hours_ago, timeout_hours=48):
    """Helper: create a review that was requested `hours_ago` hours in the past."""
    past_time = datetime.now() - timedelta(hours=hours_ago)
    with db.connect(db_path=db_path) as conn:
        conn.execute(
            """INSERT INTO review_history
               (id, project_id, feature_id, reviewer_id, reviewer_type,
                review_requested_at, review_timeout_hours, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (review_id, "proj-1", feature_id, "reviewer-1", "human",
             past_time.isoformat(), timeout_hours, past_time.isoformat()),
        )


# ============================================================
# Step 1: check_review_timeouts() function exists
# ============================================================


class TestCheckReviewTimeoutsExists:
    def test_function_exists(self, tmp_db):
        assert hasattr(db, "check_review_timeouts")
        assert callable(db.check_review_timeouts)

    def test_returns_list(self, tmp_db):
        result = db.check_review_timeouts(project_id="proj-1")
        assert isinstance(result, list)

    def test_returns_empty_list_when_no_reviews(self, tmp_db):
        result = db.check_review_timeouts(project_id="proj-1")
        assert result == []


# ============================================================
# Step 2: Query reviews_pending for timed-out reviews
# ============================================================


class TestQueryPendingReviews:
    def test_finds_timed_out_review(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-1", feature_id="feat-low",
                           hours_ago=50, timeout_hours=48)
        result = db.check_review_timeouts(project_id="proj-1")
        assert len(result) >= 1

    def test_ignores_non_timed_out_review(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-fresh", feature_id="feat-low",
                           hours_ago=10, timeout_hours=48)
        result = db.check_review_timeouts(project_id="proj-1")
        assert not any(r.id == "rev-fresh" for r in result)

    def test_ignores_already_resolved_review(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-resolved", feature_id="feat-low",
                           hours_ago=50, timeout_hours=48)
        # Mark as already having a verdict
        with db.connect(db_path=tmp_db) as conn:
            conn.execute(
                "UPDATE review_history SET verdict = 'approve' WHERE id = ?",
                ("rev-resolved",),
            )
        result = db.check_review_timeouts(project_id="proj-1")
        assert not any(r.id == "rev-resolved" for r in result)

    def test_ignores_already_actioned_timeout(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-actioned", feature_id="feat-low",
                           hours_ago=50, timeout_hours=48)
        # Mark as already having timeout action taken
        with db.connect(db_path=tmp_db) as conn:
            conn.execute(
                "UPDATE review_history SET timeout_action_taken = 'auto_approved' WHERE id = ?",
                ("rev-actioned",),
            )
        result = db.check_review_timeouts(project_id="proj-1")
        assert not any(r.id == "rev-actioned" for r in result)


# ============================================================
# Step 3: Calculate hours_waiting from review_requested_at
# ============================================================


class TestHoursWaitingCalculation:
    def test_review_barely_past_timeout_is_detected(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-barely", feature_id="feat-low",
                           hours_ago=49, timeout_hours=48)
        result = db.check_review_timeouts(project_id="proj-1")
        assert any(r.id == "rev-barely" for r in result)

    def test_review_well_before_timeout_not_detected(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-early", feature_id="feat-low",
                           hours_ago=10, timeout_hours=48)
        result = db.check_review_timeouts(project_id="proj-1")
        assert not any(r.id == "rev-early" for r in result)

    def test_custom_timeout_hours_respected(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-custom", feature_id="feat-low",
                           hours_ago=25, timeout_hours=24)
        result = db.check_review_timeouts(project_id="proj-1")
        assert any(r.id == "rev-custom" for r in result)


# ============================================================
# Step 4: Compare against review_timeout_hours
# ============================================================


class TestTimeoutComparison:
    def test_zero_timeout_immediately_detected(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-zero", feature_id="feat-low",
                           hours_ago=1, timeout_hours=0)
        result = db.check_review_timeouts(project_id="proj-1")
        assert any(r.id == "rev-zero" for r in result)

    def test_large_timeout_not_detected(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-large", feature_id="feat-low",
                           hours_ago=100, timeout_hours=9999)
        result = db.check_review_timeouts(project_id="proj-1")
        assert not any(r.id == "rev-large" for r in result)


# ============================================================
# Step 5: Low/medium risk auto-approve
# ============================================================


class TestLowMediumRiskAutoApprove:
    def test_low_risk_auto_approved(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-low", feature_id="feat-low",
                           hours_ago=50, timeout_hours=48)
        result = db.check_review_timeouts(project_id="proj-1")
        processed = [r for r in result if r.id == "rev-low"]
        assert len(processed) == 1
        assert processed[0].timeout_action_taken == "auto_approved"
        assert processed[0].verdict == "approve"

    def test_medium_risk_auto_approved(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-med", feature_id="feat-med",
                           hours_ago=50, timeout_hours=48)
        result = db.check_review_timeouts(project_id="proj-1")
        processed = [r for r in result if r.id == "rev-med"]
        assert len(processed) == 1
        assert processed[0].timeout_action_taken == "auto_approved"
        assert processed[0].verdict == "approve"

    def test_low_risk_verdict_persisted(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-low-p", feature_id="feat-low",
                           hours_ago=50, timeout_hours=48)
        db.check_review_timeouts(project_id="proj-1")
        fetched = db.get_review("rev-low-p")
        assert fetched.verdict == "approve"
        assert fetched.timeout_action_taken == "auto_approved"

    def test_medium_risk_verdict_persisted(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-med-p", feature_id="feat-med",
                           hours_ago=50, timeout_hours=48)
        db.check_review_timeouts(project_id="proj-1")
        fetched = db.get_review("rev-med-p")
        assert fetched.verdict == "approve"
        assert fetched.timeout_action_taken == "auto_approved"


# ============================================================
# Step 6: High/critical risk escalate to human
# ============================================================


class TestHighCriticalRiskEscalate:
    def test_high_risk_escalated(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-high", feature_id="feat-high",
                           hours_ago=50, timeout_hours=48)
        result = db.check_review_timeouts(project_id="proj-1")
        processed = [r for r in result if r.id == "rev-high"]
        assert len(processed) == 1
        assert processed[0].timeout_action_taken == "escalated"

    def test_critical_risk_escalated(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-crit", feature_id="feat-crit",
                           hours_ago=50, timeout_hours=48)
        result = db.check_review_timeouts(project_id="proj-1")
        processed = [r for r in result if r.id == "rev-crit"]
        assert len(processed) == 1
        assert processed[0].timeout_action_taken == "escalated"

    def test_high_risk_feature_status_set_to_needs_human(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-high-s", feature_id="feat-high",
                           hours_ago=50, timeout_hours=48)
        db.check_review_timeouts(project_id="proj-1")
        feature = db.get_feature("feat-high")
        assert feature.status == "needs_human"

    def test_critical_risk_feature_status_set_to_needs_human(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-crit-s", feature_id="feat-crit",
                           hours_ago=50, timeout_hours=48)
        db.check_review_timeouts(project_id="proj-1")
        feature = db.get_feature("feat-crit")
        assert feature.status == "needs_human"

    def test_high_risk_escalation_persisted(self, tmp_db):
        _create_old_review(tmp_db, review_id="rev-high-p", feature_id="feat-high",
                           hours_ago=50, timeout_hours=48)
        db.check_review_timeouts(project_id="proj-1")
        fetched = db.get_review("rev-high-p")
        assert fetched.timeout_action_taken == "escalated"


# ============================================================
# Step 7: Low-risk review, simulate 48+ hour wait, verify auto-approved
# ============================================================


class TestLowRiskIntegration:
    def test_low_risk_full_workflow(self, tmp_db):
        """Create low-risk review, simulate 48+ hour wait, verify auto-approved."""
        _create_old_review(tmp_db, review_id="rev-int-low", feature_id="feat-low",
                           hours_ago=50, timeout_hours=48)

        # Before processing, review should be pending
        review_before = db.get_review("rev-int-low")
        assert review_before.verdict is None
        assert review_before.timeout_action_taken is None

        # Process timeouts
        result = db.check_review_timeouts(project_id="proj-1")

        # Verify the review was auto-approved
        processed = [r for r in result if r.id == "rev-int-low"]
        assert len(processed) == 1
        assert processed[0].verdict == "approve"
        assert processed[0].timeout_action_taken == "auto_approved"

        # Verify database state
        review_after = db.get_review("rev-int-low")
        assert review_after.verdict == "approve"
        assert review_after.timeout_action_taken == "auto_approved"

    def test_medium_risk_full_workflow(self, tmp_db):
        """Create medium-risk review, simulate 48+ hour wait, verify auto-approved."""
        _create_old_review(tmp_db, review_id="rev-int-med", feature_id="feat-med",
                           hours_ago=72, timeout_hours=48)

        result = db.check_review_timeouts(project_id="proj-1")

        processed = [r for r in result if r.id == "rev-int-med"]
        assert len(processed) == 1
        assert processed[0].verdict == "approve"
        assert processed[0].timeout_action_taken == "auto_approved"

        review_after = db.get_review("rev-int-med")
        assert review_after.verdict == "approve"
        assert review_after.timeout_action_taken == "auto_approved"


# ============================================================
# Step 8: Critical-risk review, simulate 48+ hour wait, verify escalated
# ============================================================


class TestCriticalRiskIntegration:
    def test_critical_risk_full_workflow(self, tmp_db):
        """Create critical-risk review, simulate 48+ hour wait, verify escalated."""
        _create_old_review(tmp_db, review_id="rev-int-crit", feature_id="feat-crit",
                           hours_ago=50, timeout_hours=48)

        # Before processing, review should be pending
        review_before = db.get_review("rev-int-crit")
        assert review_before.verdict is None
        assert review_before.timeout_action_taken is None

        # Process timeouts
        result = db.check_review_timeouts(project_id="proj-1")

        # Verify the review was escalated
        processed = [r for r in result if r.id == "rev-int-crit"]
        assert len(processed) == 1
        assert processed[0].timeout_action_taken == "escalated"

        # Verify feature status changed
        feature = db.get_feature("feat-crit")
        assert feature.status == "needs_human"

        # Verify database state
        review_after = db.get_review("rev-int-crit")
        assert review_after.timeout_action_taken == "escalated"

    def test_high_risk_full_workflow(self, tmp_db):
        """Create high-risk review, simulate 48+ hour wait, verify escalated."""
        _create_old_review(tmp_db, review_id="rev-int-high", feature_id="feat-high",
                           hours_ago=50, timeout_hours=48)

        result = db.check_review_timeouts(project_id="proj-1")

        processed = [r for r in result if r.id == "rev-int-high"]
        assert len(processed) == 1
        assert processed[0].timeout_action_taken == "escalated"

        feature = db.get_feature("feat-high")
        assert feature.status == "needs_human"

    def test_mixed_risk_levels_processed_correctly(self, tmp_db):
        """Multiple reviews with different risk levels handled correctly."""
        _create_old_review(tmp_db, review_id="rev-mix-low", feature_id="feat-low",
                           hours_ago=50, timeout_hours=48)
        _create_old_review(tmp_db, review_id="rev-mix-med", feature_id="feat-med",
                           hours_ago=50, timeout_hours=48)
        _create_old_review(tmp_db, review_id="rev-mix-high", feature_id="feat-high",
                           hours_ago=50, timeout_hours=48)
        _create_old_review(tmp_db, review_id="rev-mix-crit", feature_id="feat-crit",
                           hours_ago=50, timeout_hours=48)

        result = db.check_review_timeouts(project_id="proj-1")
        assert len(result) == 4

        result_map = {r.id: r for r in result}

        # Low and medium: auto-approved
        assert result_map["rev-mix-low"].timeout_action_taken == "auto_approved"
        assert result_map["rev-mix-low"].verdict == "approve"
        assert result_map["rev-mix-med"].timeout_action_taken == "auto_approved"
        assert result_map["rev-mix-med"].verdict == "approve"

        # High and critical: escalated
        assert result_map["rev-mix-high"].timeout_action_taken == "escalated"
        assert result_map["rev-mix-crit"].timeout_action_taken == "escalated"

        # Verify feature statuses
        feat_high = db.get_feature("feat-high")
        feat_crit = db.get_feature("feat-crit")
        assert feat_high.status == "needs_human"
        assert feat_crit.status == "needs_human"

    def test_idempotent_no_double_processing(self, tmp_db):
        """Running check_review_timeouts twice does not double-process."""
        _create_old_review(tmp_db, review_id="rev-idem", feature_id="feat-low",
                           hours_ago=50, timeout_hours=48)

        result1 = db.check_review_timeouts(project_id="proj-1")
        assert len(result1) == 1

        result2 = db.check_review_timeouts(project_id="proj-1")
        assert len(result2) == 0  # Already processed
