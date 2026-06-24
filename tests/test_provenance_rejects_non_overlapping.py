"""Tests for reject_non_overlapping — raises when spans share no tokens with AC."""

import pytest

from bob3.spec_quality.provenance import (
    NonOverlappingProvenanceError,
    Span,
    reject_non_overlapping,
)


INTENT = (
    "The system shall emit acceptance criteria from the feature description. "
    "Each criterion must be machine-checkable by automated tooling."
)


def test_non_overlapping_raises_when_spans_cover_different_region():
    """Spans anchored at the start of intent don't cover the AC about 'machine-checkable'."""
    ac = "machine-checkable automated tooling"
    # The intent starts with "The system shall emit..." - no 'machine' there.
    spans = [Span(0, 30)]  # only covers "The system shall emit acceptan"
    with pytest.raises(NonOverlappingProvenanceError):
        reject_non_overlapping(ac, spans, INTENT)


def test_non_overlapping_passes_when_spans_do_overlap():
    """No exception when spans cover load-bearing tokens shared with the AC."""
    ac = "emit acceptance criteria feature description"
    spans = [Span(0, 65)]  # covers first sentence
    reject_non_overlapping(ac, spans, INTENT)  # should not raise


def test_non_overlapping_no_op_on_empty_spans():
    """Empty spans list is silently ignored (caller uses reject_empty_provenance)."""
    ac = "machine-checkable tooling"
    reject_non_overlapping(ac, [], INTENT)  # must not raise


def test_non_overlapping_no_op_on_empty_ac_tokens():
    """AC with only stop words has no load-bearing tokens — no error raised."""
    ac = "the an or but"  # all stop words
    spans = [Span(0, 10)]
    reject_non_overlapping(ac, spans, INTENT)  # must not raise


def test_non_overlapping_error_message_contains_diagnostic():
    """The exception message includes useful info for debugging."""
    ac = "xyz completely different"
    spans = [Span(0, 20)]
    with pytest.raises(NonOverlappingProvenanceError, match="spans do not overlap"):
        reject_non_overlapping(ac, spans, INTENT)


def test_non_overlapping_partial_overlap_passes():
    """A single shared load-bearing token is sufficient to pass."""
    ac = "acceptance criteria"
    # Span covers the word 'acceptance' inside the intent
    start = INTENT.index("acceptance")
    spans = [Span(start, start + len("acceptance"))]
    reject_non_overlapping(ac, spans, INTENT)  # must not raise


def test_non_overlapping_multiple_spans_any_overlap_passes():
    """If any one of multiple spans overlaps, no exception is raised."""
    ac = "machine-checkable automated"
    # First span: doesn't overlap; second span: does
    start = INTENT.index("machine")
    spans = [Span(0, 10), Span(start, start + 25)]
    reject_non_overlapping(ac, spans, INTENT)  # must not raise


def test_non_overlapping_raises_with_non_overlapping_multi_spans():
    """Multiple spans, none overlapping the AC, still raises."""
    ac = "machine-checkable automated tooling"
    spans = [Span(0, 10), Span(15, 25)]  # both in "The system shall"
    with pytest.raises(NonOverlappingProvenanceError):
        reject_non_overlapping(ac, spans, INTENT)
