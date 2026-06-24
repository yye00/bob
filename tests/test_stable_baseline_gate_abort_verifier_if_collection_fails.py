"""Tests for stable_baseline_gate_abort_verifier_if_collection_fails.

Acceptance criteria:
  - File exists: src/bob/stable_baseline_gate_abort_verifier_if_collection_fails.py
  - pytest: tests/test_stable_baseline_gate_abort_verifier_if_collection_fails.py::test_stable_baseline_gate_abort_verifier_if_collection_fails
  - Function defined: bob.stable_baseline_gate_abort_verifier_if_collection_fails.stable_baseline_gate_abort_verifier_if_collection_fails
"""
from __future__ import annotations

import pathlib
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bob.stable_baseline_gate_abort_verifier_if_collection_fails import (
    stable_baseline_gate_abort_verifier_if_collection_fails,
)


def _fake_proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_stable_baseline_gate_abort_verifier_if_collection_fails(tmp_path):
    """Primary AC test — covers the gate's core behaviours end-to-end."""

    # 1. Collection failure → status baseline_unstable, snapshot is None
    (tmp_path / "tests").mkdir()
    collect_error_output = (
        "ERROR collecting tests/test_broken.py\n"
        "ImportError: No module named 'hypothesis'\n"
    )
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=collect_error_output)):
        result = stable_baseline_gate_abort_verifier_if_collection_fails(
            workspace=tmp_path,
            test_dir="tests",
        )
    assert result["status"] == "baseline_unstable"
    assert result["snapshot"] is None
    assert result["aborted"] is True

    # 2. Clean collection → status ok, aborted=False
    clean_output = "<Module tests/test_ok.py>\n  <Function test_foo>\n"
    fake_snapshot = {"tests/test_ok.py::test_foo": True}
    with (
        patch("subprocess.run", return_value=_fake_proc(0, stdout=clean_output)),
        patch(
            "bob.verifier.baseline_capture._capture_snapshot",
            return_value=fake_snapshot,
        ),
    ):
        result = stable_baseline_gate_abort_verifier_if_collection_fails(
            workspace=tmp_path,
            test_dir="tests",
        )
    assert result["status"] == "ok"
    assert result["aborted"] is False

    # 3. Missing workspace → graceful ok (no crash)
    result = stable_baseline_gate_abort_verifier_if_collection_fails(
        workspace=tmp_path / "nonexistent",
        test_dir="tests",
    )
    assert result["status"] == "ok"
    assert result["aborted"] is False

    # 4. Failing file is named in the result on collection error
    (tmp_path / "tests2").mkdir()
    collect_error_output2 = (
        "ERROR collecting tests2/test_import_error.py\n"
        "ImportError: cannot import name 'X'\n"
    )
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=collect_error_output2)):
        result = stable_baseline_gate_abort_verifier_if_collection_fails(
            workspace=tmp_path,
            test_dir="tests2",
        )
    assert result["status"] == "baseline_unstable"
    assert "test_import_error" in (result.get("failing_file") or "")
