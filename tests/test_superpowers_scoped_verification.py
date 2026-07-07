"""Tests for bob.superpowers.build_scoped_pytest_command.

Feature: bd777bc4-8f49-4093-9b78-42bfa323e766
Subagent self-verification must use scoped pytest, not the full 1800+ test
suite. build_scoped_pytest_command extracts ``pytest:`` acceptance-criteria
paths and returns a pytest invocation scoped to the feature's own test files,
falling back to the full suite only when no ``pytest:`` ACs are present.
"""

from __future__ import annotations

import pytest

from bob import superpowers
from bob.superpowers import build_scoped_pytest_command


class TestBuildScopedPytestCommand:
    def test_function_is_exported(self):
        assert hasattr(superpowers, "build_scoped_pytest_command")
        assert callable(superpowers.build_scoped_pytest_command)

    def test_single_pytest_ac_is_scoped(self):
        acs = ["pytest: tests/test_foo.py"]
        assert build_scoped_pytest_command(acs) == "python -m pytest tests/test_foo.py -v"

    def test_multiple_pytest_acs_all_included(self):
        acs = [
            "pytest: tests/test_foo.py",
            "pytest: tests/test_bar.py",
            "Function defined: foo.bar",
        ]
        result = build_scoped_pytest_command(acs)
        assert result == "python -m pytest tests/test_foo.py tests/test_bar.py -v"

    def test_does_not_target_full_suite_when_scoped(self):
        acs = ["pytest: tests/test_foo.py"]
        result = build_scoped_pytest_command(acs)
        assert "tests/ -v" not in result
        assert result != "python -m pytest tests/ -v"

    def test_no_pytest_acs_falls_back_to_full_suite(self):
        acs = ["Function defined: foo.bar", "integration: foo"]
        assert build_scoped_pytest_command(acs) == "python -m pytest tests/ -v"

    def test_none_falls_back_to_full_suite(self):
        assert build_scoped_pytest_command(None) == "python -m pytest tests/ -v"

    def test_empty_list_falls_back_to_full_suite(self):
        assert build_scoped_pytest_command([]) == "python -m pytest tests/ -v"

    def test_result_always_starts_with_python_m_pytest(self):
        for acs in [None, [], ["File exists: x"], ["pytest: tests/test_x.py"]]:
            assert build_scoped_pytest_command(acs).startswith("python -m pytest")

    def test_result_always_ends_with_v_flag(self):
        for acs in [None, [], ["File exists: x"], ["pytest: tests/test_x.py"]]:
            assert build_scoped_pytest_command(acs).endswith(" -v")

    def test_matches_this_features_own_acs(self):
        """The command scoped to this feature's ACs targets only its files."""
        acs = [
            "Function defined: superpowers.build_scoped_pytest_command",
            "pytest: tests/test_superpowers_scoped_verification.py",
            "integration: superpowers",
            "pytest: tests/test_subagent_self_verification_must_use_scoped_pytest__boundary.py",
            "pytest: tests/test_subagent_self_verification_must_use_scoped_pytest__error.py",
        ]
        result = build_scoped_pytest_command(acs)
        assert "tests/test_superpowers_scoped_verification.py" in result
        assert "tests/ -v" not in result

    def test_invalid_scalar_raises_value_error(self):
        with pytest.raises(ValueError):
            build_scoped_pytest_command("tests/test_foo.py")

    def test_non_string_item_raises_value_error(self):
        with pytest.raises(ValueError):
            build_scoped_pytest_command([123])
