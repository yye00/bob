"""Top-level regression attribution facade for bob3.

Feature c2dcfcda-ee72-4e80-91a3-967c0d532acc
Feature dcdef134-19b5-41a0-8f5b-1622239bc703 (test-ownership map, no scapegoats)

Exposes ``attribute_failures_to_owning_feature``, the canonical entry point
for the regression-vs-baseline verification gate to filter failing tests so
that only those attributable to the currently-verifying feature count as gate
failures.

Sibling-feature regressions (tests owned by a *different* feature) are
re-attributed to their true owner via the sub-module; the current feature is
not penalised for them.

Also exposes ``detect_regression`` and ``get_feature_owned_tests`` which
enforce the no-scapegoat policy: demotion to ``regression`` is only permitted
when the feature's own tests newly fail.

Integration with bob3.verification
------------------------------------
The filtering is wired into the regression-vs-baseline step in the verifier
via ``bob3.verification.regression_attribution.filter_attributable_failures``.
This module provides the convenience facade (a single unified function) so
orchestrator call-sites only need one import rather than two.

Integration with bob3.orchestrator
-------------------------------------
``detect_regression`` replaces any bare heuristic that demoted the "first
completed feature" when no ownership entry existed.  Every feature must
declare which test files it owns; the orchestrator calls
``get_feature_owned_tests`` to read those declarations and passes the
resulting map to ``detect_regression``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bob3.test_ownership_map import load_test_ownership_map
from bob3.test_ownership_map import get_test_owners
from bob3.test_ownership_map import validate_test_ownership
from bob3.verification.regression_attribution import (
    attribute_regression_to_owner,
    filter_attributable_failures,
    is_attributable_to_current_feature,
    owning_feature_for_test,
)

__all__ = [
    "attribute_failure_to_owner",
    "attribute_failures_to_owning_feature",
    "attribute_regression_to_feature",
    "attribute_test_failure_to_owner",
    "build_test_owner_map",
    "build_test_ownership_map",
    "detect_regression",
    "get_feature_owned_tests",
    "get_test_owners",
    "load_test_ownership_map",
    "map_test_ownership",
    "TestOwnershipMap",
    "validate_test_ownership",
    "verify_regression_ownership",
    # Re-exports for callers that import from here
    "attribute_regression_to_owner",
    "filter_attributable_failures",
    "is_attributable_to_current_feature",
    "owning_feature_for_test",
]

# Sentinel key for tests with no declared owner.
UNATTRIBUTED_KEY = "unattributed"


class TestOwnershipMap:
    """Maps test node-ids / file paths to the feature that owns them.

    Built from each feature's ``pytest:`` acceptance criteria.  The no-scapegoat
    policy is enforced here: a feature is only eligible for regression demotion
    when at least one of its *own* declared tests newly fails.

    Usage::

        ownership = TestOwnershipMap.from_features(all_features)
        result = ownership.detect_regression(newly_failing)

    """

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        """Initialise with an optional ``{test_path: feature_id}`` mapping.

        Args:
            mapping: Initial ownership map.  Defaults to an empty dict.

        Raises:
            TypeError: When *mapping* is not a dict or None.
        """
        if mapping is None:
            mapping = {}
        if not isinstance(mapping, dict):
            raise TypeError(
                f"mapping must be a dict, got {type(mapping)!r}"
            )
        self._map: dict[str, str] = dict(mapping)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_features(cls, features: list[Any]) -> "TestOwnershipMap":
        """Build a map from a list of feature dicts/objects.

        Scans each feature's ``acceptance_criteria`` for ``pytest:`` lines and
        registers the extracted paths as owned by that feature.

        Args:
            features: Iterable of feature dicts or objects with ``id`` and
                ``acceptance_criteria`` fields.

        Returns:
            A populated :class:`TestOwnershipMap` instance.

        Raises:
            TypeError: When *features* is None.
            ValueError: When a feature has no ``id``.
        """
        if features is None:
            raise TypeError("features must not be None")
        mapping: dict[str, str] = {}
        for feature in features:
            owned = get_feature_owned_tests(feature)
            fid = (
                feature["id"]
                if isinstance(feature, dict)
                else getattr(feature, "id")
            )
            for path in owned:
                mapping[path] = fid
        return cls(mapping)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def owner_for(self, test_path: str) -> str | None:
        """Return the feature_id that owns *test_path*, or None.

        Performs both exact-match and file-prefix matching so that a
        ``pytest: tests/test_foo.py`` declaration matches any
        ``tests/test_foo.py::test_something`` node-id.
        """
        if test_path in self._map:
            return self._map[test_path]
        # File-prefix match: "tests/test_foo.py" owns "tests/test_foo.py::test_x"
        for declared, fid in self._map.items():
            if test_path.startswith(declared + "::") or test_path == declared:
                return fid
        return None

    def detect_regression(
        self,
        newly_failing_tests: list[str],
    ) -> dict[str, dict]:
        """Attribute *newly_failing_tests* using this ownership map.

        Delegates to the module-level :func:`detect_regression` after
        expanding file-prefix entries to cover node-id variants.

        Args:
            newly_failing_tests: Pytest node-ids that newly fail vs baseline.

        Returns:
            Same structure as the module-level :func:`detect_regression`:
            ``{feature_id: {"tests": [...], "demote": bool}}``.

        Raises:
            TypeError: When *newly_failing_tests* is None or not a list.
        """
        if newly_failing_tests is None:
            raise TypeError("newly_failing_tests must not be None")
        if not isinstance(newly_failing_tests, list):
            raise TypeError(
                f"newly_failing_tests must be a list, got {type(newly_failing_tests)!r}"
            )
        # Build a resolved map for exact node-ids so detect_regression can
        # look them up directly.
        resolved: dict[str, str] = {}
        for test in newly_failing_tests:
            owner = self.owner_for(test)
            if owner is not None:
                resolved[test] = owner
        return detect_regression(
            newly_failing_tests=newly_failing_tests,
            test_ownership_map=resolved,
        )

    # ------------------------------------------------------------------
    # Dict-like helpers
    # ------------------------------------------------------------------

    def __getitem__(self, test_path: str) -> str:
        owner = self.owner_for(test_path)
        if owner is None:
            raise KeyError(test_path)
        return owner

    def __contains__(self, test_path: object) -> bool:
        if not isinstance(test_path, str):
            return False
        return self.owner_for(test_path) is not None

    def __len__(self) -> int:
        return len(self._map)

    def __repr__(self) -> str:
        return f"TestOwnershipMap({self._map!r})"

# Regex matching "pytest: <test_path>" AC lines.
_PYTEST_AC_RE = re.compile(r"^\s*pytest\s*:\s*(.+?)(\s*—.*)?$", re.IGNORECASE)


def _parse_ac_list(acceptance_criteria: Any) -> list[str]:
    """Return the acceptance_criteria field as a flat list of strings."""
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
            return [raw]
    return [str(acceptance_criteria)]


def get_feature_owned_tests(feature: Any) -> list[str]:
    """Return the list of test node-ids / paths declared by *feature*.

    Scans the feature's ``acceptance_criteria`` for lines of the form
    ``pytest: <path>`` and returns the extracted paths.  Features that
    declare no ``pytest:`` ACs return an empty list — they own no tests and
    MUST NOT be scapegoated for failures in tests they never claimed.

    Args:
        feature: A feature dict or object with ``id`` and
            ``acceptance_criteria`` fields.

    Returns:
        List of pytest node-ids the feature has declared ownership of.
        Empty list when no ``pytest:`` ACs are declared.

    Raises:
        ValueError: When *feature* is None or has no ``id`` field.
        TypeError: When *feature* is not a dict or object with the required
            fields.
    """
    if feature is None:
        raise ValueError("feature must not be None")

    if isinstance(feature, dict):
        if "id" not in feature:
            raise ValueError("feature dict must have an 'id' key")
        raw_acs = feature.get("acceptance_criteria", [])
    else:
        if not hasattr(feature, "id"):
            raise ValueError("feature object must have an 'id' attribute")
        raw_acs = getattr(feature, "acceptance_criteria", [])

    ac_list = _parse_ac_list(raw_acs)
    owned: list[str] = []
    for ac in ac_list:
        m = _PYTEST_AC_RE.match(ac)
        if m:
            owned.append(m.group(1).strip())
    return owned


def detect_regression(
    newly_failing_tests: list[str],
    test_ownership_map: dict[str, str],
) -> dict[str, dict]:
    """Attribute newly-failing tests to their owning features — no scapegoats.

    For each test in *newly_failing_tests*:
    - If the test appears in *test_ownership_map*, it is attributed to the
      owning feature and that feature is marked for demotion.
    - If no entry exists, the test is placed under the ``"unattributed"``
      sentinel key; no other feature is blamed.

    A feature is demoted (``"demote": True``) ONLY when at least one of its
    own tests appears in *newly_failing_tests*.  This prevents the historical
    scapegoat pattern where "the first completed feature that isn't the
    causing feature" was blindly blamed.

    Args:
        newly_failing_tests: Pytest node-ids that newly fail vs baseline.
        test_ownership_map: ``{test_nodeid: feature_id}`` ownership map,
            typically built from each feature's ``pytest:`` ACs via
            ``get_feature_owned_tests``.

    Returns:
        Dict keyed by feature_id (and possibly ``"unattributed"``).
        Values are ``{"tests": [...], "demote": bool}``.
        Only features with at least one newly-failing owned test are present.

    Raises:
        TypeError: When *newly_failing_tests* or *test_ownership_map* is None
            or the wrong type.
    """
    if newly_failing_tests is None:
        raise TypeError("newly_failing_tests must not be None")
    if not isinstance(newly_failing_tests, list):
        raise TypeError(
            f"newly_failing_tests must be a list, got {type(newly_failing_tests)!r}"
        )
    if test_ownership_map is None:
        raise TypeError("test_ownership_map must not be None")
    if not isinstance(test_ownership_map, dict):
        raise TypeError(
            f"test_ownership_map must be a dict, got {type(test_ownership_map)!r}"
        )

    if not newly_failing_tests:
        return {}

    result: dict[str, dict] = {}
    for test in newly_failing_tests:
        owner = test_ownership_map.get(test)
        if owner is None:
            bucket = result.setdefault(UNATTRIBUTED_KEY, {"tests": [], "demote": False})
            bucket["tests"].append(test)
        else:
            bucket = result.setdefault(owner, {"tests": [], "demote": True})
            bucket["tests"].append(test)

    for bucket in result.values():
        bucket["tests"].sort()

    return result


def attribute_test_failure_to_owner(
    test_path: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
) -> str | None:
    """Return the feature_id that owns *test_path*, or None if unknown.

    This is a single-test convenience wrapper around
    ``owning_feature_for_test`` that resolves ownership via the
    ``tests/<feature_id>/`` directory convention and pytest-prefix ACs.

    Args:
        test_path: Pytest node-id or file path to look up.
        all_features: Optional list of feature dicts/objects for the
            pytest-prefix AC ownership strategy.
        workspace_root: Workspace root path (forwarded to sub-module).

    Returns:
        The owning feature_id string, or None when unattributed.

    Raises:
        ValueError: When *test_path* is not a non-empty string.
    """
    if not isinstance(test_path, str) or not test_path.strip():
        raise ValueError(
            f"test_path must be a non-empty string, got {test_path!r}"
        )
    return owning_feature_for_test(
        test_path,
        workspace_root=workspace_root,
        all_features=all_features,
    )


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

    The regression-vs-baseline verification gate should call this function
    and only count the returned *attributable* tests toward the gate decision
    for *current_feature_id*.  Tests in *non_attributable* are handled
    (re-opened or orphan-logged) by the sub-module; the calling gate MUST NOT
    penalise the current feature for them.

    Args:
        failing_tests: Test node-ids that newly fail vs the pre-impl baseline.
        current_feature_id: The feature currently under verification.
        all_features: Optional list of feature dicts/objects for the
            pytest-prefix AC strategy.  Pass None to rely on directory
            convention only.
        workspace_root: Workspace root path (forwarded to sub-module).
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot.
        _update_feature_fn: Callable for DB update — forwarded to sub-module.
        _emit_event_fn: Callable for event emission — forwarded to sub-module.

    Returns:
        A ``(attributable, non_attributable)`` tuple:
        - *attributable*: tests owned by *current_feature_id* that should
          count toward the gate decision.
        - *non_attributable*: tests owned by another feature (or orphaned);
          these have been re-opened / logged by the sub-module already.
    """
    attributable = filter_attributable_failures(
        failing_tests,
        current_feature_id,
        all_features=all_features,
        workspace_root=workspace_root,
        previously_passed_at=previously_passed_at,
        _update_feature_fn=_update_feature_fn,
        _emit_event_fn=_emit_event_fn,
    )
    non_attributable = [t for t in failing_tests if t not in attributable]
    return attributable, non_attributable


