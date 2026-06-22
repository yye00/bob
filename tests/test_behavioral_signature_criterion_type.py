"""Tests for the behavioral_signature_criterion_type module.

Verifies that the public API re-exported from
``bob3.behavioral_signature_criterion_type`` (``check_behavioral_signature``
and ``parse_behavioral_signature_args``) is callable and correct, and that
the ``behavioral_signature:`` criterion is routed properly through
``_check_criterion_with_details``.
"""

from __future__ import annotations

import sys
import pathlib

import pytest

from bob3.behavioral_signature_criterion_type import (
    check_behavioral_signature,
    parse_behavioral_signature_args,
)
from bob3.enhanced_verification import _check_criterion_with_details


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_script(tmp_path: pathlib.Path, losses: list[float], *, key: str = "loss") -> str:
    """Return a shell command that prints the given loss values."""
    script = tmp_path / "train.py"
    lines = "\n".join(f'    print("{key}: {v}")' for v in losses)
    script.write_text(f"#!/usr/bin/env python3\nif True:\n{lines}\n")
    return f"{sys.executable} {script}"


# ---------------------------------------------------------------------------
# Tests for parse_behavioral_signature_args
# ---------------------------------------------------------------------------


class TestParseBehavioralSignatureArgs:
    def test_command_extracted(self):
        args = parse_behavioral_signature_args('command="python train.py"')
        assert args["command"] == "python train.py"

    def test_monotone_decrease_bool(self):
        args = parse_behavioral_signature_args(
            'command="python train.py", monotone_decrease=true'
        )
        assert args["monotone_decrease"] is True

    def test_min_steps_int(self):
        args = parse_behavioral_signature_args(
            'command="python train.py", min_steps=10'
        )
        assert args["min_steps"] == 10

    def test_max_final_loss_float(self):
        args = parse_behavioral_signature_args(
            'command="python train.py", max_final_loss=0.5'
        )
        assert abs(args["max_final_loss"] - 0.5) < 1e-9

    def test_converges_within_int(self):
        args = parse_behavioral_signature_args(
            'command="python train.py", converges_within=50'
        )
        assert args["converges_within"] == 50

    def test_loss_key_string(self):
        args = parse_behavioral_signature_args(
            'command="python train.py", loss_key=val_loss'
        )
        assert args["loss_key"] == "val_loss"

    def test_empty_expression(self):
        args = parse_behavioral_signature_args("")
        assert "command" not in args


# ---------------------------------------------------------------------------
# Tests for check_behavioral_signature
# ---------------------------------------------------------------------------


class TestCheckBehavioralSignature:
    def test_monotone_decreasing_passes(self, tmp_path):
        cmd = _make_script(tmp_path, [1.0, 0.7, 0.4, 0.1])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            monotone_decrease=True,
        )
        assert passed is True
        assert details == ""

    def test_non_monotone_fails(self, tmp_path):
        cmd = _make_script(tmp_path, [1.0, 0.5, 0.8, 0.2])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            monotone_decrease=True,
        )
        assert passed is False
        assert details != ""

    def test_constant_loss_fails_monotone(self, tmp_path):
        cmd = _make_script(tmp_path, [0.5] * 5)
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            monotone_decrease=True,
        )
        assert passed is False

    def test_min_steps_satisfied(self, tmp_path):
        cmd = _make_script(tmp_path, [1.0, 0.8, 0.6])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=3,
        )
        assert passed is True

    def test_min_steps_not_satisfied(self, tmp_path):
        cmd = _make_script(tmp_path, [0.5])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=5,
        )
        assert passed is False

    def test_max_final_loss_pass(self, tmp_path):
        cmd = _make_script(tmp_path, [1.0, 0.5, 0.05])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            max_final_loss=0.1,
        )
        assert passed is True

    def test_max_final_loss_fail(self, tmp_path):
        cmd = _make_script(tmp_path, [1.0, 0.5, 0.4])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            max_final_loss=0.1,
        )
        assert passed is False

    def test_no_loss_values_fails(self, tmp_path):
        script = tmp_path / "noloss.py"
        script.write_text("print('no losses here')\n")
        cmd = f"{sys.executable} {script}"
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=1,
        )
        assert passed is False

    def test_missing_command_fails(self, tmp_path):
        passed, details = check_behavioral_signature(
            command=None,
            workspace=tmp_path,
        )
        assert passed is False
        assert "command" in details.lower()

    def test_command_nonzero_exit_fails(self, tmp_path):
        cmd = f"{sys.executable} -c 'import sys; sys.exit(1)'"
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is False

    def test_timeout_fails_gracefully(self, tmp_path):
        script = tmp_path / "slow.py"
        script.write_text("import time; time.sleep(999)\n")
        cmd = f"{sys.executable} {script}"
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            timeout=1,
        )
        assert passed is False
        assert "timeout" in details.lower() or "timed" in details.lower()

    def test_custom_loss_key(self, tmp_path):
        cmd = _make_script(tmp_path, [1.0, 0.5, 0.1], key="val_loss")
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            loss_key="val_loss",
            min_steps=3,
        )
        assert passed is True

    def test_no_constraints_passes(self, tmp_path):
        cmd = _make_script(tmp_path, [5.0, 10.0, 1.0])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is True


# ---------------------------------------------------------------------------
# Routing tests via _check_criterion_with_details
# ---------------------------------------------------------------------------


class TestBehavioralSignatureCriterionRouting:
    def test_criterion_routed(self, tmp_path):
        cmd = _make_script(tmp_path, [1.0, 0.5, 0.1])
        passed, details = _check_criterion_with_details(
            criterion=f'behavioral_signature: command="{cmd}", min_steps=3',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_case_insensitive(self, tmp_path):
        cmd = _make_script(tmp_path, [1.0, 0.5])
        passed, details = _check_criterion_with_details(
            criterion=f'Behavioral_Signature: command="{cmd}", min_steps=2',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_missing_command_fails(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion="behavioral_signature: monotone_decrease=true",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "command" in details.lower()
