"""Tests for the deterministic_output: criterion type in enhanced_verification.

The deterministic_output: criterion runs a command with seeds 0-3 and asserts
that the stdout output is identical across all four runs.  This catches
implementations that use random state without a fixed seed.

Criterion syntax:
    deterministic_output: command="python infer.py"
    deterministic_output: command="python infer.py", seeds=[0,1,2,3]
    deterministic_output: command="python infer.py --seed {seed}"
    deterministic_output: command="python infer.py", env_var=SEED
    deterministic_output: command="python infer.py", timeout=30

Parameters:
    command:   Shell command to run (required).  The literal ``{seed}`` in the
               command string is replaced with the numeric seed value before
               execution.
    seeds:     List of integer seeds to test (default: [0, 1, 2, 3]).
    env_var:   Environment variable name to inject the seed into (default:
               ``"SEED"``).  Combined with the ``{seed}`` substitution — both
               mechanisms are always active.
    timeout:   Max seconds to wait for each invocation (default: 60).

The criterion PASSES when all invocations produce identical stdout.
The criterion FAILS when any invocation's stdout differs from the first, or
when any invocation exits with a non-zero code, or times out.
"""

from __future__ import annotations

import json
import pathlib
import sys
import textwrap

import pytest

from bob.enhanced_verification import (
    _check_criterion_with_details,
    check_deterministic_output,
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


def _deterministic_script(tmp_path: pathlib.Path) -> str:
    """A script that always prints the same fixed output, ignoring seed."""
    script = tmp_path / "deterministic.py"
    script.write_text("print('hello world')\n")
    return f"{sys.executable} {script}"


def _nondeterministic_script(tmp_path: pathlib.Path) -> str:
    """A script that uses Python's random module without seeding."""
    script = tmp_path / "nondeterministic.py"
    script.write_text(
        "import random\nprint(random.random())\n"
    )
    return f"{sys.executable} {script}"


def _seed_aware_script(tmp_path: pathlib.Path) -> str:
    """A script that reads SEED env var but always produces the same fixed output.

    This simulates an implementation that accepts a seed parameter but its output
    is not affected by the seed (e.g., it computes a deterministic lookup table).
    The criterion passes because output is identical regardless of seed value.
    """
    script = tmp_path / "seed_aware.py"
    script.write_text(
        "import os\n"
        "# Read seed but output is always identical (seed-invariant)\n"
        "_seed = int(os.environ.get('SEED', 0))  # noqa: F841\n"
        "print('result: 42')\n"
    )
    return f"{sys.executable} {script}"


def _seed_arg_script(tmp_path: pathlib.Path) -> str:
    """A script that accepts a seed CLI arg but always produces the same output."""
    script = tmp_path / "seed_arg.py"
    script.write_text(
        "import sys\n"
        "# Accept seed arg but output is always identical\n"
        "_seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # noqa: F841\n"
        "print('result: 42')\n"
    )
    return f"{sys.executable} {script}"


# ---------------------------------------------------------------------------
# Unit tests for check_deterministic_output()
# ---------------------------------------------------------------------------


class TestCheckDeterministicOutputBasic:
    """Basic determinism tests."""

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

    def test_seed_env_var_injected_by_default(self, tmp_path):
        """When command is seed-aware via SEED env var it should be deterministic."""
        cmd = _seed_aware_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is True

    def test_seed_substitution_in_command_string(self, tmp_path):
        """The {seed} placeholder in the command is replaced with the numeric seed."""
        script = _seed_arg_script(tmp_path)
        cmd = f"{script} {{seed}}"
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is True


class TestCheckDeterministicOutputSeeds:
    """Tests for the seeds parameter."""

    def test_custom_seeds_list(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
            seeds=[0, 1, 2],
        )
        assert passed is True

    def test_single_seed_always_passes(self, tmp_path):
        """A single seed has nothing to compare against — should pass."""
        cmd = _nondeterministic_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
            seeds=[0],
        )
        assert passed is True

    def test_two_seeds_nondeterministic_fails(self, tmp_path):
        cmd = _nondeterministic_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
            seeds=[0, 1],
        )
        assert passed is False

    def test_four_seeds_default(self, tmp_path):
        """Default seeds [0,1,2,3] with a deterministic script should pass."""
        cmd = _deterministic_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is True


