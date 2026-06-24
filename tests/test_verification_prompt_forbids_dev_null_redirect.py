"""Tests that the verification prompt forbids stdout/stderr redirection to /dev/null.

Feature: ee61c0b1-017e-439d-ae67-2886b73fe862
AC: pytest: tests/test_verification_prompt_forbids_dev_null_redirect.py
"""

from __future__ import annotations

from bob.superpowers import get_verification_prompt, verification_prompt_forbids_stdout_redirect


class TestVerificationPromptForbidsDevNullRedirect:
    def test_prompt_mentions_dev_null(self):
        prompt = get_verification_prompt()
        assert "/dev/null" in prompt

    def test_prompt_forbids_stdout_to_dev_null(self):
        prompt = get_verification_prompt()
        assert "> /dev/null" in prompt

    def test_prompt_forbids_stderr_to_dev_null(self):
        prompt = get_verification_prompt()
        assert "2>/dev/null" in prompt

    def test_verification_prompt_forbids_stdout_redirect_returns_true(self):
        assert verification_prompt_forbids_stdout_redirect() is True

    def test_prompt_contains_forbidden_keyword(self):
        prompt = get_verification_prompt()
        assert "FORBIDDEN" in prompt

    def test_prompt_explicitly_marks_redirect_pattern_forbidden(self):
        prompt = get_verification_prompt()
        assert "2>&1 | grep" in prompt
