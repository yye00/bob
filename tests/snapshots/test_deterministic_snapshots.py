"""Tests for pytest_plugins.snapshot_maxfail_enforcer.

Acceptance criteria:
- File exists: tests/snapshots/test_deterministic_snapshots.py
- pytest: tests/snapshots/test_deterministic_snapshots.py
- Function defined: pytest_plugins.snapshot_maxfail_enforcer
- integration: bob3.test_slug_capping
"""

from __future__ import annotations

import pytest


class TestModuleAndFunctionExist:
    """snapshot_maxfail_enforcer must be importable from pytest_plugins."""

    def test_module_importable(self):
        import pytest_plugins  # noqa: F401

    def test_function_exists(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        assert callable(snapshot_maxfail_enforcer)

    def test_maxfail_zero_constant(self):
        import pytest_plugins
        assert hasattr(pytest_plugins, "MAXFAIL_ZERO")
        assert pytest_plugins.MAXFAIL_ZERO == "--maxfail=0"


class TestInjectMaxfailZero:
    """snapshot_maxfail_enforcer must inject --maxfail=0 into argv."""

    def test_injects_maxfail_zero(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_returns_new_list(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        argv = ["pytest", "tests/"]
        result = snapshot_maxfail_enforcer(argv)
        assert result is not argv

    def test_original_args_preserved(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(["pytest", "tests/", "-v"])
        assert "pytest" in result
        assert "tests/" in result
        assert "-v" in result

    def test_maxfail_zero_at_index_1(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_command_at_index_0(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(["pytest", "tests/"])
        assert result[0] == "pytest"


class TestStripsExistingMaxfail:
    """Any existing --maxfail value must be stripped before injecting 0."""

    def test_strips_nonzero_maxfail(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_exactly_one_maxfail_flag(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(["pytest", "--maxfail=5", "tests/"])
        count = sum(1 for arg in result if arg.startswith("--maxfail"))
        assert count == 1

    def test_strips_duplicate_maxfail_zero(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(
            ["pytest", "--maxfail=0", "--maxfail=0", "tests/"]
        )
        count = sum(1 for arg in result if arg == "--maxfail=0")
        assert count == 1

    def test_idempotent(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        argv = ["pytest", "--maxfail=0", "tests/"]
        result1 = snapshot_maxfail_enforcer(argv)
        result2 = snapshot_maxfail_enforcer(result1)
        assert result1 == result2


class TestXdistInteraction:
    """--maxfail=0 must appear before xdist parallelism flags."""

    def test_maxfail_before_n_flag(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(["pytest", "-n", "4", "tests/"])
        idx_maxfail = result.index("--maxfail=0")
        idx_n = result.index("-n")
        assert idx_maxfail < idx_n

    def test_maxfail_before_numprocesses(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(
            ["pytest", "--numprocesses=auto", "tests/"]
        )
        idx_maxfail = result.index("--maxfail=0")
        idx_np = result.index("--numprocesses=auto")
        assert idx_maxfail < idx_np

    def test_xdist_flags_preserved(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(["pytest", "-n", "auto", "tests/"])
        assert "-n" in result
        assert "auto" in result


class TestEdgeCases:
    """Edge cases: empty list, single element."""

    def test_empty_argv(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer([])
        assert "--maxfail=0" in result

    def test_single_element_argv(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        result = snapshot_maxfail_enforcer(["pytest"])
        assert "--maxfail=0" in result
        assert "pytest" in result

    def test_multiple_test_paths_preserved(self):
        from pytest_plugins import snapshot_maxfail_enforcer
        argv = ["pytest", "tests/foo/", "tests/bar/", "-v"]
        result = snapshot_maxfail_enforcer(argv)
        assert "tests/foo/" in result
        assert "tests/bar/" in result
        assert "--maxfail=0" in result


class TestSlugCappingIntegration:
    """Integration: snapshot enforcement is compatible with bob3.test_slug_capping."""

    def test_slug_capping_importable(self):
        from bob3.test_slug_capping import verify_slug_capping, slug_is_capped  # noqa: F401
        assert callable(verify_slug_capping)
        assert callable(slug_is_capped)

    def test_slug_is_capped_for_normal_title(self):
        from bob3.test_slug_capping import slug_is_capped
        assert slug_is_capped("Deterministic pytest snapshots disable xdist early halt")

    def test_slug_is_capped_for_long_title(self):
        from bob3.test_slug_capping import slug_is_capped
        long_title = "A very long feature title that exceeds sixty characters in total length"
        assert slug_is_capped(long_title)

    def test_verify_slug_capping_returns_string(self):
        from bob3.test_slug_capping import verify_slug_capping
        slug = verify_slug_capping("Deterministic pytest snapshots")
        assert isinstance(slug, str)
        assert len(slug) <= 60

    def test_snapshot_enforcer_args_within_slug_cap(self):
        """snapshot_maxfail_enforcer args are short strings, all within slug cap."""
        from pytest_plugins import snapshot_maxfail_enforcer
        argv = ["pytest", "--maxfail=5", "tests/snapshots/"]
        result = snapshot_maxfail_enforcer(argv)
        for arg in result:
            assert len(arg) <= 255
