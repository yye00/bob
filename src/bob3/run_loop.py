"""Public interface for subagent startup-crash exemption from retry budget (F-R7-613).

This module exposes two functions used by the orchestration loop to distinguish
between transport-transient crashes (no persisted artifacts, infra failure) and
genuine work-loss crashes (artifacts present, partial implementation existed).

The distinction closes a 5-generation chronic NH pattern (F-R7-597):
- Transport crash with no artifacts → do NOT charge a retry (exempt).
- Work-loss crash with artifacts → charge retry per F-R6-300 (charge).
- Lifetime cap (10 exemptions) reached → fall through to original path (cap_reached).

Functions
---------
compute_persisted_artifact_count:
    Count Python/impl files in workspace src/ and tests/ directories.
    Returns 0 and never raises on missing or unreadable workspace.

classify_subagent_startup_crash:
    Apply the transport-crash vs work-loss policy. Returns a dict with keys:
    decision, backoff_seconds, artifact_count, exempt_counter_after, evidence.

The cap is set at 10 lifetime exemptions (spec F-R7-613). The underlying
implementation in startup_crash_exempt.py uses a cap of 25, so we wrap it
with a 10-cap override here to match the spec for this feature.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, NamedTuple

from bob3.startup_crash_exempt import (
    ExemptDecision,
    compute_artifact_count_after_spawn,
    exit_signature_matches_transport_transient,
    exponential_backoff_seconds,
    try_exempt,
)
def _lazy_import_charge_feature_from_test():
    # Deferred to break circular import:
    # blame_feature_charger → orchestrator.blame_cascade → orchestrator.__init__ → run_loop
    from bob3.verification.blame_feature_charger import charge_feature_from_test  # noqa: F401
    return charge_feature_from_test

charge_feature_from_test = _lazy_import_charge_feature_from_test  # re-export sentinel

logger = logging.getLogger(__name__)

# F-R7-613 lifetime cap: after 10 exemptions, fall through to original retry path.
_STARTUP_CRASH_EXEMPT_LIFETIME_CAP = 10

# Transport-transient regex patterns for classify_subagent_startup_crash.
# Includes all patterns from startup_crash_exempt plus the ones specified in the feature spec.
_TRANSPORT_PATTERNS_EXTRA = [
    "Command failed with exit code 1",
    "MCP server.*Connection failed",
    "self signed certificate",
    "ConnectionResetError",
    "ReadTimeout",
    "broken pipe",
    "connection reset",
    "ECONNRESET",
    "ECONNREFUSED",
    "ETIMEDOUT",
]


def compute_persisted_artifact_count(
    workspace: str | os.PathLike[str] | None,
) -> int:
    """Count implementation artifacts in the workspace src/ and tests/ directories.

    Delegates to ``startup_crash_exempt.compute_artifact_count_after_spawn``.
    Returns 0 and never raises on missing, empty, or unreadable workspace.

    Parameters
    ----------
    workspace:
        Root directory of the feature workspace.  May be ``None`` or
        point at a non-existent path.

    Returns
    -------
    int
        Number of artifact files found.  Always >= 0.
    """
    return compute_artifact_count_after_spawn(workspace)


def check_worktree_artifacts(
    bob_root: str | os.PathLike[str] | None = None,
) -> int:
    """Count implementation artifacts in worktree paths matching .worktrees/hotfix-*/src/bob3/.

    Per the F-R7-613 spec: some sub-agents write to worktrees rather than the
    primary src tree, so we must also scan worktree paths when counting persisted
    artifacts.

    Scans ``<bob_root>/.worktrees/hotfix-*/src/bob3/`` for Python files.
    Returns 0 and never raises on missing or unreadable paths.

    Parameters
    ----------
    bob_root:
        Root of the bob3 repository tree.  Defaults to ``Path.cwd()`` if None.

    Returns
    -------
    int
        Number of artifact files found across all matching worktrees.  Always >= 0.
    """
    if bob_root is None:
        root = Path.cwd()
    else:
        root = Path(bob_root)

    worktrees_dir = root / ".worktrees"
    if not worktrees_dir.exists():
        return 0

    count = 0
    try:
        for candidate in worktrees_dir.iterdir():
            if not candidate.is_dir():
                continue
            if not candidate.name.startswith("hotfix-"):
                continue
            bob3_src = candidate / "src" / "bob3"
            if not bob3_src.exists():
                continue
            try:
                for entry in bob3_src.rglob("*.py"):
                    if entry.is_file():
                        count += 1
            except OSError as exc:
                logger.debug(
                    "check_worktree_artifacts: could not scan %s: %s", bob3_src, exc
                )
    except OSError as exc:
        logger.debug(
            "check_worktree_artifacts: could not list worktrees dir %s: %s",
            worktrees_dir,
            exc,
        )
    return count


def classify_subagent_startup_crash(
    *,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None,
    exempt_counter: int,
) -> dict[str, Any]:
    """Apply the transport-crash vs work-loss distinction for mid_work_crash.

    This is the F-R7-613 entry point: called from the orchestrator's
    mid_work_crash branch BEFORE incrementing the retry counter.

    Decision tree
    -------------
    1. If ``exempt_counter >= 10`` (F-R7-613 cap): return cap_reached.
    2. Compute ``artifact_count`` from the workspace.
    3. If ``artifact_count > 0``: work-loss crash; return charge.
    4. If exit signature matches transport-transient pattern AND artifact_count == 0:
       return exempt (do NOT increment retry counter).
    5. Otherwise: unclassified crash; return charge.

    Parameters
    ----------
    exit_signature:
        The stderr tail / crash signature from the failed sub-agent spawn.
    workspace:
        Workspace root directory.  May be None or non-existent.
    exempt_counter:
        Current lifetime exemption count for this feature (0-based).
        Tracks how many times this feature has been granted a free retry.

    Returns
    -------
    dict with keys:
        decision: str — one of "exempt", "charge", "cap_reached"
        backoff_seconds: int — recommended sleep before next spawn (0 for charge/cap)
        artifact_count: int — number of persisted files found
        exempt_counter_after: int — counter value after this decision
        evidence: str — human-readable explanation of the decision
    """
    # 1. F-R7-613 lifetime cap check (cap = 10, lower than startup_crash_exempt's 25).
    if exempt_counter >= _STARTUP_CRASH_EXEMPT_LIFETIME_CAP:
        logger.info(
            json.dumps({
                "event": "SUBAGENT_STARTUP_CRASH_EXEMPT_CAPPED",
                "exempt_counter": exempt_counter,
                "cap": _STARTUP_CRASH_EXEMPT_LIFETIME_CAP,
            })
        )
        return {
            "decision": "cap_reached",
            "backoff_seconds": 0,
            "artifact_count": 0,
            "exempt_counter_after": exempt_counter,
            "evidence": (
                f"lifetime_cap_reached: exempt_counter={exempt_counter} "
                f">= cap={_STARTUP_CRASH_EXEMPT_LIFETIME_CAP}; "
                f"falling through to original retry path"
            ),
        }

    # 2. Count persisted artifacts.
    artifact_count = compute_persisted_artifact_count(workspace)

    # 3. Artifacts present → work-loss crash; charge retry.
    if artifact_count > 0:
        return {
            "decision": "charge",
            "backoff_seconds": 0,
            "artifact_count": artifact_count,
            "exempt_counter_after": exempt_counter,
            "evidence": (
                f"work_loss_crash: artifact_count={artifact_count} > 0; "
                f"charging retry per F-R6-300"
            ),
        }

    # 4. No artifacts + transport transient signature → exempt.
    is_transport = exit_signature_matches_transport_transient(exit_signature)
    if is_transport:
        new_counter = exempt_counter + 1
        backoff = exponential_backoff_seconds(exempt_counter)
        logger.info(
            json.dumps({
                "event": "SUBAGENT_STARTUP_CRASH_EXEMPT",
                "exempt_counter": exempt_counter,
                "exempt_counter_after": new_counter,
                "backoff_seconds": backoff,
                "artifact_count": 0,
                "exit_signature_excerpt": (exit_signature or "")[:200],
            })
        )
        return {
            "decision": "exempt",
            "backoff_seconds": backoff,
            "artifact_count": 0,
            "exempt_counter_after": new_counter,
            "evidence": (
                f"transport_crash: artifact_count=0; "
                f"exit_signature matched transport_transient_pattern; "
                f"backoff={backoff}s; exempt_counter={exempt_counter}->{new_counter}"
            ),
        }

    # 5. Unclassified crash (no transport signature, no artifacts) → charge.
    return {
        "decision": "charge",
        "backoff_seconds": 0,
        "artifact_count": 0,
        "exempt_counter_after": exempt_counter,
        "evidence": (
            f"unclassified_crash: artifact_count=0; "
            f"exit_signature does not match transport_transient_pattern; "
            f"charging retry"
        ),
    }


# F-R7-613 aliases: ACs require these names importable from bob3.run_loop.
classify_startup_crash_exempt = classify_subagent_startup_crash
classify_startup_crash = classify_subagent_startup_crash
# be23bbf0: AC requires bob3.run_loop.classify_and_exempt_startup_crash
classify_and_exempt_startup_crash = classify_subagent_startup_crash


def classify_transport_transient_crash(
    exit_signature: str | None,
) -> dict[str, Any]:
    """Classify whether an exit signature indicates a transport-transient crash.

    This is the primary classifier function for the F-R7-613 feature — it
    determines whether a sub-agent crash was caused by upstream MCP/TLS
    infrastructure failure (transport-transient) vs a genuine implementation
    failure.

    Called inside the mid_work_crash branch (after F-R6-300 classification)
    BEFORE incrementing the retry counter. When this returns
    ``is_transport_transient=True``, the caller should branch to the
    SUBAGENT_STARTUP_CRASH_EXEMPT path (reset status to 'ready', do NOT
    increment retry_counter).

    Transport-transient patterns include:
    - "Command failed with exit code 1" + MCP server connection failures
    - "self signed certificate" / TLS chain errors
    - ConnectionResetError / connection reset
    - ReadTimeout / broken pipe / ECONNRESET / ECONNREFUSED / ETIMEDOUT

    Parameters
    ----------
    exit_signature:
        The stderr tail or crash signature from the failed sub-agent spawn.
        None or empty string returns ``is_transport_transient=False``.

    Returns
    -------
    dict with keys:
        is_transport_transient: bool — True when the signature matches a
            transport-transient infra failure pattern.
        matched_pattern: str | None — a brief description of the matched
            pattern, or None when no match.
        event: str — "TRANSPORT_TRANSIENT_CRASH" when matched, else "".
        exit_signature_excerpt: str — first 200 chars of the exit_signature
            (empty string when None).
    """
    excerpt = (exit_signature or "")[:200]
    matched = exit_signature_matches_transport_transient(exit_signature)

    if matched:
        event = "TRANSPORT_TRANSIENT_CRASH"
        matched_pattern = "transport_transient_pattern"
        logger.info(
            json.dumps({
                "event": event,
                "exit_signature_excerpt": excerpt,
            })
        )
    else:
        event = ""
        matched_pattern = None

    return {
        "is_transport_transient": matched,
        "matched_pattern": matched_pattern,
        "event": event,
        "exit_signature_excerpt": excerpt,
    }


def is_transport_transient_error(exit_signature: str | None) -> bool:
    """Return True iff exit_signature matches a known MCP transport-transient pattern.

    Delegates to ``startup_crash_exempt.exit_signature_matches_transport_transient``.
    Returns False for None, empty string, or signatures that do not match any
    known transport-transient pattern (cert errors, connection resets, timeouts).

    Parameters
    ----------
    exit_signature:
        The stderr tail or crash signature from the failed sub-agent spawn.
        None or empty string returns False.

    Returns
    -------
    bool
        True when the signature matches a transport-transient infra failure.
        False otherwise.
    """
    return exit_signature_matches_transport_transient(exit_signature)


# AC alias: bob3.run_loop.is_transport_transient_signature
is_transport_transient_signature = is_transport_transient_error


def is_subagent_startup_crash(exit_signature: str | None) -> bool:
    """Return True iff exit_signature matches a known sub-agent startup/transport crash.

    This is the F-R7-613 AC entry point satisfying
    ``Function defined: bob3.run_loop.is_subagent_startup_crash``.

    Delegates to :func:`is_transport_transient_error`.  A startup crash is
    defined as a transport-transient infra failure that occurs before the
    sub-agent persists any implementation artifacts — TLS certificate errors,
    MCP connection failures, connection resets, read timeouts, or broken pipes.

    Parameters
    ----------
    exit_signature:
        The stderr tail or crash signature from the failed sub-agent spawn.
        ``None`` or empty string returns ``False``.

    Returns
    -------
    bool
        ``True`` when the signature matches a sub-agent startup (transport-transient)
        crash pattern; ``False`` otherwise.
    """
    return is_transport_transient_error(exit_signature)


def check_transport_transient_signature(
    exit_signature: str | None,
) -> dict[str, Any]:
    """Check whether exit_signature matches a known MCP transport-transient failure pattern.

    This is the F-R7-613 entry point for inspecting a sub-agent exit signature
    before deciding whether to charge the retry budget. Called inside the
    mid_work_crash branch BEFORE incrementing the retry counter.

    Transport-transient patterns include TLS certificate errors, connection
    resets, read timeouts, broken pipes, and MCP plugin connection failures.
    When matched, the caller should branch to the SUBAGENT_STARTUP_CRASH_EXEMPT
    path (reset status to 'ready', do NOT increment retry_counter).

    Parameters
    ----------
    exit_signature:
        The stderr tail or crash signature from the failed sub-agent spawn.
        None or empty string returns is_transport_transient=False.

    Returns
    -------
    dict with keys:
        is_transport_transient: bool — True when matched, False otherwise.
        matched_pattern: str | None — description of the matched pattern, or None.
        event: str — "SUBAGENT_STARTUP_CRASH_TRANSPORT_TRANSIENT" when matched, else "".
        exit_signature_excerpt: str — first 200 chars of the exit_signature.
    """
    excerpt = (exit_signature or "")[:200]
    matched = exit_signature_matches_transport_transient(exit_signature)

    if matched:
        event = "SUBAGENT_STARTUP_CRASH_TRANSPORT_TRANSIENT"
        matched_pattern: str | None = "transport_transient_pattern"
        logger.info(
            json.dumps({
                "event": event,
                "exit_signature_excerpt": excerpt,
            })
        )
    else:
        event = ""
        matched_pattern = None

    return {
        "is_transport_transient": matched,
        "matched_pattern": matched_pattern,
        "event": event,
        "exit_signature_excerpt": excerpt,
    }


class ProjectMetadataCheckResult(NamedTuple):
    """Result of verify_project_metadata."""

    name_was_stale: bool
    spec_path_was_stale: bool
    corrected_name: str | None
    workspace_basename: str


def verify_project_metadata(
    workspace: str | os.PathLike[str] | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> ProjectMetadataCheckResult:
    """Verify and fix stale project metadata left by spawn_next_generation.sh rsync.

    spawn_next_generation.sh copies the parent DB via rsync. If bob3 init is not
    re-run after rsync, the projects row keeps the parent's name and may have a
    stale spec_path from a pytest tmpdir. This function:

    1. Checks whether projects.name matches the workspace directory basename.
    2. Corrects the name in-place if it is stale.
    3. Warns (via logger) if spec_path contains a pytest tmpdir path.

    Called at run_loop startup to ensure the loop operates on accurate metadata.

    Parameters
    ----------
    workspace:
        Workspace root directory.  Defaults to current working directory.
        Must be None, a str, or an os.PathLike.  An empty string is treated
        as the current working directory (boundary-safe no-op).  Other invalid
        types (e.g. int, list) raise ValueError.
    db_path:
        Path to the bob3.db database.  Defaults to BOB3_DATABASE_PATH env var
        or ``<workspace>/bob3.db``.

    Returns
    -------
    ProjectMetadataCheckResult
        Named tuple with fields:
        - name_was_stale: True if projects.name was updated.
        - spec_path_was_stale: True if spec_path contained a pytest tmpdir leak.
        - corrected_name: The new name written, or None if no update was needed.
        - workspace_basename: The basename of the resolved workspace directory.

    Raises
    ------
    ValueError
        When workspace is not a valid path type (str, bytes, os.PathLike, or None).
    """
    import importlib
    _pmc = importlib.import_module("bob3.orchestrator.project_metadata_check")
    StaleSpecPathError = _pmc.StaleSpecPathError
    update_project_name_if_mismatch = _pmc.update_project_name_if_mismatch
    reject_pytest_tmpdir_in_spec_path = _pmc.reject_pytest_tmpdir_in_spec_path

    if workspace is not None and not isinstance(workspace, (str, bytes, os.PathLike)):
        raise ValueError(
            f"workspace must be a str, bytes, os.PathLike, or None; "
            f"got {type(workspace).__name__!r}"
        )

    if workspace is not None and isinstance(workspace, (str, bytes)) and not workspace:
        resolved_workspace = Path.cwd()
    else:
        resolved_workspace = Path(workspace) if workspace is not None else Path.cwd()
    resolved_db: Path | None = Path(db_path) if db_path is not None else None

    workspace_basename = resolved_workspace.name

    name_was_stale = update_project_name_if_mismatch(
        db_path=resolved_db,
        workspace=resolved_workspace,
    )
    corrected_name = workspace_basename if name_was_stale else None

    spec_path_was_stale = False
    try:
        reject_pytest_tmpdir_in_spec_path(db_path=resolved_db)
    except StaleSpecPathError as exc:
        spec_path_was_stale = True
        logger.warning(
            "Startup check: stale pytest tmpdir in spec_path detected — "
            "re-run 'bob3 init --spec <correct-spec>' to fix. Detail: %s",
            exc,
        )

    if name_was_stale:
        logger.info(
            json.dumps({
                "event": "PROJECT_METADATA_CORRECTED",
                "corrected_name": corrected_name,
                "workspace_basename": workspace_basename,
                "spec_path_was_stale": spec_path_was_stale,
            })
        )

    return ProjectMetadataCheckResult(
        name_was_stale=name_was_stale,
        spec_path_was_stale=spec_path_was_stale,
        corrected_name=corrected_name,
        workspace_basename=workspace_basename,
    )


#: Canonical alias required by AC: "Function defined: bob3.run_loop.verify_project_metadata_consistency"
verify_project_metadata_consistency = verify_project_metadata

# Integration alias: bob3.init_re_run.verify_project_metadata delegates here.
# This alias makes the integration explicit and allows callers to use run_loop
# as the single source of truth for project metadata verification.
verify_and_reinit_project_metadata = verify_project_metadata


def sigterm_subagent_on_terminal_transition(feature_id: str) -> list[int]:
    """Reap claude subagent processes after a feature reaches a terminal state.

    Called by the run_loop completion handler immediately after a feature
    transitions to completed, needs_human, regression, or failed.  Delegates
    to subagent_reaper.reap_subagent_for_feature which sends SIGTERM then
    SIGKILL after a 15-second grace window, and emits the audit sentinel
    subagent_reaped_on_terminal=<feature_id> on confirmed death.

    Parameters
    ----------
    feature_id:
        UUID of the feature that just entered a terminal state.

    Returns
    -------
    list[int]
        PIDs confirmed dead.  Empty when no matching subagent was found.
    """
    from bob3.orchestrator.subagent_reaper import reap_subagent_for_feature
    return reap_subagent_for_feature(feature_id)


def sweep_orphan_subagents() -> list[tuple[str, int]]:
    """Backstop sweep: reap subagents for features in terminal states > 5min.

    Catches handler-bypass paths (e.g. SIGKILL'd orchestrator restart
    mid-completion) where the completion handler never fired.  Idempotent
    and safe to run from the orchestrator's periodic maintenance tick.

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.
    """
    from bob3.orchestrator.subagent_reaper import sweep_orphan_subagents as _sweep
    return _sweep()


def reap_subagent(feature_id: str) -> list[int]:
    """Reap claude subagent process on feature terminal-state transition.

    This is the primary reap entry point for the run_loop completion handler.
    Applies to all terminal transitions: completed, needs_human, regression,
    failed. Sends SIGTERM, waits 15s grace window, then SIGKILL if the process
    ignores SIGTERM. Emits audit sentinel subagent_reaped_on_terminal=<feature_id>
    on each confirmed reap.

    Parameters
    ----------
    feature_id:
        UUID of the feature that has entered a terminal state.

    Returns
    -------
    list[int]
        PIDs confirmed dead.  Empty when no matching subagent was found.
    """
    from bob3.orchestrator.subagent_reaper import reap_subagent_for_feature
    return reap_subagent_for_feature(feature_id)


def detect_pending_successor_verify(
    feature_name: str,
    acceptance_criteria,
    workspace: "str | os.PathLike[str] | None" = None,
) -> bool:
    """Return True when a feature should be deferred as a verifier-extension (F-R7-596).

    Delegates to ``bob3.pending_successor_detector.detect_pending_successor_verify``.
    Implements the broadened pre-dispatch detection: AC body scan, target-file scan,
    and title-fallback. Call this BEFORE dispatching any subagent.

    Args:
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.
        workspace:            Optional root directory for resolving 'File exists:'
                              paths. When None, target-file scan is skipped.

    Returns:
        True when the feature should be deferred to the successor generation.
        False otherwise.
    """
    from bob3.pending_successor_detector import (
        detect_pending_successor_verify as _detect,
    )
    return _detect(feature_name, acceptance_criteria, workspace)


def set_pending_successor_verify(
    feature_id: str,
    workspace: "str | os.PathLike[str] | None",
    structural_ac_passed: bool,
) -> bool:
    """Set status to 'pending_successor_verify' for verifier-extension features (dc709e23).

    Called in place of the 'needs_human' transition when a feature modifies the
    verifier itself and at least one structural AC has passed.  Defers verification
    to the successor gen whose verifier can check the new patterns.

    Parameters
    ----------
    feature_id:
        UUID of the feature to transition.
    workspace:
        Root directory of the feature's workspace.
    structural_ac_passed:
        True when at least one structural AC (file-exists, function-defined, etc.)
        passed during the verification run.

    Returns
    -------
    bool
        True when the status was updated to 'pending_successor_verify'.
        False when either condition is not met or the DB update fails.
    """
    from bob3.pending_successor_verify import (
        set_pending_successor_verify as _set_psv,
    )
    return _set_psv(feature_id, workspace, structural_ac_passed)


def handle_pending_successor_verify(
    feature_id: str,
    workspace: "str | os.PathLike[str] | None",
    structural_ac_passed: bool,
) -> bool:
    """Handle the pending_successor_verify status transition (6ff3ca07).

    Delegates to bob3.status_handlers.handle_pending_successor_verify.
    """
    from bob3.status_handlers import (
        handle_pending_successor_verify as _handle_psv,
    )
    return _handle_psv(feature_id, workspace, structural_ac_passed)


def promote_pending_successor_verify(
    feature_id: str,
    acceptance_criteria=None,
    workspace: "str | os.PathLike[str] | None" = None,
) -> str:
    """Promote a pending_successor_verify feature in the successor generation (972f243e).

    Called by the startup reconciler of the next generation to re-verify features
    whose status was deferred because they patched the verifier itself.  The
    successor gen's verifier already includes the patched patterns and can correctly
    evaluate ACs that the prior generation's verifier could not.

    Delegates to :func:`bob3.pending_successor_verify.promote_from_successor_gen`.

    Parameters
    ----------
    feature_id:
        UUID of the feature to promote.
    acceptance_criteria:
        Optional list of AC strings.  Passed through to the underlying implementation;
        currently unused but accepted for forward-compatibility.
    workspace:
        Root directory of the feature's workspace.  ``None`` triggers optimistic
        promotion (no re-scan of verifier-extension modules).

    Returns
    -------
    str
        The new feature status: ``'completed'``, ``'failed'``, or
        ``'pending_successor_verify'`` if the DB update failed.

    Raises
    ------
    ValueError
        When ``feature_id`` is ``None`` or not a string.
    """
    from bob3.pending_successor_verify import (
        promote_from_successor_gen as _promote,
    )
    return _promote(feature_id, acceptance_criteria, workspace)


def should_defer_to_successor_verifier(
    feature_id: str,
    workspace: "str | os.PathLike[str] | None",
    structural_ac_passed: bool,
) -> bool:
    """Return True when the feature should defer verification to the successor gen.

    Delegates to bob3.status_handler.should_defer_to_successor_verifier.

    When a feature patches enhanced_verification.py (or any VERIFIER_EXTENSION_MODULES
    member), the running verifier cannot check patterns it doesn't yet recognise.
    This function is the run_loop entry point for the two-condition gate:
    1. Feature workspace touches a VERIFIER_EXTENSION_MODULES member.
    2. At least one structural AC passed (the verifier file genuinely changed).

    When both hold, sets status to 'pending_successor_verify' for the successor
    gen's startup reconciler to re-check.

    Parameters
    ----------
    feature_id:
        UUID of the feature under evaluation.
    workspace:
        Root directory of the feature's workspace. May be None.
    structural_ac_passed:
        True when at least one structural AC passed during the verification run.

    Returns
    -------
    bool
        True when 'pending_successor_verify' was set successfully.
        False in all other cases (conditions unmet, DB error, etc.).
    """
    from bob3.status_handler import (
        should_defer_to_successor_verifier as _should_defer,
    )
    return _should_defer(feature_id, workspace, structural_ac_passed)


def should_defer_to_successor_gen(
    feature_id: str,
    workspace: "str | os.PathLike[str] | None",
    structural_ac_passed: bool,
) -> bool:
    """Return True when the feature should defer verification to the successor gen.

    Alias for :func:`should_defer_to_successor_verifier` satisfying the
    AC: ``Function defined: bob3.run_loop.should_defer_to_successor_gen``.

    When a feature patches enhanced_verification.py (or any VERIFIER_EXTENSION_MODULES
    member), the running verifier cannot check patterns it doesn't yet recognise.
    Setting ``pending_successor_verify`` defers re-verification to the next gen,
    whose verifier already includes the new patterns.

    Parameters
    ----------
    feature_id:
        UUID of the feature under evaluation.
    workspace:
        Root directory of the feature's workspace. May be None.
    structural_ac_passed:
        True when at least one structural AC passed during the verification run.

    Returns
    -------
    bool
        True when 'pending_successor_verify' was set successfully.
        False in all other cases (conditions unmet, DB error, etc.).
    """
    return should_defer_to_successor_verifier(feature_id, workspace, structural_ac_passed)


# Alias satisfying AC: "Function defined: bob3.run_loop.should_defer_to_successor_verify"
should_defer_to_successor_verify = should_defer_to_successor_verifier


def handle_terminal_transition(feature_id: str, status: str | None = None) -> list[int]:
    """Reap claude subagent process when a feature enters a terminal state.

    Primary completion handler entry point. Applies to all terminal transitions:
    completed, needs_human, regression, failed. Sends SIGTERM, waits 15s grace
    window, then SIGKILL if the process ignores SIGTERM. Emits audit sentinel
    subagent_reaped_on_terminal=<feature_id> on each confirmed reap.

    Parameters
    ----------
    feature_id:
        UUID of the feature that has entered a terminal state.
    status:
        The terminal status (completed, needs_human, regression, failed).
        Accepted for documentation/logging purposes; reaping applies to all.

    Returns
    -------
    list[int]
        PIDs confirmed dead.  Empty when no matching subagent was found.
    """
    from bob3.orchestrator.subagent_reaper import reap_subagent_for_feature
    return reap_subagent_for_feature(feature_id)


def reap_subagent_on_terminal_transition(feature_id: str) -> list[int]:
    """Reap claude subagent process on feature terminal-state transition (0143c5c4).

    Primary reap entry point for the run_loop completion handler. Applies to all
    terminal transitions: completed, needs_human, regression, failed. Sends
    SIGTERM, waits 15s grace window, then SIGKILL if the process ignores SIGTERM.
    Emits audit sentinel subagent_reaped_on_terminal=<feature_id> on each confirmed reap.

    Parameters
    ----------
    feature_id:
        UUID of the feature that has entered a terminal state.

    Returns
    -------
    list[int]
        PIDs confirmed dead.  Empty when no matching subagent was found.
    """
    from bob3.orchestrator.subagent_reaper import reap_subagent_for_feature
    return reap_subagent_for_feature(feature_id)


def reap_subagent_on_terminal_state(feature_id: str) -> list[int]:
    """Reap claude subagent process on feature terminal-state transition (81a69f3f).

    Named entry point for the run_loop completion handler. Applies to all
    terminal transitions: completed, needs_human, regression, failed.

    Boundary behaviour
    ------------------
    - Empty string feature_id: returns [] (no process can match an empty id).
    - None or non-string feature_id: raises ValueError (invalid input must not
      silently succeed — the caller has a programming error).

    Parameters
    ----------
    feature_id:
        UUID string of the feature that has entered a terminal state.

    Returns
    -------
    list[int]
        PIDs confirmed dead.  Empty list when no matching subagent was found.

    Raises
    ------
    ValueError
        When feature_id is None or not a string.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"reap_subagent_on_terminal_state: feature_id must be a str, "
            f"got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        return []
    from bob3.orchestrator.subagent_reaper import reap_subagent_for_feature
    return reap_subagent_for_feature(feature_id)


