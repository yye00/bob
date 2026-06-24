"""Tests that the verification prompt explains the observability rationale.

Feature: ee61c0b1-017e-439d-ae67-2886b73fe862
AC: pytest: tests/test_verification_prompt_mentions_observability_rationale.py
"""

from __future__ import annotations

from bob.superpowers import get_verification_prompt


class TestVerificationPromptMentionsObservabilityRationale:
    def test_prompt_mentions_streaming(self):
        prompt = get_verification_prompt()
        assert "streaming" in prompt

    def test_prompt_mentions_hung_process_risk(self):
        prompt = get_verification_prompt()
        assert "hung" in prompt.lower() or "hang" in prompt.lower() or "stall" in prompt.lower()

    def test_prompt_mentions_silent_failure(self):
        prompt = get_verification_prompt()
        assert "silent" in prompt

    def test_prompt_explains_streaming_is_only_signal(self):
        prompt = get_verification_prompt()
        assert "ONLY signal" in prompt

    def test_prompt_mentions_cpu_usage_as_indicator(self):
        prompt = get_verification_prompt()
        # The rationale mentions a process running at full CPU with no output
        assert "CPU" in prompt or "minutes" in prompt

    def test_prompt_contains_observability_mandate_heading(self):
        prompt = get_verification_prompt()
        assert "Observability Mandate" in prompt or "observability" in prompt.lower()

    def test_prompt_mentions_zero_observability(self):
        prompt = get_verification_prompt()
        assert "zero" in prompt.lower()
