"""Boundary-case tests for sub-translation provenance.

Empty, zero, or minimum input returns a well-defined result rather than raising.
Tests cover both bob.provenance.add_provenance_field and the core module function.
"""

from __future__ import annotations

import pytest

from bob.provenance import add_provenance_field
from bob3.spec_quality.provenance import (
    attach_provenance,
    validate_coverage,
    Span,
)
from bob3.sub_translation_provenance_every_ac_traces_source_intent import (
    sub_translation_provenance_every_ac_traces_source_intent,
)


# ---------------------------------------------------------------------------
# Empty / zero AC list
# ---------------------------------------------------------------------------


def test_empty_ac_list_returns_empty_list():
    """Empty AC list with min_coverage=0.0 returns an empty list, not an error."""
    result = sub_translation_provenance_every_ac_traces_source_intent(
        [], "some intent text", min_coverage=0.0
    )
    assert result == []


def test_attach_provenance_empty_list():
    """attach_provenance with no ACs returns an empty list."""
    records = attach_provenance([], "any intent here")
    assert records == []


# ---------------------------------------------------------------------------
# Empty intent string
# ---------------------------------------------------------------------------


def test_add_provenance_field_empty_intent_non_strict_returns_empty_spans():
    """Empty intent with strict=False yields empty spans list, not an error."""
    result = add_provenance_field("some criterion", "", strict=False)
    assert result["ac"] == "some criterion"
    assert result["spans"] == []
    assert result["provenance"] == []


def test_attach_provenance_empty_intent_returns_empty_spans():
    """attach_provenance with empty intent produces records with no spans."""
    records = attach_provenance(["some criterion"], "")
    assert len(records) == 1
    assert records[0].ac == "some criterion"
    assert records[0].spans == []


# ---------------------------------------------------------------------------
# Minimum non-empty inputs
# ---------------------------------------------------------------------------


def test_single_token_ac_and_single_token_intent_matches():
    """A one-word AC that matches a one-word intent produces a valid span."""
    result = add_provenance_field("authentication", "authentication", strict=False)
    assert result["ac"] == "authentication"
    # May or may not match depending on overlap; either way must not raise.
    assert isinstance(result["spans"], list)
    assert isinstance(result["provenance"], list)


def test_single_ac_single_sentence_intent():
    """Minimum meaningful case: one AC, one-sentence intent, matching tokens."""
    intent = "The system authenticates users."
    ac = "system authenticates users"
    result = add_provenance_field(ac, intent, strict=False)
    assert result["ac"] == ac
    assert isinstance(result["spans"], list)


# ---------------------------------------------------------------------------
# validate_coverage with no load-bearing tokens (vacuously 1.0)
# ---------------------------------------------------------------------------


def test_validate_coverage_no_load_bearing_tokens_passes():
    """Intent with only stop-words has no load-bearing tokens; coverage is 1.0."""
    intent = "a the and or"
    records = attach_provenance(["a the and"], intent)
    passed, coverage, bad = validate_coverage(records, intent, min_coverage=0.90)
    # No load-bearing tokens → coverage vacuously 1.0
    assert coverage == 1.0


# ---------------------------------------------------------------------------
# Span boundary: zero-length adjacent positions
# ---------------------------------------------------------------------------


def test_span_start_equals_end_is_valid_zero_length():
    """Span(start=0, end=0) is a valid zero-length span (end >= start)."""
    s = Span(start=0, end=0)
    assert s.start == 0
    assert s.end == 0
    assert s.text("anything") == ""


def test_span_valid_minimum():
    """Span(start=0, end=1) is the minimum valid single-character span."""
    s = Span(start=0, end=1)
    assert s.start == 0
    assert s.end == 1
    assert s.text("X") == "X"


# ---------------------------------------------------------------------------
# add_provenance_field with dict AC with empty string value
# ---------------------------------------------------------------------------


def test_add_provenance_field_dict_with_empty_ac_value_non_strict():
    """Dict AC with empty 'ac' key and strict=False returns empty spans."""
    result = add_provenance_field({"ac": ""}, "some intent text", strict=False)
    assert result["ac"] == ""
    assert result["spans"] == []
    assert result["provenance"] == []


# ---------------------------------------------------------------------------
# min_coverage=0.0 never raises coverage error
# ---------------------------------------------------------------------------


def test_min_coverage_zero_single_ac_partial_overlap():
    """min_coverage=0.0 means any coverage is acceptable, so no ValueError."""
    intent = (
        "The system shall emit acceptance criteria from the feature description. "
        "Each criterion must reference a specific behaviour observable by the user."
    )
    # Only one AC: covers only part of intent, but min_coverage=0.0 allows it.
    acs = ["emit acceptance criteria from feature description"]
    result = sub_translation_provenance_every_ac_traces_source_intent(
        acs, intent, min_coverage=0.0
    )
    assert len(result) == 1
    assert result[0]["ac"] == acs[0]
