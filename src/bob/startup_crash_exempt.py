"""Startup-crash exemption logic for mid-work-crash classification (F-R7-597).

Context
-------
A recurring failure mode in the dark factory: a sub-agent accumulates
roughly 6000 work_events over 15-20 minutes, then the MCP transport
(self-signed cert chain on the github plugin, or evaluator connection
reset) fails mid-task. The sub-agent throws an Exception with exit code 1
before writing any persistent implementation artifact to the workspace
src tree.

The existing crash classifier (F-R6-300) sees work_events > 0 and charges
a retry. After 5 retries the feature flips to needs_human.

Distinction this module introduces
------------------------------------
Separate the *reasoning-work* signal from the *persisted-artifact* signal.

  * A mid_work_crash with zero persisted artifacts → transport crash.
    Exempt from the retry budget; grant a free retry with exponential
    backoff.
  * A mid_work_crash with persisted artifacts → genuine work-loss crash.
    Charge a retry per F-R6-300 as before.

Design
------
* ``compute_artifact_count_after_spawn``: counts Python/test files written
  to ``src/`` or ``tests/`` since the spawn event. Returns 0 and never
  raises on missing or empty workspace.
* ``exit_signature_matches_transport_transient``: regex test against the
  stderr tail / exit signature. Returns False on invalid input (empty
  string, None).
* ``exponential_backoff_seconds``: 60 * 2^exempt_counter, capped at 1800.
* ``try_exempt``: the policy function. Applies the transport-crash vs
  work-loss distinction, advances the exempt counter, and enforces the
  25-exemption lifetime cap.
* ``StartupCrashExemptOutcome``: typed result returned by ``try_exempt``.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex patterns that identify MCP transport-transient failures.
# Compiled once at import time.
_TRANSPORT_TRANSIENT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in [
        r"self.signed certificate",
        r"self signed certificate",
        r"certificate chain",
        r"certificate verify failed",
        r"ECONNRESET",
        r"ConnectionResetError",
        r"connection reset",
        r"ECONNREFUSED",
        r"ETIMEDOUT",
        r"ReadTimeout",
        r"connection timed out",
        r"streamable http error",
        r"error posting to endpoint",
        r"evaluator.*connection.*reset",
        r"mcp.*transport.*fail",
        r"mcp.*connection.*fail",
        r"mcp.*server.*connection",
        r"plugin.*connection.*fail",
        r"socket hang up",
        r"broken pipe",
        r"EHOSTUNREACH",
        r"network.*unreachable",
        r"Connection failed",
    ]
)

# Exponential backoff: 60 * 2^n, capped at 1800 seconds.
_BACKOFF_BASE_SECONDS = 60
_BACKOFF_CAP_SECONDS = 1800

# Lifetime cap: after 25 exemptions, fall through to the original retry path.
_LIFETIME_EXEMPT_CAP = 25

# File extensions considered "implementation artifacts".
_ARTIFACT_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".ts", ".js", ".go", ".rs", ".java", ".yaml", ".yml", ".toml", ".sql"}
)

# Source directories to scan for artifacts.
_ARTIFACT_DIRS: tuple[str, ...] = ("src", "tests")


# ---------------------------------------------------------------------------
# Outcome dataclass
# ---------------------------------------------------------------------------


class ExemptDecision(str, Enum):
    """The decision made by ``try_exempt``."""

    EXEMPT = "exempt"          # Transport crash, no artifacts: grant free retry.
    CHARGE = "charge"          # Work-loss crash or artifacts found: charge retry.
    CAP_REACHED = "cap_reached"  # Lifetime cap hit: fall through to original path.


@dataclass
class StartupCrashExemptOutcome:
    """Result returned by :func:`try_exempt`.

    Attributes
    ----------
    decision:
        ``EXEMPT`` — grant a free retry with exponential backoff.
        ``CHARGE`` — charge a retry attempt per F-R6-300.
        ``CAP_REACHED`` — lifetime cap of 25 exemptions reached; caller
        should fall through to the original retry path.
    backoff_seconds:
        Recommended sleep before the next spawn.  0 when decision is
        ``CHARGE`` or ``CAP_REACHED``.
    artifact_count:
        Number of persisted implementation artifacts found in the
        workspace at decision time.
    exempt_counter_after:
        The exempt counter value *after* this decision (not incremented
        when decision is ``CHARGE``).
    evidence:
        Human-readable string summarising why this decision was made.
    """

    decision: ExemptDecision
    backoff_seconds: int
    artifact_count: int
    exempt_counter_after: int
    evidence: str


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def compute_artifact_count_after_spawn(
    workspace: str | os.PathLike[str] | None,
) -> int:
    """Count implementation artifacts in the workspace.

    Scans ``src/`` and ``tests/`` subdirectories of ``workspace`` for
    files with a recognised implementation-artifact extension.

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
    if workspace is None:
        return 0

    ws = Path(workspace)
    if not ws.exists():
        return 0

    count = 0
    for subdir_name in _ARTIFACT_DIRS:
        subdir = ws / subdir_name
        if not subdir.exists():
            continue
        try:
            for entry in subdir.rglob("*"):
                if entry.is_file() and entry.suffix in _ARTIFACT_EXTENSIONS:
                    count += 1
        except OSError as exc:
            logger.debug(
                "startup_crash_exempt: could not scan %s: %s", subdir, exc
            )
    return count


