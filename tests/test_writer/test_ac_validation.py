"""Tests for TestWriterAgent — AC validation (AC: test_ac_validation).

Validates that generate_failing_tests correctly validates acceptance criteria
inputs: raises ValueError for invalid inputs, accepts valid AC lists, and
produces a gate_passed result that reflects AC quality.
"""

from __future__ import annotations

import pytest

from bob3.orchestrator.test_writer_agent import generate_failing_tests
from bob3.test_writer import (
    BijectionReport,
    EmittedTest,
    FilterResult,
    generate_failing_tests as gft_reexport,
)
from test_writer import TestWriterAgent


class TestAcValidationInputGuards:
    def test_empty_feature_id_raises_value_error(self, tmp_path):
        """An empty feature_id must raise ValueError before any file I/O."""
        with pytest.raises(ValueError, match="feature_id"):
            generate_failing_tests("", ["File exists: src/x.py"], workspace=tmp_path)

    def test_whitespace_only_feature_id_raises_value_error(self, tmp_path):
        """A whitespace-only feature_id must raise ValueError."""
        with pytest.raises(ValueError, match="feature_id"):
            generate_failing_tests("   ", ["File exists: src/x.py"], workspace=tmp_path)

    def test_non_list_acceptance_criteria_raises_value_error(self, tmp_path):
        """Passing a non-list for acceptance_criteria must raise ValueError."""
        with pytest.raises(ValueError, match="acceptance_criteria"):
            generate_failing_tests("feat-val", "not a list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_none_acceptance_criteria_raises_value_error(self, tmp_path):
        """Passing None for acceptance_criteria must raise ValueError."""
        with pytest.raises(ValueError, match="acceptance_criteria"):
            generate_failing_tests("feat-val-none", None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_tuple_acceptance_criteria_raises_value_error(self, tmp_path):
        """Passing a tuple for acceptance_criteria must raise ValueError."""
        with pytest.raises(ValueError, match="acceptance_criteria"):
            generate_failing_tests("feat-val-tuple", ("ac1", "ac2"), workspace=tmp_path)  # type: ignore[arg-type]


class TestAcValidationValidInputs:
    def test_empty_ac_list_is_valid(self, tmp_path):
        """An empty AC list is valid and must return gate_passed=True."""
        result = generate_failing_tests("feat-val-empty", [], workspace=tmp_path)
        assert isinstance(result, dict)
        assert result["gate_passed"] is True
        assert result["emitted"] == []

    def test_single_ac_is_valid(self, tmp_path):
        """A single-element AC list must produce exactly one emitted test."""
        result = generate_failing_tests(
            "feat-val-single", ["File exists: src/x.py"], workspace=tmp_path
        )
        assert len(result["emitted"]) == 1
        assert result["gate_passed"] is True

    def test_multiple_acs_all_validated(self, tmp_path):
        """Multiple ACs must all produce emitted tests and pass validation."""
        acs = [
            "File exists: src/module_a.py",
            "Function defined: bob3.module_a.entry",
            "pytest: tests/test_module_a.py",
        ]
        result = generate_failing_tests("feat-val-multi", acs, workspace=tmp_path)
        assert len(result["emitted"]) == len(acs)
        assert result["bijection"].is_bijective is True

    def test_ac_with_empty_string_does_not_raise(self, tmp_path):
        """An AC that is an empty string must not raise — falls back gracefully."""
        result = generate_failing_tests("feat-val-blank", [""], workspace=tmp_path)
        assert len(result["emitted"]) == 1

    def test_reexported_function_matches_behaviour(self, tmp_path):
        """The re-exported generate_failing_tests from bob3.test_writer must behave identically."""
        result = gft_reexport("feat-val-reexport", ["File exists: src/y.py"], workspace=tmp_path)
        assert "gate_passed" in result
        assert isinstance(result["emitted"], list)

    def test_agent_generate_matches_function_output(self, tmp_path):
        """TestWriterAgent.generate must produce the same structure as generate_failing_tests."""
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-val-agent", ["File exists: src/z.py"])
        assert "emitted" in result
        assert "filter_results" in result
        assert "bijection" in result
        assert "gate_passed" in result


class TestAcValidationBijection:
    def test_bijection_is_bijective_for_valid_acs(self, tmp_path):
        """The bijection report must be bijective when each AC gets exactly one test."""
        acs = ["File exists: src/a.py", "File exists: src/b.py"]
        result = generate_failing_tests("feat-val-bijection", acs, workspace=tmp_path)
        assert result["bijection"].is_bijective is True
        assert result["bijection"].missing_tests == []
        assert result["bijection"].orphan_tests == []

    def test_bijection_report_has_correct_ac_count(self, tmp_path):
        """The BijectionReport must list one ac_id per input AC."""
        acs = ["File exists: src/a.py", "Function defined: bob3.m.fn"]
        result = generate_failing_tests("feat-val-ac-count", acs, workspace=tmp_path)
        assert len(result["bijection"].ac_ids) == len(acs)

    def test_each_emitted_test_maps_to_an_ac(self, tmp_path):
        """Every EmittedTest.ac_text must match one of the input ACs."""
        acs = ["File exists: src/a.py", "pytest: tests/test_b.py"]
        result = generate_failing_tests("feat-val-ac-map", acs, workspace=tmp_path)
        emitted_ac_texts = {et.ac_text for et in result["emitted"]}
        for ac in acs:
            assert ac in emitted_ac_texts, f"AC {ac!r} not found in emitted tests"
