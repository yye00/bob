"""Boundary tests for bob72.auditor.match_by_canonical_id.

AC: pytest: tests/test_permanent_forward_carry_auditor_must_match_by_f_r7_boundary.py
   — empty, zero, or minimum input returns a well-defined result rather than raising
     (boundary case)
"""

from __future__ import annotations

from bob72.auditor import evaluate_canonical_carry, match_by_canonical_id


class TestMatchByCanonicalIdBoundary:
    """Boundary / edge-case inputs must return well-defined results, not raise."""

    def test_empty_feature_entry_returns_false(self):
        # Empty dict — no fields to scan — must return False, not raise
        result = match_by_canonical_id({}, "F-R7-478")
        assert result is False

    def test_entry_with_only_unrelated_keys_returns_false(self):
        entry = {"status": "active", "priority": 3, "owner": "team-alpha"}
        result = match_by_canonical_id(entry, "F-R7-478")
        assert result is False

    def test_entry_with_none_values_returns_false(self):
        entry = {"id": None, "title": None, "description": None}
        result = match_by_canonical_id(entry, "F-R7-478")
        assert result is False

    def test_entry_with_empty_string_values_returns_false(self):
        entry = {"id": "", "title": "", "description": ""}
        result = match_by_canonical_id(entry, "F-R7-1")
        assert result is False

    def test_minimum_canonical_id_single_digit(self):
        # F-R7-1 is the smallest plausible canonical token
        entry = {"id": "F-R7-1", "title": "Minimal", "description": ""}
        result = match_by_canonical_id(entry, "F-R7-1")
        assert result is True

    def test_empty_spec_evaluate_returns_frozenset(self):
        result = evaluate_canonical_carry({}, required=frozenset())
        assert isinstance(result, frozenset)
        assert result == frozenset()

    def test_empty_required_set_returns_empty_missing(self):
        # No required IDs → nothing is missing
        spec = {"features": [{"id": "something", "title": "", "description": ""}]}
        result = evaluate_canonical_carry(spec, required=frozenset())
        assert result == frozenset()

    def test_spec_with_no_features_key_evaluate_returns_all_required(self):
        spec = {"name": "test-project"}
        required = frozenset({"F-R7-478"})
        result = evaluate_canonical_carry(spec, required=required)
        assert "F-R7-478" in result

    def test_spec_with_empty_features_list_returns_all_required(self):
        spec = {"features": []}
        required = frozenset({"F-R7-478", "F-R7-479"})
        result = evaluate_canonical_carry(spec, required=required)
        assert required == result

    def test_single_feature_single_required_match(self):
        # Minimum non-trivial case: 1 feature, 1 required, exact match
        entry = {"id": "F-R7-478", "title": "", "description": ""}
        result = match_by_canonical_id(entry, "F-R7-478")
        assert result is True

    def test_evaluate_single_feature_single_required_match(self):
        spec = {"features": [{"id": "F-R7-478", "title": "", "description": ""}]}
        result = evaluate_canonical_carry(spec, required=frozenset({"F-R7-478"}))
        assert result == frozenset()

    def test_large_canonical_id_number(self):
        # Very large numeric suffix — must still match
        entry = {"id": "F-R7-99999", "title": "", "description": ""}
        result = match_by_canonical_id(entry, "F-R7-99999")
        assert result is True

    def test_id_token_embedded_in_longer_string_in_title(self):
        entry = {
            "id": "unrelated",
            "title": "[F-R7-478] carry-forward feature (permanent)",
            "description": "",
        }
        result = match_by_canonical_id(entry, "F-R7-478")
        assert result is True
