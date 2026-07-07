"""Tests for the env-overridable per-project cost cap.

Covers the three persisted sources of the max_cost_usd default:
  1. bob.models.Project.max_cost_usd (Pydantic default_factory)
  2. bob.db.create_project (env-aware default when max_cost_usd is None)
  3. the `bob init` CLI command (raw INSERT sets max_cost_usd from env)

The old hardcoded 500.0 ceiling mass-NH'd every remaining feature once a long
run approached it; the effective default MUST now be effectively-unlimited
(1_000_000.0) unless BOB_MAX_COST_USD is set to a finite value.
"""

from __future__ import annotations

import pathlib

import pytest


UNLIMITED = 1_000_000.0


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BOB_MAX_COST_USD", raising=False)


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(p))
    from bob.db import init_database

    init_database()
    return p


class TestModelsDefault:
    """bob.models.Project default_factory reads BOB_MAX_COST_USD."""

    def test_default_is_unlimited_not_500(self):
        from bob.models import Project

        p = Project(id="m1", name="m1", workspace_path="/tmp")
        assert p.max_cost_usd == UNLIMITED
        assert p.max_cost_usd != 500.0

    def test_env_override_honored(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "250")
        from bob.models import Project

        p = Project(id="m2", name="m2", workspace_path="/tmp")
        assert p.max_cost_usd == 250.0

    def test_malformed_env_falls_back_to_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "not-a-number")
        from bob.models import Project

        p = Project(id="m3", name="m3", workspace_path="/tmp")
        assert p.max_cost_usd == UNLIMITED


class TestCreateProjectDefault:
    """bob.db.create_project persists an env-aware max_cost_usd, never 500.0."""

    def test_default_persisted_is_unlimited(self, db_path):
        from bob.db import create_project, get_project

        proj = create_project(name="p1", workspace_path="/tmp")
        assert proj.max_cost_usd == UNLIMITED

        reloaded = get_project(proj.id)
        assert reloaded is not None
        assert reloaded.max_cost_usd == UNLIMITED
        assert reloaded.max_cost_usd != 500.0

    def test_env_override_persisted(self, db_path, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "42.5")
        from bob.db import create_project, get_project

        proj = create_project(name="p2", workspace_path="/tmp")
        assert proj.max_cost_usd == 42.5

        reloaded = get_project(proj.id)
        assert reloaded.max_cost_usd == 42.5

    def test_explicit_arg_overrides_env(self, db_path, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "42.5")
        from bob.db import create_project

        proj = create_project(name="p3", workspace_path="/tmp", max_cost_usd=7.0)
        assert proj.max_cost_usd == 7.0

    def test_malformed_env_does_not_persist_zero(self, db_path, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "garbage")
        from bob.db import create_project

        proj = create_project(name="p4", workspace_path="/tmp")
        assert proj.max_cost_usd == UNLIMITED
        assert proj.max_cost_usd != 0.0


class TestSchemaColumnDefault:
    """schema.sql projects.max_cost_usd column default is no longer 500.0."""

    def test_schema_default_is_unlimited(self, db_path):
        from bob.db import connect

        with connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, workspace_path, status) "
                "VALUES (?, ?, ?, ?)",
                ("bare", "bare", "/tmp", "planning"),
            )
        with connect() as conn:
            row = conn.execute(
                "SELECT max_cost_usd FROM projects WHERE id = ?", ("bare",)
            ).fetchone()
        assert row[0] == UNLIMITED
        assert row[0] != 500.0


class TestBobInitCliDefault:
    """`bob init` persists max_cost_usd from BOB_MAX_COST_USD, not the old 500.0."""

    def _run_init(self, tmp_path, monkeypatch, subdir):
        """Invoke the `bob init` Click command with heavy side effects patched."""
        import sqlite3

        import bob.cli as cli

        workspace = tmp_path / subdir
        db_file = tmp_path / f"{subdir}.db"
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_file))

        # Stub out runtime/MCP/skills side effects that require external tools.
        monkeypatch.setattr(cli, "_check_runtime_dependencies", lambda: None)
        monkeypatch.setattr(cli, "start_mcp_server", lambda: None)
        import bob.skills_installer as _skills

        monkeypatch.setattr(
            _skills, "install_skills_to_workspace", lambda *a, **k: []
        )

        from click.testing import CliRunner

        result = CliRunner().invoke(cli.init, [str(workspace)])
        assert result.exit_code == 0, result.output

        conn = sqlite3.connect(str(db_file))
        try:
            return conn.execute("SELECT max_cost_usd FROM projects").fetchall()
        finally:
            conn.close()

    def test_init_persists_unlimited_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BOB_MAX_COST_USD", raising=False)
        rows = self._run_init(tmp_path, monkeypatch, "ws")
        assert rows, "bob init did not create a project row"
        assert all(r[0] != 500.0 for r in rows)
        assert any(r[0] == UNLIMITED for r in rows)

    def test_init_honors_env_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "99")
        rows = self._run_init(tmp_path, monkeypatch, "ws2")
        assert rows
        assert any(r[0] == 99.0 for r in rows)