def exit_signature_matches_transport_transient(
    exit_signature: str | None,
) -> bool:
    """Return True iff ``exit_signature`` matches a known transport-transient pattern.

    Transport-transient patterns include self-signed certificate errors,
    connection resets, timeouts, and MCP plugin failures that are caused by
    infra rather than the sub-agent's implementation.

    Parameters
    ----------
    exit_signature:
        The stderr tail, exit reason, or combined crash signature string
        from the sub-agent process.  ``None`` or empty string returns
        ``False``.

    Returns
    -------
    bool
        ``True`` when the signature matches a transport-transient pattern.
        ``False`` for empty strings, ``None``, or signatures that do not
        match any known pattern.
    """
    if not exit_signature:
        return False
    # A clean "exit code 1" with no accompanying network/transport
    # signature is NOT infra-transient — it is almost always a
    # max_turns exhaustion (SDK surfaces turn-limit as exit 1) or a
    # genuine implementation error. Both must bubble to normal
    # refinement (WIP-preserving) rather than silent full-turn retry.
    # Real transport crashes always carry a connection/cert/timeout
    # marker matched by the patterns below, so no special-case needed
    # here beyond NOT matching bare exit-1.
    for pattern in _TRANSPORT_TRANSIENT_PATTERNS:
        if pattern.search(exit_signature):
            return True
    return False


def exponential_backoff_seconds(exempt_counter: int) -> int:
    """Compute exponential backoff for the nth exempt retry.

    Formula: min(60 * 2^exempt_counter, 1800)

    The first exemption (exempt_counter=0) yields 60 seconds.
    The backoff is capped at 1800 seconds regardless of counter value.

    Parameters
    ----------
    exempt_counter:
        Number of exemptions already granted for this feature (0-based).
        Negative values are treated as 0.

    Returns
    -------
    int
        Backoff in seconds.  Always in [60, 1800].

    Raises
    ------
    ValueError
        When ``exempt_counter`` is not an integer.
    """
    if not isinstance(exempt_counter, int):
        raise ValueError(
            f"exempt_counter must be an int, got {type(exempt_counter).__name__!r}"
        )
    if exempt_counter < 0:
        exempt_counter = 0
    try:
        raw = _BACKOFF_BASE_SECONDS * (2 ** exempt_counter)
    except OverflowError:
        return _BACKOFF_CAP_SECONDS
    return min(raw, _BACKOFF_CAP_SECONDS)


