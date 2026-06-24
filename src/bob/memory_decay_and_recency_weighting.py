"""Memory decay and recency weighting for bob.

Ages lessons in the learning ledger using exponential decay. The decay
weight is w = 2^(-age_days / half_life_days) so that a lesson at exactly
one half-life is worth 0.5.

Two decay profiles are supported:
- "context" (high decay): short half-life, ~half of BOB_LESSON_HALF_LIFE_DAYS
- "long_term" (low decay): 3× the configured half-life

The weighted score returned by ``compute_decay_weight`` affects
skill-activation scoring via ``weight_learnings``.

Public API:
    MemoryDecayConfig           - dataclass holding decay configuration
    get_decay_config()          - build config from env vars
    compute_decay_weight(ts, config, pool) -> float
    weight_learnings(learnings, config) -> list[dict]
    top_k_learnings(learnings, k, config) -> list[dict]
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


_DEFAULT_HALF_LIFE_DAYS = 30.0
_CONTEXT_HALF_LIFE_FACTOR = 0.5   # context memory decays 2× faster
_LONG_TERM_HALF_LIFE_FACTOR = 3.0  # long-term memory decays 3× slower

MemoryPool = Literal["context", "long_term", "lessons", "facts", "preferences"]


@dataclass(frozen=True)
class MemoryDecayConfig:
    """Decay configuration for the memory ledger.

    Attributes:
        half_life_days: Base half-life in days (for "lessons" / default pool).
        context_half_life_days: Half-life for short-lived context memories.
        long_term_half_life_days: Half-life for durable long-term memories.
    """

    half_life_days: float
    context_half_life_days: float
    long_term_half_life_days: float

    def half_life_for_pool(self, pool: str | None) -> float:
        """Return the appropriate half-life for the given pool name."""
        if pool == "context":
            return self.context_half_life_days
        if pool == "long_term":
            return self.long_term_half_life_days
        return self.half_life_days


def get_decay_config() -> MemoryDecayConfig:
    """Build decay configuration from environment variables.

    Reads BOB_LESSON_HALF_LIFE_DAYS (default 30). Raises ValueError for
    non-positive or non-numeric values so misconfiguration surfaces loudly.
    """
    raw = os.environ.get("BOB_LESSON_HALF_LIFE_DAYS")
    if raw is None:
        half_life = _DEFAULT_HALF_LIFE_DAYS
    else:
        try:
            half_life = float(raw)
        except ValueError:
            raise ValueError(
                f"BOB_LESSON_HALF_LIFE_DAYS={raw!r} is not a valid number."
            )
        if half_life <= 0:
            raise ValueError(
                f"BOB_LESSON_HALF_LIFE_DAYS must be positive, got {half_life}."
            )

    return MemoryDecayConfig(
        half_life_days=half_life,
        context_half_life_days=half_life * _CONTEXT_HALF_LIFE_FACTOR,
        long_term_half_life_days=half_life * _LONG_TERM_HALF_LIFE_FACTOR,
    )


def compute_decay_weight(
    timestamp: str | datetime,
    config: MemoryDecayConfig | None = None,
    pool: str | None = None,
    *,
    now: datetime | None = None,
) -> float:
    """Compute the exponential decay weight for a single memory entry.

    weight = 2^(-age_days / half_life_days)

    A weight of 1.0 means the memory is brand-new; 0.5 means it is exactly
    one half-life old; 0.0 is asymptotically approached for very old memories.

    Args:
        timestamp: ISO 8601 timestamp string or datetime of when the memory was stored.
        config: Decay configuration; uses get_decay_config() when None.
        pool: Memory pool name ("context", "long_term", or lessons/facts/etc.).
        now: Reference datetime for age calculation (defaults to utcnow).

    Returns:
        Float in (0, 1] — higher means more recent / more relevant.
    """
    if config is None:
        config = get_decay_config()

    if now is None:
        now = datetime.now(timezone.utc)

    if isinstance(timestamp, str):
        # Parse ISO 8601; handle both aware and naive timestamps
        ts = _parse_iso(timestamp)
    else:
        ts = timestamp

    # Ensure both datetimes are timezone-aware for comparison
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_seconds = (now - ts).total_seconds()
    age_days = age_seconds / 86400.0

    # Clamp: memories cannot be from the future (negative age → weight 1.0)
    if age_days < 0:
        age_days = 0.0

    half_life = config.half_life_for_pool(pool)
    weight = 2.0 ** (-age_days / half_life)
    return weight


def _parse_iso(ts_str: str) -> datetime:
    """Parse an ISO 8601 timestamp string.

    Handles the trailing 'Z' that Python <3.11 datetime.fromisoformat()
    does not accept.
    """
    ts_str = ts_str.strip()
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    return datetime.fromisoformat(ts_str)


def weight_learnings(
    learnings: list[dict],
    config: MemoryDecayConfig | None = None,
    pool: str | None = None,
    *,
    now: datetime | None = None,
) -> list[dict]:
    """Attach a ``decay_weight`` field to each learning entry.

    Each entry must have a ``"timestamp"`` key (ISO 8601 string). Entries
    without a valid timestamp receive weight 0.0.

    Args:
        learnings: List of learning dicts (as returned by ``read_learnings``).
        config: Decay configuration; uses get_decay_config() when None.
        pool: Default pool for all entries (can be overridden per-entry via
              entry["pool"] if present).
        now: Reference datetime for age calculation.

    Returns:
        New list of dicts with an added ``"decay_weight"`` key. The original
        dicts are not mutated.
    """
    if config is None:
        config = get_decay_config()

    result = []
    for entry in learnings:
        entry_copy = dict(entry)
        entry_pool = entry.get("pool", pool)
        ts = entry.get("timestamp")
        if ts:
            try:
                w = compute_decay_weight(ts, config, entry_pool, now=now)
            except (ValueError, TypeError):
                w = 0.0
        else:
            w = 0.0
        entry_copy["decay_weight"] = w
        result.append(entry_copy)
    return result


def top_k_learnings(
    learnings: list[dict],
    k: int,
    config: MemoryDecayConfig | None = None,
    pool: str | None = None,
    *,
    now: datetime | None = None,
) -> list[dict]:
    """Return the top-k learnings by decay weight (most recent first).

    Args:
        learnings: List of learning dicts.
        k: Maximum number of entries to return.
        config: Decay configuration; uses get_decay_config() when None.
        pool: Pool name for decay half-life selection.
        now: Reference datetime for age calculation.

    Returns:
        List of at most ``k`` dicts, sorted by decay_weight descending.
        Each dict has an added ``"decay_weight"`` key.
    """
    weighted = weight_learnings(learnings, config, pool, now=now)
    weighted.sort(key=lambda e: e["decay_weight"], reverse=True)
    return weighted[:k]
