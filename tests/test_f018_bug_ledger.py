"""Tests for F018: Database CRUD operations for bug_ledger table."""

import json
import pathlib
import sqlite3
from datetime import datetime

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
def project(db_path):
    """Create a test project for foreign key references."""
    from bob3.db import create_project

    return create_project(
        name="Bug Ledger Test Project",
        workspace_path="/tmp/bug-test",
    )


@pytest.fixture()
def feature(db_path, project):
    """Create a test feature for foreign key references."""
    from bob3.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Bug Ledger Test Feature",
    )


@pytest.fixture()
def task(db_path, project, feature):
    """Create a test task for foreign key references."""
    from bob3.db import create_task

    return create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="implementation",
        title="Bug Ledger Test Task",
    )


# ============================================================
# Step 1: create_bug()
# ============================================================


class TestCreateBug:
    """Step 1: create_bug() inserts a new bug_ledger entry and returns it."""

    def test_create_bug_returns_bug_model(self, project, feature, task):
        from bob3.db import create_bug
        from bob3.models import BugLedger

        bug = create_bug(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="ImportError",
            error_message="No module named 'foo'",
            evidence_artifacts=json.dumps(["ev-001"]),
            fix_action="install_dependency",
        )
        assert isinstance(bug, BugLedger)

    def test_create_bug_sets_id(self, project):
        from bob3.db import create_bug

        bug = create_bug(
            project_id=project.id,
            error_type="SyntaxError",
            error_message="invalid syntax",
            evidence_artifacts=json.dumps(["ev-002"]),
            fix_action="fix_syntax",
        )
        assert bug.id is not None
        assert len(bug.id) > 0

    def test_create_bug_persists_to_database(self, db_path, project):
        from bob3.db import create_bug

        bug = create_bug(
            project_id=project.id,
            error_type="RuntimeError",
            error_message="division by zero",
            evidence_artifacts=json.dumps(["ev-003"]),
            fix_action="add_guard",
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT error_type, error_message, fix_action FROM bug_ledger WHERE id = ?",
                (bug.id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "RuntimeError"
            assert row[1] == "division by zero"
            assert row[2] == "add_guard"
        finally:
            conn.close()

    def test_create_bug_with_all_optional_fields(self, project, feature, task):
        from bob3.db import create_bug

        bug = create_bug(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="AssertionError",
            error_message="expected 5, got 3",
            error_context="running test_calculate_sum",
            evidence_artifacts=json.dumps(["ev-004", "ev-005"]),
            blame_target="implementation",
            root_cause="Off-by-one error in loop counter",
            fix_action="fix_loop",
            fix_details="Changed range(n-1) to range(n)",
            fix_evidence="Test now passes",
            titans_memory_id="mem_abc123",
        )
        assert bug.feature_id == feature.id
        assert bug.task_id == task.id
        assert bug.error_context == "running test_calculate_sum"
        assert bug.blame_target == "implementation"
        assert bug.root_cause == "Off-by-one error in loop counter"
        assert bug.fix_details == "Changed range(n-1) to range(n)"
        assert bug.fix_evidence == "Test now passes"
        assert bug.titans_memory_id == "mem_abc123"

    def test_create_bug_without_feature_or_task(self, project):
        from bob3.db import create_bug

        bug = create_bug(
            project_id=project.id,
            error_type="ConfigError",
            error_message="missing config file",
            evidence_artifacts=json.dumps(["ev-006"]),
            fix_action="create_config",
        )
        assert bug.feature_id is None
        assert bug.task_id is None

    def test_create_bug_default_resolved_false(self, project):
        from bob3.db import create_bug

        bug = create_bug(
            project_id=project.id,
            error_type="ValueError",
            error_message="invalid input",
            evidence_artifacts=json.dumps(["ev-007"]),
            fix_action="validate_input",
        )
        assert bug.resolved is False

    def test_create_bug_default_resolution_attempts_1(self, project):
        from bob3.db import create_bug

        bug = create_bug(
            project_id=project.id,
            error_type="TypeError",
            error_message="expected str, got int",
            evidence_artifacts=json.dumps(["ev-008"]),
            fix_action="fix_type",
        )
        assert bug.resolution_attempts == 1

    def test_create_bug_sets_timestamp(self, project):
        from bob3.db import create_bug

        bug = create_bug(
            project_id=project.id,
            error_type="KeyError",
            error_message="missing key",
            evidence_artifacts=json.dumps(["ev-009"]),
            fix_action="add_key",
        )
        assert bug.created_at is not None

    def test_create_bug_with_custom_id(self, project):
        from bob3.db import create_bug

        bug = create_bug(
            project_id=project.id,
            error_type="IOError",
            error_message="file not found",
            evidence_artifacts=json.dumps(["ev-010"]),
            fix_action="create_file",
            bug_id="custom-bug-id-123",
        )
        assert bug.id == "custom-bug-id-123"


# ============================================================
# Step 2: get_bug()
# ============================================================


class TestGetBug:
    """Step 2: get_bug() retrieves a bug_ledger entry by ID."""

    def test_get_bug_returns_bug_model(self, project):
        from bob3.db import create_bug, get_bug
        from bob3.models import BugLedger

        created = create_bug(
            project_id=project.id,
            error_type="ImportError",
            error_message="no module",
            evidence_artifacts=json.dumps(["ev-011"]),
            fix_action="install",
        )
        fetched = get_bug(created.id)
        assert isinstance(fetched, BugLedger)

    def test_get_bug_has_correct_fields(self, project, feature, task):
        from bob3.db import create_bug, get_bug

        created = create_bug(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="RuntimeError",
            error_message="stack overflow",
            error_context="recursive call",
            evidence_artifacts=json.dumps(["ev-012"]),
            blame_target="implementation",
            root_cause="infinite recursion",
            fix_action="add_base_case",
        )
        fetched = get_bug(created.id)
        assert fetched.project_id == project.id
        assert fetched.feature_id == feature.id
        assert fetched.task_id == task.id
        assert fetched.error_type == "RuntimeError"
        assert fetched.error_message == "stack overflow"
        assert fetched.error_context == "recursive call"
        assert fetched.blame_target == "implementation"
        assert fetched.root_cause == "infinite recursion"
        assert fetched.fix_action == "add_base_case"

    def test_get_bug_not_found_returns_none(self, db_path):
        from bob3.db import get_bug

        result = get_bug("nonexistent-bug-id")
        assert result is None

    def test_get_bug_preserves_id(self, project):
        from bob3.db import create_bug, get_bug

        created = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-013"]),
            fix_action="fix",
        )
        fetched = get_bug(created.id)
        assert fetched.id == created.id

    def test_get_bug_boolean_resolved_field(self, project):
        from bob3.db import create_bug, get_bug

        created = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-014"]),
            fix_action="fix",
        )
        fetched = get_bug(created.id)
        assert fetched.resolved is False


