"""Test-ownership map for bob3 regression attribution.

Feature 11a809ed-95e9-41f9-a0bd-9a6ba9e8337f

Every feature MUST declare which test files it owns via ``pytest:`` acceptance
criteria.  Demotion to ``regression`` MUST require evidence that the feature's
own tests newly fail — no scapegoating innocent features.

This module provides two public functions:

``load_feature_test_ownership``
    Given a list of feature records, scan each feature's ``pytest:`` ACs and
    build a ``{test_path: feature_id}`` map.  Only ``pytest:`` prefixed ACs are
    treated as ownership declarations.  File-level claims (no ``::`` separator)
    cover any test inside that file.

``validate_test_ownership``
    Given an ownership map and a list of candidate test node-ids, validate that
    every node-id can be resolved to an owner.  Returns a summary of owned and
    unowned test paths so the caller can decide whether to proceed with demotion.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "build_ownership_map",
    "build_test_ownership_map",
    "verify_regression_owner",
    "load_feature_test_ownership",
    "validate_test_ownership",
    "declare_owned_tests",
    "declare_test_ownership",
    "load_test_ownership_map",
    "map_test_to_feature_owner",
    "get_test_owners",
]

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
    """Extract test paths from 'pytest:' prefixed acceptance criteria."""
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


def _lookup_owner(test_nodeid: str, ownership_map: dict[str, str]) -> str | None:
    """Return the owning feature_id for *test_nodeid*, or None.

    Supports two claim styles:
    - Exact node-id: ``"tests/test_foo.py::test_bar"``
    - File-level: ``"tests/test_foo.py"`` matches any ``tests/test_foo.py::*``
    """
    owner = ownership_map.get(test_nodeid)
    if owner is not None:
        return owner
    for key, fid in ownership_map.items():
        if "::" not in key and test_nodeid.startswith(key + "::"):
            return fid
    return None


def build_ownership_map(features: list[Any]) -> dict[str, str]:
    """Build a ``{test_file_path: feature_id}`` ownership map.

    Alternative entry point that accepts feature dicts with a ``"test_files"``
    key (list of test file paths) rather than scanning ``pytest:`` ACs.
    Required by the ``regression attribution requires test-ownership map`` AC.

    First-writer wins for duplicate claims.

    Args:
        features: List of feature dicts with ``"id"`` (str) and optional
            ``"test_files"`` (list[str]) keys.  ``"id"`` must be a non-empty
            string; ``"test_files"`` may be absent or empty.

    Returns:
        ``{test_file_path: feature_id}`` — first-writer wins for duplicate claims.

    Raises:
        TypeError: When *features* is None or a feature id is None.
        ValueError: When a feature has an empty or missing id.
        KeyError: When a feature dict lacks the ``"id"`` key.
    """
    if features is None:
        raise TypeError("features must not be None")

    ownership: dict[str, str] = {}
    for feature in features:
        if isinstance(feature, dict):
            fid = feature["id"]  # KeyError if missing
        else:
            fid = getattr(feature, "id", "")

        if fid is None:
            raise TypeError("feature id must not be None")
        if not isinstance(fid, str):
            raise TypeError(f"feature id must be a string, got {type(fid)!r}")
        if not fid:
            raise ValueError("feature id must not be an empty string")

        if isinstance(feature, dict):
            test_files = feature.get("test_files", []) or []
        else:
            test_files = getattr(feature, "test_files", []) or []

        for tf in test_files:
            if tf not in ownership:
                ownership[tf] = fid

    return ownership


def build_test_ownership_map(
    features: list[Any],
) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map from feature records.

    Alias for :func:`load_feature_test_ownership`.  Required by the
    ``regression attribution requires test-ownership map`` feature AC.

    Walks each feature's ``acceptance_criteria`` for ``pytest:`` prefixed
    entries and records the claiming feature as owner of that test path.
    First-writer wins for duplicate claims.

    Args:
        features: Sequence of feature objects or dicts with ``id`` and
            ``acceptance_criteria`` fields.

    Returns:
        ``{test_path: feature_id}`` mapping.

    Raises:
        TypeError: When *features* is None or a feature id is None.
        ValueError: When a feature has an empty or missing id.
    """
    return load_feature_test_ownership(features)


