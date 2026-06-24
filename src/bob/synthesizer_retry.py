"""bob.synthesizer_retry — retry primitives for transient upstream API 400/empty-response.

Root cause addressed: the shared upstream API key intermittently returns HTTP 400
("Application 'Claude Code' (Production Restricted) is being deprecated; subsequent
requests will continue to work in the meantime"). The claude CLI exits ~1s with EMPTY
assistant text on this 400 and does NOT retry it. A single swallowed 400 silently
degrades EVERY feature to thin fallback ACs (~0.75, below the 0.85 gate), causing
60+ features per generation to never be promoted or built.

This module provides two public functions:

  retry_with_exponential_backoff  — generic async retry loop with exponential backoff,
                                    env-tunable via BOB_SYNTH_MAX_ATTEMPTS (default 40).

  synthesize_with_retry           — wraps bob.synthesizer.synthesize_for_feature in the
                                    retry loop; the canonical entry-point for any caller
                                    that needs retry-protected spec synthesis.

Backoff schedule: 2,4,8,16,32 seconds, capped at 60s, with deterministic jitter.
Each retry attempt is logged at WARNING so transient upstream bursts are observable,
not silent. Recovery is logged at INFO.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ATTEMPTS = 40


def _max_attempts_from_env() -> int:
    """Read BOB_SYNTH_MAX_ATTEMPTS from env; fall back to 40 on invalid values."""
    try:
        return max(1, int(os.environ.get("BOB_SYNTH_MAX_ATTEMPTS", str(_DEFAULT_MAX_ATTEMPTS))))
    except (ValueError, TypeError):
        return _DEFAULT_MAX_ATTEMPTS


async def retry_with_exponential_backoff(
    fn: Callable[..., Awaitable[str]],
    *,
    label: str = "",
    max_attempts: int | None = None,
    **fn_kwargs: Any,
) -> str:
    """Call async ``fn(**fn_kwargs)`` with exponential backoff until non-empty text is returned.

    Retries on:
    - Empty or whitespace-only return value (upstream 400 produces empty text)
    - Any exception raised by ``fn``

    Backoff schedule: 2,4,8,16,32 seconds capped at 60s plus deterministic jitter.

    Telemetry: every retry attempt is logged at WARNING so transient bursts are
    observable. Recovery is logged at INFO.

    Returns the first non-empty text result, or "" after all attempts are exhausted.
    Callers MUST check for empty return and decide whether to fall back.
    Never raises — exceptions from ``fn`` are caught and retried.

    Args:
        fn: async callable to invoke.
        label: human-readable label for log messages (feature title or similar).
        max_attempts: override attempt count; defaults to BOB_SYNTH_MAX_ATTEMPTS env var.
        **fn_kwargs: forwarded to ``fn`` on every call.
    """
    if max_attempts is None:
        max_attempts = _max_attempts_from_env()

    jitter = (abs(hash(label)) % 1000) / 1000.0
    text = ""

    for attempt in range(1, max_attempts + 1):
        try:
            text = await fn(**fn_kwargs)
        except Exception as exc:
            logger.warning(
                "synthesizer_retry: spawn raised for %r (attempt %d/%d): %s",
                label, attempt, max_attempts, exc,
            )
            text = ""

        if text and text.strip():
            if attempt > 1:
                logger.info(
                    "synthesizer_retry: recovered for %r on attempt %d/%d "
                    "(transient upstream cleared)",
                    label, attempt, max_attempts,
                )
            return text

        if attempt < max_attempts:
            backoff = min(2 ** attempt, 60) + int(jitter * 5)
            logger.warning(
                "synthesizer_retry: empty response for %r (attempt %d/%d) — "
                "likely transient upstream 400; retrying in %ds",
                label, attempt, max_attempts, backoff,
            )
            await asyncio.sleep(backoff)

    logger.warning(
        "synthesizer_retry: all %d attempts exhausted for %r — "
        "returning empty (caller should fall back)",
        max_attempts, label,
    )
    return ""


async def synthesize_with_retry(
    *,
    project_id: str,
    title: str,
    description: str,
    project_context: str = "",
    workspace: object = None,
    retry_feedback: str | None = None,
    max_attempts: int | None = None,
) -> list[str] | None:
    """Synthesize acceptance criteria with aggressive retry on transient upstream 400.

    Wraps ``bob.synthesizer.synthesize_for_feature`` in the
    :func:`retry_with_exponential_backoff` loop. A synthesis pass that encounters an
    upstream 400/empty-response burst will retry up to BOB_SYNTH_MAX_ATTEMPTS times
    (default 40, ~40 min at the 60s cap) before falling back.

    Returns ``list[str]`` of synthesized ACs on success, or ``None`` when all
    attempts are exhausted (caller should fall back to deterministic ACs).

    Telemetry: each retry attempt is logged at WARNING; recovery is logged at
    INFO so transient upstream bursts are observable rather than silent.

    Args:
        project_id: project identifier forwarded to the synthesizer.
        title: feature title, used for prompt construction and log labels.
        description: feature description forwarded to the synthesizer.
        project_context: optional project-level context for the synthesizer.
        workspace: optional Path to the workspace directory.
        retry_feedback: optional feedback string for re-synthesis (score gate loop).
        max_attempts: override retry count; defaults to BOB_SYNTH_MAX_ATTEMPTS.
    """
    from bob.synthesizer import synthesize_for_feature as _synthesize

    if max_attempts is None:
        max_attempts = _max_attempts_from_env()

    jitter = (abs(hash(title)) % 1000) / 1000.0

    for attempt in range(1, max_attempts + 1):
        try:
            result = await _synthesize(
                project_id=project_id,
                title=title,
                description=description,
                project_context=project_context,
                workspace=workspace,
                retry_feedback=retry_feedback,
            )
        except Exception as exc:
            logger.warning(
                "synthesizer_retry.synthesize_with_retry: synthesize_for_feature raised "
                "for %r (attempt %d/%d): %s",
                title, attempt, max_attempts, exc,
            )
            result = None

        if result is not None:
            if attempt > 1:
                logger.info(
                    "synthesizer_retry.synthesize_with_retry: recovered for %r "
                    "on attempt %d/%d",
                    title, attempt, max_attempts,
                )
            return result

        if attempt < max_attempts:
            backoff = min(2 ** attempt, 60) + int(jitter * 5)
            logger.warning(
                "synthesizer_retry.synthesize_with_retry: attempt %d/%d returned None "
                "for %r — transient upstream; retrying in %ds",
                attempt, max_attempts, title, backoff,
            )
            await asyncio.sleep(backoff)

    logger.warning(
        "synthesizer_retry.synthesize_with_retry: all %d attempts exhausted for %r "
        "— returning None",
        max_attempts, title,
    )
    return None


# AC alias: "Function defined: bob.synthesizer_retry.retry_with_backoff"
retry_with_backoff = retry_with_exponential_backoff

__all__ = [
    "retry_with_backoff",
    "retry_with_exponential_backoff",
    "synthesize_with_retry",
]
