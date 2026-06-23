"""bob3.linters.smell_detector — canonical integration point for the
full 22-smell spec linter (F-R7-410 extension).

Wraps the 22-detector catalogue (Femmer/Smella + 2025 LLM extensions) and
exposes the two functions required by the acceptance criteria:

- :func:`detect_smells` — run all 22 detectors against a single AC text
- :func:`check_severity_blocks` — return True when any E-severity finding
  is present (blocking ``bob3 plan --create``)

Severities: E (Error), W (Warning), I (Informational).
E-severity smells block ``bob3 plan --create`` via :func:`check_severity_blocks`.

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02, S05,
S06, S07, S08, S18). When unavailable, those detectors fall back to regex
heuristics.

Example::

    from bob3.linters.smell_detector import detect_smells, check_severity_blocks

    findings = detect_smells("The system shall be fast and simple.")
    if check_severity_blocks(findings):
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
    "check_severity_blocks",
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


def detect_smells(
    text: str,
    peer_criteria: list[str] | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> list[SmellFinding]:
    """Run all 22 smell detectors against a single acceptance-criterion text.

    This is the canonical entry point for the F-R7-410 extended linter,
    integrating with ``bob3.orchestrator`` via ``check_severity_blocks``.

    Parameters
    ----------
    text:
        The acceptance criterion string to lint. Must be a ``str``; passing
        any other type raises ``TypeError``.
    peer_criteria:
        Other criteria in the same feature (used for S22 cross-check: does a
        ``behavior:`` criterion have a matching ``pytest:`` criterion?).
    known_feature_ids:
        Set of valid feature IDs in the spec (used for S17 dangling-ref check).

    Returns
    -------
    list[SmellFinding]
        Findings ordered by smell ID. Empty when the text is clean or when
        ``text`` is an empty/whitespace-only string.
        Each finding exposes ``severity`` (``"E"``, ``"W"``, ``"I"``) and
        ``blocks_plan`` (``True`` for E-severity smells).

    Raises
    ------
    TypeError
        When ``text`` is not a ``str``.

    Examples
    --------
    >>> findings = detect_smells("The system shall be fast and simple.")
    >>> any(f.blocks_plan for f in findings)
    True
    >>> findings = detect_smells("pytest: tests/test_foo.py -v")
    >>> findings
    []
    >>> detect_smells("")
    []
    """
    if not isinstance(text, str):
        raise TypeError(
            f"detect_smells() requires a str, got {type(text).__name__!r}"
        )
    return _detect_smells(
        text=text,
        peer_criteria=peer_criteria,
        known_feature_ids=known_feature_ids,
    )


def check_severity_blocks(findings: list[SmellFinding]) -> bool:
    """Return ``True`` when any E-severity finding is present.

    E-severity findings block ``bob3 plan --create``. Use this function as
    the gate check after calling :func:`detect_smells`.

    Parameters
    ----------
    findings:
        List of :class:`SmellFinding` returned by :func:`detect_smells`.
        Must be a ``list``; passing any other type raises ``TypeError``.

    Returns
    -------
    bool
        ``True`` if any finding has ``severity == "E"`` (i.e. ``blocks_plan``
        is ``True``). ``False`` when findings is empty or contains only W/I
        severity findings.

    Raises
    ------
    TypeError
        When ``findings`` is not a ``list``.
    ValueError
        When ``findings`` is not iterable (for callers who pass non-list
        iterables without explicit conversion).

    Examples
    --------
    >>> check_severity_blocks([])
    False
    >>> findings = detect_smells("The system shall be fast.")
    >>> check_severity_blocks(findings)  # depends on whether S01 fires
    True
    """
    if not isinstance(findings, list):
        raise TypeError(
            f"check_severity_blocks() requires a list, got {type(findings).__name__!r}"
        )
    return blocks_plan_create(findings)
