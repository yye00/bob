"""Tests for the resource_limit: criterion type in enhanced_verification.

The resource_limit: criterion runs a command and enforces hard caps on:
  - wall-clock execution time (wall_clock_s)
  - peak resident-set memory (peak_mem_mb)

Criterion syntax:
    resource_limit: command="python train.py"
    resource_limit: command="python train.py", wall_clock_s=30
    resource_limit: command="python train.py", peak_mem_mb=512
    resource_limit: command="python train.py", wall_clock_s=60, peak_mem_mb=256

Parameters:
    command:       Shell command to run (required).
    wall_clock_s:  Maximum allowed wall-clock seconds (default: no cap beyond the
                   global criterion exec timeout).
    peak_mem_mb:   Maximum allowed peak RSS in mebibytes (default: no cap).
    timeout:       Overall subprocess kill timeout in seconds (defaults to the
                   global BOB3_CRITERION_EXEC_TIMEOUT).  Should be >= wall_clock_s.

The criterion PASSES when the command exits 0 within the time and memory caps.
The criterion FAILS when:
  - 'command' is missing
  - the command times out (wall_clock_s exceeded)
  - the command exits with a non-zero code
  - peak RSS exceeds peak_mem_mb
"""

from __future__ import annotations

import json
import pathlib
import sys
import textwrap
import time

import pytest

from bob3.enhanced_verification import (
    _check_criterion_with_details,
    check_resource_limit,
    validate_acceptance_criteria,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


def _fast_script(tmp_path: pathlib.Path) -> str:
    """A script that exits immediately with code 0."""
    script = tmp_path / "fast.py"
    script.write_text("import sys; sys.exit(0)\n")
    return f"{sys.executable} {script}"


def _slow_script(tmp_path: pathlib.Path, sleep_s: float = 5.0) -> str:
    """A script that sleeps for sleep_s seconds."""
    script = tmp_path / "slow.py"
    script.write_text(f"import time; time.sleep({sleep_s})\n")
    return f"{sys.executable} {script}"


def _failing_script(tmp_path: pathlib.Path) -> str:
    """A script that exits with code 1."""
    script = tmp_path / "failing.py"
    script.write_text("import sys; sys.exit(1)\n")
    return f"{sys.executable} {script}"


def _memory_hungry_script(tmp_path: pathlib.Path, mb: int = 200) -> str:
    """A script that allocates approximately mb MiB and then exits."""
    script = tmp_path / "memory_hungry.py"
    script.write_text(
        f"buf = bytearray({mb} * 1024 * 1024)\n"
        "import time; time.sleep(0.1)\n"
    )
    return f"{sys.executable} {script}"


# ---------------------------------------------------------------------------
# Unit tests for check_resource_limit()
# ---------------------------------------------------------------------------


class TestCheckResourceLimit:
    """Direct tests for check_resource_limit()."""

    def test_missing_command_fails(self, tmp_path):
        passed, details = check_resource_limit(workspace=tmp_path, command=None)
        assert not passed
        assert "command" in details.lower()

    def test_empty_command_fails(self, tmp_path):
        passed, details = check_resource_limit(workspace=tmp_path, command="")
        assert not passed
        assert "command" in details.lower()

    def test_fast_command_passes(self, tmp_path):
        cmd = _fast_script(tmp_path)
        passed, details = check_resource_limit(
            workspace=tmp_path,
            command=cmd,
            wall_clock_s=10,
        )
        assert passed, f"Expected pass, got: {details}"
        assert details == ""

    def test_no_caps_passes_for_fast_command(self, tmp_path):
        """Without any caps, a fast command should pass."""
        cmd = _fast_script(tmp_path)
        passed, details = check_resource_limit(workspace=tmp_path, command=cmd)
        assert passed, f"Expected pass, got: {details}"

    def test_wall_clock_timeout_fails(self, tmp_path):
        """A command that exceeds wall_clock_s must fail."""
        cmd = _slow_script(tmp_path, sleep_s=10.0)
        passed, details = check_resource_limit(
            workspace=tmp_path,
            command=cmd,
            wall_clock_s=1,
            timeout=3,
        )
        assert not passed
        assert "wall_clock_s" in details or "timed out" in details.lower()

    def test_nonzero_exit_fails(self, tmp_path):
        """A command that exits non-zero must fail."""
        cmd = _failing_script(tmp_path)
        passed, details = check_resource_limit(workspace=tmp_path, command=cmd)
        assert not passed
        assert "exit" in details.lower() or "code" in details.lower()

    def test_peak_mem_within_cap_passes(self, tmp_path):
        """A command within the peak_mem_mb cap should pass."""
        cmd = _fast_script(tmp_path)
        passed, details = check_resource_limit(
            workspace=tmp_path,
            command=cmd,
            peak_mem_mb=2048,
        )
        assert passed, f"Expected pass, got: {details}"

    def test_peak_mem_exceeded_fails(self, tmp_path):
        """A command exceeding peak_mem_mb must fail."""
        # Allocate 50 MiB; cap at 5 MiB — should reliably exceed.
        cmd = _memory_hungry_script(tmp_path, mb=50)
        passed, details = check_resource_limit(
            workspace=tmp_path,
            command=cmd,
            peak_mem_mb=5,
            timeout=30,
        )
        assert not passed
        assert "peak_mem_mb" in details or "memory" in details.lower()

    def test_returns_two_tuple(self, tmp_path):
        cmd = _fast_script(tmp_path)
        result = check_resource_limit(workspace=tmp_path, command=cmd)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)


