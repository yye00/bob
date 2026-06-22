"""Full 22-smell linter extension for F-R7-410.

Replaces F-R7-410's small regex rule set with the complete 22-detector
catalogue (Femmer/Smella + 2025 LLM extensions).

Severities: E (Error), W (Warning), I (Informational).
E-severity smells block ``bob3 plan --create``.

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02, S05,
S06, S07, S08, S18). When unavailable, those detectors fall back to regex
heuristics.

Public entry point::

    from bob3.full_22_smell_linter_extension_f_r7_410 import (
        full_22_smell_linter_extension_f_r7_410,
    )

    result = full_22_smell_linter_extension_f_r7_410(
        "The system shall be fast and simple."
    )
    result["blocks_plan_create"]  # True
    result["findings"]            # list of SmellFinding
"""

from __future__ import annotations

from typing import Any

from bob3.linter_22_smells import (
    BLOCKING_SMELLS,
    SMELL_CATALOG,
    SMELL_BY_ID,
    SPACY_SMELLS,
    SmellDefinition,
    SmellFinding,
    SmellSeverity,
    SpacyModelMissingError,
    blocks_plan_create,
    detect_smells,
    detector_count,
    handle_missing_spacy_model,
    is_blocking,
    severity_of,
    spacy_backed_detectors,
)

__all__ = [
    "full_22_smell_linter_extension_f_r7_410",
    "detect_smells",
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


def full_22_smell_linter_extension_f_r7_410(
    text: str,
    peer_criteria: list[str] | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Run the full 22-smell catalogue against a single acceptance-criterion text.

    This is the primary entry point for F-R7-410's extended linter. It wraps
    ``detect_smells`` and returns a structured result dict suitable for
    integration into ``bob3 plan --create`` gating logic.

    Parameters
    ----------
    text:
        The acceptance criterion string to lint.
    peer_criteria:
        Other criteria in the same feature (used by S22: does a behavior: AC
        have a matching pytest: AC?).
    known_feature_ids:
        Set of valid feature IDs in the spec (used by S17: dangling-ref check).

    Returns
    -------
    dict with keys:
        - ``findings``: list[SmellFinding] — ordered by smell ID, empty when clean
        - ``blocks_plan_create``: bool — True when any E-severity finding present
        - ``error_count``: int — number of E-severity findings
        - ``warning_count``: int — number of W-severity findings
        - ``info_count``: int — number of I-severity findings
        - ``detector_count``: int — always 22
        - ``spacy_backed``: list[str] — smell IDs backed by spaCy (7 total)

    Examples
    --------
    >>> result = full_22_smell_linter_extension_f_r7_410(
    ...     "The system shall be fast and simple."
    ... )
    >>> result["blocks_plan_create"]
    True
    >>> result["detector_count"]
    22

    >>> result = full_22_smell_linter_extension_f_r7_410(
    ...     "pytest: tests/test_foo.py -v"
    ... )
    >>> result["blocks_plan_create"]
    False
    >>> result["findings"]
    []
    """
    findings = detect_smells(
        text=text,
        peer_criteria=peer_criteria,
        known_feature_ids=known_feature_ids,
    )

    error_count = sum(1 for f in findings if f.severity == "E")
    warning_count = sum(1 for f in findings if f.severity == "W")
    info_count = sum(1 for f in findings if f.severity == "I")

    return {
        "findings": findings,
        "blocks_plan_create": blocks_plan_create(findings),
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "detector_count": detector_count(),
        "spacy_backed": spacy_backed_detectors(),
    }
