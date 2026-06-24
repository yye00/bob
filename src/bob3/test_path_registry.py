"""Test-path → owning-feature registry for the regression-vs-baseline gate.

Feature 8ffeacb6-f5b4-4f30-86cd-a24001e9ee0e

This module provides a persistent, queryable registry that maps test paths to
the feature IDs that own them.  It powers the no-scapegoat policy: when the
regression-vs-baseline check detects a newly-failing test, it consults this
registry to determine the true owner rather than charging the currently-verifying
feature.

Two ownership signals are supported:

1. **Directory convention**: tests under ``tests/<feature_id>/`` belong to
   that feature by path convention.
2. **pytest-prefix ACs**: features that declare ``pytest: <path>`` in their
   acceptance criteria own those test paths.

Public API
----------
``build_registry`` — build a ``{test_path: feature_id}`` registry from a
    feature list.
``lookup_owner`` — query the registry for a single test path.
``register_feature_tests`` — add a feature's test paths to an existing registry.
"""

from __future__ import annotations

import json
import re
from typing import Any

# UUID pattern for tests/<feature_id>/ directory names
_FEATURE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_PYTEST_PREFIX = "pytest:"

__all__ = [
    "build_registry",
    "lookup_owner",
    "register_feature_tests",
]


def _extract_feature_id_from_path(test_path: str) -> str | None:
    """Return the feature_id embedded in a tests/<feature_id>/... path or None."""
    parts = test_path.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part == "tests" and i + 1 < len(parts):
            candidate = parts[i + 1]
            if _FEATURE_UUID_RE.match(candidate):
                return candidate
    if parts and _FEATURE_UUID_RE.match(parts[0]):
        return parts[0]
    return None


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


def _get_feature_attr(feature: Any, key: str) -> Any:
    """Return feature[key] for dicts or feature.<key> for objects."""
    if isinstance(feature, dict):
        return feature.get(key)
    return getattr(feature, key, None)


def build_registry(
    all_features: list[Any],
    *,
    workspace_root: str | None = None,
) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` registry from a feature list.

    Ownership is determined by pytest-prefix ACs declared across all features.
    Directory-convention ownership (``tests/<feature_id>/``) is resolved
    dynamically by :func:`lookup_owner` for each individual query.

    Args:
        all_features: Sequence of feature dicts or objects.  Each must expose
            ``id`` and ``acceptance_criteria`` (as dict key or attribute).
        workspace_root: Reserved for future filesystem-based discovery.

    Returns:
        ``{test_path: feature_id}`` dict covering all pytest-prefix ACs.

    Raises:
        TypeError: When *all_features* is None.
    """
    if all_features is None:
        raise TypeError("all_features must not be None")

    registry: dict[str, str] = {}
    for feature in all_features:
        fid = _get_feature_attr(feature, "id") or ""
        if not fid:
            continue
        ac_raw = _get_feature_attr(feature, "acceptance_criteria")
        for criterion in _parse_ac_list(ac_raw):
            stripped = criterion.strip()
            if stripped.lower().startswith(_PYTEST_PREFIX):
                declared_path = stripped[len(_PYTEST_PREFIX):].strip()
                if declared_path:
                    registry[declared_path] = fid
    return registry


def lookup_owner(
    test_path: str,
    registry: dict[str, str] | None = None,
) -> str | None:
    """Return the feature_id that owns *test_path*, or None when unknown.

    Ownership is resolved in order:

    1. Exact or prefix match against the *registry* (pytest-prefix ACs).
    2. ``tests/<feature_id>/`` directory convention (UUID in path).

    Args:
        test_path: Pytest node-id or file path to look up.
        registry: Pre-built ``{test_path: feature_id}`` map from
            :func:`build_registry`.  When None, only directory-convention
            ownership is checked.

    Returns:
        The owning feature_id string, or None when unattributed.

    Raises:
        ValueError: When *test_path* is not a non-empty string.
    """
    if not isinstance(test_path, str) or not test_path.strip():
        raise ValueError(
            f"test_path must be a non-empty string, got {test_path!r}"
        )

    if registry:
        # Exact match
        if test_path in registry:
            return registry[test_path]
        # Prefix match (file-only path claims all ::test_name under it)
        test_norm = test_path.replace("\\", "/")
        for declared, fid in registry.items():
            declared_norm = declared.replace("\\", "/")
            if "::" not in declared_norm:
                if test_norm == declared_norm or test_norm.startswith(declared_norm + "::"):
                    return fid

    # Directory convention fallback
    return _extract_feature_id_from_path(test_path)


def register_feature_tests(
    registry: dict[str, str],
    feature_id: str,
    test_paths: list[str],
) -> dict[str, str]:
    """Add a feature's test paths to an existing registry and return it.

    Mutates *registry* in-place and also returns it for convenience.

    Args:
        registry: The ``{test_path: feature_id}`` map to update.
        feature_id: The feature that owns the given test paths.
        test_paths: List of pytest node-ids or file paths to register.

    Returns:
        The updated *registry*.

    Raises:
        TypeError: When *registry* is not a dict, or *test_paths* is not a list.
        ValueError: When *feature_id* is empty.
    """
    if not isinstance(registry, dict):
        raise TypeError(f"registry must be a dict, got {type(registry)!r}")
    if not isinstance(test_paths, list):
        raise TypeError(f"test_paths must be a list, got {type(test_paths)!r}")
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError(f"feature_id must be a non-empty string, got {feature_id!r}")

    for path in test_paths:
        if path and isinstance(path, str):
            registry[path] = feature_id
    return registry
