#!/usr/bin/env bash
# Integration test: SWE-Bench cheap wins — F-R7-609
#
# Verifies all ACs for feature 3b4cf8fb-9927-41a2-a85f-c4a8728d57bb:
# (A) repo_tree injected into worker prompt
# (B) failing_repro_test directive injected
# (C) EDIT_MODE adaptive selection logged
# (D) WEAK_TEST_DETECTED emitted on mutation-pass
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

DISPATCH_PY="src/bob3/dispatch.py"

if [[ ! -f "$DISPATCH_PY" ]]; then
    echo "FATAL: $DISPATCH_PY not found" >&2
    exit 1
fi

DISPATCH_CONTENT=$(cat "$DISPATCH_PY")

assert_contains "dispatch.py contains F-R7-609 marker" \
    "F-R7-609" "$DISPATCH_CONTENT"

assert_contains "dispatch.py contains repo_tree" \
    "repo_tree" "$DISPATCH_CONTENT"

assert_contains "dispatch.py contains failing_repro_test" \
    "failing_repro_test" "$DISPATCH_CONTENT"

assert_contains "dispatch.py contains EDIT_MODE" \
    "EDIT_MODE" "$DISPATCH_CONTENT"

assert_contains "dispatch.py contains WEAK_TEST_DETECTED" \
    "WEAK_TEST_DETECTED" "$DISPATCH_CONTENT"

# Verify each literal is within 400 lines of the F-R7-609 marker
MARKER_LINE=$(grep -n "F-R7-609" "$DISPATCH_PY" | head -1 | cut -d: -f1)

for TERM in "repo_tree" "failing_repro_test" "EDIT_MODE" "WEAK_TEST_DETECTED"; do
    TERM_LINE=$(grep -n "$TERM" "$DISPATCH_PY" | head -1 | cut -d: -f1)
    if [[ -n "$MARKER_LINE" && -n "$TERM_LINE" ]]; then
        DIFF=$(( TERM_LINE - MARKER_LINE ))
        DIFF=${DIFF#-}
        if [[ "$DIFF" -le 400 ]]; then
            PASS=$((PASS + 1))
        else
            FAIL=$((FAIL + 1))
            FAILURES+=("FAIL: $TERM (line $TERM_LINE) is $DIFF lines from F-R7-609 (line $MARKER_LINE) — exceeds 400")
        fi
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: Could not locate $TERM (line $TERM_LINE) or F-R7-609 marker (line $MARKER_LINE)")
    fi
done

# ── Behavioral checks via Python ──────────────────────────────────────────────

PYTHON_TEST=$(python3 - <<'PYEOF'
import sys
import json
import logging
import tempfile
import os
from unittest.mock import MagicMock, patch

try:
    from bob3.dispatch import (
        build_repo_tree,
        inject_repo_tree_into_prompt,
        should_inject_repro_test_directive,
        inject_failing_repro_test_directive,
        select_edit_mode,
        emit_edit_mode_event,
        EditModeDecision,
        emit_weak_test_event,
        apply_cheap_wins,
    )
except ImportError as e:
    print(f"IMPORT_ERROR: {e}")
    sys.exit(1)


# ── (A) repo_tree tests ───────────────────────────────────────────────────────

def test_inject_repo_tree_prepends_block():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "src"))
        open(os.path.join(tmpdir, "src", "main.py"), "w").close()
        original = "Do the work."
        result = inject_repo_tree_into_prompt(original, tmpdir)
        if "repo_tree" not in result:
            return "FAIL: test_inject_repo_tree_prepends_block — 'repo_tree' not in injected prompt"
        if "F-R7-609" not in result:
            return "FAIL: test_inject_repo_tree_prepends_block — 'F-R7-609' not in injected prompt"
        if not result.endswith(original):
            return "FAIL: test_inject_repo_tree_prepends_block — original prompt not at end"
        return "PASS: test_inject_repo_tree_prepends_block"


def test_repo_tree_caps_at_200_lines():
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(500):
            open(os.path.join(tmpdir, f"file_{i:04d}.py"), "w").close()
        tree = build_repo_tree(tmpdir, max_lines=200)
        lines = tree.splitlines()
        if len(lines) > 201:  # 200 + possible "… (N more)" trailer
            return f"FAIL: test_repo_tree_caps_at_200_lines — got {len(lines)} lines"
        if "more" not in tree:
            return "FAIL: test_repo_tree_caps_at_200_lines — no truncation marker found"
        return "PASS: test_repo_tree_caps_at_200_lines"


# ── (B) failing_repro_test tests ─────────────────────────────────────────────

def test_repro_test_injected_by_default():
    feature = MagicMock()
    feature.skip_repro_test = False
    feature.acceptance_criteria = '["integration: tests/test_foo.sh"]'
    prompt = "Implement the thing."
    result = inject_failing_repro_test_directive(prompt)
    if "Write a Failing Repro Test" not in result and "STANDING DIRECTIVE" not in result:
        return "FAIL: test_repro_test_injected_by_default — directive text not in result"
    return "PASS: test_repro_test_injected_by_default"


