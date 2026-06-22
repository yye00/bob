"""Infra-error transient classifier + unlimited spawn-layer recovery (F-R7-478).

Wraps every Claude-CLI sub-agent spawn with a shared helper that:
1. Classifies the exit via ``classify_exit`` using hot-reloadable YAML patterns.
2. Retries UNLIMITED times on transient errors with exponential backoff (cap 300 s).
3. Never increments any budget counter (refinement_attempts, bootstrap_attempts,
   verification_failures, research_iterations) on transient retries.
4. Logs each retry attempt to ``.bob3/agent_logs/<job>.retry.jsonl``.
5. Warns (but does not halt) on retry storms (>20 retries in 10 min).
6. Runs a health probe before each retry; switches to BROKEN_ENV mode after
   3 consecutive probe failures (600 s backoff, error-level logs, feature continues).
7. Cleans up partial workspace state between retries.
8. Enforces a per-feature cost ceiling (default $50) as a soft circuit breaker.

Mid-work-crash classification:
- Still counts as one refinement attempt (preserves F-R6-300 behaviour).
- EXCEPT when work_events > 0 AND duration_ms == 0 (JSONL serialisation race /
  SIGPIPE / orphan-process pattern) → reclassified as TRANSIENT, no budget charge.
"""

from __future__ import annotations

import asyncio
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Deque, Literal

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ExitClassification = Literal["transient", "mid_work_crash", "real_failure"]

# Callable that the retry loop invokes to perform the actual spawn.
# Returns a dict with at minimum: {"exit_code": int, "stderr": str,
# "duration_ms": int, "work_events": int, "cost_usd": float}
SpawnCallable = Callable[[], Awaitable[dict[str, Any]]]


@dataclass
class RetryState:
    """Per-feature retry accounting used by spawn_with_retry."""

    feature_id: str
    job_name: str
    attempt: int = 0
    total_cost_usd: float = 0.0
    # Timestamps of recent retries for storm detection (unix seconds).
    recent_retry_timestamps: Deque[float] = field(default_factory=deque)
    consecutive_probe_failures: int = 0
    broken_env: bool = False


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).parents[3] / "config" / "spawn_retry.yaml"
_DEFAULT_PATTERNS: list[str] = [
    "429",
    "rate.?limit",
    "ECONNRESET",
    "ETIMEDOUT",
    "ENOENT.*claude",
    "No such file.*claude",
    "spawn.*ENOENT",
    "shared API key and is being deprecated",
]


def load_patterns(config_path: str | os.PathLike[str] | None = None) -> list[re.Pattern[str]]:
    """Hot-reload TRANSIENT_PATTERNS from config/spawn_retry.yaml.

    Called on every spawn attempt so pattern changes take effect immediately
    without restarting the orchestration loop.

    Args:
        config_path: Override path for testing.  Defaults to the canonical
                     ``config/spawn_retry.yaml`` relative to this package.

    Returns:
        Compiled regex patterns.  Falls back to ``_DEFAULT_PATTERNS`` when
        the file is missing, unreadable, or malformed.
    """
    path = Path(config_path) if config_path is not None else _CONFIG_PATH
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        raw_patterns = data.get("TRANSIENT_PATTERNS", _DEFAULT_PATTERNS)
        if not isinstance(raw_patterns, list):
            raise ValueError("TRANSIENT_PATTERNS must be a list")
        return [re.compile(p, re.IGNORECASE) for p in raw_patterns]
    except FileNotFoundError:
        logger.debug("spawn_retry: config not found at %s; using defaults", path)
        return [re.compile(p, re.IGNORECASE) for p in _DEFAULT_PATTERNS]
    except Exception as exc:  # noqa: BLE001
        logger.warning("spawn_retry: failed to load %s: %s; using defaults", path, exc)
        return [re.compile(p, re.IGNORECASE) for p in _DEFAULT_PATTERNS]


