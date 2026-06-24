"""Error-path tests for bob.self_discover_meta_agent.

Verifies that invalid input raises ValueError and the function does not
silently succeed (error path coverage).
"""

from __future__ import annotations

import pytest

from bob.self_discover_meta_agent import (
    focused_extractor,
    select_spec_sections,
)


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
                feature_id=123,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_none_name_raises_value_error(self):
        with pytest.raises(ValueError, match="name"):
            select_spec_sections(
                feature_id="err-001",
                name=None,  # type: ignore[arg-type]
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_none_description_raises_value_error(self):
        with pytest.raises(ValueError, match="description"):
            select_spec_sections(
                feature_id="err-002",
                name="Feature",
                description=None,  # type: ignore[arg-type]
                acceptance_criteria=[],
            )

    def test_non_list_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="err-003",
                name="Feature",
                description="Desc.",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_dict_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="err-004",
                name="Feature",
                description="Desc.",
                acceptance_criteria={"key": "value"},  # type: ignore[arg-type]
            )

    def test_acceptance_criteria_with_non_string_item_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="err-005",
                name="Feature",
                description="Desc.",
                acceptance_criteria=["valid AC", 42],  # type: ignore[list-item]
            )

    def test_acceptance_criteria_with_none_item_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            select_spec_sections(
                feature_id="err-006",
                name="Feature",
                description="Desc.",
                acceptance_criteria=[None],  # type: ignore[list-item]
            )

    def test_none_feature_id_does_not_silently_succeed(self):
        """Ensure the function raises rather than returning a result for None feature_id."""
        raised = False
        try:
            select_spec_sections(
                feature_id=None,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )
        except ValueError:
            raised = True
        assert raised, "Expected ValueError to be raised but function returned normally"


class TestFocusedExtractorErrorPaths:
    def test_none_feature_id_raises_value_error(self):
        with pytest.raises(ValueError, match="feature_id"):
            focused_extractor(
                feature_id=None,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_none_name_raises_value_error(self):
        with pytest.raises(ValueError, match="name"):
            focused_extractor(
                feature_id="fe-001",
                name=None,  # type: ignore[arg-type]
                description="Desc.",
                acceptance_criteria=[],
            )

    def test_none_description_raises_value_error(self):
        with pytest.raises(ValueError, match="description"):
            focused_extractor(
                feature_id="fe-002",
                name="Feature",
                description=None,  # type: ignore[arg-type]
                acceptance_criteria=[],
            )

    def test_non_list_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            focused_extractor(
                feature_id="fe-003",
                name="Feature",
                description="Desc.",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_non_string_ac_item_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            focused_extractor(
                feature_id="fe-004",
                name="Feature",
                description="Desc.",
                acceptance_criteria=[1, 2, 3],  # type: ignore[list-item]
            )

    def test_invalid_input_does_not_silently_succeed(self):
        """Confirm invalid input raises and not silently returns a result."""
        raised = False
        try:
            focused_extractor(
                feature_id=None,  # type: ignore[arg-type]
                name="Feature",
                description="Desc.",
                acceptance_criteria=[],
            )
        except ValueError:
            raised = True
        assert raised, "Expected ValueError to be raised but function returned normally"
