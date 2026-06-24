"""Tests for bob.behavior_ac_verifier.verify_quoted_substring_ac.

AC: pytest: tests/test_behavior_ac_verifier.py
AC: Function defined: bob.behavior_ac_verifier.verify_quoted_substring_ac
AC: integration: bob.verifier
"""

from __future__ import annotations

import pathlib

import pytest

from bob.behavior_ac_verifier import verify_quoted_substring_ac


@pytest.fixture
def workspace_with_queue_drained(tmp_path):
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "cli.py").write_text('MSG = "Queue drained"\n')
    return tmp_path


@pytest.fixture
def workspace_with_forbidden(tmp_path):
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "cli.py").write_text('MSG = "All remaining features are blocked"\n')
    return tmp_path


@pytest.fixture
def workspace_satisfying_both(tmp_path):
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "cli.py").write_text('MSG = "Queue drained"\n')
    return tmp_path


@pytest.fixture
def empty_workspace(tmp_path):
    (tmp_path / "src").mkdir()
    return tmp_path


# --- canonical AC from F-R7-586 ---

def test_canonical_ac_passes(workspace_satisfying_both):
    """Canonical AC: MUST mention present + MUST NOT use absent → True."""
    criterion = (
        "behavior: the CLI termination message for ALL_BLOCKED MUST mention "
        "'Queue drained' and MUST NOT use the phrase 'All remaining features are blocked'"
    )
    result = verify_quoted_substring_ac(criterion, workspace_satisfying_both)
    assert result is True


def test_forbidden_string_present_returns_none(workspace_with_forbidden):
    """If must-not-use literal is present in src, result is None."""
    criterion = (
        "behavior: MUST mention 'Queue drained' and "
        "MUST NOT use the phrase 'All remaining features are blocked'"
    )
    result = verify_quoted_substring_ac(criterion, workspace_with_forbidden)
    assert result is None


def test_no_literals_returns_none(empty_workspace):
    """No MUST-mention / MUST-NOT-use literals → None (fall-through)."""
    criterion = "behavior: the CLI must exit cleanly"
    result = verify_quoted_substring_ac(criterion, empty_workspace)
    assert result is None


def test_only_must_mention_satisfied(workspace_with_queue_drained):
    """Only MUST-mention clause present and satisfied → True."""
    criterion = "behavior: output MUST mention 'Queue drained'"
    result = verify_quoted_substring_ac(criterion, workspace_with_queue_drained)
    assert result is True


def test_only_must_not_use_absent(empty_workspace):
    """Only MUST-NOT-use clause; string absent → True."""
    criterion = "behavior: MUST NOT use the phrase 'deprecated_api'"
    result = verify_quoted_substring_ac(criterion, empty_workspace)
    assert result is True


# --- type validation ---

def test_none_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        verify_quoted_substring_ac(None, tmp_path)


def test_int_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        verify_quoted_substring_ac(42, tmp_path)


def test_bytes_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        verify_quoted_substring_ac(b"MUST mention 'X'", tmp_path)


# --- integration: bob.verifier re-exports the same function ---

def test_verifier_integration_import():
    """bob.verifier must export verify_quoted_substring_ac."""
    from bob.verifier import verify_quoted_substring_ac as vqs  # noqa: F401
    assert callable(vqs)


def test_verifier_integration_roundtrip(workspace_satisfying_both):
    """verify_quoted_substring_ac imported from bob.verifier works correctly."""
    from bob.verifier import verify_quoted_substring_ac as vqs
    criterion = (
        "behavior: the CLI MUST mention 'Queue drained' and "
        "MUST NOT use the phrase 'All remaining features are blocked'"
    )
    assert vqs(criterion, workspace_satisfying_both) is True
