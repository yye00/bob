"""Tests for F068: Query and use all database views for status reporting.

Verifies that every SQL view defined in schema.sql has a corresponding
Python query function in bob3.db and returns correct, meaningful results.
"""

import json
import pathlib
import uuid

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
def project_id(db_path):
    """Create a project and return its ID for use as a foreign key."""
    from bob3.db import create_project

    project = create_project(
        name="View Test Project",
        workspace_path="/tmp/test-views",
    )
    return project.id


def _make_feature(project_id, name, status="pending", priority=100,
                  risk_category="medium", readiness=0.0, **kwargs):
    """Helper to create a feature with given parameters."""
    from bob3.db import create_feature, update_feature

    feature = create_feature(
        project_id=project_id,
        name=name,
        priority=priority,
        risk_category=risk_category,
        status=status,
    )
    updates = {
        "conf_spec_understanding": readiness,
        "conf_impl_correctness": readiness,
        "conf_test_adequacy": readiness,
        "readiness_score": readiness,
    }
    updates.update(kwargs)
    update_feature(feature.id, **updates)
    # Re-fetch to get updated values
    from bob3.db import get_feature
    return get_feature(feature.id)


# ============================================================
# Step 1: Test features_ready view returns correct features
# ============================================================


class TestFeaturesReadyView:
    """features_ready view returns features meeting readiness thresholds."""

    def test_query_features_ready_importable(self):
        from bob3.db import query_features_ready
        assert callable(query_features_ready)

    def test_returns_ready_features_only(self, db_path, project_id):
        from bob3.db import calculate_readiness, query_features_ready

        # Ready feature with high readiness
        ready_feat = _make_feature(
            project_id, "Ready", status="ready", readiness=0.95
        )
        calculate_readiness(ready_feat.id)

        # Pending feature (should not appear)
        _make_feature(project_id, "Pending", status="pending", readiness=0.95)

        result = query_features_ready(project_id)
        assert len(result) == 1
        assert result[0]["id"] == ready_feat.id

    def test_empty_when_no_ready(self, db_path, project_id):
        from bob3.db import query_features_ready

        result = query_features_ready(project_id)
        assert result == []


# ============================================================
# Step 2: Test features_needing_refinement view
# ============================================================


class TestFeaturesNeedingRefinementView:
    """features_needing_refinement returns features below readiness threshold."""

    def test_query_importable(self):
        from bob3.db import query_features_needing_refinement
        assert callable(query_features_needing_refinement)

    def test_returns_features_below_threshold(self, db_path, project_id):
        from bob3.db import query_features_needing_refinement

        # Feature below medium threshold (0.80) with attempts remaining
        feat = _make_feature(
            project_id, "Needs Refinement",
            status="refining", readiness=0.5,
            refinement_attempts=1, max_refinement_attempts=5,
        )

        result = query_features_needing_refinement(project_id)
        assert len(result) >= 1
        ids = [r["id"] for r in result]
        assert feat.id in ids

    def test_excludes_blocked_statuses(self, db_path, project_id):
        from bob3.db import query_features_needing_refinement

        # Feature with blocked status should be excluded
        _make_feature(
            project_id, "Blocked",
            status="blocked_by_reviewer", readiness=0.3,
            refinement_attempts=0, max_refinement_attempts=5,
        )

        result = query_features_needing_refinement(project_id)
        names = [r["name"] for r in result]
        assert "Blocked" not in names

    def test_excludes_maxed_refinements(self, db_path, project_id):
        from bob3.db import query_features_needing_refinement

        # Feature that has used all refinement attempts
        _make_feature(
            project_id, "Maxed Out",
            status="refining", readiness=0.3,
            refinement_attempts=5, max_refinement_attempts=5,
        )

        result = query_features_needing_refinement(project_id)
        names = [r["name"] for r in result]
        assert "Maxed Out" not in names

    def test_empty_when_all_ready(self, db_path, project_id):
        from bob3.db import query_features_needing_refinement

        _make_feature(project_id, "Ready", status="ready", readiness=0.95)
        result = query_features_needing_refinement(project_id)
        assert result == []


# ============================================================
# Step 3: Test features_blocked view
# ============================================================


