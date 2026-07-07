"""Tests for superpowers.build_scoped_verification_section.

Feature: 87906c4c-2293-4bdd-a277-df6bbfa908cb
AC: pytest: tests/test_subagent_scoped_pytest_verification.py

build_scoped_verification_section builds the Verification-Before-Completion
prompt section pointed at the feature's OWN test files (extracted from
``pytest:`` acceptance criteria) instead of the full ``tests/`` suite root.
Running the full 1800+ test suite takes >30 min and gets the subagent
cancelled by max_turns before it can mark the feature complete.
"""

from __future__ import annotations

import pytest

from bob.superpowers import (
    VERIFICATION_PROMPT_SECTION,
    build_scoped_verification_section,
)


class TestBuildScopedVerificationSection:
    def test_returns_string(self):
        assert isinstance(build_scoped_verification_section(None), str)

    def test_none_returns_base_section(self):
        assert build_scoped_verification_section(None) == VERIFICATION_PROMPT_SECTION

    def test_empty_list_returns_base_section(self):
        assert build_scoped_verification_section([]) == VERIFICATION_PROMPT_SECTION

    def test_no_pytest_acs_returns_base_section(self):
        acs = ["File exists: src/bob/foo.py", "Function defined: foo.bar"]
        assert build_scoped_verification_section(acs) == VERIFICATION_PROMPT_SECTION

    def test_scoped_command_embedded_for_pytest_ac(self):
        acs = ["pytest: tests/test_foo.py"]
        result = build_scoped_verification_section(acs)
        assert "python -m pytest tests/test_foo.py -v" in result

    def test_multiple_pytest_acs_all_included(self):
        acs = ["pytest: tests/test_a.py", "pytest: tests/test_b.py"]
        result = build_scoped_verification_section(acs)
        assert "tests/test_a.py" in result
        assert "tests/test_b.py" in result
        assert "python -m pytest tests/test_a.py tests/test_b.py -v" in result

    def test_scoped_result_extends_base_section(self):
        acs = ["pytest: tests/test_foo.py"]
        result = build_scoped_verification_section(acs)
        assert result.startswith(VERIFICATION_PROMPT_SECTION)
        assert len(result) > len(VERIFICATION_PROMPT_SECTION)

    def test_scoped_result_warns_against_full_suite(self):
        acs = ["pytest: tests/test_foo.py"]
        result = build_scoped_verification_section(acs)
        assert "tests/ -v" in result  # warning references the full-suite command

    def test_result_always_contains_checklist(self):
        for acs in [None, [], ["pytest: tests/test_x.py"]]:
            result = build_scoped_verification_section(acs)
            assert "Verification Before Completion Checklist" in result


class TestBuildScopedVerificationSectionBoundary:
    def test_pytest_ac_empty_path_falls_back(self):
        result = build_scoped_verification_section(["pytest: "])
        assert result == VERIFICATION_PROMPT_SECTION

    def test_single_empty_string_falls_back(self):
        assert build_scoped_verification_section([""]) == VERIFICATION_PROMPT_SECTION


class TestBuildScopedVerificationSectionErrors:
    def test_non_list_non_none_raises(self):
        with pytest.raises(ValueError):
            build_scoped_verification_section("pytest: tests/test_foo.py")

    def test_integer_raises(self):
        with pytest.raises(ValueError):
            build_scoped_verification_section(42)

    def test_bool_raises(self):
        with pytest.raises(ValueError):
            build_scoped_verification_section(True)

    def test_non_string_item_raises(self):
        with pytest.raises(ValueError):
            build_scoped_verification_section([123])

    def test_error_message_mentions_acceptance_criteria(self):
        with pytest.raises(ValueError, match=r"(?i)acceptance.criteria|list"):
            build_scoped_verification_section("bad")
