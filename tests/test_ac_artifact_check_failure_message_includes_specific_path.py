"""AC artifact-existence verifier — failure message includes the specific missing path."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from bob3.verification.ac_artifact_check import (
    verify_ac_artifacts,
    fail_feature_with_explicit_reason,
    ArtifactMiss,
    ArtifactMissingError,
)
from pathlib import Path

_WORKSPACE = Path(__file__).resolve().parent.parent


def test_fail_feature_raises_artifact_missing_error_not_generic():
    """fail_feature_with_explicit_reason raises ArtifactMissingError (not RuntimeError or Exception)."""
    miss = ArtifactMiss(
        ac_text="File exists: src/missing/deep/module.py",
        expected_path="src/missing/deep/module.py",
        kind="file_exists",
        reason="ARTIFACT_MISSING:src/missing/deep/module.py",
    )
    with pytest.raises(ArtifactMissingError) as exc_info:
        fail_feature_with_explicit_reason([miss])
    assert exc_info.type is ArtifactMissingError, (
        f"Must raise ArtifactMissingError specifically, got {exc_info.type}"
    )


def test_fail_feature_error_message_contains_specific_missing_path():
    """The ArtifactMissingError message includes the exact path, not a generic placeholder."""
    specific_path = "src/some/very/specific/path.py"
    miss = ArtifactMiss(
        ac_text=f"File exists: {specific_path}",
        expected_path=specific_path,
        kind="file_exists",
        reason=f"ARTIFACT_MISSING:{specific_path}",
    )
    with pytest.raises(ArtifactMissingError) as exc_info:
        fail_feature_with_explicit_reason([miss])
    error_msg = str(exc_info.value)
    assert specific_path in error_msg, (
        f"Error message must include the specific path '{specific_path}', got: {error_msg!r}"
    )
    assert "ARTIFACT_MISSING" in error_msg, (
        f"Error message must contain ARTIFACT_MISSING prefix, got: {error_msg!r}"
    )


def test_fail_feature_with_multiple_misses_names_all_paths():
    """When multiple misses are passed, the error message includes all missing paths."""
    path_a = "src/module_a.py"
    path_b = "src/module_b.py"
    misses = [
        ArtifactMiss(
            ac_text=f"File exists: {path_a}",
            expected_path=path_a,
            kind="file_exists",
            reason=f"ARTIFACT_MISSING:{path_a}",
        ),
        ArtifactMiss(
            ac_text=f"File exists: {path_b}",
            expected_path=path_b,
            kind="file_exists",
            reason=f"ARTIFACT_MISSING:{path_b}",
        ),
    ]
    with pytest.raises(ArtifactMissingError) as exc_info:
        fail_feature_with_explicit_reason(misses)
    error_msg = str(exc_info.value)
    assert path_a in error_msg, f"Error must name first missing path '{path_a}'"
    assert path_b in error_msg, f"Error must name second missing path '{path_b}'"


def test_verify_ac_artifacts_miss_reason_contains_specific_path(tmp_path):
    """verify_ac_artifacts returns ArtifactMiss whose reason includes the exact missing path."""
    missing_rel = "src/definitely_not_here_xyz.py"
    acs = [f"File exists: {missing_rel}"]
    misses = verify_ac_artifacts(acs, workspace=tmp_path)
    assert len(misses) == 1, f"Expected exactly one miss, got {misses}"
    assert missing_rel in misses[0].reason, (
        f"reason must name the specific path '{missing_rel}', got: {misses[0].reason!r}"
    )
    assert misses[0].expected_path == missing_rel
