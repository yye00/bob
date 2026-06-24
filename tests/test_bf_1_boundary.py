"""Boundary tests for bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite.

Empty, zero, or minimum input must return a well-defined result rather than
raising.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite import (
    bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite,
)


def test_empty_repo(tmp_path: Path) -> None:
    """Empty workspace (no Python files) must return ok=True and empty candidates."""
    result = bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=tmp_path,
        db_path=tmp_path / "survey.db",
    )

    assert result["ok"] is True
    assert result["implicit_features"] == []
    assert result["feature_count"] == 0


def test_single_empty_file(tmp_path: Path) -> None:
    """Workspace with a single empty Python file must not raise."""
    (tmp_path / "empty.py").write_text("")

    result = bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=tmp_path,
        db_path=tmp_path / "survey.db",
    )

    assert result["ok"] is True
    assert isinstance(result["implicit_features"], list)


def test_single_function_file(tmp_path: Path) -> None:
    """Workspace with one function is a valid minimum input."""
    (tmp_path / "one.py").write_text("def hello(): pass\n")

    result = bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=tmp_path,
        db_path=tmp_path / "survey.db",
    )

    assert result["ok"] is True
    assert result["feature_count"] >= 0


def test_refresh_on_empty_db(tmp_path: Path) -> None:
    """Incremental refresh on a workspace with no prior DB must not raise."""
    result = bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=tmp_path,
        db_path=tmp_path / "survey.db",
        refresh=True,
    )

    assert result["ok"] is True


def test_workspace_with_only_non_python_files(tmp_path: Path) -> None:
    """Workspace containing only non-Python files returns empty candidates."""
    (tmp_path / "README.md").write_text("# Hello\n")
    (tmp_path / "config.yaml").write_text("key: value\n")

    result = bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=tmp_path,
        db_path=tmp_path / "survey.db",
    )

    assert result["ok"] is True
    assert result["feature_count"] == 0
