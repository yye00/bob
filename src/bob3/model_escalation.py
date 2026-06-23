"""Model escalation ladder (F-R7-633).

When a feature exhausts its refinement-attempt budget on the current model —
the point where the orchestrator would otherwise mark it ``needs_human``, AFTER
RCA and decomposition recovery have already been tried and failed — escalate it
to the next, more capable model in an ordered ladder, reset its attempt counter,
and re-dispatch for a fresh round of attempts. Only when the LAST ladder entry is
also exhausted is the feature marked ``needs_human``.

The ladder is read from ``BOB3_MODEL_ESCALATION_LADDER`` (comma-separated, ordered
by increasing capability; default ``"sonnet,opus"``). Each feature tracks its
position via a persisted integer ``model_tier`` (default 0 = first ladder entry).

This is the final automated recovery stage before human escalation.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

__all__ = ["parse_ladder", "resolve_model_for_tier", "try_escalate", "DEFAULT_LADDER"]

logger = logging.getLogger(__name__)

DEFAULT_LADDER: tuple[str, ...] = ("sonnet", "opus")
_ENV_VAR = "BOB3_MODEL_ESCALATION_LADDER"
# Final fallback when the configured ladder is empty/malformed/all-unknown.
# A single-tier ladder can never crash the run or silently disable building.
_SAFE_FALLBACK: tuple[str, ...] = ("sonnet",)


def parse_ladder(raw: str | None = None) -> list[str]:
    """Parse the model-escalation ladder into an ordered list of model aliases.

    ``raw`` defaults to ``os.environ[BOB3_MODEL_ESCALATION_LADDER]`` (or the
    built-in default when unset). Entries are split on commas, trimmed, and
    validated against the known model aliases via ``resolve_model_name``; unknown
    entries are DROPPED (not raised) so a typo cannot crash the run. Order is
    preserved and exact duplicates are collapsed. An empty / malformed / wholly
    unknown ladder falls back to ``["sonnet"]``.
    """
    # Imported lazily to avoid a circular import: claude_executor pulls in the
    # orchestrator package, which imports run_loop, which imports this module.
    from bob3.orchestrator.claude_executor import resolve_model_name

    if raw is None:
        raw = os.environ.get(_ENV_VAR)
    # Only an UNSET ladder uses the default. An explicitly empty/malformed value
    # is a misconfiguration and falls through to the safe single-tier fallback.
    if raw is None:
        raw = ",".join(DEFAULT_LADDER)

    out: list[str] = []
    for token in str(raw).split(","):
        alias = token.strip()
        if not alias:
            continue
        try:
            resolved = resolve_model_name(alias)
        except Exception:
            resolved = None
        if resolved is None:
            logger.warning(
                "model_escalation: dropping unknown ladder model %r (not a valid alias/id)",
                alias,
            )
            continue
        if alias not in out:
            out.append(alias)

    if not out:
        logger.warning(
            "model_escalation: ladder %r yielded no valid models; falling back to %r",
            raw, list(_SAFE_FALLBACK),
        )
        return list(_SAFE_FALLBACK)
    return out


def resolve_model_for_tier(tier: int | None, raw: str | None = None) -> str:
    """Return the model alias for ``tier``, clamped to the ladder bounds.

    Tier 0 is the first (least capable) ladder entry. A tier beyond the ladder
    end clamps to the last (most capable) entry; a negative/None tier clamps to 0.
    """
    ladder = parse_ladder(raw)
    try:
        t = int(tier) if tier is not None else 0
    except (TypeError, ValueError):
        t = 0
    if t < 0:
        t = 0
    if t >= len(ladder):
        t = len(ladder) - 1
    return ladder[t]


def try_escalate(
    feature,
    db_update_fn: Callable[..., object],
    *,
    raw: str | None = None,
) -> bool:
    """Escalate ``feature`` to the next ladder model, if one exists.

    On success: bumps ``model_tier`` by one, resets ``refinement_attempts`` to 0,
    returns the feature to ``ready`` (overriding the pending needs_human demotion),
    persists via ``db_update_fn``, logs a ``MODEL_ESCALATION`` event, and returns
    ``True``. When the feature is already at the LAST ladder tier, makes no change
    and returns ``False`` (caller should mark it needs_human).
    """
    ladder = parse_ladder(raw)
    current_tier = getattr(feature, "model_tier", 0) or 0
    try:
        current_tier = int(current_tier)
    except (TypeError, ValueError):
        current_tier = 0

    next_tier = current_tier + 1
    if next_tier >= len(ladder):
        # Already on (or past) the strongest model — escalation exhausted.
        return False

    feature_id = getattr(feature, "id", None)
    if feature_id is None:
        return False

    db_update_fn(
        feature_id,
        model_tier=next_tier,
        refinement_attempts=0,
        status="ready",
    )
    logger.info(
        '{"event": "MODEL_ESCALATION", "feature_id": "%s", "from_model": "%s", '
        '"to_model": "%s", "from_tier": %d, "to_tier": %d, "F-R7-633": true}',
        str(feature_id)[:8], ladder[current_tier], ladder[next_tier],
        current_tier, next_tier,
    )
    return True
