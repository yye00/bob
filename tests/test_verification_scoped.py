"""Tests for superpowers.verification.extract_pytest_ac_paths.

Feature: 88a1e31f-9122-4493-b4db-0c4214806a8c
AC: pytest: tests/test_verification_scoped.py

Verifies that subagent self-verification uses scoped pytest (only the
``pytest:``-prefixed AC test files) rather than the full test suite root.
"""

from __future__ import annotations

import pytest

from superpowers.verification import extract_pytest_ac_paths


class TestExtractPytestAcPaths:
    """Core behaviour of extract_pytest_ac_paths."""

    def test_none_returns_empty_list(self):
        """None input returns an empty list without raising."""
        result = extract_pytest_ac_paths(None)
        assert result == []

    def test_empty_list_returns_empty_list(self):
        """Empty list returns an empty list."""
        result = extract_pytest_ac_paths([])
        assert result == []

    def test_single_pytest_ac_extracted(self):
        """A single pytest: AC yields one path."""
        acs = ["pytest: tests/test_foo.py"]
        result = extract_pytest_ac_paths(acs)
        assert result == ["tests/test_foo.py"]

    def test_multiple_pytest_acs_extracted_in_order(self):
        """Multiple pytest: ACs yield paths in document order."""
        acs = [
            "pytest: tests/test_alpha.py",
            "File exists: src/alpha.py",
            "pytest: tests/test_beta.py",
        ]
        result = extract_pytest_ac_paths(acs)
        assert result == ["tests/test_alpha.py", "tests/test_beta.py"]

    def test_non_pytest_acs_ignored(self):
        """ACs without pytest: prefix are not included."""
        acs = [
            "File exists: src/superpowers/verification.py",
            "Function defined: superpowers.verification.extract_pytest_ac_paths",
            "integration: superpowers",
        ]
        result = extract_pytest_ac_paths(acs)
        assert result == []

    def test_case_insensitive_prefix_upper(self):
        """PYTEST: prefix (all-caps) is recognised."""
        acs = ["PYTEST: tests/test_upper.py"]
        result = extract_pytest_ac_paths(acs)
        assert result == ["tests/test_upper.py"]

    def test_case_insensitive_prefix_mixed(self):
        """PyTest: prefix (mixed-case) is recognised."""
        acs = ["PyTest: tests/test_mixed.py"]
        result = extract_pytest_ac_paths(acs)
        assert result == ["tests/test_mixed.py"]

    def test_path_with_description_separator_stripped(self):
        """Trailing em-dash description is stripped from the path."""
        acs = ["pytest: tests/test_foo.py — boundary case description here"]
        result = extract_pytest_ac_paths(acs)
        assert result == ["tests/test_foo.py"]

    def test_path_with_double_dash_separator_stripped(self):
        """Trailing double-dash description is stripped from the path."""
        acs = ["pytest: tests/test_bar.py -- some description"]
        result = extract_pytest_ac_paths(acs)
        assert result == ["tests/test_bar.py"]

    def test_whitespace_around_path_stripped(self):
        """Leading/trailing whitespace around the path token is stripped."""
        acs = ["pytest:   tests/test_spaces.py   "]
        result = extract_pytest_ac_paths(acs)
        assert result == ["tests/test_spaces.py"]

    def test_empty_path_after_pytest_prefix_omitted(self):
        """A pytest: AC with nothing after the colon contributes no path."""
        acs = ["pytest:", "pytest:   "]
        result = extract_pytest_ac_paths(acs)
        assert result == []

    def test_non_list_raises_value_error(self):
        """Passing a non-list, non-None value raises ValueError."""
        with pytest.raises(ValueError):
            extract_pytest_ac_paths("tests/test_foo.py")

    def test_integer_raises_value_error(self):
        """Passing an integer raises ValueError."""
        with pytest.raises(ValueError):
            extract_pytest_ac_paths(42)

    def test_non_string_item_in_list_raises_value_error(self):
        """A list containing a non-string item raises ValueError."""
        with pytest.raises(ValueError):
            extract_pytest_ac_paths(["pytest: tests/test_foo.py", 123])

    def test_returns_list_type(self):
        """Return value is always a list."""
        assert isinstance(extract_pytest_ac_paths(None), list)
        assert isinstance(extract_pytest_ac_paths([]), list)
        assert isinstance(extract_pytest_ac_paths(["pytest: tests/t.py"]), list)

    def test_real_feature_ac_list(self):
        """Integration: process a realistic feature AC list."""
        acs = [
            "File exists: src/superpowers/verification.py",
            "Function defined: superpowers.verification.extract_pytest_ac_paths",
            "pytest: tests/test_verification_scoped.py",
            "integration: superpowers",
            "pytest: tests/test_subagent_self_verification_must_use_scoped_pytest__boundary.py — empty, zero, or minimum input returns a well-defined result rather than raising (boundary case)",
            "pytest: tests/test_subagent_self_verification_must_use_scoped_pytest__error.py — invalid input raises ValueError and the function does not silently succeed (error path)",
        ]
        result = extract_pytest_ac_paths(acs)
        assert result == [
            "tests/test_verification_scoped.py",
            "tests/test_subagent_self_verification_must_use_scoped_pytest__boundary.py",
            "tests/test_subagent_self_verification_must_use_scoped_pytest__error.py",
        ]
