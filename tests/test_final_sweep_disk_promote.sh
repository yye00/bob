#!/usr/bin/env bash
# Integration test: _final_exit_sweep — F-R7-598 reconciler-before-sweep guard.
#
# Verifies that _final_exit_sweep calls disk_reconciler ACs before flipping
# an orphan-executing feature to failed, and that FINAL_SWEEP_DISK_PROMOTED /
# FINAL_SWEEP_SUMMARY events are emitted correctly.
#
# Exit 0 on all assertions passing, exit 1 on any failure.

set -euo pipefail

# Ensure this workspace's src is on PYTHONPATH so imports use the local bob3.
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
DISK_RECONCILER="src/bob3/orchestrator/disk_reconciler.py"

if [[ ! -f "$RUN_LOOP" ]]; then
    echo "FATAL: $RUN_LOOP not found" >&2
    exit 1
fi

RUN_LOOP_CONTENT=$(cat "$RUN_LOOP")
DISK_RECONCILER_CONTENT=$(cat "$DISK_RECONCILER")

assert_contains "run_loop.py contains F-R7-598 marker" \
    "F-R7-598" "$RUN_LOOP_CONTENT"

assert_contains "run_loop.py contains FINAL_SWEEP_DISK_PROMOTED event" \
    "FINAL_SWEEP_DISK_PROMOTED" "$RUN_LOOP_CONTENT"

assert_contains "run_loop.py contains FINAL_SWEEP_SUMMARY event" \
    "FINAL_SWEEP_SUMMARY" "$RUN_LOOP_CONTENT"

assert_contains "run_loop.py references disk_reconciler" \
    "disk_reconciler" "$RUN_LOOP_CONTENT"

assert_contains "run_loop.py contains _final_exit_sweep definition" \
    "_final_exit_sweep" "$RUN_LOOP_CONTENT"

