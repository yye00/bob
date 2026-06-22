"""Tests verifying the Build (compilation) check of the TestGen-LLM triple filter.

The triple filter's first leg rejects test files that fail to compile —
those with SyntaxError or ImportError at collection time.
"""

from __future__ import annotations

import pytest

from bob3.orchestrator.test_writer_agent import (
    UncompilableTestError,
    _check_compiles,
    reject_uncompilable,
)
from bob3.test_writer_subagent import emit_failing_test, generate_failing_tests


class TestTestgenBuildFilter:
    def test_valid_python_passes_build_check(self, tmp_path):
        """A syntactically valid test file must pass the build (compile) check."""
        f = tmp_path / "test_valid.py"
        f.write_text("import pytest\n\ndef test_red():\n    pytest.fail('not yet')\n")
        assert _check_compiles(f) is True

    def test_syntax_error_fails_build_check(self, tmp_path):
        """A file with SyntaxError must fail the build check."""
        f = tmp_path / "test_broken.py"
        f.write_text("def broken(\n")
        assert _check_compiles(f) is False

    def test_incomplete_class_fails_build_check(self, tmp_path):
        """A class definition missing the colon must fail the build check."""
        f = tmp_path / "test_no_colon.py"
        f.write_text("class Bad\n    pass\n")
        assert _check_compiles(f) is False

    def test_empty_file_passes_build_check(self, tmp_path):
        """An empty file is valid Python and must pass the build check."""
        f = tmp_path / "test_empty.py"
        f.write_text("")
        assert _check_compiles(f) is True

    def test_reject_uncompilable_raises_for_broken_file(self, tmp_path):
        """reject_uncompilable must raise UncompilableTestError for files with SyntaxError."""
        f = tmp_path / "test_bad.py"
        f.write_text("class Bad\n")
        with pytest.raises(UncompilableTestError):
            reject_uncompilable(f)

    def test_reject_uncompilable_silent_for_valid_file(self, tmp_path):
        """reject_uncompilable must not raise for a syntactically valid file."""
        f = tmp_path / "test_ok.py"
        f.write_text("def test_pass():\n    assert 1 == 1\n")
        reject_uncompilable(f)

    def test_emitted_tests_pass_build_filter(self, tmp_path):
        """Tests emitted by generate_failing_tests must always pass the build check."""
        acs = [
            "File exists: src/bob3/build_filter_target.py",
            "Function defined: bob3.build_filter_target.fn",
        ]
        result = generate_failing_tests("feat-build-filter", acs, workspace=tmp_path)
        for fr in result["filter_results"]:
            assert fr.compiles is True, (
                f"Emitted test {fr.test_path} failed build filter"
            )

    def test_emit_failing_test_produces_compilable_file(self, tmp_path):
        """emit_failing_test must produce a file that passes the build check."""
        et = emit_failing_test(
            "feat-build-single",
            0,
            "File exists: src/bob3/build_single.py",
            workspace=tmp_path,
        )
        assert _check_compiles(et.test_path) is True

    def test_filter_result_compiles_field_is_bool(self, tmp_path):
        """Each FilterResult must have compiles as a bool."""
        result = generate_failing_tests(
            "feat-build-bool",
            ["File exists: src/bob3/build_bool.py"],
            workspace=tmp_path,
        )
        for fr in result["filter_results"]:
            assert isinstance(fr.compiles, bool)
