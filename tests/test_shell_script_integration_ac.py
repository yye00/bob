"""Tests for Pattern 9: shell-script integration AC handler (F-R7-594).

When an 'integration:' AC body resolves to an existing, executable .sh (or
.bash) file, the verifier MUST demote to PASS with a WARNING tagged 'F-R7-594'.
Missing scripts or standard pytest forms must NOT be demoted.
"""
from __future__ import annotations

import logging
import os
import pathlib
import stat

import pytest


def _make_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a minimal Python workspace with a tools/ directory."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tools").mkdir(exist_ok=True)
    return tmp_path


def _make_executable_sh(workspace: pathlib.Path, rel_path: str) -> pathlib.Path:
    """Create a shell script at *rel_path* inside *workspace* with mode 0o755."""
    full = workspace / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text("#!/bin/bash\necho hello\n")
    full.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    return full


def test_existing_executable_demotes(tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture) -> None:
    """AC: existing executable .sh → PASS with F-R7-594 WARNING."""
    workspace = _make_workspace(tmp_path)
    _make_executable_sh(workspace, "tools/spawn_next_generation.sh")

    from bob.enhanced_verification import _check_criterion_with_details

    criterion = "integration: tools/spawn_next_generation.sh"
    with caplog.at_level(logging.WARNING, logger="bob"):
        result, _ = _check_criterion_with_details(
            criterion=criterion,
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )

    assert result is True, "Existing executable .sh must demote to PASS"
    assert "F-R7-594" in caplog.text, "WARNING must be tagged F-R7-594"
    assert "spawn_next_generation.sh" in caplog.text, "WARNING must include the script path"


def test_missing_script_fails(tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture) -> None:
    """AC: .sh path that does NOT exist → NOT demoted (hard fail)."""
    workspace = _make_workspace(tmp_path)
    # Do NOT create the script

    from bob.enhanced_verification import _check_criterion_with_details

    criterion = "integration: tools/self_heal.sh"
    with caplog.at_level(logging.WARNING, logger="bob"):
        result, _ = _check_criterion_with_details(
            criterion=criterion,
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )

    assert result is False, "Missing .sh must NOT be demoted — regression guard"


def test_pytest_form_unchanged(tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture) -> None:
    """AC: standard pytest form must go through Pattern 8 unchanged (no Pattern-9 short-circuit)."""
    workspace = _make_workspace(tmp_path)
    # Create a dummy module so _integration_wired can succeed
    src_pkg = workspace / "src" / "bob"
    src_pkg.mkdir(parents=True, exist_ok=True)
    (src_pkg / "__init__.py").write_text("")
    (src_pkg / "mymodule.py").write_text("def my_func(): pass\n")

    from bob.enhanced_verification import _check_criterion_with_details

    # A pytest form — must NOT trigger the .sh short-circuit
    criterion = "integration: pytest tests/test_mymodule.py::test_my_func"
    # We don't assert True/False here — only that no F-R7-594 warning was emitted
    with caplog.at_level(logging.WARNING, logger="bob"):
        _check_criterion_with_details(
            criterion=criterion,
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )

    assert "F-R7-594" not in caplog.text, (
        "pytest-form integration AC must NOT trigger the shell-script demotion path"
    )
