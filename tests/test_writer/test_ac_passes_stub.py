"""Tests for TestWriterAgent — stub-pass filter (AC: test_ac_passes_stub).

Validates that the TestWriterAgent correctly identifies tests that pass on
stub code (mysteriously green) — check 2 of 3 in the triple filter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_writer import TestWriterAgent
from bob3.orchestrator.test_writer_agent import (
    StubPassError,
    _check_fails_on_stub,
    reject_passes_on_stub,
)


class TestAcPassesStub:
    def test_emitted_test_fails_on_stub(self, tmp_path):
        """Tests emitted by TestWriterAgent.emit must fail against an empty stub."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["Function defined: bob3.mymod.my_fn"]
        emitted = agent.emit("feat-stub-check", acs)
        assert emitted, "expected at least one emitted test"
        for et in emitted:
            assert _check_fails_on_stub(et.test_path), (
                f"{et.test_path} should fail on stub (pytest.fail() call present)"
            )

    def test_assert_true_test_passes_on_stub(self, tmp_path):
        """A test containing only 'assert True' passes on stub — must be detected."""
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

    def test_filter_rejects_mysteriously_green_test(self, tmp_path):
        """filter() must not accept a test that passes on stub code."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["File exists: src/bob3/placeholder.py"]
        emitted = agent.emit("feat-pass-filter", acs)
        # Replace with a test that always passes
        emitted[0].test_path.write_text(
            "def test_stub_passes():\n    assert True\n",
            encoding="utf-8",
        )
        results = agent.filter(emitted)
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
        reject_passes_on_stub(red)

    def test_reject_passes_on_stub_raises_for_always_passing_test(self, tmp_path):
        """reject_passes_on_stub must raise StubPassError for always-green tests."""
        green = tmp_path / "test_green.py"
        green.write_text(
            "def test_always():\n    assert True\n",
            encoding="utf-8",
        )
        with pytest.raises(StubPassError):
            reject_passes_on_stub(green)

    def test_generate_gate_fails_for_mysteriously_green_test(self, tmp_path):
        """generate() returns gate_passed=False when a test passes on stub."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["File exists: src/bob3/placeholder.py"]
        emitted = agent.emit("feat-gate-green", acs)
        # Replace emitted test with always-passing content
        emitted[0].test_path.write_text(
            "def test_stub_passes():\n    assert True\n",
            encoding="utf-8",
        )
        results = agent.filter(emitted)
        assert not results[0].accepted
