"""RCA failure classifier for verification-gate failures.

Classifies verification gate failures to determine whether another attempt
should be granted (code_emission_defect), the failure is genuinely terminal
(spec_ambiguity), or infrastructure-caused (infra_transient).

This module exposes the public API used by bob.rca.auto_reset_on_code_defect
and delegated to by bob.orchestrator.rca_infra_recovery.
"""

from __future__ import annotations

from bob.orchestrator.rca_attempt_budget import (
    Classification,
    classify_verification_failure,
    should_grant_fresh_attempt,
)

__all__ = [
    "Classification",
    "classify_verification_failure",
    "should_grant_fresh_attempt",
]
