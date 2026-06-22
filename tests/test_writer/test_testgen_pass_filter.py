"""Tests for the TestGen-LLM pass (fails-on-stub) filter — check 2 of the triple filter.

The pass filter rejects tests that mysteriously pass on stub code (i.e. would
be green even when no implementation exists).  A valid test must fail when no
source modules are present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.orchestrator.test_writer_agent import (
    EmittedTest,
    FilterResult,
    _ast_stub_check,
    _check_fails_on_stub,
    triple_filter,
)


class TestPassFilter:
    def test_pytest_fail_call_detected_as_definitively_red(self, tmp_path):
        """A file with unconditional pytest.fail must be detected as definitively red by AST."""
        p = tmp_path / "test_red.py"
        p.write_text(
            "import pytest\n"
            "def test_x(): pytest.fail('not implemented')\n"
        )
        result = _ast_stub_check(p)
        assert result is True

    def test_assert_true_only_detected_as_definitively_green(self, tmp_path):
        """A file with only 'assert True' must be detected as definitively green (passes on stub)."""
        p = tmp_path / "test_green.py"
        p.write_text("def test_x(): assert True\n")
        result = _ast_stub_check(p)
        assert result is False

    def test_ambiguous_file_returns_none(self, tmp_path):
        """A file with real assertions (not pytest.fail, not assert True) must return None from AST check."""
        p = tmp_path / "test_ambiguous.py"
        p.write_text(
            "import bob3.mymod\n"
            "def test_x(): assert bob3.mymod.fn() == 42\n"
        )
        result = _ast_stub_check(p)
        assert result is None  # ambiguous — subprocess needed

    def test_check_fails_on_stub_returns_true_for_pytest_fail(self, tmp_path):
        """_check_fails_on_stub must return True for a test with unconditional pytest.fail."""
        p = tmp_path / "test_fail.py"
        p.write_text(
            "import pytest\n"
            "def test_x(): pytest.fail('always fails')\n"
        )
        assert _check_fails_on_stub(p) is True

    def test_check_fails_on_stub_returns_false_for_assert_true(self, tmp_path):
        """_check_fails_on_stub must return False for a test with only assert True."""
        p = tmp_path / "test_pass_stub.py"
        p.write_text("def test_x(): assert True\n")
        assert _check_fails_on_stub(p) is False

    def test_triple_filter_rejects_passes_on_stub(self, tmp_path):
        """triple_filter must reject an EmittedTest that passes on stub code."""
        p = tmp_path / "test_trivial.py"
        p.write_text("def test_x(): assert True\n")
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_trivial",
            ac_text="File exists: src/x.py",
            test_path=p,
            feature_id="feat-stub-pass",
        )
        results = triple_filter([et])
        assert len(results) == 1
        result = results[0]
        assert result.fails_on_stub is False
        assert result.accepted is False
        assert "stub" in result.reason.lower() or "green" in result.reason.lower() or "pass" in result.reason.lower()

    def test_triple_filter_accepts_definitively_red_test(self, tmp_path):
        """triple_filter must not reject a test with unconditional pytest.fail on stub grounds."""
        p = tmp_path / "test_red_pass.py"
        p.write_text(
            "import pytest\n"
            "def test_x(): pytest.fail('not implemented yet')\n"
        )
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_red",
            ac_text="File exists: src/x.py",
            test_path=p,
            feature_id="feat-red-accepted",
        )
        results = triple_filter([et])
        assert results[0].fails_on_stub is True

    def test_pytest_raises_call_is_red(self, tmp_path):
        """A test body using pytest.raises is definitively red per AST check."""
        p = tmp_path / "test_raises.py"
        p.write_text(
            "import pytest\n"
            "def test_x():\n"
            "    with pytest.raises(NotImplementedError):\n"
            "        raise NotImplementedError()\n"
        )
        result = _ast_stub_check(p)
        assert result is True

    def test_pass_only_body_returns_false_from_ast(self, tmp_path):
        """A test function with only a 'pass' statement is detected as green by AST."""
        p = tmp_path / "test_pass.py"
        p.write_text("def test_x(): pass\n")
        result = _ast_stub_check(p)
        assert result is False
