"""22-smell linter module for F-R7-410 extension.

Exposes the full 22-detector catalogue (Femmer/Smella + 2025 LLM extensions)
with the canonical public API: ``detect_smells`` and ``get_severity``.

Severity levels E/W/I:
  E - Error: blocks ``bob3 plan --create``
  W - Warning: surfaced but does not block
  I - Informational: advisory only

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02, S05,
S06, S07, S08, S18). When unavailable those detectors fall back to regex
heuristics so linting remains functional.

Public API::

    from bob3.linter_22_detectors import detect_smells, get_severity

    findings = detect_smells("The system shall be fast and simple.")
    if any(f.blocks_plan for f in findings):
        raise RuntimeError("E-severity smells block plan --create")

    sev = get_severity("S01")  # -> "E"
"""

from __future__ import annotations

from bob3.spec_quality.smell_catalog import SMELL_BY_ID, SMELL_CATALOG
from bob3.spec_quality.smell_detectors import (
    SmellFinding,
    blocks_plan_create,
    detect_all,
    is_blocking,
    severity_of,
)

__all__ = [
    "detect_smells",
    "get_severity",
    "SmellFinding",
    "blocks_plan_create",
    "is_blocking",
    "SMELL_CATALOG",
    "SMELL_BY_ID",
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
        Other criteria in the same feature (used by S22 cross-checker).
    known_feature_ids:
        Set of valid feature IDs in the spec (used by S17 dangling-ref check).

    Returns
    -------
    list[SmellFinding]
        Findings ordered by smell ID. Empty when the text is clean.
        Each finding has ``severity`` (E/W/I) and ``blocks_plan`` (True for
        E-severity smells that gate ``bob3 plan --create``).

    Raises
    ------
    TypeError
        When ``text`` is not a string.

    Examples
    --------
    >>> findings = detect_smells("The system shall be fast and simple.")
    >>> any(f.blocks_plan for f in findings)
    True
    >>> findings = detect_smells("")
    >>> findings
    []
    """
    if not isinstance(text, str):
        raise TypeError(f"detect_smells expects a str, got {type(text).__name__!r}")
    return detect_all(
        text=text,
        peer_criteria=peer_criteria,
        known_feature_ids=known_feature_ids,
    )


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
