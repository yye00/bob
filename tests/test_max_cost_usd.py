"""Tests for per-project cost cap env-override feature.

Covers resolve_max_cost_usd, Project.max_cost_usd default, and
db.create_project max_cost_usd behaviour.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BOB_MAX_COST_USD", raising=False)


class TestResolveMaxCostUsd:
    """Unit tests for bob.models.resolve_max_cost_usd."""

    def test_no_env_returns_unlimited(self):
        from bob.models import resolve_max_cost_usd
        assert resolve_max_cost_usd() == 1_000_000.0

    def test_env_set_returns_that_value(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "250.0")
        from bob.models import resolve_max_cost_usd
        assert resolve_max_cost_usd() == pytest.approx(250.0)

    def test_empty_env_returns_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "")
        from bob.models import resolve_max_cost_usd
        assert resolve_max_cost_usd() == 1_000_000.0

    def test_whitespace_only_env_returns_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "   ")
        from bob.models import resolve_max_cost_usd
        assert resolve_max_cost_usd() == 1_000_000.0

    def test_non_numeric_env_returns_unlimited_not_zero(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "invalid")
        from bob.models import resolve_max_cost_usd
        result = resolve_max_cost_usd()
        assert result == 1_000_000.0
        assert result != 0.0

    def test_nan_env_returns_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "NaN")
        from bob.models import resolve_max_cost_usd
        assert resolve_max_cost_usd() == 1_000_000.0

    def test_inf_env_returns_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "inf")
        from bob.models import resolve_max_cost_usd
        assert resolve_max_cost_usd() == 1_000_000.0

    def test_negative_env_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "-50.0")
        from bob.models import resolve_max_cost_usd
        assert resolve_max_cost_usd() == 0.0

    def test_zero_env_returns_zero(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "0")
        from bob.models import resolve_max_cost_usd
        assert resolve_max_cost_usd() == 0.0

    def test_old_hardcoded_500_is_not_the_default(self):
        from bob.models import resolve_max_cost_usd
        assert resolve_max_cost_usd() != 500.0

    def test_returns_float(self):
        from bob.models import resolve_max_cost_usd
        assert isinstance(resolve_max_cost_usd(), float)


class TestProjectMaxCostUsdDefault:
    """Project.max_cost_usd defaults from env via resolve_max_cost_usd."""

    def test_default_is_unlimited_when_no_env(self):
        from bob.models import Project
        p = Project(id="p1", name="test", workspace_path="/tmp")
        assert p.max_cost_usd == 1_000_000.0

    def test_default_reflects_env_var(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "750.0")
        from bob.models import Project
        p = Project(id="p1", name="test", workspace_path="/tmp")
        assert p.max_cost_usd == pytest.approx(750.0)

    def test_default_is_not_500(self):
        from bob.models import Project
        p = Project(id="p1", name="test", workspace_path="/tmp")
        assert p.max_cost_usd != 500.0

    def test_explicit_value_overrides_default(self):
        from bob.models import Project
        p = Project(id="p1", name="test", workspace_path="/tmp", max_cost_usd=100.0)
        assert p.max_cost_usd == pytest.approx(100.0)

    def test_negative_explicit_value_raises(self):
        from bob.models import Project
        with pytest.raises((ValueError, TypeError)):
            Project(id="p1", name="test", workspace_path="/tmp", max_cost_usd=-1.0)


class TestDbCreateProjectMaxCostUsd:
    """db.create_project persists env-aware max_cost_usd, not hardcoded 500."""

    @pytest.fixture()
    def _db(self, tmp_path, monkeypatch):
        from bob import db
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
        db.init_database(db_path=db_path)
        return db_path

    def test_create_project_uses_env_var(self, monkeypatch, _db):
        monkeypatch.setenv("BOB_MAX_COST_USD", "333.0")
        from bob.db import create_project
        project = create_project(name="p", workspace_path="/tmp", db_path=_db)
        assert project.max_cost_usd == pytest.approx(333.0)

    def test_create_project_default_unlimited_when_no_env(self, _db):
        from bob.db import create_project
        project = create_project(name="p", workspace_path="/tmp", db_path=_db)
        assert project.max_cost_usd == 1_000_000.0

    def test_create_project_not_500_by_default(self, _db):
        from bob.db import create_project
        project = create_project(name="p", workspace_path="/tmp", db_path=_db)
        assert project.max_cost_usd != 500.0

    def test_create_project_explicit_max_cost_honored(self, _db):
        from bob.db import create_project
        project = create_project(name="p", workspace_path="/tmp", db_path=_db, max_cost_usd=42.0)
        assert project.max_cost_usd == pytest.approx(42.0)
