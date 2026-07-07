"""Verifier-extension AC discipline rule (hippy namespace).

Companion to F-R7-592. Features that extend the verifier itself cannot
reliably express behavior ACs against their own new patterns — the running
verifier cannot check what it does not yet know. All ACs for such features
MUST be either:

  - structural  ("file X contains regex/literal Y") — any verifier version
    can check this
  - integration pytest ("pytest tests/test_X.py::test_Y passes") — runs
    against post-change code directly

This module enforces the rule at spec-extraction time: when a feature's
primary diff target includes a :data:`VERIFIER_EXTENSION_MODULES` path,
every AC line starting with 'behavior:' is rejected (demoted to a
skip-with-note) and a WARNING is emitted suggesting the structural or
integration form.

The canonical implementation lives in :mod:`bob.spec_quality.spec_extractor`;
this module re-exposes it under the hippy namespace with the AC-named entry
points the spec extractor pipeline expects.

Integration: :mod:`hippy.spec_extractor`.
"""

from __future__ import annotations

import logging

from bob.spec_quality.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    _is_verifier_extension,
    filter_behavior_acs_for_verifier_extension,
)

logger = logging.getLogger(__name__)


def is_verifier_extension_target(primary_diff_target: str) -> bool:
    """Return True when *primary_diff_target* names a verifier-extension module.

    A feature is a verifier extension when its primary diff target includes any
    path from :data:`VERIFIER_EXTENSION_MODULES`. Empty/falsy targets are never
    verifier extensions.

    Parameters
    ----------
    primary_diff_target:
        The primary file/module this feature changes.

    Returns
    -------
    bool
    """
    return _is_verifier_extension(primary_diff_target)


def reject_behavior_acs_for_verifier_extensions(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Reject behavior ACs for verifier-extension features at extraction time.

    When *primary_diff_target* resolves to a :data:`VERIFIER_EXTENSION_MODULES`
    path, every AC line starting with 'behavior:' (case-insensitive) is demoted
    to a skip-with-note string and a WARNING is emitted suggesting the
    structural or integration pytest form. Non-verifier-extension features pass
    through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings extracted from the spec.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier used in log messages for context.

    Returns
    -------
    ACFilterResult
        ``filtered_acs``, ``demoted``, and ``is_verifier_extension``.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list (invalid input type).
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got "
            f"{type(acceptance_criteria).__name__!r}"
        )

    result = filter_behavior_acs_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )

    if result.is_verifier_extension and result.demoted:
        logger.warning(
            "AC discipline: %d behavior AC(s) rejected for verifier-extension "
            "feature (primary_diff_target=%r, feature_id=%r). Use 'structural:' "
            "or 'integration: pytest ...' forms instead.",
            len(result.demoted),
            primary_diff_target,
            feature_id,
        )

    return result


__all__ = [
    "ACFilterResult",
    "DemotedAC",
    "VERIFIER_EXTENSION_MODULES",
    "is_verifier_extension_target",
    "reject_behavior_acs_for_verifier_extensions",
]