def verify_regression_owner(
    newly_failing_tests: list[str],
    ownership_map: dict[str, str],
    candidate_feature_id: str,
) -> dict[str, Any]:
    """Verify that a candidate feature has evidence to be demoted as a regression.

    A feature may only be demoted to ``regression`` when at least one of
    *newly_failing_tests* is owned by *candidate_feature_id* in
    *ownership_map*.  If there is no such evidence, the feature must NOT be
    demoted — scapegoating is forbidden.

    Args:
        newly_failing_tests: Pytest node-ids that newly fail.  Must be a list;
            may be empty (returns ``{"verdict": "no_evidence", ...}``).
        ownership_map: ``{test_nodeid: feature_id}`` — built by
            :func:`build_test_ownership_map`.  Must be a dict and must not be
            None.
        candidate_feature_id: The feature whose demotion is being considered.
            Must be a non-empty string.

    Returns:
        A dict with keys:
        - ``"verdict"``: ``"demote"`` when at least one owned test newly
          fails; ``"no_evidence"`` otherwise.
        - ``"owned_failing_tests"``: sorted list of newly-failing tests owned
          by *candidate_feature_id*.
        - ``"may_demote"``: bool — True iff ``verdict == "demote"``.

    Raises:
        TypeError: When *newly_failing_tests* is None or not a list;
            *ownership_map* is None or not a dict; *candidate_feature_id* is
            not a string.
        ValueError: When *candidate_feature_id* is an empty string.
    """
    if newly_failing_tests is None:
        raise TypeError("newly_failing_tests must not be None")
    if not isinstance(newly_failing_tests, list):
        raise TypeError(
            f"newly_failing_tests must be a list, got {type(newly_failing_tests)!r}"
        )
    if ownership_map is None:
        raise TypeError("ownership_map must not be None")
    if not isinstance(ownership_map, dict):
        raise TypeError(
            f"ownership_map must be a dict, got {type(ownership_map)!r}"
        )
    if not isinstance(candidate_feature_id, str):
        raise TypeError(
            f"candidate_feature_id must be a str, got {type(candidate_feature_id)!r}"
        )
    if not candidate_feature_id:
        raise ValueError("candidate_feature_id must not be an empty string")

    owned_failing: list[str] = []
    for test in newly_failing_tests:
        owner = _lookup_owner(test, ownership_map)
        if owner == candidate_feature_id:
            owned_failing.append(test)

    owned_failing.sort()
    may_demote = len(owned_failing) > 0
    verdict = "demote" if may_demote else "no_evidence"

    return {
        "verdict": verdict,
        "owned_failing_tests": owned_failing,
        "may_demote": may_demote,
    }


def load_feature_test_ownership(
    features: list[Any],
) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map from feature records.

    Walks each feature's ``acceptance_criteria`` for ``pytest:`` prefixed
    entries and records the claiming feature as owner of that test path.
    Only ``pytest:`` ACs are treated as ownership declarations.  File-level
    claims (no ``::`` separator) cover any test inside that file.

    First-writer wins for duplicate claims — the first feature to claim a
    test path is considered its owner.

    Args:
        features: Sequence of feature objects or dicts.  Each must expose
            ``id`` and ``acceptance_criteria`` (via attribute or dict key).

    Returns:
        ``{test_path: feature_id}`` — first-writer wins for duplicate claims.

    Raises:
        TypeError: When *features* is None, or when a feature id is None.
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


def validate_test_ownership(
    test_node_ids: list[str],
    ownership_map: dict[str, str],
) -> dict[str, Any]:
    """Validate that test node-ids can be resolved to owners in *ownership_map*.

    For each test in *test_node_ids*, attempts to find its owner using
    exact-match and file-level prefix matching.  Returns a summary dict
    distinguishing owned tests (safe to demote their owner) from unowned
    tests (which must never trigger scapegoating).

    Args:
        test_node_ids: Pytest node-ids to validate.  Must be a list; may be
            empty (returns well-defined empty result rather than raising).
        ownership_map: ``{test_path: feature_id}`` — built by
            ``load_feature_test_ownership`` or equivalent.  Must be a dict;
            must not be None.

    Returns:
        A dict with keys:
        - ``"owned"``: ``{test_nodeid: feature_id}`` for tests with an owner.
        - ``"unowned"``: list of test node-ids that have no owner entry.
        - ``"all_owned"``: bool — True iff every test has an owner.

    Raises:
        TypeError: When *test_node_ids* is None, not a list, *ownership_map*
            is None, or not a dict.
        ValueError: When *ownership_map* contains an entry with an empty
            feature_id value.
    """
    if test_node_ids is None:
        raise TypeError("test_node_ids must not be None")
    if not isinstance(test_node_ids, list):
        raise TypeError(
            f"test_node_ids must be a list, got {type(test_node_ids)!r}"
        )
    if ownership_map is None:
        raise TypeError("ownership_map must not be None")
    if not isinstance(ownership_map, dict):
        raise TypeError(
            f"ownership_map must be a dict, got {type(ownership_map)!r}"
        )

    for key, fid in ownership_map.items():
        if fid is not None and not isinstance(fid, str):
            raise TypeError(
                f"ownership_map values must be strings, got {type(fid)!r} for key {key!r}"
            )
        if isinstance(fid, str) and not fid:
            raise ValueError(
                f"ownership_map contains empty feature_id for test path {key!r}"
            )

    owned: dict[str, str] = {}
    unowned: list[str] = []

    for test in test_node_ids:
        owner = _lookup_owner(test, ownership_map)
        if owner is not None:
            owned[test] = owner
        else:
            unowned.append(test)

    return {
        "owned": owned,
        "unowned": unowned,
        "all_owned": len(unowned) == 0,
    }