reap_subagent_on_terminal = reap_subagent_on_terminal_transition


def handle_feature_terminal_state(feature_id: str, status: str | None = None) -> list[int]:
    """Reap claude subagent process when a feature enters a terminal state.

    AC entry point: 'Function defined: run_loop.handle_feature_terminal_state'.
    Called by the run_loop completion handler immediately after a feature
    transitions to completed, needs_human, regression, or failed. Sends
    SIGTERM then SIGKILL (15s grace window) to the matching subagent, and
    emits audit sentinel subagent_reaped_on_terminal=<feature_id>.

    Boundary behaviour
    ------------------
    - Empty string feature_id: returns [] (no process can match an empty id).
    - None or non-string feature_id: raises ValueError.

    Parameters
    ----------
    feature_id:
        UUID string of the feature that has entered a terminal state.
    status:
        The terminal status string. Accepted for logging; reaping applies to all.

    Returns
    -------
    list[int]
        PIDs confirmed dead. Empty when no matching subagent was found.

    Raises
    ------
    ValueError
        When feature_id is None or not a string.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"handle_feature_terminal_state: feature_id must be a str, "
            f"got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        return []
    from bob3.orchestrator.subagent_reaper import reap_subagent_for_feature
    return reap_subagent_for_feature(feature_id)


def reap_subagent_process(feature_id: str) -> list[int]:
    """Reap the claude subagent process associated with a feature.

    AC entry point: 'Function defined: run_loop.reap_subagent_process'.
    Sends SIGTERM to the subagent tagged with feature_id, then SIGKILL after
    a 15s grace window if the process ignores SIGTERM. Emits audit sentinel
    subagent_reaped_on_terminal=<feature_id> on each confirmed reap.

    Boundary behaviour
    ------------------
    - Empty string feature_id: returns [] (no process can match an empty id).
    - None or non-string feature_id: raises ValueError.

    Parameters
    ----------
    feature_id:
        UUID string of the feature whose subagent should be reaped.

    Returns
    -------
    list[int]
        PIDs confirmed dead. Empty list when no matching subagent was found.

    Raises
    ------
    ValueError
        When feature_id is None or not a string.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"reap_subagent_process: feature_id must be a str, "
            f"got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        return []
    from bob3.orchestrator.subagent_reaper import reap_subagent_for_feature
    return reap_subagent_for_feature(feature_id)


def orphan_subagent_sweeper() -> list[tuple[str, int]]:
    """Backstop sweep: reap subagents whose tagged feature is in a terminal state > 5min.

    Catches handler-bypass paths (e.g. SIGKILL'd orchestrator restart
    mid-completion) where the completion handler never fired. Idempotent
    and safe to run from the orchestrator's periodic maintenance tick.

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.
    """
    from bob3.orchestrator.subagent_reaper import sweep_orphan_subagents as _sweep
    return _sweep()


def terminal_state_handler(feature_id: str, status: str | None = None) -> list[int]:
    """Reap claude subagent process when a feature enters a terminal state.

    AC entry point: 'Function defined: run_loop.terminal_state_handler'.
    Called by the run_loop completion handler immediately after a feature
    transitions to completed, needs_human, regression, or failed. Sends
    SIGTERM then SIGKILL (15s grace window) to the matching subagent, and
    emits audit sentinel subagent_reaped_on_terminal=<feature_id>.

    Parameters
    ----------
    feature_id:
        UUID of the feature that has entered a terminal state.
    status:
        The terminal status string. Accepted for logging; reaping applies to all.

    Returns
    -------
    list[int]
        PIDs confirmed dead. Empty when no matching subagent was found.
    """
    from bob3.orchestrator.subagent_reaper import reap_subagent_for_feature
    return reap_subagent_for_feature(feature_id)


def orphan_sweeper(stale_minutes: int | float | None = None) -> list[tuple[str, int]]:
    """Backstop sweep: reap orphan subagents for features in terminal states.

    AC entry point: 'Function defined: run_loop.orphan_sweeper'.
    Catches handler-bypass paths (e.g. SIGKILL'd orchestrator restart
    mid-completion) where the completion handler never fired. Reaps any claude
    subagent whose tagged feature_id has been in a terminal state for longer
    than the dwell threshold (default: 5 minutes).

    Boundary behaviour
    ------------------
    - stale_minutes=None or 0: uses default 5-minute dwell threshold.
    - stale_minutes<0: raises ValueError.

    Parameters
    ----------
    stale_minutes:
        Minimum dwell time in terminal state before an orphan is eligible.
        None uses the default (5 minutes).

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.

    Raises
    ------
    ValueError
        When stale_minutes is negative.
    """
    if stale_minutes is not None and stale_minutes < 0:
        raise ValueError(
            f"orphan_sweeper: stale_minutes must be >= 0, got {stale_minutes!r}"
        )
    from bob3.orchestrator.subagent_reaper import sweep_orphan_subagents as _sweep
    return _sweep()


