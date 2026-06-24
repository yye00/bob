"""Tests for bob3.test_writer — the public API of the test-writer sub-agent.

Covers:
- generate_failing_tests (the required AC function)
- emit_failing_test (single-AC entry point)
- triple_filter_one (single-test filter wrapper)
- spawn_test_writer_subagent (orchestrator entry point)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.test_writer import (
    BijectionReport,
    EmittedTest,
    FilterResult,
    emit_failing_test,
    emit_failing_tests,
    generate_failing_tests,
    spawn_test_writer_subagent,
    triple_filter,
    triple_filter_one,
    verify_bijection,
)


class TestGenerateFailingTests:
    """Tests for the generate_failing_tests function (primary AC)."""

    def test_returns_dict_with_required_keys(self, tmp_path):
        acs = ["File exists: src/bob3/test_writer.py"]
        result = generate_failing_tests("feat-tw-001", acs, workspace=tmp_path)
        assert isinstance(result, dict)
        assert "emitted" in result
        assert "filter_results" in result
        assert "bijection" in result
        assert "gate_passed" in result

    def test_one_ac_produces_one_emitted_test(self, tmp_path):
        acs = ["Function defined: bob3.test_writer.generate_failing_tests"]
        result = generate_failing_tests("feat-tw-002", acs, workspace=tmp_path)
        assert len(result["emitted"]) == 1
        assert len(result["filter_results"]) == 1

    def test_multiple_acs_produce_matching_counts(self, tmp_path):
        acs = [
            "File exists: src/bob3/test_writer.py",
            "Function defined: bob3.test_writer.generate_failing_tests",
            "pytest: tests/test_test_writer.py",
        ]
        result = generate_failing_tests("feat-tw-003", acs, workspace=tmp_path)
        assert len(result["emitted"]) == 3
        assert len(result["filter_results"]) == 3

    def test_empty_acs_returns_gate_passed(self, tmp_path):
        result = generate_failing_tests("feat-tw-empty", [], workspace=tmp_path)
        assert result["emitted"] == []
        assert result["filter_results"] == []
        assert result["gate_passed"] is True
        assert result["bijection"].is_bijective is True

    def test_gate_passed_true_for_valid_acs(self, tmp_path):
        acs = ["File exists: src/bob3/test_writer.py"]
        result = generate_failing_tests("feat-tw-gate", acs, workspace=tmp_path)
        assert result["gate_passed"] is True

    def test_emitted_files_exist_on_disk(self, tmp_path):
        acs = ["File exists: src/mymod.py", "pytest: tests/test_mymod.py"]
        result = generate_failing_tests("feat-tw-disk", acs, workspace=tmp_path)
        for e in result["emitted"]:
            assert e.test_path.exists()

    def test_emitted_is_list_of_emitted_test(self, tmp_path):
        acs = ["Function defined: bob3.core.run"]
        result = generate_failing_tests("feat-tw-types", acs, workspace=tmp_path)
        assert all(isinstance(e, EmittedTest) for e in result["emitted"])

    def test_filter_results_is_list_of_filter_result(self, tmp_path):
        acs = ["Function defined: bob3.core.run"]
        result = generate_failing_tests("feat-tw-frtypes", acs, workspace=tmp_path)
        assert all(isinstance(r, FilterResult) for r in result["filter_results"])

    def test_bijection_is_bijection_report(self, tmp_path):
        acs = ["File exists: src/bob3/test_writer.py"]
        result = generate_failing_tests("feat-tw-bij", acs, workspace=tmp_path)
        assert isinstance(result["bijection"], BijectionReport)

    def test_bijection_satisfied_after_generation(self, tmp_path):
        acs = ["File exists: src/a.py", "Function defined: bob3.a.fn"]
        result = generate_failing_tests("feat-tw-bijsatisfied", acs, workspace=tmp_path)
        assert result["bijection"].is_bijective is True
        assert result["bijection"].missing_tests == []
        assert result["bijection"].orphan_tests == []

    def test_empty_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="feature_id"):
            generate_failing_tests("", ["File exists: src/x.py"], workspace=tmp_path)

    def test_whitespace_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="feature_id"):
            generate_failing_tests("   ", ["File exists: src/x.py"], workspace=tmp_path)

    def test_non_list_acs_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            generate_failing_tests("feat-tw-err", "not a list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_accepts_string_workspace(self, tmp_path):
        acs = ["File exists: src/strws.py"]
        result = generate_failing_tests("feat-tw-strws", acs, workspace=str(tmp_path))
        assert len(result["emitted"]) == 1

    def test_generated_test_contains_pytest_fail(self, tmp_path):
        # Non-structural AC falls through to the RED placeholder template which uses pytest.fail.
        acs = ["Verify the widget frobs correctly"]
        result = generate_failing_tests("feat-tw-content", acs, workspace=tmp_path)
        content = result["emitted"][0].test_path.read_text()
        assert "pytest.fail" in content

    def test_output_dir_has_init_py(self, tmp_path):
        acs = ["File exists: src/init_check.py"]
        generate_failing_tests("feat-tw-init", acs, workspace=tmp_path)
        init = tmp_path / "tests" / "feat-tw-init" / "__init__.py"
        assert init.exists()


class TestEmitFailingTest:
    """Tests for the single-AC emit_failing_test entry point."""

    def test_emits_one_file(self, tmp_path):
        result = emit_failing_test(
            "feat-single", 0, "File exists: src/single.py", workspace=tmp_path
        )
        assert isinstance(result, EmittedTest)
        assert result.test_path.exists()

    def test_ac_index_zero_accepted(self, tmp_path):
        result = emit_failing_test("feat-idx0", 0, "File exists: src/x.py", workspace=tmp_path)
        assert result.ac_index == 0

    def test_empty_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="feature_id"):
            emit_failing_test("", 0, "File exists: src/x.py", workspace=tmp_path)

    def test_non_string_ac_text_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="ac_text"):
            emit_failing_test("feat-err", 0, 123, workspace=tmp_path)  # type: ignore[arg-type]

    def test_test_file_contains_feature_id(self, tmp_path):
        result = emit_failing_test(
            "feat-fid-check", 0, "File exists: src/x.py", workspace=tmp_path
        )
        content = result.test_path.read_text()
        assert "feat-fid-check" in content


class TestTripleFilterOne:
    """Tests for triple_filter_one convenience wrapper."""

    def test_accepts_valid_emitted_test(self, tmp_path):
        emitted = emit_failing_test(
            "feat-filter-one", 0, "File exists: src/x.py", workspace=tmp_path
        )
        fr = triple_filter_one(emitted, workspace=tmp_path)
        assert isinstance(fr, FilterResult)
        assert fr.accepted is True

    def test_non_emitted_test_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="EmittedTest"):
            triple_filter_one("not an EmittedTest")  # type: ignore[arg-type]


class TestSpawnTestWriterSubagent:
    """Tests for the orchestrator entry point."""

    def test_returns_dict_with_gate_passed(self, tmp_path):
        acs = ["File exists: src/bob3/test_writer.py"]
        result = spawn_test_writer_subagent("feat-spawn", acs, workspace=tmp_path)
        assert isinstance(result, dict)
        assert "gate_passed" in result
        assert result["gate_passed"] is True

    def test_empty_acs_returns_valid_result(self, tmp_path):
        result = spawn_test_writer_subagent("feat-spawn-empty", [], workspace=tmp_path)
        assert result["emitted"] == []
        assert result["gate_passed"] is True

    def test_invalid_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="feature_id"):
            spawn_test_writer_subagent("", ["File exists: src/x.py"], workspace=tmp_path)
