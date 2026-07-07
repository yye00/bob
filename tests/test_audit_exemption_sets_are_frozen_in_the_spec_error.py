"""Error-path tests for spec-frozen audit exemptions (feature 47b70bd7).

Invalid input raises ValueError and the function does not silently succeed.

AC: pytest: tests/test_audit_exemption_sets_are_frozen_in_the_spec_error.py
    — invalid input raises ValueError and the function does not silently
      succeed (error path)
"""

from __future__ import annotations

import pytest

from hippy.audit_exemptions import classify_op_exemption


class TestClassifyErrorPaths:
    def test_non_string_op_name_raises(self) -> None:
        with pytest.raises(ValueError):
            classify_op_exemption(123, result_size=0)  # type: ignore[arg-type]

    def test_empty_op_name_raises(self) -> None:
        with pytest.raises(ValueError):
            classify_op_exemption("", result_size=0)

    def test_whitespace_op_name_raises(self) -> None:
        with pytest.raises(ValueError):
            classify_op_exemption("   ", result_size=0)

    def test_negative_result_size_raises(self) -> None:
        with pytest.raises(ValueError):
            classify_op_exemption("sci.sparse.spmv", result_size=-1)

    def test_non_int_result_size_raises(self) -> None:
        with pytest.raises(ValueError):
            classify_op_exemption("sci.sparse.spmv", result_size="0")  # type: ignore[arg-type]

    def test_frozen_exempt_ops_wrong_type_raises(self) -> None:
        # A mutable set would let the implementer inject members — forbid it.
        with pytest.raises(ValueError):
            classify_op_exemption(
                "sci.sparse.spmv", result_size=0, frozen_exempt_ops=["sci.sparse.spmv"]  # type: ignore[arg-type]
            )

    def test_frozen_exempt_ops_mutable_set_raises(self) -> None:
        with pytest.raises(ValueError):
            classify_op_exemption(
                "sci.sparse.spmv", result_size=0, frozen_exempt_ops={"sci.sparse.spmv"}  # type: ignore[arg-type]
            )
