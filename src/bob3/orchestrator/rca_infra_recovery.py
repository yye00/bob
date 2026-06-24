"""F-R7-479: RCA-layer infra-error recovery — second-line defense against false NH.

When the orchestrator is about to transition a feature to ``needs_human``,
``auto_reset_if_infra`` is called first. It inspects the history of failed
attempts and determines if ALL failures were infrastructure-caused. If so, the
feature is reset to ``ready`` instead of being handed to a human, and any
novel infra error signature is auto-appended to config/spawn_retry.yaml so the
*first-line* spawn-layer guard (F-R7-478) catches it in the future.

Auto-reset cap: a feature can only be auto-reset this way at most 3 times per
generation. On the 4th attempt, needs_human stands regardless of verdict.

Cross-feature crash clustering: if multiple features crashed in the same 30-min
window with similar exit signatures, that boosts the infra_only verdict.

Pattern graduation: a MEDIUM-confidence discovered pattern that matches a
successful spawn within 24h is promoted to HIGH confidence; otherwise it is
pruned on the next housekeeping pass.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import pathlib
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPAWN_RETRY_CONFIG = pathlib.Path("config/spawn_retry.yaml")
_RCA_RESETS_JSONL = pathlib.Path("reviews/rca_resets.jsonl")

# Maximum RCA-driven resets before NH stands
_MAX_AUTO_RESETS = 3

# Cross-feature clustering window (seconds)
_CLUSTER_WINDOW_SECS = 30 * 60  # 30 minutes

# Agent log directory
_AGENT_LOGS_DIR = pathlib.Path(".bob3/agent_logs")

# Known transient infra heuristics (augmented from spawn_retry.yaml at runtime)
_BUILTIN_INFRA_PATTERNS: tuple[str, ...] = (
    "shared API key and is being deprecated",
    "Application 'Claude Code' (Production Restricted) is a shared API key",
    "self signed certificate in certificate chain",
    "ECONNRESET",
    "ETIMEDOUT",
    "connection reset by peer",
    "Error: connect ENOENT",
    "ENOENT.*socket",
    "spawn.*ENOENT",
    "getaddrinfo ENOTFOUND",
    "net::ERR_",
    "502 Bad Gateway",
    "503 Service Unavailable",
    "504 Gateway Timeout",
    "rate_limit_error",
    "overloaded_error",
    "APIStatusError.*529",
    "APIConnectionError",
    "read ECONNRESET",
)

Verdict = Literal["infra_only", "feature_defect", "mixed"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_discovered_patterns() -> list[str]:
    """Load discovered patterns from config/spawn_retry.yaml."""
    if not _SPAWN_RETRY_CONFIG.exists():
        return []
    try:
        with _SPAWN_RETRY_CONFIG.open() as fh:
            data = yaml.safe_load(fh) or {}
        discovered = data.get("discovered_patterns", [])
        return [p["pattern"] for p in discovered if isinstance(p, dict) and "pattern" in p]
    except Exception:
        logger.debug("rca_infra_recovery: failed to load spawn_retry.yaml", exc_info=True)
        return []


def _all_infra_patterns() -> tuple[str, ...]:
    """Combine builtin + discovered patterns."""
    discovered = _load_discovered_patterns()
    return _BUILTIN_INFRA_PATTERNS + tuple(discovered)


def _matches_infra_pattern(text: str) -> bool:
    """True if text matches any known infra pattern (regex or substring)."""
    if not text:
        return False
    for pattern in _all_infra_patterns():
        try:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        except re.error:
            if pattern.lower() in text.lower():
                return True
    return False


def _has_work_events(progress_path: pathlib.Path) -> bool:
    """Return True if the progress.jsonl contains real work events."""
    _WORK_EVENT_TYPES = frozenset({
        "progress_updated",
        "skill_activation_logged",
        "nondeterminism_detected",
        "tool_use",
        "tool_result",
    })
    if not progress_path.exists():
        return False
    try:
        with progress_path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") in _WORK_EVENT_TYPES:
                        return True
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return False


def _read_stderr_tail(log_path: pathlib.Path, max_bytes: int = 8192) -> str:
    """Read the tail of a stderr log file."""
    if not log_path.exists():
        return ""
    try:
        size = log_path.stat().st_size
        with log_path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _find_feature_logs(feature_id: str) -> list[pathlib.Path]:
    """Find agent log files associated with a feature."""
    if not _AGENT_LOGS_DIR.exists():
        return []
    short_id = feature_id[:8]
    results = []
    try:
        for p in _AGENT_LOGS_DIR.iterdir():
            name = p.name
            if short_id in name or feature_id in name:
                results.append(p)
    except OSError:
        pass
    return results


def _find_recent_logs_for_other_features(
    feature_id: str,
    window_secs: int = _CLUSTER_WINDOW_SECS,
) -> list[tuple[pathlib.Path, float]]:
    """Find agent logs from OTHER features within the cluster window."""
    if not _AGENT_LOGS_DIR.exists():
        return []
    now = time.time()
    cutoff = now - window_secs
    short_id = feature_id[:8]
    results = []
    try:
        for p in _AGENT_LOGS_DIR.iterdir():
            # skip this feature's own logs
            if short_id in p.name or feature_id in p.name:
                continue
            try:
                mtime = p.stat().st_mtime
                if mtime >= cutoff:
                    results.append((p, mtime))
            except OSError:
                pass
    except OSError:
        pass
    return results


def _lcs_length(a: str, b: str) -> int:
    """Longest common subsequence length of two strings (character-level)."""
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sum(block.size for block in matcher.get_matching_blocks())


def _extract_lcs_pattern(texts: list[str]) -> str | None:
    """Extract the longest common substring across all texts.

    Uses difflib to find the largest common block. Returns None if the
    common part is too short to be a useful regex anchor.
    """
    if not texts:
        return None
    if len(texts) == 1:
        # single text — extract the "interesting" part
        snippet = texts[0][:200].strip()
        return snippet if len(snippet) >= 10 else None

    # Iteratively narrow down common text
    common = texts[0]
    for other in texts[1:]:
        matcher = difflib.SequenceMatcher(None, common, other, autojunk=False)
        blocks = matcher.get_matching_blocks()
        if not blocks:
            return None
        # pick the longest block
        best = max(blocks, key=lambda b: b.size)
        if best.size < 8:
            return None
        common = common[best.a: best.a + best.size]

    # Clean up to make a safe regex anchor
    anchor = common.strip()
    if len(anchor) < 8:
        return None
    return re.escape(anchor)


def _count_rca_resets(feature_id: str) -> int:
    """Count how many RCA-driven resets have been recorded for this feature."""
    if not _RCA_RESETS_JSONL.exists():
        return 0
    count = 0
    try:
        with _RCA_RESETS_JSONL.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if ev.get("feature_id") == feature_id:
                        count += 1
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return count


def _emit_rca_reset_event(
    feature_id: str,
    verdict: Verdict,
    novel_pattern: str | None,
    evidence: dict,
) -> None:
    """Emit a structured event to reviews/rca_resets.jsonl."""
    _RCA_RESETS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "feature_id": feature_id,
        "verdict": verdict,
        "novel_pattern": novel_pattern,
        "evidence": evidence,
    }
    try:
        with _RCA_RESETS_JSONL.open("a") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError:
        logger.warning("rca_infra_recovery: failed to emit rca_reset event", exc_info=True)


def _append_discovered_pattern(
    pattern: str,
    feature_id: str,
) -> None:
    """Append a novel pattern to config/spawn_retry.yaml under discovered_patterns."""
    _SPAWN_RETRY_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if _SPAWN_RETRY_CONFIG.exists():
        try:
            with _SPAWN_RETRY_CONFIG.open() as fh:
                existing = yaml.safe_load(fh) or {}
        except Exception:
            existing = {}

    # Deduplicate
    discovered = existing.get("discovered_patterns", [])
    for entry in discovered:
        if isinstance(entry, dict) and entry.get("pattern") == pattern:
            return  # already present

    discovered.append({
        "pattern": pattern,
        "confidence": "medium",
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "feature_id": feature_id,
    })
    existing["discovered_patterns"] = discovered

    with _SPAWN_RETRY_CONFIG.open("w") as fh:
        yaml.dump(existing, fh, default_flow_style=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_attempts(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> Verdict:
    """Classify the failure history of a feature.

    Heuristics (need 2 of 4 to return infra_only):
    1. All stderr tails match a known infra pattern.
    2. No work events in any progress.jsonl (pure spawn-time failure).
    3. Cross-feature crash cluster: ≥1 other feature crashed in same 30-min
       window with similar exit signature.
    4. Zero turns + zero duration in ALL attempts (SDK never started work).

    Returns
    -------
    "infra_only"    — All failures appear infrastructure-caused.
    "feature_defect" — At least one failure has evidence of real work + non-infra error.
    "mixed"          — Mix of infra and non-infra failures.
    """
    ws = pathlib.Path(workspace) if workspace else pathlib.Path(".")
    progress_path = ws / ".bob3" / "progress.jsonl"

    # Gather log files for this feature
    feature_logs = _find_feature_logs(feature_id)
    stderr_tails = [_read_stderr_tail(p) for p in feature_logs if p.suffix == ".log"]

    has_work = _has_work_events(progress_path)

    # Heuristic 1: all stderrs match infra pattern
    if stderr_tails:
        h1 = all(_matches_infra_pattern(t) for t in stderr_tails if t)
    else:
        h1 = False  # no evidence → can't confirm infra

    # Heuristic 2: no work events
    h2 = not has_work

    # Heuristic 3: cross-feature crash cluster
    other_recent = _find_recent_logs_for_other_features(feature_id)
    clustered_infra = 0
    for other_log, _ in other_recent:
        tail = _read_stderr_tail(other_log)
        if _matches_infra_pattern(tail):
            clustered_infra += 1
    h3 = clustered_infra >= 1

    # Heuristic 4: all logs exist in agent_logs but are very short (pure spawn failures)
    if feature_logs:
        h4 = all(
            p.stat().st_size < 1024
            for p in feature_logs
            if p.exists()
        )
    else:
        h4 = False

    logger.debug(
        "rca_infra_recovery classify_attempts(%s): h1=%s h2=%s h3=%s h4=%s",
        feature_id[:8],
        h1,
        h2,
        h3,
        h4,
    )

    if has_work:
        # Real work happened → can never be pure infra_only regardless of other signals.
        # If there are infra signals (stderr patterns or cluster), classify as mixed.
        if h1 or h3:
            return "mixed"
        return "feature_defect"

    # No work happened. Need ≥2 heuristics where at least one is an
    # "infra-positive" signal (h1 or h3) to conclude infra_only.
    # h2 (no work) and h4 (tiny logs) are necessary but not sufficient alone —
    # they don't distinguish infra failures from a feature that just never ran.
    infra_positive = h1 or h3  # directly observed infra evidence
    circumstantial = h2 or h4  # consistent with infra but not proof

    if infra_positive and circumstantial:
        return "infra_only"
    elif infra_positive:
        # Single strong signal with no corroboration → still lean infra
        return "infra_only"
    else:
        # No observed infra evidence at all → feature defect
        return "feature_defect"


def harvest_novel_pattern(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> str | None:
    """Extract a regex from N matching stderr tails using longest-common-subsequence.

    Returns None if no pattern emerges (stderrs too dissimilar or too short).
    """
    feature_logs = _find_feature_logs(feature_id)
    stderr_tails = []
    for p in feature_logs:
        if not p.suffix == ".log":
            continue
        tail = _read_stderr_tail(p, max_bytes=2000)
        if tail and not _matches_infra_pattern(tail):
            # Only harvest from tails that don't already match known patterns
            stderr_tails.append(tail)

    if not stderr_tails:
        # Try all tails
        stderr_tails = [_read_stderr_tail(p, max_bytes=2000) for p in feature_logs if p.suffix == ".log"]
        stderr_tails = [t for t in stderr_tails if t]

    if len(stderr_tails) < 2:
        if len(stderr_tails) == 1 and len(stderr_tails[0]) >= 10:
            # Single log — extract the first "error-like" line
            for line in stderr_tails[0].splitlines():
                line = line.strip()
                if len(line) >= 10 and ("error" in line.lower() or "fail" in line.lower() or "ENOENT" in line):
                    return re.escape(line[:80])
        return None

    pattern = _extract_lcs_pattern(stderr_tails)
    return pattern


def auto_reset_if_infra(
    feature_id: str,
    project_id: str,
    db_update_fn,
    workspace: str | os.PathLike[str] | None = None,
    failed_acs: list[str] | None = None,
    refinement_attempts: int | None = None,
) -> bool:
    """Called by run_loop BEFORE transitioning a feature to needs_human.

    Two recovery paths:

    1. **Infra-only** (existing F-R7-479 behavior): all failures were
       infrastructure-caused → reset to ready with refinement_attempts=0.

    2. **Code-emission defect** (F-R7-479 extension): verification gate failed
       on behavior/integration/pytest ACs and refinement_attempts < 5 → grant a
       fresh attempt by transitioning to ready WITHOUT resetting attempt count.
       Logs sentinel ``rca_granted_fresh_attempt=<feature_id>:<classification>``.

    Returns True when a reset happened (skip needs_human), False otherwise.

    Parameters
    ----------
    feature_id : str
    project_id : str
    db_update_fn : callable
        A callable ``(feature_id, **kwargs)`` that updates the feature in the DB.
        Signature matches ``bob3.db.update_feature``.
    workspace : str or Path, optional
    failed_acs : list[str], optional
        AC strings (or error messages) that caused verification to fail.
        When provided, enables the code-emission-defect recovery path.
    refinement_attempts : int, optional
        Current attempt count. Required to apply the attempt cap for
        code_emission_defect classification.
    """
    from bob3.orchestrator.rca_attempt_budget import (
        classify_verification_failure,
        should_grant_fresh_attempt,
    )

    # --- Code-emission-defect path (F-R7-479 extension) ---
    if failed_acs is not None and refinement_attempts is not None:
        classification = classify_verification_failure(failed_acs)
        if classification == "code_emission_defect":
            if should_grant_fresh_attempt(classification, refinement_attempts):
                # Reopen to ready but preserve attempt count (budget accounting intact).
                db_update_fn(feature_id, status="ready")
                logger.info(
                    "rca_infra_recovery: rca_granted_fresh_attempt=%s:%s "
                    "(attempts=%d, keeping budget)",
                    feature_id,
                    classification,
                    refinement_attempts,
                )
                _emit_rca_reset_event(
                    feature_id=feature_id,
                    verdict="feature_defect",
                    novel_pattern=None,
                    evidence={
                        "classification": classification,
                        "refinement_attempts": refinement_attempts,
                        "fresh_attempt_granted": True,
                    },
                )
                return True
            else:
                # Cap reached for code defect — NH stands.
                logger.debug(
                    "rca_infra_recovery: feature %s code_emission_defect at cap "
                    "(attempts=%d >= %d); NH proceeds",
                    feature_id[:8],
                    refinement_attempts,
                    5,
                )
                return False
        elif classification == "spec_ambiguity":
            # Genuinely terminal — NH proceeds.
            logger.debug(
                "rca_infra_recovery: feature %s spec_ambiguity; NH proceeds",
                feature_id[:8],
            )
            return False
        # infra_transient with failed_acs supplied → fall through to infra path below

    # --- Infra-only path (original F-R7-479 behavior) ---
    verdict = classify_attempts(feature_id, workspace=workspace)

    if verdict != "infra_only":
        logger.debug(
            "rca_infra_recovery: feature %s verdict=%s; NH proceeds",
            feature_id[:8],
            verdict,
        )
        return False

    reset_count = _count_rca_resets(feature_id)
    if reset_count >= _MAX_AUTO_RESETS:
        logger.warning(
            "rca_infra_recovery: feature %s auto_reset_cap_reached "
            "(resets=%d >= cap=%d); NH stands regardless of infra_only verdict",
            feature_id[:8],
            reset_count,
            _MAX_AUTO_RESETS,
        )
        _emit_rca_reset_event(
            feature_id=feature_id,
            verdict=verdict,
            novel_pattern=None,
            evidence={"auto_reset_cap_reached": True, "reset_count": reset_count},
        )
        return False

    # Extract novel pattern
    novel_pattern = harvest_novel_pattern(feature_id, workspace=workspace)

    if novel_pattern:
        logger.info(
            "rca_infra_recovery: appending novel pattern to spawn_retry.yaml: %r",
            novel_pattern,
        )
        _append_discovered_pattern(novel_pattern, feature_id)

    # Restore baseline confidence components so readiness is not permanently ratcheted
    try:
        from bob3.db.readiness_recompute import restore_baseline_confidence
        restore_baseline_confidence(feature_id)
        logger.info(
            "rca_infra_recovery: restored baseline confidence for feature %s",
            feature_id[:8],
        )
    except (ValueError, Exception) as exc:
        logger.warning(
            "rca_infra_recovery: could not restore baseline confidence for feature %s: %s",
            feature_id[:8],
            exc,
        )

    # Reset the feature
    db_update_fn(feature_id, status="ready", refinement_attempts=0)

    evidence = {
        "verdict": verdict,
        "novel_pattern": novel_pattern,
        "reset_number": reset_count + 1,
    }
    _emit_rca_reset_event(
        feature_id=feature_id,
        verdict=verdict,
        novel_pattern=novel_pattern,
        evidence=evidence,
    )

    logger.info(
        "rca_infra_recovery: feature %s auto-reset to ready "
        "(infra_only verdict, reset #%d/%d)",
        feature_id[:8],
        reset_count + 1,
        _MAX_AUTO_RESETS,
    )
    return True


def run_pattern_graduation_pass(
    window_hours: int = 24,
    spawn_retry_path: str | os.PathLike[str] | None = None,
    rca_resets_path: str | os.PathLike[str] | None = None,
) -> dict:
    """Promote medium-confidence patterns that matched a successful spawn to high.

    Patterns that did NOT match a successful spawn within ``window_hours`` are
    pruned. Returns a dict with 'promoted' and 'pruned' counts.

    This is called once per orchestration round as a housekeeping job.
    """
    cfg_path = pathlib.Path(spawn_retry_path) if spawn_retry_path else _SPAWN_RETRY_CONFIG
    resets_path = pathlib.Path(rca_resets_path) if rca_resets_path else _RCA_RESETS_JSONL

    if not cfg_path.exists():
        return {"promoted": 0, "pruned": 0}

    try:
        with cfg_path.open() as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        logger.debug("pattern_graduation: failed to load config", exc_info=True)
        return {"promoted": 0, "pruned": 0}

    discovered = data.get("discovered_patterns", [])
    if not discovered:
        return {"promoted": 0, "pruned": 0}

    # Collect successful spawns from rca_resets for comparison
    recent_successes: list[str] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    if resets_path.exists():
        try:
            with resets_path.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                        ts_str = ev.get("timestamp", "")
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str)
                            if ts >= cutoff:
                                # A successful reset means the pattern was useful
                                if ev.get("verdict") == "infra_only":
                                    np = ev.get("novel_pattern")
                                    if np:
                                        recent_successes.append(np)
                    except (json.JSONDecodeError, ValueError):
                        pass
        except OSError:
            pass

    promoted = 0
    pruned = 0
    kept = []
    for entry in discovered:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        confidence = entry.get("confidence", "medium")
        if confidence != "medium":
            kept.append(entry)
            continue

        pattern = entry.get("pattern", "")
        discovered_at_str = entry.get("discovered_at", "")

        # Check if pattern is recent enough (within window_hours)
        try:
            discovered_at = datetime.fromisoformat(discovered_at_str)
            if datetime.now(timezone.utc) - discovered_at > timedelta(hours=window_hours):
                # Prune: too old without promotion
                pruned += 1
                continue
        except (ValueError, TypeError):
            pass

        # Check if any recent success used this pattern
        matched_success = any(pattern == s for s in recent_successes)
        if matched_success:
            entry = dict(entry)
            entry["confidence"] = "high"
            entry["graduated_at"] = datetime.now(timezone.utc).isoformat()
            promoted += 1
        kept.append(entry)

    data["discovered_patterns"] = kept
    try:
        with cfg_path.open("w") as fh:
            yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)
    except OSError:
        logger.warning("pattern_graduation: failed to write config", exc_info=True)

    logger.info(
        "pattern_graduation: promoted=%d pruned=%d",
        promoted,
        pruned,
    )
    return {"promoted": promoted, "pruned": pruned}
