"""F-R7-479: bob74 shim for RCA auto-reset — grants fresh attempt budget on code-fixable failures.

Re-exports the full public API from bob3.rca_auto_reset / bob3.rca_classifier so that
bob74 callers can import from ``bob74.rca_auto_reset`` without coupling to the bob3
internal layout.

Classification logic:
- ``code_emission_defect``: emitted code is wrong but plausibly fixable by a
  different subagent attempt. Grant if refinement_attempts < 5.
- ``spec_ambiguity``: genuinely terminal. NH stands.
- ``infra_transient``: subprocess/IO/network error. Always grant (existing path).
"""

from __future__ import annotations

from bob3.orchestrator.rca_attempt_budget import (
    Classification,
    classify_verification_failure,
    should_grant_fresh_attempt,
)
from bob3.rca import auto_reset_on_code_defect, classify_verification_failure_cause, should_grant_fresh_attempt_budget

__all__ = [
    "Classification",
    "classify_verification_failure",
    "should_grant_fresh_attempt",
    "classify_verification_failure_cause",
    "should_grant_fresh_attempt_budget",
    "auto_reset_on_code_defect",
]
