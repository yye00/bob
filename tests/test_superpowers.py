"""Tests that VERIFICATION_PROMPT_SECTION and SUPERPOWERS_ORIENTATION_SECTION
instruct subagents to run scoped pytest (feature-specific test files) rather
than the full test suite.

Feature: Subagent self-verification must use scoped pytest, not full-suite
AC: pytest: tests/test_superpowers.py
"""

import pytest

from bob.superpowers import (
    VERIFICATION_PROMPT_SECTION,
    SUPERPOWERS_ORIENTATION_SECTION,
    build_scoped_pytest_invocation,
    extract_pytest_paths,
    get_feature_test_files,
    get_verification_prompt,
    get_superpowers_orientation,
)


class TestVerificationPromptSectionScoped:
    """VERIFICATION_PROMPT_SECTION must warn against the full suite and
    instruct subagents to use scoped pytest paths."""

    def test_verification_prompt_warns_against_full_suite(self):
        """VERIFICATION_PROMPT_SECTION must explicitly warn against running
        the full test suite."""
        assert "Do NOT run the full test suite" in VERIFICATION_PROMPT_SECTION or \
               "do NOT run" in VERIFICATION_PROMPT_SECTION or \
               "Do NOT run" in VERIFICATION_PROMPT_SECTION

    def test_verification_prompt_no_unqualified_full_suite_instruction(self):
        """VERIFICATION_PROMPT_SECTION must not instruct subagents to run
        `python -m pytest tests/ -v` as the primary command (only as a warning
        of what NOT to do)."""
        lines = VERIFICATION_PROMPT_SECTION.splitlines()
        for line in lines:
            stripped = line.strip()
            # The word "Run" followed by `python -m pytest tests/ -v` would be
            # an instruction to run the full suite. The only valid occurrence is
            # in the warning that says NOT to run it.
            if "python -m pytest tests/ -v" in stripped:
                # Must be in a warning/forbidden context, not as a primary instruction
                assert any(
                    neg in stripped
                    for neg in ("NOT", "WARNING", "FORBIDDEN", "do not", "Don't", "don't")
                ), (
                    f"Line appears to instruct full-suite run without a warning: {stripped!r}"
                )

    def test_verification_prompt_references_scoped_pytest(self):
        """VERIFICATION_PROMPT_SECTION must reference running scoped/feature-specific tests."""
        prompt = VERIFICATION_PROMPT_SECTION
        # The prompt must mention scoped or feature-specific test running
        assert any(phrase in prompt for phrase in [
            "scoped",
            "pytest:` AC",
            "pytest:` ACs",
            "feature's test files",
            "feature's own test files",
            "YOUR feature",
        ]), "Verification prompt must reference running scoped/feature-specific tests"

    def test_verification_prompt_item4_not_full_suite(self):
        """Item 4 in the verification checklist must NOT say 'run python -m pytest -v'
        without qualification (which would invoke the full suite)."""
        prompt = VERIFICATION_PROMPT_SECTION
        # Look for item 4 in the checklist
        lines = prompt.splitlines()
        item4_lines = []
        capture = False
        for line in lines:
            if line.strip().startswith("4.") and "Tests pass" in line:
                capture = True
            elif capture and line.strip().startswith(("5.", "6.", "7.")):
                break
            if capture:
                item4_lines.append(line)

        item4_text = "\n".join(item4_lines)
        # Item 4 must not simply say run pytest -v (full suite)
        assert "python -m pytest -v" not in item4_text or "scoped" in item4_text or "YOUR feature" in item4_text, (
            f"Item 4 appears to direct running the full suite without scoping:\n{item4_text}"
        )


