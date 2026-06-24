"""Spec smell linter — public entry point for the full 22-detector catalogue.

Wraps the Femmer/Smella + 2025 LLM-extension 22-detector set under the
canonical function name ``lint_spec_for_smells``, which the orchestrator and
CLI call to gate ``bob3 plan --create``.

Severities:
  E  (Error)       — blocks plan --create
  W  (Warning)     — surfaced to console, does not block
  I  (Informational) — surfaced to console, does not block

spaCy (en_core_web_sm) is used by 7 of the 22 detectors. When unavailable,
those detectors fall back to regex heuristics so linting remains functional.

Usage::

    from bob3.smell_linter import lint_spec_for_smells

    result = lint_spec_for_smells("The system shall be fast and simple.")
    if result["blocks_plan_create"]:
        raise RuntimeError("E-severity smells block plan --create")
"""

from __future__ import annotations

from typing import Any

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
    "lint_spec_for_smells",
    "detect_smells",
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
    "filter_by_severity",
    "detector_count",
    "spacy_backed_detectors",
    "SpacyModelMissingError",
    "handle_missing_spacy_model",
]


def lint_spec_for_smells(
    text: str,
    peer_criteria: list[str] | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Run all 22 smell detectors against a single acceptance-criterion text.

    This is the primary orchestrator/CLI entry point for the full 22-detector
    catalogue (Femmer/Smella + 2025 LLM extensions).  It wraps ``detect_smells``
    and returns a structured result dict suitable for gating ``bob3 plan --create``.

    Parameters
    ----------
    text:
        The acceptance criterion string to lint.  Must be a ``str``; passing
        any other type raises ``ValueError``.
    peer_criteria:
        Other criteria in the same feature (used by S22: does a ``behavior:``
        AC have a matching ``pytest:`` AC?).
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

    Raises
    ------
    ValueError
        When ``text`` is not a ``str``.

    Examples
    --------
    >>> result = lint_spec_for_smells("The system shall be fast and simple.")
    >>> result["blocks_plan_create"]
    True
    >>> result = lint_spec_for_smells("pytest: tests/test_foo.py")
    >>> result["findings"]
    []
    >>> result["blocks_plan_create"]
    False
    """
    if not isinstance(text, str):
        raise ValueError(
            f"lint_spec_for_smells expects a str, got {type(text).__name__!r}"
        )

    findings = detect_smells(
        text=text,
        peer_criteria=peer_criteria,
        known_feature_ids=known_feature_ids,
    )

    errors = [f for f in findings if f.severity == "E"]
    warnings = [f for f in findings if f.severity == "W"]
    infos = [f for f in findings if f.severity == "I"]

    return {
        "findings": findings,
        "blocks_plan_create": blocks_plan_create(findings),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "info_count": len(infos),
        "detector_count": detector_count(),
        "spacy_backed": spacy_backed_detectors(),
    }


def get_severity(smell_id: str) -> str:
    """Return the severity level ("E", "W", or "I") for a smell by its ID.

    Parameters
    ----------
    smell_id:
        Smell identifier such as ``"S01"`` through ``"S22"``.

    Returns
    -------
    str
        One of ``"E"`` (Error — blocks plan --create), ``"W"`` (Warning), or
        ``"I"`` (Informational).

    Raises
    ------
    KeyError
        When ``smell_id`` is not in the 22-smell catalogue.

    Examples
    --------
    >>> get_severity("S01")
    'E'
    >>> get_severity("S02")
    'W'
    """
    return severity_of(smell_id)
