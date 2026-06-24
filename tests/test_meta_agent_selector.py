"""Tests for bob.meta_agent_selector.

Covers select_spec_sections and run_focused_extraction for feature
08e256ba-bf12-40ec-9117-c2da7ccbe9b2 (Self-Discover meta-agent for
per-feature spec-section selection).
"""

from __future__ import annotations

import pytest

from bob.meta_agent_selector import (
    run_focused_extraction,
    select_spec_sections,
)
from bob.spec_quality.section_selector import module_set


VALID_LABELS = {"REQUIRED", "OPTIONAL", "SKIP"}


class TestSelectSpecSections:
    def test_returns_dict(self):
        result = select_spec_sections(
            feature_id="test-001",
            name="Add auth middleware",
            description="Adds authentication and security token validation.",
            acceptance_criteria=["Function defined: bob.foo.bar"],
        )
        assert isinstance(result, dict)

    def test_all_module_set_keys_present(self):
        result = select_spec_sections(
            feature_id="test-002",
            name="Some feature",
            description="Some description.",
            acceptance_criteria=[],
        )
        assert set(result.keys()) == set(module_set())

    def test_values_are_valid_labels(self):
        result = select_spec_sections(
            feature_id="test-003",
            name="Some feature",
            description="Some description.",
            acceptance_criteria=[],
        )
        for section, value in result.items():
            assert value in VALID_LABELS, (
                f"section {section!r} has invalid value {value!r}"
            )

    def test_functional_always_required(self):
        result = select_spec_sections(
            feature_id="test-004",
            name="Any feature",
            description="Any description.",
            acceptance_criteria=[],
        )
        assert result["functional"] == "REQUIRED"

    def test_security_required_when_security_keywords_present(self):
        result = select_spec_sections(
            feature_id="test-005",
            name="Token auth and security layer",
            description="Validates auth tokens and security credentials.",
            acceptance_criteria=["Validate security token on each request"],
        )
        assert result["security"] == "REQUIRED"

    def test_empty_feature_id_does_not_raise(self):
        result = select_spec_sections(
            feature_id="",
            name="Feature",
            description="Desc.",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)

    def test_empty_name_does_not_raise(self):
        result = select_spec_sections(
            feature_id="test-007",
            name="",
            description="Desc.",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)

    def test_none_feature_id_raises_value_error(self):
        with pytest.raises(ValueError, match="feature_id"):
            select_spec_sections(
                feature_id=None,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_none_name_raises_value_error(self):
        with pytest.raises(ValueError, match="name"):
            select_spec_sections(
                feature_id="test-009",
                name=None,  # type: ignore[arg-type]
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_none_description_raises_value_error(self):
        with pytest.raises(ValueError, match="description"):
            select_spec_sections(
                feature_id="test-010",
                name="Feature",
                description=None,  # type: ignore[arg-type]
                acceptance_criteria=[],
            )

    def test_non_list_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="test-011",
                name="Feature",
                description="Desc.",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_non_string_ac_item_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="test-012",
                name="Feature",
                description="Desc.",
                acceptance_criteria=["Valid AC", 42],  # type: ignore[list-item]
            )

    def test_trivial_feature_skips_nfr_sections(self):
        result = select_spec_sections(
            feature_id="test-013",
            name="Rename helper utility",
            description="Internal cleanup refactor of a helper alias.",
            acceptance_criteria=[],
        )
        # Trivial features (rename/refactor/utility) should skip NFR sections
        assert result["functional"] == "REQUIRED"


class TestRunFocusedExtraction:
    def test_returns_dict(self):
        result = run_focused_extraction(
            feature_id="rfe-001",
            name="Some feature",
            description="Some description.",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = run_focused_extraction(
            feature_id="rfe-002",
            name="Some feature",
            description="Some description.",
            acceptance_criteria=["File exists: src/foo.py"],
        )
        assert "feature_id" in result
        assert "section_map" in result
        assert "filtered_acs" in result
        assert "skipped_sections" in result
        assert "active_sections" in result

    def test_feature_id_echoed(self):
        result = run_focused_extraction(
            feature_id="rfe-003",
            name="Feature",
            description="Desc.",
            acceptance_criteria=[],
        )
        assert result["feature_id"] == "rfe-003"

    def test_filtered_acs_passthrough(self):
        acs = ["File exists: src/foo.py", "Function defined: bob.foo.bar"]
        result = run_focused_extraction(
            feature_id="rfe-004",
            name="Feature",
            description="Desc.",
            acceptance_criteria=acs,
        )
        assert result["filtered_acs"] == acs

    def test_empty_acs_filtered_acs_is_empty_list(self):
        result = run_focused_extraction(
            feature_id="rfe-005",
            name="Feature",
            description="Desc.",
            acceptance_criteria=[],
        )
        assert result["filtered_acs"] == []

    def test_section_map_has_valid_values(self):
        result = run_focused_extraction(
            feature_id="rfe-006",
            name="Feature",
            description="Desc.",
            acceptance_criteria=[],
        )
        for section, value in result["section_map"].items():
            assert value in VALID_LABELS, (
                f"section {section!r} has invalid value {value!r}"
            )

    def test_skipped_sections_is_list(self):
        result = run_focused_extraction(
            feature_id="rfe-007",
            name="Feature",
            description="Desc.",
            acceptance_criteria=[],
        )
        assert isinstance(result["skipped_sections"], list)

    def test_active_sections_is_list(self):
        result = run_focused_extraction(
            feature_id="rfe-008",
            name="Feature",
            description="Desc.",
            acceptance_criteria=[],
        )
        assert isinstance(result["active_sections"], list)

    def test_active_plus_skipped_equals_module_set(self):
        result = run_focused_extraction(
            feature_id="rfe-009",
            name="Feature",
            description="Desc.",
            acceptance_criteria=[],
        )
        all_sections = set(result["active_sections"]) | set(result["skipped_sections"])
        assert all_sections == set(module_set())

    def test_no_overlap_active_and_skipped(self):
        result = run_focused_extraction(
            feature_id="rfe-010",
            name="Feature",
            description="Desc.",
            acceptance_criteria=[],
        )
        active = set(result["active_sections"])
        skipped = set(result["skipped_sections"])
        assert active.isdisjoint(skipped)

    def test_section_map_keys_match_module_set(self):
        result = run_focused_extraction(
            feature_id="rfe-011",
            name="Feature",
            description="Desc.",
            acceptance_criteria=[],
        )
        assert set(result["section_map"].keys()) == set(module_set())

    def test_none_feature_id_raises_value_error(self):
        with pytest.raises(ValueError, match="feature_id"):
            run_focused_extraction(
                feature_id=None,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_none_name_raises_value_error(self):
        with pytest.raises(ValueError, match="name"):
            run_focused_extraction(
                feature_id="rfe-013",
                name=None,  # type: ignore[arg-type]
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_none_description_raises_value_error(self):
        with pytest.raises(ValueError, match="description"):
            run_focused_extraction(
                feature_id="rfe-014",
                name="Feature",
                description=None,  # type: ignore[arg-type]
                acceptance_criteria=[],
            )

    def test_non_list_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            run_focused_extraction(
                feature_id="rfe-015",
                name="Feature",
                description="Desc.",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )
