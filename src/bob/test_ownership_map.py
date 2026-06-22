"""Test ownership map — maps test file paths to the feature that owns them.

Feature 7bf35555-77ae-4e85-9a11-a753dc0bc599

Every feature must declare which test files it owns.  This module provides
``build_ownership_map``, which builds a ``{test_nodeid: feature_id}`` map
from a list of feature declarations, each carrying a ``test_files`` list.
"""

from __future__ import annotations

__all__ = ["build_ownership_map"]


def build_ownership_map(features: list[dict]) -> dict[str, str]:
    """Build a ``{test_file_path: feature_id}`` ownership map.

    Args:
        features: List of feature dicts, each with ``"id"`` (str) and
            ``"test_files"`` (list[str]) keys.  ``"id"`` must be a non-empty
            string; ``"test_files"`` may be empty.

    Returns:
        Mapping from test file path to the feature_id that declared ownership.
        Features with no test files contribute nothing to the map.

    Raises:
        TypeError: When *features* is None.
        ValueError: When a feature dict is missing ``"id"`` or has a None/empty
            ``"id"``.
        KeyError: When a feature dict lacks the ``"id"`` key.
    """
    if features is None:
        raise TypeError("features must not be None")

    ownership: dict[str, str] = {}
    for feature in features:
        fid = feature["id"]  # KeyError if missing
        if fid is None:
            raise TypeError("feature id must not be None")
        if not isinstance(fid, str):
            raise TypeError(f"feature id must be a string, got {type(fid)!r}")
        if not fid:
            raise ValueError("feature id must not be an empty string")

        test_files = feature.get("test_files", [])
        for tf in test_files:
            ownership[tf] = fid

    return ownership