# ---------------------------------------------------------------------------
# Tests via _check_criterion_with_details()
# ---------------------------------------------------------------------------


class TestCheckCriterionWithDetails:
    """Tests that verify routing via _check_criterion_with_details."""

    def _call(self, tmp_path, criterion):
        return _check_criterion_with_details(
            criterion=criterion,
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )

    def test_basic_fast_command(self, tmp_path):
        cmd = _fast_script(tmp_path)
        passed, details = self._call(tmp_path, f'resource_limit: command="{cmd}"')
        assert passed, f"Expected pass, got: {details}"

    def test_wall_clock_s_respected(self, tmp_path):
        cmd = _slow_script(tmp_path, sleep_s=10.0)
        passed, details = self._call(
            tmp_path,
            f'resource_limit: command="{cmd}", wall_clock_s=1, timeout=3',
        )
        assert not passed

    def test_nonzero_exit_via_criterion(self, tmp_path):
        cmd = _failing_script(tmp_path)
        passed, details = self._call(tmp_path, f'resource_limit: command="{cmd}"')
        assert not passed

    def test_missing_command_criterion(self, tmp_path):
        passed, details = self._call(tmp_path, "resource_limit: wall_clock_s=10")
        assert not passed
        assert "command" in details.lower()

    def test_case_insensitive_prefix(self, tmp_path):
        cmd = _fast_script(tmp_path)
        passed, details = self._call(tmp_path, f'RESOURCE_LIMIT: command="{cmd}"')
        assert passed, f"Expected pass, got: {details}"


# ---------------------------------------------------------------------------
# Tests via validate_acceptance_criteria()
# ---------------------------------------------------------------------------


class TestValidateAcceptanceCriteria:
    """Tests that verify resource_limit: works end-to-end through the full API."""

    def test_fast_command_passes_e2e(self, tmp_path):
        cmd = _fast_script(tmp_path)
        passed, details = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=json.dumps([f'resource_limit: command="{cmd}"']),
            is_python_project=True,
        )
        assert passed, f"Expected pass, got: {details}"

    def test_slow_command_fails_e2e(self, tmp_path):
        cmd = _slow_script(tmp_path, sleep_s=10.0)
        passed, details = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=json.dumps(
                [f'resource_limit: command="{cmd}", wall_clock_s=1, timeout=3']
            ),
            is_python_project=True,
        )
        assert not passed

    def test_missing_command_fails_e2e(self, tmp_path):
        passed, details = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=json.dumps(["resource_limit: wall_clock_s=30"]),
            is_python_project=True,
        )
        assert not passed


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParseResourceLimitArgs:
    """Unit tests for _parse_resource_limit_args."""

    def _parse(self, expression: str) -> dict:
        from bob3.enhanced_verification import _parse_resource_limit_args
        return _parse_resource_limit_args(expression)

    def test_command_only(self):
        args = self._parse('command="python train.py"')
        assert args["command"] == "python train.py"

    def test_wall_clock_s(self):
        args = self._parse('command="run.sh", wall_clock_s=60')
        assert args["wall_clock_s"] == 60

    def test_peak_mem_mb(self):
        args = self._parse('command="run.sh", peak_mem_mb=512')
        assert args["peak_mem_mb"] == 512

    def test_timeout(self):
        args = self._parse('command="run.sh", timeout=120')
        assert args["timeout"] == 120

    def test_all_params(self):
        args = self._parse(
            'command="python eval.py", wall_clock_s=30, peak_mem_mb=256, timeout=60'
        )
        assert args["command"] == "python eval.py"
        assert args["wall_clock_s"] == 30
        assert args["peak_mem_mb"] == 256
        assert args["timeout"] == 60

    def test_missing_command_returns_no_command_key(self):
        args = self._parse("wall_clock_s=10")
        assert "command" not in args

    def test_empty_expression_returns_empty(self):
        args = self._parse("")
        assert args == {}
