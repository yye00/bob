"""Tests for F051: Implement regression detection when tests start failing."""

import json
import pathlib

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
        name="Regression Detection Test",
        workspace_path="/tmp/regression-test",
    )


@pytest.fixture()
def feature_a(project):
    """Create feature A (the feature whose tests will be broken)."""
    from bob3.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Feature A",
        status="completed",
    )


@pytest.fixture()
def feature_b(project):
    """Create feature B (the feature that causes the regression)."""
    from bob3.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Feature B",
        status="executing",
    )


@pytest.fixture()
def task_a(project, feature_a):
    """Create a validation task for feature A."""
    from bob3.db import create_task

    return create_task(
        project_id=project.id,
        feature_id=feature_a.id,
        type="validation",
        title="Test Feature A",
        status="completed",
    )


@pytest.fixture()
def task_b(project, feature_b):
    """Create an implementation task for feature B."""
    from bob3.db import create_task

    return create_task(
        project_id=project.id,
        feature_id=feature_b.id,
        type="implementation",
        title="Implement Feature B",
        status="completed",
    )


# ============================================================
# Step 1: Add detect_regression() function
# ============================================================


class TestDetectRegressionExists:
    """Step 1: detect_regression() is importable and callable."""

    def test_function_is_importable(self, db_path):
        from bob3.db import detect_regression

        assert callable(detect_regression)

    def test_returns_regression_event_or_none(self, project, feature_a, feature_b, task_a):
        from bob3.db import detect_regression

        # No regression when results match
        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True, "test_a_2": True},
            after_results={"test_a_1": True, "test_a_2": True},
        )
        assert result is None


# ============================================================
# Step 2: Compare test results before/after feature implementation
# ============================================================


class TestCompareTestResults:
    """Step 2: Compare test results before and after feature implementation."""

    def test_no_regression_when_all_still_pass(self, project, feature_a, feature_b, task_a):
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True, "test_a_2": True},
            after_results={"test_a_1": True, "test_a_2": True},
        )
        assert result is None

    def test_regression_detected_when_test_starts_failing(self, project, feature_a, feature_b, task_a):
        from bob3.db import detect_regression
        from bob3.models import RegressionEvent

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True, "test_a_2": True},
            after_results={"test_a_1": False, "test_a_2": True},
        )
        assert result is not None
        assert isinstance(result, RegressionEvent)

    def test_no_regression_for_newly_added_failing_tests(self, project, feature_a, feature_b, task_a):
        """A test that wasn't in before_results is new, not a regression."""
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True},
            after_results={"test_a_1": True, "test_b_new": False},
        )
        assert result is None

    def test_no_regression_when_previously_failing_still_fails(self, project, feature_a, feature_b, task_a):
        """Tests that were already failing should not be counted as regressions."""
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": False, "test_a_2": True},
            after_results={"test_a_1": False, "test_a_2": True},
        )
        assert result is None


# ============================================================
# Step 3: Identify affected tests and causing feature
# ============================================================


class TestIdentifyAffectedTestsAndCause:
    """Step 3: Identify the affected tests and the causing feature."""

    def test_affected_tests_listed_in_regression_event(self, project, feature_a, feature_b, task_a):
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True, "test_a_2": True, "test_a_3": True},
            after_results={"test_a_1": False, "test_a_2": True, "test_a_3": False},
        )
        assert result is not None
        affected = json.loads(result.affected_tests)
        assert sorted(affected) == ["test_a_1", "test_a_3"]

    def test_causing_feature_is_recorded(self, project, feature_a, feature_b, task_a):
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True},
            after_results={"test_a_1": False},
        )
        assert result is not None
        assert result.causing_feature_id == feature_b.id

    def test_affected_feature_determined_from_failing_tests(self, project, feature_a, feature_b, task_a):
        """detect_regression should map failing tests back to their feature."""
        from bob3.db import detect_regression

        # task_a belongs to feature_a, and its test is in before_results
        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True},
            after_results={"test_a_1": False},
            test_to_feature_map={"test_a_1": feature_a.id},
        )
        assert result is not None
        assert result.affected_feature_id == feature_a.id


