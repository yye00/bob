"""Tests for bob.baseline_gate.validate_collection.

Acceptance criteria:
  - File exists: src/bob/baseline_gate.py
  - Function defined: bob.baseline_gate.validate_collection
  - pytest: tests/test_baseline_gate.py
  - integration: bob.verifier
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bob_legacy.baseline_gate import CollectionResult, validate_collection
from bob.verifier import validate_collection as vc_from_verifier, CollectionResult as CR_from_verifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# Integration: bob.verifier exposes validate_collection
# ---------------------------------------------------------------------------

def test_verifier_integration_exposes_validate_collection():
    """bob.verifier re-exports validate_collection from bob_legacy.baseline_gate."""
    assert vc_from_verifier is validate_collection
    assert CR_from_verifier is CollectionResult


# ---------------------------------------------------------------------------
# Core behaviour: collection failure → ok=False
# ---------------------------------------------------------------------------

def test_collection_failure_detected(tmp_path):
    (tmp_path / "tests").mkdir()
    error_output = (
        "ERROR collecting tests/test_broken.py\n"
        "ImportError: No module named 'hypothesis'\n"
    )
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=error_output)):
        result = validate_collection(tmp_path, test_dir="tests")

    assert not result.ok
    assert "tests/test_broken.py" in result.failing_files


def test_collection_failure_returns_collection_result_type(tmp_path):
    (tmp_path / "tests").mkdir()
    error_output = "ERROR collecting tests/test_foo.py\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=error_output)):
        result = validate_collection(tmp_path, test_dir="tests")

    assert isinstance(result, CollectionResult)
    assert not result.ok


def test_clean_collection_returns_ok(tmp_path):
    (tmp_path / "tests").mkdir()
    clean_output = "<Module tests/test_ok.py>\n  <Function test_foo>\n"
    with patch("subprocess.run", return_value=_fake_proc(0, stdout=clean_output)):
        result = validate_collection(tmp_path, test_dir="tests")

    assert result.ok
    assert result.failing_files == []


def test_exit_code_2_without_error_line_still_unstable(tmp_path):
    """Exit code 2 + 'ERROR' in output → collection failure even without named file."""
    (tmp_path / "tests").mkdir()
    output = "ERROR\nsome problem\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=output)):
        result = validate_collection(tmp_path, test_dir="tests")

    assert not result.ok


def test_exit_code_1_not_treated_as_collection_error(tmp_path):
    """Exit code 1 (test failures, not collection errors) → ok=True."""
    (tmp_path / "tests").mkdir()
    output = "FAILED tests/test_foo.py::test_bar\n"
    with patch("subprocess.run", return_value=_fake_proc(1, stdout=output)):
        result = validate_collection(tmp_path, test_dir="tests")

    assert result.ok


# ---------------------------------------------------------------------------
# Result object attributes
# ---------------------------------------------------------------------------

def test_result_has_details_on_failure(tmp_path):
    (tmp_path / "tests").mkdir()
    error_output = "ERROR collecting tests/test_x.py\nImportError: oops\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=error_output)):
        result = validate_collection(tmp_path, test_dir="tests")

    assert not result.ok
    assert "ImportError" in result.details


def test_multiple_failing_files_collected(tmp_path):
    (tmp_path / "tests").mkdir()
    error_output = (
        "ERROR collecting tests/test_a.py\n"
        "ERROR collecting tests/test_b.py\n"
    )
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=error_output)):
        result = validate_collection(tmp_path, test_dir="tests")

    assert not result.ok
    assert "tests/test_a.py" in result.failing_files
    assert "tests/test_b.py" in result.failing_files
