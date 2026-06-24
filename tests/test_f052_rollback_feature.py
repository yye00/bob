"""Tests for F052: Implement rollback operation for failed features."""

import json
import pathlib

import pytest

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Create a temporary database and initialize schema."""
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(p))
    from bob.db import init_database

    init_database()
    return p


@pytest.fixture()
def project(db_path):
    """Create a test project for foreign key references."""
    from bob.db import create_project

    return create_project(
        name="Rollback Test Project",
        workspace_path="/tmp/rollback-test",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature that will be rolled back."""
    from bob.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Feature To Rollback",
        status="failed",
    )


@pytest.fixture()
def completed_feature(project):
    """Create a completed feature whose tests were broken."""
    from bob.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Affected Feature",
        status="completed",
    )


@pytest.fixture()
def evidence(project, feature):
    """Create evidence artifacts associated with the feature."""
    from bob.db import create_evidence

    return create_evidence(
        project_id=project.id,
        feature_id=feature.id,
        type="test_output",
        content=json.dumps({"tests_passed": 3, "tests_failed": 2}),
    )


@pytest.fixture()
def regression_event(project, completed_feature, feature):
    """Create a regression event linking the features."""
    from bob.db import create_regression_event

    return create_regression_event(
        project_id=project.id,
        affected_feature_id=completed_feature.id,
        causing_feature_id=feature.id,
        affected_tests=json.dumps(["test_a_1", "test_a_2"]),
    )


# ============================================================
# Step 1: Add rollback_feature() function
# ============================================================


class TestRollbackFeatureExists:
    """Step 1: rollback_feature() is importable and callable."""

    def test_function_is_importable(self, db_path):
        from bob.db import rollback_feature

        assert callable(rollback_feature)

    def test_returns_rollback_event(self, project, feature):
        from bob.db import rollback_feature
        from bob.models import RollbackEvent

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="human_request",
            commit_before="abc123",
            commit_after="def456",
        )
        assert result is not None
        assert isinstance(result, RollbackEvent)


# ============================================================
# Step 2: Record commit_before and commit_after
# ============================================================


class TestRecordCommitBeforeAfter:
    """Step 2: rollback_feature() records commit_before and commit_after."""

    def test_commit_before_is_recorded(self, project, feature):
        from bob.db import rollback_feature

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="human_request",
            commit_before="aaa111",
            commit_after="bbb222",
        )
        assert result.commit_before == "aaa111"

    def test_commit_after_is_recorded(self, project, feature):
        from bob.db import rollback_feature

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="human_request",
            commit_before="aaa111",
            commit_after="bbb222",
        )
        assert result.commit_after == "bbb222"

    def test_commits_persisted_in_database(self, project, feature):
        from bob.db import connect, rollback_feature

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="critical_bug",
            commit_before="commit_before_sha",
            commit_after="commit_after_sha",
        )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT commit_before, commit_after FROM rollback_events WHERE id = ?",
                (result.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == "commit_before_sha"
        assert row[1] == "commit_after_sha"


# ============================================================
# Step 3: Execute git revert or git reset
# ============================================================


class TestRollbackCommitRecorded:
    """Step 3: rollback_feature() records a rollback_commit SHA."""

    def test_rollback_commit_can_be_provided(self, project, feature):
        from bob.db import rollback_feature

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="regression",
            commit_before="aaa111",
            commit_after="bbb222",
            rollback_commit="ccc333",
        )
        assert result.rollback_commit == "ccc333"

    def test_rollback_commit_is_optional(self, project, feature):
        from bob.db import rollback_feature

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="regression",
            commit_before="aaa111",
            commit_after="bbb222",
        )
        assert result.rollback_commit is None


# ============================================================
# Step 4: Create rollback_events record
# ============================================================


class TestCreateRollbackEventsRecord:
    """Step 4: rollback event is stored in the rollback_events table."""

    def test_rollback_event_persisted_in_database(self, project, feature):
        from bob.db import connect, rollback_feature

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="human_request",
            commit_before="abc123",
            commit_after="def456",
        )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT id, project_id, feature_id, trigger, "
                "commit_before, commit_after FROM rollback_events WHERE id = ?",
                (result.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == result.id
        assert row[1] == project.id
        assert row[2] == feature.id
        assert row[3] == "human_request"
        assert row[4] == "abc123"
        assert row[5] == "def456"

    def test_feature_status_updated_to_rolled_back(self, project, feature):
        from bob.db import get_feature, rollback_feature

        rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="regression",
            commit_before="abc123",
            commit_after="def456",
        )

        updated_feature = get_feature(feature.id)
        assert updated_feature is not None
        assert updated_feature.status == "rolled_back"

    def test_regression_event_id_linked(self, project, feature, completed_feature, regression_event):
        from bob.db import rollback_feature

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="regression",
            commit_before="abc123",
            commit_after="def456",
            regression_event_id=regression_event.id,
        )
        assert result.regression_event_id == regression_event.id

    def test_trigger_values_are_accepted(self, project):
        from bob.db import create_feature, rollback_feature

        for trigger in ("regression", "human_request", "critical_bug"):
            f = create_feature(
                project_id=project.id,
                name=f"Feature for {trigger}",
                status="failed",
            )
            result = rollback_feature(
                project_id=project.id,
                feature_id=f.id,
                trigger=trigger,
                commit_before="aaa",
                commit_after="bbb",
            )
            assert result.trigger == trigger

    def test_create_rollback_event_crud(self, project, feature):
        """Test the lower-level create_rollback_event function."""
        from bob.db import create_rollback_event
        from bob.models import RollbackEvent

        event = create_rollback_event(
            project_id=project.id,
            feature_id=feature.id,
            trigger="human_request",
            commit_before="abc123",
            commit_after="def456",
        )
        assert isinstance(event, RollbackEvent)
        assert event.project_id == project.id
        assert event.feature_id == feature.id
        assert event.trigger == "human_request"
        assert event.commit_before == "abc123"
        assert event.commit_after == "def456"

    def test_get_rollback_event(self, project, feature):
        """Test retrieval of a rollback event by ID."""
        from bob.db import create_rollback_event, get_rollback_event

        event = create_rollback_event(
            project_id=project.id,
            feature_id=feature.id,
            trigger="critical_bug",
            commit_before="aaa",
            commit_after="bbb",
        )
        fetched = get_rollback_event(event.id)
        assert fetched is not None
        assert fetched.id == event.id
        assert fetched.trigger == "critical_bug"

    def test_list_rollback_events(self, project, feature):
        """Test listing rollback events for a project."""
        from bob.db import create_feature, create_rollback_event, list_rollback_events

        create_rollback_event(
            project_id=project.id,
            feature_id=feature.id,
            trigger="regression",
            commit_before="aaa",
            commit_after="bbb",
        )
        f2 = create_feature(
            project_id=project.id,
            name="Another Feature",
            status="failed",
        )
        create_rollback_event(
            project_id=project.id,
            feature_id=f2.id,
            trigger="human_request",
            commit_before="ccc",
            commit_after="ddd",
        )

        events = list_rollback_events(project_id=project.id)
        assert len(events) == 2