def test_repro_test_skipped_when_all_structural():
    feature = MagicMock()
    feature.skip_repro_test = False
    feature.acceptance_criteria = '["structural: src/foo.py contains X", "file_exists: README.md"]'
    result = should_inject_repro_test_directive(feature)
    if result:
        return "FAIL: test_repro_test_skipped_when_all_structural — should return False for all-structural ACs"
    return "PASS: test_repro_test_skipped_when_all_structural"


def test_repro_test_skipped_when_flag_set():
    feature = MagicMock()
    feature.skip_repro_test = True
    feature.acceptance_criteria = '["integration: tests/test_foo.sh"]'
    result = should_inject_repro_test_directive(feature)
    if result:
        return "FAIL: test_repro_test_skipped_when_flag_set — should return False when skip_repro_test=True"
    return "PASS: test_repro_test_skipped_when_flag_set"


def test_repro_test_injected_for_mixed_acs():
    feature = MagicMock()
    feature.skip_repro_test = False
    feature.acceptance_criteria = '["structural: src/foo.py contains X", "integration: tests/test_foo.sh"]'
    result = should_inject_repro_test_directive(feature)
    if not result:
        return "FAIL: test_repro_test_injected_for_mixed_acs — should return True for mixed ACs"
    return "PASS: test_repro_test_injected_for_mixed_acs"


# ── (C) EDIT_MODE tests ───────────────────────────────────────────────────────

def test_edit_mode_replace_by_default():
    decision = select_edit_mode(2, 10)
    if decision.mode != "replace":
        return f"FAIL: test_edit_mode_replace_by_default — expected replace, got {decision.mode}"
    return "PASS: test_edit_mode_replace_by_default"


def test_edit_mode_rewrite_when_sites_exceeded():
    decision = select_edit_mode(4, 10)  # sites > 3
    if decision.mode != "rewrite":
        return f"FAIL: test_edit_mode_rewrite_when_sites_exceeded — expected rewrite, got {decision.mode}"
    return "PASS: test_edit_mode_rewrite_when_sites_exceeded"


def test_edit_mode_rewrite_when_span_exceeded():
    decision = select_edit_mode(1, 50)  # span > 40
    if decision.mode != "rewrite":
        return f"FAIL: test_edit_mode_rewrite_when_span_exceeded — expected rewrite, got {decision.mode}"
    return "PASS: test_edit_mode_rewrite_when_span_exceeded"


def test_edit_mode_replace_at_exact_threshold():
    decision = select_edit_mode(3, 40)  # exactly at threshold — not exceeded
    if decision.mode != "replace":
        return f"FAIL: test_edit_mode_replace_at_exact_threshold — expected replace at threshold, got {decision.mode}"
    return "PASS: test_edit_mode_replace_at_exact_threshold"


def test_edit_mode_event_emitted():
    log_records = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            log_records.append(self.format(record))

    handler = CapturingHandler()
    dispatch_logger = logging.getLogger("bob3.dispatch")
    dispatch_logger.addHandler(handler)
    dispatch_logger.setLevel(logging.DEBUG)
    try:
        decision = EditModeDecision(mode="rewrite", sites=5, span=60)
        event = emit_edit_mode_event(decision, feature_id="test-feature-id")
    finally:
        dispatch_logger.removeHandler(handler)

    if event.get("event") != "EDIT_MODE":
        return f"FAIL: test_edit_mode_event_emitted — event key wrong: {event}"
    if event.get("mode") != "rewrite":
        return f"FAIL: test_edit_mode_event_emitted — mode wrong: {event}"
    if event.get("sites") != 5:
        return f"FAIL: test_edit_mode_event_emitted — sites wrong: {event}"
    if event.get("span") != 60:
        return f"FAIL: test_edit_mode_event_emitted — span wrong: {event}"

    found_in_log = any("EDIT_MODE" in r for r in log_records)
    if not found_in_log:
        return f"FAIL: test_edit_mode_event_emitted — EDIT_MODE not found in log: {log_records}"
    return "PASS: test_edit_mode_event_emitted"


# ── (D) WEAK_TEST_DETECTED tests ─────────────────────────────────────────────

def test_weak_test_event_structure():
    log_records = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            log_records.append(self.format(record))

    handler = CapturingHandler()
    dispatch_logger = logging.getLogger("bob3.dispatch")
    dispatch_logger.addHandler(handler)
    dispatch_logger.setLevel(logging.WARNING)
    try:
        event = emit_weak_test_event("feat-abc-123", detail="constant flip did not fail test")
    finally:
        dispatch_logger.removeHandler(handler)

    if event.get("event") != "WEAK_TEST_DETECTED":
        return f"FAIL: test_weak_test_event_structure — event key wrong: {event}"
    if event.get("feature_id") != "feat-abc-123":
        return f"FAIL: test_weak_test_event_structure — feature_id wrong: {event}"

    found_in_log = any("WEAK_TEST_DETECTED" in r for r in log_records)
    if not found_in_log:
        return f"FAIL: test_weak_test_event_structure — WEAK_TEST_DETECTED not in log: {log_records}"
    return "PASS: test_weak_test_event_structure"


