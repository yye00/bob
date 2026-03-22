"""Tests for F053: Link rollback events to regression events.

This feature verifies the integration between regression detection (F051) and
rollback operations (F052). When a rollback is triggered by a regression, the
rollback event must store the regression_event_id, and the regression event's
status must be updated to 'rolled_back'.
"""

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
    """Create a test project."""
    from bob3.db import create_project

    return create_project(
        name="Rollback-Regression Link Test",
        workspace_path="/tmp/rollback-regression-test",
    )


@pytest.fixture()
def feature_a(project):
    """Create feature A (completed feature whose tests will be broken)."""
    from bob3.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Feature A - Stable",
        status="completed",
    )


@pytest.fixture()
def feature_b(project):
    """Create feature B (the feature that causes regression and will be rolled back)."""
    from bob3.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Feature B - Causes Regression",
        status="executing",
    )


@pytest.fixture()
def evidence_for_b(project, feature_b):
    """Create evidence artifacts for feature B."""
    from bob3.db import create_evidence

    return create_evidence(
        project_id=project.id,
        feature_id=feature_b.id,
        type="test_output",
        content=json.dumps({"tests_passed": 5, "tests_failed": 0}),
    )


# ============================================================
# Step 1: When creating rollback, store regression_event_id
#         if triggered by regression
# ============================================================


class TestStoreRegressionEventIdOnRollback:
    """Step 1: rollback stores regression_event_id when triggered by regression."""

    def test_rollback_stores_regression_event_id(self, project, feature_a, feature_b):
        """When a rollback is triggered by a regression, the regression_event_id is stored."""
        from bob3.db import create_regression_event, rollback_feature

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )

        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="abc123",
            commit_after="def456",
            regression_event_id=reg_event.id,
        )

        assert rollback_event.regression_event_id == reg_event.id

    def test_rollback_regression_event_id_persisted_in_db(self, project, feature_a, feature_b):
        """The regression_event_id is persisted in the rollback_events table."""
        from bob3.db import connect, create_regression_event, rollback_feature

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )

        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="abc123",
            commit_after="def456",
            regression_event_id=reg_event.id,
        )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT regression_event_id FROM rollback_events WHERE id = ?",
                (rollback_event.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == reg_event.id

    def test_rollback_without_regression_has_null_regression_event_id(self, project, feature_b):
        """Rollback not triggered by regression has NULL regression_event_id."""
        from bob3.db import rollback_feature

        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="human_request",
            commit_before="abc123",
            commit_after="def456",
        )

        assert rollback_event.regression_event_id is None

    def test_create_rollback_event_with_regression_event_id(self, project, feature_a, feature_b):
        """Lower-level create_rollback_event also accepts regression_event_id."""
        from bob3.db import create_regression_event, create_rollback_event

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )

        rollback_event = create_rollback_event(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="abc",
            commit_after="def",
            regression_event_id=reg_event.id,
        )

        assert rollback_event.regression_event_id == reg_event.id

    def test_get_rollback_event_preserves_regression_event_id(self, project, feature_a, feature_b):
        """get_rollback_event returns the regression_event_id correctly."""
        from bob3.db import create_regression_event, create_rollback_event, get_rollback_event

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )

        rollback_event = create_rollback_event(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="abc",
            commit_after="def",
            regression_event_id=reg_event.id,
        )

        fetched = get_rollback_event(rollback_event.id)
        assert fetched is not None
        assert fetched.regression_event_id == reg_event.id


# ============================================================
# Step 2: Update regression_events.status to 'rolled_back'
# ============================================================


