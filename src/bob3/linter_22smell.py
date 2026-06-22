"""Full 22-smell linter for spec quality (F-R7-410 extension).

Re-exports the complete public API from bob3.linter_22_smells under the
canonical module name ``bob3.linter_22smell`` (no trailing 's').

Severities: E (Error), W (Warning), I (Informational).
E-severity smells block ``bob3 plan --create``.

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02, S05,
S06, S07, S08, S18). When unavailable, those detectors fall back to regex
heuristics.

Public API::

    from bob3.linter_22smell import detect_smells, SmellFinding, blocks_plan_create

    findings = detect_smells("The system shall be fast and simple.")
    if blocks_plan_create(findings):
        raise RuntimeError("E-severity smells block plan --create")
"""

from __future__ import annotations

from bob3.linter_22_smells import (
    BLOCKING_SMELLS,
    SMELL_BY_ID,
    SMELL_CATALOG,
    SPACY_SMELLS,
    SmellDefinition,
    SmellFinding,
    SmellSeverity,
    SpacyModelMissingError,
    blocks_plan_create,
    detect_smells,
    detector_count,
    filter_by_severity,
    handle_missing_spacy_model,
    is_blocking,
    severity_of,
    spacy_backed_detectors,
)


def apply_severity_filter(
    findings: list[SmellFinding],
    severity: str,
) -> list[SmellFinding]:
    """Return only those findings whose severity matches ``severity``.

    Alias for :func:`filter_by_severity` satisfying the F-R7-410 AC.

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
        requested level.

    Raises
    ------
    ValueError
        When ``severity`` is not one of the three valid levels.
    """
    return filter_by_severity(findings, severity)


__all__ = [
    "detect_smells",
    "apply_severity_filter",
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
