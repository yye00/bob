"""Tests for VERIFICATION_PROMPT_SECTION and get_verification_prompt in bob3.superpowers.

Feature: cbc97518-7499-47c7-a26b-0ab1b8e206f3
AC: pytest: tests/test_subagent_verification.py

Verifies that the subagent verification prompt instructs subagents to use
scoped pytest (their own feature's test files extracted from 'pytest:' ACs)
rather than the full test suite ('python -m pytest tests/ -v'), preventing
max_turns cancellation from running 1800+ tests.
"""

from __future__ import annotations

import bob3.superpowers as superpowers
from bob3.superpowers import (
    VERIFICATION_PROMPT_SECTION,
    build_scoped_pytest_invocation,
    extract_pytest_paths,
    get_scoped_pytest_command,
    get_verification_prompt,
)


class TestVerificationPromptSectionExists:
    """VERIFICATION_PROMPT_SECTION must exist and be non-empty."""

    def test_section_is_string(self):
        assert isinstance(VERIFICATION_PROMPT_SECTION, str)

    def test_section_is_non_empty(self):
        assert len(VERIFICATION_PROMPT_SECTION.strip()) > 0

    def test_section_accessible_on_module(self):
        assert hasattr(superpowers, "VERIFICATION_PROMPT_SECTION")
        assert superpowers.VERIFICATION_PROMPT_SECTION is VERIFICATION_PROMPT_SECTION


class TestVerificationPromptWarnsFullSuite:
    """The prompt must explicitly warn against running the full test suite."""

    def test_warns_against_full_suite_command(self):
        assert "python -m pytest tests/ -v" in VERIFICATION_PROMPT_SECTION

    def test_warns_about_full_suite_size(self):
        assert "1800" in VERIFICATION_PROMPT_SECTION or "30 min" in VERIFICATION_PROMPT_SECTION

    def test_says_do_not_run_full_suite(self):
        lower = VERIFICATION_PROMPT_SECTION.lower()
        assert "do not" in lower or "don't" in lower or "warning" in lower

    def test_mentions_scoped_pytest_acs(self):
        assert "pytest:" in VERIFICATION_PROMPT_SECTION or "scoped" in VERIFICATION_PROMPT_SECTION.lower()


class TestGetVerificationPrompt:
    """get_verification_prompt() returns scoped command when pytest: ACs present."""

    def test_no_acs_returns_section(self):
        result = get_verification_prompt()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_none_returns_section(self):
        result = get_verification_prompt(None)
        assert isinstance(result, str)
        assert VERIFICATION_PROMPT_SECTION in result or result == VERIFICATION_PROMPT_SECTION

    def test_empty_list_returns_section(self):
        result = get_verification_prompt([])
        assert isinstance(result, str)

    def test_with_pytest_acs_includes_scoped_command(self):
        acs = ["pytest: tests/test_my_feature.py"]
        result = get_verification_prompt(acs)
        assert "tests/test_my_feature.py" in result

    def test_with_pytest_acs_scoped_command_starts_correctly(self):
        acs = ["pytest: tests/test_my_feature.py"]
        result = get_verification_prompt(acs)
        assert "python -m pytest tests/test_my_feature.py" in result

    def test_with_pytest_acs_warns_against_full_suite(self):
        acs = ["pytest: tests/test_alpha.py", "pytest: tests/test_beta.py"]
        result = get_verification_prompt(acs)
        # Still warns about full suite even when scoped paths present
        lower = result.lower()
        assert "30 min" in lower or ">30" in lower or "not" in lower

    def test_with_multiple_pytest_acs_includes_all(self):
        acs = [
            "pytest: tests/test_alpha.py",
            "pytest: tests/test_beta.py::test_case",
            "File exists: src/bob3/my_module.py",
        ]
        result = get_verification_prompt(acs)
        assert "tests/test_alpha.py" in result
        assert "tests/test_beta.py::test_case" in result

    def test_non_pytest_acs_not_included_as_paths(self):
        acs = [
            "File exists: src/bob3/my_module.py",
            "Function defined: my_module.do_thing",
        ]
        result = get_verification_prompt(acs)
        # Should not produce a scoped path from non-pytest ACs
        assert "src/bob3/my_module.py" not in result.replace(VERIFICATION_PROMPT_SECTION, "")


