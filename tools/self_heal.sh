#!/usr/bin/env bash
# self_heal.sh — weekend watchdog self-healing routine for bob3 orchestrator.
# Usage: bash tools/self_heal.sh <gen_dir>
# Returns: 0 healthy/progress-possible, 1 hard-blocked.

set -euo pipefail

GEN_DIR="${1:?Usage: self_heal.sh <gen_dir>}"
LOG_FILE="$GEN_DIR/tools/self_heal.log"
LOCK_FILE="$GEN_DIR/.bob3.lock"
DB_FILE="$GEN_DIR/bob3.db"
HEAL_ATTEMPTS_FILE="$GEN_DIR/tools/heal_attempts.json"

mkdir -p "$GEN_DIR/tools"

log() {
    local msg="$*"
    local ts
    ts="$(date '+%Y-%m-%dT%H:%M:%S')"
    echo "[$ts] $msg" | tee -a "$LOG_FILE"
}

log "=== self_heal.sh start (gen_dir=$GEN_DIR) ==="

# ── 0. Stale-bytecode guard ───────────────────────────────────────────────────
# If any orchestrator .py file is newer than the previous process's start time,
# the running process held pre-edit bytecode.  Log each stale file so operators
# can correlate with their edits.
STALE_CHECK_OUT=""
STALE_CHECK_OUT="$(python3 - "$GEN_DIR" "$LOCK_FILE" <<'STALE_PYEOF'
import sys, pathlib, logging
gen_dir = pathlib.Path(sys.argv[1])
lock_file = pathlib.Path(sys.argv[2])

import importlib.util, os
# Add the src path so we can import the guard even before pip install
src_path = gen_dir / "src"
if src_path.is_dir():
    sys.path.insert(0, str(src_path))

try:
    from bob3.orchestrator.stale_bytecode_guard import check_freshness
    stale = check_freshness(gen_dir, lock_file=lock_file)
    for f in stale:
        print(f"STALE-BYTECODE: {f} is newer than process start — relaunch required")
    if stale:
        sys.exit(10)
except ImportError as e:
    print(f"STALE-BYTECODE-SKIP: guard module not importable ({e})", flush=True)
except Exception as e:
    print(f"STALE-BYTECODE-ERROR: {e}", flush=True)
STALE_PYEOF
)" || STALE_EXIT=$?
STALE_EXIT="${STALE_EXIT:-0}"

while IFS= read -r line; do
    [[ -n "$line" ]] && log "$line"
done <<< "$STALE_CHECK_OUT"

if [[ $STALE_EXIT -eq 10 ]]; then
    log "STALE-BYTECODE: stale source files detected — process must be relaunched"
fi

# ── 1. Stale lock cleanup ─────────────────────────────────────────────────────
# Extract PID from lock file (supports both old plain-PID and new JSON format)
if [[ -f "$LOCK_FILE" ]]; then
    LOCK_CONTENT="$(cat "$LOCK_FILE" 2>/dev/null || true)"
    # Try JSON format first: {"pid": N, "started_at": ...}
    LOCK_PID="$(python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    print(d['pid'])
except Exception:
    pass
" <<< "$LOCK_CONTENT" 2>/dev/null || true)"
    # Fall back to plain-PID format (old lock files contain just the PID number)
    if [[ -z "$LOCK_PID" ]]; then
        LOCK_PID="$LOCK_CONTENT"
    fi
    if [[ -z "$LOCK_PID" ]]; then
        log "LOCK: file is empty, removing $LOCK_FILE"
        rm -f "$LOCK_FILE"
    elif kill -0 "$LOCK_PID" 2>/dev/null; then
        log "LOCK: pid $LOCK_PID still alive — lock is valid, skipping"
    else
        log "LOCK: pid $LOCK_PID is gone — removing stale $LOCK_FILE"
        rm -f "$LOCK_FILE"
    fi
else
    log "LOCK: no lock file present"
fi

# ── 2. Reap zombie MCP processes (adopted by init, parent dead) ───────────────
ZOMBIE_PIDS="$(pgrep -P 1 -fa "bob3.memory_mcp" 2>/dev/null | awk '{print $1}' || true)"
if [[ -n "$ZOMBIE_PIDS" ]]; then
    log "MCP: found zombie MCP pids: $ZOMBIE_PIDS — sending SIGTERM"
    for pid in $ZOMBIE_PIDS; do
        kill -TERM "$pid" 2>/dev/null && log "MCP: SIGTERM → $pid" || log "MCP: SIGTERM failed for $pid (already gone?)"
    done
    sleep 2
    # Second pass: SIGKILL survivors
    for pid in $ZOMBIE_PIDS; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -KILL "$pid" 2>/dev/null && log "MCP: SIGKILL → $pid" || true
        fi
    done
else
    log "MCP: no zombie MCP processes found"
fi

