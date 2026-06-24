"""Boundary tests for bob.explain-gate-block CLI.

Verifies that empty, zero, or minimum input returns a well-defined result
rather than raising.
"""

from __future__ import annotations

import json

import pytest

from bob.enhanced_verification import explain_gate_block, score_feature


class TestExplainGateBlockBoundary:
    def test_empty_acceptance_criteria_list(self):
        result = explain_gate_block(
            feature_id="boundary-empty-001",
            feature_name="Empty ACs",
            description=None,
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)
        assert result["score"] == 0.0
        assert isinstance(result["remediation_hints"], list)

    def test_empty_acceptance_criteria_json_string(self):
        result = explain_gate_block(
            feature_id="boundary-empty-002",
            feature_name="Empty JSON ACs",
            description=None,
            acceptance_criteria="[]",
        )
        assert isinstance(result, dict)
        assert result["score"] == 0.0

    def test_empty_feature_name(self):
        result = explain_gate_block(
            feature_id="boundary-name-001",
            feature_name="",
            description=None,
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)
        assert "score" in result

    def test_none_description(self):
        result = explain_gate_block(
            feature_id="boundary-desc-001",
            feature_name="No Description Feature",
            description=None,
            acceptance_criteria=["File exists: src/bob/enhanced_verification.py"],
        )
        assert isinstance(result, dict)
        assert "score" in result

    def test_empty_string_description(self):
        result = explain_gate_block(
            feature_id="boundary-desc-002",
            feature_name="Empty Desc Feature",
            description="",
            acceptance_criteria=["File exists: src/bob/enhanced_verification.py"],
        )
        assert isinstance(result, dict)
        assert "score" in result

    def test_single_ac_minimum_input(self):
        result = explain_gate_block(
            feature_id="boundary-single-001",
            feature_name="Single AC Feature",
            description=None,
            acceptance_criteria=["File exists: src/bob/enhanced_verification.py"],
        )
        assert isinstance(result, dict)
        assert 0.0 <= result["score"] <= 1.0

    def test_score_feature_empty_acs(self):
        result = score_feature(name="Empty", description=None, acceptance_criteria=[])
        assert isinstance(result, dict)
        assert result["score"] == 0.0

    def test_score_feature_minimum_input(self):
        result = score_feature(
            name="Min",
            description=None,
            acceptance_criteria=["File exists: src/bob/enhanced_verification.py"],
        )
        assert isinstance(result, dict)
        assert 0.0 <= result["score"] <= 1.0

    def test_score_feature_returns_required_keys(self):
        result = score_feature(name="Test", description=None, acceptance_criteria=[])
        assert "score" in result
        assert "threshold" in result
        assert "components" in result
        assert "remediation_hints" in result

    def test_score_feature_components_keys(self):
        result = score_feature(name="Test", description=None, acceptance_criteria=[])
        components = result["components"]
        assert "ambiguity_score" in components
        assert "reachability_score" in components
        assert "ears_score" in components
        assert "ac_coverage_score" in components

    def test_explain_gate_block_zero_score_no_raise(self):
        """Zero score must not raise — it is a valid state."""
        result = explain_gate_block(
            feature_id="zero-score-001",
            feature_name="Zero Score",
            description=None,
            acceptance_criteria=[],
        )
        assert result["score"] == 0.0
        assert result["threshold"] > 0.0
        assert isinstance(result["remediation_hints"], list)
        assert len(result["remediation_hints"]) > 0

    def test_explain_gate_block_very_long_feature_name(self):
        long_name = "A" * 512
        result = explain_gate_block(
            feature_id="boundary-long-001",
            feature_name=long_name,
            description=None,
            acceptance_criteria=[],
        )
        assert isinstance(result, dict)
        assert result["feature_name"] == long_name

    def test_explain_gate_block_feature_id_passed_through(self):
        fid = "00000000-0000-0000-0000-000000000000"
        result = explain_gate_block(
            feature_id=fid,
            feature_name="Zero UUID Feature",
            description=None,
            acceptance_criteria=[],
        )
        assert result["feature_id"] == fid
