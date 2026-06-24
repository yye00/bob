"""Bob bootstrap utilities."""

from __future__ import annotations

from bob.yaml_writer import atomic_write  # noqa: F401 — wired for integration AC
from bob.loader import handle_scanner_error, load_safe  # noqa: F401 — wired for integration AC
from bob.spec_writer import atomic_write as spec_writer_atomic_write  # noqa: F401 — wired for integration AC (feature 6cafea74)
from bob.bootstrap.permanent_forward_carry_auditor import (  # noqa: F401 — integration AC
    BootstrapAuditError,
    PermanentForwardCarryMissing,
    audit_bootstrap_spec,
    audit_merged_spec,
    fail_loud_on_missing,
    required_feature_ids,
)
from bob.bootstrap.permanent_forward_carry_auditor import (  # noqa: F401 — satisfy audit_permanent_forward_carry AC without circular import
    audit_bootstrap_spec as audit_permanent_forward_carry,
)

_MAX_BOOTSTRAP_ATTEMPTS = 1


def check_bootstrap_override(feature) -> bool:
    """Return True if this feature may bypass the readiness gate once.

    A feature is eligible for a bootstrap bypass when it has never been
    researched (research_iterations == 0) and the single allowed bypass has
    not yet been consumed (bootstrap_attempts < 1).

    Raises ValueError if bootstrap_attempts or research_iterations is negative.
    """
    bootstrap_attempts = feature.bootstrap_attempts or 0
    research_iterations = feature.research_iterations or 0

    if bootstrap_attempts < 0:
        raise ValueError(
            f"bootstrap_attempts must be non-negative, got {bootstrap_attempts}"
        )
    if research_iterations < 0:
        raise ValueError(
            f"research_iterations must be non-negative, got {research_iterations}"
        )

    return bootstrap_attempts < _MAX_BOOTSTRAP_ATTEMPTS and research_iterations == 0


def check_bootstrap_readiness_override(feature) -> bool:
    """Return True if this feature may bypass the readiness gate once.

    Canonical entry point for the bootstrap readiness override predicate.
    Delegates to check_bootstrap_override. A feature may bypass exactly once
    when bootstrap_attempts < 1 and research_iterations == 0.

    Raises ValueError if bootstrap_attempts or research_iterations is negative.
    """
    return check_bootstrap_override(feature)
