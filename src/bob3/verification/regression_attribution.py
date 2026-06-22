"""Regression attribution for the regression-vs-baseline verification gate.

Feature 8add91fb-617f-4cbd-8aa5-681e96c3f5f8

Problem solved
--------------
The regression-vs-baseline check runs whole-suite and attributes all
newly-failing tests to whichever feature is currently being verified.
When sibling-feature test stubs regress (e.g. feature 73879589 left broken
stubs after being NH-demoted), the current feature is incorrectly gate-blocked.

This module introduces a three-function attribution layer:

1. ``owning_feature_for_test`` — resolve a test path to the feature that owns it,
   using two strategies:
   - The tests/<feature_id>/ subtree convention (directory-based ownership)
   - pytest-prefix ACs declared by completed features

2. ``attribute_regression_to_owner`` — re-open the owning feature when a
   terminal-state feature's test newly regresses.

3. ``is_attributable_to_current_feature`` — return True only when the
   failing test is owned by the currently-verifying feature; False for
   sibling or unknown tests.

Integration
-----------
The regression-vs-baseline step in the verifier should filter its
failing-test set through ``is_attributable_to_current_feature``.  Only
attributable failures count toward the current feature's gate result.
The whole-suite invariant pass (F-R7-532-style) retains operation;
reattribution is a layer on top, not a replacement.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# UUID pattern used in tests/<feature_id>/ directory names
_FEATURE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Terminal feature statuses that can be re-opened
_TERMINAL_STATUSES = frozenset({"completed", "failed", "needs_human", "rolled_back", "regression"})

# Sentinel key written to the audit log when a test is reattributed
_SENTINEL_KEY = "test_regression_reattributed_to"

# pytest: AC prefix (same convention as orchestrator module)
_PYTEST_PREFIX = "pytest:"


def _extract_feature_id_from_path(test_path: str) -> str | None:
    """Return the feature_id embedded in a tests/<feature_id>/... path.

    Returns None if the path does not follow the convention.
    """
    parts = test_path.replace("\\", "/").split("/")
    # Look for a UUID-shaped path segment that follows "tests"
    for i, part in enumerate(parts):
        if part == "tests" and i + 1 < len(parts):
            candidate = parts[i + 1]
            if _FEATURE_UUID_RE.match(candidate):
                return candidate
    # Also handle bare <feature_id>/... without leading "tests/"
    if len(parts) >= 1 and _FEATURE_UUID_RE.match(parts[0]):
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


def _test_matches_pytest_path(test_path: str, pytest_path: str) -> bool:
    """Return True when test_path is claimed by pytest_path."""
    # Normalise separators
    test_norm = test_path.replace("\\", "/")
    pytest_norm = pytest_path.replace("\\", "/")
    if "::" not in pytest_norm:
        # File-level claim: match any test in the file
        return test_norm == pytest_norm or test_norm.startswith(pytest_norm + "::")
    return test_norm == pytest_norm


def _find_owner_via_pytest_acs(
    test_path: str,
    all_features: list[Any],
) -> str | None:
    """Search all_features for a feature whose pytest: ACs claim test_path."""
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
                declared_path = stripped[len(_PYTEST_PREFIX):].strip()
                if declared_path and _test_matches_pytest_path(test_path, declared_path):
                    return fid
    return None


def owning_feature_for_test(
    test_path: str,
    *,
    workspace_root: str | None = None,
    all_features: list[Any] | None = None,
) -> str | None:
    """Return the feature_id that owns *test_path*, or None when unknown.

    Ownership is determined by two strategies (tried in order):

    1. **Directory convention**: if *test_path* is under
       ``tests/<feature_id>/``, return that feature_id.

    2. **pytest-prefix ACs**: if any feature in *all_features* has a
       ``pytest: <path>`` AC that claims *test_path*, return that feature_id.

    Args:
        test_path: Pytest node-id or file path, e.g.
            ``"tests/abc123.../test_foo.py::test_bar"`` or
            ``"tests/abc123.../test_foo.py"``.
        workspace_root: Ignored; kept for future filesystem-based lookup.
        all_features: Sequence of feature dicts or objects used for the
            pytest-prefix AC strategy.  Pass an empty list (or None) to
            skip this strategy.

    Returns:
        A feature_id string, or None when no owner is found.
    """
    if not test_path:
        return None

    # Strategy 1: directory-based ownership via tests/<feature_id>/
    feature_id = _extract_feature_id_from_path(test_path)
    if feature_id is not None:
        logger.debug("owning_feature_for_test: %r → %s (directory)", test_path, feature_id)
        return feature_id

    # Strategy 2: pytest-prefix ACs
    if all_features:
        owner = _find_owner_via_pytest_acs(test_path, all_features)
        if owner is not None:
            logger.debug("owning_feature_for_test: %r → %s (pytest AC)", test_path, owner)
            return owner

    logger.debug("owning_feature_for_test: %r → None (orphan)", test_path)
    return None


def attribute_regression_to_owner(
    test_path: str,
    *,
    previously_passed_at: str | None = None,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> str | None:
    """Re-open the owner feature when its test newly regresses.

    When the owning feature is in a terminal state and the test was
    previously passing, reset its status to ``needs_human``, reset
    ``refinement_attempts`` to 0, and write a structured audit-log event
    with sentinel ``test_regression_reattributed_to=<owner_id>``.

    When no owner is found, emit an ``orphan_test_regression`` event and
    return None — the calling gate must NOT block the current feature.

    Args:
        test_path: Failing test path / node-id.
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot
            (used in the orphan event).
        all_features: Feature list for the pytest-prefix AC strategy.
        workspace_root: Workspace root (forwarded to owning_feature_for_test).
        _update_feature_fn: Callable ``(feature_id, **kwargs) -> Any``.
            Defaults to ``bob3.db.update_feature``.
        _emit_event_fn: Callable ``(event_type, **kwargs) -> None``.
            Defaults to a logger-based emitter.

    Returns:
        The owner feature_id that was re-opened, or None when unattributed.
    """
    if _update_feature_fn is None:
        from bob3 import db as _db
        _update_feature_fn = _db.update_feature

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs):
            logger.info("regression_attribution event=%s payload=%s", event_type, kwargs)

    owner_id = owning_feature_for_test(
        test_path,
        workspace_root=workspace_root,
        all_features=all_features,
    )

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

    # Determine whether owner is in a terminal state
    owner_feature = None
    if all_features:
        for f in all_features:
            if isinstance(f, dict):
                fid = f.get("id", "")
                fstatus = f.get("status", "")
            else:
                fid = getattr(f, "id", "")
                fstatus = getattr(f, "status", "")
            if fid == owner_id:
                owner_feature = f
                current_status = fstatus
                break
        else:
            current_status = None
    else:
        current_status = None

    # If we can't determine status from the list, fetch from DB
    if current_status is None:
        try:
            from bob3 import db as _db
            db_feature = _db.get_feature(owner_id)
            current_status = db_feature.status if db_feature else None
        except Exception:
            current_status = None

    in_terminal = current_status in _TERMINAL_STATUSES if current_status else False

    if in_terminal:
        logger.info(
            "attribute_regression_to_owner: re-opening terminal feature %s "
            "(status=%s) because its test %r newly regresses",
            owner_id,
            current_status,
            test_path,
        )
        _update_feature_fn(owner_id, status="needs_human", refinement_attempts=0)

    _emit_event_fn(
        "test_regression_reattributed",
        **{_SENTINEL_KEY: owner_id},
        test_path=test_path,
        previous_status=current_status,
        previously_passed_at=previously_passed_at,
        reopened=in_terminal,
    )

    if not in_terminal:
        logger.debug(
            "attribute_regression_to_owner: owner %s is not in a terminal state (%s) — no reopen",
            owner_id,
            current_status,
        )

    return owner_id


def is_attributable_to_current_feature(
    test_path: str,
    current_feature_id: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
) -> bool:
    """Return True only when *test_path* is owned by *current_feature_id*.

    Returns False when:
    - The test is owned by a sibling feature (different feature_id)
    - The test has no owner (orphan)

    This is the gate predicate: the regression-vs-baseline step MUST filter
    its failing-test set through this function.  Only True results count
    toward the current feature's gate decision.

    Args:
        test_path: Failing test path / node-id.
        current_feature_id: The feature currently being verified.
        all_features: Feature list for the pytest-prefix AC strategy.
        workspace_root: Workspace root (forwarded to owning_feature_for_test).

    Returns:
        True iff ``owning_feature_for_test(test_path) == current_feature_id``.
    """
    owner = owning_feature_for_test(
        test_path,
        workspace_root=workspace_root,
        all_features=all_features,
    )
    result = owner == current_feature_id
    if not result:
        logger.debug(
            "is_attributable_to_current_feature: %r owner=%s current=%s → False",
            test_path,
            owner,
            current_feature_id,
        )
    return result


def filter_attributable_failures(
    failing_tests: list[str],
    current_feature_id: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    previously_passed_at: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> list[str]:
    """Filter *failing_tests* to only those attributable to *current_feature_id*.

    For each failing test that is NOT attributable to the current feature,
    call ``attribute_regression_to_owner`` to re-open or log the orphan.

    Returns the subset of *failing_tests* that should count toward the
    current feature's gate result.
    """
    attributable: list[str] = []
    for test_path in failing_tests:
        if is_attributable_to_current_feature(
            test_path,
            current_feature_id,
            all_features=all_features,
            workspace_root=workspace_root,
        ):
            attributable.append(test_path)
        else:
            attribute_regression_to_owner(
                test_path,
                previously_passed_at=previously_passed_at,
                all_features=all_features,
                workspace_root=workspace_root,
                _update_feature_fn=_update_feature_fn,
                _emit_event_fn=_emit_event_fn,
            )
    return attributable
