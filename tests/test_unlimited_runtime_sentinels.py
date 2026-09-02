"""Persisted sentinels for Bob's explicitly unlimited runtime controls."""

from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture(autouse=True)
def _clear_runtime_limit_env(monkeypatch):
    monkeypatch.delenv("BOB_MAX_REFINEMENT_ATTEMPTS", raising=False)
    monkeypatch.delenv("BOB_MAX_COST_USD", raising=False)


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "bob.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(path))

    from bob.db import init_database

    init_database()
    return path


@pytest.mark.parametrize("value", ["unlimited", "none", " UNLIMITED "])
def test_refinement_unlimited_spellings_resolve_to_sqlite_int64(monkeypatch, value):
    from bob.models import SQLITE_INT64_MAX, resolve_max_refinement_attempts

    monkeypatch.setenv("BOB_MAX_REFINEMENT_ATTEMPTS", value)

    assert resolve_max_refinement_attempts() == SQLITE_INT64_MAX


def test_refinement_default_and_numeric_override(monkeypatch):
    from bob.models import resolve_max_refinement_attempts

    assert resolve_max_refinement_attempts() == 5

    monkeypatch.setenv("BOB_MAX_REFINEMENT_ATTEMPTS", "37")
    assert resolve_max_refinement_attempts() == 37


@pytest.mark.parametrize("value", ["forever", "0", "-2", "9223372036854775808"])
def test_invalid_refinement_limit_is_rejected(monkeypatch, value):
    from bob.models import resolve_max_refinement_attempts

    monkeypatch.setenv("BOB_MAX_REFINEMENT_ATTEMPTS", value)

    with pytest.raises(ValueError, match="BOB_MAX_REFINEMENT_ATTEMPTS"):
        resolve_max_refinement_attempts()


def test_feature_model_uses_refinement_sentinel(monkeypatch):
    from bob.models import Feature, SQLITE_INT64_MAX

    monkeypatch.setenv("BOB_MAX_REFINEMENT_ATTEMPTS", "none")

    feature = Feature(id="feature-model", project_id="project", name="feature")
    assert feature.max_refinement_attempts == SQLITE_INT64_MAX


def test_create_feature_persists_refinement_sentinel(db_path, monkeypatch):
    from bob.db import create_feature, create_project, get_feature
    from bob.models import SQLITE_INT64_MAX

    monkeypatch.setenv("BOB_MAX_REFINEMENT_ATTEMPTS", "unlimited")
    project = create_project(name="project", workspace_path="/tmp")

    feature = create_feature(project_id=project.id, name="feature")
    reloaded = get_feature(feature.id)

    assert feature.max_refinement_attempts == SQLITE_INT64_MAX
    assert reloaded is not None
    assert reloaded.max_refinement_attempts == SQLITE_INT64_MAX

    with sqlite3.connect(db_path) as conn:
        persisted = conn.execute(
            "SELECT max_refinement_attempts FROM features WHERE id = ?",
            (feature.id,),
        ).fetchone()[0]
    assert persisted == SQLITE_INT64_MAX


def test_unlimited_refinement_does_not_demote_at_legacy_limit(db_path, monkeypatch):
    from bob.db import (
        create_feature,
        create_project,
        increment_refinement_attempts,
        update_feature,
    )

    monkeypatch.setenv("BOB_MAX_REFINEMENT_ATTEMPTS", "none")
    project = create_project(name="project", workspace_path="/tmp")
    feature = create_feature(
        project_id=project.id,
        name="feature",
        status="ready",
    )
    update_feature(feature.id, refinement_attempts=4)

    updated = increment_refinement_attempts(feature.id)

    assert updated is not None
    assert updated.refinement_attempts == 5
    assert updated.status == "ready"


@pytest.mark.parametrize(
    ("attempts", "maximum", "expected_outcome", "expected_status"),
    [
        (0, 2, "UNDER_LIMIT", "ready"),
        (1, 2, "EXHAUSTED", "needs_human"),
    ],
)
def test_atomic_attempt_charge_routes_boundary_status(
    db_path, attempts, maximum, expected_outcome, expected_status
):
    from bob.db import (
        charge_refinement_attempt,
        create_feature,
        create_project,
        update_feature,
    )

    project = create_project(name="project", workspace_path="/tmp")
    feature = create_feature(
        project_id=project.id,
        name="feature",
        status="executing",
        max_refinement_attempts=maximum,
    )
    update_feature(feature.id, refinement_attempts=attempts)

    outcome, updated = charge_refinement_attempt(feature.id)

    assert outcome == expected_outcome
    assert updated is not None
    assert updated.refinement_attempts == attempts + 1
    assert updated.status == expected_status


