"""bob3.provenance — Sub-translation provenance public API.

Every emitted AC must carry a provenance field naming the contiguous character
spans of the original human intent that produced it.  This module is the
canonical top-level entry point for that functionality.

Public API
----------
:func:`extract_spans`
    Given an AC string and the original intent text, return the best-matching
    character spans of the intent that produced the AC.
:func:`attach_provenance`
    Given a list of ACs and the original intent text, return a list of
    ProvenanceRecord objects with spans attached.
"""

from __future__ import annotations

from typing import Any

from bob3.spec_quality.provenance import (
    ProvenanceRecord,
    Span,
    attach_provenance,
    validate_coverage,
    trace_ac,
    reject_empty_provenance,
    reject_non_overlapping,
    EmptyProvenanceError,
    NonOverlappingProvenanceError,
    _best_span_for_ac,
)

__all__ = [
    "add_provenance",
    "extract_spans",
    "extract_provenance_spans",
    "trace_ac_to_source",
    "attach_provenance",
    "ProvenanceRecord",
    "Span",
    "validate_coverage",
    "trace_ac",
    "reject_empty_provenance",
    "reject_non_overlapping",
    "EmptyProvenanceError",
    "NonOverlappingProvenanceError",
]


def add_provenance(
    acs: list[str],
    intent: str,
    *,
    strict: bool = False,
) -> list[dict[str, Any]]:
    """Attach source-intent provenance spans to a list of acceptance criteria.

    For each AC in *acs*, locates the contiguous character span(s) of *intent*
    that produced it and returns a provenance record dict with the AC text,
    its character spans, and the corresponding source substrings.

    Parameters
    ----------
    acs:
        List of acceptance-criteria strings to annotate.
    intent:
        The original human-intent text from which the ACs were derived.
    strict:
        When True, raises ``ValueError`` for any AC with no span overlap.
        When False (default), such ACs receive an empty spans list.

    Returns
    -------
    list of dicts, one per AC, each with keys:
        ``ac``         — the acceptance-criterion text
        ``spans``      — list of ``{"start": int, "end": int}`` dicts
        ``provenance`` — list of source substrings for each span

    Raises
    ------
    ValueError
        When *intent* is not a str, or when *strict* is True and any AC
        has an empty span list.
    TypeError
        When *acs* contains a non-string element.
    """
    if not isinstance(intent, str):
        raise ValueError(f"intent must be a str, got {type(intent).__name__!r}")

    ac_texts: list[str] = []
    for ac in acs:
        if not isinstance(ac, str):
            raise TypeError(f"each AC must be a str, got {type(ac).__name__!r}")
        ac_texts.append(ac)

    records = attach_provenance(ac_texts, intent)

    result: list[dict[str, Any]] = []
    for rec in records:
        if strict:
            reject_empty_provenance(rec.ac, rec.spans)
        spans_dicts = [s.to_dict() for s in rec.spans]
        result.append(
            {
                "ac": rec.ac,
                "spans": spans_dicts,
                "provenance": [intent[s["start"]: s["end"]] for s in spans_dicts],
            }
        )
    return result


def extract_provenance_spans(
    acs: list[str],
    intent: str,
    *,
    strict: bool = False,
) -> list[dict[str, Any]]:
    """Extract provenance spans for a list of ACs against the original intent.

    For each AC, locates the contiguous character span(s) of *intent* that
    produced it and returns a provenance record dict.

    Parameters
    ----------
    acs:
        List of acceptance-criteria strings to annotate.
    intent:
        The original human-intent text from which the ACs were derived.
    strict:
        When True, raises ``ValueError`` for any AC with no span overlap.
        When False (default), such ACs receive an empty spans list.

    Returns
    -------
    list of dicts, one per AC, each with keys:
        ``ac``         — the acceptance-criterion text
        ``spans``      — list of ``{"start": int, "end": int}`` dicts
        ``provenance`` — list of source substrings for each span

    Raises
    ------
    ValueError
        When *intent* is not a str, or when *strict* is True and any AC
        has an empty span list.
    TypeError
        When *acs* contains a non-string element.
    """
    if not isinstance(intent, str):
        raise ValueError(f"intent must be a str, got {type(intent).__name__!r}")

    ac_texts: list[str] = []
    for ac in acs:
        if not isinstance(ac, str):
            raise TypeError(f"each AC must be a str, got {type(ac).__name__!r}")
        ac_texts.append(ac)

    records = attach_provenance(ac_texts, intent)

    result: list[dict[str, Any]] = []
    for rec in records:
        if strict:
            reject_empty_provenance(rec.ac, rec.spans)
        spans_dicts = [s.to_dict() for s in rec.spans]
        result.append(
            {
                "ac": rec.ac,
                "spans": spans_dicts,
                "provenance": [intent[s["start"]: s["end"]] for s in spans_dicts],
            }
        )
    return result


def trace_ac_to_source(
    feature_id: str,
    ac_index: int,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return an AC and its source-intent spans for a given feature.

    Delegates to ``bob3.spec_quality.provenance.trace_ac`` and returns a
    dict with the AC text and its provenance spans.

    Parameters
    ----------
    feature_id:
        UUID of the feature to look up.
    ac_index:
        0-based index into the feature's acceptance_criteria list.
    db_path:
        Optional path to the SQLite database. Falls back to the
        ``BOB3_DATABASE_PATH`` environment variable and then to ``bob3.db``.

    Returns
    -------
    dict with keys:
        ``feature_id``, ``ac_index``, ``ac``, ``spans``,
        ``provenance_spans_raw``

    Raises
    ------
    KeyError
        If the feature is not found.
    IndexError
        If *ac_index* is out of range.
    ValueError
        If the feature has no acceptance_criteria.
    """
    return trace_ac(feature_id, ac_index, db_path=db_path)


def extract_spans(
    ac: str,
    intent: str,
) -> list[dict[str, int]]:
    """Extract the best-matching character span(s) for an AC against intent.

    Locates the sentence in *intent* that best explains *ac* by token overlap
    and returns it as a list of ``{"start": int, "end": int}`` span dicts.

    Parameters
    ----------
    ac:
        The acceptance-criterion text to trace.
    intent:
        The original human-intent text from which the AC was derived.

    Returns
    -------
    list of ``{"start": int, "end": int}`` dicts.
        Empty list when no sentence in *intent* shares a load-bearing token
        with *ac*.

    Raises
    ------
    ValueError
        When *ac* is not a string, or *intent* is not a string.
    """
    if not isinstance(ac, str):
        raise ValueError(f"ac must be a str, got {type(ac).__name__!r}")
    if not isinstance(intent, str):
        raise ValueError(f"intent must be a str, got {type(intent).__name__!r}")

    span = _best_span_for_ac(ac, intent)
    if span is None:
        return []
    return [span.to_dict()]