# ============================================================
# Step 4: Create regression_events record
# ============================================================


class TestCreateRegressionEventsRecord:
    """Step 4: Regression event is stored in the regression_events table."""

    def test_regression_event_persisted_in_database(self, project, feature_a, feature_b, task_a):
        from bob3.db import connect, detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True},
            after_results={"test_a_1": False},
            test_to_feature_map={"test_a_1": feature_a.id},
        )
        assert result is not None

        with connect() as conn:
            cursor = conn.execute(
                "SELECT id, project_id, affected_feature_id, causing_feature_id, "
                "affected_tests, status FROM regression_events WHERE id = ?",
                (result.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == result.id
        assert row[1] == project.id
        assert row[2] == feature_a.id
        assert row[3] == feature_b.id
        assert "test_a_1" in row[4]
        assert row[5] == "detected"

    def test_regression_event_has_detected_status(self, project, feature_a, feature_b, task_a):
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True},
            after_results={"test_a_1": False},
            test_to_feature_map={"test_a_1": feature_a.id},
        )
        assert result is not None
        assert result.status == "detected"

    def test_regression_event_has_detected_at_timestamp(self, project, feature_a, feature_b, task_a):
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True},
            after_results={"test_a_1": False},
            test_to_feature_map={"test_a_1": feature_a.id},
        )
        assert result is not None
        assert result.detected_at is not None

    def test_create_regression_event_directly(self, project, feature_a, feature_b):
        """Test the lower-level create_regression_event function."""
        from bob3.db import create_regression_event
        from bob3.models import RegressionEvent

        event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_1", "test_2"]),
        )
        assert isinstance(event, RegressionEvent)
        assert event.project_id == project.id
        assert event.affected_feature_id == feature_a.id
        assert event.causing_feature_id == feature_b.id
        assert event.status == "detected"

    def test_get_regression_event(self, project, feature_a, feature_b):
        """Test retrieval of a regression event by ID."""
        from bob3.db import create_regression_event, get_regression_event

        event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_1"]),
        )
        fetched = get_regression_event(event.id)
        assert fetched is not None
        assert fetched.id == event.id
        assert fetched.causing_feature_id == feature_b.id

    def test_update_regression_event_status(self, project, feature_a, feature_b):
        """Test updating a regression event's status."""
        from bob3.db import create_regression_event, update_regression_event

        event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_1"]),
        )
        updated = update_regression_event(event.id, status="investigating")
        assert updated is not None
        assert updated.status == "investigating"

    def test_list_active_regressions(self, project, feature_a, feature_b):
        """Test listing active (unresolved) regressions."""
        from bob3.db import create_regression_event, list_regression_events, update_regression_event

        event1 = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_1"]),
        )
        event2 = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_2"]),
        )
        # Resolve event1
        update_regression_event(event1.id, status="resolved", resolution="Fixed in code")

        active = list_regression_events(project_id=project.id, active_only=True)
        assert len(active) == 1
        assert active[0].id == event2.id


# ============================================================
# Step 5: Test: Implement feature B that breaks feature A's tests
# ============================================================


class TestFeatureBBreaksFeatureA:
    """Step 5: Simulate feature B breaking feature A's tests."""

    def test_feature_b_causes_regression_in_feature_a(self, project, feature_a, feature_b, task_a):
        from bob3.db import detect_regression

        # Before feature B: feature A's tests all pass
        before = {"test_feature_a_unit_1": True, "test_feature_a_unit_2": True, "test_feature_a_integration": True}

        # After feature B: some of feature A's tests fail
        after = {"test_feature_a_unit_1": True, "test_feature_a_unit_2": False, "test_feature_a_integration": False}

        test_to_feature = {
            "test_feature_a_unit_1": feature_a.id,
            "test_feature_a_unit_2": feature_a.id,
            "test_feature_a_integration": feature_a.id,
        }

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before,
            after_results=after,
            test_to_feature_map=test_to_feature,
        )

        assert result is not None
        affected = json.loads(result.affected_tests)
        assert len(affected) == 2
        assert "test_feature_a_unit_2" in affected
        assert "test_feature_a_integration" in affected

    def test_affected_feature_is_feature_a(self, project, feature_a, feature_b, task_a):
        from bob3.db import detect_regression

        before = {"test_a_check": True}
        after = {"test_a_check": False}
        test_to_feature = {"test_a_check": feature_a.id}

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before,
            after_results=after,
            test_to_feature_map=test_to_feature,
        )
        assert result is not None
        assert result.affected_feature_id == feature_a.id
        assert result.causing_feature_id == feature_b.id


