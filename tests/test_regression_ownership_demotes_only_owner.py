"""Tests that may_demote_to_regression only demotes features that own failing tests.

Feature fb683f94-cf73-457e-bd3f-1c2bb51d93f5

AC: pytest: tests/test_regression_ownership_demotes_only_owner.py
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
        name="Demotes Only Owner Project",
        workspace_path="/tmp/demotes-owner-test",
    )


@pytest.fixture()
def feature_owner(project):
    from bob.db import create_feature
    return create_feature(
        project_id=project.id,
        name="Owner Feature",
        status="completed",
        test_files=json.dumps(["tests/test_owner.py"]),
    )


@pytest.fixture()
def feature_bystander(project):
    from bob.db import create_feature
    return create_feature(
        project_id=project.id,
        name="Bystander Feature",
        status="completed",
        test_files=json.dumps(["tests/test_bystander.py"]),
    )


@pytest.fixture()
def causing_feature(project):
    from bob.db import create_feature
    return create_feature(
        project_id=project.id,
        name="Causing Feature",
        status="executing",
    )


class TestMayDemoteToRegression:
    """may_demote_to_regression correctly gates demotion on ownership evidence."""

    def test_owner_feature_is_eligible_for_demotion(self, feature_owner):
        """A feature is eligible for demotion when its tests appear in the map."""
        from bob.db.regression_ownership import may_demote_to_regression

        ownership_map = {
            "tests/test_owner.py::test_fails": feature_owner.id,
        }
        assert may_demote_to_regression(feature_owner.id, ownership_map) is True

    def test_bystander_feature_is_not_eligible(self, feature_owner, feature_bystander):
        """A feature with no tests in the map must not be eligible for demotion."""
        from bob.db.regression_ownership import may_demote_to_regression

        ownership_map = {
            "tests/test_owner.py::test_fails": feature_owner.id,
        }
        assert may_demote_to_regression(feature_bystander.id, ownership_map) is False

    def test_returns_false_for_empty_map(self, feature_owner):
        """Empty map -> no feature is eligible."""
        from bob.db.regression_ownership import may_demote_to_regression

        assert may_demote_to_regression(feature_owner.id, {}) is False

    def test_returns_false_for_unknown_feature_id(self):
        """A feature_id that is absent from all map values is not eligible."""
        from bob.db.regression_ownership import may_demote_to_regression

        ownership_map = {
            "tests/test_other.py::test_foo": "some-other-feature-id",
        }
        assert may_demote_to_regression("unknown-feature-id", ownership_map) is False

    def test_multiple_owners_correct_one_returned(self, feature_owner, feature_bystander):
        """With multiple features in map, only the one that owns failing tests is eligible."""
        from bob.db.regression_ownership import may_demote_to_regression

        ownership_map = {
            "tests/test_owner.py::test_fails": feature_owner.id,
            "tests/test_bystander.py::test_passes": feature_bystander.id,
        }
        assert may_demote_to_regression(feature_owner.id, ownership_map) is True
        assert may_demote_to_regression(feature_bystander.id, ownership_map) is True

    def test_may_demote_importable(self):
        from bob.db.regression_ownership import may_demote_to_regression
        assert callable(may_demote_to_regression)


class TestDetectRegressionDemotesOnlyOwner:
    """detect_regression demotes only the feature that owns the newly-failing tests."""

    def test_only_owner_is_demoted_not_bystander(
        self, project, feature_owner, feature_bystander, causing_feature
    ):
        """Bystander is not demoted even when other features' tests fail."""
        from bob.db import detect_regression, get_feature

        detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={"tests/test_owner.py::test_core": True},
            after_results={"tests/test_owner.py::test_core": False},
            test_to_feature_map={
                "tests/test_owner.py::test_core": feature_owner.id,
            },
        )

        owner_after = get_feature(feature_owner.id)
        bystander_after = get_feature(feature_bystander.id)

        assert owner_after.status == "regression", "Owner must be demoted"
        assert bystander_after.status == "completed", "Bystander must not be demoted"

    def test_no_demotion_when_test_not_in_map(
        self, project, feature_owner, causing_feature
    ):
        """A feature is not demoted when its tests are not in the map."""
        from bob.db import detect_regression, get_feature

        detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={"tests/test_unowned.py::test_orphan": True},
            after_results={"tests/test_unowned.py::test_orphan": False},
            test_to_feature_map={},  # empty: nothing attributed
        )

        owner_after = get_feature(feature_owner.id)
        assert owner_after.status == "completed", "Feature must not be demoted without ownership"

    def test_build_test_to_feature_map_populates_correctly(
        self, project, feature_owner, feature_bystander
    ):
        """build_test_to_feature_map correctly maps test files to feature IDs."""
        from bob.db.regression_ownership import build_test_to_feature_map

        result = build_test_to_feature_map(project.id)

        assert "tests/test_owner.py" in result
        assert "tests/test_bystander.py" in result
        assert result["tests/test_owner.py"] == feature_owner.id
        assert result["tests/test_bystander.py"] == feature_bystander.id

    def test_build_test_to_feature_map_skips_null_test_files(
        self, project, causing_feature
    ):
        """Features with no test_files are excluded from the map."""
        from bob.db.regression_ownership import build_test_to_feature_map

        result = build_test_to_feature_map(project.id)

        assert causing_feature.id not in result.values()
