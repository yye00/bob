"""Error-path tests for the clangd/libclang C++ survey backend.

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.survey.clangd_backend import build_clangd_index, detect_clangd_availability


def test_nonexistent_workspace_raises(tmp_path: Path) -> None:
    """A workspace path that does not exist raises ValueError."""
    with pytest.raises(ValueError):
        build_clangd_index(
            tmp_path / "does_not_exist",
            db_path=tmp_path / "survey.db",
            index_records={"symbols": [], "edges": []},
        )


def test_workspace_is_file_raises(tmp_path: Path) -> None:
    """A workspace that is a file, not a directory, raises ValueError."""
    f = tmp_path / "a_file"
    f.write_text("not a dir")
    with pytest.raises(ValueError):
        build_clangd_index(f, db_path=tmp_path / "survey.db", index_records={})


def test_index_records_wrong_type_raises(tmp_path: Path) -> None:
    """A non-dict index_records value raises ValueError."""
    with pytest.raises(ValueError):
        build_clangd_index(tmp_path, db_path=tmp_path / "survey.db", index_records=[1, 2, 3])


def test_symbol_missing_usr_raises(tmp_path: Path) -> None:
    """A symbol record lacking the mandatory 'usr' key raises ValueError."""
    with pytest.raises(ValueError):
        build_clangd_index(
            tmp_path,
            db_path=tmp_path / "survey.db",
            index_records={"symbols": [{"name": "orphan", "kind": "function"}]},
        )


def test_symbol_missing_name_raises(tmp_path: Path) -> None:
    """A symbol record lacking the mandatory 'name' key raises ValueError."""
    with pytest.raises(ValueError):
        build_clangd_index(
            tmp_path,
            db_path=tmp_path / "survey.db",
            index_records={"symbols": [{"usr": "c:@F@x#", "kind": "function"}]},
        )


def test_invalid_edge_kind_raises(tmp_path: Path) -> None:
    """An edge with a kind outside the allowed set raises ValueError."""
    with pytest.raises(ValueError):
        build_clangd_index(
            tmp_path,
            db_path=tmp_path / "survey.db",
            index_records={
                "symbols": [
                    {"usr": "A", "name": "A", "kind": "function"},
                    {"usr": "B", "name": "B", "kind": "function"},
                ],
                "edges": [{"src_usr": "A", "dst_usr": "B", "kind": "bogus_kind"}],
            },
        )


def test_detect_nonexistent_workspace_raises(tmp_path: Path) -> None:
    """detect_clangd_availability on a missing workspace raises ValueError."""
    with pytest.raises(ValueError):
        detect_clangd_availability(tmp_path / "nope")


def test_edge_missing_endpoint_key_raises(tmp_path: Path) -> None:
    """An edge record missing 'src_usr'/'dst_usr' raises ValueError."""
    with pytest.raises(ValueError):
        build_clangd_index(
            tmp_path,
            db_path=tmp_path / "survey.db",
            index_records={
                "symbols": [{"usr": "A", "name": "A", "kind": "function"}],
                "edges": [{"src_usr": "A", "kind": "calls"}],
            },
        )
