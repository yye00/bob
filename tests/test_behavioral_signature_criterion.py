"""Tests for the behavioral_signature: criterion type in enhanced_verification.

The behavioral_signature: criterion validates the shape of a loss curve produced
by a command (e.g. a training script), rather than just checking a final scalar.

It catches fake training scripts that emit hardcoded or random losses.

Criterion syntax (all fields optional except 'command'):
    behavioral_signature: command="python train.py"
    behavioral_signature: command="python train.py", monotone_decrease=true
    behavioral_signature: command="python train.py", converges_within=50
    behavioral_signature: command="python train.py", monotone_decrease=true, converges_within=50
    behavioral_signature: command="python train.py", min_steps=5, max_final_loss=0.5
    behavioral_signature: command="python train.py", loss_key=val_loss

The command's stdout/stderr is scanned for lines containing a numeric loss value.
Recognized formats (matched in order):
    loss: 0.45
    loss=0.45
    val_loss: 0.45
    {"loss": 0.45}   (JSON with a "loss" or configured loss_key)

Parameters:
    command:           Shell command to run (required).
    monotone_decrease: If true, each loss value must be <= the previous.
    converges_within:  The loss must stop changing significantly within N steps.
    min_steps:         Minimum number of loss values that must appear.
    max_final_loss:    The last reported loss must be at or below this threshold.
    loss_key:          Key to extract from JSON output lines (default: "loss").
    timeout:           Max seconds to wait for the command (default: 60).
"""

from __future__ import annotations

import json
import pathlib
import textwrap
import sys

import pytest

from bob3.enhanced_verification import (
    _check_criterion_with_details,
    check_behavioral_signature,
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


def _make_training_script(tmp_path: pathlib.Path, losses: list[float], *, key: str = "loss") -> str:
    """Create a Python script that emits the given loss values to stdout."""
    script = tmp_path / "train.py"
    lines_code = "\n".join(
        f'    print("{key}: {loss}")'
        for loss in losses
    )
    script.write_text(
        f"#!/usr/bin/env python3\nif True:\n{lines_code}\n"
    )
    return f"{sys.executable} {script}"


def _make_json_training_script(tmp_path: pathlib.Path, losses: list[float], *, key: str = "loss") -> str:
    """Create a Python script that emits JSON loss dicts to stdout."""
    script = tmp_path / "train_json.py"
    lines_code = "\n".join(
        f'import json; print(json.dumps({{"{key}": {loss}}}))'
        for loss in losses
    )
    script.write_text(
        f"#!/usr/bin/env python3\n{lines_code}\n"
    )
    return f"{sys.executable} {script}"


# ---------------------------------------------------------------------------
# Unit tests for check_behavioral_signature()
# ---------------------------------------------------------------------------


class TestCheckBehavioralSignatureMonotoneDecrease:
    """Tests for monotone_decrease constraint."""

    def test_monotone_decreasing_losses_pass(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.8, 0.6, 0.4, 0.2])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            monotone_decrease=True,
        )
        assert passed is True
        assert details == ""

    def test_non_monotone_losses_fail(self, tmp_path):
        # Loss goes up at step 3 (0.4 -> 0.5)
        cmd = _make_training_script(tmp_path, [1.0, 0.8, 0.5, 0.7, 0.3])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            monotone_decrease=True,
        )
        assert passed is False
        assert "monotone" in details.lower() or "increas" in details.lower()

    def test_constant_loss_fails_monotone(self, tmp_path):
        """A hardcoded constant loss is NOT monotonically decreasing (it must decrease)."""
        cmd = _make_training_script(tmp_path, [0.5, 0.5, 0.5, 0.5])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            monotone_decrease=True,
        )
        # Constant is not strictly decreasing — should fail
        assert passed is False

    def test_monotone_not_required_by_default(self, tmp_path):
        """Without monotone_decrease=True, non-monotone curves pass."""
        cmd = _make_training_script(tmp_path, [1.0, 0.8, 0.9, 0.3])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            monotone_decrease=False,
        )
        assert passed is True


