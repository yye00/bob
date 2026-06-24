"""Error path tests for bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite.

Invalid input must raise ValueError; the function must not silently succeed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite import (
    bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite,
)


def test_nonexistent_workspace_raises(tmp_path: Path) -> None:
    """Passing a non-existent path must raise ValueError."""
    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(ValueError, match="does not exist"):
        bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
            workspace=nonexistent,
        )


def test_file_as_workspace_raises(tmp_path: Path) -> None:
    """Passing a file path (not a directory) as workspace must raise ValueError."""
    a_file = tmp_path / "notadir.py"
    a_file.write_text("x = 1\n")
    with pytest.raises(ValueError, match="not a directory"):
        bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
            workspace=a_file,
        )


def test_nonexistent_workspace_string_raises(tmp_path: Path) -> None:
    """Passing a non-existent string path must raise ValueError (not KeyError/OSError)."""
    bad_path = str(tmp_path / "ghost_dir")
    with pytest.raises(ValueError):
        bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
            workspace=bad_path,
        )
