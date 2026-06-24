#!/usr/bin/env bash
# weekend_watchdog.sh — unattended cross-round build chain monitor
#
# Monitors bob run --all in the current generation, detects round completion,
# self-heals, spawns the next generation, and repeats until bob8 is built or
# a halt gate fires.
#
# Launch (survives session end):
#   nohup tools/weekend_watchdog.sh > /dev/null 2>&1 & disown
#
# See tools/watchdog_state.json for live state.
# See weekend_chain.log for structured event log.
# See tools/HALT_REASON.txt if halted.

set -euo pipefail

# ---------------------------------------------------------------------------
# PATH: ensure node + claude CLI are visible to subprocesses. bob cli.py
# does shutil.which("claude") at every entry point; without nvm sourced
# the check fails and `bob init` errors out, halting the chain at gen
# boundaries (round 5 launch into bob8 hit this on 2026-05-19T07:19).
# Auto-discover the newest installed node bin so this survives nvm bumps.
# ---------------------------------------------------------------------------
for _node_bin in "$HOME"/.nvm/versions/node/v*/bin; do
  [[ -x "$_node_bin/claude" ]] || continue
  case ":$PATH:" in
    *":$_node_bin:"*) :;;
    *) PATH="$_node_bin:$PATH";;
  esac
done
export PATH
unset _node_bin

# ---------------------------------------------------------------------------
# Paths (everything anchored to the gen dir where watchdog was launched)
# ---------------------------------------------------------------------------
LAUNCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$LAUNCH_DIR/tools"
LOCK_FILE="$TOOLS_DIR/.weekend_watchdog.lock"
STATE_FILE="$TOOLS_DIR/watchdog_state.json"
HALT_FILE="$TOOLS_DIR/HALT_REASON.txt"
CHAIN_LOG="$LAUNCH_DIR/weekend_chain.log"

# ---------------------------------------------------------------------------
# Idempotency: single-instance lock
# ---------------------------------------------------------------------------
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[watchdog] Another instance is already running (lock: $LOCK_FILE). Exiting." >&2
  exit 0
fi
# Lock is held for the lifetime of this process via fd 9.

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log() {
  local level="$1"; shift
  local msg="$*"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "${ts} [${level}] ${msg}" >> "$CHAIN_LOG"
  # Also echo to stdout so nohup log captures it if caller redirects
  echo "${ts} [${level}] ${msg}"
}

log_info()  { log "INFO " "$@"; }
log_warn()  { log "WARN " "$@"; }
log_error() { log "ERROR" "$@"; }
log_event() { log "EVENT" "$@"; }

# ---------------------------------------------------------------------------
# Halt: write reason file and exit 0
# ---------------------------------------------------------------------------
halt() {
  local reason="$1"
  local detail="${2:-}"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

  log_event "HALT gate fired: $reason"

  # Read current state for the summary
  local gen round cost started
  gen="$(state_get current_gen)"
  round="$(state_get current_round)"
  cost="$(state_get total_cost_spent)"
  started="$(state_get started_at)"

  cat > "$HALT_FILE" <<EOF
WATCHDOG HALT — $ts
======================================================
Reason   : $reason
Detail   : ${detail:-none}

State at halt:
  current_gen    : $gen
  current_round  : $round
  total_cost_usd : \$$cost
  chain_started  : $started
  halt_time      : $ts

Chain log: $CHAIN_LOG
State file: $STATE_FILE

Action required: Review the chain log and bob.db in
  ~/dark-factory/bob${gen}/
before deciding whether to restart or continue manually.

To restart from this point (if safe):
  cd ~/dark-factory/bob${gen}
  nohup tools/weekend_watchdog.sh > /dev/null 2>&1 & disown
  (remove HALT_REASON.txt first, or it will halt again on
   the 'halt:true' gate)
EOF

  state_set "last_event" "HALTED: $reason"
  # Write halt:true into state so a re-launch also halts
  python3 - "$STATE_FILE" "halt" "true" <<'PYEOF'
import sys, json
path, key, val = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(path) as f:
        s = json.load(f)
except Exception:
    s = {}
s[key] = (val == "true")
with open(path, 'w') as f:
    json.dump(s, f, indent=2)
PYEOF

  log_error "Halt reason written to $HALT_FILE"
  exit 0
}

