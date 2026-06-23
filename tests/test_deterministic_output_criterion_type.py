"""Tests for the deterministic_output_criterion_type module.

Verifies that the public API re-exported from
``bob3.deterministic_output_criterion_type`` (``check_deterministic_output``
and ``parse_deterministic_output_args``) is callable and correct, and that
the ``deterministic_output:`` criterion is routed properly through
``_check_criterion_with_details``.
"""

from __future__ import annotations

import sys
import pathlib

import pytest

from bob3.deterministic_output_criterion_type import (
    check_deterministic_output,
    parse_deterministic_output_args,
)
from bob3.enhanced_verification import _check_criterion_with_details


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deterministic_script(tmp_path: pathlib.Path) -> str:
    """A script that always produces identical output regardless of seed."""
    script = tmp_path / "deterministic.py"
    script.write_text("print('hello world')\n")
    return f"{sys.executable} {script}"


def _nondeterministic_script(tmp_path: pathlib.Path) -> str:
    """A script that uses random without seeding — output differs per run."""
    script = tmp_path / "nondeterministic.py"
    script.write_text("import random\nprint(random.random())\n")
    return f"{sys.executable} {script}"


# ---------------------------------------------------------------------------
# Tests for parse_deterministic_output_args
# ---------------------------------------------------------------------------


class TestParseDeterministicOutputArgs:
    def test_command_extracted(self):
        args = parse_deterministic_output_args('command="python infer.py"')
        assert args["command"] == "python infer.py"

    def test_seeds_list_parsed(self):
        args = parse_deterministic_output_args(
            'command="python infer.py", seeds=[0,1,2,3]'
        )
        assert args["seeds"] == [0, 1, 2, 3]

    def test_env_var_extracted(self):
        args = parse_deterministic_output_args(
            'command="python infer.py", env_var=MY_SEED'
        )
        assert args["env_var"] == "MY_SEED"

    def test_timeout_int(self):
        args = parse_deterministic_output_args(
            'command="python infer.py", timeout=30'
        )
        assert args["timeout"] == 30

    def test_empty_expression(self):
        args = parse_deterministic_output_args("")
        assert "command" not in args

    def test_seeds_with_spaces(self):
        args = parse_deterministic_output_args(
            'command="python infer.py", seeds=[0, 1, 2]'
        )
        assert args["seeds"] == [0, 1, 2]


# ---------------------------------------------------------------------------
# Tests for check_deterministic_output
# ---------------------------------------------------------------------------


class TestCheckDeterministicOutput:
    def test_deterministic_command_passes(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is True
        assert details == ""

    def test_nondeterministic_command_fails(self, tmp_path):
        cmd = _nondeterministic_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is False
        assert details != ""

    def test_missing_command_fails(self, tmp_path):
        passed, details = check_deterministic_output(
            command=None,
            workspace=tmp_path,
        )
        assert passed is False
        assert "command" in details.lower()

    def test_empty_command_fails(self, tmp_path):
        passed, details = check_deterministic_output(
            command="",
            workspace=tmp_path,
        )
        assert passed is False
        assert "command" in details.lower()

    def test_custom_seeds_list(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
            seeds=[0, 1, 2],
        )
        assert passed is True

    def test_single_seed_always_passes(self, tmp_path):
        cmd = _nondeterministic_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
            seeds=[0],
        )
        assert passed is True

    def test_nonzero_exit_code_fails(self, tmp_path):
        cmd = f"{sys.executable} -c 'import sys; sys.exit(1)'"
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is False

    def test_timeout_handled_gracefully(self, tmp_path):
        script = tmp_path / "slow.py"
        script.write_text("import time; time.sleep(999)\n")
        cmd = f"{sys.executable} {script}"
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
            timeout=1,
        )
        assert passed is False
        assert "timeout" in details.lower() or "timed" in details.lower()

    def test_custom_env_var(self, tmp_path):
        script = tmp_path / "custom_env.py"
        script.write_text(
            "import os\n"
            "_seed = int(os.environ.get('MY_SEED', 0))\n"
            "print('fixed')\n"
        )
        cmd = f"{sys.executable} {script}"
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
            env_var="MY_SEED",
        )
        assert passed is True

    def test_seed_placeholder_substitution(self, tmp_path):
        script = tmp_path / "seed_arg.py"
        script.write_text(
            "import sys\n"
            "_seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0\n"
            "print('result: 42')\n"
        )
        cmd = f"{sys.executable} {script} {{seed}}"
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is True


# ---------------------------------------------------------------------------
# Routing tests via _check_criterion_with_details
# ---------------------------------------------------------------------------


class TestDeterministicOutputCriterionTypeRouting:
    def test_criterion_routed_passes(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        passed, details = _check_criterion_with_details(
            criterion=f'deterministic_output: command="{cmd}"',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_nondeterministic_fails(self, tmp_path):
        cmd = _nondeterministic_script(tmp_path)
        passed, details = _check_criterion_with_details(
            criterion=f'deterministic_output: command="{cmd}"',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False

    def test_criterion_missing_command_fails(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion="deterministic_output: seeds=[0,1]",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "command" in details.lower()

    def test_criterion_case_insensitive(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        passed, details = _check_criterion_with_details(
            criterion=f'Deterministic_Output: command="{cmd}"',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_with_custom_seeds(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        passed, details = _check_criterion_with_details(
            criterion=f'deterministic_output: command="{cmd}", seeds=[0,1,2]',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True