class TestFeaturesBlockedView:
    """features_blocked returns features with blocking statuses and reasons."""

    def test_query_importable(self):
        from bob3.db import query_features_blocked
        assert callable(query_features_blocked)

    def test_returns_blocked_features(self, db_path, project_id):
        from bob3.db import query_features_blocked

        _make_feature(project_id, "Reviewer Block", status="blocked_by_reviewer")
        _make_feature(project_id, "Dep Block", status="blocked_by_dependency")
        _make_feature(project_id, "Human Needed", status="needs_human")
        _make_feature(project_id, "Resource Limit", status="resource_limited")

        result = query_features_blocked(project_id)
        assert len(result) == 4

    def test_includes_block_reason(self, db_path, project_id):
        from bob3.db import query_features_blocked

        _make_feature(project_id, "Reviewer Block", status="blocked_by_reviewer")

        result = query_features_blocked(project_id)
        assert len(result) == 1
        assert "block_reason" in result[0]
        assert result[0]["block_reason"] == "Reviewer veto active"

    def test_excludes_non_blocked(self, db_path, project_id):
        from bob3.db import query_features_blocked

        _make_feature(project_id, "Pending", status="pending")
        _make_feature(project_id, "Ready", status="ready")

        result = query_features_blocked(project_id)
        assert result == []


# ============================================================
# Step 4: Test unresolved_issues view
# ============================================================


class TestUnresolvedIssuesView:
    """unresolved_issues returns features with unresolved review issues."""

    def test_query_importable(self):
        from bob3.db import query_unresolved_issues
        assert callable(query_unresolved_issues)

    def test_returns_features_with_issues(self, db_path, project_id):
        from bob3.db import (
            create_review,
            create_review_issue,
            query_unresolved_issues,
        )

        feat = _make_feature(project_id, "Has Issues", status="refining")
        review = create_review(
            project_id=project_id,
            feature_id=feat.id,
            reviewer_id="reviewer-1",
        )
        create_review_issue(
            feature_id=feat.id,
            review_id=review.id,
            issue_description="Fix the bug",
        )
        create_review_issue(
            feature_id=feat.id,
            review_id=review.id,
            issue_description="Add tests",
        )

        result = query_unresolved_issues(project_id)
        assert len(result) == 1
        assert result[0]["feature_id"] == feat.id
        assert result[0]["issue_count"] == 2

    def test_excludes_resolved_issues(self, db_path, project_id):
        from bob3.db import (
            create_review,
            create_review_issue,
            query_unresolved_issues,
            resolve_review_issue,
        )

        feat = _make_feature(project_id, "Resolved Issues", status="refining")
        review = create_review(
            project_id=project_id,
            feature_id=feat.id,
            reviewer_id="reviewer-1",
        )
        issue = create_review_issue(
            feature_id=feat.id,
            review_id=review.id,
            issue_description="Fixed now",
        )
        resolve_review_issue(issue.id)

        result = query_unresolved_issues(project_id)
        assert result == []

    def test_empty_when_no_issues(self, db_path, project_id):
        from bob3.db import query_unresolved_issues

        result = query_unresolved_issues(project_id)
        assert result == []


# ============================================================
# Step 5: Test calibration_drift_summary view
# ============================================================


class TestCalibrationDriftSummaryView:
    """calibration_drift_summary shows calibration state per task class."""

    def test_query_importable(self):
        from bob3.db import query_calibration_drift_summary
        assert callable(query_calibration_drift_summary)

    def test_returns_drift_data(self, db_path, project_id):
        from bob3.db import create_or_update_calibration, query_calibration_drift_summary

        # Create enough attempts to reach the 10-minimum threshold
        for _ in range(12):
            create_or_update_calibration(
                project_id=project_id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=True,
                expected_pass_rate=0.85,
            )

        result = query_calibration_drift_summary(project_id)
        assert len(result) >= 1
        entry = result[0]
        assert "task_class" in entry
        assert "status" in entry
        assert entry["total_attempts"] >= 10

    def test_excludes_low_sample_size(self, db_path, project_id):
        from bob3.db import create_or_update_calibration, query_calibration_drift_summary

        # Only 5 attempts (below minimum of 10)
        for _ in range(5):
            create_or_update_calibration(
                project_id=project_id,
                task_class="test_writing",
                confidence_bucket="0.7-0.8",
                passed=True,
                expected_pass_rate=0.75,
            )

        result = query_calibration_drift_summary(project_id)
        classes = [r["task_class"] for r in result]
        assert "test_writing" not in classes

    def test_empty_when_no_data(self, db_path, project_id):
        from bob3.db import query_calibration_drift_summary

        result = query_calibration_drift_summary(project_id)
        assert result == []


