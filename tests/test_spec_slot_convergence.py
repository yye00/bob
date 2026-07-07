"""Tests for bob.spec_slot — convergence detection by stable spec_slot.

Feature a8534447: the convergence detector must compare feature sets across
generations by the stable ``spec_slot`` (derived from the spec YAML key), NOT
by the ``features.id`` UUID (which is minted fresh on every ``bob init``, so a
UUID set-diff is always 100% and convergence can never be detected).

Public functions under test:

  * ``backfill_spec_slot(db_path, spec_path)`` — populate spec_slot for rows
    whose spec_slot is NULL, by matching feature name/title to the spec key.
  * ``check_convergence(db_a, db_b)`` — set-diff completed spec_slots across
    two databases; returns ``(converged, diff)``.
"""
from __future__ import annotations

import contextlib
import os
import pathlib

import pytest
import yaml

from bob import db
from bob.spec_slot import backfill_spec_slot, check_convergence


@contextlib.contextmanager
def _use_db(path: pathlib.Path):
    """Point bob's global db resolution at *path* for the duration of the block.

    create_feature / list_features resolve the database via the
    BOB_DATABASE_PATH env var (they have no db_path parameter), so tests that
    juggle multiple databases must switch the env var per operation.
    """
    prev = os.environ.get("BOB_DATABASE_PATH")
    os.environ["BOB_DATABASE_PATH"] = str(path)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("BOB_DATABASE_PATH", None)
        else:
            os.environ["BOB_DATABASE_PATH"] = prev


def _fresh_db(path: pathlib.Path):
    db.init_database(db_path=path)
    return db.create_project(
        name="P", workspace_path=str(path.parent), db_path=path
    )


def _add_feature(path: pathlib.Path, **kwargs):
    with _use_db(path):
        return db.create_feature(**kwargs)


def _features(path: pathlib.Path, project_id: str):
    with _use_db(path):
        return db.list_features(project_id=project_id)


def _write_spec(path: pathlib.Path, features) -> pathlib.Path:
    path.write_text(yaml.safe_dump({"name": "demo", "features": features}))
    return path


# ---------------------------------------------------------------------------
# check_convergence
# ---------------------------------------------------------------------------


def test_same_feature_set_converges_despite_fresh_uuids(tmp_path):
    """Two dbs whose completed features share spec_slots converge even though
    their UUIDs are entirely disjoint (the core bug this feature fixes)."""
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    pa = _fresh_db(db_a)
    pb = _fresh_db(db_b)

    for slot in ("F-R7-400", "F-R7-401"):
        _add_feature(db_a, project_id=pa.id, name=f"n-{slot}", spec_slot=slot,
                          status="completed")
        _add_feature(db_b, project_id=pb.id, name=f"n-{slot}", spec_slot=slot,
                          status="completed")

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_divergent_feature_sets_do_not_converge(tmp_path):
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    pa = _fresh_db(db_a)
    pb = _fresh_db(db_b)

    _add_feature(db_a, project_id=pa.id, name="x", spec_slot="F-R7-400",
                      status="completed")
    _add_feature(db_b, project_id=pb.id, name="y", spec_slot="F-R7-999",
                      status="completed")

    converged, diff = check_convergence(db_a, db_b)
    assert converged is False
    assert diff == {"F-R7-400", "F-R7-999"}


def test_only_completed_features_count(tmp_path):
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    pa = _fresh_db(db_a)
    pb = _fresh_db(db_b)

    _add_feature(db_a, project_id=pa.id, name="done", spec_slot="F-1",
                      status="completed")
    # Pending feature only in a — must NOT cause divergence.
    _add_feature(db_a, project_id=pa.id, name="pend", spec_slot="F-2",
                      status="pending")
    _add_feature(db_b, project_id=pb.id, name="done", spec_slot="F-1",
                      status="completed")

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True