def map_test_ownership(features: list[Any]) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map from a feature list.

    Every feature must declare which test files it owns via ``pytest:`` ACs.
    This function scans each feature's ``acceptance_criteria`` for those
    declarations and returns a flat ownership map suitable for passing to
    ``detect_regression``.

    Features that declare no ``pytest:`` ACs contribute nothing to the map —
    they own no tests and MUST NOT be scapegoated for failures in tests they
    never claimed.

    This is the canonical entry point for orchestrator call-sites that need
    to build the ownership map before calling ``detect_regression``.

    Args:
        features: List of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.

    Returns:
        ``{test_path: feature_id}`` ownership map.  Returns an empty dict
        when *features* is empty.

    Raises:
        TypeError: When *features* is None.
        ValueError: When any feature has no ``id`` field.
    """
    if features is None:
        raise TypeError("features must not be None")

    ownership: dict[str, str] = {}
    for feature in features:
        owned_tests = get_feature_owned_tests(feature)
        fid = (
            feature["id"]
            if isinstance(feature, dict)
            else getattr(feature, "id")
        )
        for test_path in owned_tests:
            ownership[test_path] = fid
    return ownership


def attribute_regression_to_feature(
    newly_failing_tests: list[str],
    features: list[Any],
) -> dict[str, dict]:
    """Attribute newly-failing tests to their owning features — no scapegoats.

    This is a high-level convenience that combines ``map_test_ownership`` and
    ``detect_regression`` into a single call.  Every feature MUST declare
    which test files it owns via ``pytest:`` ACs; demotion to ``regression``
    requires evidence that the feature's own tests newly fail.

    The no-scapegoat policy: if a test has no declared owner in *features*,
    it is placed under the ``"unattributed"`` sentinel key — no other feature
    is blamed for it.

    Integration with bob3.orchestrator
    ------------------------------------
    The orchestrator calls this function after the verification checklist
    reports newly-failing tests, replacing the historical heuristic that
    demoted "the first completed feature that isn't the causing feature".

    Args:
        newly_failing_tests: Pytest node-ids that newly fail vs baseline.
        features: All features (dicts or objects with ``id`` and
            ``acceptance_criteria``) that could own the failing tests.

    Returns:
        Dict keyed by feature_id (and possibly ``"unattributed"``).
        Values are ``{"tests": [...], "demote": bool}``.
        Only features with at least one newly-failing owned test appear.

    Raises:
        TypeError: When *newly_failing_tests* or *features* is None, or
            when either is the wrong type.
    """
    if newly_failing_tests is None:
        raise TypeError("newly_failing_tests must not be None")
    if not isinstance(newly_failing_tests, list):
        raise TypeError(
            f"newly_failing_tests must be a list, got {type(newly_failing_tests)!r}"
        )
    if features is None:
        raise TypeError("features must not be None")

    ownership_map = map_test_ownership(features)
    return detect_regression(
        newly_failing_tests=newly_failing_tests,
        test_ownership_map=ownership_map,
    )


def attribute_failure_to_owner(
    test_path: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
) -> str | None:
    """Return the feature_id that owns *test_path*, or None if unknown.

    AC-required alias for :func:`attribute_test_failure_to_owner`.

    The regression-vs-baseline gate calls this to determine which feature
    is responsible for a newly-failing test before deciding whether to
    penalise the currently-verifying feature.

    Args:
        test_path: Pytest node-id or file path to look up.
        all_features: Optional list of feature dicts/objects for the
            pytest-prefix AC ownership strategy.
        workspace_root: Workspace root path (forwarded to sub-module).

    Returns:
        The owning feature_id string, or None when unattributed.

    Raises:
        ValueError: When *test_path* is not a non-empty string.
    """
    return attribute_test_failure_to_owner(
        test_path,
        all_features=all_features,
        workspace_root=workspace_root,
    )


def build_test_owner_map(features: list[Any]) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map from a feature list.

    AC-required alias for :func:`map_test_ownership`.

    Every feature must declare which test files it owns via ``pytest:`` ACs.
    This function scans each feature's ``acceptance_criteria`` for those
    declarations and returns a flat ownership map suitable for the
    regression-vs-baseline attribution gate.

    Features that declare no ``pytest:`` ACs contribute nothing to the map —
    they own no tests and MUST NOT be scapegoated for failures in tests they
    never claimed.

    Args:
        features: List of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.

    Returns:
        ``{test_path: feature_id}`` ownership map.  Returns an empty dict
        when *features* is empty.

    Raises:
        TypeError: When *features* is None.
        ValueError: When any feature has no ``id`` field.
    """
    return map_test_ownership(features)