class TestOrientationSectionScoped:
    """SUPERPOWERS_ORIENTATION_SECTION item 4 must not instruct the full suite."""

    def test_orientation_verification_item4_not_unqualified_full_suite(self):
        """In SUPERPOWERS_ORIENTATION_SECTION, the Verification skill's item 4
        must NOT say 'Run `python -m pytest -v`' (full suite instruction)."""
        orientation = SUPERPOWERS_ORIENTATION_SECTION
        # Find the Verification Before Completion section
        idx = orientation.find("Verification Before Completion")
        assert idx != -1, "Orientation must contain Verification Before Completion section"
        verification_section = orientation[idx:]

        # Within this section, find item 4
        item4_idx = verification_section.find("4.")
        if item4_idx == -1:
            return  # No item 4 found, can't check

        item4_end = verification_section.find("\n5.", item4_idx)
        if item4_end == -1:
            item4_end = len(verification_section)
        item4_text = verification_section[item4_idx:item4_end]

        # The item must not say "Run `python -m pytest -v`" without qualification
        assert "python -m pytest -v" not in item4_text, (
            f"Orientation section item 4 instructs the full pytest suite:\n{item4_text!r}\n"
            "This causes subagents to run 1800+ tests and get cancelled before completion."
        )

    def test_orientation_verification_item4_references_scoped_pytest(self):
        """The Verification Before Completion section in SUPERPOWERS_ORIENTATION_SECTION
        must instruct subagents to run ONLY their feature's test files."""
        orientation = SUPERPOWERS_ORIENTATION_SECTION
        idx = orientation.find("Verification Before Completion")
        assert idx != -1
        verification_section = orientation[idx:]

        # Must mention scoped or feature-specific pytest
        assert any(phrase in verification_section for phrase in [
            "scoped",
            "feature's test",
            "pytest:` AC",
            "YOUR feature",
            "own test files",
            "feature-specific",
        ]), (
            "Orientation Verification section must direct subagents to scoped pytest, "
            "not the full test suite."
        )

    def test_get_superpowers_orientation_matches_constant(self):
        """get_superpowers_orientation() must return SUPERPOWERS_ORIENTATION_SECTION."""
        assert get_superpowers_orientation() == SUPERPOWERS_ORIENTATION_SECTION

    def test_orientation_does_not_contain_run_pytest_v_alone(self):
        """SUPERPOWERS_ORIENTATION_SECTION must not contain an unqualified
        'Run `python -m pytest -v`' instruction anywhere."""
        # The pattern that's wrong: "Run `python -m pytest -v`" as an instruction
        problematic = "Run `python -m pytest -v`"
        assert problematic not in SUPERPOWERS_ORIENTATION_SECTION, (
            f"Found unqualified full-suite pytest instruction in orientation: {problematic!r}"
        )


class TestBuildScopedPytestInvocationIntegration:
    """Verify build_scoped_pytest_invocation integrates with the prompt sections."""

    def test_build_scoped_invocation_with_feature_acs(self):
        """With pytest: ACs, build_scoped_pytest_invocation returns scoped command."""
        acs = [
            "File exists: src/bob/superpowers.py",
            "Function defined: bob.superpowers.VERIFICATION_PROMPT_SECTION",
            "pytest: tests/test_superpowers.py",
            "integration: bob.superpowers",
        ]
        result = build_scoped_pytest_invocation(acs)
        assert result == "python -m pytest tests/test_superpowers.py -v"

    def test_build_scoped_invocation_no_pytest_acs_falls_back(self):
        """With no pytest: ACs, fall back to full suite (still correct for
        features without explicit test paths)."""
        acs = ["File exists: src/foo.py", "Function defined: foo.bar"]
        result = build_scoped_pytest_invocation(acs)
        assert result == "python -m pytest tests/ -v"

    def test_build_scoped_invocation_multiple_pytest_acs(self):
        """Multiple pytest: ACs produce a space-separated paths command."""
        acs = [
            "pytest: tests/test_foo.py",
            "pytest: tests/test_bar.py",
        ]
        result = build_scoped_pytest_invocation(acs)
        assert "tests/test_foo.py" in result
        assert "tests/test_bar.py" in result
        assert result.startswith("python -m pytest ")
        assert result.endswith(" -v")

    def test_get_verification_prompt_with_pytest_acs_includes_scoped_cmd(self):
        """get_verification_prompt with pytest: ACs embeds the scoped command."""
        acs = ["pytest: tests/test_superpowers.py"]
        prompt = get_verification_prompt(acs)
        assert "tests/test_superpowers.py" in prompt
        assert "python -m pytest tests/test_superpowers.py -v" in prompt

    def test_get_verification_prompt_without_acs_returns_base_section(self):
        """get_verification_prompt without ACs returns VERIFICATION_PROMPT_SECTION."""
        prompt = get_verification_prompt()
        assert prompt == VERIFICATION_PROMPT_SECTION

    def test_get_verification_prompt_with_no_pytest_acs_returns_base_section(self):
        """get_verification_prompt with ACs lacking pytest: prefix returns base."""
        acs = ["File exists: src/foo.py"]
        prompt = get_verification_prompt(acs)
        assert prompt == VERIFICATION_PROMPT_SECTION


