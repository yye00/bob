"""Tests verifying generate_failing_tests emits one failing pytest per AC.

Covers the core contract: one-to-one mapping between acceptance criteria and
emitted test files, with each test guaranteed to fail on stub code.
"""

from __future__ import annotations

import pytest

from bob.test_writer_subagent import generate_failing_tests


class TestGeneratesFailingTests:
    def test_single_ac_emits_one_test(self, tmp_path):
        """A single AC must produce exactly one emitted failing test."""
        result = generate_failing_tests(
            "feat-gft-single",
            ["File exists: src/bob/target.py"],
            workspace=tmp_path,
        )
        assert len(result["emitted"]) == 1

    def test_multiple_acs_emit_multiple_tests(self, tmp_path):
        """Each AC must map to exactly one emitted test."""
        acs = [
            "File exists: src/bob/mod_a.py",
            "Function defined: bob.mod_a.func_a",
            "pytest: tests/test_mod_a.py",
        ]
        result = generate_failing_tests("feat-gft-multi", acs, workspace=tmp_path)
        assert len(result["emitted"]) == len(acs)

    def test_emitted_tests_are_under_tests_feature_id_directory(self, tmp_path):
        """Emitted tests must be placed under tests/<feature_id>/test_<ac_id>.py."""
        feature_id = "feat-gft-path-check"
        result = generate_failing_tests(
            feature_id,
            ["File exists: src/bob/path_check.py"],
            workspace=tmp_path,
        )
        for et in result["emitted"]:
            assert feature_id in str(et.test_path)
            assert et.test_path.suffix == ".py"
            assert et.test_path.exists()

    def test_result_has_required_keys(self, tmp_path):
        """Return dict must contain emitted, filter_results, bijection, gate_passed."""
        result = generate_failing_tests(
            "feat-gft-keys",
            ["File exists: src/bob/keys_check.py"],
            workspace=tmp_path,
        )
        for key in ("emitted", "filter_results", "bijection", "gate_passed"):
            assert key in result, f"Missing key: {key}"

    def test_emitted_test_feature_id_matches(self, tmp_path):
        """Each EmittedTest.feature_id must match the requested feature_id."""
        feature_id = "feat-gft-id"
        result = generate_failing_tests(
            feature_id,
            ["File exists: src/bob/id_check.py"],
            workspace=tmp_path,
        )
        for et in result["emitted"]:
            assert et.feature_id == feature_id

    def test_emitted_ac_index_is_sequential(self, tmp_path):
        """EmittedTest.ac_index must be 0-based and sequential."""
        acs = [
            "File exists: src/bob/seq_a.py",
            "File exists: src/bob/seq_b.py",
        ]
        result = generate_failing_tests("feat-gft-seq", acs, workspace=tmp_path)
        for idx, et in enumerate(result["emitted"]):
            assert et.ac_index == idx

    def test_filter_results_length_matches_emitted(self, tmp_path):
        """filter_results must have the same length as emitted."""
        acs = ["File exists: src/bob/fr_a.py", "File exists: src/bob/fr_b.py"]
        result = generate_failing_tests("feat-gft-fr-count", acs, workspace=tmp_path)
        assert len(result["emitted"]) == len(result["filter_results"])

    def test_bijection_satisfied(self, tmp_path):
        """verify_bijection must report is_bijective=True after emission."""
        result = generate_failing_tests(
            "feat-gft-bijection",
            ["File exists: src/bob/bij.py", "Function defined: bob.bij.fn"],
            workspace=tmp_path,
        )
        assert result["bijection"].is_bijective is True

    def test_gate_passed_true_for_valid_acs(self, tmp_path):
        """gate_passed must be True when all triple-filter checks pass."""
        result = generate_failing_tests(
            "feat-gft-gate",
            ["File exists: src/bob/gate_check.py"],
            workspace=tmp_path,
        )
        assert result["gate_passed"] is True

    def test_empty_acs_returns_empty_emitted_and_gate_passed(self, tmp_path):
        """Zero ACs must return empty emitted list and gate_passed=True."""
        result = generate_failing_tests("feat-gft-zero", [], workspace=tmp_path)
        assert result["emitted"] == []
        assert result["filter_results"] == []
        assert result["gate_passed"] is True
        assert result["bijection"].is_bijective is True
