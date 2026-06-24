"""Verifier MUST scope pytest to the current feature's own tests/ subtree.

Cumulative prior-feature test failures cause pytest-xdist stop-after-20 to
fail every subsequent feature's verification. This module provides the
canonical entry point that the verifier's tests_pass step MUST call — it
scopes pytest to ONLY the current feature's own test paths.

Root cause (F-R7-fbd68fee): when the full ``tests/`` tree is run, pytest-xdist
``--maxfail=20`` trips on accumulated failures from prior features before the
current feature's own tests execute, burning retry budget and producing false
negatives.

Public API
----------
verifier_must_scope_pytest_current_feature_s_own_tests(feature_id, acs, workspace)
    Primary entry point. Returns the sorted list of test paths scoped to the
    current feature. Wraps :func:`scope_pytest_to_feature` from
    :mod:`bob.verification.per_feature_test_scope`.
"""

from __future__ import annotations

from pathlib import Path

from bob.verification.per_feature_test_scope import (
    SiblingTestCollectionError,  # noqa: F401 — re-exported for callers
    scope_pytest_to_feature,
)

__all__ = [
    "SiblingTestCollectionError",
    "verifier_must_scope_pytest_current_feature_s_own_tests",
]


def verifier_must_scope_pytest_current_feature_s_own_tests(
    feature_id: str,
    acs: list[str],
    workspace: str | Path,
) -> list[str]:
    """Return test paths scoped to *feature_id*'s own tests, never the full suite.

    The verifier's tests_pass step MUST call this function instead of running
    ``pytest tests/``. Running the full tree causes pytest-xdist --maxfail=20
    to trip on accumulated failures from prior features before the current
    feature's own tests ever execute.

    Sources for scoped paths:
    1. Every ``pytest:`` AC entry (path portion, stripped of ``::`` node-ids).
    2. ``tests/<feature_id>/`` when that directory exists under *workspace*.

    Args:
        feature_id: The feature's UUID string.
        acs:        The feature's acceptance criteria list.
        workspace:  Repository root (directory containing ``tests/``).

    Returns:
        Sorted list of test paths for this feature. Returns an empty list
        when neither source yields paths — caller should skip pytest rather
        than falling back to the full suite.

    Raises:
        SiblingTestCollectionError: If any resolved path would pull in tests
            from another feature's subtree (defensive guard).
    """
    return scope_pytest_to_feature(feature_id, acs, workspace)