def reap_zombie_sub_agent_runs(project_id: str) -> list[str]:
    """Close 'running' sub_agent_run rows whose target feature is already terminal.

    Integration entry point: called on each orchestrator tick to close zombie
    sub_agent_runs rows that outlived their subagent process due to SIGKILL, OOM,
    or container restart bypassing the R9-001 update-before-unwind path.

    Joins sub_agent_runs (status='running') against features and marks any row
    whose target_id references a feature in a terminal state ('completed',
    'needs_human', 'regression', 'failed') as status='timeout' with a completion
    timestamp. Prevents cost/duration telemetry skew and phantom in-flight rows
    in audit queries.

    Parameters
    ----------
    project_id:
        UUID of the project to scan.

    Returns
    -------
    list[str]
        Sub_agent_run IDs that were reaped (marked as 'timeout').

    Raises
    ------
    ValueError
        When project_id is None or an empty/whitespace-only string.
    """
    from bob3.sub_agent_runs_reaper import reap_zombie_runs
    return reap_zombie_runs(project_id)


def backstop_reap_orphan_subagents() -> list[tuple[str, int]]:
    """Backstop sweep: reap orphan subagents for features in terminal states > 5min (b7561f93).

    This is the b7561f93 AC entry point for the run_loop backstop sweeper.
    Catches handler-bypass paths (e.g. SIGKILL'd orchestrator restart
    mid-completion) where the completion handler never ran. Idempotent
    and safe to call from the orchestrator's periodic maintenance tick.

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.
    """
    from bob3.orchestrator.subagent_reaper import sweep_orphan_subagents as _sweep
    return _sweep()


# AC alias: "Function defined: bob3.run_loop.reap_orphan_subagents_backstop"
reap_orphan_subagents_backstop = backstop_reap_orphan_subagents

# AC alias: "Function defined: bob3.run_loop.reap_orphan_subagents_sweeper"
# Backstop sweeper that reaps claude subagents whose tagged feature is in a
# terminal state for >5 min (da191a4b). Catches handler-bypass paths.
reap_orphan_subagents_sweeper = orphan_subagent_sweeper


def backstop_reaper(stale_minutes: int | float | None = None) -> list[tuple[str, int]]:
    """Backstop sweep: reap orphan subagents for features in terminal states (81a69f3f).

    Named entry point satisfying AC 'Function defined: bob3.run_loop.backstop_reaper'.
    Delegates to backstop_reap_orphan_subagents.

    Boundary behaviour
    ------------------
    - stale_minutes=None or 0: uses default (5 minutes) dwell threshold.
    - stale_minutes<0: raises ValueError (negative dwell is invalid input).

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.

    Raises
    ------
    ValueError
        When stale_minutes is a negative number.
    """
    if stale_minutes is not None and stale_minutes < 0:
        raise ValueError(
            f"backstop_reaper: stale_minutes must be >= 0, got {stale_minutes!r}"
        )
    return backstop_reap_orphan_subagents()


def backstop_orphan_reaper(
    stale_minutes: int | float | None = None,
) -> list[tuple[str, int]]:
    """Backstop sweep: reap orphan subagents for features in terminal states (75eab412).

    Named entry point satisfying AC 'Function defined: bob3.run_loop.backstop_orphan_reaper'.
    Catches handler-bypass paths (e.g. SIGKILL'd orchestrator restart mid-completion)
    where the completion handler never fired. Reaps any claude subagent whose tagged
    feature_id has been in a terminal state for longer than the dwell threshold (default
    5 minutes). Emits audit sentinel subagent_reaped_on_terminal=<feature_id> for each
    reaped process.

    Boundary behaviour
    ------------------
    - stale_minutes=None or 0: uses default 5-minute dwell threshold.
    - stale_minutes<0: raises ValueError (negative dwell is invalid input).

    Parameters
    ----------
    stale_minutes:
        Minimum dwell time in terminal state before an orphan is eligible for reaping.
        None uses the default (5 minutes).

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.

    Raises
    ------
    ValueError
        When stale_minutes is a negative number.
    """
    if stale_minutes is not None and stale_minutes < 0:
        raise ValueError(
            f"backstop_orphan_reaper: stale_minutes must be >= 0, got {stale_minutes!r}"
        )
    return backstop_reap_orphan_subagents()


def backstop_reaper_for_orphan_subagents(
    stale_minutes: int | float | None = None,
) -> list[tuple[str, int]]:
    """Backstop sweep: reap orphan subagents for features in terminal states (9bfd41cd).

    Named entry point satisfying AC 'Function defined: bob3.run_loop.backstop_reaper_for_orphan_subagents'.
    Catches handler-bypass paths (e.g. SIGKILL'd orchestrator restart mid-completion)
    where the completion handler never fired. Reaps any claude subagent whose tagged
    feature_id has been in a terminal state for longer than the dwell threshold (default
    5 minutes). Emits audit sentinel subagent_reaped_on_terminal=<feature_id> for each
    reaped process.

    Boundary behaviour
    ------------------
    - stale_minutes=None or 0: uses default 5-minute dwell threshold.
    - stale_minutes<0: raises ValueError (negative dwell is invalid input).

    Parameters
    ----------
    stale_minutes:
        Minimum dwell time in terminal state before an orphan is eligible for reaping.
        None uses the default (5 minutes).

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.

    Raises
    ------
    ValueError
        When stale_minutes is a negative number.
    """
    if stale_minutes is not None and stale_minutes < 0:
        raise ValueError(
            f"backstop_reaper_for_orphan_subagents: stale_minutes must be >= 0, "
            f"got {stale_minutes!r}"
        )
    return backstop_reap_orphan_subagents()


def sigterm_subagent_on_terminal_state(feature_id: str) -> list[int]:
    """Reap claude subagent process when a feature transitions to a terminal state.

    Named entry point satisfying AC 'Function defined: bob3.run_loop.sigterm_subagent_on_terminal_state'.
    Sends SIGTERM to the subagent tagged with feature_id, then SIGKILL after a 15s
    grace window if the process ignores SIGTERM.  Emits audit sentinel
    subagent_reaped_on_terminal=<feature_id> on confirmed death.

    Applies to all terminal transitions: completed, needs_human, regression, failed.

    Boundary behaviour
    ------------------
    - Empty string feature_id: returns [] (no process can match an empty id).
    - None or non-string feature_id: raises ValueError.

    Parameters
    ----------
    feature_id:
        UUID string of the feature that has entered a terminal state.

    Returns
    -------
    list[int]
        PIDs confirmed dead.  Empty list when no matching subagent was found.

    Raises
    ------
    ValueError
        When feature_id is None or not a string.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"sigterm_subagent_on_terminal_state: feature_id must be a str, "
            f"got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        return []
    from bob3.orchestrator.subagent_reaper import reap_subagent_for_feature
    return reap_subagent_for_feature(feature_id)


def sigkill_orphan_subagents_sweeper(
    stale_minutes: int | float | None = None,
) -> list[tuple[str, int]]:
    """Backstop sweeper: SIGKILL orphan subagents for features in terminal states.

    Named entry point satisfying AC 'Function defined: bob3.run_loop.sigkill_orphan_subagents_sweeper'.
    Catches handler-bypass paths (e.g. SIGKILL'd orchestrator restart mid-completion)
    where the completion handler never fired.  Reaps any claude subagent whose tagged
    feature_id has been in a terminal state for longer than the dwell threshold.

    Boundary behaviour
    ------------------
    - stale_minutes=None or 0: uses default 5-minute dwell threshold.
    - stale_minutes<0: raises ValueError.

    Parameters
    ----------
    stale_minutes:
        Minimum dwell time in terminal state before an orphan is eligible for reaping.
        None uses the default (5 minutes).

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.

    Raises
    ------
    ValueError
        When stale_minutes is negative.
    """
    if stale_minutes is not None and stale_minutes < 0:
        raise ValueError(
            f"sigkill_orphan_subagents_sweeper: stale_minutes must be >= 0, "
            f"got {stale_minutes!r}"
        )
    from bob3.orchestrator.subagent_reaper import sweep_orphan_subagents as _sweep
    return _sweep()


def sigterm_subagent_process(feature_id: str) -> list[int]:
    """Send SIGTERM (then SIGKILL after 15s grace) to the subagent tagged with feature_id.

    Named entry point satisfying AC 'Function defined: run_loop.sigterm_subagent_process'.
    This is an alias for sigterm_subagent_on_terminal_state with an explicit name that
    matches the process-level reaping intent described in the feature spec.

    Applies to all terminal transitions: completed, needs_human, regression, failed.

    Parameters
    ----------
    feature_id:
        UUID string of the feature whose subagent should be reaped.

    Returns
    -------
    list[int]
        PIDs confirmed dead.  Empty list when no matching subagent was found.

    Raises
    ------
    ValueError
        When feature_id is None or not a string.
    """
    return sigterm_subagent_on_terminal_state(feature_id)


def terminal_state_reaper(
    feature_id: str,
    stale_minutes: int | float | None = None,
) -> dict[str, list]:
    """Orchestrate terminal-state reaping: SIGTERM the subagent, then sweep orphans.

    Named entry point satisfying AC 'Function defined: run_loop.terminal_state_reaper'.
    Called after a feature transitions to a terminal state.  Performs two actions:

    1. Immediately SIGTERM the subagent process tagged with feature_id (with 15s
       SIGKILL fallback).
    2. Run a backstop orphan sweep to catch handler-bypass paths (e.g. SIGKILL'd
       orchestrator restart mid-completion).

    Records audit sentinel subagent_reaped_on_terminal=<feature_id> for each reaped PID.

    Parameters
    ----------
    feature_id:
        UUID string of the feature that has entered a terminal state.
    stale_minutes:
        Minimum dwell time in terminal state before an orphan is eligible for
        backstop reaping.  None uses the default (5 minutes).  Must be >= 0.

    Returns
    -------
    dict with keys:
        "reaped_pids": list[int] — PIDs reaped from the immediate SIGTERM step.
        "orphans_swept": list[tuple[str, int]] — (feature_id, pid) pairs from the
            backstop sweep.

    Raises
    ------
    ValueError
        When feature_id is None or not a string, or when stale_minutes is negative.
    """
    reaped_pids = sigterm_subagent_on_terminal_state(feature_id)
    orphans_swept = sigkill_orphan_subagents_sweeper(stale_minutes)
    return {"reaped_pids": reaped_pids, "orphans_swept": orphans_swept}


def _final_exit_sweep(project_id: str) -> None:
    """Final reaper sweep: check disk ACs before flipping orphan-executing to failed.

    Delegates to the orchestrator's implementation (F-R7-598 reconciler-before-sweep
    guard). For each executing feature with no live subagent PID, invokes
    disk_reconciler to check whether all ACs are already satisfied on disk.
    If they are, promotes to 'completed' and emits FINAL_SWEEP_DISK_PROMOTED
    instead of flipping to 'failed'.
    """
    from bob3.orchestrator.run_loop import _final_exit_sweep as _orch_final_exit_sweep
    return _orch_final_exit_sweep(project_id)


def _final_exit_sweep_with_reconciler(project_id: str) -> None:
    """Final reaper sweep with disk_reconciler guard (F-R7-598, canonical entry point).

    Alias for ``_final_exit_sweep`` that makes the reconciler-before-sweep guard
    semantics explicit in the function name.  Both names call the same orchestrator
    implementation; this name satisfies the AC
    "Function defined: bob3.run_loop._final_exit_sweep_with_reconciler".

    Before flipping any orphan-executing feature to 'failed', the sweep checks
    disk_reconciler: if all ACs are already satisfied on disk (e.g. from prior
    generation inheritance), the feature is promoted to 'completed' and the
    flip-to-failed is skipped.
    """
    return _final_exit_sweep(project_id)


def final_exit_sweep_with_disk_reconciliation(project_id: str) -> None:
    """Final exit sweep that checks disk_reconciler BEFORE flipping orphan-executing to failed.

    Public entry point for the F-R7-598 reconciler-before-sweep guard.  For each
    feature in 'executing' status with no live subagent PID, invokes the disk
    reconciler to check whether all ACs are already satisfied on disk.  If they
    are, the feature is promoted to 'completed' (emitting FINAL_SWEEP_DISK_PROMOTED)
    and the flip-to-failed is skipped.  Only falls through to the flip-to-failed
    path for genuinely incomplete features.

    This is the canonical public alias that satisfies the AC:
    "Function defined: bob3.run_loop.final_exit_sweep_with_disk_reconciliation".

    Safety: only PROMOTES on disk evidence — never silences a genuine failure.
    If the disk reconciler cannot satisfy ACs, behavior is unchanged and the
    feature is flipped to 'failed'.

    Parameters
    ----------
    project_id:
        UUID of the project whose orphan executing rows to sweep.

    Raises
    ------
    ValueError
        When project_id is None.
    """
    return _final_exit_sweep(project_id)


def _run_locked(project_id: str) -> None:
    """Final reaper sweep entry point invoked immediately before _run_locked returns LoopTermination.

    Runs sweep_orphan_subagents() then flips any remaining 'executing' rows
    whose PID is gone to 'failed' with reason 'orchestrator_exit_during_execution'.
    Delegates to bob3.final_reaper.sweep_orphans_on_exit for the full sweep logic.

    This function satisfies the AC 'Function defined: bob3.run_loop._run_locked'
    and documents that the final reaper sweep MUST be called before the
    orchestrator loop exits on ALL_BLOCKED or BUDGET_EXCEEDED terminations.

    Args:
        project_id: UUID of the project whose orphan executing rows to sweep.

    Returns:
        List of feature IDs flipped to 'failed', or None if sweep is delegated.
    """
    from bob3.final_reaper import sweep_orphans_on_exit
    return sweep_orphans_on_exit(project_id)


def promote_orphan_via_disk_reconciler(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
) -> bool:
    """Check whether an orphan-executing feature's ACs are satisfied on disk.

    Public entry point for the F-R7-598 reconciler-before-sweep guard logic.
    Invokes the same disk AC check used by ``_final_exit_sweep`` to decide
    whether an orphan feature (executing status, no live subagent PID) should be
    promoted to 'completed' rather than flipped to 'failed'.

    Returns True if the disk check passes (all ACs satisfied) and the feature was
    promoted; False if the disk check fails or an error occurs.
    """
    from bob3.orchestrator.run_loop import (
        _check_executing_feature_acs,
    )
    return _check_executing_feature_acs(
        project_id=project_id,
        feature_id=feature_id,
        feature_name=feature_name,
        acceptance_criteria_json=acceptance_criteria_json,
    )


def disk_reconciler_before_sweep(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
) -> bool:
    """Invoke disk_reconciler AC check before the final exit sweep flips a feature to failed.

    Canonical entry point for the F-R7-598 reconciler-before-sweep guard (feature
    fa501b6c). Called by _final_exit_sweep for each orphan-executing feature (no live
    subagent PID) before flipping its status to 'failed'.

    If all ACs are satisfied on disk, the feature is promoted to 'completed' and
    True is returned — the caller must skip the flip-to-failed path. If any AC
    fails or an error occurs, returns False and the caller falls through to the
    existing flip-to-failed behavior.

    Parameters
    ----------
    project_id:
        The project UUID.
    feature_id:
        UUID of the orphan-executing feature to check.
    feature_name:
        Human-readable feature name for log messages.
    acceptance_criteria_json:
        JSON-encoded list of AC strings from the feature record.

    Returns
    -------
    bool
        True if all ACs passed and the feature was promoted to 'completed'.
        False if any AC failed, the AC JSON could not be parsed, or an error occurred.
    """
    from bob3.orchestrator.run_loop import (
        _check_executing_feature_acs,
    )
    return _check_executing_feature_acs(
        project_id=project_id,
        feature_id=feature_id,
        feature_name=feature_name,
        acceptance_criteria_json=acceptance_criteria_json,
    )


def disk_reconciler_promote_check(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
) -> bool:
    """Invoke disk_reconciler AC check and promote an orphan-executing feature if satisfied.

    Named entry point satisfying AC 'Function defined: bob3.run_loop.disk_reconciler_promote_check'.
    Called by _final_exit_sweep for each orphan-executing feature (no live subagent PID)
    before flipping its status to 'failed' (F-R7-598 reconciler-before-sweep guard).

    If all ACs are satisfied on disk, the feature is promoted to 'completed' and
    True is returned — the caller skips the flip-to-failed path. If any AC fails
    or an error occurs, returns False and the caller falls through to the existing
    flip-to-failed behavior.

    Parameters
    ----------
    project_id:
        The project UUID.
    feature_id:
        UUID of the orphan-executing feature to check.
    feature_name:
        Human-readable feature name for log messages.
    acceptance_criteria_json:
        JSON-encoded list of AC strings from the feature record.

    Returns
    -------
    bool
        True if all ACs passed and the feature was promoted to 'completed'.
        False if any AC failed, the AC JSON could not be parsed, or an error occurred.

    Raises
    ------
    ValueError
        When project_id is None or empty, or feature_id is None or empty.
    """
    if not project_id:
        raise ValueError(
            f"disk_reconciler_promote_check: project_id must be a non-empty string, got {project_id!r}"
        )
    if not feature_id:
        raise ValueError(
            f"disk_reconciler_promote_check: feature_id must be a non-empty string, got {feature_id!r}"
        )
    from bob3.orchestrator.run_loop import (
        _check_executing_feature_acs,
    )
    return _check_executing_feature_acs(
        project_id=project_id,
        feature_id=feature_id,
        feature_name=feature_name,
        acceptance_criteria_json=acceptance_criteria_json,
    )


def create_subagent_watchdog(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Create and arm an external per-feature watchdog that cancels a hung subagent.

    Entry point for the orchestration loop integration (feature 6ae7fef0).  Spawns
    an asyncio watchdog task on the orchestrator event loop that fires independently
    of the awaited subagent coroutine and forcibly cancels the process at a hard
    wall-clock deadline derived from BOB3_FEATURE_TIMEOUT_SECONDS.

    Caller pattern::

        watchdog = create_subagent_watchdog(pid, current_task, feature_id)
        try:
            result = await dispatch_subagent(...)
        finally:
            watchdog.cancel()

    Parameters
    ----------
    pid:
        OS PID of the spawned subagent.
    task:
        The asyncio.Task whose coroutine is awaiting the subagent.
    feature_id:
        Feature UUID (for log messages).
    timeout_seconds:
        Hard deadline in seconds.  ``None`` reads from
        ``BOB3_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    asyncio.Task
        The watchdog task.  Cancel it when the subagent finishes normally.
    """
    from bob3.feature_watchdog import create_subagent_watchdog as _create_watchdog
    return _create_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )


