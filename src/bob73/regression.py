"""Regression attribution utilities for bob73 — test-ownership-map based.

Feature 2eb6aea0-6576-40cd-a98a-886dae844cd3

Provides:
- ``get_test_ownership_map``: build a {test_nodeid: feature_id} map from
  features whose pytest: ACs declare test ownership.
- ``detect_regression``: given newly-failing tests and an ownership map,
  return which features should be demoted — only those whose own tests fail.

No feature is ever demoted without evidence that its own tests newly fail
(no scapegoating).  Tests with no owner entry in the map are filed under
the ``"unattributed"`` sentinel key and no other feature is blamed.
"""

from __future__ import annotations

import json

__all__ = [
    "get_test_ownership_map",
    "detect_regression",
    "UNATTRIBUTED_KEY",
]

UNATTRIBUTED_KEY = "unattributed"


def _parse_ac_list(acceptance_criteria) -> list[str]:
    """Parse acceptance_criteria into a list of strings."""
    if isinstance(acceptance_criteria, list):
        return [str(ac) for ac in acceptance_criteria]
    if isinstance(acceptance_criteria, str):
        try:
            parsed = json.loads(acceptance_criteria)
            if isinstance(parsed, list):
                return [str(ac) for ac in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
        # plain text: treat each line as an AC
        return [line.strip() for line in acceptance_criteria.splitlines() if line.strip()]
    return []


def get_test_ownership_map(features) -> dict[str, str]:
    """Build a ``{test_nodeid: feature_id}`` ownership map from feature ACs.

    Scans the ``acceptance_criteria`` of each feature for ``pytest:`` prefixed
    entries.  Each such entry declares that the feature owns the referenced
    test file or node-id.

    Args:
        features: Iterable of feature objects.  Each item must have an ``id``
            attribute (or key) and an ``acceptance_criteria`` attribute (or
            key) that is either a JSON-encoded list or a plain string list.

    Returns:
        ``{test_nodeid_or_file: feature_id}`` mapping.  Features with no
        pytest: ACs contribute nothing.

    Raises:
        TypeError: When *features* is None.
    """
    if features is None:
        raise TypeError("features must not be None")

    ownership: dict[str, str] = {}

    for feature in features:
        # Support both dict-like and attribute-based access
        if hasattr(feature, "id"):
            fid = feature.id
            raw_ac = getattr(feature, "acceptance_criteria", "[]")
        else:
            fid = feature["id"]
            raw_ac = feature.get("acceptance_criteria", "[]")

        ac_list = _parse_ac_list(raw_ac)
        for ac in ac_list:
            stripped = ac.strip()
            if stripped.lower().startswith("pytest:"):
                test_path = stripped[len("pytest:"):].strip()
                # Strip trailing descriptions after " — " or " -- "
                for sep in (" — ", " -- "):
                    if sep in test_path:
                        test_path = test_path.split(sep)[0].strip()
                if test_path:
                    ownership[test_path] = fid

    return ownership


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
