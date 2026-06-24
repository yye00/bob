"""Public API for the 22-smell spec linter (F-R7-410 extension).

Exposes the full 22-detector catalogue (Femmer/Smella + 2025 LLM extensions)
as a top-level ``bob`` module. Severity levels E/W/I; E-severity findings
block ``bob plan --create``.

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02, S05, S06,
S07, S08, S18). When unavailable, those detectors fall back to regex heuristics.

Public API::

    from bob.linter_22_smells import (
        detect_smells,
        SmellFinding,
        blocks_plan_create,
        SmellSeverity,
    )

    findings = detect_smells("The system shall be fast and simple.")
    if blocks_plan_create(findings):
        raise RuntimeError("E-severity smells found — fix spec before plan --create")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bob.spec_quality.smell_catalog import (
    SMELL_CATALOG,
    SMELL_BY_ID,
    BLOCKING_SMELLS,
    SPACY_SMELLS,
    SmellDefinition,
    Severity as SmellSeverity,
)
from bob.spec_quality.smell_detectors import (
    SmellFinding,
    detect_all,
    severity_of,
    is_blocking,
    detector_count,
    spacy_backed_detectors,
    blocks_plan_create,
    SpacyModelMissingError,
    handle_missing_spacy_model,
)


__all__ = [
    "detect_smells",
    "detect_all_smells",
    "filter_by_severity",
    "get_severity",
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
        Other criteria in the same feature (used for S22 cross-check: does a
        behavior: criterion have a matching pytest: criterion?).
    known_feature_ids:
        Set of valid feature IDs in the spec (used for S17 dangling-ref check).

    Returns
    -------
    list[SmellFinding]
        Findings ordered by smell ID. Empty when the text is clean.
        Each finding has ``severity`` ("E", "W", or "I") and ``blocks_plan``
        (True for E-severity smells that block ``bob plan --create``).

    Examples
    --------
    >>> findings = detect_smells("The system shall be fast and simple.")
    >>> any(f.blocks_plan for f in findings)
    True
    >>> findings = detect_smells("pytest: tests/test_foo.py -v")
    >>> findings
    []
    """
    return detect_all(
        text=text,
        peer_criteria=peer_criteria,
        known_feature_ids=known_feature_ids,
    )


def get_severity(smell_id: str) -> str:
    """Return the severity level ("E", "W", or "I") for a given smell ID.

    Parameters
    ----------
    smell_id:
        A smell identifier such as ``"S01"`` through ``"S22"``.

    Returns
    -------
    str
        ``"E"`` (error), ``"W"`` (warning), or ``"I"`` (informational).

    Raises
    ------
    KeyError
        When ``smell_id`` is not in the catalogue.

    Examples
    --------
    >>> get_severity("S01")
    'E'
    >>> get_severity("S15")
    'I'
    """
    return severity_of(smell_id)


def filter_by_severity(
    findings: list[SmellFinding],
    severity: SmellSeverity,
) -> list[SmellFinding]:
    """Return only those findings whose severity matches ``severity``.

    Parameters
    ----------
    findings:
        List of :class:`SmellFinding` returned by :func:`detect_smells`.
    severity:
        One of ``"E"`` (error), ``"W"`` (warning), or ``"I"`` (informational).

    Returns
    -------
    list[SmellFinding]
        Subset of ``findings`` whose ``severity`` attribute equals the
        requested level. Returns an empty list when no findings match.

    Raises
    ------
    ValueError
        When ``severity`` is not one of the three valid levels.

    Examples
    --------
    >>> findings = detect_smells("The system shall be fast.")
    >>> errors = filter_by_severity(findings, "E")
    >>> all(f.severity == "E" for f in errors)
    True
    """
    valid = {"E", "W", "I"}
    if severity not in valid:
        raise ValueError(
            f"Invalid severity {severity!r}; must be one of {sorted(valid)}"
        )
    return [f for f in findings if f.severity == severity]
