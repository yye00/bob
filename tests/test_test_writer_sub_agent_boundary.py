"""Boundary cases for test_writer_agent.generate_failing_tests.

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising unexpected exceptions.
"""

from __future__ import annotations

import pytest

from bob3.orchestrator.test_writer_agent import generate_failing_tests


class TestGenerateFailingTestsBoundary:
    def test_empty_acceptance_criteria_returns_valid_dict(self, tmp_path):
        """Zero ACs must return a gate_passed=True result, not raise."""
        result = generate_failing_tests("feat-boundary-empty", [], workspace=tmp_path)
        assert isinstance(result, dict)
        assert result["emitted"] == []
        assert result["filter_results"] == []
        assert result["gate_passed"] is True
        assert result["bijection"].is_bijective is True

    def test_single_ac_returns_one_emitted_test(self, tmp_path):
        """A single AC must produce exactly one emitted test and one filter result."""
        result = generate_failing_tests(
            "feat-boundary-single",
            ["File exists: src/single.py"],
            workspace=tmp_path,
        )
        assert len(result["emitted"]) == 1
        assert len(result["filter_results"]) == 1
        assert result["bijection"].is_bijective is True

    def test_very_short_feature_id_is_accepted(self, tmp_path):
        """A single-character feature_id is the minimum valid input."""
        result = generate_failing_tests("x", ["File exists: src/x.py"], workspace=tmp_path)
        assert len(result["emitted"]) == 1

    def test_ac_with_empty_string_is_handled_gracefully(self, tmp_path):
        """An AC that is an empty string must not raise — the slug falls back to ac_<n>."""
        result = generate_failing_tests(
            "feat-boundary-blank-ac", [""], workspace=tmp_path
        )
        assert len(result["emitted"]) == 1
        assert result["emitted"][0].test_path.exists()

    def test_single_whitespace_ac_handled_gracefully(self, tmp_path):
        """An AC consisting only of whitespace must not raise."""
        result = generate_failing_tests(
            "feat-boundary-ws-ac", ["   "], workspace=tmp_path
        )
        assert len(result["emitted"]) == 1