# ---------------------------------------------------------------------------
# State file helpers (simple JSON via python3)
# ---------------------------------------------------------------------------
state_init() {
  local gen="$1" round="$2" started="$3"
  python3 - "$STATE_FILE" "$gen" "$round" "$started" <<'PYEOF'
import sys, json
path, gen, rnd, started = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
s = {
  "current_gen": int(gen),
  "current_round": int(rnd),
  "total_cost_spent": 0.0,
  "started_at": started,
  "last_event": "watchdog started",
  "consecutive_self_heal_failures": 0,
  "halt": False
}
with open(path, 'w') as f:
    json.dump(s, f, indent=2)
PYEOF
}

state_get() {
  local key="$1"
  python3 - "$STATE_FILE" "$key" <<'PYEOF'
import sys, json
path, key = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        s = json.load(f)
    v = s.get(key, "")
    print(v if v is not None else "")
except Exception:
    print("")
PYEOF
}

state_set() {
  local key="$1" val="$2"
  python3 - "$STATE_FILE" "$key" "$val" <<'PYEOF'
import sys, json
path, key, raw = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(path) as f:
        s = json.load(f)
except Exception:
    s = {}
# coerce numeric types
try:
    s[key] = int(raw)
except ValueError:
    try:
        s[key] = float(raw)
    except ValueError:
        s[key] = raw
with open(path, 'w') as f:
    json.dump(s, f, indent=2)
PYEOF
}

state_increment() {
  local key="$1" delta="${2:-1}"
  python3 - "$STATE_FILE" "$key" "$delta" <<'PYEOF'
import sys, json
path, key, delta = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    with open(path) as f:
        s = json.load(f)
except Exception:
    s = {}
s[key] = s.get(key, 0) + delta
with open(path, 'w') as f:
    json.dump(s, f, indent=2)
PYEOF
}

# ---------------------------------------------------------------------------
# DB helpers — read-only, short timeout, never write
# ---------------------------------------------------------------------------
db_feature_counts() {
  # Prints space-separated: pending ready executing completed failed needs_human
  local db="$1"
  python3 - "$db" <<'PYEOF'
import sys, sqlite3
db = sys.argv[1]
try:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    cur = con.cursor()
    cur.execute("""
        SELECT status, COUNT(*) FROM features GROUP BY status
    """)
    rows = dict(cur.fetchall())
    con.close()
    for s in ('pending','ready','executing','completed','failed','needs_human'):
        print(rows.get(s, 0), end=' ')
    print()
except Exception as e:
    print("0 0 0 0 0 0")
PYEOF
}

db_total_cost() {
  # Sum of all sub_agent_runs.cost_usd for this db
  local db="$1"
  python3 - "$db" <<'PYEOF'
import sys, sqlite3
db = sys.argv[1]
try:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    cur = con.cursor()
    cur.execute("SELECT COALESCE(SUM(cost_usd),0) FROM sub_agent_runs")
    val = cur.fetchone()[0]
    con.close()
    print(f"{val:.4f}")
except Exception:
    print("0.0")
PYEOF
}

# ---------------------------------------------------------------------------
# Disk free check (bytes)
# ---------------------------------------------------------------------------
disk_free_bytes() {
  python3 -c "import shutil; print(shutil.disk_usage('/').free)"
}

# ---------------------------------------------------------------------------
# Gen-number helpers
# ---------------------------------------------------------------------------
gen_from_dir() {
  local dir="$1"
  local name
  name="$(basename "$dir")"
  if [[ "$name" == "bob" ]]; then
    echo 3
  elif [[ "$name" =~ ^bob([0-9]+)$ ]]; then
    echo "${BASH_REMATCH[1]}"
  else
    echo "ERROR: cannot parse gen from $name" >&2
    exit 1
  fi
}

spec_for_next_gen() {
  # Arg: next_gen (the generation being seeded, e.g. 5 when bob4→bob5)
  # spec version = next_gen - 1  (v0.4 when building bob5, v0.5 when building bob6, …)
  local next_gen="$1"
  local ver=$(( next_gen - 1 ))
  echo "examples/bootstrap_v0.${ver}.yaml"
}

