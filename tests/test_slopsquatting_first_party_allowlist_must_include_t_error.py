"""Error path tests for slopsquatting first-party allowlist feature.

Tests that invalid input raises ValueError and the function does not
silently succeed (error path).
"""

from __future__ import annotations

import pytest
from pathlib import Path

from bob3.slopsquatting_first_party_allowlist_must_include_tools import (
    slopsquatting_first_party_allowlist_must_include_tools,
)


def test_raises_value_error_on_none() -> None:
    """None input raises ValueError, not AttributeError or other exception."""
    with pytest.raises(ValueError):
        slopsquatting_first_party_allowlist_must_include_tools(None)  # type: ignore[arg-type]


def test_raises_value_error_on_none_contains_none_message() -> None:
    """ValueError message for None input mentions 'None'."""
    with pytest.raises(ValueError, match="None"):
        slopsquatting_first_party_allowlist_must_include_tools(None)  # type: ignore[arg-type]


def test_raises_value_error_on_empty_string() -> None:
    """Empty string input raises ValueError."""
    with pytest.raises(ValueError):
        slopsquatting_first_party_allowlist_must_include_tools("")


def test_raises_value_error_on_empty_string_mentions_empty() -> None:
    """ValueError message for empty string mentions 'empty'."""
    with pytest.raises(ValueError, match="empty"):
        slopsquatting_first_party_allowlist_must_include_tools("")


def test_raises_value_error_on_nonexistent_path(tmp_path: Path) -> None:
    """Nonexistent path raises ValueError, not FileNotFoundError or OSError."""
    missing = tmp_path / "does_not_exist_at_all"
    with pytest.raises(ValueError):
        slopsquatting_first_party_allowlist_must_include_tools(missing)


def test_raises_value_error_on_nonexistent_path_mentions_does_not_exist(tmp_path: Path) -> None:
    """ValueError for nonexistent path mentions 'does not exist'."""
    missing = tmp_path / "no_such_dir"
    with pytest.raises(ValueError, match="does not exist"):
        slopsquatting_first_party_allowlist_must_include_tools(missing)


def test_raises_value_error_on_file_path(tmp_path: Path) -> None:
    """A file path (not a directory) raises ValueError."""
    f = tmp_path / "not_a_directory.py"
    f.write_text("# file\n")
    with pytest.raises(ValueError):
        slopsquatting_first_party_allowlist_must_include_tools(f)


def test_raises_value_error_on_file_path_mentions_directory(tmp_path: Path) -> None:
    """ValueError for file path mentions 'directory'."""
    f = tmp_path / "some_file.txt"
    f.write_text("content\n")
    with pytest.raises(ValueError, match="directory"):
        slopsquatting_first_party_allowlist_must_include_tools(f)


def test_does_not_silently_succeed_on_none() -> None:
    """None does not silently return an empty set — it must raise."""
    raised = False
    try:
        slopsquatting_first_party_allowlist_must_include_tools(None)  # type: ignore[arg-type]
    except ValueError:
        raised = True
    assert raised, "None must raise ValueError, not return silently"


def test_does_not_silently_succeed_on_empty_string() -> None:
    """Empty string does not silently return an empty set — it must raise."""
    raised = False
    try:
        slopsquatting_first_party_allowlist_must_include_tools("")
    except ValueError:
        raised = True
    assert raised, "Empty string must raise ValueError, not return silently"


def test_does_not_silently_succeed_on_nonexistent_path(tmp_path: Path) -> None:
    """Nonexistent path does not silently return an empty set — it must raise."""
    raised = False
    missing = tmp_path / "ghost_dir"
    try:
        slopsquatting_first_party_allowlist_must_include_tools(missing)
    except ValueError:
        raised = True
    assert raised, "Nonexistent path must raise ValueError, not return silently"
