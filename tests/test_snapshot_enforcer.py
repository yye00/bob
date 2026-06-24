"""Tests for bob.snapshot_enforcer.enforce_maxfail_zero.

Verifies that enforce_maxfail_zero correctly enforces --maxfail=0 in pytest
argv at the snapshot boundary, integrating with pytest_plugins.
"""

from __future__ import annotations

import pytest

from bob.snapshot_enforcer import enforce_maxfail_zero


class TestBasicInjection:
    """--maxfail=0 is injected into a standard pytest argv."""

    def test_injects_maxfail_zero_at_index_1(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_preserves_command_at_index_0(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[0] == "pytest"

    def test_preserves_trailing_args(self):
        result = enforce_maxfail_zero(["pytest", "tests/", "-v"])
        assert "tests/" in result
        assert "-v" in result

    def test_returns_new_list(self):
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv

    def test_result_is_list(self):
        result = enforce_maxfail_zero(["pytest"])
        assert isinstance(result, list)


class TestMaxfailStripping:
    """Existing --maxfail values are stripped and replaced with --maxfail=0."""

    def test_strips_nonzero_maxfail(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_25(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=25", "tests/"])
        assert "--maxfail=25" not in result
        assert "--maxfail=0" in result

    def test_strips_duplicate_maxfail_zero(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_idempotent_on_maxfail_zero(self):
        argv = ["pytest", "--maxfail=0", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result.count("--maxfail=0") == 1
        assert "--maxfail=0" in result


class TestBoundaryCases:
    """Empty and minimal input returns well-defined results."""

    def test_empty_list_returns_maxfail_zero(self):
        result = enforce_maxfail_zero([])
        assert result == ["--maxfail=0"]

    def test_single_element_injects_at_index_1(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result == ["pytest", "--maxfail=0"]

    def test_empty_list_result_is_list(self):
        result = enforce_maxfail_zero([])
        assert isinstance(result, list)

    def test_only_maxfail_flag_stripped_and_replaced(self):
        result = enforce_maxfail_zero(["--maxfail=5"])
        assert "--maxfail=0" in result
        assert "--maxfail=5" not in result


class TestXdistCompatibility:
    """--maxfail=0 appears before xdist -n flags."""

    def test_maxfail_before_n_flag(self):
        argv = ["pytest", "-n", "4", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert "--maxfail=0" in result
        mf_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert mf_idx < n_idx

    def test_maxfail_before_numprocesses(self):
        argv = ["pytest", "--numprocesses=4", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert "--maxfail=0" in result
        mf_idx = result.index("--maxfail=0")
        np_idx = result.index("--numprocesses=4")
        assert mf_idx < np_idx


class TestErrorPaths:
    """Invalid argv raises ValueError; no silent failures."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match=r"list"):
            enforce_maxfail_zero(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero("pytest --maxfail=0")

    def test_tuple_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(("pytest", "tests/"))

    def test_int_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(42)

    def test_non_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", 4])

    def test_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", None])


class TestPytestPluginsIntegration:
    """enforce_maxfail_zero delegates to / is consistent with pytest_plugins.snapshot_maxfail_enforcer."""

    def test_pytest_plugins_importable(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        assert callable(snapshot_maxfail_enforcer)

    def test_consistent_with_pytest_plugins_on_standard_argv(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        argv = ["pytest", "tests/", "-v"]
        result_enforcer = enforce_maxfail_zero(argv)
        result_plugin = snapshot_maxfail_enforcer(argv)
        assert result_enforcer == result_plugin

    def test_consistent_with_pytest_plugins_on_empty(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result_enforcer = enforce_maxfail_zero([])
        result_plugin = snapshot_maxfail_enforcer([])
        assert result_enforcer == result_plugin

    def test_consistent_with_pytest_plugins_on_nonzero_maxfail(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        argv = ["pytest", "--maxfail=10", "tests/"]
        result_enforcer = enforce_maxfail_zero(argv)
        result_plugin = snapshot_maxfail_enforcer(argv)
        assert result_enforcer == result_plugin


class TestSnapshotEnforcerImportable:
    """Module and function are importable from the expected location."""

    def test_module_importable(self):
        from bob import snapshot_enforcer
        assert hasattr(snapshot_enforcer, "enforce_maxfail_zero")

    def test_enforce_maxfail_zero_callable(self):
        assert callable(enforce_maxfail_zero)
