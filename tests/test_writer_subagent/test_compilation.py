"""Tests verifying the compilation (Build) check of the test-writer sub-agent.

The triple filter's first check rejects test files that fail to compile —
i.e., those with SyntaxError or unresolvable ImportError at collection time.
"""

from __future__ import annotations

import pytest

from bob.orchestrator.test_writer_agent import (
    UncompilableTestError,
    _check_compiles,
    reject_uncompilable,
)
from bob.test_writer_subagent import emit_failing_test, generate_failing_tests


class TestCompilationCheck:
    def test_valid_python_file_compiles(self, tmp_path):
        """A syntactically valid file must pass the compile check."""
        f = tmp_path / "test_valid.py"
        f.write_text("import pytest\n\ndef test_ok():\n    pytest.fail('red')\n")
        assert _check_compiles(f) is True

    def test_syntax_error_fails_compile_check(self, tmp_path):
        """A file with SyntaxError must fail the compile check."""
        f = tmp_path / "test_syntax_error.py"
        f.write_text("def broken(\n")
        assert _check_compiles(f) is False

    def test_missing_colon_fails_compile_check(self, tmp_path):
        """A class definition missing the colon must fail the compile check."""
        f = tmp_path / "test_missing_colon.py"
        f.write_text("class Bad\n    pass\n")
        assert _check_compiles(f) is False

    def test_empty_file_compiles(self, tmp_path):
        """An empty file is valid Python and must pass the compile check."""
        f = tmp_path / "test_empty.py"
        f.write_text("")
        assert _check_compiles(f) is True

    def test_reject_uncompilable_raises_for_syntax_error(self, tmp_path):
        """reject_uncompilable must raise UncompilableTestError for broken files."""
        f = tmp_path / "test_broken.py"
        f.write_text("class Bad\n")
        with pytest.raises(UncompilableTestError):
            reject_uncompilable(f)

    def test_reject_uncompilable_silent_for_valid_file(self, tmp_path):
        """reject_uncompilable must not raise for a syntactically valid file."""
        f = tmp_path / "test_good.py"
        f.write_text("def test_foo():\n    assert 1 == 1\n")
        reject_uncompilable(f)

    def test_emitted_tests_always_compile(self, tmp_path):
        """Tests emitted by generate_failing_tests must always compile."""
        acs = [
            "File exists: src/bob/compile_target.py",
            "Function defined: bob.compile_target.my_fn",
        ]
        result = generate_failing_tests("feat-compile-check", acs, workspace=tmp_path)
        for fr in result["filter_results"]:
            assert fr.compiles is True, (
                f"Emitted test {fr.test_path} failed compilation check"
            )

    def test_emit_failing_test_produces_compilable_file(self, tmp_path):
        """emit_failing_test must produce a file that passes the compile check."""
        et = emit_failing_test(
            "feat-single-compile",
            0,
            "File exists: src/bob/single.py",
            workspace=tmp_path,
        )
        assert _check_compiles(et.test_path) is True
