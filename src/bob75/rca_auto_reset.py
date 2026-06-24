"""bob75.rca_auto_reset — F-R7-479 fresh-attempt budget gate.

Re-exports the canonical implementation from bob.rca so that the bob75 package
satisfies the acceptance criterion ``File exists: src/bob75/rca_auto_reset.py``
and ``Function defined: bob75.rca_auto_reset.should_grant_fresh_attempt``.

The key decision logic:
- ``code_emission_defect``: emitted code is wrong but plausibly fixable by a
  different subagent attempt. Grant if refinement_attempts < 5.
- ``spec_ambiguity``: genuinely terminal. NH stands. No grant.
- ``infra_transient``: subprocess/IO/network error. Always grant.
"""

from __future__ import annotations

from bob.rca import (
    classify_verification_failure_cause,
    should_grant_fresh_attempt_budget,
)
from bob.rca_classifier import (
    Classification,
    classify_verification_failure,
    should_grant_fresh_attempt,
)

__all__ = [
    "Classification",
    "classify_verification_failure",
    "classify_verification_failure_cause",
    "should_grant_fresh_attempt",
    "should_grant_fresh_attempt_budget",
]
