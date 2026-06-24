"""F-R6-300: Classifier that distinguishes sub-agent shutdown crashes from
true process-spawn-time failures.

Context
-------
In Round 5 the orchestrator (``run_loop.py``) treated any sub-agent
result with ``duration_ms == 0`` and ``num_turns == 0`` as a transient
process-spawn-time failure and granted a free retry (R10-015). That
heuristic misclassified claude-code *shutdown* crashes: the SDK
sometimes loses the message reader after the sub-agent has already
produced real work (source files, partial pytest progress, tool calls)
and reports ``duration_ms = 0`` / ``num_turns = 0`` from the harness
even though the sub-agent ran for minutes. The orchestrator then
looped on the same feature without ever charging
``refinement_attempts``, producing the F-R5-202 infinite-loop incident.

This module reads *real* evidence from disk — the per-feature
``.bob/progress.jsonl`` and (when available) the session log — to
decide whether the sub-agent ever did meaningful work. The classifier
never trusts the caller alone; the duration / turns / exit_code /
stderr fields are corroborating signals only.

Decision tree
-------------
1. ``exit_code == 0`` and no other crash indicators  →  ``clean_exit``.
2. There is on-disk evidence the sub-agent did work (progress.jsonl
   records progress / tool-use events, or the session log shows tool
   calls)  →  ``mid_work_crash``. The orchestrator MUST charge a
   refinement attempt so a buggy feature spec cannot loop forever.
3. Otherwise (no progress events, no tool calls, the message reader
   never started)  →  ``spawn_failure``. The orchestrator may grant a
   free retry, capped by ``_MAX_SPAWN_RETRIES`` in ``run_loop``.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable, Literal, TypedDict

logger = logging.getLogger(__name__)


# Event types written to ``.bob/progress.jsonl`` that indicate the
# sub-agent did substantive work. ``progress_updated`` is emitted by
# ``increment_progress`` calls inside the sub-agent; the other entries
# come from auxiliary tooling (build-twice, skill effectiveness, etc.).
_WORK_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "progress_updated",
        "skill_activation_logged",
        "nondeterminism_detected",
        "tool_use",
        "tool_result",
    }
)

# Substrings in the session log / stderr tail that prove the sub-agent
# at least started executing tools, even when progress.jsonl is empty.
_TOOL_LOG_MARKERS: tuple[str, ...] = (
    '"tool_use"',
    '"tool_result"',
    "ToolUseBlock",
    "ToolResultBlock",
    "tool_uses=",
)

# Substrings that identify a claude-code shutdown crash AFTER work
# started. They are advisory only: their presence cannot promote a
# truly-empty run to ``mid_work_crash``, because they appear in many
# spawn-time failures too.
_SHUTDOWN_CRASH_MARKERS: tuple[str, ...] = (
    "Fatal error in message reader",
    "message reader crashed",
    "MessageReader",
)

# F-R6-315: Infra-level transient signatures. The AMD Vertex gateway
# returns HTTP 400 with "shared API key and is being deprecated;
# subsequent requests will continue to work in the meantime" as an
# advisory warning, but claude-code currently surfaces it as a fatal
# exit (exit_code=1, duration_ms=0, num_turns=0). Any classification
# that sees one of these markers should be promoted to ``spawn_failure``
# (free retry, no charge) regardless of the SDK-reported turns/duration,
# because the failure originates in the upstream gateway, not in the
# sub-agent's work.
_TRANSIENT_INFRA_MARKERS: tuple[str, ...] = (
    "shared API key and is being deprecated",
    "Application 'Claude Code' (Production Restricted) is a shared API key",
)

# When the SDK reports zero turns AND zero duration AND we have no
# disk evidence at all, treat that as a spawn-time failure. ``run_loop``
# uses a 100 ms cushion for clock jitter; we keep the same threshold so
# the two heuristics agree on the boundary case.
_SPAWN_DURATION_THRESHOLD_MS: int = 100


CrashKind = Literal["spawn_failure", "mid_work_crash", "clean_exit"]


class ClassificationResult(TypedDict):
    """The classifier's verdict.

    ``kind`` selects the orchestrator branch; ``evidence`` is a short
    human-readable string suitable for logging; ``should_charge_attempt``
    tells the caller whether to call ``increment_refinement_attempts``.
    """

    kind: CrashKind
    evidence: str
    should_charge_attempt: bool


# ---------------------------------------------------------------------------
# Filesystem readers (defensive — never raise on missing/garbled files)
# ---------------------------------------------------------------------------


def _iter_jsonl_events(path: Path) -> Iterable[dict[str, Any]]:
    """Yield decoded JSON objects from a ``.jsonl`` file.

    Missing files, unreadable files, blank lines and malformed JSON
    lines are silently skipped — the classifier must NEVER raise just
    because a sub-agent died before flushing its log.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.debug("crash_classifier: could not read %s: %s", path, exc)
        return


