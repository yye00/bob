"""Tests ensuring unmapped failures go to unattributed_failures, not a scapegoat.

Feature 63ce7239-7c9f-439a-b02f-19159f9dde11

When a test fails and is NOT in test_to_feature_map, it must be stored in
the unattributed_failures table and must NOT cause any completed feature to
be demoted to 'regression'.
"""

from __future__ import annotations

import json

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
        name="Scapegoat Prevention Project",
        workspace_path="/tmp/scapegoat-test",
    )


@pytest.fixture()
def completed_feature_alpha(project):
    from bob3.db import create_feature
    return create_feature(
        project_id=project.id,
        name="Alpha (completed)",
        status="completed",
        test_files=json.dumps(["tests/test_alpha.py"]),
    )


@pytest.fixture()
def completed_feature_beta(project):
    from bob3.db import create_feature
    return create_feature(
        project_id=project.id,
        name="Beta (completed)",
        status="completed",
        test_files=json.dumps(["tests/test_beta.py"]),
    )


@pytest.fixture()
def causing_feature(project):
    from bob3.db import create_feature
    return create_feature(
        project_id=project.id,
        name="Causing Feature (executing)",
        status="executing",
    )


class TestUnattributedFailuresTable:
    """unattributed_failures table exists and is used for unmapped tests."""

    def test_table_exists(self, db_path):
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='unattributed_failures'"
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None, "unattributed_failures table must exist in schema"

    def test_table_has_expected_columns(self, db_path):
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(unattributed_failures)")
        cols = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert "id" in cols
        assert "project_id" in cols
        assert "causing_feature_id" in cols
        assert "test_name" in cols
        assert "created_at" in cols


