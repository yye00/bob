"""Tests that check_pytest_ac and verify_ac_artifacts correctly detect
a pytest file that EXISTS but contains zero test functions."""
from __future__ import annotations

from pathlib import Path

from bob3.verification.ac_artifact_check import (
    ArtifactMiss,
    check_pytest_ac,
    verify_ac_artifacts,
)


def test_check_pytest_ac_returns_false_for_file_with_no_tests(tmp_path: Path) -> None:
    """A file with no test functions should cause check_pytest_ac to return False."""
    empty_test_file = tmp_path / "test_empty.py"
    empty_test_file.write_text(
        "# This file has no test functions\n"
        "def helper():\n"
        "    return 42\n"
        "\n"
        "class NotATest:\n"
        "    def setup(self):\n"
        "        pass\n",
        encoding="utf-8",
    )

    assert empty_test_file.exists(), "precondition: file must exist"

    result = check_pytest_ac(empty_test_file.name, tmp_path)

    assert result is False, (
        "check_pytest_ac should return False for a file with no test_ functions"
    )


def test_check_pytest_ac_returns_false_for_completely_empty_file(tmp_path: Path) -> None:
    """A completely empty file should cause check_pytest_ac to return False."""
    empty_file = tmp_path / "test_blank.py"
    empty_file.write_text("", encoding="utf-8")

    assert empty_file.exists(), "precondition: file must exist"
    assert empty_file.stat().st_size == 0, "precondition: file must be empty"

    result = check_pytest_ac(empty_file.name, tmp_path)

    assert result is False, (
        "check_pytest_ac should return False for a completely empty test file"
    )


def test_verify_ac_artifacts_returns_artifact_miss_for_empty_pytest_file(
    tmp_path: Path,
) -> None:
    """verify_ac_artifacts should return an ArtifactMiss for a file with no tests."""
    empty_test_file = tmp_path / "test_no_functions.py"
    empty_test_file.write_text(
        "# Only imports and constants, no test functions\n"
        "import os\n"
        "CONSTANT = 'nothing'\n",
        encoding="utf-8",
    )

    assert empty_test_file.exists(), "precondition: file must exist"

    ac_string = f"pytest: {empty_test_file.name}"
    misses = verify_ac_artifacts([ac_string], tmp_path)

    assert len(misses) == 1, (
        f"Expected exactly 1 ArtifactMiss, got {len(misses)}"
    )
    miss = misses[0]
    assert isinstance(miss, ArtifactMiss), (
        f"Expected an ArtifactMiss instance, got {type(miss)}"
    )
    assert miss.kind == "pytest", (
        f"Expected kind='pytest', got kind={miss.kind!r}"
    )
    assert empty_test_file.name in miss.reason, (
        f"Expected file name in reason, got reason={miss.reason!r}"
    )


def test_check_pytest_ac_returns_true_for_file_with_tests(tmp_path: Path) -> None:
    """Sanity check: a file WITH test functions returns True."""
    real_test_file = tmp_path / "test_has_function.py"
    real_test_file.write_text(
        "def test_something():\n"
        "    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )

    assert real_test_file.exists(), "precondition: file must exist"

    result = check_pytest_ac(real_test_file.name, tmp_path)

    assert result is True, (
        "check_pytest_ac should return True for a file that contains test_ functions"
    )


def test_verify_ac_artifacts_no_miss_when_file_has_tests(tmp_path: Path) -> None:
    """verify_ac_artifacts should return no misses when the pytest file has real tests."""
    real_test_file = tmp_path / "test_valid.py"
    real_test_file.write_text(
        "def test_one():\n"
        "    assert 1 == 1\n"
        "\n"
        "def test_two():\n"
        "    assert 2 == 2\n",
        encoding="utf-8",
    )

    assert real_test_file.exists(), "precondition: file must exist"

    ac_string = f"pytest: {real_test_file.name}"
    misses = verify_ac_artifacts([ac_string], tmp_path)

    assert misses == [], (
        f"Expected no misses for a file with test functions, got {misses}"
    )
