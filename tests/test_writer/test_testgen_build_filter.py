"""Tests for the TestGen-LLM build (compile) filter — check 1 of the triple filter.

The build filter rejects test files that do not compile (SyntaxError or
UnicodeDecodeError at AST-parse time).  It is the first gate in triple_filter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.orchestrator.test_writer_agent import (
    EmittedTest,
    FilterResult,
    _check_compiles,
    triple_filter,
)


class TestBuildFilter:
    def test_valid_python_file_compiles(self, tmp_path):
        """A syntactically correct Python file must pass the compile check."""
        p = tmp_path / "test_valid.py"
        p.write_text("import pytest\ndef test_x(): pytest.fail('red')\n")
        assert _check_compiles(p) is True

    def test_syntax_error_file_fails_compile(self, tmp_path):
        """A file with a SyntaxError must fail the compile check."""
        p = tmp_path / "test_broken.py"
        p.write_text("def test_x(\n")  # unclosed paren — SyntaxError
        assert _check_compiles(p) is False

    def test_empty_file_compiles(self, tmp_path):
        """An empty file is valid Python and must pass the compile check."""
        p = tmp_path / "test_empty.py"
        p.write_text("")
        assert _check_compiles(p) is True

    def test_triple_filter_rejects_uncompilable_test(self, tmp_path):
        """triple_filter must reject an EmittedTest whose file has a SyntaxError."""
        p = tmp_path / "test_broken.py"
        p.write_text("def broken(\n")
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_broken",
            ac_text="File exists: src/x.py",
            test_path=p,
            feature_id="feat-compile-reject",
        )
        results = triple_filter([et])
        assert len(results) == 1
        result = results[0]
        assert result.compiles is False
        assert result.accepted is False
        assert "compile" in result.reason.lower() or "compilable" in result.reason.lower()

    def test_triple_filter_passes_compilable_test(self, tmp_path):
        """triple_filter must not reject a properly compilable test on compile grounds."""
        p = tmp_path / "test_good.py"
        p.write_text(
            "import pytest\n"
            "class TestOk:\n"
            "    def test_fail(self): pytest.fail('red')\n"
        )
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_good",
            ac_text="File exists: src/x.py",
            test_path=p,
            feature_id="feat-compile-pass",
        )
        results = triple_filter([et])
        assert results[0].compiles is True

    def test_multiple_tests_first_uncompilable_isolated(self, tmp_path):
        """An uncompilable test must not affect the result for subsequent tests."""
        p_bad = tmp_path / "test_bad.py"
        p_bad.write_text("def bad(\n")
        p_good = tmp_path / "test_good.py"
        p_good.write_text(
            "import pytest\ndef test_ok(): pytest.fail('x')\n"
        )
        ets = [
            EmittedTest(0, "ac_0_bad", "File exists: src/bad.py", p_bad, "feat-iso"),
            EmittedTest(1, "ac_1_good", "File exists: src/good.py", p_good, "feat-iso"),
        ]
        results = triple_filter(ets)
        assert results[0].compiles is False
        assert results[1].compiles is True

    def test_filter_result_has_correct_ac_id(self, tmp_path):
        """FilterResult.ac_id must match the EmittedTest.ac_id."""
        p = tmp_path / "test_ac.py"
        p.write_text("import pytest\ndef test_x(): pytest.fail('red')\n")
        et = EmittedTest(0, "ac_0_my_ac", "File exists: src/x.py", p, "feat-ac-id")
        results = triple_filter([et])
        assert results[0].ac_id == "ac_0_my_ac"

    def test_filter_result_test_path_matches(self, tmp_path):
        """FilterResult.test_path must match the EmittedTest.test_path."""
        p = tmp_path / "test_path_check.py"
        p.write_text("import pytest\ndef test_x(): pytest.fail('red')\n")
        et = EmittedTest(0, "ac_0_path", "File exists: src/x.py", p, "feat-path")
        results = triple_filter([et])
        assert results[0].test_path == p