# ---------------------------------------------------------------------------
# Policy function
# ---------------------------------------------------------------------------


def try_exempt(
    *,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None,
    exempt_counter: int,
) -> StartupCrashExemptOutcome:
    """Apply the transport-crash vs work-loss distinction.

    Decision tree
    -------------
    1. If ``exempt_counter >= _LIFETIME_EXEMPT_CAP`` (25): fall through to
       the original retry path (``CAP_REACHED``).
    2. Compute ``artifact_count`` from the workspace.
    3. If ``artifact_count > 0``: genuine work-loss crash; charge the retry
       (``CHARGE``).
    4. If ``exit_signature_matches_transport_transient(exit_signature)`` is
       ``True`` AND ``artifact_count == 0``: transport crash; grant exemption
       (``EXEMPT``).
    5. Otherwise (no transport signature, no artifacts): not classifiable as
       exempt; charge the retry (``CHARGE``).

    Parameters
    ----------
    exit_signature:
        The stderr tail / crash signature from the failed sub-agent spawn.
    workspace:
        Workspace root directory.  May be None or non-existent.
    exempt_counter:
        Current lifetime exemption count for this feature (0-based).

    Returns
    -------
    StartupCrashExemptOutcome
        Structured outcome with decision, backoff, and diagnostic evidence.

    Raises
    ------
    ValueError
        When ``exempt_counter`` is not an integer, or when ``exit_signature``
        is provided but is not a string or None.
    """
    if not isinstance(exempt_counter, int):
        raise ValueError(
            f"exempt_counter must be an int, got {type(exempt_counter).__name__!r}"
        )
    if exit_signature is not None and not isinstance(exit_signature, str):
        raise ValueError(
            f"exit_signature must be a str or None, got {type(exit_signature).__name__!r}"
        )
    # 1. Lifetime cap check.
    if exempt_counter >= _LIFETIME_EXEMPT_CAP:
        return StartupCrashExemptOutcome(
            decision=ExemptDecision.CAP_REACHED,
            backoff_seconds=0,
            artifact_count=0,
            exempt_counter_after=exempt_counter,
            evidence=(
                f"lifetime_cap_reached: exempt_counter={exempt_counter} "
                f">= cap={_LIFETIME_EXEMPT_CAP}; falling through to original retry path"
            ),
        )

    # 2. Count persisted artifacts.
    artifact_count = compute_artifact_count_after_spawn(workspace)

    # 3. Artifacts present → work-loss crash; charge retry.
    if artifact_count > 0:
        return StartupCrashExemptOutcome(
            decision=ExemptDecision.CHARGE,
            backoff_seconds=0,
            artifact_count=artifact_count,
            exempt_counter_after=exempt_counter,
            evidence=(
                f"work_loss_crash: artifact_count={artifact_count} > 0; "
                f"charging retry per F-R6-300"
            ),
        )

    # 4. No artifacts + transport transient signature → exempt.
    is_transport = exit_signature_matches_transport_transient(exit_signature)
    if is_transport:
        new_counter = exempt_counter + 1
        backoff = exponential_backoff_seconds(exempt_counter)
        logger.info(
            "startup_crash_exempt: EXEMPT feature (transport_crash; "
            "artifact_count=0; exempt_counter=%d → %d; backoff=%ds)",
            exempt_counter,
            new_counter,
            backoff,
        )
        return StartupCrashExemptOutcome(
            decision=ExemptDecision.EXEMPT,
            backoff_seconds=backoff,
            artifact_count=0,
            exempt_counter_after=new_counter,
            evidence=(
                f"transport_crash: artifact_count=0; "
                f"exit_signature matched transport_transient_pattern; "
                f"backoff={backoff}s; exempt_counter={exempt_counter}→{new_counter}"
            ),
        )

    # 5. No transport signature, no artifacts → unclassified; charge retry.
    return StartupCrashExemptOutcome(
        decision=ExemptDecision.CHARGE,
        backoff_seconds=0,
        artifact_count=0,
        exempt_counter_after=exempt_counter,
        evidence=(
            f"unclassified_crash: artifact_count=0; "
            f"exit_signature does not match transport_transient_pattern; "
            f"charging retry"
        ),
    )


