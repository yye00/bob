"""Verifier-extension AC discipline: reject behavior ACs for verifier-extension features.

Provides the canonical ``enforce_ac_discipline`` and ``validate_ac_form`` entry
points for enforcing the rule that features whose primary diff target is a
verifier-extension module MUST NOT carry 'behavior:' acceptance criteria.

The running verifier cannot check patterns it doesn't yet know, so all ACs for
verifier-extension features MUST be either:
  - structural  ("file X contains regex/literal Y")
  - integration pytest ("pytest tests/test_X.py::test_Y passes")

Integrates with bob.spec_quality.spec_extractor for the actual enforcement logic.
"""

from __future__ import annotations

import re

from bob.spec_quality.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    filter_behavior_acs_for_verifier_extension,
)

# Valid AC form prefixes for verifier-extension features.
_VALID_VE_FORMS = re.compile(
    r"^\s*(structural:|integration:|pytest:|File exists:|Function defined:|Class defined:)",
    re.IGNORECASE,
)

_BEHAVIOR_PREFIX = re.compile(r"^\s*behavior\s*:", re.IGNORECASE)


def enforce_ac_discipline(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Enforce AC discipline for verifier-extension features at spec-extraction time.

    When *primary_diff_target* resolves to a VERIFIER_EXTENSION_MODULES path,
    every AC line starting with 'behavior:' is rejected — replaced with a
    skip-with-note string — and a WARNING is emitted suggesting the structural
    or integration pytest form instead.

    Non-verifier-extension features pass through unchanged.

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
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per rejected behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list (invalid input type).
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    return filter_behavior_acs_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


def validate_ac_form(ac: str) -> dict[str, object]:
    """Validate whether an AC string uses an allowed form for verifier-extension features.

    Returns a dict with keys:
      - ``valid``: bool — True when the AC uses a permitted form.
      - ``form``: str — detected form label ("structural", "integration", "pytest",
        "file_exists", "function_defined", "class_defined", "behavior", or "unknown").
      - ``allowed_for_verifier_extension``: bool — True for all non-behavior forms.

    Parameters
    ----------
    ac:
        A single AC string to validate.

    Returns
    -------
    dict
        Validation result with ``valid``, ``form``, and
        ``allowed_for_verifier_extension`` keys.

    Raises
    ------
    ValueError
        If *ac* is not a string.
    """
    if not isinstance(ac, str):
        raise ValueError(f"ac must be a str, got {type(ac).__name__!r}")

    stripped = ac.strip()

    if _BEHAVIOR_PREFIX.match(ac):
        return {"valid": False, "form": "behavior", "allowed_for_verifier_extension": False}

    form_map = [
        (re.compile(r"^\s*structural\s*:", re.IGNORECASE), "structural"),
        (re.compile(r"^\s*integration\s*:", re.IGNORECASE), "integration"),
        (re.compile(r"^\s*pytest\s*:", re.IGNORECASE), "pytest"),
        (re.compile(r"^\s*File exists\s*:", re.IGNORECASE), "file_exists"),
        (re.compile(r"^\s*Function defined\s*:", re.IGNORECASE), "function_defined"),
        (re.compile(r"^\s*Class defined\s*:", re.IGNORECASE), "class_defined"),
    ]
    for pattern, form_label in form_map:
        if pattern.match(ac):
            return {"valid": True, "form": form_label, "allowed_for_verifier_extension": True}

    return {"valid": False, "form": "unknown", "allowed_for_verifier_extension": False}


def reject_behavior_ac(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Reject behavior ACs for verifier-extension features at spec-extraction time.

    When *primary_diff_target* resolves to a VERIFIER_EXTENSION_MODULES path,
    every AC line starting with 'behavior:' is rejected — replaced with a
    skip-with-note string — and a WARNING is emitted suggesting the structural
    or integration pytest form instead.

    Non-verifier-extension features pass through unchanged.

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
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per rejected behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list (invalid input type).
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    return filter_behavior_acs_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


__all__ = [
    "enforce_ac_discipline",
    "validate_ac_form",
    "reject_behavior_ac",
    "ACFilterResult",
    "DemotedAC",
    "VERIFIER_EXTENSION_MODULES",
]
