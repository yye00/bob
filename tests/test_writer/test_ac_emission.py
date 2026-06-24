"""Tests for test_writer AC emission — one failing pytest per acceptance criterion.

Validates that emit_failing_tests and emit_failing_test write one test file per
AC under tests/<feature_id>/test_<ac_id>.py, and that each emitted file is a
genuinely red test (contains pytest.fail or real assertions that fail before
implementation).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from bob3.orchestrator.test_writer_agent import (
    EmittedTest,
    emit_failing_test,
    emit_failing_tests,
    _ac_id,
)


class TestEmitOneTestPerAC:
    """emit_failing_tests emits exactly one test file per acceptance criterion."""

    def test_single_ac_emits_one_file(self, tmp_path):
        results = emit_failing_tests("feat-emit-one", ["File exists: src/x.py"], workspace=tmp_path)
        assert len(results) == 1

    def test_three_acs_emit_three_files(self, tmp_path):
        acs = ["File exists: src/a.py", "File exists: src/b.py", "Function defined: bob3.m.f"]
        results = emit_failing_tests("feat-emit-three", acs, workspace=tmp_path)
        assert len(results) == 3

    def test_zero_acs_emits_empty_list(self, tmp_path):
        results = emit_failing_tests("feat-emit-zero", [], workspace=tmp_path)
        assert results == []

    def test_returns_emitted_test_objects(self, tmp_path):
        results = emit_failing_tests("feat-emit-obj", ["File exists: src/x.py"], workspace=tmp_path)
        assert all(isinstance(r, EmittedTest) for r in results)

    def test_files_placed_under_feature_dir(self, tmp_path):
        feature_id = "feat-emit-dir"
        results = emit_failing_tests(feature_id, ["File exists: src/x.py"], workspace=tmp_path)
        expected_dir = tmp_path / "tests" / feature_id
        for et in results:
            assert et.test_path.parent == expected_dir

    def test_all_files_exist_on_disk(self, tmp_path):
        acs = ["File exists: src/a.py", "pytest: tests/test_b.py"]
        results = emit_failing_tests("feat-emit-disk", acs, workspace=tmp_path)
        for et in results:
            assert et.test_path.exists(), f"File not written: {et.test_path}"

    def test_init_py_created_in_feature_dir(self, tmp_path):
        feature_id = "feat-emit-init"
        emit_failing_tests(feature_id, ["File exists: src/x.py"], workspace=tmp_path)
        init = tmp_path / "tests" / feature_id / "__init__.py"
        assert init.exists()

    def test_emitted_files_are_named_test_ac_id(self, tmp_path):
        feature_id = "feat-emit-name"
        ac = "File exists: src/named.py"
        results = emit_failing_tests(feature_id, [ac], workspace=tmp_path)
        expected_ac_id = _ac_id(0, ac)
        expected_name = f"test_{expected_ac_id}.py"
        assert results[0].test_path.name == expected_name

    def test_each_emitted_file_is_valid_python(self, tmp_path):
        acs = ["File exists: src/a.py", "Function defined: bob3.m.g"]
        results = emit_failing_tests("feat-emit-syntax", acs, workspace=tmp_path)
        for et in results:
            source = et.test_path.read_text()
            ast.parse(source)  # raises SyntaxError on failure

    def test_emitted_file_contains_failing_assertion(self, tmp_path):
        """Each emitted test must be red — contain pytest.fail or a real assertion."""
        acs = ["File exists: src/a.py", "Function defined: bob3.m.h"]
        results = emit_failing_tests("feat-emit-red", acs, workspace=tmp_path)
        for et in results:
            content = et.test_path.read_text()
            has_fail = "pytest.fail" in content
            has_assert = "assert " in content
            assert has_fail or has_assert, f"No failing assertion in {et.test_path}"


class TestEmitSingleAC:
    """emit_failing_test (singular) writes exactly one test for one AC."""

    def test_returns_emitted_test(self, tmp_path):
        result = emit_failing_test("feat-single-ac", 0, "File exists: src/x.py", workspace=tmp_path)
        assert isinstance(result, EmittedTest)

    def test_file_exists_after_emission(self, tmp_path):
        et = emit_failing_test("feat-single-exists", 0, "File exists: src/x.py", workspace=tmp_path)
        assert et.test_path.exists()

    def test_ac_index_stored_correctly(self, tmp_path):
        et = emit_failing_test("feat-single-idx", 2, "pytest: tests/t.py", workspace=tmp_path)
        assert et.ac_index == 2

    def test_feature_id_stored_correctly(self, tmp_path):
        et = emit_failing_test("feat-single-fid", 0, "File exists: src/x.py", workspace=tmp_path)
        assert et.feature_id == "feat-single-fid"

    def test_empty_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="feature_id"):
            emit_failing_test("", 0, "File exists: src/x.py", workspace=tmp_path)

    def test_non_string_ac_text_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="ac_text"):
            emit_failing_test("feat-type-err", 0, 42, workspace=tmp_path)  # type: ignore[arg-type]

    def test_emitted_file_is_valid_python(self, tmp_path):
        et = emit_failing_test("feat-syntax-one", 0, "Function defined: bob3.m.f", workspace=tmp_path)
        source = et.test_path.read_text()
        ast.parse(source)

    def test_emitted_file_is_red(self, tmp_path):
        et = emit_failing_test("feat-red-one", 0, "File exists: src/x.py", workspace=tmp_path)
        content = et.test_path.read_text()
        assert "pytest.fail" in content or "assert " in content