class TestUnmappedFailureRecordedNotScapegoated:
    """Unmapped failures are stored in unattributed_failures, not on a feature."""

    def test_unmapped_failure_does_not_demote_completed_feature(
        self, project, completed_feature_alpha, completed_feature_beta, causing_feature
    ):
        """An unmapped test failure must NOT demote any completed feature."""
        from bob3.db import detect_regression, get_feature

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={"tests/test_orphan.py::test_nobody_owns_me": True},
            after_results={"tests/test_orphan.py::test_nobody_owns_me": False},
            test_to_feature_map={},  # test is not in any ownership map
        )

        assert result is None, "No regression event should be created for unmapped tests"
        alpha = get_feature(completed_feature_alpha.id)
        beta = get_feature(completed_feature_beta.id)
        assert alpha.status == "completed", "Alpha must not be scapegoated"
        assert beta.status == "completed", "Beta must not be scapegoated"

    def test_unmapped_failure_stored_in_unattributed_table(
        self, db_path, project, completed_feature_alpha, causing_feature
    ):
        """Unmapped failures are persisted to unattributed_failures."""
        import sqlite3
        from bob3.db import detect_regression

        detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={"tests/test_orphan.py::test_lost": True},
            after_results={"tests/test_orphan.py::test_lost": False},
            test_to_feature_map={},
        )

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT test_name, causing_feature_id FROM unattributed_failures WHERE project_id = ?",
            (project.id,),
        ).fetchall()
        conn.close()

        assert len(rows) == 1, "Unmapped failure must be recorded in unattributed_failures"
        assert rows[0][0] == "tests/test_orphan.py::test_lost"
        assert rows[0][1] == causing_feature.id

    def test_multiple_unmapped_failures_all_stored(
        self, db_path, project, completed_feature_alpha, causing_feature
    ):
        """Multiple unmapped failures are all persisted; none scapegoated."""
        import sqlite3
        from bob3.db import detect_regression

        detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={
                "tests/test_orphan.py::test_a": True,
                "tests/test_orphan.py::test_b": True,
                "tests/test_orphan.py::test_c": True,
            },
            after_results={
                "tests/test_orphan.py::test_a": False,
                "tests/test_orphan.py::test_b": False,
                "tests/test_orphan.py::test_c": False,
            },
            test_to_feature_map={},
        )

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT test_name FROM unattributed_failures WHERE project_id = ?",
            (project.id,),
        ).fetchall()
        conn.close()
        stored = {r[0] for r in rows}

        assert "tests/test_orphan.py::test_a" in stored
        assert "tests/test_orphan.py::test_b" in stored
        assert "tests/test_orphan.py::test_c" in stored

    def test_mixed_failures_only_unmapped_go_to_unattributed(
        self, db_path, project, completed_feature_alpha, causing_feature
    ):
        """Mixed batch: owned tests create regression_event; unowned go to unattributed."""
        import sqlite3
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={
                "tests/test_alpha.py::test_owned": True,
                "tests/test_orphan.py::test_unowned": True,
            },
            after_results={
                "tests/test_alpha.py::test_owned": False,
                "tests/test_orphan.py::test_unowned": False,
            },
            test_to_feature_map={
                "tests/test_alpha.py::test_owned": completed_feature_alpha.id,
            },
        )

        # Owned failure → regression event
        assert result is not None, "Owned failure must produce a regression event"

        # Unowned failure → unattributed_failures
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT test_name FROM unattributed_failures WHERE project_id = ?",
            (project.id,),
        ).fetchall()
        conn.close()
        stored = {r[0] for r in rows}
        assert "tests/test_orphan.py::test_unowned" in stored
        assert "tests/test_alpha.py::test_owned" not in stored

    def test_no_regression_event_when_all_failures_unmapped(
        self, project, completed_feature_alpha, causing_feature
    ):
        """When all failures are unmapped, detect_regression returns None."""
        from bob3.db import detect_regression, list_regression_events

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={
                "tests/test_x.py::test_one": True,
                "tests/test_y.py::test_two": True,
            },
            after_results={
                "tests/test_x.py::test_one": False,
                "tests/test_y.py::test_two": False,
            },
            test_to_feature_map={},
        )

        assert result is None
        events = list_regression_events(project_id=project.id)
        assert len(events) == 0

    def test_already_failing_tests_not_treated_as_regression(
        self, project, completed_feature_alpha, causing_feature
    ):
        """Tests that were failing before are not new regressions."""
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={"tests/test_old_fail.py::test_broken": False},
            after_results={"tests/test_old_fail.py::test_broken": False},
            test_to_feature_map={
                "tests/test_old_fail.py::test_broken": completed_feature_alpha.id,
            },
        )

        assert result is None, "Pre-existing failures must not trigger regression"


class TestDetectRegressionIntegration:
    """Integration: bob3.db.detect_regression end-to-end contract."""

    def test_detect_regression_is_importable_from_bob3_db(self, db_path):
        from bob3.db import detect_regression
        assert callable(detect_regression)

    def test_no_newly_failing_tests_returns_none(
        self, project, completed_feature_alpha, causing_feature
    ):
        """When no tests newly fail, detect_regression returns None."""
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={"tests/test_alpha.py::test_one": True},
            after_results={"tests/test_alpha.py::test_one": True},
            test_to_feature_map={
                "tests/test_alpha.py::test_one": completed_feature_alpha.id,
            },
        )
        assert result is None

    def test_regression_event_has_correct_fields(
        self, project, completed_feature_alpha, causing_feature
    ):
        """When attribution succeeds, regression event links correct features."""
        from bob3.db import detect_regression

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=causing_feature.id,
            before_results={"tests/test_alpha.py::test_broke": True},
            after_results={"tests/test_alpha.py::test_broke": False},
            test_to_feature_map={
                "tests/test_alpha.py::test_broke": completed_feature_alpha.id,
            },
        )

        assert result is not None
        assert result.project_id == project.id
        assert result.causing_feature_id == causing_feature.id
        assert result.affected_feature_id == completed_feature_alpha.id
