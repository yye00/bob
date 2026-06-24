"""Tests for bob.self_discover_meta_agent_per_feature_spec_section_selection."""

from __future__ import annotations

import pytest

from bob.self_discover_meta_agent_per_feature_spec_section_selection import (
    self_discover_meta_agent_per_feature_spec_section_selection,
)
from bob.spec_quality.section_selector import module_set


def test_self_discover_meta_agent_per_feature_spec_section_selection():
    """Core AC test: function is callable and returns a valid structured result."""
    result = self_discover_meta_agent_per_feature_spec_section_selection(
        feature_id="7e4cff70-0d16-47e8-8965-75213863afa7",
        name="Self-Discover meta-agent for per-feature spec-section selection",
        description=(
            "bob's PRD schema (F-R7-457) is fixed: every spec must fill every slot. "
            "A meta-agent that first picks WHICH spec sections matter, "
            "then drives a focused extractor pass, beats one-size-fits-all."
        ),
        acceptance_criteria=[
            "File exists: src/bob/self_discover_meta_agent_per_feature_spec_section_selection.py",
            "pytest: tests/test_self_discover_meta_agent_per_feature_spec_section_selection.py::test_self_discover_meta_agent_per_feature_spec_section_selection",
            "Function defined: bob.self_discover_meta_agent_per_feature_spec_section_selection.self_discover_meta_agent_per_feature_spec_section_selection",
        ],
    )

    # Result is a dict
    assert isinstance(result, dict)

    # feature_id is echoed
    assert result["feature_id"] == "7e4cff70-0d16-47e8-8965-75213863afa7"

    # section_map covers all canonical sections
    assert "section_map" in result
    assert set(result["section_map"].keys()) == set(module_set())

    # All section_map values are valid labels
    valid_labels = {"REQUIRED", "OPTIONAL", "SKIP"}
    for section, label in result["section_map"].items():
        assert label in valid_labels, f"Invalid label {label!r} for section {section!r}"

    # functional is always REQUIRED
    assert result["section_map"]["functional"] == "REQUIRED"

    # filtered_acs is a list
    assert isinstance(result["filtered_acs"], list)

    # skipped_sections and active_sections partition section_map
    assert "skipped_sections" in result
    assert "active_sections" in result
    expected_skipped = {s for s, v in result["section_map"].items() if v == "SKIP"}
    expected_active = {s for s, v in result["section_map"].items() if v != "SKIP"}
    assert set(result["skipped_sections"]) == expected_skipped
    assert set(result["active_sections"]) == expected_active

    # active + skipped == full module_set
    all_sections = set(result["skipped_sections"]) | set(result["active_sections"])
    assert all_sections == set(module_set())


# ---------------------------------------------------------------------------
# Additional tests for robustness
# ---------------------------------------------------------------------------


def test_function_importable():
    from bob.self_discover_meta_agent_per_feature_spec_section_selection import (
        self_discover_meta_agent_per_feature_spec_section_selection as fn,
    )
    assert callable(fn)


def test_empty_inputs_do_not_raise():
    result = self_discover_meta_agent_per_feature_spec_section_selection(
        feature_id="empty-test",
        name="",
        description="",
        acceptance_criteria=[],
    )
    assert isinstance(result, dict)
    assert set(result["section_map"].keys()) == set(module_set())


def test_security_feature_marks_security_required():
    result = self_discover_meta_agent_per_feature_spec_section_selection(
        feature_id="sec-test",
        name="JWT auth security token validation",
        description="Validate auth tokens with security permission checks.",
        acceptance_criteria=[],
    )
    assert result["section_map"]["security"] == "REQUIRED"


def test_trivial_feature_skips_nfr_sections():
    result = self_discover_meta_agent_per_feature_spec_section_selection(
        feature_id="trivial-test",
        name="Cleanup unused utilities",
        description="Refactor and cleanup internal helper stubs.",
        acceptance_criteria=[],
    )
    nfr_sections = {"perf", "security", "observability", "ops", "ux", "compat"}
    for section in nfr_sections:
        assert result["section_map"][section] == "SKIP", (
            f"Expected SKIP for NFR section {section!r} in trivial feature"
        )


def test_complex_feature_has_few_skipped_sections():
    result = self_discover_meta_agent_per_feature_spec_section_selection(
        feature_id="complex-test",
        name="Auth service with monitoring and logging",
        description=(
            "Implement auth token validation with security checks. "
            "Log trace metrics for all auth events. "
            "Handle exceptions with retry and recovery fallback."
        ),
        acceptance_criteria=["pytest: tests/test_auth.py"],
    )
    assert len(result["skipped_sections"]) < 6


def test_feature_id_echoed():
    result = self_discover_meta_agent_per_feature_spec_section_selection(
        feature_id="echo-test-xyz",
        name="Some feature",
        description="Some description.",
        acceptance_criteria=[],
    )
    assert result["feature_id"] == "echo-test-xyz"


def test_filtered_acs_preserves_input():
    acs = ["File exists: src/foo.py", "pytest: tests/test_foo.py"]
    result = self_discover_meta_agent_per_feature_spec_section_selection(
        feature_id="acs-test",
        name="Some feature",
        description="Some description.",
        acceptance_criteria=acs,
    )
    assert result["filtered_acs"] == acs
