#!/usr/bin/env bash
# weekend_status.sh — one-screen status for the running weekend chain.
# Safe to run while bob is active (read-only db access with timeout).
#
# Usage:
#   bash tools/weekend_status.sh                # auto-detect current gen
#   bash tools/weekend_status.sh <gen_dir>      # force a specific gen
#
# The chain has two distinct directories:
#   CHAIN_HOME — where the watchdog state + chain log + halt file live
#                (always bob4, regardless of which gen is being built).
#   GEN_DIR    — the bob_N currently being built. Has bob.db, .bob.lock,
#                a running orchestrator process. Advances bob4→bob5→… as
#                the chain progresses.
#
# Discovery order for GEN_DIR (when not passed explicitly):
#   1. tools/watchdog_state.json → current_gen
#   2. Running orchestrator process (pgrep 'bob[0-9]+ run --all') → cwd
#   3. Highest-numbered bob<N>/ sibling with a bob.db

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHAIN_HOME="$(dirname "$SCRIPT_DIR")"   # bob4/
PARENT_DIR="$(dirname "$CHAIN_HOME")"   # dark-factory/
STATE_FILE="$CHAIN_HOME/tools/watchdog_state.json"
CHAIN_LOG="$CHAIN_HOME/weekend_chain.log"
HALT_FILE="$CHAIN_HOME/tools/HALT_REASON.txt"

# ── Discover GEN_DIR (current bob being built) ───────────────────────────────
discover_gen_dir() {
    # 1. watchdog_state.json
    if [[ -f "$STATE_FILE" ]]; then
        local gen
        gen="$(python3 -c "
import json, sys
try:
    s = json.load(open('$STATE_FILE'))
    g = s.get('current_gen')
    if g: print(g)
except Exception: pass
" 2>/dev/null)"
        if [[ -n "$gen" && -d "$PARENT_DIR/bob$gen" ]]; then
            echo "$PARENT_DIR/bob$gen"; return
        fi
    fi

    # 2. running orchestrator → cwd
    local pid cwd
    pid="$(pgrep -f 'bob[0-9]+ run --all' 2>/dev/null | head -n 1 || true)"
    if [[ -n "$pid" ]]; then
        cwd="$(readlink -f /proc/$pid/cwd 2>/dev/null || true)"
        if [[ -n "$cwd" && -f "$cwd/bob.db" ]]; then
            echo "$cwd"; return
        fi
    fi

    # 3. highest-numbered bob<N>/ with a bob.db
    local best="" best_n=-1
    for d in "$PARENT_DIR"/bob[0-9]*/; do
        [[ -f "$d/bob.db" ]] || continue
        local n="${d##*/bob}"; n="${n%/}"
        [[ "$n" =~ ^[0-9]+$ ]] || continue
        if (( n > best_n )); then best_n=$n; best="${d%/}"; fi
    done
    [[ -n "$best" ]] && { echo "$best"; return; }

    # 4. last-resort fallback
    echo "$CHAIN_HOME"
}

GEN_DIR="${1:-$(discover_gen_dir)}"
DB_FILE="$GEN_DIR/bob.db"
LOCK_FILE="$GEN_DIR/.bob.lock"
GEN_NAME="$(basename "$GEN_DIR")"

HR="──────────────────────────────────────────────────────────"

echo "$HR"
echo "  BOB WEEKEND STATUS  —  $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "$HR"

# ── Active generation + round ────────────────────────────────────────────────
echo ""
echo "GENERATION / ROUND"
echo "  Chain home : $CHAIN_HOME"
echo "  Current gen: $GEN_NAME  ($GEN_DIR)"

if [[ -f "$STATE_FILE" ]]; then
    python3 - "$STATE_FILE" <<'PYEOF' 2>/dev/null || true
import json, sys
try:
    s = json.load(open(sys.argv[1]))
    g = s.get('current_gen'); r = s.get('current_round')
    le = s.get('last_event'); halt = s.get('halt')
    print(f"  Watchdog   : gen={g} round={r} last_event={le}")
    if halt:
        print(f"  Watchdog   : HALT  reason={s.get('halt_reason')!r}")
