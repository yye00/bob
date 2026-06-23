"""Boundary-case tests for permanent_forward_carry_auditor.audit_merged_spec.

Verifies that empty, zero, or minimum inputs return a well-defined result
(a frozenset of missing IDs) rather than raising an exception.
"""

from __future__ import annotations

import pytest

from bob3.permanent_forward_carry_auditor import audit_merged_spec, required_feature_ids


class TestAuditMergedSpecBoundary:
    """Boundary cases: minimum/empty/zero inputs return frozenset, not exceptions."""

    def test_empty_dict_returns_frozenset(self):
        result = audit_merged_spec({})
        assert isinstance(result, frozenset)

    def test_empty_dict_reports_all_required_missing(self):
        result = audit_merged_spec({})
        required = required_feature_ids()
        assert result == required

    def test_none_features_key_returns_frozenset(self):
        result = audit_merged_spec({"features": None})
        assert isinstance(result, frozenset)

    def test_empty_list_features_returns_frozenset(self):
        result = audit_merged_spec({"features": []})
        assert isinstance(result, frozenset)
        assert len(result) == len(required_feature_ids())

    def test_empty_dict_features_returns_frozenset(self):
        result = audit_merged_spec({"features": {}})
        assert isinstance(result, frozenset)

    def test_single_feature_missing_two_returns_frozenset(self):
        result = audit_merged_spec({"features": [{"id": "F-R7-478", "title": "t", "description": "d"}]})
        assert isinstance(result, frozenset)
        assert "F-R7-479" in result
        assert "F-R7-553" in result
        assert "F-R7-478" not in result

    def test_spec_with_only_non_feature_keys_returns_frozenset(self):
        result = audit_merged_spec({"name": "spec", "version": "1.0", "description": "x"})
        assert isinstance(result, frozenset)
        assert len(result) == len(required_feature_ids())

    def test_all_required_present_returns_empty_frozenset(self):
        spec = {
            "features": [
                {"id": "F-R7-478", "title": "Spawn retry"},
                {"id": "F-R7-479", "title": "RCA reset"},
                {"id": "F-R7-553", "title": "Slopsquatting"},
            ]
        }
        result = audit_merged_spec(spec)
        assert result == frozenset()

    def test_feature_with_no_id_field_does_not_raise(self):
        spec = {"features": [{"title": "No ID here", "description": "d"}]}
        result = audit_merged_spec(spec)
        assert isinstance(result, frozenset)

    def test_feature_with_none_id_does_not_raise(self):
        spec = {"features": [{"id": None, "title": "t"}]}
        result = audit_merged_spec(spec)
        assert isinstance(result, frozenset)