# Verify F-R7-598 and FINAL_SWEEP_DISK_PROMOTED are within 200 lines of each other.
FR598_LINE=$(grep -n "F-R7-598" "$RUN_LOOP" | head -1 | cut -d: -f1)
PROMOTED_LINE=$(grep -n "FINAL_SWEEP_DISK_PROMOTED" "$RUN_LOOP" | head -1 | cut -d: -f1)
if [[ -n "$FR598_LINE" && -n "$PROMOTED_LINE" ]]; then
    DIFF=$(( PROMOTED_LINE - FR598_LINE ))
    DIFF=${DIFF#-}  # absolute value
    if [[ "$DIFF" -le 200 ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: F-R7-598 and FINAL_SWEEP_DISK_PROMOTED are $DIFF lines apart (>200)")
    fi
else
    FAIL=$((FAIL + 1))
    FAILURES+=("FAIL: Could not locate both F-R7-598 (line $FR598_LINE) and FINAL_SWEEP_DISK_PROMOTED (line $PROMOTED_LINE)")
fi

# Verify _final_exit_sweep and F-R7-598 are within 400 lines of each other.
SWEEP_LINE=$(grep -n "def _final_exit_sweep" "$RUN_LOOP" | head -1 | cut -d: -f1)
if [[ -n "$SWEEP_LINE" && -n "$FR598_LINE" ]]; then
    DIFF=$(( FR598_LINE - SWEEP_LINE ))
    DIFF=${DIFF#-}
    if [[ "$DIFF" -le 400 ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: _final_exit_sweep (line $SWEEP_LINE) and F-R7-598 (line $FR598_LINE) are $DIFF lines apart (>400)")
    fi
else
    FAIL=$((FAIL + 1))
    FAILURES+=("FAIL: Could not locate _final_exit_sweep (line $SWEEP_LINE) or F-R7-598 (line $FR598_LINE)")
fi

# Verify disk_reconciler and F-R7-598 are within 400 lines of each other.
DR_LINE=$(grep -n "disk_reconciler" "$RUN_LOOP" | awk -F: '{print $1}' | sort -n | \
    awk -v ref="$FR598_LINE" 'BEGIN{best=999999; bline=0} {d=$1-ref; if(d<0)d=-d; if(d<best){best=d; bline=$1}} END{print bline}')
if [[ -n "$DR_LINE" && -n "$FR598_LINE" ]]; then
    DIFF=$(( DR_LINE - FR598_LINE ))
    DIFF=${DIFF#-}
    if [[ "$DIFF" -le 400 ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: nearest disk_reconciler ref (line $DR_LINE) and F-R7-598 (line $FR598_LINE) are $DIFF lines apart (>400)")
    fi
fi

# ── Behavioral checks via Python ──────────────────────────────────────────────

PYTHON_TEST=$(python3 - <<'PYEOF'
import sys
import json
from unittest.mock import MagicMock, patch, call

try:
    from bob3.orchestrator.run_loop import _final_exit_sweep
except ImportError as e:
    print(f"IMPORT_ERROR: {e}")
    sys.exit(1)

results = []

# Test 1: disk_reconciler promotes → no flip-to-failed, FINAL_SWEEP_DISK_PROMOTED emitted
def test_disk_reconciler_promotes_avoids_failed():
    project_id = "proj-sweep-disk-0001-000000000001"
    feature_id = "feat-disk-prom-000-000000000001"

    fake_feature = MagicMock()
    fake_feature.id = feature_id
    fake_feature.name = "test feature"
    fake_feature.acceptance_criteria = '["file_exists: src/bob3/run_loop.py"]'

    with patch("bob3.orchestrator.run_loop.db") as mock_db, \
         patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pid, \
         patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_check:

        mock_db.list_features.return_value = [fake_feature]
        mock_pid.return_value = []  # dead PID
        mock_check.return_value = True  # disk reconciler promotes

        _final_exit_sweep(project_id)

    # update_feature should NOT be called for flip-to-failed when disk promoted
    for c in mock_db.update_feature.call_args_list:
        if c.kwargs.get("status") == "failed":
            return f"FAIL: test_disk_reconciler_promotes_avoids_failed — update_feature called with failed={c}"
    return "PASS: test_disk_reconciler_promotes_avoids_failed"

# Test 2: disk_reconciler fails → flip-to-failed proceeds
def test_disk_reconciler_fails_flips_to_failed():
    project_id = "proj-sweep-disk-0002-000000000002"
    feature_id = "feat-disk-fail-000-000000000002"

    fake_feature = MagicMock()
    fake_feature.id = feature_id
    fake_feature.name = "test feature 2"
    fake_feature.acceptance_criteria = '[]'

    with patch("bob3.orchestrator.run_loop.db") as mock_db, \
         patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pid, \
         patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_check:

        mock_db.list_features.return_value = [fake_feature]
        mock_pid.return_value = []  # dead PID
        mock_check.return_value = False  # disk check fails

        _final_exit_sweep(project_id)

    # update_feature should be called with failed
    for c in mock_db.update_feature.call_args_list:
        if c.args and c.args[0] == feature_id and c.kwargs.get("status") == "failed":
            return "PASS: test_disk_reconciler_fails_flips_to_failed"
    return f"FAIL: test_disk_reconciler_fails_flips_to_failed — update_feature not called with failed; calls={mock_db.update_feature.call_args_list}"

# Test 3: FINAL_SWEEP_SUMMARY event emitted in all cases
def test_final_sweep_summary_emitted():
    import logging
    log_records = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            log_records.append(self.format(record))

    handler = CapturingHandler()
    run_loop_logger = logging.getLogger("bob3.orchestrator.run_loop")
    run_loop_logger.addHandler(handler)
    run_loop_logger.setLevel(logging.DEBUG)

    try:
        project_id = "proj-sweep-summary-0003-00000001"
        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature"), \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs"):
            mock_db.list_features.return_value = []
            _final_exit_sweep(project_id)
    finally:
        run_loop_logger.removeHandler(handler)

    for record in log_records:
        if "FINAL_SWEEP_SUMMARY" in record:
            return "PASS: test_final_sweep_summary_emitted"
    return f"FAIL: test_final_sweep_summary_emitted — FINAL_SWEEP_SUMMARY not found in log records: {log_records}"

# Test 4: Live PID features are still skipped (regression guard)
def test_live_pid_still_skipped():
    project_id = "proj-sweep-live-0004-000000000004"
    feature_id = "feat-live-pid-000-000000000004"

    fake_feature = MagicMock()
    fake_feature.id = feature_id
    fake_feature.name = "live feature"
    fake_feature.acceptance_criteria = '[]'

    with patch("bob3.orchestrator.run_loop.db") as mock_db, \
         patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pid, \
         patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_check:

        mock_db.list_features.return_value = [fake_feature]
        mock_pid.return_value = [12345]  # live PID

        _final_exit_sweep(project_id)

    # disk check should NOT be called for live-PID features
    if mock_check.called:
        return f"FAIL: test_live_pid_still_skipped — _check_executing_feature_acs was called for live PID feature"
    return "PASS: test_live_pid_still_skipped"

# Test 5: _check_executing_feature_acs is called with correct args
def test_disk_check_called_with_correct_args():
    project_id = "proj-sweep-args-0005-000000000005"
    feature_id = "feat-args-check-000-000000000005"
    ac_json = '["file_exists: README.md"]'

    fake_feature = MagicMock()
    fake_feature.id = feature_id
    fake_feature.name = "args check feature"
    fake_feature.acceptance_criteria = ac_json

    with patch("bob3.orchestrator.run_loop.db") as mock_db, \
         patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pid, \
         patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_check:

        mock_db.list_features.return_value = [fake_feature]
        mock_pid.return_value = []
        mock_check.return_value = False

        _final_exit_sweep(project_id)

    if not mock_check.called:
        return "FAIL: test_disk_check_called_with_correct_args — _check_executing_feature_acs not called"
    call_kwargs = mock_check.call_args.kwargs
    if call_kwargs.get("project_id") != project_id:
        return f"FAIL: test_disk_check_called_with_correct_args — project_id mismatch: {call_kwargs}"
    if call_kwargs.get("feature_id") != feature_id:
        return f"FAIL: test_disk_check_called_with_correct_args — feature_id mismatch: {call_kwargs}"
    if call_kwargs.get("acceptance_criteria_json") != ac_json:
        return f"FAIL: test_disk_check_called_with_correct_args — acceptance_criteria_json mismatch: {call_kwargs}"
    return "PASS: test_disk_check_called_with_correct_args"

for test_fn in [
    test_disk_reconciler_promotes_avoids_failed,
    test_disk_reconciler_fails_flips_to_failed,
    test_final_sweep_summary_emitted,
    test_live_pid_still_skipped,
    test_disk_check_called_with_correct_args,
]:
    try:
        result = test_fn()
        print(result)
    except Exception as exc:
        print(f"FAIL: {test_fn.__name__} raised exception: {exc}")
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
echo "=== test_final_sweep_disk_promote.sh results ==="
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
