"""Tests for F003: Database schema file (schema.sql) with complete Bob3 v2.1 schema."""

import pathlib
import sqlite3
import tempfile

import pytest

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_PATH = WORKSPACE / "src" / "bob3" / "schema.sql"


class TestSchemaFileExists:
    """Step 1: src/bob3/schema.sql must exist."""

    def test_schema_file_exists(self):
        assert SCHEMA_PATH.is_file(), "src/bob3/schema.sql must exist"

    def test_schema_file_is_not_empty(self):
        content = SCHEMA_PATH.read_text()
        assert len(content.strip()) > 0, "schema.sql must not be empty"


class TestSchemaIsValidSQL:
    """Step 7: Schema must be valid SQL that SQLite can execute."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = tmp_path / "test.db"
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        schema_sql = SCHEMA_PATH.read_text()
        self.conn.executescript(schema_sql)
        yield
        self.conn.close()

    def test_schema_executes_without_errors(self):
        # If we got here, the schema executed successfully in the fixture
        cursor = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert len(tables) > 0, "Schema must create at least one table"

    def test_schema_is_idempotent(self):
        """Schema should be safe to re-execute (using IF NOT EXISTS)."""
        schema_sql = SCHEMA_PATH.read_text()
        # Should not raise - all CREATE statements use IF NOT EXISTS
        self.conn.executescript(schema_sql)


class TestCoreTables:
    """Step 2: All core table definitions must be present."""

    CORE_TABLES = [
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
    ]

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = tmp_path / "test.db"
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        schema_sql = SCHEMA_PATH.read_text()
        self.conn.executescript(schema_sql)
        yield
        self.conn.close()

    def _get_tables(self):
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]

    @pytest.mark.parametrize("table_name", CORE_TABLES)
    def test_core_table_exists(self, table_name):
        tables = self._get_tables()
        assert table_name in tables, f"Core table '{table_name}' must exist in schema"

    def test_all_core_tables_present(self):
        tables = self._get_tables()
        missing = [t for t in self.CORE_TABLES if t not in tables]
        assert not missing, f"Missing core tables: {missing}"


class TestBob3SpecificTables:
    """Step 3: Bob3-specific tables must be present."""

    BOB3_TABLES = [
        "research_results",
        "reference_documents",
        "feature_references",
    ]

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = tmp_path / "test.db"
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        schema_sql = SCHEMA_PATH.read_text()
        self.conn.executescript(schema_sql)
        yield
        self.conn.close()

    def _get_tables(self):
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]

    @pytest.mark.parametrize("table_name", BOB3_TABLES)
    def test_bob3_table_exists(self, table_name):
        tables = self._get_tables()
        assert table_name in tables, f"Bob3 table '{table_name}' must exist in schema"


class TestIndexes:
    """Step 4: All indexes must be present."""

    EXPECTED_INDEXES = [
        "idx_features_project",
        "idx_features_status",
        "idx_features_risk",
        "idx_features_readiness",
        "idx_features_parent",
        "idx_features_priority",
        "idx_tasks_feature",
        "idx_tasks_project",
        "idx_tasks_status",
        "idx_tasks_class",
        "idx_tasks_flaky",
        "idx_evidence_feature",
        "idx_evidence_task",
        "idx_evidence_current",
        "idx_evidence_env_match",
        "idx_review_history_feature",
        "idx_review_history_verdict",
        "idx_review_history_timeout",
        "idx_review_issues_feature",
        "idx_review_issues_resolved",
        "idx_calibration_class",
        "idx_bug_ledger_project",
        "idx_bug_ledger_blame",
        "idx_regression_affected",
        "idx_regression_causing",
        "idx_rollback_feature",
        "idx_checkpoints_feature",
        "idx_checkpoints_resumable",
        "idx_flaky_runs_task",
        "idx_sub_agent_runs_project",
        "idx_sub_agent_runs_purpose",
        "idx_readiness_history_feature",
        "idx_scope_changes_feature",
        "idx_scope_changes_approval",
        "idx_execution_logs_project",
        "idx_forgetting_project",
        "idx_forgetting_target",
        "idx_forgetting_action",
    ]

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = tmp_path / "test.db"
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        schema_sql = SCHEMA_PATH.read_text()
        self.conn.executescript(schema_sql)
        yield
        self.conn.close()

    def _get_indexes(self):
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]

    @pytest.mark.parametrize("index_name", EXPECTED_INDEXES)
    def test_index_exists(self, index_name):
        indexes = self._get_indexes()
        assert index_name in indexes, f"Index '{index_name}' must exist in schema"

    def test_all_indexes_present(self):
        indexes = self._get_indexes()
        missing = [i for i in self.EXPECTED_INDEXES if i not in indexes]
        assert not missing, f"Missing indexes: {missing}"


class TestViews:
    """Step 5: All views must be present."""

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
    def setup_db(self, tmp_path):
        self.db_path = tmp_path / "test.db"
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        schema_sql = SCHEMA_PATH.read_text()
        self.conn.executescript(schema_sql)
        yield
        self.conn.close()

    def _get_views(self):
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]

    @pytest.mark.parametrize("view_name", EXPECTED_VIEWS)
    def test_view_exists(self, view_name):
        views = self._get_views()
        assert view_name in views, f"View '{view_name}' must exist in schema"

    def test_all_views_present(self):
        views = self._get_views()
        missing = [v for v in self.EXPECTED_VIEWS if v not in views]
        assert not missing, f"Missing views: {missing}"

    @pytest.mark.parametrize("view_name", EXPECTED_VIEWS)
    def test_view_is_queryable(self, view_name):
        """Each view should be queryable without errors."""
        cursor = self.conn.execute(f"SELECT * FROM {view_name} LIMIT 0")
        assert cursor.description is not None or cursor.description is None  # Just confirm no exception


class TestTitansMemoryExclusion:
    """Step 6: project_memory and lessons_learned should NOT exist as local tables."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = tmp_path / "test.db"
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        schema_sql = SCHEMA_PATH.read_text()
        self.conn.executescript(schema_sql)
        yield
        self.conn.close()

    def _get_tables(self):
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]

    def test_no_project_memory_table(self):
        tables = self._get_tables()
        assert "project_memory" not in tables, (
            "project_memory should NOT be a local table - it's handled by TITANS Memory MCP"
        )

    def test_no_lessons_learned_table(self):
        tables = self._get_tables()
        assert "lessons_learned" not in tables, (
            "lessons_learned should NOT be a local table - it's handled by TITANS Memory MCP"
        )

    def test_schema_has_titans_memory_comments(self):
        """Schema should have comments about bob3-memory handling project memory and lessons.

        Originally checked for "TITANS Memory MCP" wording; bob3 now uses
        bob3-memory (the legacy column name `titans_memory_id` is intentionally
        retained for backwards compatibility).
        """
        content = SCHEMA_PATH.read_text()
        assert "bob3-memory" in content, (
            "Schema should mention bob3-memory (the external memory backend)"
        )


