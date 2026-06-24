"""Tests for bob.provenance.add_provenance_field."""

from __future__ import annotations

import pytest

from bob.provenance import add_provenance_field


INTENT = (
    "The system shall emit acceptance criteria from the feature description. "
    "Each criterion must reference a specific behaviour observable by the user. "
    "The extractor parses sentences and maps keywords to structured output. "
    "Ambiguous clauses are flagged for human review before code generation begins."
)

FULL_COVERAGE_ACS = [
    "emit acceptance criteria from feature description",
    "criterion references observable user behaviour",
    "extractor parses sentences maps keywords structured output",
    "ambiguous clauses flagged human review before code generation",
]


def test_add_provenance_field_returns_dict():
    ac = FULL_COVERAGE_ACS[0]
    result = add_provenance_field(ac, INTENT)
    assert isinstance(result, dict)
    assert "ac" in result
    assert "spans" in result
    assert "provenance" in result


def test_add_provenance_field_ac_text_preserved():
    ac = FULL_COVERAGE_ACS[0]
    result = add_provenance_field(ac, INTENT)
    assert result["ac"] == ac


def test_add_provenance_field_spans_are_valid():
    ac = FULL_COVERAGE_ACS[0]
    result = add_provenance_field(ac, INTENT)
    assert len(result["spans"]) > 0
    for span in result["spans"]:
        assert "start" in span
        assert "end" in span
        assert span["start"] >= 0
        assert span["end"] <= len(INTENT)
        assert span["start"] < span["end"]


def test_add_provenance_field_provenance_texts_are_substrings():
    ac = FULL_COVERAGE_ACS[0]
    result = add_provenance_field(ac, INTENT)
    for prov in result["provenance"]:
        assert prov in INTENT


def test_add_provenance_field_provenance_matches_spans():
    ac = FULL_COVERAGE_ACS[0]
    result = add_provenance_field(ac, INTENT)
    for span, prov in zip(result["spans"], result["provenance"]):
        assert INTENT[span["start"]: span["end"]] == prov


def test_add_provenance_field_accepts_dict_with_ac_key():
    ac_dict = {"ac": FULL_COVERAGE_ACS[1], "extra": "meta"}
    result = add_provenance_field(ac_dict, INTENT)
    assert result["ac"] == FULL_COVERAGE_ACS[1]
    assert result["extra"] == "meta"
    assert len(result["spans"]) > 0


def test_add_provenance_field_dict_extra_fields_preserved():
    ac_dict = {"ac": FULL_COVERAGE_ACS[2], "priority": 1, "tag": "core"}
    result = add_provenance_field(ac_dict, INTENT)
    assert result["priority"] == 1
    assert result["tag"] == "core"


def test_add_provenance_field_invalid_intent_type_raises():
    with pytest.raises(ValueError, match="intent must be a str"):
        add_provenance_field("some ac", 123)


def test_add_provenance_field_invalid_ac_type_raises():
    with pytest.raises(TypeError, match="ac must be str or dict"):
        add_provenance_field(42, INTENT)


def test_add_provenance_field_unmatched_ac_raises_when_strict():
    unrelated = "xyzzy frobble quux garply 99999"
    with pytest.raises(ValueError, match="empty provenance"):
        add_provenance_field(unrelated, INTENT, strict=True)


def test_add_provenance_field_unmatched_ac_no_error_when_not_strict():
    unrelated = "xyzzy frobble quux garply 99999"
    result = add_provenance_field(unrelated, INTENT, strict=False)
    assert result["ac"] == unrelated
    assert result["spans"] == []
    assert result["provenance"] == []


def test_add_provenance_field_multiple_acs_all_match():
    for ac in FULL_COVERAGE_ACS:
        result = add_provenance_field(ac, INTENT)
        assert result["spans"], f"AC {ac!r} produced empty spans"