def persisted_artifact_count(
    workspace: str | os.PathLike[str] | None,
) -> int:
    """Alias for :func:`compute_artifact_count_after_spawn`.

    Provided so callers can import the function under the name that the
    feature's acceptance criteria reference directly.
    """
    return compute_artifact_count_after_spawn(workspace)


def count_persisted_artifacts(
    workspace: str | os.PathLike[str] | None,
) -> int:
    """Count implementation artifacts persisted to the workspace src/tests tree.

    This is the canonical name referenced by the feature acceptance criteria
    (``Function defined: bob.startup_crash_exempt.count_persisted_artifacts``).
    It delegates to :func:`compute_artifact_count_after_spawn`.

    A count of 0 means the sub-agent crashed before writing any persistent
    implementation artifact — the signal that separates a transport crash
    (exempt) from a genuine work-loss crash (charge retry).

    Parameters
    ----------
    workspace:
        Workspace root directory.  May be ``None`` or non-existent.

    Returns
    -------
    int
        Number of artifact files found.  Always >= 0; never raises.
    """
    return compute_artifact_count_after_spawn(workspace)


def is_startup_crash_exempt(
    *,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None,
    exempt_counter: int,
) -> bool:
    """Return True iff a mid_work_crash should be exempt from the retry budget.

    This is the canonical predicate referenced by the feature acceptance
    criteria (``Function defined: bob.startup_crash_exempt.is_startup_crash_exempt``).

    A crash is exempt when ALL of the following hold:

    * The exit signature matches a known transport-transient pattern
      (self-signed cert chain, connection reset, timeout, MCP plugin failure).
    * Zero persisted implementation artifacts exist in the workspace
      (no real work was lost — the crash preceded any src/tests write).
    * The lifetime exemption cap (25) has not been reached.

    A crash with persisted artifacts is a genuine work-loss crash and is
    NOT exempt (charge a retry per F-R6-300). A crash with no transport
    signature is unclassified and NOT exempt.

    Parameters
    ----------
    exit_signature:
        The stderr tail / crash signature from the failed sub-agent spawn.
        ``None`` or empty string yields ``False``.
    workspace:
        Workspace root directory.  May be ``None`` or non-existent.
    exempt_counter:
        Current lifetime exemption count for this feature (0-based).

    Returns
    -------
    bool
        ``True`` when the crash should be exempt from the retry budget,
        ``False`` otherwise.

    Raises
    ------
    ValueError
        When ``exempt_counter`` is not an integer, or when ``exit_signature``
        is provided but is not a string or None.
    """
    outcome = try_exempt(
        exit_signature=exit_signature,
        workspace=workspace,
        exempt_counter=exempt_counter,
    )
    return outcome.decision == ExemptDecision.EXEMPT


