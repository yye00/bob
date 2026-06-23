"""Regression detection with test-ownership attribution.

Separates newly-failing tests into attributed (owned by a specific feature)
and unattributed (not in the test_to_feature_map) buckets.  Only attributed
failures may demote a completed feature to 'regression'; unattributed failures
are stored in the unattributed_failures table instead.

All status→regression transitions go through
``bob3.orchestrator.regression_attribution.demote_with_evidence`` to enforce
the evidence threshold and self-blame guard.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from bob3.models import RegressionEvent


def _record_unattributed_failures_impl(
    *,
    project_id: str,
    causing_feature_id: str,
    test_names: list[str],
    connect_fn,
) -> None:
    """Persist unmapped failures to unattributed_failures table."""
    now = datetime.now().isoformat()
    with connect_fn() as conn:
        conn.executemany(
            """INSERT INTO unattributed_failures
               (id, project_id, causing_feature_id, test_name, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (str(uuid.uuid4()), project_id, causing_feature_id, t, now)
                for t in test_names
            ],
        )


def detect_regression(
    *,
    project_id: str,
    causing_feature_id: str,
    before_results: dict[str, bool],
    after_results: dict[str, bool],
    test_to_feature_map: dict[str, str],
    _connect_fn=None,
    _create_regression_event_fn=None,
    _update_feature_fn=None,
    _record_unattributed_fn=None,
) -> RegressionEvent | None:
    """Detect regressions by comparing test results before and after a feature.

    Compares before_results and after_results to find tests that were passing
    before but started failing after the causing feature was implemented.
    Only tests present in both result sets are compared (new tests are ignored).

    Attribution rules (regression-treadmill fix):
    - Only features listed in test_to_feature_map may be blamed.
    - Newly-failing tests NOT in test_to_feature_map are stored in the
      unattributed_failures table instead of being charged to a random feature.
    - A completed feature is NEVER demoted to regression unless the failing tests
      are explicitly mapped to it in test_to_feature_map.

    Args:
        project_id: ID of the project.
        causing_feature_id: ID of the feature that was just implemented.
        before_results: Dict mapping test name -> pass/fail before the feature.
        after_results: Dict mapping test name -> pass/fail after the feature.
        test_to_feature_map: Dict mapping test name -> feature_id (owner).
            Tests absent from this map are recorded as unattributed failures,
            NOT blamed on an arbitrary feature.

    Returns:
        RegressionEvent if attributable regressions were detected, None otherwise.

    Raises:
        TypeError: If test_to_feature_map is not provided.
    """
    # Inject real db functions by default (allow override for testing)
    if _connect_fn is None or _create_regression_event_fn is None or _update_feature_fn is None or _record_unattributed_fn is None:
        from bob3 import db as _db
        if _connect_fn is None:
            _connect_fn = _db.connect
        if _create_regression_event_fn is None:
            _create_regression_event_fn = _db.create_regression_event
        if _update_feature_fn is None:
            _update_feature_fn = _db.update_feature
        if _record_unattributed_fn is None:
            _record_unattributed_fn = _db._record_unattributed_failures

    # Find tests that were passing before but now fail
    newly_failing = []
    for test_name, before_passed in before_results.items():
        if not before_passed:
            continue  # Was already failing, not a regression
        if test_name not in after_results:
            continue  # Test no longer exists, skip
        if not after_results[test_name]:
            newly_failing.append(test_name)

    if not newly_failing:
        return None

    # Split into attributed vs unattributed
    attributed: dict[str, str] = {}   # test_name -> feature_id
    unattributed: list[str] = []

    for t in newly_failing:
        owner = test_to_feature_map.get(t)
        if owner is not None:
            attributed[t] = owner
        else:
            unattributed.append(t)

    # Store unattributed failures — never scapegoat a random feature
    if unattributed:
        _record_unattributed_fn(
            project_id=project_id,
            causing_feature_id=causing_feature_id,
            test_names=unattributed,
        )

    if not attributed:
        return None

    # Determine affected feature from attribution map (pick one; log all owners)
    affected_feature_id = next(iter(attributed.values()))
    attributed_tests = sorted(attributed.keys())

    # Create the regression event
    event = _create_regression_event_fn(
        project_id=project_id,
        affected_feature_id=affected_feature_id,
        causing_feature_id=causing_feature_id,
        affected_tests=json.dumps(attributed_tests),
    )

    # Demote the affected feature through the evidenced path — never bare-heuristic
    if affected_feature_id != causing_feature_id:
        from bob3.orchestrator.regression_attribution import demote_with_evidence  # lazy to avoid circular import
        failing_test_id = attributed_tests[0] if attributed_tests else ""
        evidence = [f"test {t!r} newly failing after {causing_feature_id}" for t in attributed_tests]
        demote_with_evidence(
            feature_id=affected_feature_id,
            evidence=evidence,
            confidence=1.0,  # test-ownership map is authoritative evidence
            failing_test_id=failing_test_id,
            recent_commits=[{"commit_id": causing_feature_id, "files_touched": []}],
            _update_feature_fn=lambda fid, status: _update_feature_fn(fid, status=status),
            _emit_event_fn=lambda event_type, **kwargs: None,
        )

    return event
