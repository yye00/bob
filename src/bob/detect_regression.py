"""Top-level bob.detect_regression module.

Feature 9d81f623-6e65-48c7-a0af-816db1bfebc9
Integration a166a32e-d5b9-436a-938e-243319f03245

Provides:
- ``get_feature_owned_tests``: extract test node-ids a feature declares ownership of.
- ``blame_by_test_ownership``: attribute newly-failing tests to their owners;
  never scapegoat a feature for tests it never claimed.
- ``detect_regression_with_evidence``: evidence-gated regression detection —
  no demotion without a causal ownership link (re-exported from
  bob.regression.ownership_detector).
- ``has_ownership_evidence``: check causal link for a candidate feature
  (re-exported from bob.regression.ownership_detector).

The regression-treadmill fix enforced here: demotion to ``regression`` requires
evidence that the feature's OWN tests newly fail.  Tests with no declared owner
are placed under the ``"unattributed"`` sentinel key; no completed feature is
blamed for them.
"""

from __future__ import annotations

from typing import Any

from bob.regression_attribution import (
    detect_regression as _detect_regression,
    get_feature_owned_tests,
)
from bob.regression.ownership_detector import (  # noqa: F401 — integration a166a32e
    has_ownership_evidence,
    detect_regression_with_evidence,
)
from bob.regression_ownership import (  # noqa: F401 — integration c68b3042
    validate_ownership_link,
    detect_regression_with_evidence as _detect_regression_with_evidence_ownership,
)
from bob.ownership_evidenced_regression import (  # noqa: F401 — integration 50afa15a
    detect_regression_with_ownership,
    file_touched_in_commit,
)
from regression_attribution.detect_regression import (  # noqa: F401 — feature eb9e8e9b
    require_test_ownership_evidence,
)

__all__ = [
    "get_feature_owned_tests",
    "blame_by_test_ownership",
    "has_ownership_evidence",
    "detect_regression_with_evidence",
    "detect_regression_with_ownership",
    "file_touched_in_commit",
    "require_feature_test_ownership",
    "require_owned_tests",
    "require_test_ownership_evidence",
]

UNATTRIBUTED_KEY = "unattributed"


def blame_by_test_ownership(
    newly_failing_tests: list[str],
    test_ownership_map: dict[str, str],
) -> dict[str, dict]:
    """Attribute newly-failing tests to their owning features — no scapegoats.

    For each test in *newly_failing_tests*:
    - If the test appears in *test_ownership_map*, it is attributed to the
      owning feature and that feature is marked for demotion (``demote=True``).
    - If no owner entry exists, the test is placed under the
      ``"unattributed"`` sentinel key; no other feature is blamed.

    A feature is demoted ONLY when at least one of its own declared tests
    appears in *newly_failing_tests*.  This prevents scapegoating — the
    historical bug where "the first completed feature that isn't the causing
    feature" was blindly charged for tests it never claimed.

    Args:
        newly_failing_tests: Pytest node-ids that newly fail vs baseline.
        test_ownership_map: ``{test_nodeid: feature_id}`` map, typically
            built by scanning each feature's ``pytest:`` acceptance criteria.

    Returns:
        Dict keyed by feature_id (and possibly ``"unattributed"``).
        Values are ``{"tests": [sorted list], "demote": bool}``.
        Only features with at least one newly-failing owned test are present.
        The ``"unattributed"`` key is present only when unowned tests exist.

    Raises:
        TypeError: When *newly_failing_tests* is None, not a list,
            *test_ownership_map* is None, or not a dict.
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


def require_feature_test_ownership(
    feature_id: str,
    newly_failing_tests: list[str],
    test_ownership_map: dict[str, str],
) -> bool:
    """Return True only when *feature_id* owns at least one newly-failing test.

    Enforces the no-scapegoat rule: a feature may be demoted to ``regression``
    ONLY when there is evidence that its own declared tests newly fail.  A
    feature with no ownership entry in *test_ownership_map* for any of the
    newly-failing tests is NOT blamed — it returns False, blocking demotion.

    Args:
        feature_id: Non-empty string identifying the candidate feature.
        newly_failing_tests: List of pytest node-ids that newly fail vs baseline.
        test_ownership_map: ``{test_nodeid: owning_feature_id}`` map.

    Returns:
        ``True`` if at least one test in *newly_failing_tests* is owned by
        *feature_id*; ``False`` otherwise.

    Raises:
        ValueError: When *feature_id* is empty.
        TypeError: When *feature_id* is None/not-a-str, *newly_failing_tests*
            is None/not-a-list, or *test_ownership_map* is None/not-a-dict.
    """
    if feature_id is None:
        raise TypeError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a string, got {type(feature_id)!r}")
    if not feature_id:
        raise ValueError("feature_id must not be an empty string")
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

    return any(
        test_ownership_map.get(test) == feature_id
        for test in newly_failing_tests
    )


def require_owned_tests(
    *,
    feature_id: str,
    newly_failing_tests: list[str],
    test_ownership_map: dict[str, str],
) -> dict:
    """Verify ownership evidence is required before allowing regression demotion.

    A feature may be demoted to ``regression`` ONLY when at least one of
    *newly_failing_tests* is owned by *feature_id* in *test_ownership_map*.
    If no such evidence exists, demotion is refused (no scapegoating).

    This function enforces the contract from feature 48b78cae: every feature
    MUST declare which test files it owns, and demotion MUST require evidence
    that the feature's own tests newly fail.

    Args:
        feature_id: Non-empty string identifying the candidate feature.
        newly_failing_tests: List of pytest node-ids that newly fail vs baseline.
        test_ownership_map: ``{test_nodeid: owning_feature_id}`` map.

    Returns:
        A dict with keys:
        - ``"may_demote"``: bool — True only when owned failing tests exist.
        - ``"owned_failing_tests"``: list[str] — the subset of newly_failing_tests
          owned by this feature.
        - ``"evidence"``: list[str] — human-readable evidence strings.

    Raises:
        ValueError: When *feature_id* is an empty string.
        TypeError: When *feature_id* is None/not-a-str, *newly_failing_tests*
            is None/not-a-list, or *test_ownership_map* is None/not-a-dict.
    """
    if feature_id is None:
        raise TypeError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a string, got {type(feature_id)!r}")
    if not feature_id:
        raise ValueError("feature_id must not be an empty string")
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

    owned_failing: list[str] = [
        test for test in newly_failing_tests
        if test_ownership_map.get(test) == feature_id
    ]
    may_demote = len(owned_failing) > 0
    evidence: list[str] = [
        f"test {t!r} is owned by feature {feature_id!r} and newly fails"
        for t in owned_failing
    ]
    return {
        "may_demote": may_demote,
        "owned_failing_tests": owned_failing,
        "evidence": evidence,
    }
