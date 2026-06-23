"""claude_code.hooks.context_budget — public API facade for the BF-8 context-budget hook.

This module re-exports the core functions from the .claude/hooks/context_budget.py
PreToolUse hook script, making them importable as:

    from claude_code.hooks.context_budget import check_context_budget

Satisfies AC: Function defined: claude_code.hooks.context_budget.check_context_budget

The underlying implementation lives in .claude/hooks/context_budget.py; this module
is the installable Python package surface.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Load the canonical implementation from .claude/hooks/context_budget.py
# ---------------------------------------------------------------------------

_HOOK_PATH = Path(__file__).parents[3] / ".claude" / "hooks" / "context_budget.py"


def _load_hook_module():
    spec = importlib.util.spec_from_file_location("_claude_code_context_budget_hook", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_hook = _load_hook_module()

# ---------------------------------------------------------------------------
# Re-export constants
# ---------------------------------------------------------------------------

CONTEXT_BUDGET_THRESHOLD: float = _hook.CONTEXT_BUDGET_THRESHOLD


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_context_budget(
    transcript_path: str,
    model: str | None = None,
    threshold: float = CONTEXT_BUDGET_THRESHOLD,
    feature_id: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Check whether the context budget is exceeded and return a decision dict.

    This is the primary AC-required function for claude_code.hooks.context_budget.

    Args:
        transcript_path: Path to the JSONL transcript file.
        model:           Model name (used to look up max window size).
        threshold:       Fraction of model window that triggers a block (default 0.60).
        feature_id:      Feature UUID for telemetry; None falls back to env var.
        workspace:       Workspace root for telemetry output; None uses env var or cwd.

    Returns:
        A dict with keys:
          decision  – 'continue' or 'block'
          reason    – human-readable explanation (empty string when decision=='continue')
          metrics   – sub-dict from check_context_usage (tokens_used, limit, fraction,
                      over_budget)
    """
    metrics = check_context_usage(transcript_path, model=model, threshold=threshold)
    if not metrics["over_budget"]:
        return {"decision": "continue", "reason": "", "metrics": metrics}

    import os
    fid = feature_id or os.environ.get("BOB3_FEATURE_ID", "unknown")
    tokens = metrics["tokens_used"]
    limit = metrics["limit"]
    reason = (
        f"context-budget-exceeded; spawn fresh subagent and hand off via "
        f".bob3/handoff/{fid}.md "
        f"(used {tokens}/{limit} tokens, "
        f"{metrics['fraction']:.1%} of model window)"
    )

    # Emit telemetry (best-effort; never raise on failure)
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

    return {"decision": "block", "reason": reason, "metrics": metrics}


def check_context_usage(
    transcript_path: str,
    model: str | None = None,
    threshold: float = CONTEXT_BUDGET_THRESHOLD,
) -> dict[str, Any]:
    """Delegate to the underlying hook's check_context_usage."""
    return _hook.check_context_usage(transcript_path, model=model, threshold=threshold)


def emit_telemetry(
    event: str,
    feature_id: str | None,
    tokens: int,
    limit: int,
    workspace: str | None = None,
) -> None:
    """Delegate to the underlying hook's emit_telemetry."""
    return _hook.emit_telemetry(
        event=event,
        feature_id=feature_id,
        tokens=tokens,
        limit=limit,
        workspace=workspace,
    )


def should_block(
    transcript_path: str,
    model: str | None = None,
    threshold: float = CONTEXT_BUDGET_THRESHOLD,
) -> tuple[bool, str]:
    """Delegate to the underlying hook's should_block."""
    return _hook.should_block(transcript_path, model=model, threshold=threshold)
