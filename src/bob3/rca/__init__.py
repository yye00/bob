"""Root-cause analysis helpers exposed at the bob3.rca top level.

The key entry point for F-R7-479 is ``auto_reset_on_code_defect``:
grant a fresh attempt budget when a verification-gate failure is
plausibly fixable by a different subagent emission, rather than
treating all non-infra failures as terminally NH-worthy.

Public API (F-R7-479 ACs):
- ``classify_verification_failure_cause``: canonical name for classification
- ``should_grant_fresh_attempt_budget``: canonical name for grant decision

Public API (F-R7-613 ACs — startup-crash exemption):
- ``is_mid_work_transport_crash``: True when crash is transport-transient w/ no artifacts
- ``exempt_mid_work_crash_from_retry``: applies full exemption policy; returns outcome dict
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Callable

from bob3.rca_classifier import (
    Classification,
    classify_verification_failure,
    should_grant_fresh_attempt,
)
from bob3.startup_crash_exempt import (
    ExemptDecision,
    StartupCrashExemptOutcome,
    is_transport_crash,
    should_exempt_from_retry,
    try_exempt,
)

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5


def classify_verification_failure_cause(failed_acs: list[str]) -> Classification:
    """Classify why a verification gate failed — canonical public name for F-R7-479.

    Parameters
    ----------
    failed_acs:
        List of AC strings or error messages that caused verification to fail.
        Must be a list (not None, not a string).

    Returns
    -------
    ``"infra_transient"``      if any AC matches an infrastructure error pattern.
    ``"code_emission_defect"`` if any AC starts with a behavior/integration/pytest prefix.
    ``"spec_ambiguity"``       otherwise — including empty list.

    Raises
    ------
    TypeError
        If ``failed_acs`` is not a list.
    ValueError
        If ``failed_acs`` is None.
    """
    if failed_acs is None:
        raise ValueError("failed_acs must be a list, got None")
    if not isinstance(failed_acs, list):
        raise TypeError(f"failed_acs must be a list, got {type(failed_acs).__name__}")
    return classify_verification_failure(failed_acs)


def should_grant_fresh_attempt_budget(
    classification: Classification,
    refinement_attempts: int,
) -> bool:
    """Return True if the feature should receive another attempt — canonical public name.

    Parameters
    ----------
    classification:
        One of ``"code_emission_defect"``, ``"spec_ambiguity"``, ``"infra_transient"``.
    refinement_attempts:
        Current refinement attempt count.

    Returns
    -------
    True if a fresh attempt should be granted, False otherwise.

    Raises
    ------
    TypeError
        If ``refinement_attempts`` is not an int.
    ValueError
        If ``refinement_attempts`` is negative.
    """
    if not isinstance(refinement_attempts, int):
        raise TypeError(
            f"refinement_attempts must be an int, got {type(refinement_attempts).__name__}"
        )
    if refinement_attempts < 0:
        raise ValueError(f"refinement_attempts must be >= 0, got {refinement_attempts}")
    return should_grant_fresh_attempt(classification, refinement_attempts)


def auto_reset_on_code_defect(
    feature_id: str,
    db_update_fn: Callable[..., None],
    failed_acs: list[str],
    refinement_attempts: int,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Grant a fresh attempt when a verification failure is code-fixable.

    Called before transitioning a feature to ``needs_human`` after a
    verification gate failure. Returns True when the feature has been
    reset to ``ready`` (caller should skip the NH transition). Returns
    False when the failure is terminal or the attempt cap is reached.

    Classification logic (see ``bob3.rca_classifier``):

    - ``code_emission_defect``: emitted code is wrong but plausibly fixable
      by a different subagent attempt. Grant if ``refinement_attempts < 5``.
    - ``spec_ambiguity``: genuinely terminal — no code could satisfy the spec.
      NH stands.
    - ``infra_transient``: subprocess/IO/network error. Grant unconditionally
      (handled by the existing ``auto_reset_if_infra`` path; this function
      is *not* responsible for infra resets, but returns False so the caller
      falls through to that path).

    Parameters
    ----------
    feature_id:
        The feature UUID.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature record.
        Matches the signature of ``bob3.db.update_feature``.
    failed_acs:
        Acceptance-criteria strings (or error messages) that caused the
        verification gate to fail.
    refinement_attempts:
        Current refinement attempt count BEFORE this reset.
    workspace:
        Optional path to the feature workspace (unused by this function,
        reserved for future logging extensions).

    Returns
    -------
    True
        Feature has been reset to ``ready``; caller must not NH-demote.
    False
        Failure is terminal (spec_ambiguity or cap reached) or infra;
        caller should continue with its normal recovery logic.
    """
    classification = classify_verification_failure(failed_acs)

    if classification == "infra_transient":
        # Infra path is handled by auto_reset_if_infra; don't double-handle.
        logger.debug(
            "rca.auto_reset_on_code_defect: feature %s classified infra_transient "
            "— deferring to infra recovery path",
            feature_id[:8],
        )
        return False

    if classification == "spec_ambiguity":
        logger.debug(
            "rca.auto_reset_on_code_defect: feature %s spec_ambiguity — NH stands",
            feature_id[:8],
        )
        return False

    # code_emission_defect
    if not should_grant_fresh_attempt(classification, refinement_attempts):
        logger.debug(
            "rca.auto_reset_on_code_defect: feature %s code_emission_defect "
            "at cap (attempts=%d >= %d) — NH stands",
            feature_id[:8],
            refinement_attempts,
            _MAX_ATTEMPTS,
        )
        return False

    # Grant fresh attempt: reopen to ready WITHOUT resetting attempt count
    # (budget accounting: the attempt number is preserved so the 5-attempt
    # cap remains enforceable across resets).
    db_update_fn(feature_id, status="ready")
    logger.info(
        "rca.auto_reset_on_code_defect: rca_granted_fresh_attempt=%s:%s "
        "(attempts=%d, preserving budget)",
        feature_id,
        classification,
        refinement_attempts,
    )
    return True


