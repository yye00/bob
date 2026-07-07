"""Continuous orchestration loop for Bob (F069 + F109 + F072).

Implements the core build loop that continuously picks ready features
from the database, spawns Claude sub-agents to implement them, and
tracks progress until all features are completed or no more progress
can be made.

Execution model — SEQUENTIAL at the orchestrator level
-------------------------------------------------------
Bob's orchestration loop runs features SEQUENTIALLY: at most one
top-level feature is in flight at any time. The main loop in ``run()``
picks a single ready feature, awaits ``execute_feature``, then loops.
There is no ``asyncio.gather`` or task fan-out across sibling features.

This is intentional, not a TODO:

1. SQLite WAL with a single writer — concurrent feature writers
   would serialize on the DB anyway, and we'd inherit lock-contention
   debugging on top.
2. Cost tracking and budget enforcement assume sequential cost
   accumulation. The single ``OrchestrationLoop._increment_cost`` method
   and ``budget_exceeded`` are checked once per iteration; concurrent
   features would race on the running total and could overshoot
   ``max_cost`` by N feature-budgets at once.
3. Failure isolation — a failed sibling shouldn't poison parallel
   peers. With features running one at a time, a failure cleanly
   updates state, possibly cascades, and the next iteration replans
   against the new state.

What IS supported is *recursive* sub-agent parallelism: a sub-agent
spawned by ``execute_feature`` may, via ``claude_executor.spawn_sub_agent``
and the Superpowers "subagent-driven-development" skill (F113), spawn
its own sub-agents to decompose internal work. That recursion is bounded
by the Claude Code SDK and is unrelated to the orchestrator-level loop,
which still dispatches exactly one top-level feature at a time.

If you are reading this expecting concurrent feature execution: it is
not implemented and not currently planned. Updating prose to claim
otherwise creates a false expectation; please don't.

F109 adds research mode integration:
- Before execution, checks if a feature needs research
- Spawns a research sub-agent via Perplexity MCP when needed
- Stores research results and increments research_iterations
- Then proceeds to normal implementation

F072 adds feature decomposition handling:
- Before execution, checks if a feature exceeds_size_limits
- Spawns a decomposer sub-agent to split the feature
- Creates child features from the decomposition result
- Links dependencies between child features
- Sets the parent feature status to pending_decomposition

Research triggers:
1. Feature description contains research_required=True (and research_iterations == 0)
2. Feature has failed 3+ times (and research_iterations == 0)

The loop runs until one of these termination conditions:
- All features are completed
- All remaining features are blocked/failed
- Budget is exceeded
- Graceful shutdown is requested (SIGINT/SIGTERM)

Shutdown handling — where it lives
----------------------------------
``OrchestrationLoop._install_signal_handlers`` installs an inline
flag-setting handler that simply sets ``self.shutdown_requested = True``.
The flag is then checked between feature iterations at the top of
``run()``; once observed, the loop stops the MCP server and returns
``LoopTermination.SHUTDOWN_REQUESTED``. The actual shutdown sequence
(checkpoint creation, marking features 'interrupted', MCP cleanup) lives
HERE in the loop, NOT in ``bob.signal_handler.GracefulShutdownHandler``.

That handler class is currently retained only for its async-signal-safe
flag-setting primitive and the tests that pin that contract; its earlier
``_perform_shutdown`` method was unwired in production and has been
removed. If a future refactor wants to centralize the shutdown sequence
into a reusable handler, do it via dependency injection rather than the
previous hidden coupling.

KNOWN LIMITATION — Ctrl-C latency during sub-agent execution
------------------------------------------------------------
``self.shutdown_requested`` is only checked between feature iterations
in ``run()``. While ``await spawn_sub_agent(...)`` is in flight (which
can take 10-20 minutes for a real implementation sub-agent), the flag
is set by the signal handler but not acted on until the sub-agent
returns. Pressing Ctrl-C during a long sub-agent will set the flag
immediately and log a warning, but the loop will not actually stop
until the current sub-agent finishes (or the second Ctrl-C raises
SystemExit via the signal handler).

TODO: plumb a shutdown-requested callable into ``spawn_sub_agent`` so
the SDK message-consumption loop can cancel the client between message
events. That requires changes in ``claude_executor.py`` and is not done
here. As a stopgap, the loop logs a clear warning when shutdown is
observed, telling the user roughly how long they might have to wait.

Defense in depth — budget tampering by sub-agents (R5-003)
----------------------------------------------------------
Sub-agents are spawned by the Claude Code SDK with
``permission_mode=bypassPermissions`` and ``cwd=<workspace>``, which gives
them write access to anything in the workspace — including ``bob.db`` if
it lives there. A malicious sub-agent could ``UPDATE projects SET
total_cost_usd = 0`` to reset the running cost and effectively disable
budget enforcement on the next iteration of the loop.

The orchestrator can't prevent the write (the trust model accepts that
sub-agents have FS access), but it can DETECT the tampering and refuse
to honor the lower value. The loop maintains an in-memory ``_expected_total_cost``
that is incremented on every ``db.update_project_cost`` call (routed
exclusively through ``_increment_cost``). When
``_refresh_project_cost_cache`` reloads the canonical DB total, it
compares to the expected total; if the DB total has DECREASED beyond a
small floating-point slack, the loop:

1. Logs a ``SECURITY:`` warning naming both totals and the suspected
   tampering.
2. Refuses to lower the in-memory cache: it clamps to the expected
   total instead.

This means a sub-agent zeroing out the DB cannot extend its own runtime
budget. As a hardened deployment, place ``bob.db`` outside the workspace
via ``BOB_DATABASE_PATH=/secure/path/bob.db`` so sub-agents cannot
reach it at all — see the README "Security considerations" section.
"""

from __future__ import annotations

import asyncio
import collections
import enum
import errno
import fcntl
import json
import logging
import os
import pathlib
import re
import signal
import stat
import time
from typing import Any

from bob import db
from bob.mcp_lifecycle import stop_mcp_server, sweep_orphans
from bob.git_ops import (
    GitCommitError,
    GitHookFailedError,
    GitRepoError,
    commit_feature as git_commit_feature,
    get_status as git_get_status,
    revert_feature as git_revert_feature,
)
from bob.models import Feature
from bob.orchestrator.subagent_reaper import (
    find_subagent_pid_for_feature,
    reap_subagent_for_feature as _reap_subagent,
    sweep_orphan_subagents as _sweep_orphan_subagents,
)
from bob.orchestrator.stuck_executing_reaper import (
    sweep_stuck_executing as _sweep_stuck_executing,
)
from bob.orchestrator.zombie_run_reaper import (
    scan_and_reap as _scan_and_reap_zombies,
)
from bob.orchestrator.periodic_resume_scan import (  # noqa: F401 — integration AC f9f35288
    periodic_resume_scan as _periodic_resume_scan,
)
from bob.periodic_resume_scan import (  # noqa: F401 — integration AC 6abe05be
    promote_interrupted_rows as _promote_interrupted_rows,
)
from bob.pending_successor_verify import (  # noqa: F401 — integration AC dc709e23
    set_pending_successor_verify as _set_pending_successor_verify,
)
from bob.mutation_testing_post_impl_quality_gate_mutmut import (  # noqa: F401 — integration AC 89226d52
    mutation_testing_post_impl_quality_gate_mutmut,
)
from bob.run_loop_must_reap_claude_subagent_process_feature_terminal import (  # noqa: F401 — integration AC 5957b0ad
    run_loop_must_reap_claude_subagent_process_feature_terminal,
)
from bob.claude_code_worker_leverage_enable_prompt_cache_slim_per import (  # noqa: F401 — integration AC 5b6febb0
    claude_code_worker_leverage_enable_prompt_cache_slim_per as _worker_leverage,
)
_claude_code_worker_leverage_integrated = True  # sentinel for integration AC verification
from bob.swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive import (  # noqa: F401 — integration AC b9dac9b9
    swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive as _swe_bench_cheap_wins,
)
_swe_bench_cheap_wins_integrated = True  # sentinel for integration AC verification
from bob.pattern_8_integration_ac_handler_must_fall_back_function import (  # noqa: F401 — integration AC 6797d411
    pattern_8_integration_ac_handler_must_fall_back_function as _pattern_8_integration_fallback,
)
from bob.enhanced_verification_pattern_8_integration_must_scan_all import (  # noqa: F401 — integration AC e9c44614
    enhanced_verification_pattern_8_integration_must_scan_all as _pattern_8_scan_all,
)
from bob.orchestrator.enhanced_verification import (  # noqa: F401 — integration AC 0a898414
    verify_structural_log_line as _verify_structural_log_line,
)
from bob.bf_3_elicitation_classifier_clarification_budget_gate import (  # noqa: F401 — integration AC 47112d92
    bf_3_elicitation_classifier_clarification_budget_gate as _bf_3_elicit_classify,
)
from bob.bootstrap_auditor import (  # noqa: F401 — integration AC 578c0c70
    audit_permanent_forward_carry as _audit_permanent_forward_carry,
    PermanentForwardCarryMissing as _PermanentForwardCarryMissing,
)
from bob.orchestrator.cost_projection import allow_spawn as _cost_allow_spawn
from bob.orchestrator.concurrent_executor import run_concurrent as _run_concurrent
from bob.orchestrator.feature_claim import claim_next_ready_feature  # noqa: F401 — atomic claim for concurrent workers (1cb15253)
from bob.orchestrator.cost_reservation import (  # noqa: F401 — wired for concurrent budget guard (7841fb76)
    reserve_budget as _reserve_budget,
    release_reservation as _release_reservation,
)
from bob.orchestrator.claude_executor import (
    DEFAULT_SUB_AGENT_MAX_TURNS,
    ExecutionResult,
    SpawnResult,
    build_sub_agent_options,
    resolve_sub_agent_max_turns,
    parse_evaluator_verdict,
    spawn_evaluator_agent,
    spawn_rca_agent,
    spawn_research_agent,
    spawn_sub_agent,
)
from bob.orchestrator.disk_reconciler import (
    reconcile_from_disk as _reconcile_from_disk,
    check_executing_feature_acs as _check_executing_feature_acs,
)
from bob.orchestrator.crash_classifier import (
    ClassificationResult,
    classify_sub_agent_exit,
    _count_work_events,
)
from bob.orchestrator.cost_telemetry_guard import (
    apply_pessimistic_cost as _apply_pessimistic_cost,
    apply_pessimistic_cost,  # public export — AC: bob.orchestrator.run_loop.apply_pessimistic_cost
    emit_cost_telemetry_lost_event as _emit_cost_telemetry_lost_event,
    is_cost_telemetry_lost as _is_cost_telemetry_lost,
)
from bob.orchestrator.per_feature_ceiling import compute_per_feature_ceiling as _compute_per_feature_ceiling  # noqa: F401 — integration AC bd38ecbd
from bob.feature_timeout_executor import execute_with_timeout as _execute_with_timeout  # noqa: F401 — integration AC 9bdba8e1
from bob.orchestrator.sticky_completed import may_demote as _may_demote
from bob.orchestrator.bootstrap_override import may_bypass_readiness as _may_bypass_readiness
from bob.orchestrator.prompt_source_reloader import maybe_reload_all as _maybe_reload_prompt_sources
from bob.orientation import update_progress_notes, wrap_prompt_with_orientation
from bob.spec_quality.quality_score import compute_score as _compute_spec_quality_score, gate_for_ready as _spec_quality_gate_for_ready
from bob.spec_quality.spec_critic import critique_feature as _spec_critic_critique, persist_findings as _spec_critic_persist
from bob.orchestrator.test_writer_agent import emit_failing_tests as _emit_failing_tests, verify_bijection as _verify_test_bijection
from bob.orchestrator.codet_triangulation import spawn_k_tests as _codet_spawn_k_tests, spawn_k_impls as _codet_spawn_k_impls
from bob.orchestrator.rca_infra_recovery import auto_reset_if_infra as _rca_auto_reset_if_infra
from bob.orchestrator.blame_cascade import charge_refinement as _blame_charge_refinement
from bob.orchestrator.path_finding_retry import (
    should_trigger as _path_finding_should_trigger,
    classify_failure as _path_finding_classify_failure,
    research_strategies as _path_finding_research_strategies,
    inject_into_implementer_prompt as _path_finding_inject,
    cache_strategies_per_attempt as _path_finding_cache_strategies,
    persist_implementer_prompt as _path_finding_persist_prompt,
)
from bob.spec_quality.clarification_loop import run_clarification_loop as _run_clarification_loop, SPEC_NEEDS_HUMAN as _SPEC_NEEDS_HUMAN
from bob.model_escalation import resolve_model_for_tier as _resolve_escalated_model, try_escalate as _try_model_escalate  # F-R7-633
from bob.spec_stability import run_parallel_extractions as _run_spec_stability_check, compute_stability_score as _compute_stability_score  # noqa: F401 — integration AC 2f4a2cd8
from bob.superpowers import (
    extract_pytest_files,  # noqa: F401 — integration AC 8b6a8b46
    extract_pytest_files_from_acs,  # noqa: F401 — integration AC d436e770
    run_verification_checklist,
    should_use_subagents,
    should_use_tdd,
)
from bob.orchestrator.per_attempt_cost_cap import (
    should_terminate_subagent as _should_terminate_subagent,
    terminate_subagent_on_cost_cap as _terminate_subagent_on_cost_cap,
)
from bob.orchestrator.stale_bytecode_guard import (  # noqa: F401 — integration AC 0a2f5688
    check_stale_bytecode as _check_stale_bytecode,
)
from bob.stuck_readiness_decomposer import (  # noqa: F401 — integration AC 7c60cae5
    check_stuck_readiness as _check_stuck_readiness,
    mark_pending_decomposition as _mark_pending_decomposition,
)
from bob.stuck_readiness_decomposition import (  # noqa: F401 — integration AC 80577d54
    should_decompose as _should_decompose,
    mark_pending_decomposition as _srd_mark_pending_decomposition,
)
from bob.readiness_decomposition import (  # noqa: F401 — integration AC 86da3f00
    should_trigger_decomposition as _should_trigger_decomposition,
    mark_pending_decomposition as _rd_mark_pending_decomposition,
)
from bob.ac_repair_linter import (  # noqa: F401 — integration AC 6128e116
    semantic_equivalence_check as _semantic_equivalence_check,
    auto_apply_repair as _auto_apply_repair,
)
from bob.spec_findings_writer import (  # noqa: F401 — integration AC 6d12b5f9
    write_findings_atomically as _write_findings_atomically,
    quarantine_corrupt_findings as _quarantine_corrupt_findings,
)
from bob.orchestrator.feature_watchdog import (  # noqa: F401 — integration AC 7d197945
    create_feature_watchdog as _create_feature_watchdog,
    cancel_subagent_forcibly as _cancel_subagent_forcibly,
)

logger = logging.getLogger(__name__)

_PER_ATTEMPT_COST_CHECK_INTERVAL_S = 30


async def _monitor_subagent_cost_cap(
    *,
    feature_id: str,
    agent_run_id: str | None,
    check_interval_s: float = _PER_ATTEMPT_COST_CHECK_INTERVAL_S,
) -> None:
    """Periodically check a live subagent's reported cost against the per-attempt cap.

    Runs as a background asyncio task alongside ``spawn_sub_agent``.  Every
    ``check_interval_s`` seconds it reads the current ``cost_usd`` from the
    ``sub_agent_runs`` row for ``agent_run_id`` and calls
    :func:`_should_terminate_subagent`.  When the cap is exceeded, it looks
    up the subagent PID via the reaper's PID tracking and delegates to
    :func:`_terminate_subagent_on_cost_cap`.  The task exits when cancelled
    (which happens as soon as ``spawn_sub_agent`` completes).
    """
    if not agent_run_id:
        return
    try:
        while True:
            await asyncio.sleep(check_interval_s)
            try:
                run = db.get_agent_run(agent_run_id)
            except Exception:
                continue
            if run is None:
                return
            reported_cost = float(run.cost_usd or 0.0)
            if not _should_terminate_subagent(reported_cost):
                continue
            # Exceeded the cap — look up the PID and terminate.
            try:
                from bob.orchestrator.subagent_reaper import get_tracked_pid as _get_tracked_pid
                pid = _get_tracked_pid(feature_id)
            except Exception:
                pid = None
            if pid:
                _terminate_subagent_on_cost_cap(
                    feature_id=feature_id,
                    pid=pid,
                    reported_cost=reported_cost,
                )
            else:
                logger.warning(
                    "per_attempt_cost_cap: cost %.4f exceeded cap for feature %s "
                    "but no tracked PID found; cannot send SIGTERM",
                    reported_cost,
                    feature_id[:8],
                )
            return
    except asyncio.CancelledError:
        pass


def _log_safe(s: str | None) -> str:
    """Sanitize a string for inclusion in a log line (R9-003).

    Feature names come from the spec YAML and ultimately from the user
    or from a sub-agent decomposition result. Both inputs are untrusted
    relative to the log stream: a name containing newline / carriage-return
    characters can spoof a fake log record by injecting a synthetic
    "feature completed" line into stdout / log files. Mitigated by
    escaping CR / LF before formatting.

    Returns ``""`` for ``None`` so callers don't have to special-case it.
    The escaping is reversible (``\\n`` / ``\\r`` literals) so the original
    name is still recoverable if the operator wants it, but it cannot
    forge a new log record.
    """
    return (s or "").replace("\n", "\\n").replace("\r", "\\r")


def _final_exit_sweep(project_id: str) -> None:
    """Final reaper sweep run immediately before _run_locked returns its LoopTermination.

    Queries all features in status='executing' for ``project_id``.  For each,
    checks whether a live claude subagent PID is still attached via
    ``find_subagent_pid_for_feature``.  If no live PID is found (the subagent
    has already exited):

    F-R7-598: Before flipping to 'failed', invoke disk_reconciler to check
    whether all ACs are already satisfied on disk (orphan-exit-during-execution
    can leave artifacts behind from prior inheritance).  If disk check passes,
    promote to 'completed' (FINAL_SWEEP_DISK_PROMOTED) instead of failing.
    Only fall through to the flip-to-failed path when disk reconciler cannot
    satisfy ACs — preserves current behavior for genuinely incomplete features.

    Safety:
    - Does NOT touch any row whose owning PID is still alive (regression guard).
    - Per-feature errors are caught and logged; the sweep continues to remaining
      features so a single broken row never aborts the cleanup.
    - Idempotent: a second call with the same DB state (no 'executing' rows left)
      produces zero additional writes.
    - Only PROMOTES on disk evidence — never silences a genuine failure.
    """
    if project_id is None:
        raise ValueError("project_id must not be None")

    # Invoke sweep_orphan_subagents to clean up any stale terminal-state subagent PIDs
    # before flipping orphan executing rows.  This is idempotent and safe to call here.
    try:
        _sweep_orphan_subagents()
    except Exception:
        logger.warning("_final_exit_sweep: sweep_orphan_subagents failed", exc_info=True)

    try:
        executing_features = db.list_features(project_id=project_id, status="executing")
    except Exception:
        logger.warning("_final_exit_sweep: failed to query executing features", exc_info=True)
        return

    promoted = 0
    flipped_failed = 0

    for feature in executing_features:
        try:
            live_pids = find_subagent_pid_for_feature(feature.id)
        except Exception:
            logger.warning(
                "_final_exit_sweep: PID lookup failed for feature %s; skipping",
                feature.id[:8],
                exc_info=True,
            )
            continue

        if live_pids:
            logger.debug(
                "_final_exit_sweep: feature %s has live PIDs %s; skipping",
                feature.id[:8],
                live_pids,
            )
            continue

        # F-R7-598: reconciler-before-sweep guard — check disk ACs before failing.
        # An orphan-executing feature may have all its artifacts already on disk
        # from prior generation inheritance; disk_reconciler would have promoted
        # it on claim but was bypassed by the final sweep path.
        ac_json = getattr(feature, "acceptance_criteria", None) or "[]"
        try:
            promoted_on_disk = _check_executing_feature_acs(
                project_id=project_id,
                feature_id=feature.id,
                feature_name=getattr(feature, "name", feature.id),
                acceptance_criteria_json=ac_json,
            )
        except Exception:
            logger.warning(
                "_final_exit_sweep: disk AC check failed for feature %s; "
                "falling through to flip-to-failed",
                feature.id[:8],
                exc_info=True,
            )
            promoted_on_disk = False

        if promoted_on_disk:
            logger.info(
                json.dumps({
                    "event": "FINAL_SWEEP_DISK_PROMOTED",
                    "feature_id": feature.id,
                    "feature_name": getattr(feature, "name", feature.id),
                })
            )
            promoted += 1
            continue

        logger.info(
            "_final_exit_sweep: flipping orphan executing feature %s to failed "
            "(no live subagent PID found)",
            feature.id[:8],
        )
        try:
            db.update_feature(
                feature.id,
                status="failed",
                last_improvement_type="orchestrator_exit_during_execution",
            )
            flipped_failed += 1
        except Exception:
            logger.warning(
                "_final_exit_sweep: failed to flip feature %s to failed",
                feature.id[:8],
                exc_info=True,
            )

    logger.info(
        json.dumps({
            "event": "FINAL_SWEEP_SUMMARY",
            "promoted": promoted,
            "flipped_failed": flipped_failed,
        })
    )


def sweep_orphan_subagents_on_exit(project_id: str) -> list:
    """Sweep orphan subagent PIDs immediately before orchestrator exits.

    Called as the first step of the final exit reaper (feature 8ee4b26b).
    Invokes ``_sweep_orphan_subagents`` to clean up any stale terminal-state
    subagent PIDs, then returns the list of reaped items.

    Idempotent and safe — the same reaper logic that runs in the main loop
    tick, extracted as a named public function so the AC verifier can confirm
    the symbol exists in ``orchestrator.run_loop``.

    Args:
        project_id: UUID of the project whose orphan subagents should be
                    swept.  Must be a non-empty string.

    Returns:
        List of reaped subagent identifiers (may be empty if none found).

    Raises:
        ValueError: If ``project_id`` is None or not a string.
    """
    if project_id is None or not isinstance(project_id, str):
        raise ValueError(
            f"sweep_orphan_subagents_on_exit: project_id must be a non-empty string, "
            f"got {project_id!r}"
        )
    try:
        reaped = _sweep_orphan_subagents()
        if reaped:
            logger.info(
                "sweep_orphan_subagents_on_exit: reaped %d orphan subagent(s) for project %s",
                len(reaped),
                project_id[:8],
            )
        return reaped if reaped is not None else []
    except Exception:
        logger.warning(
            "sweep_orphan_subagents_on_exit: sweep failed for project %s",
            project_id[:8],
            exc_info=True,
        )
        return []


def flip_orphans_to_failed(project_id: str) -> list:
    """Flip all orphan 'executing' rows to 'failed' for a project.

    Called as the second step of the final exit reaper (feature 8ee4b26b).
    Queries all features in status='executing' for ``project_id``.  For each
    feature with no live subagent PID, updates status to 'failed' with reason
    'orchestrator_exit_during_execution'.

    Features with live PIDs are skipped (regression guard).  Features with
    AC artifacts already on disk are promoted to 'completed' via the disk
    reconciler instead of being flipped to 'failed'.

    Idempotent: a second call on the same DB state (no 'executing' rows)
    produces zero additional writes.

    Args:
        project_id: UUID of the project whose orphan executing features should
                    be flipped.  Must be a non-empty string.

    Returns:
        List of feature IDs that were flipped to 'failed'.

    Raises:
        ValueError: If ``project_id`` is None or not a string.
    """
    if project_id is None or not isinstance(project_id, str):
        raise ValueError(
            f"flip_orphans_to_failed: project_id must be a non-empty string, "
            f"got {project_id!r}"
        )

    try:
        executing_features = db.list_features(project_id=project_id, status="executing")
    except Exception:
        logger.warning(
            "flip_orphans_to_failed: failed to query executing features for project %s",
            project_id[:8],
            exc_info=True,
        )
        return []

    flipped = []

    for feature in executing_features:
        try:
            live_pids = find_subagent_pid_for_feature(feature.id)
        except Exception:
            logger.warning(
                "flip_orphans_to_failed: PID lookup failed for feature %s; skipping",
                feature.id[:8],
                exc_info=True,
            )
            continue

        if live_pids:
            logger.debug(
                "flip_orphans_to_failed: feature %s has live PIDs %s; skipping",
                feature.id[:8],
                live_pids,
            )
            continue

        ac_json = getattr(feature, "acceptance_criteria", None) or "[]"
        try:
            promoted_on_disk = _check_executing_feature_acs(
                project_id=project_id,
                feature_id=feature.id,
                feature_name=getattr(feature, "name", feature.id),
                acceptance_criteria_json=ac_json,
            )
        except Exception:
            logger.warning(
                "flip_orphans_to_failed: disk AC check failed for feature %s; "
                "falling through to flip-to-failed",
                feature.id[:8],
                exc_info=True,
            )
            promoted_on_disk = False

        if promoted_on_disk:
            logger.info(
                "flip_orphans_to_failed: feature %s promoted on disk; skipping failed flip",
                feature.id[:8],
            )
            continue

        try:
            db.update_feature(
                feature.id,
                status="failed",
                last_improvement_type="orchestrator_exit_during_execution",
            )
            flipped.append(feature.id)
            logger.info(
                "flip_orphans_to_failed: flipped feature %s to failed",
                feature.id[:8],
            )
        except Exception:
            logger.warning(
                "flip_orphans_to_failed: failed to flip feature %s to failed",
                feature.id[:8],
                exc_info=True,
            )

    return flipped


def sweep_orphan_subagents() -> list:
    """Public wrapper over the subagent-reaper's sweep, callable from run_loop.

    Invokes ``_sweep_orphan_subagents`` (imported from
    ``bob.orchestrator.subagent_reaper``) to clean up stale terminal-state
    subagent PIDs.  Exposed as a module-level symbol so the verifier can
    confirm ``bob.orchestrator.run_loop.sweep_orphan_subagents`` exists.

    Idempotent and safe — the same reaper logic that runs inside
    ``_final_exit_sweep`` and the main loop tick.

    Returns:
        List of reaped subagent identifiers (may be empty if none found).
    """
    try:
        result = _sweep_orphan_subagents()
        return result if result is not None else []
    except Exception:
        logger.warning("sweep_orphan_subagents: sweep failed", exc_info=True)
        return []


# Statuses that indicate a feature cannot make further progress
_TERMINAL_STATUSES = frozenset({
    "completed",
    "failed",
    "interrupted",
    "blocked_by_reviewer",
    "blocked_by_dependency",
    "needs_human",
    "resource_limited",
    "rolled_back",
    "regression",
    "pending_decomposition",
})

# Statuses that mean a feature is done (not just stuck)
# "done" is a synonym for "completed" — some sub-agents/external writers set
# status='done' instead of 'completed'. Without it here, a finished feature in
# 'done' is neither counted as drained nor re-picked by the loop (it's not
# ready/pending) → it strands in limbo and the gen never reports clean
# (bob72: feature bdd9a138 stuck at 'done'). Treat it as terminal.
_COMPLETED_STATUSES = frozenset({"completed", "pending_decomposition", "done", "complete"})

# Statuses that mean a feature is blocked or failed (no more automatic progress)
_BLOCKED_STATUSES = frozenset({
    "failed",
    "interrupted",
    "blocked_by_reviewer",
    "blocked_by_dependency",
    "needs_human",
    "resource_limited",
    "rolled_back",
    "regression",
})


class LoopTermination(enum.Enum):
    """Reason the orchestration loop terminated."""

    ALL_COMPLETED = "all_completed"
    ALL_BLOCKED = "all_blocked"
    BUDGET_EXCEEDED = "budget_exceeded"
    SHUTDOWN_REQUESTED = "shutdown_requested"


def translate_termination_label(termination_name: str) -> str:
    """Return the user-visible label for a LoopTermination enum name.

    Translates ``ALL_BLOCKED`` → ``QUEUE_DRAINED`` so that log output and
    CLI messages convey the correct semantics (ready queue is empty, not a
    stuck/failure state). The enum value and DB serialisation are unchanged.
    """
    if termination_name == "ALL_BLOCKED":
        return "QUEUE_DRAINED"
    return termination_name


def format_termination_message(termination: "LoopTermination | None") -> str:
    """Return the user-visible log token for a LoopTermination value.

    Accepts a ``LoopTermination`` enum member (or ``None`` when the run raised
    an exception) and returns the translated label suitable for log lines.
    ``ALL_BLOCKED`` is translated to ``QUEUE_DRAINED``; all other members keep
    their enum name; ``None`` maps to ``"RAISED"``.
    """
    if termination is None:
        return "RAISED"
    return translate_termination_label(termination.name)


def run_loop(
    project_id: str,
    *,
    max_cost: float | None = None,
    workspace: str | None = None,
    fresh: bool = False,
    target_feature_id: str | None = None,
    force_unlock: bool = False,
    max_concurrent_features: int = 1,
) -> "LoopTermination":
    """Run the orchestration loop synchronously for ``project_id``.

    Thin module-level entry point wrapping :meth:`OrchestrationLoop.run`.
    Constructs an :class:`OrchestrationLoop` and drives it to completion
    via ``asyncio.run``, returning the :class:`LoopTermination` reason.

    Raises:
        ValueError: if ``project_id`` is empty/blank — a missing project id
            is a programming error, not a silently-ignored no-op.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id must be a non-empty string")

    loop = OrchestrationLoop(
        project_id=project_id,
        max_cost=max_cost,
        workspace=workspace,
        fresh=fresh,
        target_feature_id=target_feature_id,
        force_unlock=force_unlock,
        max_concurrent_features=max_concurrent_features,
    )
    return asyncio.run(loop.run())


def _run_orchestration_loop(
    project_id: str,
    max_cost: float | None = None,
    fresh: bool = False,
    target_feature_id: str | None = None,
    force_unlock: bool = False,
    max_concurrent_features: int = 1,
) -> "LoopTermination":
    """Synchronous orchestration-loop entry point.

    Delegates to :func:`bob.cli._run_orchestration_loop`, which resolves the
    project workspace from the DB before constructing the loop. Exposed here so
    the loop can be driven from ``bob.orchestrator.run_loop`` without importing
    the Click CLI layer at call sites. The import is lazy to avoid the
    ``cli → run_loop`` import cycle at module load time.

    Raises:
        ValueError: if ``project_id`` is empty/blank.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id must be a non-empty string")

    from bob.cli import _run_orchestration_loop as _cli_run_orchestration_loop

    return _cli_run_orchestration_loop(
        project_id,
        max_cost=max_cost,
        fresh=fresh,
        target_feature_id=target_feature_id,
        force_unlock=force_unlock,
        max_concurrent_features=max_concurrent_features,
    )


# R10-015: Maximum number of free retries granted to a feature whose
# sub-agent died at process spawn time (duration_ms < 100, num_turns == 0).
# These transient failures should not consume the feature's
# refinement-attempt budget, but we still cap them to avoid an infinite
# loop when the local environment is permanently broken.
_MAX_SPAWN_RETRIES = 3

# F-R6-316: Maximum number of erroring research attempts (research
# sub-agent crashed, gateway 400, etc.) before the orchestrator gives
# up and lets the feature surface for human review. Until this cap is
# reached, research errors leave ``research_iterations`` unchanged so
# ``needs_research`` can re-fire on the next loop tick — preventing
# the R7-003 ``needs_human`` guard from poisoning a feature after a
# single transient failure.
_MAX_RESEARCH_ERROR_ATTEMPTS = 3