class TestExtractPytestPaths:
    """extract_pytest_paths extracts pytest: AC entries as path strings."""

    def test_verification_uses_scoped_pytest(self):
        """Subagent verification must use scoped pytest paths extracted from pytest: ACs,
        not the full test suite. extract_pytest_paths returns paths from pytest: ACs so
        the verification prompt can be scoped per-feature."""
        acs = [
            "File exists: src/bob/superpowers.py",
            "Function defined: bob.superpowers.extract_pytest_paths",
            "pytest: tests/test_superpowers.py::test_verification_uses_scoped_pytest",
            "integration: bob.superpowers",
        ]
        paths = extract_pytest_paths(acs)
        assert paths == ["tests/test_superpowers.py::test_verification_uses_scoped_pytest"]

    def test_extract_pytest_paths_empty(self):
        """Returns empty list when no pytest: ACs are present."""
        acs = ["File exists: src/foo.py", "Function defined: foo.bar"]
        assert extract_pytest_paths(acs) == []

    def test_extract_pytest_paths_none(self):
        """Returns empty list for None input."""
        assert extract_pytest_paths(None) == []

    def test_extract_pytest_paths_multiple(self):
        """Returns all paths when multiple pytest: ACs are present."""
        acs = [
            "pytest: tests/test_foo.py",
            "pytest: tests/test_bar.py::TestClass::test_method",
        ]
        paths = extract_pytest_paths(acs)
        assert paths == ["tests/test_foo.py", "tests/test_bar.py::TestClass::test_method"]

    def test_extract_pytest_paths_strips_whitespace(self):
        """Strips leading/trailing whitespace from extracted paths."""
        acs = ["pytest:   tests/test_foo.py  "]
        paths = extract_pytest_paths(acs)
        assert paths == ["tests/test_foo.py"]

    def test_extract_pytest_paths_case_insensitive_prefix(self):
        """pytest: prefix matching is case-insensitive."""
        acs = ["Pytest: tests/test_foo.py", "PYTEST: tests/test_bar.py"]
        paths = extract_pytest_paths(acs)
        assert "tests/test_foo.py" in paths
        assert "tests/test_bar.py" in paths

    def test_extract_pytest_paths_skips_empty_paths(self):
        """Skips entries where path after pytest: is empty."""
        acs = ["pytest: ", "pytest:", "pytest: tests/test_foo.py"]
        paths = extract_pytest_paths(acs)
        assert paths == ["tests/test_foo.py"]

    def test_build_scoped_pytest_invocation_uses_extract(self):
        """build_scoped_pytest_invocation result matches extract_pytest_paths output."""
        acs = [
            "pytest: tests/test_superpowers.py",
            "pytest: tests/test_foo.py",
        ]
        paths = extract_pytest_paths(acs)
        invocation = build_scoped_pytest_invocation(acs)
        for p in paths:
            assert p in invocation


