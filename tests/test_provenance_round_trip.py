"""Round-trip test: provenance spans must cover ≥90% of load-bearing tokens."""

import pytest

from bob3.spec_quality.provenance import (
    ProvenanceRecord,
    Span,
    attach_provenance,
    validate_coverage,
)


INTENT = (
    "The system shall emit acceptance criteria from the feature description. "
    "Each criterion must reference a specific behaviour observable by the user. "
    "The extractor parses sentences and maps keywords to structured output. "
    "Ambiguous clauses are flagged for human review before code generation begins."
)


def test_attach_provenance_returns_one_record_per_ac():
    acs = [
        "emit acceptance criteria from feature description",
        "criterion references observable user behaviour",
    ]
    records = attach_provenance(acs, INTENT)
    assert len(records) == len(acs)
    for rec in records:
        assert isinstance(rec, ProvenanceRecord)
        assert rec.ac in acs


def test_attach_provenance_spans_are_within_intent_bounds():
    acs = [
        "emit acceptance criteria from feature description",
        "extractor parses sentences maps keywords structured output",
    ]
    records = attach_provenance(acs, INTENT)
    for rec in records:
        for span in rec.spans:
            assert span.start >= 0
            assert span.end <= len(INTENT)
            assert span.start < span.end


def test_attach_provenance_span_text_non_empty():
    acs = ["extractor parses sentences maps keywords structured output"]
    records = attach_provenance(acs, INTENT)
    assert records[0].spans, "Expected at least one span for a closely matching AC"
    for span in records[0].spans:
        assert span.text(INTENT).strip()


def test_round_trip_coverage_ninety_percent():
    """Union of all provenance spans must cover ≥90% of load-bearing tokens."""
    acs = [
        "emit acceptance criteria from feature description",
        "criterion references observable user behaviour",
        "extractor parses sentences maps keywords structured output",
        "ambiguous clauses flagged human review before code generation",
    ]
    records = attach_provenance(acs, INTENT)
    passed, coverage, bad_indices = validate_coverage(records, INTENT)
    assert coverage >= 0.90, (
        f"Coverage {coverage:.2%} is below the required 90% threshold"
    )


def test_round_trip_all_records_have_spans():
    acs = [
        "emit acceptance criteria from feature description",
        "criterion references observable user behaviour",
    ]
    records = attach_provenance(acs, INTENT)
    _, _, bad_indices = validate_coverage(records, INTENT)
    assert bad_indices == [], f"Records at indices {bad_indices} have empty spans"


def test_span_overlaps():
    s1 = Span(0, 10)
    s2 = Span(5, 15)
    s3 = Span(10, 20)
    assert s1.overlaps(s2)
    assert not s1.overlaps(s3)


def test_span_text():
    intent = "hello world"
    span = Span(6, 11)
    assert span.text(intent) == "world"


def test_provenance_record_roundtrip_dict():
    rec = ProvenanceRecord(ac="emit criteria", spans=[Span(0, 10), Span(20, 30)])
    d = rec.to_dict()
    restored = ProvenanceRecord.from_dict(d)
    assert restored.ac == rec.ac
    assert len(restored.spans) == 2
    assert restored.spans[0].start == 0
    assert restored.spans[1].end == 30


def test_validate_coverage_vacuously_true_for_empty_intent():
    """No load-bearing tokens in intent → coverage is 1.0 (vacuous)."""
    records = [ProvenanceRecord(ac="something", spans=[])]
    passed, coverage, bad_indices = validate_coverage(records, "a the an")
    assert coverage == 1.0


def test_validate_coverage_custom_threshold():
    acs = ["emit acceptance criteria from feature description"]
    records = attach_provenance(acs, INTENT)
    # With 0.0 threshold even partial coverage should pass
    passed, coverage, bad = validate_coverage(records, INTENT, min_coverage=0.0)
    assert passed or bad == []
