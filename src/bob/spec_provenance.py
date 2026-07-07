"""bob.spec_provenance — AC-to-source-intent provenance tracing.

Each emitted AC must carry a provenance field naming the contiguous character
spans of the original human intent that produced it.  CLI ``bob spec trace
<feature>:<ac>`` prints the AC alongside its spans.  Round-trip coverage of
source intent must be >=90% of load-bearing tokens.

Public API
----------
:func:`trace_ac_to_source`
    Given a feature_id and AC index, return the AC alongside its source-intent
    provenance spans (delegates to the database).
:func:`compute_coverage`
    Compute round-trip coverage of intent load-bearing tokens across a list
    of ACs.
"""

from __future__ import annotations

from typing import Any

from bob.spec_quality.provenance import (
    attach_provenance,
    trace_ac as _trace_ac,
    validate_coverage,
)

__all__ = [
    "compute_coverage",
    "source_coverage_ratio",
    "trace_ac_provenance",
    "trace_ac_to_source",
]


def trace_ac_to_source(
    feature_id: str,
    ac_index: int,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return an AC and its source-intent spans for a given feature.

    Reads the feature from the database and returns the AC at *ac_index*
    together with its provenance spans (character offsets into the original
    human intent / description).  This function powers the ``bob spec trace``
    CLI command.

    Parameters
    ----------
    feature_id:
        UUID of the feature to look up.
    ac_index:
        0-based index into the feature's acceptance_criteria list.
    db_path:
        Optional path to the SQLite database.  Falls back to the
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
    passed, coverage_ratio, _bad = validate_coverage(
        records, intent, min_coverage=min_coverage
    )
    return passed, coverage_ratio


def trace_ac_provenance(
    feature_id: str,
    ac_index: int,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return an AC and its source-intent provenance spans for a feature.

    This is the canonical name for the provenance-tracing entry point that
    backs the ``bob spec trace <feature>:<ac>`` CLI command.  It reads the
    feature from the database and returns the acceptance criterion at
    *ac_index* together with the character spans of the original human intent
    (the feature description) that produced it.

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


def source_coverage_ratio(
    acs: list[str],
    intent: str,
) -> float:
    """Return the fraction of *intent* load-bearing tokens covered by *acs*.

    Attaches provenance spans to every AC and measures the fraction of
    load-bearing tokens in *intent* whose character offsets fall within the
    union of all AC spans.  This is the round-trip coverage metric that the
    spec requires to be >=0.90; here it is returned as a raw ratio so callers
    can apply their own threshold.

    Parameters
    ----------
    acs:
        List of acceptance-criterion texts.
    intent:
        The original human-intent text to measure coverage against.

    Returns
    -------
    float
        The coverage ratio in ``[0.0, 1.0]``.  An intent with no load-bearing
        tokens yields a vacuous ratio of ``1.0``.

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
    _passed, coverage_ratio, _bad = validate_coverage(
        records, intent, min_coverage=0.0
    )
    return coverage_ratio
