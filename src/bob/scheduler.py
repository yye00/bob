"""Scheduler runnable/claim computation — keyed on feature id, never spec_slot.

Feature 24c307e5-e761-43e0-b44d-85dd268ab520.

Regression this guards against
------------------------------
``extract-from-peas`` once emitted three feature rows sharing spec_slot
``F-R7-003``, and both the supervisor and ``bob run`` computed
runnable/claim eligibility keyed on ``spec_slot``. A completed sibling made
the runnable-count for the still-pending audit feature read 0, so the build
STOPPED (QUEUE_DRAINED) with real work left.

The fix: runnable/claim/complete logic MUST key on the feature's unique
``id``. ``spec_slot`` is a cross-generation matching label only (per
F-R7-400) and is explicitly NOT used to decide whether a distinct feature is
runnable. A completed feature therefore never suppresses a distinct pending
feature that happens to share its spec_slot.
"""

from __future__ import annotations

from typing import Any

# Statuses that make a feature eligible to be dispatched.
_RUNNABLE_STATUSES = frozenset({"ready", "pending"})
# Only a completed dependency unblocks its dependents.
_COMPLETED_STATUS = "completed"


def _get(feature: Any, name: str, default: Any = None) -> Any:
    """Read *name* from a mapping or object feature representation."""
    if isinstance(feature, dict):
        return feature.get(name, default)
    return getattr(feature, name, default)


def _feature_id(feature: Any) -> str:
    """Return the feature's unique id, raising ValueError if absent.

    The id is the ONLY key used for runnable/claim/complete decisions.
    """
    fid = _get(feature, "id")
    if fid is None or fid == "":
        raise ValueError(f"feature has no unique id: {feature!r}")
    return str(fid)


def _depends_on(feature: Any) -> list[str]:
    deps = _get(feature, "depends_on") or []
    if isinstance(deps, str):
        return [deps]
    return list(deps)


def compute_runnable(features: Any) -> list[Any]:
    """Return the subset of *features* that are runnable right now.

    A feature is runnable when ALL of:
      - its ``status`` is 'ready' or 'pending', AND
      - every id in its ``depends_on`` list refers to a feature whose
        ``status`` is 'completed'.

    Eligibility is keyed strictly on the feature's unique ``id``. ``spec_slot``
    is never consulted, so a completed feature can never suppress a distinct
    pending feature that shares its spec_slot.

    Args:
        features: A list of feature mappings or objects. Each must expose an
            ``id``; ``status`` and optional ``depends_on`` are read too.

    Returns:
        The runnable features, preserving input order. Empty list for empty
        input.

    Raises:
        ValueError: if *features* is not a list, or any feature lacks an id.
    """
    if not isinstance(features, list):
        raise ValueError(f"features must be a list, got {type(features).__name__}")

    # Index completion state by unique id (never by spec_slot).
    completed_ids: set[str] = set()
    for feature in features:
        fid = _feature_id(feature)
        if _get(feature, "status") == _COMPLETED_STATUS:
            completed_ids.add(fid)

    runnable: list[Any] = []
    for feature in features:
        status = _get(feature, "status")
        if status not in _RUNNABLE_STATUSES:
            continue
        deps = _depends_on(feature)
        if all(dep in completed_ids for dep in deps):
            runnable.append(feature)
    return runnable
