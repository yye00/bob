"""Test-ownership registry for bob3 regression attribution.

Feature 9f8b7756-d6fd-4550-8876-376c8c691e06

Every feature MUST declare which test files it owns.  Demotion to
``regression`` MUST require evidence that the feature's own tests newly fail —
no scapegoating an arbitrary completed feature when tests cannot be mapped to
an owner.

This module provides two public functions:

``declare_test_ownership``
    Record that a feature owns a list of test files.  Returns a
    ``{feature_id: [test_file, ...]}`` declaration dict.

``get_owning_feature``
    Given an ownership map (built from declarations) and a test node-id,
    return the feature_id that owns that test, or ``None`` when no feature
    claims it.  Supports both exact node-id matches and file-level prefix
    matches (a claim on ``"tests/test_foo.py"`` covers any
    ``"tests/test_foo.py::test_*"`` node-id).
"""

from __future__ import annotations

__all__ = [
    "declare_test_ownership",
    "get_owning_feature",
]


def declare_test_ownership(
    *,
    feature_id: str,
    test_files: list[str] | None,
) -> dict[str, list[str]]:
    """Declare that *feature_id* owns the given *test_files*.

    Every feature MUST call this to register its test ownership so that the
    regression detection logic can require evidence before demoting a feature
    (no scapegoating).

    Args:
        feature_id: Non-empty string identifying the feature.
        test_files: List of test file paths the feature owns.  May be empty
            but must not be None.

    Returns:
        ``{feature_id: [test_file, ...]}`` — a dict mapping the feature to
        its declared test files.

    Raises:
        TypeError: When *feature_id* is None or not a string, or when
            *test_files* is None or not a list, or when any element of
            *test_files* is not a string.
        ValueError: When *feature_id* is an empty string.
    """
    if feature_id is None:
        raise TypeError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(
            f"feature_id must be a string, got {type(feature_id)!r}"
        )
    if not feature_id:
        raise ValueError("feature_id must not be an empty string")
    if test_files is None:
        raise TypeError("test_files must not be None")
    if not isinstance(test_files, list):
        raise TypeError(
            f"test_files must be a list, got {type(test_files)!r}"
        )
    for tf in test_files:
        if not isinstance(tf, str):
            raise TypeError(
                f"Each test file must be a string, got {type(tf)!r}"
            )

    return {feature_id: list(test_files)}


def get_owning_feature(
    test_nodeid: str,
    ownership_map: dict[str, str],
) -> str | None:
    """Return the feature_id that owns *test_nodeid*, or ``None``.

    Looks up *test_nodeid* in *ownership_map* using two strategies:

    1. **Exact match** — the node-id appears verbatim as a key.
    2. **File-level prefix match** — a key without ``::`` matches any node-id
       whose file component is that key (e.g. key ``"tests/test_foo.py"``
       matches ``"tests/test_foo.py::TestClass::test_method"``).

    When multiple keys would match via prefix, the first matching key wins
    (iteration order of *ownership_map*).

    Args:
        test_nodeid: Pytest node-id string, e.g.
            ``"tests/test_foo.py::test_bar"`` or just ``"tests/test_foo.py"``.
        ownership_map: ``{test_path_or_nodeid: feature_id}`` — built by
            accumulating :func:`declare_test_ownership` declarations.

    Returns:
        The ``feature_id`` string for the owning feature, or ``None`` when no
        feature declares ownership of *test_nodeid*.

    Raises:
        TypeError: When *test_nodeid* is None or not a string, or when
            *ownership_map* is None or not a dict.
        ValueError: When *test_nodeid* is an empty string.
    """
    if test_nodeid is None:
        raise TypeError("test_nodeid must not be None")
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

    # 1. Exact match
    if test_nodeid in ownership_map:
        return ownership_map[test_nodeid]

    # 2. File-level prefix match: key has no '::' and test_nodeid starts with key + '::'
    for key, feature_id in ownership_map.items():
        if "::" not in key and test_nodeid.startswith(key + "::"):
            return feature_id

    return None
