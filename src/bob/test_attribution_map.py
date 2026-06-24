"""Test-path → owning-feature attribution map for the regression-vs-baseline gate.

Feature ee144b68-21ad-4a5e-b1bb-da2e9087f69a

This module exposes the canonical ``get_test_owning_feature`` query function
that maps a pytest test path to the feature that owns it.

Ownership is resolved via two strategies (tried in order):
1. Directory convention: ``tests/<feature_id>/`` → that feature_id.
2. pytest-prefix ACs: features that declare ``pytest: <path>`` own those paths.

The regression-vs-baseline gate uses this map to ensure that only the
currently-verifying feature's OWN tests count toward the gate decision.
Sibling-feature regressions and orphan tests are excluded.
"""

from __future__ import annotations

from typing import Any

from bob.test_attribution import get_test_owning_feature

__all__ = [
    "get_test_owning_feature",
    "build_ownership_map",
]


def build_ownership_map(
    all_features: list[Any],
) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` map from a list of features.

    Scans each feature's ``acceptance_criteria`` for ``pytest:`` lines and
    returns a flat ownership map.  Features that declare no ``pytest:`` ACs
    contribute nothing to the map — they own no tests and must not be
    scapegoated for failures in tests they never claimed.

    Args:
        all_features: List of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.

    Returns:
        ``{test_path: feature_id}`` ownership map.  Empty dict when
        *all_features* is empty.

    Raises:
        TypeError: When *all_features* is None.
    """
    if all_features is None:
        raise TypeError("all_features must not be None")

    from bob.regression_attribution import map_test_ownership
    return map_test_ownership(all_features)
