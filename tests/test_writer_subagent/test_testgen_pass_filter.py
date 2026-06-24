"""Tests verifying the Pass (stub-rejection) check of the TestGen-LLM triple filter.

The triple filter's second leg rejects test files that mysteriously pass on stub
code — tests that return exit 0 when run in a fresh empty directory with no
source modules installed.
"""

from __future__ import annotations

import pytest

from bob.orchestrator.test_writer_agent import (
    StubPassError,
    _ast_stub_check,
    reject_passes_on_stub,
)
from bob.test_writer_subagent import generate_failing_tests


class TestTestgenPassFilter:
    def test_trivially_green_test_raises_stub_pass_error(self, tmp_path):
        """A test with only assert True must raise StubPassError."""
        f = tmp_path / "test_trivial.py"
        f.write_text("def test_trivial():\n    assert True\n")
        with pytest.raises(StubPassError):
            reject_passes_on_stub(f)

    def test_pytest_fail_test_does_not_raise_stub_pass_error(self, tmp_path):
        """A test with pytest.fail is genuinely red and must not raise StubPassError."""
        f = tmp_path / "test_red.py"
        f.write_text("import pytest\n\ndef test_red():\n    pytest.fail('not yet')\n")
        reject_passes_on_stub(f)

    def test_ast_stub_check_detects_pytest_fail_as_red(self, tmp_path):
        """_ast_stub_check must return True (red) for tests containing pytest.fail."""
        f = tmp_path / "test_fail.py"
        f.write_text("import pytest\n\ndef test_red():\n    pytest.fail('nope')\n")
        assert _ast_stub_check(f) is True

    def test_ast_stub_check_detects_assert_true_as_green(self, tmp_path):
        """_ast_stub_check must return False (green) for tests with only assert True."""
        f = tmp_path / "test_trivial.py"
        f.write_text("def test_trivial():\n    assert True\n")
        assert _ast_stub_check(f) is False

    def test_pass_body_identified_as_stub_passing(self, tmp_path):
        """A test file with only pass body must be identified as stub-passing."""
        f = tmp_path / "test_pass.py"
        f.write_text("def test_nothing():\n    pass\n")
        assert _ast_stub_check(f) is False

    def test_structural_ac_emits_genuinely_red_test(self, tmp_path):
        """A 'File exists' AC must produce a test that fails on stub code."""
        acs = ["File exists: src/bob/pass_filter_target_xyz.py"]
        result = generate_failing_tests("feat-pass-filter-red", acs, workspace=tmp_path)
        assert len(result["filter_results"]) == 1
        fr = result["filter_results"][0]
        assert fr.fails_on_stub is True, (
            "Expected 'File exists' test to fail on stub (file absent)"
        )

    def test_filter_marks_structural_ac_as_accepted(self, tmp_path):
        """A structural AC test must be accepted by the triple filter."""
        acs = ["File exists: src/bob/pass_filter_accept_xyz.py"]
        result = generate_failing_tests("feat-pass-filter-accept", acs, workspace=tmp_path)
        for fr in result["filter_results"]:
            assert fr.accepted is True, (
                f"Expected structural test to be accepted, reason: {fr.reason!r}"
            )

    def test_filter_result_fails_on_stub_is_bool(self, tmp_path):
        """Each FilterResult must have fails_on_stub as a bool."""
        result = generate_failing_tests(
            "feat-pass-filter-bool",
            ["File exists: src/bob/pass_bool.py"],
            workspace=tmp_path,
        )
        for fr in result["filter_results"]:
            assert isinstance(fr.fails_on_stub, bool)

    def test_ast_stub_check_returns_nonfalsish_for_non_trivial_assert(self, tmp_path):
        """_ast_stub_check must not return False for tests with non-trivial assertions."""
        f = tmp_path / "test_non_trivial.py"
        f.write_text(
            "def test_non_trivial():\n"
            "    x = 1 + 1\n"
            "    assert x == 2\n"
        )
        result = _ast_stub_check(f)
        assert result is not False
