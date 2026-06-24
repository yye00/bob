"""Tests for behavior_ac_quoted_substring_must_mention_must_not_use.

AC: pytest: tests/test_behavior_ac_quoted_substring_must_mention_must_not_use.py::test_behavior_ac_quoted_substring_must_mention_must_not_use
AC: Function defined: bob.behavior_ac_quoted_substring_must_mention_must_not_use.behavior_ac_quoted_substring_must_mention_must_not_use
"""

from __future__ import annotations

import pathlib

import pytest

from bob.behavior_ac_quoted_substring_must_mention_must_not_use import (
    behavior_ac_quoted_substring_must_mention_must_not_use,
)


@pytest.fixture
def workspace_with_must_mention(tmp_path):
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "cli_messages.py").write_text(
        'TERMINATION_MSG = "Queue drained"\n'
    )
    return tmp_path


@pytest.fixture
def workspace_with_forbidden_string(tmp_path):
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "cli_messages.py").write_text(
        'MSG = "All remaining features are blocked"\n'
    )
    return tmp_path


@pytest.fixture
def workspace_satisfying_both(tmp_path):
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "cli_messages.py").write_text(
        'TERMINATION_MSG = "Queue drained"\n'
    )
    return tmp_path


@pytest.fixture
def empty_workspace(tmp_path):
    (tmp_path / "src").mkdir()
    return tmp_path


def test_behavior_ac_quoted_substring_must_mention_must_not_use(workspace_satisfying_both):
    """Canonical AC test: MUST-mention present + MUST-NOT-use absent → True."""
    criterion = (
        "behavior: the CLI termination message for ALL_BLOCKED MUST mention "
        "'Queue drained' and MUST NOT use the phrase 'All remaining features are blocked'"
    )
    result = behavior_ac_quoted_substring_must_mention_must_not_use(criterion, workspace_satisfying_both)
    assert result is True


def test_returns_none_when_no_literals(empty_workspace):
    criterion = "behavior: the CLI must exit cleanly"
    result = behavior_ac_quoted_substring_must_mention_must_not_use(criterion, empty_workspace)
    assert result is None


def test_returns_none_when_must_mention_absent(empty_workspace):
    criterion = "behavior: output MUST mention 'Queue drained'"
    result = behavior_ac_quoted_substring_must_mention_must_not_use(criterion, empty_workspace)
    assert result is None


def test_returns_true_when_only_must_mention_satisfied(workspace_with_must_mention):
    criterion = "behavior: output MUST mention 'Queue drained'"
    result = behavior_ac_quoted_substring_must_mention_must_not_use(criterion, workspace_with_must_mention)
    assert result is True


def test_returns_none_when_forbidden_string_present(workspace_with_forbidden_string):
    criterion = (
        "behavior: MUST mention 'Queue drained' and "
        "MUST NOT use the phrase 'All remaining features are blocked'"
    )
    result = behavior_ac_quoted_substring_must_mention_must_not_use(criterion, workspace_with_forbidden_string)
    assert result is None


def test_returns_true_when_only_must_not_use_and_absent(empty_workspace):
    criterion = "behavior: MUST NOT use the phrase 'deprecated_api_call'"
    result = behavior_ac_quoted_substring_must_mention_must_not_use(criterion, empty_workspace)
    assert result is True


def test_no_src_dir_returns_none():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        ws = pathlib.Path(d)
        criterion = "behavior: MUST mention 'Queue drained'"
        result = behavior_ac_quoted_substring_must_mention_must_not_use(criterion, ws)
        assert result is None
