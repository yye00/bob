"""Test ownership map for bob74 — maps features to the test files they own.

Feature 82e33b94-8471-498d-9534-d020fbaaa288

Every feature must declare which test files it owns (via ``pytest:`` ACs).
Demotion to ``regression`` requires evidence that the feature's own tests
newly fail; features with no ownership entry are never scapegoated.

Public API
----------
``get_test_owners(test_path, all_features)``
    Return the feature_id that owns *test_path*, or None if unowned.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["get_test_owners"]

_PYTEST_AC_RE = re.compile(r"^\s*pytest\s*:\s*(.+)$", re.IGNORECASE)


def _build_ownership_map(all_features: list[Any]) -> dict[str, str]:
    """Build ``{test_nodeid: feature_id}`` from features' ``pytest:`` ACs."""
    ownership: dict[str, str] = {}
    for feature in all_features:
        fid = feature["id"] if isinstance(feature, dict) else feature.id
        raw_acs = (
            feature["acceptance_criteria"]
            if isinstance(feature, dict)
            else feature.acceptance_criteria
        )
        if isinstance(raw_acs, str):
            try:
                acs = json.loads(raw_acs)
            except (json.JSONDecodeError, TypeError):
                continue
        else:
            acs = list(raw_acs)

        for ac in acs:
            if not isinstance(ac, str):
                continue
            m = _PYTEST_AC_RE.match(ac)
            if m:
                node_id = m.group(1).strip()
                ownership[node_id] = fid

    return ownership


def get_test_owners(
    test_path: str,
    all_features: list[Any],
) -> str | None:
    """Return the feature_id that owns *test_path*, or None if unowned.

    Ownership is determined by scanning each feature's ``pytest:`` acceptance
    criteria lines.  A feature is an owner only if it explicitly declared
    ownership via a ``pytest: <test_path>`` AC entry.

    Args:
        test_path: Pytest node-id or file path to look up.
        all_features: List of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.

    Returns:
        The owning feature_id string, or None when no feature declared ownership.

    Raises:
        ValueError: When *test_path* is not a non-empty string.
        TypeError: When *test_path* is None.
    """
    if test_path is None:
        raise TypeError("test_path must not be None")
    if not isinstance(test_path, str):
        raise TypeError(f"test_path must be a string, got {type(test_path)!r}")
    if not test_path.strip():
        raise ValueError("test_path must not be an empty or whitespace-only string")

    ownership_map = _build_ownership_map(all_features or [])
    return ownership_map.get(test_path)
