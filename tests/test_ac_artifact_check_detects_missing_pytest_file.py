"""AC artifact-existence verifier — detects missing pytest file."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bob.verification.ac_artifact_check import (
    ArtifactMiss,
    check_pytest_ac,
    verify_ac_artifacts,
)

NONEXISTENT_PATH = "tests/nonexistent_test_file.py"
AC_TEXT = f"pytest: {NONEXISTENT_PATH}"


def test_check_pytest_ac_returns_false_for_missing_file():
    """check_pytest_ac must return False when the path does not exist."""
    result = check_pytest_ac(NONEXISTENT_PATH, workspace="/tmp")
    assert result is False


def test_verify_ac_artifacts_returns_nonempty_list_for_missing_pytest_file():
    """verify_ac_artifacts must return a non-empty list for a missing pytest file."""
    misses = verify_ac_artifacts([AC_TEXT], workspace="/tmp")
    assert len(misses) >= 1, f"Expected at least 1 miss, got {len(misses)}"


def test_verify_ac_artifacts_miss_kind_is_pytest():
    """The ArtifactMiss kind must be 'pytest' for a pytest: AC."""
    misses = verify_ac_artifacts([AC_TEXT], workspace="/tmp")
    assert misses[0].kind == "pytest", f"Expected kind='pytest', got {misses[0].kind!r}"


def test_verify_ac_artifacts_reason_contains_artifact_missing():
    """The ArtifactMiss reason must contain 'ARTIFACT_MISSING'."""
    misses = verify_ac_artifacts([AC_TEXT], workspace="/tmp")
    assert "ARTIFACT_MISSING" in misses[0].reason, (
        f"reason must contain 'ARTIFACT_MISSING', got: {misses[0].reason!r}"
    )


def test_verify_ac_artifacts_miss_expected_path_matches_nonexistent_file():
    """The ArtifactMiss expected_path must reference the missing file path."""
    misses = verify_ac_artifacts([AC_TEXT], workspace="/tmp")
    assert NONEXISTENT_PATH in misses[0].expected_path, (
        f"expected_path must contain {NONEXISTENT_PATH!r}, got: {misses[0].expected_path!r}"
    )


def test_verify_ac_artifacts_miss_is_artifact_miss_instance():
    """Each entry in the returned list must be an ArtifactMiss dataclass instance."""
    misses = verify_ac_artifacts([AC_TEXT], workspace="/tmp")
    assert isinstance(misses[0], ArtifactMiss), (
        f"Expected ArtifactMiss instance, got {type(misses[0])}"
    )
