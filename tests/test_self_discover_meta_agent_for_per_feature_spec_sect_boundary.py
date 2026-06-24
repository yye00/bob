"""Boundary tests for bob.self_discover_meta_agent.

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising exceptions (boundary case coverage).
"""

from __future__ import annotations

import pytest

from bob.self_discover_meta_agent import (
    focused_extractor,
    select_spec_sections,
)
from bob.spec_quality.section_selector import module_set


class TestSelectSpecSectionsBoundary:
    def test_empty_name_returns_dict(self):
        result = select_spec_sections(
            feature_id="b-001",
            name="",
            description="Some description.",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == set(module_set())

    def test_empty_description_returns_dict(self):
        result = select_spec_sections(
            feature_id="b-002",
            name="Some feature",
            description="",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == set(module_set())

    def test_empty_acceptance_criteria_returns_dict(self):
        result = select_spec_sections(
            feature_id="b-003",
            name="Some feature",
            description="Some description.",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == set(module_set())

    def test_all_empty_inputs_returns_dict(self):
        result = select_spec_sections(
            feature_id="b-004",
            name="",
            description="",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == set(module_set())

    def test_all_empty_inputs_functional_is_required(self):
        result = select_spec_sections(
            feature_id="b-005",
            name="",
            description="",
            acceptance_criteria=[],
        )
        assert result["functional"] == "REQUIRED"

    def test_all_empty_inputs_values_are_valid(self):
        result = select_spec_sections(
            feature_id="b-006",
            name="",
            description="",
            acceptance_criteria=[],
        )
        valid = {"REQUIRED", "OPTIONAL", "SKIP"}
        for section, value in result.items():
            assert value in valid, f"Invalid value {value!r} for section {section!r}"

    def test_single_ac_string_does_not_raise(self):
        result = select_spec_sections(
            feature_id="b-007",
            name="Min feature",
            description="Minimal.",
            acceptance_criteria=["File exists: src/min.py"],
        )
        assert isinstance(result, dict)

    def test_empty_feature_id_does_not_raise(self):
        result = select_spec_sections(
            feature_id="",
            name="Some feature",
            description="Some description.",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)


class TestFocusedExtractorBoundary:
    def test_all_empty_inputs_returns_dict(self):
        result = focused_extractor(
            feature_id="fb-001",
            name="",
            description="",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)

    def test_all_empty_inputs_has_required_keys(self):
        result = focused_extractor(
            feature_id="fb-002",
            name="",
            description="",
            acceptance_criteria=[],
        )
        assert "feature_id" in result
        assert "section_map" in result
        assert "filtered_acs" in result
        assert "skipped_sections" in result

    def test_all_empty_inputs_filtered_acs_is_empty_list(self):
        result = focused_extractor(
            feature_id="fb-003",
            name="",
            description="",
            acceptance_criteria=[],
        )
        assert result["filtered_acs"] == []

    def test_empty_acs_skipped_sections_is_list(self):
        result = focused_extractor(
            feature_id="fb-004",
            name="",
            description="",
            acceptance_criteria=[],
        )
        assert isinstance(result["skipped_sections"], list)

    def test_minimum_name_description_returns_valid_section_map(self):
        result = focused_extractor(
            feature_id="fb-005",
            name="x",
            description="y",
            acceptance_criteria=[],
        )
        valid = {"REQUIRED", "OPTIONAL", "SKIP"}
        for section, value in result["section_map"].items():
            assert value in valid, f"Invalid value {value!r} for section {section!r}"

    def test_zero_length_ac_list_does_not_raise(self):
        result = focused_extractor(
            feature_id="fb-006",
            name="Feature",
            description="Description.",
            acceptance_criteria=[],
        )
        assert result["feature_id"] == "fb-006"
