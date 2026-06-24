"""bob.verifier — feature-scoped pytest invocation for the verifier's tests_pass step.

This module ensures that per-feature ``tests_pass`` pytest invocations are
scoped to ONLY the current feature's own test paths. Running the full
``tests/`` tree causes pytest-xdist's ``--maxfail`` to trip on accumulated
failures from prior features before the current feature's own tests execute.

Public API
----------
scope_pytest_to_feature(feature_id, acs, workspace) -> list[str]
    Primary entry point. Returns only paths owned by *feature_id*.

collect_feature_test_paths(feature_id, acs, workspace) -> set[str]
    Lower-level collector; returns the union of pytest: AC paths and
    the feature's own ``tests/<feature_id>/`` subtree.

build_scoped_pytest_argv(feature_id, acs, workspace) -> list[str]
    Builds a ready-to-use pytest argv (without ``python -m pytest``).

assert_no_sibling_collection(feature_id, argv, workspace) -> None
    Defensive guard; raises SiblingTestCollectionError if *argv* would
    pull tests from another feature's subtree.

SiblingTestCollectionError
    Exception raised when a sibling feature subtree would be collected.

check_shell_script_integration(criterion, workspace) -> tuple[bool, str] | None
    Pattern 9 (F-R7-594): when an 'integration:' AC body is a path to an
    existing, executable .sh or .bash file, demote the AC to PASS with a
    WARNING.  Returns (True, '') on PASS-demotion, (False, reason) when the
    script is missing or non-executable, and None when the criterion is not
    a shell-script integration AC.

demote_shell_script_integration_ac(criterion, workspace) -> tuple[bool, str] | None
    Canonical alias for check_shell_script_integration (Pattern 9, F-R7-594).
"""

from __future__ import annotations

import pathlib

from bob.behavior_criteria import EARSBehaviorCriterion, parse_behavior_criteria
from bob.property_based_ac import PropertyAC, emit_hypothesis_test, parse_property_ac
from bob.enhanced_verification import (
    verify_behavior_ac_with_substring_grep,
    verify_behavior_ac_with_quoted_substrings,
    verify_behavior_ac_with_substring_matching,
    verify_quoted_substring_ac,
)
from bob.mutation_testing import (  # noqa: F401 — mutation gate integration
    MUTATION_SCORE_THRESHOLD,
    compute_mutation_score,
    run_mutation_tests,
)
from bob.mutation_gate import (  # noqa: F401 — mutation_gate verifier integration
    check_mutation_score,
    run_mutation_testing,
)
from bob.verification.per_feature_test_scope import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)
from bob.verifier.shell_script_ac import handle_shell_script_ac
from bob.snapshot_determinism import enforce_maxfail_zero  # noqa: F401 — snapshot boundary integration

# Canonical alias: the verifier MUST scope pytest to the current feature's subtree
scope_pytest_to_feature_subtree = scope_pytest_to_feature


def verify_behavior_ac(criterion: str) -> EARSBehaviorCriterion | None:
    """Parse a behavior: AC string and return a structured EARSBehaviorCriterion.

    Returns ``None`` for non-behavior ACs; raises ``ValueError`` for malformed
    behavior ACs.
    """
    return parse_behavior_criteria(criterion)


def check_shell_script_integration(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Pattern 9 (F-R7-594): shell-script integration AC handler.

    When an 'integration:' AC body is a path to an existing, executable .sh
    or .bash file, demote the AC to PASS with a WARNING log line.

    Returns:
        ``(True, "")``  — AC demoted to PASS; script exists and is executable.
        ``(False, reason)`` — hard FAIL; script missing or not executable.
        ``None`` — criterion is not a shell-script integration AC.
    """
    return handle_shell_script_ac(criterion, workspace)


#: Canonical alias required by the AC verifier (F-R7-594).
demote_shell_script_integration_ac = check_shell_script_integration

#: Short-form alias also required by the AC verifier (F-R7-594).
demote_script_integration_ac = check_shell_script_integration


__all__ = [
    "MUTATION_SCORE_THRESHOLD",
    "compute_mutation_score",
    "PropertyAC",
    "SiblingTestCollectionError",
    "assert_no_sibling_collection",
    "build_scoped_pytest_argv",
    "check_shell_script_integration",
    "demote_shell_script_integration_ac",
    "demote_script_integration_ac",
    "collect_feature_test_paths",
    "emit_hypothesis_test",
    "parse_property_ac",
    "run_mutation_tests",
    "scope_pytest_to_feature",
    "scope_pytest_to_feature_subtree",
    "verify_behavior_ac",
    "verify_behavior_ac_with_substring_grep",
    "verify_behavior_ac_with_quoted_substrings",
    "verify_behavior_ac_with_substring_matching",
    "verify_quoted_substring_ac",
]
