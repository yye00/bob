"""Tests for bob.scoped_pytest_runner.run_scoped_pytest.

AC: pytest: tests/test_scoped_pytest_to_feature.py
Feature: verifier MUST scope pytest to the current feature's own tests/ subtree
"""

from __future__ import annotations

import pytest

from bob.scoped_pytest_runner import (
    ScopedPytestResult,
    ScopedPytestSkipped,
    SiblingTestCollectionError,
    run_scoped_pytest,
)

FEATURE_ID = "720bc408-79ab-415e-908f-d9ee414a7075"
OTHER_FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_run_scoped_pytest_is_callable():
    """run_scoped_pytest is defined and callable."""
    assert callable(run_scoped_pytest)


def test_scoped_pytest_skipped_when_no_paths(tmp_path):
    """run_scoped_pytest raises ScopedPytestSkipped when no test paths found."""
    acs = ["File exists: src/bob/foo.py", "Function defined: bob.foo.bar"]
    with pytest.raises(ScopedPytestSkipped):
        run_scoped_pytest(FEATURE_ID, acs, tmp_path)


def test_run_scoped_pytest_returns_scoped_pytest_result(tmp_path):
    """run_scoped_pytest returns a ScopedPytestResult when paths are found."""
    # Create a simple passing test file in the workspace
    test_dir = tmp_path / "tests"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_trivial_pass.py"
    test_file.write_text("def test_ok(): assert True\n")

    acs = ["pytest: tests/test_trivial_pass.py"]
    result = run_scoped_pytest(FEATURE_ID, acs, tmp_path)
    assert isinstance(result, ScopedPytestResult)
    assert result.feature_id == FEATURE_ID
    assert "tests/test_trivial_pass.py" in result.scoped_paths


def test_scoped_result_has_returncode(tmp_path):
    """ScopedPytestResult includes an integer returncode."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_trivial_pass2.py"
    test_file.write_text("def test_ok(): assert True\n")

    acs = ["pytest: tests/test_trivial_pass2.py"]
    result = run_scoped_pytest(FEATURE_ID, acs, tmp_path)
    assert isinstance(result.returncode, int)


def test_passing_test_yields_returncode_zero(tmp_path):
    """A passing test file results in returncode 0."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_pass_check.py"
    test_file.write_text("def test_always_passes(): assert 1 + 1 == 2\n")

    acs = ["pytest: tests/test_pass_check.py"]
    result = run_scoped_pytest(FEATURE_ID, acs, tmp_path)
    assert result.passed, f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"


def test_failing_test_yields_nonzero_returncode(tmp_path):
    """A failing test file results in a non-zero returncode."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_fail_check.py"
    test_file.write_text("def test_always_fails(): assert False\n")

    acs = ["pytest: tests/test_fail_check.py"]
    result = run_scoped_pytest(FEATURE_ID, acs, tmp_path)
    assert not result.passed
    assert result.returncode != 0


def test_scoped_paths_do_not_include_bare_tests(tmp_path):
    """Scoped paths never include bare 'tests/' which would collect all features."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_specific.py"
    test_file.write_text("def test_ok(): assert True\n")

    acs = ["pytest: tests/test_specific.py"]
    result = run_scoped_pytest(FEATURE_ID, acs, tmp_path)
    for path in result.scoped_paths:
        assert path not in ("tests", "tests/"), f"Bare tests/ path found: {path}"


def test_sibling_feature_path_raises_sibling_error(tmp_path):
    """run_scoped_pytest raises SiblingTestCollectionError for sibling feature paths."""
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_other.py"]
    with pytest.raises((SiblingTestCollectionError, ScopedPytestSkipped)):
        run_scoped_pytest(FEATURE_ID, acs, tmp_path)


def test_result_workspace_matches_input(tmp_path):
    """ScopedPytestResult.workspace reflects the workspace passed in."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_ws_check.py"
    test_file.write_text("def test_ok(): assert True\n")

    acs = ["pytest: tests/test_ws_check.py"]
    result = run_scoped_pytest(FEATURE_ID, acs, tmp_path)
    assert result.workspace == str(tmp_path)


def test_result_has_stdout_and_stderr(tmp_path):
    """ScopedPytestResult provides stdout and stderr strings."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_output_check.py"
    test_file.write_text("def test_ok(): assert True\n")

    acs = ["pytest: tests/test_output_check.py"]
    result = run_scoped_pytest(FEATURE_ID, acs, tmp_path)
    assert isinstance(result.stdout, str)
    assert isinstance(result.stderr, str)


def test_feature_subtree_included_when_exists(tmp_path):
    """run_scoped_pytest includes tests/<feature_id>/ when that directory exists."""
    feature_test_dir = tmp_path / "tests" / FEATURE_ID
    feature_test_dir.mkdir(parents=True)
    test_file = feature_test_dir / "test_feature_subtree.py"
    test_file.write_text("def test_ok(): assert True\n")

    acs = []
    result = run_scoped_pytest(FEATURE_ID, acs, tmp_path)
    assert f"tests/{FEATURE_ID}" in result.scoped_paths
