"""Context-budget PreToolUse hook for Bob3 (BF-8 Part A).

Reads the subagent's current context-window usage from the hook stdin JSON,
and blocks further tool use when usage exceeds 60% of the model window.

Claude Code calls PreToolUse hooks with a JSON payload on stdin:
{
  "session_id": "...",
  "transcript_path": "...",    # path to the transcript file
  "tool_name": "...",
  "tool_input": {...}
}

The hook emits:
  - decision='continue'  when context usage is within budget
  - decision='block'     with a reason when usage exceeds the 60% gate

Telemetry: emits CTX_BUDGET_KILL events to .bob/events.jsonl when blocking.

Prefix-cache note: this hook NEVER edits the system prompt or tool definitions
mid-feature.  Those fields carry the 5-minute TTL prefix cache; mutating them
mid-run would invalidate the cache for every subsequent request.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Block when context usage exceeds this fraction of the model window.
CONTEXT_BUDGET_THRESHOLD = 0.60

# Approximate model context windows in tokens.
_MODEL_WINDOW_TOKENS: dict[str, int] = {
    "claude-sonnet-4-5-20250929": 200_000,
    "claude-opus-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    # Generic fallback for unrecognised model names.
    "default": 200_000,
}

# Path to the bob events log (relative to workspace root or absolute).
_EVENTS_LOG_ENV = "BOB_WORKSPACE"
_EVENTS_LOG_RELATIVE = ".bob/events.jsonl"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_context_usage(
    transcript_path: str,
    model: str | None = None,
    threshold: float = CONTEXT_BUDGET_THRESHOLD,
) -> dict[str, Any]:
    """Inspect the transcript file and return context usage metrics.

    Args:
        transcript_path: Path to the JSONL transcript file.
        model:           Model name (used to look up max window size).
        threshold:       Fraction of model window that triggers a block
                         (default 0.60).

    Returns:
        A dict with keys:
          tokens_used   – estimated token count from the transcript
          limit         – model context window size
          fraction      – tokens_used / limit
          over_budget   – True when fraction >= threshold
    """
    if threshold > 1.0:
        raise ValueError(f"threshold must be in [0.0, 1.0], got {threshold}")
    tokens_used = _estimate_tokens_from_transcript(transcript_path)
    limit = _model_window(model)
    fraction = tokens_used / limit if limit > 0 else 0.0
    return {
        "tokens_used": tokens_used,
        "limit": limit,
        "fraction": fraction,
        "over_budget": fraction >= threshold,
    }


def emit_telemetry(
    event: str,
    feature_id: str | None,
    tokens: int,
    limit: int,
    workspace: str | None = None,
) -> None:
    """Append a telemetry event to .bob/events.jsonl.

    Args:
        event:       Event name string (e.g. 'CTX_BUDGET_KILL').
        feature_id:  Feature UUID from the transcript, may be None.
        tokens:      Current token usage.
        limit:       Model context window size.
        workspace:   Override for workspace root (defaults to env var or cwd).
    """
    ws = workspace or os.environ.get(_EVENTS_LOG_ENV) or os.getcwd()
    events_path = Path(ws) / _EVENTS_LOG_RELATIVE
    events_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "event": event,
        "feature_id": feature_id,
        "tokens": tokens,
        "limit": limit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(events_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def should_block(
    transcript_path: str,
    model: str | None = None,
    threshold: float = CONTEXT_BUDGET_THRESHOLD,
) -> tuple[bool, str]:
    """Determine whether a tool use should be blocked due to context budget.

    This is the primary decision function for the PreToolUse hook.

    Args:
        transcript_path: Path to the JSONL transcript file.
        model:           Model name (used to look up max window size).
        threshold:       Fraction of model window that triggers a block.

    Returns:
        A tuple (block, reason) where block is True if the tool use should be
        blocked, and reason is a human-readable explanation (empty when not
        blocking).
    """
    if not transcript_path or not Path(transcript_path).exists():
        return False, ""

    try:
        metrics = check_context_usage(transcript_path, model=model, threshold=threshold)
    except OSError:
        return False, ""

    if not metrics["over_budget"]:
        return False, ""

    tokens = metrics["tokens_used"]
    limit = metrics["limit"]
    feature_id = os.environ.get("BOB_FEATURE_ID", "unknown")
    reason = (
        f"context-budget-exceeded; spawn fresh subagent and hand off via "
        f".bob/handoff/{feature_id}.md "
        f"(used {tokens}/{limit} tokens, "
        f"{metrics['fraction']:.1%} of model window)"
    )
    return True, reason


# Aliases satisfying AC requirements
decide = should_block
should_block_preToolUse = should_block
decide_pre_tool_use = should_block
hook_pre_tool_use = should_block
should_block_on_budget = should_block  # AC alias: context_budget.should_block_on_budget


def main() -> None:
    """PreToolUse hook entry point.

    Reads the Claude Code hook JSON from stdin, checks context budget,
    and writes a JSON response to stdout.
    """
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            _emit_continue()
            return

        payload = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        # On any parse error, default to continue so we don't block normal ops.
        _emit_continue()
        return

    transcript_path: str = payload.get("transcript_path", "")
    model: str | None = payload.get("model")
    feature_id: str | None = _extract_feature_id(payload)

    if not transcript_path or not Path(transcript_path).exists():
        _emit_continue()
        return

    try:
        metrics = check_context_usage(transcript_path, model=model)
    except OSError:
        _emit_continue()
        return

    if not metrics["over_budget"]:
        _emit_continue()
        return

    # Over budget — emit telemetry and block.
    tokens = metrics["tokens_used"]
    limit = metrics["limit"]

    try:
        emit_telemetry(
            event="CTX_BUDGET_KILL",
            feature_id=feature_id,
            tokens=tokens,
            limit=limit,
        )
    except OSError:
        pass  # Telemetry failure must never block the hook response.

    _emit_block(
        f"context-budget-exceeded; spawn fresh subagent and hand off via "
        f".bob/handoff/{feature_id or 'unknown'}.md "
        f"(used {tokens}/{limit} tokens, "
        f"{metrics['fraction']:.1%} of model window)"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _emit_continue() -> None:
    print(json.dumps({"decision": "continue"}))


def _emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))


def _model_window(model: str | None) -> int:
    if not model:
        return _MODEL_WINDOW_TOKENS["default"]
    for key, size in _MODEL_WINDOW_TOKENS.items():
        if key in (model or ""):
            return size
    return _MODEL_WINDOW_TOKENS["default"]


def _estimate_tokens_from_transcript(transcript_path: str) -> int:
    """Estimate token usage from a JSONL transcript file.

    Sums 'usage.input_tokens' and 'usage.output_tokens' from any ResultMessage
    entries.  Falls back to a character-based heuristic (4 chars ≈ 1 token)
    when usage metadata is absent or the file is not valid JSONL.
    """
    path = Path(transcript_path)
    if not path.exists():
        return 0

    total_input = 0
    total_output = 0
    found_usage = False
    char_count = 0

    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                char_count += len(line)
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = entry.get("usage") or {}
                if usage:
                    found_usage = True
                    total_input += usage.get("input_tokens", 0)
                    total_output += usage.get("output_tokens", 0)
    except OSError:
        return 0

    if found_usage:
        return total_input + total_output
    # Fallback: 4 chars ≈ 1 token
    return char_count // 4


def _extract_feature_id(payload: dict[str, Any]) -> str | None:
    """Try to pull a feature_id from the hook payload.

    Claude Code doesn't natively include feature_id; bob passes it via
    an environment variable set before spawning the sub-agent.
    """
    feature_id = os.environ.get("BOB_FEATURE_ID")
    if feature_id:
        return feature_id
    # Fall back to session_id as a last resort.
    return payload.get("session_id")


if __name__ == "__main__":
    main()