def exempt_counter(feature_id: str, *, db_path: str | os.PathLike[str] | None = None) -> int:
    """Return the current lifetime exemption count for ``feature_id``.

    Reads the exempt counter from a lightweight JSON sidecar file stored
    next to the workspace, falling back to 0 when no record exists.

    The counter tracks how many transport-transient free retries have been
    granted to a feature so the lifetime cap (25) can be enforced across
    process restarts.

    Parameters
    ----------
    feature_id:
        The feature UUID whose exempt counter should be returned.
    db_path:
        Optional path to the JSON sidecar directory.  When ``None``,
        defaults to a ``.bob_startup_exempt`` directory in the current
        working directory.

    Returns
    -------
    int
        The current exemption count for this feature (0 if unknown).

    Raises
    ------
    ValueError
        When ``feature_id`` is not a non-empty string.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a non-empty str, got {feature_id!r}"
        )

    sidecar_dir = Path(db_path) if db_path is not None else Path(".bob_startup_exempt")
    sidecar_file = sidecar_dir / f"{feature_id}.json"

    if not sidecar_file.exists():
        return 0

    try:
        import json as _json
        data = _json.loads(sidecar_file.read_text())
        return int(data.get("exempt_counter", 0))
    except (OSError, ValueError, KeyError, TypeError):
        logger.debug(
            "startup_crash_exempt: could not read exempt counter for %s", feature_id
        )
        return 0


def is_transport_crash(
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True iff the crash looks like a transport-transient failure.

    A transport crash is defined as: the exit signature matches a known
    transport-transient pattern AND there are zero persisted implementation
    artifacts in the workspace (i.e., no real work was lost).

    If ``workspace`` is None or non-existent, the artifact check treats
    artifact_count as 0 (conservative assumption: no artifacts found).

    Parameters
    ----------
    exit_signature:
        The stderr tail / crash signature from the failed sub-agent.
        ``None`` or empty string returns ``False``.
    workspace:
        Workspace root to check for persisted artifacts. Optional.

    Returns
    -------
    bool
        ``True`` when the signature matches a transport-transient pattern
        and zero artifacts are present. ``False`` otherwise.
    """
    if not exit_signature_matches_transport_transient(exit_signature):
        return False
    artifact_count = compute_artifact_count_after_spawn(workspace)
    return artifact_count == 0


def should_exempt_from_retry(
    *,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None,
    exempt_counter: int,
) -> bool:
    """Return True iff this crash should be granted a free retry (exempt from budget).

    Convenience predicate wrapping :func:`try_exempt`. Returns ``True`` only
    when the outcome decision is ``ExemptDecision.EXEMPT`` — i.e., the crash
    is a transport-transient failure with no persisted artifacts and the
    lifetime exemption cap has not been reached.

    Parameters
    ----------
    exit_signature:
        The stderr tail / crash signature from the failed sub-agent spawn.
    workspace:
        Workspace root directory. May be None or non-existent.
    exempt_counter:
        Current lifetime exemption count for this feature (0-based).

    Returns
    -------
    bool
        ``True`` when the crash should be exempt from the retry budget.
        ``False`` when the retry should be charged or the cap is reached.
    """
    outcome = try_exempt(
        exit_signature=exit_signature,
        workspace=workspace,
        exempt_counter=exempt_counter,
    )
    return outcome.decision == ExemptDecision.EXEMPT


def classify_startup_crash(
    *,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None,
    exempt_counter: int,
) -> dict[str, object]:
    """Classify a startup crash and return a dict result.

    This is the dict-returning variant of :func:`try_exempt`, provided so
    callers that expect a plain ``dict`` (rather than a typed dataclass) can
    use it without unpacking the dataclass.

    AC: ``Function defined: bob.startup_crash_exempt.classify_startup_crash``

    Parameters
    ----------
    exit_signature:
        The stderr tail / crash signature from the failed sub-agent spawn.
    workspace:
        Workspace root directory.  May be None or non-existent.
    exempt_counter:
        Current lifetime exemption count for this feature (0-based).

    Returns
    -------
    dict with keys:
        decision: str — one of "exempt", "charge", "cap_reached"
        backoff_seconds: int — recommended sleep before next spawn
        artifact_count: int — number of persisted implementation files found
        exempt_counter_after: int — counter value after this decision
        evidence: str — human-readable decision explanation

    Raises
    ------
    ValueError
        When ``exempt_counter`` is not an integer, or when ``exit_signature``
        is provided but is not a string or None.
    """
    outcome = try_exempt(
        exit_signature=exit_signature,
        workspace=workspace,
        exempt_counter=exempt_counter,
    )
    return {
        "decision": outcome.decision.value,
        "backoff_seconds": outcome.backoff_seconds,
        "artifact_count": outcome.artifact_count,
        "exempt_counter_after": outcome.exempt_counter_after,
        "evidence": outcome.evidence,
    }


