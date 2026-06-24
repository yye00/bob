"""Tests for bob.verifier.baseline_gate.abort_on_collection_failure.

Acceptance criteria:
  - File exists: src/bob/verifier/baseline_gate.py
  - Function defined: bob.verifier.baseline_gate.abort_on_collection_failure
  - pytest: tests/verifier/test_baseline_gate.py
  - integration: bob.verifier.orchestrator
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bob.verifier.baseline_gate import (
    BaselineUnstableError,
    CollectionResult,
    abort_on_collection_failure,
)


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
# Module-level: function and class are importable
# ---------------------------------------------------------------------------


def test_abort_on_collection_failure_is_callable():
    assert callable(abort_on_collection_failure)


def test_baseline_unstable_error_is_exception_subclass():
    assert issubclass(BaselineUnstableError, Exception)


def test_collection_result_is_importable():
    assert CollectionResult is not None


# ---------------------------------------------------------------------------
# None workspace (no-op)
# ---------------------------------------------------------------------------


def test_none_workspace_returns_ok():
    result = abort_on_collection_failure(None)
    assert isinstance(result, CollectionResult)
    assert result.ok


def test_none_workspace_does_not_raise():
    abort_on_collection_failure(None)


# ---------------------------------------------------------------------------
# Clean collection → ok=True, no error raised
# ---------------------------------------------------------------------------


def test_clean_collection_returns_result(tmp_path):
    (tmp_path / "tests").mkdir()
    clean_output = "<Module tests/test_ok.py>\n  <Function test_foo>\n"
    with patch("subprocess.run", return_value=_fake_proc(0, stdout=clean_output)):
        result = abort_on_collection_failure(tmp_path)
    assert isinstance(result, CollectionResult)
    assert result.ok


def test_clean_collection_does_not_raise(tmp_path):
    (tmp_path / "tests").mkdir()
    clean_output = "<Module tests/test_ok.py>\n"
    with patch("subprocess.run", return_value=_fake_proc(0, stdout=clean_output)):
        abort_on_collection_failure(tmp_path)  # must not raise


# ---------------------------------------------------------------------------
# Collection failure → BaselineUnstableError raised
# ---------------------------------------------------------------------------


def test_collection_failure_raises_baseline_unstable_error(tmp_path):
    (tmp_path / "tests").mkdir()
    error_output = (
        "ERROR collecting tests/test_broken.py\n"
        "ImportError: No module named 'hypothesis'\n"
    )
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=error_output)):
        with pytest.raises(BaselineUnstableError):
            abort_on_collection_failure(tmp_path)


def test_collection_failure_message_contains_collect(tmp_path):
    (tmp_path / "tests").mkdir()
    error_output = "ERROR collecting tests/test_broken.py\nImportError: oops\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=error_output)):
        with pytest.raises(BaselineUnstableError, match="collect"):
            abort_on_collection_failure(tmp_path)


def test_collection_failure_message_contains_failing_file(tmp_path):
    (tmp_path / "tests").mkdir()
    error_output = "ERROR collecting tests/test_bad_import.py\nImportError: oops\n"
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=error_output)):
        with pytest.raises(BaselineUnstableError, match="test_bad_import.py"):
            abort_on_collection_failure(tmp_path)


def test_multiple_failing_files_in_error_message(tmp_path):
    (tmp_path / "tests").mkdir()
    error_output = (
        "ERROR collecting tests/test_a.py\n"
        "ERROR collecting tests/test_b.py\n"
    )
    with patch("subprocess.run", return_value=_fake_proc(2, stdout=error_output)):
        with pytest.raises(BaselineUnstableError) as exc_info:
            abort_on_collection_failure(tmp_path)
    msg = str(exc_info.value)
    assert "test_a.py" in msg or "test_b.py" in msg


# ---------------------------------------------------------------------------
# Integration: bob.verifier re-exports abort_on_collection_failure
# ---------------------------------------------------------------------------


def test_verifier_package_exports_abort_on_collection_failure():
    import bob.verifier as v
    assert hasattr(v, "abort_on_collection_failure")
    assert v.abort_on_collection_failure is abort_on_collection_failure


def test_verifier_package_exports_baseline_unstable_error():
    import bob.verifier as v
    assert hasattr(v, "BaselineUnstableError")
    assert v.BaselineUnstableError is BaselineUnstableError


# ---------------------------------------------------------------------------
# Integration: bob.verifier.orchestrator exposes abort_on_collection_failure
# ---------------------------------------------------------------------------


def test_orchestrator_exposes_abort_on_collection_failure():
    import bob.orchestrator as o
    assert hasattr(o, "abort_on_collection_failure")
    assert callable(o.abort_on_collection_failure)


# ---------------------------------------------------------------------------
# ValueError propagation — invalid inputs still raise
# ---------------------------------------------------------------------------


def test_invalid_workspace_type_raises_value_error():
    with pytest.raises(ValueError):
        abort_on_collection_failure(42)


def test_invalid_timeout_raises_value_error():
    with pytest.raises(ValueError):
        abort_on_collection_failure(None, timeout=0)


def test_negative_timeout_raises_value_error():
    with pytest.raises(ValueError):
        abort_on_collection_failure(None, timeout=-5)
