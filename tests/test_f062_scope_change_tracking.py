"""Tests for F062: Scope change tracking (acceptance criteria, tasks).

Validates that:
- Step 1: record_scope_change() function exists and works
- Step 2: Detect when acceptance_criteria or tasks are added to feature
- Step 3: Calculate growth_percent
- Step 4: Flag requires_approval if growth > 50%
- Step 5: Add 5 criteria to feature with 3 original, verify 67% growth flagged
"""

import json
import pathlib

import pytest

from bob3 import db
from bob3.models import ScopeChange

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project."""
    return db.create_project(
        name="F062 Test Project",
        workspace_path="/tmp/test-f062",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature with 3 original acceptance criteria."""
    original_criteria = json.dumps(["criterion_1", "criterion_2", "criterion_3"])
    f = db.create_feature(
        project_id=project.id,
        name="Scope Tracking Test Feature",
        description="Feature for testing scope change tracking",
        acceptance_criteria=original_criteria,
    )
    # Set the original counts
    db.update_feature(
        f.id,
        original_acceptance_criteria_count=3,
        original_task_count=0,
    )
    return db.get_feature(f.id)


@pytest.fixture()
def feature_with_tasks(project):
    """Create a test feature with 2 original tasks."""
    f = db.create_feature(
        project_id=project.id,
        name="Task Scope Feature",
        description="Feature for testing task scope tracking",
    )
    db.update_feature(f.id, original_task_count=2)
    # Create 2 original tasks
    db.create_task(
        feature_id=f.id,
        project_id=project.id,
        type="implementation",
        title="Original task 1",
    )
    db.create_task(
        feature_id=f.id,
        project_id=project.id,
        type="implementation",
        title="Original task 2",
    )
    return db.get_feature(f.id)


# ===================================================================
# Step 1: record_scope_change() function exists and works
# ===================================================================


class TestRecordScopeChangeExists:
    """Step 1: record_scope_change() must exist and create scope_changes rows."""

    def test_function_exists(self):
        assert hasattr(db, "record_scope_change")
        assert callable(db.record_scope_change)

    def test_creates_scope_change_record(self, feature):
        sc = db.record_scope_change(
            feature_id=feature.id,
            change_type="acceptance_criteria_added",
            before_value="3",
            after_value="5",
            growth_percent=66.67,
        )
        assert isinstance(sc, ScopeChange)
        assert sc.feature_id == feature.id
        assert sc.change_type == "acceptance_criteria_added"

    def test_returns_scope_change_with_id(self, feature):
        sc = db.record_scope_change(
            feature_id=feature.id,
            change_type="task_added",
            before_value="2",
            after_value="4",
            growth_percent=100.0,
        )
        assert sc.id is not None
        assert len(sc.id) > 0

    def test_stores_before_and_after_values(self, feature):
        sc = db.record_scope_change(
            feature_id=feature.id,
            change_type="acceptance_criteria_added",
            before_value="3",
            after_value="5",
            growth_percent=66.67,
        )
        assert sc.before_value == "3"
        assert sc.after_value == "5"

    def test_stores_growth_percent(self, feature):
        sc = db.record_scope_change(
            feature_id=feature.id,
            change_type="acceptance_criteria_added",
            before_value="3",
            after_value="5",
            growth_percent=66.67,
        )
        assert abs(sc.growth_percent - 66.67) < 0.01


# ===================================================================
# Step 2: Detect when acceptance_criteria or tasks are added
# ===================================================================


