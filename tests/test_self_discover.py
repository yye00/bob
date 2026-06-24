"""Tests for bob.meta_agent.self_discover.

Verifies that select_spec_sections and run_focused_extractor behave correctly
for the Self-Discover meta-agent feature (14d1c097-e778-493c-a863-25efd2f034fb).
"""

from __future__ import annotations

import pytest

from bob.meta_agent.self_discover import (
    run_focused_extractor,
    select_spec_sections,
)
from bob.spec_quality.section_selector import module_set


FEATURE_ID = "14d1c097-e778-493c-a863-25efd2f034fb"
FEATURE_NAME = "Self-Discover meta-agent for per-feature spec-section selection"
FEATURE_DESCRIPTION = (
    "bob's PRD schema (F-R7-457) is fixed: every spec must fill every slot. "
    "A meta-agent that first picks WHICH spec sections matter, "
    "then drives a focused extractor pass, beats one-size-fits-all."
)
FEATURE_ACS = [
    "File exists: src/bob/meta_agent/self_discover.py",
    "Function defined: bob.meta_agent.self_discover.select_spec_sections",
    "Function defined: bob.meta_agent.self_discover.run_focused_extractor",
    "pytest: tests/test_self_discover.py",
    "integration: bob.orchestrator",
]


class TestSelectSpecSections:
    def test_returns_dict(self):
        result = select_spec_sections(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        assert isinstance(result, dict)

    def test_covers_all_canonical_sections(self):
        result = select_spec_sections(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        assert set(result.keys()) == set(module_set())

    def test_all_values_are_valid_labels(self):
        result = select_spec_sections(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        valid = {"REQUIRED", "OPTIONAL", "SKIP"}
        for section, label in result.items():
            assert label in valid, f"Invalid label {label!r} for section {section!r}"

    def test_functional_is_required(self):
        result = select_spec_sections(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        assert result["functional"] == "REQUIRED"

    def test_none_feature_id_raises_value_error(self):
        with pytest.raises(ValueError, match="feature_id"):
            select_spec_sections(
                feature_id=None,  # type: ignore[arg-type]
                name=FEATURE_NAME,
                description=FEATURE_DESCRIPTION,
                acceptance_criteria=FEATURE_ACS,
            )

    def test_non_list_acs_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id=FEATURE_ID,
                name=FEATURE_NAME,
                description=FEATURE_DESCRIPTION,
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_non_string_ac_item_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id=FEATURE_ID,
                name=FEATURE_NAME,
                description=FEATURE_DESCRIPTION,
                acceptance_criteria=["valid", 42],  # type: ignore[list-item]
            )

    def test_empty_acs_does_not_raise(self):
        result = select_spec_sections(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)


class TestRunFocusedExtractor:
    def test_returns_dict(self):
        result = run_focused_extractor(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = run_focused_extractor(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        assert "feature_id" in result
        assert "section_map" in result
        assert "filtered_acs" in result
        assert "skipped_sections" in result

    def test_echoes_feature_id(self):
        result = run_focused_extractor(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        assert result["feature_id"] == FEATURE_ID

    def test_filtered_acs_matches_input(self):
        result = run_focused_extractor(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        assert result["filtered_acs"] == FEATURE_ACS

    def test_section_map_covers_all_canonical_sections(self):
        result = run_focused_extractor(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        assert set(result["section_map"].keys()) == set(module_set())

    def test_skipped_sections_is_list(self):
        result = run_focused_extractor(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        assert isinstance(result["skipped_sections"], list)

    def test_skipped_sections_are_subset_of_module_set(self):
        result = run_focused_extractor(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        all_sections = set(module_set())
        for section in result["skipped_sections"]:
            assert section in all_sections

    def test_section_map_values_are_valid(self):
        result = run_focused_extractor(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=FEATURE_ACS,
        )
        valid = {"REQUIRED", "OPTIONAL", "SKIP"}
        for section, label in result["section_map"].items():
            assert label in valid

    def test_none_feature_id_raises_value_error(self):
        with pytest.raises(ValueError, match="feature_id"):
            run_focused_extractor(
                feature_id=None,  # type: ignore[arg-type]
                name=FEATURE_NAME,
                description=FEATURE_DESCRIPTION,
                acceptance_criteria=FEATURE_ACS,
            )

    def test_none_name_raises_value_error(self):
        with pytest.raises(ValueError, match="name"):
            run_focused_extractor(
                feature_id=FEATURE_ID,
                name=None,  # type: ignore[arg-type]
                description=FEATURE_DESCRIPTION,
                acceptance_criteria=FEATURE_ACS,
            )

    def test_non_list_acs_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            run_focused_extractor(
                feature_id=FEATURE_ID,
                name=FEATURE_NAME,
                description=FEATURE_DESCRIPTION,
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_empty_acs_returns_empty_filtered_acs(self):
        result = run_focused_extractor(
            feature_id=FEATURE_ID,
            name=FEATURE_NAME,
            description=FEATURE_DESCRIPTION,
            acceptance_criteria=[],
        )
        assert result["filtered_acs"] == []


class TestOrchestratorIntegration:
    """Verify that bob.meta_agent.self_discover is importable from bob.orchestrator context."""

    def test_orchestrator_can_import_select_spec_sections(self):
        from bob.meta_agent.self_discover import select_spec_sections as fn
        assert callable(fn)

    def test_orchestrator_can_import_run_focused_extractor(self):
        from bob.meta_agent.self_discover import run_focused_extractor as fn
        assert callable(fn)

    def test_meta_agent_package_exports_both_functions(self):
        import bob.meta_agent as pkg
        assert hasattr(pkg, "select_spec_sections")
        assert hasattr(pkg, "run_focused_extractor")
