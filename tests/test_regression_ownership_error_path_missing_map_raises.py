"""Tests that detect_regression() raises TypeError when test_to_feature_map kwarg is absent.

Feature fb683f94-cf73-457e-bd3f-1c2bb51d93f5

AC: detect_regression() raises TypeError with message containing "test_to_feature_map"
when the kwarg is missing.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(p))
    from bob3.db import init_database
    init_database()
    return p


@pytest.fixture()
def project(db_path):
    from bob3.db import create_project
    return create_project(name="Error Path Project", workspace_path="/tmp/error-path-test")


@pytest.fixture()
def causing_feature(project):
    from bob3.db import create_feature
    return create_feature(project_id=project.id, name="Causing Feature", status="executing")


class TestDetectRegressionRaisesTypeErrorWhenMapMissing:
    """detect_regression raises TypeError with informative message when map kwarg absent."""

    def test_raises_typeerror_when_test_to_feature_map_omitted(
        self, project, causing_feature
    ):
        """TypeError raised when test_to_feature_map kwarg is missing."""
        from bob3.db import detect_regression

        with pytest.raises(TypeError) as exc_info:
            detect_regression(
                project_id=project.id,
                causing_feature_id=causing_feature.id,
                before_results={"tests/test_x.py::test_a": True},
                after_results={"tests/test_x.py::test_a": False},
                # test_to_feature_map intentionally omitted
            )

        error_message = str(exc_info.value)
        assert "test_to_feature_map" in error_message, (
            f"TypeError message must contain 'test_to_feature_map', got: {error_message!r}"
        )

    def test_raises_typeerror_with_empty_results(self, project, causing_feature):
        """TypeError still raised even with empty before/after results."""
        from bob3.db import detect_regression

        with pytest.raises(TypeError) as exc_info:
            detect_regression(
                project_id=project.id,
                causing_feature_id=causing_feature.id,
                before_results={},
                after_results={},
            )

        assert "test_to_feature_map" in str(exc_info.value)

    def test_no_typeerror_when_map_provided(self, project, causing_feature):
        """No TypeError when test_to_feature_map is provided (even empty)."""
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={},
            after_results={},
            test_to_feature_map={},
        )
        assert result is None  # no newly failing tests

    def test_raises_ownership_module_declares_contract(self):
        """regression_ownership.raises_typeerror_when_map_missing returns True."""
        from bob3.db.regression_ownership import raises_typeerror_when_map_missing
        assert raises_typeerror_when_map_missing() is True
