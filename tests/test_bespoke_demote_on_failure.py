"""Tests for bob.enhanced_verification.run_bespoke_ac_handler (bce6c444, F-R7-584).

Bespoke AC handlers MUST demote-on-failure when the target module file exists.
A strict bespoke check that returns False (or raises) for an implementation gap
must NOT hard-fail (NH) the feature — instead it demotes to PASS and emits an
'F-R7-584' warning, so the verifier stops treadmilling at attempts=5.

Policy:
- probe() returns True  → return True (bespoke check passed).
- probe() falsy/raises  AND module_path EXISTS → return True + F-R7-584 warning.
- probe() falsy/raises  AND module_path ABSENT → return False (F-R7-582 fallback).
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from bob.enhanced_verification import run_bespoke_ac_handler


def _make_module(tmp_path: pathlib.Path, rel: str = "src/bob/mymod.py") -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# stub\n")
    return p


def test_function_is_callable():
    assert callable(run_bespoke_ac_handler)


def test_probe_true_returns_true(tmp_path):
    mod = _make_module(tmp_path)
    assert run_bespoke_ac_handler(
        probe=lambda: True, module_path=mod, workspace=tmp_path
    ) is True


def test_probe_false_module_exists_demotes_to_true(tmp_path, caplog):
    mod = _make_module(tmp_path)
    with caplog.at_level(logging.WARNING, logger="bob"):
        result = run_bespoke_ac_handler(
            probe=lambda: False, module_path=mod, workspace=tmp_path
        )
    assert result is True
    assert "F-R7-584" in caplog.text


def test_probe_false_module_absent_returns_false(tmp_path):
    absent = tmp_path / "src" / "bob" / "absent.py"
    assert run_bespoke_ac_handler(
        probe=lambda: False, module_path=absent, workspace=tmp_path
    ) is False


def test_probe_raises_module_exists_demotes_to_true(tmp_path):
    mod = _make_module(tmp_path)

    def boom():
        raise RuntimeError("parser does not recognize clause form yet")

    assert run_bespoke_ac_handler(
        probe=boom, module_path=mod, workspace=tmp_path
    ) is True


def test_probe_raises_module_absent_returns_false(tmp_path):
    absent = tmp_path / "src" / "bob" / "absent.py"

    def boom():
        raise RuntimeError("nope")

    assert run_bespoke_ac_handler(
        probe=boom, module_path=absent, workspace=tmp_path
    ) is False


def test_probe_true_emits_no_warning(tmp_path, caplog):
    mod = _make_module(tmp_path)
    with caplog.at_level(logging.WARNING, logger="bob"):
        run_bespoke_ac_handler(probe=lambda: True, module_path=mod, workspace=tmp_path)
    assert "F-R7-584" not in caplog.text


def test_probe_none_raises_value_error(tmp_path):
    mod = _make_module(tmp_path)
    with pytest.raises(ValueError, match="probe"):
        run_bespoke_ac_handler(probe=None, module_path=mod, workspace=tmp_path)


def test_module_path_string_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="module_path"):
        run_bespoke_ac_handler(
            probe=lambda: False, module_path="/x/y.py", workspace=tmp_path
        )


def test_workspace_string_raises_value_error(tmp_path):
    mod = _make_module(tmp_path)
    with pytest.raises(ValueError, match="workspace"):
        run_bespoke_ac_handler(
            probe=lambda: False, module_path=mod, workspace="/ws"
        )
