"""Tests for TestWriterAgent — compilation validation (AC: test_compilation_validation).

Validates that the TestWriterAgent triple-filter correctly identifies test files
that compile vs. those that have syntax errors (check 1 of 3 in the triple filter).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_writer import TestWriterAgent
from bob.orchestrator.test_writer_agent import (
    UncompilableTestError,
    _check_compiles,
    reject_uncompilable,
)


class TestCompilationValidation:
    def test_emitted_test_compiles_without_errors(self, tmp_path):
        """Every test file emitted by TestWriterAgent.emit must parse cleanly."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["File exists: src/bob/example.py", "pytest: tests/test_example.py"]
        emitted = agent.emit("feat-compile-val", acs)
        assert emitted, "expected at least one emitted test"
        for et in emitted:
            assert _check_compiles(et.test_path), f"{et.test_path} must compile"

    def test_syntax_error_file_rejected(self, tmp_path):
        """A file with SyntaxError must return False from _check_compiles."""
        broken = tmp_path / "test_broken.py"
        broken.write_text("def incomplete(:\n    pass\n", encoding="utf-8")
        assert _check_compiles(broken) is False

    def test_valid_file_accepted(self, tmp_path):
        """A syntactically valid test file must pass _check_compiles."""
        valid = tmp_path / "test_valid.py"
        valid.write_text(
            "import pytest\n\ndef test_something():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        assert _check_compiles(valid) is True

    def test_empty_file_accepted(self, tmp_path):
        """An empty file is valid Python and must pass _check_compiles."""
        empty = tmp_path / "test_empty.py"
        empty.write_text("", encoding="utf-8")
        assert _check_compiles(empty) is True

    def test_filter_marks_bad_compile_as_not_accepted(self, tmp_path):
        """triple_filter must mark a corrupted test as compiles=False, accepted=False."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["File exists: src/bob/something.py"]
        emitted = agent.emit("feat-bad-syntax", acs)
        emitted[0].test_path.write_text("def broken(:\n    pass\n", encoding="utf-8")
        results = agent.filter(emitted)
        assert len(results) == 1
        r = results[0]
        assert r.compiles is False
        assert r.accepted is False
        assert "SyntaxError" in r.reason or "uncompilable" in r.reason.lower()

    def test_reject_uncompilable_silent_on_valid_file(self, tmp_path):
        """reject_uncompilable must not raise for a valid Python file."""
        good = tmp_path / "good.py"
        good.write_text("import pytest\n", encoding="utf-8")
        reject_uncompilable(good)  # must not raise

    def test_reject_uncompilable_raises_for_broken_file(self, tmp_path):
        """reject_uncompilable must raise UncompilableTestError for a broken file."""
        bad = tmp_path / "bad.py"
        bad.write_text("class Bad(\n", encoding="utf-8")
        with pytest.raises(UncompilableTestError):
            reject_uncompilable(bad)

    def test_unicode_decode_error_file_fails_check(self, tmp_path):
        """A file with invalid UTF-8 must fail _check_compiles."""
        binary = tmp_path / "test_binary.py"
        binary.write_bytes(b"\xff\xfe invalid bytes \x00")
        assert _check_compiles(binary) is False

    def test_all_emitted_tests_pass_triple_filter_compilation(self, tmp_path):
        """All emitted tests must have compiles=True in triple_filter results."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = [
            "File exists: src/mod_a.py",
            "Function defined: mod_b.fn",
            "pytest: tests/test_mod_c.py",
        ]
        result = agent.generate("feat-compile-all", acs)
        for r in result["filter_results"]:
            assert r.compiles is True, f"Expected {r.test_path} to compile"
