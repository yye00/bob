"""Claude-Code worker leverage — three high-ROI platform fixes for spawned workers.

Feature 79ba244c. Research synthesis from brownfield agents identified three
platform fixes bob must apply to every spawned Claude-Code worker:

(A) Enable prompt caching on every worker  (Issue #29966)
    Sub-agents otherwise hardcode enablePromptCaching=false, re-billing ~7K
    system prompts every call. ``enable_prompt_caching`` returns a worker env
    with ANTHROPIC_PROMPT_CACHING=1.

(B) Slim per-worker context  — the operator loop's full CLAUDE.md is irrelevant
    to a feature-implementing worker. ``generate_worker_md`` produces a WORKER.md
    containing only the feature title/description, resolved AC list, localization
    shortlist, and workspace path.

(C) Re-declare settings per worker  (Issue #27661)
    Sub-agents do NOT inherit hooks/permissions from the parent settings.json.
    ``write_worker_settings`` writes an explicit per-feature settings.json passed
    to the worker via ``--settings``, preventing silent permission-prompt stalls.

This module is the AC-named public surface for feature 79ba244c; the underlying
machinery lives in :mod:`bob.dispatch` and is reused here to avoid divergence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob import dispatch

__all__ = [
    "enable_prompt_caching",
    "generate_worker_md",
    "write_worker_settings",
]


def enable_prompt_caching(env: dict[str, str] | None = None) -> dict[str, str]:
    """Return a worker environment dict with prompt caching enabled.

    Fix (A) for Issue #29966: sets ``ANTHROPIC_PROMPT_CACHING=1`` so the worker's
    Claude Code CLI enables prompt caching on every API call. The input ``env`` is
    not mutated; a new dict is returned.

    Args:
        env: Existing environment to extend. ``None`` starts from empty.

    Returns:
        New dict merging *env* with the cache-enable flag.

    Raises:
        ValueError: If *env* is neither ``None`` nor a dict.
    """
    if env is not None and not isinstance(env, dict):
        raise ValueError(f"env must be a dict or None, got {type(env).__name__}")
    return dispatch.enable_worker_prompt_cache(env)


def generate_worker_md(feature: Any, workspace: str | Path) -> str:
    """Return slim WORKER.md content for *feature*.

    Fix (B): contains only what a feature-implementing worker needs — title,
    description, resolved ACs, localization shortlist, and workspace path — not
    the operator loop's full CLAUDE.md.

    Args:
        feature:   Feature object (read-only).
        workspace: Project workspace path.

    Returns:
        Markdown string for WORKER.md.

    Raises:
        ValueError: If *feature* is None.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    return dispatch.build_worker_md(feature, workspace)


def write_worker_settings(
    feature: Any,
    *,
    bob_dir: str | Path,
    extra_allow: list[str] | None = None,
) -> Path:
    """Write per-feature settings.json for a worker and return its path.

    Fix (C) for Issue #27661: workers do not inherit the parent settings.json, so
    an explicit ``.bob/features/<id>/settings.json`` is written at dispatch time.

    Args:
        feature:     Feature object (read-only); ``feature.id`` names the dir.
        bob_dir:     Path to the .bob directory (project-level).
        extra_allow: Additional allow patterns beyond project defaults.

    Returns:
        Path to the written settings.json file.

    Raises:
        ValueError: If *feature* is None.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    return dispatch.write_feature_settings(
        feature, bob_dir=bob_dir, extra_allow=extra_allow
    )