class TestDetectScopeChanges:
    """Step 2: detect_scope_changes() detects additions to criteria or tasks."""

    def test_function_exists(self):
        assert hasattr(db, "detect_scope_changes")
        assert callable(db.detect_scope_changes)

    def test_detects_criteria_addition(self, feature):
        """When acceptance criteria count exceeds original, detect the change."""
        # Update the feature with more criteria (5 instead of original 3)
        new_criteria = json.dumps([
            "criterion_1", "criterion_2", "criterion_3",
            "criterion_4", "criterion_5",
        ])
        db.update_feature(feature.id, acceptance_criteria=new_criteria)

        result = db.detect_scope_changes(feature_id=feature.id)
        assert result is not None
        assert result.change_type == "acceptance_criteria_added"

    def test_detects_task_addition(self, project, feature_with_tasks):
        """When task count exceeds original, detect the change."""
        # Add a new task (3rd task, original was 2)
        db.create_task(
            feature_id=feature_with_tasks.id,
            project_id=project.id,
            type="implementation",
            title="New extra task",
        )

        result = db.detect_scope_changes(feature_id=feature_with_tasks.id)
        assert result is not None
        assert result.change_type == "task_added"

    def test_no_change_when_within_original_count(self, feature):
        """When criteria count is at original, no change detected."""
        result = db.detect_scope_changes(feature_id=feature.id)
        assert result is None

    def test_no_change_when_no_original_count(self, project):
        """When original counts are not set, no change detected."""
        f = db.create_feature(
            project_id=project.id,
            name="No originals feature",
        )
        result = db.detect_scope_changes(feature_id=f.id)
        assert result is None

    def test_returns_none_for_nonexistent_feature(self):
        result = db.detect_scope_changes(feature_id="nonexistent-id")
        assert result is None


# ===================================================================
# Step 3: Calculate growth_percent
# ===================================================================


class TestGrowthPercentCalculation:
    """Step 3: growth_percent is calculated correctly."""

    def test_growth_percent_from_3_to_5_criteria(self, feature):
        """3 original, 5 current => (5-3)/3 * 100 = 66.67%."""
        new_criteria = json.dumps([
            "criterion_1", "criterion_2", "criterion_3",
            "criterion_4", "criterion_5",
        ])
        db.update_feature(feature.id, acceptance_criteria=new_criteria)

        result = db.detect_scope_changes(feature_id=feature.id)
        assert result is not None
        # (5-3)/3 * 100 = 66.67
        assert abs(result.growth_percent - 66.67) < 0.1

    def test_growth_percent_100_for_doubled_tasks(self, project, feature_with_tasks):
        """2 original, 4 current => (4-2)/2 * 100 = 100%."""
        db.create_task(
            feature_id=feature_with_tasks.id,
            project_id=project.id,
            type="implementation",
            title="Extra task 1",
        )
        db.create_task(
            feature_id=feature_with_tasks.id,
            project_id=project.id,
            type="implementation",
            title="Extra task 2",
        )

        result = db.detect_scope_changes(feature_id=feature_with_tasks.id)
        assert result is not None
        assert abs(result.growth_percent - 100.0) < 0.1

    def test_growth_zero_when_no_change(self, feature):
        """No growth when current matches original."""
        result = db.detect_scope_changes(feature_id=feature.id)
        assert result is None


# ===================================================================
# Step 4: Flag requires_approval if growth > 50%
# ===================================================================


class TestRequiresApprovalFlag:
    """Step 4: requires_approval is set to True when growth > 50%."""

    def test_flagged_when_growth_over_50_percent(self, feature):
        """Growth of 66.67% (3->5) should flag requires_approval."""
        new_criteria = json.dumps([
            "criterion_1", "criterion_2", "criterion_3",
            "criterion_4", "criterion_5",
        ])
        db.update_feature(feature.id, acceptance_criteria=new_criteria)

        result = db.detect_scope_changes(feature_id=feature.id)
        assert result is not None
        assert result.requires_approval is True

    def test_not_flagged_when_growth_under_50_percent(self, project):
        """Growth of 33% (3->4) should NOT flag requires_approval."""
        f = db.create_feature(
            project_id=project.id,
            name="Small growth feature",
            acceptance_criteria=json.dumps(["c1", "c2", "c3"]),
        )
        db.update_feature(f.id, original_acceptance_criteria_count=3)

        # Add 1 criterion (3->4 = 33%)
        db.update_feature(
            f.id,
            acceptance_criteria=json.dumps(["c1", "c2", "c3", "c4"]),
        )

        result = db.detect_scope_changes(feature_id=f.id)
        assert result is not None
        assert result.requires_approval is False

    def test_flagged_at_exactly_51_percent(self, feature):
        """Growth of exactly 51% should flag requires_approval."""
        sc = db.record_scope_change(
            feature_id=feature.id,
            change_type="acceptance_criteria_added",
            before_value="100",
            after_value="151",
            growth_percent=51.0,
            requires_approval=True,
        )
        assert sc.requires_approval is True

    def test_not_flagged_at_exactly_50_percent(self, feature):
        """Growth of exactly 50% should NOT flag requires_approval."""
        sc = db.record_scope_change(
            feature_id=feature.id,
            change_type="task_added",
            before_value="2",
            after_value="3",
            growth_percent=50.0,
            requires_approval=False,
        )
        assert sc.requires_approval is False

    def test_flagged_for_task_growth_over_50(self, project, feature_with_tasks):
        """Task growth from 2 to 4 (100%) should flag requires_approval."""
        db.create_task(
            feature_id=feature_with_tasks.id,
            project_id=project.id,
            type="implementation",
            title="Extra task 1",
        )
        db.create_task(
            feature_id=feature_with_tasks.id,
            project_id=project.id,
            type="implementation",
            title="Extra task 2",
        )

        result = db.detect_scope_changes(feature_id=feature_with_tasks.id)
        assert result is not None
        assert result.requires_approval is True


