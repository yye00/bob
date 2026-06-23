"""Full 22-smell linter for spec quality (F-R7-410 extension).

Re-exports the complete public API from bob3.linter_22_smells under the
canonical module name ``bob3.linter_22_smell``.

Severities: E (Error), W (Warning), I (Informational).
E-severity smells block ``bob3 plan --create``.

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02, S05,
S06, S07, S08, S18). When unavailable, those detectors fall back to regex
heuristics.

Public API::

    from bob3.linter_22_smell import detect_smells, filter_by_severity, SmellFinding

    findings = detect_smells("The system shall be fast and simple.")
    if any(f.blocks_plan for f in findings):
        raise RuntimeError("E-severity smells block plan --create")

    errors = filter_by_severity(findings, "E")
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

__all__ = [
    "detect_smells",
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
