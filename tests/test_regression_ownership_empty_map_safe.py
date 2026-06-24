"""Tests that handle_empty_ownership_map records unattributed_failure when map is empty.

Feature fb683f94-cf73-457e-bd3f-1c2bb51d93f5

AC: pytest: tests/test_regression_ownership_empty_map_safe.py asserts
handle_empty_ownership_map records unattributed_failure when map is empty
(zero/empty boundary)
"""

from __future__ import annotations

import json
import sqlite3

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
    return create_project(
        name="Empty Map Safe Test Project",
        workspace_path="/tmp/empty-map-test",
    )


@pytest.fixture()
def feature_alpha(project):
    from bob3.db import create_feature
    return create_feature(
        project_id=project.id,
        name="Alpha (completed)",
        status="completed",
        test_files=json.dumps(["tests/test_alpha.py"]),
    )


@pytest.fixture()
def causing_feature(project):
    from bob3.db import create_feature
    return create_feature(
        project_id=project.id,
        name="Causing Feature",
        status="executing",
    )


class TestHandleEmptyOwnershipMapRecordsUnattributed:
    """handle_empty_ownership_map stores failures as unattributed and leaves statuses intact."""

    def test_single_failing_test_recorded_as_unattributed(
        self, db_path, project, causing_feature
    ):
        """Zero/empty boundary: one failing test, empty map -> one unattributed row."""
        from bob3.db.regression_ownership import handle_empty_ownership_map

        handle_empty_ownership_map(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            newly_failing_tests=["tests/test_x.py::test_foo"],
        )

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT test_name, causing_feature_id FROM unattributed_failures WHERE project_id = ?",
            (project.id,),
        ).fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0][0] == "tests/test_x.py::test_foo"
        assert rows[0][1] == causing_feature.id

    def test_multiple_failing_tests_all_recorded(
        self, db_path, project, causing_feature
    ):
        """Multiple failing tests on empty map -> all stored as unattributed."""
        from bob3.db.regression_ownership import handle_empty_ownership_map

        tests = [
            "tests/test_a.py::test_one",
            "tests/test_b.py::test_two",
            "tests/test_c.py::test_three",
        ]
        handle_empty_ownership_map(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            newly_failing_tests=tests,
        )

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT test_name FROM unattributed_failures WHERE project_id = ?",
            (project.id,),
        ).fetchall()
        conn.close()

        stored = {r[0] for r in rows}
        assert stored == set(tests)

    def test_empty_newly_failing_list_is_noop(
        self, db_path, project, causing_feature
    ):
        """Empty newly_failing_tests list -> no rows written, no error."""
        from bob3.db.regression_ownership import handle_empty_ownership_map

        handle_empty_ownership_map(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            newly_failing_tests=[],
        )

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT test_name FROM unattributed_failures WHERE project_id = ?",
            (project.id,),
        ).fetchall()
        conn.close()

        assert len(rows) == 0

    def test_feature_status_untouched_after_empty_map_call(
        self, project, feature_alpha, causing_feature
    ):
        """handle_empty_ownership_map must not modify any feature's status."""
        from bob3.db import get_feature
        from bob3.db.regression_ownership import handle_empty_ownership_map

        handle_empty_ownership_map(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            newly_failing_tests=["tests/test_alpha.py::test_owned_by_alpha"],
        )

        alpha_after = get_feature(feature_alpha.id)
        causing_after = get_feature(causing_feature.id)

        assert alpha_after.status == "completed", "Alpha must not be demoted"
        assert causing_after.status == "executing", "Causing feature must not be modified"


class TestEmptyMapLeavesFeatureStatusUntouched:
    """empty_map_leaves_feature_status_untouched documents the contract."""

    def test_contract_function_returns_true(self):
        from bob3.db.regression_ownership import empty_map_leaves_feature_status_untouched

        assert empty_map_leaves_feature_status_untouched() is True

    def test_handle_empty_ownership_map_importable(self):
        from bob3.db.regression_ownership import handle_empty_ownership_map

        assert callable(handle_empty_ownership_map)

    def test_empty_map_safe_module_importable(self):
        import bob3.db.regression_ownership as m

        assert hasattr(m, "handle_empty_ownership_map")
        assert hasattr(m, "empty_map_leaves_feature_status_untouched")
