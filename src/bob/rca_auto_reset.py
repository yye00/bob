"""RCA auto-reset module for F-R7-479: grant fresh attempt on code-fixable failures.

Exposes ``should_grant_fresh_attempt`` and ``should_grant_fresh_attempt_budget``
(and re-exports the full public API) so that the orchestration loop can call
``bob.rca_auto_reset.should_grant_fresh_attempt_budget`` to decide whether a
verification-gate failure warrants another attempt instead of escalating to
needs_human.

Classification logic:
- ``code_emission_defect``: emitted code is wrong but plausibly fixable by a
  different subagent attempt. Grant if refinement_attempts < 5.
- ``spec_ambiguity``: genuinely terminal. NH stands.
- ``infra_transient``: subprocess/IO/network error. Always grant (existing path).
"""

from __future__ import annotations

from bob.orchestrator.rca_attempt_budget import (
    Classification,
    classify_verification_failure,
    should_grant_fresh_attempt,
)
from bob.rca import (
    auto_reset_on_code_defect,
    classify_failure_as_code_emission_defect,
    classify_failure_cause as _classify_failure_cause,
    classify_verification_failure_cause,
    should_grant_fresh_attempt_budget,
)

# AC-required canonical name: bob.rca_auto_reset.grant_fresh_attempt_on_code_defect
grant_fresh_attempt_on_code_defect = auto_reset_on_code_defect

# AC-required canonical name: bob.rca_auto_reset.should_grant_fresh_budget
# (short alias for should_grant_fresh_attempt_budget — same logic, same signature)
should_grant_fresh_budget = should_grant_fresh_attempt_budget

__all__ = [
    "Classification",
    "classify_failure_as_code_emission_defect",
    "classify_verification_failure",
    "classify_verification_failure_cause",
    "should_grant_fresh_attempt",
    "should_grant_fresh_attempt_budget",
    "should_grant_fresh_budget",
    "auto_reset_on_code_defect",
    "grant_fresh_attempt_on_code_defect",
]
