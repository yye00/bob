"""Blame-the-cause regression cascade — charge only the breaking feature.

Feature 2f2050c0-5478-420a-8b2d-522be8cb9bcf

For each failing test, walks the AC table to find the feature whose
``pytest:`` AC owns that test path. Charges a refinement attempt only to
that owning feature. Features that merely ran during the same verification
but own no failing test stay at their pre-verification status.

Public API
----------
- ``charge_failing_features`` — top-level entry point. For each failing test,
  finds the feature whose pytest: AC owns it and increments its
  refinement_attempts via the caller-supplied increment_fn.
- ``find_owner_feature`` — returns the feature_id whose pytest AC matches a
  failing test path, or None if unowned.
- ``preserve_innocent_status`` — returns statuses for uncharged features.
- ``handle_unowned_failure`` — records an unattributed_failure event.
- ``OrphanTestError`` — raised when strict=True and no owner is found.

Integration
-----------
``bob3.orchestrator`` re-exports ``charge_failing_features`` as its
integration AC.  To avoid a circular import (bob3.blame_cascade →
bob3.orchestrator.blame_cascade → bob3.orchestrator.__init__ →
bob3.blame_cascade), this module implements the logic directly rather than
delegating to the orchestrator sub-module.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

_PYTEST_PREFIX = "pytest:"

__all__ = [
    "charge_broken_tests",
    "charge_breaking_feature",
    "charge_failing_features",
    "charge_failing_test_to_feature",
    "charge_to_owning_feature",
    "find_owner_feature",
    "find_owning_feature",
    "preserve_innocent_status",
    "handle_unowned_failure",
    "OrphanTestError",
]


class OrphanTestError(Exception):
    """Raised when a failing test has no owning feature and strict mode is on."""


def _parse_ac_list(acceptance_criteria: Any) -> list[str]:
    if acceptance_criteria is None:
        return []
    if isinstance(acceptance_criteria, list):
        return [str(c) for c in acceptance_criteria]
    if isinstance(acceptance_criteria, str):
        raw = acceptance_criteria.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(c) for c in parsed]
            return [str(parsed)]
        except (json.JSONDecodeError, ValueError):
            pass
        return [raw]
    return [str(acceptance_criteria)]


def _extract_pytest_paths(ac_list: list[str]) -> list[str]:
    paths: list[str] = []
    for criterion in ac_list:
        stripped = criterion.strip()
        lower = stripped.lower()
        if lower.startswith(_PYTEST_PREFIX):
            path_section = stripped[len(_PYTEST_PREFIX):].strip()
            path = path_section.split()[0] if path_section else ""
            if path:
                paths.append(path)
    return paths


def _test_matches_pytest_path(test_nodeid: str, pytest_path: str) -> bool:
    if "::" not in pytest_path:
        return test_nodeid.startswith(pytest_path + "::")
    return test_nodeid == pytest_path


def find_owner_feature(
    *,
    failing_test: str,
    all_features: list[Any],
    strict: bool = False,
) -> str | None:
    """Return the feature_id whose pytest AC owns *failing_test*.

    Args:
        failing_test: A pytest node-id, e.g. ``"tests/test_foo.py::test_bar"``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        strict: When True, raises ``OrphanTestError`` if no owner is found.

    Returns:
        The owning feature_id string, or ``None`` if not found (and not strict).

    Raises:
        ValueError: If ``failing_test`` is not a non-empty string.
        OrphanTestError: If ``strict=True`` and no owner is found.
    """
    if not isinstance(failing_test, str) or not failing_test.strip():
        raise ValueError(
            f"failing_test must be a non-empty string; got {failing_test!r}"
        )

    for feature in all_features:
        if isinstance(feature, dict):
            fid = feature.get("id", "")
            ac_raw = feature.get("acceptance_criteria")
        else:
            fid = getattr(feature, "id", "")
            ac_raw = getattr(feature, "acceptance_criteria", None)

        if not fid:
            continue

        ac_list = _parse_ac_list(ac_raw)
        for path in _extract_pytest_paths(ac_list):
            if _test_matches_pytest_path(failing_test, path):
                logger.debug("Failing test %r attributed to feature %s", failing_test, fid)
                return fid

    logger.debug("Failing test %r has no owning feature in the AC table", failing_test)
    if strict:
        raise OrphanTestError(
            f"No feature owns failing test {failing_test!r}; "
            "add a 'pytest: <path>' AC to the appropriate feature."
        )
    return None


find_owning_feature = find_owner_feature


def handle_unowned_failure(
    *,
    failing_test: str,
    record_fn: Callable[[Any], Any],
) -> None:
    """Record an unattributed_failure event for a test with no owning feature.

    Args:
        failing_test: The pytest node-id that could not be attributed.
        record_fn: Callback that receives the event dict.
    """
    event = {
        "type": "unattributed_failure",
        "failing_test": failing_test,
    }
    logger.warning(
        "Unattributed failure: no feature owns test %r; recording orphan event",
        failing_test,
    )
    record_fn(event)


def preserve_innocent_status(
    *,
    all_features: list[Any],
    charged_feature_ids: set[str],
) -> dict[str, str]:
    """Return a mapping of feature_id → status for all non-charged features.

    Args:
        all_features: All features that participated in the verification run.
        charged_feature_ids: Set of feature_ids that were charged.

    Returns:
        Dict mapping feature_id to status for every feature NOT in
        *charged_feature_ids*.
    """
    preserved: dict[str, str] = {}
    for feature in all_features:
        if isinstance(feature, dict):
            fid = feature.get("id", "")
            status = feature.get("status", "unknown")
        else:
            fid = getattr(feature, "id", "")
            status = getattr(feature, "status", "unknown")

        if fid and fid not in charged_feature_ids:
            preserved[fid] = str(status)

    return preserved


def charge_failing_features(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the feature that owns each failing test.

    For each failing test, the AC table is searched for the feature with a
    matching ``pytest: <path>`` acceptance criterion. Each unique owning feature
    is charged exactly once, regardless of how many of its tests are failing.
    Features that ran during the same verification but own no failing test are
    not charged — their pre-verification status is preserved.

    Args:
        failing_tests: Pytest node-ids that are currently failing, e.g.
            ``["tests/test_foo.py::test_bar", "tests/test_baz.py::test_x"]``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Callable invoked once per unique owning ``feature_id``.
            Typically a DB call like ``db.increment_refinement_attempts``.
        unowned_record_fn: Optional callback for tests that have no owning
            feature. Each call receives an event dict
            ``{"type": "unattributed_failure", "failing_test": <path>}``.

    Returns:
        The count of unique features charged (0 when no failing test has an
        owner, or when *failing_tests* is empty).
    """
    if not isinstance(failing_tests, list):
        raise ValueError(
            f"failing_tests must be a list; got {type(failing_tests).__name__!r}"
        )

    if not failing_tests:
        return 0

    owners: set[str] = set()

    for test_nodeid in failing_tests:
        owner = find_owner_feature(
            failing_test=test_nodeid,
            all_features=all_features,
            strict=False,
        )
        if owner is not None:
            owners.add(owner)
        else:
            if unowned_record_fn is not None:
                handle_unowned_failure(
                    failing_test=test_nodeid,
                    record_fn=unowned_record_fn,
                )

    for feature_id in owners:
        logger.info(
            "Charging refinement attempt to feature %s (blame cascade attribution)",
            feature_id,
        )
        increment_fn(feature_id)

    return len(owners)


