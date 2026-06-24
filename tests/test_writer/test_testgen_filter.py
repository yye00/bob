"""Tests for the TestGen-LLM triple filter via bob.test_writer.

Validates the triple filter (compile / fails-on-stub / coverage heuristic)
as exposed through bob.test_writer.triple_filter_one and the underlying
bob.orchestrator.test_writer_agent.triple_filter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.test_writer import (
    emit_failing_test,
    triple_filter_one,
    triple_filter,
    EmittedTest,
    FilterResult,
)
from bob.orchestrator.test_writer_agent import (
    _check_compiles,
    _check_raises_coverage,
    _ast_stub_check,
)


class TestTripleFilterOne:
    def test_accepts_well_formed_emitted_test(self, tmp_path):
        """triple_filter_one must accept a test emitted by emit_failing_test."""
        et = emit_failing_test("feat-accept", 0, "File exists: src/x.py", workspace=tmp_path)
        result = triple_filter_one(et, workspace=tmp_path)
        assert isinstance(result, FilterResult)
        assert result.accepted, f"Expected accepted, got reason: {result.reason}"

    def test_returns_filter_result(self, tmp_path):
        """triple_filter_one must return a FilterResult instance."""
        et = emit_failing_test("feat-result-type", 0, "pytest: tests/t.py", workspace=tmp_path)
        result = triple_filter_one(et, workspace=tmp_path)
        assert isinstance(result, FilterResult)

    def test_rejects_uncompilable_test(self, tmp_path):
        """triple_filter_one must reject a test with a SyntaxError."""
        et = emit_failing_test("feat-bad-syntax", 0, "File exists: src/x.py", workspace=tmp_path)
        et.test_path.write_text("def broken(:\n    pass\n", encoding="utf-8")
        result = triple_filter_one(et, workspace=tmp_path)
        assert not result.accepted
        assert not result.compiles

    def test_rejects_always_passing_test(self, tmp_path):
        """triple_filter_one must reject a test that passes on stub code."""
        et = emit_failing_test("feat-passes-stub", 0, "File exists: src/x.py", workspace=tmp_path)
        et.test_path.write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
        result = triple_filter_one(et, workspace=tmp_path)
        assert not result.accepted
        assert not result.fails_on_stub

    def test_rejects_no_coverage_uplift(self, tmp_path):
        """triple_filter_one must reject a test with only pass (no coverage)."""
        et = emit_failing_test("feat-no-cov", 0, "File exists: src/x.py", workspace=tmp_path)
        et.test_path.write_text("def test_noop():\n    pass\n", encoding="utf-8")
        result = triple_filter_one(et, workspace=tmp_path)
        assert not result.accepted

    def test_non_emitted_test_raises_value_error(self, tmp_path):
        """triple_filter_one must raise ValueError for non-EmittedTest input."""
        with pytest.raises(ValueError, match="EmittedTest"):
            triple_filter_one("not-an-emitted-test", workspace=tmp_path)  # type: ignore[arg-type]

    def test_accepted_test_has_all_checks_true(self, tmp_path):
        """An accepted test must have compiles, fails_on_stub, raises_coverage all True."""
        et = emit_failing_test("feat-all-true", 0, "Function defined: bob.m.f", workspace=tmp_path)
        result = triple_filter_one(et, workspace=tmp_path)
        assert result.compiles
        assert result.fails_on_stub
        assert result.raises_coverage
        assert result.accepted

    def test_result_ac_id_matches_emitted(self, tmp_path):
        """FilterResult.ac_id must match EmittedTest.ac_id."""
        et = emit_failing_test("feat-ac-id-match", 0, "File exists: src/z.py", workspace=tmp_path)
        result = triple_filter_one(et, workspace=tmp_path)
        assert result.ac_id == et.ac_id

    def test_result_test_path_matches_emitted(self, tmp_path):
        """FilterResult.test_path must match EmittedTest.test_path."""
        et = emit_failing_test("feat-path-match", 0, "File exists: src/q.py", workspace=tmp_path)
        result = triple_filter_one(et, workspace=tmp_path)
        assert result.test_path == et.test_path


class TestTripleFilter:
    def test_empty_list_returns_empty_list(self, tmp_path):
        """triple_filter with empty input must return an empty list."""
        results = triple_filter([], workspace=tmp_path)
        assert results == []

    def test_one_test_returns_one_result(self, tmp_path):
        """triple_filter with one test must return exactly one result."""
        et = emit_failing_test("feat-one", 0, "File exists: src/x.py", workspace=tmp_path)
        results = triple_filter([et], workspace=tmp_path)
        assert len(results) == 1

    def test_multiple_tests_return_same_count(self, tmp_path):
        """triple_filter must return one result per input test."""
        ets = [
            emit_failing_test("feat-multi-filter", i, f"File exists: src/f{i}.py", workspace=tmp_path)
            for i in range(3)
        ]
        results = triple_filter(ets, workspace=tmp_path)
        assert len(results) == 3

    def test_all_emitted_tests_accepted(self, tmp_path):
        """All tests emitted by emit_failing_test must be accepted by triple_filter."""
        ets = [
            emit_failing_test("feat-all-accept", i, ac, workspace=tmp_path)
            for i, ac in enumerate(["File exists: src/a.py", "pytest: tests/t.py"])
        ]
        results = triple_filter(ets, workspace=tmp_path)
        for r in results:
            assert r.accepted, f"Expected {r.test_path} accepted, got: {r.reason}"


class TestAstStubCheck:
    def test_pytest_fail_call_is_definitively_red(self, tmp_path):
        """_ast_stub_check must return True for tests with unconditional pytest.fail."""
        f = tmp_path / "t.py"
        f.write_text(
            "import pytest\ndef test_red():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        assert _ast_stub_check(f) is True

    def test_assert_true_only_is_definitively_green(self, tmp_path):
        """_ast_stub_check must return False for tests with only assert True."""
        f = tmp_path / "t.py"
        f.write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
        assert _ast_stub_check(f) is False

    def test_nontrivial_assertion_returns_none(self, tmp_path):
        """_ast_stub_check returns None for tests with non-trivial assertions (ambiguous)."""
        f = tmp_path / "t.py"
        f.write_text(
            "def test_val():\n    assert 1 + 1 == 3\n",
            encoding="utf-8",
        )
        result = _ast_stub_check(f)
        # Could be None (ambiguous) or True (non-trivial raise) — not False
        assert result is not False


class TestCheckCompiles:
    def test_valid_file_returns_true(self, tmp_path):
        """_check_compiles must return True for syntactically valid files."""
        f = tmp_path / "valid.py"
        f.write_text("import pytest\n", encoding="utf-8")
        assert _check_compiles(f) is True

    def test_syntax_error_returns_false(self, tmp_path):
        """_check_compiles must return False for files with SyntaxError."""
        f = tmp_path / "broken.py"
        f.write_text("def broken(:\n    pass\n", encoding="utf-8")
        assert _check_compiles(f) is False


class TestCheckRaisesCoverage:
    def test_pytest_fail_call_passes(self, tmp_path):
        """_check_raises_coverage must return True for pytest.fail calls."""
        f = tmp_path / "t.py"
        f.write_text(
            "import pytest\ndef test_red():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(f) is True

    def test_non_pytest_import_passes(self, tmp_path):
        """_check_raises_coverage must return True for non-pytest imports."""
        f = tmp_path / "t.py"
        f.write_text("import os\ndef test_something():\n    pass\n", encoding="utf-8")
        assert _check_raises_coverage(f) is True

    def test_only_pass_fails(self, tmp_path):
        """_check_raises_coverage must return False for tests with only pass."""
        f = tmp_path / "t.py"
        f.write_text("def test_noop():\n    pass\n", encoding="utf-8")
        assert _check_raises_coverage(f) is False

    def test_assert_true_only_fails(self, tmp_path):
        """_check_raises_coverage must return False for tests with only assert True."""
        f = tmp_path / "t.py"
        f.write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
        assert _check_raises_coverage(f) is False
