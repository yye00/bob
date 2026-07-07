"""Full 22-smell detector catalogue for ``bob.linter`` (F-R7-410 extension).

This module replaces F-R7-410's original small regex rule set with the full
22-detector Femmer/Smella + 2025-LLM-extension catalogue. It is the canonical
``bob.linter.smell_detectors`` entry point named by the feature's acceptance
criteria.

Severities:
  E - Error: blocks ``bob plan --create``
  W - Warning: surfaced but does not block
  I - Informational: advisory only

spaCy (``en_core_web_sm``) is used by 7 of the 22 detectors (S01, S02, S05,
S06, S07, S08, S18). When unavailable those detectors fall back to regex
heuristics.

Public API::

    from bob.linter.smell_detectors import detect_smells, blocks_plan_create

    findings = detect_smells("The system shall be fast and simple.")
    if blocks_plan_create(findings):
        raise RuntimeError("E-severity smells block plan --create")
"""

from __future__ import annotations

from bob.spec_quality.smell_catalog import (
    BLOCKING_SMELLS,
    SMELL_BY_ID,
    SMELL_CATALOG,
    SPACY_SMELLS,
    Severity,
    SmellDefinition,
)
from bob.spec_quality.smell_detectors import (
    SmellFinding,
    SpacyModelMissingError,
    blocks_plan_create,
    detect_all,
    detector_count,
    handle_missing_spacy_model,
    is_blocking,
    severity_of,
    spacy_backed_detectors,
)

SmellSeverity = Severity

__all__ = [
    "detect_smells",
    "filter_by_severity",
    "SmellFinding",
    "SmellDefinition",
    "SmellSeverity",
    "Severity",
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

    This is the canonical entry point for the F-R7-410 extended linter,
    replacing the earlier small regex rule set with the full Femmer/Smella
    + 2025 LLM-extension catalogue. E-severity findings block
    ``bob plan --create``.

    Parameters
    ----------
    text:
        The acceptance criterion string to lint. Must be a ``str``; any
        other type raises ``ValueError`` (error path).
    peer_criteria:
        Other criteria in the same feature (used by S22: does a ``behavior:``
        AC have a matching ``pytest:`` AC?). ``None`` skips the cross-check.
    known_feature_ids:
        Set of valid feature IDs in the spec (used by S17: dangling-ref
        check). ``None`` skips cross-reference validation.

    Returns
    -------
    list[SmellFinding]
        Findings ordered by smell ID. Empty when the text is clean or empty
        (boundary case). Each finding has ``severity`` ("E", "W", or "I") and
        ``blocks_plan`` (True for E-severity smells).

    Raises
    ------
    ValueError
        When *text* is not a ``str`` instance.

    Examples
    --------
    >>> any(f.blocks_plan for f in detect_smells("The system shall be fast."))
    True
    >>> detect_smells("pytest: tests/test_foo.py")
    []
    >>> detect_smells("")
    []
    """
    if not isinstance(text, str):
        raise ValueError(
            f"detect_smells expects a str, got {type(text).__name__!r}"
        )
    return detect_all(
        text=text,
        peer_criteria=peer_criteria,
        known_feature_ids=known_feature_ids,
    )


def filter_by_severity(
    findings: list[SmellFinding],
    severity: Severity,
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
        Subset of ``findings`` whose ``severity`` equals the requested level.

    Raises
    ------
    ValueError
        When ``severity`` is not one of the three valid levels.
    """
    valid = {"E", "W", "I"}
    if severity not in valid:
        raise ValueError(
            f"Invalid severity {severity!r}; must be one of {sorted(valid)}"
        )
    return [f for f in findings if f.severity == severity]
