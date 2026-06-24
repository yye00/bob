"""Tests for canonical F-R7-NNN ID extraction and pattern matching.

Feature 9929e185: Permanent-forward-carry auditor MUST match by F-R7-NNN
canonical ID regex — sidecar rename or shortname drift silently drops features.

Covers:
- canonical_feature_id_pattern returns a compiled regex matching F-R7-\d+ exactly
- extract_canonical_ids walks spec dict and finds tokens in id/title/description
- Non-canonical strings (F-R6-100) NOT included in result set
- F-R7-478 detected when only in description prose
- audit_merged_spec passes when required IDs appear in any feature field
"""

from __future__ import annotations

import re

import pytest

from bob3.bootstrap.permanent_forward_carry_auditor import (
    audit_merged_spec,
    canonical_feature_id_pattern,
    extract_canonical_ids,
)


class TestCanonicalFeatureIdPattern:
    """Tests for canonical_feature_id_pattern()."""

    def test_returns_compiled_regex(self):
        pattern = canonical_feature_id_pattern()
        assert hasattr(pattern, "match") and hasattr(pattern, "findall")

    def test_matches_f_r7_pattern(self):
        pattern = canonical_feature_id_pattern()
        assert pattern.search("F-R7-478")
        assert pattern.search("F-R7-100")
        assert pattern.search("F-R7-9999")

    def test_does_not_match_f_r6(self):
        pattern = canonical_feature_id_pattern()
        assert not pattern.search("F-R6-100")

    def test_does_not_match_f_r8(self):
        pattern = canonical_feature_id_pattern()
        assert not pattern.search("F-R8-200")

    def test_does_not_match_partial_strings(self):
        pattern = canonical_feature_id_pattern()
        # Must match F-R7-NNN form, not just "R7"
        assert not pattern.search("R7-100")
        assert not pattern.search("FR7-100")

    def test_extracts_id_from_prose(self):
        pattern = canonical_feature_id_pattern()
        text = "This feature implements F-R7-478 for infra recovery"
        matches = pattern.findall(text)
        assert "F-R7-478" in matches

    def test_extracts_multiple_ids_from_prose(self):
        pattern = canonical_feature_id_pattern()
        text = "Depends on F-R7-478 and F-R7-479, relates to F-R7-553"
        matches = pattern.findall(text)
        assert "F-R7-478" in matches
        assert "F-R7-479" in matches
        assert "F-R7-553" in matches


class TestExtractCanonicalIds:
    """Tests for extract_canonical_ids()."""

    def test_finds_id_in_feature_id_field(self):
        spec = {
            "features": [
                {"id": "F-R7-478", "title": "Infra recovery", "description": "..."}
            ]
        }
        result = extract_canonical_ids(spec)
        assert "F-R7-478" in result

    def test_finds_id_in_title_field(self):
        spec = {
            "features": [
                {"id": "some-shortname", "title": "F-R7-479 RCA auto-reset", "description": "..."}
            ]
        }
        result = extract_canonical_ids(spec)
        assert "F-R7-479" in result

    def test_finds_id_in_description_prose(self):
        """AC: F-R7-478 detected when referenced only in description prose."""
        spec = {
            "features": [
                {
                    "id": "infra-recovery",
                    "title": "Infra recovery feature",
                    "description": "Implements the requirements from F-R7-478 for error handling",
                }
            ]
        }
        result = extract_canonical_ids(spec)
        assert "F-R7-478" in result

    def test_non_canonical_strings_not_in_result(self):
        """AC: non-canonical strings (e.g. 'F-R6-100') not in result set."""
        spec = {
            "features": [
                {
                    "id": "F-R6-100",
                    "title": "Old style feature F-R6-200",
                    "description": "References F-R6-300 for context",
                }
            ]
        }
        result = extract_canonical_ids(spec)
        assert "F-R6-100" not in result
        assert "F-R6-200" not in result
        assert "F-R6-300" not in result

    def test_returns_set(self):
        spec = {
            "features": [
                {"id": "F-R7-478", "title": "t", "description": "d"}
            ]
        }
        result = extract_canonical_ids(spec)
        assert isinstance(result, set)

    def test_empty_spec_returns_empty_set(self):
        result = extract_canonical_ids({})
        assert result == set()

    def test_no_features_key_returns_empty_set(self):
        result = extract_canonical_ids({"name": "project"})
        assert result == set()

    def test_finds_multiple_ids_across_features(self):
        spec = {
            "features": [
                {"id": "F-R7-478", "title": "Feature A", "description": "..."},
                {"id": "F-R7-479", "title": "Feature B", "description": "..."},
                {"id": "F-R7-553", "title": "Feature C", "description": "..."},
            ]
        }
        result = extract_canonical_ids(spec)
        assert "F-R7-478" in result
        assert "F-R7-479" in result
        assert "F-R7-553" in result

    def test_finds_id_only_in_description_not_in_id_field(self):
        """When the 'id' field is a shortname, description reference still found."""
        spec = {
            "features": [
                {
                    "id": "slopsquatting-whitelist",
                    "title": "Slopsquatting local-module whitelist",
                    "description": "Satisfies F-R7-553 requirements for import validation",
                }
            ]
        }
        result = extract_canonical_ids(spec)
        assert "F-R7-553" in result

    def test_dict_of_dicts_features_format(self):
        """Supports both list-of-dicts and dict-of-dicts spec formats."""
        spec = {
            "features": {
                "F-R7-478": {
                    "title": "Unlimited spawn retry",
                    "description": "Core infra recovery",
                },
                "shortname-feature": {
                    "id": "F-R7-479",
                    "title": "RCA NH auto-reset",
                    "description": "...",
                },
            }
        }
        result = extract_canonical_ids(spec)
        assert "F-R7-478" in result
        assert "F-R7-479" in result

    def test_ids_in_nested_description_prose(self):
        """Multiple IDs embedded in a single description string all extracted."""
        spec = {
            "features": [
                {
                    "id": "meta-feature",
                    "title": "Meta",
                    "description": (
                        "This aggregates F-R7-478, F-R7-479, and F-R7-553 "
                        "requirements into a single capability gate."
                    ),
                }
            ]
        }
        result = extract_canonical_ids(spec)
        assert "F-R7-478" in result
        assert "F-R7-479" in result
        assert "F-R7-553" in result

    def test_does_not_include_non_f_r7_ids_from_mixed_spec(self):
        """Mixed spec: only F-R7-NNN tokens are returned."""
        spec = {
            "features": [
                {
                    "id": "F-R7-478",
                    "title": "Feature with F-R6-999 mention",
                    "description": "Also mentions F-R8-001 but those don't count",
                }
            ]
        }
        result = extract_canonical_ids(spec)
        assert "F-R7-478" in result
        assert "F-R6-999" not in result
        assert "F-R8-001" not in result


