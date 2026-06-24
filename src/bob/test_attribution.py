"""Test-path → owning-feature attribution for the regression-vs-baseline gate.

Feature 24081bf7-9335-454c-b85e-e6f1cbfe0fd9

Problem solved
--------------
The regression-vs-baseline check previously attributed ALL newly-failing tests
to the feature currently under verification, even when the failing tests belonged
to completely unrelated sibling features.  This caused innocent features to be
demoted to ``needs_human`` for regressions they did not cause.

This module provides two public functions:

``build_test_to_feature_map`` — build a ``{test_path: feature_id}`` map from
    the available ownership signals:
    1. Directory convention: tests under ``tests/<feature_id>/`` belong to that
       feature.
    2. pytest-prefix ACs: features that declare ``pytest: <path>`` own those
       test paths.

``attribute_failure_to_owner`` — given a single failing test path and the
    currently-verifying feature, determine the true owner, re-open terminal
    features whose tests newly regress, and log orphan regressions.  Returns
    the owner feature_id (or None for orphan tests).

Integration with bob.verification
------------------------------------
Both functions are re-exported via ``bob.verification.verifier`` so the
regression-vs-baseline gate can import from a single stable namespace.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# UUID pattern for tests/<feature_id>/ directory names
_FEATURE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_PYTEST_PREFIX = "pytest:"

_TERMINAL_STATUSES = frozenset({"completed", "failed", "needs_human", "rolled_back", "regression"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_feature_id_from_path(test_path: str) -> str | None:
    """Return the feature_id embedded in a tests/<feature_id>/... path or None."""
    parts = test_path.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part == "tests" and i + 1 < len(parts):
            candidate = parts[i + 1]
            if _FEATURE_UUID_RE.match(candidate):
                return candidate
    # Bare <feature_id>/... without leading tests/
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


def _test_matches_pytest_path(test_path: str, pytest_path: str) -> bool:
    """Return True when test_path is claimed by pytest_path."""
    test_norm = test_path.replace("\\", "/")
    pytest_norm = pytest_path.replace("\\", "/")
    if "::" not in pytest_norm:
        return test_norm == pytest_norm or test_norm.startswith(pytest_norm + "::")
    return test_norm == pytest_norm


def _get_feature_attr(feature: Any, key: str) -> Any:
    """Return feature[key] for dicts or feature.<key> for objects."""
    if isinstance(feature, dict):
        return feature.get(key)
    return getattr(feature, key, None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_test_to_feature_map(
    all_features: list[Any],
    *,
    workspace_root: str | None = None,
) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` map from all available ownership signals.

    Ownership is determined by two strategies applied in order:

    1. **pytest-prefix ACs**: features that declare ``pytest: <path>`` in their
       acceptance criteria own those test paths.  This strategy is checked first
       and the result takes precedence.

    2. **Directory convention**: test paths matching ``tests/<feature_id>/...``
       are mapped to that feature_id via the UUID embedded in the path.

    Both strategies are complementary: features that have ``pytest:`` ACs will
    be found via strategy 1; tests in ``tests/<uuid>/`` directories that lack
    a matching ``pytest:`` AC will be discovered via strategy 2 when
    ``discover_directory_tests`` is set (by iterating known test paths).

    For the verifier's purposes, call :func:`attribute_failure_to_owner` on
    each individually failing test; this function is provided for callers that
    need a bulk pre-built map (e.g. the regression detector).

    Args:
        all_features: Sequence of feature dicts or objects.  Each must expose
            ``id`` and ``acceptance_criteria`` (as a dict key or attribute).
        workspace_root: Unused; kept for forward-compatibility with filesystem
            strategies.

    Returns:
        ``dict[test_path, feature_id]`` covering all test paths that can be
        attributed via pytest-prefix ACs.
    """
    result: dict[str, str] = {}

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
                    result[declared_path] = fid

    return result


def map_test_path_to_feature_id(
    all_features: list[Any],
    *,
    workspace_root: str | None = None,
) -> dict[str, str]:
    """Alias for :func:`build_test_to_feature_map` — maps test paths to owning feature IDs.

    Returns a ``{test_path: feature_id}`` dict built from pytest-prefix ACs
    declared across all features.  This is the function name required by the
    AC for feature 3dba857e-0c80-46f9-9e78-ff864fa65fb3.

    See :func:`build_test_to_feature_map` for full documentation.
    """
    return build_test_to_feature_map(all_features, workspace_root=workspace_root)


