"""Tests for F035: Review issue tracking (feature_review_issues table).

Tests create_review_issue(), resolve_review_issue(), issue-to-review linking,
severity tracking, issue counts, and resolved_at timestamp verification.
"""

import pathlib
import tempfile
from datetime import datetime

import pytest

from bob3 import db
from bob3.models import FeatureReviewIssue


@pytest.fixture()
def tmp_db(monkeypatch):
    """Create a temporary database for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test.db"
        monkeypatch.setattr(db, "get_database_path", lambda: db_path)
        db.init_database(db_path=db_path)
        # Seed project, feature, and review for FK constraints
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
                "INSERT INTO review_history (id, project_id, feature_id, reviewer_id) VALUES (?, ?, ?, ?)",
                ("rev-1", "proj-1", "feat-1", "reviewer-1"),
            )
            conn.execute(
                "INSERT INTO review_history (id, project_id, feature_id, reviewer_id) VALUES (?, ?, ?, ?)",
                ("rev-2", "proj-1", "feat-1", "reviewer-2"),
            )
        yield db_path


# ============================================================
# Step 1: create_review_issue()
# ============================================================


class TestCreateReviewIssue:
    def test_creates_issue_with_required_fields(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Missing error handling",
        )
        assert isinstance(issue, FeatureReviewIssue)
        assert issue.feature_id == "feat-1"
        assert issue.review_id == "rev-1"
        assert issue.issue_description == "Missing error handling"
        assert issue.id  # Has a generated ID

    def test_default_severity_is_medium(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Some issue",
        )
        assert issue.severity == "medium"

    def test_custom_severity(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Critical flaw",
            severity="critical",
        )
        assert issue.severity == "critical"

    def test_default_resolved_is_false(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Some issue",
        )
        assert issue.resolved is False

    def test_default_resolved_at_is_none(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Some issue",
        )
        assert issue.resolved_at is None

    def test_custom_issue_id(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Some issue",
            issue_id="custom-issue-id",
        )
        assert issue.id == "custom-issue-id"

    def test_created_at_is_set(self, tmp_db):
        before = datetime.now()
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Some issue",
        )
        after = datetime.now()
        assert before <= issue.created_at <= after

    def test_persists_to_database(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Persisted issue",
            issue_id="persist-test",
        )
        fetched = db.get_review_issue("persist-test")
        assert fetched is not None
        assert fetched.id == "persist-test"
        assert fetched.issue_description == "Persisted issue"


# ============================================================
# Step 2: resolve_review_issue()
# ============================================================


class TestResolveReviewIssue:
    def test_marks_issue_as_resolved(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Fix needed",
        )
        resolved = db.resolve_review_issue(issue.id)
        assert resolved is not None
        assert resolved.resolved is True

    def test_sets_resolved_at_timestamp(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Fix needed",
        )
        before = datetime.now()
        resolved = db.resolve_review_issue(issue.id)
        after = datetime.now()
        assert resolved.resolved_at is not None
        assert before <= resolved.resolved_at <= after

    def test_sets_resolved_by_attempt(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Fix needed",
        )
        resolved = db.resolve_review_issue(issue.id, resolved_by_attempt=2)
        assert resolved.resolved_by_attempt == 2

    def test_sets_resolution_evidence(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Fix needed",
        )
        resolved = db.resolve_review_issue(
            issue.id, resolution_evidence="Added error handling in handler.py"
        )
        assert resolved.resolution_evidence == "Added error handling in handler.py"

    def test_returns_none_for_nonexistent(self, tmp_db):
        result = db.resolve_review_issue("nonexistent-id")
        assert result is None

    def test_persists_resolution(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Fix needed",
            issue_id="resolve-persist",
        )
        db.resolve_review_issue(
            "resolve-persist",
            resolved_by_attempt=3,
            resolution_evidence="Fixed it",
        )
        fetched = db.get_review_issue("resolve-persist")
        assert fetched.resolved is True
        assert fetched.resolved_at is not None
        assert fetched.resolved_by_attempt == 3
        assert fetched.resolution_evidence == "Fixed it"


# ============================================================
# Step 3: Link issues to review_id
# ============================================================


class TestIssueReviewLinking:
    def test_issues_linked_to_review(self, tmp_db):
        db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Issue A",
        )
        db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Issue B",
        )
        issues = db.get_review_issues(review_id="rev-1")
        assert len(issues) == 2
        assert all(i.review_id == "rev-1" for i in issues)

    def test_issues_scoped_to_correct_review(self, tmp_db):
        db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Issue for rev-1",
        )
        db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-2",
            issue_description="Issue for rev-2",
        )
        issues_rev1 = db.get_review_issues(review_id="rev-1")
        issues_rev2 = db.get_review_issues(review_id="rev-2")
        assert len(issues_rev1) == 1
        assert len(issues_rev2) == 1
        assert issues_rev1[0].issue_description == "Issue for rev-1"
        assert issues_rev2[0].issue_description == "Issue for rev-2"

    def test_get_issues_by_feature_id(self, tmp_db):
        db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Issue A",
        )
        db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-2",
            issue_description="Issue B",
        )
        issues = db.get_review_issues(feature_id="feat-1")
        assert len(issues) == 2
        assert all(i.feature_id == "feat-1" for i in issues)

    def test_get_issues_empty_when_none_exist(self, tmp_db):
        issues = db.get_review_issues(review_id="rev-1")
        assert issues == []


# ============================================================
# Step 4: Track severity levels
# ============================================================


class TestSeverityTracking:
    def test_low_severity(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Minor style issue",
            severity="low",
        )
        assert issue.severity == "low"

    def test_medium_severity(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Missing validation",
            severity="medium",
        )
        assert issue.severity == "medium"

    def test_high_severity(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Security vulnerability",
            severity="high",
        )
        assert issue.severity == "high"

    def test_critical_severity(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Data loss bug",
            severity="critical",
        )
        assert issue.severity == "critical"

    def test_severity_persists(self, tmp_db):
        db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="High severity issue",
            severity="high",
            issue_id="sev-test",
        )
        fetched = db.get_review_issue("sev-test")
        assert fetched.severity == "high"


# ============================================================
# Step 5: Create review with 3 issues, resolve 2, verify counts
# ============================================================


class TestIssueCountsAfterResolution:
    def test_create_three_resolve_two_verify_counts(self, tmp_db):
        # Create 3 issues for the same review
        issue1 = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Issue 1: Missing tests",
            severity="high",
        )
        issue2 = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Issue 2: No error handling",
            severity="medium",
        )
        issue3 = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Issue 3: Style violation",
            severity="low",
        )

        # Verify all 3 issues exist, none resolved
        all_issues = db.get_review_issues(review_id="rev-1")
        assert len(all_issues) == 3

        unresolved = db.get_unresolved_review_issues(review_id="rev-1")
        assert len(unresolved) == 3

        # Resolve 2 of the 3
        db.resolve_review_issue(issue1.id, resolved_by_attempt=1, resolution_evidence="Tests added")
        db.resolve_review_issue(issue2.id, resolved_by_attempt=2, resolution_evidence="Error handling added")

        # Verify counts
        all_issues = db.get_review_issues(review_id="rev-1")
        assert len(all_issues) == 3  # Total unchanged

        unresolved = db.get_unresolved_review_issues(review_id="rev-1")
        assert len(unresolved) == 1
        assert unresolved[0].id == issue3.id

        # Verify the resolved ones are marked correctly
        resolved1 = db.get_review_issue(issue1.id)
        resolved2 = db.get_review_issue(issue2.id)
        assert resolved1.resolved is True
        assert resolved2.resolved is True
        assert resolved1.resolution_evidence == "Tests added"
        assert resolved2.resolution_evidence == "Error handling added"


# ============================================================
# Step 6: Verify resolved_at timestamp is set
# ============================================================


class TestResolvedAtTimestamp:
    def test_resolved_at_set_on_resolution(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Needs fix",
        )
        assert issue.resolved_at is None

        before = datetime.now()
        resolved = db.resolve_review_issue(issue.id)
        after = datetime.now()

        assert resolved.resolved_at is not None
        assert before <= resolved.resolved_at <= after

    def test_resolved_at_persists_in_database(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Needs fix",
            issue_id="ts-persist",
        )
        before = datetime.now()
        db.resolve_review_issue("ts-persist")
        after = datetime.now()

        fetched = db.get_review_issue("ts-persist")
        assert fetched.resolved_at is not None
        assert before <= fetched.resolved_at <= after

    def test_unresolved_issue_has_no_resolved_at(self, tmp_db):
        issue = db.create_review_issue(
            feature_id="feat-1",
            review_id="rev-1",
            issue_description="Still open",
        )
        fetched = db.get_review_issue(issue.id)
        assert fetched.resolved_at is None
        assert fetched.resolved is False