# ---------------------------------------------------------------------------
# Startup-crash exemption integration (F-R7-613)
# ---------------------------------------------------------------------------


def is_mid_work_transport_crash(
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True iff the mid-work crash is a transport-transient failure.

    A transport crash is defined as: the exit signature matches a known
    transport-transient pattern (self-signed cert, ECONNRESET, ETIMEDOUT,
    MCP plugin failures, etc.) AND there are zero persisted implementation
    artifacts in the workspace.

    When zero artifacts are present, no real work was lost — the sub-agent
    was doing reasoning work only. Granting a free retry avoids burning the
    5-attempt budget on infra noise.

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
        ``True`` when this is a transport crash with no work lost.
        ``False`` otherwise.
    """
    return is_transport_crash(exit_signature=exit_signature, workspace=workspace)


def exempt_mid_work_crash_from_retry(
    *,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None,
    exempt_counter: int,
) -> dict:
    """Apply the transport-crash vs work-loss exemption policy.

    Wraps ``startup_crash_exempt.try_exempt`` and returns a plain dict so
    callers do not need to import the StartupCrashExemptOutcome dataclass.

    Decision tree:
    1. If ``exempt_counter`` >= 25: CAP_REACHED — fall through to original retry path.
    2. If workspace has persisted artifacts: CHARGE — genuine work-loss crash.
    3. If exit signature matches transport-transient AND no artifacts: EXEMPT.
    4. Otherwise: CHARGE — unclassified crash.

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
    dict with keys:
        ``decision``:            ``"exempt"`` | ``"charge"`` | ``"cap_reached"``
        ``backoff_seconds``:     int >= 0
        ``artifact_count``:      int >= 0
        ``exempt_counter_after``: int
        ``evidence``:            str

    Raises
    ------
    ValueError
        When ``exempt_counter`` is not an int, or ``exit_signature`` is
        not a str or None.
    """
    outcome: StartupCrashExemptOutcome = try_exempt(
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


def classify_failure_cause(failed_acs: list[str]) -> Classification:
    """Classify why a verification gate failed — alias of classify_verification_failure_cause.

    This name satisfies the F-R7-479 AC "Function defined: bob3.rca.classify_failure_cause"
    while delegating to the canonical implementation.

    Parameters
    ----------
    failed_acs:
        List of AC strings or error messages that caused verification to fail.
        Must be a list; raises TypeError for non-list, ValueError for None.

    Returns
    -------
    ``"infra_transient"``      if any AC matches an infrastructure error pattern.
    ``"code_emission_defect"`` if any AC starts with a behavior/integration/pytest prefix.
    ``"spec_ambiguity"``       otherwise — including empty list.
    """
    return classify_verification_failure_cause(failed_acs)


def classify_failure_as_code_emission_defect(failed_acs: list[str]) -> bool:
    """Return True iff the verification failure is a plausibly-fixable code emission defect.

    This is a predicate wrapper around ``classify_verification_failure_cause``
    that answers the yes/no question: "is this a code defect (not infra, not ambiguity)?"

    Satisfies the F-R7-479 AC "Function defined: bob3.rca.classify_failure_as_code_emission_defect".

    Parameters
    ----------
    failed_acs:
        List of AC strings or error messages that caused verification to fail.
        Must be a list; raises TypeError for non-list, ValueError for None.

    Returns
    -------
    True  if classification is ``"code_emission_defect"``.
    False for ``"infra_transient"`` or ``"spec_ambiguity"``.
    """
    return classify_verification_failure_cause(failed_acs) == "code_emission_defect"


def should_grant_fresh_attempt_on_code_defect(
    failed_acs: list[str],
    refinement_attempts: int,
) -> bool:
    """Return True when a code-emission defect warrants a fresh attempt budget.

    Combines classification and grant-decision into one call:
    1. Classifies ``failed_acs`` via ``classify_verification_failure_cause``.
    2. If classified as ``"code_emission_defect"``, delegates to
       ``should_grant_fresh_attempt_budget`` with the given attempt count.
    3. For ``"infra_transient"`` or ``"spec_ambiguity"`` returns False
       (infra is handled by the dedicated infra recovery path; spec_ambiguity
       is terminal).

    Satisfies the F-R7-479 AC "Function defined: bob3.rca.should_grant_fresh_attempt_on_code_defect".

    Parameters
    ----------
    failed_acs:
        List of AC strings or error messages that caused verification to fail.
        Must be a list; raises TypeError for non-list, ValueError for None.
    refinement_attempts:
        Current refinement attempt count. Must be a non-negative int.

    Returns
    -------
    True  if classification is ``"code_emission_defect"`` and attempt count < 5.
    False otherwise (at cap, not a code defect, or infra/ambiguity path).
    """
    classification = classify_verification_failure_cause(failed_acs)
    if classification != "code_emission_defect":
        return False
    return should_grant_fresh_attempt_budget(classification, refinement_attempts)