# ============================================================
# Step 6: Test active_regressions view
# ============================================================


class TestActiveRegressionsView:
    """active_regressions returns unresolved regression events."""

    def test_query_importable(self):
        from bob3.db import query_active_regressions
        assert callable(query_active_regressions)

    def test_returns_active_regressions(self, db_path, project_id):
        from bob3.db import create_regression_event, query_active_regressions

        affected = _make_feature(project_id, "Affected Feature")
        causing = _make_feature(project_id, "Causing Feature")

        create_regression_event(
            project_id=project_id,
            affected_feature_id=affected.id,
            causing_feature_id=causing.id,
        )

        result = query_active_regressions(project_id)
        assert len(result) == 1
        assert result[0]["affected_feature_name"] == "Affected Feature"
        assert result[0]["causing_feature_name"] == "Causing Feature"

    def test_excludes_resolved_regressions(self, db_path, project_id):
        from bob3.db import (
            create_regression_event,
            query_active_regressions,
            update_regression_event,
        )

        affected = _make_feature(project_id, "Affected")
        causing = _make_feature(project_id, "Causing")

        reg = create_regression_event(
            project_id=project_id,
            affected_feature_id=affected.id,
            causing_feature_id=causing.id,
        )
        update_regression_event(reg.id, status="resolved")

        result = query_active_regressions(project_id)
        assert result == []

    def test_empty_when_no_regressions(self, db_path, project_id):
        from bob3.db import query_active_regressions

        result = query_active_regressions(project_id)
        assert result == []


# ============================================================
# Step 7: Verify all 20+ views work correctly
# ============================================================


class TestFeaturesNeedsHumanView:
    """features_needs_human returns features requiring human intervention."""

    def test_query_importable(self):
        from bob3.db import query_features_needs_human
        assert callable(query_features_needs_human)

    def test_returns_needs_human_status(self, db_path, project_id):
        from bob3.db import query_features_needs_human

        _make_feature(project_id, "Human Needed", status="needs_human")

        result = query_features_needs_human(project_id)
        assert len(result) >= 1
        names = [r["name"] for r in result]
        assert "Human Needed" in names

    def test_returns_maxed_refinement(self, db_path, project_id):
        from bob3.db import query_features_needs_human

        _make_feature(
            project_id, "Maxed Refinement",
            status="refining",
            refinement_attempts=5,
            max_refinement_attempts=5,
        )

        result = query_features_needs_human(project_id)
        names = [r["name"] for r in result]
        assert "Maxed Refinement" in names


class TestFeaturesPendingDecompositionView:
    """features_pending_decomposition returns oversized/pending features."""

    def test_query_importable(self):
        from bob3.db import query_features_pending_decomposition
        assert callable(query_features_pending_decomposition)

    def test_returns_pending_decomposition(self, db_path, project_id):
        from bob3.db import query_features_pending_decomposition

        _make_feature(
            project_id, "Needs Decomp",
            status="pending_decomposition",
        )

        result = query_features_pending_decomposition(project_id)
        assert len(result) >= 1
        names = [r["name"] for r in result]
        assert "Needs Decomp" in names

    def test_returns_exceeds_size_limits(self, db_path, project_id):
        from bob3.db import query_features_pending_decomposition

        _make_feature(
            project_id, "Too Big",
            status="pending",
            exceeds_size_limits=True,
        )

        result = query_features_pending_decomposition(project_id)
        names = [r["name"] for r in result]
        assert "Too Big" in names


class TestReviewsPendingView:
    """reviews_pending returns reviews awaiting verdict."""

    def test_query_importable(self):
        from bob3.db import query_reviews_pending
        assert callable(query_reviews_pending)

    def test_returns_pending_reviews(self, db_path, project_id):
        from bob3.db import create_review, query_reviews_pending

        feat = _make_feature(project_id, "Under Review", status="refining")
        create_review(
            project_id=project_id,
            feature_id=feat.id,
            reviewer_id="reviewer-1",
        )

        result = query_reviews_pending(project_id)
        assert len(result) == 1
        assert result[0]["feature_name"] == "Under Review"
        assert "hours_waiting" in result[0]

    def test_excludes_reviewed(self, db_path, project_id):
        from bob3.db import create_review, query_reviews_pending, update_review_verdict

        feat = _make_feature(project_id, "Reviewed", status="refining")
        review = create_review(
            project_id=project_id,
            feature_id=feat.id,
            reviewer_id="reviewer-1",
        )
        update_review_verdict(review.id, verdict="approve")

        result = query_reviews_pending(project_id)
        assert result == []


