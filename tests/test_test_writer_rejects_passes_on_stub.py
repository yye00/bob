"""Tests for reject_passes_on_stub — raises StubPassError on mysteriously green tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob.orchestrator.test_writer_agent import (
    StubPassError,
    emit_failing_tests,
    reject_passes_on_stub,
)


class TestRejectPassesOnStub:
    def test_raises_stub_pass_error_for_vacuous_test(self, tmp_path):
        """A test with assert True always passes even in an empty stub env."""
        vacuous = tmp_path / "test_always_passes.py"
        vacuous.write_text(
            "def test_always_passes():\n    assert True\n",
            encoding="utf-8",
        )
        with pytest.raises(StubPassError):
            reject_passes_on_stub(vacuous)

    def test_does_not_raise_for_failing_test(self, tmp_path):
        """A test that calls pytest.fail() should not raise StubPassError."""
        failing = tmp_path / "test_failing.py"
        failing.write_text(
            "import pytest\ndef test_red():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        # Should not raise — the test is genuinely red
        reject_passes_on_stub(failing)

    def test_raises_stub_pass_error_for_empty_test(self, tmp_path):
        """An empty test body (implicit pass) green without any implementation."""
        empty_test = tmp_path / "test_empty_body.py"
        empty_test.write_text(
            "def test_empty():\n    pass\n",
            encoding="utf-8",
        )
        with pytest.raises(StubPassError):
            reject_passes_on_stub(empty_test)

    def test_stub_pass_error_message_mentions_test_path(self, tmp_path):
        """StubPassError message should include the test path."""
        vacuous = tmp_path / "test_vacuous_named.py"
        vacuous.write_text(
            "def test_x():\n    assert True\n",
            encoding="utf-8",
        )
        with pytest.raises(StubPassError, match="test_vacuous_named"):
            reject_passes_on_stub(vacuous)

    def test_accepts_string_path(self, tmp_path):
        """reject_passes_on_stub should accept a string path, not just Path."""
        failing = tmp_path / "test_str_path.py"
        failing.write_text(
            "import pytest\ndef test_x():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        # Should not raise
        reject_passes_on_stub(str(failing))

    def test_does_not_raise_for_emitted_template_test(self, tmp_path):
        """emit_failing_tests output is genuinely red — reject_passes_on_stub should not raise."""
        acs = ["File exists: src/mymod.py"]
        emitted = emit_failing_tests("feat-stub-check", acs, workspace=tmp_path)
        # The emitted test calls pytest.fail() and should be genuinely red
        reject_passes_on_stub(emitted[0].test_path)

    def test_stub_pass_error_is_exception(self):
        """StubPassError must be a subclass of Exception."""
        assert issubclass(StubPassError, Exception)

    def test_raises_for_no_assertion_test(self, tmp_path):
        """A test with no assertion trivially passes — must be rejected."""
        no_assert = tmp_path / "test_no_assertion.py"
        no_assert.write_text(
            "def test_no_assertion():\n    x = 1 + 1\n",
            encoding="utf-8",
        )
        with pytest.raises(StubPassError):
            reject_passes_on_stub(no_assert)
