"""Error-path tests for bob3.enhanced_verification.demote_on_failure (bc07b13a).

Tests that invalid inputs raise ValueError and the function does not silently succeed.

Policy (F-R7-584): the demote_on_failure function must validate its inputs and
raise ValueError when required arguments are None or of an invalid type, rather
than silently returning True/False.
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.enhanced_verification import demote_on_failure


# ---------------------------------------------------------------------------
# Error: probe is None
# ---------------------------------------------------------------------------


def test_probe_none_raises_value_error(tmp_path):
    """Passing probe=None must raise ValueError, not silently succeed."""
    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    with pytest.raises(ValueError, match="probe"):
        demote_on_failure(probe=None, module_path=mod, workspace=tmp_path)


# ---------------------------------------------------------------------------
# Error: probe is not callable
# ---------------------------------------------------------------------------


def test_probe_not_callable_raises_value_error(tmp_path):
    """Passing a non-callable as probe must raise ValueError."""
    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    with pytest.raises(ValueError, match="probe"):
        demote_on_failure(probe="not_a_callable", module_path=mod, workspace=tmp_path)


def test_probe_integer_raises_value_error(tmp_path):
    """Passing an integer as probe must raise ValueError."""
    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    with pytest.raises(ValueError, match="probe"):
        demote_on_failure(probe=42, module_path=mod, workspace=tmp_path)


# ---------------------------------------------------------------------------
# Error: module_path is None
# ---------------------------------------------------------------------------


def test_module_path_none_raises_value_error(tmp_path):
    """Passing module_path=None must raise ValueError."""
    with pytest.raises(ValueError, match="module_path"):
        demote_on_failure(probe=lambda: False, module_path=None, workspace=tmp_path)


# ---------------------------------------------------------------------------
# Error: module_path is a string instead of pathlib.Path
# ---------------------------------------------------------------------------


def test_module_path_string_raises_value_error(tmp_path):
    """Passing module_path as a string instead of pathlib.Path must raise ValueError."""
    with pytest.raises(ValueError, match="module_path"):
        demote_on_failure(
            probe=lambda: False,
            module_path="/some/path/module.py",
            workspace=tmp_path,
        )


# ---------------------------------------------------------------------------
# Error: workspace is None
# ---------------------------------------------------------------------------


def test_workspace_none_raises_value_error(tmp_path):
    """Passing workspace=None must raise ValueError."""
    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    with pytest.raises(ValueError, match="workspace"):
        demote_on_failure(probe=lambda: False, module_path=mod, workspace=None)


# ---------------------------------------------------------------------------
# Error: workspace is a string instead of pathlib.Path
# ---------------------------------------------------------------------------


def test_workspace_string_raises_value_error(tmp_path):
    """Passing workspace as a string must raise ValueError."""
    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    with pytest.raises(ValueError, match="workspace"):
        demote_on_failure(
            probe=lambda: False,
            module_path=mod,
            workspace="/some/workspace",
        )


# ---------------------------------------------------------------------------
# Confirm: valid inputs do NOT raise
# ---------------------------------------------------------------------------


def test_valid_inputs_do_not_raise(tmp_path):
    """Sanity check: valid inputs must not raise ValueError."""
    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    result = demote_on_failure(probe=lambda: False, module_path=mod, workspace=tmp_path)
    assert result is True