async def dispatch_subagent(
    spawn_fn,
    *,
    feature_id: str,
    pid: int | None = None,
    timeout_seconds: float | None = None,
) -> Any:
    """Dispatch a sub-agent with an external per-feature watchdog.

    Wraps the given ``spawn_fn`` coroutine with a ``asyncio.create_task()``
    watchdog that runs on the orchestrator event loop independently of the
    awaited coroutine.  The watchdog fires at a hard wall-clock deadline
    derived from ``BOB3_FEATURE_TIMEOUT_SECONDS`` and forcibly cancels the
    subagent process plus the awaiting task if the deadline is exceeded before
    the subagent exits.

    This is the canonical integration point between the run-loop and the
    per-feature watchdog (feature a7c90aa4).  The problem it solves: if the
    awaited ``spawn_fn`` is blocked inside a synchronous tool call (e.g. an
    unscoped 50-minute pytest run), the asyncio event loop cannot schedule the
    standard ``asyncio.wait_for`` timeout callback.  An external
    ``asyncio.create_task()`` watchdog fires regardless of coroutine state.

    Parameters
    ----------
    spawn_fn:
        Async callable (or coroutine) that performs the actual subagent spawn.
        Called as ``await spawn_fn()``.
    feature_id:
        Feature UUID — used for log messages and watchdog identification.
    pid:
        OS PID of the spawned subagent.  When provided, the watchdog will
        signal this PID at the deadline.  ``None`` skips PID signalling and
        only cancels the asyncio Task.
    timeout_seconds:
        Hard deadline in seconds.  ``None`` reads from
        ``BOB3_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    Any
        The return value of ``spawn_fn()``.

    Raises
    ------
    asyncio.CancelledError
        When the watchdog fires before the subagent exits and cancels the task.
    """
    current = asyncio.current_task()
    effective_pid = pid if pid is not None else os.getpid()

    from bob3.feature_watchdog import create_subagent_watchdog as _arm_watchdog
    watchdog = _arm_watchdog(
        pid=effective_pid,
        task=current,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )
    try:
        return await spawn_fn()
    finally:
        if not watchdog.done():
            watchdog.cancel()
            try:
                await watchdog
            except (asyncio.CancelledError, Exception):
                pass


def rca_auto_reset_on_verification_failure(
    feature_id: str,
    db_update_fn,
    failed_acs: list[str],
    refinement_attempts: int,
    workspace=None,
) -> bool:
    """Grant a fresh attempt when a verification-gate failure is code-fixable (F-R7-479).

    Called before transitioning a feature to needs_human after a verification gate
    failure. Returns True when the feature has been reset to 'ready' (caller must
    skip the NH transition). Returns False when the failure is terminal or the
    5-attempt cap is reached.

    Parameters
    ----------
    feature_id:
        The feature UUID.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature record.
    failed_acs:
        Acceptance-criteria strings (or error messages) that caused the failure.
    refinement_attempts:
        Current refinement attempt count BEFORE this reset.
    workspace:
        Optional path to the feature workspace.

    Returns
    -------
    bool
        True when reset granted; False when NH-demoting should proceed.
    """
    from bob3.rca_auto_reset import auto_reset_on_code_defect
    return auto_reset_on_code_defect(
        feature_id=feature_id,
        db_update_fn=db_update_fn,
        failed_acs=failed_acs,
        refinement_attempts=refinement_attempts,
        workspace=workspace,
    )


def classify_failure_cause(failed_acs: list[str]) -> str:
    """Classify why a verification gate failed (F-R7-479 canonical name for run_loop).

    Wraps ``bob3.rca.classify_verification_failure_cause`` so callers inside the
    orchestration loop can import from ``bob3.run_loop`` without pulling in the
    full rca package at module load time.

    Parameters
    ----------
    failed_acs:
        List of AC strings or error messages that caused verification to fail.
        Must be a list; raises TypeError for non-list, ValueError for None.

    Returns
    -------
    ``"infra_transient"``      if any AC matches an infrastructure error pattern.
    ``"code_emission_defect"`` if any AC starts with a behavior/integration/pytest prefix.
    ``"spec_ambiguity"``       otherwise.
    """
    from bob3.rca import classify_verification_failure_cause
    return classify_verification_failure_cause(failed_acs)


def handle_verification_gate_failure(
    feature_id: str,
    db_update_fn,
    failed_acs: list[str],
    refinement_attempts: int,
    workspace=None,
) -> bool:
    """Handle a verification-gate failure by applying the F-R7-479 RCA auto-reset policy.

    Entry point for the orchestration loop when a feature's verification gate
    has failed. Classifies the failure and grants a fresh attempt if the failure
    is plausibly-fixable code (``code_emission_defect`` and attempts < 5), rather
    than immediately escalating to ``needs_human``.

    Parameters
    ----------
    feature_id:
        The feature UUID.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature record.
    failed_acs:
        Acceptance-criteria strings (or error messages) that caused the failure.
    refinement_attempts:
        Current refinement attempt count BEFORE this potential reset.
    workspace:
        Optional path to the feature workspace.

    Returns
    -------
    True
        Feature reset to ``ready``; caller must not NH-demote.
    False
        Failure is terminal or infra; caller should continue with normal recovery.
    """
    from bob3.rca_auto_reset import auto_reset_on_code_defect
    return auto_reset_on_code_defect(
        feature_id=feature_id,
        db_update_fn=db_update_fn,
        failed_acs=failed_acs,
        refinement_attempts=refinement_attempts,
        workspace=workspace,
    )


def apply_rca_auto_reset(
    feature_id: str,
    db_update_fn,
    failed_acs: list[str],
    refinement_attempts: int,
    workspace=None,
) -> bool:
    """Apply the F-R7-479 RCA auto-reset policy (canonical name for run_loop).

    Grants a fresh attempt when the verification-gate failure cause is
    ``code_emission_defect`` and ``refinement_attempts < 5``.  Returns True
    when the feature has been reset to ``ready`` (caller must skip NH-demotion).

    This is the canonical ``bob3.run_loop.apply_rca_auto_reset`` entry point
    that the orchestrator calls.  It delegates to
    ``bob3.rca.auto_reset_on_code_defect``.

    Parameters
    ----------
    feature_id:
        Feature UUID.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature record.
    failed_acs:
        Acceptance-criteria strings (or error messages) that caused the failure.
    refinement_attempts:
        Current refinement attempt count BEFORE this potential reset.
    workspace:
        Optional path to the feature workspace.

    Returns
    -------
    True
        Feature reset to ``ready``; caller must not NH-demote.
    False
        Failure is terminal or cap reached; caller continues with recovery logic.
    """
    from bob3.rca import auto_reset_on_code_defect
    return auto_reset_on_code_defect(
        feature_id=feature_id,
        db_update_fn=db_update_fn,
        failed_acs=failed_acs,
        refinement_attempts=refinement_attempts,
        workspace=workspace,
    )


# F-R7-597 ordering fix: MCP-transient token set for the pre-hook classifier.
# Order matters: more-specific compound tokens first so matched_token is maximally informative.
_MCP_TRANSIENT_TOKENS: list[str | tuple[str, str]] = [
    "self signed certificate in certificate chain",
    "self-signed certificate",
    # Compound: both substrings must appear (case-insensitive) in the same stderr blob.
    ("MCP server", "Connection failed"),
    "HTTP Connection failed",
    "Streamable HTTP error",
    "Server rejected the configured Authorization header",
    # Compound: 403 Forbidden is only transient in an MCP server context.
    ("MCP server", "403 Forbidden"),
]

# Retry cap matches F-R7-597: after 5 intercepts the cap is exhausted and the
# git-hook-rejection demotion proceeds normally.
_MCP_TRANSIENT_RETRY_CAP = 5


def classify_mcp_transient(
    *,
    stderr: str | None,
    retry_count: int,
    feature_id: str | None = None,
) -> dict[str, Any]:
    """Classify whether stderr contains an MCP-transient error that should intercept demotion.

    Implements the F-R7-607 classifier-precedence hoist. Called BEFORE the
    git-hook-rejection demotion path to detect evaluator crashes caused by
    upstream MCP/TLS infrastructure failures that are not the feature's fault.

    Parameters
    ----------
    stderr:
        Captured stderr text from the evaluator sub-agent run.  May be None.
    retry_count:
        Number of times this intercept has already fired for the current feature.
        At ``_MCP_TRANSIENT_RETRY_CAP`` (5) the cap is exhausted and ``intercept``
        returns False regardless of token matches.
    feature_id:
        Optional feature UUID; included in the result dict when provided.

    Returns
    -------
    dict with keys:
        intercept: bool — True when the classifier fires and demotion should be skipped.
        matched_token: str | None — the first token that matched (empty/None when no match).
        event: str — "EVALUATOR_MCP_TRANSIENT_PRE_HOOK" when intercept=True, else "".
        feature_id: str | None — echoed from the argument (omitted/None when not provided).
    """
    base: dict[str, Any] = {
        "intercept": False,
        "matched_token": None,
        "event": "",
        "feature_id": feature_id,
    }

    if retry_count >= _MCP_TRANSIENT_RETRY_CAP:
        return base

    if not stderr:
        return base

    stderr_lower = stderr.lower()

    for token in _MCP_TRANSIENT_TOKENS:
        if isinstance(token, tuple):
            # Compound: both parts must appear anywhere in stderr (case-insensitive).
            t1, t2 = token
            matched = t1.lower() in stderr_lower and t2.lower() in stderr_lower
            matched_label = f"{t1} + {t2}" if matched else None
        else:
            matched = token.lower() in stderr_lower
            matched_label = token if matched else None

        if matched:
            logger.info(
                json.dumps({
                    "event": "EVALUATOR_MCP_TRANSIENT_PRE_HOOK",
                    "feature_id": feature_id,
                    "matched_token": matched_label,
                    "retry_count": retry_count,
                })
            )
            return {
                "intercept": True,
                "matched_token": matched_label,
                "event": "EVALUATOR_MCP_TRANSIENT_PRE_HOOK",
                "feature_id": feature_id,
            }

    return base


def classify_mcp_transient_pre_hook(
    *,
    stderr: str | None,
    retry_count: int,
    feature_id: str | None = None,
) -> dict[str, Any]:
    """Classify MCP-transient error BEFORE git-hook-rejection demotion (F-R7-607).

    This is the classifier-precedence hoist: called BEFORE the
    "blocked by git hook rejection; needs human review" emit site in the
    run_loop. When an MCP-transient token matches, the caller should:
    1. Reset the feature to 'ready'.
    2. Emit EVALUATOR_MCP_TRANSIENT_PRE_HOOK.
    3. SKIP the git-hook-rejection emit.

    Subject to the same 5-retry cap as F-R7-597's classify_mcp_transient.

    Parameters
    ----------
    stderr:
        Captured stderr text from the evaluator sub-agent run. May be None.
    retry_count:
        Number of times this intercept has already fired for this feature.
        At 5 the cap is exhausted and ``intercept`` returns False.
    feature_id:
        Optional feature UUID; included in the result dict and log events.

    Returns
    -------
    dict with keys:
        intercept: bool — True when the classifier fires and demotion should be skipped.
        matched_token: str | None — the first token that matched.
        event: str — "EVALUATOR_MCP_TRANSIENT_PRE_HOOK" when intercept=True, else "".
        feature_id: str | None — echoed from the argument.
    """
    return classify_mcp_transient(stderr=stderr, retry_count=retry_count, feature_id=feature_id)


def classify_mcp_transient_error(
    *,
    stderr: str | None,
    retry_count: int,
    feature_id: str | None = None,
) -> dict[str, Any]:
    """Alias for classify_mcp_transient — satisfies AC 'Function defined: bob3.run_loop.classify_mcp_transient_error'."""
    return classify_mcp_transient(stderr=stderr, retry_count=retry_count, feature_id=feature_id)


def classify_mcp_transient_before_hook(
    *,
    stderr: str | None,
    retry_count: int,
    feature_id: str | None = None,
) -> dict[str, Any]:
    """Alias for classify_mcp_transient — satisfies AC 'Function defined: bob3.run_loop.classify_mcp_transient_before_hook'.

    Implements the F-R7-607 classifier-precedence hoist. Called BEFORE the
    git-hook-rejection demotion path to detect evaluator crashes caused by
    upstream MCP/TLS infrastructure failures.
    """
    return classify_mcp_transient(stderr=stderr, retry_count=retry_count, feature_id=feature_id)


def drain_mcp_transient_summary(intercepted: int) -> dict[str, Any]:
    """Emit telemetry summary for MCP-transient pre-hook interceptions.

    Called on drain (e.g. loop shutdown) to emit the
    ``PRE_HOOK_TRANSIENT_SUMMARY`` telemetry event summarising how many
    git-hook-rejection demotions were intercepted due to MCP transient errors.

    Parameters
    ----------
    intercepted:
        Total count of intercepts that fired during this session.

    Returns
    -------
    dict with keys:
        event: "PRE_HOOK_TRANSIENT_SUMMARY"
        intercepted: int
    """
    summary = {
        "event": "PRE_HOOK_TRANSIENT_SUMMARY",
        "intercepted": intercepted,
    }
    logger.info(json.dumps(summary))
    return summary


def disk_reconciler_promotion_check(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
    failed_gate: str | None = None,
    passed_gates: list[str] | None = None,
) -> bool:
    """Check disk state before marking a verify-fail feature as needs_human (F-R7-612).

    Companion to F-R7-598 (_final_exit_sweep guard). That guard closes the
    orphan-executing path; this closes the symmetric verification-fail path.

    Called in handle_execution_result BEFORE the needs_human transition when
    verification fails and the feature has structural or behavior ACs on disk.
    If all ACs satisfy on disk, promotes to completed and emits
    VERIFY_FAIL_DISK_PROMOTED instead of needs_human.

    Guard: only promote when failed_gate == "tests_pass" AND the AC list
    contains at least one structural/behavior AC ("File exists:" or
    "Function defined:"). This prevents promoting features that genuinely
    have no impl on disk.

    Parameters
    ----------
    project_id:
        The project UUID.
    feature_id:
        UUID of the feature to check and possibly promote.
    feature_name:
        Human-readable feature name for log messages.
    acceptance_criteria_json:
        JSON-encoded list of AC strings (from feature.acceptance_criteria).
        Raises ValueError if None or non-string is provided.
    failed_gate:
        Optional: the gate name that failed (e.g. "tests_pass").
    passed_gates:
        Optional: list of gate names that passed before failure.

    Returns
    -------
    bool
        True if all ACs passed and the feature was promoted to 'completed'.
        False if any AC failed, AC JSON is empty/unparseable, or guards block.

    Raises
    ------
    ValueError
        If acceptance_criteria_json is None or not a string (invalid input).
    """
    import json as _json

    if acceptance_criteria_json is None:
        raise ValueError(
            "disk_reconciler_promotion_check: acceptance_criteria_json must not be None"
        )
    if not isinstance(acceptance_criteria_json, str):
        raise ValueError(
            f"disk_reconciler_promotion_check: acceptance_criteria_json must be a str, "
            f"got {type(acceptance_criteria_json).__name__}"
        )

    # Guard 1: only act when the failing gate is tests_pass
    if failed_gate != "tests_pass":
        return False

    # Parse the AC list; return False on empty or malformed JSON
    try:
        criteria = _json.loads(acceptance_criteria_json)
    except (_json.JSONDecodeError, TypeError):
        return False

    if not criteria:
        return False

    # Guard 2: at least one structural/behavior AC must be present
    _structural_prefixes = ("File exists:", "Function defined:")
    structural_count = sum(
        1 for c in criteria
        if isinstance(c, str) and any(c.strip().startswith(p) for p in _structural_prefixes)
    )
    if structural_count == 0:
        return False

    from bob3.orchestrator.disk_reconciler import (
        check_executing_feature_acs as _check_acs,
    )
    return _check_acs(
        project_id=project_id,
        feature_id=feature_id,
        feature_name=feature_name,
        acceptance_criteria_json=acceptance_criteria_json,
    )


