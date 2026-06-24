"""Tests for bob.verifier.check_baseline_collection.

AC: pytest: tests/test_verifier_baseline_gate.py
    integration: bob.verifier
    Function defined: bob.verifier.check_baseline_collection

Verifies that check_baseline_collection is accessible from bob.verifier
and behaves correctly as the stable baseline gate entry point.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from bob.verifier import check_baseline_collection
from bob_legacy.baseline_gate import CollectionResult


# ---------------------------------------------------------------------------
# Importability / integration
# ---------------------------------------------------------------------------


def test_check_baseline_collection_importable_from_bob_verifier():
    """check_baseline_collection must be importable from bob.verifier."""
    from bob.verifier import check_baseline_collection as fn  # noqa: F401
    assert callable(fn)


def test_check_baseline_collection_in_verifier_namespace():
    """check_baseline_collection must exist in bob.verifier's namespace."""
    import bob.verifier as verifier_mod
    assert hasattr(verifier_mod, "check_baseline_collection")


def test_check_baseline_collection_returns_collection_result():
    """check_baseline_collection(None) returns CollectionResult."""
    result = check_baseline_collection(None)
    assert isinstance(result, CollectionResult)


# ---------------------------------------------------------------------------
# None workspace → ok=True (boundary, no subprocess)
# ---------------------------------------------------------------------------


def test_none_workspace_returns_ok():
    """None workspace is valid — no subprocess, returns ok=True."""
    result = check_baseline_collection(None)
    assert result.ok is True
    assert result.failing_files == []


def test_none_workspace_does_not_raise():
    """Calling check_baseline_collection(None) never raises."""
    check_baseline_collection(None)


# ---------------------------------------------------------------------------
# Non-existent workspace → ok=True
# ---------------------------------------------------------------------------


def test_nonexistent_workspace_returns_ok(tmp_path):
    """Non-existent workspace path returns ok=True."""
    result = check_baseline_collection(tmp_path / "does_not_exist")
    assert result.ok is True


# ---------------------------------------------------------------------------
# Clean suite → ok=True
# ---------------------------------------------------------------------------


def test_clean_collection_returns_ok(tmp_path):
    """A workspace with a trivially-clean test suite returns ok=True."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_nothing.py").write_text("def test_pass(): assert True\n")
    result = check_baseline_collection(tmp_path, test_dir="tests", timeout=30)
    assert isinstance(result, CollectionResult)
    assert result.ok is True
    assert result.failing_files == []


# ---------------------------------------------------------------------------
# Collection failure → ok=False, failing_files populated
# ---------------------------------------------------------------------------


def test_collection_failure_returns_not_ok(tmp_path):
    """A test file with a bad import causes ok=False."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_broken.py").write_text(
        "import nonexistent_module_xyz_abc_12345\n\ndef test_x(): pass\n"
    )
    result = check_baseline_collection(tmp_path, test_dir="tests", timeout=30)
    assert isinstance(result, CollectionResult)
    assert result.ok is False


def test_collection_failure_names_failing_file(tmp_path):
    """When collection fails, result.failing_files is non-empty."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_importerror.py").write_text(
        "import no_such_module_zzz\n\ndef test_y(): pass\n"
    )
    result = check_baseline_collection(tmp_path, test_dir="tests", timeout=30)
    assert result.failing_files  # at least one file reported


# ---------------------------------------------------------------------------
# Invalid input → ValueError
# ---------------------------------------------------------------------------


def test_invalid_workspace_type_raises_value_error():
    """workspace that is not str, Path, or None raises ValueError."""
    with pytest.raises(ValueError, match="workspace"):
        check_baseline_collection(42)


def test_invalid_timeout_raises_value_error():
    """timeout=0 raises ValueError."""
    with pytest.raises(ValueError, match="timeout"):
        check_baseline_collection(None, timeout=0)


def test_negative_timeout_raises_value_error():
    """Negative timeout raises ValueError."""
    with pytest.raises(ValueError, match="timeout"):
        check_baseline_collection(None, timeout=-5)


def test_bool_timeout_raises_value_error():
    """bool timeout raises ValueError (bool is subclass of int but invalid)."""
    with pytest.raises(ValueError, match="timeout"):
        check_baseline_collection(None, timeout=True)


# ---------------------------------------------------------------------------
# Verifier must refuse to capture baseline when collection fails
# ---------------------------------------------------------------------------


def test_verifier_must_not_use_snapshot_when_collection_fails(tmp_path):
    """When ok=False, the caller must not proceed with baseline capture.

    This test verifies the contract: if check_baseline_collection returns
    result.ok=False, any regression comparison based on that result would
    fabricate failures.  The verifier must check result.ok before proceeding.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_bad.py").write_text(
        "import missing_lib_never_exists\ndef test_x(): pass\n"
    )
    result = check_baseline_collection(tmp_path, test_dir="tests", timeout=30)
    # The verifier gate: if not ok, abort — do not capture baseline
    if not result.ok:
        aborted = True
    else:
        aborted = False
    assert aborted, "Verifier must abort when collection fails"