def test_atomic_attempt_charge_unlimited_saturates_and_missing_is_explicit(
    db_path, monkeypatch
):
    from bob.db import (
        charge_refinement_attempt,
        create_feature,
        create_project,
        update_feature,
    )
    from bob.models import SQLITE_INT64_MAX

    monkeypatch.setenv("BOB_MAX_REFINEMENT_ATTEMPTS", "unlimited")
    project = create_project(name="project", workspace_path="/tmp")
    feature = create_feature(
        project_id=project.id, name="feature", status="executing"
    )
    update_feature(feature.id, refinement_attempts=SQLITE_INT64_MAX)

    outcome, updated = charge_refinement_attempt(feature.id)
    missing_outcome, missing = charge_refinement_attempt("missing")

    assert outcome == "UNDER_LIMIT"
    assert updated is not None
    assert updated.refinement_attempts == SQLITE_INT64_MAX
    assert updated.status == "ready"
    assert (missing_outcome, missing) == ("MISSING", None)


def test_atomic_leaf_parent_and_dependent_completion(db_path):
    from bob.db import (
        add_feature_dependency,
        complete_feature_hierarchy_and_cascade,
        create_child_feature,
        create_feature,
        create_project,
        get_feature,
        update_feature,
    )

    project = create_project(name="project", workspace_path="/tmp")
    parent = create_feature(
        project_id=project.id,
        name="parent",
        status="pending_decomposition",
    )
    first = create_child_feature(
        parent_feature_id=parent.id,
        project_id=project.id,
        name="first",
        status="executing",
    )
    second = create_child_feature(
        parent_feature_id=parent.id,
        project_id=project.id,
        name="second",
        status="completed",
    )
    dependent = create_feature(
        project_id=project.id, name="dependent", status="pending"
    )
    add_feature_dependency(
        feature_id=dependent.id, depends_on_feature_id=parent.id
    )

    promoted = complete_feature_hierarchy_and_cascade(first.id)

    assert get_feature(first.id).status == "completed"
    assert get_feature(second.id).status == "completed"
    assert get_feature(parent.id).status == "completed"
    assert get_feature(dependent.id).status == "ready"
    assert promoted == [dependent.id]


def test_explicit_feature_limit_overrides_unlimited_env(db_path, monkeypatch):
    from bob.db import create_feature, create_project

    monkeypatch.setenv("BOB_MAX_REFINEMENT_ATTEMPTS", "unlimited")
    project = create_project(name="project", workspace_path="/tmp")

    feature = create_feature(
        project_id=project.id,
        name="feature",
        max_refinement_attempts=9,
    )

    assert feature.max_refinement_attempts == 9


@pytest.mark.parametrize("value", ["unlimited", "none", " NONE "])
def test_cost_unlimited_spellings_resolve_to_finite_persisted_sentinel(
    monkeypatch, value
):
    from bob.models import UNLIMITED_MAX_COST_USD, resolve_max_cost_usd

    monkeypatch.setenv("BOB_MAX_COST_USD", value)

    assert resolve_max_cost_usd() == UNLIMITED_MAX_COST_USD


def test_project_model_and_db_persist_unlimited_cost(db_path, monkeypatch):
    from bob.db import create_project, get_project
    from bob.models import Project, UNLIMITED_MAX_COST_USD

    monkeypatch.setenv("BOB_MAX_COST_USD", "unlimited")

    model = Project(id="model", name="model", workspace_path="/tmp")
    persisted = create_project(name="persisted", workspace_path="/tmp")
    reloaded = get_project(persisted.id)

    assert model.max_cost_usd == UNLIMITED_MAX_COST_USD
    assert persisted.max_cost_usd == UNLIMITED_MAX_COST_USD
    assert reloaded is not None
    assert reloaded.max_cost_usd == UNLIMITED_MAX_COST_USD


@pytest.mark.parametrize("value", ["unlimited", "none"])
def test_bob_init_accepts_and_persists_unlimited_cost(
    tmp_path, monkeypatch, value
):
    import bob.cli as cli
    import bob.skills_installer as skills_installer
    from bob.models import UNLIMITED_MAX_COST_USD

    workspace = tmp_path / f"workspace-{value}"
    db_file = tmp_path / f"{value}.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_file))
    monkeypatch.setenv("BOB_MAX_COST_USD", value)
    monkeypatch.setattr(cli, "_check_runtime_dependencies", lambda: None)
    monkeypatch.setattr(cli, "start_mcp_server", lambda: None)
    monkeypatch.setattr(
        skills_installer,
        "install_skills_to_workspace",
        lambda *args, **kwargs: [],
    )

    from click.testing import CliRunner

    result = CliRunner().invoke(cli.init, [str(workspace)])

    assert result.exit_code == 0, result.output
    with sqlite3.connect(db_file) as conn:
        persisted = conn.execute("SELECT max_cost_usd FROM projects").fetchone()[0]
    assert persisted == UNLIMITED_MAX_COST_USD
