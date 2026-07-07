"""Tests for the env-overridable per-project cost cap.

The old hardcoded 500.0 per-project ceiling mass-demoted every remaining feature
to needs_human once a long run approached it. The fix makes the ceiling read
BOB_MAX_COST_USD when set and otherwise default to an effectively-unlimited
value (1_000_000.0). This must hold in all THREE persistence sources:
  1. bob.models.resolve_max_cost_usd / Project.max_cost_usd default,
  2. bob.db.create_project default,
  3. the schema.sql projects.max_cost_usd column DEFAULT.
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest

from bob.db import create_project, init_database
from bob.models import Project, resolve_max_cost_usd


UNLIMITED = 1_000_000.0


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BOB_MAX_COST_USD", raising=False)


class TestResolveMaxCostUsd:
    def test_absent_env_defaults_unlimited(self):
        assert resolve_max_cost_usd() == UNLIMITED

    def test_env_value_honored(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "250.5")
        assert resolve_max_cost_usd() == pytest.approx(250.5)

    def test_explicit_zero_budget_honored(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "0")
        assert resolve_max_cost_usd() == 0.0

    def test_malformed_env_falls_back_unlimited_not_zero(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "not-a-number")
        result = resolve_max_cost_usd()
        assert result == UNLIMITED
        assert result != 0.0

    def test_never_the_old_hardcoded_500(self):
        assert resolve_max_cost_usd() != 500.0


class TestProjectModelDefault:
    def test_project_default_max_cost_is_unlimited(self):
        p = Project(id="p1", name="n", workspace_path="/tmp/x")
        assert p.max_cost_usd == UNLIMITED

    def test_project_default_honors_env(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "42")
        p = Project(id="p2", name="n", workspace_path="/tmp/x")
        assert p.max_cost_usd == pytest.approx(42.0)


class TestCreateProjectPersistence:
    def _db(self, tmp_path: pathlib.Path) -> pathlib.Path:
        db_path = tmp_path / "bob.db"
        init_database(db_path=db_path)
        return db_path

    def test_create_project_default_persists_unlimited(self, tmp_path):
        db_path = self._db(tmp_path)
        project = create_project(
            name="proj", workspace_path=str(tmp_path), db_path=db_path
        )
        assert project.max_cost_usd == UNLIMITED

        con = sqlite3.connect(db_path)
        try:
            row = con.execute(
                "SELECT max_cost_usd FROM projects WHERE id = ?", (project.id,)
            ).fetchone()
        finally:
            con.close()
        assert row is not None
        assert row[0] == UNLIMITED
        assert row[0] != 500.0

    def test_create_project_honors_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "750")
        db_path = self._db(tmp_path)
        project = create_project(
            name="proj", workspace_path=str(tmp_path), db_path=db_path
        )
        assert project.max_cost_usd == pytest.approx(750.0)

        con = sqlite3.connect(db_path)
        try:
            row = con.execute(
                "SELECT max_cost_usd FROM projects WHERE id = ?", (project.id,)
            ).fetchone()
        finally:
            con.close()
        assert row[0] == pytest.approx(750.0)

    def test_create_project_explicit_arg_overrides_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "750")
        db_path = self._db(tmp_path)
        project = create_project(
            name="proj",
            workspace_path=str(tmp_path),
            max_cost_usd=123.0,
            db_path=db_path,
        )
        assert project.max_cost_usd == pytest.approx(123.0)


class TestSchemaDefault:
    def test_schema_column_default_not_500(self, tmp_path):
        db_path = tmp_path / "bob.db"
        init_database(db_path=db_path)
        con = sqlite3.connect(db_path)
        try:
            con.execute(
                "INSERT INTO projects (id, name, workspace_path, status) "
                "VALUES (?, ?, ?, ?)",
                ("raw1", "n", str(tmp_path), "planning"),
            )
            con.commit()
            row = con.execute(
                "SELECT max_cost_usd FROM projects WHERE id = ?", ("raw1",)
            ).fetchone()
        finally:
            con.close()
        assert row[0] == UNLIMITED
        assert row[0] != 500.0
