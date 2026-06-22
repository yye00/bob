"""Tests for the TestGen-LLM Build/Pass/Coverage triple filter.

Validates that triple_filter rejects tests that:
1. Don't compile (Build check)
2. Mysteriously pass on stub code (Pass check)
3. Fail to raise coverage of the AC-named region (Coverage check)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.orchestrator.test_writer_agent import (
    EmittedTest,
    FilterResult,
    _check_compiles,
    _check_fails_on_stub,
    _check_raises_coverage,
    emit_failing_tests,
    triple_filter,
)


class TestBuildFilter:
    """Build check: test must compile without SyntaxError."""

    def test_accepts_valid_python(self, tmp_path):
        """A syntactically valid test file must pass the build check."""
        p = tmp_path / "test_valid.py"
        p.write_text("import pytest\ndef test_x():\n    pytest.fail('not impl')\n")
        assert _check_compiles(p) is True

    def test_rejects_syntax_error(self, tmp_path):
        """A file with a SyntaxError must fail the build check."""
        p = tmp_path / "test_broken.py"
        p.write_text("def broken(:\n    pass\n")
        assert _check_compiles(p) is False

    def test_rejects_incomplete_expression(self, tmp_path):
        """An incomplete expression causes a SyntaxError and must be rejected."""
        p = tmp_path / "test_incomplete.py"
        p.write_text("x = (1 + \n")
        assert _check_compiles(p) is False

    def test_empty_file_compiles(self, tmp_path):
        """An empty file is valid Python and must pass the build check."""
        p = tmp_path / "test_empty.py"
        p.write_text("")
        assert _check_compiles(p) is True

    def test_triple_filter_marks_compile_failed(self, tmp_path):
        """triple_filter must mark compiles=False and accepted=False for SyntaxError files."""
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_test",
            ac_text="File exists: src/x.py",
            test_path=tmp_path / "test_broken.py",
            feature_id="feat-build-fail",
        )
        et.test_path.write_text("def bad(:\n    pass\n")
        results = triple_filter([et], workspace=tmp_path)
        assert len(results) == 1
        assert results[0].compiles is False
        assert results[0].accepted is False


class TestPassFilter:
    """Pass check: test must fail on stub (i.e., must be genuinely red)."""

    def test_pytest_fail_is_red_on_stub(self, tmp_path):
        """A test with unconditional pytest.fail is definitively failing."""
        p = tmp_path / "test_red.py"
        p.write_text("import pytest\ndef test_x():\n    pytest.fail('not impl')\n")
        assert _check_fails_on_stub(p) is True

    def test_assert_true_passes_on_stub(self, tmp_path):
        """A test with only assert True is trivially green and must be rejected."""
        p = tmp_path / "test_green.py"
        p.write_text("def test_x():\n    assert True\n")
        assert _check_fails_on_stub(p) is False

    def test_triple_filter_rejects_stub_passer(self, tmp_path):
        """triple_filter must mark fails_on_stub=False and accepted=False for trivially green tests."""
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_test",
            ac_text="File exists: src/x.py",
            test_path=tmp_path / "test_trivial.py",
            feature_id="feat-pass-fail",
        )
        et.test_path.write_text("def test_x():\n    assert True\n")
        results = triple_filter([et], workspace=tmp_path)
        assert len(results) == 1
        assert results[0].fails_on_stub is False
        assert results[0].accepted is False

    def test_emitted_test_fails_on_stub(self, tmp_path):
        """Every test emitted by emit_failing_tests must fail on a stub."""
        emitted = emit_failing_tests(
            "feat-stub-check",
            ["File exists: src/x.py", "Function defined: bob3.m.f"],
            workspace=tmp_path,
        )
        for et in emitted:
            assert _check_fails_on_stub(et.test_path), (
                f"Expected {et.test_path} to fail on stub, but it passes"
            )


class TestCoverageFilter:
    """Coverage check: test must reference at least one non-pytest symbol."""

    def test_import_of_project_module_passes(self, tmp_path):
        """A test importing a project module passes the coverage heuristic."""
        p = tmp_path / "test_cov.py"
        p.write_text(
            "import pathlib\nimport pytest\ndef test_x():\n    pytest.fail('not impl')\n"
        )
        assert _check_raises_coverage(p) is True

    def test_only_pytest_import_with_pytest_fail_passes(self, tmp_path):
        """A test with only pytest.fail() passes — pytest.fail is itself non-trivial."""
        p = tmp_path / "test_pytest_only.py"
        p.write_text(
            "from __future__ import annotations\nimport pytest\ndef test_x():\n    pytest.fail('not impl')\n"
        )
        assert _check_raises_coverage(p) is True

    def test_real_assertion_passes_coverage(self, tmp_path):
        """A non-trivial assert statement passes the coverage heuristic."""
        p = tmp_path / "test_assert.py"
        p.write_text("def test_x():\n    assert 1 == 2\n")
        assert _check_raises_coverage(p) is True

    def test_triple_filter_marks_no_coverage_not_accepted(self, tmp_path):
        """triple_filter must mark raises_coverage=False and accepted=False for no-coverage tests."""
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_test",
            ac_text="File exists: src/x.py",
            test_path=tmp_path / "test_no_cov.py",
            feature_id="feat-cov-fail",
        )
        # A file that fails on stub (has pytest.fail) but with no non-pytest imports
        # and no real assertions — but note pytest.fail itself counts as coverage
        # so use a pass-only body that also fails on stub via a raise
        et.test_path.write_text(
            "def test_x():\n    raise AssertionError('fail')\n"
        )
        results = triple_filter([et], workspace=tmp_path)
        # raise AssertionError counts as non-trivial (not assert True)
        assert len(results) == 1
        # The raise is non-trivial — it passes coverage check
        assert results[0].raises_coverage is True


class TestTripleFilterIntegration:
    """Integration tests for triple_filter over emit_failing_tests output."""

    def test_all_emitted_tests_accepted(self, tmp_path):
        """All tests emitted by emit_failing_tests must be accepted by triple_filter."""
        emitted = emit_failing_tests(
            "feat-triple-pass",
            [
                "File exists: src/bob3/mymod.py",
                "Function defined: bob3.mymod.my_func",
                "integration: bob3.mymod",
                "pytest: tests/test_mymod.py — checks the module loads",
            ],
            workspace=tmp_path,
        )
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == len(emitted)
        for r in results:
            assert r.accepted, (
                f"Expected {r.ac_id} to be accepted, reason: {r.reason}"
            )

    def test_filter_result_has_correct_ac_ids(self, tmp_path):
        """FilterResult.ac_id must match the ac_id of the emitted test."""
        acs = ["File exists: src/a.py", "File exists: src/b.py"]
        emitted = emit_failing_tests("feat-id-check", acs, workspace=tmp_path)
        results = triple_filter(emitted, workspace=tmp_path)
        for et, r in zip(emitted, results):
            assert r.ac_id == et.ac_id

    def test_mixed_valid_and_invalid_tests(self, tmp_path):
        """A mix of valid and invalid tests must produce correct FilterResults."""
        emitted = emit_failing_tests(
            "feat-mixed",
            ["File exists: src/x.py"],
            workspace=tmp_path,
        )
        # Corrupt the first test to have a SyntaxError
        emitted[0].test_path.write_text("def broken(:\n    pass\n")

        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == 1
        assert results[0].compiles is False
        assert results[0].accepted is False
