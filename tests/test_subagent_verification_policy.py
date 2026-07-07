"""Tests for hippy.subagent_verification_policy.

Feature: 6afd3f13-b886-49de-a32a-efb5d37d5125 — Subagent observability mandate.

Locks the no-redirect rule into the hippy generation spec: the verification
prompt handed to sub-agents MUST forbid redirecting/suppressing pytest output
(`> /dev/null`, `2>/dev/null`, `| grep`, capture-only filters, `-q --no-header`),
because for long-running tests the streaming output is the ONLY signal that the
run is not hung.
"""

from __future__ import annotations

import pytest

from hippy.subagent_verification_policy import (
    build_verification_prompt,
    forbid_pytest_output_redirection,
)


class TestForbidPytestOutputRedirection:
    def test_safe_command_returns_true(self):
        ok, msg = forbid_pytest_output_redirection(
            "python -m pytest tests/test_foo.py -v"
        )
        assert ok is True
        assert msg == ""

    def test_stdout_to_dev_null_rejected(self):
        ok, msg = forbid_pytest_output_redirection(
            "python -m pytest tests/ > /dev/null"
        )
        assert ok is False
        assert msg

    def test_stderr_to_dev_null_rejected(self):
        ok, msg = forbid_pytest_output_redirection(
            "python -m pytest tests/ 2>/dev/null"
        )
        assert ok is False
        assert msg

    def test_grep_capture_filter_rejected(self):
        # The exact defect that caused the 43+ min silent stall.
        ok, msg = forbid_pytest_output_redirection(
            "python -m pytest tests/ -q --tb=short 2>&1 | grep -E 'FAILED|ERROR' | head -10"
        )
        assert ok is False
        assert msg

    def test_quiet_flag_rejected(self):
        ok, msg = forbid_pytest_output_redirection("python -m pytest tests/ -q")
        assert ok is False
        assert msg

    def test_no_header_flag_rejected(self):
        ok, msg = forbid_pytest_output_redirection(
            "python -m pytest tests/ --no-header"
        )
        assert ok is False
        assert msg

    def test_return_is_two_tuple(self):
        result = forbid_pytest_output_redirection("pytest -v")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            forbid_pytest_output_redirection(None)


class TestBuildVerificationPrompt:
    def test_returns_non_empty_string(self):
        prompt = build_verification_prompt()
        assert isinstance(prompt, str)
        assert prompt.strip()

    def test_prompt_forbids_dev_null(self):
        prompt = build_verification_prompt()
        assert "/dev/null" in prompt

    def test_prompt_mentions_forbidden_marker(self):
        prompt = build_verification_prompt().upper()
        assert "FORBIDDEN" in prompt

    def test_prompt_explains_streaming_rationale(self):
        prompt = build_verification_prompt().lower()
        assert "stream" in prompt

    def test_prompt_mentions_grep_capture_filter(self):
        prompt = build_verification_prompt()
        assert "grep" in prompt

    def test_prompt_includes_acceptance_criteria_when_given(self):
        acs = ["pytest: tests/test_my_feature.py"]
        prompt = build_verification_prompt(acs)
        assert "tests/test_my_feature.py" in prompt

    def test_prompt_stable_across_calls(self):
        assert build_verification_prompt() == build_verification_prompt()

    def test_invalid_acceptance_criteria_type_raises(self):
        with pytest.raises((ValueError, TypeError)):
            build_verification_prompt("not-a-list")
