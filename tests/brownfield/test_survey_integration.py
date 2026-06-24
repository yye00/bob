"""Integration tests for BF-1 brownfield survey — CLI + end-to-end DB verification.

These tests exercise the full stack: CLI → build_survey/refresh_survey → SQLite,
and verify that the symbol graph, edges, file_hashes, and PageRank columns are
populated correctly after a real survey run.
"""

from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from bob3.brownfield.survey import (
    build_survey,
    build_symbol_graph,
    compute_pagerank,
    scan_implicit_features,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def multi_module_repo(tmp_path: Path) -> Path:
    """Multi-module Python repo to exercise cross-file edges and PageRank."""
    pkg = tmp_path / "app"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "models.py").write_text(
        textwrap.dedent("""\
        class Base:
            '''Base model.'''
            def save(self):
                pass

        class User(Base):
            '''A user.'''
            def profile(self):
                pass

        class Admin(User):
            pass
        """)
    )
    (pkg / "services.py").write_text(
        textwrap.dedent("""\
        from app.models import User, Admin

        def create_user(name: str) -> User:
            return User()

        def promote_to_admin(user: User) -> Admin:
            return Admin()
        """)
    )
    (pkg / "tasks.py").write_text(
        textwrap.dedent("""\
        from app.services import create_user, promote_to_admin

        def run_batch():
            users = [create_user(f"user_{i}") for i in range(10)]
            return users

        class BackgroundTask:
            '''TODO: implement background task scheduling.'''
            pass
        """)
    )
    (pkg / "legacy.py").write_text(
        textwrap.dedent("""\
        class OldAdapter:
            '''stub: this is a placeholder for the old API adapter.'''
            def adapt(self):
                pass
        """)
    )
    return tmp_path


# ---------------------------------------------------------------------------
# build_symbol_graph integration
# ---------------------------------------------------------------------------


def test_build_symbol_graph_returns_list(multi_module_repo: Path, tmp_path: Path) -> None:
    """build_symbol_graph must return a non-empty list of symbol dicts."""
    db_path = tmp_path / "survey.db"
    symbols = build_symbol_graph(multi_module_repo, db_path=db_path)

    assert isinstance(symbols, list)
    assert len(symbols) > 0, "Expected symbols from multi-module repo"


def test_build_symbol_graph_schema(multi_module_repo: Path, tmp_path: Path) -> None:
    """Each symbol dict must have the required keys."""
    db_path = tmp_path / "survey.db"
    symbols = build_symbol_graph(multi_module_repo, db_path=db_path)

    required_keys = {"path", "kind", "name", "sha", "lineno", "pagerank"}
    for sym in symbols:
        assert required_keys <= set(sym.keys()), f"Symbol missing keys: {sym}"


def test_build_symbol_graph_contains_known_symbols(multi_module_repo: Path, tmp_path: Path) -> None:
    """build_symbol_graph must discover classes and functions from all modules."""
    db_path = tmp_path / "survey.db"
    symbols = build_symbol_graph(multi_module_repo, db_path=db_path)

    names = {s["name"] for s in symbols}
    assert "Base" in names
    assert "User" in names
    assert "Admin" in names
    assert "create_user" in names
    assert "run_batch" in names
    assert "BackgroundTask" in names
    assert "OldAdapter" in names


def test_build_symbol_graph_pagerank_populated(multi_module_repo: Path, tmp_path: Path) -> None:
    """All returned symbols must have a float pagerank value."""
    db_path = tmp_path / "survey.db"
    symbols = build_symbol_graph(multi_module_repo, db_path=db_path)

    for sym in symbols:
        assert isinstance(sym["pagerank"], float), f"Expected float pagerank in {sym}"
        assert sym["pagerank"] >= 0.0, f"Negative pagerank in {sym}"


def test_build_symbol_graph_creates_db(multi_module_repo: Path, tmp_path: Path) -> None:
    """build_symbol_graph must persist symbols to survey.db."""
    db_path = tmp_path / "survey.db"
    build_symbol_graph(multi_module_repo, db_path=db_path)

    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    conn.close()
    assert count > 0


# ---------------------------------------------------------------------------
# compute_pagerank integration
# ---------------------------------------------------------------------------


def test_compute_pagerank_returns_sorted_list(multi_module_repo: Path, tmp_path: Path) -> None:
    """compute_pagerank must return symbols sorted by descending pagerank."""
    db_path = tmp_path / "survey.db"
    build_survey(multi_module_repo, db_path=db_path)
    ranked = compute_pagerank(multi_module_repo, db_path=db_path)

    assert isinstance(ranked, list)
    assert len(ranked) > 0

    scores = [r["pagerank"] for r in ranked]
    assert scores == sorted(scores, reverse=True), "compute_pagerank result is not sorted descending"


def test_compute_pagerank_result_schema(multi_module_repo: Path, tmp_path: Path) -> None:
    """Each entry from compute_pagerank must have id, name, path, kind, pagerank."""
    db_path = tmp_path / "survey.db"
    build_survey(multi_module_repo, db_path=db_path)
    ranked = compute_pagerank(multi_module_repo, db_path=db_path)

    for entry in ranked:
        assert "id" in entry
        assert "name" in entry
        assert "path" in entry
        assert "kind" in entry
        assert "pagerank" in entry


