"""Tests for regression attribution ownership contract (feature 63ce7239).

Ensures that:
- features.test_files column exists in the schema
- detect_regression requires test_to_feature_map argument
- A completed feature is NEVER demoted to regression unless its own tests fail
- Unmapped failures go to unattributed_failures, not scapegoated onto a feature
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(p))
    from bob.db import init_database
    init_database()
    return p


@pytest.fixture()
def project(db_path):
    from bob.db import create_project
    return create_project(
        name="Ownership Test Project",
        workspace_path="/tmp/ownership-test",
    )


@pytest.fixture()
def feature_completed(project):
    from bob.db import create_feature
    return create_feature(
        project_id=project.id,
        name="Completed Feature",
        status="completed",
        test_files=json.dumps(["tests/test_completed.py"]),
    )


@pytest.fixture()
def feature_causing(project):
    from bob.db import create_feature
    return create_feature(
        project_id=project.id,
        name="Causing Feature",
        status="executing",
        test_files=json.dumps(["tests/test_causing.py"]),
    )


class TestTestFilesColumnExists:
    """Spec column: features.test_files is stored and retrieved."""

    def test_feature_has_test_files_attribute(self, feature_completed):
        assert hasattr(feature_completed, "test_files")

    def test_test_files_stored_as_json_array(self, feature_completed):
        parsed = json.loads(feature_completed.test_files)
        assert isinstance(parsed, list)
        assert "tests/test_completed.py" in parsed

    def test_test_files_defaults_to_none(self, project):
        from bob.db import create_feature
        f = create_feature(project_id=project.id, name="No Test Files Feature")
        assert f.test_files is None

    def test_test_files_can_be_updated(self, project):
        from bob.db import create_feature, update_feature
        f = create_feature(project_id=project.id, name="Updatable Feature")
        updated = update_feature(f.id, test_files=json.dumps(["tests/test_new.py"]))
        assert updated is not None
        parsed = json.loads(updated.test_files)
        assert "tests/test_new.py" in parsed


class TestDetectRegressionSignature:
    """detect_regression requires test_to_feature_map argument."""

    def test_detect_regression_importable(self, db_path):
        from bob.db import detect_regression
        assert callable(detect_regression)

    def test_detect_regression_accepts_test_to_feature_map(
        self, project, feature_completed, feature_causing
    ):
        from bob.db import detect_regression
        import inspect
        sig = inspect.signature(detect_regression)
        assert "test_to_feature_map" in sig.parameters

    def test_detect_regression_requires_test_to_feature_map_as_kwarg(
        self, project, feature_completed, feature_causing
    ):
        """detect_regression must accept test_to_feature_map as a keyword argument."""
        from bob.db import detect_regression
        # Should NOT raise when test_to_feature_map is provided
        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_causing.id,
            before_results={"tests/test_completed.py::test_one": True},
            after_results={"tests/test_completed.py::test_one": True},
            test_to_feature_map={},
        )
        assert result is None  # no failures → no regression


class TestCompletedFeatureNotDemotedWithoutOwnTests:
    """A completed feature MUST NOT be demoted to regression unless its own tests fail."""

    def test_completed_feature_not_demoted_if_unowned_test_fails(
        self, project, feature_completed, feature_causing
    ):
        """An unowned test fails → completed feature stays completed."""
        from bob.db import detect_regression, get_feature

        # test_orphan.py is not in any feature's test_to_feature_map
        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_causing.id,
            before_results={"tests/test_orphan.py::test_mystery": True},
            after_results={"tests/test_orphan.py::test_mystery": False},
            test_to_feature_map={},  # no ownership
        )

        assert result is None  # no attributable regression
        refreshed = get_feature(feature_completed.id)
        assert refreshed.status == "completed", (
            "Completed feature must not be demoted when it owns no failing test"
        )

    def test_completed_feature_not_demoted_when_other_feature_test_fails(
        self, project, feature_completed, feature_causing
    ):
        """feature_causing's test fails → only feature_causing is attributable, not feature_completed."""
        from bob.db import detect_regression, get_feature

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_causing.id,
            before_results={"tests/test_causing.py::test_breaks": True},
            after_results={"tests/test_causing.py::test_breaks": False},
            test_to_feature_map={
                "tests/test_causing.py::test_breaks": feature_causing.id,
            },
        )

        refreshed_completed = get_feature(feature_completed.id)
        assert refreshed_completed.status == "completed", (
            "Completed feature must not be demoted when it owns no failing test"
        )

    def test_completed_feature_demoted_only_when_its_own_tests_fail(
        self, project, feature_completed, feature_causing
    ):
        """feature_completed IS demoted when its own test_files tests newly fail."""
        from bob.db import detect_regression, get_feature

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_causing.id,
            before_results={"tests/test_completed.py::test_one": True},
            after_results={"tests/test_completed.py::test_one": False},
            test_to_feature_map={
                "tests/test_completed.py::test_one": feature_completed.id,
            },
        )

        assert result is not None, "Should detect regression when owned test fails"
        refreshed = get_feature(feature_completed.id)
        assert refreshed.status == "regression", (
            "Completed feature MUST be demoted when its own test newly fails"
        )

    def test_no_regression_event_created_for_unowned_failures(
        self, project, feature_completed, feature_causing
    ):
        """No regression_events record created when test is unmapped."""
        from bob.db import detect_regression, list_regression_events

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_causing.id,
            before_results={"tests/test_ghost.py::test_haunted": True},
            after_results={"tests/test_ghost.py::test_haunted": False},
            test_to_feature_map={},
        )

        assert result is None
        events = list_regression_events(project_id=project.id)
        assert len(events) == 0
