"""Tests for ac_verifier.verify_artifacts — main test suite."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ac_verifier import verify_artifacts


def _make_ws_with_file(filename: str, content: str = "") -> Path:
    """Create a temporary workspace directory with one file."""
    tmp = Path(tempfile.mkdtemp())
    f = tmp / filename
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content)
    return tmp


def test_verify_artifacts_returns_list():
    """verify_artifacts must return a list."""
    result = verify_artifacts([], workspace="/tmp")
    assert isinstance(result, list)


def test_verify_artifacts_empty_acs_returns_empty_list():
    """Empty AC list must yield no misses."""
    result = verify_artifacts([], workspace="/tmp")
    assert result == []


def test_verify_artifacts_file_exists_ac_passes_when_file_present():
    """File exists: AC must pass when the file is present."""
    ws = _make_ws_with_file("src/mymodule.py", "# hello")
    result = verify_artifacts(["File exists: src/mymodule.py"], workspace=ws)
    assert result == [], f"Expected no misses, got {result}"


def test_verify_artifacts_file_exists_ac_fails_when_file_missing():
    """File exists: AC must fail when the file is absent."""
    result = verify_artifacts(["File exists: src/nonexistent.py"], workspace="/tmp")
    assert len(result) >= 1
    assert result[0].kind == "file_exists"


def test_verify_artifacts_pytest_ac_fails_when_file_missing():
    """pytest: AC must fail when the test file does not exist."""
    result = verify_artifacts(["pytest: tests/missing_test.py"], workspace="/tmp")
    assert len(result) >= 1
    assert result[0].kind == "pytest"


def test_verify_artifacts_pytest_ac_passes_when_test_file_has_tests():
    """pytest: AC must pass when the test file exists and contains test functions."""
    ws = _make_ws_with_file(
        "tests/test_sample.py",
        "def test_something():\n    assert True\n",
    )
    result = verify_artifacts(["pytest: tests/test_sample.py"], workspace=ws)
    assert result == [], f"Expected no misses, got {result}"


def test_verify_artifacts_reason_contains_artifact_missing():
    """The miss reason must contain ARTIFACT_MISSING:<path>."""
    result = verify_artifacts(["File exists: missing_file.py"], workspace="/tmp")
    assert len(result) >= 1
    assert "ARTIFACT_MISSING" in result[0].reason


def test_verify_artifacts_miss_expected_path_set():
    """The miss expected_path must be populated with the relevant path."""
    result = verify_artifacts(["File exists: some/missing.py"], workspace="/tmp")
    assert len(result) >= 1
    assert "some/missing.py" in result[0].expected_path or "missing.py" in result[0].expected_path


def test_verify_artifacts_function_defined_ac_fails_when_module_missing():
    """Function defined: AC must fail when the module cannot be imported."""
    result = verify_artifacts(
        ["Function defined: nonexistent_module_xyz.some_func"],
        workspace="/tmp",
    )
    assert len(result) >= 1
    assert result[0].kind == "function_defined"


def test_verify_artifacts_multiple_acs_collects_all_misses():
    """All failing ACs must be reported, not just the first."""
    result = verify_artifacts(
        [
            "File exists: no_such_file_a.py",
            "File exists: no_such_file_b.py",
        ],
        workspace="/tmp",
    )
    assert len(result) >= 2


def test_verify_artifacts_passing_and_failing_acs_mixed():
    """Only failing ACs appear in the misses list; passing ones are silent."""
    ws = _make_ws_with_file("present.py", "# ok")
    result = verify_artifacts(
        [
            "File exists: present.py",
            "File exists: absent.py",
        ],
        workspace=ws,
    )
    # Only the absent file should be in misses
    assert len(result) == 1
    assert "absent.py" in result[0].expected_path


def test_verify_artifacts_miss_ac_text_preserved():
    """The original AC text must be preserved in the miss object."""
    ac = "File exists: lost_file.py"
    result = verify_artifacts([ac], workspace="/tmp")
    assert len(result) >= 1
    assert result[0].ac_text == ac
