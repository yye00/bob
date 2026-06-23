"""Error-path tests for sub-translation provenance.

Invalid input raises ValueError and the function does not silently succeed.
Tests cover both bob.provenance.add_provenance_field and the core module function.
"""

from __future__ import annotations

import pytest

from bob.provenance import add_provenance_field
from bob3.spec_quality.provenance import (
    Span,
    attach_provenance,
    reject_empty_provenance,
    reject_non_overlapping,
    EmptyProvenanceError,
    NonOverlappingProvenanceError,
)
from bob3.sub_translation_provenance_every_ac_traces_source_intent import (
    sub_translation_provenance_every_ac_traces_source_intent,
)


INTENT = (
    "The system shall emit acceptance criteria from the feature description. "
    "Each criterion must reference a specific behaviour observable by the user."
)


# ---------------------------------------------------------------------------
# add_provenance_field — invalid argument types
# ---------------------------------------------------------------------------


def test_add_provenance_field_int_ac_raises_type_error():
    """Passing an integer as ac raises TypeError."""
    with pytest.raises(TypeError, match="ac must be str or dict"):
        add_provenance_field(42, INTENT)


def test_add_provenance_field_list_ac_raises_type_error():
    """Passing a list as ac raises TypeError."""
    with pytest.raises(TypeError, match="ac must be str or dict"):
        add_provenance_field(["criterion"], INTENT)


def test_add_provenance_field_none_ac_raises_type_error():
    """Passing None as ac raises TypeError."""
    with pytest.raises(TypeError, match="ac must be str or dict"):
        add_provenance_field(None, INTENT)


def test_add_provenance_field_intent_not_str_raises_value_error():
    """Passing a non-string intent raises ValueError."""
    with pytest.raises(ValueError, match="intent must be a str"):
        add_provenance_field("some criterion", 123)


def test_add_provenance_field_intent_none_raises_value_error():
    """Passing None as intent raises ValueError."""
    with pytest.raises(ValueError, match="intent must be a str"):
        add_provenance_field("some criterion", None)


def test_add_provenance_field_intent_list_raises_value_error():
    """Passing a list as intent raises ValueError."""
    with pytest.raises(ValueError, match="intent must be a str"):
        add_provenance_field("some criterion", ["intent text"])


# ---------------------------------------------------------------------------
# add_provenance_field — strict mode with no span overlap
# ---------------------------------------------------------------------------


def test_add_provenance_field_unrelated_ac_strict_raises():
    """An AC with no token overlap raises ValueError when strict=True."""
    unrelated = "xyzzy frobble quux garply waldo"
    with pytest.raises(ValueError, match="empty provenance"):
        add_provenance_field(unrelated, INTENT, strict=True)


def test_add_provenance_field_strict_is_default():
    """strict=True is the default — unrelated AC raises without explicit strict=True."""
    unrelated = "xyzzy frobble quux garply waldo"
    with pytest.raises(ValueError):
        add_provenance_field(unrelated, INTENT)


def test_add_provenance_field_unrelated_ac_non_strict_does_not_raise():
    """An AC with no token overlap does NOT raise when strict=False."""
    unrelated = "xyzzy frobble quux garply waldo"
    result = add_provenance_field(unrelated, INTENT, strict=False)
    assert result["spans"] == []
    assert result["provenance"] == []


# ---------------------------------------------------------------------------
# sub_translation_provenance — invalid ACs raise ValueError
# ---------------------------------------------------------------------------


def test_sub_translation_raises_for_unrelated_ac():
    """AC with no token overlap in intent raises ValueError (empty provenance)."""
    unrelated = ["xyzzy frobble quux garply 12345"]
    with pytest.raises(ValueError, match="empty provenance"):
        sub_translation_provenance_every_ac_traces_source_intent(
            unrelated, INTENT
        )


def test_sub_translation_raises_for_coverage_below_threshold():
    """Single partial AC against multi-sentence intent fails at 90% threshold."""
    single_ac = ["emit acceptance criteria from feature description"]
    with pytest.raises(ValueError, match="coverage|threshold|provenance"):
        sub_translation_provenance_every_ac_traces_source_intent(
            single_ac, INTENT, min_coverage=0.90
        )


def test_sub_translation_raises_does_not_return_partial_result():
    """When ValueError is raised, no partial result is silently returned."""
    unrelated = ["xyzzy frobble quux garply waldo"]
    result_holder = []

    with pytest.raises(ValueError):
        result_holder.append(
            sub_translation_provenance_every_ac_traces_source_intent(
                unrelated, INTENT
            )
        )

    # result_holder must remain empty — the function raised before returning.
    assert result_holder == []


# ---------------------------------------------------------------------------
# reject_empty_provenance — guard function
# ---------------------------------------------------------------------------


def test_reject_empty_provenance_raises_empty_provenance_error():
    """reject_empty_provenance raises EmptyProvenanceError for empty spans."""
    with pytest.raises(EmptyProvenanceError, match="empty provenance spans"):
        reject_empty_provenance("some criterion", [])


def test_reject_empty_provenance_is_subclass_of_value_error():
    """EmptyProvenanceError is a ValueError subclass."""
    with pytest.raises(ValueError):
        reject_empty_provenance("some criterion", [])


def test_reject_empty_provenance_does_not_raise_when_spans_present():
    """reject_empty_provenance does NOT raise when spans is non-empty."""
    reject_empty_provenance("some criterion", [Span(0, 5)])  # should not raise


# ---------------------------------------------------------------------------
# reject_non_overlapping — guard function
# ---------------------------------------------------------------------------


def test_reject_non_overlapping_raises_when_no_overlap():
    """reject_non_overlapping raises NonOverlappingProvenanceError when spans miss AC tokens."""
    intent = "authentication user login"
    ac = "database migration"
    spans = [Span(0, len(intent))]  # covers intent but contains none of ac tokens
    # "database" and "migration" are not in intent, so no overlap
    with pytest.raises(NonOverlappingProvenanceError, match="spans do not overlap"):
        reject_non_overlapping(ac, spans, intent)


def test_reject_non_overlapping_is_subclass_of_value_error():
    """NonOverlappingProvenanceError is a ValueError subclass."""
    intent = "authentication user login"
    ac = "database migration"
    spans = [Span(0, len(intent))]
    with pytest.raises(ValueError):
        reject_non_overlapping(ac, spans, intent)


def test_reject_non_overlapping_noop_on_empty_spans():
    """reject_non_overlapping is a no-op when spans is empty (defer to reject_empty)."""
    reject_non_overlapping("any criterion", [], "any intent")  # must not raise


# ---------------------------------------------------------------------------
# Span — invalid construction raises ValueError
# ---------------------------------------------------------------------------


def test_span_negative_start_raises():
    """Span with negative start raises ValueError."""
    with pytest.raises(ValueError):
        Span(start=-1, end=5)


def test_span_end_less_than_start_raises():
    """Span with end < start raises ValueError."""
    with pytest.raises(ValueError):
        Span(start=10, end=5)


def test_span_start_equals_end_is_valid():
    """Span(start=n, end=n) is a valid zero-length span; only end < start raises."""
    s = Span(start=3, end=3)  # allowed by implementation (end >= start)
    assert s.start == s.end == 3
