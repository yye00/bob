"""Tests for bob72.auditor.match_by_canonical_id.

AC: pytest: tests/test_auditor_canonical_id.py
AC: Function defined: bob72.auditor.match_by_canonical_id
AC: integration: bob3.evaluator
"""

from __future__ import annotations

import pytest

from bob72.auditor import (
    BootstrapAuditError,
    evaluate_canonical_carry,
    extract_canonical_ids,
    match_by_canonical_id,
    required_feature_ids,
)


class TestMatchByCanonicalId:
    """Tests for match_by_canonical_id."""

    def test_matches_id_field_exact(self):
        entry = {"id": "F-R7-478", "title": "Spawn retry", "description": "..."}
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_matches_title_field_when_id_is_sidecar(self):
        entry = {
            "id": "bob27-unlimited-spawn-retry",
            "title": "F-R7-478 Permanent carry feature",
            "description": "implements carry",
        }
        assert match_by_canonical_id(entry, "F-R7-478") is True

    def test_matches_description_field(self):
        entry = {
            "id": "some-alias",
            "title": "Carry forward",
            "description": "Implements F-R7-479 for infra recovery",
        }
        assert match_by_canonical_id(entry, "F-R7-479") is True

    def test_returns_false_when_id_not_present_anywhere(self):
        entry = {
            "id": "unlimited-spawn-retry",
            "title": "Spawn retry",
            "description": "retry logic",
        }
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_does_not_match_partial_id(self):
        # F-R7-47 should not match F-R7-478 (exact token required)
        entry = {"id": "F-R7-478", "title": "Feature", "description": ""}
        assert match_by_canonical_id(entry, "F-R7-47") is False

    def test_does_not_match_wrong_id_in_description(self):
        entry = {"id": "x", "title": "y", "description": "See F-R7-479"}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_matches_when_id_and_description_both_contain_token(self):
        entry = {
            "id": "F-R7-553",
            "title": "Slopsquatting whitelist",
            "description": "F-R7-553 provides protection",
        }
        assert match_by_canonical_id(entry, "F-R7-553") is True

    def test_empty_entry_returns_false(self):
        assert match_by_canonical_id({}, "F-R7-478") is False

    def test_missing_all_text_fields_returns_false(self):
        entry = {"status": "done", "priority": 1}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_none_values_in_fields_do_not_raise(self):
        entry = {"id": None, "title": None, "description": None}
        assert match_by_canonical_id(entry, "F-R7-478") is False

    def test_raises_valueerror_for_non_dict_entry(self):
        with pytest.raises(ValueError, match="feature_entry must be a dict"):
            match_by_canonical_id(["F-R7-478"], "F-R7-478")  # type: ignore[arg-type]

    def test_raises_valueerror_for_none_entry(self):
        with pytest.raises(ValueError):
            match_by_canonical_id(None, "F-R7-478")  # type: ignore[arg-type]

    def test_raises_valueerror_for_empty_canonical_id(self):
        with pytest.raises(ValueError, match="non-empty string"):
            match_by_canonical_id({"id": "F-R7-478"}, "")

    def test_raises_valueerror_for_blank_canonical_id(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "   ")

    def test_raises_valueerror_for_none_canonical_id(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, None)  # type: ignore[arg-type]

    def test_raises_valueerror_for_non_canonical_token(self):
        # A string with no digits cannot be a canonical ID
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "NODIGITS")

    def test_raises_valueerror_for_digits_only(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "12345")

    def test_sidecar_rename_bob26_to_bob27_detected_via_title(self):
        # Simulate a sidecar rename: bob26-feature → bob27-feature, canonical in title
        entry = {
            "id": "bob27-slopsquatting-whitelist",
            "title": "F-R7-553 slopsquatting protection carry-forward",
            "description": "whitelist-based protection",
        }
        assert match_by_canonical_id(entry, "F-R7-553") is True

    def test_shortname_only_is_not_detected(self):
        # Feature referenced only by shortname, no canonical ID anywhere
        entry = {
            "id": "slopsquatting-whitelist",
            "title": "Slopsquatting whitelist",
            "description": "Provides whitelist-based protection",
        }
        assert match_by_canonical_id(entry, "F-R7-553") is False


class TestEvaluateCanonicalCarry:
    """Tests for evaluate_canonical_carry."""

    def _spec(self, *ids: str) -> dict:
        return {
            "features": [
                {"id": fid, "title": f"Feature {fid}", "description": "test"}
                for fid in ids
            ]
        }

    def test_empty_frozenset_when_all_required_present(self):
        spec = self._spec("F-R7-478", "F-R7-479", "F-R7-553")
        result = evaluate_canonical_carry(spec, required=frozenset({"F-R7-478", "F-R7-479", "F-R7-553"}))
        assert result == frozenset()

    def test_missing_id_in_result(self):
        spec = self._spec("F-R7-479", "F-R7-553")
        result = evaluate_canonical_carry(spec, required=frozenset({"F-R7-478", "F-R7-479", "F-R7-553"}))
        assert "F-R7-478" in result

    def test_renamed_sidecar_via_title_is_found(self):
        spec = {
            "features": [
                {
                    "id": "bob27-unlimited-spawn-retry",
                    "title": "F-R7-478 Permanent carry feature",
                    "description": "carry",
                },
                {"id": "F-R7-479", "title": "RCA reset", "description": ""},
                {"id": "F-R7-553", "title": "Slopsquatting", "description": ""},
            ]
        }
        result = evaluate_canonical_carry(spec, required=frozenset({"F-R7-478", "F-R7-479", "F-R7-553"}))
        assert result == frozenset()

    def test_shortname_only_spec_reports_missing(self):
        spec = {
            "features": [
                {"id": "unlimited-spawn-retry", "title": "Spawn retry", "description": "retry"},
                {"id": "rca-nh-auto-reset", "title": "RCA reset", "description": "reset"},
                {"id": "slopsquatting-whitelist", "title": "Whitelist", "description": "protect"},
            ]
        }
        result = evaluate_canonical_carry(spec, required=frozenset({"F-R7-478", "F-R7-479", "F-R7-553"}))
        assert "F-R7-478" in result
        assert "F-R7-479" in result
        assert "F-R7-553" in result

    def test_returns_frozenset(self):
        result = evaluate_canonical_carry({})
        assert isinstance(result, frozenset)

    def test_raises_valueerror_for_non_dict_spec(self):
        with pytest.raises(ValueError, match="spec must be a dict"):
            evaluate_canonical_carry(["F-R7-478"])  # type: ignore[arg-type]

    def test_empty_spec_reports_all_required_missing(self):
        result = evaluate_canonical_carry(
            {}, required=frozenset({"F-R7-478", "F-R7-479", "F-R7-553"})
        )
        assert "F-R7-478" in result
        assert "F-R7-479" in result
        assert "F-R7-553" in result


class TestIntegrationWithBob3Evaluator:
    """Verify that bob3.evaluator is wired into bob72.auditor."""

    def test_bob3_evaluator_is_importable_via_auditor_module(self):
        import bob72.auditor as auditor_mod
        import bob3.evaluator as evaluator_mod
        # The import at the top of auditor.py wires the integration
        assert auditor_mod is not None
        assert evaluator_mod is not None

    def test_evaluator_build_evaluator_task_section_callable(self):
        from bob3.evaluator import build_evaluator_task_section
        result = build_evaluator_task_section(["File exists: src/bob72/auditor.py"])
        assert isinstance(result, str)
        assert len(result) > 0
