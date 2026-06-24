"""Tests for auditor.match_carry_forward_by_canonical_id (F-R7-554).

Verifies that carry-forward detection uses regex-based canonical ID matching
rather than exact-string equality, so renamed sidecars and shortname aliases
are correctly detected rather than silently dropped.
"""

from __future__ import annotations

import pytest

from auditor import canonical_id_matcher, match_carry_forward_by_canonical_id


class TestMatchCarryForwardByCanonicalId:
    """Core matching tests for match_carry_forward_by_canonical_id."""

    def test_exact_id_match_in_id_field(self):
        entry = {"id": "F-R7-478", "title": "Some feature", "description": ""}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-478") is True

    def test_canonical_id_in_title_field(self):
        entry = {"id": "bob26-renamed", "title": "[F-R7-478] carry feature", "description": ""}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-478") is True

    def test_canonical_id_in_description_field(self):
        entry = {
            "id": "some-sidecar-alias",
            "title": "Carry feature",
            "description": "Implements requirement F-R7-478 for carry-forward.",
        }
        assert match_carry_forward_by_canonical_id(entry, "F-R7-478") is True

    def test_sidecar_rename_still_detected_via_title(self):
        # Simulates renamed sidecar: id changed but title still contains token
        entry = {"id": "bob27-sidecar", "title": "F-R7-554 sidecar module", "description": ""}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-554") is True

    def test_shortname_alias_detected_via_description(self):
        # id is a shortname alias; token appears only in description
        entry = {"id": "perm-carry-check", "title": "Checker", "description": "Required by F-R7-478."}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-478") is True

    def test_token_not_present_returns_false(self):
        entry = {"id": "F-R7-479", "title": "Other feature", "description": ""}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-478") is False

    def test_word_boundary_no_partial_match(self):
        # F-R7-47 must NOT match inside F-R7-478
        entry = {"id": "F-R7-478", "title": "feature", "description": ""}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-47") is False

    def test_word_boundary_prefix_no_match(self):
        # XF-R7-478 must NOT match for F-R7-478
        entry = {"id": "XF-R7-478", "title": "", "description": ""}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-478") is False

    def test_empty_entry_returns_false(self):
        assert match_carry_forward_by_canonical_id({}, "F-R7-478") is False

    def test_entry_with_none_fields_returns_false(self):
        entry = {"id": None, "title": None, "description": None}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-478") is False

    def test_entry_with_unrelated_keys_returns_false(self):
        entry = {"status": "active", "owner": "team", "priority": 1}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-478") is False

    def test_minimum_canonical_id(self):
        entry = {"id": "F-R7-1", "title": "", "description": ""}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-1") is True

    def test_large_numeric_suffix(self):
        entry = {"id": "F-R7-99999", "title": "", "description": ""}
        assert match_carry_forward_by_canonical_id(entry, "F-R7-99999") is True


class TestMatchCarryForwardByCanonicalIdErrors:
    """Error-path tests — invalid input must raise ValueError."""

    def test_non_dict_entry_raises_valueerror(self):
        with pytest.raises(ValueError, match="feature_entry must be a dict"):
            match_carry_forward_by_canonical_id(["F-R7-478"], "F-R7-478")  # type: ignore[arg-type]

    def test_none_entry_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_carry_forward_by_canonical_id(None, "F-R7-478")  # type: ignore[arg-type]

    def test_empty_canonical_id_raises_valueerror(self):
        with pytest.raises(ValueError, match="non-empty string"):
            match_carry_forward_by_canonical_id({"id": "F-R7-478"}, "")

    def test_blank_canonical_id_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_carry_forward_by_canonical_id({"id": "F-R7-478"}, "   ")

    def test_none_canonical_id_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_carry_forward_by_canonical_id({"id": "F-R7-478"}, None)  # type: ignore[arg-type]

    def test_digits_only_canonical_id_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_carry_forward_by_canonical_id({"id": "F-R7-478"}, "478")

    def test_letters_only_canonical_id_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_carry_forward_by_canonical_id({"id": "F-R7-478"}, "FEATUREID")


class TestAuditorCanonicalIdMatcherIntegration:
    """Integration: auditor.canonical_id_matcher module is accessible."""

    def test_canonical_id_matcher_module_is_importable(self):
        assert canonical_id_matcher is not None

    def test_canonical_id_matcher_has_match_by_canonical_id(self):
        assert hasattr(canonical_id_matcher, "match_by_canonical_id")
        assert callable(canonical_id_matcher.match_by_canonical_id)

    def test_canonical_id_matcher_match_by_canonical_id_works(self):
        entry = {"id": "F-R7-478", "title": "", "description": ""}
        result = canonical_id_matcher.match_by_canonical_id(entry, "F-R7-478")
        assert result is True

    def test_carry_forward_matcher_and_canonical_id_matcher_agree(self):
        # Both functions should return the same result for valid inputs
        entry = {"id": "F-R7-478", "title": "Some feature", "description": ""}
        canonical_id = "F-R7-478"
        assert match_carry_forward_by_canonical_id(entry, canonical_id) == \
               canonical_id_matcher.match_by_canonical_id(entry, canonical_id)

    def test_both_functions_agree_on_no_match(self):
        entry = {"id": "F-R7-479", "title": "Other", "description": ""}
        canonical_id = "F-R7-478"
        assert match_carry_forward_by_canonical_id(entry, canonical_id) == \
               canonical_id_matcher.match_by_canonical_id(entry, canonical_id)