class TestCheckBehavioralSignatureConvergence:
    """Tests for converges_within constraint."""

    def test_converges_within_n_steps_passes(self, tmp_path):
        # Loss drops in first 10 steps then converges
        losses = [1.0, 0.7, 0.4, 0.2, 0.15, 0.14, 0.14, 0.14, 0.14, 0.14]
        cmd = _make_training_script(tmp_path, losses)
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            converges_within=10,
        )
        assert passed is True

    def test_does_not_converge_fails(self, tmp_path):
        # Loss keeps changing significantly beyond N steps
        import random
        random.seed(42)
        losses = [1.0 - i * 0.05 + random.uniform(-0.2, 0.2) for i in range(20)]
        # Force large variation at the end
        losses[-5:] = [5.0, 0.1, 5.0, 0.1, 5.0]
        cmd = _make_training_script(tmp_path, losses)
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            converges_within=5,
        )
        assert passed is False
        assert "converg" in details.lower()


class TestCheckBehavioralSignatureMinSteps:
    """Tests for min_steps constraint."""

    def test_enough_steps_pass(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.8, 0.5, 0.3, 0.1])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=3,
        )
        assert passed is True

    def test_too_few_steps_fail(self, tmp_path):
        cmd = _make_training_script(tmp_path, [0.5])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=5,
        )
        assert passed is False
        assert "step" in details.lower() or "loss" in details.lower()

    def test_zero_loss_values_fail(self, tmp_path):
        """Command that emits no loss values fails min_steps."""
        script = tmp_path / "noloss.py"
        script.write_text("print('Training done!')\n")
        cmd = f"{sys.executable} {script}"
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=1,
        )
        assert passed is False
        assert "loss" in details.lower() or "no" in details.lower()


class TestCheckBehavioralSignatureMaxFinalLoss:
    """Tests for max_final_loss constraint."""

    def test_final_loss_below_threshold_passes(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.5, 0.2, 0.05])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            max_final_loss=0.1,
        )
        assert passed is True

    def test_final_loss_above_threshold_fails(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.5, 0.4, 0.35])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            max_final_loss=0.1,
        )
        assert passed is False
        assert "final" in details.lower() or "loss" in details.lower()

    def test_final_loss_exactly_at_threshold_passes(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.5, 0.1])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            max_final_loss=0.1,
        )
        assert passed is True


class TestCheckBehavioralSignatureJsonOutput:
    """Tests for JSON loss line parsing."""

    def test_json_loss_key_parsed(self, tmp_path):
        cmd = _make_json_training_script(tmp_path, [1.0, 0.7, 0.3])
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=3,
        )
        assert passed is True

    def test_custom_loss_key(self, tmp_path):
        cmd = _make_json_training_script(tmp_path, [1.0, 0.5, 0.2], key="val_loss")
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            loss_key="val_loss",
            min_steps=3,
        )
        assert passed is True

    def test_wrong_loss_key_finds_no_losses(self, tmp_path):
        cmd = _make_json_training_script(tmp_path, [1.0, 0.5, 0.2], key="val_loss")
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            loss_key="train_loss",  # wrong key
            min_steps=1,
        )
        assert passed is False


class TestCheckBehavioralSignatureTextParsing:
    """Tests for text-format loss parsing."""

    def test_loss_colon_format(self, tmp_path):
        script = tmp_path / "train.py"
        script.write_text("print('loss: 0.5\\nloss: 0.3\\nloss: 0.1')\n")
        cmd = f"{sys.executable} {script}"
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=3,
        )
        assert passed is True

    def test_loss_equals_format(self, tmp_path):
        script = tmp_path / "train.py"
        script.write_text("print('loss=0.5\\nloss=0.3\\nloss=0.1')\n")
        cmd = f"{sys.executable} {script}"
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=3,
        )
        assert passed is True

    def test_custom_key_colon_format(self, tmp_path):
        script = tmp_path / "train.py"
        script.write_text("print('val_loss: 0.5\\nval_loss: 0.3\\nval_loss: 0.1')\n")
        cmd = f"{sys.executable} {script}"
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            loss_key="val_loss",
            min_steps=3,
        )
        assert passed is True

    def test_non_loss_lines_ignored(self, tmp_path):
        script = tmp_path / "train.py"
        script.write_text(
            "print('Epoch 1/10\\nloss: 0.8\\nEpoch 2/10\\nloss: 0.5\\n')\n"
        )
        cmd = f"{sys.executable} {script}"
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=2,
        )
        assert passed is True


