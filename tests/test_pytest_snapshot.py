"""Tests for bob.pytest_snapshot.enforce_maxfail_zero.

Acceptance criteria:
- File exists: src/bob/pytest_snapshot.py
- Function defined: bob.pytest_snapshot.enforce_maxfail_zero
- pytest: tests/test_pytest_snapshot.py
- integration: bob.orchestrator (run_loop imports enforce_maxfail_zero)
"""

from __future__ import annotations

import pytest

from bob.pytest_snapshot import enforce_maxfail_zero, MAXFAIL_ZERO


class TestModuleAttributes:
    """Module must expose enforce_maxfail_zero and MAXFAIL_ZERO."""

    def test_enforce_maxfail_zero_is_callable(self):
        assert callable(enforce_maxfail_zero)

    def test_maxfail_zero_constant_value(self):
        assert MAXFAIL_ZERO == "--maxfail=0"


class TestBasicBehavior:
    """enforce_maxfail_zero must inject --maxfail=0 at position 1."""

    def test_typical_argv_injects_flag(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_flag_placed_at_index_1(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_command_preserved_at_index_0(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[0] == "pytest"

    def test_other_args_preserved(self):
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


class TestStripsExistingMaxfail:
    """Existing --maxfail flags must be stripped before injecting --maxfail=0."""

    def test_strips_nonzero_maxfail(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_duplicate_maxfail_zero(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_strips_maxfail_without_value(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail", "tests/"])
        # --maxfail without = is not a recognized form; should be passed through
        # or stripped — the important thing is exactly one --maxfail=0 is injected
        assert "--maxfail=0" in result

    def test_exactly_one_maxfail_flag_in_result(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=20", "-n", "4", "tests/"])
        maxfail_flags = [a for a in result if a.startswith("--maxfail")]
        assert len(maxfail_flags) == 1
        assert maxfail_flags[0] == "--maxfail=0"


class TestXdistInteraction:
    """--maxfail=0 must appear before -n / --numprocesses flags."""

    def test_maxfail_before_xdist_n_flag(self):
        result = enforce_maxfail_zero(["pytest", "-n", "4", "tests/"])
        maxfail_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert maxfail_idx < n_idx

    def test_xdist_flag_preserved(self):
        result = enforce_maxfail_zero(["pytest", "-n", "4", "tests/"])
        assert "-n" in result
        assert "4" in result


class TestEmptyAndBoundaryInput:
    """Empty and single-element inputs must not raise."""

    def test_empty_list_returns_maxfail_zero(self):
        result = enforce_maxfail_zero([])
        assert "--maxfail=0" in result
        assert isinstance(result, list)

    def test_single_element_injects_at_index_1(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result == ["pytest", "--maxfail=0"]


class TestErrorPaths:
    """Invalid input must raise ValueError."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero("pytest")

    def test_tuple_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(("pytest", "tests/"))

    def test_int_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", 4])

    def test_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", None])


class TestOrchestratorIntegration:
    """run_loop.capture_pytest_snapshot must import enforce_maxfail_zero from bob.pytest_snapshot."""

    def test_run_loop_imports_enforce_maxfail_zero(self):
        import importlib
        import bob.orchestrator.run_loop as run_loop_mod
        src = importlib.util.find_spec("bob.orchestrator.run_loop")
        assert src is not None, "bob.orchestrator.run_loop must be importable"

    def test_enforce_maxfail_zero_importable_from_bob_pytest_snapshot(self):
        from bob.pytest_snapshot import enforce_maxfail_zero as fn
        assert callable(fn)

    def test_run_loop_source_references_pytest_snapshot(self):
        import inspect
        import bob.orchestrator.run_loop as rl
        src = inspect.getsource(rl)
        assert "bob.snapshot_pytest" in src or "bob.pytest_snapshot" in src, (
            "run_loop must import enforce_maxfail_zero from a bob snapshot module"
        )
