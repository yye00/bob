"""Public linter API for Bob spec quality checks.

Extends F-R7-410 with the full 22-detector catalogue (Femmer/Smella +
2025 LLM extensions). Severities E/W/I; E-severity findings block
``bob plan --create``.

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02,
S05, S06, S07, S08, S18). When unavailable those detectors fall back
to regex heuristics.

Public API::

    from bob.linter import detect_smells, SmellFinding, blocks_plan_create

    findings = detect_smells("The system shall be fast and simple.")
    if blocks_plan_create(findings):
        raise RuntimeError("E-severity smells block plan --create")
"""

from __future__ import annotations

from typing import Literal

from bob.coverage_detector import detect_boundary_error_coverage  # noqa: F401 — integration: bob.linter
from bob.coverage_detector import detect_boundary_and_error_coverage  # noqa: F401 — integration: bob.linter
from bob.linter.auto_repair import apply_semantic_equivalence_check, should_auto_repair
from bob.linter_ac_repair import auto_repair_ac, semantic_equivalence_check  # noqa: F401 — integration: bob.linter

# apply_auto_repair: canonical entry point for AC3 (bob.linter.apply_auto_repair)
apply_auto_repair = auto_repair_ac
from bob.linter.smell_detectors import (
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

# Severity type alias: E=Error (blocks plan --create), W=Warning, I=Informational
Severity = Literal["E", "W", "I"]


def lint_code(
    text: str,
    peer_criteria: list[str] | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> list[SmellFinding]:
    """Run all 22 smell detectors against an acceptance-criterion text.

    Public entry point for the full 22-smell linter (F-R7-410 extension).
    E-severity findings block ``bob plan --create``.

    Parameters
    ----------
    text:
        The acceptance criterion string to lint.
    peer_criteria:
        Other criteria in the same feature spec (used for S22 cross-check).
    known_feature_ids:
        Set of valid feature IDs (used for S17 dangling-ref check).

    Returns
    -------
    list[SmellFinding]
        Findings ordered by smell ID. Empty when the text is clean.

    Raises
    ------
    ValueError
        When ``text`` is not a string.
    """
    if not isinstance(text, str):
        raise ValueError(f"lint_code expects a str, got {type(text).__name__!r}")
    return detect_smells(
        text=text,
        peer_criteria=peer_criteria,
        known_feature_ids=known_feature_ids,
    )


__all__ = [
    "detect_boundary_error_coverage",
    "detect_boundary_and_error_coverage",
    "apply_semantic_equivalence_check",
    "should_auto_repair",
    "auto_repair_ac",
    "apply_auto_repair",
    "semantic_equivalence_check",
    "detect_smells",
    "lint_code",
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
