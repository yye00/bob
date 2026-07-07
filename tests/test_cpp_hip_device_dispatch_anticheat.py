"""Tests for the C++/HIP device-dispatch anti-cheat.

Feature 2449179e-2def-4769-ad3d-53912854b478.
"""

from __future__ import annotations

import pytest

from bob.cpp_hip_device_dispatch_anticheat import (
    CompiledEvidenceResult,
    DispatchScanResult,
    scan_cpp_device_dispatch,
    verify_compiled_device_evidence,
)


# --- scan_cpp_device_dispatch: genuine dispatch is accepted ----------------


class TestScanAcceptsGenuineDispatch:
    def test_kernel_def_plus_launch_site_passes(self):
        src = {
            "reduce.hip": (
                "__global__ void reduce(float* d) { d[0] += 1.0f; }\n"
                "void run() { hipLaunchKernelGGL(reduce, 1, 256, 0, 0, buf); }\n"
            )
        }
        res = scan_cpp_device_dispatch(src)
        assert res.has_kernel_def is True
        assert res.has_launch_site is True
        assert res.has_device_dispatch is True
        assert res.passed is True
        assert res.files_scanned == 1

    def test_triple_chevron_launch_passes(self):
        src = {"k.cu": "__global__ void f(){}\nvoid g(){ f<<<1, 32>>>(); }\n"}
        res = scan_cpp_device_dispatch(src)
        assert res.has_launch_site is True
        assert res.passed is True

    def test_module_launch_kernel_passes(self):
        src = {"mod.cpp": "void g(){ hipModuleLaunchKernel(fn,1,1,1,1,1,1,0,0,0,0); }"}
        res = scan_cpp_device_dispatch(src)
        assert res.has_launch_site is True
        assert res.passed is True

    def test_real_rccl_collective_passes(self):
        src = {
            "allreduce.cpp": (
                "void run(ncclComm_t c) {\n"
                "  ncclCommInitRank(&c, 4, id, rank);\n"
                "  ncclAllReduce(sbuf, rbuf, n, ncclFloat, ncclSum, c, stream);\n"
                "}\n"
            )
        }
        res = scan_cpp_device_dispatch(src)
        assert res.has_rccl_call is True
        assert res.has_device_dispatch is True
        assert res.passed is True


# --- scan_cpp_device_dispatch: cheats are rejected -------------------------


class TestScanRejectsCheats:
    def test_include_only_is_not_dispatch(self):
        src = {
            "fake.cpp": (
                '#include <rccl.h>\n'
                "float allreduce(const std::vector<float>& v) {\n"
                "  return std::accumulate(v.begin(), v.end(), 0.0f);\n"
                "}\n"
            )
        }
        res = scan_cpp_device_dispatch(src)
        assert res.has_device_dispatch is False
        assert res.passed is False

    def test_host_simulation_marker_flagged(self):
        src = {
            "sim.cpp": (
                "// simulate on host — no GPU here\n"
                "__global__ void k(){}\n"
                "void run(){ hipLaunchKernelGGL(k,1,1,0,0); }\n"
            )
        }
        res = scan_cpp_device_dispatch(src)
        # Even with a real launch site, an explicit simulation admission fails.
        assert res.sim_marker is not None
        assert res.passed is False

    def test_cpu_fallback_marker_flagged(self):
        src = {"f.hip": "// CPU fallback path\nint main(){ return 0; }"}
        res = scan_cpp_device_dispatch(src)
        assert res.sim_marker is not None
        assert res.passed is False

    def test_kernel_token_inside_comment_does_not_count(self):
        src = {
            "c.cpp": (
                "// this would use __global__ and hipLaunchKernelGGL( on a real gpu\n"
                "int main(){ return 0; }\n"
            )
        }
        res = scan_cpp_device_dispatch(src)
        assert res.has_kernel_def is False
        assert res.has_launch_site is False
        assert res.has_device_dispatch is False
        # "on a real gpu" is a sim marker; regardless, no dispatch => not passed.
        assert res.passed is False

    def test_kernel_def_without_launch_is_not_dispatch(self):
        src = {"only_def.hip": "__global__ void k(float* d){ d[0]=1; }\n"}
        res = scan_cpp_device_dispatch(src)
        assert res.has_kernel_def is True
        assert res.has_launch_site is False
        assert res.has_device_dispatch is False
        assert res.passed is False

    def test_non_cpp_files_ignored(self):
        src = {"notes.md": "hipLaunchKernelGGL( __global__ ncclAllReduce("}
        res = scan_cpp_device_dispatch(src)
        assert res.files_scanned == 0
        assert res.has_device_dispatch is False


# --- scan accepts iterable-of-pairs form -----------------------------------


class TestScanInputForms:
    def test_iterable_of_pairs(self):
        pairs = [("k.cu", "__global__ void f(){}\nvoid g(){ f<<<1,1>>>(); }")]
        res = scan_cpp_device_dispatch(pairs)
        assert res.passed is True

    def test_returns_dispatch_scan_result_type(self):
        assert isinstance(scan_cpp_device_dispatch({}), DispatchScanResult)


# --- verify_compiled_device_evidence ---------------------------------------


class TestVerifyCompiledEvidence:
    def test_amdgpu_device_code_detected(self):
        out = "0000000000001120 T __amdgpu_kernel_reduce\n.hip_fatbin section present"
        res = verify_compiled_device_evidence(out, tool="readelf")
        assert res.has_device_code is True
        assert res.passed is True

    def test_rccl_symbol_detected(self):
        out = "0000000000002000 T ncclAllReduce\n0000000000002100 T ncclCommInitRank"
        res = verify_compiled_device_evidence(out, tool="nm")
        assert res.has_rccl_symbol is True
        assert res.passed is True

    def test_cpu_only_binary_rejected(self):
        # nm on a CPU-only binary that merely linked rccl headers: only host syms.
        out = (
            "0000000000001000 T main\n"
            "0000000000001100 T _Z9allreduceRKSt6vectorIfSaIfEE\n"
            "                 U std::accumulate\n"
        )
        res = verify_compiled_device_evidence(out, tool="nm")
        assert res.has_device_code is False
        assert res.has_rccl_symbol is False
        assert res.passed is False

    def test_offload_bundle_marker_detected(self):
        out = "__CLANG_OFFLOAD_BUNDLE__hip-amdgcn-amd-amdhsa--gfx90a"
        res = verify_compiled_device_evidence(out)
        assert res.has_device_code is True
        assert res.passed is True

    def test_returns_result_type(self):
        assert isinstance(
            verify_compiled_device_evidence("x"), CompiledEvidenceResult
        )
