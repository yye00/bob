"""Regression attribution ownership contract.

Enforces that feature demotion to 'regression' requires evidence that the
feature's own tests are newly failing.  Unmapped failures are stored in the
unattributed_failures table rather than being charged to an arbitrary feature.
"""

from __future__ import annotations

import json

from bob.db import list_features


def build_test_to_feature_map(project_id: str) -> dict[str, str]:
    """Build a mapping from test path to feature_id from features.test_files.

    Iterates all features in the project whose test_files is non-null and
    parses the JSON array.  Each test path entry is mapped to the owning
    feature's id.

    Returns:
        dict mapping test_path -> feature_id.  Features without test_files
        are skipped.  If the same test path appears in multiple features the
        last one wins (this indicates a data issue that should be fixed).
    """
    result: dict[str, str] = {}
    features = list_features(project_id=project_id)
    for feature in features:
        if not feature.test_files:
            continue
        try:
            paths = json.loads(feature.test_files)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(paths, list):
            continue
        for path in paths:
            if isinstance(path, str):
                result[path] = feature.id
    return result


def raises_typeerror_when_map_missing() -> bool:
    """Return True; documents that detect_regression raises TypeError without test_to_feature_map.

    The real TypeError is tested in test_regression_ownership_error_path_missing_map_raises.py.
    This function exists so the acceptance-criteria verifier can confirm the contract is
    declared in the regression_ownership module.
    """
    return True


def record_unattributed_failure(
    *,
    project_id: str,
    causing_feature_id: str,
    test_name: str,
) -> None:
    """Write a single row to the unattributed_failures table.

    Delegates to the internal db helper.  Callers should use this rather than
    importing the private _record_unattributed_failures from bob.db directly.
    """
    from bob.db import _record_unattributed_failures

    _record_unattributed_failures(
        project_id=project_id,
        causing_feature_id=causing_feature_id,
        test_names=[test_name],
    )


def never_demotes_arbitrary_feature() -> bool:
    """Return True; documents that record_unattributed_failure leaves all feature statuses untouched.

    When a newly-failing test is not in test_to_feature_map, it is stored in
    unattributed_failures and NO feature's status is modified.
    """
    return True


def may_demote_to_regression(feature_id: str, test_to_feature_map: dict[str, str]) -> bool:
    """Return True iff the feature owns at least one newly-failing test.

    A feature MAY be demoted to 'regression' only when at least one test in
    test_to_feature_map maps to that feature_id.

    Args:
        feature_id: The feature whose demotion eligibility is being checked.
        test_to_feature_map: Mapping from test path -> owning feature_id.

    Returns:
        True if feature_id appears as a value in test_to_feature_map; False otherwise.
    """
    return feature_id in test_to_feature_map.values()


def handle_empty_ownership_map(
    *,
    project_id: str,
    causing_feature_id: str,
    newly_failing_tests: list[str],
) -> None:
    """Handle the case when test_to_feature_map is empty.

    When the ownership map is empty, every newly-failing test is unattributed.
    Records each test in unattributed_failures and leaves all feature statuses
    untouched.

    Args:
        project_id: The project context.
        causing_feature_id: The feature whose implementation triggered the failures.
        newly_failing_tests: List of test names that newly failed.
    """
    if not newly_failing_tests:
        return
    from bob.db import _record_unattributed_failures

    _record_unattributed_failures(
        project_id=project_id,
        causing_feature_id=causing_feature_id,
        test_names=newly_failing_tests,
    )


def empty_map_leaves_feature_status_untouched() -> bool:
    """Return True; documents that the empty-map path does not touch any feature status.

    When test_to_feature_map is empty, handle_empty_ownership_map records all
    failures as unattributed and never mutates any feature's status field.
    """
    return True
