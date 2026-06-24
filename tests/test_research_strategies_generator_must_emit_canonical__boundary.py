"""Boundary tests for research_strategies canonical AC generator.

Covers edge cases: minimum input, zero features, single-character topics,
very long topics. All should return a well-defined result rather than raising.
"""

from __future__ import annotations

import pytest

from bob.research_strategies import emit_canonical_acs, validate_against_spec_quality_gate


class TestBoundaryCases:
    def test_single_character_topic_returns_list(self):
        acs = emit_canonical_acs("x")
        assert isinstance(acs, list)
        assert len(acs) >= 1

    def test_very_long_topic_does_not_raise(self):
        long_topic = "a_very_long_feature_name_" * 10
        acs = emit_canonical_acs(long_topic)
        assert isinstance(acs, list)

    def test_topic_with_special_chars_returns_canonical_acs(self):
        # Dashes and underscores are common in feature names
        acs = emit_canonical_acs("path-finding_retry-v2")
        assert isinstance(acs, list)
        assert len(acs) >= 1

    def test_topic_with_dots_returns_canonical_acs(self):
        acs = emit_canonical_acs("bob.feature.sub_component")
        assert isinstance(acs, list)

    def test_validate_empty_list_returns_dict(self):
        result = validate_against_spec_quality_gate([])
        assert isinstance(result, dict)
        assert "passed" in result
        assert "non_canonical" in result

    def test_validate_single_canonical_ac_passes(self):
        result = validate_against_spec_quality_gate(
            ["Function defined: bob.foo.bar"]
        )
        assert result["passed"] is True

    def test_validate_single_prose_ac_fails(self):
        result = validate_against_spec_quality_gate(
            ["The feature should handle all errors properly"]
        )
        assert result["passed"] is False

    def test_validate_returns_exact_non_canonical_acs(self):
        prose_ac = "The system should work correctly always"
        canonical_ac = "pytest: tests/test_foo.py"
        result = validate_against_spec_quality_gate([prose_ac, canonical_ac])
        assert prose_ac in result["non_canonical"]
        assert canonical_ac not in result["non_canonical"]

    def test_emit_with_numeric_suffix_topic(self):
        acs = emit_canonical_acs("feature_v2")
        assert isinstance(acs, list)
        assert len(acs) >= 1

    def test_emit_does_not_return_none(self):
        acs = emit_canonical_acs("any_feature")
        assert acs is not None
