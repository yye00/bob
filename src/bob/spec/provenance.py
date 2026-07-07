"""bob.spec.provenance — AC-to-source-intent provenance tracing (package API).

Each emitted AC carries a provenance field naming the contiguous character
spans of the original human intent that produced it.  This module is the
``bob.spec`` package entry point for provenance tracing; it delegates to the
shared implementation in :mod:`bob.spec_quality.provenance`.

The CLI ``bob spec trace <feature>:<ac>`` prints an AC alongside its spans by
way of :func:`trace_ac_provenance`.  Round-trip coverage of source intent must
be >=90% of load-bearing tokens (see :func:`round_trip_coverage`).

Public API
----------
:func:`trace_ac_provenance`
    Given a feature_id and AC index, return the AC alongside its source-intent
    provenance spans.
:func:`round_trip_coverage`
    Compute round-trip coverage of source intent load-bearing tokens across a
    list of ACs.
"""

from __future__ import annotations

from typing import Any

from bob.spec_quality.provenance import (
    attach_provenance,
    trace_ac as _trace_ac,
    validate_coverage,
)

__all__ = [
    "round_trip_coverage",
    "trace_ac_provenance",
]


def trace_ac_provenance(
    feature_id: str,
    ac_index: int,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return an AC and its source-intent provenance spans for a feature.

    Reads the feature from the database and returns the acceptance criterion at
    *ac_index* together with the character spans of the original human intent
    (the feature description) that produced it.  This function backs the
    ``bob spec trace`` CLI command.

    Parameters
    ----------
    feature_id:
        UUID of the feature to look up.  Must be a non-empty string.
    ac_index:
        0-based index into the feature's acceptance_criteria list.  Must be an
        integer.
    db_path:
        Optional path to the SQLite database.  Falls back to the
        ``BOB_DATABASE_PATH`` environment variable and then to ``bob.db``.

    Returns
    -------
    dict with keys:
        ``feature_id``, ``ac_index``, ``ac``, ``spans``,
        ``provenance_spans_raw``.

    Raises
    ------
    ValueError
        If *feature_id* is not a non-empty string or *ac_index* is not an int.
    KeyError
        If the feature is not found.
    IndexError
        If *ac_index* is out of range.
    """
    if not isinstance(feature_id, str) or not feature_id:
        raise ValueError(
            f"feature_id must be a non-empty str, got {feature_id!r}"
        )
    if isinstance(ac_index, bool) or not isinstance(ac_index, int):
        raise ValueError(
            f"ac_index must be an int, got {type(ac_index).__name__!r}"
        )
    return _trace_ac(feature_id, ac_index, db_path=db_path)


def round_trip_coverage(
    acs: list[str],
    intent: str,
    *,
    min_coverage: float = 0.90,
) -> tuple[bool, float]:
    """Compute round-trip coverage of *intent* load-bearing tokens across *acs*.

    Attaches provenance spans to every AC, then checks whether the union of all
    spans covers at least *min_coverage* of the load-bearing tokens in *intent*.

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
        *passed* is True when coverage >= *min_coverage* and every AC has at
        least one non-empty provenance span.
        *coverage_ratio* is the fraction of load-bearing tokens covered
        (0.0-1.0).

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
