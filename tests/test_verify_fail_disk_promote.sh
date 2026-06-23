#!/usr/bin/env bash
# Integration test: VERIFY_FAIL_DISK_PROMOTED — F-R7-612 disk-reconciler promotion
# on verification-fail path (companion to F-R7-598 final-sweep guard).
#
# Verifies that handle_execution_result calls disk_reconciler BEFORE marking a
# feature needs_human when verification fails with structural/behavior ACs
# satisfied on disk, emitting VERIFY_FAIL_DISK_PROMOTED instead.
#
# Exit 0 on all assertions passing, exit 1 on any failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(dirname "$SCRIPT_DIR")"
export PYTHONPATH="${WORKSPACE_DIR}/src${PYTHONPATH:+:$PYTHONPATH}"

PASS=0
FAIL=0
FAILURES=()

assert_contains() {
    local description="$1"
    local needle="$2"
    local haystack="$3"
    if echo "$haystack" | grep -qF "$needle"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: $description — expected to find: $needle")
    fi
}

assert_not_contains() {
    local description="$1"
    local needle="$2"
    local haystack="$3"
    if ! echo "$haystack" | grep -qF "$needle"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: $description — expected NOT to find: $needle")
    fi
}

# ── Structural checks ─────────────────────────────────────────────────────────

RUN_LOOP="src/bob3/orchestrator/run_loop.py"

if [[ ! -f "$RUN_LOOP" ]]; then
    echo "FATAL: $RUN_LOOP not found" >&2
    exit 1
fi

RUN_LOOP_CONTENT=$(cat "$RUN_LOOP")

assert_contains "run_loop.py contains F-R7-612 marker" \
    "F-R7-612" "$RUN_LOOP_CONTENT"

assert_contains "run_loop.py contains VERIFY_FAIL_DISK_PROMOTED event" \
    "VERIFY_FAIL_DISK_PROMOTED" "$RUN_LOOP_CONTENT"

assert_contains "run_loop.py references reconcile_from_disk or check_executing_feature_acs near F-R7-612" \
    "reconcile_from_disk" "$RUN_LOOP_CONTENT"

assert_contains "run_loop.py references tests_pass near F-R7-612" \
    "tests_pass" "$RUN_LOOP_CONTENT"