# ---------------------------------------------------------------------------
# Bob PID detection
# ---------------------------------------------------------------------------
find_bob_pid() {
  local gen_dir="$1"
  local lock="$gen_dir/.bob.lock"
  if [[ -f "$lock" ]]; then
    local pid
    pid="$(cat "$lock" 2>/dev/null || true)"
    pid="${pid//[^0-9]/}"   # strip whitespace/newlines
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$pid"
      return
    fi
  fi
  # Fallback: pgrep for any bob{N} run process whose cwd is gen_dir
  # (matches both legacy `bob run` and gen-named `bob6 run`/`bob7 run`)
  local pids
  pids="$(pgrep -f "bob[0-9]+ run" 2>/dev/null || true)"
  for pid in $pids; do
    local cwd
    cwd="$(readlink -f /proc/$pid/cwd 2>/dev/null || true)"
    if [[ "$cwd" == "$gen_dir" ]]; then
      echo "$pid"
      return
    fi
  done
  echo ""  # not running
}

# ---------------------------------------------------------------------------
# Round completion detection
# ---------------------------------------------------------------------------
round_is_complete() {
  local gen_dir="$1"
  local db="$gen_dir/bob.db"

  # bob process must be gone
  local pid
  pid="$(find_bob_pid "$gen_dir")"
  if [[ -n "$pid" ]]; then
    return 1  # still running
  fi

  # No pending or ready features
  if [[ ! -f "$db" ]]; then
    return 1
  fi
  local counts
  counts="$(db_feature_counts "$db")"
  read -r pending ready _rest <<< "$counts"
  if [[ "$pending" -eq 0 && "$ready" -eq 0 ]]; then
    return 0
  fi
  return 1
}

# ---------------------------------------------------------------------------
# Detect: bob died but work remains (crash/ALL_BLOCKED). Caller decides whether
# to relaunch in same gen or move on.
# ---------------------------------------------------------------------------
bob_died_with_work() {
  local gen_dir="$1"
  local db="$gen_dir/bob.db"
  local pid
  pid="$(find_bob_pid "$gen_dir")"
  [[ -n "$pid" ]] && return 1   # still running
  [[ -f "$db" ]] || return 1
  local counts
  counts="$(db_feature_counts "$db")"
  read -r pending ready _rest <<< "$counts"
  if [[ "$pending" -gt 0 || "$ready" -gt 0 ]]; then
    return 0
  fi
  return 1
}

