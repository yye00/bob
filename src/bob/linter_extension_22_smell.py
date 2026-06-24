"""Full 22-smell linter extension — bob.linter_extension_22_smell.

This module is the canonical entry point for the 22-detector catalogue
(Femmer/Smella + 2025 LLM extensions) as required by feature 8a8802cf.

Severity levels:
  E - Error:          blocks ``bob plan --create``
  W - Warning:        surfaced but does not block
  I - Informational:  advisory only

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02, S05,
S06, S07, S08, S18). When unavailable those detectors fall back to regex
heuristics.

Public API::

    from bob.linter_extension_22_smell import detect_smells, validate_severity

    findings = detect_smells("The system shall be fast and simple.")
    validate_severity("E")   # returns "E"
    validate_severity("X")   # raises ValueError
"""

from __future__ import annotations

from typing import Literal

from bob.linter_22_smells import (
    BLOCKING_SMELLS,
    SMELL_CATALOG,
    SMELL_BY_ID,
    SPACY_SMELLS,
    SmellDefinition,
    SmellFinding,
    SmellSeverity,
    SpacyModelMissingError,
    blocks_plan_create,
    detect_smells as _detect_smells,
    detector_count,
    filter_by_severity,
    handle_missing_spacy_model,
    is_blocking,
    severity_of,
    spacy_backed_detectors,
)


__all__ = [
    "detect_smells",
    "validate_severity",
    "filter_by_severity",
    "SmellFinding",
    "SmellDefinition",
    "SmellSeverity",
    "SMELL_CATALOG",
    "SMELL_BY_ID",
    "BLOCKING_SMELLS",
    "SPACY_SMELLS",
    "blocks_plan_create",
    "severity_of",
    "is_blocking",
    "detector_count",
    "spacy_backed_detectors",
    "SpacyModelMissingError",
    "handle_missing_spacy_model",
]

_VALID_SEVERITIES: frozenset[str] = frozenset({"E", "W", "I"})


def detect_smells(
    text: str,
    peer_criteria: list[str] | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> list[SmellFinding]:
    """Run all 22 smell detectors against a single acceptance-criterion text.

    Parameters
    ----------
    text:
        The acceptance criterion string to lint.
    peer_criteria:
        Other criteria in the same feature (used by S22: does a behavior: AC
        have a matching pytest: AC?).
    known_feature_ids:
        Set of valid feature IDs in the spec (used by S17 dangling-ref check).

    Returns
    -------
    list[SmellFinding]
        Findings ordered by smell ID. Empty when the text is clean.

    Raises
    ------
    ValueError
        When ``text`` is not a string.

    Examples
    --------
    >>> findings = detect_smells("The system shall be fast and simple.")
    >>> any(f.blocks_plan for f in findings)
    True
    >>> detect_smells("")
    []
    """
    if not isinstance(text, str):
        raise ValueError(f"text must be a str, got {type(text).__name__!r}")
    return _detect_smells(
        text=text,
        peer_criteria=peer_criteria,
        known_feature_ids=known_feature_ids,
    )


def validate_severity(severity: str) -> Literal["E", "W", "I"]:
    """Validate and return a severity string.

    Parameters
    ----------
    severity:
        Severity code to validate. Must be one of ``"E"``, ``"W"``, or ``"I"``.

    Returns
    -------
    str
        The same value as ``severity`` if valid (``"E"``, ``"W"``, or ``"I"``).

    Raises
    ------
    ValueError
        When ``severity`` is not one of the three valid levels.

    Examples
    --------
    >>> validate_severity("E")
    'E'
    >>> validate_severity("W")
    'W'
    >>> validate_severity("I")
    'I'
    >>> validate_severity("X")
    Traceback (most recent call last):
        ...
    ValueError: Invalid severity 'X'; must be one of ['E', 'I', 'W']
    """
    if severity not in _VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity {severity!r}; must be one of {sorted(_VALID_SEVERITIES)}"
        )
    return severity  # type: ignore[return-value]
