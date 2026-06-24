"""Tests for bob3.meta_agent.

Covers:
- select_spec_sections: per-feature section classification
- SelfDiscoverMetaAgent: class-based two-phase meta-agent
- Integration with bob3.spec_quality.spec_extractor
"""

from __future__ import annotations

import pytest

from bob3.meta_agent import (
    SelfDiscoverMetaAgent,
    select_spec_sections,
)
from bob3.spec_quality.section_selector import module_set


# ---------------------------------------------------------------------------
# select_spec_sections tests
# ---------------------------------------------------------------------------


class TestSelectSpecSections:
    def test_returns_dict_with_all_sections(self):
        result = select_spec_sections(
            feature_id="ma-001",
            name="Add caching layer",
            description="Cache query results for performance.",
            acceptance_criteria=["File exists: src/cache.py"],
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == set(module_set())

    def test_all_values_are_valid(self):
        result = select_spec_sections(
            feature_id="ma-002",
            name="Add logging",
            description="Log all auth events with trace IDs.",
            acceptance_criteria=["pytest: tests/test_logging.py"],
        )
        valid_values = {"REQUIRED", "OPTIONAL", "SKIP"}
        for section, value in result.items():
            assert value in valid_values, f"Invalid value {value!r} for section {section!r}"

    def test_functional_is_always_required(self):
        result = select_spec_sections(
            feature_id="ma-003",
            name="Rename function",
            description="Rename internal helper.",
            acceptance_criteria=[],
        )
        assert result["functional"] == "REQUIRED"

    def test_trivial_feature_skips_nfr_sections(self):
        result = select_spec_sections(
            feature_id="ma-004",
            name="Cleanup old code",
            description="Refactor and cleanup unused utilities.",
            acceptance_criteria=[],
        )
        nfr_sections = {"perf", "security", "observability", "ops", "ux", "compat"}
        for section in nfr_sections:
            assert result[section] == "SKIP", (
                f"Expected {section!r} to be SKIP for trivial feature, got {result[section]!r}"
            )

    def test_security_keywords_classify_security_section(self):
        result = select_spec_sections(
            feature_id="ma-005",
            name="Auth token rotation",
            description="Rotate auth tokens and encrypt secrets in credential store.",
            acceptance_criteria=[],
        )
        assert result["security"] in {"REQUIRED", "OPTIONAL"}

    def test_raises_value_error_on_none_feature_id(self):
        with pytest.raises(ValueError, match="feature_id"):
            select_spec_sections(
                feature_id=None,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_raises_value_error_on_non_list_acs(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="ma-007",
                name="Feature",
                description="Desc.",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_raises_value_error_on_non_string_ac_item(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="ma-008",
                name="Feature",
                description="Desc.",
                acceptance_criteria=["valid", 42],  # type: ignore[list-item]
            )

    def test_empty_inputs_return_valid_map(self):
        result = select_spec_sections(
            feature_id="ma-009",
            name="",
            description="",
            acceptance_criteria=[],
        )
        valid_values = {"REQUIRED", "OPTIONAL", "SKIP"}
        for section, value in result.items():
            assert value in valid_values

    def test_error_handling_keywords_classify_error_handling_section(self):
        result = select_spec_sections(
            feature_id="ma-010",
            name="Error recovery",
            description="Retry on error with fallback mechanism.",
            acceptance_criteria=[],
        )
        assert result["error_handling"] in {"REQUIRED", "OPTIONAL"}


# ---------------------------------------------------------------------------
# SelfDiscoverMetaAgent tests
# ---------------------------------------------------------------------------


class TestSelfDiscoverMetaAgent:
    def test_instantiation_with_valid_inputs(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-001",
            name="Test feature",
            description="A test feature description.",
            acceptance_criteria=["File exists: src/test.py"],
        )
        assert agent.feature_id == "agent-001"
        assert agent.name == "Test feature"

    def test_instantiation_with_empty_acs(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-002",
            name="Minimal feature",
            description="Minimal description.",
            acceptance_criteria=[],
        )
        assert agent.acceptance_criteria == []

    def test_instantiation_raises_on_none_feature_id(self):
        with pytest.raises(ValueError, match="feature_id"):
            SelfDiscoverMetaAgent(
                feature_id=None,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_instantiation_raises_on_none_name(self):
        with pytest.raises(ValueError, match="name"):
            SelfDiscoverMetaAgent(
                feature_id="agent-003",
                name=None,  # type: ignore[arg-type]
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_instantiation_raises_on_non_list_acs(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            SelfDiscoverMetaAgent(
                feature_id="agent-004",
                name="Feature",
                description="Desc.",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_select_sections_returns_all_sections(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-005",
            name="Add caching",
            description="Cache query results for performance.",
            acceptance_criteria=["File exists: src/cache.py"],
        )
        result = agent.select_sections()
        assert set(result.keys()) == set(module_set())

    def test_select_sections_functional_always_required(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-006",
            name="Simple feature",
            description="A simple feature.",
            acceptance_criteria=[],
        )
        result = agent.select_sections()
        assert result["functional"] == "REQUIRED"

    def test_run_returns_dict_with_required_keys(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-007",
            name="Test feature",
            description="Description.",
            acceptance_criteria=["File exists: src/test.py"],
        )
        result = agent.run()
        assert "feature_id" in result
        assert "section_map" in result
        assert "filtered_acs" in result
        assert "skipped_sections" in result

    def test_run_echoes_feature_id(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-008",
            name="Feature",
            description="Description.",
            acceptance_criteria=[],
        )
        result = agent.run()
        assert result["feature_id"] == "agent-008"

    def test_run_filtered_acs_is_list(self):
        acs = ["File exists: src/test.py", "pytest: tests/test_feature.py"]
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-009",
            name="Feature",
            description="Description.",
            acceptance_criteria=acs,
        )
        result = agent.run()
        assert isinstance(result["filtered_acs"], list)

    def test_run_skipped_sections_is_list(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-010",
            name="Feature",
            description="Description.",
            acceptance_criteria=[],
        )
        result = agent.run()
        assert isinstance(result["skipped_sections"], list)

    def test_run_section_map_has_valid_values(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-011",
            name="Security feature",
            description="Encrypt auth tokens and secure credentials.",
            acceptance_criteria=[],
        )
        result = agent.run()
        valid_values = {"REQUIRED", "OPTIONAL", "SKIP"}
        for section, value in result["section_map"].items():
            assert value in valid_values, f"Invalid value {value!r} for {section!r}"

    def test_run_skipped_sections_match_section_map(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-012",
            name="Rename helper",
            description="Refactor internal utility method.",
            acceptance_criteria=[],
        )
        result = agent.run()
        skip_from_map = {k for k, v in result["section_map"].items() if v == "SKIP"}
        assert set(result["skipped_sections"]) == skip_from_map

    def test_default_acceptance_criteria_is_empty_list(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-013",
            name="Feature",
            description="Description.",
        )
        assert agent.acceptance_criteria == []

    def test_run_with_empty_acs_does_not_raise(self):
        agent = SelfDiscoverMetaAgent(
            feature_id="agent-014",
            name="Feature",
            description="Description.",
            acceptance_criteria=[],
        )
        result = agent.run()
        assert result["filtered_acs"] == []


# ---------------------------------------------------------------------------
# Integration with bob3.spec_quality.spec_extractor
# ---------------------------------------------------------------------------


class TestSpecExtractorIntegration:
    def test_run_integrates_with_spec_extractor(self):
        from bob3.spec_quality.spec_extractor import extract_acs

        acs = ["File exists: src/mod.py", "pytest: tests/test_mod.py"]
        agent = SelfDiscoverMetaAgent(
            feature_id="integ-001",
            name="Integration test feature",
            description="Tests integration with spec_extractor.",
            acceptance_criteria=acs,
        )
        result = agent.run()
        # Verify the result matches what extract_acs would produce
        expected_acs = extract_acs(
            feature_id="integ-001",
            name="Integration test feature",
            description="Tests integration with spec_extractor.",
            acceptance_criteria=acs,
        )
        assert result["filtered_acs"] == expected_acs

    def test_section_selector_and_extractor_cooperate(self):
        from bob3.spec_quality.section_selector import extractor_skips_marked_sections

        agent = SelfDiscoverMetaAgent(
            feature_id="integ-002",
            name="Rename utility",
            description="Refactor and rename utility functions.",
            acceptance_criteria=[],
        )
        result = agent.run()
        # Build an extraction_output dict using the skipped_sections
        extraction_output = {
            section: None if section in result["skipped_sections"] else {}
            for section in result["section_map"]
        }
        # extractor_skips_marked_sections should return True for properly nulled SKIP slots
        assert extractor_skips_marked_sections(extraction_output, result["section_map"])
