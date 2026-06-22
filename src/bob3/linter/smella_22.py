"""22-smell linter for bob3.linter (F-R7-410 full extension).

Provides the primary entry points ``detect_all_smells`` and
``filter_by_severity`` for the full 22-detector Femmer/Smella +
2025-LLM-extension catalogue.

Severities:
  E - Error: blocks ``bob3 plan --create``
  W - Warning: surfaced but does not block
  I - Informational: advisory only

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02, S05,
S06, S07, S08, S18). When unavailable those detectors fall back to regex
heuristics.

Public API::

    from bob3.linter.smella_22 import detect_all_smells, filter_by_severity

    findings = detect_all_smells("The system shall be fast and simple.")
    errors = filter_by_severity(findings, "E")
    blocking = [f for f in findings if f.blocks_plan]
"""

from __future__ import annotations

from bob3.spec_quality.smell_catalog import (
    BLOCKING_SMELLS,
    SMELL_BY_ID,
    SMELL_CATALOG,
    SPACY_SMELLS,
    Severity,
    SmellDefinition,
)
from bob3.spec_quality.smell_detectors import (
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
    "detect_all_smells",
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


def detect_all_smells(
    text: str,
    peer_criteria: list[str] | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> list[SmellFinding]:
    """Run all 22 smell detectors against a single acceptance-criterion text.

    This is the primary entry point for the F-R7-410 extended linter,
    replacing the earlier small regex rule set with the full Femmer/Smella
    + 2025 LLM-extension catalogue.

    Parameters
    ----------
    text:
        The acceptance criterion string to lint. Must be a ``str``; any
        other type raises ``ValueError``.
    peer_criteria:
        Other criteria in the same feature (used by S22: does a
        ``behavior:`` AC have a matching ``pytest:`` AC?).
    known_feature_ids:
        Set of valid feature IDs in the spec (used by S17: dangling-ref
        check). Pass ``None`` to skip cross-reference validation.

    Returns
    -------
    list[SmellFinding]
        Findings ordered by smell ID. Empty when the text is clean.
        Each finding has:
          - ``smell_id``    – e.g. ``"S01"``
          - ``severity``    – ``"E"``, ``"W"``, or ``"I"``
          - ``blocks_plan`` – ``True`` for E-severity findings
          - ``detail``      – human-readable explanation

    Raises
    ------
    ValueError
        When *text* is not a ``str`` instance.

    Examples
    --------
    >>> from bob3.linter.smella_22 import detect_all_smells
    >>> findings = detect_all_smells("The system shall be fast and simple.")
    >>> any(f.blocks_plan for f in findings)
    True
    >>> detect_all_smells("pytest: tests/test_foo.py")
    []
    """
    if not isinstance(text, str):
        raise ValueError(
            f"detect_all_smells expects a str, got {type(text).__name__!r}"
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
        List of :class:`SmellFinding` returned by :func:`detect_all_smells`.
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
    >>> from bob3.linter.smella_22 import detect_all_smells, filter_by_severity
    >>> findings = detect_all_smells("The system shall be fast.")
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
