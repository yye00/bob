"""Tests for bob3.carry_forward_auditor.match_by_canonical_id.

Verifies that the module re-exports the canonical-ID matcher from bob72.auditor
and that the function correctly detects F-R7-NNN tokens in feature entries even
when sidecar aliases or shortnames are used in the id field.
"""

from __future__ import annotations

import pytest

from bob3.carry_forward_auditor import (
    evaluate_canonical_carry,
    match_by_canonical_id,
)


class TestMatchByCanonicalIdImportable:
    """match_by_canonical_id must be importable from bob3.carry_forward_auditor."""

    def test_function_is_callable(self):
        assert callable(match_by_canonical_id)

    def test_evaluate_canonical_carry_is_callable(self):
        assert callable(evaluate_canonical_carry)


class TestMatchByCanonicalIdCorrectness:
    """Core matching behaviour: regex not exact-string so sidecar renames are caught."""

    def test_exact_id_match(self):
        entry = {"id": "F-R7-478", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_sidecar_alias_in_id_with_canonical_in_description(self):
        # Sidecar renamed: id holds alias, description mentions canonical ID
        entry = {
            "id": "infra-recovery-slop",
            "title": "Slopsquatting protection",
            "description": "See F-R7-478 for full specification.",
        }
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_canonical_in_title_only(self):
        entry = {
            "id": "infra-protection",
            "title": "[F-R7-479] infra-recovery carry-forward",
            "description": "",
        }
        assert match_by_canonical_id(entry, "F-R7-479") is True

    def test_unrelated_feature_returns_false(self):
        entry = {"id": "F-R7-999", "title": "Other feature", "description": "Unrelated."}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_prefix_not_matched(self):
        # F-R7-47 must NOT match inside F-R7-478 (word-boundary check)
        entry = {"id": "F-R7-478", "title": "", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-47") is False

    def test_non_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            match_by_canonical_id(["F-R7-478"], "F-R7-478")  # type: ignore[arg-type]

    def test_empty_canonical_id_raises_value_error(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "")

    def test_none_entry_raises_value_error(self):
        with pytest.raises(ValueError):
            match_by_canonical_id(None, "F-R7-478")  # type: ignore[arg-type]


class TestEvaluateCanonicalCarry:
    """evaluate_canonical_carry must return missing IDs not present in spec."""

    def test_all_present_returns_empty_frozenset(self):
        spec = {
            "features": [
                {"id": "F-R7-478", "title": "", "description": ""},
                {"id": "F-R7-479", "title": "", "description": ""},
                {"id": "F-R7-553", "title": "", "description": ""},
            ]
        }
        result = evaluate_canonical_carry(spec, required=frozenset({"F-R7-478", "F-R7-479", "F-R7-553"}))
        assert result == frozenset()

    def test_missing_returns_in_frozenset(self):
        spec = {"features": [{"id": "F-R7-478", "title": "", "description": ""}]}
        result = evaluate_canonical_carry(spec, required=frozenset({"F-R7-478", "F-R7-479"}))
        assert "F-R7-479" in result
        assert "F-R7-478" not in result

    def test_empty_spec_returns_all_required(self):
        required = frozenset({"F-R7-478", "F-R7-479"})
        result = evaluate_canonical_carry({}, required=required)
        assert result == required

    def test_non_dict_spec_raises_value_error(self):
        with pytest.raises(ValueError):
            evaluate_canonical_carry(None)  # type: ignore[arg-type]

    def test_canonical_id_in_description_counts_as_present(self):
        # Feature carries the ID in description (sidecar alias in id field)
        spec = {
            "features": [
                {
                    "id": "slop-protection",
                    "title": "Slopsquatting protection",
                    "description": "Implements F-R7-478 requirements.",
                }
            ]
        }
        result = evaluate_canonical_carry(spec, required=frozenset({"F-R7-478"}))
        assert result == frozenset()
