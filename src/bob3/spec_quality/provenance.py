"""Sub-translation provenance — every AC traces to source-intent span.

Implements nl2spec's interpretability layer: each emitted AC carries a
``provenance:`` field naming the contiguous character span(s) of the
original human intent that produced it.

Three public functions:

* ``attach_provenance``   — annotate a list of ACs with source spans
* ``validate_coverage``   — reject ACs with empty / non-overlapping provenance
* ``trace_ac``            — return one AC and its spans by (feature_id, ac_index)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Span:
    """A character-level span in the original intent string."""

    start: int
    end: int  # exclusive

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"Invalid span: start={self.start}, end={self.end}")

    def text(self, source: str) -> str:
        return source[self.start : self.end]

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, d: dict[str, int]) -> "Span":
        return cls(start=d["start"], end=d["end"])


@dataclass
class ProvenanceRecord:
    """An AC with its source spans."""

    ac: str
    spans: list[Span] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ac": self.ac, "spans": [s.to_dict() for s in self.spans]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProvenanceRecord":
        return cls(
            ac=d["ac"],
            spans=[Span.from_dict(s) for s in d.get("spans", [])],
        )


# ---------------------------------------------------------------------------
# Stop-word list (English) for coverage calculation
# ---------------------------------------------------------------------------

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can", "not",
        "no", "nor", "so", "yet", "both", "either", "neither", "this", "that",
        "these", "those", "it", "its", "i", "we", "you", "he", "she", "they",
        "them", "their", "our", "your", "my", "his", "her", "which", "who",
        "whom", "what", "when", "where", "why", "how", "if", "then", "else",
        "each", "every", "any", "all", "some", "such",
    }
)


def _load_bearing_tokens(text: str) -> set[int]:
    """Return character offsets of the first character of each load-bearing word.

    A load-bearing word is a sequence of alphanumeric characters that is NOT
    in the stop-word list.
    """
    offsets: set[int] = set()
    for m in re.finditer(r"\b[A-Za-z0-9_]+\b", text):
        word = m.group(0).lower()
        if word not in _STOP_WORDS:
            offsets.add(m.start())
    return offsets


def _covered_token_offsets(
    text: str, spans: list[Span]
) -> set[int]:
    """Return load-bearing token offsets that fall within at least one span."""
    all_lb = _load_bearing_tokens(text)
    covered: set[int] = set()
    for span in spans:
        for offset in all_lb:
            # token is within this span if offset >= start and offset < end
            if span.start <= offset < span.end:
                covered.add(offset)
    return covered


# ---------------------------------------------------------------------------
# Core keyword-to-span extractor
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=\n)")


def _sentence_spans(text: str) -> list[Span]:
    """Split *text* into sentence-level spans."""
    spans: list[Span] = []
    start = 0
    for m in _SENTENCE_SPLIT.finditer(text):
        end = m.start()
        if end > start:
            spans.append(Span(start=start, end=end))
        start = m.end()
    if start < len(text):
        spans.append(Span(start=start, end=len(text)))
    return spans


def _best_span_for_ac(ac: str, intent: str) -> Span | None:
    """Find the sentence in *intent* that best matches *ac* by token overlap.

    Returns the span of the best-matching sentence, or None if no sentence
    has any load-bearing token in common with the AC.
    """
    ac_tokens: set[str] = {
        m.group(0).lower()
        for m in re.finditer(r"\b[A-Za-z0-9_]+\b", ac)
        if m.group(0).lower() not in _STOP_WORDS
    }
    if not ac_tokens:
        return None

    best_span: Span | None = None
    best_overlap = 0

    for sent_span in _sentence_spans(intent):
        sent_text = sent_span.text(intent)
        sent_tokens = {
            m.group(0).lower()
            for m in re.finditer(r"\b[A-Za-z0-9_]+\b", sent_text)
            if m.group(0).lower() not in _STOP_WORDS
        }
        overlap = len(ac_tokens & sent_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_span = sent_span

    return best_span if best_overlap > 0 else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def attach_provenance(
    acs: list[str],
    intent: str,
) -> list[ProvenanceRecord]:
    """Attach source-intent spans to each AC.

    For every AC in *acs*, locate the sentence(s) in *intent* that best
    explain it and record them as ``Span`` objects. ACs with no overlapping
    sentence receive an empty span list — callers should subsequently call
    ``validate_coverage`` to decide whether to reject them.

    Parameters
    ----------
    acs:
        List of acceptance-criteria strings to annotate.
    intent:
        The original human-intent text (spec description) from which the
        ACs were extracted.

    Returns
    -------
    list[ProvenanceRecord]
        One record per AC, in the same order as *acs*.
    """
    records: list[ProvenanceRecord] = []
    for ac in acs:
        span = _best_span_for_ac(ac, intent)
        spans = [span] if span is not None else []
        records.append(ProvenanceRecord(ac=ac, spans=spans))
    return records


def validate_coverage(
    records: list[ProvenanceRecord],
    intent: str,
    *,
    min_coverage: float = 0.90,
) -> tuple[bool, float, list[int]]:
    """Validate that provenance spans satisfy the ≥90% coverage requirement.

    Checks two things:

    1. **Per-AC check**: every record in *records* must have at least one
       non-empty span. Returns the indices of records that fail this check
       (empty provenance).

    2. **Global coverage check**: the union of all provenance spans must
       cover ≥ *min_coverage* of the load-bearing token offsets in *intent*.

    Parameters
    ----------
    records:
        ProvenanceRecords as returned by ``attach_provenance``.
    intent:
        The original intent text (used for coverage calculation).
    min_coverage:
        Fraction of load-bearing tokens that must be covered. Default 0.90.

    Returns
    -------
    (passed, coverage_ratio, bad_indices)
        *passed* is True when all per-AC spans are non-empty **and**
        global coverage ≥ *min_coverage*.
        *coverage_ratio* is the fraction covered (0.0–1.0).
        *bad_indices* lists the 0-based indices of records with empty spans.
    """
    bad_indices: list[int] = [
        i for i, rec in enumerate(records) if not rec.spans
    ]

    all_lb = _load_bearing_tokens(intent)
    if not all_lb:
        # No load-bearing tokens means coverage is vacuously 1.0
        coverage = 1.0
    else:
        all_spans: list[Span] = [s for rec in records for s in rec.spans]
        covered = _covered_token_offsets(intent, all_spans)
        coverage = len(covered) / len(all_lb)

    passed = (not bad_indices) and (coverage >= min_coverage)
    return passed, coverage, bad_indices


# ---------------------------------------------------------------------------
# Guard functions (raise on invalid provenance)
# ---------------------------------------------------------------------------


class EmptyProvenanceError(ValueError):
    """Raised when an AC is submitted with an empty spans list."""


class NonOverlappingProvenanceError(ValueError):
    """Raised when spans do not overlap the AC text (both non-empty)."""


def reject_empty_provenance(ac: str, spans: list[Span]) -> None:
    """Raise EmptyProvenanceError when *spans* is empty.

    Parameters
    ----------
    ac:
        The acceptance-criterion text (used in the error message).
    spans:
        The provenance span list to validate.

    Raises
    ------
    EmptyProvenanceError
        When *spans* is an empty list.
    """
    if not spans:
        raise EmptyProvenanceError(
            f"empty provenance spans for AC: {ac!r}"
        )


def reject_non_overlapping(ac: str, spans: list[Span], intent: str) -> None:
    """Raise NonOverlappingProvenanceError when spans cover no AC tokens.

    Checks that at least one load-bearing token from *ac* falls within at
    least one span when the span is anchored in *intent*. If the spans are
    empty this function is a no-op (callers should use
    ``reject_empty_provenance`` first).

    Parameters
    ----------
    ac:
        The acceptance-criterion text.
    spans:
        Provenance spans (character offsets into *intent*).
    intent:
        The original human-intent text that *spans* index into.

    Raises
    ------
    NonOverlappingProvenanceError
        When none of the span regions in *intent* share a load-bearing
        token with *ac*.
    """
    if not spans:
        return  # defer to reject_empty_provenance

    ac_tokens: set[str] = {
        m.group(0).lower()
        for m in re.finditer(r"\b[A-Za-z0-9_]+\b", ac)
        if m.group(0).lower() not in _STOP_WORDS
    }
    if not ac_tokens:
        return  # no load-bearing tokens to check

    for span in spans:
        span_text = intent[span.start : span.end]
        span_tokens = {
            m.group(0).lower()
            for m in re.finditer(r"\b[A-Za-z0-9_]+\b", span_text)
            if m.group(0).lower() not in _STOP_WORDS
        }
        if ac_tokens & span_tokens:
            return  # at least one span overlaps

    raise NonOverlappingProvenanceError(
        f"spans do not overlap AC tokens: ac={ac!r}"
    )


def trace_ac(
    feature_id: str,
    ac_index: int,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return an AC and its source spans for a given feature.

    Reads the feature from the database and reconstructs the provenance
    record for the AC at position *ac_index* (0-based).

    Parameters
    ----------
    feature_id:
        UUID of the feature to look up.
    ac_index:
        0-based index into the feature's acceptance_criteria list.
    db_path:
        Optional path to the SQLite database. Falls back to the ``BOB3_DATABASE_PATH``
        environment variable and then to ``bob3.db``.

    Returns
    -------
    dict with keys:
        ``feature_id``, ``ac_index``, ``ac``, ``spans``, ``provenance_spans_raw``

    Raises
    ------
    KeyError
        If the feature is not found.
    IndexError
        If *ac_index* is out of range.
    ValueError
        If the feature has no acceptance_criteria.
    """
    import os

    if db_path is None:
        db_path = os.environ.get("BOB3_DATABASE_PATH", "bob3.db")

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT acceptance_criteria, description, provenance_spans FROM features WHERE id = ?",
            (feature_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise KeyError(f"Feature not found: {feature_id!r}")

    ac_raw, description, provenance_spans_raw = row

    if not ac_raw:
        raise ValueError(f"Feature {feature_id!r} has no acceptance_criteria")

    try:
        acs: list[str] = json.loads(ac_raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"acceptance_criteria is not valid JSON: {exc}") from exc

    if ac_index < 0 or ac_index >= len(acs):
        raise IndexError(
            f"ac_index {ac_index} out of range for feature {feature_id!r} "
            f"(has {len(acs)} criteria)"
        )

    ac = acs[ac_index]

    # Reconstruct spans: prefer stored provenance_spans, fall back to live extraction
    spans: list[dict[str, int]] = []
    if provenance_spans_raw:
        try:
            stored = json.loads(provenance_spans_raw)
            if isinstance(stored, list) and ac_index < len(stored):
                entry = stored[ac_index]
                if isinstance(entry, dict):
                    spans = entry.get("spans", [])
                elif isinstance(entry, list):
                    spans = entry
        except (json.JSONDecodeError, TypeError):
            pass

    if not spans and description:
        record = attach_provenance([ac], description)
        spans = [s.to_dict() for s in record[0].spans]

    return {
        "feature_id": feature_id,
        "ac_index": ac_index,
        "ac": ac,
        "spans": spans,
        "provenance_spans_raw": provenance_spans_raw,
    }
