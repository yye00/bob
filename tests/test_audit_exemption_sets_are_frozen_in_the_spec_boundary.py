"""Boundary tests for spec-frozen audit exemptions (feature 47b70bd7).

Empty, zero, or minimum input returns a well-defined result rather than raising.

AC: pytest: tests/test_audit_exemption_sets_are_frozen_in_the_spec_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than
      raising (boundary case)
"""

from __future__ import annotations

from hippy.audit_exemptions import classify_op_exemption, get_frozen_exempt_ops


class TestFrozenSetBoundary:
    def test_get_frozen_exempt_ops_no_args(self) -> None:
        assert get_frozen_exempt_ops() == frozenset()


class TestClassifyBoundary:
    def test_size_zero_result_well_defined(self) -> None:
        verdict = classify_op_exemption("sci.sparse.spmv", result_size=0)
        assert verdict.exempt is True
        assert verdict.audit_fails is False

    def test_empty_frozen_set_nonzero_result(self) -> None:
        # Minimum frozen set (empty) with a non-zero result: not exempt, no raise.
        verdict = classify_op_exemption(
            "sci.sparse.spmv", result_size=1, frozen_exempt_ops=frozenset()
        )
        assert verdict.exempt is False
        assert verdict.authorized is False

    def test_minimum_op_name_single_char(self) -> None:
        verdict = classify_op_exemption("x", result_size=0)
        assert verdict.exempt is True

    def test_no_claim_defaults_to_not_exempt(self) -> None:
        verdict = classify_op_exemption("sci.linalg.norm", result_size=4)
        assert verdict.exempt is False
        assert verdict.audit_fails is False
