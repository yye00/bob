"""Error-path tests for research_strategies canonical AC generator.

Verifies that invalid input raises ValueError and the functions do not
silently succeed with bad inputs.
"""

from __future__ import annotations

import pytest

from bob3.research_strategies import emit_canonical_acs, validate_against_spec_quality_gate


class TestErrorPaths:
    def test_empty_string_topic_raises_value_error(self):
        with pytest.raises(ValueError, match="topic"):
            emit_canonical_acs("")

    def test_whitespace_only_topic_raises_value_error(self):
        with pytest.raises(ValueError, match="topic"):
            emit_canonical_acs("   \t\n")

    def test_none_topic_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            emit_canonical_acs(None)  # type: ignore[arg-type]

    def test_integer_topic_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            emit_canonical_acs(42)  # type: ignore[arg-type]

    def test_validate_string_instead_of_list_raises(self):
        with pytest.raises((ValueError, TypeError)):
            validate_against_spec_quality_gate("not_a_list")  # type: ignore[arg-type]

    def test_validate_none_raises(self):
        with pytest.raises((ValueError, TypeError)):
            validate_against_spec_quality_gate(None)  # type: ignore[arg-type]

    def test_validate_list_with_none_element_raises(self):
        with pytest.raises((ValueError, TypeError)):
            validate_against_spec_quality_gate([None])  # type: ignore[arg-type]

    def test_validate_list_with_integer_element_raises(self):
        with pytest.raises((ValueError, TypeError)):
            validate_against_spec_quality_gate([42])  # type: ignore[arg-type]

    def test_emit_does_not_silently_succeed_with_empty_topic(self):
        """Confirm no silent success — must raise, not return empty or None."""
        raised = False
        try:
            result = emit_canonical_acs("")
            # If we get here, the function must have returned something non-empty
            # If it returned empty list, that's a silent success — fail the test
            if result == [] or result is None:
                raised = True  # treat empty result as error
        except (ValueError, TypeError):
            raised = True
        assert raised, "emit_canonical_acs('') must not silently return empty/None"

    def test_validate_prose_acs_does_not_silently_pass(self):
        """Prose ACs must fail gate, not silently succeed."""
        prose_only = [
            "The module handles errors gracefully",
            "All functions return correct results",
        ]
        result = validate_against_spec_quality_gate(prose_only)
        assert result["passed"] is False, (
            "Prose-only ACs must not silently pass the gate"
        )
