"""Tests for bob.audit_permanent_forward_carry module.

Verifies that match_by_canonical_id and resolve_feature_reference are
correctly exported and behave as specified for the F-R7-554 fix.
"""

from __future__ import annotations

import pytest

import bob.audit_permanent_forward_carry as auditor_module
from bob.audit_permanent_forward_carry import match_by_canonical_id, resolve_feature_reference


class TestModuleExports:
    def test_match_by_canonical_id_exported(self):
        assert hasattr(auditor_module, "match_by_canonical_id")
        assert callable(auditor_module.match_by_canonical_id)

    def test_resolve_feature_reference_exported(self):
        assert hasattr(auditor_module, "resolve_feature_reference")
        assert callable(auditor_module.resolve_feature_reference)

    def test_all_contains_expected_names(self):
        assert "match_by_canonical_id" in auditor_module.__all__
        assert "resolve_feature_reference" in auditor_module.__all__


class TestMatchByCanonicalId:
    def test_exact_id_match(self):
        entry = {"id": "F-R7-478", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_token_in_title(self):
        entry = {"id": "bob27-sidecar", "title": "F-R7-478 carry feature", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_token_in_description(self):
        entry = {"id": "some-alias", "title": "carry", "description": "Implements F-R7-479"}
        assert match_by_canonical_id(entry, "F-R7-479") is True

    def test_no_match_returns_false(self):
        entry = {"id": "unlimited-spawn", "title": "spawn retry", "description": "carry feature"}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_partial_id_no_false_positive(self):
        # F-R7-47 should not match F-R7-478
        entry = {"id": "F-R7-478", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-47") is False

    def test_empty_dict_returns_false(self):
        assert match_by_canonical_id({}, "F-R7-478") is False

    def test_none_field_values_return_false(self):
        entry = {"id": None, "title": None, "description": None}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_non_dict_entry_raises(self):
        with pytest.raises(ValueError, match="feature_entry must be a dict"):
            match_by_canonical_id(["F-R7-478"], "F-R7-478")

    def test_empty_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "")

    def test_blank_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "   ")

    def test_none_canonical_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, None)  # type: ignore[arg-type]

    def test_digits_only_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "478")

    def test_letters_only_id_raises(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "FEATUREID")


class TestResolveFeatureReference:
    def test_canonical_id_passthrough(self):
        assert resolve_feature_reference("F-R7-478") == "F-R7-478"

    def test_extracts_canonical_id_from_alias(self):
        result = resolve_feature_reference("my-sidecar (F-R7-478)")
        assert result == "F-R7-478"

    def test_returns_stripped_shortname_when_no_canonical(self):
        result = resolve_feature_reference("  unlimited-spawn-retry  ")
        assert result == "unlimited-spawn-retry"

    def test_extracts_first_canonical_id_when_multiple(self):
        result = resolve_feature_reference("F-R7-478 and F-R7-479")
        assert result == "F-R7-478"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            resolve_feature_reference("")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            resolve_feature_reference(None)  # type: ignore[arg-type]

    def test_non_string_raises(self):
        with pytest.raises(ValueError):
            resolve_feature_reference(478)  # type: ignore[arg-type]