def _load_config(config_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load full YAML config dict, falling back to hardcoded defaults."""
    path = Path(config_path) if config_path is not None else _CONFIG_PATH
    defaults: dict[str, Any] = {
        "BACKOFF_BASE_SECONDS": 1.0,
        "BACKOFF_MULTIPLIER": 2.0,
        "BACKOFF_CAP_SECONDS": 300,
        "HEALTH_PROBE_TIMEOUT_SECONDS": 5,
        "HEALTH_PROBE_MAX_CONSECUTIVE_FAILURES": 3,
        "HEALTH_PROBE_BROKEN_ENV_BACKOFF_SECONDS": 600,
        "RETRY_STORM_MAX_COUNT": 20,
        "RETRY_STORM_WINDOW_SECONDS": 600,
        "RETRY_COST_CEILING_USD": 50.0,
    }
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        merged = {**defaults, **data}
        return merged
    except Exception:  # noqa: BLE001
        return defaults


# ---------------------------------------------------------------------------
# Exit classification
# ---------------------------------------------------------------------------


def classify_exit(
    exit_code: int | None,
    stderr: str | None,
    duration_ms: int | None = None,
    work_events: int | None = None,
    config_path: str | os.PathLike[str] | None = None,
) -> ExitClassification:
    """Classify a Claude sub-agent exit into one of three buckets.

    Args:
        exit_code: Process exit code (0 = success).
        stderr: Combined stderr text from the sub-agent process.
        duration_ms: Milliseconds the sub-agent ran.  When work_events > 0
                     AND duration_ms == 0 this is a JSONL-serialisation race
                     / SIGPIPE signature → reclassified as TRANSIENT.
        work_events: Count of substantive progress events written to disk.
                     Used for the duration_ms == 0 reclassification rule.
        config_path: Override config file path (for testing).

    Returns:
        ``"transient"``        – infra error, retry unlimited, no budget charge.
        ``"mid_work_crash"``   – sub-agent did real work then died; charge one
                                 refinement attempt (F-R6-300).
        ``"real_failure"``     – implementation error; charge budget normally.
    """
    if exit_code is not None and not isinstance(exit_code, int):
        raise TypeError(f"exit_code must be int or None, got {type(exit_code).__name__!r}")
    if work_events is not None and not isinstance(work_events, int):
        raise TypeError(f"work_events must be int or None, got {type(work_events).__name__!r}")
    if duration_ms is not None and not isinstance(duration_ms, int):
        raise TypeError(f"duration_ms must be int or None, got {type(duration_ms).__name__!r}")

    if exit_code == 0:
        return "real_failure"  # clean exit; caller should treat as success

    stderr_text = (stderr or "").lower()

    # Hot-reload patterns from config.
    patterns = load_patterns(config_path)
    for pattern in patterns:
        if pattern.search(stderr or ""):
            return "transient"

    # Special reclassification: mid-work-crash with duration_ms == 0 is
    # a JSONL serialisation race / SIGPIPE / orphan-process pattern, not a
    # real sub-agent decision to abort.  Treat as transient.
    _work_events = work_events or 0
    _duration_ms = duration_ms if duration_ms is not None else -1
    if _work_events > 0 and _duration_ms == 0:
        logger.debug(
            "classify_exit: work_events=%d, duration_ms=0 → reclassifying as transient "
            "(JSONL serialisation race / SIGPIPE signature)",
            _work_events,
        )
        return "transient"

    # If the sub-agent wrote substantive progress it's a mid-work crash.
    if _work_events > 0:
        return "mid_work_crash"

    # Heuristic stderr signals for mid-work crash without progress events.
    mid_work_markers = (
        "fatal error in message reader",
        "message reader crashed",
        "messagereader",
        "shutdown crash",
    )
    if any(m in stderr_text for m in mid_work_markers):
        return "mid_work_crash"

    return "real_failure"


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


def _run_health_probe(timeout_seconds: float = 5.0) -> bool:
    """Run ``claude --version`` as a health probe.

    Returns True when the probe succeeds within ``timeout_seconds``.
    """
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


# ---------------------------------------------------------------------------
# Retry log
# ---------------------------------------------------------------------------


def _write_retry_log(
    log_path: Path,
    attempt: int,
    classification: ExitClassification,
    matched_pattern: str | None,
    backoff_seconds: float,
    elapsed_total: float,
) -> None:
    """Append a retry event to the feature's .retry.jsonl log."""
    entry = {
        "attempt": attempt,
        "classification": classification,
        "matched_pattern": matched_pattern,
        "backoff_seconds": backoff_seconds,
        "elapsed_total": elapsed_total,
        "ts": time.time(),
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError as exc:
        logger.debug("spawn_retry: could not write retry log %s: %s", log_path, exc)


# ---------------------------------------------------------------------------
# Partial-state cleanup
# ---------------------------------------------------------------------------


def _cleanup_partial_state(feature_id: str, workspace: str | os.PathLike[str] | None) -> None:
    """Remove orphan lock files and partial git index entries for feature_id.

    Ensures retry N+1 starts from the same baseline as retry 1 (idempotency AC).
    """
    if workspace is None:
        return
    ws = Path(workspace)

    # Orphan lock file under .bob3/locks/<feature_id>
    lock_path = ws / ".bob3" / "locks" / feature_id
    if lock_path.exists():
        try:
            lock_path.unlink()
            logger.debug("spawn_retry: removed orphan lock %s", lock_path)
        except OSError as exc:
            logger.debug("spawn_retry: could not remove lock %s: %s", lock_path, exc)

    # Partial git index: reset any uncommitted changes in the workspace
    # WITHOUT destroying untracked files (they may be intentional mid-state).
    git_dir = ws / ".git"
    if git_dir.exists():
        try:
            subprocess.run(
                ["git", "checkout", "--", "."],
                cwd=ws,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


# ---------------------------------------------------------------------------
# Retry storm detection
# ---------------------------------------------------------------------------


def _check_retry_storm(
    state: RetryState,
    storm_max: int,
    storm_window_seconds: float,
) -> bool:
    """Return True if a retry storm is detected and a WARN should be emitted."""
    now = time.time()
    cutoff = now - storm_window_seconds
    # Prune old timestamps
    while state.recent_retry_timestamps and state.recent_retry_timestamps[0] < cutoff:
        state.recent_retry_timestamps.popleft()
    state.recent_retry_timestamps.append(now)
    return len(state.recent_retry_timestamps) > storm_max


# ---------------------------------------------------------------------------
# Backoff calculation
# ---------------------------------------------------------------------------


def _compute_backoff(
    attempt: int,
    base: float,
    multiplier: float,
    cap: float,
    broken_env: bool,
    broken_env_backoff: float,
) -> float:
    """Compute exponential backoff capped at ``cap`` seconds."""
    if broken_env:
        return broken_env_backoff
    try:
        raw = base * (multiplier ** attempt)
    except OverflowError:
        return cap
    return min(raw, cap)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def spawn_with_retry(
    spawn_fn: SpawnCallable,
    *,
    feature_id: str,
    job_name: str,
    workspace: str | os.PathLike[str] | None = None,
    log_dir: str | os.PathLike[str] | None = None,
    config_path: str | os.PathLike[str] | None = None,
    # Callbacks for budget integration (never mutated on transient retries).
    on_real_failure: Callable[[dict[str, Any]], None] | None = None,
    on_mid_work_crash: Callable[[dict[str, Any]], None] | None = None,
    on_cost_update: Callable[[float], None] | None = None,
    # Overrideable for testing.
    sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    probe_fn: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Wrap a Claude spawn callable with unlimited transient-retry logic.

    Retries UNLIMITED times when ``classify_exit`` returns ``"transient"``.
    Exponential backoff capped at 300 s (configurable via spawn_retry.yaml).

    Budget counters (refinement_attempts, bootstrap_attempts,
    verification_failures, research_iterations) are NEVER incremented on
    transient retries.  Only ``on_real_failure`` and ``on_mid_work_crash``
    callbacks are invoked, and only for non-transient outcomes.

    Args:
        spawn_fn: Async callable that performs the actual spawn and returns a
                  result dict with at minimum: {exit_code, stderr, duration_ms,
                  work_events, cost_usd}.
        feature_id: Feature UUID used for log naming and lock cleanup.
        job_name: Short name for log file disambiguation.
        workspace: Workspace directory for partial-state cleanup.
        log_dir: Override directory for the .retry.jsonl log.
        config_path: Override config/spawn_retry.yaml path (for testing).
        on_real_failure: Called once when classification is ``real_failure``.
        on_mid_work_crash: Called once when classification is ``mid_work_crash``.
        on_cost_update: Called after each spawn with the spawn cost.
        sleep_fn: Async sleep override for testing.
        probe_fn: Health probe override for testing.

    Returns:
        The result dict returned by ``spawn_fn`` on the final (non-transient)
        attempt, or the last result dict when a cost ceiling is hit.
    """
    cfg = _load_config(config_path)
    backoff_base: float = float(cfg.get("BACKOFF_BASE_SECONDS", 1.0))
    backoff_multiplier: float = float(cfg.get("BACKOFF_MULTIPLIER", 2.0))
    backoff_cap: float = float(cfg.get("BACKOFF_CAP_SECONDS", 300.0))
    probe_timeout: float = float(cfg.get("HEALTH_PROBE_TIMEOUT_SECONDS", 5.0))
    probe_max_failures: int = int(cfg.get("HEALTH_PROBE_MAX_CONSECUTIVE_FAILURES", 3))
    broken_env_backoff: float = float(cfg.get("HEALTH_PROBE_BROKEN_ENV_BACKOFF_SECONDS", 600.0))
    storm_max: int = int(cfg.get("RETRY_STORM_MAX_COUNT", 20))
    storm_window: float = float(cfg.get("RETRY_STORM_WINDOW_SECONDS", 600.0))
    cost_ceiling: float = float(cfg.get("RETRY_COST_CEILING_USD", 50.0))

    _sleep = sleep_fn or asyncio.sleep
    _probe = probe_fn or (lambda: _run_health_probe(probe_timeout))

    state = RetryState(feature_id=feature_id, job_name=job_name)

    # Determine log path
    if log_dir is not None:
        _log_dir = Path(log_dir)
    elif workspace is not None:
        _log_dir = Path(workspace) / ".bob3" / "agent_logs"
    else:
        _log_dir = Path(".bob3") / "agent_logs"
    log_path = _log_dir / f"{job_name}.retry.jsonl"

    start_time = time.time()
    last_result: dict[str, Any] = {}

    while True:
        state.attempt += 1

        # --- Perform spawn ---
        result = await spawn_fn()
        last_result = result

        exit_code: int | None = result.get("exit_code")
        stderr: str | None = result.get("stderr")
        duration_ms: int | None = result.get("duration_ms")
        work_events: int | None = result.get("work_events")
        cost_usd: float = float(result.get("cost_usd") or 0.0)

        # Accumulate cost regardless of outcome.
        state.total_cost_usd += cost_usd
        if on_cost_update is not None:
            on_cost_update(cost_usd)

        # Success path.
        if exit_code == 0:
            return result

        # Classify the exit.
        classification = classify_exit(
            exit_code=exit_code,
            stderr=stderr,
            duration_ms=duration_ms,
            work_events=work_events,
            config_path=config_path,
        )

        elapsed_total = time.time() - start_time

        if classification == "transient":
            # --- Retry storm detection ---
            if _check_retry_storm(state, storm_max, storm_window):
                logger.warning(
                    "spawn_retry: WARN retry_storm feature=%s retries=%d in %.0fs window",
                    feature_id,
                    len(state.recent_retry_timestamps),
                    storm_window,
                )

            # --- Cost ceiling check ---
            if state.total_cost_usd >= cost_ceiling:
                logger.warning(
                    "spawn_retry: retry_cost_ceiling hit for feature=%s "
                    "(accumulated=%.2f >= ceiling=%.2f); pausing for next round",
                    feature_id,
                    state.total_cost_usd,
                    cost_ceiling,
                )
                result["retry_cost_ceiling"] = True
                result["total_retry_cost_usd"] = state.total_cost_usd
                return result

            # --- Pre-retry health probe ---
            probe_ok = _probe()
            if not probe_ok:
                state.consecutive_probe_failures += 1
                if state.consecutive_probe_failures >= probe_max_failures:
                    if not state.broken_env:
                        logger.error(
                            "spawn_retry: env_broken detected for feature=%s "
                            "(probe failed %d consecutive times); switching to "
                            "BROKEN_ENV mode (backoff=%ds)",
                            feature_id,
                            state.consecutive_probe_failures,
                            int(broken_env_backoff),
                        )
                        state.broken_env = True
                    _write_retry_log(log_path, state.attempt, classification, None, broken_env_backoff, elapsed_total)
                    await _sleep(broken_env_backoff)
                    continue
            else:
                state.consecutive_probe_failures = 0
                if state.broken_env:
                    logger.info("spawn_retry: env recovered for feature=%s", feature_id)
                    state.broken_env = False

            # --- Compute backoff ---
            backoff = _compute_backoff(
                attempt=state.attempt - 1,
                base=backoff_base,
                multiplier=backoff_multiplier,
                cap=backoff_cap,
                broken_env=state.broken_env,
                broken_env_backoff=broken_env_backoff,
            )

            # --- Detect matched pattern for logging ---
            patterns = load_patterns(config_path)
            matched = next(
                (p.pattern for p in patterns if p.search(stderr or "")),
                None,
            )

            _write_retry_log(log_path, state.attempt, classification, matched, backoff, elapsed_total)

            logger.info(
                "spawn_retry: transient retry feature=%s attempt=%d "
                "backoff=%.1fs matched_pattern=%r",
                feature_id,
                state.attempt,
                backoff,
                matched,
            )

            # --- Clean up partial state before retry ---
            _cleanup_partial_state(feature_id, workspace)

            await _sleep(backoff)
            continue

        elif classification == "mid_work_crash":
            if on_mid_work_crash is not None:
                on_mid_work_crash(result)
            return result

        else:  # real_failure
            if on_real_failure is not None:
                on_real_failure(result)
            return result


__all__ = [
    "ExitClassification",
    "RetryState",
    "SpawnCallable",
    "classify_exit",
    "load_patterns",
    "spawn_with_retry",
]
