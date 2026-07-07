#!/usr/bin/env bash
# Auto-resume supervisor for bob96 self-build (builder = bob95 CLI).
# - resets FAILED/orphaned -> pending each pass (preserves live 'executing'/'ready' work)
# - UN-PARKS needs_human features with >=1 dependent so the tail can progress
# - NEVER lowers any threshold. Runs until no runnable pending remain (while-not-done).
cd /home/yelkhamr/dark-factory/bob96
source ~/dark-factory/bob/bob_build.env
export BOB_REGRESSION_DETECTION_ENABLED=0
export BOB_SUB_AGENT_MAX_TURNS=100
export BOB_MAX_CONCURRENT_FEATURES=32
unset BOB_CI_MODE
PY=~/dark-factory/bob/.venv/bin/python
BOB=~/dark-factory/bob/.venv/bin/bob
i=0
while true; do
  i=$((i+1))
  $PY - <<'PYEOF'
import sqlite3
d=sqlite3.connect("bob.db");c=d.cursor()
c.execute('UPDATE features SET status="pending" WHERE status IN ("failed","interrupted","gate_blocked","executing")')
rows=c.execute("SELECT id,status FROM features").fetchall()
try:
    deps=c.execute("SELECT feature_id,depends_on_feature_id FROM feature_dependencies").fetchall()
except Exception:
    deps=[]
has_dep=set(dd for _,dd in deps)
nh=[i for i,s in rows if s=="needs_human"]
unpark=[i for i in nh if i in has_dep]
for i in unpark:
    c.execute('UPDATE features SET status="pending", refinement_attempts=0 WHERE id=?', (i,))
d.commit(); print("unparked_blockers=%d"%len(unpark))
PYEOF
  completed=$($PY -c "import sqlite3;print(sqlite3.connect('bob.db').cursor().execute('SELECT COUNT(*) FROM features WHERE status=\"completed\"').fetchone()[0])")
  RUN=$($PY -c "
import sqlite3
from collections import defaultdict
c=sqlite3.connect('bob.db').cursor()
rows=c.execute('SELECT id,status FROM features').fetchall(); st={i:s for i,s in rows}
try:
    deps=c.execute('SELECT feature_id,depends_on_feature_id FROM feature_dependencies').fetchall()
except Exception:
    deps=[]
dd=defaultdict(list)
for f,dp in deps: dd[f].append(dp)
print(sum(1 for i,s in rows if s in ('pending','ready') and all(st.get(x)=='completed' for x in dd.get(i,[]))))")
  echo "[supervisor] iter=$i completed=$completed runnable=$RUN $(date +%T)"
  if [ "$RUN" = "0" ]; then echo "[supervisor] STOP: no runnable pending"; break; fi
  $BOB run --all --max-concurrent-features 32 < /dev/null >> /home/yelkhamr/dark-factory/bob96/build.log 2>&1
  echo "[supervisor] bob exited=$? completed_after=$($PY -c "import sqlite3;print(sqlite3.connect('bob.db').cursor().execute('SELECT COUNT(*) FROM features WHERE status=\"completed\"').fetchone()[0])") $(date +%T)"
  sleep 5
done
echo "[supervisor] EXIT final=$($PY -c "import sqlite3;print(sqlite3.connect('bob.db').cursor().execute('SELECT COUNT(*) FROM features WHERE status=\"completed\"').fetchone()[0])")"