# ============================================================
# Step 3: update_bug()
# ============================================================


class TestUpdateBug:
    """Step 3: update_bug() modifies existing bug_ledger fields."""

    def test_update_bug_changes_blame_target(self, project):
        from bob3.db import create_bug, get_bug, update_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-015"]),
            fix_action="fix",
        )
        update_bug(bug.id, blame_target="validation")
        fetched = get_bug(bug.id)
        assert fetched.blame_target == "validation"

    def test_update_bug_changes_root_cause(self, project):
        from bob3.db import create_bug, get_bug, update_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-016"]),
            fix_action="fix",
        )
        update_bug(bug.id, root_cause="Missing null check")
        fetched = get_bug(bug.id)
        assert fetched.root_cause == "Missing null check"

    def test_update_bug_changes_fix_details(self, project):
        from bob3.db import create_bug, get_bug, update_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-017"]),
            fix_action="fix",
        )
        update_bug(bug.id, fix_details="Added null check before dereference")
        fetched = get_bug(bug.id)
        assert fetched.fix_details == "Added null check before dereference"

    def test_update_bug_changes_resolution_attempts(self, project):
        from bob3.db import create_bug, get_bug, update_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-018"]),
            fix_action="fix",
        )
        update_bug(bug.id, resolution_attempts=3)
        fetched = get_bug(bug.id)
        assert fetched.resolution_attempts == 3

    def test_update_bug_changes_titans_memory_id(self, project):
        from bob3.db import create_bug, get_bug, update_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-019"]),
            fix_action="fix",
        )
        update_bug(bug.id, titans_memory_id="mem_xyz789")
        fetched = get_bug(bug.id)
        assert fetched.titans_memory_id == "mem_xyz789"

    def test_update_bug_returns_updated_model(self, project):
        from bob3.db import create_bug, update_bug
        from bob3.models import BugLedger

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-020"]),
            fix_action="fix",
        )
        updated = update_bug(bug.id, blame_target="infrastructure")
        assert isinstance(updated, BugLedger)
        assert updated.blame_target == "infrastructure"

    def test_update_bug_not_found_returns_none(self, db_path):
        from bob3.db import update_bug

        result = update_bug("nonexistent-id", blame_target="test")
        assert result is None

    def test_update_bug_multiple_fields(self, project):
        from bob3.db import create_bug, get_bug, update_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-021"]),
            fix_action="fix",
        )
        update_bug(
            bug.id,
            blame_target="external",
            root_cause="API changed",
            fix_details="Updated API call",
            fix_evidence="Integration test passes",
            resolution_attempts=2,
        )
        fetched = get_bug(bug.id)
        assert fetched.blame_target == "external"
        assert fetched.root_cause == "API changed"
        assert fetched.fix_details == "Updated API call"
        assert fetched.fix_evidence == "Integration test passes"
        assert fetched.resolution_attempts == 2


