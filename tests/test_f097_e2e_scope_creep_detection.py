"""Tests for F097: End-to-end test - Scope creep detection.

Exercises the complete scope creep detection lifecycle:

Step 1: Create feature with 4 acceptance criteria and 5 tasks
Step 2: Store original counts
Step 3: Add 6 more criteria (total 10, growth 150%)
Step 4: Verify scope_changes record created with growth_percent=150
Step 5: Verify requires_approval=TRUE
"""

import json
import pathlib
import tempfile

import pytest

from bob3 import db
from bob3.models import ScopeChange


@pytest.fixture()
def tmp_db(monkeypatch):
    """Create a temporary database with schema initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test.db"
        monkeypatch.setattr(db, "get_database_path", lambda: db_path)
        db.init_database(db_path=db_path)
        yield db_path


# ============================================================
# Step 1: Create feature with 4 acceptance criteria and 5 tasks
# ============================================================


class TestStep1CreateFeatureWithCriteriaAndTasks:
    def test_create_feature_with_4_criteria(self, tmp_db):
        """Create a feature with exactly 4 acceptance criteria."""
        project = db.create_project(
            name="scope-creep-project",
            workspace_path="/tmp/scope-creep-ws",
        )
        criteria = json.dumps([
            "User can log in",
            "User can log out",
            "User can reset password",
            "User receives email confirmation",
        ])
        feature = db.create_feature(
            project_id=project.id,
            name="Auth Feature",
            description="Authentication system",
            acceptance_criteria=criteria,
            status="ready",
            priority=10,
        )

        parsed = json.loads(feature.acceptance_criteria)
        assert len(parsed) == 4

    def test_create_feature_with_5_tasks(self, tmp_db):
        """Create 5 tasks for the feature."""
        project = db.create_project(
            name="scope-creep-project",
            workspace_path="/tmp/scope-creep-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Auth Feature",
            acceptance_criteria=json.dumps(["c1", "c2", "c3", "c4"]),
            status="ready",
        )

        task_titles = [
            "Implement login endpoint",
            "Implement logout endpoint",
            "Implement password reset",
            "Write unit tests",
            "Write integration tests",
        ]
        for title in task_titles:
            db.create_task(
                feature_id=feature.id,
                project_id=project.id,
                type="implementation",
                title=title,
            )

        tasks = db.list_tasks(feature_id=feature.id)
        assert len(tasks) == 5


# ============================================================
# Step 2: Store original counts
# ============================================================


class TestStep2StoreOriginalCounts:
    def test_store_original_acceptance_criteria_count(self, tmp_db):
        """Store the original count of acceptance criteria on the feature."""
        project = db.create_project(
            name="scope-creep-project",
            workspace_path="/tmp/scope-creep-ws",
        )
        criteria = json.dumps(["c1", "c2", "c3", "c4"])
        feature = db.create_feature(
            project_id=project.id,
            name="Auth Feature",
            acceptance_criteria=criteria,
            status="ready",
        )
        db.update_feature(
            feature.id,
            original_acceptance_criteria_count=4,
            original_task_count=5,
        )

        updated = db.get_feature(feature.id)
        assert updated.original_acceptance_criteria_count == 4
        assert updated.original_task_count == 5


# ============================================================
# Step 3: Add 6 more criteria (total 10, growth 150%)
# ============================================================


class TestStep3AddMoreCriteria:
    def test_add_6_more_criteria_total_10(self, tmp_db):
        """Expand acceptance criteria from 4 to 10 (adding 6 more)."""
        project = db.create_project(
            name="scope-creep-project",
            workspace_path="/tmp/scope-creep-ws",
        )
        original_criteria = ["c1", "c2", "c3", "c4"]
        feature = db.create_feature(
            project_id=project.id,
            name="Auth Feature",
            acceptance_criteria=json.dumps(original_criteria),
            status="ready",
        )
        db.update_feature(
            feature.id,
            original_acceptance_criteria_count=4,
        )

        # Add 6 more criteria (total 10)
        expanded_criteria = original_criteria + [
            "c5", "c6", "c7", "c8", "c9", "c10",
        ]
        assert len(expanded_criteria) == 10
        db.update_feature(
            feature.id,
            acceptance_criteria=json.dumps(expanded_criteria),
        )

        updated = db.get_feature(feature.id)
        parsed = json.loads(updated.acceptance_criteria)
        assert len(parsed) == 10


# ============================================================
# Step 4: Verify scope_changes record created with growth_percent=150
# ============================================================


class TestStep4VerifyScopeChangeRecord:
    def test_detect_scope_change_with_150_percent_growth(self, tmp_db):
        """detect_scope_changes records a scope_change with growth_percent=150."""
        project = db.create_project(
            name="scope-creep-project",
            workspace_path="/tmp/scope-creep-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Auth Feature",
            acceptance_criteria=json.dumps(["c1", "c2", "c3", "c4"]),
            status="ready",
        )
        db.update_feature(
            feature.id,
            original_acceptance_criteria_count=4,
        )

        # Expand to 10 criteria
        db.update_feature(
            feature.id,
            acceptance_criteria=json.dumps([
                "c1", "c2", "c3", "c4",
                "c5", "c6", "c7", "c8", "c9", "c10",
            ]),
        )

        result = db.detect_scope_changes(feature_id=feature.id)
        assert result is not None
        assert isinstance(result, ScopeChange)
        assert result.change_type == "acceptance_criteria_added"
        assert result.before_value == "4"
        assert result.after_value == "10"
        # (10-4)/4 * 100 = 150%
        assert abs(result.growth_percent - 150.0) < 0.1

    def test_scope_change_persisted_to_database(self, tmp_db):
        """The scope change is persisted and retrievable via get_scope_changes."""
        project = db.create_project(
            name="scope-creep-project",
            workspace_path="/tmp/scope-creep-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Auth Feature",
            acceptance_criteria=json.dumps(["c1", "c2", "c3", "c4"]),
            status="ready",
        )
        db.update_feature(feature.id, original_acceptance_criteria_count=4)

        db.update_feature(
            feature.id,
            acceptance_criteria=json.dumps([
                "c1", "c2", "c3", "c4",
                "c5", "c6", "c7", "c8", "c9", "c10",
            ]),
        )
        db.detect_scope_changes(feature_id=feature.id)

        changes = db.get_scope_changes(feature_id=feature.id)
        assert len(changes) >= 1
        latest = changes[-1]
        assert abs(latest.growth_percent - 150.0) < 0.1
        assert latest.change_type == "acceptance_criteria_added"


# ============================================================
# Step 5: Verify requires_approval=TRUE
# ============================================================


class TestStep5VerifyRequiresApproval:
    def test_requires_approval_true_for_150_percent_growth(self, tmp_db):
        """150% growth (well above 50% threshold) sets requires_approval=True."""
        project = db.create_project(
            name="scope-creep-project",
            workspace_path="/tmp/scope-creep-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Auth Feature",
            acceptance_criteria=json.dumps(["c1", "c2", "c3", "c4"]),
            status="ready",
        )
        db.update_feature(feature.id, original_acceptance_criteria_count=4)

        db.update_feature(
            feature.id,
            acceptance_criteria=json.dumps([
                "c1", "c2", "c3", "c4",
                "c5", "c6", "c7", "c8", "c9", "c10",
            ]),
        )

        result = db.detect_scope_changes(feature_id=feature.id)
        assert result is not None
        assert result.requires_approval is True

    def test_pending_approvals_includes_this_change(self, tmp_db):
        """The detected scope change appears in pending approvals."""
        project = db.create_project(
            name="scope-creep-project",
            workspace_path="/tmp/scope-creep-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Auth Feature",
            acceptance_criteria=json.dumps(["c1", "c2", "c3", "c4"]),
            status="ready",
        )
        db.update_feature(feature.id, original_acceptance_criteria_count=4)

        db.update_feature(
            feature.id,
            acceptance_criteria=json.dumps([
                "c1", "c2", "c3", "c4",
                "c5", "c6", "c7", "c8", "c9", "c10",
            ]),
        )
        db.detect_scope_changes(feature_id=feature.id)

        pending = db.get_pending_approvals(feature_id=feature.id)
        assert len(pending) == 1
        assert pending[0].requires_approval is True
        assert pending[0].approved_by is None


# ============================================================
# Full E2E: All 5 steps in a single test
# ============================================================


class TestFullScopeCreepE2E:
    def test_complete_scope_creep_detection_lifecycle(self, tmp_db):
        """End-to-end: create feature -> store counts -> add criteria -> detect creep -> approval flagged.

        Exercises the full acceptance criteria in a single sequential workflow:
          Step 1: Create feature with 4 acceptance criteria and 5 tasks
          Step 2: Store original counts
          Step 3: Add 6 more criteria (total 10, growth 150%)
          Step 4: Verify scope_changes record created with growth_percent=150
          Step 5: Verify requires_approval=TRUE
        """
        # ---- Step 1: Create feature with 4 criteria and 5 tasks ----
        project = db.create_project(
            name="e2e-scope-creep-project",
            workspace_path="/tmp/e2e-scope-creep-ws",
        )

        original_criteria = [
            "User can log in",
            "User can log out",
            "User can reset password",
            "User receives email confirmation",
        ]
        feature = db.create_feature(
            project_id=project.id,
            name="Auth Feature E2E",
            description="Authentication system for scope creep testing",
            acceptance_criteria=json.dumps(original_criteria),
            status="ready",
            priority=10,
            risk_category="medium",
        )

        task_titles = [
            "Implement login endpoint",
            "Implement logout endpoint",
            "Implement password reset",
            "Write unit tests",
            "Write integration tests",
        ]
        for title in task_titles:
            db.create_task(
                feature_id=feature.id,
                project_id=project.id,
                type="implementation",
                title=title,
            )

        parsed_criteria = json.loads(feature.acceptance_criteria)
        assert len(parsed_criteria) == 4
        tasks = db.list_tasks(feature_id=feature.id)
        assert len(tasks) == 5

        # ---- Step 2: Store original counts ----
        db.update_feature(
            feature.id,
            original_acceptance_criteria_count=4,
            original_task_count=5,
        )

        stored = db.get_feature(feature.id)
        assert stored.original_acceptance_criteria_count == 4
        assert stored.original_task_count == 5

        # ---- Step 3: Add 6 more criteria (total 10, growth 150%) ----
        expanded_criteria = original_criteria + [
            "User can enable 2FA",
            "User can link social accounts",
            "Admin can revoke sessions",
            "Rate limiting on login attempts",
            "Audit log for all auth events",
            "User can manage API keys",
        ]
        assert len(expanded_criteria) == 10

        db.update_feature(
            feature.id,
            acceptance_criteria=json.dumps(expanded_criteria),
        )

        refreshed = db.get_feature(feature.id)
        current_criteria = json.loads(refreshed.acceptance_criteria)
        assert len(current_criteria) == 10

        # ---- Step 4: Verify scope_changes record with growth_percent=150 ----
        result = db.detect_scope_changes(feature_id=feature.id)

        assert result is not None, "Expected scope change to be detected"
        assert isinstance(result, ScopeChange)
        assert result.feature_id == feature.id
        assert result.change_type == "acceptance_criteria_added"
        assert result.before_value == "4"
        assert result.after_value == "10"
        # (10-4)/4 * 100 = 150%
        assert abs(result.growth_percent - 150.0) < 0.1, (
            f"Expected growth_percent ~150, got {result.growth_percent}"
        )

        # Verify persisted in database
        changes = db.get_scope_changes(feature_id=feature.id)
        assert len(changes) == 1
        assert abs(changes[0].growth_percent - 150.0) < 0.1

        # ---- Step 5: Verify requires_approval=TRUE ----
        assert result.requires_approval is True, (
            "150% growth (>50% threshold) must set requires_approval=True"
        )

        # Also verify via pending approvals query
        pending = db.get_pending_approvals(feature_id=feature.id)
        assert len(pending) == 1
        assert pending[0].requires_approval is True
        assert pending[0].approved_by is None

    def test_no_scope_creep_when_within_original_counts(self, tmp_db):
        """No scope change detected when criteria stay at original count."""
        project = db.create_project(
            name="no-creep-project",
            workspace_path="/tmp/no-creep-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Stable Feature",
            acceptance_criteria=json.dumps(["c1", "c2", "c3", "c4"]),
            status="ready",
        )
        db.update_feature(
            feature.id,
            original_acceptance_criteria_count=4,
            original_task_count=5,
        )

        # Create exactly 5 tasks (matches original count)
        for i in range(5):
            db.create_task(
                feature_id=feature.id,
                project_id=project.id,
                type="implementation",
                title=f"Task {i + 1}",
            )

        result = db.detect_scope_changes(feature_id=feature.id)
        assert result is None, "No scope creep should be detected"

    def test_task_scope_creep_also_detected(self, tmp_db):
        """Scope creep via task additions is also detected when criteria unchanged."""
        project = db.create_project(
            name="task-creep-project",
            workspace_path="/tmp/task-creep-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Task Creep Feature",
            acceptance_criteria=json.dumps(["c1", "c2"]),
            status="ready",
        )
        db.update_feature(
            feature.id,
            original_acceptance_criteria_count=2,
            original_task_count=2,
        )

        # Create 2 original tasks
        for i in range(2):
            db.create_task(
                feature_id=feature.id,
                project_id=project.id,
                type="implementation",
                title=f"Original task {i + 1}",
            )

        # Add 3 more tasks (total 5, growth = (5-2)/2 * 100 = 150%)
        for i in range(3):
            db.create_task(
                feature_id=feature.id,
                project_id=project.id,
                type="implementation",
                title=f"Extra task {i + 1}",
            )

        result = db.detect_scope_changes(feature_id=feature.id)
        # Criteria didn't change (2 == 2), so it checks tasks
        assert result is not None
        assert result.change_type == "task_added"
        assert abs(result.growth_percent - 150.0) < 0.1
        assert result.requires_approval is True
