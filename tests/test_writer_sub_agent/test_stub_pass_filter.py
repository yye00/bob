"""Tests for the stub-pass filter in the triple-filter.

Validates that the TestGen-LLM triple filter correctly identifies tests that
pass on stub code (mysteriously green) — check 2 of 3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.orchestrator.test_writer_agent import (
    StubPassError,
    _check_fails_on_stub,
    emit_failing_tests,
    reject_passes_on_stub,
    triple_filter,
)


class TestStubPassFilter:
    def test_emitted_test_fails_on_stub(self, tmp_path):
        """Tests emitted by emit_failing_tests must fail against an empty stub environment."""
        acs = ["Function defined: bob3.mymod.my_fn"]
        emitted = emit_failing_tests("feat-stubpass-filter-check", acs, workspace=tmp_path)
        assert emitted, "expected at least one emitted test"
        for et in emitted:
            assert _check_fails_on_stub(et.test_path), (
                f"{et.test_path} should fail on stub (pytest.fail() call present)"
            )

    def test_test_that_always_passes_is_rejected(self, tmp_path):
        """A test containing 'assert True' passes on stub — filter must reject it."""
        always_green = tmp_path / "test_always_green.py"
        always_green.write_text(
            "def test_always():\n    assert True\n",
            encoding="utf-8",
        )
        result = _check_fails_on_stub(always_green)
        assert not result, "assert True should pass on stub — must be detected as not genuinely red"

    def test_pytest_fail_test_fails_on_stub(self, tmp_path):
        """A test that unconditionally calls pytest.fail() is red by definition."""
        red = tmp_path / "test_red.py"
        red.write_text(
            "import pytest\ndef test_red():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        assert _check_fails_on_stub(red), "pytest.fail() should produce non-zero exit"

    def test_triple_filter_rejects_mysteriously_green_test(self, tmp_path):
        """triple_filter must not accept a test that passes on stub code."""
        acs = ["File exists: src/bob3/placeholder.py"]
        emitted = emit_failing_tests("feat-stubpass-filter-green", acs, workspace=tmp_path)
        # Replace with a test that always passes
        emitted[0].test_path.write_text(
            "def test_stub_passes():\n    assert True\n",
            encoding="utf-8",
        )
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r.compiles
        assert not r.fails_on_stub
        assert not r.accepted
        assert "stub" in r.reason.lower() or "mysteriously" in r.reason.lower()

    def test_reject_passes_on_stub_does_not_raise_for_red_test(self, tmp_path):
        """reject_passes_on_stub must not raise when the test correctly fails."""
        red = tmp_path / "test_red.py"
        red.write_text(
            "import pytest\ndef test_red():\n    pytest.fail('not yet')\n",
            encoding="utf-8",
        )
        reject_passes_on_stub(red)  # should not raise

    def test_reject_passes_on_stub_raises_for_always_passing_test(self, tmp_path):
        """reject_passes_on_stub must raise StubPassError for always-green tests."""
        green = tmp_path / "test_green.py"
        green.write_text(
            "def test_always():\n    assert True\n",
            encoding="utf-8",
        )
        with pytest.raises(StubPassError):
            reject_passes_on_stub(green)

    def test_all_emitted_tests_fail_on_stub_for_multi_ac(self, tmp_path):
        """All emitted tests for multiple ACs must fail against the stub."""
        acs = [
            "File exists: src/a.py",
            "pytest: tests/test_a.py",
            "Function defined: bob3.a.fn",
        ]
        emitted = emit_failing_tests("feat-stubpass-multi", acs, workspace=tmp_path)
        for et in emitted:
            assert _check_fails_on_stub(et.test_path), (
                f"{et.test_path} must fail on stub"
            )