# ===================================================================
# Step 5: Add 5 criteria to feature with 3 original, verify 67% flagged
# ===================================================================


class TestAcceptanceCriteriaIntegration:
    """Step 5: Full integration test - 3 original + 2 added = 67% growth, flagged."""

    def test_5_criteria_with_3_original_flagged(self, feature):
        """Feature starts with 3 criteria. After adding 2 more (total 5),
        growth is (5-3)/3 * 100 = 66.67%, which exceeds 50% threshold."""
        # Feature fixture already has 3 original criteria and original count set to 3
        assert feature.original_acceptance_criteria_count == 3

        # Update to 5 acceptance criteria
        new_criteria = json.dumps([
            "criterion_1", "criterion_2", "criterion_3",
            "criterion_4", "criterion_5",
        ])
        db.update_feature(feature.id, acceptance_criteria=new_criteria)

        # Detect scope change
        result = db.detect_scope_changes(feature_id=feature.id)

        # Verify detection
        assert result is not None
        assert result.change_type == "acceptance_criteria_added"

        # Verify growth percent ~ 66.67%
        assert result.growth_percent > 66
        assert result.growth_percent < 68

        # Verify flagged for approval
        assert result.requires_approval is True

        # Verify it was persisted to DB
        changes = db.get_scope_changes(feature_id=feature.id)
        assert len(changes) >= 1
        latest = changes[-1]
        assert latest.requires_approval is True
        assert latest.growth_percent > 66

    def test_get_scope_changes_returns_all_for_feature(self, feature):
        """get_scope_changes returns all scope changes for a feature."""
        db.record_scope_change(
            feature_id=feature.id,
            change_type="acceptance_criteria_added",
            before_value="3",
            after_value="4",
            growth_percent=33.33,
        )
        db.record_scope_change(
            feature_id=feature.id,
            change_type="task_added",
            before_value="0",
            after_value="2",
            growth_percent=200.0,
            requires_approval=True,
        )

        changes = db.get_scope_changes(feature_id=feature.id)
        assert len(changes) == 2
        assert all(isinstance(c, ScopeChange) for c in changes)

    def test_get_scope_changes_empty_for_no_changes(self, project):
        """No scope changes returns empty list."""
        f = db.create_feature(
            project_id=project.id,
            name="Clean feature",
        )
        changes = db.get_scope_changes(feature_id=f.id)
        assert changes == []

    def test_get_pending_approvals(self, feature):
        """get_pending_approvals returns only unapproved scope changes > 50% growth."""
        db.record_scope_change(
            feature_id=feature.id,
            change_type="acceptance_criteria_added",
            before_value="3",
            after_value="5",
            growth_percent=66.67,
            requires_approval=True,
        )
        db.record_scope_change(
            feature_id=feature.id,
            change_type="task_added",
            before_value="0",
            after_value="1",
            growth_percent=10.0,
        )

        pending = db.get_pending_approvals(feature_id=feature.id)
        assert len(pending) == 1
        assert pending[0].requires_approval is True
        assert pending[0].approved_by is None

    def test_approve_scope_change(self, feature):
        """approve_scope_change marks a scope change as approved."""
        sc = db.record_scope_change(
            feature_id=feature.id,
            change_type="acceptance_criteria_added",
            before_value="3",
            after_value="5",
            growth_percent=66.67,
            requires_approval=True,
        )

        approved = db.approve_scope_change(
            scope_change_id=sc.id,
            approved_by="human_reviewer",
        )
        assert approved is not None
        assert approved.approved_by == "human_reviewer"
        assert approved.approved_at is not None
