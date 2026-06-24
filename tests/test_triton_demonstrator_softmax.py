"""Tests for the F-R7-476 softmax_2d demonstrator spec.

AC: asserts bob4/research/demonstrators/F-R7-476/spec.yaml declares softmax_2d
feature implemented as Triton kernel numerically equal to torch.softmax
within atol=1e-5.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


SPEC_PATH = Path("bob4/research/demonstrators/F-R7-476/spec.yaml")


class TestTritonDemonstratorSoftmax:
    def test_spec_file_exists(self):
        assert SPEC_PATH.exists(), f"Missing spec file: {SPEC_PATH}"

    def test_spec_is_valid_yaml(self):
        content = SPEC_PATH.read_text()
        data = yaml.safe_load(content)
        assert isinstance(data, dict)

    def test_spec_declares_softmax_2d_feature(self):
        data = yaml.safe_load(SPEC_PATH.read_text())
        assert data["feature"]["name"] == "softmax_2d"

    def test_spec_implemented_as_triton_kernel(self):
        data = yaml.safe_load(SPEC_PATH.read_text())
        assert data["feature"]["implemented_as"] == "triton_kernel"

    def test_spec_atol_within_1e5(self):
        data = yaml.safe_load(SPEC_PATH.read_text())
        atol = float(data["feature"]["atol"])
        assert atol <= 1e-5, f"atol={atol} should be <= 1e-5"

    def test_spec_numerical_gate_reference_is_torch_softmax(self):
        data = yaml.safe_load(SPEC_PATH.read_text())
        reference = data["numerical_gate"]["reference"]
        assert "torch.softmax" in reference

    def test_spec_numerical_gate_atol_le_1e5(self):
        data = yaml.safe_load(SPEC_PATH.read_text())
        atol = float(data["numerical_gate"]["atol"])
        assert atol <= 1e-5

    def test_spec_has_feature_id(self):
        data = yaml.safe_load(SPEC_PATH.read_text())
        assert "feature_id" in data
        assert data["feature_id"] == "F-R7-476"

    def test_verify_numerical_against_reference_within_atol(self):
        """Functional test: verify_numerical sees zero error on identical arrays."""
        from bob.implementers.triton_kernel import verify_numerical

        ref = [1.0, 2.0, 3.0]
        report = verify_numerical(ref, ref)
        assert report.max_abs_err < 1e-5