# ============================================================
# Step 6: Verify regression event is created linking B as cause
#         and A as affected
# ============================================================


class TestRegressionEventLinksBCauseAAffected:
    """Step 6: Verify the regression event correctly links cause and affected features."""

    def test_regression_links_b_as_cause_a_as_affected(self, project, feature_a, feature_b, task_a):
        from bob3.db import connect, detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True, "test_a_2": True},
            after_results={"test_a_1": False, "test_a_2": True},
            test_to_feature_map={"test_a_1": feature_a.id, "test_a_2": feature_a.id},
        )

        assert result is not None
        assert result.causing_feature_id == feature_b.id
        assert result.affected_feature_id == feature_a.id

        # Verify persisted in database
        with connect() as conn:
            cursor = conn.execute(
                "SELECT causing_feature_id, affected_feature_id "
                "FROM regression_events WHERE id = ?",
                (result.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == feature_b.id
        assert row[1] == feature_a.id

    def test_affected_feature_updated_to_regression_status(self, project, feature_a, feature_b, task_a):
        """After detecting regression, the affected feature's status should be 'regression'."""
        from bob3.db import detect_regression, get_feature

        detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True},
            after_results={"test_a_1": False},
            test_to_feature_map={"test_a_1": feature_a.id},
        )

        updated_feature = get_feature(feature_a.id)
        assert updated_feature is not None
        assert updated_feature.status == "regression"

    def test_full_end_to_end_regression_scenario(self, project, feature_a, feature_b, task_a):
        """Full E2E: Feature B breaks Feature A's tests, regression detected and stored."""
        from bob3.db import connect, detect_regression, get_feature, list_regression_events

        # Run detect_regression
        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True, "test_a_2": True, "test_a_3": True},
            after_results={"test_a_1": False, "test_a_2": True, "test_a_3": False},
            test_to_feature_map={
                "test_a_1": feature_a.id,
                "test_a_2": feature_a.id,
                "test_a_3": feature_a.id,
            },
        )

        # 1. RegressionEvent was created
        assert result is not None

        # 2. Affected tests are correctly identified
        affected = json.loads(result.affected_tests)
        assert sorted(affected) == ["test_a_1", "test_a_3"]

        # 3. Cause is feature B
        assert result.causing_feature_id == feature_b.id

        # 4. Affected is feature A
        assert result.affected_feature_id == feature_a.id

        # 5. Status is 'detected'
        assert result.status == "detected"

        # 6. Persisted in database and queryable
        active = list_regression_events(project_id=project.id, active_only=True)
        assert any(e.id == result.id for e in active)

        # 7. Feature A's status was updated
        updated_a = get_feature(feature_a.id)
        assert updated_a.status == "regression"

        # 8. Verify raw database record
        with connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM regression_events WHERE project_id = ?",
                (project.id,),
            )
            count = cursor.fetchone()[0]
        assert count == 1


# ============================================================
# R4-003: Regression detection must be WIRED IN to the orchestrator.
#
# Before this fix, ``db.detect_regression`` existed and was thoroughly
# tested in isolation but was NEVER called by the orchestrator's
# ``execute_feature``. As a result the ``regression_events`` table was
# always empty in production and ``show-regressions`` was vacuous.
#
# These tests drive the orchestrator end-to-end (with mocked sub-agents
# and a controllable pytest snapshot helper) and verify that:
#   1. capture_pytest_snapshot is called before AND after the sub-agent.
#   2. db.detect_regression is invoked with both snapshots and the
#      causing feature ID.
#   3. When a regression is found, an evidence row of type
#      ``regression_detected`` is written.
# ============================================================