def test_compute_pagerank_builds_db_if_missing(tmp_path: Path) -> None:
    """compute_pagerank must build the DB if it doesn't exist yet."""
    (tmp_path / "foo.py").write_text("def hello(): pass\n")
    db_path = tmp_path / "survey.db"

    ranked = compute_pagerank(tmp_path, db_path=db_path)
    assert isinstance(ranked, list)
    assert db_path.exists()


# ---------------------------------------------------------------------------
# scan_implicit_features integration
# ---------------------------------------------------------------------------


def test_scan_implicit_features_finds_todo(multi_module_repo: Path, tmp_path: Path) -> None:
    """scan_implicit_features must find classes/functions with TODO docstrings."""
    db_path = tmp_path / "survey.db"
    candidates = scan_implicit_features(multi_module_repo, db_path=db_path)

    names = [c["name"] for c in candidates]
    assert "BackgroundTask" in names, f"Expected BackgroundTask (TODO doc) in {names}"


def test_scan_implicit_features_finds_stub(multi_module_repo: Path, tmp_path: Path) -> None:
    """scan_implicit_features must find classes with 'stub' docstrings."""
    db_path = tmp_path / "survey.db"
    candidates = scan_implicit_features(multi_module_repo, db_path=db_path)

    names = [c["name"] for c in candidates]
    assert "OldAdapter" in names, f"Expected OldAdapter (stub doc) in {names}"


def test_scan_implicit_features_result_schema(multi_module_repo: Path, tmp_path: Path) -> None:
    """Each candidate dict must have name, path, lineno, docstring, kind."""
    db_path = tmp_path / "survey.db"
    candidates = scan_implicit_features(multi_module_repo, db_path=db_path)

    for c in candidates:
        assert "name" in c, f"Missing 'name' in candidate: {c}"
        assert "path" in c, f"Missing 'path' in candidate: {c}"
        assert "lineno" in c, f"Missing 'lineno' in candidate: {c}"
        assert "docstring" in c, f"Missing 'docstring' in candidate: {c}"
        assert "kind" in c, f"Missing 'kind' in candidate: {c}"


def test_scan_implicit_features_empty_repo(tmp_path: Path) -> None:
    """scan_implicit_features on empty repo must return empty list."""
    db_path = tmp_path / "survey.db"
    candidates = scan_implicit_features(tmp_path, db_path=db_path)
    assert candidates == []


# ---------------------------------------------------------------------------
# End-to-end CLI integration
# ---------------------------------------------------------------------------


def test_cli_survey_end_to_end(multi_module_repo: Path, tmp_path: Path) -> None:
    """CLI survey command must build DB with correct symbol counts."""
    from bob3.cli import main

    db_path = tmp_path / "survey.db"
    runner = CliRunner()
    result = runner.invoke(main, ["survey", str(multi_module_repo), "--db", str(db_path)])
    assert result.exit_code == 0, f"CLI failed:\n{result.output}"

    conn = sqlite3.connect(str(db_path))
    symbol_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    file_count = conn.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0]
    conn.close()

    assert symbol_count > 0, "No symbols after CLI survey"
    assert file_count > 0, "No file_hashes after CLI survey"


def test_cli_survey_refresh_integration(multi_module_repo: Path, tmp_path: Path) -> None:
    """CLI survey --refresh must update symbols for a modified file."""
    from bob3.cli import main

    db_path = tmp_path / "survey.db"
    runner = CliRunner()

    # Initial build
    runner.invoke(main, ["survey", str(multi_module_repo), "--db", str(db_path)])

    # Add a new class to models.py
    models_file = multi_module_repo / "app" / "models.py"
    original = models_file.read_text()
    models_file.write_text(original + "\nclass NewEntity:\n    pass\n")

    result = runner.invoke(
        main, ["survey", str(multi_module_repo), "--refresh", "--db", str(db_path)]
    )
    assert result.exit_code == 0, f"CLI refresh failed:\n{result.output}"

    conn = sqlite3.connect(str(db_path))
    names = {row[0] for row in conn.execute("SELECT name FROM symbols").fetchall()}
    conn.close()

    assert "NewEntity" in names, f"NewEntity not found after refresh; symbols={names}"


def test_cli_survey_implicit_features_output(multi_module_repo: Path, tmp_path: Path) -> None:
    """CLI survey must mention implicit feature candidates in its output."""
    from bob3.cli import main

    db_path = tmp_path / "survey.db"
    runner = CliRunner()
    result = runner.invoke(main, ["survey", str(multi_module_repo), "--db", str(db_path)])
    assert result.exit_code == 0

    # The CLI should report at least the count of candidates or list them
    # BackgroundTask and OldAdapter are implicit features; output must acknowledge them
    assert "BackgroundTask" in result.output or "OldAdapter" in result.output or \
        "implicit" in result.output.lower() or "candidate" in result.output.lower(), (
        f"Expected implicit feature mention in output:\n{result.output}"
    )
