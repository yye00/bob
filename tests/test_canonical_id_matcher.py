"""Tests for auditor.canonical_id_matcher.match_by_canonical_id.

AC: pytest: tests/test_canonical_id_matcher.py
    Function defined: auditor.canonical_id_matcher.match_by_canonical_id
    File exists: src/auditor/canonical_id_matcher.py
"""

from __future__ import annotations

import pytest

from auditor.canonical_id_matcher import match_by_canonical_id


class TestMatchByCanonicalIdHappyPath:
    """Canonical ID found in various fields and formats."""

    def test_exact_match_in_id_field(self):
        entry = {"id": "F-R7-478", "title": "infra recovery", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_match_in_title_field(self):
        entry = {"id": "sidecar-alias", "title": "[F-R7-479] permanent carry", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-479") is True

    def test_match_in_description_field(self):
        entry = {"id": "unrelated", "title": "some feature", "description": "depends on F-R7-553"}
        assert match_by_canonical_id(entry, "F-R7-553") is True

    def test_id_token_embedded_in_longer_string(self):
        entry = {"id": "unrelated", "title": "[F-R7-478] carry-forward feature (permanent)", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_match_across_multiple_fields(self):
        # Matches id field; title also has it but we only need one
        entry = {"id": "F-R7-478", "title": "F-R7-478 feature", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_large_numeric_suffix(self):
        entry = {"id": "F-R7-99999", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-99999") is True

    def test_single_digit_suffix(self):
        entry = {"id": "F-R7-1", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-1") is True

    def test_different_letter_prefix(self):
        entry = {"id": "F-X9-100", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-X9-100") is True


class TestMatchByCanonicalIdNoMatch:
    """Cases where the canonical ID is NOT present."""

    def test_different_id_returns_false(self):
        entry = {"id": "F-R7-999", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_empty_entry_returns_false(self):
        assert match_by_canonical_id({}, "F-R7-478") is False

    def test_unrelated_fields_returns_false(self):
        entry = {"status": "active", "priority": 3, "owner": "team"}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_none_field_values_returns_false(self):
        entry = {"id": None, "title": None, "description": None}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_empty_string_values_returns_false(self):
        entry = {"id": "", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_prefix_only_match_returns_false(self):
        # F-R7-47 should NOT match F-R7-478 (word boundary enforced)
        entry = {"id": "F-R7-47", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_similar_id_no_match(self):
        # F-R7-4789 should NOT match F-R7-478
        entry = {"id": "F-R7-4789", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is False


class TestMatchByCanonicalIdErrorPath:
    """Invalid inputs must raise ValueError."""

    def test_non_dict_entry_list_raises(self):
        with pytest.raises(ValueError, match="feature_entry must be a dict"):
            match_by_canonical_id(["F-R7-478"], "F-R7-478")  # type: ignore[arg-type]

    def test_non_dict_entry_string_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id("F-R7-478", "F-R7-478")  # type: ignore[arg-type]

    def test_non_dict_entry_none_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id(None, "F-R7-478")  # type: ignore[arg-type]

    def test_non_dict_entry_int_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id(42, "F-R7-478")  # type: ignore[arg-type]

    def test_empty_canonical_id_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            match_by_canonical_id({"id": "F-R7-478"}, "")

    def test_blank_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "   ")

    def test_none_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, None)  # type: ignore[arg-type]

    def test_int_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, 478)  # type: ignore[arg-type]

    def test_digits_only_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "478")

    def test_letters_only_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "FEATUREID")
