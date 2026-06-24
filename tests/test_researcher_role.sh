#!/usr/bin/env bash
# Integration test for F-R7-604: Research-as-documentarian sub-agent (hide-the-ticket pattern)
#
# Verifies:
#   1. src/bob/agents/roles.py exists and contains required markers.
#   2. The researcher role has hide_intent=True.
#   3. research_notes_path() returns a path under .bob/features/<id>/.
#   4. should_skip_research() returns False when notes are absent and True when cached.
#   5. build_researcher_prompt() excludes intent text.

set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROLES_PY="$WORKSPACE/src/bob/agents/roles.py"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }

# --- AC-0: file exists ---
[ -f "$ROLES_PY" ] && pass "roles.py exists" || fail "roles.py not found at $ROLES_PY"

# --- AC-1: F-R7-604 marker present ---
grep -q "F-R7-604" "$ROLES_PY" && pass "F-R7-604 marker found" || fail "F-R7-604 marker missing"

# --- AC-2: 'researcher' present ---
grep -q "researcher" "$ROLES_PY" && pass "'researcher' found" || fail "'researcher' missing"

# --- AC-3: hide_intent present ---
grep -q "hide_intent" "$ROLES_PY" && pass "'hide_intent' found" || fail "'hide_intent' missing"

# --- AC-4: research_notes present ---
grep -q "research_notes" "$ROLES_PY" && pass "'research_notes' found" || fail "'research_notes' missing"

# --- AC-5: researcher has hide_intent=True ---
python3 - <<'EOF'
import sys
sys.path.insert(0, "src")
from bob.agents.roles import RESEARCHER, get_role
assert RESEARCHER.hide_intent is True, "RESEARCHER.hide_intent must be True"
role = get_role("researcher")
assert role.hide_intent is True, "get_role('researcher').hide_intent must be True"
print("PASS: RESEARCHER.hide_intent is True")
EOF

# --- AC-6: research_notes_path returns correct path ---
python3 - <<'EOF'
import sys, tempfile, pathlib
sys.path.insert(0, "src")
from bob.agents.roles import research_notes_path
with tempfile.TemporaryDirectory() as tmp:
    p = research_notes_path("test-feat-id", workspace=tmp)
    expected = pathlib.Path(tmp) / ".bob" / "features" / "test-feat-id" / "research_notes.md"
    assert p == expected, f"Expected {expected}, got {p}"
print("PASS: research_notes_path returns correct path")
EOF

# --- AC-7: should_skip_research returns False when file absent ---
python3 - <<'EOF'
import sys, tempfile
sys.path.insert(0, "src")
from bob.agents.roles import should_skip_research
with tempfile.TemporaryDirectory() as tmp:
    result = should_skip_research("feat-x", "sha123", "src/**", workspace=tmp)
    assert result is False, "should_skip_research must return False when notes absent"
print("PASS: should_skip_research returns False when notes absent")
EOF

# --- AC-8: should_skip_research returns True when cache matches ---
python3 - <<'EOF'
import sys, tempfile, pathlib
sys.path.insert(0, "src")
from bob.agents.roles import research_notes_path, should_skip_research
with tempfile.TemporaryDirectory() as tmp:
    notes = research_notes_path("feat-y", workspace=tmp)
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("---\nsurvey_sha: abc\npath_glob: src/**\n---\n")
    result = should_skip_research("feat-y", "abc", "src/**", workspace=tmp)
    assert result is True, "should_skip_research must return True when cache matches"
print("PASS: should_skip_research returns True on cache hit")
EOF

# --- AC-9: build_researcher_prompt excludes intent text ---
python3 - <<'EOF'
import sys
sys.path.insert(0, "src")
from bob.agents.roles import build_researcher_prompt
prompt = build_researcher_prompt("src/bob/orchestrator/**", ["run_loop", "disk_reconciler"])
assert "intent" not in prompt.lower(), "Researcher prompt must not mention 'intent'"
assert "ticket" not in prompt.lower(), "Researcher prompt must not mention 'ticket'"
assert "src/bob/orchestrator/**" in prompt, "Path glob must appear in researcher prompt"
assert "research_notes" in prompt, "research_notes must be referenced in researcher prompt"
print("PASS: build_researcher_prompt is hide-the-ticket compliant")
EOF

echo ""
echo "All integration tests passed."
