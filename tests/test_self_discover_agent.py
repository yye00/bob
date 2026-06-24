"""Tests for bob.self_discover_agent.

Feature 869cc539-1c8e-4703-80f9-f740a3d0a846: Self-Discover meta-agent for
per-feature spec-section selection.
"""

from __future__ import annotations

import pytest

from bob.self_discover_agent import (
    run_focused_extraction,
    select_spec_sections,
)
from bob.spec_quality.section_selector import module_set

VALID_LABELS = {"REQUIRED", "OPTIONAL", "SKIP"}


class TestSelectSpecSections:
    def test_returns_dict(self):
        result = select_spec_sections(
            feature_id="test-001",
            name="My Feature",
            description="Does something useful.",
            acceptance_criteria=["File exists: src/bob/my_feature.py"],
        )
        assert isinstance(result, dict)

    def test_keys_match_module_set(self):
        result = select_spec_sections(
            feature_id="test-002",
            name="My Feature",
            description="Does something useful.",
            acceptance_criteria=[],
        )
        assert set(result.keys()) == set(module_set())

    def test_all_values_are_valid_labels(self):
        result = select_spec_sections(
            feature_id="test-003",
            name="My Feature",
            description="Does something useful.",
            acceptance_criteria=[],
        )
        for section, label in result.items():
            assert label in VALID_LABELS, f"Invalid label {label!r} for section {section!r}"

    def test_functional_is_always_required(self):
        result = select_spec_sections(
            feature_id="test-004",
            name="My Feature",
            description="Does something useful.",
            acceptance_criteria=[],
        )
        assert result["functional"] == "REQUIRED"

    def test_invalid_feature_id_type_raises_value_error(self):
        with pytest.raises(ValueError, match="feature_id"):
            select_spec_sections(
                feature_id=None,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_invalid_name_type_raises_value_error(self):
        with pytest.raises(ValueError, match="name"):
            select_spec_sections(
                feature_id="test-005",
                name=42,  # type: ignore[arg-type]
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_invalid_description_type_raises_value_error(self):
        with pytest.raises(ValueError, match="description"):
            select_spec_sections(
                feature_id="test-006",
                name="Feature",
                description=None,  # type: ignore[arg-type]
                acceptance_criteria=[],
            )

    def test_invalid_acceptance_criteria_type_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="test-007",
                name="Feature",
                description="Desc.",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_acceptance_criteria_with_non_string_item_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="test-008",
                name="Feature",
                description="Desc.",
                acceptance_criteria=["valid", 99],  # type: ignore[list-item]
            )


class TestRunFocusedExtraction:
    def test_returns_dict(self):
        result = run_focused_extraction(
            feature_id="fe-001",
            name="My Feature",
            description="Does something.",
            acceptance_criteria=["File exists: src/bob/my_feature.py"],
        )
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = run_focused_extraction(
            feature_id="fe-002",
            name="My Feature",
            description="Does something.",
            acceptance_criteria=[],
        )
        assert "feature_id" in result
        assert "section_map" in result
        assert "filtered_acs" in result
        assert "skipped_sections" in result

    def test_feature_id_echoed(self):
        result = run_focused_extraction(
            feature_id="fe-003",
            name="My Feature",
            description="Does something.",
            acceptance_criteria=[],
        )
        assert result["feature_id"] == "fe-003"

    def test_filtered_acs_matches_input(self):
        acs = ["AC one", "AC two"]
        result = run_focused_extraction(
            feature_id="fe-004",
            name="My Feature",
            description="Does something.",
            acceptance_criteria=acs,
        )
        assert result["filtered_acs"] == acs

    def test_skipped_sections_is_list(self):
        result = run_focused_extraction(
            feature_id="fe-005",
            name="My Feature",
            description="Does something.",
            acceptance_criteria=[],
        )
        assert isinstance(result["skipped_sections"], list)

    def test_section_map_values_are_valid(self):
        result = run_focused_extraction(
            feature_id="fe-006",
            name="My Feature",
            description="Does something.",
            acceptance_criteria=[],
        )
        for section, label in result["section_map"].items():
            assert label in VALID_LABELS, f"Invalid label {label!r} for section {section!r}"

    def test_skipped_sections_subset_of_section_map(self):
        result = run_focused_extraction(
            feature_id="fe-007",
            name="My Feature",
            description="Does something.",
            acceptance_criteria=[],
        )
        for section in result["skipped_sections"]:
            assert result["section_map"][section] == "SKIP"

    def test_invalid_feature_id_raises_value_error(self):
        with pytest.raises(ValueError, match="feature_id"):
            run_focused_extraction(
                feature_id=None,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_invalid_name_raises_value_error(self):
        with pytest.raises(ValueError, match="name"):
            run_focused_extraction(
                feature_id="fe-008",
                name=None,  # type: ignore[arg-type]
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_invalid_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            run_focused_extraction(
                feature_id="fe-009",
                name="Feature",
                description="Desc.",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_empty_acs_returns_empty_filtered_acs(self):
        result = run_focused_extraction(
            feature_id="fe-010",
            name="Feature",
            description="Desc.",
            acceptance_criteria=[],
        )
        assert result["filtered_acs"] == []