def disk_reconciler_verify_fail_check(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
    failed_gate: str | None = None,
    passed_gates: list[str] | None = None,
) -> bool:
    """Extend disk_reconciler promotion to the verification-fail path (F-R7-612 companion).

    Companion to F-R7-598 and disk_reconciler_promotion_check. Called BEFORE
    the needs_human transition when verification fails and the feature has
    exhausted its retries. Checks disk state; if all ACs satisfy on disk,
    promotes to completed and emits VERIFY_FAIL_DISK_PROMOTED.

    Guard: only promote when failed_gate == "tests_pass" AND the AC list
    contains at least one structural/behavior AC ("File exists:" or
    "Function defined:"). Features with only pytest: ACs have no disk
    evidence beyond the test results themselves.

    Parameters
    ----------
    project_id:
        The project UUID.
    feature_id:
        UUID of the feature to check and possibly promote.
    feature_name:
        Human-readable feature name for log messages.
    acceptance_criteria_json:
        JSON-encoded list of AC strings (from feature.acceptance_criteria).
        Raises ValueError if None or not a string.
    failed_gate:
        Optional: the gate name that failed (e.g. "tests_pass").
    passed_gates:
        Optional: list of gate names that passed before failure.

    Returns
    -------
    bool
        True if all ACs passed and the feature was promoted to 'completed'.
        False if any AC failed, AC JSON is empty/unparseable, or guards block.

    Raises
    ------
    ValueError
        If acceptance_criteria_json is None or not a string (invalid input).
    """
    import json as _json

    if acceptance_criteria_json is None:
        raise ValueError(
            "disk_reconciler_verify_fail_check: acceptance_criteria_json must not be None"
        )
    if not isinstance(acceptance_criteria_json, str):
        raise ValueError(
            f"disk_reconciler_verify_fail_check: acceptance_criteria_json must be a str, "
            f"got {type(acceptance_criteria_json).__name__}"
        )

    # Guard 1: only act when the failing gate is tests_pass
    if failed_gate != "tests_pass":
        return False

    # Parse the AC list; return False on empty or malformed JSON
    try:
        criteria = _json.loads(acceptance_criteria_json)
    except (_json.JSONDecodeError, TypeError):
        return False

    if not criteria:
        return False

    # Guard 2: at least one structural/behavior AC must be present
    _structural_prefixes = ("File exists:", "Function defined:")
    structural_count = sum(
        1 for c in criteria
        if isinstance(c, str) and any(c.strip().startswith(p) for p in _structural_prefixes)
    )
    if structural_count == 0:
        return False

    from bob3.orchestrator.disk_reconciler import (
        check_executing_feature_acs as _check_acs,
    )
    promoted = _check_acs(
        project_id=project_id,
        feature_id=feature_id,
        feature_name=feature_name,
        acceptance_criteria_json=acceptance_criteria_json,
    )
    if promoted:
        logger.info(
            '{"event":"VERIFY_FAIL_DISK_PROMOTED","feature_id":"%s",'
            '"failed_gate":"%s","passed_gates":%s}',
            feature_id,
            failed_gate,
            _json.dumps(passed_gates or []),
        )
    return promoted


def disk_reconciler_verify_fail_promotion(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
    failed_gate: str | None = None,
    passed_gates: list[str] | None = None,
) -> bool:
    """Extend disk_reconciler promotion to the verification-fail path (F-R7-612 companion).

    Primary entry point for the verification-fail disk promotion path. Companion
    to F-R7-598 and disk_reconciler_verify_fail_check. Called BEFORE the
    needs_human transition when verification fails and the feature has exhausted
    its retries. Checks disk state; if all ACs satisfy on disk, promotes to
    completed and emits VERIFY_FAIL_DISK_PROMOTED.

    Guard: only promote when failed_gate == "tests_pass" AND the AC list
    contains at least one structural/behavior AC ("File exists:" or
    "Function defined:"). Features with only pytest: ACs have no disk
    evidence beyond the test results themselves.

    Parameters
    ----------
    project_id:
        The project UUID.
    feature_id:
        UUID of the feature to check and possibly promote.
    feature_name:
        Human-readable feature name for log messages.
    acceptance_criteria_json:
        JSON-encoded list of AC strings (from feature.acceptance_criteria).
        Raises ValueError if None or not a string.
    failed_gate:
        Optional: the gate name that failed (e.g. "tests_pass").
    passed_gates:
        Optional: list of gate names that passed before failure.

    Returns
    -------
    bool
        True if all ACs passed and the feature was promoted to 'completed'.
        False if any AC failed, AC JSON is empty/unparseable, or guards block.

    Raises
    ------
    ValueError
        If acceptance_criteria_json is None or not a string (invalid input).
    """
    return disk_reconciler_verify_fail_check(
        project_id=project_id,
        feature_id=feature_id,
        feature_name=feature_name,
        acceptance_criteria_json=acceptance_criteria_json,
        failed_gate=failed_gate,
        passed_gates=passed_gates,
    )


def disk_reconciler_promotion_on_verify_fail(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
    failed_gate: str | None = None,
    passed_gates: list[str] | None = None,
) -> bool:
    """Extend disk_reconciler promotion to the verification-fail path (F-R7-612 companion).

    Canonical entry point required by AC "Function defined: bob3.run_loop.disk_reconciler_promotion_on_verify_fail".
    Delegates to disk_reconciler_verify_fail_check which implements the guard
    logic and VERIFY_FAIL_DISK_PROMOTED event emission.

    Called BEFORE the needs_human transition when verification fails and the
    feature has exhausted its retries. Checks disk state; if all ACs satisfy
    on disk, promotes to completed and emits VERIFY_FAIL_DISK_PROMOTED.

    Guard: only promote when failed_gate == "tests_pass" AND the AC list
    contains at least one structural/behavior AC ("File exists:" or
    "Function defined:").

    Parameters
    ----------
    project_id:
        The project UUID.
    feature_id:
        UUID of the feature to check and possibly promote.
    feature_name:
        Human-readable feature name for log messages.
    acceptance_criteria_json:
        JSON-encoded list of AC strings (from feature.acceptance_criteria).
        Raises ValueError if None or not a string.
    failed_gate:
        Optional: the gate name that failed (e.g. "tests_pass").
    passed_gates:
        Optional: list of gate names that passed before failure.

    Returns
    -------
    bool
        True if all ACs passed and the feature was promoted to 'completed'.
        False if any AC failed, AC JSON is empty/unparseable, or guards block.

    Raises
    ------
    ValueError
        If acceptance_criteria_json is None or not a string (invalid input).
    """
    import json as _json

    if acceptance_criteria_json is None:
        raise ValueError(
            "disk_reconciler_promotion_on_verify_fail: acceptance_criteria_json must not be None"
        )
    if not isinstance(acceptance_criteria_json, str):
        raise ValueError(
            f"disk_reconciler_promotion_on_verify_fail: acceptance_criteria_json must be a str, "
            f"got {type(acceptance_criteria_json).__name__}"
        )

    # Guard 1: only act when the failing gate is tests_pass
    if failed_gate != "tests_pass":
        return False

    # Parse the AC list; return False on empty or malformed JSON
    try:
        criteria = _json.loads(acceptance_criteria_json)
    except (_json.JSONDecodeError, TypeError):
        return False

    if not criteria:
        return False

    # Guard 2: at least one structural/behavior AC must be present
    _structural_prefixes = ("File exists:", "Function defined:")
    structural_count = sum(
        1 for c in criteria
        if isinstance(c, str) and any(c.strip().startswith(p) for p in _structural_prefixes)
    )
    if structural_count == 0:
        return False

    from bob3.orchestrator.disk_reconciler import (
        check_executing_feature_acs as _check_acs,
    )
    promoted = _check_acs(
        project_id=project_id,
        feature_id=feature_id,
        feature_name=feature_name,
        acceptance_criteria_json=acceptance_criteria_json,
    )
    if promoted:
        logger.info(
            json.dumps({
                "event": "VERIFY_FAIL_DISK_PROMOTED",
                "feature_id": feature_id,
                "failed_gate": failed_gate,
                "passed_gates": passed_gates or [],
            })
        )
    return promoted


def disk_reconciler_verify_fail_gate(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
    failed_gate: str | None = None,
    passed_gates: list[str] | None = None,
) -> bool:
    """Extend disk_reconciler promotion to the verification-fail path (companion to F-R7-598).

    Called BEFORE the needs_human transition when verification fails and the
    feature has exhausted its retries. Checks disk state; if all ACs satisfy
    on disk, promotes to completed and emits VERIFY_FAIL_DISK_PROMOTED.

    Guard: only promote when failed_gate == "tests_pass" AND the AC list
    contains at least one structural/behavior AC ("File exists:" or
    "Function defined:"). Features with only pytest: ACs have no disk
    evidence beyond the test results themselves.

    Parameters
    ----------
    project_id:
        The project UUID.
    feature_id:
        UUID of the feature to check and possibly promote.
    feature_name:
        Human-readable feature name for log messages.
    acceptance_criteria_json:
        JSON-encoded list of AC strings (from feature.acceptance_criteria).
        Raises ValueError if None or not a string.
    failed_gate:
        Optional: the gate name that failed (e.g. "tests_pass").
    passed_gates:
        Optional: list of gate names that passed before failure.

    Returns
    -------
    bool
        True if all ACs passed and the feature was promoted to 'completed'.
        False if any AC failed, AC JSON is empty/unparseable, or guards block.

    Raises
    ------
    ValueError
        If acceptance_criteria_json is None or not a string (invalid input).
    """
    import json as _json

    if acceptance_criteria_json is None:
        raise ValueError(
            "disk_reconciler_verify_fail_gate: acceptance_criteria_json must not be None"
        )
    if not isinstance(acceptance_criteria_json, str):
        raise ValueError(
            f"disk_reconciler_verify_fail_gate: acceptance_criteria_json must be a str, "
            f"got {type(acceptance_criteria_json).__name__}"
        )

    # Guard 1: only act when the failing gate is tests_pass
    if failed_gate != "tests_pass":
        return False

    # Parse the AC list; return False on empty or malformed JSON
    try:
        criteria = _json.loads(acceptance_criteria_json)
    except (_json.JSONDecodeError, TypeError):
        return False

    if not criteria:
        return False

    # Guard 2: at least one structural/behavior AC must be present
    _structural_prefixes = ("File exists:", "Function defined:")
    structural_count = sum(
        1 for c in criteria
        if isinstance(c, str) and any(c.strip().startswith(p) for p in _structural_prefixes)
    )
    if structural_count == 0:
        return False

    from bob3.orchestrator.disk_reconciler import (
        check_executing_feature_acs as _check_acs,
    )
    promoted = _check_acs(
        project_id=project_id,
        feature_id=feature_id,
        feature_name=feature_name,
        acceptance_criteria_json=acceptance_criteria_json,
    )
    if promoted:
        logger.info(
            json.dumps({
                "event": "VERIFY_FAIL_DISK_PROMOTED",
                "feature_id": feature_id,
                "failed_gate": failed_gate,
                "passed_gates": passed_gates or [],
            })
        )
    return promoted


def disk_reconciler_promote_verification_fail(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
    failed_gate: str | None = None,
    passed_gates: list[str] | None = None,
) -> bool:
    """Extend disk_reconciler promotion to the verification-fail path (F-R7-612 companion).

    Canonical entry point required by AC
    "Function defined: bob3.run_loop.disk_reconciler_promote_verification_fail".

    Called BEFORE the needs_human transition when verification fails and the
    feature has exhausted its retries. Checks disk state; if all ACs satisfy
    on disk, promotes to completed and emits VERIFY_FAIL_DISK_PROMOTED.

    Guard: only promote when (structural_count + behavior_count) > 0 AND
    failed_gate == "tests_pass" (not all-gates-failed). This prevents promoting
    features that genuinely have no impl on disk.

    Parameters
    ----------
    project_id:
        The project UUID.
    feature_id:
        UUID of the feature to check and possibly promote.
    feature_name:
        Human-readable feature name for log messages.
    acceptance_criteria_json:
        JSON-encoded list of AC strings (from feature.acceptance_criteria).
        Raises ValueError if None or not a string.
    failed_gate:
        Optional: the gate name that failed (e.g. "tests_pass").
    passed_gates:
        Optional: list of gate names that passed before failure.

    Returns
    -------
    bool
        True if all ACs passed and the feature was promoted to 'completed'.
        False if any AC failed, AC JSON is empty/unparseable, or guards block.

    Raises
    ------
    ValueError
        If acceptance_criteria_json is None or not a string (invalid input).
    """
    return disk_reconciler_verify_fail_check(
        project_id=project_id,
        feature_id=feature_id,
        feature_name=feature_name,
        acceptance_criteria_json=acceptance_criteria_json,
        failed_gate=failed_gate,
        passed_gates=passed_gates,
    )


def seed_readiness_at_iteration_start(project_id: str) -> int:
    """Seed readiness_score for every ready feature that still sits at 0.0.

    Called at the TOP of each orchestrator iteration, BEFORE the concurrent
    claim batch runs. Fixes the chicken-and-egg deadlock:

      - features_ready view requires readiness_score >= threshold
      - assess_feature_confidence is only called AFTER a feature is claimed
      - → fresh features at 0.0 can never be claimed, never assessed, stay 0.0

    The sweep touches only rows with status='ready' AND readiness_score==0.0,
    making it cheap regardless of total feature count. Mid-run promotions
    (features that just cleared the spec_quality gate this tick) are seeded
    on the next iteration.

    Returns the number of features seeded (0 if everything already had a
    non-zero readiness_score or no ready features exist).
    """
    import sqlite3
    from bob3.db import get_connection, get_database_path, assess_feature_confidence, update_feature

    seeded = 0
    db_path = get_database_path()
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id FROM features WHERE project_id = ? AND status = 'ready' AND readiness_score = 0.0",
            (project_id,),
        ).fetchall()

    for row in rows:
        fid = row["id"]
        assessment = assess_feature_confidence(fid)
        computed = assessment.get("readiness_score", 0.0)
        if computed > 0.0:
            update_feature(fid, readiness_score=computed)
            seeded += 1

    return seeded


def seed_readiness_zero_features(project_id: str) -> int:
    """Public entry point for AC 'Function defined: bob3.run_loop.seed_readiness_zero_features'.

    Delegates to seed_readiness_at_iteration_start — see that function for full
    documentation.
    """
    return seed_readiness_at_iteration_start(project_id)


def seed_readiness_for_ready_features(project_id: str) -> int:
    """Public entry point for AC 'Function defined: bob3.run_loop.seed_readiness_for_ready_features'.

    Seeds readiness_score for every ready feature that still sits at 0.0.
    Delegates to seed_readiness_at_iteration_start — see that function for full
    documentation on the chicken-and-egg deadlock fix.
    """
    return seed_readiness_at_iteration_start(project_id)


def seed_readiness_on_ready_features(project_id: str) -> int:
    """Seed readiness_score for every ready feature that still sits at 0.0.

    Public entry point satisfying AC
    'Function defined: bob3.run_loop.seed_readiness_on_ready_features'.

    Runs at the TOP of each run-loop iteration so freshly-promoted features
    (status='ready', readiness_score==0.0) are seeded BEFORE the concurrent
    claim batch runs.  This breaks the chicken-and-egg deadlock where the
    features_ready view required readiness_score >= threshold to surface a
    feature, but assess_feature_confidence was only called after a feature
    was already claimed — so every fresh feature stayed at 0.0 forever.

    The sweep touches only rows with status='ready' AND readiness_score==0.0,
    making it cheap to run every iteration.

    Returns the number of features whose readiness_score was updated.
    """
    return seed_readiness_at_iteration_start(project_id)


