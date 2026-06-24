"""Regression-vs-baseline failure attributor for bob3 verification.

Feature 69972c5e-bf50-4e8a-a1f9-8740e2e487ff

Problem solved
--------------
The regression-vs-baseline check ran whole-suite and attributed all
newly-failing tests to whichever feature was currently being verified.
When sibling-feature test stubs regressed, the current feature was
incorrectly gate-blocked (the 9b2e1060 scenario: 7 sibling tests blocked
an unrelated feature at attempt=5).

Fix
---
Provides two canonical entry points:

1. ``build_test_path_to_feature_map`` — builds a ``{test_path: feature_id}``
   ownership map from ``tests/<feature_id>/`` directory convention AND
   ``pytest:`` AC declarations.

2. ``attribute_failure_to_owning_feature`` — resolves the owning feature for
   a single failing test path.  Returns the owning feature_id or None for
   orphan tests.  Only tests owned by the *current* feature should count
   toward the gate decision; all others must be re-attributed to their
   true owner.

Integration with bob3.verification
------------------------------------
The regression-vs-baseline step in the verifier calls
``attribute_failure_to_owning_feature`` for each newly-failing test and
counts only those owned by the current feature toward the gate decision.
Sibling-owned and orphan tests are logged or re-opened but do NOT block
the current feature's verification.

Public API
----------
``build_test_path_to_feature_map(features)``
    Returns ``{test_path: feature_id}`` ownership map (first-writer wins).

``attribute_failure_to_owning_feature(test_path, *, all_features=None, workspace_root=None)``
    Returns the owning feature_id or None for a single test path.
"""

from __future__ import annotations

from typing import Any

from tests_pass.feature_test_map import (
    attribute_failures_to_owning_feature as _multi_attribute,
    build_feature_test_map as _build_feature_test_map,
    _owning_feature_for_test,
)

__all__ = [
    "attribute_failure_to_owning_feature",
    "build_test_path_to_feature_map",
]


def build_test_path_to_feature_map(features: list[Any]) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map from a list of features.

    Ownership is determined from ``pytest:`` prefixed acceptance criteria.
    First-writer wins for duplicate claims.

    Args:
        features: Sequence of feature dicts or objects, each with ``id`` and
            ``acceptance_criteria`` attributes/keys.

    Returns:
        ``{test_path: feature_id}`` ownership map.

    Raises:
        TypeError: When *features* is None.
        ValueError: When a feature has a missing or empty id.
    """
    return _build_feature_test_map(features)


def attribute_failure_to_owning_feature(
    test_path: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
) -> str | None:
    """Return the feature_id that owns *test_path*, or None if unknown.

    Ownership is resolved via two strategies (in order):
    1. **Directory convention**: ``tests/<feature_id>/`` paths are owned by
       the feature whose UUID appears in the subtree.
    2. **pytest-prefix ACs**: features that declare ``pytest: <path>`` own
       those test paths.

    The regression-vs-baseline verification gate MUST call this for each
    newly-failing test.  Only tests for which this returns the
    *current_feature_id* should count toward the gate decision — tests
    owned by a sibling feature or returning None (orphan) must not block
    the current feature.

    Args:
        test_path: Pytest node-id or file path to look up.
        all_features: Optional list of feature dicts/objects for the
            pytest-prefix AC ownership strategy.  Pass None to rely on
            directory convention only.
        workspace_root: Workspace root path (currently unused; kept for
            API symmetry with other attribution helpers).

    Returns:
        The owning feature_id string, or None when the test is an orphan
        (no UUID directory and no feature claims it via pytest: AC).

    Raises:
        ValueError: When *test_path* is not a non-empty string.
    """
    if not isinstance(test_path, str) or not test_path.strip():
        raise ValueError(
            f"test_path must be a non-empty string, got {test_path!r}"
        )
    return _owning_feature_for_test(test_path, all_features=all_features)
