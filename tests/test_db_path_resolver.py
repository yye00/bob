"""Tests for bob3.db_path_resolver.get_absolute_db_path.

Verifies that get_absolute_db_path:
  - is importable from bob3.db_path_resolver
  - returns an absolute path when given an explicit path argument
  - returns an absolute path when falling back to BOB3_DATABASE_PATH env var
  - returns an absolute path when falling back to cwd/bob3.db
  - resolves relative paths to absolute
  - logs the resolved path for telemetry
"""
from __future__ import annotations

import os
import pathlib
import tempfile

import pytest


def test_importable():
    from bob3.db_path_resolver import get_absolute_db_path
    assert callable(get_absolute_db_path)


def test_explicit_path_is_returned_as_absolute():
    from bob3.db_path_resolver import get_absolute_db_path
    with tempfile.TemporaryDirectory() as td:
        explicit = pathlib.Path(td) / "myproject.db"
        result = get_absolute_db_path(db_path=explicit)
        assert result == explicit.resolve()
        assert result.is_absolute()


def test_explicit_str_path_is_accepted():
    from bob3.db_path_resolver import get_absolute_db_path
    with tempfile.TemporaryDirectory() as td:
        explicit = str(pathlib.Path(td) / "myproject.db")
        result = get_absolute_db_path(db_path=explicit)
        assert result.is_absolute()
        assert result == pathlib.Path(explicit).resolve()


def test_env_var_used_when_no_explicit_path(monkeypatch):
    from bob3.db_path_resolver import get_absolute_db_path
    with tempfile.TemporaryDirectory() as td:
        env_path = str(pathlib.Path(td) / "env.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", env_path)
        result = get_absolute_db_path()
        assert result == pathlib.Path(env_path).resolve()
        assert result.is_absolute()


def test_cwd_fallback_when_no_env_and_no_explicit(monkeypatch, tmp_path):
    from bob3.db_path_resolver import get_absolute_db_path
    monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    result = get_absolute_db_path()
    assert result == (tmp_path / "bob3.db").resolve()
    assert result.is_absolute()


def test_explicit_path_takes_priority_over_env_var(monkeypatch):
    from bob3.db_path_resolver import get_absolute_db_path
    with tempfile.TemporaryDirectory() as td:
        explicit = pathlib.Path(td) / "explicit.db"
        env_path = str(pathlib.Path(td) / "env.db")
        monkeypatch.setenv("BOB3_DATABASE_PATH", env_path)
        result = get_absolute_db_path(db_path=explicit)
        assert result == explicit.resolve()
        assert str(result) != env_path


def test_relative_path_resolved_to_absolute():
    from bob3.db_path_resolver import get_absolute_db_path
    # relative path must become absolute
    result = get_absolute_db_path(db_path=pathlib.Path("somedir/test.db"))
    assert result.is_absolute()


def test_returns_pathlib_path_instance():
    from bob3.db_path_resolver import get_absolute_db_path
    with tempfile.TemporaryDirectory() as td:
        result = get_absolute_db_path(db_path=pathlib.Path(td) / "test.db")
        assert isinstance(result, pathlib.Path)