class TestUpdateRegressionStatusOnRollback:
    """Step 2: When rollback is linked to a regression, its status becomes 'rolled_back'."""

    def test_regression_status_updated_to_rolled_back(self, project, feature_a, feature_b):
        """rollback_feature updates the linked regression event's status."""
        from bob3.db import create_regression_event, get_regression_event, rollback_feature

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )
        assert reg_event.status == "detected"

        rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="abc123",
            commit_after="def456",
            regression_event_id=reg_event.id,
        )

        updated_reg = get_regression_event(reg_event.id)
        assert updated_reg is not None
        assert updated_reg.status == "rolled_back"

    def test_regression_resolved_at_set_on_rollback(self, project, feature_a, feature_b):
        """When regression status becomes 'rolled_back', resolved_at is auto-set."""
        from bob3.db import create_regression_event, get_regression_event, rollback_feature

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )

        rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="abc123",
            commit_after="def456",
            regression_event_id=reg_event.id,
        )

        updated_reg = get_regression_event(reg_event.id)
        assert updated_reg is not None
        assert updated_reg.resolved_at is not None

    def test_regression_status_unchanged_without_link(self, project, feature_a, feature_b):
        """A regression NOT linked to the rollback should not change status."""
        from bob3.db import create_regression_event, get_regression_event, rollback_feature

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )

        # Rollback WITHOUT linking the regression event
        rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="human_request",
            commit_before="abc123",
            commit_after="def456",
        )

        unchanged_reg = get_regression_event(reg_event.id)
        assert unchanged_reg is not None
        assert unchanged_reg.status == "detected"

    def test_regression_status_persisted_in_db(self, project, feature_a, feature_b):
        """Verify the rolled_back status is persisted in the database."""
        from bob3.db import connect, create_regression_event, rollback_feature

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )

        rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="abc",
            commit_after="def",
            regression_event_id=reg_event.id,
        )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT status, resolved_at FROM regression_events WHERE id = ?",
                (reg_event.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == "rolled_back"
        assert row[1] is not None  # resolved_at is set

    def test_regression_no_longer_in_active_list(self, project, feature_a, feature_b):
        """After rollback, the regression should not appear in active regressions."""
        from bob3.db import create_regression_event, list_regression_events, rollback_feature

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )

        # Before rollback, it should be active
        active_before = list_regression_events(project_id=project.id, active_only=True)
        assert any(e.id == reg_event.id for e in active_before)

        rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="abc",
            commit_after="def",
            regression_event_id=reg_event.id,
        )

        # After rollback, it should no longer be active
        active_after = list_regression_events(project_id=project.id, active_only=True)
        assert not any(e.id == reg_event.id for e in active_after)


# ============================================================
# Step 3: Test: Detect regression, trigger rollback, verify
#         link is created
# ============================================================


