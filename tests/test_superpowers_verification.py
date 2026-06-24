"""Tests for superpowers.VERIFICATION_PROMPT_SECTION scoped-pytest behavior.

Feature: 83020d42-3e1a-4170-b407-1ac221f01e05
AC: pytest: tests/test_superpowers_verification.py

Verifies that VERIFICATION_PROMPT_SECTION instructs subagents to use scoped
pytest (pointing at feature-specific test files) rather than the full suite
root (python -m pytest tests/ -v), which takes >30 min and causes max_turns
cancellation before the subagent can report completion.
"""

from __future__ import annotations

import pytest

from bob.superpowers import (
    VERIFICATION_PROMPT_SECTION,
    build_scoped_pytest_invocation,
    get_verification_prompt,
    extract_pytest_paths,
)


class TestVerificationPromptSectionExists:
    """VERIFICATION_PROMPT_SECTION must be a non-empty string."""

    def test_verification_prompt_section_is_string(self):
        assert isinstance(VERIFICATION_PROMPT_SECTION, str)

    def test_verification_prompt_section_is_non_empty(self):
        assert len(VERIFICATION_PROMPT_SECTION.strip()) > 0


class TestVerificationPromptWarnsFullSuite:
    """VERIFICATION_PROMPT_SECTION must warn against running the full suite."""

    def test_warns_against_full_suite(self):
        assert "python -m pytest tests/ -v" in VERIFICATION_PROMPT_SECTION or \
               "Do NOT run" in VERIFICATION_PROMPT_SECTION

    def test_warns_duration(self):
        """Must mention the time cost so subagents understand the risk."""
        lower = VERIFICATION_PROMPT_SECTION.lower()
        assert "30" in lower or "minutes" in lower or "1800" in lower

    def test_contains_scoped_instruction(self):
        """Must instruct running only the feature's own test files."""
        lower = VERIFICATION_PROMPT_SECTION.lower()
        assert "scoped" in lower or "pytest:" in lower or "your feature" in lower


class TestVerificationPromptContainsChecklist:
    """VERIFICATION_PROMPT_SECTION must contain verification checklist items."""

    def test_contains_files_exist_item(self):
        assert "Files exist" in VERIFICATION_PROMPT_SECTION or \
               "files exist" in VERIFICATION_PROMPT_SECTION.lower()

    def test_contains_no_stubs_item(self):
        lower = VERIFICATION_PROMPT_SECTION.lower()
        assert "stub" in lower or "no stubs" in lower

    def test_contains_tests_pass_item(self):
        lower = VERIFICATION_PROMPT_SECTION.lower()
        assert "tests pass" in lower or "test" in lower


class TestGetVerificationPromptScopesTests:
    """get_verification_prompt() with pytest: ACs must include scoped command."""

    def test_no_acs_returns_base_section(self):
        """Without ACs, returns the base VERIFICATION_PROMPT_SECTION text."""
        result = get_verification_prompt(None)
        assert result == VERIFICATION_PROMPT_SECTION

    def test_empty_acs_returns_base_section(self):
        result = get_verification_prompt([])
        assert result == VERIFICATION_PROMPT_SECTION

    def test_with_pytest_ac_includes_scoped_path(self):
        """With a pytest: AC, result includes the specific test file path."""
        acs = ["pytest: tests/test_myfeature.py"]
        result = get_verification_prompt(acs)
        assert "tests/test_myfeature.py" in result

    def test_with_pytest_ac_does_not_recommend_full_suite_as_command(self):
        """When ACs specify test files, must not suggest 'python -m pytest tests/ -v' as the command."""
        acs = ["pytest: tests/test_myfeature.py"]
        result = get_verification_prompt(acs)
        scoped_cmd = "python -m pytest tests/test_myfeature.py -v"
        assert scoped_cmd in result

    def test_with_multiple_pytest_acs_includes_all_paths(self):
        acs = [
            "pytest: tests/test_foo.py",
            "pytest: tests/test_bar.py",
            "File exists: src/foo.py",
        ]
        result = get_verification_prompt(acs)
        assert "tests/test_foo.py" in result
        assert "tests/test_bar.py" in result

    def test_non_pytest_acs_not_included_in_command(self):
        """Non-pytest: ACs do not appear in the pytest command."""
        acs = [
            "File exists: src/foo.py",
            "Function defined: foo.bar",
            "pytest: tests/test_foo.py",
        ]
        result = get_verification_prompt(acs)
        assert "File exists" not in "python -m pytest " + result.split("python -m pytest")[-1].split("\n")[0]


class TestExtractPytestPaths:
    """extract_pytest_paths must extract only pytest:-prefixed paths."""

    def test_none_returns_empty(self):
        assert extract_pytest_paths(None) == []

    def test_empty_list_returns_empty(self):
        assert extract_pytest_paths([]) == []

    def test_single_pytest_ac(self):
        result = extract_pytest_paths(["pytest: tests/test_foo.py"])
        assert result == ["tests/test_foo.py"]

    def test_mixed_acs_extracts_only_pytest(self):
        acs = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo.py",
            "Function defined: foo.bar",
            "pytest: tests/test_bar.py",
        ]
        result = extract_pytest_paths(acs)
        assert result == ["tests/test_foo.py", "tests/test_bar.py"]

    def test_case_insensitive_prefix(self):
        """pytest: prefix matching is case-insensitive."""
        result = extract_pytest_paths(["PYTEST: tests/test_foo.py"])
        assert "tests/test_foo.py" in result

    def test_path_with_extra_description_included(self):
        """Paths with trailing description (after dash) are included as-is."""
        ac = "pytest: tests/test_foo.py — boundary case for empty input"
        result = extract_pytest_paths([ac])
        assert len(result) == 1
        assert result[0].startswith("tests/test_foo.py")


class TestBuildScopedPytestInvocation:
    """build_scoped_pytest_invocation must produce the right command string."""

    def test_with_no_acs_falls_back_to_tests_root(self):
        """Without pytest: ACs, falls back to tests/ — must warn in context."""
        result = build_scoped_pytest_invocation(None)
        assert result == "python -m pytest tests/ -v"

    def test_with_pytest_ac_produces_scoped_command(self):
        acs = ["pytest: tests/test_myfeature.py"]
        result = build_scoped_pytest_invocation(acs)
        assert result == "python -m pytest tests/test_myfeature.py -v"

    def test_with_multiple_pytest_acs_includes_all(self):
        acs = ["pytest: tests/test_foo.py", "pytest: tests/test_bar.py"]
        result = build_scoped_pytest_invocation(acs)
        assert "tests/test_foo.py" in result
        assert "tests/test_bar.py" in result
        assert result.startswith("python -m pytest")
        assert result.endswith(" -v")

    def test_result_is_string(self):
        result = build_scoped_pytest_invocation([])
        assert isinstance(result, str)
