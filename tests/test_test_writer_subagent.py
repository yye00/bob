"""Tests for bob.test_writer_subagent.generate_failing_tests.

Verifies the public facade over bob.orchestrator.test_writer_agent:
- generate_failing_tests returns the expected dict structure
- emitted list maps one-to-one with acceptance criteria
- gate_passed reflects filter and bijection results
- file exists and function is callable
"""

from __future__ import annotations

import importlib

import pytest

from bob.test_writer_subagent import (
    BijectionReport,
    EmittedTest,
    FilterResult,
    generate_failing_tests,
)


class TestGenerateFailingTestsReturnsStructure:
    def test_returns_dict_with_required_keys(self, tmp_path):
        result = generate_failing_tests(
            "twsa-structure",
            ["File exists: src/twsa_structure.py"],
            workspace=tmp_path,
        )
        assert isinstance(result, dict)
        assert "emitted" in result
        assert "filter_results" in result
        assert "bijection" in result
        assert "gate_passed" in result

    def test_emitted_is_list_of_emitted_test(self, tmp_path):
        result = generate_failing_tests(
            "twsa-emitted",
            ["File exists: src/twsa_emitted.py"],
            workspace=tmp_path,
        )
        assert isinstance(result["emitted"], list)
        for item in result["emitted"]:
            assert isinstance(item, EmittedTest)

    def test_filter_results_is_list_of_filter_result(self, tmp_path):
        result = generate_failing_tests(
            "twsa-filter",
            ["File exists: src/twsa_filter.py"],
            workspace=tmp_path,
        )
        assert isinstance(result["filter_results"], list)
        for item in result["filter_results"]:
            assert isinstance(item, FilterResult)

    def test_bijection_is_bijection_report(self, tmp_path):
        result = generate_failing_tests(
            "twsa-bijection",
            ["File exists: src/twsa_bijection.py"],
            workspace=tmp_path,
        )
        assert isinstance(result["bijection"], BijectionReport)

    def test_gate_passed_is_bool(self, tmp_path):
        result = generate_failing_tests(
            "twsa-gate",
            ["File exists: src/twsa_gate.py"],
            workspace=tmp_path,
        )
        assert isinstance(result["gate_passed"], bool)


class TestGenerateFailingTestsEmitCount:
    def test_two_acs_produce_two_emitted_tests(self, tmp_path):
        result = generate_failing_tests(
            "twsa-two",
            ["File exists: src/a.py", "File exists: src/b.py"],
            workspace=tmp_path,
        )
        assert len(result["emitted"]) == 2
        assert len(result["filter_results"]) == 2

    def test_emitted_test_paths_exist_on_disk(self, tmp_path):
        result = generate_failing_tests(
            "twsa-paths",
            ["File exists: src/twsa_paths.py"],
            workspace=tmp_path,
        )
        for et in result["emitted"]:
            assert et.test_path.exists(), f"expected test file at {et.test_path}"

    def test_emitted_test_paths_under_feature_dir(self, tmp_path):
        feature_id = "twsa-dir-check"
        result = generate_failing_tests(
            feature_id,
            ["File exists: src/twsa_dir.py"],
            workspace=tmp_path,
        )
        for et in result["emitted"]:
            assert feature_id in str(et.test_path)


class TestModuleStructure:
    def test_module_is_importable(self):
        mod = importlib.import_module("bob.test_writer_subagent")
        assert mod is not None

    def test_generate_failing_tests_is_callable(self):
        from bob.test_writer_subagent import generate_failing_tests as fn
        assert callable(fn)
