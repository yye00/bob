"""Sub-translation provenance — every AC traces to source-intent span.

Each emitted AC carries a provenance field naming the contiguous character
spans of the original human intent that produced it. Round-trip coverage of
source intent must be >=90% of load-bearing tokens.

The CLI command ``bob spec trace <feature>:<ac>`` prints the AC alongside its
spans. This module provides the core function that powers that command.

Public API
----------
:func:`sub_translation_provenance_every_ac_traces_source_intent`
    Given ACs and original intent text, return provenance records with
    coverage validation. Raises ValueError if coverage < 90%.
"""

from __future__ import annotations

from typing import Any

from bob3.spec_quality.provenance import (
    ProvenanceRecord,
    attach_provenance,
    validate_coverage,
)


def sub_translation_provenance_every_ac_traces_source_intent(
    acs: list[str],
    intent: str,
    *,
    min_coverage: float = 0.90,
) -> list[dict[str, Any]]:
    """Attach source-intent provenance spans to acceptance criteria.

    For each AC in *acs*, locates the sentence(s) in *intent* that produced it
    and records them as character spans. Validates that the union of all spans
    covers >=90% of load-bearing tokens in *intent*.

    Parameters
    ----------
    acs:
        List of acceptance-criteria strings extracted from the feature spec.
    intent:
        The original human-intent text (feature description) from which the
        ACs were derived.
    min_coverage:
        Minimum fraction of load-bearing tokens that must be covered.
        Default is 0.90 (90%).

    Returns
    -------
    list of dicts with keys:
        ``ac``      — the acceptance-criterion text
        ``spans``   — list of ``{"start": int, "end": int}`` dicts
        ``provenance`` — the source text substring for each span

    Raises
    ------
    ValueError
        When round-trip coverage of load-bearing tokens is below
        *min_coverage*, or when any AC has an empty provenance span list.
    """
    records: list[ProvenanceRecord] = attach_provenance(acs, intent)
    passed, coverage, bad_indices = validate_coverage(
        records, intent, min_coverage=min_coverage
    )

    if bad_indices:
        bad_acs = [acs[i] for i in bad_indices]
        raise ValueError(
            f"ACs at indices {bad_indices} have empty provenance spans: {bad_acs!r}"
        )

    if not passed:
        raise ValueError(
            f"Round-trip provenance coverage {coverage:.1%} is below the "
            f"required {min_coverage:.0%} threshold"
        )

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
