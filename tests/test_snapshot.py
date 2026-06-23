"""Tests for pytest_snapshot.enforce_maxfail_with_xdist.

Acceptance criteria:
- pytest: tests/test_snapshot.py
- Function defined: pytest_snapshot.enforce_maxfail_with_xdist
- integration: pytest
"""

from __future__ import annotations

import pytest


class TestEnforceMaxfailWithXdistExists:
    """The module and function must be importable."""

    def test_module_importable(self):
        import pytest_snapshot  # noqa: F401

    def test_function_exists(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        assert callable(enforce_maxfail_with_xdist)


class TestEnforceMaxfailWithXdistBasicBehavior:
    """enforce_maxfail_with_xdist must inject --maxfail=0."""

    def test_injects_maxfail_zero(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_returns_list(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "tests/"])
        assert isinstance(result, list)

    def test_returns_new_list(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_with_xdist(argv)
        assert result is not argv

    def test_original_args_preserved(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "tests/", "-v"])
        assert "pytest" in result
        assert "tests/" in result
        assert "-v" in result

    def test_all_elements_are_strings(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "-n", "auto", "tests/"])
        assert all(isinstance(arg, str) for arg in result)

    def test_empty_argv(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist([])
        assert "--maxfail=0" in result

    def test_single_element_argv(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest"])
        assert "--maxfail=0" in result


class TestEnforceMaxfailWithXdistStripsExistingMaxfail:
    """Existing --maxfail values must be stripped and replaced with --maxfail=0."""

    def test_strips_maxfail_5(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_1(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "--maxfail=1", "tests/"])
        assert "--maxfail=1" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_25(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "--maxfail=25", "tests/"])
        assert "--maxfail=25" not in result
        assert "--maxfail=0" in result

    def test_no_duplicate_maxfail_zero_when_already_present(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_strips_duplicate_maxfail_zero(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(
            ["pytest", "--maxfail=0", "--maxfail=0", "tests/"]
        )
        assert result.count("--maxfail=0") == 1


class TestEnforceMaxfailWithXdistXdistPresent:
    """When xdist flags are present, --maxfail=0 is enforced."""

    def test_n_auto_gets_maxfail_zero(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "-n", "auto", "tests/"])
        assert "--maxfail=0" in result

    def test_n_4_gets_maxfail_zero(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "-n", "4", "tests/"])
        assert "--maxfail=0" in result

    def test_numprocesses_gets_maxfail_zero(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "--numprocesses", "8", "tests/"])
        assert "--maxfail=0" in result

    def test_xdist_with_nonzero_maxfail_strips_and_replaces(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(
            ["pytest", "-n", "auto", "--maxfail=5", "tests/"]
        )
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_xdist_flags_preserved(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "-n", "auto", "tests/"])
        assert "-n" in result
        assert "auto" in result

    def test_maxfail_zero_before_xdist_n_flag(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "-n", "auto", "tests/"])
        mf_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert mf_idx < n_idx

    def test_maxfail_zero_early_in_argv(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "tests/"])
        idx = result.index("--maxfail=0")
        assert idx <= 2


class TestEnforceMaxfailWithXdistEdgeCases:
    """Edge cases and robustness."""

    def test_maxfail_bare_flag_stripped(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        # --maxfail (bare, no value) should be stripped
        result = enforce_maxfail_with_xdist(["pytest", "--maxfail", "tests/"])
        assert "--maxfail" not in result or "--maxfail=0" in result

    def test_multiple_test_paths_preserved(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(
            ["pytest", "tests/foo/", "tests/bar/", "-v"]
        )
        assert "tests/foo/" in result
        assert "tests/bar/" in result
        assert "--maxfail=0" in result

    def test_verbose_flag_preserved(self):
        from pytest_snapshot import enforce_maxfail_with_xdist
        result = enforce_maxfail_with_xdist(["pytest", "-v", "tests/"])
        assert "-v" in result
        assert "--maxfail=0" in result
