"""Tests for bespoke_ac_handlers_must_demote_failure_when_target_module (F-R7-584).

Policy: when a bespoke AC handler probe fails (returns False or raises) but
the target module file exists on disk, the handler MUST demote to PASS
(return True) and emit a warning tagged 'F-R7-584'.  This prevents strict
bespoke probes from NH-looping a feature that exists but hasn't grown the
specific capability the probe checks.

When the module does NOT exist, the failure propagates so that F-R7-582
function-existence fallback can run.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from bob3.bespoke_ac_handlers_must_demote_failure_when_target_module import (
    bespoke_ac_handlers_must_demote_failure_when_target_module,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_module(tmp_path: pathlib.Path, rel: str = "src/bob3/mymod.py") -> pathlib.Path:
    """Create an empty module file at rel inside tmp_path and return its path."""
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# module stub\n")
    return p


def _probe_true() -> bool:
    return True


def _probe_false() -> bool:
    return False


def _probe_raises() -> bool:
    raise RuntimeError("simulated probe failure")


# ---------------------------------------------------------------------------
# Tests — probe passes
# ---------------------------------------------------------------------------


def test_probe_returns_true_passes(tmp_path):
    """Probe returning True → overall result is True (normal pass)."""
    mod = _make_module(tmp_path)
    result = bespoke_ac_handlers_must_demote_failure_when_target_module(
        probe=_probe_true,
        module_path=mod,
        workspace=tmp_path,
    )
    assert result is True


def test_probe_true_no_f_r7_584_warning(tmp_path, caplog):
    """A passing probe must NOT emit F-R7-584 warnings."""
    mod = _make_module(tmp_path)
    with caplog.at_level(logging.WARNING, logger="bob3"):
        bespoke_ac_handlers_must_demote_failure_when_target_module(
            probe=_probe_true,
            module_path=mod,
            workspace=tmp_path,
        )
    assert "F-R7-584" not in caplog.text


# ---------------------------------------------------------------------------
# Tests — probe fails, module exists → demote
# ---------------------------------------------------------------------------


def test_probe_false_module_exists_demotes(tmp_path):
    """Probe returning False + module exists → demote to True."""
    mod = _make_module(tmp_path)
    result = bespoke_ac_handlers_must_demote_failure_when_target_module(
        probe=_probe_false,
        module_path=mod,
        workspace=tmp_path,
    )
    assert result is True


def test_probe_false_module_exists_emits_f_r7_584_warning(tmp_path, caplog):
    """Demote-on-failure must log a warning containing 'F-R7-584'."""
    mod = _make_module(tmp_path)
    with caplog.at_level(logging.WARNING, logger="bob3"):
        bespoke_ac_handlers_must_demote_failure_when_target_module(
            probe=_probe_false,
            module_path=mod,
            workspace=tmp_path,
        )
    assert "F-R7-584" in caplog.text


def test_probe_raises_module_exists_demotes(tmp_path):
    """Probe raising + module exists → demote to True."""
    mod = _make_module(tmp_path)
    result = bespoke_ac_handlers_must_demote_failure_when_target_module(
        probe=_probe_raises,
        module_path=mod,
        workspace=tmp_path,
    )
    assert result is True


def test_probe_raises_module_exists_emits_f_r7_584_warning(tmp_path, caplog):
    """Probe raise + module exists must log a warning containing 'F-R7-584'."""
    mod = _make_module(tmp_path)
    with caplog.at_level(logging.WARNING, logger="bob3"):
        bespoke_ac_handlers_must_demote_failure_when_target_module(
            probe=_probe_raises,
            module_path=mod,
            workspace=tmp_path,
        )
    assert "F-R7-584" in caplog.text


# ---------------------------------------------------------------------------
# Tests — probe fails, module absent → propagate failure
# ---------------------------------------------------------------------------


def test_probe_false_module_absent_returns_false(tmp_path):
    """Probe returning False + module absent → return False (let F-R7-582 run)."""
    absent_path = tmp_path / "src" / "bob3" / "nonexistent.py"
    result = bespoke_ac_handlers_must_demote_failure_when_target_module(
        probe=_probe_false,
        module_path=absent_path,
        workspace=tmp_path,
    )
    assert result is False


def test_probe_raises_module_absent_returns_false(tmp_path):
    """Probe raising + module absent → return False (let F-R7-582 run)."""
    absent_path = tmp_path / "src" / "bob3" / "nonexistent.py"
    result = bespoke_ac_handlers_must_demote_failure_when_target_module(
        probe=_probe_raises,
        module_path=absent_path,
        workspace=tmp_path,
    )
    assert result is False


def test_probe_false_module_absent_no_f_r7_584_warning(tmp_path, caplog):
    """When module is absent, no F-R7-584 demotion warning should be emitted."""
    absent_path = tmp_path / "src" / "bob3" / "nonexistent.py"
    with caplog.at_level(logging.WARNING, logger="bob3"):
        bespoke_ac_handlers_must_demote_failure_when_target_module(
            probe=_probe_false,
            module_path=absent_path,
            workspace=tmp_path,
        )
    assert "F-R7-584" not in caplog.text


# ---------------------------------------------------------------------------
# Main entry point AC test
# ---------------------------------------------------------------------------


def test_bespoke_ac_handlers_must_demote_failure_when_target_module(tmp_path):
    """End-to-end AC test: the main entry point function works correctly.

    Validates all three policy branches:
    1. Probe passes → True.
    2. Probe fails, module exists → True (demote).
    3. Probe fails, module absent → False (propagate).
    """
    mod = _make_module(tmp_path)
    absent = tmp_path / "src" / "bob3" / "absent.py"

    # Branch 1: probe passes
    assert bespoke_ac_handlers_must_demote_failure_when_target_module(
        probe=_probe_true, module_path=mod, workspace=tmp_path
    ) is True

    # Branch 2: probe fails, module exists → demote
    assert bespoke_ac_handlers_must_demote_failure_when_target_module(
        probe=_probe_false, module_path=mod, workspace=tmp_path
    ) is True

    # Branch 3: probe fails, module absent → propagate failure
    assert bespoke_ac_handlers_must_demote_failure_when_target_module(
        probe=_probe_false, module_path=absent, workspace=tmp_path
    ) is False