class TestAuditMergedSpecWithRegex:
    """Integration tests: audit_merged_spec uses extract_canonical_ids for matching."""

    def test_passes_when_required_id_in_description_only(self):
        """AC: audit_merged_spec passes when required IDs appear in any feature field."""
        spec = {
            "features": [
                {
                    "id": "infra-recovery-shim",
                    "title": "Infra recovery shim",
                    "description": "Implements F-R7-478 for transient error handling",
                },
                {
                    "id": "rca-reset",
                    "title": "RCA reset",
                    "description": "Covers F-R7-479 reset logic",
                },
                {
                    "id": "whitelist",
                    "title": "Module whitelist for F-R7-553",
                    "description": "Local module import validation",
                },
            ]
        }
        missing = audit_merged_spec(spec)
        assert missing == frozenset(), f"Expected no missing, got: {missing}"

    def test_required_id_in_title_is_sufficient(self):
        spec = {
            "features": [
                {"id": "feat-a", "title": "F-R7-478 spawn retry", "description": "..."},
                {"id": "feat-b", "title": "F-R7-479 auto-reset", "description": "..."},
                {"id": "feat-c", "title": "F-R7-553 whitelist", "description": "..."},
            ]
        }
        missing = audit_merged_spec(spec)
        assert missing == frozenset()

    def test_still_reports_missing_when_id_absent_from_all_fields(self):
        spec = {
            "features": [
                {"id": "unrelated-1", "title": "Unrelated feature", "description": "No carry IDs here"},
                {"id": "F-R7-479", "title": "Has 479", "description": "..."},
                {"id": "F-R7-553", "title": "Has 553", "description": "..."},
            ]
        }
        missing = audit_merged_spec(spec)
        assert "F-R7-478" in missing

    def test_sidecar_renamed_but_id_in_description_detected(self):
        """Simulates sidecar rename: feature id changed but canonical ID still in description."""
        spec = {
            "features": [
                {
                    "id": "bob27-infra-recovery",  # was "bob26-infra-recovery"
                    "title": "Infra recovery carry-forward",
                    "description": "Permanent forward carry for F-R7-478 from bob26",
                },
                {
                    "id": "F-R7-479",
                    "title": "RCA reset",
                    "description": "...",
                },
                {
                    "id": "F-R7-553",
                    "title": "Slopsquatting whitelist",
                    "description": "...",
                },
            ]
        }
        missing = audit_merged_spec(spec)
        assert "F-R7-478" not in missing, "F-R7-478 should be detected via description prose"
