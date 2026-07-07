"""Boundary tests — empty / zero / minimum input returns a well-defined result.

Feature 2449179e-2def-4769-ad3d-53912854b478.

Verifies that empty or minimal inputs return well-defined results rather than
raising unexpected exceptions.
"""

from __future__ import annotations

from bob.cpp_hip_device_dispatch_anticheat import (
    CompiledEvidenceResult,
    DispatchScanResult,
    scan_cpp_device_dispatch,
    verify_compiled_device_evidence,
)


class TestScanBoundary:
    def test_empty_mapping_returns_result_not_raise(self):
        res = scan_cpp_device_dispatch({})
        assert isinstance(res, DispatchScanResult)
        assert res.files_scanned == 0
        assert res.has_device_dispatch is False
        assert res.passed is False

    def test_empty_iterable_returns_result(self):
        res = scan_cpp_device_dispatch([])
        assert isinstance(res, DispatchScanResult)
        assert res.files_scanned == 0
        assert res.passed is False

    def test_single_empty_source_file(self):
        res = scan_cpp_device_dispatch({"empty.cpp": ""})
        assert res.files_scanned == 1
        assert res.has_device_dispatch is False
        assert res.passed is False

    def test_details_is_string_for_empty(self):
        res = scan_cpp_device_dispatch({})
        assert isinstance(res.details, str)
        assert res.details


class TestVerifyBoundary:
    def test_empty_output_returns_result_not_raise(self):
        res = verify_compiled_device_evidence("")
        assert isinstance(res, CompiledEvidenceResult)
        assert res.inspected is False
        assert res.passed is False

    def test_whitespace_only_output_is_not_inspected(self):
        res = verify_compiled_device_evidence("   \n\t  ")
        assert res.inspected is False
        assert res.passed is False

    def test_minimal_non_matching_output(self):
        res = verify_compiled_device_evidence("main")
        assert res.inspected is True
        assert res.has_device_code is False
        assert res.has_rccl_symbol is False
        assert res.passed is False

    def test_details_is_string(self):
        assert isinstance(verify_compiled_device_evidence("").details, str)
