"""Feature-scoped pytest path resolver for the verifier's tests_pass step.

This module ensures the verifier's pytest invocations are scoped to ONLY the
current feature's own test paths.  Running the entire tests/ tree causes
pytest-xdist's --maxfail to trip on accumulated failures from prior features
before the current feature's tests ever execute, burning retry budget and
producing false negatives.

The public API is intentionally minimal:

    scope_pytest_to_feature(feature_id, acs, workspace) -> list[str]
        Primary entry point.  Returns only paths owned by *feature_id*.

    collect_feature_test_paths(feature_id, acs, workspace) -> set[str]
        Lower-level collector.

    build_scoped_pytest_argv(feature_id, acs, workspace) -> list[str]
        Builds a ready-to-use pytest argv (without ``python -m pytest``).

    assert_no_sibling_collection(feature_id, argv, workspace) -> None
        Defensive guard; raises SiblingTestCollectionError on violation.

    SiblingTestCollectionError
        Exception type for sibling-test-collection guard failures.
"""

from __future__ import annotations

from bob3.verification.per_feature_test_scope import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)

# Alias: the AC declares "Function defined: bob3.verifier.scope_pytest_to_feature_subtree".
# This name emphasises that the function scopes to the feature's OWN subtree only.
scope_pytest_to_feature_subtree = scope_pytest_to_feature

__all__ = [
    "SiblingTestCollectionError",
    "assert_no_sibling_collection",
    "build_scoped_pytest_argv",
    "collect_feature_test_paths",
    "scope_pytest_to_feature",
    "scope_pytest_to_feature_subtree",
]
