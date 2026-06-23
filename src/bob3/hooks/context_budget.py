"""BF-8 Part A — context_budget hook adapter module.

This module exposes the enforce_context_budget function and other public API
from the .claude/hooks/context_budget.py PreToolUse hook script, making them
importable as bob3.hooks.context_budget.

Satisfies ACs:
  - File exists: src/bob3/hooks/context_budget.py
  - Function defined: bob3.hooks.context_budget.enforce_context_budget
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Load the actual hook implementation from .claude/hooks/context_budget.py
# ---------------------------------------------------------------------------

_HOOK_PATH = Path(__file__).parents[3] / ".claude" / "hooks" / "context_budget.py"


def _load_hook_module():
    spec = importlib.util.spec_from_file_location("_context_budget_hook", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_hook = _load_hook_module()

# Re-export the hook's public API.
check_context_usage = _hook.check_context_usage
emit_telemetry = _hook.emit_telemetry
should_block = _hook.should_block
main = _hook.main
CONTEXT_BUDGET_THRESHOLD = _hook.CONTEXT_BUDGET_THRESHOLD


# ---------------------------------------------------------------------------
# enforce_context_budget — primary AC-required function
# ---------------------------------------------------------------------------


def enforce_context_budget(
    transcript_path: str,
    model: str | None = None,
    threshold: float = CONTEXT_BUDGET_THRESHOLD,
    feature_id: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Enforce the context-budget policy for a running subagent.

    Checks whether the subagent's context usage exceeds the threshold.
    If it does, emits a CTX_BUDGET_KILL telemetry event and returns a block
    decision dict.  If within budget, returns a continue decision dict.

    Args:
        transcript_path: Path to the JSONL transcript file.
        model:           Model name (used to look up max window size).
        threshold:       Fraction of model window triggering a block (default 0.60).
        feature_id:      Feature UUID for telemetry; defaults to BOB3_FEATURE_ID env var.
        workspace:       Workspace root path for events.jsonl; defaults to cwd.

    Returns:
        A dict with keys:
          decision  – "continue" or "block"
          reason    – human-readable explanation (empty when continuing)
          metrics   – context usage metrics dict from check_context_usage
    """
    fid = feature_id or os.environ.get("BOB3_FEATURE_ID", "unknown")

    metrics: dict[str, Any] = {}
    try:
        metrics = _hook.check_context_usage(transcript_path, model=model, threshold=threshold)
    except OSError:
        return {"decision": "continue", "reason": "", "metrics": metrics}

    if not metrics.get("over_budget", False):
        return {"decision": "continue", "reason": "", "metrics": metrics}

    tokens = metrics["tokens_used"]
    limit = metrics["limit"]
    fraction = metrics["fraction"]

    try:
        _hook.emit_telemetry(
            event="CTX_BUDGET_KILL",
            feature_id=fid,
            tokens=tokens,
            limit=limit,
            workspace=workspace,
        )
    except OSError:
        pass

    reason = (
        f"context-budget-exceeded; spawn fresh subagent and hand off via "
        f".bob3/handoff/{fid}.md "
        f"(used {tokens}/{limit} tokens, {fraction:.1%} of model window)"
    )
    return {"decision": "block", "reason": reason, "metrics": metrics}


__all__ = [
    "CONTEXT_BUDGET_THRESHOLD",
    "check_context_usage",
    "emit_telemetry",
    "enforce_context_budget",
    "main",
    "should_block",
]
