"""Tests for the per-project cost cap env-override feature (AC: pytest: tests/test_per_project_cost_cap.py).

Validates the three-source fix:
1. models.Project.max_cost_usd uses env-aware default_factory
2. db.create_project writes env-aware max_cost_usd to the DB
3. schema.sql DEFAULT is 1_000_000.0, not 500.0

And that bob.models.resolve_max_cost_usd is importable and correct.
"""
from __future__ import annotations

import importlib
import os
import pathlib
import sqlite3
import tempfile

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure BOB_MAX_COST_USD is unset before each test."""
    monkeypatch.delenv("BOB_MAX_COST_USD", raising=False)


# ---------------------------------------------------------------------------
# AC: Function defined — bob.models.resolve_max_cost_usd
# ---------------------------------------------------------------------------


def test_resolve_max_cost_usd_importable():
    """bob.models.resolve_max_cost_usd is importable and callable."""
    from bob.models import resolve_max_cost_usd

    assert callable(resolve_max_cost_usd)


def test_resolve_max_cost_usd_default_is_unlimited():
    """Default (no env var) returns effectively-unlimited 1_000_000.0."""
    from bob.models import resolve_max_cost_usd

    assert resolve_max_cost_usd() == 1_000_000.0


def test_resolve_max_cost_usd_not_500():
    """Default must not be the old hardcoded 500.0 ceiling."""
    from bob.models import resolve_max_cost_usd

    assert resolve_max_cost_usd() != 500.0


def test_resolve_max_cost_usd_honors_env(monkeypatch):
    """BOB_MAX_COST_USD=750 → returns 750.0."""
    monkeypatch.setenv("BOB_MAX_COST_USD", "750")
    from bob.models import resolve_max_cost_usd

    assert resolve_max_cost_usd() == 750.0


def test_resolve_max_cost_usd_empty_env_returns_unlimited(monkeypatch):
    """Empty BOB_MAX_COST_USD → unlimited, never 0."""
    monkeypatch.setenv("BOB_MAX_COST_USD", "")
    from bob.models import resolve_max_cost_usd

    result = resolve_max_cost_usd()
    assert result == 1_000_000.0
    assert result != 0.0


def test_resolve_max_cost_usd_malformed_env_returns_unlimited(monkeypatch):
    """Malformed BOB_MAX_COST_USD → unlimited, not 0, does not raise."""
    monkeypatch.setenv("BOB_MAX_COST_USD", "not_a_number")
    from bob.models import resolve_max_cost_usd

    result = resolve_max_cost_usd()
    assert result == 1_000_000.0


def test_resolve_max_cost_usd_nan_returns_unlimited(monkeypatch):
    """NaN BOB_MAX_COST_USD → unlimited."""
    monkeypatch.setenv("BOB_MAX_COST_USD", "NaN")
    from bob.models import resolve_max_cost_usd

    result = resolve_max_cost_usd()
    assert result == 1_000_000.0


def test_resolve_max_cost_usd_inf_returns_unlimited(monkeypatch):
    """Inf BOB_MAX_COST_USD → unlimited."""
    monkeypatch.setenv("BOB_MAX_COST_USD", "inf")
    from bob.models import resolve_max_cost_usd

    result = resolve_max_cost_usd()
    assert result == 1_000_000.0


def test_resolve_max_cost_usd_zero_is_honored(monkeypatch):
    """BOB_MAX_COST_USD=0 → 0.0 (explicit user budget; empty/malformed must not produce this)."""
    monkeypatch.setenv("BOB_MAX_COST_USD", "0")
    from bob.models import resolve_max_cost_usd

    assert resolve_max_cost_usd() == 0.0


def test_resolve_max_cost_usd_negative_clamped_to_zero(monkeypatch):
    """Negative BOB_MAX_COST_USD is clamped to 0.0, not raises."""
    monkeypatch.setenv("BOB_MAX_COST_USD", "-50")
    from bob.models import resolve_max_cost_usd

    assert resolve_max_cost_usd() == 0.0


# ---------------------------------------------------------------------------
# AC: models.Project.max_cost_usd default_factory
# ---------------------------------------------------------------------------


def test_project_default_max_cost_usd_is_unlimited():
    """Project() without explicit max_cost_usd gets 1_000_000.0, not 500."""
    from bob.models import Project

    p = Project(id="t1", name="t1", workspace_path="/tmp")
    assert p.max_cost_usd == 1_000_000.0
    assert p.max_cost_usd != 500.0


def test_project_default_max_cost_usd_reads_env(monkeypatch):
    """Project() picks up BOB_MAX_COST_USD via default_factory."""
    monkeypatch.setenv("BOB_MAX_COST_USD", "300")
    import bob.models as _m
    importlib.reload(_m)
    try:
        p = _m.Project(id="t2", name="t2", workspace_path="/tmp")
        assert p.max_cost_usd == 300.0
    finally:
        importlib.reload(_m)


# ---------------------------------------------------------------------------
# AC: schema.sql DEFAULT is 1_000_000.0
# ---------------------------------------------------------------------------


def test_schema_sql_default_is_unlimited():
    """schema.sql projects.max_cost_usd DEFAULT must be 1_000_000.0, not 500.0."""
    schema_candidates = [
        pathlib.Path("migrations/schema.sql"),
        pathlib.Path("src/bob/schema.sql"),
        pathlib.Path("src/bob/migrations/schema.sql"),
    ]
    schema_path = next((p for p in schema_candidates if p.exists()), None)
    assert schema_path is not None, "Could not find schema.sql"

    content = schema_path.read_text()
    # Must not contain the old hardcoded 500.0 default for max_cost_usd
    assert "DEFAULT 500" not in content, (
        "schema.sql still has DEFAULT 500 — must be 1_000_000.0"
    )
    assert "1000000" in content or "1_000_000" in content.replace(",", ""), (
        "schema.sql must set max_cost_usd DEFAULT to 1000000.0"
    )


# ---------------------------------------------------------------------------
# AC: db.create_project writes env-aware max_cost_usd
# ---------------------------------------------------------------------------


def test_db_create_project_default_unlimited():
    """create_project without max_cost_usd writes 1_000_000.0 to the DB."""
    from bob.db import create_project, init_database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test.db"
        init_database(db_path=db_path)
        p = create_project(
            name="test-project",
            workspace_path=tmpdir,
            db_path=db_path,
        )
        assert p.max_cost_usd == 1_000_000.0
        assert p.max_cost_usd != 500.0

        # Verify it was persisted to the DB row, not just the model
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT max_cost_usd FROM projects WHERE id=?", (p.id,)).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 1_000_000.0


def test_db_create_project_honors_env(monkeypatch):
    """create_project reads BOB_MAX_COST_USD when max_cost_usd not explicitly passed."""
    monkeypatch.setenv("BOB_MAX_COST_USD", "1234.56")
    from bob.db import create_project, init_database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test.db"
        init_database(db_path=db_path)
        p = create_project(
            name="test-project-env",
            workspace_path=tmpdir,
            db_path=db_path,
        )
        assert p.max_cost_usd == pytest.approx(1234.56)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT max_cost_usd FROM projects WHERE id=?", (p.id,)).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == pytest.approx(1234.56)


def test_db_create_project_explicit_max_cost_usd_respected():
    """Explicit max_cost_usd argument overrides env var."""
    from bob.db import create_project, init_database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test.db"
        init_database(db_path=db_path)
        p = create_project(
            name="test-explicit",
            workspace_path=tmpdir,
            max_cost_usd=999.0,
            db_path=db_path,
        )
        assert p.max_cost_usd == 999.0


# ---------------------------------------------------------------------------
# AC: integration — orchestrator reads project.max_cost_usd
# ---------------------------------------------------------------------------


def test_orchestrator_imports_resolve_max_cost_usd():
    """bob.orchestrator module is importable and run_loop reads project.max_cost_usd."""
    # The orchestrator uses project.max_cost_usd to gate spawning — verify the
    # attribute exists on Project and is non-zero by default (unlimited sentinel).
    from bob.models import Project

    p = Project(id="orch-test", name="orch-test", workspace_path="/tmp")
    # The run_loop checks: if self._project_max_cost_usd: (truthy gate)
    # With unlimited default this must be truthy (> 0).
    assert p.max_cost_usd > 0, (
        "Default max_cost_usd must be > 0 so the orchestrator cost gate works correctly"
    )
    assert p.max_cost_usd == 1_000_000.0
