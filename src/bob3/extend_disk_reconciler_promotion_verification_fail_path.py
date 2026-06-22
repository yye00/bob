"""Extend disk_reconciler promotion to the verification-fail path (b161fced).

Companion to F-R7-598 (_final_exit_sweep guard). F-R7-598 closes the
orphan-executing path; this module closes the symmetric verification-fail path.

Context
-------
When a feature exhausts its retries and the verifier reports failure, run_loop
transitions the feature to needs_human. However, structural AC markers (file
exists, function defined) may already be present on disk — this happens when
the test_writer emits snapshot tests that the sub-agent cannot satisfy, even
though the implementation artifacts are present.

Fix
---
Before transitioning to needs_human, call check_executing_feature_acs from
the orchestrator disk_reconciler. If all ACs satisfy on disk, promote the
feature to completed and emit {"event":"VERIFY_FAIL_DISK_PROMOTED",...}.

Guard (prevents false promotions)
----------------------------------
Only run the disk check when ALL of these hold:
  1. failed_gate == "tests_pass" (structural/behavior gate failures indicate
     a genuine implementation gap, not a test-spec mismatch)
  2. The AC list includes at least one structural or behavior AC
     ("File exists:" or "Function defined:"). Features with only pytest: ACs
     have no disk evidence beyond the test results themselves.

Safety invariant: on any exception or guard bypass, returns promoted=False so
the caller falls through to the original needs_human transition.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from bob3.orchestrator.disk_reconciler import check_executing_feature_acs

logger = logging.getLogger(__name__)

_STRUCTURAL_PREFIXES = ("File exists:", "Function defined:")


def _count_structural_behavior_acs(criteria: list[str]) -> int:
    """Return the number of ACs that are structural or behavior type."""
    count = 0
    for c in criteria:
        stripped = c.strip()
        if any(stripped.startswith(p) for p in _STRUCTURAL_PREFIXES):
            count += 1
    return count


def extend_disk_reconciler_promotion_verification_fail_path(
    *,
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
    failed_gate: str | None = None,
    passed_gates: list[str] | None = None,
) -> dict[str, Any]:
    """Check disk state before marking a verify-fail feature as needs_human.

    Called BEFORE the needs_human transition when verification fails and the
    feature has exhausted its retries. If all ACs satisfy on disk via
    check_executing_feature_acs, promotes to completed and emits
    VERIFY_FAIL_DISK_PROMOTED. Otherwise returns promoted=False so the caller
    can proceed to the needs_human branch.

    Parameters
    ----------
    project_id:
        The project UUID.
    feature_id:
        UUID of the feature to check and possibly promote.
    feature_name:
        Human-readable feature name for log messages.
    acceptance_criteria_json:
        JSON-encoded list of AC strings (from feature.acceptance_criteria).
    failed_gate:
        The gate name that triggered the verification failure (e.g. "tests_pass").
        Guard only activates when this equals "tests_pass".
    passed_gates:
        List of gate names that passed before the failure. Recorded in result.

    Returns
    -------
    dict with keys:
        ``promoted``     — True if promoted to completed via disk check.
        ``failed_gate``  — The failed_gate argument, echoed back.
        ``passed_gates`` — The passed_gates argument, echoed back.
    """
    if passed_gates is None:
        passed_gates = []

    base_result: dict[str, Any] = {
        "promoted": False,
        "failed_gate": failed_gate,
        "passed_gates": passed_gates,
    }

    # Guard 1: only useful when the failing gate is tests_pass
    if failed_gate != "tests_pass":
        return base_result

    # Guard 2: AC list must be parseable and non-empty
    try:
        criteria: list[str] = json.loads(acceptance_criteria_json)
    except (json.JSONDecodeError, TypeError):
        logger.debug(
            "extend_disk_reconciler: could not parse AC JSON for feature %s; "
            "skipping disk promotion",
            feature_id,
        )
        return base_result

    if not criteria:
        return base_result

    # Guard 3: at least one structural/behavior AC must be present
    if _count_structural_behavior_acs(criteria) == 0:
        logger.debug(
            "extend_disk_reconciler: feature %s has no structural/behavior ACs; "
            "skipping disk promotion",
            feature_id,
        )
        return base_result

    # All guards passed — delegate to the disk reconciler
    try:
        disk_promoted = check_executing_feature_acs(
            project_id=project_id,
            feature_id=feature_id,
            feature_name=feature_name,
            acceptance_criteria_json=acceptance_criteria_json,
        )
    except Exception:
        logger.debug(
            "extend_disk_reconciler: check_executing_feature_acs raised for feature %s; "
            "falling through to needs_human",
            feature_id,
            exc_info=True,
        )
        return base_result

    if disk_promoted:
        logger.info(
            '{"event":"VERIFY_FAIL_DISK_PROMOTED","feature_id":"%s",'
            '"failed_gate":"%s","passed_gates":%s}',
            feature_id,
            failed_gate,
            json.dumps(passed_gates),
        )
        return {
            "promoted": True,
            "failed_gate": failed_gate,
            "passed_gates": passed_gates,
        }

    return base_result


__all__ = ["extend_disk_reconciler_promotion_verification_fail_path"]
