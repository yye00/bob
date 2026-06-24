"""Tests for the compile-check component (AC: test_compile_check).

Validates the first leg of the TestGen-LLM triple filter: the compile check.
Tests that _check_compiles correctly identifies valid and invalid Python files,
and that reject_uncompilable raises the right exception type on failure.
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
    def test_valid_pytest_file_compiles(self, tmp_path):
        """A well-formed pytest file must return True from _check_compiles."""
        valid = tmp_path / "test_valid.py"
        valid.write_text(
            "import pytest\n\ndef test_something():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        assert _check_compiles(valid) is True

    def test_syntax_error_file_does_not_compile(self, tmp_path):
        """A file with a SyntaxError must return False from _check_compiles."""
        broken = tmp_path / "test_broken.py"
        broken.write_text("def bad(:\n    pass\n", encoding="utf-8")
        assert _check_compiles(broken) is False

    def test_empty_file_compiles(self, tmp_path):
        """An empty file is valid Python and must return True from _check_compiles."""
        empty = tmp_path / "test_empty.py"
        empty.write_text("", encoding="utf-8")
        assert _check_compiles(empty) is True

    def test_file_with_only_comments_compiles(self, tmp_path):
        """A file containing only comments is valid Python."""
        comments_only = tmp_path / "test_comments.py"
        comments_only.write_text("# This is a comment\n# No code here\n", encoding="utf-8")
        assert _check_compiles(comments_only) is True

    def test_invalid_utf8_file_does_not_compile(self, tmp_path):
        """A file with invalid UTF-8 bytes must return False from _check_compiles."""
        binary = tmp_path / "test_binary.py"
        binary.write_bytes(b"\xff\xfe invalid bytes \x00\x01")
        assert _check_compiles(binary) is False

    def test_unmatched_parenthesis_does_not_compile(self, tmp_path):
        """Unmatched parentheses constitute a SyntaxError."""
        bad_parens = tmp_path / "test_bad_parens.py"
        bad_parens.write_text("x = (1 + 2\n", encoding="utf-8")
        assert _check_compiles(bad_parens) is False

    def test_valid_class_definition_compiles(self, tmp_path):
        """A valid class-based test file must compile successfully."""
        class_test = tmp_path / "test_class.py"
        class_test.write_text(
            "import pytest\n\nclass TestSomething:\n    def test_it(self):\n        pytest.fail('red')\n",
            encoding="utf-8",
        )
        assert _check_compiles(class_test) is True


class TestRejectUncompilable:
    def test_does_not_raise_for_valid_file(self, tmp_path):
        """reject_uncompilable must be silent (no exception) for a valid Python file."""
        good = tmp_path / "good.py"
        good.write_text("import pytest\n\ndef test_x():\n    pytest.fail('red')\n", encoding="utf-8")
        reject_uncompilable(good)  # must not raise

    def test_raises_uncompilable_error_for_syntax_error(self, tmp_path):
        """reject_uncompilable must raise UncompilableTestError for SyntaxError files."""
        bad = tmp_path / "bad.py"
        bad.write_text("class X(\n    pass\n", encoding="utf-8")
        with pytest.raises(UncompilableTestError):
            reject_uncompilable(bad)

    def test_raises_uncompilable_error_message_references_file(self, tmp_path):
        """The UncompilableTestError message must reference the file path."""
        bad = tmp_path / "bad_ref.py"
        bad.write_text("def bad(:\n    pass\n", encoding="utf-8")
        with pytest.raises(UncompilableTestError, match=str(bad)):
            reject_uncompilable(bad)

    def test_raises_for_empty_function_def_with_missing_body(self, tmp_path):
        """An incomplete function definition (no body) is a SyntaxError."""
        incomplete = tmp_path / "incomplete.py"
        incomplete.write_text("def broken()\n", encoding="utf-8")
        with pytest.raises(UncompilableTestError):
            reject_uncompilable(incomplete)


class TestTripleFilterCompileCheck:
    def test_filter_marks_emitted_test_as_compiles_true(self, tmp_path):
        """All tests emitted by emit_failing_tests must have compiles=True."""
        acs = ["File exists: src/bob/foo.py"]
        emitted = emit_failing_tests("feat-compile-filter", acs, workspace=tmp_path)
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == 1
        assert results[0].compiles is True

    def test_filter_marks_corrupted_file_as_not_compiles(self, tmp_path):
        """A corrupted test file must have compiles=False in triple_filter output."""
        acs = ["File exists: src/bob/bar.py"]
        emitted = emit_failing_tests("feat-compile-corrupt", acs, workspace=tmp_path)
        emitted[0].test_path.write_text("def broken(:\n    pass\n", encoding="utf-8")
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == 1
        assert results[0].compiles is False
        assert results[0].accepted is False

    def test_filter_compile_failure_reason_mentions_syntax(self, tmp_path):
        """FilterResult.reason for a compile failure must mention SyntaxError or uncompilable."""
        acs = ["File exists: src/bob/baz.py"]
        emitted = emit_failing_tests("feat-compile-reason", acs, workspace=tmp_path)
        emitted[0].test_path.write_text("class Bad(\n", encoding="utf-8")
        results = triple_filter(emitted, workspace=tmp_path)
        r = results[0]
        assert "SyntaxError" in r.reason or "uncompilable" in r.reason.lower()

    def test_agent_filter_compile_check_integration(self, tmp_path):
        """TestWriterAgent.filter must reflect compiles=True for normally emitted tests."""
        agent = TestWriterAgent(workspace=tmp_path)
        emitted = agent.emit("feat-compile-agent", ["pytest: tests/test_x.py"])
        results = agent.filter(emitted)
        assert all(r.compiles for r in results), "All emitted tests should compile"

    def test_generate_marks_gate_failed_when_compile_error(self, tmp_path):
        """gate_passed must be False when any test fails the compile check."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["File exists: src/broken_mod.py"]
        emitted = agent.emit("feat-compile-gate", acs)
        emitted[0].test_path.write_text("def oops(:\n    pass\n", encoding="utf-8")
        results = agent.filter(emitted)
        all_accepted = all(r.accepted for r in results)
        assert not all_accepted, "gate should not pass when compile fails"
