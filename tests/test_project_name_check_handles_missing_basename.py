"""Tests: handle_missing_workspace_basename raises WorkspaceBasenameMissingError.

Asserts that handle_missing_workspace_basename raises WorkspaceBasenameMissingError
when cwd has no basename (null/empty boundary), and returns the basename when
the path is a normal directory.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bob.orchestrator.project_metadata_check import (
    WorkspaceBasenameMissingError,
    handle_missing_workspace_basename,
)


def test_returns_basename_for_normal_path(tmp_path):
    """Returns the basename string for a normal directory."""
    basename = handle_missing_workspace_basename(tmp_path)
    assert basename == tmp_path.name
    assert len(basename) > 0


def test_raises_for_filesystem_root():
    """Raises WorkspaceBasenameMissingError for the root path '/'."""
    root = Path("/")
    with pytest.raises(WorkspaceBasenameMissingError) as exc_info:
        handle_missing_workspace_basename(root)
    assert "no basename" in str(exc_info.value).lower() or "basename" in str(exc_info.value).lower()


def test_raises_error_message_mentions_path():
    """The error message should reference the problematic path."""
    root = Path("/")
    with pytest.raises(WorkspaceBasenameMissingError) as exc_info:
        handle_missing_workspace_basename(root)
    # Error should give context about what path caused the issue
    error_msg = str(exc_info.value)
    assert "/" in error_msg


def test_returns_basename_for_nested_path(tmp_path):
    """Works correctly for deeply nested directories."""
    nested = tmp_path / "dark-factory" / "bob13"
    nested.mkdir(parents=True)
    basename = handle_missing_workspace_basename(nested)
    assert basename == "bob13"


def test_default_uses_cwd(monkeypatch, tmp_path):
    """Without an argument, uses Path.cwd() as the workspace."""
    monkeypatch.chdir(tmp_path)
    basename = handle_missing_workspace_basename()
    assert basename == tmp_path.name
