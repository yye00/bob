"""Tests for bob.auditor.carry_forward_matcher.

Covers match_by_canonical_id and resolve_feature_reference — the two public
functions required by AC for feature 18b825b3.
"""

from __future__ import annotations

import pytest

from bob.auditor.carry_forward_matcher import (
    match_by_canonical_id,
    resolve_feature_reference,
)


class TestMatchByCanonicalId:
    """Tests for match_by_canonical_id."""

    def test_exact_id_field_match(self):
        entry = {"id": "F-R7-478", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_title_field_match(self):
        entry = {"id": "sidecar-alias", "title": "Implement F-R7-478 carry", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_description_field_match(self):
        entry = {"id": "other", "title": "", "description": "See F-R7-478 for details"}
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_no_match_returns_false(self):
        entry = {"id": "F-R7-999", "title": "unrelated", "description": "nothing here"}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_empty_entry_returns_false(self):
        assert match_by_canonical_id({}, "F-R7-478") is False

    def test_no_partial_match(self):
        # F-R7-47 must not match inside F-R7-478
        entry = {"id": "F-R7-478", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-47") is False

    def test_none_field_values_returns_false(self):
        entry = {"id": None, "title": None, "description": None}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_non_dict_entry_raises(self):
        with pytest.raises(ValueError, match="feature_entry must be a dict"):
            match_by_canonical_id(["F-R7-478"], "F-R7-478")

    def test_none_entry_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id(None, "F-R7-478")

    def test_empty_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "")

    def test_blank_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "   ")

    def test_none_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, None)

    def test_digits_only_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "478")

    def test_letters_only_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "FEATUREID")

    def test_sidecar_rename_still_detected_via_title(self):
        # Simulates sidecar rename: 'id' no longer matches but title still has the token
        entry = {
            "id": "bob27-renamed-sidecar",
            "title": "[F-R7-478] permanent carry-forward feature",
            "description": "carry-forward per F-R7-553",
        }
        assert match_by_canonical_id(entry, "F-R7-478") is True
        assert match_by_canonical_id(entry, "F-R7-553") is True

    def test_shortname_alias_detected_via_description(self):
        entry = {
            "id": "infra-recovery",
            "title": "Infrastructure recovery",
            "description": "Implements F-R7-479 carry-forward protection.",
        }
        assert match_by_canonical_id(entry, "F-R7-479") is True


class TestResolveFeatureReference:
    """Tests for resolve_feature_reference."""

    def test_canonical_id_passthrough(self):
        assert resolve_feature_reference("F-R7-478") == "F-R7-478"

    def test_extracts_canonical_from_alias_string(self):
        assert resolve_feature_reference("my-sidecar (F-R7-478)") == "F-R7-478"

    def test_extracts_first_canonical_from_multiple(self):
        result = resolve_feature_reference("F-R7-478 and F-R7-479")
        assert result == "F-R7-478"

    def test_bare_shortname_returns_stripped(self):
        # No canonical token — return stripped original
        assert resolve_feature_reference("  infra-recovery  ") == "infra-recovery"

    def test_non_string_raises(self):
        with pytest.raises(ValueError):
            resolve_feature_reference(None)

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            resolve_feature_reference("")

    def test_canonical_embedded_in_longer_text(self):
        result = resolve_feature_reference(
            "Feature: [F-R7-553] slopsquatting protection (permanent carry)"
        )
        assert result == "F-R7-553"
