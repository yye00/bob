"""Tests that get_verification_prompt injects a scoped pytest command when ACs supply paths.

Feature: 9901139e-bde3-4f3d-b648-f83d2494f98d
AC: pytest: tests/test_verification_prompt_uses_scoped_pytest.py
"""

from __future__ import annotations

from bob.superpowers import (
    VERIFICATION_PROMPT_SECTION,
    build_scoped_pytest_invocation,
    get_verification_prompt,
)


class TestGetVerificationPromptScopedPytest:
    def test_no_acs_returns_base_section(self):
        result = get_verification_prompt()
        assert result == VERIFICATION_PROMPT_SECTION

    def test_none_acs_returns_base_section(self):
        result = get_verification_prompt(None)
        assert result == VERIFICATION_PROMPT_SECTION

    def test_empty_list_returns_base_section(self):
        result = get_verification_prompt([])
        assert result == VERIFICATION_PROMPT_SECTION

    def test_acs_with_pytest_prefix_inject_scoped_command(self):
        acs = ["pytest: tests/test_foo.py", "Function defined: bar"]
        result = get_verification_prompt(acs)
        assert "python -m pytest tests/test_foo.py -v" in result

    def test_acs_with_multiple_pytest_paths(self):
        acs = [
            "pytest: tests/test_alpha.py",
            "pytest: tests/test_beta.py",
            "Function defined: baz",
        ]
        result = get_verification_prompt(acs)
        assert "tests/test_alpha.py" in result
        assert "tests/test_beta.py" in result

    def test_scoped_prompt_still_contains_base_content(self):
        acs = ["pytest: tests/test_x.py"]
        result = get_verification_prompt(acs)
        assert "Verification Before Completion Checklist" in result
        assert "Pytest Observability Mandate" in result

    def test_scoped_prompt_warns_against_full_suite(self):
        acs = ["pytest: tests/test_x.py"]
        result = get_verification_prompt(acs)
        assert "Do NOT run" in result

    def test_acs_without_pytest_prefix_returns_base_section(self):
        acs = ["Function defined: foo", "integration: bob.bar"]
        result = get_verification_prompt(acs)
        assert result == VERIFICATION_PROMPT_SECTION

    def test_scoped_section_header_present(self):
        acs = ["pytest: tests/test_something.py"]
        result = get_verification_prompt(acs)
        assert "Scoped Pytest Command" in result

    def test_base_section_warns_against_full_suite(self):
        result = get_verification_prompt()
        assert "Do NOT run the full test suite" in result
