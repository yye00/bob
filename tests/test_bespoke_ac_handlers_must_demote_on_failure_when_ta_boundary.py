"""Boundary cases for bob.enhanced_verification.demote_on_failure (bc07b13a).

Tests edge/boundary inputs: empty probes, None-like returns, module paths at
filesystem boundaries, and minimum valid call shapes.

Policy (F-R7-584): when a bespoke probe fails (returns False or raises) but the
target module file EXISTS on disk, demote_on_failure must return True and emit
an 'F-R7-584' warning.  When the module does NOT exist, return False.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from bob.enhanced_verification import demote_on_failure


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_module(tmp_path: pathlib.Path, rel: str = "src/bob/mymod.py") -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# stub\n")
    return p


# ---------------------------------------------------------------------------
# Boundary: probe returns None (falsy but not False)
# ---------------------------------------------------------------------------


def test_probe_returns_none_module_exists_demotes(tmp_path):
    """probe() returning None (falsy) with module present → demote to True."""
    mod = _make_module(tmp_path)

    def probe_none():
        return None

    result = demote_on_failure(probe=probe_none, module_path=mod, workspace=tmp_path)
    assert result is True


def test_probe_returns_none_module_absent_returns_false(tmp_path):
    """probe() returning None (falsy) without module → return False."""
    absent = tmp_path / "src" / "bob" / "absent.py"

    def probe_none():
        return None

    result = demote_on_failure(probe=probe_none, module_path=absent, workspace=tmp_path)
    assert result is False


# ---------------------------------------------------------------------------
# Boundary: probe returns 0 (falsy but not False)
# ---------------------------------------------------------------------------


def test_probe_returns_zero_module_exists_demotes(tmp_path):
    """probe() returning 0 (falsy) with module present → demote to True."""
    mod = _make_module(tmp_path)

    def probe_zero():
        return 0

    result = demote_on_failure(probe=probe_zero, module_path=mod, workspace=tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# Boundary: probe returns empty string (falsy)
# ---------------------------------------------------------------------------


def test_probe_returns_empty_string_module_exists_demotes(tmp_path):
    """probe() returning empty string (falsy) with module present → demote to True."""
    mod = _make_module(tmp_path)

    def probe_empty_str():
        return ""

    result = demote_on_failure(probe=probe_empty_str, module_path=mod, workspace=tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# Boundary: probe returns True (passing probe)
# ---------------------------------------------------------------------------


def test_probe_returns_true_no_warning_emitted(tmp_path, caplog):
    """probe() returning True → True, and no F-R7-584 warning is emitted."""
    mod = _make_module(tmp_path)

    def probe_true():
        return True

    with caplog.at_level(logging.WARNING, logger="bob"):
        result = demote_on_failure(probe=probe_true, module_path=mod, workspace=tmp_path)

    assert result is True
    assert "F-R7-584" not in caplog.text


# ---------------------------------------------------------------------------
# Boundary: module_path is a directory (exists but not a file)
# ---------------------------------------------------------------------------


def test_probe_false_module_path_is_directory_demotes(tmp_path):
    """module_path pointing to an existing directory → demote to True (exists check)."""
    dir_path = tmp_path / "src" / "bob"
    dir_path.mkdir(parents=True, exist_ok=True)

    def probe_false():
        return False

    result = demote_on_failure(probe=probe_false, module_path=dir_path, workspace=tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# Boundary: probe raises BaseException subclass (not just Exception)
# ---------------------------------------------------------------------------


def test_probe_raises_keyboard_interrupt_module_exists_demotes(tmp_path):
    """probe() raising KeyboardInterrupt with module present → demote to True."""
    mod = _make_module(tmp_path)

    def probe_keyboard():
        raise KeyboardInterrupt("simulated")

    result = demote_on_failure(probe=probe_keyboard, module_path=mod, workspace=tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# Boundary: module_path in deeply nested directory
# ---------------------------------------------------------------------------


def test_probe_false_deeply_nested_module_exists_demotes(tmp_path):
    """Module nested deep in tmp_path with probe False → demotes to True."""
    mod = _make_module(tmp_path, rel="src/bob/sub/deep/nested/module.py")

    def probe_false():
        return False

    result = demote_on_failure(probe=probe_false, module_path=mod, workspace=tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# Boundary: workspace arg unused in core logic (just passed through)
# ---------------------------------------------------------------------------


def test_workspace_arg_does_not_affect_probe_false_module_exists(tmp_path):
    """Changing workspace does not affect the demote decision when module exists."""
    mod = _make_module(tmp_path)
    other_workspace = tmp_path / "other"
    other_workspace.mkdir()

    def probe_false():
        return False

    result = demote_on_failure(probe=probe_false, module_path=mod, workspace=other_workspace)
    assert result is True


# ---------------------------------------------------------------------------
# Boundary: minimum valid call — all required kwargs provided
# ---------------------------------------------------------------------------


def test_minimum_valid_call_probe_passes(tmp_path):
    """Minimum valid call with a passing probe returns True without error."""
    mod = _make_module(tmp_path)

    result = demote_on_failure(probe=lambda: True, module_path=mod, workspace=tmp_path)
    assert result is True


def test_minimum_valid_call_probe_fails_module_exists(tmp_path):
    """Minimum valid call with a failing probe and existing module returns True."""
    mod = _make_module(tmp_path)

    result = demote_on_failure(probe=lambda: False, module_path=mod, workspace=tmp_path)
    assert result is True


def test_minimum_valid_call_probe_fails_module_absent(tmp_path):
    """Minimum valid call with a failing probe and absent module returns False."""
    absent = tmp_path / "does_not_exist.py"

    result = demote_on_failure(probe=lambda: False, module_path=absent, workspace=tmp_path)
    assert result is False
