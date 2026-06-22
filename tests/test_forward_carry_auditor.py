"""Tests for bob3.forward_carry_auditor.audit_forward_carry_by_canonical_id."""

from __future__ import annotations

import pytest

from bob3.forward_carry_auditor import audit_forward_carry_by_canonical_id


class TestAuditForwardCarryByCanonicalId:
    """Core correctness tests for the regex-based canonical ID auditor."""

    def test_empty_spec_returns_all_required(self):
        required = frozenset({"F-R7-478", "F-R7-479"})
        result = audit_forward_carry_by_canonical_id({}, required=required)
        assert result == required

    def test_spec_without_features_key_returns_all_required(self):
        spec = {"name": "test-project", "version": "1.0"}
        required = frozenset({"F-R7-478"})
        result = audit_forward_carry_by_canonical_id(spec, required=required)
        assert "F-R7-478" in result

    def test_exact_id_match(self):
        spec = {"features": [{"id": "F-R7-478", "title": "", "description": ""}]}
        result = audit_forward_carry_by_canonical_id(spec, required=frozenset({"F-R7-478"}))
        assert result == frozenset()

    def test_id_in_title_field_detected(self):
        spec = {
            "features": [
                {
                    "id": "renamed-sidecar",
                    "title": "Permanent carry [F-R7-478] slopsquatting protection",
                    "description": "",
                }
            ]
        }
        result = audit_forward_carry_by_canonical_id(spec, required=frozenset({"F-R7-478"}))
        assert result == frozenset()

    def test_id_in_description_field_detected(self):
        spec = {
            "features": [
                {
                    "id": "shortname-alias",
                    "title": "Some feature",
                    "description": "Implements F-R7-479 carry-forward requirement",
                }
            ]
        }
        result = audit_forward_carry_by_canonical_id(spec, required=frozenset({"F-R7-479"}))
        assert result == frozenset()

    def test_sidecar_rename_still_detected_via_description(self):
        # Simulates: sidecar renamed from bob26 to bob27, but description still
        # contains the canonical ID token — auditor must find it.
        spec = {
            "features": [
                {
                    "id": "bob27-slopsquatting-guard",
                    "title": "Slopsquatting guard",
                    "description": "Permanent carry of F-R7-478 (renamed from bob26)",
                }
            ]
        }
        result = audit_forward_carry_by_canonical_id(spec, required=frozenset({"F-R7-478"}))
        assert result == frozenset()

    def test_missing_feature_reported(self):
        spec = {
            "features": [
                {"id": "F-R7-999", "title": "Unrelated", "description": ""}
            ]
        }
        result = audit_forward_carry_by_canonical_id(spec, required=frozenset({"F-R7-478"}))
        assert "F-R7-478" in result

    def test_multiple_required_some_missing(self):
        spec = {
            "features": [
                {"id": "F-R7-478", "title": "", "description": ""},
                {"id": "other", "title": "", "description": ""},
            ]
        }
        required = frozenset({"F-R7-478", "F-R7-479", "F-R7-553"})
        result = audit_forward_carry_by_canonical_id(spec, required=required)
        assert "F-R7-478" not in result
        assert "F-R7-479" in result
        assert "F-R7-553" in result

    def test_all_required_present_returns_empty(self):
        spec = {
            "features": [
                {"id": "F-R7-478", "title": "Slopsquatting protection", "description": ""},
                {"id": "F-R7-479", "title": "Second guard", "description": ""},
            ]
        }
        required = frozenset({"F-R7-478", "F-R7-479"})
        result = audit_forward_carry_by_canonical_id(spec, required=required)
        assert result == frozenset()

    def test_empty_required_set_returns_empty_missing(self):
        spec = {"features": [{"id": "F-R7-100", "title": "", "description": ""}]}
        result = audit_forward_carry_by_canonical_id(spec, required=frozenset())
        assert result == frozenset()

    def test_dict_features_format_also_supported(self):
        spec = {
            "features": {
                "F-R7-478": {"title": "Slopsquatting", "description": ""},
            }
        }
        result = audit_forward_carry_by_canonical_id(spec, required=frozenset({"F-R7-478"}))
        assert result == frozenset()

    def test_returns_frozenset(self):
        result = audit_forward_carry_by_canonical_id({}, required=frozenset())
        assert isinstance(result, frozenset)

    def test_non_dict_spec_raises_valueerror(self):
        with pytest.raises(ValueError, match="spec must be a dict"):
            audit_forward_carry_by_canonical_id(["F-R7-478"])  # type: ignore[arg-type]

    def test_none_spec_raises_valueerror(self):
        with pytest.raises(ValueError):
            audit_forward_carry_by_canonical_id(None)  # type: ignore[arg-type]

    def test_raise_on_missing_raises_when_absent(self):
        spec = {"features": []}
        required = frozenset({"F-R7-478"})
        with pytest.raises(ValueError, match="F-R7-478"):
            audit_forward_carry_by_canonical_id(spec, required=required, raise_on_missing=True)

    def test_raise_on_missing_does_not_raise_when_present(self):
        spec = {"features": [{"id": "F-R7-478", "title": "", "description": ""}]}
        required = frozenset({"F-R7-478"})
        result = audit_forward_carry_by_canonical_id(
            spec, required=required, raise_on_missing=True
        )
        assert result == frozenset()

    def test_shortname_without_canonical_id_not_matched(self):
        # A feature with only a shortname in the id field and no canonical token
        # anywhere must NOT be counted as matching F-R7-478.
        spec = {
            "features": [
                {
                    "id": "slopsquatting-guard",
                    "title": "Slopsquatting guard",
                    "description": "Prevents pip install confusion attacks",
                }
            ]
        }
        result = audit_forward_carry_by_canonical_id(spec, required=frozenset({"F-R7-478"}))
        assert "F-R7-478" in result

    def test_partial_id_not_matched(self):
        # F-R7-47 must NOT match F-R7-478 (word-boundary anchoring)
        spec = {
            "features": [
                {"id": "F-R7-47", "title": "", "description": ""}
            ]
        }
        result = audit_forward_carry_by_canonical_id(spec, required=frozenset({"F-R7-478"}))
        assert "F-R7-478" in result
