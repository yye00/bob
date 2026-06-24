"""Tests for TestWriterAgent — compilation check (AC: test_ac_compilation).

Validates that the TestWriterAgent correctly identifies test files that
do and do not compile (SyntaxError / uncompilable) via the triple filter.
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


class TestAcCompilation:
    def test_emitted_test_file_compiles(self, tmp_path):
        """Tests emitted by TestWriterAgent.emit must parse without SyntaxError."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["File exists: src/bob/sample.py"]
        emitted = agent.emit("feat-compile-check", acs)
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

    def test_generate_rejects_uncompilable_in_triple_filter(self, tmp_path):
        """When an emitted test is corrupted, triple_filter marks it as not accepted."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["File exists: src/bob/sample.py"]
        emitted = agent.emit("feat-bad-compile", acs)
        # Corrupt the file
        emitted[0].test_path.write_text("def broken(:\n    pass\n", encoding="utf-8")
        results = agent.filter(emitted)
        assert len(results) == 1
        r = results[0]
        assert not r.compiles
        assert not r.accepted
        assert "SyntaxError" in r.reason or "uncompilable" in r.reason.lower()

    def test_reject_uncompilable_passes_on_valid_file(self, tmp_path):
        """reject_uncompilable must not raise for a valid test file."""
        valid = tmp_path / "valid.py"
        valid.write_text("import pytest\n", encoding="utf-8")
        reject_uncompilable(valid)

    def test_reject_uncompilable_raises_on_syntax_error(self, tmp_path):
        """reject_uncompilable must raise UncompilableTestError for broken files."""
        broken = tmp_path / "broken.py"
        broken.write_text("def f(:\n    pass\n", encoding="utf-8")
        with pytest.raises(UncompilableTestError):
            reject_uncompilable(broken)

    def test_generate_gate_passes_for_valid_ac(self, tmp_path):
        """generate() must return gate_passed=True when ACs produce valid tests."""
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-compile-gate", ["File exists: src/bob/x.py"])
        assert result["gate_passed"] is True
        assert all(r.compiles for r in result["filter_results"])
