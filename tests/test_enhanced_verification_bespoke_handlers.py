"""Tests for bespoke_ac_handler_with_demotion (F-R7-584 / feature 057a011f).

The function implements the "soft bespoke probe" policy:
- If the probe callable returns True  → bespoke check passed, return True.
- If the probe returns False/raises AND the target module file EXISTS
  → log a warning with 'F-R7-584' and return True (demote-on-failure).
- If the module file does NOT exist → return False so F-R7-582 can take over.

This prevents strict bespoke handlers from NH-looping a feature that simply
hasn't yet grown the probed capability — the module exists, it just hasn't
implemented the specific behaviour the probe checks.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Callable

import pytest

from bob3.enhanced_verification import bespoke_ac_handler_with_demotion


# ---------------------------------------------------------------------------
# Probe factories
# ---------------------------------------------------------------------------

def _probe_returns_true() -> Callable[[], bool]:
    def probe() -> bool:
        return True
    return probe


def _probe_returns_false() -> Callable[[], bool]:
    def probe() -> bool:
        return False
    return probe


def _probe_raises() -> Callable[[], bool]:
    def probe() -> bool:
        raise RuntimeError("simulated probe failure")
    return probe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _module_at(tmp_path: pathlib.Path, rel: str = "src/mymod/module.py") -> pathlib.Path:
    """Create an empty module file and return its path."""
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# stub\n")
    return p


# ---------------------------------------------------------------------------
# Tests — probe passes
# ---------------------------------------------------------------------------


def test_probe_true_returns_true(tmp_path):
    """When the probe returns True, the function must return True."""
    mod_path = _module_at(tmp_path)
    result = bespoke_ac_handler_with_demotion(
        probe=_probe_returns_true(),
        module_path=mod_path,
        workspace=tmp_path,
    )
    assert result is True


def test_probe_true_no_warning(tmp_path, caplog):
    """A passing probe must NOT emit any F-R7-584 warning."""
    mod_path = _module_at(tmp_path)
    with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
        bespoke_ac_handler_with_demotion(
            probe=_probe_returns_true(),
            module_path=mod_path,
            workspace=tmp_path,
        )
    assert not any("F-R7-584" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Tests — probe fails, module EXISTS (demote-on-failure)
# ---------------------------------------------------------------------------


def test_probe_false_module_exists_returns_true(tmp_path):
    """probe() → False + module exists → must return True (demote)."""
    mod_path = _module_at(tmp_path)
    result = bespoke_ac_handler_with_demotion(
        probe=_probe_returns_false(),
        module_path=mod_path,
        workspace=tmp_path,
    )
    assert result is True


def test_probe_false_module_exists_emits_warning(tmp_path, caplog):
    """probe() → False + module exists → must emit an F-R7-584 warning."""
    mod_path = _module_at(tmp_path)
    with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
        bespoke_ac_handler_with_demotion(
            probe=_probe_returns_false(),
            module_path=mod_path,
            workspace=tmp_path,
        )
    assert any("F-R7-584" in r.message for r in caplog.records), (
        "Expected an F-R7-584 warning when probe fails but module exists"
    )


def test_probe_raises_module_exists_returns_true(tmp_path):
    """probe() raises + module exists → must return True (demote)."""
    mod_path = _module_at(tmp_path)
    result = bespoke_ac_handler_with_demotion(
        probe=_probe_raises(),
        module_path=mod_path,
        workspace=tmp_path,
    )
    assert result is True


def test_probe_raises_module_exists_emits_warning(tmp_path, caplog):
    """probe() raises + module exists → must emit an F-R7-584 warning."""
    mod_path = _module_at(tmp_path)
    with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
        bespoke_ac_handler_with_demotion(
            probe=_probe_raises(),
            module_path=mod_path,
            workspace=tmp_path,
        )
    assert any("F-R7-584" in r.message for r in caplog.records), (
        "Expected an F-R7-584 warning when probe raises but module exists"
    )


# ---------------------------------------------------------------------------
# Tests — probe fails, module ABSENT (hard-fail, fall through to F-R7-582)
# ---------------------------------------------------------------------------


def test_probe_false_module_absent_returns_false(tmp_path):
    """probe() → False + module does NOT exist → must return False."""
    absent_path = tmp_path / "src" / "nonexistent" / "missing.py"
    result = bespoke_ac_handler_with_demotion(
        probe=_probe_returns_false(),
        module_path=absent_path,
        workspace=tmp_path,
    )
    assert result is False


def test_probe_raises_module_absent_returns_false(tmp_path):
    """probe() raises + module does NOT exist → must return False."""
    absent_path = tmp_path / "src" / "nonexistent" / "missing.py"
    result = bespoke_ac_handler_with_demotion(
        probe=_probe_raises(),
        module_path=absent_path,
        workspace=tmp_path,
    )
    assert result is False


def test_probe_false_module_absent_no_warning(tmp_path, caplog):
    """When the module is absent, no F-R7-584 warning should be emitted
    — the absence is a real gap, not an impl-gap-in-existing-module."""
    absent_path = tmp_path / "src" / "nonexistent" / "missing.py"
    with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
        bespoke_ac_handler_with_demotion(
            probe=_probe_returns_false(),
            module_path=absent_path,
            workspace=tmp_path,
        )
    assert not any("F-R7-584" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Tests — edge cases
# ---------------------------------------------------------------------------


def test_accepts_pathlib_path(tmp_path):
    """module_path must accept a pathlib.Path object."""
    mod_path = _module_at(tmp_path)
    # Should not raise regardless of result
    result = bespoke_ac_handler_with_demotion(
        probe=_probe_returns_true(),
        module_path=mod_path,
        workspace=tmp_path,
    )
    assert isinstance(result, bool)


def test_workspace_param_accepted(tmp_path):
    """workspace parameter must be accepted without error."""
    mod_path = _module_at(tmp_path)
    result = bespoke_ac_handler_with_demotion(
        probe=_probe_returns_true(),
        module_path=mod_path,
        workspace=tmp_path,
    )
    assert result is True


def test_returns_bool_not_truthy(tmp_path):
    """Return value must be exactly True or False, not just truthy/falsy."""
    mod_path = _module_at(tmp_path)
    result_pass = bespoke_ac_handler_with_demotion(
        probe=_probe_returns_true(),
        module_path=mod_path,
        workspace=tmp_path,
    )
    result_fail = bespoke_ac_handler_with_demotion(
        probe=_probe_returns_false(),
        module_path=tmp_path / "nonexistent.py",
        workspace=tmp_path,
    )
    assert result_pass is True
    assert result_fail is False