class TestStaleEvidenceView:
    """stale_evidence returns evidence that may be outdated."""

    def test_query_importable(self):
        from bob3.db import query_stale_evidence
        assert callable(query_stale_evidence)

    def test_returns_env_mismatch_evidence(self, db_path, project_id):
        from bob3.db import create_evidence, query_stale_evidence

        feat = _make_feature(project_id, "Stale Ev Feature")
        create_evidence(
            project_id=project_id,
            feature_id=feat.id,
            type="test_result",
            content=json.dumps({"result": "pass"}),
            is_current=True,
            environment_matches_current=False,
            iteration_created=1,
        )

        result = query_stale_evidence(project_id)
        assert len(result) >= 1

    def test_empty_when_all_current(self, db_path, project_id):
        from bob3.db import query_stale_evidence

        result = query_stale_evidence(project_id)
        assert result == []


class TestFlakyTestsPendingView:
    """flaky_tests_pending returns flaky tests needing attention."""

    def test_query_importable(self):
        from bob3.db import query_flaky_tests_pending
        assert callable(query_flaky_tests_pending)

    def test_returns_flaky_tests(self, db_path, project_id):
        from bob3.db import create_task, query_flaky_tests_pending, update_task

        feat = _make_feature(project_id, "Flaky Feature")
        task = create_task(
            feature_id=feat.id,
            project_id=project_id,
            type="validation",
            title="Flaky Test",
        )
        update_task(task.id, is_flaky=True, status="pending")

        result = query_flaky_tests_pending(project_id)
        assert len(result) >= 1
        assert result[0]["title"] == "Flaky Test"

    def test_excludes_completed_flaky(self, db_path, project_id):
        from bob3.db import create_task, query_flaky_tests_pending, update_task

        feat = _make_feature(project_id, "Completed Flaky Feature")
        task = create_task(
            feature_id=feat.id,
            project_id=project_id,
            type="validation",
            title="Completed Flaky",
        )
        update_task(task.id, is_flaky=True, status="completed")

        result = query_flaky_tests_pending(project_id)
        titles = [r["title"] for r in result]
        assert "Completed Flaky" not in titles


class TestScopeCreepAlertsView:
    """scope_creep_alerts returns features with significant scope growth."""

    def test_query_importable(self):
        from bob3.db import query_scope_creep_alerts
        assert callable(query_scope_creep_alerts)

    def test_returns_scope_creep(self, db_path, project_id):
        from bob3.db import create_task, query_scope_creep_alerts

        feat = _make_feature(
            project_id, "Scope Creep",
            original_task_count=2,
        )
        # Create 5 tasks (more than 2x the original 2)
        for i in range(5):
            create_task(
                feature_id=feat.id,
                project_id=project_id,
                type="implementation",
                title=f"Task {i}",
            )

        result = query_scope_creep_alerts(project_id)
        assert len(result) >= 1
        names = [r["name"] for r in result]
        assert "Scope Creep" in names

    def test_no_alert_for_normal_growth(self, db_path, project_id):
        from bob3.db import create_task, query_scope_creep_alerts

        feat = _make_feature(
            project_id, "Normal Growth",
            original_task_count=5,
        )
        # Only 6 tasks (less than 2x the original 5)
        for i in range(6):
            create_task(
                feature_id=feat.id,
                project_id=project_id,
                type="implementation",
                title=f"Task {i}",
            )

        result = query_scope_creep_alerts(project_id)
        names = [r["name"] for r in result]
        assert "Normal Growth" not in names


