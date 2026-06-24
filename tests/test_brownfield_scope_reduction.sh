#!/usr/bin/env bash
# Integration test: Brownfield scope correction — F-R7-611.
#
# Verifies structural acceptance criteria for:
#   (A) survey.py — vendors RepoMapper as MCP server (replaces custom impl)
#   (B) resurrection.py — deep_resurrection_scan gate for Signal-B/C
#   (C) elicit.py — AskUserQuestion enforcement + feature.mode dispatch
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

assert_file_exists() {
    local description="$1"
    local filepath="$2"
    if [[ -f "$filepath" ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: $description — file not found: $filepath")
    fi
}

assert_python_import() {
    local description="$1"
    local module="$2"
    if python3 -c "import $module" 2>/dev/null; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: $description — failed to import: $module")
    fi
}

assert_python_eval() {
    local description="$1"
    local code="$2"
    if python3 -c "$code" 2>/dev/null; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: $description — python eval failed: $code")
    fi
}

# ── File existence checks ─────────────────────────────────────────────────────

cd "$WORKSPACE_DIR"

assert_file_exists "brownfield/__init__.py exists" \
    "src/bob/brownfield/__init__.py"

assert_file_exists "brownfield/survey.py exists" \
    "src/bob/brownfield/survey.py"

assert_file_exists "brownfield/resurrection.py exists" \
    "src/bob/brownfield/resurrection.py"

assert_file_exists "brownfield/elicit.py exists" \
    "src/bob/brownfield/elicit.py"

# ── survey.py structural checks ───────────────────────────────────────────────

SURVEY_CONTENT=$(cat src/bob/brownfield/survey.py)

assert_contains "survey.py contains F-R7-611 marker" \
    "F-R7-611" "$SURVEY_CONTENT"

assert_contains "survey.py contains RepoMapper string" \
    "RepoMapper" "$SURVEY_CONTENT"

assert_contains "survey.py references MCP server" \
    "MCP" "$SURVEY_CONTENT"

assert_contains "survey.py has launch_repomapper_mcp function" \
    "launch_repomapper_mcp" "$SURVEY_CONTENT"

assert_contains "survey.py has survey.db cache reference" \
    "survey.db" "$SURVEY_CONTENT"

# Verify F-R7-611 and RepoMapper are within 200 lines of each other
MARKER_LINE=$(grep -n "F-R7-611" src/bob/brownfield/survey.py | head -1 | cut -d: -f1)
REPOMAPPER_LINE=$(grep -n "RepoMapper" src/bob/brownfield/survey.py | head -1 | cut -d: -f1)
if [[ -n "$MARKER_LINE" && -n "$REPOMAPPER_LINE" ]]; then
    DIFF=$(( REPOMAPPER_LINE - MARKER_LINE ))
    if [[ $DIFF -lt 0 ]]; then DIFF=$(( -DIFF )); fi
    if [[ $DIFF -le 200 ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: RepoMapper not within 200 lines of F-R7-611 in survey.py (diff=$DIFF)")
    fi
else
    FAIL=$((FAIL + 1))
    FAILURES+=("FAIL: Could not find F-R7-611 or RepoMapper line numbers in survey.py")
fi

# ── resurrection.py structural checks ────────────────────────────────────────

RESURRECTION_CONTENT=$(cat src/bob/brownfield/resurrection.py)

assert_contains "resurrection.py contains F-R7-611 marker" \
    "F-R7-611" "$RESURRECTION_CONTENT"

assert_contains "resurrection.py contains deep_resurrection_scan" \
    "deep_resurrection_scan" "$RESURRECTION_CONTENT"

assert_contains "resurrection.py contains Signal-A reference" \
    "Signal-A" "$RESURRECTION_CONTENT"

assert_contains "resurrection.py contains Signal-B reference" \
    "Signal-B" "$RESURRECTION_CONTENT"

assert_contains "resurrection.py contains Signal-C reference" \
    "Signal-C" "$RESURRECTION_CONTENT"

# Verify deep_resurrection_scan is within 300 lines of F-R7-611 marker
R_MARKER_LINE=$(grep -n "F-R7-611" src/bob/brownfield/resurrection.py | head -1 | cut -d: -f1)
R_GATE_LINE=$(grep -n "deep_resurrection_scan" src/bob/brownfield/resurrection.py | head -1 | cut -d: -f1)
if [[ -n "$R_MARKER_LINE" && -n "$R_GATE_LINE" ]]; then
    DIFF=$(( R_GATE_LINE - R_MARKER_LINE ))
    if [[ $DIFF -lt 0 ]]; then DIFF=$(( -DIFF )); fi
    if [[ $DIFF -le 300 ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: deep_resurrection_scan not within 300 lines of F-R7-611 in resurrection.py (diff=$DIFF)")
    fi
else
    FAIL=$((FAIL + 1))
    FAILURES+=("FAIL: Could not find F-R7-611 or deep_resurrection_scan line numbers in resurrection.py")
fi

# ── elicit.py structural checks ───────────────────────────────────────────────

ELICIT_CONTENT=$(cat src/bob/brownfield/elicit.py)

assert_contains "elicit.py contains F-R7-611 marker" \
    "F-R7-611" "$ELICIT_CONTENT"

assert_contains "elicit.py contains AskUserQuestion string" \
    "AskUserQuestion" "$ELICIT_CONTENT"

assert_contains "elicit.py contains feature.mode string" \
    "feature.mode" "$ELICIT_CONTENT"

assert_contains "elicit.py has headless mode support" \
    "headless" "$ELICIT_CONTENT"

assert_contains "elicit.py has interactive mode support" \
    "interactive" "$ELICIT_CONTENT"

# Verify AskUserQuestion within 300 lines of F-R7-611
E_MARKER_LINE=$(grep -n "F-R7-611" src/bob/brownfield/elicit.py | head -1 | cut -d: -f1)
E_AUQ_LINE=$(grep -n "AskUserQuestion" src/bob/brownfield/elicit.py | head -1 | cut -d: -f1)
if [[ -n "$E_MARKER_LINE" && -n "$E_AUQ_LINE" ]]; then
    DIFF=$(( E_AUQ_LINE - E_MARKER_LINE ))
    if [[ $DIFF -lt 0 ]]; then DIFF=$(( -DIFF )); fi
    if [[ $DIFF -le 300 ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: AskUserQuestion not within 300 lines of F-R7-611 in elicit.py (diff=$DIFF)")
    fi
else
    FAIL=$((FAIL + 1))
    FAILURES+=("FAIL: Could not find F-R7-611 or AskUserQuestion line numbers in elicit.py")
fi

# Verify feature.mode within 300 lines of F-R7-611
E_FM_LINE=$(grep -n "feature.mode" src/bob/brownfield/elicit.py | head -1 | cut -d: -f1)
if [[ -n "$E_MARKER_LINE" && -n "$E_FM_LINE" ]]; then
    DIFF=$(( E_FM_LINE - E_MARKER_LINE ))
    if [[ $DIFF -lt 0 ]]; then DIFF=$(( -DIFF )); fi
    if [[ $DIFF -le 300 ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILURES+=("FAIL: feature.mode not within 300 lines of F-R7-611 in elicit.py (diff=$DIFF)")
    fi
else
    FAIL=$((FAIL + 1))
    FAILURES+=("FAIL: Could not find F-R7-611 or feature.mode line numbers in elicit.py")
fi

# ── Python import checks ──────────────────────────────────────────────────────

assert_python_import "bob.brownfield imports cleanly" \
    "bob.brownfield"

assert_python_import "bob.brownfield.survey imports cleanly" \
    "bob.brownfield.survey"

assert_python_import "bob.brownfield.resurrection imports cleanly" \
    "bob.brownfield.resurrection"

assert_python_import "bob.brownfield.elicit imports cleanly" \
    "bob.brownfield.elicit"

# ── Behavioral checks ─────────────────────────────────────────────────────────

# ResurrectionConfig defaults deep_resurrection_scan to False
assert_python_eval "ResurrectionConfig.deep_resurrection_scan defaults to False" \
    "from bob.brownfield.resurrection import ResurrectionConfig; c = ResurrectionConfig(); assert c.deep_resurrection_scan == False"

# deep_resurrection_scan can be set to True
assert_python_eval "ResurrectionConfig.deep_resurrection_scan can be True" \
    "from bob.brownfield.resurrection import ResurrectionConfig; c = ResurrectionConfig(deep_resurrection_scan=True); assert c.deep_resurrection_scan == True"

# run_resurrection_scan without deep_resurrection_scan returns empty Signal-B/C
assert_python_eval "Signal-B and Signal-C empty when deep_resurrection_scan=False" \
    "from bob.brownfield.resurrection import run_resurrection_scan, ResurrectionConfig; r = run_resurrection_scan('/tmp', config=ResurrectionConfig(deep_resurrection_scan=False)); assert r.signal_b_exports_without_impl == []; assert r.signal_c_todo_clusters == []"

# elicit in interactive mode emits AskUserQuestion
assert_python_eval "elicit interactive mode emits AskUserQuestion" \
    "from bob.brownfield.elicit import elicit, ElicitationRequest, MODE_INTERACTIVE; r = elicit(ElicitationRequest(intent_stub='test'), feature_mode=MODE_INTERACTIVE); assert r.ask_user_question_emitted == True"

# elicit in headless mode returns candidates
assert_python_eval "elicit headless mode returns candidates" \
    "from bob.brownfield.elicit import elicit, ElicitationRequest, MODE_HEADLESS; r = elicit(ElicitationRequest(intent_stub='test'), feature_mode=MODE_HEADLESS); assert len(r.candidates) > 0"

# elicit_from_feature dispatches on feature.mode
assert_python_eval "elicit_from_feature dispatches on feature.mode" \
    "from bob.brownfield.elicit import elicit_from_feature; class F: mode='headless'; description='test'; research_notes=''; r = elicit_from_feature(F()); assert r.mode == 'headless'"

# _cache_key is deterministic
assert_python_eval "survey cache key is deterministic" \
    "from bob.brownfield.survey import _cache_key; from pathlib import Path; k1 = _cache_key(Path('/tmp'), '**/*.py', ['a', 'b']); k2 = _cache_key(Path('/tmp'), '**/*.py', ['b', 'a']); assert k1 == k2, 'cache key not deterministic across symbol order'"

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "=================================="
echo "F-R7-611 Brownfield Scope Reduction"
echo "=================================="
echo "PASSED: $PASS"
echo "FAILED: $FAIL"

if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for f in "${FAILURES[@]}"; do
        echo "  $f"
    done
    echo ""
    exit 1
fi

echo ""
echo "All assertions passed."
exit 0
