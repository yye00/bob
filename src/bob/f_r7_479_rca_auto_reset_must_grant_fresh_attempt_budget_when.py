"""F-R7-479: RCA auto-reset MUST grant fresh attempt budget when verification-gate failure
is plausibly-fixable code — not just infra/transient.

The 5-attempt cap exists precisely because verification failures are often code-fixable
on retry (different subagent may produce correct emission). Treating ALL non-infra
verification failures as terminal defeats the budget.

This module exposes ``f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when`` as
the canonical entry point, delegating to ``bob.rca.auto_reset_on_code_defect``.
"""

from __future__ import annotations

import os
from typing import Callable

from bob.rca import (
    auto_reset_on_code_defect,
    classify_verification_failure_cause,
    should_grant_fresh_attempt_budget,
)
from bob.rca_classifier import Classification


def f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
    feature_id: str,
    db_update_fn: Callable[..., None],
    failed_acs: list[str],
    refinement_attempts: int,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Grant fresh attempt budget when verification-gate failure is code-fixable.

    Decision gate:
    - ``code_emission_defect`` (behavior/integration/pytest AC failed): grant if
      ``refinement_attempts < 5``.
    - ``spec_ambiguity`` (no plausible code could satisfy): NH stands — return False.
    - ``infra_transient`` (subprocess/IO/network): defer to infra recovery — return False.

    Parameters
    ----------
    feature_id:
        Feature UUID.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` updating the feature record (e.g. db.update_feature).
    failed_acs:
        AC strings or error messages that caused the verification gate to fail.
    refinement_attempts:
        Current refinement attempt count BEFORE this potential reset.
    workspace:
        Optional workspace path (reserved for future logging extensions).

    Returns
    -------
    True
        Feature reset to ``ready``; caller must not NH-demote.
    False
        Failure is terminal or infra; caller continues with normal recovery logic.
    """
    return auto_reset_on_code_defect(
        feature_id=feature_id,
        db_update_fn=db_update_fn,
        failed_acs=failed_acs,
        refinement_attempts=refinement_attempts,
        workspace=workspace,
    )


def classify_verification_gate_cause(failed_acs: list[str]) -> "Classification":
    """Classify the cause of a verification-gate failure.

    AC-named entry point (``bob.f_r7_479_...classify_verification_gate_cause``).
    Delegates to ``bob.rca.classify_verification_failure_cause``.

    Parameters
    ----------
    failed_acs:
        AC strings / error messages that caused the gate to fail. Must be a list.

    Returns
    -------
    One of ``"infra_transient"``, ``"code_emission_defect"``, ``"spec_ambiguity"``.

    Raises
    ------
    ValueError
        If ``failed_acs`` is None.
    TypeError
        If ``failed_acs`` is not a list.
    """
    return classify_verification_failure_cause(failed_acs)


def should_reset_attempt_budget(
    failed_acs: list[str],
    refinement_attempts: int,
) -> bool:
    """Decide whether a verification-gate failure warrants a fresh attempt budget.

    AC-named entry point (``bob.f_r7_479_...should_reset_attempt_budget``).
    Classifies the failure, then applies the grant decision:

    - ``code_emission_defect``: reset if ``refinement_attempts < 5``.
    - ``infra_transient``: this function returns ``False`` — infra resets are
      owned by the dedicated infra-recovery path, not the code-defect path.
    - ``spec_ambiguity``: never reset (genuinely terminal).

    Parameters
    ----------
    failed_acs:
        AC strings / error messages that caused the gate to fail. Must be a list.
    refinement_attempts:
        Current refinement attempt count. Must be a non-negative int.

    Returns
    -------
    True when a fresh attempt budget should be granted for a code defect,
    False otherwise.

    Raises
    ------
    ValueError
        If ``failed_acs`` is None or ``refinement_attempts`` is negative.
    TypeError
        If ``failed_acs`` is not a list or ``refinement_attempts`` is not an int.
    """
    classification = classify_verification_failure_cause(failed_acs)
    if classification != "code_emission_defect":
        # Validate refinement_attempts even on the non-grant path so invalid
        # input raises rather than silently returning False.
        should_grant_fresh_attempt_budget(classification, refinement_attempts)
        return False
    return should_grant_fresh_attempt_budget(classification, refinement_attempts)


__all__ = [
    "f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when",
    "classify_verification_gate_cause",
    "should_reset_attempt_budget",
]