def test_mutation_pass_check_true_when_test_passes():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("bob3.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = __import__("bob3.dispatch", fromlist=["run_mutation_pass_check"]).run_mutation_pass_check(
                ["python", "-m", "pytest", "tests/test_foo.py"],
                workspace=tmpdir,
                feature_id="feat-mut-001",
            )
    if not result:
        return "FAIL: test_mutation_pass_check_true_when_test_passes — expected True when test still passes"
    return "PASS: test_mutation_pass_check_true_when_test_passes"


def test_mutation_pass_check_false_when_test_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("bob3.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = __import__("bob3.dispatch", fromlist=["run_mutation_pass_check"]).run_mutation_pass_check(
                ["python", "-m", "pytest", "tests/test_foo.py"],
                workspace=tmpdir,
                feature_id="feat-mut-002",
            )
    if result:
        return "FAIL: test_mutation_pass_check_false_when_test_fails — expected False when test fails"
    return "PASS: test_mutation_pass_check_false_when_test_fails"


# ── apply_cheap_wins integration ─────────────────────────────────────────────

def test_apply_cheap_wins_returns_augmented_prompt():
    with tempfile.TemporaryDirectory() as tmpdir:
        feature = MagicMock()
        feature.id = "feat-cheap-wins-001"
        feature.skip_repo_tree = False
        feature.skip_repro_test = False
        feature.acceptance_criteria = '["integration: tests/test_foo.sh"]'

        result_prompt, metadata = apply_cheap_wins(
            "Original prompt.",
            workspace=tmpdir,
            feature=feature,
            edit_site_count=2,
            edit_span=15,
        )

    if "repo_tree" not in result_prompt:
        return "FAIL: test_apply_cheap_wins_returns_augmented_prompt — repo_tree not in result"
    if "STANDING DIRECTIVE" not in result_prompt and "Failing Repro Test" not in result_prompt:
        return "FAIL: test_apply_cheap_wins_returns_augmented_prompt — repro test directive not in result"
    if metadata.get("edit_mode", {}).get("event") != "EDIT_MODE":
        return f"FAIL: test_apply_cheap_wins_returns_augmented_prompt — edit_mode metadata wrong: {metadata}"
    if metadata.get("edit_mode", {}).get("mode") != "replace":
        return f"FAIL: test_apply_cheap_wins_returns_augmented_prompt — expected replace mode: {metadata}"
    return "PASS: test_apply_cheap_wins_returns_augmented_prompt"


def test_apply_cheap_wins_rewrite_mode_for_large_edit():
    with tempfile.TemporaryDirectory() as tmpdir:
        feature = MagicMock()
        feature.id = "feat-cheap-wins-002"
        feature.skip_repo_tree = True  # skip tree for speed
        feature.skip_repro_test = True
        feature.acceptance_criteria = '["structural: src/foo.py"]'

        result_prompt, metadata = apply_cheap_wins(
            "Original prompt.",
            workspace=tmpdir,
            feature=feature,
            edit_site_count=5,
            edit_span=100,
        )

    if metadata.get("edit_mode", {}).get("mode") != "rewrite":
        return f"FAIL: test_apply_cheap_wins_rewrite_mode_for_large_edit — expected rewrite: {metadata}"
    return "PASS: test_apply_cheap_wins_rewrite_mode_for_large_edit"


ALL_TESTS = [
    test_inject_repo_tree_prepends_block,
    test_repo_tree_caps_at_200_lines,
    test_repro_test_injected_by_default,
    test_repro_test_skipped_when_all_structural,
    test_repro_test_skipped_when_flag_set,
    test_repro_test_injected_for_mixed_acs,
    test_edit_mode_replace_by_default,
    test_edit_mode_rewrite_when_sites_exceeded,
    test_edit_mode_rewrite_when_span_exceeded,
    test_edit_mode_replace_at_exact_threshold,
    test_edit_mode_event_emitted,
    test_weak_test_event_structure,
    test_mutation_pass_check_true_when_test_passes,
    test_mutation_pass_check_false_when_test_fails,
    test_apply_cheap_wins_returns_augmented_prompt,
    test_apply_cheap_wins_rewrite_mode_for_large_edit,
]

for test_fn in ALL_TESTS:
    try:
        result = test_fn()
        print(result)
    except Exception as exc:
        import traceback
        print(f"FAIL: {test_fn.__name__} raised exception: {exc}")
        traceback.print_exc(file=sys.stderr)

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
echo "=== test_swebench_cheap_wins.sh results ==="
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
