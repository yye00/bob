"""Regression attribution requires test-ownership map (no scapegoats).

Feature f131cf75-2655-467d-af4e-0761bb0412fc

Problem solved
--------------
``detect_regression`` previously picked "the first completed feature that
isn't the causing feature" as the blame target when newly-failing tests
could not be mapped to an owner.  This is scapegoating: a feature is demoted
to ``regression`` without any evidence that its own tests newly fail.

This module enforces that:
1. Every feature MUST declare which test files it owns (via ``pytest:`` ACs).
2. Demotion to ``regression`` MUST be supported by evidence that the
   feature's own tests newly fail in the after-snapshot.

Public API
----------
``regression_attribution_requires_test_ownership_map_no_scapegoats``
    Top-level entry point.  Given the full set of newly-failing tests and a
    test-ownership map (``{test_nodeid: feature_id}``), returns a
    ``RegressionAttributionResult`` — a dict keyed by feature_id whose values
    are ``{"tests": [...], "demote": bool}``.

    A feature is included in the result ONLY if at least one of the
    newly-failing tests is owned by that feature (i.e. evidence exists).
    Features with no ownership entry in the map are never scapegoated; their
    tests are collected under the ``"unattributed"`` sentinel key instead.

``build_test_ownership_map``
    Convenience builder: given a list of feature dicts (each with ``id`` and
    ``acceptance_criteria`` JSON), returns ``{test_nodeid: feature_id}`` by
    scanning each feature's ``pytest:`` acceptance criteria lines.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = [
    "regression_attribution_requires_test_ownership_map_no_scapegoats",
    "build_test_ownership_map",
    "RegressionAttributionResult",
]

# Sentinel key used for tests that have no owner in the ownership map.
UNATTRIBUTED_KEY = "unattributed"

# Type alias for the result dict.
RegressionAttributionResult = dict[str, dict]

# Regex that extracts a pytest node-id from an AC line like:
#   "pytest: tests/test_foo.py::test_bar"
_PYTEST_AC_RE = re.compile(r"^\s*pytest\s*:\s*(.+)$", re.IGNORECASE)


def build_test_ownership_map(all_features: list[Any]) -> dict[str, str]:
    """Build a ``{test_nodeid: feature_id}`` map from feature AC declarations.

    Scans each feature's ``acceptance_criteria`` (JSON-encoded list of
    strings) for lines of the form ``pytest: <node_id>`` and maps the
    extracted node-id to the owning feature's ``id``.

    Args:
        all_features: Iterable of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.  ``acceptance_criteria`` may be a
            JSON-encoded string or an already-decoded list.

    Returns:
        Mapping from pytest test node-id to the feature_id that owns it.
        When the same node-id is claimed by multiple features, the last
        writer wins (implementation-defined; in practice IDs are unique).
    """
    ownership: dict[str, str] = {}
    for feature in all_features:
        fid = feature["id"] if isinstance(feature, dict) else feature.id
        raw_acs = (
            feature["acceptance_criteria"]
            if isinstance(feature, dict)
            else feature.acceptance_criteria
        )
        if isinstance(raw_acs, str):
            try:
                acs = json.loads(raw_acs)
            except (json.JSONDecodeError, TypeError):
                continue
        else:
            acs = list(raw_acs)

        for ac in acs:
            m = _PYTEST_AC_RE.match(ac)
            if m:
                node_id = m.group(1).strip()
                ownership[node_id] = fid

    return ownership


def regression_attribution_requires_test_ownership_map_no_scapegoats(
    *,
    newly_failing_tests: list[str],
    test_ownership_map: dict[str, str],
) -> RegressionAttributionResult:
    """Attribute newly-failing tests to their owning features — no scapegoats.

    For each test in *newly_failing_tests*:
    - If the test appears in *test_ownership_map*, it is attributed to the
      owning feature and that feature is marked for demotion.
    - If the test has no entry in *test_ownership_map*, it is placed under
      the ``"unattributed"`` sentinel key.  No other feature is blamed for it.

    A feature is demoted (``"demote": True``) ONLY when at least one of its
    own tests appears in *newly_failing_tests*.  Features that are merely
    "nearby" or "completed before the regression" are never scapegoated.

    Args:
        newly_failing_tests: Pytest node-ids that newly fail (i.e. passed
            before the causative change and fail after).
        test_ownership_map: ``{test_nodeid: feature_id}`` — built from the
            ``pytest:`` ACs of all known features.  Features absent from this
            map own no declared tests and cannot be blamed.

    Returns:
        A ``RegressionAttributionResult`` dict.  Keys are feature_ids
        (including the ``"unattributed"`` sentinel); values are::

            {
                "tests": [<test_nodeid>, ...],   # sorted list
                "demote": bool,                  # True iff this feature should
                                                 # be demoted to "regression"
            }

        Only features with at least one newly-failing owned test are present.
        The ``"unattributed"`` key is present only when unowned tests exist.
    """
    result: RegressionAttributionResult = {}

    for test in newly_failing_tests:
        owner = test_ownership_map.get(test)
        if owner is None:
            # No owner — collect under sentinel; never scapegoat another feature.
            bucket = result.setdefault(UNATTRIBUTED_KEY, {"tests": [], "demote": False})
            bucket["tests"].append(test)
        else:
            bucket = result.setdefault(owner, {"tests": [], "demote": True})
            bucket["tests"].append(test)

    # Sort test lists for deterministic output.
    for bucket in result.values():
        bucket["tests"].sort()

    return result
