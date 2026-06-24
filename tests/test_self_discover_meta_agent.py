"""Tests for bob.self_discover_meta_agent.

Covers:
- select_spec_sections: per-feature section classification
- run_focused_extractor: focused extraction using section selection
- Integration with spec_synthesizer
"""

from __future__ import annotations

import pytest

from bob.self_discover_meta_agent import (
    run_focused_extractor,
    select_spec_sections,
)
from bob.spec_quality.section_selector import module_set


# ---------------------------------------------------------------------------
# select_spec_sections tests
# ---------------------------------------------------------------------------


class TestSelectSpecSections:
    def test_returns_dict_with_all_sections(self):
        result = select_spec_sections(
            feature_id="test-001",
            name="Add caching layer",
            description="Cache query results for performance.",
            acceptance_criteria=["File exists: src/cache.py"],
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == set(module_set())

    def test_all_values_are_valid(self):
        result = select_spec_sections(
            feature_id="test-002",
            name="Add logging",
            description="Log all auth events with trace IDs.",
            acceptance_criteria=["pytest: tests/test_logging.py"],
        )
        valid_values = {"REQUIRED", "OPTIONAL", "SKIP"}
        for section, value in result.items():
            assert value in valid_values, f"Invalid value {value!r} for section {section!r}"

    def test_functional_is_always_required(self):
        result = select_spec_sections(
            feature_id="test-003",
            name="Rename function",
            description="Rename internal helper.",
            acceptance_criteria=[],
        )
        assert result["functional"] == "REQUIRED"

    def test_trivial_feature_skips_nfr_sections(self):
        result = select_spec_sections(
            feature_id="test-004",
            name="Cleanup old code",
            description="Refactor and cleanup unused utilities.",
            acceptance_criteria=[],
        )
        nfr_sections = {"perf", "security", "observability", "ops", "ux", "compat"}
        for section in nfr_sections:
            assert result[section] == "SKIP", f"Expected SKIP for {section!r} in trivial feature"

    def test_security_required_for_auth_features(self):
        result = select_spec_sections(
            feature_id="test-005",
            name="Add JWT auth and security tokens",
            description="Implement authentication with auth tokens and security privileges.",
            acceptance_criteria=["File exists: src/auth.py"],
        )
        assert result["security"] == "REQUIRED"

    def test_perf_required_when_mentioned_twice(self):
        result = select_spec_sections(
            feature_id="test-006",
            name="Optimize query latency",
            description="Improve throughput and reduce latency for heavy queries.",
            acceptance_criteria=[],
        )
        assert result["perf"] == "REQUIRED"

    def test_perf_optional_when_mentioned_once(self):
        result = select_spec_sections(
            feature_id="test-007",
            name="Query builder",
            description="Build queries with latency monitoring.",
            acceptance_criteria=[],
        )
        assert result["perf"] == "OPTIONAL"

    def test_observability_required_for_logging_features(self):
        result = select_spec_sections(
            feature_id="test-008",
            name="Add trace logging and metrics",
            description="Emit log lines and metrics for each request. Monitor telemetry.",
            acceptance_criteria=[],
        )
        assert result["observability"] == "REQUIRED"

    def test_empty_inputs_do_not_raise(self):
        result = select_spec_sections(
            feature_id="test-009",
            name="",
            description="",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == set(module_set())

    def test_compat_required_for_versioning_features(self):
        result = select_spec_sections(
            feature_id="test-010",
            name="Schema upgrade backward compat check",
            description="Upgrade schema with legacy backward compatibility and version downgrade.",
            acceptance_criteria=[],
        )
        assert result["compat"] == "REQUIRED"

    def test_error_handling_required_when_errors_mentioned(self):
        result = select_spec_sections(
            feature_id="test-011",
            name="Retry handler",
            description="Handle exception and retry on failure with recovery fallback.",
            acceptance_criteria=[],
        )
        assert result["error_handling"] == "REQUIRED"

    def test_ux_required_for_ui_features(self):
        result = select_spec_sections(
            feature_id="test-012",
            name="UI dashboard frontend",
            description="Render user interface with HTML layout and CSS.",
            acceptance_criteria=[],
        )
        assert result["ux"] == "REQUIRED"

    def test_ops_required_for_deploy_features(self):
        result = select_spec_sections(
            feature_id="test-013",
            name="Kubernetes deployment config",
            description="Deploy service to kubernetes with docker and CI environment config.",
            acceptance_criteria=[],
        )
        assert result["ops"] == "REQUIRED"


# ---------------------------------------------------------------------------
# run_focused_extractor tests
# ---------------------------------------------------------------------------


class TestRunFocusedExtractor:
    def test_returns_dict(self):
        result = run_focused_extractor(
            feature_id="test-f01",
            name="Add cache",
            description="Cache DB results.",
            acceptance_criteria=["File exists: src/cache.py"],
        )
        assert isinstance(result, dict)

    def test_result_has_section_map_key(self):
        result = run_focused_extractor(
            feature_id="test-f02",
            name="Add cache",
            description="Cache DB results.",
            acceptance_criteria=[],
        )
        assert "section_map" in result

    def test_result_has_filtered_acs_key(self):
        result = run_focused_extractor(
            feature_id="test-f03",
            name="Add cache",
            description="Cache DB results.",
            acceptance_criteria=["File exists: src/cache.py"],
        )
        assert "filtered_acs" in result

    def test_result_has_skipped_sections_key(self):
        result = run_focused_extractor(
            feature_id="test-f04",
            name="Refactor cleanup",
            description="Refactor old internal utility code.",
            acceptance_criteria=[],
        )
        assert "skipped_sections" in result

    def test_skipped_sections_match_skip_in_section_map(self):
        result = run_focused_extractor(
            feature_id="test-f05",
            name="Refactor cleanup",
            description="Refactor old internal utility code.",
            acceptance_criteria=[],
        )
        section_map = result["section_map"]
        skipped = result["skipped_sections"]
        expected_skipped = {s for s, v in section_map.items() if v == "SKIP"}
        assert set(skipped) == expected_skipped

    def test_focused_extractor_passes_feature_id(self):
        result = run_focused_extractor(
            feature_id="test-f06",
            name="Add logging",
            description="Log events.",
            acceptance_criteria=[],
        )
        assert result.get("feature_id") == "test-f06"

    def test_trivial_feature_has_many_skipped_sections(self):
        result = run_focused_extractor(
            feature_id="test-f07",
            name="Cleanup stub",
            description="Refactor and cleanup migration alias.",
            acceptance_criteria=[],
        )
        skipped = result["skipped_sections"]
        assert len(skipped) >= 3, f"Expected at least 3 skipped sections, got {skipped}"

    def test_complex_feature_has_fewer_skipped_sections(self):
        result = run_focused_extractor(
            feature_id="test-f08",
            name="Auth service with monitoring",
            description=(
                "Implement auth token validation with security checks. "
                "Log trace metrics for all auth events. "
                "Handle exceptions with retry and recovery fallback."
            ),
            acceptance_criteria=["pytest: tests/test_auth.py"],
        )
        skipped = result["skipped_sections"]
        assert len(skipped) < 6, f"Expected few skipped sections for complex feature, got {skipped}"

    def test_filtered_acs_is_list(self):
        result = run_focused_extractor(
            feature_id="test-f09",
            name="Add feature",
            description="Add a new feature.",
            acceptance_criteria=["File exists: src/feature.py", "pytest: tests/test_feature.py"],
        )
        assert isinstance(result["filtered_acs"], list)

    def test_filtered_acs_preserves_all_acs_by_default(self):
        acs = ["File exists: src/feature.py", "pytest: tests/test_feature.py"]
        result = run_focused_extractor(
            feature_id="test-f10",
            name="Add feature",
            description="Add a new feature.",
            acceptance_criteria=acs,
        )
        assert result["filtered_acs"] == acs


# ---------------------------------------------------------------------------
# Integration with spec_synthesizer
# ---------------------------------------------------------------------------


class TestSpecSynthesizerIntegration:
    def test_select_spec_sections_importable_from_self_discover(self):
        from bob.self_discover_meta_agent import select_spec_sections as fn
        assert callable(fn)

    def test_run_focused_extractor_importable_from_self_discover(self):
        from bob.self_discover_meta_agent import run_focused_extractor as fn
        assert callable(fn)

    def test_select_spec_sections_uses_spec_quality_module_set(self):
        result = select_spec_sections(
            feature_id="integ-001",
            name="Integration test feature",
            description="Test that section set matches spec_quality module_set.",
            acceptance_criteria=[],
        )
        assert set(result.keys()) == set(module_set())

    def test_run_focused_extractor_section_map_valid(self):
        from bob.spec_quality.section_selector import validate_output_schema
        result = run_focused_extractor(
            feature_id="integ-002",
            name="Integration test feature",
            description="Validate the section_map against spec_quality schema.",
            acceptance_criteria=["File exists: src/test.py"],
        )
        # Should not raise
        validate_output_schema(result["section_map"])
