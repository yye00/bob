"""bob.verifier_test_scoping — AC-named entry point for per-feature pytest scoping.

The verifier's ``tests_pass`` step MUST scope its pytest invocation to ONLY the
current feature's own test paths. Running the full ``tests/`` tree causes
pytest-xdist's ``--maxfail=20`` to trip on accumulated failures from prior
features before the current feature's own tests execute, producing false
negatives that burn retry budget (root cause: F-R7-fbd68fee).

This module is the AC-declared surface (``bob.verifier_test_scoping``). It
re-exports the canonical implementation from
:mod:`bob.verification.per_feature_test_scope` so callers, the boundary/error
test suites, and :mod:`bob.verifier` all resolve to a single source of truth.
"""

from __future__ import annotations

from pathlib import Path

from bob.verification.per_feature_test_scope import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature as _scope_pytest_to_feature,
)

__all__ = [
    "SiblingTestCollectionError",
    "assert_no_sibling_collection",
    "build_scoped_pytest_argv",
    "collect_feature_test_paths",
    "scope_pytest_to_feature",
]


def scope_pytest_to_feature(
    feature_id: str,
    acs: list[str],
    workspace: str | Path,
) -> list[str]:
    """Return the sorted test paths scoped to *feature_id*'s own tests.

    Primary entry point for the verifier's ``tests_pass`` step. Ensures pytest
    is NEVER run against the whole ``tests/`` tree or any sibling feature
    subtree — only the paths that belong to *feature_id*:

    1. Every ``pytest:`` AC entry (path portion, stripped of ``::`` node-ids).
    2. ``tests/<feature_id>/`` when that directory exists under *workspace*.

    Args:
        feature_id: The feature's UUID string.
        acs:        The feature's acceptance criteria list.
        workspace:  Repository root (directory containing ``tests/``).

    Returns:
        Sorted list of test paths for this feature. Empty list when neither
        source yields paths — the caller should skip pytest rather than
        falling back to the full suite.

    Raises:
        SiblingTestCollectionError: If a resolved path would pull in another
            feature's subtree (defensive guard).
    """
    return _scope_pytest_to_feature(feature_id, acs, workspace)
