"""Canonical 22-smell linter module for F-R7-410 extension.

Exposes the full 22-detector catalogue (Femmer/Smella + 2025 LLM extensions)
under the name ``detect_all_smells``. Severities E/W/I; E-severity findings
block ``bob plan --create``.

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02, S05,
S06, S07, S08, S18). When unavailable those detectors fall back to regex
heuristics so linting remains functional.

Public API::

    from bob.linter_22 import detect_all_smells, SmellSeverity

    findings = detect_all_smells("The system shall be fast and simple.")
    if any(f.blocks_plan for f in findings):
        raise RuntimeError("E-severity smells block plan --create")
"""

from __future__ import annotations

import enum

from bob.linter_22_smells import (
    BLOCKING_SMELLS,
    SMELL_BY_ID,
    SMELL_CATALOG,
    SPACY_SMELLS,
    SmellDefinition,
    SmellFinding,
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


class SmellSeverity(str, enum.Enum):
    """Severity levels for spec smell findings.

    E - Error: blocks ``bob plan --create``
    W - Warning: surfaced but does not block
    I - Informational: advisory only
    """
    E = "E"
    W = "W"
    I = "I"


def detect_all_smells(
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
        Other criteria in the same feature (used by S22 cross-checker).
    known_feature_ids:
        Set of valid feature IDs in the spec (used by S17 dangling-ref check).

    Returns
    -------
    list[SmellFinding]
        Findings ordered by smell ID. Empty when the text is clean.
        Each finding has ``severity`` (E/W/I) and ``blocks_plan`` (True for
        E-severity smells that gate ``bob plan --create``).
    """
    return detect_smells(
        text=text,
        peer_criteria=peer_criteria,
        known_feature_ids=known_feature_ids,
    )


def spacy_backed_count() -> int:
    """Return the number of detectors that use spaCy (always 7)."""
    return len(spacy_backed_detectors())


__all__ = [
    "detect_all_smells",
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
    "spacy_backed_count",
    "SpacyModelMissingError",
    "handle_missing_spacy_model",
]