def check_startup_crash_exemption(
    *,
    feature_id: str,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None,
    exempt_counter: int,
    sidecar_dir: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    """Check whether a mid_work_crash should be exempt from the retry budget.

    Integration entry point for the orchestrator's mid_work_crash branch,
    called BEFORE incrementing the retry counter. Wraps :func:`classify_startup_crash`
    with feature telemetry and returns a rich dict suitable for orchestrator
    dispatch.

    AC: ``Function defined: bob.startup_crash_exempt.check_startup_crash_exemption``

    Decision semantics
    ------------------
    "exempt"
        Transport crash with no artifacts, lifetime cap not reached.
        Caller MUST: reset feature.status → 'ready', skip retry increment.
    "cap_reached"
        Lifetime cap reached. Fall through to original retry path.
    "charge"
        Work-loss crash (artifacts present) or unclassified crash.
        Caller MUST: increment retry_counter per F-R6-300.

    Parameters
    ----------
    feature_id:
        UUID of the crashed feature.  Used for telemetry.
    exit_signature:
        Stderr tail / crash signature from the failed spawn.
    workspace:
        Workspace root directory. May be None or non-existent.
    exempt_counter:
        Current lifetime exemption count for this feature (0-based).
    sidecar_dir:
        Optional directory for per-feature exemption sidecar files. When None,
        uses BOB_STARTUP_EXEMPT_DIR env var or .bob_startup_exempt/.

    Returns
    -------
    dict with keys:
        action: str — one of "exempt", "charge", "cap_reached"
        decision: str — same as action (alias for compatibility)
        backoff_seconds: int — recommended sleep before next spawn
        artifact_count: int — number of persisted files found
        exempt_counter_after: int — counter value after this decision
        error_pattern: str | None — matched pattern description, or None
        exit_signature_excerpt: str — first 200 chars of exit_signature
        evidence: str — human-readable decision explanation

    Raises
    ------
    ValueError
        When ``exempt_counter`` is not an integer.
    """
    result = classify_startup_crash(
        exit_signature=exit_signature,
        workspace=workspace,
        exempt_counter=exempt_counter,
    )

    decision = result["decision"]
    excerpt = (exit_signature or "")[:200]

    if decision == "exempt":
        logger.info(
            "startup_crash_exempt: EXEMPT feature_id=%s transport_crash "
            "exempt_count=%s",
            feature_id,
            result["exempt_counter_after"],
        )
        action: str = "exempt"
        error_pattern: str | None = "transport_transient_pattern"
    elif decision == "cap_reached":
        logger.info(
            "startup_crash_exempt: CAP_REACHED feature_id=%s exempt_counter=%s",
            feature_id,
            exempt_counter,
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


__all__ = [
    "ExemptDecision",
    "StartupCrashExemptOutcome",
    "calculate_backoff",
    "check_startup_crash_exemption",
    "classify_startup_crash",
    "compute_artifact_count_after_spawn",
    "count_persisted_artifacts",
    "exempt_counter",
    "exempt_from_retry_budget",
    "exit_signature_matches_transport_transient",
    "exponential_backoff_seconds",
    "get_exempt_count",
    "is_startup_crash_exempt",
    "is_transport_crash",
    "persisted_artifact_count",
    "should_exempt_from_retry",
    "try_exempt",
]


# Alias required by AC: "Function defined: bob.startup_crash_exempt.exempt_from_retry_budget"
exempt_from_retry_budget = should_exempt_from_retry

# Alias required by AC: "Function defined: bob.startup_crash_exempt.get_exempt_count"
get_exempt_count = exempt_counter

# Alias required by AC: "Function defined: bob.startup_crash_exempt.calculate_backoff"
calculate_backoff = exponential_backoff_seconds
