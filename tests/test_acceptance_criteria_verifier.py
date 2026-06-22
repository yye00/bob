"""Tests for bob3.acceptance_criteria.verify_artifact_existence (FC56E557).

Verifies the pre-pytest AC artifact-existence check:
- Missing artifact -> ArtifactMiss with reason ARTIFACT_MISSING:<path>
- Existing artifact -> no miss returned
- Function defined checks work correctly
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from bob3.acceptance_criteria import (
    ArtifactMiss,
    ArtifactMissingError,
    fail_feature_with_explicit_reason,
    recognized_ac_prefixes,
    verify_artifact_existence,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Provide a temporary workspace directory with src/ set up."""
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture
def workspace_with_file(workspace: Path) -> tuple[Path, Path]:
    """Return workspace and a real file inside it."""
    real_file = workspace / "src" / "mymodule.py"
    real_file.write_text("def my_func(): pass\n")
    return workspace, real_file


# ---------------------------------------------------------------------------
# verify_artifact_existence — happy paths
# ---------------------------------------------------------------------------

def test_empty_acs_returns_empty_list(workspace):
    misses = verify_artifact_existence([], workspace)
    assert misses == []


def test_file_exists_present_returns_no_miss(workspace):
    target = workspace / "src" / "existing.py"
    target.write_text("# content\n")
    misses = verify_artifact_existence(["File exists: src/existing.py"], workspace)
    assert misses == []


def test_file_exists_missing_returns_miss(workspace):
    misses = verify_artifact_existence(["File exists: src/missing.py"], workspace)
    assert len(misses) == 1
    miss = misses[0]
    assert isinstance(miss, ArtifactMiss)
    assert "ARTIFACT_MISSING" in miss.reason
    assert "src/missing.py" in miss.reason


def test_file_modified_present_returns_no_miss(workspace):
    target = workspace / "src" / "changed.py"
    target.write_text("x = 1\n")
    misses = verify_artifact_existence(["File modified: src/changed.py"], workspace)
    assert misses == []


def test_file_modified_missing_returns_miss(workspace):
    misses = verify_artifact_existence(["File modified: src/ghost.py"], workspace)
    assert len(misses) == 1
    assert "ARTIFACT_MISSING" in misses[0].reason


def test_pytest_ac_existing_test_file_returns_no_miss(workspace):
    test_file = workspace / "src" / "test_example.py"
    test_file.write_text("def test_something():\n    assert True\n")
    misses = verify_artifact_existence(["pytest: src/test_example.py"], workspace)
    assert misses == []


def test_pytest_ac_missing_file_returns_miss(workspace):
    misses = verify_artifact_existence(["pytest: tests/test_nonexistent.py"], workspace)
    assert len(misses) == 1
    assert "ARTIFACT_MISSING" in misses[0].reason


def test_function_defined_existing_symbol_returns_no_miss(workspace):
    src_dir = workspace / "src"
    pkg = src_dir / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text("def my_fn(): pass\n")
    misses = verify_artifact_existence(
        ["Function defined: mypkg.core.my_fn"],
        workspace,
    )
    assert misses == []


def test_function_defined_missing_symbol_returns_miss(workspace):
    misses = verify_artifact_existence(
        ["Function defined: totally.nonexistent.symbol"],
        workspace,
    )
    assert len(misses) == 1
    assert "ARTIFACT_MISSING" in misses[0].reason


def test_multiple_acs_mixed_results(workspace):
    existing = workspace / "src" / "real.py"
    existing.write_text("# exists\n")
    acs = [
        "File exists: src/real.py",
        "File exists: src/phantom.py",
    ]
    misses = verify_artifact_existence(acs, workspace)
    assert len(misses) == 1
    assert "phantom.py" in misses[0].reason


def test_unknown_prefix_returns_miss_with_unknown_prefix_kind(workspace):
    misses = verify_artifact_existence(["integration: bob3.run_loop"], workspace)
    assert len(misses) == 1
    assert misses[0].kind == "unknown_prefix"


# ---------------------------------------------------------------------------
# ArtifactMiss fields
# ---------------------------------------------------------------------------

def test_artifact_miss_fields_populated(workspace):
    misses = verify_artifact_existence(["File exists: src/nope.py"], workspace)
    assert len(misses) == 1
    miss = misses[0]
    assert miss.ac_text == "File exists: src/nope.py"
    assert "nope.py" in miss.expected_path
    assert miss.kind == "file_exists"
    assert miss.reason.startswith("ARTIFACT_MISSING:")


# ---------------------------------------------------------------------------
# fail_feature_with_explicit_reason
# ---------------------------------------------------------------------------

def test_fail_feature_raises_artifact_missing_error(workspace):
    misses = verify_artifact_existence(["File exists: src/missing.py"], workspace)
    with pytest.raises(ArtifactMissingError) as exc_info:
        fail_feature_with_explicit_reason(misses)
    assert "ARTIFACT_MISSING" in str(exc_info.value)
    assert "src/missing.py" in str(exc_info.value)


def test_fail_feature_empty_misses_does_not_raise(workspace):
    fail_feature_with_explicit_reason([])  # should not raise


# ---------------------------------------------------------------------------
# recognized_ac_prefixes
# ---------------------------------------------------------------------------

def test_recognized_ac_prefixes_returns_tuple():
    prefixes = recognized_ac_prefixes()
    assert isinstance(prefixes, tuple)
    assert "pytest:" in prefixes
    assert "File exists:" in prefixes
    assert "Function defined:" in prefixes


# ---------------------------------------------------------------------------
# run_loop integration — verify_artifact_existence_pre_pytest
# ---------------------------------------------------------------------------

def test_run_loop_integration_pre_pytest_function_exists():
    from bob3 import run_loop
    assert hasattr(run_loop, "verify_artifact_existence_pre_pytest")


def test_run_loop_pre_pytest_delegates_correctly(workspace):
    from bob3.run_loop import verify_artifact_existence_pre_pytest
    misses = verify_artifact_existence_pre_pytest([], workspace)
    assert misses == []


def test_run_loop_pre_pytest_detects_missing_file(workspace):
    from bob3.run_loop import verify_artifact_existence_pre_pytest
    misses = verify_artifact_existence_pre_pytest(
        ["File exists: src/no_such_file.py"], workspace
    )
    assert len(misses) == 1
    assert "ARTIFACT_MISSING" in misses[0].reason
