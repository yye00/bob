"""Tests for bob3.self_discover_selector.select_spec_sections.

Verifies the Self-Discover meta-agent per-feature spec-section selector
(feature e10c6a19-fb0f-4d55-bfdd-743253367c61).
"""

from __future__ import annotations

import pytest

from bob3.self_discover_selector import select_spec_sections
from bob3.spec_quality.section_selector import module_set


class TestSelectSpecSectionsCore:
    def test_returns_dict(self):
        result = select_spec_sections(
            feature_id="e10c6a19-fb0f-4d55-bfdd-743253367c61",
            name="Self-Discover meta-agent for per-feature spec-section selection",
            description=(
                "bob3's PRD schema (F-R7-457) is fixed: every spec must fill every slot. "
                "A meta-agent that first picks WHICH spec sections matter."
            ),
            acceptance_criteria=[
                "File exists: src/bob3/self_discover_selector.py",
                "Function defined: bob3.self_discover_selector.select_spec_sections",
            ],
        )
        assert isinstance(result, dict)

    def test_covers_all_canonical_sections(self):
        result = select_spec_sections(
            feature_id="test-001",
            name="Some feature",
            description="A description.",
            acceptance_criteria=[],
        )
        assert set(result.keys()) == set(module_set())

    def test_functional_is_always_required(self):
        result = select_spec_sections(
            feature_id="test-002",
            name="Any feature",
            description="Any description.",
            acceptance_criteria=[],
        )
        assert result["functional"] == "REQUIRED"

    def test_all_values_are_valid_labels(self):
        result = select_spec_sections(
            feature_id="test-003",
            name="Any feature",
            description="Any description.",
            acceptance_criteria=["File exists: src/foo.py"],
        )
        valid = {"REQUIRED", "OPTIONAL", "SKIP"}
        for section, label in result.items():
            assert label in valid, f"Invalid label {label!r} for section {section!r}"

    def test_empty_ac_list_is_accepted(self):
        result = select_spec_sections(
            feature_id="test-004",
            name="Feature",
            description="Description.",
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)

    def test_multiple_acs_returns_valid_result(self):
        result = select_spec_sections(
            feature_id="test-005",
            name="My feature",
            description="Does something useful.",
            acceptance_criteria=[
                "File exists: src/foo.py",
                "pytest: tests/test_foo.py",
                "Function defined: foo.bar",
            ],
        )
        assert set(result.keys()) == set(module_set())
        valid = {"REQUIRED", "OPTIONAL", "SKIP"}
        for section, label in result.items():
            assert label in valid


class TestSelectSpecSectionsErrorPaths:
    def test_none_feature_id_raises_value_error(self):
        with pytest.raises(ValueError, match="feature_id"):
            select_spec_sections(
                feature_id=None,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_int_feature_id_raises_value_error(self):
        with pytest.raises(ValueError, match="feature_id"):
            select_spec_sections(
                feature_id=42,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_none_name_raises_value_error(self):
        with pytest.raises(ValueError, match="name"):
            select_spec_sections(
                feature_id="f-001",
                name=None,  # type: ignore[arg-type]
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_none_description_raises_value_error(self):
        with pytest.raises(ValueError, match="description"):
            select_spec_sections(
                feature_id="f-002",
                name="Feature",
                description=None,  # type: ignore[arg-type]
                acceptance_criteria=[],
            )

    def test_non_list_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="f-003",
                name="Feature",
                description="Desc.",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_non_string_ac_item_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="f-004",
                name="Feature",
                description="Desc.",
                acceptance_criteria=["valid", 99],  # type: ignore[list-item]
            )

    def test_none_ac_item_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="f-005",
                name="Feature",
                description="Desc.",
                acceptance_criteria=[None],  # type: ignore[list-item]
            )


class TestSelectSpecSectionsIntegration:
    """Verify select_spec_sections integrates cleanly with bob3.spec_critic."""

    def test_section_map_usable_with_spec_critic_import(self):
        """Spec critic can be imported alongside self_discover_selector."""
        from bob3.spec_critic import SpecCritic  # noqa: F401 — import check only

        result = select_spec_sections(
            feature_id="integ-001",
            name="Integration test feature",
            description="Checks that selector and spec_critic coexist.",
            acceptance_criteria=["File exists: src/bob3/self_discover_selector.py"],
        )
        assert isinstance(result, dict)
        assert result["functional"] == "REQUIRED"

    def test_section_map_covers_full_module_set_for_critic(self):
        """The section_map returned covers every section the critic evaluates."""
        result = select_spec_sections(
            feature_id="integ-002",
            name="Full section map",
            description="Every section is classified.",
            acceptance_criteria=[],
        )
        assert set(result.keys()) == set(module_set())
