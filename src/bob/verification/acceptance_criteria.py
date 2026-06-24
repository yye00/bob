"""bob.verification.acceptance_criteria — AC checking entry point.

Exposes acceptance-criteria validation functions from the canonical
``bob.enhanced_verification`` and ``bob.verification.verifier`` implementations
under the ``bob.verification.acceptance_criteria`` namespace.

This module satisfies the integration AC

    integration: bob.verification.acceptance_criteria

by providing a single importable surface for the Pattern 8 integration
AC resolver (``bob.verification.integration_ac_resolver``) and the
enhanced-verification checker (``_check_criterion``).

Public API
----------
check_criterion(criterion, workspace, feature_id=None) -> tuple[bool, str]
    Thin wrapper around the enhanced_verification criterion checker that
    returns (passed: bool, reason: str).

resolve_integration_criterion(criterion, workspace) -> tuple[bool, str]
    Delegates to ``bob.verification.integration_ac_resolver.resolve_integration_ac``
    for 'integration:'-prefixed ACs.
"""

from __future__ import annotations

import pathlib

from bob.verification.integration_ac_resolver import (  # noqa: F401
    extract_integration_targets,
    resolve_integration_ac,
    log_integration_ac_prose_demoted,
)


def check_criterion(
    criterion: str,
    workspace: pathlib.Path,
    feature_id: str | None = None,
) -> tuple[bool, str]:
    """Check a single acceptance criterion and return (passed, reason).

    Delegates to ``bob.enhanced_verification._check_criterion`` for all
    pattern matching (Pattern 1–10, prose-AC demotion, etc.).

    Parameters
    ----------
    criterion:
        The raw criterion string (e.g. "Function defined: foo.bar").
    workspace:
        Path to the project root.
    feature_id:
        Optional feature UUID for logging purposes.
    """
    from bob.enhanced_verification import _check_criterion

    passed = _check_criterion(criterion, workspace)
    reason = "" if passed else f"criterion not satisfied: {criterion}"
    return (passed, reason)


def resolve_integration_criterion(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str]:
    """Resolve an 'integration:' AC using the Pattern 8 resolver.

    Delegates entirely to
    ``bob.verification.integration_ac_resolver.resolve_integration_ac``.
    """
    return resolve_integration_ac(criterion, workspace)


__all__ = [
    "check_criterion",
    "resolve_integration_criterion",
    "extract_integration_targets",
    "resolve_integration_ac",
    "log_integration_ac_prose_demoted",
]
