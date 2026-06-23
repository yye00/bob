"""Tests for src/snapshot_determinism.py, src/pytest_snapshot_config.py, and src/pytest_snapshot_determinism.py.

Acceptance criteria:
- File exists: src/snapshot_determinism.py
- Function defined: snapshot_determinism.enforce_maxfail_zero
- File exists: src/pytest_snapshot_config.py
- Function defined: pytest_snapshot_config.enforce_maxfail_for_snapshots
- File exists: src/pytest_snapshot_determinism.py
- Function defined: pytest_snapshot_determinism.enforce_maxfail_zero
- pytest: tests/test_snapshot_determinism.py
- integration: pytest
"""

from __future__ import annotations

import pytest


class TestEnforceMaxfailZeroExists:
    """The module and function must be importable."""

    def test_module_importable(self):
        import snapshot_determinism  # noqa: F401

    def test_function_exists(self):
        from snapshot_determinism import enforce_maxfail_zero
        assert callable(enforce_maxfail_zero)


class TestEnforceMaxfailZeroNoXdist:
    """When no xdist flags, enforce_maxfail_zero inserts --maxfail=0."""

    def test_returns_list_with_maxfail_zero(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_returns_new_list(self):
        from snapshot_determinism import enforce_maxfail_zero
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv

    def test_original_args_preserved(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/", "-v"])
        assert "pytest" in result
        assert "tests/" in result
        assert "-v" in result

    def test_maxfail_zero_early_in_argv(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/"])
        # --maxfail=0 should be near the start (index <= 2)
        idx = result.index("--maxfail=0")
        assert idx <= 2

    def test_empty_argv(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero([])
        assert "--maxfail=0" in result

    def test_single_element_argv(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest"])
        assert "--maxfail=0" in result


class TestEnforceMaxfailZeroStripsNonZeroMaxfail:
    """Existing non-zero --maxfail values must be stripped and replaced."""

    def test_strips_maxfail_5(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_1(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=1", "tests/"])
        assert "--maxfail=1" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_100(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=100", "tests/"])
        assert "--maxfail=100" not in result
        assert "--maxfail=0" in result

    def test_keeps_maxfail_zero_when_already_present(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_strips_duplicate_maxfail_zero(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1


class TestEnforceMaxfailZeroWithXdist:
    """When xdist flags are present, --maxfail=0 is also enforced."""

    def test_n_auto_gets_maxfail_zero(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert "--maxfail=0" in result

    def test_n_4_gets_maxfail_zero(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "4", "tests/"])
        assert "--maxfail=0" in result

    def test_numprocesses_gets_maxfail_zero(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--numprocesses", "8", "tests/"])
        assert "--maxfail=0" in result

    def test_xdist_with_nonzero_maxfail_strips_and_replaces(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_xdist_flags_preserved(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert "-n" in result
        assert "auto" in result

    def test_maxfail_zero_before_xdist_n_flag(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert "--maxfail=0" in result
        mf_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert mf_idx < n_idx


class TestEnforceMaxfailZeroReturnType:
    """Return value must always be a list of strings."""

    def test_returns_list(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest"])
        assert isinstance(result, list)

    def test_all_elements_are_strings(self):
        from snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert all(isinstance(arg, str) for arg in result)


# ---------------------------------------------------------------------------
# Tests for pytest_snapshot_config.enforce_maxfail_for_snapshots
# ---------------------------------------------------------------------------


class TestEnforceMaxfailForSnapshotsExists:
    """The module and function must be importable."""

    def test_module_importable(self):
        import pytest_snapshot_config  # noqa: F401

    def test_function_exists(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        assert callable(enforce_maxfail_for_snapshots)


class TestEnforceMaxfailForSnapshotsNoXdist:
    """When no xdist flags, enforce_maxfail_for_snapshots inserts --maxfail=0."""

    def test_returns_list_with_maxfail_zero(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_returns_new_list(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_for_snapshots(argv)
        assert result is not argv

    def test_original_args_preserved(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "tests/", "-v"])
        assert "pytest" in result
        assert "tests/" in result
        assert "-v" in result

    def test_maxfail_zero_early_in_argv(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "tests/"])
        idx = result.index("--maxfail=0")
        assert idx <= 2

    def test_empty_argv(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots([])
        assert "--maxfail=0" in result

    def test_single_element_argv(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest"])
        assert "--maxfail=0" in result


class TestEnforceMaxfailForSnapshotsStripsNonZeroMaxfail:
    """Existing non-zero --maxfail values must be stripped and replaced."""

    def test_strips_maxfail_5(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_1(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=1", "tests/"])
        assert "--maxfail=1" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_100(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=100", "tests/"])
        assert "--maxfail=100" not in result
        assert "--maxfail=0" in result

    def test_keeps_maxfail_zero_when_already_present(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_strips_duplicate_maxfail_zero(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=0", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1


class TestEnforceMaxfailForSnapshotsWithXdist:
    """When xdist flags are present, --maxfail=0 is also enforced."""

    def test_n_auto_gets_maxfail_zero(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "-n", "auto", "tests/"])
        assert "--maxfail=0" in result

    def test_n_4_gets_maxfail_zero(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "-n", "4", "tests/"])
        assert "--maxfail=0" in result

    def test_numprocesses_gets_maxfail_zero(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "--numprocesses", "8", "tests/"])
        assert "--maxfail=0" in result

    def test_xdist_with_nonzero_maxfail_strips_and_replaces(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "-n", "auto", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_xdist_flags_preserved(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "-n", "auto", "tests/"])
        assert "-n" in result
        assert "auto" in result

    def test_maxfail_zero_before_xdist_n_flag(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "-n", "auto", "tests/"])
        assert "--maxfail=0" in result
        mf_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert mf_idx < n_idx


class TestEnforceMaxfailForSnapshotsReturnType:
    """Return value must always be a list of strings."""

    def test_returns_list(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest"])
        assert isinstance(result, list)

    def test_all_elements_are_strings(self):
        from pytest_snapshot_config import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "-n", "auto", "tests/"])
        assert all(isinstance(arg, str) for arg in result)


# ---------------------------------------------------------------------------
# Tests for pytest_snapshots.enforce_maxfail_for_xdist
# ---------------------------------------------------------------------------


class TestEnforceMaxfailForXdistExists:
    """The module and function must be importable."""

    def test_module_importable(self):
        import pytest_snapshots  # noqa: F401

    def test_function_exists(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        assert callable(enforce_maxfail_for_xdist)


class TestEnforceMaxfailForXdistNoXdistFlags:
    """When no xdist flags are present, argv is returned unchanged."""

    def test_returns_same_object_without_xdist(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_for_xdist(argv)
        assert result is argv

    def test_no_maxfail_injected_without_xdist(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        argv = ["pytest", "tests/", "-v"]
        result = enforce_maxfail_for_xdist(argv)
        assert "--maxfail=0" not in result

    def test_empty_argv_unchanged(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        argv = []
        result = enforce_maxfail_for_xdist(argv)
        assert result is argv

    def test_single_element_argv_unchanged(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        argv = ["pytest"]
        result = enforce_maxfail_for_xdist(argv)
        assert result is argv


class TestEnforceMaxfailForXdistWithXdistFlags:
    """When xdist flags are present, --maxfail=0 is enforced."""

    def test_n_auto_injects_maxfail_zero(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "-n", "auto", "tests/"])
        assert "--maxfail=0" in result

    def test_n_4_injects_maxfail_zero(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "-n", "4", "tests/"])
        assert "--maxfail=0" in result

    def test_numprocesses_flag_injects_maxfail_zero(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "--numprocesses", "8", "tests/"])
        assert "--maxfail=0" in result

    def test_numprocesses_eq_form_injects_maxfail_zero(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "--numprocesses=4", "tests/"])
        assert "--maxfail=0" in result

    def test_dist_flag_injects_maxfail_zero(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "--dist", "loadfile", "tests/"])
        assert "--maxfail=0" in result

    def test_strips_nonzero_maxfail_when_xdist(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "-n", "auto", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_duplicate_maxfail_when_xdist(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "-n", "4", "--maxfail=0", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_xdist_flags_preserved(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "-n", "auto", "tests/"])
        assert "-n" in result
        assert "auto" in result

    def test_maxfail_zero_before_xdist_flag(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "-n", "auto", "tests/"])
        mf_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert mf_idx < n_idx

    def test_returns_new_list_with_xdist(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        argv = ["pytest", "-n", "auto", "tests/"]
        result = enforce_maxfail_for_xdist(argv)
        assert result is not argv

    def test_returns_list_type(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "-n", "auto"])
        assert isinstance(result, list)

    def test_all_elements_are_strings(self):
        from pytest_snapshots import enforce_maxfail_for_xdist
        result = enforce_maxfail_for_xdist(["pytest", "-n", "4", "tests/"])
        assert all(isinstance(arg, str) for arg in result)


# ---------------------------------------------------------------------------
# Tests for pytest_snapshot_determinism.enforce_maxfail_zero
# ---------------------------------------------------------------------------


class TestPytestSnapshotDeterminismExists:
    """The module and function must be importable."""

    def test_module_importable(self):
        import pytest_snapshot_determinism  # noqa: F401

    def test_function_exists(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        assert callable(enforce_maxfail_zero)


class TestPytestSnapshotDeterminismNoXdist:
    """When no xdist flags, enforce_maxfail_zero inserts --maxfail=0."""

    def test_returns_list_with_maxfail_zero(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_returns_new_list(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv

    def test_original_args_preserved(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/", "-v"])
        assert "pytest" in result
        assert "tests/" in result
        assert "-v" in result

    def test_maxfail_zero_early_in_argv(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/"])
        idx = result.index("--maxfail=0")
        assert idx <= 2

    def test_empty_argv(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero([])
        assert "--maxfail=0" in result

    def test_single_element_argv(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest"])
        assert "--maxfail=0" in result


class TestPytestSnapshotDeterminismStripsNonZeroMaxfail:
    """Existing non-zero --maxfail values must be stripped and replaced."""

    def test_strips_maxfail_5(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_1(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=1", "tests/"])
        assert "--maxfail=1" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_100(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=100", "tests/"])
        assert "--maxfail=100" not in result
        assert "--maxfail=0" in result

    def test_keeps_maxfail_zero_when_already_present(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_strips_duplicate_maxfail_zero(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1


class TestPytestSnapshotDeterminismWithXdist:
    """When xdist flags are present, --maxfail=0 is also enforced."""

    def test_n_auto_gets_maxfail_zero(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert "--maxfail=0" in result

    def test_n_4_gets_maxfail_zero(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "4", "tests/"])
        assert "--maxfail=0" in result

    def test_numprocesses_gets_maxfail_zero(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--numprocesses", "8", "tests/"])
        assert "--maxfail=0" in result

    def test_xdist_with_nonzero_maxfail_strips_and_replaces(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_xdist_flags_preserved(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert "-n" in result
        assert "auto" in result

    def test_maxfail_zero_before_xdist_n_flag(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert "--maxfail=0" in result
        mf_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert mf_idx < n_idx


class TestPytestSnapshotDeterminismReturnType:
    """Return value must always be a list of strings."""

    def test_returns_list(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest"])
        assert isinstance(result, list)

    def test_all_elements_are_strings(self):
        from pytest_snapshot_determinism import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert all(isinstance(arg, str) for arg in result)
