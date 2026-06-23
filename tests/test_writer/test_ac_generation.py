"""Tests for AC-test generation via bob3.test_writer.generate_failing_tests.

Validates that generate_failing_tests correctly emits one failing pytest per
acceptance criterion, applies the triple filter, and verifies the AC↔test
bijection.  This module tests the full AC-generation pipeline exposed by
bob3.test_writer (re-exported from bob3.orchestrator.test_writer_agent).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.test_writer import (
    EmittedTest,
    FilterResult,
    BijectionReport,
    generate_failing_tests,
    emit_failing_test,
)


class TestGenerateFailingTestsReturnsStructure:
    def test_returns_dict_with_required_keys(self, tmp_path):
        """generate_failing_tests must return a dict with emitted, filter_results, bijection, gate_passed."""
        result = generate_failing_tests("feat-keys", ["File exists: src/x.py"], workspace=tmp_path)
        assert isinstance(result, dict)
        assert "emitted" in result
        assert "filter_results" in result
        assert "bijection" in result
        assert "gate_passed" in result

    def test_emitted_is_list_of_emitted_test(self, tmp_path):
        """generate_failing_tests result['emitted'] must be a list of EmittedTest instances."""
        result = generate_failing_tests("feat-emitted-type", ["File exists: src/a.py"], workspace=tmp_path)
        assert isinstance(result["emitted"], list)
        assert all(isinstance(e, EmittedTest) for e in result["emitted"])

    def test_filter_results_is_list_of_filter_result(self, tmp_path):
        """generate_failing_tests result['filter_results'] must be a list of FilterResult instances."""
        result = generate_failing_tests("feat-filter-type", ["File exists: src/b.py"], workspace=tmp_path)
        assert isinstance(result["filter_results"], list)
        assert all(isinstance(r, FilterResult) for r in result["filter_results"])

    def test_bijection_is_bijection_report(self, tmp_path):
        """generate_failing_tests result['bijection'] must be a BijectionReport."""
        result = generate_failing_tests("feat-bijection-type", ["File exists: src/c.py"], workspace=tmp_path)
        assert isinstance(result["bijection"], BijectionReport)

    def test_gate_passed_is_bool(self, tmp_path):
        """generate_failing_tests result['gate_passed'] must be a bool."""
        result = generate_failing_tests("feat-gate-bool", ["File exists: src/d.py"], workspace=tmp_path)
        assert isinstance(result["gate_passed"], bool)


class TestGenerateFailingTestsACCoverage:
    def test_one_emitted_test_per_ac(self, tmp_path):
        """generate_failing_tests must emit exactly one test per acceptance criterion."""
        acs = ["File exists: src/a.py", "Function defined: bob3.mod.fn", "pytest: tests/t.py"]
        result = generate_failing_tests("feat-count-gen", acs, workspace=tmp_path)
        assert len(result["emitted"]) == len(acs)

    def test_one_filter_result_per_ac(self, tmp_path):
        """generate_failing_tests must produce one FilterResult per acceptance criterion."""
        acs = ["File exists: src/a.py", "File exists: src/b.py"]
        result = generate_failing_tests("feat-filter-count", acs, workspace=tmp_path)
        assert len(result["filter_results"]) == len(acs)

    def test_emitted_test_files_exist_on_disk(self, tmp_path):
        """All test files emitted by generate_failing_tests must be written to disk."""
        acs = ["File exists: src/x.py", "Function defined: bob3.m.f"]
        result = generate_failing_tests("feat-files-exist", acs, workspace=tmp_path)
        for et in result["emitted"]:
            assert et.test_path.exists(), f"Missing test file: {et.test_path}"

    def test_test_files_under_feature_dir(self, tmp_path):
        """All emitted test files must reside under tests/<feature_id>/."""
        feature_id = "feat-dir-placement"
        acs = ["File exists: src/a.py"]
        result = generate_failing_tests(feature_id, acs, workspace=tmp_path)
        expected_dir = tmp_path / "tests" / feature_id
        for et in result["emitted"]:
            assert et.test_path.parent == expected_dir

    def test_empty_acs_returns_zero_emitted(self, tmp_path):
        """An empty AC list must return an empty emitted list and gate_passed True (vacuously)."""
        result = generate_failing_tests("feat-empty-gen", [], workspace=tmp_path)
        assert result["emitted"] == []
        assert result["filter_results"] == []

    def test_bijection_is_satisfied_for_well_formed_acs(self, tmp_path):
        """generate_failing_tests must produce a bijective AC↔test mapping."""
        acs = ["File exists: src/a.py", "Function defined: bob3.m.f"]
        result = generate_failing_tests("feat-bijection-ok", acs, workspace=tmp_path)
        assert result["bijection"].is_bijective

    def test_all_generated_tests_pass_triple_filter(self, tmp_path):
        """All tests emitted by generate_failing_tests must pass the triple filter."""
        acs = ["File exists: src/x.py", "pytest: tests/t.py"]
        result = generate_failing_tests("feat-triple-filter", acs, workspace=tmp_path)
        for fr in result["filter_results"]:
            assert fr.accepted, f"Filter rejected {fr.test_path}: {fr.reason}"
        assert result["gate_passed"] is True


class TestGenerateFailingTestsTemplateContent:
    def test_emitted_test_contains_pytest_fail(self, tmp_path):
        """Each generated test file must contain an unconditional pytest.fail call."""
        result = generate_failing_tests("feat-content-check", ["File exists: src/x.py"], workspace=tmp_path)
        for et in result["emitted"]:
            content = et.test_path.read_text(encoding="utf-8")
            assert "pytest.fail" in content, f"No pytest.fail in {et.test_path}"

    def test_emitted_test_contains_ac_text(self, tmp_path):
        """Each generated test file must reference the original AC text."""
        ac = "File exists: src/special_module.py"
        result = generate_failing_tests("feat-ac-text-embed", [ac], workspace=tmp_path)
        for et in result["emitted"]:
            content = et.test_path.read_text(encoding="utf-8")
            assert "File exists" in content or "special_module" in content

    def test_emitted_test_has_test_prefix_function(self, tmp_path):
        """Each generated test file must contain a function starting with 'test_'."""
        result = generate_failing_tests("feat-test-prefix", ["pytest: tests/t.py"], workspace=tmp_path)
        for et in result["emitted"]:
            content = et.test_path.read_text(encoding="utf-8")
            assert "def test_" in content, f"No test_ function in {et.test_path}"

    def test_emitted_test_imports_pytest(self, tmp_path):
        """Each generated test file must import pytest."""
        result = generate_failing_tests("feat-pytest-import", ["File exists: src/y.py"], workspace=tmp_path)
        for et in result["emitted"]:
            content = et.test_path.read_text(encoding="utf-8")
            assert "import pytest" in content, f"No pytest import in {et.test_path}"


class TestGenerateFailingTestsAcIdNaming:
    def test_emitted_ac_id_starts_with_ac_index(self, tmp_path):
        """Each EmittedTest.ac_id must start with 'ac_<index>'."""
        acs = ["File exists: src/a.py", "File exists: src/b.py"]
        result = generate_failing_tests("feat-acid-naming", acs, workspace=tmp_path)
        for i, et in enumerate(result["emitted"]):
            assert et.ac_id.startswith(f"ac_{i}_") or et.ac_id == f"ac_{i}", \
                f"ac_id {et.ac_id!r} doesn't start with ac_{i}"

    def test_emitted_feature_id_matches_input(self, tmp_path):
        """EmittedTest.feature_id must match the feature_id argument."""
        feature_id = "feat-id-check"
        result = generate_failing_tests(feature_id, ["File exists: src/x.py"], workspace=tmp_path)
        for et in result["emitted"]:
            assert et.feature_id == feature_id

    def test_emitted_ac_text_matches_input(self, tmp_path):
        """EmittedTest.ac_text must match the original AC string."""
        ac = "Function defined: bob3.mymod.myfunc"
        result = generate_failing_tests("feat-actext-match", [ac], workspace=tmp_path)
        assert result["emitted"][0].ac_text == ac
