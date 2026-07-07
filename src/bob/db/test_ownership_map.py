"""Test-ownership map builder for regression attribution (bob.db).

Feature d09811ec-eff4-4e2d-a67a-fb771c97d121

Every feature MUST declare which test files it owns via ``pytest:`` acceptance
criteria.  Regression demotion MUST require evidence that a feature's own tests
newly fail — no scapegoating.  This module exposes ``get_test_ownership_map``
which builds the ``{test_path: feature_id}`` map consumed by
``bob.db.detect_regression``.

Delegates to the canonical implementation in ``bob.test_ownership_map`` so the
map-building logic lives in one place.
"""

from __future__ import annotations

from typing import Any

from bob.test_ownership_map import load_feature_test_ownership

__all__ = ["get_test_ownership_map"]


def get_test_ownership_map(features: list[Any]) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map from feature records.

    Scans each feature's ``acceptance_criteria`` for ``pytest:`` prefixed
    entries and records the claiming feature as the owner of that test path.
    File-level claims (no ``::`` separator) cover any test inside that file.
    First-writer wins for duplicate claims.

    Args:
        features: Sequence of feature objects or dicts.  Each must expose
            ``id`` and ``acceptance_criteria`` (via attribute or dict key).

    Returns:
        ``{test_path: feature_id}`` — first-writer wins for duplicate claims.

    Raises:
        TypeError: When *features* is None, or when a feature id is None.
        ValueError: When a feature has an empty or missing id.
    """
    return load_feature_test_ownership(features)