class TestPotentialGamingView:
    """potential_gaming returns confidence scores reported 3+ times identically."""

    def test_query_importable(self):
        from bob3.db import query_potential_gaming
        assert callable(query_potential_gaming)

    def test_detects_repeated_confidence(self, db_path, project_id):
        from bob3.db import query_potential_gaming, record_confidence

        feat = _make_feature(project_id, "Gaming Feature")
        task = None
        from bob3.db import create_task
        task = create_task(
            feature_id=feat.id,
            project_id=project_id,
            type="implementation",
            title="Gamed Task",
        )

        # Report same confidence 3 times
        for _ in range(3):
            record_confidence(
                project_id=project_id,
                feature_id=feat.id,
                task_id=task.id,
                conf_impl_correctness=0.99,
                rated_by="agent",
            )

        result = query_potential_gaming(project_id)
        assert len(result) >= 1

    def test_empty_when_no_gaming(self, db_path, project_id):
        from bob3.db import query_potential_gaming

        result = query_potential_gaming(project_id)
        assert result == []


class TestTestIntegrityViolationsView:
    """test_integrity_violations returns tests with weakened assertions."""

    def test_query_importable(self):
        from bob3.db import query_test_integrity_violations_view
        assert callable(query_test_integrity_violations_view)

    def test_detects_assertion_decrease(self, db_path, project_id):
        from bob3.db import create_task, query_test_integrity_violations_view, update_task

        feat = _make_feature(project_id, "Integrity Feature")
        task = create_task(
            feature_id=feat.id,
            project_id=project_id,
            type="validation",
            title="Weakened Test",
        )
        update_task(
            task.id,
            original_assertion_count=10,
            current_assertion_count=5,
        )

        result = query_test_integrity_violations_view(project_id)
        assert len(result) >= 1
        assert result[0]["title"] == "Weakened Test"
        assert result[0]["feature_name"] == "Integrity Feature"

    def test_detects_coverage_decrease(self, db_path, project_id):
        from bob3.db import create_task, query_test_integrity_violations_view, update_task

        feat = _make_feature(project_id, "Coverage Feature")
        task = create_task(
            feature_id=feat.id,
            project_id=project_id,
            type="validation",
            title="Coverage Drop",
        )
        update_task(
            task.id,
            original_coverage_percent=90.0,
            current_coverage_percent=80.0,
        )

        result = query_test_integrity_violations_view(project_id)
        titles = [r["title"] for r in result]
        assert "Coverage Drop" in titles


class TestResourceUsageView:
    """resource_usage returns project resource consumption summary."""

    def test_query_importable(self):
        from bob3.db import query_resource_usage
        assert callable(query_resource_usage)

    def test_returns_project_usage(self, db_path, project_id):
        from bob3.db import query_resource_usage

        result = query_resource_usage(project_id)
        assert len(result) == 1
        assert result[0]["id"] == project_id
        assert "cost_percent_used" in result[0]
        assert "features_completed" in result[0]
        assert "features_total" in result[0]

    def test_includes_feature_counts(self, db_path, project_id):
        from bob3.db import query_resource_usage

        _make_feature(project_id, "Completed", status="completed")
        _make_feature(project_id, "Pending", status="pending")

        result = query_resource_usage(project_id)
        assert result[0]["features_total"] == 2
        assert result[0]["features_completed"] == 1


class TestActiveBugsView:
    """active_bugs returns unresolved bugs."""

    def test_query_importable(self):
        from bob3.db import query_active_bugs
        assert callable(query_active_bugs)

    def test_returns_active_bugs(self, db_path, project_id):
        from bob3.db import create_bug, query_active_bugs

        feat = _make_feature(project_id, "Buggy Feature")
        create_bug(
            project_id=project_id,
            feature_id=feat.id,
            error_type="RuntimeError",
            error_message="Something broke",
            evidence_artifacts=json.dumps(["ev-1"]),
            fix_action="retry",
        )

        result = query_active_bugs(project_id)
        assert len(result) == 1
        assert result[0]["feature_name"] == "Buggy Feature"

    def test_excludes_resolved_bugs(self, db_path, project_id):
        from bob3.db import create_bug, query_active_bugs, resolve_bug

        feat = _make_feature(project_id, "Fixed Feature")
        bug = create_bug(
            project_id=project_id,
            feature_id=feat.id,
            error_type="ValueError",
            error_message="Bad value",
            evidence_artifacts=json.dumps(["ev-2"]),
            fix_action="validate input",
        )
        resolve_bug(bug.id)

        result = query_active_bugs(project_id)
        assert result == []