# ============================================================
# Step 4: resolve_bug()
# ============================================================


class TestResolveBug:
    """Step 4: resolve_bug() marks a bug as resolved with timestamp."""

    def test_resolve_bug_sets_resolved_true(self, project):
        from bob3.db import create_bug, get_bug, resolve_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-022"]),
            fix_action="fix",
        )
        resolve_bug(bug.id)
        fetched = get_bug(bug.id)
        assert fetched.resolved is True

    def test_resolve_bug_sets_resolved_at_timestamp(self, project):
        from bob3.db import create_bug, get_bug, resolve_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-023"]),
            fix_action="fix",
        )
        resolve_bug(bug.id)
        fetched = get_bug(bug.id)
        assert fetched.resolved_at is not None
        assert isinstance(fetched.resolved_at, datetime)

    def test_resolve_bug_returns_updated_model(self, project):
        from bob3.db import create_bug, resolve_bug
        from bob3.models import BugLedger

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-024"]),
            fix_action="fix",
        )
        result = resolve_bug(bug.id)
        assert isinstance(result, BugLedger)
        assert result.resolved is True

    def test_resolve_bug_not_found_returns_none(self, db_path):
        from bob3.db import resolve_bug

        result = resolve_bug("nonexistent-id")
        assert result is None

    def test_resolve_bug_with_fix_evidence(self, project):
        from bob3.db import create_bug, get_bug, resolve_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-025"]),
            fix_action="fix",
        )
        resolve_bug(bug.id, fix_evidence="All tests pass after fix")
        fetched = get_bug(bug.id)
        assert fetched.resolved is True
        assert fetched.fix_evidence == "All tests pass after fix"

    def test_resolve_bug_with_titans_memory_id(self, project):
        from bob3.db import create_bug, get_bug, resolve_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-026"]),
            fix_action="fix",
        )
        resolve_bug(bug.id, titans_memory_id="mem_lesson_001")
        fetched = get_bug(bug.id)
        assert fetched.resolved is True
        assert fetched.titans_memory_id == "mem_lesson_001"


# ============================================================
# Step 5: Bug tracking lifecycle
# ============================================================


