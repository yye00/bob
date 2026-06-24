"""Regression attribution utilities for the bob package.

Feature 7bf35555-77ae-4e85-9a11-a753dc0bc599

Provides:
- ``declare_test_ownership``: register which test files a feature owns.
- ``detect_regression``: given newly-failing tests and an ownership map,
  return which features should be demoted — only those whose own tests fail.

No feature is ever demoted without evidence that its own tests newly fail
(no scapegoating).  Tests with no owner entry in the map are filed under
the ``"unattributed"`` sentinel key and no other feature is blamed for them.
"""

from __future__ import annotations

__all__ = [
    "declare_test_ownership",
    "detect_regression",
    "UNATTRIBUTED_KEY",
]

UNATTRIBUTED_KEY = "unattributed"


def declare_test_ownership(
    *,
    feature_id: str,
    test_files: list[str] | None,
) -> dict[str, list[str]]:
    """Declare that *feature_id* owns the given *test_files*.

    Args:
        feature_id: Non-empty string identifying the feature.
        test_files: List of test file paths the feature owns.  May be empty
            but must not be None.

    Returns:
        ``{feature_id: [test_file, ...]}`` — a dict mapping the feature to
        its declared test files.

    Raises:
        ValueError: When *feature_id* is an empty string.
        TypeError: When *feature_id* is None or *test_files* is None.
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

    # Validate each entry is a string
    for tf in test_files:
        if not isinstance(tf, str):
            raise TypeError(f"Each test file must be a string, got {type(tf)!r}")

    return {feature_id: list(test_files)}


def detect_regression(
    *,
    newly_failing_tests: list[str],
    test_ownership_map: dict[str, str],
) -> dict[str, dict]:
    """Attribute newly-failing tests to their owning features — no scapegoats.

    For each test in *newly_failing_tests*:
    - If the test appears in *test_ownership_map*, it is attributed to the
      owning feature and that feature is marked for demotion.
    - If the test has no entry in *test_ownership_map*, it is placed under
      the ``"unattributed"`` sentinel key.  No other feature is blamed.

    A feature is demoted (``"demote": True``) ONLY when at least one of its
    own tests appears in *newly_failing_tests*.

    Args:
        newly_failing_tests: Pytest node-ids that newly fail.
        test_ownership_map: ``{test_nodeid: feature_id}`` ownership map.

    Returns:
        Dict keyed by feature_id (and possibly ``"unattributed"``).  Values::

            {"tests": [...], "demote": bool}

        Only features with at least one newly-failing owned test are present.
        The ``"unattributed"`` key is present only when unowned tests exist.

    Raises:
        TypeError: When *newly_failing_tests* is None or *test_ownership_map*
            is None, or when either is the wrong type.
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