# Verify F-R7-612 and VERIFY_FAIL_DISK_PROMOTED are within 300 lines of each other
FR612_LINE=$(grep -n "F-R7-612" "$RUN_LOOP" | head -1 | cut -d: -f1)
VFD_LINE=$(grep -n "VERIFY_FAIL_DISK_PROMOTED" "$RUN_LOOP" | head -1 | cut -d: -f1)
if [[ -n "$FR612_LINE" && -n "$VFD_LINE" ]]; then
    DIFF=$(( VFD_LINE - FR612_LINE ))
    DIFF=${DIFF#-}
    if [[ "$DIFF" -le 300 ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: F-R7-612 (line $FR612_LINE) and VERIFY_FAIL_DISK_PROMOTED (line $VFD_LINE) are $DIFF lines apart (>300)")
    fi
else
    FAIL=$((FAIL + 1))
    FAILURES+=("FAIL: Could not locate F-R7-612 (line $FR612_LINE) and VERIFY_FAIL_DISK_PROMOTED (line $VFD_LINE)")
fi

# Verify reconcile_from_disk is within 300 lines of F-R7-612
if [[ -n "$FR612_LINE" ]]; then
    RFD_LINE=$(grep -n "reconcile_from_disk\|check_executing_feature_acs" "$RUN_LOOP" | \
        awk -F: -v ref="$FR612_LINE" 'BEGIN{best=999999; bline=0} {d=$1-ref; if(d<0)d=-d; if(d<best){best=d; bline=$1}} END{print bline}')
    if [[ -n "$RFD_LINE" && "$RFD_LINE" -gt 0 ]]; then
        DIFF=$(( RFD_LINE - FR612_LINE ))
        DIFF=${DIFF#-}
        if [[ "$DIFF" -le 300 ]]; then
            PASS=$((PASS + 1))
        else
            FAIL=$((FAIL + 1))
            FAILURES+=("FAIL: nearest reconcile_from_disk ref (line $RFD_LINE) and F-R7-612 (line $FR612_LINE) are $DIFF lines apart (>300)")
        fi
    fi
fi

# Verify tests_pass is within 300 lines of F-R7-612
if [[ -n "$FR612_LINE" ]]; then
    TP_LINE=$(grep -n "tests_pass" "$RUN_LOOP" | \
        awk -F: -v ref="$FR612_LINE" 'BEGIN{best=999999; bline=0} {d=$1-ref; if(d<0)d=-d; if(d<best){best=d; bline=$1}} END{print bline}')
    if [[ -n "$TP_LINE" && "$TP_LINE" -gt 0 ]]; then
        DIFF=$(( TP_LINE - FR612_LINE ))
        DIFF=${DIFF#-}
        if [[ "$DIFF" -le 300 ]]; then
            PASS=$((PASS + 1))
        else
            FAIL=$((FAIL + 1))
            FAILURES+=("FAIL: nearest tests_pass ref (line $TP_LINE) and F-R7-612 (line $FR612_LINE) are $DIFF lines apart (>300)")
        fi
    fi
fi

# ── Behavioral checks via Python ──────────────────────────────────────────────

PYTHON_TEST=$(python3 - <<'PYEOF'
import sys
import json
import pathlib
from unittest.mock import MagicMock, patch, call

try:
    from bob3.orchestrator.run_loop import handle_execution_result
except ImportError as e:
    print(f"IMPORT_ERROR: {e}")
    sys.exit(1)

results = []

def _make_feature(feature_id, ac_json=None):
    f = MagicMock()
    f.id = feature_id
    f.name = "test feature"
    f.acceptance_criteria = ac_json or '["structural: src/foo.py contains X"]'
    f.parent_feature_id = None
    f.project_id = "proj-test-0001"
    return f

def _make_spawn_result(is_error=False):
    sr = MagicMock()
    sr.execution_result.is_error = is_error
    sr.execution_result.text = "output text"
    sr.execution_result.duration_ms = 1000
    sr.execution_result.num_turns = 5
    sr.execution_result.total_cost_usd = 0.10
    sr.execution_result.tool_uses = []
    sr.execution_result.error_message = "" if not is_error else "sub-agent error"
    sr.agent_run = MagicMock()
    sr.agent_run.id = "run-test-0001"
    return sr

# Test 1: disk promotion fires when tests_pass is the only failing gate
# and structural ACs are satisfied on disk → feature promoted, NOT needs_human
def test_disk_promote_on_tests_pass_failure():
    feature_id = "feat-vfd-prom-0001-000000000001"
    feature = _make_feature(feature_id, '["structural: src/bob3/run_loop.py contains F-R7-612"]')
    spawn_result = _make_spawn_result(is_error=False)

    verification_result = {
        "passed": False,
        "summary": "tests_pass failed",
        "checks": [
            {"name": "structural_acs_present", "passed": True},
            {"name": "tests_pass", "passed": False, "severity": "error"},
            {"name": "acceptance_criteria_met", "passed": True},
        ],
    }

    called_nh = []
    called_promote = []

    with patch("bob3.orchestrator.run_loop.db") as mock_db, \
         patch("bob3.orchestrator.run_loop._may_demote", return_value=True), \
         patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_check_acs:

        mock_db.increment_refinement_attempts.return_value = None  # exhausted → would go NH
        mock_check_acs.return_value = True  # disk says: ACs all pass

        outcome = handle_execution_result(
            project_id="proj-vfd-0001",
            feature=feature,
            spawn_result=spawn_result,
            verification_passed=False,
            verification_summary="tests_pass failed",
            verification_result=verification_result,
            workspace=str(pathlib.Path.cwd()),
        )

    # If disk promoted, update_feature should NOT be called with needs_human
    nh_calls = [c for c in mock_db.update_feature.call_args_list
                if c.kwargs.get("status") == "needs_human"]
    if nh_calls:
        return f"FAIL: test_disk_promote_on_tests_pass_failure — feature marked needs_human despite disk promotion: {nh_calls}"
    return "PASS: test_disk_promote_on_tests_pass_failure"

# Test 2: when disk check returns False (ACs not satisfied), needs_human proceeds
def test_needs_human_when_disk_check_fails():
    feature_id = "feat-vfd-nh-0002-000000000002"
    feature = _make_feature(feature_id, '["structural: missing_file.py contains X"]')
    spawn_result = _make_spawn_result(is_error=False)

    verification_result = {
        "passed": False,
        "summary": "tests_pass failed",
        "checks": [
            {"name": "tests_pass", "passed": False, "severity": "error"},
            {"name": "acceptance_criteria_met", "passed": True},
        ],
    }

    with patch("bob3.orchestrator.run_loop.db") as mock_db, \
         patch("bob3.orchestrator.run_loop._may_demote", return_value=True), \
         patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_check_acs, \
         patch("bob3.orchestrator.run_loop._rca_auto_reset_if_infra", return_value=False):

        mock_db.increment_refinement_attempts.return_value = None  # NH
        mock_check_acs.return_value = False  # disk check fails

        outcome = handle_execution_result(
            project_id="proj-vfd-0002",
            feature=feature,
            spawn_result=spawn_result,
            verification_passed=False,
            verification_summary="tests_pass failed",
            verification_result=verification_result,
            workspace=str(pathlib.Path.cwd()),
        )

    nh_calls = [c for c in mock_db.update_feature.call_args_list
                if c.kwargs.get("status") == "needs_human"]
    if not nh_calls:
        return f"FAIL: test_needs_human_when_disk_check_fails — needs_human not called; calls={mock_db.update_feature.call_args_list}"
    return "PASS: test_needs_human_when_disk_check_fails"

# Test 3: guard — all-gates-failed (no structural ACs at all) → no disk promotion attempt
def test_no_disk_promote_when_all_gates_fail():
    feature_id = "feat-vfd-allf-0003-000000000003"
    feature = _make_feature(feature_id, '[]')
    spawn_result = _make_spawn_result(is_error=False)

    verification_result = {
        "passed": False,
        "summary": "all checks failed",
        "checks": [
            {"name": "acceptance_criteria_met", "passed": False},
            {"name": "tests_pass", "passed": False},
        ],
    }

    with patch("bob3.orchestrator.run_loop.db") as mock_db, \
         patch("bob3.orchestrator.run_loop._may_demote", return_value=True), \
         patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_check_acs, \
         patch("bob3.orchestrator.run_loop._rca_auto_reset_if_infra", return_value=False):

        mock_db.increment_refinement_attempts.return_value = None
        mock_check_acs.return_value = True  # even if disk "passes", guard should block

        outcome = handle_execution_result(
            project_id="proj-vfd-0003",
            feature=feature,
            spawn_result=spawn_result,
            verification_passed=False,
            verification_summary="all failed",
            verification_result=verification_result,
            workspace=str(pathlib.Path.cwd()),
        )

    # With no structural/behavior ACs, should NOT skip to needs_human bypass
    # The guard condition requires (structural_count + behavior_count) > 0
    # Feature has empty AC list, so structural_count=0, behavior_count=0 → no disk promote
    # The test verifies needs_human IS called (disk promote skipped)
    nh_calls = [c for c in mock_db.update_feature.call_args_list
                if c.kwargs.get("status") == "needs_human"]
    if not nh_calls:
        return f"FAIL: test_no_disk_promote_when_all_gates_fail — expected needs_human; calls={mock_db.update_feature.call_args_list}"
    return "PASS: test_no_disk_promote_when_all_gates_fail"

# Test 4: backward compat — when verification_result=None (old callers), behavior unchanged
def test_no_verification_result_falls_through_to_nh():
    feature_id = "feat-vfd-compat-0004-000000000004"
    feature = _make_feature(feature_id)
    spawn_result = _make_spawn_result(is_error=False)

    with patch("bob3.orchestrator.run_loop.db") as mock_db, \
         patch("bob3.orchestrator.run_loop._may_demote", return_value=True), \
         patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_check_acs, \
         patch("bob3.orchestrator.run_loop._rca_auto_reset_if_infra", return_value=False):

        mock_db.increment_refinement_attempts.return_value = None
        mock_check_acs.return_value = True  # should not be called

        outcome = handle_execution_result(
            project_id="proj-vfd-0004",
            feature=feature,
            spawn_result=spawn_result,
            verification_passed=False,
            verification_summary="failed",
            # verification_result NOT passed — old caller pattern
            workspace=str(pathlib.Path.cwd()),
        )

    # Without verification_result, disk promote cannot fire; falls through to NH
    nh_calls = [c for c in mock_db.update_feature.call_args_list
                if c.kwargs.get("status") == "needs_human"]
    if not nh_calls:
        return f"FAIL: test_no_verification_result_falls_through_to_nh — needs_human not called; calls={mock_db.update_feature.call_args_list}"
    return "PASS: test_no_verification_result_falls_through_to_nh"

# Test 5: disk promote only fires when is_error=False (sub-agent success + verify fail)
def test_no_disk_promote_when_sub_agent_errored():
    feature_id = "feat-vfd-err-0005-000000000005"
    feature = _make_feature(feature_id, '["structural: src/foo.py contains X"]')
    spawn_result = _make_spawn_result(is_error=True)  # sub-agent errored

    verification_result = {
        "passed": False,
        "summary": "tests_pass failed",
        "checks": [
            {"name": "tests_pass", "passed": False},
            {"name": "acceptance_criteria_met", "passed": True},
        ],
    }

    with patch("bob3.orchestrator.run_loop.db") as mock_db, \
         patch("bob3.orchestrator.run_loop._may_demote", return_value=True), \
         patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_check_acs:

        mock_check_acs.return_value = True

        outcome = handle_execution_result(
            project_id="proj-vfd-0005",
            feature=feature,
            spawn_result=spawn_result,
            verification_passed=False,
            verification_summary="tests_pass failed",
            verification_result=verification_result,
            workspace=str(pathlib.Path.cwd()),
        )

    # When is_error=True, the error branch fires, not the verify-fail branch.
    # disk promote must not cause a completed status here.
    completed_calls = [c for c in mock_db.update_feature.call_args_list
                       if c.kwargs.get("status") == "completed"]
    if completed_calls:
        return f"FAIL: test_no_disk_promote_when_sub_agent_errored — feature marked completed despite sub-agent error: {completed_calls}"
    return "PASS: test_no_disk_promote_when_sub_agent_errored"

for test_fn in [
    test_disk_promote_on_tests_pass_failure,
    test_needs_human_when_disk_check_fails,
    test_no_disk_promote_when_all_gates_fail,
    test_no_verification_result_falls_through_to_nh,
    test_no_disk_promote_when_sub_agent_errored,
]:
    try:
        result = test_fn()
        print(result)
    except Exception as exc:
        import traceback
        print(f"FAIL: {test_fn.__name__} raised exception: {type(exc).__name__}: {exc}")
        traceback.print_exc()
PYEOF
)

while IFS= read -r line; do
    if [[ "$line" == PASS:* ]]; then
        PASS=$((PASS + 1))
    elif [[ "$line" == FAIL:* || "$line" == IMPORT_ERROR:* ]]; then
        FAIL=$((FAIL + 1))
        FAILURES+=("$line")
    fi
done <<< "$PYTHON_TEST"

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "=== test_verify_fail_disk_promote.sh results ==="
echo "PASS: $PASS  FAIL: $FAIL"
if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for f in "${FAILURES[@]}"; do
        echo "  $f"
    done
fi

if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
echo "All assertions passed."
exit 0
