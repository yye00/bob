"""F-R7-479: auto-reset logic for verification-gate failures.

Exposes ``should_grant_fresh_attempt`` — the decision gate that determines
whether a verification-gate failure on plausibly-fixable code ACs warrants
a fresh attempt budget rather than an immediate needs_human transition.

Classification logic:
- ``code_emission_defect``: emitted code is wrong but plausibly fixable.
  Grant if refinement_attempts < 5 (the cap).
- ``infra_transient``: subprocess/IO/network failure. Always grant.
- ``spec_ambiguity``: genuinely terminal. NH stands.
"""

from __future__ import annotations

from bob.orchestrator.rca_attempt_budget import (
    Classification,
    should_grant_fresh_attempt as _should_grant,
)

_MAX_ATTEMPTS = 5


def should_grant_fresh_attempt(
    classification: Classification,
    refinement_attempts: int,
) -> bool:
    """Return True if the feature should receive another attempt budget.

    Parameters
    ----------
    classification:
        One of ``"code_emission_defect"``, ``"spec_ambiguity"``, ``"infra_transient"``.
    refinement_attempts:
        Current refinement attempt count.

    Returns
    -------
    True if a fresh attempt should be granted, False otherwise.
    """
    return _should_grant(classification, refinement_attempts)
