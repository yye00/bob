"""Tests for F004: Create db.py with SQLite database connection and initialization."""

import os
import pathlib
import sqlite3

import pytest

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_PATH = WORKSPACE / "src" / "bob3" / "schema.sql"


class TestGetDatabasePath:
    """Step 2: get_database_path() returns workspace/bob3.db or BOB3_DATABASE_PATH."""

    def test_default_path_is_workspace_bob3_db(self, monkeypatch):
        monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)
        from bob3.db import get_database_path

        result = get_database_path()
        assert result == pathlib.Path(WORKSPACE) / "bob3.db"

    def test_env_var_overrides_default(self, monkeypatch, tmp_path):
        custom_path = str(tmp_path / "custom.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", custom_path)
        from bob3.db import get_database_path

        result = get_database_path()
        assert result == pathlib.Path(custom_path)

    def test_returns_pathlib_path(self, monkeypatch):
        monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)
        from bob3.db import get_database_path

        result = get_database_path()
        assert isinstance(result, pathlib.Path)


class TestGetConnection:
    """Step 3: Database connection function using sqlite3."""

    def test_returns_sqlite3_connection(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import get_connection

        conn = get_connection()
        try:
            assert isinstance(conn, sqlite3.Connection)
        finally:
            conn.close()

    def test_connection_has_foreign_keys_enabled(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import get_connection

        conn = get_connection()
        try:
            cursor = conn.execute("PRAGMA foreign_keys")
            assert cursor.fetchone()[0] == 1
        finally:
            conn.close()

    def test_connection_has_wal_mode(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import get_connection

        conn = get_connection()
        try:
            cursor = conn.execute("PRAGMA journal_mode")
            assert cursor.fetchone()[0] == "wal"
        finally:
            conn.close()

    def test_creates_database_file(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        from bob3.db import get_connection

        conn = get_connection()
        conn.close()
        assert db_path.exists()

    def test_accepts_explicit_path(self, tmp_path):
        db_path = tmp_path / "explicit.db"
        from bob3.db import get_connection

        conn = get_connection(db_path=db_path)
        conn.close()
        assert db_path.exists()


class TestInitDatabase:
    """Step 4: Schema initialization from schema.sql."""

    def test_init_creates_tables(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import init_database

        init_database()
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]
            assert "projects" in tables
            assert "features" in tables
            assert "tasks" in tables
        finally:
            conn.close()

    def test_init_creates_views(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import init_database

        init_database()
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
            )
            views = [row[0] for row in cursor.fetchall()]
            assert "features_ready" in views
            assert "active_regressions" in views
        finally:
            conn.close()

    def test_init_creates_indexes(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import init_database

        init_database()
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            )
            indexes = [row[0] for row in cursor.fetchall()]
            assert "idx_features_project" in indexes
            assert "idx_tasks_feature" in indexes
        finally:
            conn.close()

    def test_init_is_idempotent(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import init_database

        init_database()
        init_database()  # Should not raise

    def test_init_accepts_explicit_path(self, tmp_path):
        db_path = tmp_path / "explicit.db"
        from bob3.db import init_database

        init_database(db_path=db_path)
        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            assert "projects" in tables
        finally:
            conn.close()


class TestConnectionContextManager:
    """Step 5: Connection context manager."""

    def test_context_manager_yields_connection(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import connect

        with connect() as conn:
            assert isinstance(conn, sqlite3.Connection)

    def test_context_manager_commits_on_success(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import init_database, connect

        init_database()
        with connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, workspace_path) VALUES (?, ?, ?)",
                ("p1", "Test Project", "/tmp/test"),
            )

        # Verify data persisted after context exit
        verify_conn = sqlite3.connect(db_path)
        try:
            cursor = verify_conn.execute("SELECT name FROM projects WHERE id='p1'")
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "Test Project"
        finally:
            verify_conn.close()

    def test_context_manager_rolls_back_on_exception(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import init_database, connect

        init_database()
        with pytest.raises(ValueError):
            with connect() as conn:
                conn.execute(
                    "INSERT INTO projects (id, name, workspace_path) VALUES (?, ?, ?)",
                    ("p2", "Bad Project", "/tmp/bad"),
                )
                raise ValueError("Simulated error")

        # Verify data was NOT persisted
        verify_conn = sqlite3.connect(db_path)
        try:
            cursor = verify_conn.execute("SELECT name FROM projects WHERE id='p2'")
            row = cursor.fetchone()
            assert row is None
        finally:
            verify_conn.close()

    def test_context_manager_closes_connection(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", db_path)
        from bob3.db import connect

        with connect() as conn:
            pass

        # Connection should be closed after context exit
        with pytest.raises(Exception):
            conn.execute("SELECT 1")

    def test_context_manager_accepts_explicit_path(self, tmp_path):
        db_path = tmp_path / "explicit.db"
        from bob3.db import connect

        with connect(db_path=db_path) as conn:
            assert isinstance(conn, sqlite3.Connection)


class TestAllTablesAndViews:
    """Step 7: Verify all tables and views are created by init_database."""

    EXPECTED_TABLES = [
        "projects",
        "features",
        "tasks",
        "feature_dependencies",
        "task_dependencies",
        "evidence_artifacts",
        "review_history",
        "feature_review_issues",
        "bug_ledger",
        "calibration_data",
        "calibration_alerts",
        "regression_events",
        "rollback_events",
        "resource_checkpoints",
        "flaky_test_runs",
        "sub_agent_runs",
        "confidence_history",
        "readiness_history",
        "scope_changes",
        "forgetting_events",
        "execution_logs",
        "research_results",
        "reference_documents",
        "feature_references",
    ]

    EXPECTED_VIEWS = [
        "features_ready",
        "features_needing_refinement",
        "features_pending_decomposition",
        "features_blocked",
        "features_needs_human",
        "unresolved_issues",
        "reviews_pending",
        "review_timeouts",
        "stale_evidence",
        "calibration_drift_summary",
        "active_regressions",
        "flaky_tests_pending",
        "scope_creep_alerts",
        "potential_gaming",
        "test_integrity_violations",
        "resource_usage",
        "active_bugs",
        "orphaned_features",
        "oversized_features",
    ]

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path, monkeypatch):
        self.db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", self.db_path)
        from bob3.db import init_database

        init_database()

    def test_all_tables_created(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]
            missing = [t for t in self.EXPECTED_TABLES if t not in tables]
            assert not missing, f"Missing tables after init_database: {missing}"
        finally:
            conn.close()

    def test_all_views_created(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
            )
            views = [row[0] for row in cursor.fetchall()]
            missing = [v for v in self.EXPECTED_VIEWS if v not in views]
            assert not missing, f"Missing views after init_database: {missing}"
        finally:
            conn.close()
