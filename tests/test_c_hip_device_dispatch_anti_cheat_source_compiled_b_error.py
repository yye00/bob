"""Error-path tests — invalid input raises ValueError, no silent success.

Feature 2449179e-2def-4769-ad3d-53912854b478.
"""

from __future__ import annotations

import pytest

from bob.cpp_hip_device_dispatch_anticheat import (
    scan_cpp_device_dispatch,
    verify_compiled_device_evidence,
)


class TestScanErrors:
    def test_none_sources_raises(self):
        with pytest.raises(ValueError):
            scan_cpp_device_dispatch(None)

    def test_bare_string_sources_raises(self):
        with pytest.raises(ValueError):
            scan_cpp_device_dispatch("__global__ void k(){}")

    def test_non_string_path_raises(self):
        with pytest.raises(ValueError):
            scan_cpp_device_dispatch({123: "code"})

    def test_non_string_text_raises(self):
        with pytest.raises(ValueError):
            scan_cpp_device_dispatch({"k.cpp": 42})

    def test_malformed_pair_raises(self):
        with pytest.raises(ValueError):
            scan_cpp_device_dispatch([("k.cpp",)])

    def test_non_pair_entries_raise(self):
        with pytest.raises(ValueError):
            scan_cpp_device_dispatch([1, 2, 3])


class TestVerifyErrors:
    def test_non_string_output_raises(self):
        with pytest.raises(ValueError):
            verify_compiled_device_evidence(None)

    def test_int_output_raises(self):
        with pytest.raises(ValueError):
            verify_compiled_device_evidence(1234)

    def test_empty_tool_raises(self):
        with pytest.raises(ValueError):
            verify_compiled_device_evidence("ncclAllReduce", tool="")

    def test_non_string_tool_raises(self):
        with pytest.raises(ValueError):
            verify_compiled_device_evidence("ncclAllReduce", tool=None)
