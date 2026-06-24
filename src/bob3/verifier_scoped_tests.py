"""bob3.verifier_scoped_tests — scoped pytest path resolver for per-feature verification.

The verifier's tests_pass step MUST scope its pytest invocation to ONLY the
current feature's own test paths. Running the full ``tests/`` tree causes
pytest-xdist's ``--maxfail=20`` to trip on accumulated failures from prior
features before the current feature's own tests execute, producing false
negatives that burn retry budget.

Root cause (F-R7-fbd68fee): prior-feature broken test stubs accumulate; the
20th cumulative failure stops pytest before the current feature's tests run.

Public API
----------
scope_pytest_to_feature(feature_id, acs, workspace) -> list[str]
    Return the sorted list of test paths scoped to *feature_id*'s own tests.
    Sources: ``pytest:`` AC entries and ``tests/<feature_id>/`` subtree.
    Returns an empty list when no paths found — caller should skip pytest
    rather than falling back to the full suite.

SiblingTestCollectionError
    Re-exported for callers that catch the guard error.
"""

from __future__ import annotations

from pathlib import Path

from bob3.verification.per_feature_test_scope import (
    SiblingTestCollectionError,  # noqa: F401 — re-exported for callers
    scope_pytest_to_feature as _scope_pytest_to_feature,
)

__all__ = [
    "SiblingTestCollectionError",
    "scope_pytest_to_feature",
]


def scope_pytest_to_feature(
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
    return _scope_pytest_to_feature(feature_id, acs, workspace)
