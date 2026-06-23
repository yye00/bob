"""Error path tests for bob3.brownfield.survey — BF-1 (AC-required file).

Invalid input must raise ValueError; the functions must not silently succeed.
This file satisfies the AC: pytest: tests/brownfield/test_survey_error_paths.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.brownfield.survey import (
    build_survey,
    compute_pagerank,
    parse_symbols,
    scan_implicit_features,
    survey_repository,
)


def test_survey_repository_nonexistent_workspace_raises(tmp_path: Path) -> None:
    """survey_repository must raise ValueError when workspace does not exist."""
    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(ValueError, match="does not exist"):
        survey_repository(nonexistent)


def test_survey_repository_file_as_workspace_raises(tmp_path: Path) -> None:
    """survey_repository must raise ValueError when a file path is given as workspace."""
    a_file = tmp_path / "not_a_dir.py"
    a_file.write_text("x = 1\n")
    with pytest.raises(ValueError, match="not a directory"):
        survey_repository(a_file)


def test_compute_pagerank_nonexistent_workspace_raises(tmp_path: Path) -> None:
    """compute_pagerank must raise ValueError when workspace does not exist."""
    nonexistent = tmp_path / "nowhere"
    with pytest.raises(ValueError, match="does not exist"):
        compute_pagerank(nonexistent)


def test_compute_pagerank_file_as_workspace_raises(tmp_path: Path) -> None:
    """compute_pagerank must raise ValueError when a file path is given as workspace."""
    a_file = tmp_path / "file.py"
    a_file.write_text("pass\n")
    with pytest.raises(ValueError, match="not a directory"):
        compute_pagerank(a_file)


def test_scan_implicit_features_nonexistent_workspace_raises(tmp_path: Path) -> None:
    """scan_implicit_features must raise ValueError when workspace does not exist."""
    nonexistent = tmp_path / "ghost_dir"
    with pytest.raises(ValueError, match="does not exist"):
        scan_implicit_features(nonexistent)


def test_scan_implicit_features_file_as_workspace_raises(tmp_path: Path) -> None:
    """scan_implicit_features must raise ValueError when given a file path as workspace."""
    a_file = tmp_path / "file.py"
    a_file.write_text("pass\n")
    with pytest.raises(ValueError, match="not a directory"):
        scan_implicit_features(a_file)


def test_parse_symbols_nonexistent_file_raises(tmp_path: Path) -> None:
    """parse_symbols must raise ValueError when the given file does not exist."""
    ghost = tmp_path / "ghost.py"
    with pytest.raises(ValueError, match="does not exist"):
        parse_symbols(ghost)


def test_parse_symbols_directory_as_file_raises(tmp_path: Path) -> None:
    """parse_symbols must raise ValueError when given a directory instead of a file."""
    with pytest.raises(ValueError, match="not a file"):
        parse_symbols(tmp_path)
