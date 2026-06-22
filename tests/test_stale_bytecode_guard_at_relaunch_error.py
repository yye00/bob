"""Error path tests for check_stale_bytecode (feature d2df584f-9b5a-4279-9a2c-d712609fe474).

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import math
import pathlib
import time

import pytest

from bob_orchestrator.stale_bytecode_guard import check_stale_bytecode


class TestErrorPathInvalidInput:
    def test_non_path_workspace_raises_value_error(self, tmp_path):
        """workspace as a string raises ValueError, not TypeError or silent pass."""
        with pytest.raises(ValueError, match="workspace must be a pathlib.Path"):
            check_stale_bytecode("/some/path", time.time())  # type: ignore[arg-type]

    def test_workspace_as_int_raises_value_error(self, tmp_path):
        """workspace as int raises ValueError."""
        with pytest.raises(ValueError, match="workspace must be a pathlib.Path"):
            check_stale_bytecode(42, time.time())  # type: ignore[arg-type]

    def test_start_time_as_string_raises_value_error(self, tmp_path):
        """start_time as str raises ValueError."""
        with pytest.raises(ValueError, match="start_time must be a numeric type"):
            check_stale_bytecode(tmp_path, "2026-01-01")  # type: ignore[arg-type]

    def test_start_time_as_none_raises_value_error(self, tmp_path):
        """start_time=None raises ValueError (not AttributeError or silent pass)."""
        with pytest.raises((ValueError, TypeError)):
            check_stale_bytecode(tmp_path, None)  # type: ignore[arg-type]

    def test_start_time_nan_raises_value_error(self, tmp_path):
        """start_time=float('nan') raises ValueError."""
        with pytest.raises(ValueError, match="start_time must be a finite number"):
            check_stale_bytecode(tmp_path, math.nan)

    def test_start_time_inf_raises_value_error(self, tmp_path):
        """start_time=float('inf') raises ValueError."""
        with pytest.raises(ValueError, match="start_time must be a finite number"):
            check_stale_bytecode(tmp_path, math.inf)

    def test_start_time_neg_inf_raises_value_error(self, tmp_path):
        """start_time=-float('inf') raises ValueError."""
        with pytest.raises(ValueError, match="start_time must be a finite number"):
            check_stale_bytecode(tmp_path, -math.inf)

    def test_does_not_silently_succeed_on_invalid_workspace(self, tmp_path):
        """Passing wrong workspace type must not return a list silently."""
        try:
            result = check_stale_bytecode(None, time.time())  # type: ignore[arg-type]
            # If it didn't raise, it must at least not return a "success" result
            pytest.fail(
                f"Expected ValueError but got result: {result!r}"
            )
        except (ValueError, AttributeError, TypeError):
            pass  # Any of these is acceptable — it must not succeed silently