def build_test_ownership_map(features: list[Any]) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map from a feature list.

    AC-canonical alias for :func:`map_test_ownership`.  This is the name
    required by the feature AC: ``bob3.regression_attribution.build_test_ownership_map``.

    Every feature MUST declare which test files it owns via ``pytest:`` ACs.
    Features with no ``pytest:`` ACs own no tests and MUST NOT be scapegoated.

    Args:
        features: List of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.

    Returns:
        ``{test_path: feature_id}`` ownership map.  Empty dict when
        *features* is empty.

    Raises:
        TypeError: When *features* is None.
        ValueError: When any feature has no ``id`` field.
    """
    return map_test_ownership(features)


def verify_regression_ownership(
    newly_failing_tests: list[str],
    candidate_feature_id: str,
    test_ownership_map: dict[str, str],
) -> bool:
    """Return True only if *candidate_feature_id* owns at least one newly-failing test.

    Enforces the no-scapegoat policy: demotion to ``regression`` is only
    permitted when the feature's own declared tests newly fail.  A feature
    that owns none of the failing tests MUST NOT be demoted.

    Args:
        newly_failing_tests: Pytest node-ids that newly fail vs baseline.
        candidate_feature_id: The feature being considered for regression demotion.
        test_ownership_map: ``{test_nodeid: feature_id}`` ownership map built
            from each feature's ``pytest:`` ACs via :func:`build_test_ownership_map`.

    Returns:
        True when at least one entry in *newly_failing_tests* is owned by
        *candidate_feature_id*.  False otherwise — the feature must not be
        demoted.

    Raises:
        TypeError: When any argument is None or of the wrong type.
        ValueError: When *candidate_feature_id* is an empty string.
    """
    if newly_failing_tests is None:
        raise TypeError("newly_failing_tests must not be None")
    if not isinstance(newly_failing_tests, list):
        raise TypeError(
            f"newly_failing_tests must be a list, got {type(newly_failing_tests)!r}"
        )
    if candidate_feature_id is None:
        raise TypeError("candidate_feature_id must not be None")
    if not isinstance(candidate_feature_id, str):
        raise TypeError(
            f"candidate_feature_id must be a str, got {type(candidate_feature_id)!r}"
        )
    if not candidate_feature_id:
        raise ValueError("candidate_feature_id must not be an empty string")
    if test_ownership_map is None:
        raise TypeError("test_ownership_map must not be None")
    if not isinstance(test_ownership_map, dict):
        raise TypeError(
            f"test_ownership_map must be a dict, got {type(test_ownership_map)!r}"
        )

    return any(
        test_ownership_map.get(test) == candidate_feature_id
        for test in newly_failing_tests
    )
