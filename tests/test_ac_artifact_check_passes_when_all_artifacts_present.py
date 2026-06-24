"""AC artifact-existence verifier — passes when all artifacts are present."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path

from bob.verification.ac_artifact_check import verify_ac_artifacts

# Workspace root — the bob16 project directory.
_WORKSPACE = Path(__file__).resolve().parent.parent
# A file we know exists: the implementation itself (relative to workspace).
_IMPL_REL = "src/bob/verification/ac_artifact_check.py"


def test_file_exists_ac_passes_for_implementation_file():
    """File exists: AC pointing to the real implementation file returns no misses."""
    ac = f"File exists: {_IMPL_REL}"
    result = verify_ac_artifacts([ac], _WORKSPACE)
    assert isinstance(result, list), "verify_ac_artifacts must return a list"
    assert result == [], f"Expected no misses for real file, got: {result}"
    assert len(result) == 0, "Length must be zero when file exists"


def test_file_modified_ac_passes_for_implementation_file():
    """File modified: AC pointing to the real implementation file returns no misses."""
    ac = f"File modified: {_IMPL_REL}"
    result = verify_ac_artifacts([ac], _WORKSPACE)
    assert isinstance(result, list), "verify_ac_artifacts must return a list"
    assert result == [], f"Expected no misses for real file, got: {result}"


def test_function_defined_ac_passes_for_verify_ac_artifacts():
    """Function defined: AC for verify_ac_artifacts itself returns no misses."""
    ac = "Function defined: bob.verification.ac_artifact_check.verify_ac_artifacts"
    result = verify_ac_artifacts([ac], _WORKSPACE)
    assert isinstance(result, list), "verify_ac_artifacts must return a list"
    assert result == [], f"Expected no misses for real function, got: {result}"


def test_all_three_ac_types_pass_together():
    """File exists, File modified, and Function defined ACs all pass when artifacts exist."""
    acs = [
        f"File exists: {_IMPL_REL}",
        f"File modified: {_IMPL_REL}",
        "Function defined: bob.verification.ac_artifact_check.fail_feature_with_explicit_reason",
    ]
    result = verify_ac_artifacts(acs, _WORKSPACE)
    assert isinstance(result, list), "verify_ac_artifacts must return a list"
    assert result == [], f"Expected no misses for all valid ACs, got: {result}"
    assert len(result) == 0, "All three AC types must pass when artifacts exist"


def test_empty_ac_list_returns_empty_list():
    """verify_ac_artifacts with an empty AC list returns an empty list."""
    result = verify_ac_artifacts([], _WORKSPACE)
    assert isinstance(result, list), "verify_ac_artifacts must return a list"
    assert result == [], "Empty input must yield empty output"
