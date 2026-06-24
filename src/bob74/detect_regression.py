"""Regression detection with mandatory test-ownership verification for bob74.

Feature 82e33b94-8471-498d-9534-d020fbaaa288

Enforces that demotion to ``regression`` requires evidence that the demoted
feature's own tests newly fail.  Features absent from the test-ownership map
cannot be blamed (no scapegoating).

Public API
----------
``requires_test_ownership_verification(newly_failing_tests, test_ownership_map)``
    Verify that test-ownership evidence exists before any demotion decision.
    Returns a ``VerificationResult`` describing which features have sufficient
    evidence to be demoted and which tests are unattributed.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "requires_test_ownership_verification",
    "VerificationResult",
    "UNATTRIBUTED_KEY",
]

UNATTRIBUTED_KEY = "unattributed"

VerificationResult = dict[str, Any]


def requires_test_ownership_verification(
    newly_failing_tests: list[str],
    test_ownership_map: dict[str, str],
) -> VerificationResult:
    """Verify that demotion evidence exists before attributing regressions.

    For each test in *newly_failing_tests*, the test must appear in
    *test_ownership_map* to attribute the failure to a feature.  Tests with
    no owner entry are placed under the ``"unattributed"`` sentinel and no
    feature is blamed for them.

    A feature is marked with ``"demote": True`` ONLY when at least one of its
    declared tests appears in *newly_failing_tests*.  Features that are merely
    completed or nearby are never scapegoated.

    This function is the enforcement gate for ``bob.db.detect_regression``:
    callers must invoke this before demoting any feature to ``regression`` status
    to ensure the evidence requirement is met.

    Args:
        newly_failing_tests: Pytest node-ids that newly fail vs the baseline.
        test_ownership_map: ``{test_nodeid: feature_id}`` built from each
            feature's ``pytest:`` acceptance criteria.  Features absent from
            this map own no declared tests and cannot be blamed.

    Returns:
        A ``VerificationResult`` dict.  Keys are feature_ids and the
        ``"unattributed"`` sentinel.  Values::

            {
                "tests": [<test_nodeid>, ...],   # sorted list
                "demote": bool,                  # True iff evidence exists
            }

        Only features with at least one newly-failing owned test are present.
        The ``"unattributed"`` key is present only when unowned tests exist.

    Raises:
        TypeError: When *newly_failing_tests* is None or not a list, or when
            *test_ownership_map* is None or not a dict.
        ValueError: When *newly_failing_tests* contains non-string entries.
    """
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

    for item in newly_failing_tests:
        if not isinstance(item, str):
            raise ValueError(
                f"Every entry in newly_failing_tests must be a string, got {type(item)!r}"
            )

    if not newly_failing_tests:
        return {}

    result: VerificationResult = {}

    for test in newly_failing_tests:
        owner = test_ownership_map.get(test)
        if owner is None:
            bucket = result.setdefault(UNATTRIBUTED_KEY, {"tests": [], "demote": False})
            bucket["tests"].append(test)
        else:
            bucket = result.setdefault(owner, {"tests": [], "demote": True})
            bucket["tests"].append(test)

    for bucket in result.values():
        bucket["tests"].sort()

    return result