class TestBugLifecycle:
    """Step 5: Full bug tracking lifecycle from creation to resolution."""

    def test_full_lifecycle(self, project, feature, task):
        from bob3.db import create_bug, get_bug, update_bug, resolve_bug

        # 1. Create bug
        bug = create_bug(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="AssertionError",
            error_message="test_calculate failed",
            evidence_artifacts=json.dumps(["ev-030"]),
            fix_action="investigate",
        )
        assert bug.resolved is False
        assert bug.resolved_at is None

        # 2. Update with RCA results
        update_bug(
            bug.id,
            blame_target="implementation",
            root_cause="Integer overflow in accumulator",
            fix_action="use_bigint",
            fix_details="Switch from int32 to int64",
        )
        fetched = get_bug(bug.id)
        assert fetched.blame_target == "implementation"
        assert fetched.root_cause == "Integer overflow in accumulator"

        # 3. Resolve
        resolve_bug(bug.id, fix_evidence="All 15 tests now pass")
        fetched = get_bug(bug.id)
        assert fetched.resolved is True
        assert fetched.resolved_at is not None
        assert fetched.fix_evidence == "All 15 tests now pass"

    def test_list_bugs_by_project(self, project):
        from bob3.db import create_bug, list_bugs

        create_bug(
            project_id=project.id,
            error_type="Error1",
            error_message="msg1",
            evidence_artifacts=json.dumps(["ev-031"]),
            fix_action="fix1",
        )
        create_bug(
            project_id=project.id,
            error_type="Error2",
            error_message="msg2",
            evidence_artifacts=json.dumps(["ev-032"]),
            fix_action="fix2",
        )

        bugs = list_bugs(project_id=project.id)
        assert len(bugs) == 2

    def test_list_bugs_filter_resolved(self, project):
        from bob3.db import create_bug, resolve_bug, list_bugs

        bug1 = create_bug(
            project_id=project.id,
            error_type="Error1",
            error_message="msg1",
            evidence_artifacts=json.dumps(["ev-033"]),
            fix_action="fix1",
        )
        create_bug(
            project_id=project.id,
            error_type="Error2",
            error_message="msg2",
            evidence_artifacts=json.dumps(["ev-034"]),
            fix_action="fix2",
        )
        resolve_bug(bug1.id)

        unresolved = list_bugs(project_id=project.id, resolved=False)
        assert len(unresolved) == 1
        assert unresolved[0].error_type == "Error2"

        resolved = list_bugs(project_id=project.id, resolved=True)
        assert len(resolved) == 1
        assert resolved[0].error_type == "Error1"

    def test_list_bugs_empty(self, project):
        from bob3.db import list_bugs

        bugs = list_bugs(project_id=project.id)
        assert bugs == []

    def test_multiple_resolution_attempts(self, project):
        from bob3.db import create_bug, update_bug, get_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="flaky",
            evidence_artifacts=json.dumps(["ev-035"]),
            fix_action="retry",
        )
        # First attempt failed, increment
        update_bug(bug.id, resolution_attempts=2)
        # Second attempt also failed
        update_bug(bug.id, resolution_attempts=3)

        fetched = get_bug(bug.id)
        assert fetched.resolution_attempts == 3


# ============================================================
# Step 6: RCA fields are stored correctly
# ============================================================


class TestRCAFields:
    """Step 6: Verify RCA fields are stored and retrieved correctly."""

    def test_all_blame_targets(self, project):
        from bob3.db import create_bug, get_bug

        valid_targets = [
            "implementation", "validation", "feature_spec",
            "infrastructure", "external", "test_flaky",
        ]
        for target in valid_targets:
            bug = create_bug(
                project_id=project.id,
                error_type="Error",
                error_message=f"blame={target}",
                evidence_artifacts=json.dumps([f"ev-{target}"]),
                fix_action="fix",
                blame_target=target,
            )
            fetched = get_bug(bug.id)
            assert fetched.blame_target == target

    def test_rca_root_cause_preserved(self, project):
        from bob3.db import create_bug, get_bug

        long_root_cause = (
            "The system failed because the database connection pool was "
            "exhausted due to a connection leak in the retry handler. Each "
            "retry opened a new connection without closing the previous one."
        )
        bug = create_bug(
            project_id=project.id,
            error_type="ConnectionError",
            error_message="pool exhausted",
            evidence_artifacts=json.dumps(["ev-rca-001"]),
            fix_action="fix_connection_leak",
            root_cause=long_root_cause,
        )
        fetched = get_bug(bug.id)
        assert fetched.root_cause == long_root_cause

    def test_rca_fix_action_and_details(self, project):
        from bob3.db import create_bug, get_bug

        bug = create_bug(
            project_id=project.id,
            error_type="MemoryError",
            error_message="out of memory",
            evidence_artifacts=json.dumps(["ev-rca-002"]),
            fix_action="optimize_memory",
            fix_details="Use streaming iterator instead of loading all records into memory",
        )
        fetched = get_bug(bug.id)
        assert fetched.fix_action == "optimize_memory"
        assert fetched.fix_details == "Use streaming iterator instead of loading all records into memory"

    def test_evidence_artifacts_json_array(self, project):
        from bob3.db import create_bug, get_bug

        artifacts = ["ev-001", "ev-002", "ev-003"]
        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="multi evidence",
            evidence_artifacts=json.dumps(artifacts),
            fix_action="fix",
        )
        fetched = get_bug(bug.id)
        assert json.loads(fetched.evidence_artifacts) == artifacts

    def test_titans_memory_id_linkage(self, project):
        from bob3.db import create_bug, get_bug, resolve_bug

        bug = create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="test",
            evidence_artifacts=json.dumps(["ev-rca-003"]),
            fix_action="fix",
        )
        resolve_bug(bug.id, titans_memory_id="mem_lesson_from_rca")
        fetched = get_bug(bug.id)
        assert fetched.titans_memory_id == "mem_lesson_from_rca"
