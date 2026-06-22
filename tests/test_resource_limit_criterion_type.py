"""Tests for src/bob3/resource_limit_criterion_type.py public API.

Verifies that the thin wrapper module correctly re-exports
check_resource_limit and parse_resource_limit_args from enhanced_verification.
"""

from __future__ import annotations

import pathlib
import sys
import textwrap

import pytest

from bob3.resource_limit_criterion_type import (
    check_resource_limit,
    parse_resource_limit_args,
)


def _fast_script(tmp_path: pathlib.Path) -> str:
    script = tmp_path / "fast.py"
    script.write_text("import sys; sys.exit(0)\n")
    return f"{sys.executable} {script}"


def _slow_script(tmp_path: pathlib.Path, sleep_s: float = 5.0) -> str:
    script = tmp_path / "slow.py"
    script.write_text(f"import time; time.sleep({sleep_s})\n")
    return f"{sys.executable} {script}"


def _failing_script(tmp_path: pathlib.Path) -> str:
    script = tmp_path / "failing.py"
    script.write_text("import sys; sys.exit(1)\n")
    return f"{sys.executable} {script}"


class TestPublicAPI:
    """Verify the public API exported from resource_limit_criterion_type."""

    def test_check_resource_limit_is_callable(self):
        assert callable(check_resource_limit)

    def test_parse_resource_limit_args_is_callable(self):
        assert callable(parse_resource_limit_args)

    def test_check_resource_limit_missing_command(self, tmp_path):
        passed, details = check_resource_limit(workspace=tmp_path, command=None)
        assert not passed
        assert "command" in details.lower()

    def test_check_resource_limit_fast_command_passes(self, tmp_path):
        cmd = _fast_script(tmp_path)
        passed, details = check_resource_limit(workspace=tmp_path, command=cmd)
        assert passed, f"Expected pass, got: {details}"
        assert details == ""

    def test_check_resource_limit_wall_clock_exceeded(self, tmp_path):
        cmd = _slow_script(tmp_path, sleep_s=10.0)
        passed, details = check_resource_limit(
            workspace=tmp_path,
            command=cmd,
            wall_clock_s=1,
            timeout=3,
        )
        assert not passed
        assert "wall_clock_s" in details or "timed out" in details.lower()

    def test_check_resource_limit_nonzero_exit(self, tmp_path):
        cmd = _failing_script(tmp_path)
        passed, details = check_resource_limit(workspace=tmp_path, command=cmd)
        assert not passed

    def test_check_resource_limit_returns_two_tuple(self, tmp_path):
        cmd = _fast_script(tmp_path)
        result = check_resource_limit(workspace=tmp_path, command=cmd)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_parse_resource_limit_args_command_only(self):
        args = parse_resource_limit_args('command="python eval.py"')
        assert args["command"] == "python eval.py"

    def test_parse_resource_limit_args_all_params(self):
        args = parse_resource_limit_args(
            'command="run.sh", wall_clock_s=30, peak_mem_mb=256, timeout=60'
        )
        assert args["command"] == "run.sh"
        assert args["wall_clock_s"] == 30
        assert args["peak_mem_mb"] == 256
        assert args["timeout"] == 60

    def test_parse_resource_limit_args_empty(self):
        args = parse_resource_limit_args("")
        assert args == {}

    def test_parse_resource_limit_args_no_command(self):
        args = parse_resource_limit_args("wall_clock_s=10")
        assert "command" not in args
        assert args["wall_clock_s"] == 10