# ============================================================
# Step 5: Preserve artifacts before rollback
# ============================================================


class TestPreserveArtifactsBeforeRollback:
    """Step 5: Evidence artifacts are preserved before rollback."""

    def test_artifacts_preserved_ids_recorded(self, project, feature, evidence):
        from bob.db import rollback_feature

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="human_request",
            commit_before="abc123",
            commit_after="def456",
        )
        assert result.artifacts_preserved is not None
        preserved = json.loads(result.artifacts_preserved)
        assert evidence.id in preserved

    def test_artifacts_persisted_in_database(self, project, feature, evidence):
        from bob.db import connect, rollback_feature

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="regression",
            commit_before="abc123",
            commit_after="def456",
        )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT artifacts_preserved FROM rollback_events WHERE id = ?",
                (result.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        preserved = json.loads(row[0])
        assert evidence.id in preserved

    def test_multiple_artifacts_are_all_preserved(self, project, feature):
        from bob.db import create_evidence, rollback_feature

        e1 = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"result": "output1"}),
        )
        e2 = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="code_diff",
            content=json.dumps({"result": "output2"}),
        )

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="critical_bug",
            commit_before="abc",
            commit_after="def",
        )
        preserved = json.loads(result.artifacts_preserved)
        assert e1.id in preserved
        assert e2.id in preserved

    def test_no_artifacts_gives_empty_list(self, project):
        from bob.db import create_feature, rollback_feature

        f = create_feature(
            project_id=project.id,
            name="No Artifacts Feature",
            status="failed",
        )
        result = rollback_feature(
            project_id=project.id,
            feature_id=f.id,
            trigger="human_request",
            commit_before="abc",
            commit_after="def",
        )
        preserved = json.loads(result.artifacts_preserved)
        assert preserved == []


# ============================================================
# Step 6: Test: Rollback feature, verify commit is reverted and record created
# ============================================================


class TestFullRollbackScenario:
    """Step 6: Full end-to-end rollback scenario."""

    def test_full_rollback_e2e(self, project, feature, evidence, completed_feature, regression_event):
        from bob.db import (
            connect,
            get_feature,
            get_regression_event,
            list_rollback_events,
            rollback_feature,
            update_regression_event,
        )

        # Perform rollback
        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="regression",
            commit_before="sha_before_feature",
            commit_after="sha_after_feature",
            rollback_commit="sha_rollback",
            regression_event_id=regression_event.id,
        )

        # 1. RollbackEvent was created with all fields
        assert result is not None
        assert result.project_id == project.id
        assert result.feature_id == feature.id
        assert result.trigger == "regression"
        assert result.commit_before == "sha_before_feature"
        assert result.commit_after == "sha_after_feature"
        assert result.rollback_commit == "sha_rollback"
        assert result.regression_event_id == regression_event.id

        # 2. Artifacts were preserved
        preserved = json.loads(result.artifacts_preserved)
        assert evidence.id in preserved

        # 3. Feature status is 'rolled_back'
        updated_feature = get_feature(feature.id)
        assert updated_feature.status == "rolled_back"

        # 4. Rollback event is persisted in database
        with connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM rollback_events WHERE project_id = ?",
                (project.id,),
            )
            count = cursor.fetchone()[0]
        assert count == 1

        # 5. Rollback events are listable
        events = list_rollback_events(project_id=project.id)
        assert len(events) == 1
        assert events[0].id == result.id

    def test_rollback_updates_regression_event_when_linked(
        self, project, feature, completed_feature, regression_event
    ):
        """When a rollback is linked to a regression, the regression should be updated."""
        from bob.db import get_regression_event, rollback_feature

        rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="regression",
            commit_before="abc",
            commit_after="def",
            regression_event_id=regression_event.id,
        )

        updated_reg = get_regression_event(regression_event.id)
        assert updated_reg is not None
        assert updated_reg.status == "rolled_back"

    def test_rollback_without_regression_event(self, project, feature):
        """Rollback without a regression event (e.g. human request) should work fine."""
        from bob.db import rollback_feature

        result = rollback_feature(
            project_id=project.id,
            feature_id=feature.id,
            trigger="human_request",
            commit_before="abc",
            commit_after="def",
        )
        assert result is not None
        assert result.regression_event_id is None
        assert result.trigger == "human_request"