class TestDetectRegressionThenRollbackE2E:
    """Step 3: End-to-end flow - detect regression, trigger rollback, verify link."""

    def test_e2e_detect_regression_then_rollback(
        self, project, feature_a, feature_b, evidence_for_b
    ):
        """Full E2E: detect regression → rollback feature → verify link."""
        from bob3.db import (
            detect_regression,
            get_feature,
            get_regression_event,
            get_rollback_event,
            list_regression_events,
            list_rollback_events,
            rollback_feature,
        )

        # Phase 1: Detect regression
        before_results = {"test_a_1": True, "test_a_2": True, "test_a_3": True}
        after_results = {"test_a_1": False, "test_a_2": True, "test_a_3": False}
        test_to_feature_map = {
            "test_a_1": feature_a.id,
            "test_a_2": feature_a.id,
            "test_a_3": feature_a.id,
        }

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        assert reg_event is not None
        assert reg_event.status == "detected"
        assert reg_event.causing_feature_id == feature_b.id
        assert reg_event.affected_feature_id == feature_a.id

        affected_tests = json.loads(reg_event.affected_tests)
        assert sorted(affected_tests) == ["test_a_1", "test_a_3"]

        # Phase 2: Feature A's status should now be 'regression'
        feature_a_updated = get_feature(feature_a.id)
        assert feature_a_updated.status == "regression"

        # Phase 3: Trigger rollback of feature B, linking the regression event
        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before_b",
            commit_after="sha_after_b",
            rollback_commit="sha_rollback_b",
            regression_event_id=reg_event.id,
        )

        # Phase 4: Verify the link is created
        assert rollback_event.regression_event_id == reg_event.id
        assert rollback_event.trigger == "regression"
        assert rollback_event.feature_id == feature_b.id

        # Phase 5: Verify regression event status updated to 'rolled_back'
        updated_reg = get_regression_event(reg_event.id)
        assert updated_reg.status == "rolled_back"
        assert updated_reg.resolved_at is not None

        # Phase 6: Verify feature B status is 'rolled_back'
        feature_b_updated = get_feature(feature_b.id)
        assert feature_b_updated.status == "rolled_back"

        # Phase 7: Verify evidence was preserved
        preserved = json.loads(rollback_event.artifacts_preserved)
        assert evidence_for_b.id in preserved

        # Phase 8: Verify rollback event is persisted and retrievable
        fetched_rollback = get_rollback_event(rollback_event.id)
        assert fetched_rollback is not None
        assert fetched_rollback.regression_event_id == reg_event.id

        # Phase 9: Verify regression is no longer active
        active_regressions = list_regression_events(project_id=project.id, active_only=True)
        assert not any(e.id == reg_event.id for e in active_regressions)

        # Phase 10: Verify rollback appears in list
        rollbacks = list_rollback_events(project_id=project.id)
        assert len(rollbacks) == 1
        assert rollbacks[0].id == rollback_event.id

    def test_e2e_no_regression_no_rollback_link(self, project, feature_a, feature_b):
        """When no regression is detected, rollback has no regression link."""
        from bob3.db import detect_regression, rollback_feature

        # No regression (all tests still pass)
        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True},
            after_results={"test_a_1": True},
        )
        assert reg_event is None

        # Rollback for a different reason (e.g., human request)
        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="human_request",
            commit_before="abc",
            commit_after="def",
        )

        assert rollback_event.regression_event_id is None
        assert rollback_event.trigger == "human_request"

    def test_e2e_multiple_regressions_single_rollback(self, project, feature_a, feature_b):
        """One rollback can only link to one regression event."""
        from bob3.db import create_regression_event, get_regression_event, rollback_feature

        reg_event_1 = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )
        reg_event_2 = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_2"]),
        )

        # Link rollback to first regression only
        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="abc",
            commit_after="def",
            regression_event_id=reg_event_1.id,
        )

        assert rollback_event.regression_event_id == reg_event_1.id

        # First regression is rolled back
        updated_1 = get_regression_event(reg_event_1.id)
        assert updated_1.status == "rolled_back"

        # Second regression is still detected (not linked)
        updated_2 = get_regression_event(reg_event_2.id)
        assert updated_2.status == "detected"

    def test_e2e_rollback_with_critical_bug_trigger(self, project, feature_a, feature_b):
        """Rollback triggered by critical_bug can still link a regression."""
        from bob3.db import create_regression_event, get_regression_event, rollback_feature

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1"]),
        )

        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="critical_bug",
            commit_before="abc",
            commit_after="def",
            regression_event_id=reg_event.id,
        )

        assert rollback_event.regression_event_id == reg_event.id
        assert rollback_event.trigger == "critical_bug"

        updated_reg = get_regression_event(reg_event.id)
        assert updated_reg.status == "rolled_back"

    def test_e2e_verify_database_consistency(self, project, feature_a, feature_b):
        """Verify both rollback and regression tables are consistent after E2E flow."""
        from bob3.db import connect, create_regression_event, rollback_feature

        reg_event = create_regression_event(
            project_id=project.id,
            affected_feature_id=feature_a.id,
            causing_feature_id=feature_b.id,
            affected_tests=json.dumps(["test_a_1", "test_a_2"]),
        )

        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before",
            commit_after="sha_after",
            rollback_commit="sha_revert",
            regression_event_id=reg_event.id,
        )

        # Cross-reference: rollback points to regression, regression is rolled_back
        with connect() as conn:
            # Check rollback_events table
            cursor = conn.execute(
                "SELECT regression_event_id FROM rollback_events WHERE id = ?",
                (rollback_event.id,),
            )
            rollback_row = cursor.fetchone()
            assert rollback_row[0] == reg_event.id

            # Check regression_events table
            cursor = conn.execute(
                "SELECT status, resolved_at FROM regression_events WHERE id = ?",
                (reg_event.id,),
            )
            reg_row = cursor.fetchone()
            assert reg_row[0] == "rolled_back"
            assert reg_row[1] is not None

            # Check feature status
            cursor = conn.execute(
                "SELECT status FROM features WHERE id = ?",
                (feature_b.id,),
            )
            feature_row = cursor.fetchone()
            assert feature_row[0] == "rolled_back"
