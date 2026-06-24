"""Tests for bob.enhanced_verification.demote_bespoke_on_failure (dfaba5e5).

Validates the demote-on-failure semantics (F-R7-584): bespoke AC handlers MUST
demote (return True) when the target module exists, even if the strict probe
fails. This prevents NH-treadmilling at attempts=5 when a spec asks a module to
gain behavior it hasn't yet implemented.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from bob.enhanced_verification import demote_bespoke_on_failure


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_module(tmp_path: pathlib.Path, rel: str = "src/bob/mymod.py") -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# stub\n")
    return p


# ---------------------------------------------------------------------------
# Core demote-on-failure semantics
# ---------------------------------------------------------------------------


def test_probe_passes_returns_true(tmp_path):
    """probe() returning True → function returns True."""
    mod = _make_module(tmp_path)
    result = demote_bespoke_on_failure(probe=lambda: True, module_path=mod, workspace=tmp_path)
    assert result is True


def test_probe_fails_module_exists_demotes_to_true(tmp_path):
    """probe() returning False with module present → demote to True (F-R7-584)."""
    mod = _make_module(tmp_path)
    result = demote_bespoke_on_failure(probe=lambda: False, module_path=mod, workspace=tmp_path)
    assert result is True


def test_probe_fails_module_absent_returns_false(tmp_path):
    """probe() returning False with module absent → return False."""
    absent = tmp_path / "src" / "bob" / "missing.py"
    result = demote_bespoke_on_failure(
        probe=lambda: False, module_path=absent, workspace=tmp_path
    )
    assert result is False


def test_probe_raises_module_exists_demotes_to_true(tmp_path):
    """probe() raising with module present → demote to True (F-R7-584)."""
    mod = _make_module(tmp_path)

    def probe_raises():
        raise RuntimeError("simulated probe failure")

    result = demote_bespoke_on_failure(probe=probe_raises, module_path=mod, workspace=tmp_path)
    assert result is True


def test_probe_raises_module_absent_returns_false(tmp_path):
    """probe() raising with module absent → return False."""
    absent = tmp_path / "src" / "bob" / "not_there.py"

    def probe_raises():
        raise RuntimeError("simulated probe failure")

    result = demote_bespoke_on_failure(
        probe=probe_raises, module_path=absent, workspace=tmp_path
    )
    assert result is False


# ---------------------------------------------------------------------------
# Warning emission (F-R7-584 tag must appear in log)
# ---------------------------------------------------------------------------


def test_demotion_emits_f_r7_584_warning(tmp_path, caplog):
    """When demotion occurs, a warning containing 'F-R7-584' must be emitted."""
    mod = _make_module(tmp_path)

    with caplog.at_level(logging.WARNING, logger="bob"):
        demote_bespoke_on_failure(probe=lambda: False, module_path=mod, workspace=tmp_path)

    assert "F-R7-584" in caplog.text


def test_no_demotion_warning_when_probe_passes(tmp_path, caplog):
    """When probe passes, no F-R7-584 warning should be emitted."""
    mod = _make_module(tmp_path)

    with caplog.at_level(logging.WARNING, logger="bob"):
        demote_bespoke_on_failure(probe=lambda: True, module_path=mod, workspace=tmp_path)

    assert "F-R7-584" not in caplog.text


# ---------------------------------------------------------------------------
# Input validation (ValueError for invalid args)
# ---------------------------------------------------------------------------


def test_probe_none_raises_value_error(tmp_path):
    """probe=None must raise ValueError."""
    mod = _make_module(tmp_path)
    with pytest.raises(ValueError, match="probe"):
        demote_bespoke_on_failure(probe=None, module_path=mod, workspace=tmp_path)


def test_probe_not_callable_raises_value_error(tmp_path):
    """Non-callable probe must raise ValueError."""
    mod = _make_module(tmp_path)
    with pytest.raises(ValueError, match="probe"):
        demote_bespoke_on_failure(probe="not_callable", module_path=mod, workspace=tmp_path)


def test_module_path_string_raises_value_error(tmp_path):
    """module_path as string (not pathlib.Path) must raise ValueError."""
    with pytest.raises(ValueError, match="module_path"):
        demote_bespoke_on_failure(
            probe=lambda: False,
            module_path="/some/path/mod.py",
            workspace=tmp_path,
        )


def test_workspace_none_raises_value_error(tmp_path):
    """workspace=None must raise ValueError."""
    mod = _make_module(tmp_path)
    with pytest.raises(ValueError, match="workspace"):
        demote_bespoke_on_failure(probe=lambda: False, module_path=mod, workspace=None)


def test_workspace_string_raises_value_error(tmp_path):
    """workspace as string must raise ValueError."""
    mod = _make_module(tmp_path)
    with pytest.raises(ValueError, match="workspace"):
        demote_bespoke_on_failure(
            probe=lambda: False, module_path=mod, workspace="/some/workspace"
        )


# ---------------------------------------------------------------------------
# Integration: demote_bespoke_on_failure is importable from enhanced_verification
# ---------------------------------------------------------------------------


def test_demote_bespoke_on_failure_is_callable():
    """demote_bespoke_on_failure must be importable and callable."""
    assert callable(demote_bespoke_on_failure)
