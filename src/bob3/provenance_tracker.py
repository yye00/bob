"""bob3.provenance_tracker — Sub-translation provenance tracker.

Each emitted AC must carry a provenance field naming the contiguous character
spans of the original human intent that produced it. This module provides the
canonical tracker API used by the synthesizer and CLI.

Public API
----------
:func:`extract_source_spans`
    Given a single AC and the original intent text, return the best-matching
    character spans as a list of ``{"start": int, "end": int}`` dicts.

:func:`extract_intent_spans`
    Alias for :func:`extract_source_spans` — given a single AC and the original
    intent text, return the best-matching character spans.

:func:`add_ac_provenance`
    Given a list of AC strings and the original intent text, return a list of
    provenance record dicts — each with ``ac``, ``spans``, and ``provenance``
    fields — suitable for storage and ``bob spec trace`` display.

:func:`track_ac_provenance`
    Alias for :func:`add_ac_provenance` — attach source-intent provenance spans
    to a list of acceptance criteria.

Integration with bob3.synthesizer
----------------------------------
After synthesis, call :func:`track_ac_provenance` (or :func:`add_ac_provenance`)
with the emitted ACs and the feature's original description to attach provenance
before persistence.
"""

from __future__ import annotations

from typing import Any

from bob3.spec_quality.provenance import (
    _best_span_for_ac,
    attach_provenance,
)


def extract_source_spans(
    ac: str,
    intent: str,
) -> list[dict[str, int]]:
    """Extract the best-matching character span(s) for a single AC against intent.

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
        When *ac* is not a str, or *intent* is not a str.
    """
    if not isinstance(ac, str):
        raise ValueError(f"ac must be a str, got {type(ac).__name__!r}")
    if not isinstance(intent, str):
        raise ValueError(f"intent must be a str, got {type(intent).__name__!r}")

    span = _best_span_for_ac(ac, intent)
    if span is None:
        return []
    return [span.to_dict()]


def add_ac_provenance(
    acs: list[str],
    intent: str,
) -> list[dict[str, Any]]:
    """Attach source-intent provenance spans to a list of acceptance criteria.

    For each AC in *acs*, locates the sentence(s) in *intent* that produced it
    and records them as character spans. Returns a list of dicts ready for
    storage or display via ``bob spec trace``.

    This function is the integration point used by ``bob3.synthesizer`` after
    emitting ACs: call it with the feature description as *intent* to annotate
    the synthesized criteria before persisting them.

    Parameters
    ----------
    acs:
        List of acceptance-criteria strings to annotate.
    intent:
        The original human-intent text (feature description) from which the
        ACs were derived.

    Returns
    -------
    list of dicts, one per AC, each with keys:
        ``ac``         — the acceptance-criterion text
        ``spans``      — list of ``{"start": int, "end": int}`` dicts
        ``provenance`` — list of source substrings for each span

    Raises
    ------
    ValueError
        When *intent* is not a str.
    TypeError
        When any element of *acs* is not a str.
    """
    if not isinstance(intent, str):
        raise ValueError(f"intent must be a str, got {type(intent).__name__!r}")

    for ac in acs:
        if not isinstance(ac, str):
            raise TypeError(f"each AC must be a str, got {type(ac).__name__!r}")

    records = attach_provenance(acs, intent)

    result: list[dict[str, Any]] = []
    for rec in records:
        spans_dicts = [s.to_dict() for s in rec.spans]
        result.append(
            {
                "ac": rec.ac,
                "spans": spans_dicts,
                "provenance": [intent[s["start"]: s["end"]] for s in spans_dicts],
            }
        )
    return result


def extract_intent_spans(
    ac: str,
    intent: str,
) -> list[dict[str, int]]:
    """Extract the best-matching character span(s) for a single AC against intent.

    Alias for :func:`extract_source_spans`. Given an AC and the original
    intent text, returns the contiguous character spans that produced the AC.

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
        When *ac* is not a str, or *intent* is not a str.
    """
    return extract_source_spans(ac, intent)


def track_ac_provenance(
    acs: list[str],
    intent: str,
) -> list[dict[str, Any]]:
    """Attach source-intent provenance spans to a list of acceptance criteria.

    Alias for :func:`add_ac_provenance`. For each AC in *acs*, locates the
    sentence(s) in *intent* that produced it and records them as character
    spans. Returns a list of dicts ready for storage or display via
    ``bob spec trace``.

    Parameters
    ----------
    acs:
        List of acceptance-criteria strings to annotate.
    intent:
        The original human-intent text (feature description) from which the
        ACs were derived.

    Returns
    -------
    list of dicts, one per AC, each with keys:
        ``ac``         — the acceptance-criterion text
        ``spans``      — list of ``{"start": int, "end": int}`` dicts
        ``provenance`` — list of source substrings for each span

    Raises
    ------
    ValueError
        When *intent* is not a str.
    TypeError
        When any element of *acs* is not a str.
    """
    return add_ac_provenance(acs, intent)
