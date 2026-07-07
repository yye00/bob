"""bob.spec_slot — stable cross-generation feature identity.

Feature IDs (``features.id``) are minted as fresh UUIDs on every ``bob init``,
so a cross-generation set-diff by UUID is always 100% and convergence can never
be detected. ``spec_slot`` is the stable key derived from the spec YAML (e.g.
``F-R7-400``); comparing completed feature sets by ``spec_slot`` lets two
generations that built the same features be recognized as converged.

Public API:

  * :func:`backfill_spec_slot` — populate ``spec_slot`` for rows whose value is
    NULL, matching feature name/title against the spec YAML.
  * :func:`check_convergence` — set-diff completed ``spec_slot`` values across
    two databases; returns ``(converged, diff)``.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Any, Iterable, Union

from bob.extract import assign_unique_spec_slot
from bob.migrations.add_spec_slot import get_completed_spec_slots

PathLike = Union[str, pathlib.Path]

_RUNNABLE_STATUSES = frozenset({"ready", "pending"})
_COMPLETED_STATUS = "completed"

__all__ = [
    "assign_unique_spec_slot",
    "is_runnable",
    "check_convergence",
    "backfill_spec_slot",
]


def _feature_id(feature: Any) -> str:
    """Return the feature's unique id, raising ValueError if absent.

    The id is the ONLY key used for runnable/claim/complete decisions;
    ``spec_slot`` is for cross-generation matching only (F-R7-400).
    """
    fid = feature.get("id") if isinstance(feature, dict) else getattr(feature, "id", None)
    if fid is None or fid == "":
        raise ValueError(f"feature has no unique id: {feature!r}")
    return str(fid)


def is_runnable(feature: Any, completed_ids: Iterable[str]) -> bool:
    """Return True iff *feature* is runnable given the set of completed ids.

    A feature is runnable when its ``status`` is 'ready' or 'pending' AND every
    id in its ``depends_on`` list is present in *completed_ids*. Eligibility is
    keyed strictly on the feature's unique ``id`` — ``spec_slot`` is never
    consulted, so a completed sibling sharing a spec_slot can never suppress a
    distinct pending feature.

    Args:
        feature: A feature mapping or object exposing ``id`` and ``status``
            (and optional ``depends_on``).
        completed_ids: The unique ids of features already completed.

    Returns:
        True if the feature is runnable now, else False.

    Raises:
        ValueError: If *feature* has no unique ``id``.
    """
    _feature_id(feature)  # validate identity; never key on spec_slot

    if isinstance(feature, dict):
        status = feature.get("status")
        deps = feature.get("depends_on") or []
    else:
        status = getattr(feature, "status", None)
        deps = getattr(feature, "depends_on", None) or []

    if status not in _RUNNABLE_STATUSES:
        return False

    if isinstance(deps, str):
        deps = [deps]
    completed = set(completed_ids)
    return all(dep in completed for dep in deps)


def _validate_db_path(path: PathLike, name: str) -> None:
    """Raise ValueError if *path* is not a non-empty str/Path."""
    if path is None:
        raise ValueError(f"{name} must not be None")
    if isinstance(path, str) and not path.strip():
        raise ValueError(f"{name} must not be an empty string")
    if not isinstance(path, (str, pathlib.Path)):
        raise ValueError(
            f"{name} must be a str or Path, got {type(path).__name__}"
        )


def check_convergence(
    db_a: PathLike,
    db_b: PathLike,
) -> tuple[bool, set[str]]:
    """Compare two bob databases by completed ``spec_slot`` sets.

    Feature UUIDs change every generation; ``spec_slot`` is stable. Only
    completed features with a non-NULL ``spec_slot`` are compared. Databases
    that predate the ``spec_slot`` migration contribute an empty set (handled
    gracefully by :func:`get_completed_spec_slots`).

    Args:
        db_a: Path to the first generation's SQLite database.
        db_b: Path to the second generation's SQLite database.

    Returns:
        ``(converged, diff)`` where ``converged`` is True iff the symmetric
        difference of the two completed-spec_slot sets is empty, and ``diff``
        is that symmetric difference.

    Raises:
        ValueError: If either path is None, an empty/whitespace string, or not
            a str/Path.
    """
    _validate_db_path(db_a, "db_a")
    _validate_db_path(db_b, "db_b")

    slots_a = get_completed_spec_slots(db_a)
    slots_b = get_completed_spec_slots(db_b)
    diff = slots_a.symmetric_difference(slots_b)
    return (len(diff) == 0, diff)


def _load_name_to_slot(spec_path: pathlib.Path) -> dict[str, str]:
    """Build a {feature name/title -> spec_slot} map from a spec YAML.

    Supports both the list-of-dicts format (``features: [{key, title}, ...]``)
    used by the PEAS extractor and the dict-of-dicts format
    (``features: {F-1: {title}, ...}``) used by the shipped example specs.
    """
    import yaml

    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    raw_features = spec.get("features") if isinstance(spec, dict) else None
    name_to_slot: dict[str, str] = {}

    if isinstance(raw_features, dict):
        for slot_key, feat_val in raw_features.items():
            name = _feature_display_name(feat_val)
            if name:
                name_to_slot[str(name)] = str(slot_key)
    elif isinstance(raw_features, list):
        for feat_val in raw_features:
            if isinstance(feat_val, dict):
                slot = feat_val.get("key") or feat_val.get("id")
                name = _feature_display_name(feat_val)
                if slot and name:
                    name_to_slot[str(name)] = str(slot)

    return name_to_slot


def _feature_display_name(feat_val: object) -> str | None:
    if isinstance(feat_val, dict):
        return feat_val.get("title") or feat_val.get("name")
    if isinstance(feat_val, str):
        return feat_val
    return None


def backfill_spec_slot(
    db_path: PathLike,
    spec_path: PathLike,
) -> int:
    """Populate ``spec_slot`` for feature rows whose value is NULL.

    Existing spec_slot values are never overwritten. Rows whose name matches no
    spec key are left NULL. Idempotent: a second run over an already-backfilled
    database updates nothing and returns 0.

    Args:
        db_path: Path to the SQLite database to update.
        spec_path: Path to the spec YAML file used to resolve names to slots.

    Returns:
        The number of rows whose ``spec_slot`` was populated.

    Raises:
        ValueError: If either path is None, an empty/whitespace string, or not
            a str/Path.
    """
    _validate_db_path(db_path, "db_path")
    _validate_db_path(spec_path, "spec_path")

    name_to_slot = _load_name_to_slot(pathlib.Path(spec_path))
    if not name_to_slot:
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
        if "spec_slot" not in cols:
            conn.execute("ALTER TABLE features ADD COLUMN spec_slot TEXT DEFAULT NULL")

        rows = conn.execute(
            "SELECT id, name FROM features WHERE spec_slot IS NULL"
        ).fetchall()

        updated = 0
        for fid, fname in rows:
            slot = name_to_slot.get(fname)
            if slot is not None:
                conn.execute(
                    "UPDATE features SET spec_slot = ? WHERE id = ?",
                    (slot, fid),
                )
                updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()
