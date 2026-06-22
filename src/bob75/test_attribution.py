"""Test path → owning feature attribution for regression-vs-baseline verification.

Feature e059c1e7-fbf4-419d-8fc3-79893d321e8e

The regression-vs-baseline check MUST attribute each failing test to the
feature that owns it, not to whichever feature is currently being verified.
Sibling-feature regressions must never gate-block an unrelated feature.

Two strategies resolve ownership:
1. Directory convention: tests/<feature_id>/ paths are owned by that UUID.
2. pytest-prefix ACs: features that declare "pytest: <path>" own those paths.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# UUID pattern matching tests/<feature_id>/ directory names
_FEATURE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_PYTEST_PREFIX = "pytest:"

__all__ = ["build_test_path_to_feature_map", "attribute_regression_to_owner"]


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
        # Strip em-dash suffix (e.g. "pytest: tests/foo.py — boundary case")
        if " — " in stripped:
            stripped = stripped[: stripped.index(" — ")].strip()
        if stripped.lower().startswith(_PYTEST_PREFIX):
            path = stripped[len(_PYTEST_PREFIX):].strip()
            if path:
                paths.append(path)
    return paths


def _extract_feature_id_from_path(test_path: str) -> str | None:
    """Return the feature_id embedded in a tests/<feature_id>/... path, or None."""
    parts = test_path.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part == "tests" and i + 1 < len(parts):
            candidate = parts[i + 1]
            if _FEATURE_UUID_RE.match(candidate):
                return candidate
    # Handle bare <feature_id>/... without leading "tests/"
    if len(parts) >= 1 and _FEATURE_UUID_RE.match(parts[0]):
        return parts[0]
    return None


def build_test_path_to_feature_map(features: list[Any]) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map from feature AC lists.

    Walks each feature's ``acceptance_criteria`` for ``pytest:`` prefixed
    entries and records the claiming feature as owner of that test path.
    Only ``pytest:`` ACs are treated as ownership declarations.

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


def attribute_regression_to_owner(
    test_path: str,
    *,
    all_features: list[Any] | None = None,
    previously_passed_at: str | None = None,
    workspace_root: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> str | None:
    """Return the owning feature_id for a newly-failing test, or None.

    Ownership is resolved by:
    1. Directory convention: tests/<feature_id>/ paths return that UUID.
    2. pytest-prefix ACs: features in *all_features* that declare
       "pytest: <path>" are matched against *test_path*.

    When an owner is found, it is returned so the caller can decide whether to
    re-open the feature.  When no owner is found, None is returned and an
    orphan_test_regression event is emitted via *_emit_event_fn*.

    Args:
        test_path: Pytest node-id or file path of the newly-failing test.
        all_features: Optional list of feature dicts/objects for the
            pytest-prefix AC ownership strategy.
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot.
        workspace_root: Workspace root path (reserved for future filesystem lookup).
        _update_feature_fn: Callable ``(feature_id, **kwargs) -> Any``.
            Defaults to a no-op in this facade; callers should supply one.
        _emit_event_fn: Callable ``(event_type, **kwargs) -> None``.
            Defaults to a logger-based emitter.

    Returns:
        The owning feature_id string, or None when the test is an orphan.
    """
    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs):
            logger.info("regression_attribution event=%s payload=%s", event_type, kwargs)

    # Strategy 1: directory-based ownership via tests/<feature_id>/
    owner_id = _extract_feature_id_from_path(test_path)

    # Strategy 2: pytest-prefix ACs
    if owner_id is None and all_features:
        ownership_map = build_test_path_to_feature_map(all_features)
        # Check exact match first
        owner_id = ownership_map.get(test_path)
        if owner_id is None:
            # Check file-level prefix match
            for path_key, fid in ownership_map.items():
                if "::" not in path_key and test_path.startswith(path_key + "::"):
                    owner_id = fid
                    break

    if owner_id is None:
        logger.info(
            "attribute_regression_to_owner: no owner for %r — logging orphan_test_regression",
            test_path,
        )
        _emit_event_fn(
            "orphan_test_regression",
            test_path=test_path,
            previously_passed_at=previously_passed_at,
        )
        return None

    logger.debug("attribute_regression_to_owner: %r → %s", test_path, owner_id)
    return owner_id
