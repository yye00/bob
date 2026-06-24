"""Blame-the-cause regression cascade — charge the breaking feature only.

Feature 9dc2e845-734f-4052-9319-b949e104ac84

Problem solved
--------------
When feature B's ``tests_pass`` check fails because feature A's tests are
broken, both A and B historically got a refinement charge. This module
introduces precise attribution:

For each failing test, walk the AC table to find the feature whose
``pytest:`` AC owns that test path.  Charge refinement_attempts only to
that owning feature.  Features that merely ran during the same verification
but own no failing test remain at their pre-verification status.

Public API
----------
- ``find_owner_feature`` — returns the feature_id whose pytest AC matches
  a single failing test path, or None if unowned.  Raises ``OrphanTestError``
  when ``strict=True`` and no owner is found.
- ``charge_refinement`` — increments refinement_attempts on the owning
  feature only; returns the count of unique features charged.
- ``preserve_innocent_status`` — returns a dict of {feature_id: status}
  for all features NOT in the charged set.
- ``handle_unowned_failure`` — records an unattributed_failure event via
  a caller-supplied callback.

Integration
-----------
``bob.orchestrator.run_loop`` calls these helpers after
``run_verification_checklist`` reports failures, replacing the current
unconditional ``increment_refinement_attempts(feature.id)`` with targeted
charges.

Helpers are stateless (no DB access) and testable without a live database.
All DB side-effects go through the caller-supplied ``increment_fn``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

_PYTEST_PREFIX = "pytest:"


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
            # Take only the path portion (before any whitespace-separated description)
            path_section = stripped[len(_PYTEST_PREFIX):].strip()
            # The path is the first whitespace-delimited token
            path = path_section.split()[0] if path_section else ""
            if path:
                paths.append(path)
    return paths


def _test_matches_pytest_path(test_nodeid: str, pytest_path: str) -> bool:
    if "::" not in pytest_path:
        # File-level claim: match any test in the file
        return test_nodeid.startswith(pytest_path + "::")
    # Exact node-id claim
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
        OrphanTestError: If ``strict=True`` and no owner is found.
    """
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


def charge_refinement(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the owning feature for each failing test.

    Each unique owning feature is charged exactly once, regardless of how many
    of its tests are failing.

    Args:
        failing_tests: List of pytest node-ids that are currently failing.
        all_features: Sequence of feature dicts or objects.
        increment_fn: Called once per unique owning feature_id.
        unowned_record_fn: Optional callback invoked for each test that has
            no owning feature (triggers ``handle_unowned_failure`` internally).

    Returns:
        The count of unique features charged.
    """
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


def preserve_innocent_status(
    *,
    all_features: list[Any],
    charged_feature_ids: set[str],
) -> dict[str, str]:
    """Return a mapping of feature_id → status for all non-charged features.

    These features were not responsible for any failing test and should keep
    their pre-verification status unchanged.

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


def charge_feature_from_test(
    *,
    failing_test: str,
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> str | None:
    """Find the feature that owns *failing_test* and charge it.

    Feature 3310e08a-0932-4664-a7b2-b93bb01d88e5

    Walks the AC table for each feature looking for a ``pytest: <path>`` AC
    that matches *failing_test*.  If an owner is found, ``increment_fn`` is
    called with the owner's feature_id and that id is returned.  If no owner
    is found, ``unowned_record_fn`` is called (if provided) and ``None`` is
    returned.

    Args:
        failing_test: A pytest node-id such as
            ``"tests/test_foo.py::test_bar"``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Called once with the owning feature_id when an owner is
            found.
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
        increment_fn(owner)
        return owner

    if unowned_record_fn is not None:
        handle_unowned_failure(
            failing_test=failing_test,
            record_fn=unowned_record_fn,
        )
    return None
