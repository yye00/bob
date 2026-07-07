"""Tests for the backend-required CALL-SITE check.

Feature 5420e867: the backend-required check MUST verify a real lib CALL,
not an import. The import-but-simulate cheat (import hipblas, reference it
only in a docstring, compute on the CPU) must FAIL.
"""

import pytest

from hippy.checks.backend_required_call_site import (
    has_real_call_site,
    has_simulation_marker,
)


# ---------------------------------------------------------------------------
# has_real_call_site — a real call to a backend function must be detected.
# ---------------------------------------------------------------------------

def test_real_hipblas_gemm_call_detected():
    src = "def gemm(a, b):\n    return hipblasSgemm(handle, a, b, out)\n"
    assert has_real_call_site(src) is True


def test_real_kernel_launch_detected():
    src = "hipModuleLaunchKernel(func, gx, gy, gz, bx, by, bz, 0, stream, args, None)"
    assert has_real_call_site(src) is True


def test_hipmalloc_call_detected():
    src = "ptr = hipMalloc(nbytes)"
    assert has_real_call_site(src) is True


def test_various_backend_calls_detected():
    for call in (
        "hipfftExec(plan, idata, odata)",
        "hiprtcCompileProgram(prog, 0, None)",
        "hiprandGenerate(gen, out, n)",
        "hipsolverSgetrf(handle, m, n, a)",
        "hipsparseScsrmv(handle, op, m, n)",
        "hipLaunchKernel(kern, grid, block)",
    ):
        assert has_real_call_site(call) is True, call


# ---------------------------------------------------------------------------
# The import-but-simulate cheat: import + docstring reference, NO real call.
# ---------------------------------------------------------------------------

def test_bare_import_is_not_a_call_site():
    src = "import hipblas  # noqa: F401\n\ndef gemm(a, b):\n    return a @ b\n"
    assert has_real_call_site(src) is False


def test_docstring_mention_is_not_a_call_site():
    src = (
        'def gemm(a, b):\n'
        '    """On a live GPU this dispatches to hipblasXgemm."""\n'
        '    # Simulate hipblasXgemm for 2-D arrays\n'
        '    return [[sum(x) for x in row] for row in a]\n'
    )
    assert has_real_call_site(src) is False


def test_from_import_is_not_a_call_site():
    src = "from hipblas import hipblasSgemm  # noqa: F401\nresult = plain_cpu(a, b)\n"
    assert has_real_call_site(src) is False


# ---------------------------------------------------------------------------
# has_simulation_marker — the import-but-simulate tells must be caught.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "marker",
    [
        "# Simulate hipblasXgemm for 2-D arrays",
        "On a live GPU this dispatches to hipblasXgemm",
        "# on gpu: this would launch a kernel",
        "In a real implementation we would call the driver",
        "This is a hip-backed simulation",
        "cpu fallback path",
        "fall back to cpu when no device",
        "fallback to numpy for correctness",
        "pure-python compute only",
        "we emulate the device here",
    ],
)
def test_simulation_markers_detected(marker):
    assert has_simulation_marker(marker) is True


def test_clean_source_has_no_simulation_marker():
    src = "def gemm(a, b):\n    return hipblasSgemm(handle, a, b, out)\n"
    assert has_simulation_marker(src) is False


def test_simulation_marker_is_case_insensitive():
    assert has_simulation_marker("SIMULATE HIP kernel here") is True


# ---------------------------------------------------------------------------
# Behaviour: import-but-simulate cheat => no call site AND a sim marker.
# ---------------------------------------------------------------------------

def test_import_but_simulate_cheat_fails_both_ways():
    cheat = (
        "import hipblas  # noqa: F401\n"
        "def gemm(a, b):\n"
        '    """On a live GPU this dispatches to hipblasXgemm."""\n'
        "    # Simulate hipblasXgemm for 2-D arrays (pure-python compute)\n"
        "    return [[0.0] * len(b[0]) for _ in a]\n"
    )
    assert has_real_call_site(cheat) is False
    assert has_simulation_marker(cheat) is True


def test_genuine_call_with_cpu_reference_has_call_site():
    src = (
        "def gemm(a, b):\n"
        "    out = hipMalloc(n)\n"
        "    hipblasSgemm(handle, a, b, out)\n"
        "    return out\n"
    )
    assert has_real_call_site(src) is True