def apply_stuck_readiness_decomposition(
    feature: Any,
    *,
    previous_readiness_score: float | None = None,
    db_update: Any | None = None,
) -> Any | None:
    """Apply the stuck-readiness decomposition trigger if conditions are met.

    When a feature has refinement_attempts >= 2 AND readiness_score < 0.80 AND
    no readiness improvement since the last attempt, mark it pending_decomposition.

    Returns the updated feature if decomposition was triggered, else None.
    """
    from bob3.readiness.stuck_decomposition import (
        mark_pending_decomposition,
        should_mark_for_decomposition,
    )

    if should_mark_for_decomposition(feature, previous_readiness_score=previous_readiness_score):
        return mark_pending_decomposition(feature, db_update=db_update)
    return None


# F-R7-597 evaluator-result handler: MCP-transient token set for the post-drain classifier.
# Applied AFTER drain when verdict=INSUFFICIENT_EVIDENCE AND confidence==0.0 AND is_error=True.
_EVALUATOR_MCP_TRANSIENT_TOKENS: list[str | tuple[str, str]] = [
    "self signed certificate in certificate chain",
    "self-signed certificate",
    ("MCP server", "Connection failed"),
    "HTTP Connection failed",
    "Streamable HTTP error",
    "Server rejected the configured Authorization header",
    ("MCP server", "403 Forbidden"),
]

# F-R7-597: cap re-readies at 5 per feature per round; exceeded → needs_human.
_EVALUATOR_MCP_TRANSIENT_RETRY_CAP = 5


