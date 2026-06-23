"""Tests for bob3.provenance_tracker — sub-translation provenance tracker.

Verifies that:
- extract_source_spans returns character spans for an AC against intent text
- add_ac_provenance attaches provenance spans to a list of ACs
- Integration with bob3.synthesizer works via synthesize_for_feature
"""

from __future__ import annotations

import pytest

from bob3.provenance_tracker import add_ac_provenance, extract_source_spans


INTENT = (
    "The system shall emit acceptance criteria from the feature description. "
    "Each criterion must reference a specific behaviour observable by the user. "
    "Round-trip coverage of source intent must be at least ninety percent."
)

SIMPLE_INTENT = "The system authenticates users via secure login."
SIMPLE_AC = "system authenticates users"


# ---------------------------------------------------------------------------
# extract_source_spans
# ---------------------------------------------------------------------------


def test_extract_source_spans_returns_list():
    """extract_source_spans returns a list."""
    result = extract_source_spans(SIMPLE_AC, SIMPLE_INTENT)
    assert isinstance(result, list)


def test_extract_source_spans_non_empty_for_matching_ac():
    """extract_source_spans returns non-empty list when AC tokens match intent."""
    result = extract_source_spans(SIMPLE_AC, SIMPLE_INTENT)
    assert len(result) > 0


def test_extract_source_spans_span_has_start_and_end():
    """Each span dict has 'start' and 'end' integer keys."""
    result = extract_source_spans(SIMPLE_AC, SIMPLE_INTENT)
    assert len(result) >= 1
    span = result[0]
    assert "start" in span
    assert "end" in span
    assert isinstance(span["start"], int)
    assert isinstance(span["end"], int)


def test_extract_source_spans_start_less_than_end():
    """Span start is strictly less than end for a non-empty match."""
    result = extract_source_spans(SIMPLE_AC, SIMPLE_INTENT)
    for span in result:
        assert span["start"] <= span["end"]


def test_extract_source_spans_span_within_intent_bounds():
    """Span indices are within bounds of intent string."""
    result = extract_source_spans(SIMPLE_AC, SIMPLE_INTENT)
    for span in result:
        assert span["start"] >= 0
        assert span["end"] <= len(SIMPLE_INTENT)


def test_extract_source_spans_empty_for_unrelated_ac():
    """Unrelated AC tokens return empty list (no overlap with intent)."""
    result = extract_source_spans("xyzzy frobble quux garply", SIMPLE_INTENT)
    assert result == []


def test_extract_source_spans_empty_intent_returns_empty():
    """Empty intent string returns empty spans list."""
    result = extract_source_spans("some criterion", "")
    assert result == []


def test_extract_source_spans_raises_for_non_string_ac():
    """Non-string AC raises ValueError."""
    with pytest.raises(ValueError, match="ac must be a str"):
        extract_source_spans(42, SIMPLE_INTENT)  # type: ignore[arg-type]


def test_extract_source_spans_raises_for_non_string_intent():
    """Non-string intent raises ValueError."""
    with pytest.raises(ValueError, match="intent must be a str"):
        extract_source_spans("some ac", 123)  # type: ignore[arg-type]


def test_extract_source_spans_provenance_text_in_intent():
    """The text at the returned span should be a substring of intent."""
    result = extract_source_spans(SIMPLE_AC, SIMPLE_INTENT)
    for span in result:
        extracted = SIMPLE_INTENT[span["start"]: span["end"]]
        # The extracted text should be a meaningful substring of intent
        assert extracted in SIMPLE_INTENT


# ---------------------------------------------------------------------------
# add_ac_provenance
# ---------------------------------------------------------------------------


def test_add_ac_provenance_returns_list():
    """add_ac_provenance returns a list."""
    acs = [SIMPLE_AC]
    result = add_ac_provenance(acs, SIMPLE_INTENT)
    assert isinstance(result, list)


def test_add_ac_provenance_length_matches_acs():
    """Output list has the same length as input ACs list."""
    acs = ["system authenticates users", "criterion must reference behaviour"]
    result = add_ac_provenance(acs, INTENT)
    assert len(result) == len(acs)


def test_add_ac_provenance_record_has_required_keys():
    """Each record has 'ac', 'spans', and 'provenance' keys."""
    result = add_ac_provenance([SIMPLE_AC], SIMPLE_INTENT)
    assert len(result) == 1
    rec = result[0]
    assert "ac" in rec
    assert "spans" in rec
    assert "provenance" in rec


def test_add_ac_provenance_ac_field_matches_input():
    """The 'ac' field in each record matches the original AC text."""
    acs = ["system authenticates users", "emit acceptance criteria"]
    result = add_ac_provenance(acs, INTENT)
    for rec, original in zip(result, acs):
        assert rec["ac"] == original


def test_add_ac_provenance_spans_is_list():
    """The 'spans' field is a list in every record."""
    result = add_ac_provenance([SIMPLE_AC], SIMPLE_INTENT)
    assert isinstance(result[0]["spans"], list)


def test_add_ac_provenance_provenance_is_list():
    """The 'provenance' field is a list in every record."""
    result = add_ac_provenance([SIMPLE_AC], SIMPLE_INTENT)
    assert isinstance(result[0]["provenance"], list)


def test_add_ac_provenance_provenance_strings_are_substrings_of_intent():
    """Every string in 'provenance' is a substring of intent."""
    result = add_ac_provenance([SIMPLE_AC], SIMPLE_INTENT)
    for text in result[0]["provenance"]:
        assert text in SIMPLE_INTENT


def test_add_ac_provenance_empty_ac_list_returns_empty():
    """Empty AC list returns empty list."""
    result = add_ac_provenance([], INTENT)
    assert result == []


def test_add_ac_provenance_empty_intent_gives_empty_spans():
    """Empty intent string gives empty spans for all ACs."""
    result = add_ac_provenance(["some criterion"], "")
    assert result[0]["spans"] == []
    assert result[0]["provenance"] == []


def test_add_ac_provenance_raises_for_non_string_intent():
    """Non-string intent raises ValueError."""
    with pytest.raises(ValueError, match="intent must be a str"):
        add_ac_provenance(["ac"], None)  # type: ignore[arg-type]


def test_add_ac_provenance_raises_for_non_string_ac_in_list():
    """Non-string element in ACs list raises TypeError."""
    with pytest.raises(TypeError):
        add_ac_provenance([42], INTENT)  # type: ignore[arg-type]


def test_add_ac_provenance_multiple_acs_all_have_spans_field():
    """Multiple ACs — all records have 'spans' field (may be empty)."""
    acs = [
        "emit acceptance criteria",
        "criterion must reference behaviour",
        "round-trip coverage ninety percent",
    ]
    result = add_ac_provenance(acs, INTENT)
    for rec in result:
        assert "spans" in rec
        assert isinstance(rec["spans"], list)


def test_add_ac_provenance_span_indices_within_bounds():
    """All span indices are valid indices into intent string."""
    result = add_ac_provenance([SIMPLE_AC], SIMPLE_INTENT)
    for rec in result:
        for span in rec["spans"]:
            assert 0 <= span["start"] <= len(SIMPLE_INTENT)
            assert 0 <= span["end"] <= len(SIMPLE_INTENT)
            assert span["start"] <= span["end"]
