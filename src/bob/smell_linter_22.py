"""Full 22-smell linter — canonical module for F-R7-410 extension.

Provides the two public functions required by the AC:
  - detect_all_smells  (wraps linter_22_smells.detect_smells)
  - filter_by_severity (wraps linter_22_smells.filter_by_severity)

E-severity findings from detect_all_smells block ``bob plan --create``.

Integration with bob.patterns: this module is the authoritative import
target for smell detection across the bob pipeline.

spaCy (en_core_web_sm) is used by 7 of the 22 detectors (S01, S02, S05,
S06, S07, S08, S18). When unavailable, those detectors fall back to regex
heuristics — detection remains functional.

Usage::

    from bob.smell_linter_22 import detect_all_smells, filter_by_severity

    findings = detect_all_smells("The system shall be fast and simple.")
    errors = filter_by_severity(findings, "E")
    if errors:
        raise RuntimeError("E-severity smells block plan --create")
"""

from __future__ import annotations

from bob.linter_22_smells import (
    SmellFinding,
    SmellSeverity,
    blocks_plan_create,
    detect_smells,
    filter_by_severity as _filter_by_severity,
)

__all__ = [
    "detect_all_smells",
    "filter_by_severity",
    "SmellFinding",
    "SmellSeverity",
    "blocks_plan_create",
]


def detect_all_smells(
    text: str,
    peer_criteria: list[str] | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> list[SmellFinding]:
    """Run all 22 smell detectors against a single acceptance-criterion text.

    Parameters
    ----------
    text:
        The acceptance criterion string to lint. Must be a ``str``; passing
        any other type raises ``ValueError``.
    peer_criteria:
        Other criteria in the same feature (used by S22 cross-check: does a
        ``behavior:`` AC have a matching ``pytest:`` AC?).
    known_feature_ids:
        Set of valid feature IDs in the spec (used by S17 dangling-ref check).

    Returns
    -------
    list[SmellFinding]
        Findings ordered by smell ID. Empty when the text is clean.
        Each finding has a ``severity`` attribute ("E", "W", or "I") and a
        ``blocks_plan`` property (True for E-severity).

    Raises
    ------
    ValueError
        When ``text`` is not a ``str``.

    Examples
    --------
    >>> findings = detect_all_smells("The system shall be fast and simple.")
    >>> any(f.blocks_plan for f in findings)
    True
    >>> findings = detect_all_smells("pytest: tests/test_foo.py")
    >>> findings
    []
    """
    if not isinstance(text, str):
        raise ValueError(
            f"detect_all_smells expects a str, got {type(text).__name__!r}"
        )
    return detect_smells(
        text=text,
        peer_criteria=peer_criteria,
        known_feature_ids=known_feature_ids,
    )


def filter_by_severity(
    findings: list[SmellFinding],
    severity: SmellSeverity,
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
    >>> findings = detect_all_smells("The system shall be fast.")
    >>> errors = filter_by_severity(findings, "E")
    >>> all(f.severity == "E" for f in errors)
    True
    """
    return _filter_by_severity(findings, severity)