# ── Python helper: DB operations with timeout ─────────────────────────────────
DB_PYTHON() {
    python3 - "$DB_FILE" "$HEAL_ATTEMPTS_FILE" <<'PYEOF'
import sys, sqlite3, json, os, pathlib

db_path = sys.argv[1]
heal_file = sys.argv[2]

try:
    con = sqlite3.connect(db_path, timeout=5)
    con.execute("PRAGMA journal_mode=WAL")
    cur = con.cursor()

    # ── 3. Reset executing → ready ────────────────────────────────────────────
    cur.execute("SELECT id, name FROM features WHERE status='executing'")
    stuck = cur.fetchall()
    for fid, fname in stuck:
        cur.execute(
            "UPDATE features SET status='ready', updated_at=datetime('now') WHERE id=?",
            (fid,),
        )
        print(f"EXEC_RESET: {fname!r} ({fid}) executing→ready")
    if not stuck:
        print("EXEC_RESET: no features stuck in executing")

    # ── 4. needs_human: reset ≤1 prior attempt, leave ≥2 ────────────────────
    # Load heal_attempts tracker
    if os.path.exists(heal_file):
        with open(heal_file) as f:
            attempts = json.load(f)
    else:
        attempts = {}

    cur.execute("SELECT id, name FROM features WHERE status='needs_human'")
    nh_rows = cur.fetchall()
    for fid, fname in nh_rows:
        count = attempts.get(fid, 0)
        if count < 2:
            cur.execute(
                "UPDATE features SET status='ready', updated_at=datetime('now') WHERE id=?",
                (fid,),
            )
            attempts[fid] = count + 1
            print(f"NH_RESET: {fname!r} ({fid}) needs_human→ready (attempt {count+1})")
        else:
            print(f"NH_SKIP: {fname!r} ({fid}) at {count} attempts — leaving needs_human (real defect)")

    if not nh_rows:
        print("NH_RESET: no features in needs_human")

    con.commit()
    con.close()

    # Persist updated attempts
    pathlib.Path(heal_file).parent.mkdir(parents=True, exist_ok=True)
    with open(heal_file, "w") as f:
        json.dump(attempts, f, indent=2)

    # ── Check if progress is possible ────────────────────────────────────────
    con2 = sqlite3.connect(db_path, timeout=5)
    cur2 = con2.cursor()
    cur2.execute("SELECT COUNT(*) FROM features WHERE status IN ('ready','pending','executing')")
    actionable = cur2.fetchone()[0]
    cur2.execute("SELECT COUNT(*) FROM features WHERE status = 'completed'")
    completed = cur2.fetchone()[0]
    cur2.execute("SELECT COUNT(*) FROM features")
    total = cur2.fetchone()[0]
    con2.close()
    print(f"DB_STATUS: actionable={actionable} completed={completed} total={total}")
    # Round-complete success: every feature completed. Caller (watchdog) should
    # proceed to spawn next generation. Do NOT treat as dead-lock.
    if total > 0 and completed == total:
        sys.exit(0)
    # True dead-lock: nothing actionable AND not all completed (rest are
    # needs_human / failed and cannot make progress without intervention).
    if actionable == 0:
        sys.exit(2)
except sqlite3.DatabaseError as e:
    print(f"DB_ERROR: {e}", file=sys.stderr)
    sys.exit(3)
PYEOF
}

# Capture Python output; log each line; check for hard-block exit codes
PYOUT=0
DB_OUTPUT="$(DB_PYTHON 2>&1)" || PYOUT=$?

while IFS= read -r line; do
    [[ -n "$line" ]] && log "$line"
done <<< "$DB_OUTPUT"

if [[ $PYOUT -eq 3 ]]; then
    log "HARD-BLOCK: bob3.db is corrupt or unreadable"
    exit 1
fi

ALL_LOCKED=false
if [[ $PYOUT -eq 2 ]]; then
    log "HARD-BLOCK: all features are dead-locked (none actionable, none completeable)"
    ALL_LOCKED=true
fi

# ── 5. Cache/artifact cleanup ─────────────────────────────────────────────────
log "CLEANUP: removing __pycache__, .pytest_cache, htmlcov, .coverage"
# Use find with pruning to skip .venv
find "$GEN_DIR" \
    -path "$GEN_DIR/.venv" -prune -o \
    -name '__pycache__' -type d -print \
    | grep -v '\.venv' \
    | xargs rm -rf 2>/dev/null || true

rm -rf \
    "$GEN_DIR/.pytest_cache" \
    "$GEN_DIR/htmlcov" \
    "$GEN_DIR/.coverage" \
    2>/dev/null || true
log "CLEANUP: done"

# ── 6. Disk space check (<5 GB = hard block) ─────────────────────────────────
FREE_KB="$(df -k "$GEN_DIR" | awk 'NR==2{print $4}')"
FREE_GB_TENTHS=$(( FREE_KB / 102400 ))  # tenths of a GB
log "DISK: free = $((FREE_KB / 1024 / 1024)) GB (${FREE_KB} kB)"
if [[ $FREE_KB -lt 5242880 ]]; then   # 5*1024*1024 kB = 5 GB
    log "HARD-BLOCK: disk free below 5 GB threshold"
    exit 1
fi

# ── Final verdict ─────────────────────────────────────────────────────────────
if $ALL_LOCKED; then
    log "=== self_heal.sh complete — HARD-BLOCKED (all features dead-locked) ==="
    exit 1
fi

log "=== self_heal.sh complete — healthy ==="
exit 0
