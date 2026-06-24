"""Feature-to-test ownership map for regression-vs-baseline attribution.

Feature f9355adb-ea38-46f2-8caa-4cf09b4cd274

Provides utilities to build and query a ``{test_path: feature_id}`` map so
that the regression-vs-baseline gate can attribute each newly-failing test to
its TRUE owning feature rather than to whichever feature is currently being
verified.

The ownership map is derived from two complementary strategies:
1. **Directory convention** — ``tests/<feature_id>/`` paths are owned by that UUID.
2. **pytest-prefix ACs** — features that declare ``pytest: <path>`` own those paths.

Public API
----------
``build_feature_test_map(features)``
    Build a ``{test_path: feature_id}`` ownership map from a list of features.

``attribute_failures_to_owning_feature(failing_tests, current_feature_id, ...)``
    Filter a list of newly-failing tests so only those owned by
    *current_feature_id* count toward the gate decision.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_FEATURE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
# Some legacy test directories use only the first 8 hex chars (e.g. tests/73879589/)
_FEATURE_SHORT_ID_RE = re.compile(r"^[0-9a-f]{8}$", re.IGNORECASE)
_PYTEST_PREFIX = "pytest:"

__all__ = [
    "build_feature_test_map",
    "attribute_failures_to_owning_feature",
]


def _extract_uuid_from_path(test_path: str) -> str | None:
    """Return the feature UUID (or short-id prefix) embedded in a tests/<feature_id>/... path."""
    parts = test_path.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part == "tests" and i + 1 < len(parts):
            candidate = parts[i + 1]
            if _FEATURE_UUID_RE.match(candidate):
                return candidate
            if _FEATURE_SHORT_ID_RE.match(candidate):
                return candidate
    if len(parts) >= 1:
        if _FEATURE_UUID_RE.match(parts[0]):
            return parts[0]
        if _FEATURE_SHORT_ID_RE.match(parts[0]):
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


def _extract_pytest_paths_from_acs(ac_list: list[str]) -> list[str]:
    """Extract test file paths from 'pytest:' prefixed ACs."""
    paths: list[str] = []
    for criterion in ac_list:
        stripped = criterion.strip()
        if " — " in stripped:
            stripped = stripped[: stripped.index(" — ")].strip()
        if stripped.lower().startswith(_PYTEST_PREFIX):
            path = stripped[len(_PYTEST_PREFIX):].strip()
            if path:
                paths.append(path)
    return paths


def build_feature_test_map(features: list[Any]) -> dict[str, str]:
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
        paths = _extract_pytest_paths_from_acs(ac_list)
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


def _owning_feature_for_test(
    test_path: str,
    *,
    all_features: list[Any] | None = None,
) -> str | None:
    """Return the feature_id that owns *test_path*, using both ownership strategies."""
    if not test_path or not test_path.strip():
        raise ValueError(f"test_path must be a non-empty string, got {test_path!r}")

    # Strategy 1: directory convention
    uuid = _extract_uuid_from_path(test_path)
    if uuid is not None:
        return uuid

    # Strategy 2: pytest-prefix ACs
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
                if " — " in stripped:
                    stripped = stripped[: stripped.index(" — ")].strip()
                if stripped.lower().startswith(_PYTEST_PREFIX):
                    declared_path = stripped[len(_PYTEST_PREFIX):].strip()
                    if declared_path:
                        test_norm = test_path.replace("\\", "/")
                        declared_norm = declared_path.replace("\\", "/")
                        if "::" not in declared_norm:
                            if test_norm == declared_norm or test_norm.startswith(declared_norm + "::"):
                                return fid
                        elif test_norm == declared_norm:
                            return fid
    return None


def attribute_failures_to_owning_feature(
    failing_tests: list[str],
    current_feature_id: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    previously_passed_at: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> tuple[list[str], list[str]]:
    """Filter *failing_tests* into attributable and non-attributable sets.

    The regression-vs-baseline gate MUST call this and count only
    *attributable* tests toward the gate decision for *current_feature_id*.
    Tests in *non_attributable* are owned by sibling features or are orphans;
    they are re-opened or orphan-logged, but NEVER block the current feature.

    Ownership is resolved by two strategies (tried in order):

    1. **Directory convention**: ``tests/<feature_id>/`` paths are owned by
       the feature whose UUID appears in the subtree.
    2. **pytest-prefix ACs**: features that declare ``pytest: <path>`` own
       those test paths.

    Args:
        failing_tests: Pytest node-ids that newly fail vs the pre-impl baseline.
        current_feature_id: The feature currently under verification.
        all_features: Optional list of feature dicts/objects for the
            pytest-prefix AC strategy.  Pass None to rely on directory
            convention only.
        workspace_root: Workspace root path (unused; kept for API symmetry).
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot.
        _update_feature_fn: Callable for DB update — called when re-opening
            a terminal feature.
        _emit_event_fn: Callable for event emission.

    Returns:
        A ``(attributable, non_attributable)`` tuple:
        - *attributable*: tests owned by *current_feature_id*.
        - *non_attributable*: tests owned by sibling features or orphaned.

    Raises:
        ValueError: When *failing_tests* is not a list or
            *current_feature_id* is not a non-empty string.
    """
    if not isinstance(failing_tests, list):
        raise ValueError(
            f"failing_tests must be a list of strings, got {type(failing_tests).__name__}"
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

    attributable: list[str] = []
    non_attributable: list[str] = []

    for test_path in failing_tests:
        owner = _owning_feature_for_test(test_path, all_features=all_features)
        if owner == current_feature_id:
            attributable.append(test_path)
        else:
            non_attributable.append(test_path)
            _handle_non_attributable(
                test_path,
                owner=owner,
                previously_passed_at=previously_passed_at,
                all_features=all_features,
                _update_feature_fn=_update_feature_fn,
                _emit_event_fn=_emit_event_fn,
            )

    return attributable, non_attributable


_TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "needs_human", "rolled_back", "regression"}
)


def _handle_non_attributable(
    test_path: str,
    *,
    owner: str | None,
    previously_passed_at: str | None,
    all_features: list[Any] | None,
    _update_feature_fn,
    _emit_event_fn,
) -> None:
    """Re-open owner or log orphan for a non-attributable failing test."""
    if owner is None:
        _emit_event_fn(
            "orphan_test_regression",
            test_path=test_path,
            previously_passed_at=previously_passed_at,
        )
        return

    current_status: str | None = None
    if all_features:
        for f in all_features:
            fid = f.get("id", "") if isinstance(f, dict) else getattr(f, "id", "")
            if fid == owner:
                current_status = (
                    f.get("status", "") if isinstance(f, dict) else getattr(f, "status", "")
                )
                break

    if current_status is None:
        try:
            from bob3 import db as _db
            db_feature = _db.get_feature(owner)
            current_status = db_feature.status if db_feature else None
        except Exception:
            current_status = None

    in_terminal = current_status in _TERMINAL_STATUSES if current_status else False

    if in_terminal and _update_feature_fn is not None:
        _update_feature_fn(owner, status="needs_human", refinement_attempts=0)
        logger.info(
            "Re-opened terminal feature %s (was %s) because test %r newly fails",
            owner,
            current_status,
            test_path,
        )

    _emit_event_fn(
        "test_regression_reattributed",
        test_regression_reattributed_to=owner,
        test_path=test_path,
        previous_status=current_status,
        previously_passed_at=previously_passed_at,
        reopened=in_terminal,
    )