def _count_work_events(path: Path) -> tuple[int, int]:
    """Return ``(work_event_count, total_event_count)`` for a JSONL file.

    A *work* event is one whose ``event_type`` is in
    ``_WORK_EVENT_TYPES``. The total count lets the caller distinguish
    "file missing / never opened" from "file present but only contains
    heartbeats".
    """
    work = 0
    total = 0
    for event in _iter_jsonl_events(path):
        total += 1
        etype = event.get("event_type")
        if isinstance(etype, str) and etype in _WORK_EVENT_TYPES:
            work += 1
    return work, total


def _session_log_has_tool_calls(path: Path | None) -> bool:
    """True iff the session log contains a recognizable tool-use marker."""
    if path is None:
        return False
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                for marker in _TOOL_LOG_MARKERS:
                    if marker in line:
                        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.debug("crash_classifier: could not read %s: %s", path, exc)
        return False
    return False


def _has_transient_infra_signature(stderr_tail: str | None) -> bool:
    """F-R6-315: True iff stderr identifies an upstream-gateway transient
    error that should not consume a refinement attempt."""
    if not stderr_tail:
        return False
    return any(marker in stderr_tail for marker in _TRANSIENT_INFRA_MARKERS)


def _has_shutdown_crash_signature(stderr_tail: str | None) -> bool:
    """True iff ``stderr_tail`` contains a known shutdown-crash marker.

    Advisory only — used to enrich the ``evidence`` string and to push
    a borderline case into ``mid_work_crash`` when we already have
    other evidence of work.
    """
    if not stderr_tail:
        return False
    return any(marker in stderr_tail for marker in _SHUTDOWN_CRASH_MARKERS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_sub_agent_exit(
    progress_jsonl_path: str | os.PathLike[str] | None,
    session_log_path: str | os.PathLike[str] | None,
    duration_ms: int | None,
    num_turns: int | None,
    exit_code: int | None,
    stderr_tail: str | None,
) -> ClassificationResult:
    """Classify a sub-agent termination using real on-disk evidence.

    Parameters
    ----------
    progress_jsonl_path:
        Path to the sub-agent's ``.bob/progress.jsonl``. May be
        ``None`` or point at a missing file — that's a strong signal
        the sub-agent never started.
    session_log_path:
        Path to the raw session transcript, if the harness captured
        one. Used to detect tool calls when ``progress.jsonl`` is
        empty (the SDK can crash before the first event is flushed
        even after tool calls have happened).
    duration_ms, num_turns:
        SDK-reported scalars. Treated as advisory: a sub-agent that
        crashed during shutdown can have ``duration_ms == 0`` even
        after running for several minutes.
    exit_code:
        Process exit code. ``0`` is a hard signal for ``clean_exit``;
        any non-zero (or ``None``) value is treated as an error.
    stderr_tail:
        Last few KiB of stderr. Used to detect the shutdown-crash
        signature so we can mark the evidence string clearly.

    Returns
    -------
    ClassificationResult
        ``kind`` is one of ``'spawn_failure' | 'mid_work_crash' |
        'clean_exit'``. ``should_charge_attempt`` is ``True`` for every
        kind except ``spawn_failure``.
    """
    progress_path = Path(progress_jsonl_path) if progress_jsonl_path else None
    session_path = Path(session_log_path) if session_log_path else None

    work_events = 0
    total_events = 0
    if progress_path is not None:
        work_events, total_events = _count_work_events(progress_path)

    log_has_tools = _session_log_has_tool_calls(session_path)
    has_shutdown_sig = _has_shutdown_crash_signature(stderr_tail)
    duration = duration_ms or 0
    turns = num_turns or 0

    # 1. Clean exit — the only case where exit_code is 0. We still
    # consider this a "charge attempt" outcome from the orchestrator's
    # point of view because a clean exit is a completed attempt, not
    # a free retry.
    if exit_code == 0:
        return ClassificationResult(
            kind="clean_exit",
            evidence=(
                f"exit_code=0; work_events={work_events}; "
                f"turns={turns}; duration_ms={duration}"
            ),
            should_charge_attempt=True,
        )

    # 1b. F-R6-315: AMD gateway transient infra error (deprecated shared
    # API key advisory returned as HTTP 400). Classify as ``spawn_failure``
    # so the run_loop grants a free retry without charging a refinement
    # attempt or decaying confidence. Capped by ``_MAX_SPAWN_RETRIES`` in
    # run_loop, so a permanently-broken gateway still terminates the loop.
    if _has_transient_infra_signature(stderr_tail):
        return ClassificationResult(
            kind="spawn_failure",
            evidence=(
                "transient_infra_error=amd_gateway_deprecated_key; "
                f"exit_code={exit_code}; work_events={work_events}; "
                f"turns={turns}; duration_ms={duration}"
            ),
            should_charge_attempt=False,
        )

    # 2. Mid-work crash — the bug we're fixing. ANY of the following
    # constitutes "the sub-agent did real work before dying":
    #   * progress.jsonl recorded one or more work events
    #   * the session log shows tool calls
    #   * SDK reports at least one turn (turns>=1 means a message
    #     round-trip completed)
    #   * SDK reports non-trivial duration AND a shutdown-crash marker
    did_work = (
        work_events > 0
        or log_has_tools
        or turns >= 1
        or (duration >= _SPAWN_DURATION_THRESHOLD_MS and has_shutdown_sig)
    )
    if did_work:
        reasons: list[str] = []
        if work_events > 0:
            reasons.append(f"progress_jsonl.work_events={work_events}")
        if log_has_tools:
            reasons.append("session_log.tool_calls=yes")
        if turns >= 1:
            reasons.append(f"sdk.turns={turns}")
        if has_shutdown_sig:
            reasons.append("stderr.shutdown_crash_marker=yes")
        reasons.append(f"exit_code={exit_code!r}")
        reasons.append(f"duration_ms={duration}")
        return ClassificationResult(
            kind="mid_work_crash",
            evidence="; ".join(reasons),
            should_charge_attempt=True,
        )

    # 3. Spawn failure — no disk evidence, no turns, no work. This is
    # the only case where the orchestrator may grant a free retry.
    spawn_evidence_bits: list[str] = [
        f"exit_code={exit_code!r}",
        f"duration_ms={duration}",
        f"turns={turns}",
    ]
    if progress_path is None:
        spawn_evidence_bits.append("progress_jsonl=not_provided")
    elif not progress_path.exists():
        spawn_evidence_bits.append("progress_jsonl=missing")
    else:
        spawn_evidence_bits.append(
            f"progress_jsonl.events={total_events} (work=0)"
        )
    if session_path is not None and not log_has_tools:
        spawn_evidence_bits.append("session_log.tool_calls=no")
    if has_shutdown_sig and duration < _SPAWN_DURATION_THRESHOLD_MS:
        # Shutdown marker without any duration is itself a spawn-time
        # symptom (the SDK crashed before any work happened); call it
        # out so the operator can tell the two error modes apart.
        spawn_evidence_bits.append("stderr.shutdown_crash_marker=yes(pre-work)")
    return ClassificationResult(
        kind="spawn_failure",
        evidence="; ".join(spawn_evidence_bits),
        should_charge_attempt=False,
    )


# Public alias matching the acceptance-criteria name expected by the verifier.
classify_exit = classify_sub_agent_exit


__all__ = [
    "ClassificationResult",
    "CrashKind",
    "classify_exit",
    "classify_sub_agent_exit",
]