class TestRegressionDetectionWiredIntoOrchestrator:
    """R4-003: db.detect_regression must be called from execute_feature."""

    @pytest.mark.asyncio
    async def test_orchestrator_calls_detect_regression_on_success(
        self, project
    ):
        """execute_feature must capture before/after snapshots and call
        db.detect_regression on the success path."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            get_feature,
            list_regression_events,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import OrchestrationLoop

        # Pre-existing completed feature whose tests will start failing.
        prior = create_feature(
            project_id=project.id,
            name="Prior feature",
            status="completed",
        )
        # The feature being implemented; setting readiness_score=0.9 so it
        # passes the gating checks if anything looks at them.
        f = create_feature(
            project_id=project.id,
            name="Causes regression",
            description="will break tests/test_a.py::test_x",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=project.id, workspace="/tmp/w")

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="done",
                is_error=False,
                duration_ms=100,
                num_turns=2,
                total_cost_usd=0.10,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        # Snapshots: before all green, after one test fails.
        snapshots = [
            {"tests/test_a.py::test_x": True, "tests/test_a.py::test_y": True},
            {"tests/test_a.py::test_x": False, "tests/test_a.py::test_y": True},
        ]
        snapshot_iter = iter(snapshots)

        def fake_capture(*_args, **_kwargs):
            try:
                return next(snapshot_iter)
            except StopIteration:
                return None

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ), patch(
            "bob3.orchestrator.run_loop.capture_pytest_snapshot",
            side_effect=fake_capture,
        ), patch(
            "bob3.orchestrator.run_loop.run_verification_checklist",
            return_value={"passed": True, "summary": "ok", "checks": []},
        ), patch(
            "bob3.orchestrator.run_loop.git_commit_feature",
            return_value="deadbeef",
        ), patch(
            "bob3.orchestrator.run_loop.git_get_status",
            return_value={"sha": "abc123"},
        ):
            await loop.execute_feature(feature)

        events = list_regression_events(project_id=project.id)
        assert len(events) == 1, (
            "execute_feature must call db.detect_regression on the success "
            "path; regression_events table is empty (R4-003 wire-up "
            "missing)."
        )
        event = events[0]
        assert event.causing_feature_id == feature.id
        # The affected test should be the one that flipped from PASSED to
        # FAILED (test_x). detect_regression stores a JSON-encoded list.
        assert "test_x" in event.affected_tests

    @pytest.mark.asyncio
    async def test_orchestrator_records_regression_evidence(self, project):
        """When detect_regression returns an event, an evidence row of
        type 'regression_detected' must be written for the causing
        feature."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            get_feature,
            query_evidence,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import OrchestrationLoop

        f = create_feature(
            project_id=project.id,
            name="Causes regression with evidence",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=project.id, workspace="/tmp/w")

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="done",
                is_error=False,
                duration_ms=100,
                num_turns=1,
                total_cost_usd=0.05,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        snapshots = [
            {"tests/test_x.py::tx": True},
            {"tests/test_x.py::tx": False},
        ]
        snapshot_iter = iter(snapshots)

        def fake_capture(*_args, **_kwargs):
            try:
                return next(snapshot_iter)
            except StopIteration:
                return None

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ), patch(
            "bob3.orchestrator.run_loop.capture_pytest_snapshot",
            side_effect=fake_capture,
        ), patch(
            "bob3.orchestrator.run_loop.run_verification_checklist",
            return_value={"passed": True, "summary": "ok", "checks": []},
        ), patch(
            "bob3.orchestrator.run_loop.git_commit_feature",
            return_value="deadbeef",
        ), patch(
            "bob3.orchestrator.run_loop.git_get_status",
            return_value={"sha": "abc123"},
        ):
            await loop.execute_feature(feature)

        evidence_rows = query_evidence(feature_id=feature.id)
        regression_evidence = [
            e for e in evidence_rows if e.type == "regression_detected"
        ]
        assert len(regression_evidence) == 1, (
            "execute_feature must store evidence with type "
            "'regression_detected' so the operator sees what regressed; "
            "found "
            f"{[e.type for e in evidence_rows]}"
        )

    @pytest.mark.asyncio
    async def test_orchestrator_skips_detect_when_snapshot_unavailable(
        self, project
    ):
        """When capture_pytest_snapshot returns None (e.g. no test dir,
        pytest missing), detect_regression must be skipped — empty
        snapshots aren't useful and the feature wasn't really
        regression-checked."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            get_feature,
            list_regression_events,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import OrchestrationLoop

        f = create_feature(
            project_id=project.id,
            name="No snapshot",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=project.id, workspace="/tmp/w")

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="done",
                is_error=False,
                duration_ms=100,
                num_turns=1,
                total_cost_usd=0.05,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ), patch(
            "bob3.orchestrator.run_loop.capture_pytest_snapshot",
            return_value=None,
        ), patch(
            "bob3.orchestrator.run_loop.run_verification_checklist",
            return_value={"passed": True, "summary": "ok", "checks": []},
        ), patch(
            "bob3.orchestrator.run_loop.git_commit_feature",
            return_value="deadbeef",
        ), patch(
            "bob3.orchestrator.run_loop.git_get_status",
            return_value={"sha": "abc123"},
        ):
            await loop.execute_feature(feature)

        events = list_regression_events(project_id=project.id)
        assert events == [], (
            "When snapshots are unavailable, detect_regression must be "
            "skipped to avoid spurious empty-comparison records."
        )

    def test_capture_pytest_snapshot_returns_none_for_missing_workspace(
        self, db_path
    ):
        """capture_pytest_snapshot must safely return None for missing
        workspaces (regression on the helper itself)."""
        from bob3.orchestrator.run_loop import capture_pytest_snapshot

        assert capture_pytest_snapshot(None) is None
        assert capture_pytest_snapshot("") is None
        assert capture_pytest_snapshot("/nonexistent/path/does/not/exist") is None


# ============================================================
# R5-006 / R7-001: regression-snapshot offload + toggle + decomposition skip
# ============================================================


class TestRegressionSnapshotInWorkerThread:
    """R5-006: capture_pytest_snapshot must run via asyncio.to_thread so it
    does not block the event loop for the duration of the pytest run.
    """

    @pytest.mark.asyncio
    async def test_snapshot_runs_in_worker_thread(self, project):
        """The before- and after-snapshots must execute on a thread other
        than the one running the asyncio event loop.
        """
        import threading
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import create_feature, get_feature, update_feature
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import OrchestrationLoop

        f = create_feature(
            project_id=project.id,
            name="Snapshot in worker thread",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=project.id, workspace="/tmp/w")

        loop_thread = threading.get_ident()
        snapshot_calls: list[int] = []

        def fake_capture(*_args, **_kwargs):
            snapshot_calls.append(threading.get_ident())
            return {"tests/test_x.py::tx": True}

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="done",
                is_error=False,
                duration_ms=1,
                num_turns=1,
                total_cost_usd=0.0,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ), patch(
            "bob3.orchestrator.run_loop.capture_pytest_snapshot",
            side_effect=fake_capture,
        ), patch(
            "bob3.orchestrator.run_loop.run_verification_checklist",
            return_value={"passed": True, "summary": "ok", "checks": []},
        ), patch(
            "bob3.orchestrator.run_loop.git_commit_feature",
            return_value="deadbeef",
        ), patch(
            "bob3.orchestrator.run_loop.git_get_status",
            return_value={"sha": "abc123"},
        ):
            await loop.execute_feature(feature)

        # We expect 2 calls (before + after) and BOTH must run on a thread
        # different from the event-loop thread.
        assert len(snapshot_calls) == 2, (
            f"expected 2 snapshot calls (before + after); got {len(snapshot_calls)}"
        )
        for tid in snapshot_calls:
            assert tid != loop_thread, (
                "capture_pytest_snapshot ran on the event-loop thread; "
                "must be offloaded via asyncio.to_thread (R5-006)."
            )


class TestRegressionDetectionToggle:
    """R7-001: BOB3_REGRESSION_DETECTION_ENABLED=0 must skip both snapshots."""

    @pytest.mark.asyncio
    async def test_env_var_disables_snapshots(self, project, monkeypatch):
        """When BOB3_REGRESSION_DETECTION_ENABLED=0, capture_pytest_snapshot
        must not be called at all during execute_feature.
        """
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import create_feature, get_feature, update_feature
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import OrchestrationLoop

        monkeypatch.setenv("BOB3_REGRESSION_DETECTION_ENABLED", "0")

        f = create_feature(
            project_id=project.id,
            name="Snapshots disabled",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=project.id, workspace="/tmp/w")

        snapshot_call_count = 0

        def fake_capture(*_args, **_kwargs):
            nonlocal snapshot_call_count
            snapshot_call_count += 1
            return None

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="done",
                is_error=False,
                duration_ms=1,
                num_turns=1,
                total_cost_usd=0.0,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ), patch(
            "bob3.orchestrator.run_loop.capture_pytest_snapshot",
            side_effect=fake_capture,
        ), patch(
            "bob3.orchestrator.run_loop.run_verification_checklist",
            return_value={"passed": True, "summary": "ok", "checks": []},
        ), patch(
            "bob3.orchestrator.run_loop.git_commit_feature",
            return_value="deadbeef",
        ), patch(
            "bob3.orchestrator.run_loop.git_get_status",
            return_value={"sha": "abc123"},
        ):
            await loop.execute_feature(feature)

        assert snapshot_call_count == 0, (
            "BOB3_REGRESSION_DETECTION_ENABLED=0 must skip both pytest "
            "snapshots; capture_pytest_snapshot was called "
            f"{snapshot_call_count} times."
        )


class TestDecompositionSkipsSnapshot:
    """R7-001: A feature that gets decomposed (exceeds_size_limits=True)
    must not trigger the pre-execution pytest snapshot. The pre-snapshot
    is wasted work because execute_feature returns early before any
    sub-agent runs against the implementation path.
    """

    @pytest.mark.asyncio
    async def test_decomposition_path_does_not_call_snapshot(self, project):
        import uuid
        from unittest.mock import AsyncMock, patch

        from bob3.db import (
            check_feature_size,
            create_feature,
            get_feature,
            update_feature,
        )
        from bob3.orchestrator.run_loop import OrchestrationLoop

        f = create_feature(
            project_id=project.id,
            name="Oversized",
            description="This feature should decompose",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            estimated_lines_of_code=1000,
            estimated_files_touched=10,
            estimated_complexity=9,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        check_feature_size(f.id)
        feature = get_feature(f.id)
        assert feature.exceeds_size_limits is True

        loop = OrchestrationLoop(project_id=project.id, workspace="/tmp/w")

        snapshot_calls: list[int] = []

        def fake_capture(*_args, **_kwargs):
            snapshot_calls.append(1)
            return None

        async def fake_decomp(*_args, **_kwargs):
            return {
                "success": True,
                "children_created": 2,
                "cost_usd": 0.0,
                "num_turns": 0,
            }

        with patch(
            "bob3.orchestrator.run_loop.handle_decomposition",
            new_callable=AsyncMock,
            side_effect=fake_decomp,
        ), patch(
            "bob3.orchestrator.run_loop.capture_pytest_snapshot",
            side_effect=fake_capture,
        ):
            await loop.execute_feature(feature)

        assert snapshot_calls == [], (
            "Decomposition path must not call capture_pytest_snapshot — "
            "execute_feature returns early before any implementation "
            "snapshot would be useful (R7-001). Got "
            f"{len(snapshot_calls)} call(s)."
        )