def charge_failing_test_to_feature(
    *,
    failing_test: str,
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> str | None:
    """Find the feature that owns a single failing test and charge it.

    Walks the AC table looking for a ``pytest: <path>`` criterion that matches
    *failing_test*. If an owner is found, ``increment_fn`` is called with the
    owner's feature_id and that id is returned. If no owner is found,
    ``unowned_record_fn`` is called (if provided) and ``None`` is returned.

    Args:
        failing_test: A pytest node-id such as ``"tests/test_foo.py::test_bar"``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Called once with the owning feature_id when an owner is found.
        unowned_record_fn: Optional callback invoked when no owner is found.

    Returns:
        The charged feature_id, or ``None`` if the test has no owning feature.

    Raises:
        ValueError: If ``failing_test`` is not a non-empty string.
    """
    if not isinstance(failing_test, str) or not failing_test.strip():
        raise ValueError(
            f"failing_test must be a non-empty string; got {failing_test!r}"
        )

    owner = find_owner_feature(
        failing_test=failing_test,
        all_features=all_features,
        strict=False,
    )

    if owner is not None:
        logger.info(
            "Charging refinement attempt to feature %s for failing test %r",
            owner,
            failing_test,
        )
        increment_fn(owner)
        return owner

    if unowned_record_fn is not None:
        handle_unowned_failure(
            failing_test=failing_test,
            record_fn=unowned_record_fn,
        )
    return None


def charge_broken_tests(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the feature that owns each failing test.

    For each failing test, the AC table is searched for the feature with a
    matching ``pytest: <path>`` acceptance criterion. Each unique owning feature
    is charged exactly once. Features that ran during the same verification but
    own no failing test are not charged — their pre-verification status is
    preserved.

    This is the primary entry point for the blame-the-cause regression cascade:
    when a verification run reports failures, call this function with the list
    of failing test node-ids instead of unconditionally charging every feature
    that participated in the run.

    Args:
        failing_tests: Pytest node-ids that are currently failing, e.g.
            ``["tests/test_foo.py::test_bar", "tests/test_baz.py::test_x"]``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Callable invoked once per unique owning ``feature_id``.
            Typically a DB call like ``db.increment_refinement_attempts``.
        unowned_record_fn: Optional callback for tests that have no owning
            feature. Each call receives an event dict
            ``{"type": "unattributed_failure", "failing_test": <path>}``.

    Returns:
        The count of unique features charged (0 when no failing test has an
        owner, or when *failing_tests* is empty).

    Raises:
        ValueError: If ``failing_tests`` is not a list.
    """
    return charge_failing_features(
        failing_tests=failing_tests,
        all_features=all_features,
        increment_fn=increment_fn,
        unowned_record_fn=unowned_record_fn,
    )


def charge_breaking_feature(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the feature that owns each failing test.

    Feature ba53e982-803e-4fdc-8e11-4aea2583201f

    For each failing test, walks the AC table to find the owning feature
    (the one with a matching ``pytest:`` AC). Each unique owner is charged
    exactly once via *increment_fn*. Features that ran during the same
    verification but own no failing test are not charged — their
    pre-verification status is preserved.

    Args:
        failing_tests: Pytest node-ids that are currently failing, e.g.
            ``["tests/test_foo.py::test_bar", "tests/test_baz.py::test_x"]``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Callable invoked once per unique owning ``feature_id``.
        unowned_record_fn: Optional callback for tests that have no owning
            feature.

    Returns:
        The count of unique features charged.

    Raises:
        ValueError: If ``failing_tests`` is not a list.
    """
    return charge_failing_features(
        failing_tests=failing_tests,
        all_features=all_features,
        increment_fn=increment_fn,
        unowned_record_fn=unowned_record_fn,
    )


def charge_to_owning_feature(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the feature that owns each failing test.

    Feature 65236321-1f28-4ddc-804e-505f882a7ce9

    For each failing test, walks the AC table to find the feature whose
    ``pytest:`` AC owns that test path. Each unique owning feature is charged
    exactly once via *increment_fn*. Features that merely ran during the same
    verification but own no failing test stay at their pre-verification status.

    Args:
        failing_tests: Pytest node-ids that are currently failing, e.g.
            ``["tests/test_foo.py::test_bar", "tests/test_baz.py::test_x"]``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Callable invoked once per unique owning ``feature_id``.
        unowned_record_fn: Optional callback for tests that have no owning
            feature.

    Returns:
        The count of unique features charged.

    Raises:
        ValueError: If ``failing_tests`` is not a list.
    """
    return charge_failing_features(
        failing_tests=failing_tests,
        all_features=all_features,
        increment_fn=increment_fn,
        unowned_record_fn=unowned_record_fn,
    )