class TestExtractPytestPaths:
    """extract_pytest_paths extracts only pytest: AC entries."""

    def test_none_returns_empty(self):
        assert extract_pytest_paths(None) == []

    def test_empty_list_returns_empty(self):
        assert extract_pytest_paths([]) == []

    def test_no_pytest_acs_returns_empty(self):
        acs = ["File exists: src/foo.py", "Function defined: foo.bar"]
        assert extract_pytest_paths(acs) == []

    def test_single_pytest_ac_extracted(self):
        acs = ["pytest: tests/test_foo.py"]
        result = extract_pytest_paths(acs)
        assert result == ["tests/test_foo.py"]

    def test_multiple_pytest_acs_extracted(self):
        acs = [
            "pytest: tests/test_alpha.py",
            "File exists: src/bob3/x.py",
            "pytest: tests/test_beta.py::test_case",
        ]
        result = extract_pytest_paths(acs)
        assert result == ["tests/test_alpha.py", "tests/test_beta.py::test_case"]

    def test_pytest_ac_with_description_after_dash_extracted(self):
        acs = ["pytest: tests/test_boundary.py — boundary case description"]
        result = extract_pytest_paths(acs)
        # The path token is everything after "pytest: " — trim at space before em-dash
        assert len(result) == 1
        assert result[0].startswith("tests/test_boundary.py")


class TestBuildScopedPytestInvocation:
    """build_scoped_pytest_invocation returns scoped command from ACs."""

    def test_none_falls_back_to_full_suite(self):
        result = build_scoped_pytest_invocation(None)
        assert result == "python -m pytest tests/ -v"

    def test_empty_list_falls_back_to_full_suite(self):
        result = build_scoped_pytest_invocation([])
        assert result == "python -m pytest tests/ -v"

    def test_with_pytest_acs_returns_scoped(self):
        acs = ["pytest: tests/test_foo.py"]
        result = build_scoped_pytest_invocation(acs)
        assert result == "python -m pytest tests/test_foo.py -v"
        assert "tests/ " not in result

    def test_with_multiple_pytest_acs_returns_all_paths(self):
        acs = ["pytest: tests/test_a.py", "pytest: tests/test_b.py"]
        result = build_scoped_pytest_invocation(acs)
        assert "tests/test_a.py" in result
        assert "tests/test_b.py" in result
        assert result.startswith("python -m pytest ")
        assert result.endswith(" -v")


class TestScopedPytestIntegration:
    """Integration: the full pipeline from ACs → scoped command works end-to-end."""

    def test_feature_acs_produce_scoped_not_full_command(self):
        """The feature's own ACs produce a scoped command, not the full-suite."""
        feature_acs = [
            "File exists: superpowers.py",
            "Function defined: superpowers.VERIFICATION_PROMPT_SECTION",
            "pytest: tests/test_subagent_verification.py",
            "integration: superpowers",
            "pytest: tests/test_subagent_self_verification_must_use_scoped_pytest__boundary.py",
            "pytest: tests/test_subagent_self_verification_must_use_scoped_pytest__error.py",
        ]
        cmd = get_scoped_pytest_command(feature_acs)
        assert cmd != "python -m pytest tests/ -v", (
            "Scoped command must not be the full-suite fallback when pytest: ACs are present"
        )
        assert "tests/test_subagent_verification.py" in cmd
        assert "tests/test_subagent_self_verification_must_use_scoped_pytest__boundary.py" in cmd
        assert "tests/test_subagent_self_verification_must_use_scoped_pytest__error.py" in cmd

    def test_prompt_with_feature_acs_shows_scoped_cmd(self):
        """get_verification_prompt with feature ACs embeds scoped command."""
        feature_acs = [
            "pytest: tests/test_subagent_verification.py",
            "pytest: tests/test_subagent_self_verification_must_use_scoped_pytest__boundary.py",
        ]
        prompt = get_verification_prompt(feature_acs)
        assert "tests/test_subagent_verification.py" in prompt
        assert "tests/test_subagent_self_verification_must_use_scoped_pytest__boundary.py" in prompt

    def test_verification_prompt_forbids_stdout_redirect(self):
        """The verification prompt must contain the no-redirect mandate."""
        from bob3.superpowers import verification_prompt_forbids_stdout_redirect
        assert verification_prompt_forbids_stdout_redirect() is True
