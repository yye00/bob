"""Regression-vs-baseline attribution: map failing tests to owning features.

Feature f50db34c-871e-43db-b59f-97ec42622cde

Problem
-------
The regression-vs-baseline verification gate ran whole-suite pytest and
attributed every newly-failing test to the currently-verifying feature.  When
sibling-feature test stubs regressed (e.g. feature 73879589 left broken stubs
after being NH-demoted), the currently-verifying feature was incorrectly
gate-blocked.

Fix
---
Two public functions provide scoped attribution so the gate can filter:

1. ``build_test_ownership_map`` — scan a workspace to build a
   ``{test_node_id_or_file: feature_id}`` ownership map using the
   ``tests/<feature_id>/`` directory convention and pytest-prefix ACs.

2. ``attribute_regression_to_owner`` — given a failing test path and the
   current feature being verified, determine whether the failure belongs to
   the current feature, a sibling feature, or is an orphan.  Returns a
   structured attribution record; never raises on valid inputs.

Integration
-----------
The ``bob3.verification`` module wraps these functions through
``bob3.regression_attribution``.  Orchestrators that call the gate directly
should use ``attribute_failures_to_owning_feature`` from
``bob3.regression_attribution`` as a higher-level entry point.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_FEATURE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_PYTEST_PREFIX = "pytest:"

__all__ = [
    "build_test_ownership_map",
    "attribute_regression_to_owner",
]


def _extract_feature_id_from_path(test_path: str) -> str | None:
    """Return the feature_id from a tests/<feature_id>/... path, or None."""
    parts = test_path.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part == "tests" and i + 1 < len(parts):
            candidate = parts[i + 1]
            if _FEATURE_UUID_RE.match(candidate):
                return candidate
    return None


def _parse_ac_list(acceptance_criteria: Any) -> list[str]:
    """Return acceptance_criteria as a flat list of strings."""
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


def build_test_ownership_map(
    workspace_root: str | None = None,
    all_features: list[Any] | None = None,
) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map.

    Two strategies are combined:

    1. **Directory scan**: walk ``tests/`` under *workspace_root* and record
       any file path under ``tests/<feature_id>/`` as owned by that feature.

    2. **pytest-prefix ACs**: iterate *all_features* and record any
       ``pytest: <path>`` AC as owned by that feature.

    Strategy 2 takes precedence over strategy 1 for the same test path
    (more specific declaration wins).

    Args:
        workspace_root: Root of the workspace to scan.  Uses the current
            working directory when None.
        all_features: Optional list of feature dicts or objects.  Each item
            must have an ``id`` field and an ``acceptance_criteria`` field
            (list or JSON string).

    Returns:
        ``{normalised_test_path: feature_id}`` mapping.  Paths are
        forward-slash-normalised relative to the workspace root.
    """
    if workspace_root is None:
        workspace_root = os.getcwd()

    ownership_map: dict[str, str] = {}

    # Strategy 1: scan tests/<feature_id>/ subtrees
    tests_dir = os.path.join(workspace_root, "tests")
    if os.path.isdir(tests_dir):
        for entry in os.scandir(tests_dir):
            if entry.is_dir() and _FEATURE_UUID_RE.match(entry.name):
                feature_id = entry.name
                for dirpath, _dirs, filenames in os.walk(entry.path):
                    for fname in filenames:
                        abs_path = os.path.join(dirpath, fname)
                        rel_path = os.path.relpath(abs_path, workspace_root)
                        norm = rel_path.replace("\\", "/")
                        if norm not in ownership_map:
                            ownership_map[norm] = feature_id

    # Strategy 2: pytest-prefix ACs (overrides directory for same path)
    if all_features:
        for feature in all_features:
            if isinstance(feature, dict):
                fid = feature.get("id", "")
                ac_raw = feature.get("acceptance_criteria")
            else:
                fid = getattr(feature, "id", "")
                ac_raw = getattr(feature, "acceptance_criteria", None)
            if not fid:
                continue
            for criterion in _parse_ac_list(ac_raw):
                stripped = criterion.strip()
                if stripped.lower().startswith(_PYTEST_PREFIX):
                    path_part = stripped[len(_PYTEST_PREFIX):].strip()
                    if path_part:
                        norm = path_part.replace("\\", "/")
                        ownership_map[norm] = fid

    return ownership_map