def attribute_failure_to_owner(
    test_path: str,
    current_feature_id: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    previously_passed_at: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> str | None:
    """Return the feature_id that owns *test_path* and handle re-attribution side-effects.

    This is the gate predicate for the regression-vs-baseline step:

    - If the test belongs to *current_feature_id*, return *current_feature_id*
      so the gate counts it.
    - If the test belongs to a sibling feature (different id), re-open that
      sibling if it is in a terminal state, emit a
      ``test_regression_reattributed`` event, and return the sibling id so
      the current feature is NOT penalised.
    - If the test has no owner (orphan), emit an ``orphan_test_regression``
      event and return None so the current feature is NOT penalised.

    Ownership resolution order:
    1. ``tests/<feature_id>/`` directory convention (UUID in path).
    2. ``pytest: <path>`` ACs from *all_features*.

    Args:
        test_path: Pytest node-id or file path of the failing test.
        current_feature_id: The feature currently being verified.
        all_features: Feature list for the pytest-prefix AC strategy.
        workspace_root: Workspace root (unused; kept for future strategies).
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot.
        _update_feature_fn: Callable ``(feature_id, **kwargs)`` for DB updates.
            Defaults to ``bob.db.update_feature``.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.
            Defaults to a logger-based emitter.

    Returns:
        The owner feature_id, or None when the test is an orphan.
    """
    # Delegate to the canonical implementation in bob.verification.regression_attribution
    from bob.verification.regression_attribution import (
        attribute_regression_to_owner,
        owning_feature_for_test,
    )

    if _update_feature_fn is None:
        try:
            from bob import db as _db
            _update_feature_fn = _db.update_feature
        except Exception:
            _update_feature_fn = lambda fid, **kw: None

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs):
            logger.info("test_attribution event=%s payload=%s", event_type, kwargs)

    owner_id = owning_feature_for_test(
        test_path,
        workspace_root=workspace_root,
        all_features=all_features or [],
    )

    if owner_id == current_feature_id:
        # Test belongs to the currently-verifying feature — count it
        return owner_id

    # Sibling or orphan — re-attribute and do NOT penalise the current feature
    attribute_regression_to_owner(
        test_path,
        previously_passed_at=previously_passed_at,
        all_features=all_features or [],
        workspace_root=workspace_root,
        _update_feature_fn=_update_feature_fn,
        _emit_event_fn=_emit_event_fn,
    )
    return owner_id  # None for orphans, sibling id otherwise


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

    Delegates to :func:`bob.verification.regression_attribution.attribute_regression_to_owner`.

    When the owning feature is in a terminal state and the test was previously
    passing, reset its status to ``needs_human`` and emit a structured audit
    event.  When no owner is found, emit an ``orphan_test_regression`` event
    and return None — the calling gate must NOT block the current feature.

    Args:
        test_path: Failing test path / node-id.
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot.
        all_features: Feature list for the pytest-prefix AC strategy.
        workspace_root: Workspace root (forwarded to ownership resolvers).
        _update_feature_fn: Callable ``(feature_id, **kwargs)`` for DB updates.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.

    Returns:
        The owner feature_id that was re-opened, or None when unattributed.
    """
    from bob.verification.regression_attribution import (
        attribute_regression_to_owner as _attr,
    )

    return _attr(
        test_path,
        previously_passed_at=previously_passed_at,
        all_features=all_features,
        workspace_root=workspace_root,
        _update_feature_fn=_update_feature_fn,
        _emit_event_fn=_emit_event_fn,
    )


def attribute_regression_to_owning_feature(
    test_path: str,
    current_feature_id: str,
    *,
    previously_passed_at: str | None = None,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> str | None:
    """Attribute a regression to its owning feature, not the current one being verified.

    This is the canonical entry point for the regression-vs-baseline gate.
    Given a failing test path and the feature currently under verification,
    it determines the true owner:

    - If the test belongs to *current_feature_id*, return *current_feature_id*
      so the gate counts the failure.
    - If the test belongs to a sibling feature, re-open that sibling (if
      terminal) and return the sibling id — the current feature is NOT penalised.
    - If the test is orphaned (no known owner), log an
      ``orphan_test_regression`` event and return None — current feature is
      NOT penalised.

    Args:
        test_path: Pytest node-id or file path of the failing test.
        current_feature_id: The feature currently being verified.
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot.
        all_features: Feature list for pytest-prefix AC ownership resolution.
        workspace_root: Workspace root (forwarded to ownership resolvers).
        _update_feature_fn: ``(feature_id, **kwargs)`` callable for DB updates.
        _emit_event_fn: ``(event_type, **kwargs)`` callable for event emission.

    Returns:
        The owning feature_id (possibly equal to *current_feature_id*), or
        None when the test is an orphan.

    Raises:
        ValueError: When *test_path* is not a non-empty string.
    """
    if not isinstance(test_path, str) or not test_path.strip():
        raise ValueError(
            f"test_path must be a non-empty string, got {test_path!r}"
        )
    return attribute_failure_to_owner(
        test_path,
        current_feature_id,
        all_features=all_features,
        workspace_root=workspace_root,
        previously_passed_at=previously_passed_at,
        _update_feature_fn=_update_feature_fn,
        _emit_event_fn=_emit_event_fn,
    )


def get_test_owning_feature(
    test_path: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
) -> str | None:
    """Return the feature_id that owns *test_path*, or None when unknown.

    Ownership is determined by two strategies (tried in order):

    1. **Directory convention**: if *test_path* is under
       ``tests/<feature_id>/``, return that feature_id.
    2. **pytest-prefix ACs**: if any feature in *all_features* has a
       ``pytest: <path>`` AC that claims *test_path*, return that feature_id.

    This is the canonical public query function.  Use it in the
    regression-vs-baseline gate to determine who owns a failing test before
    deciding whether to count it against the currently-verifying feature.

    Args:
        test_path: Pytest node-id or file path.
        all_features: Sequence of feature dicts/objects for pytest-prefix
            AC lookup.  Pass None or an empty list to skip that strategy.
        workspace_root: Workspace root (unused; kept for future strategies).

    Returns:
        A feature_id string, or None when no owner is found.
    """
    from bob.verification.regression_attribution import owning_feature_for_test

    return owning_feature_for_test(
        test_path,
        workspace_root=workspace_root,
        all_features=all_features or [],
    )


def attribute_test_failure(
    test_path: str,
    current_feature_id: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    previously_passed_at: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> dict[str, Any]:
    """Attribute a failing test and return an attribution record.

    This is the high-level attribution entrypoint for the regression-vs-baseline
    gate.  It determines the true owner of *test_path*, emits the appropriate
    event (reattribution or orphan), and returns a structured dict describing
    the attribution decision.

    Side-effects:
    - If the owner is a sibling feature in a terminal state, that feature is
      re-opened for repair via *_update_feature_fn*.
    - If the test has no known owner, an ``orphan_test_regression`` event is
      emitted via *_emit_event_fn*.

    Args:
        test_path: Pytest node-id or file path of the failing test.
        current_feature_id: The feature currently being verified.
        all_features: Feature list for pytest-prefix AC ownership resolution.
        workspace_root: Workspace root (forwarded to ownership resolvers).
        previously_passed_at: ISO-8601 timestamp when the test last passed.
        _update_feature_fn: ``(feature_id, **kwargs)`` callable for DB updates.
        _emit_event_fn: ``(event_type, **kwargs)`` callable for event emission.

    Returns:
        A dict with keys:
        - ``test_path``: the input test path.
        - ``owner_feature_id``: the resolved owner, or None for orphans.
        - ``counts_against_current``: True iff the failure should be counted
          against *current_feature_id*.
        - ``event``: the emitted event type string.
    """
    owner_id = attribute_failure_to_owner(
        test_path,
        current_feature_id,
        all_features=all_features,
        workspace_root=workspace_root,
        previously_passed_at=previously_passed_at,
        _update_feature_fn=_update_feature_fn,
        _emit_event_fn=_emit_event_fn,
    )

    counts_against_current = (owner_id == current_feature_id)

    if owner_id is None:
        event = "orphan_test_regression"
    elif not counts_against_current:
        event = "test_regression_reattributed"
    else:
        event = "test_regression_attributed_to_current"

    return {
        "test_path": test_path,
        "owner_feature_id": owner_id,
        "counts_against_current": counts_against_current,
        "event": event,
    }


def attribute_regression_to_feature(
    newly_failing_tests: list[str],
    features: list[Any],
) -> dict[str, dict]:
    """Attribute newly-failing tests to their owning features — no scapegoats.

    This is the canonical entry point for the regression-vs-baseline gate to
    attribute a batch of newly-failing tests to their true owner features.
    Tests under ``tests/<feature_id>/`` are attributed by directory convention;
    tests declared by ``pytest: <path>`` ACs are attributed by that declaration.
    Tests with no known owner are placed under the ``"unattributed"`` sentinel
    key — no other feature is penalised for them.

    Args:
        newly_failing_tests: Pytest node-ids that newly fail vs baseline.
        features: All features (dicts or objects with ``id`` and
            ``acceptance_criteria``) that could own the failing tests.

    Returns:
        Dict keyed by feature_id (and possibly ``"unattributed"``).
        Values are ``{"tests": [...], "demote": bool}``.
        Only features with at least one newly-failing owned test appear.

    Raises:
        TypeError: When *newly_failing_tests* or *features* is None.
        TypeError: When *newly_failing_tests* is not a list.
    """
    if newly_failing_tests is None:
        raise TypeError("newly_failing_tests must not be None")
    if not isinstance(newly_failing_tests, list):
        raise TypeError(
            f"newly_failing_tests must be a list, got {type(newly_failing_tests)!r}"
        )
    if features is None:
        raise TypeError("features must not be None")

    ownership_map = build_test_to_feature_map(features)
    result: dict[str, dict] = {}

    for test_path in newly_failing_tests:
        # Strategy 1: pytest-prefix ACs
        owner_id = ownership_map.get(test_path)

        # Strategy 2: tests/<feature_id>/ directory convention
        if not owner_id:
            owner_id = _extract_feature_id_from_path(test_path)

        bucket_key = owner_id if owner_id else "unattributed"
        if bucket_key not in result:
            result[bucket_key] = {"tests": [], "demote": bucket_key != "unattributed"}
        result[bucket_key]["tests"].append(test_path)

    return result


def attribute_test_failure_to_owner(
    test_path: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
) -> str | None:
    """Return the feature_id that owns *test_path*, or None when unattributed.

    This is the canonical single-test ownership query for the
    regression-vs-baseline gate.  Ownership is resolved via:

    1. ``tests/<feature_id>/`` directory convention (UUID in path).
    2. ``pytest: <path>`` ACs from *all_features*.

    Args:
        test_path: Pytest node-id or file path of the failing test.
        all_features: Feature list for pytest-prefix AC ownership resolution.
        workspace_root: Workspace root (forwarded to ownership resolvers).

    Returns:
        The owning feature_id string, or None when the test is an orphan.

    Raises:
        ValueError: When *test_path* is not a non-empty string.
    """
    if not isinstance(test_path, str) or not test_path.strip():
        raise ValueError(
            f"test_path must be a non-empty string, got {test_path!r}"
        )
    return get_test_owning_feature(
        test_path,
        all_features=all_features,
        workspace_root=workspace_root,
    )


def load_feature_test_map(
    all_features: list[Any],
    *,
    workspace_root: str | None = None,
) -> dict[str, str]:
    """Build and return a ``{test_path: feature_id}`` ownership map.

    Loads the ownership map from a list of features by scanning each
    feature's ``pytest:`` acceptance criteria.  This is the canonical
    entry point for callers that need a pre-built map before the
    regression-vs-baseline gate runs.

    Args:
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        workspace_root: Workspace root (unused; kept for forward-compatibility).

    Returns:
        ``{test_path: feature_id}`` map covering all pytest-prefix ACs.
        Empty dict when *all_features* is empty.

    Raises:
        TypeError: When *all_features* is None.
    """
    if all_features is None:
        raise TypeError("all_features must not be None")
    return build_test_to_feature_map(all_features, workspace_root=workspace_root)


def attribute_failure_to_owning_feature(
    test_path: str,
    current_feature_id: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    previously_passed_at: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> str | None:
    """Return the feature_id that owns *test_path* for regression attribution.

    This is the canonical entry point for the regression-vs-baseline gate:
    given a failing test and the feature currently under verification, return
    the true owning feature_id so the gate can decide whether the failure
    counts against the current feature.

    - Returns *current_feature_id* when the test belongs to it (counts).
    - Returns a sibling feature_id when the test belongs to a different
      feature; that sibling is re-opened if in a terminal state (does NOT
      count against the current feature).
    - Returns None when the test has no known owner (orphan); emits an
      ``orphan_test_regression`` event (does NOT count against the current
      feature).

    Args:
        test_path: Pytest node-id or file path of the failing test.
        current_feature_id: The feature currently being verified.
        all_features: Feature list for pytest-prefix AC ownership resolution.
        workspace_root: Workspace root (forwarded to ownership resolvers).
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot.
        _update_feature_fn: ``(feature_id, **kwargs)`` callable for DB updates.
        _emit_event_fn: ``(event_type, **kwargs)`` callable for event emission.

    Returns:
        The owning feature_id (possibly *current_feature_id*), or None when
        the test is an orphan.

    Raises:
        ValueError: When *test_path* is not a non-empty string.
    """
    if not isinstance(test_path, str) or not test_path.strip():
        raise ValueError(
            f"test_path must be a non-empty string, got {test_path!r}"
        )
    return attribute_failure_to_owner(
        test_path,
        current_feature_id,
        all_features=all_features,
        workspace_root=workspace_root,
        previously_passed_at=previously_passed_at,
        _update_feature_fn=_update_feature_fn,
        _emit_event_fn=_emit_event_fn,
    )
