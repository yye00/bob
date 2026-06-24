"""Test that validate_coverage rejects ACs with empty provenance spans."""

import pytest

from bob3.spec_quality.provenance import (
    EmptyProvenanceError,
    ProvenanceRecord,
    Span,
    attach_provenance,
    reject_empty_provenance,
    validate_coverage,
)


def test_validate_rejects_record_with_no_spans():
    records = [
        ProvenanceRecord(ac="some criterion", spans=[]),
    ]
    intent = "some criterion described here"
    passed, coverage, bad_indices = validate_coverage(records, intent)
    assert not passed
    assert 0 in bad_indices


def test_validate_rejects_mixed_empty_and_nonempty():
    intent = "criterion A is defined here. criterion B is also present."
    records = [
        ProvenanceRecord(ac="criterion A", spans=[Span(0, 30)]),
        ProvenanceRecord(ac="completely unrelated jargon xyz", spans=[]),
    ]
    passed, coverage, bad_indices = validate_coverage(records, intent)
    assert not passed
    assert 1 in bad_indices
    assert 0 not in bad_indices


def test_validate_passes_when_all_have_spans():
    intent = "system emits criteria from intent text for coverage"
    acs = ["system emits criteria", "intent text coverage"]
    records = attach_provenance(acs, intent)
    _, _, bad_indices = validate_coverage(records, intent)
    assert bad_indices == []


def test_validate_fails_low_coverage():
    """Manually set spans that cover very little; must fail coverage check."""
    intent = "the quick brown fox jumps over lazy dog near riverbank at sunset"
    # Span covers only the first 3 chars — nearly no load-bearing tokens
    records = [
        ProvenanceRecord(ac="quick brown fox", spans=[Span(4, 7)]),
    ]
    passed, coverage, bad_indices = validate_coverage(records, intent, min_coverage=0.90)
    assert not passed


def test_attach_provenance_unrelated_ac_gets_empty_spans():
    """An AC with zero keyword overlap with any sentence gets no spans."""
    intent = "the system shall validate user inputs before processing."
    acs = ["zqxk mfrw plvb"]  # nonsense tokens, no overlap
    records = attach_provenance(acs, intent)
    assert records[0].spans == []


def test_validate_coverage_multiple_empty_records():
    records = [
        ProvenanceRecord(ac="first", spans=[]),
        ProvenanceRecord(ac="second", spans=[]),
        ProvenanceRecord(ac="third", spans=[]),
    ]
    intent = "first second third load bearing words"
    passed, coverage, bad_indices = validate_coverage(records, intent)
    assert not passed
    assert bad_indices == [0, 1, 2]


def test_span_invalid_raises():
    with pytest.raises(ValueError):
        Span(start=5, end=3)

    with pytest.raises(ValueError):
        Span(start=-1, end=5)


def test_reject_empty_provenance_raises_on_empty_spans():
    """reject_empty_provenance raises EmptyProvenanceError with 'empty' when spans list is empty."""
    with pytest.raises(EmptyProvenanceError, match="empty"):
        reject_empty_provenance("some criterion", [])


def test_reject_empty_provenance_passes_with_nonempty_spans():
    """reject_empty_provenance does not raise when spans list is non-empty."""
    reject_empty_provenance("some criterion", [Span(0, 10)])  # must not raise


def test_reject_empty_provenance_error_is_valueerror_subclass():
    """EmptyProvenanceError is a subclass of ValueError."""
    with pytest.raises(ValueError):
        reject_empty_provenance("criterion text", [])
