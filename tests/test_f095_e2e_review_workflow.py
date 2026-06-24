"""Tests for F095: End-to-end test - Review workflow.

Exercises the complete review lifecycle:
  Step 1: Complete feature and request review
  Step 2: Create 2 review issues
  Step 3: Verify feature status is blocked_by_reviewer
  Step 4: Resolve 1 issue
  Step 5: Resolve 2nd issue
  Step 6: Record approve verdict
  Step 7: Verify feature status becomes ready
"""

import json
import pathlib
import tempfile

import pytest

from bob3 import db
from bob3.models import Feature, FeatureReviewIssue, ReviewHistory


@pytest.fixture()
def tmp_db(monkeypatch):
    """Create a temporary database with a project and a completed-ish feature."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test.db"
        monkeypatch.setattr(db, "get_database_path", lambda: db_path)
        db.init_database(db_path=db_path)
        yield db_path


# ============================================================
# Step 1: Complete feature and request review
# ============================================================


class TestStep1CompleteFeatureAndRequestReview:
    def test_feature_created_and_review_requested(self, tmp_db):
        """Create a project/feature, mark it executing, then request a review."""
        project = db.create_project(
            name="review-test-project",
            workspace_path="/tmp/review-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Review Workflow Feature",
            description="A feature that needs review",
            acceptance_criteria=json.dumps(["Criterion 1", "Criterion 2"]),
            status="executing",
            priority=10,
            risk_category="medium",
        )
        db.update_feature(
            feature.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )

        # Request review
        review = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="senior-reviewer",
            reviewer_type="human",
            reviewer_seniority=5,
            notes="Please review the implementation",
        )

        assert isinstance(review, ReviewHistory)
        assert review.verdict is None
        assert review.reviewer_id == "senior-reviewer"
        assert review.feature_id == feature.id

        # Should appear in pending reviews
        pending = db.get_pending_reviews(project_id=project.id)
        assert len(pending) == 1
        assert pending[0].id == review.id


# ============================================================
# Step 2: Create 2 review issues
# ============================================================


class TestStep2CreateReviewIssues:
    def test_two_issues_created_for_review(self, tmp_db):
        """Create 2 review issues after requesting a review."""
        project = db.create_project(
            name="review-test-project",
            workspace_path="/tmp/review-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Review Workflow Feature",
            status="executing",
            priority=10,
        )
        review = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-1",
        )

        issue1 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Missing error handling in edge case",
            severity="high",
        )
        issue2 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Insufficient test coverage for boundary conditions",
            severity="medium",
        )

        assert isinstance(issue1, FeatureReviewIssue)
        assert isinstance(issue2, FeatureReviewIssue)
        assert issue1.id != issue2.id

        # Both issues exist and are unresolved
        issues = db.get_review_issues(review_id=review.id)
        assert len(issues) == 2
        assert all(not i.resolved for i in issues)

        unresolved = db.get_unresolved_review_issues(feature_id=feature.id)
        assert len(unresolved) == 2


# ============================================================
# Step 3: Verify feature status is blocked_by_reviewer
# ============================================================


class TestStep3FeatureBlockedByReviewer:
    def test_block_verdict_sets_feature_blocked(self, tmp_db):
        """Recording a block verdict sets feature status to blocked_by_reviewer."""
        project = db.create_project(
            name="review-test-project",
            workspace_path="/tmp/review-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Review Workflow Feature",
            status="executing",
            priority=10,
        )
        review = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-1",
        )

        # Create issues
        db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Issue 1",
            severity="high",
        )
        db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Issue 2",
            severity="medium",
        )

        # Reviewer blocks the feature
        issues_json = json.dumps(["Issue 1", "Issue 2"])
        result = db.record_verdict(
            review.id,
            verdict="block",
            issues_flagged=issues_json,
        )

        assert result.verdict == "block"
        assert result.veto_active is True

        # Feature should now be blocked_by_reviewer
        feat = db.get_feature(feature.id)
        assert feat.status == "blocked_by_reviewer"


# ============================================================
# Step 4: Resolve 1 issue
# ============================================================


class TestStep4ResolveOneIssue:
    def test_resolve_first_issue(self, tmp_db):
        """Resolve the first issue, verify 1 remains unresolved."""
        project = db.create_project(
            name="review-test-project",
            workspace_path="/tmp/review-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Review Workflow Feature",
            status="executing",
            priority=10,
        )
        review = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-1",
        )
        issue1 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Issue 1: Missing error handling",
            severity="high",
        )
        issue2 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Issue 2: Insufficient tests",
            severity="medium",
        )

        # Block the feature
        db.record_verdict(
            review.id,
            verdict="block",
            issues_flagged=json.dumps(["Issue 1", "Issue 2"]),
        )
        assert db.get_feature(feature.id).status == "blocked_by_reviewer"

        # Resolve first issue
        resolved1 = db.resolve_review_issue(
            issue1.id,
            resolved_by_attempt=1,
            resolution_evidence="Added error handling in handler.py",
        )
        assert resolved1.resolved is True
        assert resolved1.resolved_at is not None
        assert resolved1.resolution_evidence == "Added error handling in handler.py"

        # Still 1 unresolved issue remaining
        unresolved = db.get_unresolved_review_issues(feature_id=feature.id)
        assert len(unresolved) == 1
        assert unresolved[0].id == issue2.id


# ============================================================
# Step 5: Resolve 2nd issue
# ============================================================


class TestStep5ResolveSecondIssue:
    def test_resolve_second_issue(self, tmp_db):
        """Resolve the second issue, verify 0 remain unresolved."""
        project = db.create_project(
            name="review-test-project",
            workspace_path="/tmp/review-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Review Workflow Feature",
            status="executing",
            priority=10,
        )
        review = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-1",
        )
        issue1 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Issue 1",
            severity="high",
        )
        issue2 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Issue 2",
            severity="medium",
        )

        # Block the feature
        db.record_verdict(
            review.id,
            verdict="block",
            issues_flagged=json.dumps(["Issue 1", "Issue 2"]),
        )

        # Resolve both issues
        db.resolve_review_issue(issue1.id, resolved_by_attempt=1, resolution_evidence="Fixed")
        db.resolve_review_issue(issue2.id, resolved_by_attempt=2, resolution_evidence="Tests added")

        # No unresolved issues remain
        unresolved = db.get_unresolved_review_issues(feature_id=feature.id)
        assert len(unresolved) == 0

        # All issues are resolved
        all_issues = db.get_review_issues(review_id=review.id)
        assert len(all_issues) == 2
        assert all(i.resolved for i in all_issues)


# ============================================================
# Step 6: Record approve verdict
# ============================================================


class TestStep6RecordApproveVerdict:
    def test_new_review_approve_after_issues_resolved(self, tmp_db):
        """After resolving all issues, a new review approves the feature."""
        project = db.create_project(
            name="review-test-project",
            workspace_path="/tmp/review-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Review Workflow Feature",
            status="executing",
            priority=10,
        )
        # First review: block
        review1 = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-1",
        )
        issue1 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review1.id,
            issue_description="Issue 1",
        )
        issue2 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review1.id,
            issue_description="Issue 2",
        )
        db.record_verdict(review1.id, verdict="block")
        assert db.get_feature(feature.id).status == "blocked_by_reviewer"

        # Resolve all issues
        db.resolve_review_issue(issue1.id, resolution_evidence="Fixed")
        db.resolve_review_issue(issue2.id, resolution_evidence="Fixed")
        assert len(db.get_unresolved_review_issues(feature_id=feature.id)) == 0

        # Second review: approve
        review2 = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-1",
        )
        result = db.record_verdict(review2.id, verdict="approve")
        assert result.verdict == "approve"
        assert result.veto_active is False


# ============================================================
# Step 7: Verify feature status becomes ready
# ============================================================


class TestStep7FeatureBecomesReady:
    def test_approve_sets_feature_ready(self, tmp_db):
        """After approval, feature status becomes 'ready'."""
        project = db.create_project(
            name="review-test-project",
            workspace_path="/tmp/review-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Review Workflow Feature",
            status="executing",
            priority=10,
        )
        # First review: block
        review1 = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-1",
        )
        issue1 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review1.id,
            issue_description="Issue 1",
        )
        issue2 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review1.id,
            issue_description="Issue 2",
        )
        db.record_verdict(review1.id, verdict="block")
        assert db.get_feature(feature.id).status == "blocked_by_reviewer"

        # Resolve issues
        db.resolve_review_issue(issue1.id, resolution_evidence="Fixed")
        db.resolve_review_issue(issue2.id, resolution_evidence="Fixed")

        # Approve
        review2 = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-1",
        )
        db.record_verdict(review2.id, verdict="approve")

        # Feature should now be 'ready'
        feat = db.get_feature(feature.id)
        assert feat.status == "ready"


# ============================================================
# Full E2E: All 7 steps in a single test
# ============================================================


class TestFullReviewWorkflowE2E:
    def test_complete_review_workflow(self, tmp_db):
        """End-to-end: request review -> block with issues -> resolve -> approve -> ready.

        Exercises the full acceptance criteria in a single sequential workflow:
          Step 1: Complete feature and request review
          Step 2: Create 2 review issues
          Step 3: Verify feature status is blocked_by_reviewer
          Step 4: Resolve 1 issue
          Step 5: Resolve 2nd issue
          Step 6: Record approve verdict
          Step 7: Verify feature status becomes ready
        """
        # ---- Step 1: Complete feature and request review ----
        project = db.create_project(
            name="e2e-review-project",
            workspace_path="/tmp/e2e-review-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="E2E Review Feature",
            description="Feature for full review workflow test",
            acceptance_criteria=json.dumps(["Criterion A", "Criterion B"]),
            status="executing",
            priority=10,
            risk_category="medium",
        )
        db.update_feature(
            feature.id,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
            readiness_score=0.85,
        )

        review = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="lead-reviewer",
            reviewer_type="human",
            reviewer_seniority=7,
            notes="Full review of E2E feature",
        )
        assert isinstance(review, ReviewHistory)
        assert review.verdict is None
        pending = db.get_pending_reviews(project_id=project.id)
        assert any(r.id == review.id for r in pending)

        # ---- Step 2: Create 2 review issues ----
        issue1 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Missing error handling for network timeouts",
            severity="high",
        )
        issue2 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Test coverage below threshold for edge cases",
            severity="medium",
        )
        assert issue1.resolved is False
        assert issue2.resolved is False
        issues = db.get_review_issues(review_id=review.id)
        assert len(issues) == 2
        unresolved = db.get_unresolved_review_issues(feature_id=feature.id)
        assert len(unresolved) == 2

        # ---- Step 3: Verify feature status is blocked_by_reviewer ----
        issues_json = json.dumps([
            "Missing error handling for network timeouts",
            "Test coverage below threshold for edge cases",
        ])
        verdict_result = db.record_verdict(
            review.id,
            verdict="block",
            issues_flagged=issues_json,
        )
        assert verdict_result.verdict == "block"
        assert verdict_result.veto_active is True

        feat = db.get_feature(feature.id)
        assert feat.status == "blocked_by_reviewer"

        # Review should no longer be pending (it has a verdict now)
        pending = db.get_pending_reviews(project_id=project.id)
        assert not any(r.id == review.id for r in pending)

        # ---- Step 4: Resolve 1 issue ----
        resolved1 = db.resolve_review_issue(
            issue1.id,
            resolved_by_attempt=1,
            resolution_evidence="Added timeout handling with retry logic in network_client.py",
        )
        assert resolved1.resolved is True
        assert resolved1.resolved_at is not None
        assert resolved1.resolution_evidence is not None

        # 1 issue still unresolved
        unresolved = db.get_unresolved_review_issues(feature_id=feature.id)
        assert len(unresolved) == 1
        assert unresolved[0].id == issue2.id

        # Feature is still blocked
        feat = db.get_feature(feature.id)
        assert feat.status == "blocked_by_reviewer"

        # ---- Step 5: Resolve 2nd issue ----
        resolved2 = db.resolve_review_issue(
            issue2.id,
            resolved_by_attempt=2,
            resolution_evidence="Added 12 new edge-case tests, coverage now at 94%",
        )
        assert resolved2.resolved is True
        assert resolved2.resolved_at is not None

        # All issues resolved
        unresolved = db.get_unresolved_review_issues(feature_id=feature.id)
        assert len(unresolved) == 0

        # Verify all issues show as resolved
        all_issues = db.get_review_issues(review_id=review.id)
        assert len(all_issues) == 2
        assert all(i.resolved for i in all_issues)

        # ---- Step 6: Record approve verdict ----
        # Request a new review for the re-submission
        review2 = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="lead-reviewer",
            reviewer_type="human",
            reviewer_seniority=7,
            notes="Re-review after issues resolved",
        )
        assert review2.id != review.id
        assert review2.verdict is None

        approve_result = db.record_verdict(review2.id, verdict="approve")
        assert approve_result.verdict == "approve"
        assert approve_result.veto_active is False

        # ---- Step 7: Verify feature status becomes ready ----
        final_feature = db.get_feature(feature.id)
        assert final_feature.status == "ready"

        # Verify the full review history for the feature
        all_reviews = db.get_feature_reviews(feature_id=feature.id)
        assert len(all_reviews) == 2
        verdicts = [r.verdict for r in all_reviews]
        assert "block" in verdicts
        assert "approve" in verdicts

    def test_request_changes_then_approve_workflow(self, tmp_db):
        """Alternative workflow: request_changes (not block) -> resolve issues -> approve."""
        project = db.create_project(
            name="changes-review-project",
            workspace_path="/tmp/changes-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Changes Workflow Feature",
            status="executing",
            priority=10,
        )

        # Step 1: Request review
        review = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-A",
        )

        # Step 2: Create issues and request changes (softer than block)
        issue1 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Naming convention inconsistency",
            severity="low",
        )
        issue2 = db.create_review_issue(
            feature_id=feature.id,
            review_id=review.id,
            issue_description="Missing docstring on public API",
            severity="low",
        )
        db.record_verdict(review.id, verdict="request_changes")

        # Step 3: Feature should be 'refining' (not blocked)
        feat = db.get_feature(feature.id)
        assert feat.status == "refining"

        # Step 4 & 5: Resolve both issues
        db.resolve_review_issue(issue1.id, resolution_evidence="Renamed variables")
        db.resolve_review_issue(issue2.id, resolution_evidence="Added docstrings")
        assert len(db.get_unresolved_review_issues(feature_id=feature.id)) == 0

        # Step 6: Approve
        review2 = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-A",
        )
        db.record_verdict(review2.id, verdict="approve")

        # Step 7: Feature is ready
        feat = db.get_feature(feature.id)
        assert feat.status == "ready"

    def test_multiple_reviewers_workflow(self, tmp_db):
        """Workflow with two reviewers: one blocks, one approves, block wins until resolved."""
        project = db.create_project(
            name="multi-reviewer-project",
            workspace_path="/tmp/multi-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Multi-Reviewer Feature",
            status="executing",
            priority=10,
        )

        # Reviewer A approves
        review_a = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-A",
            reviewer_seniority=3,
        )
        db.record_verdict(review_a.id, verdict="approve")
        assert db.get_feature(feature.id).status == "ready"

        # Reviewer B (more senior) blocks with issues
        review_b = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-B",
            reviewer_seniority=8,
        )
        issue = db.create_review_issue(
            feature_id=feature.id,
            review_id=review_b.id,
            issue_description="Security vulnerability in auth flow",
            severity="critical",
        )
        db.record_verdict(review_b.id, verdict="block")

        # Block overrides the earlier approve
        assert db.get_feature(feature.id).status == "blocked_by_reviewer"

        # Resolve the issue
        db.resolve_review_issue(issue.id, resolution_evidence="Patched auth flow")

        # New review from senior reviewer: approve
        review_b2 = db.request_review(
            project_id=project.id,
            feature_id=feature.id,
            reviewer_id="reviewer-B",
            reviewer_seniority=8,
        )
        db.record_verdict(review_b2.id, verdict="approve")

        assert db.get_feature(feature.id).status == "ready"
