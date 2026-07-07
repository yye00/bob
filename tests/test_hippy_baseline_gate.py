"""Tests for hippy.baseline_gate — stable baseline gate.

Acceptance criteria:
  - File exists: src/hippy/baseline_gate.py
  - Function defined: hippy.baseline_gate.capture_baseline
  - Function defined: hippy.baseline_gate.collects_cleanly
  - integration: hippy.verifier
"""

from __future__ import annotations

import pathlib
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from hippy.baseline_gate import (
    BaselineResult,
    BaselineUnstableError,
    capture_baseline,
    collects_cleanly,
)


def _fake_proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# collects_cleanly — boolean predicate
# ---------------------------------------------------------------------------

def test_collects_cleanly_true_on_clean(tmp_path):
    (tmp_path / "tests").mkdir()
    with patch("subprocess.run", return_value=_fake_proc(0, stdout="<Module x>")):
        assert collects_cleanly(tmp_path, test_dir="tests") is True


def test_collects_cleanly_false_on_collect_error(tmp_path):
    (tmp_path / "tests").mkdir()
    err = "ERROR collecting tests/test_broken.py\nImportError: nope\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=err)):
        assert collects_cleanly(tmp_path, test_dir="tests") is False


def test_collects_cleanly_none_workspace_true():
    assert collects_cleanly(None) is True


def test_collects_cleanly_returns_plain_bool(tmp_path):
    (tmp_path / "tests").mkdir()
    with patch("subprocess.run", return_value=_fake_proc(0, stdout="")):
        assert type(collects_cleanly(tmp_path, test_dir="tests")) is bool


def test_collects_cleanly_exit1_is_clean(tmp_path):
    """Exit code 1 = test failures, not a collection error."""
    (tmp_path / "tests").mkdir()
    out = "FAILED tests/test_foo.py::test_bar\n"
    with patch("subprocess.run", return_value=_fake_proc(1, stdout=out)):
        assert collects_cleanly(tmp_path, test_dir="tests") is True


# ---------------------------------------------------------------------------
# capture_baseline — refuses to snapshot an unstable baseline
# ---------------------------------------------------------------------------

def test_capture_baseline_clean_returns_snapshot(tmp_path):
    (tmp_path / "tests").mkdir()
    snap = {"tests/test_ok.py::test_foo": "passed"}
    with patch("subprocess.run", return_value=_fake_proc(0, stdout="<Module x>")):
        result = capture_baseline(
            tmp_path, test_dir="tests", capture_fn=lambda ws: snap
        )
    assert isinstance(result, BaselineResult)
    assert result.stable is True
    assert result.snapshot == snap
    assert result.failing_files == []


def test_capture_baseline_unstable_aborts(tmp_path):
    (tmp_path / "tests").mkdir()
    err = "ERROR collecting tests/test_broken.py\nImportError: nope\n"
    called = {"n": 0}

    def _cap(ws):
        called["n"] += 1
        return {"x": "passed"}

    with patch("subprocess.run", return_value=_fake_proc(2, stdout=err)):
        result = capture_baseline(tmp_path, test_dir="tests", capture_fn=_cap)

    assert result.stable is False
    assert result.snapshot is None
    assert "tests/test_broken.py" in result.failing_files
    assert called["n"] == 0, "capture_fn must NOT run on an unstable baseline"


def test_capture_baseline_none_workspace_stable():
    result = capture_baseline(None, capture_fn=lambda ws: {})
    assert result.stable is True
    assert result.snapshot == {}


def test_capture_baseline_default_capture_fn_returns_empty(tmp_path):
    (tmp_path / "tests").mkdir()
    with patch("subprocess.run", return_value=_fake_proc(0, stdout="<Module x>")):
        result = capture_baseline(tmp_path, test_dir="tests")
    assert result.stable is True
    assert result.snapshot == {}


def test_capture_baseline_raise_on_unstable_flag(tmp_path):
    (tmp_path / "tests").mkdir()
    err = "ERROR collecting tests/test_broken.py\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=err)):
        with pytest.raises(BaselineUnstableError, match="test_broken.py"):
            capture_baseline(
                tmp_path, test_dir="tests", raise_on_unstable=True
            )


# ---------------------------------------------------------------------------
# integration: hippy.verifier
# ---------------------------------------------------------------------------

def test_verifier_exposes_baseline_gate():
    from hippy import verifier

    assert verifier.collects_cleanly is collects_cleanly
    assert verifier.capture_baseline is capture_baseline