def attribute_regression_to_owner(
    test_path: str,
    current_feature_id: str,
    *,
    ownership_map: dict[str, str] | None = None,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    _emit_event_fn=None,
) -> dict[str, Any]:
    """Attribute a failing test to its owning feature.

    Returns a structured attribution record indicating whether the failure
    should count against *current_feature_id* or be re-attributed to a
    sibling feature (or logged as an orphan).

    Args:
        test_path: Pytest node-id or file path (e.g.
            ``"tests/<uuid>/test_foo.py::test_bar"`` or
            ``"tests/test_flat.py"``).
        current_feature_id: The feature currently under verification.
        ownership_map: Pre-built ownership map from ``build_test_ownership_map``.
            When None, one is built on-the-fly using *all_features* and
            *workspace_root*.
        all_features: Feature list for pytest-prefix AC strategy (passed to
            ``build_test_ownership_map`` when *ownership_map* is None).
        workspace_root: Workspace root (passed to ``build_test_ownership_map``
            when *ownership_map* is None).
        _emit_event_fn: Optional callable ``(event_type, **kwargs) -> None``
            for structured event emission (e.g. audit logging).  When None,
            events are logged at INFO level.

    Returns:
        A dict with keys:
        - ``"test_path"`` (str): the input path, unchanged.
        - ``"owner_feature_id"`` (str | None): the owning feature, or None.
        - ``"counts_against_current"`` (bool): True iff failure belongs to
          *current_feature_id*.
        - ``"event"`` (str): one of
          - ``"test_regression_attributed_to_current"``
          - ``"test_regression_reattributed"``
          - ``"orphan_test_regression"``

    Raises:
        ValueError: When *test_path* or *current_feature_id* is not a
            non-empty string.
    """
    if not isinstance(test_path, str) or not test_path.strip():
        raise ValueError(
            f"test_path must be a non-empty string, got {test_path!r}"
        )
    if not isinstance(current_feature_id, str) or not current_feature_id.strip():
        raise ValueError(
            f"current_feature_id must be a non-empty string, got {current_feature_id!r}"
        )

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs):
            logger.info(
                "regression_attribution event=%s payload=%s", event_type, kwargs
            )

    if ownership_map is None:
        ownership_map = build_test_ownership_map(
            workspace_root=workspace_root,
            all_features=all_features,
        )

    # Resolve owner: try directory convention first, then ownership map
    owner = _extract_feature_id_from_path(test_path)

    if owner is None:
        # Check ownership map (handles pytest-prefix ACs and directory-scanned files)
        norm_path = test_path.replace("\\", "/")
        # Try exact match
        owner = ownership_map.get(norm_path)
        if owner is None:
            # Try file-level prefix match (strip ::test_name suffix)
            for key, fid in ownership_map.items():
                if "::" not in key and norm_path.startswith(key + "::"):
                    owner = fid
                    break

    if owner is None:
        _emit_event_fn("orphan_test_regression", test_path=test_path)
        return {
            "test_path": test_path,
            "owner_feature_id": None,
            "counts_against_current": False,
            "event": "orphan_test_regression",
        }

    if owner == current_feature_id:
        _emit_event_fn(
            "test_regression_attributed_to_current",
            test_path=test_path,
            owner_feature_id=owner,
        )
        return {
            "test_path": test_path,
            "owner_feature_id": owner,
            "counts_against_current": True,
            "event": "test_regression_attributed_to_current",
        }

    # Sibling feature's test
    _emit_event_fn(
        "test_regression_reattributed",
        test_path=test_path,
        owner_feature_id=owner,
        current_feature_id=current_feature_id,
    )
    return {
        "test_path": test_path,
        "owner_feature_id": owner,
        "counts_against_current": False,
        "event": "test_regression_reattributed",
    }
