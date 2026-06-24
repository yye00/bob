"""Tests verifying that generate_failing_tests emits exactly one test per AC.

Covers the core contract: one-to-one mapping between acceptance criteria and
emitted test files, with the bijection check satisfied.
"""

from __future__ import annotations

import pytest

from bob.test_writer_subagent import generate_failing_tests


class TestGeneratesOneTestPerAc:
    def test_two_acs_produce_two_emitted_tests(self, tmp_path):
        """Each AC must produce exactly one emitted test file."""
        acs = [
            "File exists: src/bob/my_module.py",
            "Function defined: bob.my_module.my_func",
        ]
        result = generate_failing_tests("feat-two-acs", acs, workspace=tmp_path)
        assert len(result["emitted"]) == 2, (
            f"Expected 2 emitted tests, got {len(result['emitted'])}"
        )

    def test_five_acs_produce_five_emitted_tests(self, tmp_path):
        """Five ACs must produce five test files, no more, no less."""
        acs = [f"File exists: src/bob/module_{i}.py" for i in range(5)]
        result = generate_failing_tests("feat-five-acs", acs, workspace=tmp_path)
        assert len(result["emitted"]) == 5

    def test_each_emitted_test_file_exists_on_disk(self, tmp_path):
        """Every EmittedTest.test_path must refer to an existing file."""
        acs = ["File exists: src/bob/a.py", "File exists: src/bob/b.py"]
        result = generate_failing_tests("feat-disk-check", acs, workspace=tmp_path)
        for et in result["emitted"]:
            assert et.test_path.exists(), f"Expected {et.test_path} to exist on disk"

    def test_emitted_tests_are_under_feature_id_subdirectory(self, tmp_path):
        """Emitted tests must be placed under tests/<feature_id>/."""
        feature_id = "feat-subdir-check"
        acs = ["File exists: src/bob/c.py"]
        result = generate_failing_tests(feature_id, acs, workspace=tmp_path)
        for et in result["emitted"]:
            assert feature_id in str(et.test_path), (
                f"Expected {et.test_path} to be under tests/{feature_id}/"
            )

    def test_bijection_is_satisfied_for_multiple_acs(self, tmp_path):
        """verify_bijection must report is_bijective=True after emission."""
        acs = [
            "File exists: src/bob/x.py",
            "Function defined: bob.x.do_thing",
            "integration: bob.orchestrator",
        ]
        result = generate_failing_tests("feat-bijection", acs, workspace=tmp_path)
        assert result["bijection"].is_bijective is True, (
            f"Bijection not satisfied: missing={result['bijection'].missing_tests}, "
            f"orphans={result['bijection'].orphan_tests}"
        )

    def test_emitted_count_matches_filter_result_count(self, tmp_path):
        """filter_results must have the same length as emitted."""
        acs = ["File exists: src/a.py", "File exists: src/b.py", "File exists: src/c.py"]
        result = generate_failing_tests("feat-count-match", acs, workspace=tmp_path)
        assert len(result["emitted"]) == len(result["filter_results"]), (
            "emitted and filter_results must have the same length"
        )

    def test_empty_acs_yields_zero_emitted_and_bijective(self, tmp_path):
        """Zero ACs must yield an empty emitted list and a satisfied bijection."""
        result = generate_failing_tests("feat-zero-acs", [], workspace=tmp_path)
        assert result["emitted"] == []
        assert result["filter_results"] == []
        assert result["bijection"].is_bijective is True

    def test_result_dict_has_required_keys(self, tmp_path):
        """Return dict must contain emitted, filter_results, bijection, gate_passed."""
        result = generate_failing_tests("feat-keys", ["File exists: src/x.py"], workspace=tmp_path)
        for key in ("emitted", "filter_results", "bijection", "gate_passed"):
            assert key in result, f"Missing required key: {key}"

    def test_each_emitted_test_has_correct_feature_id(self, tmp_path):
        """Each EmittedTest.feature_id must match the requested feature_id."""
        feature_id = "feat-id-check"
        acs = ["File exists: src/z.py"]
        result = generate_failing_tests(feature_id, acs, workspace=tmp_path)
        for et in result["emitted"]:
            assert et.feature_id == feature_id

    def test_each_emitted_test_ac_index_is_sequential(self, tmp_path):
        """EmittedTest.ac_index must be 0-based and sequential."""
        acs = ["File exists: src/a.py", "File exists: src/b.py", "File exists: src/c.py"]
        result = generate_failing_tests("feat-sequential", acs, workspace=tmp_path)
        for expected_idx, et in enumerate(result["emitted"]):
            assert et.ac_index == expected_idx, (
                f"Expected ac_index={expected_idx}, got {et.ac_index}"
            )
