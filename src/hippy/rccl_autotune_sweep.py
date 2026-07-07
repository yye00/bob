"""RCCL autotune-sweep discipline — tune-once/cache, config pruning, parity (hippy).

Background
----------
RCCL performance is governed by a large *discrete* config space: transport
protocols (``Simple``/``LL``/``LL128``), collective algorithms (``Ring``/
``Tree``), channel counts and chunk sizes, plus the ``RCCL_*``/``NCCL_*`` env
and tuner-CSV knobs (F-R9-021). A naive sweep of that space is both expensive
(cartesian blow-up) and easy to game (pick the config with the best bandwidth
number even if it corrupts results).

This module ports the autotune discipline proven in NVIDIA's
``tilegym-cutile-autotuning`` skill to RCCL:

1. **Tune-once then cache** — :func:`tune_once_and_cache` sweeps once per
   ``(collective, size-range, ngpus, arch)`` :class:`TuneKey` and persists the
   winning :class:`RcclConfig` in a caller-supplied cache. A second call with
   the same key returns the cached winner without re-sweeping.
2. **Prune the search space** — :func:`prune_search_space` reduces the full
   grid to a bounded set (default ``<=8`` configs) using arch- and size-guards
   so a sweep cannot blow the time budget.
3. **Mandatory correctness parity** — every swept config is checked with tuning
   ENABLED and again DISABLED (a ``DISABLE_AUTOTUNE``-equivalent baseline) via
   the injected ``correctness_fn`` (the F-R9-019 ``rccl-correct`` ``#wrong==0``
   check). A config that wins on bandwidth but corrupts results is rejected.
4. **A/B vs baseline** — the tuned winner is compared to the fixed
   best-known/default via a noise-aware perf gate (F-R9-020): the tuned config
   is only adopted when it beats the baseline by more than ``noise_fraction``.

Public API
----------
RcclConfig          - Immutable one-config knob set (protocol/algo/channels/chunk).
TuneKey             - Immutable sweep identity (collective, size-range, ngpus, arch).
ConfigEvaluation    - Per-config parity + perf outcome.
TuneResult          - Winner + all evaluations + cache/baseline flags.
AutotuneError       - Raised when no swept config is correct.
default_config_grid - The full (bounded) candidate grid.
prune_search_space  - Bound the grid by arch/size guard to <=max_configs.
tune_once_and_cache - Sweep-once, parity-check, A/B, cache, and return winner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, MutableMapping, Sequence

_PROTOCOLS = ("Simple", "LL", "LL128")
_ALGORITHMS = ("Ring", "Tree")

# LL protocols are latency-optimised (small messages); Simple is bandwidth-
# optimised (large messages). Used by the size guard when pruning.
_LATENCY_PROTOCOLS = ("LL", "LL128")

# Small-message chunk ceiling: a tiny message should never keep giant chunks.
_SMALL_MSG_CHUNK_CEIL = 262144
_SMALL_MSG_BYTES = 65536
_LARGE_MSG_BYTES = 16_000_000


class AutotuneError(ValueError):
    """Raised when the sweep produces no correctness-passing config.

    Subclasses ``ValueError`` so callers can catch either.
    """


@dataclass(frozen=True)
class RcclConfig:
    """Immutable RCCL knob set for a single configuration.

    Attributes
    ----------
    protocol:   One of ``Simple``/``LL``/``LL128``.
    algorithm:  One of ``Ring``/``Tree``.
    channels:   Number of channels (``NCCL_MIN_NCHANNELS``); positive.
    chunk_size: Chunk size in bytes; positive.
    """

    protocol: str
    algorithm: str
    channels: int
    chunk_size: int

    def __post_init__(self) -> None:
        if self.protocol not in _PROTOCOLS:
            raise ValueError(
                f"protocol must be one of {_PROTOCOLS}, got {self.protocol!r}"
            )
        if self.algorithm not in _ALGORITHMS:
            raise ValueError(
                f"algorithm must be one of {_ALGORITHMS}, got {self.algorithm!r}"
            )
        if isinstance(self.channels, bool) or not isinstance(self.channels, int):
            raise ValueError(f"channels must be an int, got {type(self.channels)!r}")
        if self.channels <= 0:
            raise ValueError(f"channels must be positive, got {self.channels}")
        if isinstance(self.chunk_size, bool) or not isinstance(self.chunk_size, int):
            raise ValueError(f"chunk_size must be an int, got {type(self.chunk_size)!r}")
        if self.chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {self.chunk_size}")

    def to_env(self) -> dict[str, str]:
        """Return the ``NCCL_*``/``RCCL_*`` env knobs for this config."""
        return {
            "NCCL_PROTO": self.protocol,
            "NCCL_ALGO": self.algorithm,
            "NCCL_MIN_NCHANNELS": str(self.channels),
            "NCCL_MAX_NCHANNELS": str(self.channels),
            "NCCL_CHUNK_SIZE": str(self.chunk_size),
        }


@dataclass(frozen=True)
class TuneKey:
    """Immutable identity for one sweep, per the tune-once/cache discipline.

    A winning config is cached keyed on this tuple, so the sweep runs once per
    ``(collective, size_range, ngpus, arch)`` rather than every run.
    """

    collective: str
    size_range: str
    ngpus: int
    arch: str

    def __post_init__(self) -> None:
        if not isinstance(self.collective, str) or not self.collective.strip():
            raise ValueError("collective must be a non-empty string")
        if not isinstance(self.size_range, str) or not self.size_range.strip():
            raise ValueError("size_range must be a non-empty string")
        if isinstance(self.ngpus, bool) or not isinstance(self.ngpus, int):
            raise ValueError(f"ngpus must be an int, got {type(self.ngpus)!r}")
        if self.ngpus <= 0:
            raise ValueError(f"ngpus must be positive, got {self.ngpus}")
        if not isinstance(self.arch, str) or not self.arch.strip():
            raise ValueError("arch must be a non-empty string")


@dataclass(frozen=True)
class ConfigEvaluation:
    """Parity + perf outcome for a single swept config.

    Attributes
    ----------
    config:            The evaluated :class:`RcclConfig`.
    correct:           True iff ``#wrong == 0`` with tuning both ON and OFF.
    wrong_enabled:     ``#wrong`` from the tuning-ENABLED correctness run.
    wrong_disabled:    ``#wrong`` from the tuning-DISABLED baseline run.
    runtime:           Measured runtime (lower is better); None if not measured.
    """

    config: RcclConfig
    correct: bool
    wrong_enabled: int
    wrong_disabled: int
    runtime: float | None = None


@dataclass(frozen=True)
class TuneResult:
    """Result of a tune-once sweep.

    Attributes
    ----------
    key:            The :class:`TuneKey` this result is cached under.
    winner:         The adopted :class:`RcclConfig`.
    evaluations:    Per-config :class:`ConfigEvaluation` records.
    from_cache:     True iff the winner came from the cache (no re-sweep).
    beat_baseline:  True iff the tuned winner cleared the noise-aware A/B gate.
                    None when no baseline was supplied.
    """

    key: TuneKey
    winner: RcclConfig
    evaluations: tuple[ConfigEvaluation, ...] = field(default_factory=tuple)
    from_cache: bool = False
    beat_baseline: bool | None = None


def default_config_grid() -> list[RcclConfig]:
    """Return the full (already-bounded) candidate grid.

    The grid is intentionally small — the full cartesian product would blow the
    time budget, so :func:`prune_search_space` narrows it further per sweep.
    """
    channels = (2, 4, 8)
    chunks = (65536, 131072, 524288)
    grid: list[RcclConfig] = []
    for protocol in _PROTOCOLS:
        for algorithm in _ALGORITHMS:
            for ch in channels:
                for chunk in chunks:
                    grid.append(RcclConfig(protocol, algorithm, ch, chunk))
    return grid


def _sort_key(c: RcclConfig) -> tuple:
    """Stable ordering for deterministic pruning."""
    return (
        _PROTOCOLS.index(c.protocol),
        _ALGORITHMS.index(c.algorithm),
        c.channels,
        c.chunk_size,
    )


def prune_search_space(
    grid: Sequence[RcclConfig],
    *,
    arch: str,
    size_bytes: int,
    max_configs: int = 8,
) -> list[RcclConfig]:
    """Prune *grid* to a bounded, arch-/size-guarded candidate set.

    The sweep space is narrowed so it cannot exceed *max_configs* (the skill
    targets ``<=8`` configs/arch). Guards:

    * **Size guard** — small messages are latency-bound, so LL/LL128 protocols
      and small chunk sizes are preferred; large messages are bandwidth-bound,
      so ``Simple`` is preferred. Mid-range keeps a mix.
    * **Arch guard** — reserved for arch-specific exclusions; currently a stable
      no-op that keeps the result deterministic.

    Parameters
    ----------
    grid:        The candidate configs to prune (non-empty list of RcclConfig).
    arch:        Non-empty GPU arch string (e.g. ``gfx90a``).
    size_bytes:  Non-negative message size the sweep targets.
    max_configs: Upper bound on the returned set; must be >= 1.

    Returns
    -------
    list[RcclConfig]
        A deterministic, bounded subset (never empty when *grid* is non-empty).

    Raises
    ------
    ValueError
        If *grid* is not a non-empty list, *arch* is empty, *size_bytes* is not
        a non-negative int, or *max_configs* < 1.
    """
    if not isinstance(grid, (list, tuple)) or not grid:
        raise ValueError("grid must be a non-empty list of RcclConfig")
    if not all(isinstance(c, RcclConfig) for c in grid):
        raise ValueError("grid must contain only RcclConfig instances")
    if not isinstance(arch, str) or not arch.strip():
        raise ValueError("arch must be a non-empty string")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
        raise ValueError(f"size_bytes must be an int, got {type(size_bytes)!r}")
    if size_bytes < 0:
        raise ValueError(f"size_bytes must be non-negative, got {size_bytes}")
    if isinstance(max_configs, bool) or not isinstance(max_configs, int):
        raise ValueError(f"max_configs must be an int, got {type(max_configs)!r}")
    if max_configs < 1:
        raise ValueError(f"max_configs must be >= 1, got {max_configs}")

    candidates = sorted(set(grid), key=_sort_key)

    small = size_bytes <= _SMALL_MSG_BYTES
    large = size_bytes >= _LARGE_MSG_BYTES

    if small:
        # Latency-bound: prefer LL/LL128 and drop oversized chunks.
        filtered = [
            c
            for c in candidates
            if c.protocol in _LATENCY_PROTOCOLS and c.chunk_size <= _SMALL_MSG_CHUNK_CEIL
        ]
    elif large:
        # Bandwidth-bound: prefer Simple (keep it represented).
        filtered = [c for c in candidates if c.protocol == "Simple"]
    else:
        # Mid-range: keep the full ordering, mix of protocols.
        filtered = list(candidates)

    # Guard against a filter that removed everything: fall back to full grid.
    if not filtered:
        filtered = list(candidates)

    # Ensure at least one preferred protocol survives for the small/large case
    # even if the ceiling filter was aggressive.
    if small and not filtered:
        filtered = [c for c in candidates if c.protocol in _LATENCY_PROTOCOLS]
    if large and "Simple" not in {c.protocol for c in filtered}:
        simple = [c for c in candidates if c.protocol == "Simple"]
        filtered = simple + filtered

    return filtered[:max_configs]


def tune_once_and_cache(
    key: TuneKey,
    candidates: Sequence[RcclConfig],
    *,
    correctness_fn: Callable[..., int],
    perf_fn: Callable[[RcclConfig], float],
    cache: MutableMapping[TuneKey, RcclConfig],
    size_bytes: int,
    baseline_config: RcclConfig | None = None,
    noise_fraction: float = 0.02,
) -> TuneResult:
    """Sweep *candidates* once, parity-check, A/B vs baseline, cache the winner.

    Discipline
    ----------
    * **Tune-once/cache** — if *key* is already in *cache*, the cached winner is
      returned immediately (``from_cache=True``) with no perf measurement.
    * **Parity** — each candidate is checked with ``correctness_fn`` twice, with
      ``tuning_enabled=True`` and ``tuning_enabled=False``. Both must report
      ``#wrong == 0``; a config that corrupts results with tuning on is rejected
      no matter how fast it is.
    * **A/B gate** — when *baseline_config* is given, the fastest correct
      candidate is adopted only if it beats the baseline runtime by more than
      *noise_fraction* (F-R9-020 noise-aware perf gate); otherwise the baseline
      is kept.

    Parameters
    ----------
    key:             Sweep identity; the winner is cached under it.
    candidates:      Non-empty list of :class:`RcclConfig` to sweep.
    correctness_fn:  ``fn(config, *, tuning_enabled) -> int`` returning ``#wrong``.
    perf_fn:         ``fn(config) -> float`` runtime; lower is better.
    cache:           Mutable mapping used for tune-once/cache.
    size_bytes:      Non-negative message size (recorded, informs A/B context).
    baseline_config: Fixed best-known/default for the A/B gate; optional.
    noise_fraction:  Fractional improvement the tuned config must exceed; >= 0.

    Returns
    -------
    TuneResult

    Raises
    ------
    ValueError
        On any invalid input (bad key, empty/typed candidates, non-callable
        oracle, negative noise fraction, ...).
    AutotuneError
        When no candidate passes the correctness parity check.
    """
    if not isinstance(key, TuneKey):
        raise ValueError(f"key must be a TuneKey, got {type(key)!r}")
    if not isinstance(candidates, (list, tuple)) or not candidates:
        raise ValueError("candidates must be a non-empty list of RcclConfig")
    if not all(isinstance(c, RcclConfig) for c in candidates):
        raise ValueError("candidates must contain only RcclConfig instances")
    if not callable(correctness_fn):
        raise ValueError("correctness_fn must be callable")
    if not callable(perf_fn):
        raise ValueError("perf_fn must be callable")
    if cache is None or not hasattr(cache, "__setitem__"):
        raise ValueError("cache must be a mutable mapping")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
        raise ValueError(f"size_bytes must be an int, got {type(size_bytes)!r}")
    if size_bytes < 0:
        raise ValueError(f"size_bytes must be non-negative, got {size_bytes}")
    if baseline_config is not None and not isinstance(baseline_config, RcclConfig):
        raise ValueError("baseline_config must be an RcclConfig or None")
    if isinstance(noise_fraction, bool) or not isinstance(noise_fraction, (int, float)):
        raise ValueError("noise_fraction must be a number")
    if noise_fraction < 0:
        raise ValueError(f"noise_fraction must be non-negative, got {noise_fraction}")

    # Tune-once/cache: a prior sweep for this key wins without re-searching.
    if key in cache:
        return TuneResult(
            key=key,
            winner=cache[key],
            evaluations=(),
            from_cache=True,
            beat_baseline=None,
        )

    evaluations: list[ConfigEvaluation] = []
    correct_results: list[tuple[RcclConfig, float]] = []

    for cfg in candidates:
        wrong_enabled = int(correctness_fn(cfg, tuning_enabled=True))
        wrong_disabled = int(correctness_fn(cfg, tuning_enabled=False))
        is_correct = wrong_enabled == 0 and wrong_disabled == 0
        runtime: float | None = None
        if is_correct:
            runtime = float(perf_fn(cfg))
            correct_results.append((cfg, runtime))
        evaluations.append(
            ConfigEvaluation(
                config=cfg,
                correct=is_correct,
                wrong_enabled=wrong_enabled,
                wrong_disabled=wrong_disabled,
                runtime=runtime,
            )
        )

    if not correct_results:
        raise AutotuneError(
            f"no candidate passed correctness parity for {key!r}: "
            "every swept config had #wrong > 0"
        )

    # Fastest correct candidate (lower runtime is better).
    best_cfg, best_runtime = min(correct_results, key=lambda cr: cr[1])

    beat_baseline: bool | None = None
    winner = best_cfg
    if baseline_config is not None:
        base_runtime = float(perf_fn(baseline_config))
        # Noise-aware A/B: adopt tuned config only if it clears the noise band.
        threshold = base_runtime * (1.0 - noise_fraction)
        if best_runtime < threshold:
            beat_baseline = True
            winner = best_cfg
        else:
            beat_baseline = False
            winner = baseline_config

    cache[key] = winner
    return TuneResult(
        key=key,
        winner=winner,
        evaluations=tuple(evaluations),
        from_cache=False,
        beat_baseline=beat_baseline,
    )


__all__ = [
    "RcclConfig",
    "TuneKey",
    "ConfigEvaluation",
    "TuneResult",
    "AutotuneError",
    "default_config_grid",
    "prune_search_space",
    "tune_once_and_cache",
]
