#!/usr/bin/env bash
# Install Bob and its development dependencies into a virtualenv.
# setup.py declares both package roots and the standalone runtime modules.
# Let the build backend generate the editable finder; exposing the whole
# repository via a handwritten .pth bypasses that package selection policy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
echo "==> Creating venv at $ROOT/.venv (using: $PY)"
"$PY" -m venv .venv

echo "==> Upgrading pip"
.venv/bin/python -m pip install --quiet --upgrade pip

echo "==> Installing bob (editable) + dev extras"
.venv/bin/python -m pip install -e ".[dev]"

echo "==> Installed import and resource smoke test (isolated Python)"
.venv/bin/python -I - <<'PYEOF'
import bob, tools.spec_quality_score, bob.orchestrator.run_loop, bob.model_escalation
print("  bob import chain OK; tools OK; model_escalation OK")
PYEOF

# A source-directory cwd can hide broken packaging. Run the actual console
# entrypoint from a fresh directory without inheriting a PYTHONPATH override.
SMOKE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/bob-install-smoke.XXXXXX")"
trap 'rmdir "$SMOKE_DIR"' EXIT
(
    cd "$SMOKE_DIR"
    unset PYTHONPATH
    "$ROOT/.venv/bin/bob" --version
    "$ROOT/.venv/bin/bob" --help >/dev/null
)

cat <<EOF

✓ bob built at $ROOT/.venv

Run the test suite:
  .venv/bin/python -m pytest tests/test_model_escalation.py -q

Use the CLI:
  .venv/bin/python -m bob.cli --help     # or: .venv/bin/bob --help
EOF
