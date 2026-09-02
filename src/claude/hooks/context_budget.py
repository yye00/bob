"""Workspace-importable wrapper for the .claude/hooks/context_budget.py hook.

The actual hook script lives at .claude/hooks/context_budget.py (a hidden
directory so Claude Code picks it up as a PreToolUse hook).  This module
re-exports its public API so that bob internals and the AC integration
verifier can import it via a regular dotted path:

    from claude.hooks.context_budget import check_context_usage

This satisfies the acceptance criterion:
    integration: .claude.hooks.context_budget
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the actual hook module from .claude/hooks/context_budget.py
# ---------------------------------------------------------------------------

_SOURCE_HOOK_PATH = (
    Path(__file__).parents[3] / ".claude" / "hooks" / "context_budget.py"
)
_INSTALLED_HOOK_PATH = Path(sys.prefix) / ".claude" / "hooks" / "context_budget.py"
_HOOK_PATH = (
    _SOURCE_HOOK_PATH if _SOURCE_HOOK_PATH.is_file() else _INSTALLED_HOOK_PATH
)

_spec = importlib.util.spec_from_file_location(
    "claude.hooks.context_budget._impl", _HOOK_PATH
)
_impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impl)

# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------

check_context_usage = _impl.check_context_usage
emit_telemetry = _impl.emit_telemetry
should_block = _impl.should_block
main = _impl.main
CONTEXT_BUDGET_THRESHOLD = _impl.CONTEXT_BUDGET_THRESHOLD

__all__ = [
    "check_context_usage",
    "emit_telemetry",
    "should_block",
    "main",
    "CONTEXT_BUDGET_THRESHOLD",
]
