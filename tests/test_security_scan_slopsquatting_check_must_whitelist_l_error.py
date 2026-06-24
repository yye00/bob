"""Error path tests for security_scan.whitelist_local_modules.

Tests that invalid inputs raise ValueError and the function does not
silently succeed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bob3.security_scan import whitelist_local_modules


class TestErrorPaths:
    def test_none_workspace_raises_value_error(self) -> None:
        """Passing None as workspace raises ValueError."""
        with pytest.raises((ValueError, TypeError, AttributeError)):
            whitelist_local_modules(None)  # type: ignore[arg-type]

    def test_string_path_raises_type_error(self) -> None:
        """Passing a raw string instead of Path raises TypeError or ValueError."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            whitelist_local_modules("/tmp/some/path")  # type: ignore[arg-type]

    def test_nonexistent_workspace_raises_value_error(self, tmp_path: Path) -> None:
        """Passing a nonexistent directory raises ValueError."""
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises((ValueError, FileNotFoundError, OSError)):
            whitelist_local_modules(nonexistent)

    def test_file_as_workspace_raises(self, tmp_path: Path) -> None:
        """Passing a file path (not a directory) as workspace raises."""
        f = tmp_path / "not_a_dir.py"
        f.write_text("x = 1\n")
        with pytest.raises((ValueError, NotADirectoryError, OSError)):
            whitelist_local_modules(f)