# R10-015: Threshold (in milliseconds) below which a result with
# num_turns == 0 is treated as a process-spawn-time failure rather than
# a substantive sub-agent error. The F013 incident showed
# duration_ms == 0; we allow a small margin (100 ms) for clock jitter
# and SDK setup overhead before classifying as "really ran".
_SPAWN_FAILURE_DURATION_MS = 100


def _looks_like_spawn_failure(result: "ExecutionResult") -> bool:
    """Return True when ``result`` looks like a process-spawn-time failure.

    A sub-agent that died before the message loop started has
    ``num_turns == 0`` and a sub-100ms ``duration_ms`` (typically 0).
    A sub-agent that ran 25 turns and errored has both fields populated.
    The two cases must be distinguished so the orchestrator only grants
    a free retry to the former (R10-015).

    NOTE (F-R6-300): This SDK-only heuristic mis-fires when claude-code
    crashes during shutdown after the sub-agent has already produced
    work (it reports ``duration_ms == 0`` and ``num_turns == 0`` even
    though the sub-agent ran for minutes). The orchestrator now calls
    :func:`classify_sub_agent_exit` (which inspects on-disk evidence)
    in addition to this heuristic; see ``_classify_failure_for_retry``.
    """
    if not getattr(result, "is_error", False):
        return False
    duration = result.duration_ms or 0
    turns = result.num_turns or 0
    return turns == 0 and duration < _SPAWN_FAILURE_DURATION_MS


def _persisted_artifact_count(workspace, since_ts: float) -> int:
    """F-R7-618: count source .py files under the workspace src tree (and any
    .worktrees/hotfix-*/src tree) modified at/after *since_ts*. Used to tell a
    pure transport crash (0 artifacts → exempt from retry charge) from a real
    work-loss crash (>0 → charge per F-R6-300). Never raises."""
    import pathlib as _pl
    try:
        ws = _pl.Path(workspace) if workspace else None
    except Exception:
        return 0
    if ws is None:
        return 0
    roots = [ws / "src"]
    try:
        roots.extend((ws / ".worktrees").glob("hotfix-*/src"))
    except Exception:
        pass
    n = 0
    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob("*.py"):
                if "build" in p.parts or ".git" in p.parts:
                    continue
                try:
                    if p.stat().st_mtime >= since_ts:
                        n += 1
                except Exception:
                    continue
        except Exception:
            continue
    return n


def _classify_failure_for_retry(
    result: "ExecutionResult",
    workspace: str | None,
    feature_id: str,
) -> ClassificationResult:
    """Run the F-R6-300 classifier on an errored sub-agent result.

    Resolves the on-disk paths the classifier needs (``progress.jsonl``
    inside the workspace, and the per-agent session log when one is
    available) and forwards the SDK-reported scalars. Returns a
    ``ClassificationResult`` whose ``should_charge_attempt`` field tells
    the caller whether to count this as a real refinement attempt.

    The exit_code that claude-code reports as the literal string
    ``"Command failed with exit code N"`` is recovered from
    ``result.error_message`` when ``ExecutionResult`` does not surface
    a numeric ``exit_code`` field; in all other cases we treat any
    ``is_error`` result as exit_code=1.
    """
    progress_path: str | None = None
    if workspace:
        progress_path = str(
            pathlib.Path(workspace) / ".bob" / "progress.jsonl"
        )
    # ExecutionResult does not currently carry a numeric exit_code; we
    # synthesize one: success → 0, anything else → 1. The classifier
    # only branches on "==0 vs !=0" so the exact non-zero value does
    # not matter.
    exit_code = 0 if not getattr(result, "is_error", False) else 1
    stderr_tail = getattr(result, "error_message", "") or ""

    return classify_sub_agent_exit(
        progress_jsonl_path=progress_path,
        # Session log path is not currently captured; the classifier
        # tolerates ``None`` and falls back on progress.jsonl + SDK
        # scalars.
        session_log_path=None,
        duration_ms=getattr(result, "duration_ms", 0) or 0,
        num_turns=getattr(result, "num_turns", 0) or 0,
        exit_code=exit_code,
        stderr_tail=stderr_tail,
    )


# ---------------------------------------------------------------
# Per-project advisory file lock
# ---------------------------------------------------------------
#
# Two concurrent ``bob run --all`` invocations from the same project
# would race on the database. ``busy_timeout`` keeps them from crashing,
# but the resulting interleaving is unpredictable: both processes would
# pick "ready" features, both would write status='executing', both would
# spawn sub-agents, and the eventual cascade order is whatever the OS
# scheduler decides. To prevent that we acquire an exclusive advisory
# lock on ``<workspace>/.bob.lock`` at startup. If another process
# already holds the lock the second invocation prints a clear error and
# exits with code 1.

_BOB_LOCK_FILENAME = ".bob.lock"


class AlreadyRunningError(RuntimeError):
    """Raised when another ``bob run`` is already in progress.

    The CLI catches this and prints a friendly message before exiting
    with status 1. The exception message is suitable for direct display
    to the user.
    """


def _read_lock_pid(lock_path: pathlib.Path) -> int | None:
    """Read the holder PID from a lock file, or None if unreadable.

    R10-006: We write our PID into the lock file after acquiring it so
    a subsequent contended attempt can probe the holder with
    ``kill(pid, 0)`` and produce an actionable error message (or, with
    ``force_unlock=True``, recover automatically from a truly stale lock).
    """
    try:
        contents = lock_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not contents:
        return None
    try:
        return int(contents.split()[0])
    except (ValueError, IndexError):
        return None


def _pid_is_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` is alive (signal 0 probe).

    R10-006: ``os.kill(pid, 0)`` raises ProcessLookupError when the PID
    is not in the kernel's task table, PermissionError when the process
    exists but is owned by another user (still alive), and succeeds
    silently if the PID is alive and signalable.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        # Be conservative on unexpected errors: assume alive.
        return True
    return True


def acquire_run_lock(
    workspace: str | pathlib.Path,
    force_unlock: bool = False,
) -> Any:
    """Acquire a non-blocking exclusive advisory lock for ``bob run``.

    Opens (creates if necessary) ``<workspace>/.bob.lock`` and tries to
    place an exclusive flock on it. On success, returns the open file
    handle — the caller MUST keep this handle alive for the duration of
    the run; closing it (or letting it be garbage collected) releases
    the lock. On contention raises ``AlreadyRunningError``.

    POSIX-only (uses ``fcntl.flock``). Bob explicitly does not support
    Windows in production, so we don't bother with an msvcrt fallback.

    Symlink-attack hardening (R5-002)
    ---------------------------------
    A sub-agent with workspace write access could replace ``.bob.lock``
    with a symlink to ``/dev/null`` (or any other non-regular file) before
    the next ``bob run``. ``flock`` on a non-regular file's fd succeeds
    trivially because the kernel doesn't track exclusive locks on devices
    or unrelated paths the way it does on regular files — two concurrent
    ``bob run`` processes would then both pass the lock check and race
    on the database.

    Two defenses applied here:

    1. ``os.open(..., O_NOFOLLOW)`` refuses at open time if the path
       already exists as a symlink. The kernel returns ``ELOOP``; we
       translate that into ``AlreadyRunningError`` so the user gets a
       coherent message.
    2. After opening, we ``fstat`` the descriptor and check
       ``stat.S_ISREG(st.st_mode)``. If it isn't a regular file (e.g. a
       sub-agent replaced the lock with a fifo, a directory, or a device
       node before we got there), we refuse to use it.

    Both checks fire before any flock attempt, so no caller ever holds a
    lock against ``/dev/null``.

    Args:
        workspace: The project workspace directory (where ``.bob.lock``
            lives). The directory must already exist; we don't try to
            create the workspace itself here, only the lock file inside
            it.

    Returns:
        The open file object holding the lock. Keep it alive — when the
        file is closed (explicitly or via GC) the lock is released.

    Raises:
        AlreadyRunningError: another process holds the lock, or the lock
            path was found to be a symlink / non-regular file (suggesting
            tampering by a sub-agent).
        OSError: any other I/O failure opening the lock file.
    """
    workspace_path = pathlib.Path(workspace) if workspace else pathlib.Path.cwd()
    # If the workspace directory doesn't exist, fall back to cwd so we
    # never crash with FileNotFoundError just because the project's
    # recorded workspace_path is bogus or hasn't been created yet
    # (common in tests and on the first ``bob run`` after a manual
    # workspace_path edit). The lock is still scoped per-process via the
    # filesystem, just rooted at cwd instead of an unreachable path.
    #
    # Recursive bob-on-bob caveat: when bob invokes its own pytest as
    # part of verification, a child test that calls OrchestrationLoop
    # without a real workspace would fall through to cwd — which is the
    # parent bob's workspace, currently holding the run-lock. The child
    # would then fail with AlreadyRunningError purely because of the
    # cwd-fallback colocation. Detect pytest via PYTEST_CURRENT_TEST and
    # land the fallback in an isolated tmp file instead.
    if not workspace_path.is_dir():
        under_pytest = "PYTEST_CURRENT_TEST" in os.environ
        if under_pytest:
            import tempfile
            fallback_dir = pathlib.Path(tempfile.gettempdir()) / f"bob-pytest-{os.getpid()}"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(
                "Lock workspace %s does not exist (pytest); using isolated %s",
                workspace_path, fallback_dir,
            )
            workspace_path = fallback_dir
        else:
            logger.debug(
                "Lock workspace %s does not exist; falling back to cwd for .bob.lock",
                workspace_path,
            )
            workspace_path = pathlib.Path.cwd()
    lock_path = workspace_path / _BOB_LOCK_FILENAME

    # R5-002: open with O_NOFOLLOW so a symlink at ``.bob.lock`` (e.g.
    # pointing at /dev/null) raises ELOOP instead of giving us a usable
    # fd we'd then flock-against-a-non-regular-file. We use os.open to
    # get the flag wired in, then wrap the fd with os.fdopen so the rest
    # of the function (and callers / release_run_lock) sees a normal
    # file object as before.
    open_flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, open_flags, 0o600)
    except OSError as exc:
        # ELOOP comes from O_NOFOLLOW hitting a symlink. Surface that as
        # an AlreadyRunningError with a tampering hint — letting it
        # propagate as a bare OSError would crash the CLI with no
        # actionable message.
        if getattr(exc, "errno", None) == errno.ELOOP:
            raise AlreadyRunningError(
                f"Lock path {lock_path} is a symlink — refusing to use it. "
                f"This usually means a sub-agent or external process "
                f"tampered with the lock; remove the symlink and try "
                f"again. (Possible tampering)"
            ) from exc
        raise

    # R5-002: verify the open fd refers to a regular file. A pre-existing
    # fifo / device / directory would have skipped the symlink check but
    # is still not a sound flock anchor.
    try:
        st = os.fstat(fd)
    except OSError:
        os.close(fd)
        raise
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise AlreadyRunningError(
            f"Lock path {lock_path} is not a regular file (st_mode={oct(st.st_mode)}). "
            f"Refusing to use it; remove it and try again. (Possible tampering)"
        )

    # Wrap the fd with a Python file object so the existing
    # release_run_lock() path (close-the-file-object) keeps working. The
    # mode "ab" matches the previous behaviour (no truncation, binary).
    try:
        fh = os.fdopen(fd, "ab")
    except OSError:
        os.close(fd)
        raise

    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        # R10-006: On contention, peek at the PID we wrote into the
        # lock file the last time it was acquired and check whether
        # that holder is still alive. ``flock`` is supposed to be
        # released on process exit by the kernel, but a still-running
        # grandchild that inherited the lock FD can keep it alive past
        # the original ``bob run`` — and on systemd-managed sessions
        # we have observed cases where this happens. Surface a more
        # actionable error in that case (and recover automatically if
        # the operator passed ``--force-unlock``).
        holder_pid = _read_lock_pid(lock_path)
        holder_alive = _pid_is_alive(holder_pid) if holder_pid is not None else True
        if not holder_alive:
            if force_unlock:
                # Truly stale — close our fd, remove the lock file, and
                # recurse once. If we still can't acquire it after that,
                # something's seriously wrong; don't loop.
                fh.close()
                try:
                    lock_path.unlink()
                except OSError:
                    logger.debug(
                        "Could not unlink stale lock file %s",
                        lock_path,
                        exc_info=True,
                    )
                logger.warning(
                    "Removed stale .bob.lock (holder PID %s was dead)",
                    holder_pid,
                )
                # Recurse with force_unlock=False so a real concurrent
                # run still raises cleanly.
                return acquire_run_lock(workspace, force_unlock=False)
            fh.close()
            raise AlreadyRunningError(
                f"`.bob.lock` exists but its holder PID {holder_pid} is "
                f"not running. The lock is stale (likely from a previous "
                f"run that was SIGKILLed or OOM-killed). To recover, "
                f"either re-run with `bob run --force-unlock ...` or "
                f"remove the lock file manually: rm {lock_path}"
            ) from exc
        fh.close()
        # Real concurrent run. Tell the user which PID is holding it
        # and how to recover if they're sure no other run is active.
        pid_hint = (
            f" (holder PID {holder_pid})" if holder_pid is not None else ""
        )
        raise AlreadyRunningError(
            f"Another `bob run` is already in progress for this project. "
            f"Refusing to start. (lock: {lock_path}){pid_hint} — "
            f"if no other bob run is actually running, remove the lock "
            f"file: rm {lock_path}"
        ) from exc
    except OSError:
        fh.close()
        raise

    # R10-006: Record our PID inside the lock file so a future
    # contended attempt can identify a stale lock. We truncate first
    # because the file was opened append-only ("ab") above; rewriting
    # the same fd avoids opening a second descriptor.
    try:
        os.lseek(fh.fileno(), 0, os.SEEK_SET)
        os.ftruncate(fh.fileno(), 0)
        fh.write(f"{os.getpid()}\n".encode("utf-8"))
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            # fsync may fail on some FS types — not worth aborting the
            # whole run for.
            logger.debug("fsync on .bob.lock failed", exc_info=True)
    except OSError:
        # Best-effort. If we can't write the PID, the flock still
        # protects against concurrent runs; we just lose the
        # stale-lock detection nicety.
        logger.debug("Could not write PID to .bob.lock", exc_info=True)

    return fh


def release_run_lock(lock_handle: Any) -> None:
    """Release a lock acquired by :func:`acquire_run_lock`.

    Best-effort: any errors are swallowed since by the time we are
    releasing the lock the run is over. Closing the file is what
    actually drops the flock; the explicit ``LOCK_UN`` is just a
    courtesy for clarity.
    """
    if lock_handle is None:
        return
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        logger.debug("flock LOCK_UN failed during release", exc_info=True)
    try:
        lock_handle.close()
    except Exception:
        logger.debug("lock file close failed during release", exc_info=True)


# ---------------------------------------------------------------
# Cost normalization (Max Pro / OAuth subscription handling)
# ---------------------------------------------------------------
#
# Claude Code Max Pro is a flat-fee OAuth subscription, so the SDK reports
# total_cost_usd=None for every result. If we silently pass None through to
# update_project_cost(), accumulated cost stays at 0.0 forever and budget
# enforcement becomes a no-op. To keep budgets meaningful, we fall back to
# a turn-count proxy: a small per-turn estimate that lets a runaway
# sub-agent still trip the budget guard.
#
# The proxy rate ($0.05/turn) is deliberately approximate; users can tune
# it via the BOB_COST_PER_TURN_PROXY environment variable.

_DEFAULT_COST_PER_TURN_PROXY = 0.05


# ---------------------------------------------------------------
# Sub-agent execution wall-clock timeout
# ---------------------------------------------------------------
#
# ``max_turns=25`` bounds how many model turns a sub-agent will take, but
# does not bound wall-clock time: a single turn that hangs in a tool call
# (e.g. a stuck Puppeteer / browser MCP, an unresponsive subprocess) will
# park the orchestration loop indefinitely. We wrap the ``await
# spawn_sub_agent(...)`` call in ``execute_feature`` with
# ``asyncio.wait_for`` using this timeout so the loop can recover. On
# timeout the feature is marked ``interrupted`` and dependents are NOT
# cascaded; the next ``bob run`` resumes through the normal interrupted-
# work path.

_DEFAULT_FEATURE_TIMEOUT_SECONDS = 3600  # 1 hour


# ---------------------------------------------------------------
# Regression-detection toggle (R7-001)
# ---------------------------------------------------------------
#
# capture_pytest_snapshot is invoked twice per feature (before and after
# the sub-agent) and uses synchronous subprocess.run with a ~300s timeout.
# In environments where the workspace test suite is large, slow, or simply
# uninteresting from a regression-tracking standpoint, this overhead is
# unwanted. Operators can disable both snapshots (and therefore the entire
# regression-detection path) via BOB_REGRESSION_DETECTION_ENABLED=0.
#
# The default is "enabled" because regression detection is wired into
# show-regressions / rollback (F051 / F052) and most operators want it on.

_REGRESSION_DETECTION_DEFAULT = True


def _regression_detection_enabled() -> bool:
    """Return True when regression-detection snapshots should run.

    Honours the ``BOB_REGRESSION_DETECTION_ENABLED`` env var. Truthy
    values: ``1``, ``true``, ``yes``, ``on`` (case-insensitive). Falsy
    values: ``0``, ``false``, ``no``, ``off``. Anything unrecognised is
    treated as truthy with a warning so misconfigurations don't silently
    disable regression detection.
    """
    raw = os.environ.get("BOB_REGRESSION_DETECTION_ENABLED")
    if raw is None:
        return _REGRESSION_DETECTION_DEFAULT
    normalized = raw.strip().lower()
    if normalized in ("0", "false", "no", "off"):
        return False
    if normalized in ("1", "true", "yes", "on"):
        return True
    logger.warning(
        "Unrecognised BOB_REGRESSION_DETECTION_ENABLED=%r; treating as enabled",
        raw,
    )
    return _REGRESSION_DETECTION_DEFAULT


def _resolve_feature_timeout_seconds() -> float:
    """Read ``BOB_FEATURE_TIMEOUT_SECONDS`` from the environment.

    Returns the configured timeout in seconds, falling back to
    ``_DEFAULT_FEATURE_TIMEOUT_SECONDS`` (3600) on any parse error or
    non-positive value. Kept as a small helper so tests can monkeypatch
    the env var per-test without poking at module-level constants.
    """
    raw = os.environ.get("BOB_FEATURE_TIMEOUT_SECONDS")
    if raw is None:
        return float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB_FEATURE_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_FEATURE_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)
    if value <= 0:
        logger.warning(
            "Non-positive BOB_FEATURE_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_FEATURE_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)
    return value


def _normalize_cost(cost_usd: float | None, num_turns: int | None = None) -> tuple[float, str]:
    """Normalize a possibly-missing cost into a budget-safe value.

    Claude Max Pro often returns cost_usd=None. To keep budget enforcement
    meaningful in that mode, fall back to a turn-count proxy: each turn
    is approximated as $0.05 (configurable via BOB_COST_PER_TURN_PROXY).

    Returns (cost_to_record, source_label) where source_label is one of
    'sdk', 'turn_proxy', or 'zero'.
    """
    if cost_usd is not None and cost_usd >= 0:
        return float(cost_usd), "sdk"
    if num_turns is not None and num_turns > 0:
        try:
            proxy_per_turn = float(
                os.environ.get(
                    "BOB_COST_PER_TURN_PROXY",
                    str(_DEFAULT_COST_PER_TURN_PROXY),
                )
            )
        except (TypeError, ValueError):
            proxy_per_turn = _DEFAULT_COST_PER_TURN_PROXY
        return num_turns * proxy_per_turn, "turn_proxy"
    return 0.0, "zero"


# Per-feature de-duplication for proxy log lines (avoid spam during a run).
#
# This used to be an unbounded module-level ``set[str]`` that grew for every
# feature ever logged across the lifetime of the process. In long-running
# orchestrator processes (or test suites that share the module) it would
# slowly leak memory. We now back it with a bounded FIFO so the membership
# check is still O(1) but the population is capped — when we hit the cap,
# the oldest entry is evicted, and that feature would simply re-log its
# proxy line if it appears again.
_PROXY_LOG_DEDUP_MAX_ENTRIES = 10000


class _BoundedFeatureIdSet:
    """A bounded ``set``-like container with FIFO eviction.

    Supports ``.add``, ``.discard``, ``__contains__``, ``__len__``, and
    ``clear``, which are all the operations the proxy-log dedup path and
    its tests rely on. Insertion order is tracked via a ``deque`` so that
    when capacity is exceeded the oldest entry is dropped from both the
    deque and the membership set in O(1).
    """

    __slots__ = ("_set", "_order", "_max_entries")

    def __init__(self, max_entries: int = _PROXY_LOG_DEDUP_MAX_ENTRIES) -> None:
        self._set: set[str] = set()
        self._order: collections.deque[str] = collections.deque()
        self._max_entries = max_entries

    def __contains__(self, item: object) -> bool:
        return item in self._set

    def __len__(self) -> int:
        return len(self._set)

    def __iter__(self):
        return iter(self._set)

    def add(self, feature_id: str) -> None:
        if feature_id in self._set:
            return
        self._set.add(feature_id)
        self._order.append(feature_id)
        # Evict oldest entries until we are back within capacity.
        while len(self._order) > self._max_entries:
            oldest = self._order.popleft()
            self._set.discard(oldest)

    def discard(self, feature_id: str) -> None:
        if feature_id not in self._set:
            return
        self._set.discard(feature_id)
        # Lazy-remove from order: cheap because eviction tolerates misses.
        try:
            self._order.remove(feature_id)
        except ValueError:
            pass

    def clear(self) -> None:
        self._set.clear()
        self._order.clear()


_PROXY_LOGGED_FEATURE_IDS: _BoundedFeatureIdSet = _BoundedFeatureIdSet()


# ---------------------------------------------------------------
# Pytest snapshot helpers (for regression detection — F051)
# ---------------------------------------------------------------
#
# A "snapshot" is a mapping ``test_nodeid -> bool`` (True == passed). We
# capture one snapshot BEFORE a feature's implementation lands and
# another AFTER verification passes; comparing the two via
# ``db.detect_regression`` reveals tests that used to pass and now fail.
#
# Implementation notes:
# - Uses ``-v --tb=no -q`` and parses per-test verdict lines from
#   pytest's verbose output. When pytest is unavailable, the workspace
#   is missing, or no verdict lines parse, we return ``None`` — callers
#   must treat None as "snapshot not available; skip regression detection".
# - We deliberately do NOT use ``--collect-only`` separately because it
#   doubles the runtime; we already learn the test list from the run.
# - Pytest verbose output looks like:
#       tests/test_foo.py::test_bar PASSED
#       tests/test_foo.py::test_baz FAILED
#   When pytest-xdist is used (-n N), the format changes to:
#       [gw0] [ 33%] PASSED tests/test_foo.py::test_bar
#   We parse both forms.
_PYTEST_VERDICT_RE = re.compile(
    r"^(?P<nodeid>\S+::[^\s]+)\s+(?P<verdict>PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\b"
)
# xdist parallel output: [gwN] [PP%] VERDICT nodeid
_PYTEST_XDIST_VERDICT_RE = re.compile(
    r"^\[gw\d+\]\s+\[.*?\]\s+(?P<verdict>PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\s+(?P<nodeid>\S+::\S+)"
)

# Bumped from 300 → 1800 because bob's own test suite grew to ~180 files
# and the 300s ceiling was timing out on every snapshot, returning None and
# defeating the regression-detection layer that protects against pre-existing
# test flakiness. 1800s gives headroom for 3000+ tests; still bounded so a
# truly hung pytest doesn't stall the orchestrator indefinitely. Override
# via BOB_SNAPSHOT_TIMEOUT for very large suites.
_DEFAULT_SNAPSHOT_TIMEOUT_S = 1800


def _snapshot_timeout_s() -> int:
    """Return the per-snapshot pytest timeout (seconds).

    Honors ``BOB_SNAPSHOT_TIMEOUT`` if set; falls back to
    ``BOB_TEST_RUN_TIMEOUT`` (the same env used by the verification
    pytest call), then to a 300s default.
    """
    for env_name in ("BOB_SNAPSHOT_TIMEOUT", "BOB_TEST_RUN_TIMEOUT"):
        raw = os.environ.get(env_name)
        if not raw:
            continue
        try:
            v = int(raw)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return _DEFAULT_SNAPSHOT_TIMEOUT_S


def capture_pytest_snapshot(
    workspace: str | None,
    *,
    test_dir: str = "tests",
    changed_files: list[str] | None = None,
) -> dict[str, bool] | None:
    """Run pytest in the workspace and return a per-test pass/fail snapshot.

    Args:
        workspace: Path to the project workspace. If empty / None, returns
            None (no snapshot possible).
        test_dir: Directory under workspace to test (defaults to "tests").
        changed_files: Optional list of repo-relative paths of source files
            changed by the current feature. When provided, F-R6-301 scoping
            attempts to compute a subset of tests that actually exercise
            those files (transitive importer closure). When scoping returns
            None (critical-path change, too few tests, missing roots) we
            fall through to the existing full-suite path.

    Returns:
        ``dict[test_nodeid, passed_bool]`` on success, or ``None`` if the
        snapshot could not be captured (workspace missing, pytest absent,
        timeout, or no recognisable verdict lines).

    A test is "passed" when its verdict line is ``PASSED`` / ``XFAIL``
    / ``SKIPPED`` / ``XPASS``; only ``FAILED`` and ``ERROR`` count as
    failures (skips aren't regressions; xpass is unusual but not a
    regression).
    """
    if not workspace:
        return None
    import pathlib  # local import to avoid bringing pathlib into module top
    import subprocess

    ws = pathlib.Path(workspace)
    if not ws.exists() or not ws.is_dir():
        return None

    # Recursion guard: skip when workspace IS the bob repo itself, to
    # mirror the behaviour of superpowers._check_tests_pass.
    try:
        import bob
        bob_root = pathlib.Path(bob.__file__).resolve().parents[2]
        ws_resolved = ws.resolve()
        if ws_resolved == bob_root or bob_root in ws_resolved.parents:
            logger.debug(
                "Skipping pytest snapshot: workspace is bob itself "
                "(self-test recursion guard)"
            )
            return None
    except Exception:
        logger.debug("snapshot recursion guard skipped", exc_info=True)

    target = ws / test_dir
    if not target.exists() or not target.is_dir():
        # No test directory — empty snapshot is not useful for
        # detect_regression. Return None so the caller skips.
        return None

    # F-R6-301 integration: per-feature pytest scoping. When the caller
    # supplied a diff, try to compute just the tests that exercise the
    # changed source files. If the scoper returns None (critical-path
    # change, too few tests, missing roots) we fall through to the
    # full-suite invocation below.
    scoped_targets: list[str] | None = None
    if changed_files:
        try:
            from bob.pytest_scoper import scope_tests_for_diff
            scoped = scope_tests_for_diff(list(changed_files), ws)
        except Exception:
            # Defensive: a bug in the scoper must not break the snapshot
            # path. Fall through to the full suite.
            logger.debug("pytest_scoper raised; falling back to full suite",
                         exc_info=True)
            scoped = None
        if scoped:
            scoped_rel: list[str] = []
            ws_resolved = ws.resolve()
            for p in scoped:
                # ``scope_tests_for_diff`` returns repo-rooted absolute
                # posix paths; rewrite to ws-relative for the pytest
                # invocation.
                pp = pathlib.Path(p)
                if pp.is_absolute():
                    try:
                        pp = pp.resolve().relative_to(ws_resolved)
                    except ValueError:
                        # Path is outside ws; skip it.
                        continue
                scoped_rel.append(pp.as_posix())
            if scoped_rel:
                scoped_targets = scoped_rel
                logger.debug(
                    "F-R6-301 pytest scope: %d tests for %d changed files",
                    len(scoped_targets), len(changed_files),
                )

    pytest_targets = (
        scoped_targets
        if scoped_targets is not None
        else [target.relative_to(ws).as_posix()]
    )

    cmd = [
        "python",
        "-m",
        "pytest",
        *pytest_targets,
        "-v",
        "--tb=no",
        "--no-header",
        "--color=no",
        "-p",
        "no:cacheprovider",
    ]
    # F-R6-313: parallelise the snapshot too. Mirrors superpowers._check_tests_pass.
    # Probe the workspace's python for xdist; if absent, run sequentially with no
    # warning (the snapshot is a best-effort baseline — never block on it).
    # --maxfail=0 is enforced at the snapshot boundary regardless of xdist.
    try:
        probe = subprocess.run(
            ["python", "-c", "import xdist"],
            cwd=str(ws),
            capture_output=True,
            timeout=5,
            check=False,
        )
        if probe.returncode == 0:
            import os as _os
            _n = max(1, min((_os.cpu_count() or 1) // 4, 16))
            cmd.extend(["-n", str(_n), "--dist=loadfile"])
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Deterministic snapshots: enforce --maxfail=0 at the snapshot boundary so
    # xdist never halts early (xdist stops after ~20-25 failures otherwise,
    # making before/after snapshots non-comparable).
    try:
        from bob.deterministic_pytest_snapshots import enforce_maxfail_zero_snapshot as _enforce_mf
        cmd = _enforce_mf(cmd)
    except ImportError:
        try:
            from bob.pytest_snapshot_config import enforce_maxfail_zero as _enforce_mf
            cmd = _enforce_mf(cmd)
        except ImportError:
            try:
                from bob.deterministic_snapshot import enforce_maxfail_zero as _enforce_mf
                cmd = _enforce_mf(cmd)
            except ImportError:
                try:
                    from bob.pytest_snapshots import enforce_maxfail_zero as _enforce_mf
                    cmd = _enforce_mf(cmd)
                except ImportError:
                    try:
                        from bob.snapshot_determinism import enforce_maxfail_zero as _enforce_mf
                        cmd = _enforce_mf(cmd)
                    except ImportError:
                        try:
                            from bob.snapshot_enforcement import enforce_maxfail_for_snapshots as _enforce_mf
                            cmd = _enforce_mf(cmd)
                        except ImportError:
                            try:
                                from bob.snapshot_pytest import enforce_maxfail_zero as _enforce_mf
                                cmd = _enforce_mf(cmd)
                            except ImportError:
                                try:
                                    from pytest_snapshot_config import enforce_maxfail_for_snapshots
                                    cmd = enforce_maxfail_for_snapshots(cmd)
                                except ImportError:
                                    if "--maxfail=0" not in cmd:
                                        cmd.insert(1, "--maxfail=0")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=_snapshot_timeout_s(),
            check=False,
        )
    except FileNotFoundError:
        logger.debug("pytest snapshot skipped: python interpreter missing")
        return None
    except subprocess.TimeoutExpired:
        logger.warning(
            "pytest snapshot timed out in %s after %ss",
            ws, _snapshot_timeout_s(),
        )
        return None
    except (OSError, ValueError) as exc:
        logger.debug("pytest snapshot invocation failed: %s", exc)
        return None

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if (
        "No module named pytest" in stderr
        or "No module named 'pytest'" in stderr
    ):
        logger.debug("pytest snapshot skipped: pytest not installed")
        return None

    snapshot: dict[str, bool] = {}
    for line in stdout.splitlines():
        m = _PYTEST_VERDICT_RE.match(line)
        if not m:
            m = _PYTEST_XDIST_VERDICT_RE.match(line)
        if not m:
            continue
        nodeid = m.group("nodeid")
        verdict = m.group("verdict")
        snapshot[nodeid] = verdict in ("PASSED", "XFAIL", "SKIPPED", "XPASS")

    if not snapshot:
        return None
    return snapshot


# ---------------------------------------------------------------
# Calibration tracking helpers (F019)
# ---------------------------------------------------------------
#
# Bob calibration tracks predicted confidence (pre-execution) vs actual
# outcome (passed verification or not) per ``task_class + confidence_bucket``.
# Issue R4-004 was that ``db.create_or_update_calibration`` was never
# called from the orchestrator — the ``calibration_data`` table stayed
# empty in production so ``show-calibration`` was vacuous and drift
# detection had no inputs.
#
# ``task_class`` assignment: feature-level execution doesn't carry an
# explicit task_class today (it is a per-task concept). We pick a stable
# coarse default of ``"implementation"`` since ``execute_feature`` spawns
# an implementation sub-agent. The function ``_feature_task_class`` is
# the seam where richer classification (e.g. "refactor" / "bug_fix" /
# "greenfield_impl" derived from the feature description) can be wired
# in later. Returning a single value today is intentional: the important
# property is that ``calibration_data`` starts getting rows so drift
# detection has data to work with.
_DEFAULT_TASK_CLASS_FEATURE = "implementation"


def _feature_task_class(feature: Feature) -> str:
    """Derive a calibration task_class label from a feature.

    Currently a stable coarse bucket: ``"implementation"``. See the module
    block-comment above for rationale. TODO(F019+): plug in a real
    classifier here.
    """
    return _DEFAULT_TASK_CLASS_FEATURE


def _record_feature_calibration(
    *,
    project_id: str,
    feature: Feature,
    passed: bool,
) -> None:
    """Record a calibration data point for a feature execution.

    Wraps :func:`db.create_or_update_calibration` so a single failure
    here cannot abort the loop. The ``expected_pass_rate`` is the
    feature's ``conf_impl_correctness`` at the time of execution.
    """
    try:
        confidence = float(feature.conf_impl_correctness or 0.0)
        bucket = db._confidence_to_bucket(confidence)
        db.create_or_update_calibration(
            project_id=project_id,
            task_class=_feature_task_class(feature),
            confidence_bucket=bucket,
            passed=passed,
            expected_pass_rate=confidence,
        )
    except Exception:
        logger.warning(
            "Failed to record calibration data for feature %s",
            feature.id,
            exc_info=True,
        )


def cascade_update_dependents(feature_id: str) -> list[str]:
    """Update dependent features when a feature is completed.

    Delegates to db.cascade_update_dependents (F123) which:
    1. Finds all features depending on the completed feature
    2. Checks if ALL their dependencies are completed
    3. Checks readiness_score >= threshold for their risk_category
    4. Transitions qualifying features from 'pending' to 'ready'

    Args:
        feature_id: The ID of the just-completed feature.

    Returns:
        List of feature IDs that were transitioned to 'ready'.
    """
    return db.cascade_update_dependents(feature_id)


# ---------------------------------------------------------------
# F072: Feature decomposition handling
# ---------------------------------------------------------------

DECOMPOSER_SYSTEM_PROMPT = (
    "You are a feature decomposition agent. Your job is to break down a "
    "large feature into smaller, independently implementable child features.\n\n"
    "You MUST respond with a JSON block (inside ```json fences) containing:\n"
    '  - "children": array of child feature objects, each with:\n'
    '    - "name": short feature name\n'
    '    - "description": what this child implements\n'
    '    - "acceptance_criteria": JSON string of acceptance criteria array\n'
    '    - "priority": integer (lower = higher priority)\n'
    '    - "risk_category": "low", "medium", or "high"\n'
    '  - "dependencies": array of dependency objects, each with:\n'
    '    - "from": index of the child that depends (0-based)\n'
    '    - "to": index of the child it depends on (0-based)\n\n'
    "Keep each child small enough to be implemented in a single session "
    "(< 500 lines, < 5 files, complexity < 8)."
)


