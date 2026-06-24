"""Boundary tests for bob.brownfield.survey — BF-1 Brownfield Survey.

Empty, zero, or minimum input must return a well-defined result rather than raising.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from bob.brownfield.survey import (
    build_survey,
    compute_pagerank,
    parse_symbols,
    refresh_survey,
    scan_implicit_features,
)


def test_build_survey_empty_workspace(tmp_path: Path) -> None:
    """build_survey on an empty directory returns an empty list without raising."""
    db_path = tmp_path / "survey.db"
    result = build_survey(tmp_path, db_path=db_path)
    assert result == [], f"Expected empty list, got {result}"
    assert db_path.exists()


def test_build_survey_single_empty_file(tmp_path: Path) -> None:
    """build_survey on a workspace with one empty .py file returns an empty candidates list."""
    (tmp_path / "empty.py").write_text("")
    db_path = tmp_path / "survey.db"
    result = build_survey(tmp_path, db_path=db_path)
    assert isinstance(result, list)


def test_build_survey_no_python_files(tmp_path: Path) -> None:
    """build_survey on a workspace with no Python files returns empty candidates."""
    (tmp_path / "README.md").write_text("# Hello\n")
    (tmp_path / "data.json").write_text("{}\n")
    db_path = tmp_path / "survey.db"
    result = build_survey(tmp_path, db_path=db_path)
    assert result == []


def test_build_survey_minimal_function(tmp_path: Path) -> None:
    """build_survey on a workspace with a single function returns a list without raising."""
    (tmp_path / "one.py").write_text("def hello(): pass\n")
    db_path = tmp_path / "survey.db"
    result = build_survey(tmp_path, db_path=db_path)
    assert isinstance(result, list)


def test_refresh_survey_no_prior_db(tmp_path: Path) -> None:
    """refresh_survey when no prior survey.db exists must not raise."""
    db_path = tmp_path / "survey.db"
    result = refresh_survey(tmp_path, db_path=db_path)
    assert isinstance(result, list)


def test_refresh_survey_empty_workspace(tmp_path: Path) -> None:
    """refresh_survey on empty workspace returns empty list without raising."""
    db_path = tmp_path / "survey.db"
    build_survey(tmp_path, db_path=db_path)
    result = refresh_survey(tmp_path, db_path=db_path)
    assert result == []


def test_compute_pagerank_empty_workspace(tmp_path: Path) -> None:
    """compute_pagerank on an empty workspace returns an empty list without raising."""
    db_path = tmp_path / "survey.db"
    result = compute_pagerank(tmp_path, db_path=db_path)
    assert isinstance(result, list)
    assert result == []


def test_compute_pagerank_single_symbol(tmp_path: Path) -> None:
    """compute_pagerank with a single symbol (no edges) returns that symbol with a score."""
    (tmp_path / "one.py").write_text("def hello(): pass\n")
    db_path = tmp_path / "survey.db"
    result = compute_pagerank(tmp_path, db_path=db_path)
    assert len(result) >= 1
    for entry in result:
        assert "pagerank" in entry
        assert isinstance(entry["pagerank"], float)


def test_scan_implicit_features_empty_workspace(tmp_path: Path) -> None:
    """scan_implicit_features on an empty workspace returns an empty list."""
    db_path = tmp_path / "survey.db"
    result = scan_implicit_features(tmp_path, db_path=db_path)
    assert result == []


def test_scan_implicit_features_no_stubs(tmp_path: Path) -> None:
    """scan_implicit_features on a clean codebase returns an empty list."""
    (tmp_path / "clean.py").write_text(
        textwrap.dedent("""\
        class Widget:
            '''A well-implemented widget.'''
            def run(self) -> None:
                print("running")
        """)
    )
    db_path = tmp_path / "survey.db"
    result = scan_implicit_features(tmp_path, db_path=db_path)
    assert isinstance(result, list)
    assert result == []


def test_parse_symbols_empty_file(tmp_path: Path) -> None:
    """parse_symbols on an empty Python file returns an empty list without raising."""
    empty_file = tmp_path / "empty.py"
    empty_file.write_text("")
    result = parse_symbols(empty_file)
    assert result == []


def test_parse_symbols_single_function(tmp_path: Path) -> None:
    """parse_symbols on a minimal file with one function returns one symbol."""
    f = tmp_path / "one.py"
    f.write_text("def hello(): pass\n")
    result = parse_symbols(f)
    assert len(result) == 1
    assert result[0]["name"] == "hello"
    assert result[0]["kind"] == "function"


def test_parse_symbols_single_class(tmp_path: Path) -> None:
    """parse_symbols returns a class symbol with kind='class'."""
    f = tmp_path / "cls.py"
    f.write_text(
        textwrap.dedent("""\
        class Foo:
            pass
        """)
    )
    result = parse_symbols(f)
    names = [s["name"] for s in result]
    assert "Foo" in names
    kinds = {s["kind"] for s in result}
    assert "class" in kinds