def test_null_spec_slot_rows_are_ignored(tmp_path):
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    pa = _fresh_db(db_a)
    pb = _fresh_db(db_b)

    _add_feature(db_a, project_id=pa.id, name="s", spec_slot="F-1",
                      status="completed")
    _add_feature(db_a, project_id=pa.id, name="noslot", spec_slot=None,
                      status="completed")
    _add_feature(db_b, project_id=pb.id, name="s", spec_slot="F-1",
                      status="completed")

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True


# ---------------------------------------------------------------------------
# backfill_spec_slot
# ---------------------------------------------------------------------------


def test_backfill_populates_null_rows_by_name(tmp_path):
    db_path = tmp_path / "bob.db"
    proj = _fresh_db(db_path)
    _add_feature(db_path, project_id=proj.id, name="Alpha feature",
                      spec_slot=None)
    _add_feature(db_path, project_id=proj.id, name="Beta feature",
                      spec_slot=None)

    spec = _write_spec(tmp_path / "spec.yaml", [
        {"key": "F-100", "title": "Alpha feature"},
        {"key": "F-200", "title": "Beta feature"},
    ])

    updated = backfill_spec_slot(db_path, spec)
    assert updated == 2

    feats = {f.name: f.spec_slot
             for f in _features(db_path, project_id=proj.id)}
    assert feats["Alpha feature"] == "F-100"
    assert feats["Beta feature"] == "F-200"


def test_backfill_dict_of_dicts_format(tmp_path):
    db_path = tmp_path / "bob.db"
    proj = _fresh_db(db_path)
    _add_feature(db_path, project_id=proj.id, name="Widget", spec_slot=None)

    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump({"features": {"F-9": {"title": "Widget"}}}))

    updated = backfill_spec_slot(db_path, spec_path)
    assert updated == 1
    feats = _features(db_path, project_id=proj.id)
    assert feats[0].spec_slot == "F-9"


def test_backfill_does_not_overwrite_existing_slots(tmp_path):
    db_path = tmp_path / "bob.db"
    proj = _fresh_db(db_path)
    _add_feature(db_path, project_id=proj.id, name="Kept", spec_slot="ORIGINAL")

    spec = _write_spec(tmp_path / "spec.yaml", [{"key": "NEW", "title": "Kept"}])
    updated = backfill_spec_slot(db_path, spec)
    assert updated == 0
    feats = _features(db_path, project_id=proj.id)
    assert feats[0].spec_slot == "ORIGINAL"


def test_backfill_unmatched_name_left_null(tmp_path):
    db_path = tmp_path / "bob.db"
    proj = _fresh_db(db_path)
    _add_feature(db_path, project_id=proj.id, name="Orphan", spec_slot=None)

    spec = _write_spec(tmp_path / "spec.yaml", [{"key": "F-1", "title": "Something else"}])
    updated = backfill_spec_slot(db_path, spec)
    assert updated == 0
    feats = _features(db_path, project_id=proj.id)
    assert feats[0].spec_slot is None


def test_backfill_then_convergence_end_to_end(tmp_path):
    """After backfilling, two same-set generations converge."""
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    pa = _fresh_db(db_a)
    pb = _fresh_db(db_b)

    for p, dbp in ((pa, db_a), (pb, db_b)):
        _add_feature(dbp, project_id=p.id, name="Feat One", spec_slot=None,
                          status="completed")

    spec = _write_spec(tmp_path / "spec.yaml", [{"key": "F-ONE", "title": "Feat One"}])
    backfill_spec_slot(db_a, spec)
    backfill_spec_slot(db_b, spec)

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_check_convergence_rejects_invalid_input():
    with pytest.raises(ValueError):
        check_convergence(None, "/tmp/x.db")
    with pytest.raises(ValueError):
        check_convergence("/tmp/x.db", "")


def test_backfill_rejects_invalid_db_path():
    with pytest.raises(ValueError):
        backfill_spec_slot("", "/tmp/spec.yaml")