class TestCheckBehavioralSignatureFailureCases:
    """Tests for error/edge cases."""

    def test_command_fails_returns_false(self, tmp_path):
        cmd = f"{sys.executable} -c 'import sys; sys.exit(1)'"
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=1,
        )
        assert passed is False
        assert "exit" in details.lower() or "fail" in details.lower() or "loss" in details.lower()

    def test_no_constraints_passes_with_any_loss(self, tmp_path):
        cmd = _make_training_script(tmp_path, [5.0, 10.0, 1.0])
        # With no constraints except min_steps=0 (default), any output passes
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
        )
        assert passed is True

    def test_timeout_handled_gracefully(self, tmp_path):
        script = tmp_path / "slow.py"
        script.write_text("import time; time.sleep(999)\n")
        cmd = f"{sys.executable} {script}"
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            min_steps=1,
            timeout=1,
        )
        assert passed is False
        assert "timeout" in details.lower() or "timed" in details.lower() or "loss" in details.lower()

    def test_hardcoded_constant_loss_detected(self, tmp_path):
        """A script that emits the same loss every step should fail monotone_decrease."""
        cmd = _make_training_script(tmp_path, [0.5] * 10)
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            monotone_decrease=True,
        )
        assert passed is False


# ---------------------------------------------------------------------------
# Integration tests via _check_criterion_with_details()
# ---------------------------------------------------------------------------


class TestBehavioralSignatureCriterionRouting:
    """Test that the 'behavioral_signature:' prefix is routed correctly."""

    def test_criterion_basic_routing(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.5, 0.1])
        passed, details = _check_criterion_with_details(
            criterion=f'behavioral_signature: command="{cmd}", min_steps=3',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_monotone_fail(self, tmp_path):
        cmd = _make_training_script(tmp_path, [0.1, 0.5, 0.2])
        passed, details = _check_criterion_with_details(
            criterion=f'behavioral_signature: command="{cmd}", monotone_decrease=true',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False

    def test_criterion_case_insensitive_prefix(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.5])
        passed, details = _check_criterion_with_details(
            criterion=f'Behavioral_Signature: command="{cmd}", min_steps=2',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_max_final_loss(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.5, 0.05])
        passed, details = _check_criterion_with_details(
            criterion=f'behavioral_signature: command="{cmd}", max_final_loss=0.1',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_max_final_loss_fail(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.5, 0.5])
        passed, details = _check_criterion_with_details(
            criterion=f'behavioral_signature: command="{cmd}", max_final_loss=0.1',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False

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


# ---------------------------------------------------------------------------
# Integration via validate_acceptance_criteria()
# ---------------------------------------------------------------------------


class TestBehavioralSignatureEndToEnd:
    """End-to-end tests via validate_acceptance_criteria()."""

    def test_end_to_end_pass(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.7, 0.4, 0.2])
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=[
                f'behavioral_signature: command="{cmd}", monotone_decrease=true, min_steps=4'
            ],
            is_python_project=True,
        )
        assert ok is True

    def test_end_to_end_fail_non_decreasing(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.5, 0.8, 0.2])
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=[
                f'behavioral_signature: command="{cmd}", monotone_decrease=true'
            ],
            is_python_project=True,
        )
        assert ok is False

    def test_end_to_end_json_criteria_list(self, tmp_path):
        cmd = _make_training_script(tmp_path, [1.0, 0.5, 0.1])
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=json.dumps([
                f'behavioral_signature: command="{cmd}", min_steps=3, max_final_loss=0.2'
            ]),
            is_python_project=True,
        )
        assert ok is True

    def test_end_to_end_catches_hardcoded_loss(self, tmp_path):
        """The primary use case: detecting a fake training script with fixed loss output."""
        cmd = _make_training_script(tmp_path, [0.42] * 20)
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=[
                f'behavioral_signature: command="{cmd}", monotone_decrease=true'
            ],
            is_python_project=True,
        )
        # Hardcoded constant loss fails strict monotone decrease
        assert ok is False
