"""Tests for bob.spec_provenance.

Covers:
- trace_ac_to_source: retrieves AC + provenance spans from the database
- compute_coverage: validates round-trip coverage of intent tokens

Integration: bob.spec_synthesizer — provenance spans can be attached after
synthesis via compute_coverage and trace_ac_to_source.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid

import pytest

from bob.spec_provenance import compute_coverage, trace_ac_to_source


INTENT = (
    "The system shall emit acceptance criteria from the feature description. "
    "Each criterion must reference a specific behaviour observable by the user. "
    "The extractor parses sentences and maps keywords to structured output. "
    "Ambiguous clauses are flagged for human review before code generation begins."
)

# Four ACs covering all four sentences of INTENT (guarantees >=90% coverage)
FULL_COVERAGE_ACS = [
    "emit acceptance criteria from feature description",
    "criterion references observable user behaviour",
    "extractor parses sentences maps keywords structured output",
    "ambiguous clauses flagged human review before code generation",
]


# ---------------------------------------------------------------------------
# compute_coverage — happy path
# ---------------------------------------------------------------------------


def test_compute_coverage_returns_tuple():
    """compute_coverage returns a (bool, float) tuple."""
    result = compute_coverage(FULL_COVERAGE_ACS, INTENT)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert isinstance(result[1], float)


def test_compute_coverage_full_coverage_passes():
    """Four ACs covering all four intent sentences pass the 90% threshold."""
    passed, coverage = compute_coverage(FULL_COVERAGE_ACS, INTENT)
    assert passed is True
    assert coverage >= 0.90


def test_compute_coverage_ratio_is_between_zero_and_one():
    """Coverage ratio is always in [0.0, 1.0]."""
    _, coverage = compute_coverage(FULL_COVERAGE_ACS, INTENT)
    assert 0.0 <= coverage <= 1.0


def test_compute_coverage_empty_acs_empty_intent():
    """Empty ACs against stop-word-only intent: vacuous coverage = 1.0."""
    _, coverage = compute_coverage([], "a the and or")
    assert coverage == 1.0


def test_compute_coverage_custom_threshold():
    """min_coverage=0.0 always passes."""
    passed, _ = compute_coverage(["any criterion"], INTENT, min_coverage=0.0)
    assert passed is True


# ---------------------------------------------------------------------------
# compute_coverage — error paths
# ---------------------------------------------------------------------------


def test_compute_coverage_non_string_intent_raises():
    """compute_coverage raises ValueError when intent is not a string."""
    with pytest.raises(ValueError, match="intent must be a str"):
        compute_coverage(["criterion"], 123)


def test_compute_coverage_intent_none_raises():
    """compute_coverage raises ValueError when intent is None."""
    with pytest.raises(ValueError, match="intent must be a str"):
        compute_coverage(["criterion"], None)


def test_compute_coverage_acs_not_list_raises():
    """compute_coverage raises ValueError when acs is not a list."""
    with pytest.raises(ValueError, match="acs must be a list"):
        compute_coverage("criterion", INTENT)


# ---------------------------------------------------------------------------
# trace_ac_to_source — happy path (using a temp database)
# ---------------------------------------------------------------------------


def _make_temp_db(
    feature_id: str,
    name: str,
    description: str,
    acs: list[str],
) -> str:
    """Create a minimal sqlite3 database file and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.execute(
        """
        CREATE TABLE features (
            id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            acceptance_criteria TEXT,
            provenance_spans TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO features VALUES (?, ?, ?, ?, ?)",
        (feature_id, name, description, json.dumps(acs), None),
    )
    conn.commit()
    conn.close()
    return tmp.name


def test_trace_ac_to_source_returns_expected_keys():
    """trace_ac_to_source returns a dict with the expected keys."""
    fid = str(uuid.uuid4())
    db = _make_temp_db(fid, "Test Feature", INTENT, FULL_COVERAGE_ACS)
    result = trace_ac_to_source(fid, 0, db_path=db)
    assert "feature_id" in result
    assert "ac_index" in result
    assert "ac" in result
    assert "spans" in result


def test_trace_ac_to_source_returns_correct_feature_id():
    """trace_ac_to_source returns the requested feature_id."""
    fid = str(uuid.uuid4())
    db = _make_temp_db(fid, "Test Feature", INTENT, FULL_COVERAGE_ACS)
    result = trace_ac_to_source(fid, 0, db_path=db)
    assert result["feature_id"] == fid


def test_trace_ac_to_source_returns_correct_ac_text():
    """trace_ac_to_source returns the AC text at the requested index."""
    fid = str(uuid.uuid4())
    db = _make_temp_db(fid, "Test Feature", INTENT, FULL_COVERAGE_ACS)
    result = trace_ac_to_source(fid, 1, db_path=db)
    assert result["ac"] == FULL_COVERAGE_ACS[1]
    assert result["ac_index"] == 1


def test_trace_ac_to_source_spans_are_list():
    """trace_ac_to_source returns spans as a list."""
    fid = str(uuid.uuid4())
    db = _make_temp_db(fid, "Test Feature", INTENT, FULL_COVERAGE_ACS)
    result = trace_ac_to_source(fid, 0, db_path=db)
    assert isinstance(result["spans"], list)


def test_trace_ac_to_source_span_dicts_have_start_end():
    """Each span dict has 'start' and 'end' integer keys."""
    fid = str(uuid.uuid4())
    db = _make_temp_db(fid, "Test Feature", INTENT, FULL_COVERAGE_ACS)
    result = trace_ac_to_source(fid, 0, db_path=db)
    for span in result["spans"]:
        assert "start" in span
        assert "end" in span
        assert isinstance(span["start"], int)
        assert isinstance(span["end"], int)
        assert span["start"] >= 0
        assert span["end"] >= span["start"]


# ---------------------------------------------------------------------------
# trace_ac_to_source — error paths
# ---------------------------------------------------------------------------


def test_trace_ac_to_source_missing_feature_raises_key_error():
    """trace_ac_to_source raises KeyError when feature_id is not found."""
    fid = str(uuid.uuid4())
    db = _make_temp_db(fid, "Test Feature", INTENT, FULL_COVERAGE_ACS)
    with pytest.raises(KeyError):
        trace_ac_to_source("nonexistent-id", 0, db_path=db)


def test_trace_ac_to_source_out_of_range_ac_raises_index_error():
    """trace_ac_to_source raises IndexError when ac_index is out of range."""
    fid = str(uuid.uuid4())
    db = _make_temp_db(fid, "Test Feature", INTENT, FULL_COVERAGE_ACS)
    with pytest.raises(IndexError):
        trace_ac_to_source(fid, 999, db_path=db)


def test_trace_ac_to_source_negative_index_raises_index_error():
    """trace_ac_to_source raises IndexError for a negative ac_index."""
    fid = str(uuid.uuid4())
    db = _make_temp_db(fid, "Test Feature", INTENT, FULL_COVERAGE_ACS)
    with pytest.raises((IndexError, ValueError)):
        trace_ac_to_source(fid, -1, db_path=db)


# ---------------------------------------------------------------------------
# Integration: bob.spec_synthesizer
# ---------------------------------------------------------------------------


def test_compute_coverage_integrates_with_synthesizer_output():
    """Coverage check can be applied to ACs produced by spec_synthesizer patterns."""
    from bob import spec_synthesizer  # noqa: F401 — ensure importable

    # Simulate the ACs a synthesizer would emit for INTENT
    synthesized_acs = [
        "system emits acceptance criteria from feature description",
        "criterion references specific behaviour observable by user",
        "extractor parses sentences maps keywords structured output",
        "ambiguous clauses flagged human review before code generation",
    ]
    passed, coverage = compute_coverage(synthesized_acs, INTENT)
    assert passed is True, f"Expected coverage >=0.90, got {coverage:.2%}"