class TestCheckDeterministicOutputEnvVar:
    """Tests for custom env_var injection."""

    def test_custom_env_var_name(self, tmp_path):
        """Inject seed via a custom environment variable name; output is seed-invariant."""
        script = tmp_path / "custom_env.py"
        script.write_text(
            "import os\n"
            "_seed = int(os.environ.get('MY_SEED', 0))  # noqa: F841\n"
            "print('fixed output')\n"
        )
        cmd = f"{sys.executable} {script}"
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
            env_var="MY_SEED",
        )
        assert passed is True

    def test_wrong_env_var_name_nondeterministic_fails(self, tmp_path):
        """If command reads SEED but we inject MY_SEED it won't be seeded properly."""
        cmd = _nondeterministic_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
            env_var="UNUSED_ENV_VAR",
        )
        assert passed is False


class TestCheckDeterministicOutputErrors:
    """Tests for failure/error cases."""

    def test_command_required(self, tmp_path):
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

    def test_nonzero_exit_code_fails(self, tmp_path):
        cmd = f"{sys.executable} -c 'import sys; sys.exit(1)'"
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is False
        assert "exit" in details.lower() or "fail" in details.lower() or "code" in details.lower()

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

    def test_details_mention_seed_on_failure(self, tmp_path):
        cmd = _nondeterministic_script(tmp_path)
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is False
        assert "seed" in details.lower() or "differ" in details.lower() or "mismatch" in details.lower()


class TestCheckDeterministicOutputMultiline:
    """Tests for multiline output comparison."""

    def test_multiline_deterministic_passes(self, tmp_path):
        script = tmp_path / "multi.py"
        script.write_text(
            "for i in range(5):\n"
            "    print(f'step {i}: result={i*2}')\n"
        )
        cmd = f"{sys.executable} {script}"
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is True

    def test_multiline_nondeterministic_fails(self, tmp_path):
        script = tmp_path / "multi_random.py"
        script.write_text(
            "import random\n"
            "for i in range(5):\n"
            "    print(f'step {i}: result={random.random()}')\n"
        )
        cmd = f"{sys.executable} {script}"
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is False

    def test_empty_output_is_deterministic(self, tmp_path):
        script = tmp_path / "silent.py"
        script.write_text("pass\n")
        cmd = f"{sys.executable} {script}"
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is True


# ---------------------------------------------------------------------------
# Integration tests via _check_criterion_with_details()
# ---------------------------------------------------------------------------


class TestDeterministicOutputCriterionRouting:
    """Test that the 'deterministic_output:' prefix is routed correctly."""

    def test_criterion_basic_routing_passes(self, tmp_path):
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

    def test_criterion_case_insensitive_prefix(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        passed, details = _check_criterion_with_details(
            criterion=f'Deterministic_Output: command="{cmd}"',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_custom_seeds(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        passed, details = _check_criterion_with_details(
            criterion=f'deterministic_output: command="{cmd}", seeds=[0,1,2]',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

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

    def test_criterion_with_timeout(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        passed, details = _check_criterion_with_details(
            criterion=f'deterministic_output: command="{cmd}", timeout=30',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_with_env_var(self, tmp_path):
        """env_var=SEED is injected; seed-invariant command still passes."""
        cmd = _deterministic_script(tmp_path)
        passed, details = _check_criterion_with_details(
            criterion=f'deterministic_output: command="{cmd}", env_var=SEED',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True


# ---------------------------------------------------------------------------
# Integration via validate_acceptance_criteria()
# ---------------------------------------------------------------------------


class TestDeterministicOutputEndToEnd:
    """End-to-end tests via validate_acceptance_criteria()."""

    def test_end_to_end_deterministic_passes(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=[f'deterministic_output: command="{cmd}"'],
            is_python_project=True,
        )
        assert ok is True

    def test_end_to_end_nondeterministic_fails(self, tmp_path):
        cmd = _nondeterministic_script(tmp_path)
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=[f'deterministic_output: command="{cmd}"'],
            is_python_project=True,
        )
        assert ok is False

    def test_end_to_end_seed_invariant_passes(self, tmp_path):
        """A seed-invariant command (same output for all seeds) passes."""
        cmd = _seed_aware_script(tmp_path)
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=[f'deterministic_output: command="{cmd}"'],
            is_python_project=True,
        )
        assert ok is True

    def test_end_to_end_json_criteria_list(self, tmp_path):
        cmd = _deterministic_script(tmp_path)
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=json.dumps(
                [f'deterministic_output: command="{cmd}", seeds=[0,1,2,3]']
            ),
            is_python_project=True,
        )
        assert ok is True

    def test_end_to_end_catches_unseeded_random(self, tmp_path):
        """Primary use case: detect a script that uses random without seeding."""
        cmd = _nondeterministic_script(tmp_path)
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=[f'deterministic_output: command="{cmd}"'],
            is_python_project=True,
        )
        assert ok is False
