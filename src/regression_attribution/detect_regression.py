"""Regression detection requiring test-ownership evidence.

Feature a438fa7c-59ae-46c5-8ce8-1a91a064897d

``require_test_ownership_evidence`` enforces the contract that a feature may
ONLY be demoted to 'regression' when at least one of its own declared tests
newly fails.  Features that have no declared ownership of the failing tests
are never charged — this prevents scapegoating innocent features.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = ["require_test_ownership_evidence"]


def require_test_ownership_evidence(
    *,
    feature_id: str,
    newly_failing_tests: list[str],
    test_ownership_map: dict[str, str],
) -> dict:
    """Verify that test-ownership evidence exists before allowing regression demotion.

    A feature may be demoted to 'regression' ONLY when the ``test_ownership_map``
    maps at least one of the ``newly_failing_tests`` to that feature's id.
    If no owned tests appear among the newly failing ones, demotion is refused.

    Args:
        feature_id: The feature proposed for regression demotion.
        newly_failing_tests: List of pytest node-ids that newly fail.
        test_ownership_map: ``{test_nodeid_or_file: feature_id}`` ownership map.
            A test matches when its node-id starts with an ownership-map key
            (file-level ownership) or equals the key exactly.

    Returns:
        A dict with keys:
        - ``"may_demote"``: bool — True only when owned failing tests exist.
        - ``"owned_failing_tests"``: list[str] — the subset of newly_failing_tests
          owned by this feature.
        - ``"evidence"``: list[str] — human-readable evidence strings.

    Raises:
        ValueError: When ``feature_id`` is empty.
        TypeError: When any argument is None or of wrong type.
    """
    if feature_id is None:
        raise TypeError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a string, got {type(feature_id)!r}")
    if not feature_id:
        raise ValueError("feature_id must not be an empty string")

    if newly_failing_tests is None:
        raise TypeError("newly_failing_tests must not be None")
    if not isinstance(newly_failing_tests, list):
        raise TypeError(
            f"newly_failing_tests must be a list, got {type(newly_failing_tests)!r}"
        )

    if test_ownership_map is None:
        raise TypeError("test_ownership_map must not be None")
    if not isinstance(test_ownership_map, dict):
        raise TypeError(
            f"test_ownership_map must be a dict, got {type(test_ownership_map)!r}"
        )

    owned_failing: list[str] = []
    for test in newly_failing_tests:
        owner = _lookup_owner(test, test_ownership_map)
        if owner == feature_id:
            owned_failing.append(test)

    may_demote = len(owned_failing) > 0
    evidence: list[str] = [
        f"test {t!r} is owned by feature {feature_id!r} and newly fails"
        for t in owned_failing
    ]

    if not may_demote:
        logger.info(
            "Refusing regression demotion of %s: none of its tests appear "
            "in newly_failing_tests (no ownership evidence)",
            feature_id,
        )

    return {
        "may_demote": may_demote,
        "owned_failing_tests": owned_failing,
        "evidence": evidence,
    }


def _lookup_owner(test_nodeid: str, ownership_map: dict[str, str]) -> str | None:
    """Return the owning feature_id for *test_nodeid*, or None.

    Supports two claim styles:
    - Exact node-id: ``"tests/test_foo.py::test_bar"``
    - File-level: ``"tests/test_foo.py"`` matches any ``tests/test_foo.py::*``
    """
    # Try exact match first
    owner = ownership_map.get(test_nodeid)
    if owner is not None:
        return owner
    # Try file-level prefix match
    for key, fid in ownership_map.items():
        if "::" not in key and test_nodeid.startswith(key + "::"):
            return fid
    return None
