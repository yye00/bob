"""Tests for the compilation check in the triple-filter (AC: test_ac_compilation).

Validates that the TestGen-LLM triple filter correctly identifies test files
that do and do not compile (SyntaxError / uncompilable) — check 1 of 3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.orchestrator.test_writer_agent import (
    UncompilableTestError,
    _check_compiles,
    emit_failing_tests,
    reject_uncompilable,
    triple_filter,
)


class TestAcCompilation:
    def test_emitted_test_file_compiles(self, tmp_path):
        """Tests emitted by emit_failing_tests must parse without SyntaxError."""
        acs = ["File exists: src/bob/sample.py"]
        emitted = emit_failing_tests("feat-compile-check", acs, workspace=tmp_path)
        assert emitted, "expected at least one emitted test"
        for et in emitted:
            assert _check_compiles(et.test_path), f"{et.test_path} should compile"

    def test_syntactically_invalid_file_fails_check(self, tmp_path):
        """A file with a SyntaxError must be rejected by _check_compiles."""
        bad = tmp_path / "bad_test.py"
        bad.write_text("def broken(:\n    pass\n", encoding="utf-8")
        assert not _check_compiles(bad)

    def test_valid_python_file_passes_check(self, tmp_path):
        """A syntactically valid test file must pass _check_compiles."""
        good = tmp_path / "good_test.py"
        good.write_text(
            "import pytest\n\ndef test_something():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        assert _check_compiles(good)

    def test_triple_filter_rejects_uncompilable(self, tmp_path):
        """triple_filter must mark a test as not accepted when it won't compile."""
        acs = ["File exists: src/bob/sample.py"]
        emitted = emit_failing_tests("feat-bad-compile", acs, workspace=tmp_path)
        # Corrupt the file
        emitted[0].test_path.write_text("def broken(:\n    pass\n", encoding="utf-8")
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == 1
        r = results[0]
        assert not r.compiles
        assert not r.accepted
        assert "SyntaxError" in r.reason or "uncompilable" in r.reason.lower()

    def test_reject_uncompilable_passes_on_valid_file(self, tmp_path):
        """reject_uncompilable must not raise for a valid test file."""
        valid = tmp_path / "valid.py"
        valid.write_text("import pytest\n", encoding="utf-8")
        reject_uncompilable(valid)  # should not raise

    def test_reject_uncompilable_raises_on_syntax_error(self, tmp_path):
        """reject_uncompilable must raise UncompilableTestError for broken files."""
        broken = tmp_path / "broken.py"
        broken.write_text("def f(:\n    pass\n", encoding="utf-8")
        with pytest.raises(UncompilableTestError):
            reject_uncompilable(broken)

    def test_unicode_decode_error_treated_as_uncompilable(self, tmp_path):
        """Binary content that can't be decoded must fail _check_compiles."""
        bad = tmp_path / "binary.py"
        bad.write_bytes(b"\xff\xfe\x00")  # not valid UTF-8 Python
        assert not _check_compiles(bad)