# ---------------------------------------------------------------------------
# Resolve which bob binary BUILDS bob<N>. Convention:
#   bob4 is built by /home/yelkhamr/dark-factory/bob/.venv/bin/bob (parent gen 3)
#   bob<N> for N>=5 is built by /home/yelkhamr/dark-factory/bob<N-1>/.venv/bin/bob
# ---------------------------------------------------------------------------
parent_bob_for_gen() {
  local gen="$1"
  if [[ "$gen" -eq 4 ]]; then
    echo "$HOME/dark-factory/bob/.venv/bin/bob"
  else
    local prev=$(( gen - 1 ))
    # Prefer gen-named binary (bobN) so `ps`/`pgrep` confirms the right
    # generation is doing the building. Fall back to legacy `bob` if the
    # parent venv predates the per-gen entry_point.
    local gen_named="$HOME/dark-factory/bob${prev}/.venv/bin/bob${prev}"
    local legacy="$HOME/dark-factory/bob${prev}/.venv/bin/bob"
    if [[ -x "$gen_named" ]]; then
      echo "$gen_named"
    else
      echo "$legacy"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Relaunch bob run --all in the CURRENT gen (post-crash recovery).
# Caller is responsible for calling self_heal.sh first.
# ---------------------------------------------------------------------------
relaunch_bob_current_gen() {
  local gen_dir="$1"
  local gen="$2"
  local round="$3"

  local bob_bin
  bob_bin="$(parent_bob_for_gen "$gen")"
  if [[ ! -x "$bob_bin" ]]; then
    log_error "Parent bob binary not found at $bob_bin"
    return 1
  fi

  local log_file="$gen_dir/round${round}_run_relaunch.log"
  log_event "Relaunching bob in $gen_dir (binary: $bob_bin)"

  # setsid -f forks into a new session so bob reparents to PID 1, not
  # back to the watchdog (the prior "( nohup ... & )" pattern left bob
  # parented to the watchdog, which then blocked in wait() and stopped
  # logging status / running halt-gate checks).
  (
    cd "$gen_dir" && \
    BOB_SNAPSHOT_TIMEOUT=1800 BOB_TEST_RUN_TIMEOUT=1800 \
    setsid -f "$bob_bin" run --all --max-cost 1000 < /dev/null >> "$log_file" 2>&1
  )

  log_event "bob relaunched in $gen_dir, log: $log_file"
  return 0
}

# ---------------------------------------------------------------------------
# Status log line (every 5 minutes)
# ---------------------------------------------------------------------------
log_status_line() {
  local gen_dir="$1" gen="$2" round="$3"
  local db="$gen_dir/bob.db"
  local cost="0.0"
  local counts="0 0 0 0 0 0"

  if [[ -f "$db" ]]; then
    counts="$(db_feature_counts "$db")"
    cost="$(db_total_cost "$db")"
  fi
  read -r pending ready executing completed failed needs_human <<< "$counts"
  local total_cost
  total_cost="$(state_get total_cost_spent)"
  log_info "status gen=$gen round=$round features=p:${pending} r:${ready} x:${executing} c:${completed} f:${failed} h:${needs_human} round_cost=\$${cost} cumulative=\$${total_cost}"
}

# ---------------------------------------------------------------------------
# Halt gate checks — call before every spawn
# ---------------------------------------------------------------------------
check_halt_gates() {
  local gen_dir="$1" gen="$2"
  local db="$gen_dir/bob.db"

  # Gate 1: halt flag in state file
  local halt_flag
  halt_flag="$(state_get halt)"
  if [[ "$halt_flag" == "True" || "$halt_flag" == "true" ]]; then
    halt "Manual halt flag set in $STATE_FILE" "Set halt:false in state file to re-enable"
  fi

  # Gate 2: HALT_REASON.txt exists (leftover from previous halt — human must clean)
  if [[ -f "$HALT_FILE" ]]; then
    # Don't re-write; just exit
    log_error "HALT_REASON.txt already exists. Remove it to continue."
    exit 0
  fi

  # Gate 3: Wall-clock > 168 hours (7 days). Raised from 72h after the
  # 3-day gate fired mid-chain with the orchestrator still healthy and
  # actively burning budget; 7d matches the durable scheduling ceiling.
  local started elapsed
  started="$(state_get started_at)"
  elapsed=$(( $(date -u +%s) - $(date -u -d "$started" +%s 2>/dev/null || echo 0) ))
  if [[ "$elapsed" -gt $((168 * 3600)) ]]; then
    halt "Wall-clock time exceeded 168 hours (7 days)" "Elapsed: ${elapsed}s since $started"
  fi

  # Gate 4: Cumulative cost > $4000
  local total_cost
  total_cost="$(state_get total_cost_spent)"
  if python3 -c "import sys; sys.exit(0 if float('${total_cost}') > 4000 else 1)" 2>/dev/null; then
    halt "Cumulative cost exceeded \$4000" "total_cost_spent=\$${total_cost}"
  fi

  # Gate 5: Disk free < 5 GB
  local free_bytes
  free_bytes="$(disk_free_bytes)"
  if [[ "$free_bytes" -lt $((5 * 1024 * 1024 * 1024)) ]]; then
    halt "Disk free below 5 GB" "free_bytes=$free_bytes"
  fi

  # Gate 6: >60% needs_human, but only after at least 5 features have completed
  # (min-sample guard prevents false positives early in a round)
  if [[ -f "$db" ]]; then
    local counts
    counts="$(db_feature_counts "$db")"
    read -r _p _r _x completed failed needs_human <<< "$counts"
    local total_done=$(( completed + failed + needs_human ))
    if [[ "$total_done" -ge 5 && "$completed" -ge 1 ]]; then
      if python3 -c "
import sys
nh = int('${needs_human}')
tot = int('${total_done}')
sys.exit(0 if (nh / tot) > 0.8 else 1)
" 2>/dev/null; then
        halt "Over 80% of features ended needs_human (sample >=5, completed >=1)" \
          "needs_human=${needs_human} total_done=${total_done} — systemic spec problem, manual review required"
      fi
    fi
  fi

  # Gate 7: 3 consecutive self-heal failures
  local shf
  shf="$(state_get consecutive_self_heal_failures)"
  if [[ "$shf" -ge 3 ]]; then
    halt "3 consecutive self-heal failures" "tools/self_heal.sh has failed $shf times in a row"
  fi
}

# ---------------------------------------------------------------------------
# Run a round: init + plan + nohup bob run --all
# ---------------------------------------------------------------------------
launch_round() {
  local gen_dir="$1"   # bob(N+1) directory
  local bob_bin="$2"  # path to bob binary from *current* gen's venv
  local spec="$3"      # relative spec path e.g. examples/bootstrap_v0.5.yaml
  local gen="$4"       # numeric gen of gen_dir (N+1)
  local round="$5"     # round number

  local log_file="$gen_dir/round${round}_run.log"

  log_event "Launching round $round in $gen_dir with spec $spec"

  # init (PROJECT_PATH = current dir; idempotent failure tolerated if already init'd)
  if [[ ! -f "$gen_dir/bob.db" ]]; then
    (cd "$gen_dir" && "$bob_bin" init .) >> "$log_file" 2>&1 || {
      log_error "bob init failed in $gen_dir"
      return 1
    }
  else
    log_info "bob.db already exists in $gen_dir — skipping init"
  fi

  # plan (--create persists features into the DB; without it, plan is a no-op preview)
  (cd "$gen_dir" && "$bob_bin" plan --create "$spec") >> "$log_file" 2>&1 || {
    log_error "bob plan --create $spec failed in $gen_dir"
    return 1
  }

  # setsid -f puts bob in its own session so it reparents to PID 1
  # (not the watchdog). nohup-in-subshell on its own left bob parented
  # to the watchdog, which then blocked in wait().
  (cd "$gen_dir" && setsid -f "$bob_bin" run --all --max-cost 1000 < /dev/null >> "$log_file" 2>&1)

  log_event "bob run --all launched in $gen_dir, log: $log_file"
  return 0
}

# ---------------------------------------------------------------------------
# Convergence detector: compare two bob databases by spec_slot set.
#
# Usage: check_convergence <db_a> <db_b>
#
# Exits 0 if the symmetric difference of completed spec_slots is empty
# (the two generations implement the same feature set). Exits 1 otherwise.
#
# Uses get_completed_spec_slots() from bob.migrations.add_spec_slot so the
# comparison is stable across `bob init` runs that mint fresh UUIDs.
# ---------------------------------------------------------------------------
check_convergence() {
  local db_a="$1"
  local db_b="$2"

  python3 - "$db_a" "$db_b" <<'PYEOF'
import sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parent.parent / "src" if False else "src")

import pathlib, sys

db_a = pathlib.Path(sys.argv[1])
db_b = pathlib.Path(sys.argv[2])

# Locate the bob package (works both in-venv and with editable install)
import importlib.util

def _find_bob_src():
    """Return the src/ directory that contains the bob package."""
    script = pathlib.Path(__file__) if pathlib.Path(__file__).exists() else pathlib.Path(sys.argv[0])
    # weekend_watchdog.sh lives in <workspace>/tools/; src/ is one level up
    candidate = script.parent.parent / "src"
    if candidate.is_dir():
        return str(candidate)
    return None

src_dir = _find_bob_src()
if src_dir and src_dir not in sys.path:
    sys.path.insert(0, src_dir)

try:
    from bob.migrations.add_spec_slot import get_completed_spec_slots
except ImportError as exc:
    print(f"[check_convergence] ERROR: cannot import get_completed_spec_slots: {exc}", file=sys.stderr)
    sys.exit(2)

slots_a = get_completed_spec_slots(db_a)
slots_b = get_completed_spec_slots(db_b)
diff = slots_a.symmetric_difference(slots_b)

if diff:
    print(f"[check_convergence] DIVERGED — {len(diff)} spec_slot(s) differ: {sorted(diff)}", file=sys.stderr)
    sys.exit(1)
else:
    print(f"[check_convergence] CONVERGED — both dbs share {len(slots_a)} completed spec_slot(s)", file=sys.stderr)
    sys.exit(0)
PYEOF
}

