"""Boundary tests for the pytest observability section in the verification prompt.

Feature: ee61c0b1-017e-439d-ae67-2886b73fe862
AC: pytest: tests/test_verification_prompt_boundary_no_pytest_section.py
"""

from __future__ import annotations

from bob.superpowers import (
    VERIFICATION_PROMPT_SECTION,
    get_verification_prompt,
    verification_prompt_forbids_stdout_redirect,
)


class TestVerificationPromptBoundaryNoPytestSection:
    def test_get_verification_prompt_returns_string(self):
        result = get_verification_prompt()
        assert isinstance(result, str)

    def test_get_verification_prompt_returns_nonempty_string(self):
        result = get_verification_prompt()
        assert len(result) > 0

    def test_verification_prompt_constant_matches_function(self):
        assert get_verification_prompt() == VERIFICATION_PROMPT_SECTION

    def test_prompt_still_contains_original_checklist(self):
        prompt = get_verification_prompt()
        assert "Files exist" in prompt
        assert "No stubs" in prompt
        assert "No mocks in production" in prompt
        assert "Tests pass" in prompt
        assert "Real tests" in prompt
        assert "No regressions" in prompt

    def test_forbids_function_returns_false_when_prompt_missing_redirect_phrase(self):
        # Verify the helper detects absence: monkeypatch VERIFICATION_PROMPT_SECTION
        import bob.superpowers as sp
        original = sp.VERIFICATION_PROMPT_SECTION
        try:
            sp.VERIFICATION_PROMPT_SECTION = "no relevant content here"
            result = sp.verification_prompt_forbids_stdout_redirect()
            assert result is False
        finally:
            sp.VERIFICATION_PROMPT_SECTION = original

    def test_forbids_function_returns_true_for_real_prompt(self):
        assert verification_prompt_forbids_stdout_redirect() is True

    def test_observability_section_appears_after_original_checklist(self):
        prompt = get_verification_prompt()
        checklist_pos = prompt.find("Verification Before Completion Checklist")
        observability_pos = prompt.find("Observability Mandate")
        assert checklist_pos != -1
        assert observability_pos != -1
        assert observability_pos > checklist_pos
