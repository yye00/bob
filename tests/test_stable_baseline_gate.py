"""Tests for bob.stable_baseline_gate.enforce_stable_baseline_gate.

Acceptance criteria:
  - File exists: src/bob/stable_baseline_gate.py
  - Function defined: bob.stable_baseline_gate.enforce_stable_baseline_gate
  - pytest: tests/test_stable_baseline_gate.py
  - integration: bob.verifier
"""
from __future__ import annotations

import pathlib
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bob.stable_baseline_gate import (
    BaselineUnstableError,
    CollectionResult,
    enforce_stable_baseline_gate,
)


def _fake_proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# Core behaviour: enforce_stable_baseline_gate exists and is callable
# ---------------------------------------------------------------------------

def test_enforce_stable_baseline_gate_is_callable():
    """enforce_stable_baseline_gate must be a callable."""
    assert callable(enforce_stable_baseline_gate)


def test_enforce_stable_baseline_gate_none_workspace_returns_ok():
    """None workspace → ok=True without running pytest."""
    result = enforce_stable_baseline_gate(None)
    assert isinstance(result, CollectionResult)
    assert result.ok


def test_enforce_stable_baseline_gate_nonexistent_workspace_returns_ok(tmp_path):
    """Nonexistent workspace → ok=True (nothing to fail)."""
    ghost = tmp_path / "does_not_exist"
    result = enforce_stable_baseline_gate(ghost)
    assert isinstance(result, CollectionResult)
    assert result.ok


def test_enforce_stable_baseline_gate_missing_test_dir_returns_ok(tmp_path):
    """Missing test directory → ok=True (well-defined boundary)."""
    result = enforce_stable_baseline_gate(tmp_path, test_dir="tests")
    assert isinstance(result, CollectionResult)
    assert result.ok


# ---------------------------------------------------------------------------
# Collection failure → BaselineUnstableError raised
# ---------------------------------------------------------------------------

def test_enforce_raises_baseline_unstable_error_on_collection_failure(tmp_path):
    """Collection failure causes enforce_stable_baseline_gate to raise BaselineUnstableError."""
    (tmp_path / "tests").mkdir()
    collect_error_output = (
        "ERROR collecting tests/test_broken.py\n"
        "ImportError: No module named 'hypothesis'\n"
    )
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=collect_error_output)):
        with pytest.raises(BaselineUnstableError) as exc_info:
            enforce_stable_baseline_gate(tmp_path, test_dir="tests")

    assert "collect" in str(exc_info.value).lower()


def test_enforce_raises_on_import_error_in_test_file(tmp_path):
    """ImportError in a test file triggers BaselineUnstableError."""
    (tmp_path / "tests").mkdir()
    output = "ERROR collecting tests/test_import_fail.py\nImportError: cannot import name 'X'\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=output)):
        with pytest.raises(BaselineUnstableError):
            enforce_stable_baseline_gate(tmp_path, test_dir="tests")


def test_enforce_error_message_includes_failing_file(tmp_path):
    """BaselineUnstableError message must mention the failing file."""
    (tmp_path / "tests").mkdir()
    output = "ERROR collecting tests/test_oops.py\nImportError: bad import\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=output)):
        with pytest.raises(BaselineUnstableError) as exc_info:
            enforce_stable_baseline_gate(tmp_path, test_dir="tests")

    assert "test_oops" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Clean collection → returns CollectionResult with ok=True
# ---------------------------------------------------------------------------

def test_enforce_returns_ok_when_collection_clean(tmp_path):
    """Clean collection → CollectionResult with ok=True."""
    (tmp_path / "tests").mkdir()
    clean_output = "<Module tests/test_ok.py>\n  <Function test_foo>\n"
    with patch("subprocess.run", return_value=_fake_proc(0, stdout=clean_output)):
        result = enforce_stable_baseline_gate(tmp_path, test_dir="tests")

    assert isinstance(result, CollectionResult)
    assert result.ok


def test_enforce_returns_collection_result_type(tmp_path):
    """Return type is always CollectionResult when not raising."""
    (tmp_path / "tests").mkdir()
    with patch("subprocess.run", return_value=_fake_proc(0, stdout="")):
        result = enforce_stable_baseline_gate(tmp_path, test_dir="tests")
    assert isinstance(result, CollectionResult)


# ---------------------------------------------------------------------------
# Invalid inputs → ValueError
# ---------------------------------------------------------------------------

def test_enforce_raises_value_error_for_invalid_workspace_type():
    """Invalid workspace type raises ValueError."""
    with pytest.raises(ValueError):
        enforce_stable_baseline_gate(42)


def test_enforce_raises_value_error_for_zero_timeout():
    """Zero timeout raises ValueError."""
    with pytest.raises(ValueError, match="timeout"):
        enforce_stable_baseline_gate(None, timeout=0)


def test_enforce_raises_value_error_for_negative_timeout():
    """Negative timeout raises ValueError."""
    with pytest.raises(ValueError, match="timeout"):
        enforce_stable_baseline_gate(None, timeout=-5)


# ---------------------------------------------------------------------------
# Integration: bob.verifier exposes the gate
# ---------------------------------------------------------------------------

def test_bob_verifier_exposes_baseline_unstable_error():
    """bob.verifier must re-export BaselineUnstableError."""
    from bob import verifier
    assert hasattr(verifier, "BaselineUnstableError")


def test_bob_verifier_exposes_abort_on_collection_failure():
    """bob.verifier must re-export abort_on_collection_failure."""
    from bob import verifier
    assert hasattr(verifier, "abort_on_collection_failure")


def test_bob_verifier_exposes_should_abort_on_collection_failure():
    """bob.verifier must re-export should_abort_on_collection_failure."""
    from bob import verifier
    assert hasattr(verifier, "should_abort_on_collection_failure")


def test_enforce_stable_baseline_gate_importable_from_stable_baseline_gate():
    """enforce_stable_baseline_gate must be importable from bob.stable_baseline_gate."""
    from bob.stable_baseline_gate import enforce_stable_baseline_gate as fn
    assert callable(fn)


# ---------------------------------------------------------------------------
# Integration via bob.verifier — gate is callable from verifier namespace
# ---------------------------------------------------------------------------

def test_abort_on_collection_failure_via_verifier_raises_on_failure(tmp_path):
    """abort_on_collection_failure via bob.verifier raises BaselineUnstableError."""
    from bob.verifier import abort_on_collection_failure, BaselineUnstableError as BUE

    (tmp_path / "tests").mkdir()
    output = "ERROR collecting tests/test_bad.py\nImportError: boom\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=output)):
        with pytest.raises(BUE):
            abort_on_collection_failure(tmp_path, test_dir="tests")


def test_should_abort_on_collection_failure_via_verifier_returns_true(tmp_path):
    """should_abort_on_collection_failure returns True when collection fails."""
    from bob.verifier import should_abort_on_collection_failure

    (tmp_path / "tests").mkdir()
    output = "ERROR collecting tests/test_bad.py\nImportError: boom\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=output)):
        assert should_abort_on_collection_failure(tmp_path, test_dir="tests") is True


def test_should_abort_returns_false_when_collection_clean(tmp_path):
    """should_abort_on_collection_failure returns False when collection is clean."""
    from bob.verifier import should_abort_on_collection_failure

    (tmp_path / "tests").mkdir()
    with patch("subprocess.run", return_value=_fake_proc(0, stdout="")):
        assert should_abort_on_collection_failure(tmp_path, test_dir="tests") is False
