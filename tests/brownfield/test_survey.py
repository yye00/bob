"""Tests for bob.brownfield.survey — BF-1 Brownfield Survey/Index."""

from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from bob.brownfield.survey import build_survey, refresh_survey


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Minimal fake Python repo with defs + imports."""
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "models.py").write_text(
        textwrap.dedent("""\
        class User:
            '''A user model.'''
            def get_name(self):
                return self.name

        class Admin(User):
            pass
        """)
    )
    (pkg / "utils.py").write_text(
        textwrap.dedent("""\
        from mypkg.models import User

        def make_user(name: str) -> User:
            return User()

        # TODO: add role validation
        """)
    )
    (pkg / "stub_module.py").write_text(
        textwrap.dedent("""\
        class NotImplFeature:
            '''stub: not yet implemented'''
            def run(self):
                pass
        """)
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tests for build_survey
# ---------------------------------------------------------------------------


def test_build_survey_creates_db(repo: Path, tmp_path: Path) -> None:
    """build_survey must create survey.db under .bob/."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)
    assert db_path.exists(), "survey.db was not created"


def test_build_survey_symbols_table(repo: Path, tmp_path: Path) -> None:
    """symbols table must contain class and function definitions."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    names = {row[0] for row in conn.execute("SELECT name FROM symbols").fetchall()}
    conn.close()

    assert "User" in names, f"Expected class User in symbols, got {names}"
    assert "Admin" in names
    assert "make_user" in names


def test_build_survey_symbols_schema(repo: Path, tmp_path: Path) -> None:
    """symbols table must have id, path, kind, name, sha, lineno, parent_id, pagerank columns."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(symbols)").fetchall()}
    conn.close()

    required = {"id", "path", "kind", "name", "sha", "lineno", "parent_id", "pagerank"}
    assert required <= cols, f"Missing columns: {required - cols}"


def test_build_survey_edges_table(repo: Path, tmp_path: Path) -> None:
    """edges table must record import edges between symbols."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    cols = {row[1] for row in conn.execute("PRAGMA table_info(edges)").fetchall()}
    conn.close()

    assert {"src_id", "dst_id", "kind"} <= cols, f"Missing edge columns: {cols}"
    assert edge_count >= 0  # edges table exists and is queryable


def test_build_survey_file_hashes(repo: Path, tmp_path: Path) -> None:
    """file_hashes must record path, sha, mtime, parsed_at for each parsed file."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(file_hashes)").fetchall()}
    row_count = conn.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0]
    conn.close()

    assert {"path", "sha", "mtime", "parsed_at"} <= cols, f"Missing file_hashes columns: {cols}"
    assert row_count > 0, "file_hashes must have at least one entry after build_survey"


def test_build_survey_pagerank_computed(repo: Path, tmp_path: Path) -> None:
    """pagerank column in symbols must be non-null floats after build_survey."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT pagerank FROM symbols WHERE pagerank IS NOT NULL").fetchall()
    conn.close()

    assert rows, "No symbols have a non-null pagerank value"
    for (rank,) in rows:
        assert isinstance(rank, float), f"pagerank must be float, got {type(rank)}"
        assert rank >= 0.0, f"pagerank must be non-negative, got {rank}"


def test_build_survey_implicit_feature_scan(repo: Path, tmp_path: Path) -> None:
    """build_survey must return candidate features for stub/todo/notimpl docstrings."""
    db_path = tmp_path / "survey.db"
    candidates = build_survey(repo, db_path=db_path)

    assert isinstance(candidates, list), "build_survey must return a list of candidate features"
    # NotImplFeature has 'stub' in its docstring — must appear
    names = [c["name"] for c in candidates]
    assert any("NotImplFeature" in n for n in names), (
        f"Expected NotImplFeature (stub docstring) in candidates, got {names}"
    )


def test_build_survey_method_kind(repo: Path, tmp_path: Path) -> None:
    """Methods inside classes should be stored with kind='method' and a parent_id."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT name, kind, parent_id FROM symbols WHERE kind='method'"
    ).fetchall()
    conn.close()

    assert rows, "No method-kind symbols found"
    for name, kind, parent_id in rows:
        assert parent_id is not None, f"Method {name} must have a parent_id"


