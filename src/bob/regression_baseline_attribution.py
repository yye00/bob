"""Regression-vs-baseline attribution — blame the OWNING feature, not the current one.

Feature 2644949e-18aa-40d7-bbec-745beb3963e7

Problem
-------
The regression-vs-baseline check runs whole-suite and, on finding a
previously-passing test that now fails, attributes the failure to whichever
feature happens to be under verification.  When a *sibling* feature's test
stubs regress (e.g. the 9b2e1060 scenario: 7 tests from prior features such
as 73879589, itself NH-demoted with uncleaned stubs), the gate mis-blames the
current, unrelated feature and demotes it.

Fix
---
Regression attribution MUST consult a ``{test_path: feature_id}`` ownership
map derived from the ``tests/<feature_id>/`` subtree convention AND from the
``pytest:`` acceptance criteria of features.  A previously-passing test that
now fails is attributed to its OWN owning feature — never counted against the
currently-verifying feature.  Orphan tests (no known owner) are logged rather
than blamed on the current feature.

Public API
----------
``build_test_path_to_feature_map(features)``
    Build a ``{test_path: feature_id}`` ownership map from a list of features.

``attribute_regression_to_owning_feature(test_path, current_feature_id, ...)``
    Resolve the true owner of a single failing test path.  Returns the owning
    feature_id (which may equal *current_feature_id*), or None for orphans.

Both delegate to the canonical implementations in ``bob.test_attribution`` so
the attribution logic lives in one place.
"""

from __future__ import annotations

from typing import Any

from bob.test_attribution import (
    attribute_regression_to_owning_feature as _attribute_regression_to_owning_feature,
)
from bob.regression_vs_baseline_attributor import (
    build_test_path_to_feature_map as _build_test_path_to_feature_map,
)

__all__ = [
    "attribute_regression_to_owning_feature",
    "build_test_path_to_feature_map",
]


def build_test_path_to_feature_map(features: list[Any]) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map from a list of features.

    Ownership is derived from ``pytest:`` prefixed acceptance criteria.
    File-level claims (no ``::`` node separator) cover any test inside that
    file.  First-writer wins for duplicate claims.

    Args:
        features: Sequence of feature dicts or objects, each exposing ``id``
            and ``acceptance_criteria`` (via attribute or dict key).

    Returns:
        ``{test_path: feature_id}`` ownership map.

    Raises:
        TypeError: When *features* is None.
        ValueError: When a feature has a missing or empty id.
    """
    return _build_test_path_to_feature_map(features)


def attribute_regression_to_owning_feature(
    test_path: str,
    current_feature_id: str,
    *,
    previously_passed_at: str | None = None,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> str | None:
    """Attribute a newly-failing test to its owning feature, not the current one.

    Given a failing test path and the feature currently under verification,
    determine the true owner:

    - If the test belongs to *current_feature_id*, return *current_feature_id*
      so the gate legitimately counts the failure.
    - If the test belongs to a sibling feature, return the sibling id (re-opening
      it for repair when in a terminal state) — the current feature is NOT blamed.
    - If the test is orphaned (no known owner), log an ``orphan_test_regression``
      event and return None — the current feature is NOT blamed.

    Args:
        test_path: Pytest node-id or file path of the failing test.
        current_feature_id: The feature currently being verified.
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot.
        all_features: Feature list for pytest-prefix AC ownership resolution.
        workspace_root: Workspace root (forwarded to ownership resolvers).
        _update_feature_fn: ``(feature_id, **kwargs)`` callable for DB updates.
        _emit_event_fn: ``(event_type, **kwargs)`` callable for event emission.

    Returns:
        The owning feature_id (possibly equal to *current_feature_id*), or None
        when the test is an orphan.

    Raises:
        ValueError: When *test_path* is not a non-empty string.
    """
    return _attribute_regression_to_owning_feature(
        test_path,
        current_feature_id,
        previously_passed_at=previously_passed_at,
        all_features=all_features,
        workspace_root=workspace_root,
        _update_feature_fn=_update_feature_fn,
        _emit_event_fn=_emit_event_fn,
    )
