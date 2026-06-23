#!/usr/bin/env bash
# Spawn the next bob generation from the current one.
#
# Recursive build convention:
#   bob_N's .venv/bin/bob3 is what builds bob_(N+1).
#   Each generation has its own venv so fixes propagate forward
#   (bob_(N+1) inherits whatever code is in bob_N at spawn time).
#
# Usage:
#   tools/spawn_next_generation.sh            # auto-detect next number
#   tools/spawn_next_generation.sh 6          # explicit target generation
#
# Run from inside bob_N. Produces ../bob_(N+1) with .venv ready to run.

set -euo pipefail

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT_DIR="$(dirname "$CURRENT_DIR")"
CURRENT_NAME="$(basename "$CURRENT_DIR")"

if [[ "$CURRENT_NAME" == "bob" ]]; then
  CURRENT_NUM=3
elif [[ "$CURRENT_NAME" =~ ^bob([0-9]+)$ ]]; then
  CURRENT_NUM="${BASH_REMATCH[1]}"
else
  echo "ERROR: cannot infer generation from directory name '$CURRENT_NAME'" >&2
  exit 1
fi

NEXT_NUM="${1:-$((CURRENT_NUM + 1))}"
NEXT_DIR="$PARENT_DIR/bob$NEXT_NUM"

if [[ -e "$NEXT_DIR" ]]; then
  echo "ERROR: $NEXT_DIR already exists. Refusing to overwrite." >&2
  exit 1
fi

PY="${PYTHON:-python3}"

echo "==> Seeding bob$NEXT_NUM from $CURRENT_NAME (current generation: $CURRENT_NUM)"
rsync -a \
  --exclude='.venv/' \
  --exclude='bob3.db' \
  --exclude='bob3.db-shm' \
  --exclude='bob3.db-wal' \
  --exclude='.bob3.lock' \
  --exclude='*.log' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='.claude/' \
  --exclude='.coverage' \
  --exclude='htmlcov/' \
  --exclude='dist/' \
  --exclude='build/' \
  --exclude='*.egg-info/' \
  "$CURRENT_DIR/" "$NEXT_DIR/"

echo "==> Creating venv at $NEXT_DIR/.venv"
"$PY" -m venv "$NEXT_DIR/.venv"

echo "==> Ensuring pyproject.toml has gen-named entry_point bob$NEXT_NUM"
python3 - "$NEXT_DIR/pyproject.toml" "$NEXT_NUM" <<'PYEOF'
import sys, re
from pathlib import Path
p = Path(sys.argv[1]); n = sys.argv[2]
t = p.read_text()
key = f'bob{n} = "bob3.cli:main"'
if key in t:
    sys.exit(0)
# Append the new key after the bob3 line, without disturbing siblings.
# The old regex stripped EVERY bobN= line including bob3 itself, which
# erased the anchor and wiped [project.scripts] (observed bob9 seed).
if 'bob3 = "bob3.cli:main"' in t:
    t = t.replace('bob3 = "bob3.cli:main"',
                  f'bob3 = "bob3.cli:main"\n{key}')
else:
    # If bob3 anchor missing, recreate the whole [project.scripts] block.
    t = re.sub(r'\[project\.scripts\][^\[]*',
               f'[project.scripts]\nbob3 = "bob3.cli:main"\n{key}\n\n', t,
               count=1)
p.write_text(t)
PYEOF

echo "==> Installing bob3 (editable) + dev extras into bob$NEXT_NUM venv"
"$NEXT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$NEXT_DIR/.venv/bin/pip" install --quiet -e "$NEXT_DIR[dev]"

echo "==> Smoke test"
"$NEXT_DIR/.venv/bin/bob$NEXT_NUM" --version || true

echo "==> Re-initializing bob$NEXT_NUM project metadata (fixes stale name/spec_path from rsync)"
# spawn_next_generation.sh rsync copies the parent DB which still records the
# parent's name and spec_path.  Running bob3 init with the correct --name and
# --spec rewrites those project-row fields so bob{NEXT_NUM}/bob3.db reflects
# the real generation.  The init command detects the existing row and UPDATE-s
# rather than inserting a duplicate.
SPEC_FOR_NEXT="$NEXT_DIR/examples/bootstrap_v0.$CURRENT_NUM.yaml"
if [[ -f "$SPEC_FOR_NEXT" ]]; then
  "$NEXT_DIR/.venv/bin/bob$NEXT_NUM" init "$NEXT_DIR" \
    --name "bob$NEXT_NUM" \
    --spec "$SPEC_FOR_NEXT" \
    || echo "WARNING: bob$NEXT_NUM init returned non-zero; project metadata may be stale" >&2
else
  "$NEXT_DIR/.venv/bin/bob$NEXT_NUM" init "$NEXT_DIR" \
    --name "bob$NEXT_NUM" \
    || echo "WARNING: bob$NEXT_NUM init returned non-zero; project metadata may be stale" >&2
  echo "  (spec file $SPEC_FOR_NEXT not found; skipping --spec flag)" >&2
fi

echo "==> Inheriting parent-gen DB provenance into bob$NEXT_NUM"
# Run the migration first so the new DB has the required columns, then
# stamp child features whose spec_slot matches a completed/needs_human/
# regression row in the parent DB (feature e1b5bacb — F-R7-420 prereq).
"$NEXT_DIR/.venv/bin/python" - "$CURRENT_DIR/bob3.db" "$NEXT_DIR/bob3.db" <<'PYEOF'
import sys
from pathlib import Path

parent_db = Path(sys.argv[1])
child_db = Path(sys.argv[2])

if not child_db.exists():
    print(f"  Child DB {child_db} not found; skipping inheritance (bob3 init not yet run?)")
    sys.exit(0)

if not parent_db.exists():
    print(f"  Parent DB {parent_db} not found; skipping inheritance")
    sys.exit(0)

# Ensure the child DB has the provenance columns before stamping.
import os
os.environ["BOB3_DATABASE_PATH"] = str(child_db)
from bob3.migrations.add_parent_gen_inheritance_fields import upgrade
upgrade(db_path=child_db)

from bob3.orchestrator.parent_gen_inheritance import inherit_from_parent_db
result = inherit_from_parent_db(parent_db_path=parent_db, child_db_path=child_db)
print(f"  stamped={result.stamped} skipped_no_slot={result.skipped_no_slot} skipped_no_parent_match={result.skipped_no_parent_match}")
PYEOF

cat <<EOF

✓ bob$NEXT_NUM is ready at $NEXT_DIR

Next steps to drive bob$((NEXT_NUM + 1)) from bob$NEXT_NUM:
  cd $NEXT_DIR
  source .venv/bin/activate
  bob3 init                      # initialize the workspace
  bob3 plan examples/<spec>.yaml # add features for this round
  bob3 run --all --max-cost 1000

When that round completes, spawn the next generation:
  $NEXT_DIR/tools/spawn_next_generation.sh
EOF
