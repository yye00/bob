"""Tests for sub_translation_provenance_every_ac_traces_source_intent."""

import pytest

from bob3.sub_translation_provenance_every_ac_traces_source_intent import (
    sub_translation_provenance_every_ac_traces_source_intent,
)


INTENT = (
    "The system shall emit acceptance criteria from the feature description. "
    "Each criterion must reference a specific behaviour observable by the user. "
    "The extractor parses sentences and maps keywords to structured output. "
    "Ambiguous clauses are flagged for human review before code generation begins."
)

# Four ACs that cover all 4 sentences of INTENT (guarantees >=90% coverage)
FULL_COVERAGE_ACS = [
    "emit acceptance criteria from feature description",
    "criterion references observable user behaviour",
    "extractor parses sentences maps keywords structured output",
    "ambiguous clauses flagged human review before code generation",
]


def test_sub_translation_provenance_every_ac_traces_source_intent():
    """Each AC in the result carries a non-empty provenance span list."""
    result = sub_translation_provenance_every_ac_traces_source_intent(
        FULL_COVERAGE_ACS, INTENT
    )

    assert len(result) == len(FULL_COVERAGE_ACS)
    for entry in result:
        assert "ac" in entry
        assert "spans" in entry
        assert "provenance" in entry
        assert entry["spans"], f"AC {entry['ac']!r} has empty spans"
        for span in entry["spans"]:
            assert "start" in span
            assert "end" in span
            assert span["start"] >= 0
            assert span["end"] <= len(INTENT)
            assert span["start"] < span["end"]


def test_returns_one_record_per_ac():
    result = sub_translation_provenance_every_ac_traces_source_intent(
        FULL_COVERAGE_ACS, INTENT
    )
    assert len(result) == len(FULL_COVERAGE_ACS)
    for entry, expected_ac in zip(result, FULL_COVERAGE_ACS):
        assert entry["ac"] == expected_ac


def test_provenance_text_is_substring_of_intent():
    result = sub_translation_provenance_every_ac_traces_source_intent(
        FULL_COVERAGE_ACS, INTENT
    )
    for entry in result:
        for prov in entry["provenance"]:
            assert prov in INTENT


def test_empty_ac_list_returns_empty_result():
    """Empty AC list with min_coverage=0.0 returns empty result."""
    result = sub_translation_provenance_every_ac_traces_source_intent(
        [], INTENT, min_coverage=0.0
    )
    assert result == []


def test_raises_when_ac_has_no_overlap_with_intent():
    """An AC with zero token overlap raises ValueError (empty spans)."""
    unrelated_acs = ["xyzzy frobble quux garply waldo 12345"]
    with pytest.raises(ValueError, match="empty provenance"):
        sub_translation_provenance_every_ac_traces_source_intent(
            unrelated_acs, INTENT
        )


def test_span_offsets_reference_intent_correctly():
    result = sub_translation_provenance_every_ac_traces_source_intent(
        FULL_COVERAGE_ACS, INTENT
    )
    for entry in result:
        for span, prov in zip(entry["spans"], entry["provenance"]):
            assert INTENT[span["start"]: span["end"]] == prov


def test_custom_min_coverage_zero_allows_single_ac():
    """With min_coverage=0.0, a single AC that partially covers intent passes."""
    acs = ["emit acceptance criteria from feature description"]
    result = sub_translation_provenance_every_ac_traces_source_intent(
        acs, INTENT, min_coverage=0.0
    )
    assert len(result) == 1
    assert result[0]["ac"] == acs[0]


def test_raises_on_insufficient_coverage():
    """Single-sentence AC against a multi-sentence intent fails at 90% threshold."""
    single_ac = ["emit acceptance criteria from feature description"]
    with pytest.raises(ValueError, match="coverage|threshold|provenance"):
        sub_translation_provenance_every_ac_traces_source_intent(
            single_ac, INTENT, min_coverage=0.90
        )


def test_result_structure_has_expected_keys():
    """Every result dict has exactly the expected keys."""
    result = sub_translation_provenance_every_ac_traces_source_intent(
        FULL_COVERAGE_ACS, INTENT
    )
    for entry in result:
        assert set(entry.keys()) == {"ac", "spans", "provenance"}