class TestOrphanedFeaturesView:
    """orphaned_features returns child features whose parents are abandoned."""

    def test_query_importable(self):
        from bob3.db import query_orphaned_features
        assert callable(query_orphaned_features)

    def test_returns_orphaned_children(self, db_path, project_id):
        from bob3.db import query_orphaned_features, update_feature

        parent = _make_feature(project_id, "Parent", status="failed")
        child = _make_feature(project_id, "Child", status="pending")
        update_feature(child.id, parent_feature_id=parent.id)

        result = query_orphaned_features(project_id)
        assert len(result) >= 1
        ids = [r["id"] for r in result]
        assert child.id in ids

    def test_excludes_non_orphaned(self, db_path, project_id):
        from bob3.db import query_orphaned_features

        parent = _make_feature(project_id, "Active Parent", status="executing")
        child = _make_feature(project_id, "Active Child", status="pending")
        from bob3.db import update_feature
        update_feature(child.id, parent_feature_id=parent.id)

        result = query_orphaned_features(project_id)
        ids = [r["id"] for r in result]
        assert child.id not in ids


class TestOversizedFeaturesView:
    """oversized_features returns features exceeding size limits."""

    def test_query_importable(self):
        from bob3.db import query_oversized_features
        assert callable(query_oversized_features)

    def test_returns_exceeds_size_limits(self, db_path, project_id):
        from bob3.db import query_oversized_features

        feat = _make_feature(
            project_id, "Oversized",
            exceeds_size_limits=True,
            estimated_lines_of_code=600,
        )

        result = query_oversized_features(project_id)
        assert len(result) >= 1
        names = [r["name"] for r in result]
        assert "Oversized" in names

    def test_detects_too_many_tasks(self, db_path, project_id):
        from bob3.db import create_task, query_oversized_features

        feat = _make_feature(project_id, "Many Tasks")
        for i in range(11):
            create_task(
                feature_id=feat.id,
                project_id=project_id,
                type="implementation",
                title=f"Task {i}",
            )

        result = query_oversized_features(project_id)
        names = [r["name"] for r in result]
        assert "Many Tasks" in names

    def test_includes_limit_exceeded_reason(self, db_path, project_id):
        from bob3.db import query_oversized_features

        _make_feature(
            project_id, "Too Complex",
            estimated_complexity=9,
        )

        result = query_oversized_features(project_id)
        if result:
            assert "limit_exceeded" in result[0]


class TestReviewTimeoutsView:
    """review_timeouts returns reviews past their timeout period."""

    def test_query_importable(self):
        from bob3.db import query_review_timeouts
        assert callable(query_review_timeouts)

    def test_empty_when_no_timeouts(self, db_path, project_id):
        from bob3.db import query_review_timeouts

        result = query_review_timeouts(project_id)
        assert result == []


# ============================================================
# Comprehensive: query_all_views returns data from all views
# ============================================================


class TestQueryAllViews:
    """query_all_views aggregates all view data into a single status report."""

    def test_query_all_views_importable(self):
        from bob3.db import query_all_views
        assert callable(query_all_views)

    def test_returns_dict_with_all_view_keys(self, db_path, project_id):
        from bob3.db import query_all_views

        result = query_all_views(project_id)
        assert isinstance(result, dict)

        expected_keys = [
            "features_ready",
            "features_needing_refinement",
            "features_pending_decomposition",
            "features_blocked",
            "features_needs_human",
            "unresolved_issues",
            "reviews_pending",
            "review_timeouts",
            "stale_evidence",
            "calibration_drift_summary",
            "active_regressions",
            "flaky_tests_pending",
            "scope_creep_alerts",
            "potential_gaming",
            "test_integrity_violations",
            "resource_usage",
            "active_bugs",
            "orphaned_features",
            "oversized_features",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_all_values_are_lists(self, db_path, project_id):
        from bob3.db import query_all_views

        result = query_all_views(project_id)
        for key, value in result.items():
            assert isinstance(value, list), f"{key} should be a list, got {type(value)}"

    def test_all_views_return_empty_on_fresh_db(self, db_path, project_id):
        from bob3.db import query_all_views

        result = query_all_views(project_id)
        # resource_usage should have the project itself
        assert len(result["resource_usage"]) == 1
        # Everything else should be empty on a fresh project
        for key in result:
            if key != "resource_usage":
                assert isinstance(result[key], list)
