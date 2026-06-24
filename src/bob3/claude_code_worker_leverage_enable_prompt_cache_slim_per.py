"""Claude-Code worker leverage — enable prompt cache, slim per-worker context, re-declare settings.

Feature 5b6febb0: Three high-ROI platform fixes applied to every spawned worker:

(A) Prompt caching — sets ANTHROPIC_PROMPT_CACHING=1 in the worker environment.
    Addresses Issue #29966 where sub-agents hardcode enablePromptCaching=false,
    causing ~378K wasted tokens per session from re-billed system prompts.

(B) Slim worker context — generates per-feature WORKER.md at dispatch time.
    bob3's CLAUDE.md (loop-operator memory ~70 bullets) is irrelevant to a
    feature-implementing worker. Only the feature title, description, AC list,
    localization shortlist, and workspace path are included.
    Saves ~6K tokens × 8 workers × 88 features ≈ 4.2M tokens/round.

(C) Per-worker settings — writes .bob3/features/<id>/settings.json at dispatch
    time and passes via `claude -p --settings <path>`. Addresses Issue #27661:
    sub-agents do NOT inherit hooks/permissions from parent settings.json.

Integration: bob3.orchestrator.run_loop (imported as integration AC).

Public API
----------
claude_code_worker_leverage_enable_prompt_cache_slim_per(feature, workspace, bob3_dir, ...)
    Main entry point: applies all three fixes and returns metadata dict.

apply_worker_leverage(feature, workspace, bob3_dir, ...)
    Apply all three platform fixes, write files, return metadata.

build_worker_context(feature, workspace)
    Build worker environment and WORKER.md content without writing to disk.

emit_perm_prompt_event(feature_id, tool)
    Emit and log WORKER_PERM_PROMPT telemetry event.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from bob3.dispatch import (
    build_worker_md,
    write_feature_settings,
)

logger = logging.getLogger(__name__)


def build_worker_context(
    feature: Any,
    workspace: str,
) -> dict[str, Any]:
    """Build worker environment and WORKER.md content without writing to disk.

    Args:
        feature:   Feature object (read-only).
        workspace: Project workspace directory path.

    Returns:
        Dict with ``worker_md`` (str) and ``env`` (dict) keys.
    """
    worker_md = build_worker_md(feature, workspace)
    env = {"ANTHROPIC_PROMPT_CACHING": "1"}
    return {"worker_md": worker_md, "env": env}


def emit_perm_prompt_event(feature_id: str, tool: str) -> dict[str, Any]:
    """Emit and log WORKER_PERM_PROMPT telemetry when a permission prompt is detected.

    Issue #27661: without per-worker settings, workers stall silently on
    permission prompts. This event identifies which feature and tool triggered
    the prompt so operators can add the missing allow pattern.

    Args:
        feature_id: Feature UUID for correlation.
        tool:       Tool name that triggered the permission prompt.

    Returns:
        The event dict, also emitted via logger.warning.
    """
    event: dict[str, Any] = {
        "event": "WORKER_PERM_PROMPT",
        "feature_id": feature_id,
        "tool": tool,
    }
    logger.warning(json.dumps(event))
    return event


def apply_worker_leverage(
    feature: Any,
    workspace: str,
    bob3_dir: str | Path,
    *,
    extra_allow: list[str] | None = None,
) -> dict[str, Any]:
    """Apply all three worker-leverage platform fixes and write files to disk.

    (A) Builds environment with ANTHROPIC_PROMPT_CACHING=1.
    (B) Writes per-feature WORKER.md to .bob3/features/WORKER.md.
    (C) Writes per-feature settings.json to .bob3/features/<id>/settings.json.

    Args:
        feature:     Feature object with id, name, description, etc.
        workspace:   Project workspace directory path.
        bob3_dir:    Path to the .bob3 directory.
        extra_allow: Additional permission allow patterns for the worker.

    Returns:
        Dict with ``settings_path``, ``worker_md_path``, and ``env`` keys.
    """
    bob3_dir = Path(bob3_dir)
    feature_id = getattr(feature, "id", "unknown")

    # (B) Write per-feature WORKER.md
    worker_md_content = build_worker_md(feature, workspace)
    worker_md_dir = bob3_dir / "features"
    worker_md_dir.mkdir(parents=True, exist_ok=True)
    worker_md_path = worker_md_dir / "WORKER.md"
    worker_md_path.write_text(worker_md_content)

    # (C) Write per-feature settings.json
    settings_path = write_feature_settings(feature, bob3_dir=bob3_dir, extra_allow=extra_allow)

    # (A) Build environment with prompt caching enabled
    env = {"ANTHROPIC_PROMPT_CACHING": "1"}

    logger.info(
        json.dumps({
            "event": "WORKER_LEVERAGE_APPLIED",
            "feature_id": feature_id,
            "settings_path": str(settings_path),
            "worker_md_path": str(worker_md_path),
        })
    )

    return {
        "settings_path": settings_path,
        "worker_md_path": worker_md_path,
        "env": env,
    }


def claude_code_worker_leverage_enable_prompt_cache_slim_per(
    feature: Any,
    workspace: str,
    bob3_dir: str | Path,
    *,
    extra_allow: list[str] | None = None,
) -> dict[str, Any]:
    """Main entry point: apply all three Claude-Code worker leverage fixes.

    Applies prompt caching (A), slim context via WORKER.md (B), and
    per-worker settings.json (C) before any worker is dispatched.

    This is the canonical function satisfying the feature AC:
      "Function defined: bob3.claude_code_worker_leverage_enable_prompt_cache_slim_per
       .claude_code_worker_leverage_enable_prompt_cache_slim_per"

    Args:
        feature:     Feature object with id, name, description, acceptance_criteria,
                     localization_shortlist attributes.
        workspace:   Project workspace directory path string.
        bob3_dir:    Path to the .bob3 directory where feature dirs are written.
        extra_allow: Additional permission allow patterns beyond project defaults.

    Returns:
        Dict with:
          - ``settings_path``: Path to the written settings.json
          - ``worker_md_path``: Path to the written WORKER.md
          - ``env``: Dict of environment variables to set on the worker process
    """
    return apply_worker_leverage(
        feature=feature,
        workspace=workspace,
        bob3_dir=bob3_dir,
        extra_allow=extra_allow,
    )


__all__ = [
    "apply_worker_leverage",
    "build_worker_context",
    "claude_code_worker_leverage_enable_prompt_cache_slim_per",
    "emit_perm_prompt_event",
]