class TestGetFeatureTestFiles:
    """get_feature_test_files extracts scoped pytest paths from pytest: ACs."""

    def test_returns_pytest_ac_paths(self):
        """Returns paths from pytest: ACs for the feature."""
        acs = [
            "File exists: src/bob/superpowers.py",
            "Function defined: bob.superpowers.get_feature_test_files",
            "pytest: tests/test_superpowers.py",
            "integration: bob.superpowers",
        ]
        result = get_feature_test_files(acs)
        assert result == ["tests/test_superpowers.py"]

    def test_returns_empty_for_no_pytest_acs(self):
        """Returns empty list when no pytest: ACs are present."""
        acs = ["File exists: src/foo.py", "Function defined: foo.bar"]
        assert get_feature_test_files(acs) == []

    def test_returns_empty_for_none(self):
        """Returns empty list for None input."""
        assert get_feature_test_files(None) == []

    def test_returns_multiple_paths(self):
        """Returns all paths when multiple pytest: ACs are present."""
        acs = [
            "pytest: tests/test_foo.py",
            "pytest: tests/test_bar.py",
        ]
        result = get_feature_test_files(acs)
        assert result == ["tests/test_foo.py", "tests/test_bar.py"]

    def test_strips_whitespace_from_paths(self):
        """Strips leading/trailing whitespace from extracted paths."""
        acs = ["pytest:   tests/test_foo.py  "]
        result = get_feature_test_files(acs)
        assert result == ["tests/test_foo.py"]

    def test_case_insensitive_prefix(self):
        """pytest: prefix matching is case-insensitive."""
        acs = ["Pytest: tests/test_foo.py", "PYTEST: tests/test_bar.py"]
        result = get_feature_test_files(acs)
        assert "tests/test_foo.py" in result
        assert "tests/test_bar.py" in result

    def test_skips_empty_paths(self):
        """Skips entries where path after pytest: is empty."""
        acs = ["pytest: ", "pytest:", "pytest: tests/test_foo.py"]
        result = get_feature_test_files(acs)
        assert result == ["tests/test_foo.py"]

    def test_matches_extract_pytest_paths(self):
        """get_feature_test_files returns same result as extract_pytest_paths."""
        acs = [
            "pytest: tests/test_superpowers.py",
            "pytest: tests/test_foo.py",
            "File exists: src/foo.py",
        ]
        assert get_feature_test_files(acs) == extract_pytest_paths(acs)

    def test_supports_node_id_paths(self):
        """Handles pytest node IDs with :: separators."""
        acs = ["pytest: tests/test_foo.py::TestClass::test_method"]
        result = get_feature_test_files(acs)
        assert result == ["tests/test_foo.py::TestClass::test_method"]

    def test_scoped_not_full_suite(self):
        """get_feature_test_files returns the feature's own test files, not tests/."""
        acs = ["pytest: tests/test_superpowers.py"]
        result = get_feature_test_files(acs)
        assert result != ["tests/"]
        assert result == ["tests/test_superpowers.py"]


class TestOrientationWarnsMandateCompliance:
    """The orientation prompt must contain the observability mandate (no redirects)."""

    def test_orientation_contains_observability_mandate_or_reference(self):
        """The SUPERPOWERS_ORIENTATION_SECTION or VERIFICATION_PROMPT_SECTION must
        contain the pytest stdout redirect prohibition (NEVER Redirect or equivalent).
        The prompt subagents receive must carry this warning."""
        # The mandate lives in VERIFICATION_PROMPT_SECTION which is the canonical
        # reference; orientation may reference it or include it directly.
        prompt = get_verification_prompt()
        assert "NEVER Redirect" in prompt or "FORBIDDEN" in prompt, (
            "The verification prompt subagents receive must include the "
            "observability mandate (no stdout redirect)"
        )
