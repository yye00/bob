"""Tests for F060: Implement bug creation from RCA results.

Validates that:
- Step 1: create_bug_from_rca() function exists in db module
- Step 2: Extracts error_type and error_message from failure context
- Step 3: Stores RCA blame_target and fix_action
- Step 4: Links to titans_memory_id if lesson created in TITANS Memory
- Step 5: Integration: RCA identifies implementation bug, create bug record, verify fields
"""

import json
import pathlib

import pytest

from bob3 import db
from bob3.models import BugLedger

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
        name="F060 Test Project",
        workspace_path="/tmp/test-f060",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature within the project."""
    return db.create_feature(
        project_id=project.id,
        name="Test Feature for Bug RCA",
        description="A feature whose task fails and triggers RCA",
    )


@pytest.fixture()
def task(project, feature):
    """Create a test task within the feature."""
    return db.create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="validation",
        title="Run test suite",
        task_class="test_writing",
    )


# ===================================================================
# Step 1: create_bug_from_rca() function exists
# ===================================================================


class TestCreateBugFromRcaExists:
    """Step 1: create_bug_from_rca() function must exist and be callable."""

    def test_function_exists(self):
        assert hasattr(db, "create_bug_from_rca")
        assert callable(db.create_bug_from_rca)

    def test_returns_bug_ledger_model(self, project, feature, task):
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Missing return statement",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="AssertionError",
            error_message="expected 42 got None",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-001"]),
        )
        assert isinstance(bug, BugLedger)

    def test_generates_id(self, project):
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Bug in code",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="RuntimeError",
            error_message="something broke",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-002"]),
        )
        assert bug.id is not None
        assert len(bug.id) > 0


# ===================================================================
# Step 2: Extracts error_type and error_message from failure
# ===================================================================


class TestExtractsErrorFields:
    """Step 2: error_type and error_message are stored correctly."""

    def test_error_type_stored(self, project):
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Type mismatch",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="TypeError",
            error_message="expected str got int",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-003"]),
        )
        assert bug.error_type == "TypeError"

    def test_error_message_stored(self, project):
        rca_result = {
            "blame_target": "validation",
            "recommended_action": "fix_test",
            "root_cause": "Wrong assertion",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="AssertionError",
            error_message="assert 5 == 3",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-004"]),
        )
        assert bug.error_message == "assert 5 == 3"

    def test_error_context_stored_when_provided(self, project):
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Index error",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="IndexError",
            error_message="list index out of range",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-005"]),
            error_context="processing batch item 47 of 100",
        )
        assert bug.error_context == "processing batch item 47 of 100"

    def test_persisted_to_database(self, project):
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Bad logic",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="ValueError",
            error_message="invalid value",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-006"]),
        )
        fetched = db.get_bug(bug.id)
        assert fetched is not None
        assert fetched.error_type == "ValueError"
        assert fetched.error_message == "invalid value"


# ===================================================================
# Step 3: Stores RCA blame_target and fix_action
# ===================================================================


class TestStoresRcaFields:
    """Step 3: blame_target and fix_action from RCA result are stored."""

    def test_blame_target_from_rca(self, project):
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Off-by-one error",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="AssertionError",
            error_message="expected 10 got 9",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-007"]),
        )
        assert bug.blame_target == "implementation"

    def test_fix_action_from_recommended_action(self, project):
        rca_result = {
            "blame_target": "validation",
            "recommended_action": "fix_test",
            "root_cause": "Test expectation wrong",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="AssertionError",
            error_message="wrong expected value",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-008"]),
        )
        assert bug.fix_action == "fix_test"

    def test_root_cause_from_rca(self, project):
        rca_result = {
            "blame_target": "infrastructure",
            "recommended_action": "retry",
            "root_cause": "Network timeout during API call",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="ConnectionError",
            error_message="timeout",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-009"]),
        )
        assert bug.root_cause == "Network timeout during API call"

    def test_all_blame_targets_accepted(self, project):
        valid_targets = [
            "implementation", "validation", "feature_spec",
            "infrastructure", "external", "test_flaky",
        ]
        for target in valid_targets:
            rca_result = {
                "blame_target": target,
                "recommended_action": "fix",
                "root_cause": f"Cause for {target}",
            }
            bug = db.create_bug_from_rca(
                project_id=project.id,
                error_type="Error",
                error_message=f"msg for {target}",
                rca_result=rca_result,
                evidence_artifacts=json.dumps([f"ev-{target}"]),
            )
            fetched = db.get_bug(bug.id)
            assert fetched.blame_target == target

    def test_rca_details_stored(self, project):
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Null pointer dereference",
            "details": "Line 42 in factory.py attempts .upper() on None",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="AttributeError",
            error_message="'NoneType' has no attribute 'upper'",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-010"]),
        )
        assert bug.fix_details == "Line 42 in factory.py attempts .upper() on None"

    def test_defaults_for_missing_rca_fields(self, project):
        """When RCA result has minimal fields, defaults are used."""
        rca_result = {
            "blame_target": "unknown",
            "recommended_action": "investigate",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="Error",
            error_message="unclear error",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-011"]),
        )
        assert bug.blame_target == "unknown"
        assert bug.fix_action == "investigate"
        assert bug.root_cause is None


# ===================================================================
# Step 4: Link to titans_memory_id if lesson created
# ===================================================================


class TestTitansMemoryLink:
    """Step 4: titans_memory_id is stored when provided."""

    def test_titans_memory_id_stored(self, project):
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Logic error",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="AssertionError",
            error_message="test failed",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-012"]),
            titans_memory_id="mem_lesson_001",
        )
        assert bug.titans_memory_id == "mem_lesson_001"

    def test_titans_memory_id_none_by_default(self, project):
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Logic error",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="AssertionError",
            error_message="test failed",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-013"]),
        )
        assert bug.titans_memory_id is None

    def test_titans_memory_id_persisted(self, project):
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Logic error",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-014"]),
            titans_memory_id="mem_rca_xyz",
        )
        fetched = db.get_bug(bug.id)
        assert fetched.titans_memory_id == "mem_rca_xyz"


# ===================================================================
# Step 5: Integration: full RCA-to-bug lifecycle
# ===================================================================


class TestRcaToBugIntegration:
    """Step 5: Full integration test from RCA result to bug record."""

    def test_full_rca_to_bug_lifecycle(self, project, feature, task):
        """RCA identifies implementation bug -> create bug record -> verify all fields."""
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "create_widget() does not handle None widget_type parameter",
            "details": "Line 42 in factory.py attempts to call .upper() on widget_type without null check",
        }

        bug = db.create_bug_from_rca(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="test_failure",
            error_message="AttributeError: 'NoneType' object has no attribute 'upper'",
            error_context="FAILED tests/test_widgets.py::test_create_widget",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-trace-001", "ev-log-002"]),
            titans_memory_id="mem_lesson_widget_null",
        )

        # Verify returned model
        assert isinstance(bug, BugLedger)
        assert bug.project_id == project.id
        assert bug.feature_id == feature.id
        assert bug.task_id == task.id

        # Verify error extraction (Step 2)
        assert bug.error_type == "test_failure"
        assert bug.error_message == "AttributeError: 'NoneType' object has no attribute 'upper'"
        assert bug.error_context == "FAILED tests/test_widgets.py::test_create_widget"

        # Verify RCA fields (Step 3)
        assert bug.blame_target == "implementation"
        assert bug.fix_action == "fix_code"
        assert bug.root_cause == "create_widget() does not handle None widget_type parameter"
        assert bug.fix_details == "Line 42 in factory.py attempts to call .upper() on widget_type without null check"

        # Verify TITANS Memory link (Step 4)
        assert bug.titans_memory_id == "mem_lesson_widget_null"

        # Verify evidence artifacts
        artifacts = json.loads(bug.evidence_artifacts)
        assert "ev-trace-001" in artifacts
        assert "ev-log-002" in artifacts

        # Verify defaults
        assert bug.resolved is False
        assert bug.resolved_at is None
        assert bug.resolution_attempts == 1

        # Verify persisted to database
        fetched = db.get_bug(bug.id)
        assert fetched is not None
        assert fetched.blame_target == "implementation"
        assert fetched.fix_action == "fix_code"
        assert fetched.titans_memory_id == "mem_lesson_widget_null"

    def test_bug_from_rca_without_optional_fields(self, project):
        """Bug creation works with minimal RCA result."""
        rca_result = {
            "blame_target": "unknown",
            "recommended_action": "investigate",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="Error",
            error_message="something failed",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-minimal"]),
        )
        assert bug.blame_target == "unknown"
        assert bug.fix_action == "investigate"
        assert bug.feature_id is None
        assert bug.task_id is None
        assert bug.titans_memory_id is None
        assert bug.root_cause is None
        assert bug.fix_details is None

    def test_bug_queryable_by_project(self, project):
        """Bugs created from RCA are queryable via list_bugs."""
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Bug 1",
        }
        db.create_bug_from_rca(
            project_id=project.id,
            error_type="Error1",
            error_message="msg1",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-q1"]),
        )

        rca_result2 = {
            "blame_target": "validation",
            "recommended_action": "fix_test",
            "root_cause": "Bug 2",
        }
        db.create_bug_from_rca(
            project_id=project.id,
            error_type="Error2",
            error_message="msg2",
            rca_result=rca_result2,
            evidence_artifacts=json.dumps(["ev-q2"]),
        )

        bugs = db.list_bugs(project_id=project.id)
        assert len(bugs) == 2

    def test_bug_from_rca_can_be_resolved(self, project):
        """Bug created from RCA can be resolved via resolve_bug."""
        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Missing return",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="AssertionError",
            error_message="got None",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-resolve"]),
        )

        resolved = db.resolve_bug(bug.id, fix_evidence="All tests pass now")
        assert resolved.resolved is True
        assert resolved.fix_evidence == "All tests pass now"

    def test_bug_from_rca_with_agent_run_id(self, project, feature, task):
        """Bug can reference the agent run that produced the RCA."""
        agent_run = db.create_agent_run(
            project_id=project.id,
            purpose="rca_analyst",
            target_type="task",
            target_id=task.id,
        )

        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Logic error in handler",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="test_failure",
            error_message="AssertionError",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-agent-run", agent_run.id]),
        )

        # The agent run ID is tracked in evidence_artifacts
        artifacts = json.loads(bug.evidence_artifacts)
        assert agent_run.id in artifacts