# ---------------------------------------------------------------------------
# Stall escalation: write STALL_ATTENTION.txt and log chain_dead_locked WARN
# ---------------------------------------------------------------------------

# Resolve escalation threshold from env: default 5, clamped to [2, 60]
_stall_escalation_count() {
  local raw="${BOB_STALL_ESCALATION_COUNT:-5}"
  python3 -c "
import sys
try:
    n = int('$raw')
except ValueError:
    n = 5
n = max(2, min(60, n))
print(n)
"
}

# Write the STALL_ATTENTION sentinel file and emit chain_dead_locked WARN log.
# Args: gen round observation_count first_observed
_write_stall_attention() {
  local gen="$1" round="$2" obs_count="$3" first_observed="$4"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

  # The sentinel lives in the *parent* gen's tools dir (bob4/tools/) so the
  # operator sees it in the directory they monitor. Resolve dynamically:
  # for gen=N the parent dir is ~/dark-factory/bob<N-1>/tools/ (or bob/tools/ for N=4).
  local parent_tools
  if [[ "$gen" -le 4 ]]; then
    parent_tools="$HOME/dark-factory/bob/tools"
  else
    local parent_gen=$(( gen - 1 ))
    parent_tools="$HOME/dark-factory/bob${parent_gen}/tools"
  fi
  mkdir -p "$parent_tools"
  local sentinel="$parent_tools/STALL_ATTENTION.txt"

  cat > "$sentinel" <<EOF
STALL_ATTENTION — chain dead-locked
=====================================
gen             : $gen
round           : $round
observation_count: $obs_count
first_observed  : $first_observed
written_at      : $ts

Operator action required:
  1. Drop spec_quality / needs_human thresholds so blocked features can
     proceed (edit the spec or lower gate values in the DB directly).
  2. Then manually relaunch:
       cd ~/dark-factory/bob${gen}
       nohup tools/weekend_watchdog.sh > /dev/null 2>&1 & disown
  3. Remove this file once handled — the watchdog will clear it
     automatically when it sees a real "Executing feature" event.

Chain log : $CHAIN_LOG
State file: $STATE_FILE
EOF

  # WARN-level structured event — distinct keyword so default greps surface it
  log_warn "chain_dead_locked gen=$gen round=$round observation_count=$obs_count first_observed=$first_observed sentinel=$sentinel"
}

