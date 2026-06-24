#!/usr/bin/env bash
# Build bob3 from a clean clone into a self-contained virtualenv.
#
# Why this script (and not just `pip install -e .`): bob3's source is split
# across TWO roots — `src/` (the bob3 package + many sibling packages and loose
# top-level modules like ears_criteria) and the gen-root `tools/` package. pip's
# default "editable" finder maps discovered packages individually and misses the
# loose modules / second root, so a plain editable install can't import
# everything. We install editable for the metadata, then drop a path-based .pth
# that puts BOTH roots on sys.path — exactly what the runtime needs, with no
# PYTHONPATH environment variable required afterwards.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
echo "==> Creating venv at $ROOT/.venv (using: $PY)"
"$PY" -m venv .venv

echo "==> Upgrading pip"
.venv/bin/python -m pip install --quiet --upgrade pip

echo "==> Installing bob3 (editable) + dev extras"
.venv/bin/python -m pip install -e ".[dev]"

echo "==> Writing dual-root path file so src/ AND tools/ are importable (no PYTHONPATH needed)"
SITE="$(.venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
printf '%s\n%s\n' "$ROOT" "$ROOT/src" > "$SITE/_bob_roots.pth"

echo "==> Smoke test"
.venv/bin/python - <<'PYEOF'
import bob3, tools.spec_quality_score, bob3.orchestrator.run_loop, bob3.model_escalation
print("  bob3 import chain OK; tools OK; model_escalation OK")
PYEOF

cat <<EOF

✓ bob3 built at $ROOT/.venv

Run the test suite:
  .venv/bin/python -m pytest tests/test_model_escalation.py -q

Use the CLI:
  .venv/bin/python -m bob3.cli --help     # or: .venv/bin/bob3 --help
EOF