class TestKeyTableColumns:
    """Verify key columns exist in important tables."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = tmp_path / "test.db"
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        schema_sql = SCHEMA_PATH.read_text()
        self.conn.executescript(schema_sql)
        yield
        self.conn.close()

    def _get_columns(self, table_name):
        cursor = self.conn.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor.fetchall()]

    def test_projects_columns(self):
        cols = self._get_columns("projects")
        expected = ["id", "name", "workspace_path", "status", "total_cost_usd",
                     "max_cost_usd", "spec_hash", "environment_fingerprint",
                     "created_at", "updated_at"]
        for col in expected:
            assert col in cols, f"projects table missing column: {col}"

    def test_features_columns(self):
        cols = self._get_columns("features")
        expected = ["id", "project_id", "parent_feature_id", "decomposition_depth",
                     "name", "description", "acceptance_criteria", "status",
                     "priority", "risk_category", "conf_spec_understanding",
                     "conf_impl_correctness", "conf_test_adequacy",
                     "readiness_score", "refinement_attempts",
                     "exceeds_size_limits", "completion_mode",
                     "created_at", "updated_at"]
        for col in expected:
            assert col in cols, f"features table missing column: {col}"

    def test_tasks_columns(self):
        cols = self._get_columns("tasks")
        expected = ["id", "feature_id", "project_id", "type", "task_class",
                     "title", "status", "conf_spec_understanding",
                     "conf_impl_correctness", "conf_test_adequacy",
                     "readiness_score", "attempts", "max_attempts",
                     "is_flaky", "created_at", "updated_at"]
        for col in expected:
            assert col in cols, f"tasks table missing column: {col}"

    def test_sub_agent_runs_has_mcp_enabled(self):
        cols = self._get_columns("sub_agent_runs")
        assert "mcp_enabled" in cols, "sub_agent_runs should have mcp_enabled column for Bob3"

    def test_research_results_columns(self):
        cols = self._get_columns("research_results")
        expected = ["id", "feature_id", "project_id", "agent_run_id",
                     "query", "findings", "sources", "code_examples",
                     "applied", "created_at"]
        for col in expected:
            assert col in cols, f"research_results table missing column: {col}"

    def test_reference_documents_columns(self):
        cols = self._get_columns("reference_documents")
        expected = ["id", "project_id", "file_path", "title",
                     "extracted_text", "page_count", "sections", "created_at"]
        for col in expected:
            assert col in cols, f"reference_documents table missing column: {col}"

    def test_feature_references_columns(self):
        cols = self._get_columns("feature_references")
        expected = ["feature_id", "reference_id", "section_hint"]
        for col in expected:
            assert col in cols, f"feature_references table missing column: {col}"

    def test_bug_ledger_has_titans_memory_id(self):
        cols = self._get_columns("bug_ledger")
        assert "titans_memory_id" in cols, "bug_ledger should have titans_memory_id for TITANS integration"

    def test_rollback_events_has_titans_memory_id(self):
        cols = self._get_columns("rollback_events")
        assert "titans_memory_id" in cols, "rollback_events should have titans_memory_id for TITANS integration"
