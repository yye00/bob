"""Tests that the verification prompt forbids quiet/capture pytest modes.

Feature: ee61c0b1-017e-439d-ae67-2886b73fe862
AC: pytest: tests/test_verification_prompt_forbids_quiet_capture_modes.py
"""

from __future__ import annotations

from bob.superpowers import get_verification_prompt, verification_prompt_forbids_stdout_redirect


class TestVerificationPromptForbidsQuietCaptureModes:
    def test_prompt_forbids_q_flag(self):
        prompt = get_verification_prompt()
        assert "-q" in prompt

    def test_prompt_forbids_no_header_flag(self):
        prompt = get_verification_prompt()
        assert "--no-header" in prompt

    def test_prompt_forbids_grep_pipe_pattern(self):
        prompt = get_verification_prompt()
        assert "grep" in prompt

    def test_prompt_forbids_head_truncation(self):
        prompt = get_verification_prompt()
        assert "head -10" in prompt

    def test_prompt_forbids_pipe_that_captures_output(self):
        prompt = get_verification_prompt()
        assert "pipe" in prompt.lower()

    def test_forbids_stdout_redirect_function_covers_quiet_modes(self):
        # verification_prompt_forbids_stdout_redirect checks streaming-related phrases
        assert verification_prompt_forbids_stdout_redirect() is True

    def test_prompt_specifies_required_verbose_flag(self):
        prompt = get_verification_prompt()
        assert "-v" in prompt
