"""bob.provenance — AC provenance field utilities.

Provides ``add_provenance_field`` which annotates a single AC dict (or plain
AC string) with a ``provenance`` list of ``{"start": int, "end": int}`` span
dicts, identifying the contiguous character spans of the original human intent
that produced the AC.

The implementation delegates to ``bob.spec_quality.provenance`` which houses
the full span extraction and coverage validation logic.

Public API
----------
:func:`add_provenance_field`
    Attach a ``provenance`` field to an AC dict or string.
:func:`trace_ac_to_spans`
    Given a feature_id and AC index, return the AC text and its source spans.
"""

from __future__ import annotations

from typing import Any

from bob.spec_quality.provenance import (
    Span,
    attach_provenance,
    validate_coverage,
    reject_empty_provenance,
    trace_ac as _trace_ac,
)


def extract_provenance(
    acs: "list[str | dict[str, Any]]",
    intent: str,
    *,
    strict: bool = False,
) -> "list[dict[str, Any]]":
    """Extract provenance spans for a list of ACs against the original intent.

    For each AC, locates the contiguous character span(s) of *intent* that
    produced it and returns a provenance record dict.

    Parameters
    ----------
    acs:
        List of acceptance criteria. Each element is either a plain string or
        a dict with at least an ``"ac"`` key.
    intent:
        The original human-intent text from which the ACs were derived.
    strict:
        When True, raises ``ValueError`` for any AC with no span overlap with
        *intent*. When False (default), such ACs receive an empty spans list.

    Returns
    -------
    list of dicts, one per AC, each with keys:
        ``ac``         — the acceptance-criterion text
        ``spans``      — list of ``{"start": int, "end": int}`` dicts
        ``provenance`` — list of source substrings for each span

    Raises
    ------
    ValueError
        When *intent* is not a str, or when *strict* is True and any AC has
        an empty span list.
    TypeError
        When an element of *acs* is neither a string nor a dict.
    """
    if not isinstance(intent, str):
        raise ValueError(f"intent must be a str, got {type(intent).__name__!r}")

    ac_texts: list[str] = []
    extra_fields: list[dict[str, Any]] = []
    for ac in acs:
        if isinstance(ac, dict):
            ac_text = ac.get("ac", "") or ac.get("criterion", "") or ac.get("text", "")
            if not isinstance(ac_text, str):
                raise ValueError(
                    f"ac dict must have a string 'ac' key, got {type(ac_text).__name__!r}"
                )
            extras = {k: v for k, v in ac.items() if k not in ("ac", "criterion", "text")}
        elif isinstance(ac, str):
            ac_text = ac
            extras = {}
        else:
            raise TypeError(f"ac must be str or dict, got {type(ac).__name__!r}")
        ac_texts.append(ac_text)
        extra_fields.append(extras)

    records = attach_provenance(ac_texts, intent)

    result: list[dict[str, Any]] = []
    for rec, extras in zip(records, extra_fields):
        if strict:
            reject_empty_provenance(rec.ac, rec.spans)
        spans_dicts = [s.to_dict() for s in rec.spans]
        entry: dict[str, Any] = {
            "ac": rec.ac,
            "spans": spans_dicts,
            "provenance": [intent[s["start"]: s["end"]] for s in spans_dicts],
        }
        entry.update(extras)
        result.append(entry)

    return result


def trace_ac_to_spans(
    feature_id: str,
    ac_index: int,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return an AC and its source-intent spans for a given feature.

    Delegates to ``bob.spec_quality.provenance.trace_ac`` and returns
    a dict with the AC text and its provenance spans.

    Parameters
    ----------
    feature_id:
        UUID of the feature to look up.
    ac_index:
        0-based index into the feature's acceptance_criteria list.
    db_path:
        Optional path to the SQLite database. Falls back to the
        ``BOB_DATABASE_PATH`` environment variable and then to ``bob.db``.

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
    return _trace_ac(feature_id, ac_index, db_path=db_path)


def add_provenance_field(
    ac: "str | dict[str, Any]",
    intent: str,
    *,
    min_coverage: float = 0.90,
    strict: bool = True,
) -> dict[str, Any]:
    """Attach a ``provenance`` field to an acceptance criterion.

    Given a single AC (as a plain string or a dict that already carries an
    ``ac`` key) and the original human-intent text, compute the best-matching
    character span(s) of *intent* that produced the AC and return a dict with:

    * ``ac``         — the acceptance-criterion text (str)
    * ``spans``      — list of ``{"start": int, "end": int}`` dicts
    * ``provenance`` — list of source substrings corresponding to each span

    Parameters
    ----------
    ac:
        The acceptance criterion, either a plain string or a dict with at
        least an ``"ac"`` key.
    intent:
        The original human-intent text (feature description).
    min_coverage:
        Minimum fraction of load-bearing tokens that must be covered when
        *strict* is True.  Default is 0.90.
    strict:
        When True (default), raises ``ValueError`` if the AC has no span
        overlap with *intent*.  When False, returns an empty ``spans`` list.

    Returns
    -------
    dict
        ``{"ac": str, "spans": [...], "provenance": [...]}``

    Raises
    ------
    ValueError
        When *ac* is not a str or dict, or when *intent* is not a str, or
        when *strict* is True and the AC has an empty span list.
    TypeError
        When *ac* is neither a string nor a dict.
    """
    if not isinstance(intent, str):
        raise ValueError(f"intent must be a str, got {type(intent).__name__!r}")

    if isinstance(ac, dict):
        ac_text: str = ac.get("ac", "") or ac.get("criterion", "") or ac.get("text", "")
        if not isinstance(ac_text, str):
            raise ValueError(f"ac dict must have a string 'ac' key, got {type(ac_text).__name__!r}")
    elif isinstance(ac, str):
        ac_text = ac
    else:
        raise TypeError(f"ac must be str or dict, got {type(ac).__name__!r}")

    records = attach_provenance([ac_text], intent)
    record = records[0]

    if strict:
        reject_empty_provenance(ac_text, record.spans)

    spans_dicts = [s.to_dict() for s in record.spans]
    provenance_texts = [intent[s["start"]: s["end"]] for s in spans_dicts]

    result: dict[str, Any] = {
        "ac": ac_text,
        "spans": spans_dicts,
        "provenance": provenance_texts,
    }

    # Preserve extra fields if a dict was passed in
    if isinstance(ac, dict):
        for k, v in ac.items():
            if k not in result:
                result[k] = v

    return result
