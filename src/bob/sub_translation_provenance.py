"""bob.sub_translation_provenance — AC-to-intent provenance tracing.

Every emitted AC must carry a provenance field naming the contiguous character
spans of the original human intent that produced it.  Round-trip coverage of
source intent must be >=90% of load-bearing tokens.

Public API
----------
:func:`add_provenance_to_ac`
    Attach source-intent provenance spans to a single AC.
:func:`trace_ac_to_intent`
    Given a feature_id and AC index, return the AC and its source spans.
"""

from __future__ import annotations

from typing import Any

from bob.spec_quality.provenance import (
    attach_provenance,
    reject_empty_provenance,
    trace_ac as _trace_ac,
    validate_coverage,
)

__all__ = [
    "add_provenance_to_ac",
    "attach_provenance_to_ac",
    "compute_coverage",
    "compute_round_trip_coverage",
    "extract_provenance_spans",
    "trace_ac_to_intent",
    "trace_ac_to_intent_spans",
    "trace_ac_to_source",
    "validate_round_trip_coverage",
]


def add_provenance_to_ac(
    ac: str,
    intent: str,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Attach source-intent provenance spans to a single acceptance criterion.

    Locates the sentence(s) in *intent* that best explain *ac* by token
    overlap and returns a dict with the AC text, its character spans, and
    the corresponding source substrings.

    Parameters
    ----------
    ac:
        The acceptance-criterion text to annotate.
    intent:
        The original human-intent text from which the AC was derived.
    strict:
        When True (default), raises ``ValueError`` if no span can be found.
        When False, returns an empty ``spans`` list for unmatched ACs.

    Returns
    -------
    dict with keys:
        ``ac``         — the acceptance-criterion text
        ``spans``      — list of ``{"start": int, "end": int}`` dicts
        ``provenance`` — list of source substrings for each span

    Raises
    ------
    TypeError
        When *ac* is not a string.
    ValueError
        When *intent* is not a string, or when *strict* is True and no
        provenance span could be found.
    """
    if not isinstance(ac, str):
        raise TypeError(f"ac must be a str, got {type(ac).__name__!r}")
    if not isinstance(intent, str):
        raise ValueError(f"intent must be a str, got {type(intent).__name__!r}")

    records = attach_provenance([ac], intent)
    record = records[0]

    if strict:
        reject_empty_provenance(ac, record.spans)

    spans_dicts = [s.to_dict() for s in record.spans]
    return {
        "ac": ac,
        "spans": spans_dicts,
        "provenance": [intent[s["start"]: s["end"]] for s in spans_dicts],
    }


def trace_ac_to_intent(
    feature_id: str,
    ac_index: int,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return an AC and its source-intent spans for a given feature.

    Reads the feature from the database and returns the AC at *ac_index*
    together with its provenance spans (character offsets into the original
    human intent / description).

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


# ---------------------------------------------------------------------------
# Canonical function names required by AC spec
# ---------------------------------------------------------------------------


def attach_provenance_to_ac(
    ac: str,
    intent: str,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Alias for :func:`add_provenance_to_ac` — canonical AC-spec name."""
    return add_provenance_to_ac(ac, intent, strict=strict)


def trace_ac_to_intent_spans(
    feature_id: str,
    ac_index: int,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Alias for :func:`trace_ac_to_intent` — canonical AC-spec name."""
    return trace_ac_to_intent(feature_id, ac_index, db_path=db_path)


def extract_provenance_spans(
    ac: str,
    intent: str,
    *,
    strict: bool = True,
) -> list[dict[str, Any]]:
    """Extract contiguous character spans from *intent* that produced *ac*.

    Parameters
    ----------
    ac:
        The acceptance-criterion text to annotate.
    intent:
        The original human-intent text from which the AC was derived.
    strict:
        When True (default), raises ``ValueError`` if no span can be found.
        When False, returns an empty list for unmatched ACs.

    Returns
    -------
    List of ``{"start": int, "end": int}`` dicts — one per matched span.

    Raises
    ------
    TypeError
        When *ac* is not a string.
    ValueError
        When *intent* is not a string, or when *strict* is True and no
        provenance span could be found.
    """
    result = add_provenance_to_ac(ac, intent, strict=strict)
    return result["spans"]


def validate_round_trip_coverage(
    acs: list[str],
    intent: str,
    *,
    min_coverage: float = 0.90,
) -> tuple[bool, float]:
    """Validate that ACs achieve round-trip coverage of source intent tokens.

    Alias for :func:`compute_coverage` using the canonical AC-spec name.

    Parameters
    ----------
    acs:
        List of acceptance-criterion texts.
    intent:
        The original human-intent text to measure coverage against.
    min_coverage:
        Minimum required fraction of load-bearing tokens covered (default 0.90).

    Returns
    -------
    (passed, coverage_ratio)
        *passed* is True when coverage >= *min_coverage*.
        *coverage_ratio* is the fraction of load-bearing tokens covered (0.0–1.0).

    Raises
    ------
    ValueError
        When *intent* is not a string or *acs* is not a list.
    """
    return compute_coverage(acs, intent, min_coverage=min_coverage)


def compute_round_trip_coverage(
    acs: list[str],
    intent: str,
    *,
    min_coverage: float = 0.90,
) -> tuple[bool, float]:
    """Compute round-trip coverage — canonical AC-spec name.

    Alias for :func:`compute_coverage`.

    Parameters
    ----------
    acs:
        List of acceptance-criterion texts.
    intent:
        The original human-intent text to measure coverage against.
    min_coverage:
        Minimum required fraction of load-bearing tokens covered (default 0.90).

    Returns
    -------
    (passed, coverage_ratio)
        *passed* is True when coverage >= *min_coverage*.
        *coverage_ratio* is the fraction of load-bearing tokens covered (0.0–1.0).

    Raises
    ------
    ValueError
        When *intent* is not a string or *acs* is not a list.
    """
    return compute_coverage(acs, intent, min_coverage=min_coverage)


def compute_coverage(
    acs: list[str],
    intent: str,
    *,
    min_coverage: float = 0.90,
) -> tuple[bool, float]:
    """Compute round-trip coverage of *intent* load-bearing tokens across *acs*.

    Attaches provenance spans to every AC, then delegates to
    :func:`bob.spec_quality.provenance.validate_coverage` to check whether
    the union of all spans covers at least *min_coverage* of the load-bearing
    tokens in *intent*.

    Parameters
    ----------
    acs:
        List of acceptance-criterion texts.
    intent:
        The original human-intent text to measure coverage against.
    min_coverage:
        Minimum required fraction of load-bearing tokens that must be
        covered (default 0.90).

    Returns
    -------
    (passed, coverage_ratio)
        *passed* is True when coverage >= *min_coverage* and no individual
        AC has empty provenance.
        *coverage_ratio* is the fraction of load-bearing tokens covered
        (0.0–1.0).

    Raises
    ------
    ValueError
        When *intent* is not a string or *acs* is not a list.
    """
    if not isinstance(intent, str):
        raise ValueError(f"intent must be a str, got {type(intent).__name__!r}")
    if not isinstance(acs, list):
        raise ValueError(f"acs must be a list, got {type(acs).__name__!r}")

    records = attach_provenance(acs, intent)
    passed, coverage_ratio, _bad = validate_coverage(records, intent, min_coverage=min_coverage)
    return passed, coverage_ratio


def trace_ac_to_source(
    feature_id: str,
    ac_index: int,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return an AC and its source-intent spans for a given feature.

    Alias for :func:`trace_ac_to_intent` — canonical AC-spec name matching
    the ``bob spec trace`` CLI command.

    Parameters
    ----------
    feature_id:
        UUID of the feature to look up.
    ac_index:
        0-based index into the feature's acceptance_criteria list.
    db_path:
        Optional path to the SQLite database.

    Returns
    -------
    dict with keys: ``feature_id``, ``ac_index``, ``ac``, ``spans``,
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
    return trace_ac_to_intent(feature_id, ac_index, db_path=db_path)
