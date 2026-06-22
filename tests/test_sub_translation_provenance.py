"""Tests for bob3.sub_translation_provenance.

Covers:
- add_provenance_to_ac: attaches spans and provenance substrings
- trace_ac_to_intent: retrieves AC + spans from the database
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid

import pytest

from bob3.sub_translation_provenance import add_provenance_to_ac, trace_ac_to_intent


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


# ---------------------------------------------------------------------------
# add_provenance_to_ac — happy path
# ---------------------------------------------------------------------------


def test_add_provenance_to_ac_returns_ac_spans_provenance():
    """Returns a dict with 'ac', 'spans', and 'provenance' keys."""
    result = add_provenance_to_ac(FULL_COVERAGE_ACS[0], INTENT)
    assert "ac" in result
    assert "spans" in result
    assert "provenance" in result


def test_add_provenance_to_ac_preserves_ac_text():
    ac = FULL_COVERAGE_ACS[0]
    result = add_provenance_to_ac(ac, INTENT)
    assert result["ac"] == ac


def test_add_provenance_to_ac_span_is_valid_range():
    """Each span must have start < end and both within intent bounds."""
    result = add_provenance_to_ac(FULL_COVERAGE_ACS[0], INTENT)
    assert result["spans"], "Expected at least one span"
    for span in result["spans"]:
        assert span["start"] >= 0
        assert span["end"] <= len(INTENT)
        assert span["start"] < span["end"]


def test_add_provenance_to_ac_provenance_is_substring_of_intent():
    """Each provenance entry must be a substring of the original intent."""
    result = add_provenance_to_ac(FULL_COVERAGE_ACS[0], INTENT)
    for prov in result["provenance"]:
        assert prov in INTENT


def test_add_provenance_to_ac_spans_and_provenance_lengths_match():
    """Number of spans and provenance substrings must agree."""
    result = add_provenance_to_ac(FULL_COVERAGE_ACS[0], INTENT)
    assert len(result["spans"]) == len(result["provenance"])


def test_add_provenance_to_ac_all_full_coverage_acs():
    """All four coverage ACs produce non-empty spans."""
    for ac in FULL_COVERAGE_ACS:
        result = add_provenance_to_ac(ac, INTENT)
        assert result["spans"], f"AC {ac!r} returned empty spans"


# ---------------------------------------------------------------------------
# add_provenance_to_ac — error path
# ---------------------------------------------------------------------------


def test_add_provenance_to_ac_non_str_ac_raises_type_error():
    """Non-string ac raises TypeError."""
    with pytest.raises(TypeError, match="ac must be a str"):
        add_provenance_to_ac(42, INTENT)  # type: ignore[arg-type]


def test_add_provenance_to_ac_none_ac_raises_type_error():
    """None ac raises TypeError."""
    with pytest.raises(TypeError, match="ac must be a str"):
        add_provenance_to_ac(None, INTENT)  # type: ignore[arg-type]


def test_add_provenance_to_ac_non_str_intent_raises_value_error():
    """Non-string intent raises ValueError."""
    with pytest.raises(ValueError, match="intent must be a str"):
        add_provenance_to_ac("some ac", 123)  # type: ignore[arg-type]


def test_add_provenance_to_ac_none_intent_raises_value_error():
    """None intent raises ValueError."""
    with pytest.raises(ValueError, match="intent must be a str"):
        add_provenance_to_ac("some ac", None)  # type: ignore[arg-type]


def test_add_provenance_to_ac_unrelated_ac_strict_raises():
    """AC with zero token overlap raises ValueError when strict=True (default)."""
    unrelated = "xyzzy frobble quux garply waldo 12345"
    with pytest.raises(ValueError, match="empty provenance"):
        add_provenance_to_ac(unrelated, INTENT)


def test_add_provenance_to_ac_unrelated_ac_non_strict_returns_empty_spans():
    """AC with zero token overlap returns empty spans when strict=False."""
    unrelated = "xyzzy frobble quux garply waldo 12345"
    result = add_provenance_to_ac(unrelated, INTENT, strict=False)
    assert result["ac"] == unrelated
    assert result["spans"] == []
    assert result["provenance"] == []


# ---------------------------------------------------------------------------
# trace_ac_to_intent — database integration
# ---------------------------------------------------------------------------


def _make_temp_db(feature_id: str, description: str, acs: list[str]) -> str:
    """Create a minimal bob3.db in a temp directory and return its path."""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "bob3.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE features (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            parent_id TEXT,
            depth INTEGER,
            title TEXT,
            description TEXT,
            acceptance_criteria TEXT,
            status TEXT,
            confidence REAL,
            provenance_spans TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO features (id, project_id, title, description, acceptance_criteria, status) VALUES (?, ?, ?, ?, ?, ?)",
        (feature_id, "proj-1", "Test Feature", description, json.dumps(acs), "pending"),
    )
    conn.commit()
    conn.close()
    return db_path


def test_trace_ac_to_intent_returns_expected_keys():
    """trace_ac_to_intent returns a dict with required keys."""
    feature_id = str(uuid.uuid4())
    db_path = _make_temp_db(feature_id, INTENT, FULL_COVERAGE_ACS)
    result = trace_ac_to_intent(feature_id, 0, db_path=db_path)
    assert "feature_id" in result
    assert "ac_index" in result
    assert "ac" in result
    assert "spans" in result


def test_trace_ac_to_intent_returns_correct_ac():
    """trace_ac_to_intent returns the correct AC text for the given index."""
    feature_id = str(uuid.uuid4())
    db_path = _make_temp_db(feature_id, INTENT, FULL_COVERAGE_ACS)
    for idx, expected_ac in enumerate(FULL_COVERAGE_ACS):
        result = trace_ac_to_intent(feature_id, idx, db_path=db_path)
        assert result["ac"] == expected_ac
        assert result["ac_index"] == idx


def test_trace_ac_to_intent_returns_feature_id():
    """trace_ac_to_intent returns the requested feature_id."""
    feature_id = str(uuid.uuid4())
    db_path = _make_temp_db(feature_id, INTENT, FULL_COVERAGE_ACS)
    result = trace_ac_to_intent(feature_id, 0, db_path=db_path)
    assert result["feature_id"] == feature_id


def test_trace_ac_to_intent_unknown_feature_raises_key_error():
    """trace_ac_to_intent raises KeyError for an unknown feature_id."""
    feature_id = str(uuid.uuid4())
    db_path = _make_temp_db(feature_id, INTENT, FULL_COVERAGE_ACS)
    with pytest.raises(KeyError):
        trace_ac_to_intent("does-not-exist", 0, db_path=db_path)


def test_trace_ac_to_intent_out_of_range_raises_index_error():
    """trace_ac_to_intent raises IndexError when ac_index is out of range."""
    feature_id = str(uuid.uuid4())
    db_path = _make_temp_db(feature_id, INTENT, FULL_COVERAGE_ACS)
    with pytest.raises(IndexError):
        trace_ac_to_intent(feature_id, 999, db_path=db_path)


def test_trace_ac_to_intent_spans_are_dicts_or_list():
    """spans in the result is a list (may be empty for unresolved provenance)."""
    feature_id = str(uuid.uuid4())
    db_path = _make_temp_db(feature_id, INTENT, FULL_COVERAGE_ACS)
    result = trace_ac_to_intent(feature_id, 0, db_path=db_path)
    assert isinstance(result["spans"], list)