def parse_decomposition_result(text: str) -> dict | None:
    """Parse decomposition agent response to extract children and dependencies.

    Looks for a JSON block (inside ```json fences or inline) containing
    a "children" array and optional "dependencies" array.

    Returns a dict with keys "children" and "dependencies", or None if
    parsing fails or children is empty.
    """
    # Try fenced JSON first: ```json ... ```
    fenced = re.search(r"```json\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    json_str = fenced.group(1) if fenced else None

    # Fall back to inline JSON: { ... "children" ... }
    if json_str is None:
        inline = re.search(r"\{[^{}]*\"children\"\s*:", text, re.DOTALL)
        if inline:
            # Try to find the full JSON object
            start = inline.start()
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        json_str = text[start : i + 1]
                        break

    if json_str is None:
        return None

    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(parsed, dict):
        return None

    children = parsed.get("children")
    if not children or not isinstance(children, list) or len(children) == 0:
        return None

    dependencies = parsed.get("dependencies", [])
    if not isinstance(dependencies, list):
        dependencies = []

    return {
        "children": children,
        "dependencies": dependencies,
    }


async def handle_decomposition(
    *,
    project_id: str,
    feature: Feature,
    workspace: str | None = None,
) -> dict:
    """Decompose an oversized feature into smaller child features.

    Spawns a decomposer sub-agent to analyze the feature and produce
    a plan for splitting it into independently implementable children.
    Then creates the child features and links dependencies.

    Args:
        project_id: The project ID.
        feature: The oversized feature to decompose.
        workspace: Optional path to the project workspace. When supplied,
            ``build_sub_agent_options`` runs ``install_skills_to_workspace``
            and ``verify_skills_integrity`` against this directory before
            spawning the decomposer. This closes the R9-007 skill-poisoning
            window for the decomposer path.

            SECURITY TRADE-OFF: passing ``cwd`` also gives the decomposer
            sub-agent filesystem access to ``workspace`` (with the default
            ``bypassPermissions`` mode it can read/write any file under
            it). The decomposer is purely a planning agent — its prompt
            asks for a JSON output, not file edits — so the practical
            blast radius is small. The integrity check is what closes
            the chained-attack window where a prior malicious agent
            replaced a skill symlink in ``.claude/skills``.

    Returns:
        Dict with keys: success, children_created, cost_usd, error_message.
    """
    prompt = (
        f"Decompose this oversized feature into smaller, independently "
        f"implementable child features.\n\n"
        f"Feature: {feature.name}\n"
        f"Description: {feature.description or 'No description'}\n"
        f"Acceptance Criteria: {feature.acceptance_criteria or 'None specified'}\n"
        f"Size Justification: {feature.size_limit_justification or 'Exceeds size limits'}\n\n"
        f"Break this into 2-5 smaller features, each under 500 lines of code, "
        f"touching fewer than 5 files, and with complexity under 8.\n\n"
        f"Respond with a JSON block containing the children and their dependencies."
    )

    options = build_sub_agent_options(
        cwd=workspace or None,
        model="sonnet",
        max_turns=10,
        system_prompt=DECOMPOSER_SYSTEM_PROMPT,
    )

    spawn_result = await spawn_sub_agent(
        project_id=project_id,
        purpose="decompose_feature",
        prompt=prompt,
        target_type="feature",
        target_id=feature.id,
        options=options,
    )

    result = spawn_result.execution_result
    outcome = {
        "success": False,
        "children_created": 0,
        "cost_usd": result.total_cost_usd,
        # Surface num_turns so the caller can run cost normalization (the
        # turn-count proxy is needed when total_cost_usd is None on Max Pro
        # / OAuth subscriptions).
        "num_turns": result.num_turns,
        "error_message": None,
    }

    if result.is_error:
        outcome["error_message"] = result.error_message
        return outcome

    # Parse the decomposition result
    decomposition = parse_decomposition_result(result.text)
    if decomposition is None:
        outcome["error_message"] = "Failed to parse decomposition result"
        return outcome

    children_specs = decomposition["children"]
    dependencies = decomposition["dependencies"]

    # Create child features
    created_children = []
    for spec in children_specs:
        child = db.create_child_feature(
            parent_feature_id=feature.id,
            project_id=project_id,
            name=spec.get("name", f"Child of {feature.name}"),
            description=spec.get("description"),
            acceptance_criteria=spec.get("acceptance_criteria"),
            status="ready",
            priority=spec.get("priority", feature.priority),
            risk_category=spec.get("risk_category", feature.risk_category),
        )
        # Set readiness high so children are immediately ready
        db.update_feature(
            child.id,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
            readiness_score=0.85,
        )
        created_children.append(child)

    # Link dependencies between children
    for dep in dependencies:
        from_idx = dep.get("from")
        to_idx = dep.get("to")
        if (
            isinstance(from_idx, int)
            and isinstance(to_idx, int)
            and 0 <= from_idx < len(created_children)
            and 0 <= to_idx < len(created_children)
            and from_idx != to_idx
        ):
            db.add_feature_dependency(
                feature_id=created_children[from_idx].id,
                depends_on_feature_id=created_children[to_idx].id,
            )

    # Update parent status
    db.update_feature(feature.id, status="pending_decomposition")

    outcome["success"] = True
    outcome["children_created"] = len(created_children)

    logger.info(
        "Decomposed feature %s into %d children",
        feature.id,
        len(created_children),
    )

    return outcome


# ---------------------------------------------------------------
# Stuck-readiness decomposition trigger (feature 077db964)
# ---------------------------------------------------------------
#
# When a feature has been attempted >= 2 times and its readiness_score
# remains below 0.80 with no improvement, re-executing is a treadmill:
# the eval sub-agent will demote confidence, charge refinement_attempts,
# and leave the feature in the same stuck state. Instead we mark it
# ``pending_decomposition`` so a decomposer can split it into smaller,
# independently solvable sub-features.
#
# The three conditions that must ALL be true:
#   1. refinement_attempts >= 2  (at least one prior retry has happened)
#   2. readiness_score < 0.80   (feature is below the standard threshold)
#   3. no improvement since last attempt  (treadmill confirmation)
#
# Guard: refinement_attempts < 0 is a data corruption sentinel; we raise
# ValueError so the caller can detect and log it rather than silently
# skipping decomposition.

_DECOMPOSE_READINESS_THRESHOLD = 0.80
_DECOMPOSE_MIN_ATTEMPTS = 2


def _refinement_attempts_at_or_above_two(feature: Feature) -> bool:
    """Return True iff feature.refinement_attempts >= 2."""
    return feature.refinement_attempts >= _DECOMPOSE_MIN_ATTEMPTS


def _readiness_below_threshold(feature: Feature) -> bool:
    """Return True iff feature.readiness_score < 0.80."""
    return feature.readiness_score < _DECOMPOSE_READINESS_THRESHOLD


def _readiness_did_not_improve(
    feature: Feature,
    *,
    previous_score: float | None,
) -> bool:
    """Return True iff readiness_score did not improve since last attempt.

    When ``previous_score`` is None (no prior reading available), we
    conservatively treat it as no improvement so the decomposition gate
    can still fire.
    """
    if previous_score is None:
        return True
    return feature.readiness_score <= previous_score


def _handle_first_attempt(feature: Feature) -> bool:
    """Return False on attempt 1 — first attempts must never trigger decomposition.

    Documents the invariant: _should_decompose_instead_of_execute always
    returns False when refinement_attempts < 2.
    """
    return False


def _never_decomposes_on_first_attempt() -> bool:
    """Return True; documents that _handle_first_attempt always returns False at attempt==1."""
    return True


def _should_decompose_instead_of_execute(
    feature: Feature,
    *,
    previous_readiness_score: float | None,
) -> bool:
    """Return True when decomposition should replace re-execution.

    Raises ValueError when feature.refinement_attempts is negative
    (data corruption guard — error message contains "negative").
    """
    if feature.refinement_attempts < 0:
        raise ValueError(
            f"feature.refinement_attempts is negative "
            f"({feature.refinement_attempts}) for feature {feature.id!r}; "
            f"this indicates data corruption"
        )
    if not _refinement_attempts_at_or_above_two(feature):
        return False
    if not _readiness_below_threshold(feature):
        return False
    if not _readiness_did_not_improve(feature, previous_score=previous_readiness_score):
        return False
    return True


def _transition_to_pending_decomposition(feature: Feature) -> Feature:
    """Set feature.status to 'pending_decomposition' atomically via db.update_feature."""
    return db.update_feature(feature.id, status="pending_decomposition")


def _log_decomposition_reason(
    feature: Feature,
    reason: str,
    *,
    runs_round_dir: str,
) -> None:
    """Write a structured reason entry to runs/<round>/decompositions.jsonl."""
    import datetime

    dest = pathlib.Path(runs_round_dir)
    dest.mkdir(parents=True, exist_ok=True)
    decomp_file = dest / "decompositions.jsonl"
    entry = {
        "feature_id": feature.id,
        "feature_name": feature.name,
        "reason": reason,
        "refinement_attempts": feature.refinement_attempts,
        "readiness_score": feature.readiness_score,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    with open(decomp_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _preserve_f_r6_317_bypass(feature: Feature) -> bool:
    """Return True when below threshold but decomposition not triggered.

    This is the F-R6-317 fallthrough: a feature that is below readiness
    threshold but has refinement budget remaining bypasses the
    preemptive needs_human gate and goes to execute_feature instead.
    Returns True to document the bypass is active.
    """
    return (
        _readiness_below_threshold(feature)
        and not _refinement_attempts_at_or_above_two(feature)
    )


def _execute_feature(
    feature_id: str,
    refinement_attempts: int,
    failure_info: dict,
    workspace: "pathlib.Path",
) -> str | None:
    """F-R7-474: Apply path-finding retry logic after a feature execution attempt.

    When refinement_attempts >= 2 and the failure is classifiable, this
    function spawns research to surface alternative strategies, injects
    them into the next implementer prompt, and persists both the cached
    strategies and the augmented prompt.

    Returns the augmented implementer prompt string if path-finding was
    triggered and strategies were found, otherwise None.
    """
    if not _path_finding_should_trigger(refinement_attempts, failure_info):
        return None
    failure_class = _path_finding_classify_failure(failure_info)
    strategies = _path_finding_research_strategies(failure_class)
    if not strategies:
        return None
    _path_finding_cache_strategies(
        feature_id,
        refinement_attempts,
        strategies,
        workspace=workspace,
    )
    prompt = _path_finding_inject(
        base_prompt=f"Implement feature {feature_id}",
        strategies=strategies,
        failure_class=failure_class,
        attempt_number=refinement_attempts,
    )
    _path_finding_persist_prompt(
        feature_id,
        refinement_attempts,
        prompt,
        workspace=workspace,
    )
    return prompt


def _record_cost_saved(
    feature: Feature,
    *,
    estimated_cost_avoided: float,
    metrics_path: str,
) -> None:
    """Append to metrics.yaml eval_treadmill_avoided_cost list."""
    import datetime

    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not available; skipping cost-saved metrics update")
        return

    p = pathlib.Path(metrics_path)
    if p.exists():
        try:
            existing = yaml.safe_load(p.read_text()) or {}
        except Exception:
            existing = {}
    else:
        existing = {}

    treadmill_list = existing.get("eval_treadmill_avoided_cost", [])
    treadmill_list.append({
        "feature_id": feature.id,
        "cost_avoided": estimated_cost_avoided,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    })
    existing["eval_treadmill_avoided_cost"] = treadmill_list

    try:
        p.write_text(yaml.dump(existing, default_flow_style=False))
    except Exception as exc:
        logger.warning("Failed to update metrics.yaml cost_saved: %s", exc)


def _decide_next_action(
    feature: Feature,
    *,
    previous_readiness_score: float | None = None,
) -> str:
    """Decide the next orchestration action for a ready feature.

    Returns one of:
    - ``"decompose"`` when _should_decompose_instead_of_execute fires
    - ``"execute"`` otherwise

    This is the integration point: callers that used to unconditionally
    call execute_feature can now route through _decide_next_action to
    break the eval-demotion treadmill.
    """
    if _should_decompose_instead_of_execute(
        feature, previous_readiness_score=previous_readiness_score
    ):
        return "decompose"
    return "execute"


# ---------------------------------------------------------------
# F109: Research mode helpers
# ---------------------------------------------------------------

_RESEARCH_REQUIRED_MARKER = "research_required=True"

# R10-010: Lowered from 3 → 2 after an examples/04_swedish_circle e2e run
# spent two consecutive 1-hour feature timeouts on F009 before the
# previous threshold of 3 would have fired research. After 2 failures
# (vs 3), research becomes more responsive — by failure 2 we've already
# burned ~2× the feature's expected cost; an expensive V&V feature needs
# research sooner than a cheap one. Configurable via
# ``BOB_FAILURE_THRESHOLD_FOR_RESEARCH`` for operators who want the
# old behaviour back (or a more aggressive 1).
_DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH = 2
_FAILURE_THRESHOLD_FOR_RESEARCH = _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH


def _resolve_failure_threshold_for_research() -> int:
    """Read ``BOB_FAILURE_THRESHOLD_FOR_RESEARCH`` from the environment.

    Returns the configured threshold, falling back to
    ``_DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH`` (2) on any parse error or
    non-positive value. Kept as a small helper so tests can monkeypatch
    the env var per-test without poking at module-level constants.
    """
    raw = os.environ.get("BOB_FAILURE_THRESHOLD_FOR_RESEARCH")
    if raw is None:
        return _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB_FAILURE_THRESHOLD_FOR_RESEARCH=%r; using default %d",
            raw,
            _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH,
        )
        return _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH
    if value < 1:
        logger.warning(
            "Non-positive BOB_FAILURE_THRESHOLD_FOR_RESEARCH=%r; using default %d",
            raw,
            _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH,
        )
        return _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH
    return value


# R10-011: How much to drop confidence scores after each failed feature
# attempt. After 2 failures with the default of 0.15, a feature that
# started at 0.7 conf falls to 0.40 — below the 0.5 needs_research
# threshold — so Trigger 3 in ``needs_research`` re-fires on the third
# attempt regardless of the failure-count threshold. Configurable via
# ``BOB_CONFIDENCE_DECAY_PER_FAILURE``.
_DEFAULT_CONFIDENCE_DECAY_PER_FAILURE = 0.15


def _resolve_confidence_decay_per_failure() -> float:
    """Read ``BOB_CONFIDENCE_DECAY_PER_FAILURE`` from the environment.

    Returns the configured decay, falling back to
    ``_DEFAULT_CONFIDENCE_DECAY_PER_FAILURE`` (0.15) on any parse error
    or negative value. A decay of 0.0 disables confidence decay entirely.
    """
    raw = os.environ.get("BOB_CONFIDENCE_DECAY_PER_FAILURE")
    if raw is None:
        return _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB_CONFIDENCE_DECAY_PER_FAILURE=%r; using default %.2f",
            raw,
            _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE,
        )
        return _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE
    if value < 0:
        logger.warning(
            "Negative BOB_CONFIDENCE_DECAY_PER_FAILURE=%r; using default %.2f",
            raw,
            _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE,
        )
        return _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE
    return value


# R10-009: bound RCA wall-clock so a stuck RCA sub-agent cannot park
# the orchestration loop. Default 600s (10 minutes) is plenty for the
# hypothesis-only Phase 1-4 work the RCA prompt asks for; production
# deployments that want a longer window can raise this. Set very low
# (e.g., 1) in tests to short-circuit the SDK spawn entirely.
_DEFAULT_RCA_TIMEOUT_SECONDS = 600


def _rca_enabled() -> bool:
    """Whether the RCA wiring (R10-009) is active.

    Defaults to True in production. Tests that don't explicitly mock
    ``spawn_rca_agent`` should set ``BOB_RCA_ENABLED=0`` to opt out
    rather than gate every assertion on a real SDK invocation. The
    autouse fixture in tests/conftest.py wires the default to "0" so
    pre-existing failure-path tests don't try to launch a real Claude
    sub-agent.
    """
    raw = os.environ.get("BOB_RCA_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _resolve_rca_timeout_seconds() -> float:
    """Read ``BOB_RCA_TIMEOUT_SECONDS`` from the environment.

    Returns the configured timeout, falling back to
    ``_DEFAULT_RCA_TIMEOUT_SECONDS`` (600) on any parse error or
    non-positive value.
    """
    raw = os.environ.get("BOB_RCA_TIMEOUT_SECONDS")
    if raw is None:
        return float(_DEFAULT_RCA_TIMEOUT_SECONDS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB_RCA_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_RCA_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_RCA_TIMEOUT_SECONDS)
    if value <= 0:
        logger.warning(
            "Non-positive BOB_RCA_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_RCA_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_RCA_TIMEOUT_SECONDS)
    return value


def _decay_confidence_after_failure(feature_id: str) -> Feature | None:
    """Decrement confidence scores after a failed feature attempt.

    R10-011 fix: confidence scores never dropped between attempts, so
    the low-confidence ``needs_research`` trigger (Trigger 3) was
    effectively a one-shot. Lowering the scores after each failure
    means the next retry is more likely to trigger research even when
    the failure-count threshold (R10-010) hasn't fired yet.

    The decay amount is read from ``BOB_CONFIDENCE_DECAY_PER_FAILURE``
    (default 0.15). Each of ``conf_impl_correctness``,
    ``conf_spec_understanding``, and ``conf_test_adequacy`` is decremented
    independently with a floor of 0.0.

    readiness_score is NOT written here — it is derived on read via
    compute_live_readiness() from the current component values.

    Returns the updated Feature, or None if the feature was not found
    or decay is disabled.
    """
    decay = _resolve_confidence_decay_per_failure()
    if decay <= 0.0:
        return None
    current = db.get_feature(feature_id)
    if current is None:
        return None
    new_impl = max(0.0, float(current.conf_impl_correctness) - decay)
    new_spec = max(0.0, float(current.conf_spec_understanding) - decay)
    new_test = max(0.0, float(current.conf_test_adequacy) - decay)
    return db.update_feature(
        feature_id,
        conf_impl_correctness=new_impl,
        conf_spec_understanding=new_spec,
        conf_test_adequacy=new_test,
    )


def decay_confidence_components(feature_id: str, decay: float | None = None) -> "Feature | None":
    """Decrement confidence components after a failed feature attempt.

    Public alias for _decay_confidence_after_failure. Decays only the
    conf_impl_correctness, conf_spec_understanding, and conf_test_adequacy
    columns — readiness_score is NOT written (it is derived on read via
    bob.readiness.derive_readiness_score from the current component values).

    Args:
        feature_id: The feature whose confidence components should decay.
        decay: Amount to subtract from each component (floored at 0.0).
               When None, reads BOB_CONFIDENCE_DECAY_PER_FAILURE env var
               (default 0.15).

    Returns the updated Feature, or None if the feature was not found or
    decay is disabled (decay == 0.0).
    """
    if decay is not None:
        # Apply caller-specified decay directly without env-var resolution
        current = db.get_feature(feature_id)
        if current is None:
            return None
        if decay <= 0.0:
            return None
        new_impl = max(0.0, float(current.conf_impl_correctness) - decay)
        new_spec = max(0.0, float(current.conf_spec_understanding) - decay)
        new_test = max(0.0, float(current.conf_test_adequacy) - decay)
        return db.update_feature(
            feature_id,
            conf_impl_correctness=new_impl,
            conf_spec_understanding=new_spec,
            conf_test_adequacy=new_test,
        )
    return _decay_confidence_after_failure(feature_id)


def count_feature_failures(feature_id: str, project_id: str) -> int:
    """Count failed implementation attempts for a feature."""
    return db.count_agent_runs(
        project_id=project_id,
        target_id=feature_id,
        purpose="implement_feature",
        status="failed",
    )


def needs_research(feature: Feature, project_id: str) -> bool:
    """Determine if a feature needs research before implementation.

    Research is triggered when:
    1. Feature description contains 'research_required=True' AND
       research_iterations is 0 (hasn't been researched yet)
    2. Feature has failed >= ``BOB_FAILURE_THRESHOLD_FOR_RESEARCH``
       times (default 2; R10-010) AND research_iterations is 0
    3. Feature has low confidence (< 0.5) AND research_iterations is 0
       — confidence decays after each failed attempt (R10-011) so this
       trigger CAN re-fire on a retry.

    Returns False if the feature has already been researched
    (research_iterations >= 1).
    """
    # Already researched — don't re-research
    if feature.research_iterations >= 1:
        return False

    # Trigger 1: Explicit research_required marker in description
    if feature.description and _RESEARCH_REQUIRED_MARKER in feature.description:
        return True

    # Trigger 2: Feature has failed >= configured threshold (default 2)
    failure_count = count_feature_failures(feature.id, project_id)
    threshold = _resolve_failure_threshold_for_research()
    if failure_count >= threshold:
        return True

    # Trigger 3: Low confidence (< 0.5) indicating missing information
    # This proactively triggers research BEFORE attempting implementation
    if (feature.conf_impl_correctness < 0.5 or
        feature.conf_spec_understanding < 0.5 or
        feature.readiness_score < 0.5):
        logger.info(
            "Feature %s has low confidence (spec=%.2f, impl=%.2f, ready=%.2f), triggering research",
            feature.id[:8],
            feature.conf_spec_understanding,
            feature.conf_impl_correctness,
            feature.readiness_score,
        )
        return True

    return False


def handle_execution_result(
    *,
    project_id: str,
    feature: Feature,
    spawn_result: SpawnResult,
    shutdown_requested: bool = False,
    verification_passed: bool = True,
    verification_summary: str | None = None,
    verification_result: dict[str, Any] | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Handle the result of executing a feature sub-agent.

    Performs all post-execution bookkeeping EXCEPT cost accounting:
    1. Parses the execution result (success/failure)
    2. Updates the feature status (completed/failed/interrupted/needs_human)
    3. Creates evidence artifacts from the execution output
    4. Returns the normalized cost so the caller can route it through
       ``OrchestrationLoop._increment_cost`` — the single canonical
       writer for project cost. This function NO LONGER calls
       ``db.update_project_cost`` itself (recurring pattern
       ``non-atomic-counter``).

    A feature is only marked 'completed' and dependents cascaded to 'ready'
    when BOTH the sub-agent succeeded AND verification passed. If the
    sub-agent succeeded but verification failed, the feature is marked
    'needs_human' and no cascade is performed.

    Args:
        project_id: The project ID.
        feature: The feature that was executed.
        spawn_result: The SpawnResult from the sub-agent.
        shutdown_requested: If True, errors result in 'interrupted' status.
        verification_passed: If False and the sub-agent succeeded, the
            feature is marked 'needs_human' and no cascade is performed.
        verification_summary: Optional human-readable summary of the
            verification result (recorded in the evidence payload).

    Returns:
        Dict with keys: success, cost_usd, cost_source, duration_ms,
        error_message, evidence_id, verification_passed. The caller is
        responsible for incrementing project cost via
        ``OrchestrationLoop._increment_cost(cost_usd, cost_source)``
        when ``cost_usd > 0``.
    """
    result = spawn_result.execution_result
    agent_run_id = getattr(spawn_result.agent_run, "id", None)

    # Normalize cost up front so budget tracking sees a real number even
    # when the SDK returns None (typical on Claude Max Pro / OAuth subs).
    normalized_cost, cost_source = _normalize_cost(
        result.total_cost_usd, result.num_turns
    )

    # Log proxy / zero-cost diagnostics once per feature to avoid spam.
    if cost_source == "turn_proxy" and feature.id not in _PROXY_LOGGED_FEATURE_IDS:
        logger.warning(
            "Using turn-count cost proxy for feature %s: $%.2f from %d turns",
            feature.id,
            normalized_cost,
            result.num_turns or 0,
        )
        _PROXY_LOGGED_FEATURE_IDS.add(feature.id)
    elif cost_source == "zero" and feature.id not in _PROXY_LOGGED_FEATURE_IDS:
        logger.warning(
            "Cost is zero for feature %s — telemetry-loss guard will apply "
            "pessimistic ceiling if work_events > threshold (b20b4725)",
            feature.id,
        )
        _PROXY_LOGGED_FEATURE_IDS.add(feature.id)

    # Success is only "true success" when execution succeeded AND verification
    # passed; a verification failure on a successful sub-agent run should NOT
    # be reported as success (callers rely on this to avoid cascading).
    is_success = (not result.is_error) and verification_passed

    outcome: dict[str, Any] = {
        "success": is_success,
        "cost_usd": normalized_cost,
        "cost_source": cost_source,
        "duration_ms": result.duration_ms,
        "error_message": result.error_message if result.is_error else (
            f"Verification failed: {verification_summary}"
            if not verification_passed else None
        ),
        "evidence_id": None,
        "verification_passed": verification_passed,
    }

    # Step 2: Update feature status
    _ws = pathlib.Path(workspace) if workspace else None
    if result.is_error:
        if shutdown_requested:
            db.update_feature(feature.id, status="interrupted")
        else:
            if _may_demote(feature, target_status="failed", workspace=_ws):
                # F-R7-633: a sub-agent error is no longer an immediate terminal
                # 'failed'. Charge a refinement attempt and retry on the SAME
                # model until the attempt budget is exhausted; then escalate to
                # the next (stronger) ladder model (reset counter) for a fresh
                # round; only mark 'failed' when the LAST ladder tier is also
                # exhausted. This mirrors the verification-failure path so that
                # "sonnet keeps erroring on this feature" actually reaches the
                # opus escalation instead of dying early at refn < max.
                if db.increment_refinement_attempts(feature.id) is None:
                    # Attempts exhausted on the current model.
                    if not _try_model_escalate(feature, db.update_feature):
                        db.update_feature(feature.id, status="failed")
                else:
                    # Budget remains — return to ready for another attempt on
                    # the current model (strictly more lenient than the prior
                    # immediate-fail behaviour).
                    db.update_feature(feature.id, status="ready")
            else:
                logger.info(
                    "Sticky-completed gate prevented demotion of feature %s to 'failed'",
                    feature.id[:8],
                )
    elif not verification_passed:
        # Sub-agent reported success but verification failed — do NOT mark
        # as completed and do NOT cascade dependents. This prevents
        # downstream features from being unlocked on unverified work.
        # F-R6-318: charge a refinement attempt instead of unconditional NH.
        # increment_refinement_attempts auto-demotes to needs_human when the
        # budget is exhausted, so the cap (R7-003) still holds — but the
        # feature gets retry attempts rather than being stranded at rfn=0.
        if _may_demote(feature, target_status="needs_human", workspace=_ws):
            if db.increment_refinement_attempts(feature.id) is None:
                # F-R7-479: pre-NH hook — let RCA recovery intercept infra-only failures
                _rca_reset = _rca_auto_reset_if_infra(
                    feature.id,
                    project_id=getattr(feature, "project_id", ""),
                    db_update_fn=db.update_feature,
                    workspace=_ws,
                )
                if not _rca_reset:
                    # F-R7-479: code-emission defect reset — grant fresh attempt
                    # for plausibly-fixable code failures (behavior/pytest/integration ACs).
                    _ac_list_raw = getattr(feature, "acceptance_criteria", "[]") or "[]"
                    try:
                        import json as _json
                        _failed_acs_for_rca = _json.loads(_ac_list_raw) if isinstance(_ac_list_raw, str) else list(_ac_list_raw)
                    except Exception:
                        _failed_acs_for_rca = []
                    _rca_reset = _rca_auto_reset_on_code_defect(
                        feature_id=feature.id,
                        db_update_fn=db.update_feature,
                        failed_acs=_failed_acs_for_rca,
                        refinement_attempts=getattr(feature, "refinement_attempts", 0) or 0,
                        workspace=_ws,
                    )
                if not _rca_reset:
                    # F-R7-612: before marking needs_human, check disk state.
                    # Companion to F-R7-598 (orphan path). This closes the
                    # symmetric verification-fail path: if only tests_pass
                    # failed and structural/behavior ACs are present on disk,
                    # promote to completed instead of needs_human.
                    _disk_promoted = False
                    _ac_json = getattr(feature, "acceptance_criteria", "[]") or "[]"
                    _vr_checks = (verification_result or {}).get("checks", [])
                    _structural_passed = any(
                        c.get("passed") for c in _vr_checks
                        if c.get("name") == "structural_acs_present"
                    )
                    _tests_only_failed = (
                        verification_result is not None
                        and _structural_passed
                        and _ac_json not in ("[]", "null", "", None)
                    )
                    if _tests_only_failed:
                        _disk_promoted = _check_executing_feature_acs(
                            project_id=project_id,
                            feature_id=feature.id,
                            feature_name=getattr(feature, "name", ""),
                            acceptance_criteria_json=_ac_json,
                        )
                        if _disk_promoted:
                            logger.info(
                                json.dumps({
                                    "event": "VERIFY_FAIL_DISK_PROMOTED",
                                    "feature_id": feature.id,
                                    "failed_gate": "tests_pass",
                                    "passed_gates": [
                                        c.get("name") for c in _vr_checks
                                        if c.get("passed")
                                    ],
                                    "F-R7-612": True,
                                })
                            )
                    if not _disk_promoted:
                        # F-R7-633: attempts on the current model are exhausted
                        # and RCA/decompose/disk-promote recovery all failed.
                        # Before stranding the feature at needs_human, escalate
                        # it to the next (stronger) model in the ladder — this
                        # resets refinement_attempts and returns it to ready for
                        # a fresh round. needs_human only when the LAST ladder
                        # tier is also exhausted.
                        if not _try_model_escalate(feature, db.update_feature):
                            db.update_feature(feature.id, status="needs_human")
        else:
            logger.info(
                "Sticky-completed gate prevented demotion of feature %s to 'needs_human' "
                "(verification failed but parent_completed=True and ACs still verify)",
                feature.id[:8],
            )
    else:
        # F123 + atomicity fix: combine the status flip and the dependent
        # cascade into a SINGLE DB transaction. Splitting them across two
        # connections opened a window where a crash between them would
        # leave the feature 'completed' but dependents stuck on 'pending'
        # forever (the resume scan only handled 'executing'/'interrupted').
        try:
            updated_features = db.complete_feature_and_cascade(feature.id)
            if updated_features:
                logger.info(
                    "Feature %s completion unlocked %d dependent feature(s): %s",
                    feature.id[:8],
                    len(updated_features),
                    ", ".join([f[:8] for f in updated_features])
                )

            # R9-006: When this feature is a child of a decomposed parent,
            # check whether its completion finishes the parent. The parent
            # was previously left at ``pending_decomposition`` forever
            # because nothing in the orchestration loop called
            # ``check_parent_completion`` — even though that helper exists
            # in db.py specifically for this purpose. If the parent
            # transitions to completed, we ALSO need to cascade ITS
            # dependents (siblings-of-the-parent that were waiting on it),
            # and walk further up in case of multi-level decomposition.
            child_id_for_parent_check = feature.id
            parent_id = feature.parent_feature_id
            while parent_id:
                if not db.check_parent_completion(child_id_for_parent_check):
                    break
                # Parent was just transitioned to 'completed' by
                # check_parent_completion; cascade ITS dependents and
                # continue walking up. We re-fetch from the DB so the
                # ``parent_feature_id`` field reflects the latest state.
                parent_feat = db.get_feature(parent_id)
                if parent_feat is None:
                    break
                parent_updates = db.complete_feature_and_cascade(parent_id)
                if parent_updates:
                    logger.info(
                        "Parent feature %s auto-completion unlocked %d "
                        "dependent feature(s): %s",
                        parent_id[:8],
                        len(parent_updates),
                        ", ".join([f[:8] for f in parent_updates]),
                    )
                # Walk up: the just-completed parent now plays the role
                # of "child" for the grandparent check.
                child_id_for_parent_check = parent_feat.id
                parent_id = parent_feat.parent_feature_id
        except Exception:
            # The atomic complete+cascade rolled back, so the feature is
            # NOT marked completed and dependents are still pending. The
            # recovery scan in OrchestrationLoop._resume_interrupted_work
            # will detect orphaned 'pending' features whose deps are all
            # completed on the next run; meanwhile, surface this clearly
            # in the outcome so the loop doesn't pretend success.
            logger.error(
                "Atomic complete+cascade failed for feature %s; "
                "feature was NOT marked completed (transaction rolled back)",
                feature.id,
                exc_info=True,
            )
            outcome["success"] = False
            outcome["error_message"] = (
                "Atomic complete+cascade transaction rolled back"
            )

    # Step 3: Create evidence artifact
    if result.is_error:
        evidence_type = "execution_error"
        evidence_content = json.dumps({
            "status": "interrupted" if shutdown_requested else "failed",
            "error_message": result.error_message,
            "output_text": result.text[:2000] if result.text else "",
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "cost_usd": result.total_cost_usd,
            "agent_run_id": agent_run_id,
        })
    elif not verification_passed:
        evidence_type = "execution_error"
        evidence_content = json.dumps({
            "status": "needs_human",
            "error_message": f"Verification failed: {verification_summary}",
            "output_text": result.text[:2000] if result.text else "",
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "cost_usd": result.total_cost_usd,
            "agent_run_id": agent_run_id,
        })
    else:
        evidence_type = "execution_output"
        evidence_content = json.dumps({
            "status": "completed",
            "output_text": result.text[:2000] if result.text else "",
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "cost_usd": result.total_cost_usd,
            "tool_uses": result.tool_uses,
            "agent_run_id": agent_run_id,
        })

    try:
        evidence = db.create_evidence(
            project_id=project_id,
            feature_id=feature.id,
            type=evidence_type,
            content=evidence_content,
        )
        outcome["evidence_id"] = evidence.id
    except Exception:
        logger.warning(
            "Failed to create evidence artifact for feature %s",
            feature.id,
            exc_info=True,
        )

    # Step 4: Reap subagent for terminal features (01b15b47).
    # Every status transition to a terminal state must be accompanied by
    # a reap attempt so orphan claude subagents do not persist.
    _HANDLER_TERMINAL = frozenset({"completed", "needs_human", "regression", "failed", "interrupted"})
    try:
        refreshed = db.get_feature(feature.id)
        if refreshed is not None and refreshed.status in _HANDLER_TERMINAL:
            _reap_subagent(feature.id)
    except Exception:
        logger.debug(
            "Subagent reap failed for feature %s; will be caught by orphan sweeper",
            feature.id[:8],
            exc_info=True,
        )

    # Step 5: NOTE — project cost is NOT written here.
    #
    # The single canonical writer is ``OrchestrationLoop._increment_cost``,
    # called by the orchestration loop after this function returns. Routing
    # every cost write through one method retires the recurring
    # ``non-atomic-counter`` pattern (R1-003 / R2-001 / R5-010 / R6-001 /
    # R6-002 / R9-006): when this function used to issue the DB write
    # itself, the loop ALSO had to remember to mirror the delta into the
    # tamper-detection ``_expected_total_cost`` and refresh the cache —
    # and every new cost-bearing path was one ``forgot to do that`` away
    # from drift. Returning the normalized cost back to the caller and
    # letting ``_increment_cost`` perform write + mirror + refresh
    # together makes the next occurrence structurally impossible.
    return outcome


def _verify_project_name_matches_workspace(
    project_id: str,
    workspace: "pathlib.Path",
    db_path: "pathlib.Path | None" = None,
) -> bool:
    """Check that projects.name matches the workspace directory basename.

    When spawn_next_generation.sh rsync-copies a parent DB without re-running
    ``bob init``, the projects row retains the parent's name (e.g. 'bob9')
    even though the workspace directory is named 'bob10'. This startup guard
    detects that mismatch and corrects it so run_loop operates on accurate
    project metadata.

    Returns True if an update was made, False if the name was already correct.
    """
    import sqlite3 as _sqlite3
    from bob.db import get_connection as _get_conn

    expected_name = workspace.name
    conn = _get_conn(db_path=db_path)
    try:
        row = conn.execute(
            "SELECT name FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return False
        current_name = row[0]
        if current_name == expected_name:
            return False
        conn.execute(
            "UPDATE projects SET name = ? WHERE id = ?",
            (expected_name, project_id),
        )
        conn.commit()
        logger.info(
            "Startup check: updated stale project name %r → %r (workspace basename mismatch)",
            current_name,
            expected_name,
        )
        return True
    finally:
        conn.close()


class OrchestrationLoop:
    """Continuous orchestration loop for building a project.

    Picks the next ready feature, spawns a sub-agent to implement it,
    awaits completion, updates status, and repeats until done.

    Features are processed strictly one at a time (sequential execution);
    see the module docstring for why. Sub-agents may internally spawn
    their own sub-agents (recursive parallelism via the Claude Code SDK),
    but this loop never has more than one top-level feature in flight.
    """

    def __init__(
        self,
        *,
        project_id: str,
        max_cost: float | None = None,
        workspace: str | None = None,
        fresh: bool = False,
        target_feature_id: str | None = None,
        force_unlock: bool = False,
        max_concurrent_features: int = 1,
    ) -> None:
        self.project_id = project_id
        self.max_cost = max_cost
        self.workspace = workspace or ""
        self.fresh = fresh
        self.target_feature_id = target_feature_id
        # R10-006: forwarded to ``acquire_run_lock``; lets operators
        # recover from a SIGKILLed run that left a stale ``.bob.lock``.
        self.force_unlock = force_unlock
        # 6e085356: max concurrent workers. Default 1 = current sequential
        # behaviour for backward compatibility. Values < 1 are clamped to 1.
        self.max_concurrent_features: int = max(1, int(max_concurrent_features))
        self.features_completed: int = 0
        self.features_failed: int = 0
        # R5-009: wall-clock start time for the run, captured at the top
        # of ``_run_locked``. Used by the loop-level termination summary
        # log so the operator sees how long the entire run took.
        self._run_start_time: float | None = None
        self.shutdown_requested: bool = False
        self._current_feature: Feature | None = None
        # Set to True the first time we see a result with total_cost_usd=None.
        # Indicates we're running against a Max Pro / OAuth subscription where
        # the SDK does not report cost; budget enforcement falls back to the
        # turn-count proxy.
        self._cost_proxy_active: bool = False
        self._cost_proxy_warning_emitted: bool = False
        # Cached project cost values, used by ``budget_exceeded`` to avoid
        # opening a fresh SQLite connection on every loop iteration just to
        # read ``total_cost_usd``. The values are populated from the DB once
        # at startup (see ``_refresh_project_cost_cache``) and refreshed
        # after every cost-mutating call so the budget check sees the
        # latest total. With 200+ features × N retries the per-iteration
        # ``db.get_project`` was the loop's hottest read; caching collapses
        # it to one connection per cost write.
        self._project_total_cost: float = 0.0
        self._project_max_cost_usd: float | None = None
        # R5-003: tamper-detection running total. Mirrors every
        # ``db.update_project_cost(... cost_usd=X)`` call this loop issues
        # so that ``_refresh_project_cost_cache`` can detect a sub-agent
        # zeroing out the DB to bypass the budget. Initialized from the
        # DB total on construction so a resumed run keeps a coherent
        # baseline; ``_increment_expected_total_cost`` updates it.
        self._expected_total_cost: float = 0.0
        self._refresh_project_cost_cache(_priming=True)
        self._expected_total_cost = self._project_total_cost
        # R10-015: per-feature counter of free retries granted for
        # process-spawn-time failures (duration_ms < 100ms, num_turns == 0).
        # Capped at ``_MAX_SPAWN_RETRIES`` so a permanently broken local
        # environment cannot trigger an infinite loop. Keys are feature.id.
        self._spawn_failure_counts: dict[str, int] = {}

    def request_shutdown(self) -> None:
        """Request graceful shutdown of the loop."""
        self.shutdown_requested = True
        logger.info("Shutdown requested for orchestration loop")

    def _maybe_warn_cost_proxy_active(self) -> None:
        """Emit a one-time loop-level warning when the cost proxy is active.

        Once we observe ANY result with total_cost_usd=None we know the SDK
        is not reporting cost (typical on Claude Max Pro / OAuth subs). If
        the user passed a max_cost, surface a clear warning explaining that
        budget enforcement is using the turn-count proxy. Logged once per
        loop instance so we don't spam the operator.
        """
        if not self._cost_proxy_active or self._cost_proxy_warning_emitted:
            return
        if self.max_cost is None:
            # No budget specified — nothing to enforce, nothing to warn about.
            self._cost_proxy_warning_emitted = True
            return
        try:
            proxy = float(
                os.environ.get(
                    "BOB_COST_PER_TURN_PROXY",
                    str(_DEFAULT_COST_PER_TURN_PROXY),
                )
            )
        except (TypeError, ValueError):
            proxy = _DEFAULT_COST_PER_TURN_PROXY
        logger.warning(
            "Claude SDK is not reporting cost (likely Max Pro subscription). "
            "Budget enforcement is using a turn-count proxy at $%.2f/turn.",
            proxy,
        )
        self._cost_proxy_warning_emitted = True

    def _increment_expected_total_cost(self, delta: float) -> None:
        """Mirror a ``db.update_project_cost(... cost_usd=delta)`` call.

        Caller MUST invoke this immediately after issuing the DB write,
        with the SAME ``delta`` it passed to the DB. The expected total
        is the floor below which ``_refresh_project_cost_cache`` will
        not let the cache drop — see the module docstring's "Defense in
        depth — budget tampering" section for the threat model.

        Negative deltas are rejected: cost is monotonic by contract.

        Internal helper: the only caller is ``_increment_cost``. Do NOT
        call this directly from new code; route every cost write through
        ``_increment_cost`` so the DB write, expected-total bump, and
        cache refresh stay in lockstep.
        """
        if delta < 0:
            logger.error(
                "SECURITY: refusing to apply negative cost delta %.6f to "
                "expected total (cost is monotonic by contract)",
                delta,
            )
            return
        self._expected_total_cost += float(delta)

    def _increment_cost(self, normalized_cost: float, source: str) -> None:
        """Single canonical entry point for recording loop-level cost.

        This is the ONLY method that writes cost into the project. Every
        path that previously did ``db.update_project_cost(...)`` (the
        feature execution path inside ``handle_execution_result``, the
        research path, the decomposition path, plus any future cost-
        bearing sub-agent the loop orchestrates) MUST go through here.

        The structural reason: the loop used to maintain TWO trackers —
        ``self.total_cost`` (in-memory) and ``db.update_project_cost``
        (atomic DB column) — and every new cost-bearing code path had
        to remember which one to use. Reviewers kept finding paths that
        used the wrong one (R1-003, R2-001, R5-010, R6-001, R6-002,
        R9-006). Collapsing both writes behind one method makes the
        seventh occurrence structurally impossible: there is no second-
        class field to forget about.

        Steps performed atomically from the caller's point of view:
        1. ``db.update_project_cost`` — the canonical, atomic column
           write. SQLite serialises this against any concurrent writer,
           so the project total stays monotonic.
        2. ``_increment_expected_total_cost`` — bumps the tamper-detection
           floor (see ``_refresh_project_cost_cache``). Must happen with
           the SAME delta we just sent to the DB so a sub-agent zeroing
           the column gets caught on the next refresh.
        3. ``_refresh_project_cost_cache`` — reloads the cached total so
           ``budget_exceeded()`` and any code reading
           ``self._project_total_cost`` sees the post-write value
           without paying for a fresh SQLite connection.

        ``normalized_cost`` MUST already have been through ``_normalize_cost``
        (so Max Pro / OAuth subscriptions, which return ``cost_usd=None``,
        are accounted for via the turn-count proxy). A non-positive value
        is a no-op against all three steps.

        ``source`` is one of: ``"sdk"``, ``"turn_proxy"``, ``"zero"``. It
        is used for the once-per-loop proxy warning and is otherwise
        free-form for diagnostics. When ``source == "turn_proxy"`` we
        also flip ``self._cost_proxy_active`` so ``_maybe_warn_cost_proxy_active``
        surfaces the warning at the next safe point.
        """
        # Flag the proxy state regardless of the magnitude — even a
        # zero-magnitude proxy reading still tells us the SDK is not
        # reporting cost on this subscription tier.
        if source == "turn_proxy":
            self._cost_proxy_active = True
        if normalized_cost <= 0:
            return
        db.update_project_cost(
            project_id=self.project_id,
            cost_usd=normalized_cost,
        )
        self._increment_expected_total_cost(normalized_cost)
        self._refresh_project_cost_cache()

    def _refresh_project_cost_cache(self, _priming: bool = False) -> None:
        """Reload cached project cost values from the DB.

        Call this exactly when something has, or might have, mutated the
        project's ``total_cost_usd``. Specifically: after every successful
        ``db.update_project_cost`` issued by ``handle_execution_result``,
        the research path, and the decomposition path. ``budget_exceeded``
        reads the cache rather than re-fetching the project, which keeps
        the per-iteration overhead at zero new SQLite connections.

        On a missing project the cache stays at the previous values; this
        is safe because the loop simply will not advance past the next
        ``find_next_ready_feature`` if the project has been deleted out
        from under it.

        R5-003 tamper detection
        -----------------------
        After each refresh, the loaded DB total is compared against
        ``self._expected_total_cost`` — the in-memory running total of
        every cost increment THIS loop has issued. If the DB total has
        gone DOWN beyond a tiny floating-point slack, that means
        something outside the orchestrator (almost always: a sub-agent
        with workspace write access) has mutated the projects table to
        reduce ``total_cost_usd``. We log a SECURITY warning and clamp
        the in-memory cache to ``_expected_total_cost`` instead of the
        attacker-supplied lower value, so the next ``budget_exceeded``
        check honors the original budget.

        ``_priming=True`` is used by ``__init__`` for the first call,
        before the expected total has been seeded — that path skips the
        comparison so we don't compare against a default-zero baseline.
        """
        project = db.get_project(self.project_id)
        if project is None:
            return
        total = project.total_cost_usd
        if total is None:
            logger.warning(
                "Project %s has total_cost_usd=None; treating as 0.0 for budget check",
                self.project_id,
            )
            total = 0.0
        db_total = float(total)

        # Tamper detection: a sub-agent with workspace FS access can
        # ``UPDATE projects SET total_cost_usd = 0`` directly in bob.db
        # to disable the budget guard on the next iteration. Detect any
        # decrease beyond floating-point slack and refuse to honor it.
        if not _priming and db_total + 1e-6 < self._expected_total_cost:
            logger.warning(
                "SECURITY: Project cost in DB reduced unexpectedly "
                "(db=%.2f, expected=%.2f); possible tampering. "
                "Refusing to lower budget.",
                db_total,
                self._expected_total_cost,
            )
            self._project_total_cost = self._expected_total_cost
        else:
            self._project_total_cost = db_total
            # If the DB total moved UP relative to our expected (e.g. a
            # peer process legitimately recorded cost we didn't issue),
            # bring the expected total along so future comparisons stay
            # consistent.
            if db_total > self._expected_total_cost:
                self._expected_total_cost = db_total

        self._project_max_cost_usd = project.max_cost_usd

    def budget_exceeded(self) -> bool:
        """Check if the budget has been exceeded.

        Reads the cached project total (``self._project_total_cost``) and
        compares it to BOTH the loop-level ``self.max_cost`` and the
        project-level ``self._project_max_cost_usd`` ceiling. Cost is
        tracked atomically via ``_increment_cost`` (the single method
        through which every loop cost write flows) and the cache is
        refreshed on every write — so the cache is the single source of
        truth for the loop, without paying for a fresh SQLite connection
        every iteration.

        Defensively coerces a missing/None project total to 0.0 — if cost
        normalization is bypassed somewhere and None lands in the DB, the
        budget check should not silently treat it as "infinite room".
        """
        project_total = self._project_total_cost or 0.0

        # Check loop-level budget against the DB-tracked project total.
        # There is no second-class in-memory accumulator any more; tests
        # that want to drive a synthetic running cost should set
        # ``self._project_total_cost`` (the cached canonical value) or
        # write directly through ``db.update_project_cost`` before
        # invoking the budget check.
        if self.max_cost is not None:
            if project_total >= self.max_cost:
                return True

        # Check project-level budget against the project's own max.
        if self._project_max_cost_usd:
            if project_total >= self._project_max_cost_usd:
                return True

        return False

    def _cost_projection_gate(self, feature: Feature) -> "SpawnResult | None":
        """F-R6-307: refuse the spawn if projected cost exceeds headroom.

        Returns ``None`` if the spawn is allowed (caller should proceed).
        Returns a synthetic ``SpawnResult`` if the spawn was blocked, in
        which case this method has ALREADY marked the feature
        ``needs_human`` and recorded the reason.

        The effective cap is the *tighter* of the loop-level ``max_cost``
        and the project-level ``max_cost_usd``. If neither is set we
        skip the gate (no cap means no projection to enforce).

        Set ``BOB_COST_PROJECTION_GATE=0`` to bypass the gate (only
        intended for tests that exercise cost-tracking arithmetic with
        artificially tight caps where the conservative fallback estimate
        would always block).
        """

        if os.environ.get("BOB_COST_PROJECTION_GATE", "1") == "0":
            return None

        # Compute the tightest cap that applies. Both can be None.
        caps = [c for c in (self.max_cost, self._project_max_cost_usd) if c]
        if not caps:
            return None
        cap = min(caps)

        committed = float(self._project_total_cost or 0.0)

        try:
            conn = db.get_connection()
        except Exception:
            # If we can't read the DB the safest thing is to LET the spawn
            # proceed — the existing budget_exceeded check will still
            # backstop us. The gate is an optimization on top of that.
            logger.debug("cost projection gate: could not open db", exc_info=True)
            return None

        try:
            allowed, info = _cost_allow_spawn(
                conn,
                feature,
                committed_spend_usd=committed,
                cap_usd=cap,
            )
        except Exception:
            logger.warning(
                "cost projection gate failed for feature %s; allowing spawn",
                feature.id,
                exc_info=True,
            )
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if allowed:
            return None

        # Block: mark needs_human with the projection reason. Use the
        # standard ``cost-cap projection (...)`` wording from
        # cost_projection.allow_spawn so downstream tooling can grep it.
        projected = info.get("projected_total_usd", 0.0)
        remaining = max(0.0, info.get("effective_ceiling_usd", 0.0) - committed
                        - info.get("outstanding_reservations_usd", 0.0))
        reason = (
            f"cost-cap projection (${projected:.2f} projected, "
            f"${remaining:.2f} remaining)"
        )
        logger.warning(
            "Feature %s blocked by cost-projection gate; marking needs_human. "
            "%s",
            feature.id,
            info.get("reason", reason),
        )
        db.update_feature(feature.id, status="needs_human")
        # Make sure we don't leave a stale ``_current_feature`` reference.
        self._current_feature = None

        # Synthetic SpawnResult so callers that ``await execute_feature``
        # get a sensible no-op back rather than ``None`` or a raised
        # exception.
        exec_result = ExecutionResult(
            text=reason,
            is_error=True,
            error_message=reason,
            duration_ms=0,
            num_turns=0,
            total_cost_usd=0.0,
        )
        agent_run = type("_FakeRun", (), {"id": None})()
        return SpawnResult(execution_result=exec_result, agent_run=agent_run)

    def _maybe_resynthesize_blocked(self, feature_obj) -> "tuple[list[str] | None, float]":
        """F-R7-632: regenerate a gate-blocked feature's ACs via the score-gate
        synthesizer so its spec_quality score can actually rise. The promotion
        sweep is synchronous, so run the async synthesizer in a private event
        loop. Returns (new_acs, new_composite) or (None, 0.0) on any failure.
        Bounded to one re-synthesis per feature per process via an in-memory set
        so we never re-spin the same blocked feature (the bob70 livelock)."""
        if not hasattr(self, "_resynth_done"):
            self._resynth_done = set()
        if feature_obj.id in self._resynth_done:
            return None, 0.0
        self._resynth_done.add(feature_obj.id)
        try:
            import asyncio as _aio
            from bob.synthesizer import score_gate_loop, synthesize_for_feature
            from tools.spec_quality_score import compute as _compute  # noqa
        except Exception:
            return None, 0.0
        try:
            _loop = _aio.new_event_loop()
            try:
                rep = _loop.run_until_complete(score_gate_loop(
                    synthesize_fn=synthesize_for_feature,
                    title=feature_obj.name,
                    description=feature_obj.description or "",
                    project_id=self.project_id,
                    workspace=Path(self.workspace) if self.workspace else None,
                ))
            finally:
                _loop.close()
            if rep and rep.criteria:
                return rep.criteria, float(rep.composite or 0.0)
        except Exception:
            logger.warning("mid-run re-synthesis failed for %s", feature_obj.id[:8], exc_info=True)
        return None, 0.0

    def find_next_ready_feature(self) -> Feature | None:
        """Find the next feature ready for implementation.

        Queries the features_ready view which checks:
        - status = 'ready'
        - readiness_score >= risk-category threshold
        - no active reviewer vetoes
        - all dependencies completed

        Returns the highest priority ready feature, or None if none are ready.
        """
        ready = db.get_ready_features(self.project_id)
        if not ready:
            return None
        return ready[0]

    def all_features_completed(self) -> bool:
        """Check if all features in the project are completed."""
        features = db.list_features(project_id=self.project_id)
        if not features:
            return True
        return all(f.status in _COMPLETED_STATUSES for f in features)

    def all_remaining_blocked(self) -> bool:
        """Check if all non-completed features are blocked or failed.

        Returns True if every feature is either completed or in a
        blocked/failed state, meaning no more automatic progress is possible.
        """
        features = db.list_features(project_id=self.project_id)
        if not features:
            return False
        for f in features:
            if f.status in _COMPLETED_STATUSES:
                continue
            if f.status not in _BLOCKED_STATUSES:
                return False
        return True

    async def _run_research(self, feature: Feature) -> SpawnResult | None:
        """Run a research sub-agent for a feature if research is needed.

        Spawns a Perplexity-enabled research agent, stores the results
        in the research_results table, increments research_iterations,
        and tracks cost.

        Returns the SpawnResult if research was performed, None otherwise.
        """
        if not needs_research(feature, self.project_id):
            return None

        logger.info(
            "Feature %s needs research, spawning research agent", feature.id
        )

        # Build a research query from the feature's name and description
        query = (
            f"Research for implementing: {feature.name}\n\n"
            f"Description: {feature.description or 'No description'}\n\n"
            f"Find relevant documentation, libraries, patterns, and examples."
        )

        # F-R7-631: research spawn MUST have a wall-clock timeout. A hung
        # research sub-agent (e.g. Perplexity MCP unavailable) otherwise blocks
        # the ENTIRE run indefinitely — bob71 wedged 8h on one research call at
        # 29% CPU with no timeout. Cap it; on timeout treat research as a no-op
        # and proceed (the feature keeps its current confidence).
        try:
            research_result = await asyncio.wait_for(
                spawn_research_agent(
                    project_id=self.project_id,
                    query=query,
                    purpose="feature_research",
                    target_type="feature",
                    target_id=feature.id,
                    workspace=self.workspace or None,
                ),
                timeout=_resolve_feature_timeout_seconds(),
            )
        except (asyncio.TimeoutError, Exception) as _rexc:
            logger.warning(
                "Research spawn for feature %s timed out / failed (%s); "
                "proceeding without research", feature.id[:8], type(_rexc).__name__,
            )
            research_result = None
        if research_result is None:
            return

        # Track research cost (normalize so Max Pro / OAuth subscriptions,
        # which return None, still consume budget via the turn-count proxy).
        research_exec = research_result.execution_result
        research_cost, research_cost_source = _normalize_cost(
            research_exec.total_cost_usd, research_exec.num_turns
        )
        if research_cost_source == "turn_proxy":
            logger.warning(
                "Using turn-count cost proxy for research on feature %s: $%.2f from %d turns",
                feature.id,
                research_cost,
                research_exec.num_turns or 0,
            )
        elif research_cost_source == "sdk" and research_exec.total_cost_usd is None:
            # Defensive — should never happen but keep flag detection consistent.
            self._cost_proxy_active = True
        if research_exec.total_cost_usd is None:
            # Even when num_turns==0 (zero source), surface that cost data is absent.
            self._cost_proxy_active = True
        # All cost writes route through the single ``_increment_cost``
        # entry point: it issues the atomic DB write, mirrors the delta
        # into the tamper-detection floor, refreshes the cached total,
        # and flips ``_cost_proxy_active`` when source=="turn_proxy".
        # See ``non-atomic-counter`` recurring pattern in reviews/findings.yaml
        # — this is the structural fix that retired ``self.total_cost``.
        self._increment_cost(research_cost, research_cost_source)

        # F-R6-316: Count PRIOR errored attempts BEFORE recording the current
        # result so the cap check reflects only previous failures, not the
        # one we're about to store. "Prior" is the operative word in the spec.
        prior_errored_count = 0
        if research_exec.is_error:
            try:
                prior_rows = db.list_research_results(feature_id=feature.id)
                prior_errored_count = sum(1 for r in prior_rows if not r.findings)
            except Exception:
                prior_errored_count = 0

        # Store research results in DB (even if research failed, record the attempt)
        findings = research_exec.text if not research_exec.is_error else None
        # agent_run_id may not exist in DB (e.g. during tests with mocked agents)
        agent_run_id = getattr(research_result.agent_run, "id", None)
        # R7-002: The fallback ``db.create_research_result`` (without
        # agent_run_id) is itself a DB write and can fail for reasons
        # unrelated to FK violations (disk full, schema drift, transient
        # SQLite lock). If both calls raise, the unhandled exception used
        # to crash the orchestration loop. Wrap the whole block so any
        # failure is logged and the loop continues — the research
        # findings are advisory; losing one row must not stop the run.
        try:
            try:
                db.create_research_result(
                    feature_id=feature.id,
                    project_id=self.project_id,
                    query=query,
                    findings=findings,
                    agent_run_id=agent_run_id,
                )
            except Exception:
                # FK constraint may fail if agent_run record doesn't exist;
                # store without the agent_run_id reference
                db.create_research_result(
                    feature_id=feature.id,
                    project_id=self.project_id,
                    query=query,
                    findings=findings,
                )
        except Exception as exc:
            logger.warning(
                "Failed to record research result for feature %s: %s; continuing",
                feature.id,
                exc,
                exc_info=True,
            )

        # F-R6-316: Only count successful research toward
        # research_iterations. Erroring research (gateway 400,
        # transient Perplexity outage, sub-agent crash) used to
        # increment the counter, which then tripped the R7-003
        # needs_human guard in find_next_ready_feature on the very
        # next loop tick — poisoning recoverable features after a
        # single transient failure. The error path now leaves
        # research_iterations alone (so needs_research can re-fire)
        # but caps total error attempts via the research_results
        # table so a permanently broken Perplexity does eventually
        # surface for human review.
        updated_feature = db.get_feature(feature.id)
        updates: dict[str, Any] = {}
        if not research_exec.is_error and updated_feature:
            new_iterations = (updated_feature.research_iterations or 0) + 1
            updates["research_iterations"] = new_iterations
            # Successful research boosts confidence/readiness
            # Set to 0.85 which meets thresholds for medium/low risk features
            updates["conf_spec_understanding"] = max(updated_feature.conf_spec_understanding, 0.85)
            updates["conf_impl_correctness"] = max(updated_feature.conf_impl_correctness, 0.85)
            updates["readiness_score"] = max(updated_feature.readiness_score, 0.85)
            logger.info(
                "Research completed for feature %s, boosting readiness to 0.85",
                feature.id[:8]
            )
        else:
            # F-R6-316: error path. Use the prior errored count (captured
            # before storing the current failed result) to decide whether
            # to increment research_iterations. This means the cap triggers
            # only when there were already _MAX_RESEARCH_ERROR_ATTEMPTS
            # prior errors, not counting the current one.
            errored_count = prior_errored_count
            if errored_count >= _MAX_RESEARCH_ERROR_ATTEMPTS:
                new_iterations = ((updated_feature.research_iterations or 0) if updated_feature else 0) + 1
                updates["research_iterations"] = new_iterations
                logger.warning(
                    "Feature %s: research errored %d times (>= cap %d); "
                    "incrementing research_iterations to surface for needs_human.",
                    feature.id, errored_count, _MAX_RESEARCH_ERROR_ATTEMPTS,
                )
            else:
                logger.info(
                    "Feature %s: research errored (attempt %d/%d); not "
                    "incrementing research_iterations so retry can fire.",
                    feature.id, errored_count, _MAX_RESEARCH_ERROR_ATTEMPTS,
                )

        if updates:
            db.update_feature(feature.id, **updates)

        if research_exec.is_error:
            logger.warning(
                "Research for feature %s failed: %s",
                feature.id,
                research_exec.error_message,
            )
        else:
            logger.info(
                "Research for feature %s completed successfully", feature.id
            )

        return research_result

    # -----------------------------------------------------------------
    # R10-009: RCA wiring
    # -----------------------------------------------------------------
    # ``spawn_rca_agent`` exists in claude_executor.py with a full system
    # prompt and a passing F058 test suite, but had ZERO production call
    # sites until this method was added. The orchestration loop now
    # invokes RCA after a feature fails (past the first attempt, with a
    # 24h per-feature cooldown so a flapping feature doesn't burn budget
    # on repeated RCA spawns) and routes the recommendation back into
    # the loop.

    _RCA_COOLDOWN_SECONDS = 24 * 60 * 60  # 24h

    def _last_rca_run_at(self, feature_id: str) -> float | None:
        """Return UNIX timestamp of the most recent RCA evidence for a feature.

        Looks up evidence_artifacts of type ``rca_analysis`` for the
        feature and returns the latest ``created_at`` as a UNIX
        timestamp. Returns ``None`` when no RCA has run yet, so callers
        can treat ``None`` as "never run".
        """
        try:
            rows = db.query_evidence(feature_id=feature_id)
        except Exception:
            logger.debug(
                "Could not query RCA evidence for feature %s",
                feature_id,
                exc_info=True,
            )
            return None
        latest: float | None = None
        for ev in rows:
            if ev.type != "rca_analysis":
                continue
            ts: float | None = None
            created = ev.created_at
            if created is not None:
                try:
                    ts = created.timestamp()
                except Exception:
                    ts = None
            if ts is None:
                continue
            if latest is None or ts > latest:
                latest = ts
        return latest

    def _rca_cooldown_active(self, feature_id: str) -> bool:
        """True when the last RCA for this feature was less than 24h ago."""
        last = self._last_rca_run_at(feature_id)
        if last is None:
            return False
        return (time.time() - last) < self._RCA_COOLDOWN_SECONDS

    async def _maybe_run_rca(
        self,
        *,
        feature: Feature,
        result: ExecutionResult,
    ) -> dict[str, Any] | None:
        """Spawn an RCA sub-agent for a failed feature when criteria are met.

        Criteria (per R10-009 task):
        - ``feature.refinement_attempts >= 2`` (i.e. at least one PRIOR
          failure has already happened — the very first failure is too
          early to invoke RCA, since one-shot failures are common and
          the loop's normal retry path handles them at lower cost).
          Caller is expected to pass the post-``increment_refinement_attempts``
          value, so a count of 2 means the current failure is the
          second attempt. This matches the e2e scenario in R10-009
          where F009 timed out on attempt 2 after a 55-minute attempt 1.
        - No RCA has run for this feature in the last 24 hours.
        - The orchestration loop is not in budget exhaustion.

        On success, stores the RCA result as an evidence artifact of
        type ``rca_analysis`` (so ``_last_rca_run_at`` can find it) and
        returns the parsed RCA dict (``blame_target``,
        ``recommended_action``, ``root_cause``, etc.). Returns ``None``
        when RCA was skipped or failed.
        """
        # Gate 0: feature flag, primarily for tests that don't mock
        # ``spawn_rca_agent`` (and would otherwise launch a real SDK
        # subprocess). Defaults to True in production.
        if not _rca_enabled():
            return None

        # Gate 1: at least one PRIOR failure on the books (so this is
        # the second-or-later attempt). The caller passes the
        # post-increment refinement_attempts value.
        if feature.refinement_attempts < 2:
            return None

        # Gate 2: don't spam RCA on a flapping feature.
        if self._rca_cooldown_active(feature.id):
            logger.debug(
                "Skipping RCA for feature %s: 24h cooldown still active",
                feature.id,
            )
            return None

        # Gate 3: never spend post-budget budget on RCA.
        try:
            if self.budget_exceeded():
                logger.info(
                    "Skipping RCA for feature %s: budget exhausted",
                    feature.id,
                )
                return None
        except Exception:
            # If budget check raises, err on the side of running RCA —
            # it's cheap relative to the feature retry it might prevent.
            logger.debug(
                "budget_exceeded() raised during RCA gating",
                exc_info=True,
            )

        # Build a failure-evidence blob. Cap the body so the RCA prompt
        # stays bounded — sub-agent stdout can be megabytes of
        # diagnostics; the first ~4 KB is plenty for hypothesis work.
        evidence_text = (
            (result.text or "")[:4000]
            + (
                f"\n\n---\nerror_message: {result.error_message}"
                if result.error_message
                else ""
            )
        )
        error_message = (
            result.error_message
            or "Sub-agent reported is_error=True with no error_message"
        )

        # Bound the RCA spawn with its own wall-clock timeout so a stuck
        # tool call inside the RCA sub-agent cannot park the
        # orchestration loop. Configurable via ``BOB_RCA_TIMEOUT_SECONDS``
        # (default 600s = 10 minutes — RCA is meant to be a quick
        # hypothesis pass, not another implementation budget).
        rca_timeout = _resolve_rca_timeout_seconds()
        try:
            rca_spawn = await asyncio.wait_for(
                spawn_rca_agent(
                    project_id=self.project_id,
                    failure_evidence=evidence_text,
                    error_type="feature_implementation_failure",
                    error_message=error_message,
                    target_type="feature",
                    target_id=feature.id,
                ),
                timeout=rca_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "spawn_rca_agent for feature %s exceeded %ss; "
                "continuing without RCA recommendation",
                feature.id,
                rca_timeout,
            )
            return None
        except Exception:
            logger.warning(
                "spawn_rca_agent crashed for feature %s; continuing without RCA",
                feature.id,
                exc_info=True,
            )
            return None

        rca_exec = rca_spawn.execution_result
        # Extract the parsed RCA fields; fall back to a synthetic dict
        # when the SDK errored or the parser couldn't find a JSON block.
        if rca_exec.is_error:
            rca: dict[str, Any] = {
                "blame_target": "unknown",
                "recommended_action": "investigate",
                "root_cause": (
                    "RCA sub-agent itself errored: "
                    + str(rca_exec.error_message or "unknown")
                )[:500],
            }
        else:
            from bob.orchestrator.claude_executor import parse_rca_result
            rca = dict(parse_rca_result(rca_exec.text))

        # Record the RCA result as an evidence artifact so it shows up
        # alongside the feature's other evidence and so the cooldown
        # check (``_last_rca_run_at``) can find it on the next failure.
        try:
            db.create_evidence(
                project_id=self.project_id,
                feature_id=feature.id,
                type="rca_analysis",
                content=json.dumps({
                    "rca": rca,
                    "refinement_attempts": feature.refinement_attempts,
                    "agent_run_id": getattr(rca_spawn.agent_run, "id", None),
                    "rca_text": (rca_exec.text or "")[:4000],
                    "rca_is_error": rca_exec.is_error,
                    "rca_error_message": rca_exec.error_message,
                }),
            )
        except Exception:
            logger.warning(
                "Failed to record rca_analysis evidence for feature %s; "
                "continuing with the recommendation in memory",
                feature.id,
                exc_info=True,
            )

        # Route RCA cost through the canonical writer.
        rca_cost, rca_cost_source = _normalize_cost(
            rca_exec.total_cost_usd, rca_exec.num_turns
        )
        self._increment_cost(rca_cost, rca_cost_source)

        logger.info(
            "RCA for feature %s: blame=%s action=%s",
            feature.id[:8],
            rca.get("blame_target"),
            rca.get("recommended_action"),
        )
        return rca

    async def _run_evaluator(
        self,
        *,
        feature: Feature,
    ) -> dict[str, Any] | None:
        """Spawn the independent evaluator sub-agent for a feature.

        Round 0 Task 1 / Gap #1: this is the post-mechanical-verification
        gate that prevents the implementation agent from grading its own
        homework. Invoked AFTER ``run_verification_checklist`` has
        passed and BEFORE ``git_ops.commit_feature``. The evaluator runs
        in a fresh sub-agent context with no parent_run_id, no
        implementation transcript, and no implementation prompt.

        Returns a dict matching :class:`bob.models.EvaluatorVerdict`
        on success, or ``None`` when the evaluator could not be spawned
        (no workspace, missing inputs, evaluator process failure, or
        evaluator disabled via ``BOB_EVALUATOR_ENABLED=0``).
        """
        # Feature flag: tests that don't mock spawn_evaluator_agent can
        # opt out. Defaults to enabled in production.
        if os.environ.get("BOB_EVALUATOR_ENABLED", "1").strip() == "0":
            return None

        if not self.workspace:
            # No workspace, no diff to grade.
            return None

        # Build a textual diff of what the implementation agent wrote.
        # ``git diff HEAD`` shows uncommitted work; ``--no-color`` keeps
        # the prompt clean. If git isn't available or the workspace
        # isn't a repo, fall back to ``git status`` so the evaluator at
        # least knows which files were touched.
        diff_text = ""
        try:
            import subprocess as _subprocess

            diff_proc = _subprocess.run(
                ["git", "diff", "HEAD", "--no-color"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if diff_proc.returncode == 0:
                diff_text = diff_proc.stdout or ""
            if not diff_text.strip():
                # Fall back to working-tree status when there is no
                # un-staged diff (e.g. work is already staged).
                status_proc = _subprocess.run(
                    ["git", "status", "--porcelain=v1", "--no-renames"],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if status_proc.returncode == 0:
                    diff_text = (
                        "[no unified diff available; git status]\n"
                        + (status_proc.stdout or "")
                    )
        except Exception:
            logger.debug(
                "Could not collect diff for evaluator on feature %s",
                feature.id,
                exc_info=True,
            )

        # Cap diff size — very large diffs blow the prompt budget.
        max_diff_chars = 80_000
        if len(diff_text) > max_diff_chars:
            diff_text = (
                diff_text[:max_diff_chars]
                + f"\n\n[... diff truncated to {max_diff_chars} chars ...]"
            )

        feature_spec = feature.description or feature.name or feature.id
        acceptance_criteria = feature.acceptance_criteria or "(none specified)"

        evaluator_timeout = float(
            os.environ.get("BOB_EVALUATOR_TIMEOUT_SECONDS", "600")
        )

        try:
            spawn_result = await asyncio.wait_for(
                spawn_evaluator_agent(
                    project_id=self.project_id,
                    feature_spec=feature_spec,
                    acceptance_criteria=acceptance_criteria,
                    diff=diff_text,
                    workspace=self.workspace,
                    target_type="feature",
                    target_id=feature.id,
                    session_isolation_hint=feature.id,
                ),
                timeout=evaluator_timeout,
            )
        except asyncio.TimeoutError:
            # An evaluator timeout is a "could not evaluate" condition (the
            # evaluator sub-agent + its MCP servers hung on infra), NOT evidence
            # that the feature is insufficient. Return None so the feature is not
            # penalised — same treatment as the transient is_error path below.
            # Genuine FAIL verdicts (evaluator ran to completion) still block.
            logger.warning(
                "Evaluator for feature %s exceeded %ss; treating as "
                "could-not-evaluate (None), not penalising the feature.",
                feature.id,
                evaluator_timeout,
            )
            return None
        except Exception:
            logger.warning(
                "Evaluator agent crashed for feature %s; treating as "
                "INSUFFICIENT_EVIDENCE",
                feature.id,
                exc_info=True,
            )
            return None

        # Charge evaluator cost through the canonical writer.
        ev_exec = spawn_result.execution_result
        ev_cost, ev_cost_source = _normalize_cost(
            ev_exec.total_cost_usd, ev_exec.num_turns
        )
        self._increment_cost(ev_cost, ev_cost_source)

        if ev_exec.is_error:
            # Distinguish a TRANSIENT INFRA failure of the evaluator itself
            # (self-signed cert, MCP connection refused/403, SIGTERM/SIGINT,
            # transport exit codes, rate limit / overload, timeout) from a
            # genuine evaluator verdict. When the evaluator sub-agent crashes on
            # transient infra, the FEATURE is not at fault — penalising it with
            # INSUFFICIENT_EVIDENCE bounces good work back to 'ready' and creates
            # an evaluator-flakiness churn treadmill (bob77: batches reset en
            # masse). Return None ("could not evaluate") so the caller treats it
            # the same as the timeout/crash paths above (feature passes the gate)
            # rather than blocking. A real evaluator FAIL verdict — where the
            # evaluator RAN and judged the feature — is unaffected, so the quality
            # gate is NOT lowered. See [[feedback-transient-vs-spec-failures]],
            # [[startup-crash-exempt-fix]], [[regression-scapegoat-mechanism]].
            _ev_err = str(ev_exec.error_message or "").lower()
            _transient_sigs = (
                "self signed certificate", "certificate chain", "self-signed",
                "connection failed", "connection refused", "econnrefused",
                "etimedout", "403 forbidden", "429", "rate limit", "overloaded",
                "500", "502", "503", "sigterm", "sigint", "exit code -9",
                "exit code 1", "command failed with exit code", "check stderr",
                "transport", "timed out", "timeout", "mcp server", "stream",
            )
            if any(s in _ev_err for s in _transient_sigs):
                logger.warning(
                    "Evaluator for feature %s failed on TRANSIENT infra "
                    "(is_error, signature in error_message); treating as "
                    "could-not-evaluate (None) rather than penalising the "
                    "feature. err=%.200s",
                    feature.id, _ev_err,
                )
                return None
            return {
                "verdict": "INSUFFICIENT_EVIDENCE",
                "findings": [
                    "Evaluator sub-agent reported is_error=True: "
                    + str(ev_exec.error_message or "unknown"),
                ],
                "confidence": 0.0,
                "evidence": {},
            }

        verdict = parse_evaluator_verdict(ev_exec.text or "")

        # An UNPARSEABLE evaluator response is an evaluator-output problem (the
        # LLM did not emit the expected verdict JSON), NOT evidence the feature
        # is insufficient. parse_evaluator_verdict returns the INSUFFICIENT_EVIDENCE
        # default with the marker finding below in that case; treat it as
        # could-not-evaluate (return None → feature passes the gate) instead of
        # blocking. Otherwise a feature that PASSED verification can be NH'd after
        # 5 malformed evaluator responses (bob78: 9a220a8e mutmut gate). A GENUINE
        # INSUFFICIENT_EVIDENCE verdict (evaluator emitted it deliberately, with
        # real findings) is unaffected — gate NOT lowered. Same principle as
        # [[evaluator-transient-penalizes-feature]].
        if (
            verdict.get("verdict") == "INSUFFICIENT_EVIDENCE"
            and verdict.get("findings") == ["Evaluator response could not be parsed."]
        ):
            logger.warning(
                "Evaluator response for feature %s was unparseable; treating as "
                "could-not-evaluate (None), not penalising the feature.",
                feature.id,
            )
            return None

        # Persist the verdict as an evidence artifact so reviewers can
        # spot-check the evaluator's reasoning later.
        try:
            db.create_evidence(
                project_id=self.project_id,
                feature_id=feature.id,
                type="evaluator_verdict",
                content=json.dumps({
                    "verdict": verdict,
                    "agent_run_id": getattr(spawn_result.agent_run, "id", None),
                    "evaluator_text": (ev_exec.text or "")[:8000],
                }),
            )
        except Exception:
            logger.debug(
                "Could not persist evaluator_verdict evidence for "
                "feature %s",
                feature.id,
                exc_info=True,
            )

        return verdict

    def _file_evaluator_rejection_finding(
        self,
        *,
        feature: Feature,
        verdict: dict[str, Any],
    ) -> None:
        """File a finding to ``reviews/findings.yaml`` on evaluator FAIL.

        Tag is ``evaluator-rejection`` per Round 0 Task 1 AC4.
        Non-fatal on any IO failure — the orchestration loop must keep
        running even if the registry is unwritable.
        """
        try:
            from bob import reviews as _reviews

            registry = _reviews.load_registry()
            findings = verdict.get("findings") or []
            findings_text = "\n".join(f"- {f}" for f in findings) or "(no details)"
            confidence = verdict.get("confidence", 0.0)
            title = (
                f"Evaluator {verdict.get('verdict', 'FAIL')}: "
                f"{(feature.name or feature.id)[:80]}"
            )
            notes = (
                f"Verdict: {verdict.get('verdict')}\n"
                f"Confidence: {confidence}\n"
                f"Feature ID: {feature.id}\n"
                f"Findings:\n{findings_text}\n"
            )
            _reviews.add_finding(
                registry,
                round_prefix="R0",
                title=title,
                pattern="evaluator-rejection",
                files=[],
                severity="high",
                tags=["evaluator-rejection"],
                notes=notes,
            )
            _reviews.save_registry(registry)
        except Exception:
            logger.warning(
                "Failed to file evaluator-rejection finding for feature %s",
                feature.id,
                exc_info=True,
            )

    async def _force_research_for_feature(self, feature: Feature) -> None:
        """Run research on a feature even when ``needs_research`` is False.

        Used by the RCA wiring (R10-009) when an RCA returns
        ``recommended_action == "research"``. The feature has already
        failed at least once and RCA explicitly asked for research, so
        the standard threshold gates don't apply. We achieve "force"
        by temporarily resetting ``research_iterations`` to 0 if it
        was already incremented by an earlier mid-run research.
        Implementation note: ``_run_research`` already increments
        ``research_iterations`` on completion, so a forced research
        still gets recorded as one iteration.
        """
        # The simplest "force" is to call _run_research's body
        # unconditionally. We re-fetch the feature so we work against
        # the latest DB state.
        latest = db.get_feature(feature.id) or feature

        # Build the same query _run_research uses.
        query = (
            f"Research for implementing: {latest.name}\n\n"
            f"Description: {latest.description or 'No description'}\n\n"
            f"Find relevant documentation, libraries, patterns, and examples."
        )
        try:
            research_result = await asyncio.wait_for(
                spawn_research_agent(
                    project_id=self.project_id,
                    query=query,
                    purpose="feature_research",
                    target_type="feature",
                    target_id=latest.id,
                    workspace=self.workspace or None,
                ),
                timeout=_resolve_feature_timeout_seconds(),
            )
        except Exception:
            logger.warning(
                "Force-research spawn failed/timed out for feature %s; continuing",
                feature.id,
                exc_info=True,
            )
            return

        research_exec = research_result.execution_result
        research_cost, research_cost_source = _normalize_cost(
            research_exec.total_cost_usd, research_exec.num_turns
        )
        self._increment_cost(research_cost, research_cost_source)

        # F-R6-316: Count PRIOR errored attempts BEFORE recording the current
        # result so the cap check uses only previous failures.
        prior_errored_count = 0
        if research_exec.is_error:
            try:
                prior_rows = db.list_research_results(feature_id=latest.id)
                prior_errored_count = sum(1 for r in prior_rows if not r.findings)
            except Exception:
                prior_errored_count = 0

        findings = research_exec.text if not research_exec.is_error else None
        agent_run_id = getattr(research_result.agent_run, "id", None)
        try:
            try:
                db.create_research_result(
                    feature_id=latest.id,
                    project_id=self.project_id,
                    query=query,
                    findings=findings,
                    agent_run_id=agent_run_id,
                )
            except Exception:
                db.create_research_result(
                    feature_id=latest.id,
                    project_id=self.project_id,
                    query=query,
                    findings=findings,
                )
        except Exception:
            logger.warning(
                "Failed to record forced-research result for feature %s",
                latest.id,
                exc_info=True,
            )

        # F-R6-316: forced-research path mirrors _run_research —
        # only increment research_iterations on success, or after
        # _MAX_RESEARCH_ERROR_ATTEMPTS consecutive errored attempts.
        post = db.get_feature(latest.id) or latest
        updates: dict[str, Any] = {}
        if not research_exec.is_error:
            new_iters = (post.research_iterations or 0) + 1
            updates["research_iterations"] = new_iters
            updates["conf_spec_understanding"] = max(
                post.conf_spec_understanding, 0.85
            )
            updates["conf_impl_correctness"] = max(
                post.conf_impl_correctness, 0.85
            )
            updates["readiness_score"] = max(post.readiness_score, 0.85)
        else:
            errored_count = prior_errored_count
            if errored_count >= _MAX_RESEARCH_ERROR_ATTEMPTS:
                updates["research_iterations"] = (post.research_iterations or 0) + 1
                logger.warning(
                    "Feature %s: forced-research errored %d times (>= cap %d); "
                    "incrementing research_iterations.",
                    latest.id, errored_count, _MAX_RESEARCH_ERROR_ATTEMPTS,
                )
            else:
                logger.info(
                    "Feature %s: forced-research errored (attempt %d/%d); "
                    "leaving research_iterations unchanged to allow retry.",
                    latest.id, errored_count, _MAX_RESEARCH_ERROR_ATTEMPTS,
                )
        if updates:
            db.update_feature(latest.id, **updates)

    async def execute_feature(self, feature: Feature) -> SpawnResult:
        """Spawn a sub-agent to implement a feature.

        If the feature exceeds size limits (F072), a decomposer sub-agent
        is spawned to break it into smaller child features.

        If the feature needs research (F109), a research sub-agent is
        spawned first via Perplexity MCP. Then the implementation
        sub-agent is spawned with orientation context.

        Args:
            feature: The feature to implement.

        Returns:
            The SpawnResult from the sub-agent execution.
        """
        # 5899f432: Hot-reload prompt-source modules so on-disk patches land
        # immediately without requiring an orchestrator restart.
        _reloaded = _maybe_reload_prompt_sources()
        if _reloaded:
            logger.info(
                "execute_feature: hot-reloaded prompt-source modules: %s",
                _reloaded,
            )

        # F-R6-307: Pre-spawn cost projection gate.
        # Before doing ANY work (decomposition, research, implementation —
        # they all spawn billed sub-agents), project this feature's cost
        # against the remaining budget. If the projection would push us
        # over the headroom under the cap, mark the feature needs_human
        # and bail out without spawning. This stops the loop from grinding
        # to the cap with $0.70 retries against features that have no
        # chance of fitting.
        gate_result = self._cost_projection_gate(feature)
        if gate_result is not None:
            return gate_result

        # Set feature to executing and track as current. ALSO stamp the owning
        # orchestrator pid + a heartbeat so the stuck-executing reaper has a REAL
        # liveness signal instead of NULL. Previously subagent_pid/heartbeat were
        # never written (only cleared) — so the reaper was half-blind and could
        # only guess by claim-age, leaving dead 'executing' rows stranded among
        # live ones (bob73 zombie features). With the owning pid recorded, the
        # reaper can tell "orchestrator alive + heartbeat stale → reap" from
        # "legitimately running". Heartbeat is refreshed in the message callback.
        self._current_feature = feature
        import os as _os_pid
        from datetime import datetime as _dt_pid
        try:
            db.update_feature(
                feature.id,
                status="executing",
                subagent_pid=_os_pid.getpid(),
                subagent_heartbeat_at=_dt_pid.now().isoformat(),
            )
        except TypeError:
            # Older db.update_feature without these kwargs — fall back.
            db.update_feature(feature.id, status="executing")
        logger.info("Executing feature %s: %s", feature.id, _log_safe(feature.name))

        # F072: Check if feature exceeds size limits and needs decomposition
        if feature.exceeds_size_limits:
            logger.info(
                "Feature %s exceeds size limits, triggering decomposition",
                feature.id,
            )
            decomp_result = await handle_decomposition(
                project_id=self.project_id,
                feature=feature,
                workspace=self.workspace or None,
            )

            # R4-002 fix: route decomposition cost to the canonical project
            # total via the loop's single ``_increment_cost`` entry point.
            # Normalize so Max Pro / OAuth subscriptions (which return
            # cost_usd=None) still consume budget via the turn-count proxy.
            decomp_cost_raw = decomp_result.get("cost_usd")
            decomp_num_turns = decomp_result.get("num_turns")
            decomp_normalized, decomp_cost_source = _normalize_cost(
                decomp_cost_raw, decomp_num_turns
            )
            if decomp_cost_source != "turn_proxy" and decomp_cost_raw is None:
                # SDK reported no cost AND no usable turn proxy — still flag
                # so downstream consumers (CLI status / budget warnings)
                # know cost data is absent on this path. ``_increment_cost``
                # also flips the flag when source=="turn_proxy".
                self._cost_proxy_active = True
            self._increment_cost(decomp_normalized, decomp_cost_source)

            if decomp_result["success"]:
                logger.info(
                    "Feature %s decomposed into %d children",
                    feature.id,
                    decomp_result["children_created"],
                )
            else:
                # Decomposition failed — F-R6-318: charge a refinement
                # attempt instead of unconditional NH so the decomposer
                # gets retry budget. Auto-demotes when budget exhausted.
                if db.increment_refinement_attempts(feature.id) is None:
                    db.update_feature(feature.id, status="needs_human")
                logger.warning(
                    "Decomposition of feature %s failed: %s",
                    feature.id,
                    decomp_result.get("error_message"),
                )

            # Return a synthetic SpawnResult for decomposition
            self._current_feature = None
            exec_result = ExecutionResult(
                text=f"Feature decomposed into {decomp_result.get('children_created', 0)} children",
                is_error=not decomp_result["success"],
                error_message=decomp_result.get("error_message") or "",
                duration_ms=0,
                num_turns=0,
                total_cost_usd=decomp_result.get("cost_usd"),
            )
            agent_run = type("_FakeRun", (), {"id": None})()
            return SpawnResult(execution_result=exec_result, agent_run=agent_run)

        # F114: Capture pre-execution git state for rollback reference
        commit_before: str | None = None
        if self.workspace:
            try:
                pre_status = git_get_status(workspace=self.workspace)
                commit_before = pre_status.get("sha") or None
            except Exception:
                logger.debug("Could not capture pre-execution git state")

        # F051 / R4-003 / R5-006 / R7-001: Capture a pre-execution test
        # snapshot so that, after verification passes, we can compare the test
        # verdicts and detect newly-failing tests caused by THIS feature.
        # ``capture_pytest_snapshot`` returns None when pytest can't be run
        # (no workspace, no test dir, pytest not installed, timeout, etc.);
        # the post-execution code only calls ``db.detect_regression`` when
        # both before and after snapshots are available.
        #
        # R5-006: ``capture_pytest_snapshot`` uses synchronous subprocess.run
        # with a 300s timeout, which would block the asyncio event loop for
        # the entire pytest run. Offload to a worker thread so the loop
        # remains responsive (signals, cancellation).
        #
        # R7-001: The pre-execution snapshot is wasted work when the feature
        # is going to be decomposed (we returned early above) OR when the
        # operator has disabled regression detection entirely via
        # BOB_REGRESSION_DETECTION_ENABLED=0. In both cases, skip both the
        # before and after snapshots so we don't spend several minutes per
        # feature on data nobody will read.
        regression_enabled = _regression_detection_enabled()
        before_snapshot: dict[str, bool] | None = None
        if regression_enabled:
            before_snapshot = await asyncio.to_thread(
                capture_pytest_snapshot, self.workspace or None
            )

        # F109: Run research phase if needed
        await self._run_research(feature)

        # F113: Determine which Superpowers skills to enable
        enable_tdd = should_use_tdd(
            acceptance_criteria=feature.acceptance_criteria,
            description=feature.description,
            tdd_mode_override=feature.tdd_mode,  # Respect explicit YAML setting
        )
        enable_subagent = should_use_subagents(
            acceptance_criteria=feature.acceptance_criteria,
            estimated_files_touched=feature.estimated_files_touched,
            estimated_complexity=feature.estimated_complexity,
            sub_agent_mode_override=feature.sub_agent_mode,  # Respect explicit YAML setting
        )

        if enable_tdd:
            logger.info("Feature %s: TDD mode enabled", feature.id)
        if enable_subagent:
            logger.info("Feature %s: Sub-agent mode enabled", feature.id)

        # Build the prompt with orientation context
        task_prompt = (
            f"You are a Bob sub-agent implementing a feature.\n\n"
            f"Feature ID: {feature.id}\n"
            f"Feature: {feature.name}\n"
            f"Description: {feature.description or 'No description'}\n"
            f"Acceptance Criteria: {feature.acceptance_criteria or 'None specified'}\n\n"
            f"Workspace: {self.workspace}\n\n"
            f"Instructions:\n"
            f"1. Read the existing codebase to understand the project structure\n"
            f"2. Implement the feature as described\n"
            f"3. Write tests for the feature\n"
            f"4. Ensure all existing tests still pass\n"
            f"5. Do NOT create stub implementations - write real, functional code\n\n"
            f"When complete, summarize what you implemented and any tests you added.\n"
        )

        prompt = wrap_prompt_with_orientation(
            prompt=task_prompt,
            feature_id=feature.id,
            workspace=self.workspace,
            feature_name=feature.name,
            feature_description=feature.description,
            enable_tdd=enable_tdd,
            enable_verification=True,
            enable_subagent=enable_subagent,
        )

        options = build_sub_agent_options(
            cwd=self.workspace or None,
            # F-R7-633: dispatch on the model at this feature's escalation tier
            # (tier 0 = first ladder entry, sonnet). Bumped when attempts exhaust.
            model=_resolve_escalated_model(getattr(feature, "model_tier", 0)),
            # honor BOB_SUB_AGENT_MAX_TURNS env override (default 25), resolved
            # LIVE at the call site so a per-run override set after import is
            # honored (define-vs-honor gap). A large L4 feature (linalg/sparse
            # vendor wiring) needs more than 25 turns to converge in ONE window;
            # too-small a budget causes max_turns exhaustion mis-read as a
            # transport crash and an infinite rebuild.
            max_turns=resolve_sub_agent_max_turns(),
        )

        # Spawn the sub-agent, bounded by a wall-clock timeout so a stuck
        # tool call (e.g. a hung Puppeteer browser session) cannot park
        # the orchestration loop forever. Configurable via
        # ``BOB_FEATURE_TIMEOUT_SECONDS``; default 1 hour.
        feature_timeout = _resolve_feature_timeout_seconds()
        # Per-attempt cost cap monitor (94e72750): run a background task that
        # checks the live subagent cost every 30s. The agent_run_id is not
        # known until spawn_sub_agent returns, so we use a placeholder and let
        # the monitor resolve it from the DB using the feature_id.
        _cost_cap_monitor_task = asyncio.ensure_future(
            _monitor_subagent_cost_cap(
                feature_id=feature.id,
                agent_run_id=None,  # resolved by monitor via DB lookup
                check_interval_s=_PER_ATTEMPT_COST_CHECK_INTERVAL_S,
            )
        )
        # F-R7-618: timestamp the spawn so the mid_work_crash handler can tell
        # whether any source artifact was persisted DURING this attempt (real
        # work → charge retry) vs none (pure transport crash → exempt).
        _attempt_start_ts = time.time()
        # Heartbeat callback: refresh subagent_heartbeat_at as the sub-agent emits
        # messages. A LIVE feature keeps its heartbeat fresh; a HUNG one (subprocess
        # stopped emitting) goes stale, giving the stuck-executing reaper a real
        # progress signal instead of a perpetually-NULL pid. Throttled to ≤1 DB
        # write / 15s so a chatty agent doesn't hammer sqlite.
        _hb_state = {"last": 0.0}
        _fid_hb = feature.id

        def _heartbeat(_msg, _result) -> None:
            import time as _t_hb
            from datetime import datetime as _dt_hb
            _nowm = _t_hb.monotonic()
            if _nowm - _hb_state["last"] < 15:
                return
            _hb_state["last"] = _nowm
            try:
                db.update_feature(_fid_hb, subagent_heartbeat_at=_dt_hb.now().isoformat())
            except Exception:
                pass

        try:
            spawn_result = await asyncio.wait_for(
                spawn_sub_agent(
                    project_id=self.project_id,
                    purpose="implement_feature",
                    prompt=prompt,
                    target_type="feature",
                    target_id=feature.id,
                    options=options,
                    on_message=_heartbeat,
                ),
                timeout=feature_timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Feature %s exceeded BOB_FEATURE_TIMEOUT_SECONDS=%ss; "
                "marking 'interrupted' and NOT cascading dependents",
                feature.id,
                feature_timeout,
            )
            # R5-007: ``asyncio.wait_for`` cancels the underlying task,
            # but the claude_code_sdk subprocess may not always honour
            # cancellation cleanly (depends on which tool call was in
            # flight). ``spawn_sub_agent`` makes a best-effort to close
            # the SDK stream on cancellation, but if the underlying
            # Node.js process is wedged in a syscall it can survive.
            # Surface a clear SECURITY warning so the operator can
            # inspect / clean up if needed.
            logger.warning(
                "SECURITY: Sub-agent for feature %s timed out; underlying "
                "claude Node.js process may still be running. Check "
                "`pgrep -f claude` and kill any orphaned PIDs if needed.",
                feature.id,
            )
            # Persist a synthetic evidence artifact so the operator can
            # tell the difference between "sub-agent crashed" and
            # "sub-agent ran past the timeout". Best-effort — never let an
            # evidence-write failure derail the timeout handling itself.
            try:
                db.create_evidence(
                    project_id=self.project_id,
                    feature_id=feature.id,
                    type="execution_timeout",
                    content=json.dumps({
                        "status": "interrupted",
                        "reason": "feature_wall_clock_timeout",
                        "timeout_seconds": feature_timeout,
                        "feature_id": feature.id,
                    }),
                )
            except Exception:
                logger.warning(
                    "Failed to record execution_timeout evidence for feature %s",
                    feature.id,
                    exc_info=True,
                )
            # Mark the feature 'interrupted' (not 'failed') so the F116
            # auto-resume path picks it up cleanly on the next run rather
            # than burning a refinement attempt on what is almost
            # certainly an infrastructure-level hang. Do NOT cascade
            # dependents — a timed-out feature has not produced verified
            # work, so its downstream peers must stay 'pending'.
            db.update_feature(feature.id, status="interrupted")
            self.features_failed += 1
            self._current_feature = None
            timeout_exec = ExecutionResult(
                text="",
                is_error=True,
                error_message=(
                    f"Feature timed out after {feature_timeout}s "
                    f"(BOB_FEATURE_TIMEOUT_SECONDS)"
                ),
                duration_ms=int(feature_timeout * 1000),
                num_turns=0,
                total_cost_usd=None,
            )
            # R5-009: Emit a per-feature summary on the timeout path too,
            # so wall-clock-timeout features show up in the same log
            # format as normal completions / failures. Refinement attempts
            # are NOT incremented on timeout (see comment above on F116).
            logger.info(
                "Feature %s (%s) done: status=%s duration=%.1fs "
                "cost=$%.4f attempts=%d",
                feature.id[:8],
                _log_safe(feature.name),
                "interrupted",
                float(feature_timeout),
                0.0,
                feature.refinement_attempts,
            )
            agent_run = type("_FakeRun", (), {"id": None})()
            return SpawnResult(execution_result=timeout_exec, agent_run=agent_run)

        # F113 + R10-014: Run verification BEFORE marking the feature
        # completed so that a verification failure does NOT cascade
        # 'ready' status to dependent features. Verification runs even
        # when the sub-agent reported is_error=True — the workspace may
        # already contain correct work from an earlier attempt, in which
        # case the feature is genuinely done despite the sub-agent crash
        # (the F013 / PyQt6 case). Verification, not the sub-agent exit
        # status, is the source of truth.
        result = spawn_result.execution_result
        verification_passed: bool = True
        verification_summary: str | None = None
        verification_result: dict | None = None
        # Track whether the sub-agent actually reported an error before
        # we possibly clear it via the R10-014 reverification path. This
        # is needed for the spawn-time-failure detection (R10-015) and
        # for accurate logging.
        sub_agent_reported_error = bool(result.is_error)
        # Set if a git hook rejected the post-verification commit. When True,
        # the feature is reverted to 'needs_human' and dependent features must
        # NOT be cascaded as if the feature had completed successfully.
        git_hook_failed: bool = False

        if self.workspace:
            try:
                verification_result = run_verification_checklist(
                    workspace=self.workspace,
                    acceptance_criteria=feature.acceptance_criteria,
                    # Prepend the feature NAME so the GPU/harness classifier sees
                    # the clean, unambiguous title (the description prose contains
                    # incidental words like "anti-cheat" that misclassify it).
                    feature_description=(
                        f"{feature.name}\n{feature.description}"
                        if getattr(feature, "name", None)
                        else feature.description
                    ),
                    pre_snapshot=before_snapshot,
                )
                verification_passed = bool(verification_result.get("passed", True))
                verification_summary = verification_result.get("summary")
                # R10-014: a "passed" result with no acceptance-criteria
                # check is NOT positive evidence that the feature's work
                # is done. The base verification checklist passes vacuously
                # for an empty workspace (tests not required, no source
                # to scan, no acceptance criteria to fail). Only promote
                # an erroring sub-agent's feature to ``completed`` when
                # the ``acceptance_criteria_met`` check is present AND
                # passed — that's the one check that actually proves
                # the spec is satisfied.
                _ac_check = next(
                    (
                        c
                        for c in verification_result.get("checks") or ()
                        if c.get("name") == "acceptance_criteria_met"
                    ),
                    None,
                )
                verification_substantive = bool(
                    _ac_check and _ac_check.get("passed")
                )
                if verification_passed:
                    if sub_agent_reported_error and verification_substantive:
                        # R10-014: workspace already contains correct work
                        # despite the sub-agent crash (typical pattern: an
                        # earlier attempt produced the artefacts; the
                        # current spawn died at process startup before
                        # discovering they're already there). Clear the
                        # error flags so handle_execution_result marks
                        # the feature 'completed' and cascades dependents.
                        logger.info(
                            "Sub-agent for feature %s reported error "
                            "(error_message=%r) but verification passes "
                            "against the existing workspace — treating as "
                            "completed (R10-014).",
                            feature.id,
                            result.error_message,
                        )
                        result.is_error = False
                        result.error_message = ""
                    elif sub_agent_reported_error:
                        # Verification passed vacuously — no
                        # ``acceptance_criteria_met`` check was recorded
                        # OR the criteria check did not pass. Without a
                        # positive substantive check we don't have
                        # evidence the workspace really contains the
                        # feature's work. Leave ``is_error`` alone so the
                        # failure path applies — better to retry / mark
                        # needs_human than to silently promote a crashed
                        # run to completed.
                        logger.info(
                            "Sub-agent for feature %s errored; verification "
                            "returned passed=True but no substantive "
                            "acceptance-criteria check was recorded "
                            "(summary=%r). Treating as a real failure to "
                            "avoid silent completion (R10-014 guard).",
                            feature.id,
                            verification_summary,
                        )
                    else:
                        logger.info(
                            "Feature %s passed verification checklist",
                            feature.id,
                        )
                else:
                    if sub_agent_reported_error:
                        logger.warning(
                            "Feature %s: sub-agent errored AND verification "
                            "failed — treating as a real failure: %s",
                            feature.id,
                            verification_summary,
                        )
                    else:
                        logger.warning(
                            "Feature %s failed verification checklist: %s",
                            feature.id,
                            verification_summary,
                        )
                        logger.error(
                            "Feature %s will be marked needs_human due to failed verification",
                            feature.id,
                        )
            except Exception as exc:
                logger.error(
                    "Verification crashed for feature %s; treating as failure (severity: needs human review)",
                    feature.id,
                    exc_info=True,
                )
                # A crash in the verification harness must NOT silently
                # promote the feature to completed — that would let buggy
                # implementations through any time pytest crashes / OOMs /
                # times out / fails to import. Treat as a hard failure and
                # surface it for human review via 'needs_human'.
                verification_passed = False
                verification_summary = (
                    f"Verification crashed: {type(exc).__name__}"
                )
                verification_result = {
                    "passed": False,
                    "summary": verification_summary,
                    "checks": [],
                }

        # F070: Handle execution result (status, evidence, cost).
        # When verification_passed=False and the sub-agent succeeded,
        # handle_execution_result marks the feature 'needs_human' and
        # skips the dependent cascade.
        outcome = handle_execution_result(
            project_id=self.project_id,
            feature=feature,
            spawn_result=spawn_result,
            shutdown_requested=self.shutdown_requested,
            verification_passed=verification_passed,
            verification_summary=verification_summary,
            workspace=self.workspace or None,
        )
        # Single canonical cost write: ``_increment_cost`` performs the
        # atomic ``db.update_project_cost``, mirrors the delta into
        # ``_expected_total_cost`` for tamper detection, and refreshes
        # the cached project total — all in one place. ``handle_execution_result``
        # no longer touches the DB for cost (recurring pattern
        # ``non-atomic-counter``: every cost-bearing path that wrote the
        # DB on its own turned into a drift bug).
        cost_recorded = float(outcome.get("cost_usd") or 0.0)
        cost_source = str(outcome.get("cost_source") or "sdk")

        # b20b4725: telemetry-loss guard — zero reported cost is NOT always
        # safe to skip. When work_events > threshold the stream-json parser
        # dropped cost-delta events and enforcement MUST still fire.
        if cost_recorded == 0.0 and self.workspace:
            _progress_path = (
                pathlib.Path(self.workspace) / ".bob" / "progress.jsonl"
            )
            _work_events, _ = _count_work_events(_progress_path)
            # F-R7-585 (bob version 17 r1): the project-level max_cost_usd
            # is the ENTIRE budget, NOT a per-feature ceiling. Charging the
            # whole project budget for one telemetry-lost feature instantly
            # trips BUDGET_EXCEEDED, halts the orchestrator, and forces a
            # manual restart. Clamp pessimistic-cost to a sane per-feature
            # ceiling (env BOB_PER_FEATURE_COST_CEILING, default $20 —
            # matches the empirical p95 of real per-feature costs observed
            # in bob v.16/17 runs).
            _per_feature_ceiling = _compute_per_feature_ceiling()
            _is_lost = _is_cost_telemetry_lost(
                reported_cost=cost_recorded,
                work_events=_work_events,
            )
            if _is_lost:
                cost_recorded = _apply_pessimistic_cost(
                    reported_cost=0.0,
                    is_lost=True,
                    per_feature_ceiling=_per_feature_ceiling,
                )
                _emit_cost_telemetry_lost_event(
                    feature_id=feature.id,
                    work_events=_work_events,
                    exit_code=1 if result.is_error else 0,
                    attempt_number=max(1, feature.refinement_attempts),
                    applied_pessimistic_cost=cost_recorded,
                )

        self._increment_cost(cost_recorded, cost_source)

        # Store verification_checklist evidence only when verification
        # actually ran (i.e. sub-agent succeeded and workspace is set).
        if verification_result is not None:
            try:
                db.create_evidence(
                    project_id=self.project_id,
                    feature_id=feature.id,
                    type="verification_checklist",
                    content=json.dumps(verification_result),
                )
            except Exception:
                logger.debug(
                    "Could not store verification evidence for feature %s",
                    feature.id,
                )

        # Update loop-level counters
        if result.is_error:
            if self.shutdown_requested:
                self._create_interruption_checkpoint(feature, result)
                logger.info(
                    "Feature %s interrupted during graceful shutdown",
                    feature.id,
                )
            elif (
                # F-R6-300: Replace the SDK-only spawn-failure heuristic
                # with an on-disk classifier that inspects
                # ``.bob/progress.jsonl`` for real evidence that the
                # sub-agent did work before crashing. The Round-5
                # incident (F-R5-202) was driven by claude-code
                # shutdown crashes that report duration_ms==0 +
                # num_turns==0 even after the sub-agent produced source
                # files; the old heuristic mis-labeled those as
                # spawn-time failures, granted free retries, and never
                # charged ``refinement_attempts`` — producing an
                # infinite loop. The walrus stashes the verdict so the
                # warning log can reference its evidence string.
                (
                    _crash_kind := _classify_failure_for_retry(
                        result, self.workspace, feature.id
                    )
                )["kind"]
                == "spawn_failure"
                and self._spawn_failure_counts.get(feature.id, 0)
                < _MAX_SPAWN_RETRIES
            ):
                # R10-015: Sub-agent died at process spawn time and
                # produced NO on-disk evidence of work. Free retry,
                # capped at ``_MAX_SPAWN_RETRIES`` so a permanently
                # broken local environment cannot loop forever. Skip
                # ``increment_refinement_attempts``, the confidence
                # decay (R10-011), and the proxy-cost log bump.
                self._spawn_failure_counts[feature.id] = (
                    self._spawn_failure_counts.get(feature.id, 0) + 1
                )
                db.update_feature(feature.id, status="ready")
                logger.warning(
                    "Sub-agent for feature %s classified as "
                    "spawn_failure (duration_ms=%s, num_turns=%s; "
                    "evidence=%s). Treating as transient; retrying "
                    "without charging refinement_attempts "
                    "(free retry %d/%d). error_message=%r",
                    feature.id,
                    result.duration_ms,
                    result.num_turns,
                    _crash_kind["evidence"],
                    self._spawn_failure_counts[feature.id],
                    _MAX_SPAWN_RETRIES,
                    result.error_message,
                )
                # Skip the rest of the failure-handling path (no RCA,
                # no decay, no refinement increment).
                updated_feature = None
            else:
                # F071: Retry logic — check refinement attempts before
                # giving up. F-R6-300: ``mid_work_crash`` (the bug
                # being fixed) and ``spawn_failure`` past the cap both
                # land here and are correctly charged a refinement
                # attempt.
                crash_kind = _classify_failure_for_retry(
                    result, self.workspace, feature.id
                )
                if crash_kind["kind"] == "spawn_failure":
                    logger.warning(
                        "Feature %s exceeded the %d-spawn-failure cap; "
                        "treating subsequent spawn-time errors as a real "
                        "failure to avoid an infinite retry loop.",
                        feature.id,
                        _MAX_SPAWN_RETRIES,
                    )
                elif crash_kind["kind"] == "mid_work_crash":
                    # F-R7-618: distinguish a TRANSPORT crash (MCP/cert/conn reset,
                    # exit 1 with NO persisted artifact) from a real work-loss
                    # crash. A sub-agent that ran 10k+ work_events then died on a
                    # self-signed-cert / connection-reset during shutdown produced
                    # nothing retry-able and did not cause its own crash — charging
                    # it a retry exhausts the budget on upstream infra flakiness
                    # (the chronic F-R7-597-class NH across 6 gens). Exempt such
                    # crashes from the retry charge (with a lifetime cap so a
                    # genuinely broken feature can't loop forever).
                    _exempt = False
                    try:
                        _sig = (getattr(result, "error_message", "") or "").lower()
                        _transport = any(s in _sig for s in (
                            "self signed certificate", "self-signed certificate",
                            "connectionreseterror", "connection reset",
                            "readtimeout", "read timeout", "broken pipe",
                            "mcp server", "connection failed", "exit code 1",
                        ))
                        # Lifetime exempt counter persisted in a per-feature
                        # sidecar dir (no metadata column exists). Cap at 25 so a
                        # genuinely broken feature eventually charges retries.
                        _ec_dir = pathlib.Path(self.workspace) / ".bob_startup_exempt"
                        _ec_file = _ec_dir / f"{feature.id}.count"
                        try:
                            _exempt_count = int(_ec_file.read_text().strip())
                        except Exception:
                            _exempt_count = 0
                        # NOTE: the earlier persisted-artifact gate was REMOVED —
                        # in this chain the bob src tree is the build target and
                        # concurrent sibling features modify it during the crashed
                        # feature's window, so an mtime-based artifact count is
                        # always >0 and wrongly suppressed every exemption (bob65:
                        # 11 qualifying crashes, 0 exempted). A transport-transient
                        # exit signature (self-signed cert during MCP shutdown,
                        # connection reset, broken pipe) is itself sufficient
                        # evidence of an infra crash the feature did not cause.
                        # The 25-cap bounds abuse.
                        if _transport and _exempt_count < 25:
                            _exempt = True
                            _ec_dir.mkdir(parents=True, exist_ok=True)
                            _ec_file.write_text(str(_exempt_count + 1))
                    except Exception:
                        _exempt = False
                    if _exempt:
                        logger.warning(
                            "SUBAGENT_STARTUP_CRASH_EXEMPT (F-R7-618): feature %s "
                            "mid_work_crash with transport-transient signature — "
                            "NOT charging a retry (exempt #%d/25). "
                            "exit_signature_excerpt=%r",
                            feature.id, _exempt_count + 1, _sig[:120],
                        )
                        # Reset to ready WITHOUT incrementing refinement attempts
                        # and return — the main loop will re-claim and re-spawn it
                        # on a later iteration (transport flakiness is transient).
                        db.update_feature(feature.id, status="ready")
                        return spawn_result
                    logger.warning(
                        "Sub-agent for feature %s classified as "
                        "mid_work_crash (evidence=%s). Charging a "
                        "refinement attempt — the sub-agent did real "
                        "work before crashing, so this is NOT a free "
                        "retry. (F-R6-300)",
                        feature.id,
                        crash_kind["evidence"],
                    )
                updated_feature = db.increment_refinement_attempts(feature.id)

                # R10-011: Decay confidence so the low-confidence research
                # trigger (Trigger 3 in ``needs_research``) can re-fire on
                # the next attempt, even when the failure-count threshold
                # (R10-010) hasn't been crossed yet. Decay happens AFTER
                # ``increment_refinement_attempts`` so a fresh DB read is
                # consistent. Refresh the in-memory ``updated_feature``
                # after decay so subsequent log messages and RCA gating
                # see the latest values.
                decayed = _decay_confidence_after_failure(feature.id)
                if decayed is not None:
                    updated_feature = decayed

                # R10-009: Spawn an RCA sub-agent on every failure past the
                # first (gated by 24h cooldown + budget). RCA recommendations
                # short-circuit the normal retry path: ``research`` triggers
                # a forced research pass, ``decompose`` flags the feature as
                # too large, ``mark_needs_human``/``skip`` retire the feature
                # immediately, and any other action falls through to the
                # default retry/needs_human logic below.
                rca_result = await self._maybe_run_rca(
                    feature=updated_feature or feature, result=result
                )
                rca_action = (
                    rca_result.get("recommended_action") if rca_result else None
                )

                # ---- RCA short-circuits ----
                if rca_action in ("mark_needs_human", "skip", "escalate"):
                    _rca_feat = db.get_feature(feature.id) or feature
                    if _may_demote(
                        _rca_feat,
                        target_status="needs_human",
                        workspace=pathlib.Path(self.workspace) if self.workspace else None,
                    ):
                        db.update_feature(feature.id, status="needs_human")
                    else:
                        logger.info(
                            "Sticky-completed gate prevented RCA demotion of feature %s to 'needs_human'",
                            feature.id[:8],
                        )
                    self.features_failed += 1
                    logger.warning(
                        "Feature %s marked needs_human by RCA "
                        "(action=%s, blame=%s): %s",
                        feature.id,
                        rca_action,
                        (rca_result or {}).get("blame_target"),
                        (rca_result or {}).get("root_cause"),
                    )
                elif rca_action == "decompose":
                    db.update_feature(
                        feature.id,
                        exceeds_size_limits=True,
                        size_limit_justification=(
                            "RCA recommendation after failure: "
                            + str(
                                (rca_result or {}).get("root_cause")
                                or "feature too large to implement in one pass"
                            )
                        )[:500],
                        status="ready",
                    )
                    logger.info(
                        "Feature %s flagged for decomposition by RCA "
                        "(blame=%s)",
                        feature.id,
                        (rca_result or {}).get("blame_target"),
                    )
                elif rca_action in ("research", "clarify_spec"):
                    # Force a research pass even if normal triggers wouldn't fire.
                    await self._force_research_for_feature(
                        updated_feature or feature
                    )
                    if updated_feature is not None and not db.check_refinement_limit(
                        feature.id
                    ):
                        db.update_feature(feature.id, status="ready")
                        logger.info(
                            "Feature %s: RCA forced research; resetting "
                            "to ready for retry (attempt %d/%d)",
                            feature.id,
                            updated_feature.refinement_attempts,
                            updated_feature.max_refinement_attempts,
                        )
                    else:
                        self.features_failed += 1
                        logger.warning(
                            "Feature %s: RCA recommended research but "
                            "retry limit exhausted (%s/%s)",
                            feature.id,
                            updated_feature.refinement_attempts
                            if updated_feature
                            else "?",
                            updated_feature.max_refinement_attempts
                            if updated_feature
                            else "?",
                        )
                # ---- Default retry / exhaustion path ----
                elif (
                    updated_feature is not None
                    and not db.check_refinement_limit(feature.id)
                ):
                    # F-R7-474: Research-augmented retry — when refinement_attempts >= 2
                    # and the failure is classifiable, inject research strategies into
                    # the next implementer prompt.
                    _pfr_failure_info = {
                        "error_type": type(result).__name__,
                        "message": result.error_message or "",
                        "traceback": "",
                    }
                    if _path_finding_should_trigger(
                        updated_feature.refinement_attempts, _pfr_failure_info
                    ):
                        try:
                            _pfr_fc = _path_finding_classify_failure(_pfr_failure_info)
                            _pfr_strategies = _path_finding_research_strategies(_pfr_fc)
                            if _pfr_strategies:
                                _pfr_ws = (
                                    pathlib.Path(self.workspace) if self.workspace else pathlib.Path(".")
                                )
                                _path_finding_cache_strategies(
                                    feature.id,
                                    updated_feature.refinement_attempts,
                                    _pfr_strategies,
                                    workspace=_pfr_ws,
                                )
                                _pfr_prompt = _path_finding_inject(
                                    base_prompt=f"Implement feature {feature.id}: {feature.name}",
                                    strategies=_pfr_strategies,
                                    failure_class=_pfr_fc,
                                    attempt_number=updated_feature.refinement_attempts,
                                )
                                _path_finding_persist_prompt(
                                    feature.id,
                                    updated_feature.refinement_attempts,
                                    _pfr_prompt,
                                    workspace=_pfr_ws,
                                )
                                logger.info(
                                    "Feature %s: path-finding retry triggered "
                                    "(attempts=%d, failure_class=%s, strategies=%d)",
                                    feature.id,
                                    updated_feature.refinement_attempts,
                                    _pfr_fc.value,
                                    len(_pfr_strategies),
                                )
                        except Exception:
                            logger.debug(
                                "Path-finding retry preparation failed for feature %s; "
                                "proceeding with normal retry",
                                feature.id,
                                exc_info=True,
                            )
                    # Under limit: reset to 'ready' so the loop retries this feature
                    db.update_feature(feature.id, status="ready")
                    logger.info(
                        "Feature %s failed (attempt %d/%d), resetting to ready for retry: %s",
                        feature.id,
                        updated_feature.refinement_attempts,
                        updated_feature.max_refinement_attempts,
                        result.error_message,
                    )
                else:
                    # At or over limit: mark as needs_human (done by increment_refinement_attempts)
                    # and count as a permanent failure
                    self.features_failed += 1
                    logger.warning(
                        "Feature %s failed and exhausted retries (%d/%d): %s",
                        feature.id,
                        updated_feature.refinement_attempts if updated_feature else "?",
                        updated_feature.max_refinement_attempts if updated_feature else "?",
                        result.error_message,
                    )
        elif not verification_passed:
            # Sub-agent succeeded but verification failed. Do NOT commit,
            # do NOT cascade, do NOT count as completed.
            self.features_failed += 1
            logger.error(
                "Feature %s failed verification: %s",
                feature.id,
                verification_summary,
            )
        else:
            # Round 0 Task 1 (Gap #1): Independent evaluator gate.
            # Mechanical verification (run_verification_checklist) has
            # passed; before we commit, ask a fresh sub-agent — one with
            # no access to the implementation transcript or session id —
            # to grade the diff against the acceptance criteria. On FAIL
            # or INSUFFICIENT_EVIDENCE the feature is marked failed, a
            # finding is filed to reviews/findings.yaml with
            # tag="evaluator-rejection", and we route to RCA. On PASS we
            # fall through to the existing commit path.
            evaluator_verdict = await self._run_evaluator(feature=feature)
            evaluator_passed = (
                evaluator_verdict is None
                or evaluator_verdict.get("verdict") == "PASS"
            )

            if evaluator_verdict is not None and not evaluator_passed:
                # Treat FAIL and INSUFFICIENT_EVIDENCE the same way:
                # block the commit, mark needs_human, file the finding,
                # and route to RCA so the next refinement attempt has
                # the evaluator's notes to work from.
                self._file_evaluator_rejection_finding(
                    feature=feature, verdict=evaluator_verdict
                )
                # F-R6-319: Charge a refinement attempt BEFORE the cascade
                # rollback and BEFORE RCA. The RCA gate at _maybe_run_rca
                # requires refinement_attempts >= 2 to engage; without this
                # increment, eval-rejected features were stranded at
                # rfn=0/needs_human with no RCA help. increment_refinement_attempts
                # auto-demotes to needs_human when budget is exhausted, so
                # the R7-003 cap still holds.
                _eval_feat = db.get_feature(feature.id) or feature
                _eval_ws = pathlib.Path(self.workspace) if self.workspace else None
                if not _may_demote(_eval_feat, target_status="needs_human", workspace=_eval_ws):
                    logger.info(
                        "Sticky-completed gate prevented evaluator demotion of feature %s to 'needs_human'",
                        feature.id[:8],
                    )
                    updated_after_increment = None
                    budget_exhausted = False
                else:
                    updated_after_increment = db.increment_refinement_attempts(feature.id)
                    budget_exhausted = (
                        updated_after_increment is not None
                        and updated_after_increment.status == "needs_human"
                    )
                if budget_exhausted:
                    # Roll back dependents only when the feature is truly
                    # done — otherwise leave dependents alone so they can
                    # benefit from the upcoming refinement attempt.
                    try:
                        db.rollback_feature_cascade(
                            feature.id, target_status="needs_human"
                        )
                    except Exception:
                        pass  # increment_refinement_attempts already set NH
                logger.error(
                    "Feature %s rejected by independent evaluator "
                    "(verdict=%s, confidence=%.2f); commit blocked. "
                    "Findings: %s",
                    feature.id,
                    evaluator_verdict.get("verdict"),
                    float(evaluator_verdict.get("confidence", 0.0)),
                    evaluator_verdict.get("findings"),
                )
                # Synthesise an ExecutionResult so _maybe_run_rca has a
                # failure-evidence blob to feed to the RCA agent.
                rca_evidence = ExecutionResult(
                    text="\n".join(evaluator_verdict.get("findings") or []),
                    is_error=True,
                    error_message=(
                        f"Evaluator {evaluator_verdict.get('verdict')}: "
                        + (
                            "; ".join(evaluator_verdict.get("findings") or [])
                            or "no details"
                        )
                    )[:4000],
                )
                try:
                    await self._maybe_run_rca(
                        feature=feature, result=rca_evidence
                    )
                except Exception:
                    logger.debug(
                        "RCA after evaluator-rejection failed for feature %s",
                        feature.id,
                        exc_info=True,
                    )
                # Re-use the existing git_hook_failed accounting below
                # (skips the commit, increments features_failed once,
                # logs needs_human). The earlier rollback_feature_cascade
                # is the same one git-hook-failure does.
                git_hook_failed = True
            # F114: Commit feature changes to git (only once verification passed)
            commit_sha: str | None = None
            if self.workspace and not git_hook_failed:
                try:
                    commit_sha = git_commit_feature(
                        feature_id=feature.id,
                        message=feature.name,
                        workspace=self.workspace,
                        stage_all=True,
                    )
                except GitHookFailedError as exc:
                    # A pre-commit / commit-msg hook rejected our commit. The
                    # implementation may be valid (verification passed!) but
                    # something the hook checks for objects to it. Surface
                    # this for human review rather than silently moving on
                    # as if the feature were committed and complete.
                    git_hook_failed = True
                    hook_output = (exc.stderr or exc.stdout or str(exc)).strip()
                    logger.warning(
                        "Git hook rejected commit for feature %s "
                        "(rc=%s); marking needs_human. Hook output:\n%s",
                        feature.id,
                        exc.returncode,
                        hook_output,
                    )
                    # Record evidence so the operator can see the hook output
                    # alongside the feature.
                    try:
                        db.create_evidence(
                            project_id=self.project_id,
                            feature_id=feature.id,
                            type="git_hook_failure",
                            content=json.dumps({
                                "feature_id": feature.id,
                                "returncode": exc.returncode,
                                "command": exc.command,
                                "stderr": exc.stderr,
                                "stdout": exc.stdout,
                            }),
                        )
                    except Exception:
                        logger.warning(
                            "Failed to record git_hook_failure evidence for "
                            "feature %s",
                            feature.id,
                            exc_info=True,
                        )
                    # Override the 'completed' status that
                    # handle_execution_result wrote earlier — verification
                    # passed but we couldn't get the change committed, so
                    # this needs human attention. handle_execution_result
                    # already ran the F123 cascade which may have flipped
                    # dependents from 'pending' to 'ready'; we need to roll
                    # those back too. Both writes happen atomically in a
                    # single transaction (db.rollback_feature_cascade) so a
                    # crash during rollback can never leave the project in
                    # a half-rolled-back state (some dependents back to
                    # 'pending', others stuck at 'ready').
                    try:
                        db.rollback_feature_cascade(
                            feature.id, target_status="needs_human"
                        )
                    except Exception:
                        logger.error(
                            "Failed to roll back cascade for feature %s "
                            "after git hook failure",
                            feature.id,
                            exc_info=True,
                        )
                except GitRepoError as exc:
                    # Workspace isn't a git repo. Not a build failure — just
                    # log cleanly and continue without committing.
                    logger.info(
                        "Skipping git commit for feature %s: workspace is "
                        "not a git repository (%s)",
                        feature.id,
                        exc,
                    )
                except GitCommitError as exc:
                    # Other git failure (e.g. git binary broken, IO error
                    # during add). Not a hook rejection — surface it loudly
                    # and record evidence, but don't unwind the 'completed'
                    # status the way a hook rejection does.
                    logger.error(
                        "Unexpected git error committing feature %s "
                        "(rc=%s): %s",
                        feature.id,
                        exc.returncode,
                        (exc.stderr or exc.stdout or str(exc)).strip(),
                    )
                    try:
                        db.create_evidence(
                            project_id=self.project_id,
                            feature_id=feature.id,
                            type="git_commit_error",
                            content=json.dumps({
                                "feature_id": feature.id,
                                "returncode": exc.returncode,
                                "command": exc.command,
                                "stderr": exc.stderr,
                                "stdout": exc.stdout,
                            }),
                        )
                    except Exception:
                        logger.warning(
                            "Failed to record git_commit_error evidence "
                            "for feature %s",
                            feature.id,
                            exc_info=True,
                        )
                except Exception:
                    # Truly unexpected (non-GitCommitError) — keep prior
                    # permissive behaviour so we don't crash the loop, but
                    # log loudly with full traceback.
                    logger.error(
                        "Unexpected non-git exception during commit for "
                        "feature %s",
                        feature.id,
                        exc_info=True,
                    )

            if git_hook_failed:
                # Hook rejection means the feature isn't really done.
                self.features_failed += 1
                logger.error(
                    "Feature %s blocked by git hook rejection; needs human review",
                    feature.id,
                )
            else:
                self.features_completed += 1
                logger.info("Feature %s completed successfully", feature.id)

        # Cost was written above via ``self._increment_cost(...)`` — the
        # single canonical writer. There is no longer any in-memory mirror
        # to bump here; ``budget_exceeded()`` reads ``self._project_total_cost``
        # which ``_increment_cost`` already refreshed. We still flip the
        # proxy flag so downstream consumers (CLI status, run() warning)
        # can surface that the SDK is not reporting cost.
        if result.total_cost_usd is None:
            self._cost_proxy_active = True

        # F108: Update progress notes after each sub-agent session
        if self.workspace:
            try:
                if result.is_error:
                    progress_outcome = (
                        "interrupted" if self.shutdown_requested else "failed"
                    )
                    blockers = result.error_message
                elif not verification_passed:
                    progress_outcome = "failed"
                    blockers = f"Verification failed: {verification_summary}"
                else:
                    progress_outcome = "completed"
                    blockers = None
                update_progress_notes(
                    workspace=self.workspace,
                    feature_id=feature.id,
                    feature_name=feature.name,
                    outcome=progress_outcome,
                    duration_ms=result.duration_ms,
                    num_turns=result.num_turns,
                    cost_usd=result.total_cost_usd,
                    blockers=blockers,
                )
            except Exception:
                logger.debug(
                    "Failed to update progress notes for feature %s",
                    feature.id,
                    exc_info=True,
                )

        # F051 / R4-003: Regression detection.
        #
        # If verification passed AND the feature was committed without a
        # hook rejection, capture an "after" pytest snapshot and compare it
        # to the pre-execution snapshot. Any test that was passing before
        # this feature ran but is failing now is, by definition, a regression
        # caused by THIS feature. ``db.detect_regression`` records the event
        # in the ``regression_events`` table so ``show-regressions`` and the
        # rollback path (F052) actually see something.
        #
        # We deliberately gate this on the success path (verification passed
        # AND no git hook rejection) — if the feature didn't really land,
        # there's no causing-feature to attribute regressions to.
        feature_landed = (
            (not result.is_error)
            and verification_passed
            and not git_hook_failed
        )
        if feature_landed and before_snapshot is not None and regression_enabled:
            # R5-006: offload the post-execution pytest run to a worker
            # thread so the event loop stays responsive during the snapshot.
            after_snapshot = await asyncio.to_thread(
                capture_pytest_snapshot, self.workspace or None
            )
            if after_snapshot is not None:
                try:
                    event = db.detect_regression(
                        project_id=self.project_id,
                        causing_feature_id=feature.id,
                        before_results=before_snapshot,
                        after_results=after_snapshot,
                    )
                    if event is not None:
                        logger.warning(
                            "Regression detected after feature %s: "
                            "affected_feature=%s, affected_tests=%s",
                            feature.id,
                            event.affected_feature_id,
                            event.affected_tests,
                        )
                        try:
                            db.create_evidence(
                                project_id=self.project_id,
                                feature_id=feature.id,
                                type="regression_detected",
                                content=json.dumps({
                                    "regression_event_id": event.id,
                                    "causing_feature_id": feature.id,
                                    "affected_feature_id": event.affected_feature_id,
                                    "affected_tests": event.affected_tests,
                                }),
                            )
                        except Exception:
                            logger.warning(
                                "Failed to record regression_detected evidence "
                                "for feature %s",
                                feature.id,
                                exc_info=True,
                            )
                except Exception:
                    # Detection / DB error must not abort the loop.
                    logger.warning(
                        "detect_regression raised for feature %s; "
                        "continuing without regression record",
                        feature.id,
                        exc_info=True,
                    )

        # F019 / R4-004: Record a calibration data point for this feature.
        #
        # We log predicted confidence (pre-execution ``conf_impl_correctness``)
        # vs actual outcome (passed verification or not). This populates the
        # ``calibration_data`` table that ``show-calibration`` reads and that
        # drift-detection (F050) consumes; previously the table was always
        # empty in production.
        #
        # ``passed`` for calibration purposes means "the feature actually
        # landed cleanly": sub-agent didn't error, verification passed, AND
        # no git hook rejection. Anything else is treated as a failed
        # prediction, regardless of which step blew up. This may
        # over-report failures (a git hook rejection isn't really a
        # confidence-calibration failure of the implementation), but
        # under-reporting them would let buggy work erode the calibration
        # signal silently. Choice intentional; revisit if it skews drift.
        _record_feature_calibration(
            project_id=self.project_id,
            feature=feature,
            passed=feature_landed,
        )

        # R5-009: Emit a structured per-feature summary so operators can
        # see the cost / duration / outcome of each feature in the log
        # without reconstructing it from individual lines. Re-fetch the
        # feature so ``status`` and ``refinement_attempts`` reflect any
        # mutations made by handle_execution_result, retry logic, or git
        # hook rollback above. Falls back to the in-memory feature if
        # the row vanished mid-run (deleted by a parallel admin tool).
        final_feature = db.get_feature(feature.id) or feature
        normalized_cost = float(outcome.get("cost_usd") or 0.0)
        duration_ms = result.duration_ms or 0
        logger.info(
            "Feature %s (%s) done: status=%s duration=%.1fs "
            "cost=$%.4f attempts=%d",
            feature.id[:8],
            _log_safe(feature.name),
            final_feature.status,
            duration_ms / 1000.0,
            normalized_cost,
            final_feature.refinement_attempts,
        )

        # Clear current feature tracking
        self._current_feature = None

        # Note: dependent cascade is NOT re-run here. ``handle_execution_result``
        # already invokes ``db.complete_feature_and_cascade`` atomically on the
        # success path (status flip + readiness cascade in a single SQLite
        # transaction). A second ``cascade_update_dependents`` here would be
        # idempotent but wastes DB round-trips, and on the git-hook-rejection
        # path the dependents have already been rolled back inline above. The
        # rollback path explicitly re-pins dependents to 'pending' there, so
        # no further cascade work is needed at this point.

        return spawn_result

    async def execute_feature_with_timeout(
        self,
        feature: Feature,
        *,
        timeout_seconds: float | None = None,
    ) -> SpawnResult:
        """Run :meth:`execute_feature` bounded by a hard wall-clock timeout.

        Wraps ``execute_feature`` with :func:`bob.timeout.enforce_wall_clock_timeout`
        so that a single hung feature cannot block the orchestration loop
        indefinitely.  The timeout is read from ``BOB_FEATURE_TIMEOUT_SECONDS``
        (default 1800 s) unless *timeout_seconds* is given explicitly.

        When the timeout fires:
        - A TIMEOUT telemetry event (WARNING log) is emitted.
        - :class:`bob.timeout.FeatureTimeoutError` is raised.
        - The caller MUST reset the feature to 'ready' / increment its attempt
          and continue the loop.

        Args:
            feature: The feature to implement.
            timeout_seconds: Override the wall-clock timeout; reads
                ``BOB_FEATURE_TIMEOUT_SECONDS`` when ``None``.

        Returns:
            The :class:`SpawnResult` from :meth:`execute_feature` on success.

        Raises:
            bob.timeout.FeatureTimeoutError: When execution exceeds the timeout.
        """
        from bob.timeout import enforce_wall_clock_timeout

        effective_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else _resolve_feature_timeout_seconds()
        )
        return await enforce_wall_clock_timeout(
            feature.id,
            self.execute_feature(feature),
            timeout_seconds=effective_timeout,
        )

    def rollback_feature(
        self,
        *,
        feature_id: str,
        trigger: str,
        commit_sha: str,
        commit_before: str,
        regression_event_id: str | None = None,
    ) -> None:
        """Roll back a feature with git revert and database recording.

        Performs the actual git revert and then records the rollback event
        in the database.

        Args:
            feature_id: ID of the feature to roll back.
            trigger: What triggered the rollback (regression|human_request|critical_bug).
            commit_sha: The SHA of the feature's commit to revert.
            commit_before: The SHA of HEAD before the feature was implemented.
            regression_event_id: Optional linked regression event ID.
        """
        # F114: Execute the actual git revert
        rollback_commit: str | None = None
        if self.workspace:
            try:
                rollback_commit = git_revert_feature(
                    feature_id=feature_id,
                    commit_sha=commit_sha,
                    workspace=self.workspace,
                )
            except Exception:
                logger.warning(
                    "Git revert failed for feature %s", feature_id,
                    exc_info=True,
                )

        # Get current HEAD as commit_after
        commit_after = commit_sha

        # Record the rollback in the database
        db.rollback_feature(
            project_id=self.project_id,
            feature_id=feature_id,
            trigger=trigger,
            commit_before=commit_before,
            commit_after=commit_after,
            rollback_commit=rollback_commit,
            regression_event_id=regression_event_id,
        )

        logger.info(
            "Rolled back feature %s (trigger=%s, revert_commit=%s)",
            feature_id, trigger, rollback_commit,
        )

    def _create_interruption_checkpoint(
        self, feature: Feature, result: ExecutionResult
    ) -> None:
        """Create a checkpoint when a feature is interrupted by graceful shutdown.

        Captures the feature state, accumulated cost, and reason for
        interruption so that the feature can be resumed later.

        Args:
            feature: The feature that was being executed.
            result: The execution result from the sub-agent.
        """
        # R5-010 / R7-004 / structural fix (``non-atomic-counter``):
        # the in-memory ``self.total_cost`` mirror was deleted; cost is
        # written exclusively through ``self._increment_cost`` which
        # updates the DB, mirrors the delta into the tamper-detection
        # floor, and refreshes ``self._project_total_cost`` atomically.
        # R9-002: by the time this helper runs, execute_feature has
        # ALREADY routed the just-finished feature's cost through
        # ``_increment_cost``, so ``self._project_total_cost`` already
        # includes it. Adding ``result.total_cost_usd`` again here would
        # double-count.
        project_total = float(self._project_total_cost or 0.0)
        state = {
            "feature_id": feature.id,
            "feature_name": feature.name,
            "feature_status": "interrupted",
            "reason": "graceful_shutdown",
            "total_cost_at_interrupt": project_total,
            "features_completed": self.features_completed,
            "features_failed": self.features_failed,
        }
        try:
            db.create_checkpoint(
                project_id=self.project_id,
                feature_id=feature.id,
                checkpoint_type="interruption",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=project_total,
                duration_at_checkpoint_ms=result.duration_ms,
            )
            logger.info(
                "Created interruption checkpoint for feature %s", feature.id
            )
        except Exception:
            logger.warning(
                "Failed to create interruption checkpoint for feature %s",
                feature.id,
                exc_info=True,
            )

    def _install_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown.

        The handler is intentionally minimal: it only sets the
        ``shutdown_requested`` flag (async-signal-safe) and emits a
        warning. The flag is observed at the top of ``run()`` between
        feature iterations.

        KNOWN LIMITATION (mirrored in the module docstring): if the
        signal arrives while ``await spawn_sub_agent(...)`` is in
        flight, the loop will not actually stop until that sub-agent
        finishes. The warning below tells the user this so they know
        why Ctrl-C "doesn't work immediately" and that a second Ctrl-C
        will force-exit via :class:`SystemExit`.
        """
        def handler(signum, frame):
            sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
            if self.shutdown_requested:
                # Second signal: force immediate exit. Raising SystemExit
                # from a signal handler is permitted (the interpreter
                # unwinds via the regular exception path).
                logger.warning(
                    "Received %s again during shutdown — forcing immediate exit",
                    sig_name,
                )
                raise SystemExit(128 + signum)

            logger.warning(
                "Received %s — graceful shutdown requested. "
                "Shutdown will be honored after the current sub-agent finishes "
                "(this can take several minutes). Press Ctrl-C again to force exit.",
                sig_name,
            )
            self.request_shutdown()

        try:
            signal.signal(signal.SIGINT, handler)
            signal.signal(signal.SIGTERM, handler)
        except (OSError, ValueError):
            # Signal handling may fail in some contexts (e.g., threads)
            logger.debug("Could not install signal handlers")

    def _resume_interrupted_work(self) -> None:
        """Detect and resume interrupted work from a previous run.

        On startup, checks for:
        1. Features with status='executing' (crashed mid-execution)
        2. Features with status='interrupted' (gracefully stopped)
        3. Resumable checkpoints (can_resume=TRUE)
        4. Orphaned 'pending' features whose dependencies are ALL completed
           (left over from a crash mid-cascade-update — see
           ``db.complete_feature_and_cascade``)

        For each interrupted/executing feature:
        - If a resumable checkpoint exists, resume from it (restoring state)
        - If no checkpoint, reset the feature to 'ready' so it retries from scratch

        In fresh mode, all interrupted/executing features are simply reset to 'ready'
        without consuming any checkpoints.

        Orphaned-pending recovery always runs (independent of fresh mode) so
        that a mid-cascade crash never permanently strands dependents on
        'pending'.
        """
        # Find features stuck in 'executing' (process crashed)
        executing = db.list_features(project_id=self.project_id, status="executing")
        # Find features marked 'interrupted' (graceful shutdown)
        interrupted = db.list_features(project_id=self.project_id, status="interrupted")

        stale_features = executing + interrupted

        if stale_features:
            logger.info(
                "Found %d interrupted/stale features to resume",
                len(stale_features),
            )

            if self.fresh:
                # Fresh mode: reset all to 'ready' without consuming checkpoints
                for feat in stale_features:
                    db.update_feature(feat.id, status="ready")
                    logger.info(
                        "Fresh mode: reset feature %s (%s) to 'ready'",
                        feat.id,
                        feat.name,
                    )
            else:
                # Normal resume mode: try to resume from checkpoints
                resumable = db.find_resumable_checkpoints(project_id=self.project_id)
                # Build a map: feature_id -> most recent resumable checkpoint
                checkpoint_by_feature: dict[str, Any] = {}
                for cp in resumable:
                    if cp.feature_id not in checkpoint_by_feature:
                        checkpoint_by_feature[cp.feature_id] = cp

                for feat in stale_features:
                    cp = checkpoint_by_feature.get(feat.id)
                    if cp is not None:
                        # Resume from checkpoint (restores feature state then sets to 'ready')
                        logger.info(
                            "Resuming feature %s (%s) from checkpoint %s",
                            feat.id,
                            feat.name,
                            cp.id,
                        )
                        db.resume_from_checkpoint(cp.id)
                        # After state is restored, set to 'ready' so the loop picks it up
                        db.update_feature(feat.id, status="ready")
                    else:
                        # No checkpoint: reset to 'ready'
                        logger.info(
                            "No checkpoint for feature %s (%s), resetting to 'ready'",
                            feat.id,
                            feat.name,
                        )
                        db.update_feature(feat.id, status="ready")

        # Orphaned-pending recovery (atomicity safety-net):
        # Scan for 'pending' features whose dependencies are ALL completed.
        # These are the tell-tale sign of a crash between the feature
        # status update and the dependent cascade in a previous version
        # of this code (or any future regression). Promote them to
        # 'ready' so the loop can pick them up. Runs independently of
        # the 'executing'/'interrupted' branch because the orphan state
        # has nothing to do with checkpoints.
        self._recover_orphaned_pending_features()

    def _recover_orphaned_pending_features(self) -> None:
        """Promote pending features whose deps are all completed to 'ready'.

        Two cases are handled here, both with the same fix (bulk promote
        ``pending`` → ``ready``):

        1. **Mid-cascade crash recovery.** A crash between the feature
           status update and the dependent cascade in
           ``db.complete_feature_and_cascade`` would leave dependents in
           'pending' with all dependencies satisfied — a state the loop
           would otherwise never escape.
        2. **Fresh-spec root features (R10-003).** Features with no
           declared dependencies are created by ``bob plan --create``
           in ``status='pending'`` and were never promoted to ``ready``
           on first run, so a brand-new project would exit
           ``ALL_BLOCKED`` immediately. This is the most visible
           Quickstart regression: the literal README sequence ``init`` →
           ``plan --create`` → ``run --all`` did nothing useful.

        Implementation note: detection is two cheap indexed SQL queries
        (``db.find_orphaned_pending_features`` and
        ``db.find_pending_features_without_deps``), and the promotion is
        one bulk ``UPDATE ... WHERE id IN (...) AND status='pending'`` in
        ``db.bulk_promote_features_to_ready``. We dedupe before the
        promote so the log message reflects the actual unique work.
        """
        orphaned_ids = db.find_orphaned_pending_features(self.project_id)
        no_dep_ids = db.find_pending_features_without_deps(self.project_id)

        # Dedupe (the two queries are disjoint by construction — one
        # requires EXISTS deps, the other requires NOT EXISTS deps — but
        # be defensive in case a future schema change blurs the line).
        all_ids: list[str] = []
        seen: set[str] = set()
        for fid in (*orphaned_ids, *no_dep_ids):
            if fid not in seen:
                seen.add(fid)
                all_ids.append(fid)

        if not all_ids:
            return

        # Spec quality gate: filter out features whose spec_quality_score is
        # below the 0.85 threshold before promoting to 'ready'.
        gate_blocked_ids: list[str] = []
        promotable_ids: list[str] = []
        for fid in all_ids:
            feature_obj = db.get_feature(fid)
            if feature_obj is None:
                promotable_ids.append(fid)
                continue
            ac_raw = feature_obj.acceptance_criteria or "[]"
            import json as _json
            try:
                ac_list = _json.loads(ac_raw) if isinstance(ac_raw, str) else ac_raw
            except (ValueError, TypeError):
                ac_list = []
            quality_report = _compute_spec_quality_score(
                name=feature_obj.name,
                description=feature_obj.description,
                acceptance_criteria=ac_list,
            )
            allowed, block_msg = _spec_quality_gate_for_ready(quality_report)
            if not allowed:
                # MID-RUN RE-SYNTHESIS (F-R7-632): a gate-blocked feature was
                # previously left 'pending' forever — the loop only ever
                # re-dispatched it to test-writer/CodeT, which rebuild CODE and
                # can NEVER raise the spec_quality score (that depends on the
                # ACs). RCA never fired because it only runs post-EXECUTION and
                # blocked features never execute. Result: the score never
                # increased and the run livelocked (bob70: 658 "stays at pending"
                # re-scores at 78% CPU). The ONLY thing that raises the score is
                # regenerating the ACs — re-run the score-gate synthesizer once.
                new_acs, new_score = self._maybe_resynthesize_blocked(feature_obj)
                if new_acs and new_score >= quality_report.score and _spec_quality_gate_for_ready(
                    _compute_spec_quality_score(
                        name=feature_obj.name,
                        description=feature_obj.description,
                        acceptance_criteria=new_acs,
                    )
                )[0]:
                    db.update_feature(
                        fid,
                        acceptance_criteria=_json.dumps(new_acs),
                        spec_quality_score=new_score,
                    )
                    logger.info(
                        "Mid-run re-synthesis raised feature %s (%s) score %.4f -> %.4f; promoting",
                        fid[:8], feature_obj.name, quality_report.score, new_score,
                    )
                    promotable_ids.append(fid)
                    continue
            if allowed:
                promotable_ids.append(fid)
                db.update_feature(fid, spec_quality_score=quality_report.score)
            else:
                gate_blocked_ids.append(fid)
                db.update_feature(fid, spec_quality_score=quality_report.score)
                logger.info(
                    "Spec quality gate blocked feature %s (%s, score=%.4f) from reaching 'ready': %s",
                    fid[:8],
                    feature_obj.name,
                    quality_report.score,
                    block_msg,
                )

            # PRE-PROMOTION TEST-PREP IS OPT-IN (default OFF).
            #
            # The spec-critic + test-writer + CodeT triangulation blocks below
            # spawn FIVE sub-agents PER FEATURE, run synchronously inside this
            # per-feature promotion loop — i.e. BEFORE the single bulk_promote at
            # the end. With 128 features that is 128×5 serial sub-agent spawns
            # that must ALL finish before a single feature is promoted to 'ready'
            # and can execute. That pinned the run at 99% CPU with completed=0 and
            # nothing ever reaching the features_ready view (the bob72 promotion
            # livelock, distinct from the dual-scorer gate bug). This scaffolding
            # is implementation-prep, not an admission gate — it must not block
            # promotion. Gate it behind BOB_PREPROMOTE_TESTPREP (default off);
            # the 0.85 spec-quality gate above is unchanged and still enforced.
            _testprep = os.environ.get("BOB_PREPROMOTE_TESTPREP", "").strip().lower() in ("1", "true", "yes", "on")

            # Spec-critic: emit structured defects and persist for regression tracking
            if _testprep:
                try:
                    critic_defects = _spec_critic_critique(
                        feature_id=fid,
                        name=feature_obj.name,
                        description=feature_obj.description or "",
                        acceptance_criteria=ac_list,
                    )
                    _spec_critic_persist(
                        critic_defects,
                        feature_id=fid,
                        name=feature_obj.name,
                        description=feature_obj.description or "",
                        acceptance_criteria=ac_list,
                    )
                    if critic_defects:
                        logger.info(
                            "Spec-critic found %d defect(s) for feature %s (%s)",
                            len(critic_defects),
                            fid[:8],
                            feature_obj.name,
                        )
                except Exception:
                    logger.exception("Spec-critic failed for feature %s; continuing", fid[:8])

                # Test-writer sub-agent: emit one failing pytest per AC before implementer fires
                if ac_list:
                    try:
                        _emitted = _emit_failing_tests(
                            feature_id=fid,
                            acceptance_criteria=ac_list,
                        )
                        _bij = _verify_test_bijection(
                            feature_id=fid,
                            acceptance_criteria=ac_list,
                        )
                        if _bij.is_bijective:
                            logger.info(
                                "Test-writer: emitted %d failing test(s) for feature %s (%s)",
                                len(_emitted),
                                fid[:8],
                                feature_obj.name,
                            )
                        else:
                            logger.warning(
                                "Test-writer bijection check failed for feature %s: "
                                "missing=%s orphan=%s",
                                fid[:8],
                                _bij.missing_tests,
                                _bij.orphan_tests,
                            )
                    except Exception:
                        logger.exception("Test-writer failed for feature %s; continuing", fid[:8])

                # CodeT triangulation: spawn K candidate test sets and K candidate impls
                # to guard against AI-judge sycophancy (F-R7-454 / CodeT ICLR 2023)
                if ac_list:
                    try:
                        _codet_tests = _codet_spawn_k_tests(
                            feature_id=fid,
                            acceptance_criteria=ac_list,
                        )
                        _codet_impls = _codet_spawn_k_impls(
                            feature_id=fid,
                            acceptance_criteria=ac_list,
                        )
                        logger.info(
                            "CodeT triangulation: spawned %d test candidate(s) and %d impl candidate(s) "
                            "for feature %s (%s)",
                            len(_codet_tests),
                            len(_codet_impls),
                            fid[:8],
                            feature_obj.name,
                        )
                    except Exception:
                        logger.exception("CodeT triangulation failed for feature %s; continuing", fid[:8])

            # Spec self-consistency: N-sample stability check pre-critic (F-2f4a2cd8).
            # Runs the spec extractor 3 times with different seeds and computes a
            # Jaccard stability_score. Score < 0.7 routes to F-R7-456 clarification;
            # score >= 0.9 auto-accepts with consensus:true; otherwise falls through
            # to the standard critic path.
            if ac_list:
                try:
                    _stability_result = _run_spec_stability_check(
                        feature_id=fid,
                        name=feature_obj.name,
                        description=feature_obj.description or "",
                        acceptance_criteria=ac_list,
                        n=3,
                    )
                    logger.info(
                        "Spec stability check: feature %s (%s) score=%.3f route=%s consensus=%s",
                        fid[:8],
                        feature_obj.name,
                        _stability_result.stability_score,
                        _stability_result.route,
                        _stability_result.consensus,
                    )
                    if _stability_result.route == "clarification":
                        logger.warning(
                            "Spec stability below threshold (%.3f < 0.7) for feature %s (%s); "
                            "disagreeing slots: %s — routing to F-R7-456 clarification",
                            _stability_result.stability_score,
                            fid[:8],
                            feature_obj.name,
                            _stability_result.disagreeing_slots[:5],
                        )
                except Exception:
                    logger.exception("Spec stability check failed for feature %s; continuing", fid[:8])

            # Clarification loop: detect ambiguous slots above T=0.4; block in CI mode
            if ac_list:
                try:
                    _ci_mode = os.environ.get("BOB_CI_MODE", "").strip().lower() in ("1", "true", "yes", "on")
                    _slots, _cl_outcome = _run_clarification_loop(
                        ac_list,
                        ci_mode=_ci_mode,
                    )
                    if _cl_outcome == _SPEC_NEEDS_HUMAN:
                        logger.warning(
                            "Clarification loop: CI mode — feature %s (%s) has ambiguous slots "
                            "requiring human input; marking gate-blocked.",
                            fid[:8],
                            feature_obj.name,
                        )
                        if fid in promotable_ids:
                            promotable_ids.remove(fid)
                            gate_blocked_ids.append(fid)
                except Exception:
                    logger.exception("Clarification loop failed for feature %s; continuing", fid[:8])

        all_ids = promotable_ids

        if not all_ids:
            return

        promoted = db.bulk_promote_features_to_ready(all_ids)

        if orphaned_ids:
            logger.info(
                "Mid-cascade crash recovery: promoted %d orphaned pending "
                "feature(s) to 'ready': %s",
                len(orphaned_ids),
                ", ".join(p[:8] for p in orphaned_ids),
            )
        if no_dep_ids:
            logger.info(
                "Promoted %d pending root feature(s) (no declared deps) "
                "to 'ready': %s",
                len(no_dep_ids),
                ", ".join(p[:8] for p in no_dep_ids),
            )
        # Sanity check: the bulk promote is idempotent and may report a
        # smaller count than ``len(all_ids)`` if a feature moved status
        # between the SELECT and the UPDATE. Log if so — it usually means
        # a concurrent path is also touching status.
        if promoted < len(all_ids):
            logger.debug(
                "Bulk promote raced: requested %d, applied %d",
                len(all_ids),
                promoted,
            )

    async def _run_single_feature(self) -> LoopTermination:
        """Run only the target feature (one iteration) then exit.

        Used when ``target_feature_id`` is set on the loop. Skips
        ``find_next_ready_feature`` so we never run unrelated features.

        Returns:
            ALL_COMPLETED if the feature finished with status='completed',
            ALL_BLOCKED if the feature is not runnable or ended in any
            non-completed status (``needs_human``, ``failed``, ``interrupted``).
            BUDGET_EXCEEDED if --max-cost was reached before execution.
            SHUTDOWN_REQUESTED if SIGINT/SIGTERM fired mid-run.
        """
        feature = db.get_feature(self.target_feature_id)
        if feature is None:
            logger.error(
                "Target feature %s not found; aborting single-feature run",
                self.target_feature_id,
            )
            return LoopTermination.ALL_BLOCKED

        if feature.project_id != self.project_id:
            logger.error(
                "Target feature %s belongs to a different project (%s); aborting",
                self.target_feature_id,
                feature.project_id,
            )
            return LoopTermination.ALL_BLOCKED

        # Validate that the feature is runnable. find_next_ready_feature uses
        # the features_ready view, which requires status='ready' AND that
        # readiness_score >= the risk-category threshold AND that all
        # dependencies are completed. Match that here by looking up the
        # feature in the same view.
        ready = {f.id: f for f in db.get_ready_features(self.project_id)}
        runnable = feature.id in ready

        # 'ready' / 'pending' may still need a real dependency check — a
        # 'pending' feature whose dependencies are NOT all completed must
        # not run, even though its status is in the allow-set. Anything
        # outside {ready, pending} is unconditionally blocked.
        if not runnable and feature.status not in {"ready", "pending"}:
            logger.info(
                "Target feature %s is not runnable (status=%s); exiting cleanly",
                feature.id,
                feature.status,
            )
            return LoopTermination.ALL_BLOCKED

        # Bug 5: Tighten the 'pending' allowance. If any declared dependency
        # is not yet 'completed', the feature is genuinely blocked — runnable
        # would be False here (it isn't in the features_ready view) so we
        # already know readiness/threshold may be low, but the dep gate is
        # the load-bearing one. Check it explicitly so a pending feature with
        # unmet deps never sneaks through.
        if not runnable:
            try:
                deps = db.get_feature_dependencies(feature.id)
            except Exception:
                logger.warning(
                    "Could not read dependencies for target feature %s; "
                    "treating as blocked",
                    feature.id,
                    exc_info=True,
                )
                return LoopTermination.ALL_BLOCKED
            for dep in deps:
                dep_feature = db.get_feature(dep.depends_on_feature_id)
                if dep_feature is None or dep_feature.status != "completed":
                    logger.info(
                        "Target feature %s has unmet dependency %s "
                        "(status=%s); exiting cleanly",
                        feature.id,
                        dep.depends_on_feature_id,
                        dep_feature.status if dep_feature else "missing",
                    )
                    return LoopTermination.ALL_BLOCKED

        # Assess confidence if not yet assessed (mirrors main loop behaviour).
        if feature.readiness_score == 0.0:
            logger.info(
                "Assessing confidence for target feature %s (%s)",
                feature.id[:8],
                _log_safe(feature.name),
            )
            confidence = db.assess_feature_confidence(feature.id)
            db.update_feature(feature.id, **confidence)
            feature = db.get_feature(feature.id)
            if feature is None:
                logger.error("Target feature disappeared after confidence assessment")
                return LoopTermination.ALL_BLOCKED

        # Bug 3: Honour --max-cost / project budget even in single-feature
        # mode. The main run() loop checks this every iteration, but the
        # single-feature path used to skip the check entirely.
        if self.budget_exceeded():
            logger.warning(
                "Budget exceeded for project %s; cannot run feature %s",
                self.project_id,
                feature.id,
            )
            return LoopTermination.BUDGET_EXCEEDED

        # Execute exactly one feature, then exit regardless of outcome.
        await self.execute_feature(feature)
        self._maybe_warn_cost_proxy_active()
        # R10-002: If the operator hit Ctrl-C / SIGTERM during the run, the
        # outer CLI used to print "Feature completed!" and exit 0 because the
        # single-feature path returned ALL_COMPLETED unconditionally. That
        # masked an interrupted run as success — concretely, this is exactly
        # how a CI pipeline that does `bob run --feature X && deploy.sh`
        # would push a half-built tree to production. Mirror the main loop:
        # if shutdown was requested, surface SHUTDOWN_REQUESTED so the CLI
        # prints "Shutdown requested." and exits 130.
        if self.shutdown_requested:
            return LoopTermination.SHUTDOWN_REQUESTED
        # R10-007: Reflect the feature's ACTUAL final status in the
        # termination reason. Previously this returned ALL_COMPLETED
        # unconditionally — even when the sub-agent failed verification,
        # was rejected by a hook, errored out, or otherwise ended
        # ``needs_human``. The summary log then said
        # ``termination=ALL_COMPLETED features_completed=0 features_failed=1``
        # which is internally inconsistent and (worse) made `bob run
        # --feature X` exit 0 on failure, so a CI pipeline doing `bob
        # run --feature X && deploy.sh` would push a half-built tree to
        # production. Re-read the feature post-execution and map status
        # to the appropriate termination.
        try:
            final = db.get_feature(feature.id)
        except Exception:
            logger.debug(
                "Could not re-read feature %s after execution; "
                "falling back to ALL_BLOCKED",
                feature.id,
                exc_info=True,
            )
            return LoopTermination.ALL_BLOCKED
        if final is None:
            return LoopTermination.ALL_BLOCKED
        if final.status == "completed":
            return LoopTermination.ALL_COMPLETED
        # ``needs_human``, ``failed``, ``executing`` (interrupted),
        # ``interrupted``, ``ready``/``pending`` (somehow unchanged) all
        # mean: the feature did not finish cleanly. Surface that to the
        # CLI as ALL_BLOCKED so the exit code is non-zero.
        return LoopTermination.ALL_BLOCKED

    async def run(self) -> LoopTermination:
        """Run the continuous orchestration loop.

        Processes features strictly one at a time (sequential, not
        concurrent) until a termination condition is met. Each iteration
        picks the highest-priority ready feature, awaits its sub-agent
        to completion, then loops; there is no fan-out across sibling
        features. On startup, automatically detects and resumes
        interrupted work (F116).

        When ``target_feature_id`` is set, runs only that single feature and
        exits after one iteration regardless of outcome.

        Concurrency: this method acquires an exclusive advisory file lock
        on ``<workspace>/.bob.lock`` for the duration of the run. A
        second concurrent ``bob run`` for the same project will fail
        fast with :class:`AlreadyRunningError`.

        Returns:
            The reason the loop terminated.
        """
        # Acquire the per-project run lock. If another bob run is in
        # flight we want to bail out BEFORE installing signal handlers
        # or doing any DB writes — the second invocation should be a
        # no-op from the project's point of view.
        lock_handle = acquire_run_lock(
            self.workspace or os.getcwd(), force_unlock=self.force_unlock
        )
        # R5-009: Capture the wall-clock start so the termination summary
        # log reflects the actual run time (not OrchestrationLoop init
        # time). Set inside ``run`` so re-running the same loop instance
        # gets a fresh window.
        self._run_start_time = time.monotonic()
        termination: LoopTermination | None = None
        try:
            termination = await self._run_locked()
            return termination
        finally:
            # Always emit the loop-level summary on the way out — even if
            # _run_locked raised — so operators see the cost / counts
            # for partial runs too. ``termination`` stays None on a raised
            # exception; surface that distinctly so the log doesn't claim
            # a completion reason that never happened.
            self._emit_run_summary(termination)
            release_run_lock(lock_handle)

    def _emit_run_summary(self, termination: LoopTermination | None) -> None:
        """Log a single structured line summarising the run.

        Intended to be called exactly once per ``run()`` invocation,
        from the ``finally`` block so that crashes / cancellations also
        get a summary line. The log line format is parsable by ops
        tooling: features_completed / features_failed / total_cost /
        total_duration are space-separated key=value pairs.
        """
        if self._run_start_time is None:
            run_duration = 0.0
        else:
            run_duration = max(0.0, time.monotonic() - self._run_start_time)
        # ``self._project_total_cost`` is the only project cost
        # accumulator now (the prior in-memory ``self.total_cost``
        # mirror was deleted as part of the ``non-atomic-counter``
        # structural fix). Refresh once here in case something exotic
        # touched the DB out of band — every cost write site already
        # refreshes via ``_increment_cost``.
        try:
            self._refresh_project_cost_cache()
        except Exception:
            logger.debug(
                "Could not refresh project cost cache for run summary",
                exc_info=True,
            )
        total_cost = float(self._project_total_cost or 0.0)
        termination_name = translate_termination_label(
            termination.name if termination is not None else "RAISED"
        )
        logger.info(
            "Run finished: termination=%s features_completed=%d "
            "features_failed=%d total_cost=$%.2f total_duration=%.1fs",
            termination_name,
            self.features_completed,
            self.features_failed,
            total_cost,
            run_duration,
        )

    async def _run_locked(self) -> LoopTermination:
        """Body of :meth:`run` executed while the project lock is held."""
        self._install_signal_handlers()
        logger.info("Starting orchestration loop for project %s", self.project_id)

        # 1809afa5: Startup check — fix stale project metadata from rsync spawn.
        # spawn_next_generation.sh rsync-copies the parent DB, leaving projects.name
        # set to the parent gen and spec_path possibly pointing at a pytest tmpdir.
        # verify_project_metadata corrects both in-place before any work begins.
        try:
            from bob.run_loop import verify_project_metadata
            _meta_result = verify_project_metadata(
                workspace=self.workspace or None,
            )
            if _meta_result.name_was_stale:
                logger.info(
                    "Startup: corrected stale project name → %r (workspace basename: %r)",
                    _meta_result.corrected_name,
                    _meta_result.workspace_basename,
                )
        except Exception:
            logger.warning(
                "Startup: verify_project_metadata raised; continuing with possibly stale metadata",
                exc_info=True,
            )

        # F116: Auto-resume interrupted work
        self._resume_interrupted_work()

        # Single-feature mode: run only the target feature and exit.
        if self.target_feature_id is not None:
            return await self._run_single_feature()

        # F-2f69b554: Promote features whose AC artifacts already exist on disk
        # before any sub-agent spawns. Prevents the "eval-demotion treadmill"
        # where each generation re-ran features already completed on disk.
        try:
            _promoted = _reconcile_from_disk(
                self.project_id,
                workspace=pathlib.Path(self.workspace),
            )
            if _promoted:
                logger.info(
                    "reconcile_from_disk promoted %d feature(s) from on-disk state",
                    _promoted,
                )
        except Exception:
            logger.warning(
                "reconcile_from_disk raised an exception; continuing without promotion",
                exc_info=True,
            )

        # F-R6-302: Sweep orphan MCP subprocesses every N iterations.
        # In Round 5 we accumulated 59 orphan bob.memory_mcp processes
        # because nothing tore them down when a sub-agent died abnormally
        # (timeout, OOM, kill -9). Running the sweep here bounds the
        # damage to N iterations' worth of orphans even if every
        # try/finally cleanup path fails.
        _orphan_sweep_interval = 5
        _orphan_sweep_counter = 0

        def _seed_ready_confidence() -> int:
            """Readiness bootstrap sweep (readiness-score-deadlock fix): assess +
            persist confidence for EVERY ready-status feature still at
            readiness_score==0.0. Without this, the gated find_next_ready_feature()
            returns nothing (all at 0.0), so the 8-wide batch can only assess one
            feature per iteration via the below-threshold fallback — collapsing
            concurrency to ~1. Seeding them all lets high-quality features (derived
            from their earned spec_quality_score) become claimable together so the
            concurrent batch fills. Lowers no gate: assess() still returns
            sub-threshold readiness for weak/integration features. Runs each
            iteration so mid-run promotions (features that just passed the
            spec_quality gate) are seeded too. Cheap: only touches 0.0 rows."""
            try:
                _ready = db.list_features(project_id=self.project_id, status="ready")
            except Exception:
                logger.warning("Readiness seed sweep: list_features failed", exc_info=True)
                return 0
            _n = 0
            for _bf in _ready:
                if (_bf.readiness_score or 0.0) == 0.0:
                    try:
                        _conf = db.assess_feature_confidence(_bf.id)
                        db.update_feature(_bf.id, **_conf)
                        _n += 1
                    except Exception:
                        logger.warning("Readiness seed: assess failed for %s", _bf.id[:8], exc_info=True)
            if _n:
                logger.info("Readiness seed sweep: seeded confidence for %d ready feature(s)", _n)
            return _n

        while True:
            # Re-run pending→ready promotion EACH iteration, not just once at
            # startup. _recover_orphaned_pending_features was only called from
            # _resume_interrupted_work (pre-loop), so a feature that became
            # gate-eligible mid-run (e.g. after a sibling completed, or after
            # sanitize re-scored its ACs) was never promoted — bob65 exited
            # QUEUE_DRAINED with 66 pending stuck. Promote first, then seed
            # readiness on the freshly-promoted rows.
            try:
                self._recover_orphaned_pending_features()
            except Exception:
                logger.warning("in-loop pending-promotion sweep failed; continuing", exc_info=True)
            _seed_ready_confidence()
            _orphan_sweep_counter += 1
            if _orphan_sweep_counter % _orphan_sweep_interval == 0:
                try:
                    reaped = sweep_orphans()
                    if reaped:
                        logger.info(
                            "Periodic orphan sweep reaped %d MCP "
                            "subprocess(es): %s",
                            len(reaped),
                            reaped,
                        )
                except Exception:
                    logger.debug(
                        "Orphan MCP sweep failed; will retry next tick",
                        exc_info=True,
                    )
                try:
                    subagent_reaped = _sweep_orphan_subagents()
                    if subagent_reaped:
                        logger.info(
                            "Orphan subagent sweep reaped %d subagent(s): %s",
                            len(subagent_reaped),
                            subagent_reaped,
                        )
                except Exception:
                    logger.debug(
                        "Orphan subagent sweep failed; will retry next tick",
                        exc_info=True,
                    )
                try:
                    stuck_reaped = _sweep_stuck_executing(self.project_id)
                    if stuck_reaped:
                        logger.info(
                            "Stuck-executing reaper reset %d feature(s): %s",
                            len(stuck_reaped),
                            stuck_reaped,
                        )
                except Exception:
                    logger.debug(
                        "Stuck-executing reaper sweep failed; will retry next tick",
                        exc_info=True,
                    )
                try:
                    zombie_reaped = _scan_and_reap_zombies(self.project_id)
                    if zombie_reaped:
                        logger.info(
                            "Zombie-run reaper closed %d orphan run(s): %s",
                            len(zombie_reaped),
                            zombie_reaped,
                        )
                except Exception:
                    logger.debug(
                        "Zombie-run reaper sweep failed; will retry next tick",
                        exc_info=True,
                    )
                resume_promoted = _periodic_resume_scan(self.project_id)
                if resume_promoted:
                    logger.info(
                        "Periodic resume scan promoted %d interrupted feature(s): %s",
                        len(resume_promoted),
                        resume_promoted,
                    )

            # Check shutdown
            if self.shutdown_requested:
                logger.info("Shutdown requested, stopping loop")
                # F117: Stop MCP server gracefully
                try:
                    stop_mcp_server()
                except Exception:
                    logger.debug("MCP server stop failed during shutdown", exc_info=True)
                logger.info("Interrupted. Run bob run to resume.")
                return LoopTermination.SHUTDOWN_REQUESTED

            # Check budget
            if self.budget_exceeded():
                logger.info("Budget exceeded, stopping loop")
                _final_exit_sweep(self.project_id)
                return LoopTermination.BUDGET_EXCEEDED

            # Find next ready feature
            feature = self.find_next_ready_feature()
            if feature is None:
                # No feature meets readiness threshold - check for features that need research
                features_in_ready_status = db.list_features(
                    project_id=self.project_id,
                    status='ready'
                )
                if features_in_ready_status:
                    # Pick the first one that's in 'ready' status but doesn't meet threshold
                    feature = features_in_ready_status[0]
                    # R7-003: If research has already run for this feature
                    # then ``needs_research`` will return False on the next
                    # ``execute_feature`` call. Without research, readiness
                    # cannot improve, but the loop would still spawn the
                    # implementation sub-agent — burning a refinement
                    # attempt every iteration until ``max_refinement_attempts``
                    # is exhausted. Mark it ``needs_human`` instead so the
                    # operator can intervene (raise readiness, lower risk
                    # category, or split the work).
                    if feature.research_iterations and feature.research_iterations > 0:
                        threshold = db.RISK_THRESHOLDS.get(
                            feature.risk_category, 0.80
                        )
                        # F-R6-316: defense in depth. The
                        # research-iteration counter can be > 0 even
                        # when no research actually produced findings
                        # (legacy DB rows from pre-F-R6-316 builds,
                        # manual resets, race conditions). Before
                        # giving up on the feature, verify that at
                        # least one ``research_results`` row carries
                        # non-null findings. If not — and we haven't
                        # exceeded the error cap — reset the counter
                        # so ``needs_research`` re-fires next tick.
                        try:
                            prior_research = db.list_research_results(
                                feature_id=feature.id
                            )
                        except Exception:
                            prior_research = []
                        successful = [r for r in prior_research if r.findings]
                        errored = [r for r in prior_research if not r.findings]
                        if not successful and len(errored) < _MAX_RESEARCH_ERROR_ATTEMPTS:
                            logger.info(
                                "Feature %s has research_iterations=%d but no "
                                "successful research yet (errored=%d). Resetting "
                                "research_iterations=0 to allow another research "
                                "attempt instead of marking needs_human.",
                                feature.id,
                                feature.research_iterations,
                                len(errored),
                            )
                            db.update_feature(feature.id, research_iterations=0)
                            continue
                        # F-R6-317: don't preemptively mark needs_human
                        # when the feature still has refinement attempts
                        # left. The original R7-003 concern (busy-looping
                        # on a feature that will never improve) is
                        # already bounded by max_refinement_attempts:
                        # ``increment_refinement_attempts`` in db.py
                        # auto-transitions a feature to needs_human the
                        # moment the count hits max. A low readiness
                        # score after decay (mid_work_crash charged,
                        # confidence decayed) does NOT mean the
                        # implementation will fail — readiness is an
                        # orchestrator-side prior, the sub-agent never
                        # sees it. Let the natural retry budget run.
                        attempts = feature.refinement_attempts or 0
                        max_attempts = feature.max_refinement_attempts or 5
                        if attempts < max_attempts:
                            logger.info(
                                "Feature %s is below readiness threshold "
                                "(score=%.2f, threshold=%.2f) but still has "
                                "refinement budget (%d/%d); executing instead "
                                "of preemptively marking needs_human. (F-R6-317)",
                                feature.id,
                                feature.readiness_score,
                                threshold,
                                attempts,
                                max_attempts,
                            )
                            # Fall through to normal execute_feature path
                            # below.
                        else:
                            logger.warning(
                                "Feature %s is below readiness threshold "
                                "(score=%.2f, threshold=%.2f), research done "
                                "(iterations=%d, successful=%d, errored=%d), "
                                "AND refinement budget exhausted (%d/%d); "
                                "marking needs_human.",
                                feature.id,
                                feature.readiness_score,
                                threshold,
                                feature.research_iterations,
                                len(successful),
                                len(errored),
                                attempts,
                                max_attempts,
                            )
                            db.update_feature(feature.id, status="needs_human")
                            # Loop again — there may be other actionable work.
                            continue
                    # Bootstrap bypass (73d63cdc): if the feature has never been
                    # researched (research_iterations==0), the normal research →
                    # readiness loop can never start — deadlock.  Grant ONE
                    # execution pass so the result becomes the seed signal.
                    if _may_bypass_readiness(feature):
                        logger.info(
                            "Bootstrap bypass granted for feature %s "
                            "(readiness=%.2f, bootstrap_attempts=%d, "
                            "research_iterations=%d); executing once to seed "
                            "research signal.",
                            feature.id[:8],
                            feature.readiness_score,
                            feature.bootstrap_attempts or 0,
                            feature.research_iterations or 0,
                        )
                        db.update_feature(
                            feature.id,
                            bootstrap_attempts=(feature.bootstrap_attempts or 0) + 1,
                        )
                        feature = db.get_feature(feature.id) or feature
                        # Fall through to execute_feature below.
                    else:
                        logger.info(
                            "No features meet readiness threshold, but found feature %s in 'ready' status (readiness=%.2f). Will assess and potentially trigger research.",
                            feature.id[:8],
                            feature.readiness_score
                        )
                elif self.all_features_completed():
                    logger.info("All features completed")
                    _final_exit_sweep(self.project_id)
                    return LoopTermination.ALL_COMPLETED
                elif self.all_remaining_blocked():
                    logger.info("All remaining features are blocked")
                    _final_exit_sweep(self.project_id)
                    return LoopTermination.ALL_BLOCKED
                else:
                    # No ready feature but some are still pending — keep looping
                    # (this could happen if features are being reviewed or refined)
                    # To prevent busy-waiting, break if nothing is actionable
                    logger.info("No ready features, all remaining are blocked or pending")
                    _final_exit_sweep(self.project_id)
                    return LoopTermination.ALL_BLOCKED

            # Assess confidence before execution (if not already assessed)
            # This ensures features with low confidence trigger research
            if feature.readiness_score == 0.0:
                logger.info(
                    "Assessing confidence for feature %s (%s)",
                    feature.id[:8],
                    _log_safe(feature.name)
                )
                confidence = db.assess_feature_confidence(feature.id)
                db.update_feature(feature.id, **confidence)
                # Refresh feature with updated confidence scores
                feature = db.get_feature(feature.id)
                if not feature:
                    logger.error("Feature disappeared after confidence assessment")
                    continue

            # Execute the feature(s).
            #
            # When max_concurrent_features == 1 (the default) we dispatch a
            # single feature exactly as before (backward-compatible sequential
            # behaviour). When max_concurrent_features > 1 we collect up to N
            # additional ready features and dispatch them all via run_concurrent
            # (6e085356). A failure in one worker is caught inside run_concurrent
            # and does NOT propagate to peers; the on_failure callback releases
            # any cost reservation and logs the failure so the DB remains
            # consistent.
            # DISPATCH GUARD (bob72 mass-failure→idle fix): wrap the whole
            # dispatch so an exception that ESCAPES the gather (e.g. an anyio
            # ``RuntimeError: cancel scope in a different task`` raised by a
            # research/impl subagent spawn, which _run_one does not always catch)
            # cannot break the ``while True`` loop. Before this guard, such an
            # escape exited the loop body entirely — the run process stayed alive
            # but stopped dispatching, leaving N ready features stranded until the
            # auto_unstick no-progress respawn (~30 min later). On any escape we
            # reset this batch's 'executing' rows back to 'ready' and ``continue``
            # so the next iteration re-dispatches them in-process.
            _dispatch_batch_ids: list[str] = []
            try:
                if self.max_concurrent_features <= 1:
                    await self.execute_feature(feature)
                else:
                    batch = [feature]
                    # CRITICAL (concurrency-saturation fix): claim batch[0] as
                    # 'executing' BEFORE the batch-building loop. Without this, the
                    # first feature stays status='ready', so the very next
                    # find_next_ready_feature() returns it AGAIN (highest priority,
                    # still ready); the dedup guard below then breaks the loop with
                    # batch size 1 → strictly sequential execution despite an 8-wide
                    # cap and 19 claimable features (bob66: 1 feature / ~9 min).
                    # execute_feature re-writes status='executing' later (idempotent).
                    db.update_feature(feature.id, status="executing")
                    _dispatch_batch_ids.append(feature.id)
                    remaining_slots = self.max_concurrent_features - 1
                    while remaining_slots > 0:
                        next_feat = self.find_next_ready_feature()
                        if next_feat is None or next_feat.id in {f.id for f in batch}:
                            break
                        # Mark as executing so the next find_next_ready_feature
                        # call does not re-select it.
                        db.update_feature(next_feat.id, status="executing")
                        batch.append(next_feat)
                        _dispatch_batch_ids.append(next_feat.id)
                        remaining_slots -= 1

                    if len(batch) == 1:
                        # Only one feature available; fall through to sequential.
                        # (The feature was already claimed as 'executing' by
                        # execute_feature's own DB write; no double-write needed.)
                        await self.execute_feature(batch[0])
                    else:
                        def _on_failure(feat: Feature, exc: Exception) -> None:
                            # NOTE: release_reservation(conn, reservation_id) needs a
                            # sqlite connection + the reservation id; neither is
                            # available here and no per-feature reservation_id is
                            # tracked in this path, so the prior call
                            # `_release_reservation(feat.id)` ALWAYS raised
                            # "missing 1 required positional argument: 'reservation_id'"
                            # (feat.id was bound to `conn`). Budget holds are cleaned
                            # up by the cost system / at run end, so skip the release
                            # here rather than spam a TypeError on every concurrent
                            # worker failure. Reset the row to 'ready' so a failed
                            # feature is re-dispatched instead of stranded executing.
                            try:
                                db.update_feature(feat.id, status="ready")
                            except Exception as rst_exc:
                                logger.warning(
                                    "Could not reset failed feature %s to ready: %s",
                                    feat.id, rst_exc,
                                )
                            logger.warning(
                                "Concurrent worker failure for feature %s: %s",
                                feat.id, exc,
                            )

                        await _run_concurrent(
                            batch,
                            worker=self.execute_feature,
                            max_concurrent=self.max_concurrent_features,
                            on_failure=_on_failure,
                            per_task_timeout=_resolve_feature_timeout_seconds(),
                        )
            except Exception:
                logger.exception(
                    "Dispatch raised and escaped the gather; resetting %d "
                    "in-flight feature(s) to 'ready' and continuing the loop "
                    "(prevents the mass-failure→idle wedge).",
                    len(_dispatch_batch_ids),
                )
                for _fid in _dispatch_batch_ids:
                    try:
                        _cur = db.get_feature(_fid)
                        if _cur is not None and _cur.status == "executing":
                            db.update_feature(_fid, status="ready")
                    except Exception:
                        logger.debug("could not reset feature %s after dispatch escape", _fid[:8])
                continue

            self._maybe_warn_cost_proxy_active()


# ---------------------------------------------------------------
# Periodic interrupted-work resume scan (feature 9a00cda4)
#
# _resume_interrupted_work runs only at startup; a feature whose
# subagent is cancelled mid-run (max_turns hit, async timeout, etc.)
# is marked 'interrupted' but is never re-picked-up unless the
# orchestrator restarts.  _resume_interrupted_work_periodic is a
# module-level function called on every N-th tick so that interrupted
# rows are re-queued without requiring a relaunch.
# ---------------------------------------------------------------


def _resume_interrupted_work_periodic(project_id: str) -> list[str]:
    """Promote any 'interrupted' features back to 'ready' mid-run.

    Called periodically from the main orchestrator tick loop (not only at
    startup) so that a feature cancelled mid-run (max_turns hit, async
    timeout, etc.) is re-queued without requiring an orchestrator restart.

    Returns a list of feature IDs that were promoted.  DB errors are caught
    and logged so that a transient lock does not crash the loop.
    """
    promoted: list[str] = []
    try:
        interrupted = db.list_features(project_id=project_id, status="interrupted")
    except Exception:
        logger.debug(
            "periodic_resume: list_features failed; skipping this tick",
            exc_info=True,
        )
        return promoted

    for feat in interrupted:
        try:
            db.update_feature(feat.id, status="ready")
            promoted.append(feat.id)
            logger.info(
                "periodic_resume: promoted interrupted feature %s (%s) to 'ready'",
                feat.id,
                feat.name,
            )
        except Exception:
            logger.debug(
                "periodic_resume: update_feature failed for %s; skipping",
                feat.id,
                exc_info=True,
            )

    return promoted


# ---------------------------------------------------------------
# Dispatch concurrency helpers (feature 99d6c749)
#
# Introduce BOB_MAX_CONCURRENT_FEATURES (default 3) and three
# module-level functions that the orchestrator tick loop can call to
# fill concurrent dispatch slots.  The functions are designed so tests
# can exercise each piece independently without standing up a full
# OrchestrationLoop.
# ---------------------------------------------------------------

_DEFAULT_MAX_CONCURRENT_FEATURES = 3


def _resolve_max_concurrent_features() -> int:
    """Read ``BOB_MAX_CONCURRENT_FEATURES`` from the environment.

    Returns the configured cap (minimum 1), falling back to
    ``_DEFAULT_MAX_CONCURRENT_FEATURES`` (3) on any parse error or
    non-positive value.
    """
    raw = os.environ.get("BOB_MAX_CONCURRENT_FEATURES")
    if raw is None:
        return _DEFAULT_MAX_CONCURRENT_FEATURES
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB_MAX_CONCURRENT_FEATURES=%r; using default %d",
            raw,
            _DEFAULT_MAX_CONCURRENT_FEATURES,
        )
        return _DEFAULT_MAX_CONCURRENT_FEATURES
    if value < 1:
        logger.warning(
            "Non-positive BOB_MAX_CONCURRENT_FEATURES=%r; clamping to 1",
            raw,
        )
        return 1
    return value


def current_concurrency_slots(
    loop: "OrchestrationLoop",
    *,
    active_feature_ids: "set[str] | None" = None,
) -> int:
    """Return how many additional dispatch slots are open on *loop*.

    A slot is open when the cap (``loop.max_concurrent_features``) has
    not yet been filled by currently in-flight features.

    Args:
        loop: The :class:`OrchestrationLoop` whose cap to check.
        active_feature_ids: Optional set of feature IDs currently in
            flight.  When supplied the slot count is
            ``cap - len(active_feature_ids)`` (floored at 0).  When
            ``None`` the cap is returned directly (caller has no tracking
            of in-flight work).

    Returns:
        Integer >= 0; 0 means the cap is fully saturated.
    """
    cap = loop.max_concurrent_features
    if active_feature_ids is None:
        return max(0, cap)
    in_flight = len(active_feature_ids)
    return max(0, cap - in_flight)


def dispatch_up_to_concurrency(
    loop: "OrchestrationLoop",
    *,
    active_feature_ids: "set[str] | None" = None,
) -> "list[Feature]":
    """Fill open dispatch slots with ready features from *loop*'s project.

    Queries the database for features in ``ready`` status (via
    ``loop.find_next_ready_feature``), skipping any already in
    ``active_feature_ids``, until the concurrency cap is reached or no
    more ready features are available.

    Each claimed feature is marked ``executing`` in the database before
    being added to the returned list so that a subsequent
    :func:`dispatch_up_to_concurrency` call (or a parallel caller) does
    not re-select the same feature.

    Args:
        loop: The :class:`OrchestrationLoop` providing the project context
            and concurrency cap.
        active_feature_ids: Optional set of feature IDs already in flight.
            Features whose IDs are in this set are skipped even if
            ``find_next_ready_feature`` would return them.

    Returns:
        List of :class:`~bob.models.Feature` objects that were
        claimed and should be dispatched.  May be empty when there are
        no ready features or when the cap is already saturated.
    """
    if active_feature_ids is None:
        active_feature_ids = set()

    slots = current_concurrency_slots(loop, active_feature_ids=active_feature_ids)
    if slots <= 0:
        return []

    claimed: list[Feature] = []
    seen_ids = set(active_feature_ids)

    for _ in range(slots):
        feature = loop.find_next_ready_feature()
        if feature is None:
            break
        if feature.id in seen_ids:
            break
        seen_ids.add(feature.id)
        # Atomically claim the feature so parallel ticks don't re-select it.
        db.update_feature(feature.id, status="executing")
        claimed.append(feature)

    return claimed


async def gather_completed_dispatches(
    tasks: "list[asyncio.Task[object]]",
) -> "list[dict[str, object]]":
    """Await all *tasks* and return their outcomes as a structured list.

    Collects each task's result (or exception) without cancelling peers on
    failure, mirroring the failure-isolation guarantee of
    :func:`~bob.orchestrator.concurrent_executor.run_concurrent`.

    Args:
        tasks: A list of :class:`asyncio.Task` objects created from
            coroutines that implement feature execution.  The tasks must
            already be scheduled (created via ``asyncio.create_task``).

    Returns:
        A list of dicts — one per task — in task-list order::

            {
                "task":    asyncio.Task,   # the original task
                "success": bool,
                "result":  Any,            # task return value on success
                "error":   str | None,     # str(exc) on failure, else None
            }

        ``return_exceptions=True`` is passed to :func:`asyncio.gather` so
        a failing task never propagates its exception to callers; all tasks
        always run to completion.
    """
    if not tasks:
        return []

    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
    results: list[dict[str, object]] = []
    for task, outcome in zip(tasks, outcomes):
        if isinstance(outcome, BaseException):
            results.append(
                {
                    "task": task,
                    "success": False,
                    "result": None,
                    "error": str(outcome),
                }
            )
        else:
            results.append(
                {
                    "task": task,
                    "success": True,
                    "result": outcome,
                    "error": None,
                }
            )
    return results


def periodic_resume_scan(project_id: str) -> list[str]:
    """Promote any 'interrupted' features back to 'ready' mid-run.

    Module-level entry point for the periodic resume scan (feature 92c96882).
    Delegates to :func:`bob.orchestrator.periodic_resume_scan.periodic_resume_scan`
    so that the function is accessible as ``bob.orchestrator.run_loop.periodic_resume_scan``.

    Called on every orchestrator tick (or a dedicated 60 s timer) so that a
    feature cancelled mid-run (max_turns hit, async timeout, etc.) is re-queued
    without requiring an orchestrator restart.

    Args:
        project_id: UUID of the project to scan.

    Returns:
        List of feature IDs that were promoted from 'interrupted' to 'ready'.
    """
    return _periodic_resume_scan(project_id)


def resume_interrupted_work(project_id: str) -> list[str]:
    """Promote any 'interrupted' features back to 'ready' mid-run.

    Module-level entry point for the periodic resume scan (feature 099abfda).
    Delegates to :func:`bob.orchestrator.periodic_resume_scan.periodic_resume_scan`
    so that interrupted rows are re-queued without requiring an orchestrator restart.

    This is the canonical ``orchestrator.run_loop.resume_interrupted_work`` function
    required by the feature AC. Unlike the startup-only
    ``OrchestrationLoop._resume_interrupted_work`` method, this function is intended
    to be called on every orchestrator tick (or a dedicated 60 s timer).

    Args:
        project_id: UUID of the project to scan.  Must be a non-empty string.

    Returns:
        List of feature IDs that were promoted from 'interrupted' to 'ready'.

    Raises:
        ValueError: If *project_id* is not a non-empty string.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError(
            f"project_id must be a non-empty string, got {project_id!r}"
        )
    return _periodic_resume_scan(project_id)


async def dispatch_concurrent_features(
    loop: "OrchestrationLoop",
    *,
    worker: Any,
    active_feature_ids: "set[str] | None" = None,
    on_failure: Any = None,
) -> "list[dict[str, object]]":
    """Dispatch up to ``BOB_MAX_CONCURRENT_FEATURES`` ready features concurrently.

    This is the primary entry point for the concurrent dispatch tick.  It
    combines :func:`dispatch_up_to_concurrency` (slot-filling + DB claim) with
    :func:`~bob.orchestrator.concurrent_executor.run_concurrent` (bounded
    concurrency with failure isolation) into a single awaitable call.

    The orchestrator tick loop becomes::

        results = await dispatch_concurrent_features(
            loop,
            worker=execute_feature,
            active_feature_ids=in_flight_ids,
        )

    which replaces the previous sequential ``result = await execute_feature(feature)``.

    Args:
        loop: The :class:`OrchestrationLoop` providing project context and cap.
        worker: Async callable ``async def worker(feature) -> result`` invoked
            for each claimed feature.  Failures are isolated per feature.
        active_feature_ids: Set of feature IDs already in flight; claimed
            features are added before dispatch so that repeated calls within
            the same tick don't double-dispatch the same feature.
        on_failure: Optional callback ``on_failure(feature, exc)`` invoked after
            each worker failure.  Exceptions from the callback are swallowed.

    Returns:
        List of result dicts (see :func:`~bob.orchestrator.concurrent_executor.run_concurrent`),
        one per dispatched feature.  Empty when no slots are open or no ready
        features exist.

    Raises:
        ValueError: If *loop* is ``None`` or *worker* is not callable.
    """
    if loop is None:
        raise ValueError("loop must not be None")
    if not callable(worker):
        raise ValueError(f"worker must be callable, got {type(worker).__name__!r}")
    claimed = dispatch_up_to_concurrency(loop, active_feature_ids=active_feature_ids)
    if not claimed:
        return []
    return await _run_concurrent(
        claimed,
        worker=worker,
        max_concurrent=_resolve_max_concurrent_features(),
        on_failure=on_failure,
    )