def declare_test_ownership(
    *,
    feature_id: str,
    test_files: list[str] | None,
) -> dict[str, list[str]]:
    """Declare that *feature_id* owns the given *test_files*.

    Every feature MUST declare which test files it owns.  This function
    registers that ownership so regression detection can require evidence
    before demoting a feature (no scapegoating).

    Args:
        feature_id: Non-empty string identifying the feature.
        test_files: List of test file paths the feature owns.  May be empty
            but must not be None.

    Returns:
        ``{feature_id: [test_file, ...]}`` — a dict mapping the feature to
        its declared test files.

    Raises:
        ValueError: When *feature_id* is an empty string.
        TypeError: When *feature_id* is None or not a string, or when
            *test_files* is None or not a list.
    """
    if feature_id is None:
        raise TypeError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a string, got {type(feature_id)!r}")
    if not feature_id:
        raise ValueError("feature_id must not be an empty string")
    if test_files is None:
        raise TypeError("test_files must not be None")
    if not isinstance(test_files, list):
        raise TypeError(f"test_files must be a list, got {type(test_files)!r}")

    for tf in test_files:
        if not isinstance(tf, str):
            raise TypeError(f"Each test file must be a string, got {type(tf)!r}")

    return {feature_id: list(test_files)}


def declare_owned_tests(
    *,
    feature_id: str,
    test_files: list[str] | None,
) -> dict[str, list[str]]:
    """Declare that *feature_id* owns the given *test_files*.

    Alias for :func:`declare_test_ownership`.  Required by the
    ``regression attribution requires test-ownership map`` AC:
    ``Function defined: bob3.test_ownership_map.declare_owned_tests``.

    Every feature MUST declare which test files it owns so regression
    detection can require evidence before demoting a feature (no scapegoating).

    Args:
        feature_id: Non-empty string identifying the feature.
        test_files: List of test file paths the feature owns.  May be empty
            but must not be None.

    Returns:
        ``{feature_id: [test_file, ...]}`` — a dict mapping the feature to
        its declared test files.

    Raises:
        ValueError: When *feature_id* is an empty string.
        TypeError: When *feature_id* is None or not a string, or when
            *test_files* is None or not a list.
    """
    return declare_test_ownership(feature_id=feature_id, test_files=test_files)


def load_test_ownership_map(
    features: list[Any],
) -> dict[str, str]:
    """Build a ``{test_path: feature_id}`` ownership map from feature records.

    Canonical entry point for the ``regression attribution requires
    test-ownership map`` feature AC.  Delegates to
    :func:`load_feature_test_ownership`.

    Args:
        features: Sequence of feature objects or dicts.  Each must expose
            ``id`` and ``acceptance_criteria`` (via attribute or dict key).

    Returns:
        ``{test_path: feature_id}`` — first-writer wins for duplicate claims.

    Raises:
        TypeError: When *features* is None, or when a feature id is None.
        ValueError: When a feature has an empty or missing id.
    """
    return load_feature_test_ownership(features)


def map_test_to_feature_owner(
    test_nodeid: str,
    ownership_map: dict[str, str],
) -> str | None:
    """Return the feature_id that owns *test_nodeid*, or None.

    Supports two claim styles:
    - Exact node-id: ``"tests/test_foo.py::test_bar"`` matches exactly.
    - File-level: ``"tests/test_foo.py"`` matches any ``tests/test_foo.py::*``.

    When no owner can be found, returns ``None`` — the caller must not
    scapegoat any feature for unowned tests.

    Args:
        test_nodeid: A pytest node-id to look up.  Must be a non-empty string.
        ownership_map: ``{test_path: feature_id}`` — built by
            :func:`load_test_ownership_map`.  Must be a dict; must not be None.

    Returns:
        The owning ``feature_id`` string, or ``None`` when no owner is found.

    Raises:
        TypeError: When *test_nodeid* is not a string, or *ownership_map* is
            not a dict or is None.
        ValueError: When *test_nodeid* is an empty string.
    """
    if not isinstance(test_nodeid, str):
        raise TypeError(
            f"test_nodeid must be a string, got {type(test_nodeid)!r}"
        )
    if not test_nodeid:
        raise ValueError("test_nodeid must not be an empty string")
    if ownership_map is None:
        raise TypeError("ownership_map must not be None")
    if not isinstance(ownership_map, dict):
        raise TypeError(
            f"ownership_map must be a dict, got {type(ownership_map)!r}"
        )

    return _lookup_owner(test_nodeid, ownership_map)


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
        TypeError: When *test_path* is None or not a string.
        ValueError: When *test_path* is an empty or whitespace-only string.
    """
    if test_path is None:
        raise TypeError("test_path must not be None")
    if not isinstance(test_path, str):
        raise TypeError(f"test_path must be a string, got {type(test_path)!r}")
    if not test_path.strip():
        raise ValueError("test_path must not be an empty or whitespace-only string")

    ownership_map = load_feature_test_ownership(all_features or [])
    return _lookup_owner(test_path, ownership_map)