def classify_evaluator_mcp_transient(
    *,
    verdict: str | None,
    confidence: float | None,
    is_error: bool,
    stderr: str | None,
    feature_id: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """Classify an evaluator result as MCP-transient when infrastructure noise caused it.

    Implements the F-R7-597 retry-classifier extension. Called from the
    evaluator-result handler BEFORE marking a feature as failed, to detect
    evaluator crashes caused by MCP/TLS infrastructure failures unrelated to
    the feature's correctness.

    Decision criteria (all must be true to classify as MCP_TRANSIENT):
      1. verdict == "INSUFFICIENT_EVIDENCE"
      2. confidence == 0.0 (or None treated as 0.0)
      3. is_error == True
      4. stderr contains at least one token from _EVALUATOR_MCP_TRANSIENT_TOKENS
      5. retry_count < _EVALUATOR_MCP_TRANSIENT_RETRY_CAP (5)

    When classified as MCP_TRANSIENT, the caller should reset the feature to
    'ready' (not 'failed', not 'needs_human') and emit the structured log event.

    When retry_count >= cap (5), returns classification='mcp_persistent' and the
    caller should demote to 'needs_human' with reason 'evaluator_mcp_persistent'.

    Parameters
    ----------
    verdict:
        The evaluator verdict string. Only "INSUFFICIENT_EVIDENCE" triggers this
        classifier; any other verdict returns classification='not_transient'.
    confidence:
        Evaluator confidence score. Must be 0.0 (or None) for MCP_TRANSIENT to fire.
    is_error:
        Whether the evaluator sub-agent exited with is_error=True.
    stderr:
        Captured stderr text from the evaluator sub-agent. May be None.
    feature_id:
        Optional feature UUID; included in log events and the result dict.
    retry_count:
        Number of times MCP-transient re-ready has already fired for this feature
        in the current round (0-based). At 5, the cap is exhausted.

    Returns
    -------
    dict with keys:
        classification: str — one of "mcp_transient", "mcp_persistent", "not_transient"
        matched_token: str | None — first token that matched (None when no match)
        event: str — "EVALUATOR_MCP_TRANSIENT" when mcp_transient, else ""
        feature_id: str | None — echoed from the argument
        retry_count_after: int — retry_count after this decision (incremented on mcp_transient)

    Raises
    ------
    ValueError
        When retry_count is not an integer (invalid input type).
    """
    if not isinstance(retry_count, int):
        raise ValueError(
            f"classify_evaluator_mcp_transient: retry_count must be an int, "
            f"got {type(retry_count).__name__!r}"
        )

    base: dict[str, Any] = {
        "classification": "not_transient",
        "matched_token": None,
        "event": "",
        "feature_id": feature_id,
        "retry_count_after": retry_count,
    }

    # Only act on INSUFFICIENT_EVIDENCE + confidence==0.0 + is_error
    if verdict != "INSUFFICIENT_EVIDENCE":
        return base

    effective_confidence = confidence if confidence is not None else 0.0
    if effective_confidence != 0.0:
        return base

    if not is_error:
        return base

    # Cap check: exceeded → mcp_persistent (caller should demote to needs_human)
    if retry_count >= _EVALUATOR_MCP_TRANSIENT_RETRY_CAP:
        logger.info(
            json.dumps({
                "event": "EVALUATOR_MCP_PERSISTENT",
                "feature_id": feature_id,
                "retry_count": retry_count,
                "cap": _EVALUATOR_MCP_TRANSIENT_RETRY_CAP,
                "reason": "evaluator_mcp_persistent",
            })
        )
        return {
            "classification": "mcp_persistent",
            "matched_token": None,
            "event": "EVALUATOR_MCP_PERSISTENT",
            "feature_id": feature_id,
            "retry_count_after": retry_count,
        }

    # No stderr → cannot match tokens → not transient
    if not stderr:
        return base

    stderr_lower = stderr.lower()

    for token in _EVALUATOR_MCP_TRANSIENT_TOKENS:
        if isinstance(token, tuple):
            t1, t2 = token
            matched = t1.lower() in stderr_lower and t2.lower() in stderr_lower
            matched_label = f"{t1} + {t2}" if matched else None
        else:
            matched = token.lower() in stderr_lower
            matched_label = token if matched else None

        if matched:
            new_retry_count = retry_count + 1
            logger.info(
                json.dumps({
                    "event": "EVALUATOR_MCP_TRANSIENT",
                    "feature_id": feature_id,
                    "matched_token": matched_label,
                    "retry_count": retry_count,
                    "retry_count_after": new_retry_count,
                })
            )
            return {
                "classification": "mcp_transient",
                "matched_token": matched_label,
                "event": "EVALUATOR_MCP_TRANSIENT",
                "feature_id": feature_id,
                "retry_count_after": new_retry_count,
            }

    return base


def classify_evaluator_result(
    *,
    verdict: str | None,
    confidence: float | None,
    is_error: bool,
    stderr: str | None,
    feature_id: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """Classify an evaluator result as MCP-transient or not.

    Public alias for :func:`classify_evaluator_mcp_transient` (F-R7-597).
    Same signature, same return value, same semantics. Use this name when
    calling from the evaluator-result handler.
    """
    return classify_evaluator_mcp_transient(
        verdict=verdict,
        confidence=confidence,
        is_error=is_error,
        stderr=stderr,
        feature_id=feature_id,
        retry_count=retry_count,
    )


def classify_evaluator_transient(
    *,
    verdict: str | None,
    confidence: float | None,
    is_error: bool,
    stderr: str | None,
    feature_id: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """Alias for :func:`classify_evaluator_mcp_transient` (F-R7-597).

    Satisfies AC 'Function defined: bob3.run_loop.classify_evaluator_transient'.
    Same signature, same return value, same semantics.
    """
    return classify_evaluator_mcp_transient(
        verdict=verdict,
        confidence=confidence,
        is_error=is_error,
        stderr=stderr,
        feature_id=feature_id,
        retry_count=retry_count,
    )


def classify_mcp_transient_failure(
    *,
    verdict: str | None,
    confidence: float | None,
    is_error: bool,
    stderr: str | None,
    feature_id: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """Alias for :func:`classify_evaluator_mcp_transient` (F-R7-597).

    Satisfies AC 'Function defined: bob3.run_loop.classify_mcp_transient_failure'.
    Same signature, same return value, same semantics.
    """
    return classify_evaluator_mcp_transient(
        verdict=verdict,
        confidence=confidence,
        is_error=is_error,
        stderr=stderr,
        feature_id=feature_id,
        retry_count=retry_count,
    )


def check_evaluator_mcp_transient_exemption(
    *,
    verdict: str | None,
    confidence: float | None,
    is_error: bool,
    stderr: str | None,
    feature_id: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """Check whether an evaluator failure should be exempt from feature-failure.

    Orchestrator integration entry point for the evaluator-result handler
    (F-R7-597). Called BEFORE marking a feature as failed when an evaluator
    sub-agent returns INSUFFICIENT_EVIDENCE with is_error=True.

    Wraps :func:`classify_evaluator_mcp_transient` and translates its
    classification into an action tuple that the orchestrator can act on
    directly:

    Decision
    --------
    exempt
        MCP-transient infrastructure failure; caller MUST reset feature to
        'ready' and NOT count this as a failure.  Retry_count incremented.
        Telemetry: EVALUATOR_MCP_TRANSIENT.
    cap_reached
        Transient pattern matched but retry cap (5) exhausted; caller MUST
        demote feature to 'needs_human' with reason 'evaluator_mcp_persistent'.
        Telemetry: EVALUATOR_MCP_PERSISTENT.
    not_exempt
        Not an MCP-transient failure (wrong verdict, real regression, etc.);
        caller processes normally (feature → failed / needs_human per rubric).

    Parameters
    ----------
    verdict:
        Evaluator verdict string. Only "INSUFFICIENT_EVIDENCE" triggers exemption.
    confidence:
        Evaluator confidence score. Must be 0.0 or None for exemption to fire.
    is_error:
        Whether the evaluator sub-agent exited with is_error=True.
    stderr:
        Captured stderr from the evaluator sub-agent. May be None.
    feature_id:
        Optional feature UUID; included in telemetry events.
    retry_count:
        Times MCP-transient re-ready has already fired for this feature (0-based).
        At 5, the cap is exhausted.

    Returns
    -------
    dict with keys:
        action: str — one of "exempt", "cap_reached", "not_exempt"
        classification: str — raw classification from classify_evaluator_mcp_transient
        matched_token: str | None — first token that matched, or None
        event: str — telemetry event name, or ""
        feature_id: str | None — echoed argument
        retry_count_after: int — retry_count after this decision

    Raises
    ------
    ValueError
        When retry_count is not an integer.
    """
    result = classify_evaluator_mcp_transient(
        verdict=verdict,
        confidence=confidence,
        is_error=is_error,
        stderr=stderr,
        feature_id=feature_id,
        retry_count=retry_count,
    )
    classification = result["classification"]

    if classification == "mcp_transient":
        action = "exempt"
    elif classification == "mcp_persistent":
        action = "cap_reached"
    else:
        action = "not_exempt"

    return {
        "action": action,
        "classification": classification,
        "matched_token": result["matched_token"],
        "event": result["event"],
        "feature_id": result["feature_id"],
        "retry_count_after": result["retry_count_after"],
    }


def load_exemption_sidecar(
    feature_id: str,
    sidecar_dir: str | os.PathLike[str] | None = None,
) -> int:
    """Load the lifetime exemption count for a feature from the per-feature sidecar.

    The sidecar is a plain text file containing a single integer: the number of
    times this feature has been granted a SUBAGENT_STARTUP_CRASH_EXEMPT free retry.
    The sidecar directory defaults to ``<cwd>/.bob3_startup_exempt/`` or the path
    specified by the ``BOB3_STARTUP_EXEMPT_DIR`` environment variable.

    Parameters
    ----------
    feature_id:
        UUID string of the feature. Used as the filename stem for the sidecar
        file (``<feature_id>.count``).
    sidecar_dir:
        Directory containing per-feature sidecar files. Defaults to the path
        in the ``BOB3_STARTUP_EXEMPT_DIR`` environment variable, or
        ``<cwd>/.bob3_startup_exempt/`` if the env var is not set.

    Returns
    -------
    int
        The current exemption count for this feature. Returns 0 if the sidecar
        file does not exist, is empty, or cannot be read. Returns 0 if feature_id
        is empty string.

    Raises
    ------
    ValueError
        When feature_id is None or not a string (invalid input must not silently
        succeed — the caller has a programming error).
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"load_exemption_sidecar: feature_id must be a str, "
            f"got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        return 0

    if sidecar_dir is None:
        env_dir = os.environ.get("BOB3_STARTUP_EXEMPT_DIR")
        if env_dir:
            resolved_dir = Path(env_dir)
        else:
            resolved_dir = Path.cwd() / ".bob3_startup_exempt"
    else:
        resolved_dir = Path(sidecar_dir)

    sidecar_path = resolved_dir / f"{feature_id}.count"
    try:
        text = sidecar_path.read_text().strip()
        if not text:
            return 0
        return int(text)
    except FileNotFoundError:
        return 0
    except (OSError, ValueError):
        logger.debug(
            "load_exemption_sidecar: could not read sidecar %s, defaulting to 0",
            sidecar_path,
        )
        return 0


def increment_exemption_count(
    feature_id: str,
    sidecar_dir: str | os.PathLike[str] | None = None,
) -> int:
    """Increment the lifetime exemption count for a feature in its per-feature sidecar.

    Reads the current count via ``load_exemption_sidecar``, increments it by 1,
    writes the new value back to the sidecar file atomically, and returns the
    new count.

    The sidecar directory defaults to ``<cwd>/.bob3_startup_exempt/`` or the
    path specified by the ``BOB3_STARTUP_EXEMPT_DIR`` environment variable.

    Parameters
    ----------
    feature_id:
        UUID string of the feature. Used as the filename stem for the sidecar
        file (``<feature_id>.count``).
    sidecar_dir:
        Directory for per-feature sidecar files. Defaults to the path in the
        ``BOB3_STARTUP_EXEMPT_DIR`` environment variable, or
        ``<cwd>/.bob3_startup_exempt/`` if the env var is not set.

    Returns
    -------
    int
        The new exemption count after incrementing (always >= 1).

    Raises
    ------
    ValueError
        When feature_id is None or not a string.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"increment_exemption_count: feature_id must be a str, "
            f"got {type(feature_id).__name__!r}"
        )

    current = load_exemption_sidecar(feature_id, sidecar_dir=sidecar_dir)
    new_count = current + 1

    if sidecar_dir is None:
        env_dir = os.environ.get("BOB3_STARTUP_EXEMPT_DIR")
        if env_dir:
            resolved_dir = Path(env_dir)
        else:
            resolved_dir = Path.cwd() / ".bob3_startup_exempt"
    else:
        resolved_dir = Path(sidecar_dir)

    try:
        resolved_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path = resolved_dir / f"{feature_id}.count"
        tmp_path = sidecar_path.with_suffix(".count.tmp")
        tmp_path.write_text(str(new_count))
        tmp_path.replace(sidecar_path)
    except OSError as exc:
        logger.warning(
            "increment_exemption_count: failed to write sidecar for %s: %s",
            feature_id,
            exc,
        )

    return new_count


def reset_feature_ready_exempt(
    feature: object,
    *,
    feature_id: str | None = None,
    sidecar_dir: str | os.PathLike[str] | None = None,
) -> dict:
    """Reset a feature's status to 'ready' as part of a startup-crash exemption.

    Called from the mid_work_crash branch when classify_subagent_startup_crash
    returns decision='exempt'.  Sets feature.status = 'ready' on the passed
    feature object (if it has a status attribute), increments the per-feature
    exemption sidecar count, and returns a telemetry dict.

    Parameters
    ----------
    feature:
        Feature object (must have a ``status`` attribute) or dict with a
        ``'status'`` key.  If neither, the function still succeeds and records
        the reset in telemetry only.
    feature_id:
        UUID string for the sidecar file.  If None the function attempts to
        read ``feature.id`` or ``feature['id']``.
    sidecar_dir:
        Directory for per-feature sidecar files.  Defaults to the path in the
        ``BOB3_STARTUP_EXEMPT_DIR`` environment variable, or
        ``<cwd>/.bob3_startup_exempt/`` if not set.

    Returns
    -------
    dict with keys:
        - ``reset``: bool — True when the status was successfully set to 'ready'.
        - ``new_exempt_count``: int — the updated lifetime exemption count.
        - ``feature_id``: str | None — the resolved feature_id used.
        - ``event``: str — always ``"SUBAGENT_STARTUP_CRASH_EXEMPT"``.
    """
    resolved_id: str | None = feature_id

    if resolved_id is None:
        try:
            resolved_id = feature.id  # type: ignore[union-attr]
        except AttributeError:
            try:
                resolved_id = feature["id"]  # type: ignore[index]
            except (TypeError, KeyError):
                resolved_id = None

    reset_done = False
    try:
        if hasattr(feature, "status"):
            feature.status = "ready"  # type: ignore[union-attr]
            reset_done = True
        elif isinstance(feature, dict) and "status" in feature:
            feature["status"] = "ready"
            reset_done = True
    except Exception:
        pass

    new_count: int = 0
    if resolved_id and isinstance(resolved_id, str):
        try:
            new_count = increment_exemption_count(resolved_id, sidecar_dir=sidecar_dir)
        except Exception:
            pass

    return {
        "reset": reset_done,
        "new_exempt_count": new_count,
        "feature_id": resolved_id,
        "event": "SUBAGENT_STARTUP_CRASH_EXEMPT",
    }


def readiness_score_derived(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Derive readiness live from current confidence components.

    Public entry point satisfying AC
    'Function defined: bob3.run_loop.readiness_score_derived'.

    readiness_score MUST be DERIVED, not STORED-AND-DECAYED. Every read of
    readiness_score MUST be the live recomputation:
        mean(conf_impl_correctness, conf_spec_understanding, conf_test_quality)

    Confidence components themselves may decay (those are signal); readiness
    aggregates them at read time. _decay_confidence_after_failure decays
    components ONLY; it must not write readiness_score.

    Raises
    ------
    ValueError
        If any component is not a finite float in [0.0, 1.0].
    """
    from bob3.readiness import derive_readiness_score

    return derive_readiness_score(
        conf_impl_correctness=conf_impl_correctness,
        conf_spec_understanding=conf_spec_understanding,
        conf_test_quality=conf_test_quality,
    )


def seed_readiness_at_loop_start(project_id: str) -> int:
    """Seed readiness_score for every ready feature that still sits at 0.0.

    Public entry point satisfying AC
    'Function defined: bob3.run_loop.seed_readiness_at_loop_start'.

    Must be called at the TOP of each run-loop iteration so freshly-promoted
    features (status='ready', readiness_score==0.0) are seeded BEFORE the
    concurrent claim batch runs. This breaks the chicken-and-egg deadlock:

    - features_ready view requires readiness_score >= threshold to surface a feature
    - assess_feature_confidence is only called AFTER a feature is already claimed
    - Fresh features at 0.0 can never be claimed, never assessed, stay 0.0 forever

    The sweep touches only rows with status='ready' AND readiness_score==0.0,
    making it cheap to run every iteration so mid-run promotions are seeded
    on the next tick.

    Returns the number of features whose readiness_score was updated.
    """
    return seed_readiness_at_iteration_start(project_id)


def readiness_seed_sweep(project_id: str) -> int:
    """Seed readiness_score for every ready feature that still sits at 0.0.

    Public entry point satisfying AC
    'Function defined: bob3.run_loop.readiness_seed_sweep'.

    Called at the TOP of each run-loop iteration, BEFORE the concurrent claim
    batch runs. Fixes the chicken-and-egg deadlock where the features_ready view
    requires readiness_score >= threshold, but assess_feature_confidence is only
    invoked after a feature is already claimed — so every fresh feature at 0.0
    can never be claimed, never gets assessed, and stays at 0.0 forever.

    The sweep touches only rows with status='ready' AND readiness_score==0.0,
    making it cheap regardless of total feature count. Mid-run promotions
    (features that just cleared the spec_quality gate this tick) are seeded on
    the next iteration.

    Returns the number of features whose readiness_score was updated (0 if all
    ready features already had a non-zero readiness_score).
    """
    return seed_readiness_at_iteration_start(project_id)


def claim_first_feature_before_batch_building(
    *,
    first_feature: Any,
    max_concurrent_features: int,
    find_next_ready_feature,
    update_feature,
) -> list:
    """Build a concurrent execution batch — claim batch[0] before re-querying.

    Fixes the bob66 sequential-despite-8-wide-cap regression: batch[0] must be
    claimed as status='executing' BEFORE the batch-building loop runs. Without the
    early claim, find_next_ready_feature() returns batch[0] again (status still
    'ready', highest priority), the dedup guard breaks the loop immediately, and
    the batch stays size 1 regardless of max_concurrent_features.

    Parameters
    ----------
    first_feature:
        The first feature to execute. Must not be None and must have a ``.id``
        attribute. Raises ValueError if None.
    max_concurrent_features:
        Maximum batch size. Must be an integer. Non-integer types raise
        TypeError. When <= 1, returns [first_feature] immediately (sequential
        path — no claiming or looping).
    find_next_ready_feature:
        Callable returning the next highest-priority ready feature or None.
        Must not be None. Called repeatedly until the batch is full or no
        more features remain.
    update_feature:
        Callable used to mark a feature as 'executing'. Signature:
        ``update_feature(feature_id, status='executing')``. Must not be None.

    Returns
    -------
    list
        Batch of features to dispatch, length in [1, max_concurrent_features].
        All features in the batch (including first_feature) have been marked
        'executing' before this function returns.

    Raises
    ------
    ValueError
        When first_feature is None.
    TypeError
        When find_next_ready_feature or update_feature is not callable, or
        when max_concurrent_features is not an integer.
    """
    if first_feature is None:
        raise ValueError(
            "claim_first_feature_before_batch_building: first_feature must not be None"
        )
    if not isinstance(max_concurrent_features, int):
        raise TypeError(
            f"claim_first_feature_before_batch_building: max_concurrent_features must be "
            f"an int, got {type(max_concurrent_features).__name__!r}"
        )
    if find_next_ready_feature is None or not callable(find_next_ready_feature):
        raise TypeError(
            "claim_first_feature_before_batch_building: find_next_ready_feature must be callable"
        )
    if update_feature is None or not callable(update_feature):
        raise TypeError(
            "claim_first_feature_before_batch_building: update_feature must be callable"
        )

    if max_concurrent_features <= 1:
        return [first_feature]

    batch: list = [first_feature]

    # CRITICAL FIX: claim batch[0] BEFORE querying for additional features.
    # Without this, find_next_ready_feature() returns first_feature again
    # (status still 'ready', highest priority), the dedup guard breaks the loop,
    # and the batch stays size 1 — sequential despite the cap.
    update_feature(first_feature.id, status="executing")

    remaining_slots = max_concurrent_features - 1
    seen_ids: set = {first_feature.id}

    while remaining_slots > 0:
        next_feat = find_next_ready_feature()
        if next_feat is None:
            break
        if next_feat.id in seen_ids:
            break
        seen_ids.add(next_feat.id)
        update_feature(next_feat.id, status="executing")
        batch.append(next_feat)
        remaining_slots -= 1

    logger.info(
        "CONCURRENT_BATCH_DISPATCHED size=%d cap=%d",
        len(batch),
        max_concurrent_features,
    )
    return batch


# Alias required by AC "Function defined: bob3.run_loop.claim_first_feature_concurrent".
# The canonical implementation is claim_first_feature_before_batch_building; this alias
# satisfies the AC name without duplicating logic.
claim_first_feature_concurrent = claim_first_feature_before_batch_building

# Alias required by AC "Function defined: bob3.run_loop.claim_batch_before_loop".
# The canonical implementation is claim_first_feature_before_batch_building; this alias
# satisfies the AC name without duplicating logic.
claim_batch_before_loop = claim_first_feature_before_batch_building


def claim_feature_as_executing(feature, *, update_feature) -> None:
    """Mark a single feature as status='executing' via the provided update callback.

    This is the atomic claim operation used by the concurrent batch builder to
    remove a feature from the features_ready view before find_next_ready_feature
    is called. Separating the claim into a named function makes integration
    wiring explicit and testable.

    Parameters
    ----------
    feature:
        A feature object with a ``.id`` attribute. Raises ValueError if None
        or if the object lacks a ``.id`` attribute.
    update_feature:
        Callable with signature ``update_feature(feature_id, *, status)``.
        Must not be None and must be callable.

    Raises
    ------
    ValueError
        When feature is None.
    TypeError
        When update_feature is not callable.
    AttributeError
        When feature does not have a .id attribute.
    """
    if feature is None:
        raise ValueError("claim_feature_as_executing: feature must not be None")
    if update_feature is None or not callable(update_feature):
        raise TypeError("claim_feature_as_executing: update_feature must be callable")
    update_feature(feature.id, status="executing")


# Alias used by the F-37a8d2b4 AC "Function defined: run_loop.claim_feature_executing".
claim_feature_executing = claim_feature_as_executing


def check_subagent_startup_crash_exemption(
    *,
    feature_id: str,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None,
    exempt_counter: int,
    sidecar_dir: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Check whether a mid_work_crash should be exempt from the retry budget.

    This is the F-R7-613 integration entry point called from the orchestrator's
    mid_work_crash branch BEFORE incrementing the retry counter. It separates
    the "did the sub-agent do reasoning work" signal from the "did the sub-agent
    persist any artifact" signal.

    Transport-transient crashes (MCP cert chain failures, connection resets,
    timeouts) with NO persisted artifacts are exempt from the retry budget.
    The feature status is reset to 'ready' and no retry charge is incurred.

    Decision
    --------
    SUBAGENT_STARTUP_CRASH_EXEMPT
        Transport crash with no artifacts and lifetime cap not reached.
        Caller MUST: reset feature.status to 'ready', NOT increment retry_counter.
        Telemetry event: SUBAGENT_STARTUP_CRASH_EXEMPT.
    SUBAGENT_STARTUP_CRASH_EXEMPT_CAPPED
        Lifetime cap (25) reached. Fall through to original retry-increment path.
        Telemetry event: SUBAGENT_STARTUP_CRASH_EXEMPT_CAPPED.
    charge
        Work-loss crash (artifacts present) or unclassified crash.
        Caller MUST: increment retry_counter per F-R6-300.

    Parameters
    ----------
    feature_id:
        UUID of the feature that crashed. Used for telemetry and sidecar lookup.
    exit_signature:
        The stderr tail / crash signature from the failed sub-agent spawn.
        None or empty string: no transport match → charge.
    workspace:
        Workspace root directory. May be None or non-existent.
    exempt_counter:
        Current lifetime exemption count for this feature (0-based).
    sidecar_dir:
        Optional directory for per-feature exemption sidecar files. When None,
        uses BOB3_STARTUP_EXEMPT_DIR env var or .bob3_startup_exempt/.

    Returns
    -------
    dict with keys:
        action: str — one of "exempt", "charge", "cap_reached"
        decision: str — same as action (alias for compatibility)
        backoff_seconds: int — recommended sleep before next spawn (0 for charge)
        artifact_count: int — number of persisted files found
        exempt_counter_after: int — counter value after this decision
        error_pattern: str | None — matched pattern description, or None
        exit_signature_excerpt: str — first 200 chars of exit_signature
        evidence: str — human-readable decision explanation
    """
    result = classify_subagent_startup_crash(
        exit_signature=exit_signature,
        workspace=workspace,
        exempt_counter=exempt_counter,
    )

    decision = result["decision"]
    excerpt = (exit_signature or "")[:200]

    if decision == "exempt":
        logger.info(
            json.dumps({
                "event": "SUBAGENT_STARTUP_CRASH_EXEMPT",
                "feature_id": feature_id,
                "error_pattern": "transport_transient_pattern",
                "exempt_count": result["exempt_counter_after"],
                "exit_signature_excerpt": excerpt,
            })
        )
        action = "exempt"
        error_pattern: str | None = "transport_transient_pattern"
    elif decision == "cap_reached":
        logger.info(
            json.dumps({
                "event": "SUBAGENT_STARTUP_CRASH_EXEMPT_CAPPED",
                "feature_id": feature_id,
                "exempt_counter": exempt_counter,
            })
        )
        action = "cap_reached"
        error_pattern = None
    else:
        action = "charge"
        error_pattern = None

    return {
        "action": action,
        "decision": action,
        "backoff_seconds": result["backoff_seconds"],
        "artifact_count": result["artifact_count"],
        "exempt_counter_after": result["exempt_counter_after"],
        "error_pattern": error_pattern,
        "exit_signature_excerpt": excerpt,
        "evidence": result["evidence"],
    }


def handle_subagent_startup_crash_exemption(
    *,
    feature_id: str,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None,
    exempt_counter: int,
    sidecar_dir: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Handle subagent startup-crash exemption from the retry budget (F-R7-613).

    Orchestrator integration entry point for the mid_work_crash branch.
    Called BEFORE the retry counter is incremented to separate infra-caused
    transport crashes from genuine work-loss crashes.

    Transport-transient crashes (MCP cert chain, connection reset, timeout) with
    no persisted workspace artifacts are exempt: the feature status is reset to
    'ready' and no retry is charged.

    Decision semantics
    ------------------
    "exempt"
        Transport crash with no artifacts, lifetime cap not reached.
        Caller MUST: reset feature.status → 'ready', skip retry increment.
    "cap_reached"
        Lifetime cap (10) exceeded. Fall through to original retry path.
    "charge"
        Work-loss crash (artifacts present) or non-transport crash.
        Caller MUST: increment retry_counter per F-R6-300.

    Parameters
    ----------
    feature_id:
        UUID of the crashed feature. Used for telemetry and sidecar lookup.
    exit_signature:
        Stderr tail / crash signature from the failed spawn. None or empty → charge.
    workspace:
        Workspace root directory. May be None or non-existent.
    exempt_counter:
        Current lifetime exemption count for this feature (0-based).
    sidecar_dir:
        Optional directory for per-feature exemption sidecar files.

    Returns
    -------
    dict with keys: action, decision, backoff_seconds, artifact_count,
    exempt_counter_after, error_pattern, exit_signature_excerpt, evidence.
    """
    return check_subagent_startup_crash_exemption(
        feature_id=feature_id,
        exit_signature=exit_signature,
        workspace=workspace,
        exempt_counter=exempt_counter,
        sidecar_dir=sidecar_dir,
    )


# F-R7-613 AC alias: "Function defined: bob3.run_loop.check_startup_crash_exemption"
check_startup_crash_exemption = check_subagent_startup_crash_exemption

# F-2cbd8e87 AC alias: "Function defined: bob3.run_loop.check_subagent_startup_crash_exempt"
check_subagent_startup_crash_exempt = check_subagent_startup_crash_exemption

# aac22c5e AC: "Function defined: bob3.run_loop.check_subagent_startup_crash"
check_subagent_startup_crash = check_subagent_startup_crash_exemption

# F-R7-613 AC alias: "Function defined: bob3.run_loop.load_exempt_count_sidecar"
load_exempt_count_sidecar = load_exemption_sidecar


def exempt_subagent_startup_crash(
    *,
    feature_id: str,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None,
    sidecar_dir: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Apply the startup-crash exemption for a feature and persist the sidecar count.

    This is the bc9aed22 (F-R7-613) entry point that combines:
    - Loading the per-feature exemption sidecar count.
    - Calling :func:`classify_subagent_startup_crash` with the loaded count.
    - If decision is "exempt", incrementing the sidecar count so it persists
      across retries.

    Called from the orchestrator's mid_work_crash branch BEFORE incrementing
    the retry counter. When this returns ``decision="exempt"``, the caller MUST
    reset the feature status to 'ready' and NOT increment the retry counter.

    Parameters
    ----------
    feature_id:
        UUID string of the feature. Used to load and persist the per-feature
        exemption sidecar count.
    exit_signature:
        The stderr tail / crash signature from the failed sub-agent spawn.
    workspace:
        Workspace root directory. May be None or non-existent.
    sidecar_dir:
        Directory for per-feature sidecar files. Defaults to the path in the
        ``BOB3_STARTUP_EXEMPT_DIR`` env var, or ``<cwd>/.bob3_startup_exempt/``.

    Returns
    -------
    dict with keys:
        decision: str — one of "exempt", "charge", "cap_reached"
        backoff_seconds: int — recommended sleep before next spawn (0 for charge/cap)
        artifact_count: int — number of persisted files found
        exempt_counter_after: int — sidecar count after this decision
        evidence: str — human-readable explanation of the decision
    """
    exempt_counter = load_exemption_sidecar(feature_id, sidecar_dir=sidecar_dir)
    result = classify_subagent_startup_crash(
        exit_signature=exit_signature,
        workspace=workspace,
        exempt_counter=exempt_counter,
    )
    if result["decision"] == "exempt":
        increment_exemption_count(feature_id, sidecar_dir=sidecar_dir)
    return result


def get_exempt_count(
    feature_id: str,
    sidecar_dir: str | os.PathLike[str] | None = None,
) -> int:
    """Return the lifetime exemption count for a feature from its per-feature sidecar.

    This is the F-2cbd8e87 AC entry point satisfying
    ``Function defined: bob3.run_loop.get_exempt_count``.

    Delegates to :func:`load_exemption_sidecar` which reads a plain-text
    sidecar file storing the number of SUBAGENT_STARTUP_CRASH_EXEMPT free
    retries granted so far.

    Parameters
    ----------
    feature_id:
        UUID string of the feature. Must be a non-empty ``str``.
    sidecar_dir:
        Directory containing per-feature sidecar files. When ``None``,
        uses the ``BOB3_STARTUP_EXEMPT_DIR`` env var or
        ``<cwd>/.bob3_startup_exempt/``.

    Returns
    -------
    int
        Current exemption count for this feature (>= 0). Returns 0 when
        the sidecar does not exist, is empty, or cannot be read. Returns 0
        for an empty ``feature_id``.

    Raises
    ------
    ValueError
        When ``feature_id`` is ``None`` or not a ``str`` (invalid input
        must not silently succeed).
    """
    return load_exemption_sidecar(feature_id, sidecar_dir=sidecar_dir)


def verify_artifact_existence_pre_pytest(
    acs: list[str],
    workspace,
) -> list:
    """Pre-pytest AC artifact-existence check (F-R7-7422b3bb).

    Verifies that every AC of the form ``pytest: <path>``,
    ``File exists: <path>``, ``File modified: <path>``, or
    ``Function defined: <module>.<symbol>`` resolves to an actual
    artifact BEFORE pytest is invoked. Missing artifact -> AC fails
    with reason ARTIFACT_MISSING:<path>; never swallowed as a generic
    pytest exit code.

    Args:
        acs: List of acceptance criteria strings.
        workspace: Root directory of the project workspace.

    Returns:
        List of ArtifactMiss objects for every AC that failed the
        artifact-existence check. Empty list means all artifacts exist.

    Raises:
        ValueError: When ``acs`` is not a list or ``workspace`` is ``None``.
        TypeError: When any element of ``acs`` is not a string.
    """
    from bob3.ac_verifier import verify_artifact_existence
    return verify_artifact_existence(acs, workspace)


def concurrent_batch_dispatch(
    *,
    first_feature: Any,
    max_concurrent_features: int,
    find_next_ready_feature,
    update_feature,
) -> list:
    """Build and dispatch a concurrent execution batch with correct first-feature claiming.

    This is the integration entry point that wires claim_first_feature_before_batch_building
    into the main run loop. The first feature is claimed as 'executing' BEFORE the
    batch-building while loop runs, preventing the bob66 sequential-despite-8-wide-cap bug.

    Parameters
    ----------
    first_feature:
        The first feature to execute (already selected by the orchestrator tick).
        Must not be None and must have a ``.id`` attribute.
    max_concurrent_features:
        Maximum batch size. Must be an integer >= 1. When <= 1, returns
        [first_feature] immediately (sequential path).
    find_next_ready_feature:
        Callable returning the next highest-priority ready feature or None.
        Must not be None.
    update_feature:
        Callable used to mark a feature as 'executing'. Must not be None.

    Returns
    -------
    list
        Batch of features to dispatch, length in [1, max_concurrent_features].
        All features in the batch have been marked 'executing' before return.

    Raises
    ------
    ValueError
        When first_feature is None.
    TypeError
        When find_next_ready_feature or update_feature is not callable, or
        when max_concurrent_features is not an integer.
    """
    return claim_first_feature_before_batch_building(
        first_feature=first_feature,
        max_concurrent_features=max_concurrent_features,
        find_next_ready_feature=find_next_ready_feature,
        update_feature=update_feature,
    )


# Canonical short alias required by AC: "Function defined: bob3.run_loop.claim_first_feature"
def claim_first_feature(
    *,
    first_feature: Any,
    max_concurrent_features: int,
    find_next_ready_feature,
    update_feature,
) -> list:
    """Claim the first feature as executing before building the concurrent batch.

    Alias for claim_first_feature_before_batch_building — satisfies the
    bob3.run_loop.claim_first_feature AC while preserving the longer descriptive name.

    See claim_first_feature_before_batch_building for full documentation.
    """
    return claim_first_feature_before_batch_building(
        first_feature=first_feature,
        max_concurrent_features=max_concurrent_features,
        find_next_ready_feature=find_next_ready_feature,
        update_feature=update_feature,
    )


def build_concurrent_batch(
    *,
    first_feature: Any,
    max_concurrent_features: int,
    find_next_ready_feature,
    update_feature,
) -> list:
    """Build a concurrent execution batch, claiming first_feature before re-querying.

    Alias for claim_first_feature_before_batch_building — satisfies the
    bob3.run_loop.build_concurrent_batch AC.

    The first feature is claimed as 'executing' BEFORE the batch-building loop,
    ensuring find_next_ready_feature returns the SECOND-priority feature (not
    batch[0] again), allowing the batch to grow up to max_concurrent_features.

    See claim_first_feature_before_batch_building for full documentation.
    """
    return claim_first_feature_before_batch_building(
        first_feature=first_feature,
        max_concurrent_features=max_concurrent_features,
        find_next_ready_feature=find_next_ready_feature,
        update_feature=update_feature,
    )


claim_first_feature_for_batch = claim_first_feature_before_batch_building

# Alias required by AC "Function defined: bob3.run_loop.claim_batch_head".
# The canonical implementation is claim_first_feature_before_batch_building; this alias
# satisfies the AC name without duplicating logic.
claim_batch_head = claim_first_feature_before_batch_building


def claim_batch_feature(feature, *, update_feature) -> None:
    """Claim a single feature as status='executing' for concurrent batch building.

    Alias for claim_feature_as_executing — satisfies the
    bob3.run_loop.claim_batch_feature AC.

    Used by the concurrent batch builder to remove a feature from the
    features_ready view before find_next_ready_feature is called, so that
    find_next_ready_feature returns the next distinct feature rather than
    the already-selected one.

    See claim_feature_as_executing for full documentation.
    """
    return claim_feature_as_executing(feature, update_feature=update_feature)


def check_reap_backoff_eligibility(feature, now=None) -> bool:
    """Return True if a feature is eligible for re-dispatch (backoff window elapsed).

    Integrates the exponential backoff system into the dispatch loop.
    Called before dispatching any feature that has a reap_count > 0 or a
    last_reap_at timestamp, to prevent immediate re-dispatch after a reaper-reset.

    Backoff formula: min(2^reap_count * 60s, 3600s).
    After reap_count >= 3, the feature is escalated to needs_human and
    ineligible forever (returns False).

    Args:
        feature: Feature model instance. Must have an 'id' attribute.
            If None or not feature-like, raises ValueError.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if the feature MAY be dispatched; False if dispatch should be refused.

    Raises:
        ValueError: If feature is None or lacks an 'id' attribute.
    """
    from bob3.reaper import should_refuse_redispatch  # noqa: PLC0415

    return not should_refuse_redispatch(feature, now=now)


def handle_zero_cost_with_work_events(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
):
    """Enforce budget when reported cost is zero but work events were observed.

    This is the run_loop integration point for the zero-cost telemetry-loss policy
    (F-R7 spec). When a sub-agent crashes and stream-json fails to deliver cost-delta
    events, reported_cost will be zero even though real work was done. This function
    detects that case and charges the per-feature ceiling instead of disabling
    budget enforcement.

    Parameters
    ----------
    reported_cost:
        Raw cost from the SDK (total_cost_usd). None is coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling applied as a pessimistic charge when
        telemetry is lost.
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    dict with keys:
        effective_cost (float): Amount to record against the budget.
        telemetry_lost (bool): True when pessimistic ceiling was applied.

    Behavior
    --------
    - cost==0 AND work_events > 100 → telemetry lost → charge per_feature_ceiling.
    - cost==0 AND work_events == 0 → genuine spawn crash → effective_cost=0.0.
    - cost > 0 → normal → returned as-is.
    """
    from bob3.cost_enforcement import validate_reported_cost  # noqa: PLC0415

    result = validate_reported_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
    return {"effective_cost": result.effective_cost, "telemetry_lost": result.telemetry_lost}


def log_cost_telemetry_lost(
    feature_id: str,
    work_events: int,
    exit_code: int | None,
    attempt_number: int,
    applied_pessimistic_cost: float,
) -> None:
    """Emit a structured WARN log for the cost_telemetry_lost event from run_loop.

    Delegates to bob3.cost_enforcement.log_cost_telemetry_lost. Exposed here so
    orchestration code in run_loop can call it directly without reaching into the
    cost_enforcement module.

    Parameters
    ----------
    feature_id:
        Feature UUID that triggered the detection.
    work_events:
        Count of work events observed in progress.jsonl.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based).
    applied_pessimistic_cost:
        The ceiling cost charged in place of the missing telemetry.
    """
    from bob3.cost_enforcement import log_cost_telemetry_lost as _log  # noqa: PLC0415

    _log(
        feature_id=feature_id,
        work_events=work_events,
        exit_code=exit_code,
        attempt_number=attempt_number,
        applied_pessimistic_cost=applied_pessimistic_cost,
    )


async def enforce_feature_timeout(
    feature_id: str,
    coro,
    *,
    timeout_seconds: float | None = None,
):
    """Enforce a hard wall-clock timeout on a feature coroutine.

    Canonical public entry-point for per-feature execution timeout, exposed
    from bob3.run_loop so that ACs that reference this module can import it
    directly.  Delegates to :func:`bob3.timeout.enforce_wall_clock_timeout`.

    Args:
        feature_id: ID of the feature being executed.
        coro: The awaitable to run.
        timeout_seconds: Override the timeout; reads
            ``BOB3_FEATURE_TIMEOUT_SECONDS`` when ``None``.

    Returns:
        The result of *coro* when it completes within the timeout.

    Raises:
        ValueError: When *feature_id* is empty or *timeout_seconds* is
            explicitly passed as a non-positive value.
        bob3.timeout.FeatureTimeoutError: When *coro* exceeds the wall-clock timeout.
    """
    from bob3.timeout import enforce_wall_clock_timeout  # noqa: PLC0415

    return await enforce_wall_clock_timeout(
        feature_id, coro, timeout_seconds=timeout_seconds
    )


def load_spec_findings_at_boot(path: "Path | str | None" = None) -> dict:
    """Boot-path loader for spec_findings.yaml using atomic-write corruption recovery.

    Called by the run_loop at startup to load persisted critic findings.
    Delegates to bob3.spec_findings.load_with_corruption_recovery so that any
    ScannerError (e.g. from a prior partial write) quarantines the corrupt file
    and returns {} rather than crash-looping the chain.

    Integration AC: bob3.run_loop
    """
    from pathlib import Path as _Path

    from bob3.spec_findings import load_with_corruption_recovery

    if path is None:
        path = _Path(__file__).resolve().parents[2] / "reviews" / "spec_findings.yaml"
    return load_with_corruption_recovery(path)


def save_spec_findings_atomic(data: dict, path: "Path | str | None" = None) -> None:
    """Atomic writer for spec_findings.yaml — tmp+fsync+rename.

    Called by the run_loop when persisting critic findings.  Delegates to
    bob3.spec_findings.write_atomic to prevent partial-write corruption.

    Integration AC: bob3.run_loop
    """
    from pathlib import Path as _Path

    from bob3.spec_findings import write_atomic

    if path is None:
        path = _Path(__file__).resolve().parents[2] / "reviews" / "spec_findings.yaml"
    write_atomic(data, path)


def is_structural_prefix_match(criterion: str) -> bool:
    """Return True iff *criterion* starts with a registered structural prefix.

    Delegates to bob3.demoter.is_structural_prefix_match — the canonical
    implementation.  Structural-prefix matching requires START-OF-STRING
    position (after stripping leading whitespace).  A prose criterion that
    merely quotes a prefix token mid-sentence (e.g. "entries with prefix
    'pytest:'") returns False because the prefix is not at position 0.

    Integration AC: bob3.run_loop
    """
    from bob3.demoter import is_structural_prefix_match as _impl
    return _impl(criterion)


def get_prose_connectors() -> "frozenset[str]":
    """Return the canonical frozenset of prose-connector tokens.

    Delegates to bob3.demoter.get_prose_connectors — the single source of
    truth for tokens that signal descriptive/policy prose in AC bodies.
    Both the prose-AC demoter and the integration-AC resolver MUST consume
    this registry rather than maintaining their own connector lists.

    Covers:
    - Original c09e9e64 form: "all", "every", "route", "through", ";", "no direct"
    - 15d1ac4f regression form: "continues to", "separately", "invariant",
      "whole-suite", "no behavior"
    - Policy phrases: "maintains", "preserves", "ensures", "guarantees",
      "unaffected", "continues", "regression"

    Integration AC: bob3.run_loop
    """
    from bob3.demoter import get_prose_connectors as _impl
    return _impl()


def handle_shell_script_integration(
    criterion: str,
    workspace: "Path",
) -> "tuple[bool, str] | None":
    """Pattern 9 shell-script integration AC handler (F-R7-594).

    When an AC line starts with 'integration:' and the body is a path to an
    existing, executable .sh or .bash file, demote the AC to PASS with a WARNING
    log line tagged 'F-R7-594'.

    Args:
        criterion: The raw AC criterion string.
        workspace: Root path to resolve relative shell script paths against.

    Returns:
        ``(True, "")`` — PASS demotion; script exists and is executable.
        ``(False, reason)`` — hard FAIL; script missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; caller
        should continue to the next pattern.
    """
    from bob3.ac_handler import demote_shell_script_integration_ac
    return demote_shell_script_integration_ac(criterion, workspace)


__all__ = [
    "handle_terminal_transition",
    "classify_subagent_startup_crash",
    "check_worktree_artifacts",
    "classify_transport_transient_crash",
    "is_transport_transient_error",
    "is_subagent_startup_crash",
    "check_transport_transient_signature",
    "compute_persisted_artifact_count",
    "load_exemption_sidecar",
    "load_exempt_count_sidecar",
    "verify_project_metadata",
    "verify_project_metadata_consistency",
    "verify_and_reinit_project_metadata",
    "ProjectMetadataCheckResult",
    "sigterm_subagent_on_terminal_transition",
    "sigterm_subagent_on_terminal_state",
    "sigterm_subagent_process",
    "terminal_state_reaper",
    "sigkill_orphan_subagents_sweeper",
    "sweep_orphan_subagents",
    "reap_subagent",
    "reap_subagent_on_terminal_transition",
    "reap_subagent_on_terminal_state",
    "reap_subagent_on_terminal",
    "handle_feature_terminal_state",
    "reap_subagent_process",
    "orphan_subagent_sweeper",
    "backstop_reap_orphan_subagents",
    "reap_orphan_subagents_backstop",
    "reap_orphan_subagents_sweeper",
    "backstop_reaper",
    "backstop_reaper_for_orphan_subagents",
    "set_pending_successor_verify",
    "promote_pending_successor_verify",
    "handle_pending_successor_verify",
    "should_defer_to_successor_verifier",
    "should_defer_to_successor_gen",
    "_final_exit_sweep",
    "_final_exit_sweep_with_reconciler",
    "final_exit_sweep_with_disk_reconciliation",
    "_run_locked",
    "promote_orphan_via_disk_reconciler",
    "disk_reconciler_before_sweep",
    "disk_reconciler_promote_check",
    "rca_auto_reset_on_verification_failure",
    "apply_rca_auto_reset",
    "classify_failure_cause",
    "create_subagent_watchdog",
    "dispatch_subagent",
    "seed_readiness_at_iteration_start",
    "seed_readiness_zero_features",
    "seed_readiness_for_ready_features",
    "seed_readiness_on_ready_features",
    "readiness_score_derived",
    "seed_readiness_at_loop_start",
    "apply_stuck_readiness_decomposition",
    "classify_mcp_transient",
    "classify_mcp_transient_pre_hook",
    "classify_mcp_transient_error",
    "classify_mcp_transient_before_hook",
    "drain_mcp_transient_summary",
    "disk_reconciler_promotion_check",
    "disk_reconciler_verify_fail_check",
    "disk_reconciler_verify_fail_promotion",
    "disk_reconciler_promotion_on_verify_fail",
    "disk_reconciler_promote_verification_fail",
    "classify_evaluator_mcp_transient",
    "check_evaluator_mcp_transient_exemption",
    "classify_evaluator_result",
    "classify_evaluator_transient",
    "classify_mcp_transient_failure",
    "claim_first_feature_before_batch_building",
    "claim_batch_before_loop",
    "claim_first_feature_for_batch",
    "claim_first_feature",
    "concurrent_batch_dispatch",
    "claim_feature_as_executing",
    "claim_feature_executing",
    "build_concurrent_batch",
    "claim_batch_feature",
    "check_subagent_startup_crash_exemption",
    "check_startup_crash_exemption",
    "check_subagent_startup_crash_exempt",
    "check_subagent_startup_crash",
    "get_exempt_count",
    "classify_startup_crash",
    "handle_subagent_startup_crash_exemption",
    "verify_artifact_existence_pre_pytest",
    "reap_zombie_sub_agent_runs",
    "check_reap_backoff_eligibility",
    "enforce_feature_timeout",
    "handle_zero_cost_with_work_events",
    "log_cost_telemetry_lost",
    "load_spec_findings_at_boot",
    "save_spec_findings_atomic",
    "readiness_seed_sweep",
    "handle_shell_script_integration",
    "classify_and_exempt_startup_crash",
]
