"""Tests for error/failure path when src/bob/ does not exist."""
from __future__ import annotations

import pytest
from pathlib import Path
from bob.security.slopsquatting_scan import find_local_modules


def test_find_local_modules_raises_file_not_found_when_src_missing(tmp_path: Path) -> None:
    """find_local_modules raises FileNotFoundError when src/bob/ does not exist."""
    # tmp_path is a fresh empty directory — no src/bob/ present
    with pytest.raises(FileNotFoundError):
        find_local_modules(tmp_path)


def test_find_local_modules_raises_when_src_exists_but_no_bob(tmp_path: Path) -> None:
    """find_local_modules raises FileNotFoundError when src/ exists but src/bob/ does not."""
    (tmp_path / "src").mkdir()
    with pytest.raises(FileNotFoundError):
        find_local_modules(tmp_path)