except Exception as e:
    print(f"  Watchdog   : [state read error: {e}]")
PYEOF
fi

if [[ -f "$DB_FILE" ]]; then
    LAST_DB="$(python3 -c "
import sqlite3
try:
    con = sqlite3.connect('$DB_FILE', timeout=5)
    cur = con.cursor()
    cur.execute(\"SELECT MAX(updated_at) FROM features WHERE status != 'pending'\")
    row = cur.fetchone()
    print(row[0] if row and row[0] else 'n/a')
    con.close()
except Exception as e:
    print(f'err:{e}')
" 2>/dev/null || echo "err")"
    echo "  Last DB activity : $LAST_DB"
fi

# ── Process state ────────────────────────────────────────────────────────────
echo ""
echo "PROCESS STATE"

# Only count the orchestrator binary actually running a round.
# Matches: /home/.../bob<N>/.venv/bin/bob<N> run --all ...
ORCH_PIDS="$(pgrep -af 'bob[0-9]+ run --all' 2>/dev/null \
    | grep -v -E 'grep|pgrep|weekend_status' \
    | awk '{print $1}' | tr '\n' ' ' || true)"
if [[ -n "$ORCH_PIDS" ]]; then
    echo "  orchestrator    : YES  (pids: $ORCH_PIDS)"
    # Show cwd of first pid to confirm it's the current gen
    FIRST_PID="${ORCH_PIDS%% *}"
    if [[ -n "$FIRST_PID" ]]; then
        ORCH_CWD="$(readlink -f /proc/$FIRST_PID/cwd 2>/dev/null || echo '?')"
        echo "                    pid $FIRST_PID cwd: $ORCH_CWD"
    fi
else
    echo "  orchestrator    : no"
fi

WATCHDOG_PIDS="$(pgrep -af 'weekend_watchdog' 2>/dev/null \
    | grep -v grep | awk '{print $1}' | tr '\n' ' ' || true)"
if [[ -n "$WATCHDOG_PIDS" ]]; then
    echo "  watchdog        : YES  (pids: $WATCHDOG_PIDS)"
else
    echo "  watchdog        : no"
fi

# Only count MCP servers whose cwd is the current gen — old gens often leave
# orphaned MCPs that aren't relevant to current build state.
MCP_PIDS=""
for pid in $(pgrep -f 'bob\.memory_mcp' 2>/dev/null); do
    cwd="$(readlink -f /proc/$pid/cwd 2>/dev/null || true)"
    if [[ "$cwd" == "$GEN_DIR" ]]; then
        MCP_PIDS+="$pid "
    fi
done
MCP_PIDS="${MCP_PIDS% }"
MCP_OTHER_COUNT="$(pgrep -cf 'bob\.memory_mcp' 2>/dev/null || echo 0)"
if [[ -n "$MCP_PIDS" ]]; then
    echo "  MCP (this gen)  : YES  (pids: $MCP_PIDS)"
else
    echo "  MCP (this gen)  : none"
fi
if [[ "$MCP_OTHER_COUNT" -gt "$(echo "$MCP_PIDS" | wc -w)" ]]; then
    OTHER=$((MCP_OTHER_COUNT - $(echo "$MCP_PIDS" | wc -w)))
    echo "  MCP (other gens): $OTHER (orphans from earlier gens, not counted)"
fi

if [[ -f "$LOCK_FILE" ]]; then
    LOCK_PID="$(cat "$LOCK_FILE" 2>/dev/null || echo '?')"
    if [[ "$LOCK_PID" =~ ^[0-9]+$ ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
        echo "  .bob.lock      : held by pid $LOCK_PID (alive)"
    else
        echo "  .bob.lock      : STALE (pid $LOCK_PID gone) — needs self_heal"
    fi
else
    echo "  .bob.lock      : free"
fi

# ── Feature counts by status ─────────────────────────────────────────────────
echo ""
echo "FEATURE STATUS ($GEN_NAME/bob.db)"

python3 - "$DB_FILE" <<'PYEOF' 2>/dev/null || echo "  [db unavailable]"
import sqlite3, sys
db = sys.argv[1]
try:
    con = sqlite3.connect(db, timeout=5)
    cur = con.cursor()
    cur.execute("SELECT status, COUNT(*) FROM features GROUP BY status ORDER BY status")
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM features")
    total = cur.fetchone()[0]
    con.close()
    for status, cnt in rows:
        bar = "█" * min(cnt, 30)
        print(f"  {status:<14} {cnt:>4}  {bar}")
    print(f"  {'TOTAL':<14} {total:>4}")
except Exception as e:
    print(f"  [error: {e}]")
PYEOF

# ── Last 5 events from weekend_chain.log ─────────────────────────────────────
echo ""
echo "RECENT CHAIN EVENTS (last 5)"
if [[ -f "$CHAIN_LOG" ]]; then
    tail -n 5 "$CHAIN_LOG" | while IFS= read -r line; do
        echo "  $line"
    done
else
    echo "  [no chain log at $CHAIN_LOG]"
fi

# ── Cumulative cost (current gen only + chain-wide from watchdog state) ──────
echo ""
echo "COST"
python3 - "$DB_FILE" <<'PYEOF' 2>/dev/null || echo "  [db unavailable]"
import sqlite3, sys
db = sys.argv[1]
try:
    con = sqlite3.connect(db, timeout=5)
    cur = con.cursor()
    cur.execute("SELECT SUM(total_cost_usd) FROM projects")
    proj_cost = cur.fetchone()[0] or 0.0
    try:
        cur.execute("SELECT SUM(cost_usd) FROM sub_agent_runs WHERE cost_usd IS NOT NULL")
        run_cost = cur.fetchone()[0] or 0.0
    except Exception:
        run_cost = None
    con.close()
    print(f"  this gen projects.total_cost_usd : ${proj_cost:.4f}")
    if run_cost is not None:
        print(f"  this gen sub_agent_runs sum      : ${run_cost:.4f}")
except Exception as e:
    print(f"  [error: {e}]")
PYEOF

if [[ -f "$STATE_FILE" ]]; then
    python3 - "$STATE_FILE" <<'PYEOF' 2>/dev/null || true
import json, sys
try:
    s = json.load(open(sys.argv[1]))
    t = s.get('total_cost_spent')
    if t is not None:
        print(f"  chain cumulative (watchdog)      : ${float(t):.4f}")
except Exception: pass
PYEOF
fi

# ── Time since chain started ─────────────────────────────────────────────────
echo ""
echo "CHAIN START TIME"
python3 - "$STATE_FILE" "$DB_FILE" <<'PYEOF' 2>/dev/null || echo "  [unavailable]"
import json, sqlite3, sys
from datetime import datetime, timezone
state_file, db = sys.argv[1], sys.argv[2]
started = None
try:
    s = json.load(open(state_file))
    started = s.get('started_at')
except Exception: pass
if not started:
    try:
        con = sqlite3.connect(db, timeout=5)
        cur = con.cursor()
        cur.execute("SELECT MIN(created_at) FROM projects")
        row = cur.fetchone()
        if row and row[0]: started = row[0]
        con.close()
    except Exception: pass
if started:
    created = datetime.fromisoformat(started.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    delta = now - created
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    print(f"  Started : {started}")
    print(f"  Elapsed : {h}h {m}m {s}s")
else:
    print("  [no start time found]")
PYEOF

# ── Disk and memory ──────────────────────────────────────────────────────────
echo ""
echo "RESOURCES"
df -h "$GEN_DIR" | awk 'NR==2{printf "  Disk  used=%-6s free=%-6s total=%s (mount: %s)\n",$3,$4,$2,$6}'
free -h | awk '/^Mem:/{printf "  Memory total=%-6s used=%-6s free=%s\n",$2,$3,$4}'

# ── HALT_REASON.txt ──────────────────────────────────────────────────────────
echo ""
if [[ -f "$HALT_FILE" ]]; then
    echo "HALT REASON  *** CHAIN IS STOPPED ***  ($HALT_FILE)"
    while IFS= read -r line; do
        echo "  $line"
    done < "$HALT_FILE"
else
    echo "HALT REASON : none (chain appears active)"
fi

echo ""
echo "$HR"