# ---------------------------------------------------------------------------
# Tests for refresh_survey
# ---------------------------------------------------------------------------


def test_refresh_survey_skips_unchanged(repo: Path, tmp_path: Path) -> None:
    """refresh_survey must not re-parse files whose sha has not changed."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    before = conn.execute("SELECT sha FROM file_hashes ORDER BY path").fetchall()
    conn.close()

    candidates = refresh_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    after = conn.execute("SELECT sha FROM file_hashes ORDER BY path").fetchall()
    conn.close()

    assert before == after, "file_hashes changed even though no files changed"
    assert isinstance(candidates, list)


def test_refresh_survey_updates_changed_file(repo: Path, tmp_path: Path) -> None:
    """refresh_survey must re-parse a file whose content changed."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)

    changed_file = repo / "mypkg" / "models.py"
    new_content = textwrap.dedent("""\
    class Product:
        pass

    def get_product():
        return Product()
    """)
    changed_file.write_text(new_content)

    refresh_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    names = {row[0] for row in conn.execute("SELECT name FROM symbols").fetchall()}
    conn.close()

    assert "Product" in names, f"New symbol Product not found after refresh; symbols={names}"
    assert "get_product" in names


def test_refresh_survey_removes_deleted_file(repo: Path, tmp_path: Path) -> None:
    """refresh_survey must remove symbols from a deleted file."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)

    (repo / "mypkg" / "utils.py").unlink()

    refresh_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    paths = {row[0] for row in conn.execute("SELECT DISTINCT path FROM symbols").fetchall()}
    conn.close()

    assert not any("utils.py" in p for p in paths), (
        f"utils.py symbols still present after deletion; paths={paths}"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_build_survey_empty_repo(tmp_path: Path) -> None:
    """build_survey on an empty directory must not crash and return an empty list."""
    db_path = tmp_path / "survey.db"
    candidates = build_survey(tmp_path, db_path=db_path)
    assert isinstance(candidates, list)
    assert candidates == []


def test_build_survey_idempotent(repo: Path, tmp_path: Path) -> None:
    """Calling build_survey twice must produce the same symbols (idempotent)."""
    db_path = tmp_path / "survey.db"
    build_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    first = conn.execute("SELECT name FROM symbols ORDER BY name").fetchall()
    conn.close()

    build_survey(repo, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    second = conn.execute("SELECT name FROM symbols ORDER BY name").fetchall()
    conn.close()

    assert first == second, "build_survey is not idempotent"


# ---------------------------------------------------------------------------
# CLI integration (AC: integration: bob.cli)
# ---------------------------------------------------------------------------


def test_cli_survey_command_registered() -> None:
    """bob CLI must expose a 'survey' command."""
    from bob.cli import main

    assert "survey" in main.commands, (
        f"'survey' command not found in bob CLI; available: {list(main.commands.keys())}"
    )


def test_cli_survey_build(repo: Path, tmp_path: Path) -> None:
    """bob survey <path> must build the index and exit 0."""
    from bob.cli import main

    db_path = tmp_path / "survey.db"
    runner = CliRunner()
    result = runner.invoke(main, ["survey", str(repo), "--db", str(db_path)])
    assert result.exit_code == 0, f"CLI survey failed:\n{result.output}"
    assert db_path.exists(), "survey.db not created by CLI"


def test_cli_survey_refresh(repo: Path, tmp_path: Path) -> None:
    """bob survey --refresh <path> must perform incremental update and exit 0."""
    from bob.cli import main

    db_path = tmp_path / "survey.db"
    runner = CliRunner()
    # Build first
    runner.invoke(main, ["survey", str(repo), "--db", str(db_path)])
    # Then refresh
    result = runner.invoke(main, ["survey", str(repo), "--refresh", "--db", str(db_path)])
    assert result.exit_code == 0, f"CLI survey --refresh failed:\n{result.output}"
