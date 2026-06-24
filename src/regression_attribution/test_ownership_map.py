"""Test ownership map for regression attribution.

Feature a438fa7c-59ae-46c5-8ce8-1a91a064897d

Every feature must declare which test files it owns.  This module provides
``get_test_owners``, which builds a ``{test_nodeid: feature_id}`` map from
features that declare their ``pytest:`` acceptance criteria.

Demotion to 'regression' MUST require evidence that the feature's own tests
newly fail.  Tests with no declared owner are unattributed — no scapegoating.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["get_test_owners"]

_PYTEST_PREFIX = "pytest:"


def _parse_ac_list(acceptance_criteria: Any) -> list[str]:
    """Return acceptance criteria as a flat list of strings."""
    if acceptance_criteria is None:
        return []
    if isinstance(acceptance_criteria, list):
        return [str(c) for c in acceptance_criteria]
    if isinstance(acceptance_criteria, str):
        raw = acceptance_criteria.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(c) for c in parsed]
            return [str(parsed)]
        except (json.JSONDecodeError, ValueError):
            pass
        return [raw]
    return [str(acceptance_criteria)]


def _extract_pytest_paths(ac_list: list[str]) -> list[str]:
    """Extract test file paths from 'pytest:' prefixed acceptance criteria."""
    paths: list[str] = []
    for criterion in ac_list:
        stripped = criterion.strip()
        # Strip any em-dash suffix (e.g. "pytest: tests/foo.py — boundary case")
        if " — " in stripped:
            stripped = stripped[: stripped.index(" — ")].strip()
        if stripped.lower().startswith(_PYTEST_PREFIX):
            path = stripped[len(_PYTEST_PREFIX):].strip()
            if path:
                paths.append(path)
    return paths


def get_test_owners(
    features: list[Any],
) -> dict[str, str]:
    """Build a ``{test_file_path: feature_id}`` ownership map from feature AC lists.

    Walks each feature's ``acceptance_criteria`` for ``pytest:`` prefixed
    entries and records the claiming feature as owner of that test path.
    Only ``pytest:`` ACs are treated as ownership declarations.  File-level
    claims (no ``::`` separator) cover any test inside that file.

    Args:
        features: Sequence of feature objects or dicts.  Each must expose
            ``id`` and ``acceptance_criteria`` (via attribute or dict key).

    Returns:
        ``{test_path: feature_id}`` — first-writer wins for duplicate claims.

    Raises:
        TypeError: When *features* is None.
        ValueError: When a feature has an empty or missing id.
    """
    if features is None:
        raise TypeError("features must not be None")

    ownership: dict[str, str] = {}

    for feature in features:
        if isinstance(feature, dict):
            fid = feature.get("id", "")
            ac_raw = feature.get("acceptance_criteria")
        else:
            fid = getattr(feature, "id", "")
            ac_raw = getattr(feature, "acceptance_criteria", None)

        if fid is None:
            raise TypeError("feature id must not be None")
        if not fid:
            raise ValueError("feature id must not be an empty string")

        ac_list = _parse_ac_list(ac_raw)
        paths = _extract_pytest_paths(ac_list)

        for path in paths:
            if path not in ownership:
                ownership[path] = fid
            else:
                logger.debug(
                    "Test path %r already claimed by %s; ignoring claim from %s",
                    path,
                    ownership[path],
                    fid,
                )

    return ownership
