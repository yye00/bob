"""bob3.ac_provenance — AC-to-source-intent provenance tracing.

Each emitted AC carries a provenance field naming the contiguous character
spans of the original human intent that produced it. Round-trip coverage of
source intent must be >=90% of load-bearing tokens.

Public API
----------
:func:`trace_ac_to_spans`
    Given an AC text and intent, return the character spans from the intent
    that produced the AC.
:func:`compute_coverage`
    Compute round-trip coverage of intent load-bearing tokens across a list
    of ACs.
"""

from __future__ import annotations

from typing import Any

from bob3.spec_quality.provenance import (
    ProvenanceRecord,
    attach_provenance,
    reject_empty_provenance,
    validate_coverage,
)


def trace_ac_to_spans(
    ac: str,
    intent: str,
    *,
    strict: bool = True,
) -> list[dict[str, int]]:
    """Return the character spans from *intent* that produced *ac*.

    Locates the sentence(s) in *intent* that best explain *ac* by token
    overlap and returns them as ``{"start": int, "end": int}`` dicts.

    Parameters
    ----------
    ac:
        The acceptance-criterion text to trace.
    intent:
        The original human-intent text from which *ac* was derived.
    strict:
        When True (default), raises ``ValueError`` if no span is found.
        When False, returns an empty list for unmatched ACs.

    Returns
    -------
    list of ``{"start": int, "end": int}`` dicts — one per matched span.

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

    records: list[ProvenanceRecord] = attach_provenance([ac], intent)
    record = records[0]

    if strict:
        reject_empty_provenance(ac, record.spans)

    return [s.to_dict() for s in record.spans]


def compute_coverage(
    acs: list[str],
    intent: str,
    *,
    min_coverage: float = 0.90,
) -> tuple[bool, float]:
    """Compute round-trip coverage of *intent* load-bearing tokens across *acs*.

    Attaches provenance spans to every AC, then checks whether the union of
    all spans covers at least *min_coverage* of the load-bearing tokens in
    *intent*.

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
        *passed* is True when coverage >= *min_coverage* and no individual
        AC has an empty provenance span list.
        *coverage_ratio* is the fraction of load-bearing tokens covered (0.0–1.0).

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
    passed, coverage_ratio, _bad = validate_coverage(
        records, intent, min_coverage=min_coverage
    )
    return passed, coverage_ratio
