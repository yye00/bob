"""Tests for AC execution — verifying that emitted tests execute and fail as expected.

The test-writer sub-agent emits genuinely red tests per AC.  This module
verifies that those tests actually execute (are importable, collectable by
pytest) and fail before implementation is in place.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from bob.orchestrator.test_writer_agent import (
    EmittedTest,
    FilterResult,
    emit_failing_test,
    emit_failing_tests,
    triple_filter,
    generate_failing_tests,
)
from bob.test_writer import generate_failing_test


class TestGenerateFailingTestFunction:
    """Tests for bob.test_writer.generate_failing_test (singular)."""

    def test_returns_emitted_test_instance(self, tmp_path):
        result = generate_failing_test("feat-exec-1", 0, "File exists: src/x.py", workspace=tmp_path)
        assert isinstance(result, EmittedTest)

    def test_file_written_to_disk(self, tmp_path):
        result = generate_failing_test("feat-exec-2", 0, "File exists: src/y.py", workspace=tmp_path)
        assert result.test_path.exists()

    def test_file_under_feature_dir(self, tmp_path):
        feature_id = "feat-exec-dir"
        result = generate_failing_test(feature_id, 0, "File exists: src/x.py", workspace=tmp_path)
        expected_parent = tmp_path / "tests" / feature_id
        assert result.test_path.parent == expected_parent

    def test_emitted_file_is_valid_python(self, tmp_path):
        result = generate_failing_test("feat-exec-syntax", 0, "Function defined: bob.m.f", workspace=tmp_path)
        source = result.test_path.read_text(encoding="utf-8")
        ast.parse(source)

    def test_emitted_file_contains_pytest_fail(self, tmp_path):
        result = generate_failing_test("feat-exec-red", 0, "File exists: src/z.py", workspace=tmp_path)
        content = result.test_path.read_text(encoding="utf-8")
        assert "pytest.fail" in content or "assert " in content

    def test_ac_index_propagated(self, tmp_path):
        result = generate_failing_test("feat-exec-idx", 3, "File exists: src/x.py", workspace=tmp_path)
        assert result.ac_index == 3

    def test_feature_id_propagated(self, tmp_path):
        feature_id = "feat-exec-fid-check"
        result = generate_failing_test(feature_id, 0, "File exists: src/x.py", workspace=tmp_path)
        assert result.feature_id == feature_id

    def test_empty_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="feature_id"):
            generate_failing_test("", 0, "File exists: src/x.py", workspace=tmp_path)

    def test_non_string_ac_text_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="ac_text"):
            generate_failing_test("feat-exec-type", 0, 99, workspace=tmp_path)  # type: ignore[arg-type]

    def test_init_py_created(self, tmp_path):
        feature_id = "feat-exec-init"
        generate_failing_test(feature_id, 0, "File exists: src/x.py", workspace=tmp_path)
        assert (tmp_path / "tests" / feature_id / "__init__.py").exists()


class TestEmittedTestExecution:
    """Emitted tests must actually fail when collected by pytest."""

    def test_triple_filter_accepts_emitted_test(self, tmp_path):
        result = generate_failing_test("feat-exec-filter", 0, "File exists: src/x.py", workspace=tmp_path)
        filter_results = triple_filter([result], workspace=tmp_path)
        assert len(filter_results) == 1
        fr = filter_results[0]
        assert fr.compiles is True

    def test_generate_failing_tests_pipeline_runs(self, tmp_path):
        out = generate_failing_tests(
            "feat-exec-pipeline",
            ["File exists: src/a.py", "Function defined: bob.m.g"],
            workspace=tmp_path,
        )
        assert len(out["emitted"]) == 2
        assert len(out["filter_results"]) == 2
        assert out["bijection"].is_bijective is True

    def test_multiple_acs_emit_multiple_tests(self, tmp_path):
        acs = [
            "File exists: src/p.py",
            "File exists: src/q.py",
            "Function defined: bob.m.h",
        ]
        results = emit_failing_tests("feat-exec-multi", acs, workspace=tmp_path)
        assert len(results) == 3
        for et in results:
            assert et.test_path.exists()

    def test_all_emitted_tests_are_valid_python(self, tmp_path):
        acs = ["File exists: src/a.py", "pytest: tests/test_b.py"]
        results = emit_failing_tests("feat-exec-syntax-all", acs, workspace=tmp_path)
        for et in results:
            source = et.test_path.read_text(encoding="utf-8")
            ast.parse(source)
