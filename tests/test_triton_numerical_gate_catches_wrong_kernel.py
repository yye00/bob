"""Tests for gate_on_numerical_correctness — error path focus.

AC: asserts gate_on_numerical_correctness raises NumericalGateError with
message containing "atol" when error exceeds tolerance (error path).
"""

from __future__ import annotations

import pytest
import bob3.implementers.triton_kernel as tk
from bob3.implementers.triton_kernel import NumericalReport, NumericalGateError


class TestNumericalGateCatchesWrongKernel:
    def test_raises_when_abs_err_exceeds_atol(self):
        bad_report = NumericalReport(max_abs_err=1.0, max_rel_err=0.0)
        with pytest.raises(NumericalGateError):
            tk.gate_on_numerical_correctness(bad_report, atol=1e-5, rtol=1e-5)

    def test_error_message_contains_atol(self):
        bad_report = NumericalReport(max_abs_err=1.0, max_rel_err=0.0)
        with pytest.raises(NumericalGateError, match="atol"):
            tk.gate_on_numerical_correctness(bad_report, atol=1e-5, rtol=1e-5)

    def test_raises_when_rel_err_exceeds_rtol(self):
        bad_report = NumericalReport(max_abs_err=0.0, max_rel_err=1.0)
        with pytest.raises(NumericalGateError):
            tk.gate_on_numerical_correctness(bad_report, atol=1e-5, rtol=1e-5)

    def test_error_message_contains_rtol(self):
        bad_report = NumericalReport(max_abs_err=0.0, max_rel_err=1.0)
        with pytest.raises(NumericalGateError, match="rtol"):
            tk.gate_on_numerical_correctness(bad_report, atol=1e-5, rtol=1e-5)

    def test_no_raise_when_within_tolerance(self):
        good_report = NumericalReport(max_abs_err=1e-9, max_rel_err=1e-9)
        tk.gate_on_numerical_correctness(good_report, atol=1e-5, rtol=1e-5)

    def test_no_raise_exactly_at_atol_boundary(self):
        atol = 1e-5
        report = NumericalReport(max_abs_err=atol, max_rel_err=0.0)
        tk.gate_on_numerical_correctness(report, atol=atol, rtol=1e-5)

    def test_raise_just_above_atol_boundary(self):
        atol = 1e-5
        report = NumericalReport(max_abs_err=atol + 1e-12, max_rel_err=0.0)
        with pytest.raises(NumericalGateError, match="atol"):
            tk.gate_on_numerical_correctness(report, atol=atol, rtol=1e-5)

    def test_numerical_gate_error_is_exception(self):
        assert issubclass(NumericalGateError, Exception)
