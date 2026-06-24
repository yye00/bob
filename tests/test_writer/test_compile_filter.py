"""Tests for the compile-filter component (AC: test_compile_filter).

Validates the first leg of the TestGen-LLM triple filter: the compilation check.
Tests that _check_compiles correctly distinguishes valid Python from files with
SyntaxError or invalid UTF-8, and that reject_uncompilable raises
UncompilableTestError when the file cannot be compiled.
"""

from __future__ import annotations

import pytest

from bob.orchestrator.test_writer_agent import (
    UncompilableTestError,
    _check_compiles,
    emit_failing_tests,
    reject_uncompilable,
    triple_filter,
)
from test_writer import TestWriterAgent


class TestCheckCompilesBasic:
    def test_valid_python_file_passes(self, tmp_path):
        """A well-formed Python file must return True from _check_compiles."""
        valid = tmp_path / "test_valid.py"
        valid.write_text(
            "import pytest\n\ndef test_foo():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        assert _check_compiles(valid) is True

    def test_syntax_error_file_fails(self, tmp_path):
        """A file with a SyntaxError must return False from _check_compiles."""
        broken = tmp_path / "test_broken.py"
        broken.write_text("def test_bad(\n    pass\n", encoding="utf-8")
        assert _check_compiles(broken) is False

    def test_empty_file_passes(self, tmp_path):
        """An empty Python file is syntactically valid and must return True."""
        empty = tmp_path / "test_empty.py"
        empty.write_text("", encoding="utf-8")
        assert _check_compiles(empty) is True

    def test_invalid_utf8_bytes_fail(self, tmp_path):
        """A file with invalid UTF-8 bytes must return False."""
        binary = tmp_path / "test_binary.py"
        binary.write_bytes(b"\xff\xfe invalid utf-8 \x00")
        assert _check_compiles(binary) is False

    def test_multiline_valid_module_passes(self, tmp_path):
        """A multi-line valid Python module must return True."""
        multiline = tmp_path / "test_multi.py"
        multiline.write_text(
            "import os\nimport sys\n\n\ndef test_something():\n    assert 1 + 1 == 3\n",
            encoding="utf-8",
        )
        assert _check_compiles(multiline) is True

    def test_indentation_error_file_fails(self, tmp_path):
        """A file with an IndentationError (which is a SyntaxError) must return False."""
        bad_indent = tmp_path / "test_indent.py"
        bad_indent.write_text(
            "def test_bad():\nassert True\n",  # missing indent
            encoding="utf-8",
        )
        assert _check_compiles(bad_indent) is False

    def test_file_with_only_comment_passes(self, tmp_path):
        """A file containing only a comment is valid Python."""
        comment_only = tmp_path / "test_comment.py"
        comment_only.write_text("# Just a comment\n", encoding="utf-8")
        assert _check_compiles(comment_only) is True


class TestRejectUncompilable:
    def test_does_not_raise_for_valid_file(self, tmp_path):
        """reject_uncompilable must be silent for a valid Python file."""
        valid = tmp_path / "test_valid.py"
        valid.write_text(
            "import pytest\n\ndef test_it():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        reject_uncompilable(valid)  # must not raise

    def test_raises_for_syntax_error_file(self, tmp_path):
        """reject_uncompilable must raise UncompilableTestError for a SyntaxError file."""
        broken = tmp_path / "test_broken.py"
        broken.write_text("def test_bad(\n    pass\n", encoding="utf-8")
        with pytest.raises(UncompilableTestError):
            reject_uncompilable(broken)

    def test_raises_for_empty_parens_syntax_error(self, tmp_path):
        """reject_uncompilable must raise for unclosed parentheses."""
        broken = tmp_path / "test_unclosed.py"
        broken.write_text("x = (\n", encoding="utf-8")
        with pytest.raises(UncompilableTestError):
            reject_uncompilable(broken)

    def test_accepts_string_path(self, tmp_path):
        """reject_uncompilable must accept a string path, not just a Path object."""
        valid = tmp_path / "test_str_path.py"
        valid.write_text("def test_ok():\n    pass\n", encoding="utf-8")
        reject_uncompilable(str(valid))  # must not raise


class TestTripleFilterCompileCheck:
    def test_emitted_tests_all_compile(self, tmp_path):
        """All tests emitted by emit_failing_tests must pass the compile check."""
        acs = ["File exists: src/mymod.py", "Function defined: bob.mymod.fn"]
        emitted = emit_failing_tests("feat-compile-filter", acs, workspace=tmp_path)
        results = triple_filter(emitted, workspace=tmp_path)
        assert all(r.compiles for r in results), "All emitted tests should compile"

    def test_filter_rejects_uncompilable_test(self, tmp_path):
        """triple_filter must reject a test file with a SyntaxError."""
        acs = ["File exists: src/placeholder.py"]
        emitted = emit_failing_tests("feat-compile-reject", acs, workspace=tmp_path)
        # Overwrite the emitted file with invalid Python
        emitted[0].test_path.write_text("def test_bad(\n    pass\n", encoding="utf-8")
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == 1
        assert results[0].compiles is False
        assert results[0].accepted is False

    def test_filter_reason_mentions_compile_on_failure(self, tmp_path):
        """FilterResult.reason must mention compile/syntax when compilation fails."""
        acs = ["File exists: src/mod.py"]
        emitted = emit_failing_tests("feat-compile-reason", acs, workspace=tmp_path)
        emitted[0].test_path.write_text("def test_bad(\n    pass\n", encoding="utf-8")
        results = triple_filter(emitted, workspace=tmp_path)
        r = results[0]
        assert "compil" in r.reason.lower() or "syntax" in r.reason.lower()

    def test_agent_filter_compiles_field_true(self, tmp_path):
        """TestWriterAgent.filter must reflect compiles=True for emitted tests."""
        agent = TestWriterAgent(workspace=tmp_path)
        emitted = agent.emit("feat-compile-agent", ["File exists: src/z.py"])
        results = agent.filter(emitted)
        assert all(r.compiles for r in results), "All agent-emitted tests should compile"