# Clear the STALL_ATTENTION sentinel (called when a real Executing event is seen)
_clear_stall_attention() {
  local gen="$1"
  local parent_tools
  if [[ "$gen" -le 4 ]]; then
    parent_tools="$HOME/dark-factory/bob/tools"
  else
    local parent_gen=$(( gen - 1 ))
    parent_tools="$HOME/dark-factory/bob${parent_gen}/tools"
  fi
  local sentinel="$parent_tools/STALL_ATTENTION.txt"
  if [[ -f "$sentinel" ]]; then
    rm -f "$sentinel"
    log_info "STALL_ATTENTION.txt cleared — chain recovered (Executing feature observed) gen=$gen"
  fi
}

# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------
main() {
  log_event "weekend_watchdog starting. Launch dir: $LAUNCH_DIR"

  # Determine starting generation
  local start_gen
  start_gen="$(gen_from_dir "$LAUNCH_DIR")"

  # Initialize or resume state
  if [[ -f "$STATE_FILE" ]]; then
    local halt_flag
    halt_flag="$(state_get halt)"
    if [[ "$halt_flag" == "True" || "$halt_flag" == "true" ]]; then
      log_error "State file has halt:true. Remove $HALT_FILE and set halt:false to restart."
      exit 0
    fi
    log_info "Resuming from existing state file (gen=$(state_get current_gen) round=$(state_get current_round))"
  else
    state_init "$start_gen" 1 "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    log_event "State initialized for gen=$start_gen round=1"
  fi

  # Round tracking
  # Round 1: bob4 → bob5 (current running round, spec v0.4 goes into bob5)
  # Round 2: bob5 → bob6 (spec v0.5)
  # Round 3: bob6 → bob7 (spec v0.6)
  # Round 4: bob7 → bob8 (spec v0.7)
  # Round 5 would be bob8 → bob9 but we stop at bob8; chain ends naturally.

  local current_gen
  current_gen="$(state_get current_gen)"
  # current_gen is the gen whose bob process we are watching right now
  # (start_gen on first launch, may be higher on resume)

  local last_status_log=0
  local STATUS_INTERVAL=300  # 5 minutes

  # Stall escalation tracking (in-memory; reset when gen advances)
  local stall_count=0
  local stall_first_observed=""

  while true; do
    local now
    now="$(date -u +%s)"
    local gen_dir="$HOME/dark-factory/bob${current_gen}"
    local db="$gen_dir/bob.db"

    # ----- Halt gates (pre-iteration) -----
    check_halt_gates "$gen_dir" "$current_gen"

    # ----- Periodic status line -----
    if (( now - last_status_log >= STATUS_INTERVAL )); then
      log_status_line "$gen_dir" "$current_gen" "$(state_get current_round)"
      last_status_log=$now
    fi

    # ----- Check: any feature is currently Executing? → clear stall + reset counter -----
    if [[ -f "$db" ]]; then
      local _exec_count
      _exec_count="$(python3 - "$db" <<'PYEOF'
import sys, sqlite3
db = sys.argv[1]
try:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM features WHERE status='executing'")
    print(cur.fetchone()[0])
    con.close()
except Exception:
    print(0)
PYEOF
)"
      if [[ "$_exec_count" -gt 0 && "$stall_count" -gt 0 ]]; then
        _clear_stall_attention "$current_gen"
        stall_count=0
        stall_first_observed=""
      fi
    fi

    # ----- Check: bob crashed but work remains → self-heal + relaunch -----
    if bob_died_with_work "$gen_dir"; then
      local relaunch_count
      relaunch_count="$(state_get bob_relaunch_count_gen_${current_gen})"
      [[ -z "$relaunch_count" || "$relaunch_count" == "None" ]] && relaunch_count=0

      if [[ "$relaunch_count" -ge 5 ]]; then
        halt "bob in gen=$current_gen relaunched 5 times — chain broken" \
          "Repeated bob crashes with features still ready. Manual review needed."
      fi

      log_event "bob died with work remaining in gen=$current_gen (relaunch attempt $((relaunch_count + 1))/5)"

      # Self-heal first (clean lock, reset stuck features, prune)
      if bash "$gen_dir/tools/self_heal.sh" "$gen_dir" >> "$CHAIN_LOG" 2>&1; then
        state_set "consecutive_self_heal_failures" 0
      else
        state_increment "consecutive_self_heal_failures"
        log_warn "self_heal failed before relaunch (gen=$current_gen)"
        check_halt_gates "$gen_dir" "$current_gen"
        sleep 60
        continue
      fi

      if relaunch_bob_current_gen "$gen_dir" "$current_gen" "$(state_get current_round)"; then
        state_set "bob_relaunch_count_gen_${current_gen}" "$((relaunch_count + 1))"
        state_set "last_event" "relaunched_bob_gen_${current_gen}_attempt_$((relaunch_count + 1))"
        sleep 30  # let bob acquire lock and start
      else
        log_error "Relaunch failed for gen=$current_gen"
        sleep 60
      fi
      continue
    fi

    # ----- Check round completion -----
    if round_is_complete "$gen_dir"; then
      local round
      round="$(state_get current_round)"
      log_event "Round $round complete (gen=$current_gen)"

      # Accumulate cost from this round
      if [[ -f "$db" ]]; then
        local round_cost
        round_cost="$(db_total_cost "$db")"
        local prev_cost
        prev_cost="$(state_get total_cost_spent)"
        local new_cost
        new_cost="$(python3 -c "print(f'{float(\"${prev_cost}\") + float(\"${round_cost}\"):.4f}')")"
        state_set "total_cost_spent" "$new_cost"
        log_event "Round $round cost: \$${round_cost}. Cumulative: \$${new_cost}"
      fi

      state_set "last_event" "round_${round}_complete_gen_${current_gen}"

      # Re-check halt gates with updated cost
      check_halt_gates "$gen_dir" "$current_gen"

      # Determine next gen
      local next_gen=$(( current_gen + 1 ))
      local next_gen_dir="$HOME/dark-factory/bob${next_gen}"

      # Check if we've finished the chain (stop at bob8)
      if [[ "$current_gen" -ge 8 ]]; then
        log_event "Chain complete — bob8 is built. All rounds done."
        state_set "last_event" "chain_complete"
        exit 0
      fi

      # Check spec for next round exists in the next gen dir (after spawn it will)
      # The spec is determined by next gen's examples/ dir after rsync — we check
      # the source (current gen) since rsync copies it forward.
      local next_spec
      next_spec="$(spec_for_next_gen "$next_gen")"
      if [[ ! -f "$gen_dir/$next_spec" ]]; then
        halt "Spec for next round not found" \
          "Expected $gen_dir/$next_spec — parallel agent may not have committed it yet"
      fi

      # Guard against double-spawn on self-heal retry loops:
      # if next_gen_dir already exists, spawn already happened — jump straight to launch.
      if [[ ! -d "$next_gen_dir" ]]; then

        # ----- Self-heal -----
        log_event "Running self_heal.sh for gen=$current_gen"
        if bash "$gen_dir/tools/self_heal.sh" "$gen_dir" >> "$CHAIN_LOG" 2>&1; then
          state_set "consecutive_self_heal_failures" 0
          log_info "self_heal.sh succeeded for gen=$current_gen"
        else
          local self_heal_rc=$?
          state_increment "consecutive_self_heal_failures"
          local shf
          shf="$(state_get consecutive_self_heal_failures)"
          log_warn "self_heal.sh failed (rc=$self_heal_rc) for gen=$current_gen. consecutive_failures=$shf"
          check_halt_gates "$gen_dir" "$current_gen"
          # Below halt threshold: wait and retry
          log_warn "Self-heal below halt threshold. Waiting 60s before retry."
          state_set "last_event" "self_heal_failure_round_${round}"
          sleep 60
          continue
        fi

        # ----- Spawn next generation -----
        log_event "Spawning gen=$next_gen via spawn_next_generation.sh"
        if ! bash "$gen_dir/tools/spawn_next_generation.sh" >> "$CHAIN_LOG" 2>&1; then
          halt "spawn_next_generation.sh failed" "Tried to seed $next_gen_dir"
        fi
        log_event "gen=$next_gen seeded at $next_gen_dir"

      else
        log_info "gen=$next_gen dir already exists — skipping self-heal and spawn (resuming)"
      fi

      # ----- Launch next round -----
      local bob_bin="$gen_dir/.venv/bin/bob"
      local next_round=$(( round + 1 ))
      state_set "current_round" "$next_round"
      state_set "current_gen" "$next_gen"
      state_set "last_event" "launching_round_${next_round}_gen_${next_gen}"

      if ! launch_round "$next_gen_dir" "$bob_bin" "$next_spec" "$next_gen" "$next_round"; then
        halt "Failed to launch round $next_round" "gen=$next_gen spec=$next_spec"
      fi

      current_gen=$next_gen
      # Reset stall counter when gen advances
      stall_count=0
      stall_first_observed=""
      log_event "Now monitoring gen=$current_gen round=$next_round"

      # Give bob a few seconds to write its lock file
      sleep 10
      continue
    fi

    # ----- Not complete yet: detect spec_gate_stall and escalate if needed -----
    # A stall tick is: bob has exited cleanly (no PID, no work remaining per
    # bob_died_with_work) AND the round is not yet complete (has executing or
    # needs_human features blocking advance). This is the ALL_BLOCKED condition.
    local bob_pid
    bob_pid="$(find_bob_pid "$gen_dir")"
    if [[ -z "$bob_pid" ]]; then
      # bob not running and not "died with work" (checked above) and round
      # not complete (we're here, not in the round_is_complete branch) — stall.
      stall_count=$(( stall_count + 1 ))
      if [[ -z "$stall_first_observed" ]]; then
        stall_first_observed="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
      fi
      local stall_threshold
      stall_threshold="$(_stall_escalation_count)"
      log_info "spec_gate_stall_observed gen=$current_gen consecutive=$stall_count threshold=$stall_threshold first_observed=$stall_first_observed"
      if [[ "$stall_count" -ge "$stall_threshold" ]]; then
        _write_stall_attention "$current_gen" "$(state_get current_round)" \
          "$stall_count" "$stall_first_observed"
      fi
    fi

    sleep 60
  done
}

# Only run main when executed directly (not when sourced for function access)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
