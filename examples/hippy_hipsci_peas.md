# PEAS — Plain English Application Spec: hippy + hipsci
#
# A clean-room, HIP-native GPU array + scientific-computing stack for AMD GPUs:
# a drop-in alternative to numpy (as `hippy`) and scipy (as `hipsci`), in the
# spirit of CuPy but written directly against ROCm/HIP — owing nothing to CuPy's
# codebase.
#
# This file is the SOURCE OF TRUTH for the bob build. Edit prose here; the
# extract-from-peas pipeline synthesizes verifiable acceptance criteria and the
# spec_quality_gate enforces their quality. Never hand-write the extracted YAML —
# edit this file.
#
# Format per feature:
#   ## <title>
#   Tier: <Core> | Priority: <critical|high|medium|low> | Slot: <F-HP-NNN>
#   <prose description>
#
# This spec was cross-reviewed by four independent oriented agents (ROCm/HIP
# feasibility, numpy/scipy API semantics, bob-PEAS conformance, scope/risk) and
# every blocker/major/minor finding has been folded back in. Empirically-verified
# hardware facts from that review are marked "(verified)".
#
# ============================================================================
# CONTEXT (read before the features)
# ============================================================================
# Goal: a user should be able to write `import hippy as hp` and `import hipsci
# as sp` and use them as drop-in replacements for `import numpy as np` and
# `import scipy as sp`, with the computation running on an AMD GPU. The public
# import surface is two top-level packages, `hippy` and `hipsci`, mirroring the
# numpy and scipy namespaces module-for-module (e.g. `hippy.linalg`,
# `hippy.fft`, `hippy.random`, `hipsci.fft`, `hipsci.linalg`, `hipsci.ndimage`,
# `hipsci.sparse`, `hipsci.signal`, `hipsci.special`, `hipsci.stats`).
#
# GOAL FRAMING (corrected after review): the goal is "COMPREHENSIVE CORE +
# TIERED LONG TAIL," not literal 100% numpy/scipy parity. numpy is ~600 public
# functions and scipy is far larger; cloning every function (datetime64,
# structured dtypes, scipy.optimize/integrate/spatial, etc.) is explicitly NOT
# v1. The load-bearing core (ndarray, JIT ufuncs/reductions, GEMM, linalg, FFT,
# RNG, the high-value scipy submodules) is built to a high parity bar; the long
# tail is tiered and may legitimately raise NotImplementedError. Every feature
# below states its IN-SCOPE function list so "done" is decidable; functions and
# whole modules ruled OUT for v1 are enumerated in the OUT-OF-SCOPE block.
#
# Hardware (the machine bob builds and validates on): a single node with 8x AMD
# Instinct MI300X (gfx942), ROCm 7.2.1, 224 Intel Xeon Platinum 8480C CPU cores.
# Commands and numbers in this spec are concrete for THIS machine, not portable
# guesses. The GPU architecture string is `gfx942:sramecc+:xnack-`; the HIP
# offload arch for runtime compilation is `gfx942` (verified live: 8 devices
# visible, HIPRTC compiles for gfx942, a hipBLAS SGEMM matched numpy to ~2e-4).
#
# ARCHITECTURE (decided — layered hybrid, validated live before authoring):
#   L0  Driver binding. Use AMD's official `hip-python` package as the low-level
#       binding to the HIP driver API, the HIPRTC runtime compiler, and the math
#       libraries (hipBLAS, hipFFT, hipRAND, hipSOLVER, hipSPARSE) and RCCL. The
#       installed ROCm is 7.2.1; the matching wheel is hip-python 7.2.1.* . This
#       layer is consumed ONLY through a thin internal facade module (see
#       F-HP-002) so the rest of hippy never imports `hip.*` directly. (verified:
#       hip-python 7.2.1.* is a real 64 MB compiled binding exposing ~769 driver
#       callables, ~1204 hipBLAS, ~547 hipSOLVER, ~614 hipSPARSE symbols.)
#   L1  Runtime core. Device/context management, a caching memory pool (to avoid
#       per-op hipMalloc), multi-stream scheduling, events, and HIP graph
#       capture/replay — all built on L0.
#   L2  ndarray. A strided N-dimensional array over device memory: full numeric
#       dtype set, views/slicing, broadcasting, contiguity tracking, host<->
#       device transfer.
#   L3  HIPRTC JIT engine. Python emits HIP C++ kernel source as strings
#       (templated on dtype/shape/op), compiles them with HIPRTC at runtime for
#       gfx942, and caches the compiled code objects. This is the engine for
#       elementwise ufuncs, reductions, and kernel fusion.
#   L4  Vendor-library ops. matmul/GEMM via hipBLAS (and hipBLASLt where it
#       helps), dense linalg via hipSOLVER/rocSOLVER, FFT via hipFFT, RNG via
#       hipRAND, sparse via hipSPARSE. We CALL the tuned libraries; we do not
#       reimplement BLAS/LAPACK/FFT.
#   L5  Dispatch / compatibility. Implement the array protocols
#       (`__array_ufunc__`, `__array_function__`), the Python Array API standard
#       (`__array_namespace__`), and a `get_array_module`-style helper.
#   L6  hipsci. The scipy mirror, layered on hippy.
#
# WHY NO HAND-MAINTAINED C++ (validated on this machine before authoring): the
# ONLY HIP C++ in the project is kernel source emitted by Python at runtime and
# compiled by HIPRTC. There is no .cpp/.hip source file checked into the repo, no
# hipcc invocation at install time, and no pybind11/nanobind native extension to
# build or maintain. Binding glue is provided by hip-python's prebuilt compiled
# modules. Implementers MUST preserve this property — adding a compiled C/C++
# extension or a build-time hipcc step is a design violation unless this spec is
# explicitly revised to allow it.
#
# CAVEAT — "no C++" does not mean "all vendor passthrough" (added after review):
# the following are GENUINE from-scratch algorithm work as JIT-generated kernels,
# NOT thin wrappers over a vendor call, because no bound ROCm library exposes
# them: device SORT (F-HP-304; rocPRIM/rocThrust are NOT bound by hip-python),
# DCT/DST (F-HP-500; hipFFT exposes only R2C/C2R/C2C/D2Z/Z2D/Z2Z — verified, no
# DCT/DST symbols), nonsymmetric eig (F-HP-301; hipSOLVER exposes NO geev/ggev —
# verified — only symmetric/Hermitian syevd/heevd and SVD), modified Bessel
# i0/i1 and digamma/beta (F-HP-504; not in the HIPRTC device math headers —
# verified i0f/i1f undeclared), and integer/choice/permutation RNG (F-HP-303;
# hipRAND gives only uniform/normal/lognormal/poisson). These carry citations
# for the algorithm used.
#
# HIPRTC COMPILE FLAGS (blocker fix from review): runtime kernel compilation MUST
# pass BOTH `--offload-arch=gfx942` AND `-I/opt/rocm-7.2.1/include`. (verified:
# with only the offload arch, `#include <hip/hip_complex.h>`, `hip_fp16.h`, and
# `hip_bf16.h` all fail "file not found", which would break EVERY complex/fp16/
# bf16 kernel; adding the include path fixes all four.) The include path is
# resolved through the L0 facade so a ROCm version bump changes one place.
#
# NO SILENT CPU FALLBACK (decided): hippy/hipsci never transparently fall back to
# CPU execution. An operation not implemented on the GPU MUST raise a clear
# NotImplementedError (never silently run on the host). numpy and scipy are
# permitted in the TEST path only; they MUST NOT be imported on any runtime code
# path of hippy/hipsci (enforced — F-HP-004).
#
# DROP-IN MODEL (decided — match CuPy + Array API): hippy mirrors the numpy
# namespace and hipsci mirrors the scipy namespace. Supported usage is
# `import hippy as hp` / `import hipsci as sp`. Full `import hippy as np`
# module-identity is NOT a goal. Because there is no CPU fallback, "drop-in"
# holds for programs that stay within the implemented surface; a program hitting
# an unimplemented function gets a clear error, not a degraded CPU path. The
# capstone (F-HP-603) validates drop-in on curated representative programs.
#
# ============================================================================
# VERIFICATION PHILOSOPHY (rewritten after review — this is the heart of the
# anti-cheat design and two of the three review blockers were here)
# ============================================================================
# Correctness is defined by agreement with numpy/scipy, built test-first against
# tests BLIND to the implementation. THREE oracles are used; oracle (b) is the
# primary gating oracle.
#
# Oracle (a) — CURATED upstream tests (non-gating signal, NOT alias-as-numpy).
#   REVIEW BLOCKER FIX: the original "copy numpy's whole test suite and alias
#   hippy as numpy" plan does NOT work — numpy/scipy test files import C-internals
#   (numpy._core, numpy.testing, Cython helpers) so >90% are UNCOLLECTABLE under
#   aliasing, not cleanly xfail-able. Instead: hand-select FUNCTION-LEVEL upstream
#   test cases (the value/semantics tests, not the C-API/memory-layout ones),
#   port them to `import hippy as hp` / `import hipsci as sp`, and run them as a
#   NON-GATING coverage signal. The xfail/skip taxonomy applies to these ported
#   tests only. This oracle measures breadth; it does not gate the build.
#
# Oracle (b) — GENERATED parity tests with RANDOMIZED inputs (PRIMARY GATE).
#   REVIEW BLOCKER FIX (gameability): a single FROZEN input is gameable (a kernel
#   that returns a baked-in constant, or host compute disguised behind a device
#   copy, would pass). So parity tests use RANDOMIZED inputs drawn at test time
#   from a per-test seed, and assert two things: (1) the hippy/hipsci result
#   matches a reference COMPUTED INSIDE THE TEST by an INDEPENDENT path, and
#   (2) execution evidence proves real device work happened (a HIPRTC module was
#   launched or a vendor-library call was made — observable via the runtime's
#   launch counter / HIP event timeline), so a host-only or constant
#   implementation fails even if its numbers happen to match.
#   The INDEPENDENT reference is obtained WITHOUT importing numpy at runtime by:
#   computing the reference at test-GENERATION time over many randomized seeds and
#   storing (seed -> expected) pairs the test replays; the implementation never
#   sees the generator and cannot import numpy (F-HP-004), so it cannot delegate.
#   For multi-seed coverage the generator emits a table of (seed, frozen expected)
#   entries; the test picks seeds and checks against the matching stored expected.
#
#   REVIEW BLOCKER FIX (non-unique outputs): some ops have implementation-defined
#   outputs (SVD/QR column signs, eigenvector signs, eigenvalue/sort order on
#   ties). Oracle (b) MUST use a PER-OP COMPARATOR REGISTRY, not blanket allclose:
#     - reconstruction comparator (factorizations: assert A ≈ U S V^H, Q R, etc.)
#     - sign/phase-canonicalizing comparator (SVD/QR/eig vectors)
#     - sorted/multiset comparator (eigenvalues, unique, sort with ties)
#     - statistical comparator (RNG: moments within k·sigma/sqrt(N))
#     - exact comparator (integer/bool ops, shapes, dtypes, sort of distinct keys)
#   Each op declares which comparator(s) apply; default is allclose for plain
#   elementwise/reduction float ops.
#
# Oracle (c) — PROPERTY-BASED tests for invariants that hold regardless of input
#   (e.g. `ifft(fft(x)) ≈ x`, `solve(A, A@x) ≈ x`, `(a+b) == (b+a)` elementwise,
#   sort is a permutation of input). Cheap, powerful, and impossible to satisfy
#   with a constant. Used where an invariant is natural.
#
# NUMERICAL BAR: allclose within a dtype-appropriate tolerance from the central
# tolerance policy (F-HP-008): exact for integer/bool; tight rtol/atol for
# float64; documented looser bounds for float32/float16/bfloat16 and complex;
# reductions over large N get a bound that grows with N (accumulation order).
#
# PERFORMANCE BAR: a measured win over numpy/scipy on THIS node's 224 CPU cores
# under F-HP-010's protocol, ABOVE a per-op size threshold that MUST be justified
# and bounded (the win must hold at the largest problem that fits in one GPU's
# HBM; the threshold may not be set arbitrarily high to dodge the gate). Below
# threshold is parity-only, which is expected and not a failure. Some domains may
# legitimately have NO winning size for the simple single-call case (single small
# FFT, single SpMV) — the threshold search is allowed to conclude "no win" for
# those without failing, and such cases are scoped to batched/large-N variants.
#
# ANTI-CHEAT (non-negotiable, applies to EVERY feature — a prior build of this
# spec cheated by wrapping numpy, so this is now enforced by a MECHANISM that does
# not depend on build order or on what ACs a feature gets synthesized):
#   (0) A ROOT conftest.py (F-HP-000, built FIRST) fails EVERY pytest session if any
#       file under src/ contains `import numpy`/`from numpy`/`import scipy`/`from
#       scipy`. numpy/scipy may appear ONLY under tests/. Because bob runs pytest to
#       verify every feature, this makes a numpy-wrapper implementation fail
#       automatically, no matter which feature it is or what order it builds in.
#   (1) THEREFORE every feature's implementation MUST be real HIP/GPU code: it calls
#       the L0 facade `hippy._hip` (driver / HIPRTC / vendor libs), or builds on
#       lower hippy layers that do — it MUST NOT `import numpy`/`import scipy` in src/.
#   (2) no hardcoded expected-output arrays in library code.
#   (3) results must come from actual device execution with launch evidence
#       (oracle b.2), not host numpy.
# bob's AST stub/mock detectors, the root conftest, and the launch-evidence
# assertion enforce these. A feature whose "implementation" imports numpy/scipy in
# src/, delegates to them, returns precomputed constants, or stubs the kernel MUST
# fail verification. RESTATE-IN-EVERY-FEATURE: each feature description below
# carries (or implies via "real HIP") this same ban so that even when bob
# re-synthesizes a feature's acceptance criteria from its prose, the no-numpy /
# must-use-HIP requirement is present in the prose the synthesizer reads.
#
# RATCHET ANTI-GAMING (review fix): the curated-suite pass-rate ratchet (F-HP-006)
# is non-gating, and the xfail/skip RATIO is itself tracked and bounded — a batch
# of new `NOT_YET_IMPLEMENTED` skips that pushes the skip ratio above a threshold
# is flagged for review rather than silently accepted, so coverage cannot be
# "won" by skipping the hard tests.
#
# MEASUREMENT DISCIPLINE (mirrors the rccl PEAS): every performance claim comes
# from the fixed F-HP-010 protocol — warmup, multiple timed repeats, device sync
# bracketing the GPU region, report of median + noise band. A win is real only
# when the GPU median beats the CPU median by more than the combined noise band,
# same session, this machine. Internet/prior-session numbers are context only.
#
# CITATIONS (mandatory): any algorithm (GPU radix sort, Makhoul DCT construction,
# Bessel approximation, etc.), tolerance rationale, or external claim pulled from
# the internet MUST be recorded with its source (URL or paper title+venue+year) in
# the feature's evidence/design note. Uncited external numbers are not admissible.
#
# ============================================================================
# OUT OF SCOPE FOR v1 (explicit, so coverage gates are not measured against these)
# ============================================================================
#   - dtypes: datetime64/timedelta64, structured/record dtypes, void, fixed-width
#     string/unicode ('S'/'U'), object dtype. (Numeric dtypes only — F-HP-101.)
#     NOTE: bfloat16 is supported as a HIPPY-ONLY dtype; it is NOT a numpy dtype,
#     so bfloat16 has NO numpy parity oracle and is validated by property/self-
#     consistency tests only.
#   - numpy: np.vectorize, np.save/load/savez (IO), genfromtxt/loadtxt, masked
#     arrays, np.poly1d class (functional polyval/polyfit ARE in scope).
#   - scipy whole modules deferred: scipy.optimize, scipy.integrate, scipy.spatial,
#     scipy.cluster, scipy.odr, scipy.io. (fft/linalg/ndimage/sparse/special/
#     signal/stats/interpolate subsets ARE in scope, Phase 6.)
#   - linalg: general nonsymmetric eig is IN scope but built by hand (no vendor
#     primitive); generalized eig (A,B) and expm are DEFERRED unless a clean
#     algorithm is cited and approved.
#   - multi-GPU: v1 targets ONE GPU by default; device selection across the 8
#     GPUs is a single explicit feature (F-HP-011). Collective/multi-GPU compute
#     (RCCL) is OUT of v1 scope — RCCL is named in L0 only for completeness.
#
# DEPENDENCY / ENVIRONMENT NOTES:
#   - Python 3.12; numpy 2.4.x and scipy (current) installed FOR TESTS ONLY.
#   - hip-python pinned to 7.2.1.* (matches ROCm 7.2.1); facade F-HP-002 localizes it.
#   - HIPRTC flags: `--offload-arch=gfx942 -I/opt/rocm-7.2.1/include`.
#   - Workspace: fresh dir (default ~/hippy), one repo, two installable packages
#     `hippy` and `hipsci` (hipsci depends on hippy).
#   - numpy 2.x promotion: type promotion MUST follow NEP 50 (value-independent;
#     Python scalars are weak). Stating "common cases" is insufficient — NEP 50
#     is the contract (F-HP-101).
#
# CITATION REFERENCES (bob MUST re-verify live and quote accurately):
#   - hip-python: github.com/ROCm/hip-python ; rocm.docs.amd.com/projects/hip-python/
#   - HIP / HIPRTC: rocm.docs.amd.com/projects/HIP/
#   - hipBLAS/hipSOLVER/hipFFT/hipRAND/hipSPARSE: rocm.docs.amd.com/projects/<name>/
#   - numpy reference: numpy.org/doc/stable/reference/ ; NEP 50:
#     numpy.org/neps/nep-0050-scalar-promotion.html
#   - scipy reference: docs.scipy.org/doc/scipy/reference/
#   - Python Array API standard: data-apis.org/array-api/latest/
#   - DCT via FFT (Makhoul 1980, IEEE TASSP); GPU radix sort (Merrill & Grimshaw
#     2011) — bob MUST fetch and cite the actual algorithm sources it uses.
#   - CuPy (ARCHITECTURE reference only, never a code source): docs.cupy.dev/
#
# PERMANENT-FORWARD-CARRY (bob infra carry-forward) — see F-HP-001.
#
# ============================================================================
# PHASE 0 — bob infra acknowledgement
# ============================================================================

## Permanent-forward-carry acknowledgement (bob infra carry-forward)
Tier: Core | Priority: low | Slot: F-HP-001
This feature exists only to satisfy bob's permanent-forward-carry
auditor, which requires the canonical infra-recovery feature IDs
F-R7-478, F-R7-479, and F-R7-553 to be present in every spec passed
to `plan --create`. Those are bob's own internal bootstrap features
(unlimited spawn-layer retry, RCA-layer needs-human auto-reset, and
the slopsquatting first-party allowlist) and are not relevant to the
hippy/hipsci work; this acknowledgement records their IDs so the
auditor passes. Acceptance: this file contains the tokens F-R7-478,
F-R7-479, and F-R7-553. Error/boundary: no code is required and no
source file is created; the feature is satisfied purely by token
presence in this spec.

# ============================================================================
# PHASE 1 — harness: environment, L0 facade, oracles, measurement, anti-cheat
# These have no dependency on the array library and must land first.
# ============================================================================

## Global anti-cheat conftest — ban numpy/scipy in src and require HIP, enforced for every test session
Tier: Core | Priority: critical | Slot: F-HP-000
THE most important feature: it makes the whole project honest and it
MUST exist before any other src code is trusted. A prior build of this
spec CHEATED — every feature was implemented as a thin numpy/scipy
wrapper (`import numpy as np`, `import scipy.special`) with ZERO HIP
code, and the per-feature tests passed because a numpy wrapper trivially
matches the numpy oracle. This feature makes that impossible by a
mechanism that does not depend on build order or on what acceptance
criteria later features happen to get: a ROOT `conftest.py` at the
workspace root, which pytest auto-loads for EVERY test session (every
feature bob builds runs pytest, so every feature is subject to it).

The root `conftest.py` MUST, at collection time, fail the ENTIRE test
session (call pytest.exit / raise UsageError) if ANY of these hold:
(1) any file under `src/` contains a forbidden CPU-backend import —
`import numpy`, `from numpy`, `import scipy`, or `from scipy` (scan the
source text of every `src/**/*.py`; the ONLY allowed numpy/scipy imports
in the entire repo are under `tests/`); (2) once the facade exists,
`hippy` or `hipsci` cannot be imported. It MUST also install an import
hook for the test process that raises if `numpy`/`scipy` is imported as
a side effect of importing `hippy`/`hipsci` themselves (runtime path
must be numpy-free). Provide `tests/conftest.py` too if needed, but the
ROOT conftest is the load-bearing one. Acceptance: with a planted
`import numpy` in any `src/` file, a bare `pytest` exits non-zero with a
message naming the offending file; with clean src, collection proceeds.
Error/boundary: the scan MUST ignore the substring inside comments/
docstrings only if it is not an actual import statement (match import
statements, not the word "numpy" in prose); a `src/` tree with no files
yet does not crash the scan. This feature creates ONLY the conftest and
its self-test; it has no dependencies and must be buildable first.
Because it forbids numpy/scipy in src GLOBALLY, every subsequent feature
is forced to implement real HIP/GPU code (via `hippy._hip`, HIPRTC
kernels, or the vendor libraries) rather than wrapping numpy.

CRITICAL — the root conftest is load-bearing and MUST NOT be reduced to
a sys.path shim. If another feature needs `src/` on the import path, it
MUST ADD to the existing conftest (or use a pyproject/editable install),
never OVERWRITE the conftest with a bare `sys.path.insert(...)` stub. The
self-test for this feature MUST assert that the conftest actually aborts
the session on a planted numpy import (not merely that the file exists),
so a stub replacement is detectable. NO feature may delete or shrink the
anti-cheat logic in the root conftest; doing so is itself a build defect.
STANDING RULE FOR EVERY FEATURE: implementations live under `src/` and
MUST be real HIP/GPU code — they MUST NOT `import numpy` or `import
scipy` in any `src/` file (those are allowed ONLY under `tests/`). A
feature that imports numpy/scipy in src/ will fail the conftest gate and
must be rebuilt against the HIP facade.

## Reproducible environment and two-package project skeleton
Tier: Core | Priority: critical | Slot: F-HP-002
Establish the project skeleton and reproducible environment on this
machine. Create one repository exposing two installable packages,
`hippy` and `hipsci` (hipsci depends on hippy), with pyproject config
for both and a single dev-install path. Create the thin internal L0
facade module `hippy._hip` that is the ONLY place importing hip-python
(`from hip import hip, hiprtc, hipblas, hipfft, hiprand, hipsolver,
hipsparse`); it centralizes the version pin (hip-python 7.2.1.*) and
the HIPRTC compile flags (`--offload-arch=gfx942 -I/opt/rocm-7.2.1/
include`). The facade exposes device count, device properties, and a
`hip_check` error wrapper. Acceptance: both packages import; the
facade reports exactly 8 devices and a device name containing
"gfx942" on this machine; the facade exposes the compile-flag list
including the rocm include path. Error/boundary: importing the facade
on a machine with no HIP runtime MUST raise a clear, actionable error
naming the missing component, not an opaque ImportError; a grep of the
source tree finds NO `import hip` / `from hip` outside `hippy._hip`.

## HIP error-checking primitive and end-to-end toolchain canary
Tier: Core | Priority: critical | Slot: F-HP-003
Provide the error primitive used everywhere: a wrapper that unpacks
hip-python's (status, *values) return tuples, raises a typed
HippyHIPError carrying the HIP status name on a non-zero status, and
returns the unpacked values on success. Add a self-contained canary
test that, using ONLY the facade, allocates device memory, copies a
host buffer up, runs a trivial HIPRTC kernel compiled for gfx942 that
writes a known pattern, copies back, and asserts the pattern.
Acceptance: the canary passes on this machine; HippyHIPError exposes
the status name. Error/boundary: a deliberately-malformed kernel
source MUST raise HippyHIPError surfacing the HIPRTC compile log (not
hang, not segfault, not a bare nonzero return); a forced allocation
failure path raises the typed error.

## Runtime import guard — numpy/scipy forbidden on runtime paths
Tier: Core | Priority: critical | Slot: F-HP-004
Enforce the no-CPU-oracle-in-production rule mechanically. Provide a
guard test that, in a subprocess, installs an import hook that RAISES
if `numpy` or `scipy` (or submodules) are imported as a side effect of
importing `hippy`/`hipsci` and exercising their core paths (array
creation, a ufunc, a reduction, a matmul). Acceptance: the guard
passes for the real library and the allowed exception surface (test
files) is documented. Error/boundary: the guard test MUST itself be
proven effective by a negative control — a deliberately-planted
`import numpy` on a runtime path MUST make the guard FAIL — so the
guard cannot silently pass by being a no-op.

## Caching memory pool, device/runtime context, and streams
Tier: Core | Priority: critical | Slot: F-HP-009
Implement L1: a device/runtime context on the facade; a CACHING
MEMORY POOL that reuses freed device blocks (size-bucketed, exposes a
high-water + reuse-count statistic and a launch counter used by the
anti-cheat evidence in oracle b.2); and a stream abstraction with a
default per-thread stream plus explicit named streams, synchronization,
and events. Acceptance: allocating/freeing many arrays does not grow
process device memory unboundedly (pool reuse observable via the
statistic); work on two streams overlaps; events order cross-stream
deps; the launch counter increments on a real kernel launch. Error/
boundary: an allocation request larger than free device memory raises
a typed out-of-memory error (NOT a silent host allocation, NOT a
crash) reporting requested vs available bytes; the pool releases blocks
back under an explicit `free_all_blocks`. Depends on F-HP-002, F-HP-003.

## Multi-GPU device selection (single-GPU compute, explicit device control)
Tier: Core | Priority: medium | Slot: F-HP-011
Provide explicit device selection across the machine's 8 GPUs: a
`Device(id)` context manager / `set_device`/`get_device` API so a user
can place arrays and launches on a chosen GPU. v1 compute stays
single-GPU (no cross-device collectives); this feature only governs
WHICH single GPU is used and ensures an array's device is tracked.
Acceptance: arrays allocate on the selected device; operating on two
arrays from different devices raises a clear error rather than
producing wrong results. Error/boundary: selecting an out-of-range
device id raises; mixing devices in one op raises a typed
cross-device error. Depends on F-HP-009.

## Fixed performance measurement protocol and harness
Tier: Core | Priority: critical | Slot: F-HP-010
Implement the measurement discipline used by every perf feature: a
timing harness that, given a GPU callable and an equivalent CPU
(numpy/scipy) callable, performs warmup iterations, runs N timed
repeats with device synchronization bracketing the GPU region,
discards warmup, and reports median + a noise band (MAD or IQR) for
each. It exposes one decision: "GPU win is real" iff GPU median beats
CPU median by more than the combined noise band. It records machine
context (GPU arch, ROCm version, CPU core count) per measurement.
Acceptance: the harness returns medians, noise bands, and the
boolean decision for a sample workload; the decision is False when GPU
and CPU bands overlap. Error/boundary: the harness MUST reject a
measurement with too few repeats or zero warmup (raises), so a noisy
single-shot timing cannot be reported as a win. (numpy/scipy here are
the CPU BASELINE callables in the test harness, not a runtime import of
hippy — consistent with F-HP-004.) Depends on F-HP-009.

## Curated upstream test port (non-gating coverage signal) + xfail taxonomy
Tier: Core | Priority: high | Slot: F-HP-005
Build oracle (a): hand-select FUNCTION-LEVEL value/semantics test cases
from numpy's and scipy's upstream suites (NOT the C-API/memory-layout/
internal tests), port each to `import hippy as hp` / `import hipsci as
sp`, and run them as a NON-GATING coverage signal. Do NOT attempt to
alias hippy as the numpy module and run the upstream suite wholesale
(review-verified to be >90% uncollectable due to C-internal imports).
Every skipped/xfailed ported test carries a machine-readable reason
from a fixed taxonomy (CPU_C_API, HOST_MEMORY_LAYOUT, DTYPE_NA_ON_DEVICE,
OUT_OF_SCOPE_V1, NOT_YET_IMPLEMENTED). Acceptance: the ported suite
collects and runs without crashing; a pass/skip/xfail/fail summary is
emitted; every skip/xfail has a taxonomy reason. Error/boundary: a
ported test with NO taxonomy reason on its skip MUST cause the harness
summary step to fail (no untagged skips). Depends on F-HP-002.

## Generated parity-test framework — randomized inputs, comparator registry, launch evidence
Tier: Core | Priority: critical | Slot: F-HP-007
Build oracle (b), the PRIMARY gate. A generator that, for a declared
op + dtype list, emits standalone pytest files which: (1) draw inputs
from a per-test seed at run time; (2) compare the hippy/hipsci result
to an INDEPENDENT reference via the op's comparator from a PER-OP
COMPARATOR REGISTRY — allclose (default), reconstruction (factorizations),
sign/phase-canonical (SVD/QR/eig vectors), sorted/multiset (eigenvalues,
unique, tied sorts), statistical (RNG), or exact (int/bool/shape/dtype);
(3) assert LAUNCH EVIDENCE that real device work occurred (the F-HP-009
launch counter advanced or a vendor-lib call was made), so a host-only
or constant implementation fails even if numbers match. The independent
reference is produced at test-GENERATION time over many seeds (numpy/
scipy run by the generator, never by the test at run time) and stored as
(seed -> expected) entries the test replays; the implementation never
imports numpy (F-HP-004) and cannot see the generator. Acceptance: a
generated test for `add` passes on a correct kernel; the SAME test FAILS
on (i) a constant-returning stub, (ii) a host-numpy implementation
(no launch evidence), and (iii) a wrong-math kernel — proving the oracle
is not gameable. Error/boundary: an op with no registered comparator
MUST fail generation with a clear error (no silent allclose default for
ops known to be non-unique). Depends on F-HP-009.

## Dtype-aware tolerance policy
Tier: Core | Priority: high | Slot: F-HP-008
Define and centralize the numerical tolerance policy both oracles call:
exact equality for integer/bool; tight rtol/atol for float64; looser,
documented and CITED rtol/atol for float32, float16, bfloat16; defined
rules for complex64/complex128; and an N-dependent loosening for
reductions (accumulation order). Provide one function returning
(rtol, atol) for a (dtype, op-class). Acceptance: the function returns
tolerances for every supported dtype/op-class; parity tests obtain
their tolerance only from here. Error/boundary: requesting a tolerance
for an unsupported dtype raises rather than returning a silent default;
bfloat16 (no numpy oracle) routes to property/self-consistency rules,
not numpy-allclose. Depends on F-HP-007.

## Upstream pass-rate ratchet (non-gating) with bounded skip ratio
Tier: Core | Priority: medium | Slot: F-HP-006
Record the curated-suite (oracle a) pass count to a tracked baseline
and surface a regression when a previously-passing ported test newly
fails, while letting the total ratchet upward. This signal is
NON-GATING (it informs, it does not block the build). Additionally
track the xfail/skip RATIO; a change that pushes the skip ratio above a
configured threshold (default e.g. 0.40) is FLAGGED for review so
coverage cannot be "won" by mass-skipping hard tests. Acceptance: the
ratchet detects a planted regression and an over-threshold skip-ratio
jump. Error/boundary: a missing baseline file initializes cleanly
(first run) rather than erroring. Depends on F-HP-005.

# ============================================================================
# PHASE 2 — ndarray core
# ============================================================================

## ndarray object: device buffer, dtype, shape, strides, base tracking
Tier: Core | Priority: critical | Slot: F-HP-100
Implement the central N-dimensional array over pool-backed device
memory (F-HP-009). It carries shape, strides, dtype, device pointer,
offset, owning device id (F-HP-011), and tracks C/F contiguity and a
`.base` reference (for view/copy introspection). Provide the
attributes mirroring numpy.ndarray: shape, ndim, size, dtype, itemsize,
nbytes, strides, T, base. Construction is from shape+dtype
(uninitialized); the array refs its pool allocation with correct
lifetime (drop returns the block to the pool). Acceptance: attributes
match numpy for a matrix of shapes/dtypes; freeing an array returns its
block to the pool (observable). Error/boundary: constructing with a
negative or overflowing shape raises a typed error; `.base` is None for
an owning array and the parent for a view. Depends on F-HP-009.

## Numeric dtype system with NEP 50 promotion
Tier: Core | Priority: critical | Slot: F-HP-101
Implement the numeric dtype system: bool; int8/16/32/64; uint8/16/32/64;
float16, bfloat16, float32, float64; complex64, complex128. Provide
numpy-compatible dtype objects/names, itemsize, kind, and type-promotion
/ result-type rules following NEP 50 (value-independent; Python scalars
are weak — e.g. float32 + python-float -> float32, uint64 + int64 ->
float64). Map each dtype to its HIP C++ type string for codegen
(complex via hip/hip_complex.h, half via hip_fp16.h, bf16 via
hip_bf16.h — all requiring the F-HP-002 include path). Acceptance:
result_type matches numpy 2.4 (NEP 50) for representative pairs;
every dtype yields a valid HIP C++ type string that compiles.
Error/boundary: an unsupported/aliased dtype request raises; bfloat16
is flagged as hippy-only (no numpy result_type oracle) and validated
by self-consistency. Depends on F-HP-100.

## Host<->device transfer and array creation routines
Tier: Core | Priority: critical | Slot: F-HP-102
Implement transfer and creation: `asarray`/`array` from a host buffer
or another hippy array; `.get()`/`asnumpy` copy back to host (this is
the explicit, intentional boundary, not a silent fallback); and the
creation routines `empty`, `zeros`, `ones`, `full`, `arange`,
`linspace`, `eye`, `identity`, plus `*_like`. zeros/ones/full are real
device fills (memset or fill kernel), NOT host arrays uploaded.
Acceptance: parity (oracle b) vs numpy for each routine across dtypes;
a fill is proven to run on device (launch evidence). Error/boundary:
`asarray` of a non-contiguous or dtype-incompatible host buffer is
handled per numpy (copy as needed); an oversized creation raises the
F-HP-009 OOM error. Depends on F-HP-101.

## Indexing, slicing, views, reshape, transpose
Tier: Core | Priority: critical | Slot: F-HP-103
Implement basic indexing/slicing producing VIEWS sharing the parent
buffer with adjusted shape/strides/offset (no copy): integer indexing,
stepped slices, ellipsis, newaxis, negative indices. Implement
`reshape` (view when stride-compatible, else copy — using numpy's
stride predicate, not C/F flags alone), `ravel`, `flatten` (copy),
`transpose`/`.T`, `swapaxes`, `moveaxis`. Writing through a view
affects the parent; `.base` reflects the relationship. Acceptance:
parity of values AND view/copy semantics (write-through, `.base`,
`may_share_memory`) vs numpy. Error/boundary: an out-of-bounds index
raises IndexError; a reshape to an incompatible size raises; a
non-stride-compatible reshape returns a copy (asserted). Depends on
F-HP-100.

## Broadcasting and contiguity utilities
Tier: Core | Priority: critical | Slot: F-HP-104
Implement numpy broadcasting as a shape/stride computation
(`broadcast_shapes`, `broadcast_to` as a zero-copy stride trick),
and the contiguity helpers `ascontiguousarray`, `asfortranarray`, and a
strided-copy kernel that materializes an arbitrary strided array to
contiguous layout. These underpin every elementwise op on
non-trivially-strided inputs. Acceptance: broadcast shape outcomes
match numpy; the strided-copy kernel reproduces a strided view
contiguously (parity + launch evidence). Error/boundary: incompatible
broadcast shapes raise a ValueError matching numpy's; a 0-d and
0-size array broadcast correctly. Depends on F-HP-103.

# ============================================================================
# PHASE 3 — HIPRTC JIT engine: ufuncs, reductions, fusion, fancy indexing
# (F-HP-200 split into F-HP-200 + F-HP-207 per review: gate downstream on the minimal
# contiguous engine first so progress is not all-or-nothing.)
# ============================================================================

## HIPRTC codegen+cache engine — minimal contiguous-1D
Tier: Core | Priority: critical | Slot: F-HP-200
Implement the minimal core of L3: take a kernel recipe (op body +
participating dtypes), EMIT HIP C++ source as a Python string for the
CONTIGUOUS 1-D case, compile with HIPRTC using the F-HP-002 flags
(`--offload-arch=gfx942 -I/opt/rocm-7.2.1/include`), load the code
object, and cache the callable keyed by (recipe, dtypes). Handle launch
config (block/grid from element count) and argument packing, and
increment the F-HP-009 launch counter. Downstream Phase-3 features gate
on THIS minimal engine, not the general strided one (F-HP-207).
Acceptance: a generated contiguous elementwise kernel compiles and runs
for float32/float64/int32/complex64; the second launch of the same
recipe hits the cache (no recompile, observable). Error/boundary: a
recipe that fails to compile raises HippyHIPError carrying the HIPRTC
log; an unsupported dtype in a recipe raises before compile. Depends on
F-HP-104.

## HIPRTC engine — general strided / broadcast iteration
Tier: Core | Priority: critical | Slot: F-HP-207
Extend F-HP-200 to generate kernels that iterate arbitrary strided and
broadcast inputs (N-D index -> per-operand offset), so elementwise ops
work directly on views without a forced contiguous copy. Acceptance: a
generated kernel on a transposed/broadcast input matches the contiguous
result (parity + launch evidence) and avoids materializing a contiguous
temp when strides allow. Error/boundary: a kernel over a 0-size or 0-d
strided input runs without launching out-of-range threads. Depends on
F-HP-200.

## Elementwise unary/binary ufuncs (arith, comparison, logical, bitwise, core math)
Tier: Core | Priority: critical | Slot: F-HP-201
Implement the core numpy ufuncs as JIT elementwise kernels honoring
broadcasting, NEP 50 output dtype, `out=`, and `where=`: arithmetic
(add, subtract, multiply, divide, true_divide, floor_divide, power,
mod, negative, abs), comparison (greater, greater_equal, less,
less_equal, equal, not_equal), logical (and/or/not/xor), bitwise
(and/or/xor/invert, left_shift, right_shift), and core math unary (exp,
log, log2, log10, expm1, log1p, sqrt, cbrt, square, reciprocal, sign).
Acceptance: parity (oracle b) across dtypes with F-HP-008 tolerances,
on strided/broadcast inputs; `out=` and `where=` honored. Error/
boundary: integer divide-by-zero and domain errors (log of negative)
follow numpy's behavior (inf/nan, not crash); shape-incompatible
operands raise. Depends on F-HP-207.

## ufunc methods (.reduce/.accumulate/.reduceat/.outer/.at)
Tier: Core | Priority: high | Slot: F-HP-206
Implement the ufunc method surface that standalone reductions do not
cover: `reduce`, `accumulate`, `reduceat`, `outer`, and `at`
(unbuffered in-place, including duplicate-index accumulation via atomics
for the add case). `np.add.at(a, idx, v)` is semantically distinct from
`a[idx]+=v` and must accumulate at duplicate indices. Acceptance:
parity vs the equivalent numpy ufunc methods, including duplicate-index
`at` accumulation. Error/boundary: `reduceat` with an out-of-range index
list raises; `at` on duplicate indices produces the summed (not
last-write) result for add. Depends on F-HP-201 and F-HP-105.

## Transcendental, rounding, and floating-point ufuncs
Tier: Core | Priority: high | Slot: F-HP-202
Extend the ufunc set: trig (sin, cos, tan, arcsin, arccos, arctan,
arctan2, hypot), hyperbolic (sinh, cosh, tanh + inverses), rounding
(floor, ceil, trunc, rint, round), float inspection (isnan, isinf,
isfinite, signbit, copysign, nextafter, ldexp, frexp, fmod). Same
broadcasting/out/where/dtype rules and oracle-b gates as F-HP-201.
Acceptance: parity across dtypes within tolerance. Error/boundary:
arcsin/arccos outside [-1,1] yield nan like numpy (no crash); rounding
half-to-even matches numpy. Depends on F-HP-201.

## Reductions and scans
Tier: Core | Priority: critical | Slot: F-HP-203
Implement reductions as JIT kernels with correct axis/keepdims/dtype
semantics and numerically careful accumulation (pairwise/tree reduction
for floats): sum, prod, mean, min, max, argmin, argmax, all, any, and
NaN-aware variants (nansum, nanmean, nanmin, nanmax, nanprod). Implement
cumulative scans cumsum, cumprod. Single-axis, multi-axis, and whole-
array reductions work, including over strided views. Tolerances account
for accumulation order (F-HP-008). Acceptance: parity vs numpy.
Error/boundary: argmin/argmax of an empty axis raises like numpy; sum
of an empty array returns the identity (0); reduction dtype upcasting
(e.g. bool.sum -> int) matches numpy. Depends on F-HP-207.

## Advanced (fancy) indexing and boolean masking with scatter semantics
Tier: Core | Priority: high | Slot: F-HP-105
Implement advanced indexing: integer-array indexing (gather) and
assignment (scatter), boolean-mask selection and assignment, `take`,
`compress`, `where` (3-arg), `nonzero`. REVIEW FIX: scatter MUST honor
numpy's duplicate-index semantics — plain assignment `a[idx]=v` is
last-write (defined order), while accumulating assignment uses atomics;
naive parallel scatter races and is incorrect. Acceptance: parity vs
numpy including the broadcasting interactions of fancy indexing AND
duplicate-index assignment behavior. Error/boundary: out-of-bounds
fancy index raises; a boolean mask of wrong shape raises; duplicate
indices in plain assignment yield a numpy-consistent result. (Cross-
phase dependency, intentional.) Depends on F-HP-104 and F-HP-207.

## Kernel fusion for elementwise expression chains
Tier: Core | Priority: high | Slot: F-HP-204
Add a fusion path so a chain of elementwise ops (and an optional
trailing reduction) is generated as a SINGLE HIPRTC kernel, eliminating
intermediate device buffers. Provide a clean-room `fuse`-style
decorator/utility recording an expression and compiling it through the
JIT engine. Acceptance: a fused chain matches the unfused result
(oracle b), allocates fewer intermediates (observable via the pool
statistic), and under F-HP-010 is at least as fast as the unfused
sequence on a non-trivial expression. Error/boundary: a fused
expression mixing incompatible shapes raises at trace time, not at
launch. Depends on F-HP-203.

## HIP graph capture and replay for repeated pipelines
Tier: Core | Priority: medium | Slot: F-HP-205
Expose HIP graph capture/replay so a repeated launch sequence (e.g. an
iterative solver loop) is captured once and replayed with lower
per-iteration overhead. Provide a context-manager capture API and a
replay handle. The implementation MUST live under `src/hippy/` (e.g.
`hippy/graph.py`) — it MUST NOT create a top-level `src/hip/` package or
any module named `hip`/`hiprtc`/`hipblas`/`hipfft`/`hiprand`/`hipsolver`/
`hipsparse`, because such a name SHADOWS the real hip-python distribution
and silently breaks `from hip import hip` for the ENTIRE workspace,
forcing every feature into host-backed fallbacks. Acceptance: a captured
graph reproduces the eager result exactly; under F-HP-010 replay reduces
per-iteration overhead for a many-small-launch loop; no `src/hip/`
package exists. Error/boundary: capturing an operation that allocates
from the pool mid-capture is either supported or raises a clear error
(no silent corruption). Depends on F-HP-009 and F-HP-200.

# ============================================================================
# PHASE 4 — linear algebra, FFT, random (vendor-library backed where possible)
# ============================================================================

## matmul / dot via hipBLAS
Tier: Core | Priority: critical | Slot: F-HP-300
Implement `matmul`/`@`, `dot`, `vdot`, `inner`, `tensordot` backed by
hipBLAS GEMM/GEMV (and strided-batched GEMM for stacked matrices),
handling row-major arrays via the transpose/leading-dimension
convention. Support float32/float64 and complex64/complex128; fp16/
bf16 GEMM may route through hipBLASLt where beneficial. (einsum is
SEPARATE — F-HP-306.) Acceptance: parity vs numpy (oracle b,
reconstruction not needed — GEMM output is unique) within F-HP-008
tolerances. Error/boundary: non-conformable shapes raise a clear error
(never silently truncate); a 1-D·1-D dot returns a scalar; empty-matrix
products follow numpy. Depends on F-HP-104 and the facade hipBLAS handle.

## einsum (enumerated supported index patterns)
Tier: Core | Priority: high | Slot: F-HP-306
Implement `einsum` for an ENUMERATED, documented set of index patterns
(not "common subset"): pairwise contraction (`ij,jk->ik`), batched
(`bij,bjk->bik`), transposition/permutation (`ij->ji`, `...ij->...ji`),
diagonal (`ii->i`), trace (`ii->`), and full reduction (`ij->`), with
ellipsis broadcasting for the listed forms. Contractions route to
hipBLAS where expressible, else to a JIT reduction kernel. Acceptance:
parity vs numpy.einsum for every enumerated pattern. Error/boundary: an
unsupported einsum pattern raises NotImplementedError naming the
pattern (no silent wrong result); mismatched index dimensions raise.
Depends on F-HP-300 and F-HP-203.

## hippy.linalg — decompositions and solvers (hipSOLVER/rocSOLVER + hand-built eig)
Tier: Core | Priority: high | Slot: F-HP-301
Implement `hippy.linalg` backed by hipSOLVER/rocSOLVER: `solve`, `inv`,
`det`, `slogdet`, `lu_factor`+`lu_solve`, `cholesky`, `qr`, `svd`,
`eigh`/`eigvalsh` (symmetric/Hermitian — vendor-supported), `lstsq`,
`matrix_rank`, `pinv`, and `norm`. REVIEW FIX: hipSOLVER exposes NO
nonsymmetric eigensolver (verified — no geev/ggev); `eig`/`eigvals`
(general) MUST be either (a) implemented by a hand-written, CITED
QR-iteration kernel, or (b) raise NotImplementedError — implementer's
choice, but never a silent CPU call. Generalized eig and `expm` are
OUT of v1 (raise). Use the oracle-b comparator registry: reconstruction
for lu/qr/svd/cholesky, sorted+sign-canonical for eigh. Acceptance:
reconstruction/eigh parity vs numpy.linalg within tolerance. Error/
boundary: a singular matrix in `solve`/`inv` raises (matching numpy's
LinAlgError); a non-square input to a square-only routine raises; eig
on a nonsymmetric matrix either reconstructs or raises NotImplemented.
Depends on F-HP-300.

## hippy.fft — FFTs via hipFFT
Tier: Core | Priority: high | Slot: F-HP-302
Implement `hippy.fft` backed by hipFFT: `fft`, `ifft`, `fft2`, `ifft2`,
`fftn`, `ifftn`, real transforms (`rfft`, `irfft`, `rfftn`, `irfftn`),
hermitian (`hfft`, `ihfft`), and helpers `fftfreq`, `rfftfreq`,
`fftshift`, `ifftshift`. Pin the normalization conventions EXACTLY:
`norm="backward"` (default) no scale forward + 1/n inverse;
`norm="ortho"` 1/sqrt(n) both; `norm="forward"` 1/n forward. `irfft`
requires an explicit output length `n` (the real length is otherwise
ambiguous). Plans are cached by (shape, dtype, axes). Support
complex64/128 and real float32/64. Acceptance: parity vs numpy.fft for
each transform and each norm mode; `ifft(fft(x))≈x` property test.
Error/boundary: `irfft` without/with wrong `n` behaves per numpy; an
unsupported axis spec raises. Depends on F-HP-104 and the hipFFT handle.

## hippy.random — RNG via hipRAND (+ JIT integer/choice layer)
Tier: Core | Priority: high | Slot: F-HP-303
Implement `hippy.random`: a seedable Generator and the distributions
`random`/`random_sample`, `uniform`, `standard_normal`/`normal`,
`lognormal`, `poisson`, `bytes` (direct hipRAND), plus `randint`,
`choice` (incl. weighted), `permutation`/`shuffle` (a JIT layer on top
of hipRAND — verified hipRAND does NOT provide these directly).
Because GPU RNG streams differ from numpy's bit generator, parity is
STATISTICAL with EXPLICIT numeric bounds (not "distribution shape"):
sample mean within k·sigma/sqrt(N) of the theoretical mean, sample
variance within a stated relative bound, for declared (N, k); PLUS
exact reproducibility for a fixed seed on THIS backend (same seed ->
same array). Use the statistical comparator (oracle b). Acceptance:
the moment bounds hold for each distribution at the declared N; a fixed
seed reproduces bit-for-bit on hippy. Error/boundary: an invalid
distribution parameter (negative scale, empty choice population)
raises; `randint` honors the half-open [low, high) bound. Depends on
F-HP-102 and the hipRAND handle.

## Device sort, search, counting, set routines (hand-built sort)
Tier: Core | Priority: medium | Slot: F-HP-304
Implement `sort`, `argsort`, `partition`/`argpartition`, `searchsorted`,
`unique`, `bincount`, `histogram`, `count_nonzero`. REVIEW FIX: there is
NO device sort in any bound ROCm library and rocPRIM/rocThrust are NOT
bound by hip-python (verified); the sort is a from-scratch, CITED
multi-kernel GPU sort (e.g. radix/merge) via the JIT engine, on device
(no host round-trip for large arrays). `argsort`/`partition`/median/
percentile (F-HP-305) depend on this. Use the sorted/multiset
comparator and exact comparator for distinct keys. Acceptance: parity
vs numpy; large-array sort runs on device (launch evidence). Error/
boundary: sort with ties is deterministic and documented (stable or
explicitly not); NaN ordering matches numpy; `searchsorted` honors
side="left"/"right". Depends on F-HP-203.

## Statistics, manipulation, and polynomial functions
Tier: Core | Priority: medium | Slot: F-HP-305
Implement remaining commonly-used numpy top-level functions, grouped so
ACs stay atomic: (stats) `var`, `std`, `median`, `percentile`/
`quantile`, `average`, `cov`, `corrcoef`; (manipulation) `clip`, `diff`,
`gradient`, `cross`, `outer`, `kron`, `concatenate`/`stack`/`hstack`/
`vstack`/`split`, `tile`, `repeat`, `roll`, `flip`, `pad`, `meshgrid`;
(polynomial, functional) `polyval`, `polyfit` (via the lstsq path).
Acceptance: parity vs numpy for each. Error/boundary: `percentile`
outside [0,100] raises; `concatenate` of mismatched non-concat dims
raises; `median` of an empty array raises like numpy. Depends on
F-HP-300, F-HP-303, F-HP-304.

# ============================================================================
# PHASE 5 — dispatch / compatibility layer
# ============================================================================

## Array protocols and get_array_module
Tier: Core | Priority: high | Slot: F-HP-400
Implement `__array_ufunc__` and `__array_function__` on the hippy array
so generic numpy-style code dispatches to hippy when handed hippy
arrays, and provide `get_array_module(*arrays)` (CuPy-style) returning
hippy or numpy by argument type. Unimplemented functions raise (no
silent CPU fallback). Acceptance: a numpy-generic function using
get_array_module runs on the GPU path for hippy inputs; dispatch routes
a ufunc through `__array_ufunc__`. Error/boundary: an unimplemented
dispatched function raises NotImplementedError naming the function (not
a silent host execution). Depends on Phases 3-4 core ops.

## Python Array API standard namespace
Tier: Core | Priority: medium | Slot: F-HP-401
Implement the Python Array API standard surface (`__array_namespace__`
returning a module exposing the standard's required functions and the
array's required methods/attributes) so portable Array-API code runs on
hippy. Conformance is measured CONCRETELY against the array-api test
suite: record the passing count and gate on a stated minimum fraction
of the REQUIRED (non-optional) portion (e.g. >= 0.90 of required), not
a vague "where feasible." Acceptance: the array-api suite runs and the
required-fraction threshold is met. Error/boundary: an optional-extension
function that is unimplemented raises the standard's prescribed error.
Depends on F-HP-400.

# ============================================================================
# PHASE 6 — hipsci (scipy mirror), tiered by value
# ============================================================================

## hipsci.fft (incl. DCT/DST built from FFT)
Tier: Core | Priority: high | Slot: F-HP-500
Implement `hipsci.fft` (scipy.fft API): `fft`, `ifft`, `fftn`, `ifftn`,
`rfft`, `irfft`, and `dct`, `idct`, `dst`, `idst` (types I-IV).
REVIEW FIX: hipFFT exposes NO DCT/DST (verified) — they MUST be built
from real FFTs with the correct per-type pre/post-twiddle and mirror
extension (cite Makhoul 1980 or equivalent), with ortho normalization
matching scipy. Acceptance: parity vs scipy.fft for fft/rfft and for
each DCT/DST type and norm; `idct(dct(x))≈x` property test. Error/
boundary: an unsupported DCT type raises naming it; norm modes match
scipy exactly. Depends on F-HP-302 and F-HP-201.

## hipsci.linalg
Tier: Core | Priority: high | Slot: F-HP-501
Implement `hipsci.linalg` (scipy.linalg API): `solve`, `lu`,
`lu_factor`/`lu_solve`, `qr`, `svd`, `cholesky`, `eigh`/`eigvalsh`,
`inv`, `det`, `lstsq`, `pinv`, `norm`, and `solve_triangular`. General
`eig` and `expm` follow the F-HP-301 ruling (hand-built-or-raise / OUT).
Use the comparator registry (reconstruction, sorted+sign-canonical).
Acceptance: reconstruction/eigh parity vs scipy.linalg. Error/boundary:
singular/non-square inputs raise the matching scipy error; banded/
specialized solvers not listed raise NotImplemented. Depends on F-HP-301.

## hipsci.ndimage
Tier: Core | Priority: medium | Slot: F-HP-502
Implement `hipsci.ndimage`: filters (`gaussian_filter`, `uniform_filter`,
`convolve`, `correlate`, `median_filter`, `sobel`), morphology
(`binary_erosion`/`binary_dilation`), geometric transforms (`zoom`,
`shift`, `rotate`, `map_coordinates`) as JIT stencil/convolution
kernels. Acceptance: parity vs scipy.ndimage within tolerance, honoring
boundary `mode=` (reflect/constant/nearest/wrap). Error/boundary: an
unsupported mode raises; `median_filter` depends on the device sort
(F-HP-304). Depends on F-HP-204, F-HP-104, F-HP-304.

## hipsci.sparse + sparse matmul via hipSPARSE
Tier: Core | Priority: medium | Slot: F-HP-503
Implement `hipsci.sparse` with CSR (plus CSC/COO conversion) and core
ops: SpMV, SpMM, SpGEMM (verified exposed by hipSPARSE), construction
from dense, and `toarray`. Use exact/allclose comparators. Acceptance:
parity vs scipy.sparse for the implemented ops. Error/boundary:
dimension-mismatched sparse ops raise; an empty sparse matrix is
handled. No sparse PERF gate (SpMV is bandwidth-bound and may not beat
224 CPU cores — parity-only). Depends on F-HP-300 and the hipSPARSE
handle.

## hipsci.special (JIT elementwise, hand-built where no device math)
Tier: Core | Priority: medium | Slot: F-HP-504
Implement `hipsci.special` commonly-used functions as JIT elementwise
kernels: gamma/lgamma, beta, erf/erfc/erfinv, `expit`/`logit`,
factorial/comb (array-valued), digamma, and Bessel j0/j1/i0/i1. REVIEW
FIX: erf/erfc/erfinv/j0/j1 exist in the HIPRTC device math headers, but
i0/i1 (modified Bessel), digamma, and beta are NOT (verified i0f/i1f
undeclared) — these MUST be hand-coded series/asymptotic approximations
with CITED coefficients and a stated accuracy bound. Acceptance: parity
vs scipy.special within a CITED tolerance per function. Error/boundary:
out-of-domain inputs (gamma of a negative integer, logit outside (0,1))
follow scipy (inf/nan), not crash. Depends on F-HP-202.

## hipsci.signal (core)
Tier: Core | Priority: medium | Slot: F-HP-505
Implement `hipsci.signal` core: `convolve`, `correlate`, `fftconvolve`,
`oaconvolve`, `resample`, FIR filtering (`lfilter` for the FIR case,
`firwin`). IIR/recursive filtering and advanced spectral tooling are
deferred (raise NotImplemented). Acceptance: parity vs scipy.signal for
the implemented functions, honoring `mode=` (full/same/valid).
Error/boundary: an IIR `lfilter` call (nontrivial denominator) raises
NotImplemented naming the limitation; mismatched mode raises. Depends
on F-HP-302 and F-HP-204.

## hipsci.special-functions tier note / hipsci.stats (subset)
Tier: Core | Priority: low | Slot: F-HP-506
Implement a subset of `hipsci.stats`: descriptive stats (`describe`,
`zscore`, `skew`, `kurtosis`, `sem`); continuous distributions (norm,
uniform, expon, gamma, beta) with pdf/cdf/ppf/rvs on device; and the
array-parallel tests `ttest_ind`, `pearsonr`, `spearmanr`. Acceptance:
parity vs scipy.stats within tolerance (pdf/cdf/ppf analytic; rvs by
the statistical comparator). Error/boundary: invalid distribution
params raise; a constant input to pearsonr returns nan like scipy.
Depends on F-HP-305 and F-HP-303.

## hipsci.interpolate (subset)
Tier: Core | Priority: low | Slot: F-HP-507
Implement a `hipsci.interpolate` subset: 1-D `interp1d`
(linear/nearest/cubic), `RegularGridInterpolator`, and spline
evaluation where device parallelism helps. Acceptance: parity vs
scipy.interpolate within tolerance. Error/boundary: querying outside
the data range honors `bounds_error`/`fill_value`; an unsupported kind
raises. Depends on F-HP-305.

# ============================================================================
# PHASE 7 — performance gates
# Each uses F-HP-010, compares vs numpy/scipy on 224 CPU cores, above a JUSTIFIED
# and BOUNDED per-op size threshold (the win must hold at the largest size in one
# GPU's HBM; thresholds may not be inflated to dodge the gate). Below threshold =
# parity-only. A domain may conclude "no win for the simple single-call case"
# without failing, scoping the win to batched/large variants.
# ============================================================================

## Performance gate — elementwise and reductions beat CPU above threshold
Tier: Core | Priority: high | Slot: F-HP-600
Using F-HP-010, demonstrate that representative elementwise ufuncs
(F-HP-201) and reductions (F-HP-203) on large arrays (>= a declared,
justified threshold) beat numpy on 224 CPU cores by more than the
combined noise band, and that the fused path (F-HP-204) beats the
unfused path on a multi-op expression. Acceptance: GPU median beats CPU
median beyond the noise band at the declared size; the threshold is
recorded with justification. Error/boundary: the recorded sub-threshold
region where the GPU does NOT win is reported (expected), not hidden;
an inflated threshold (win only at an unrealistically tiny fraction of
HBM) fails the justification check. Depends on F-HP-204.

## Performance gate — GEMM and linalg beat CPU above threshold
Tier: Core | Priority: high | Slot: F-HP-601
Using F-HP-010, demonstrate matmul (F-HP-300) and the major
hippy.linalg decompositions (F-HP-301) on large matrices beat
numpy/scipy on 224 CPU cores beyond the noise band. Report GEMM
GFLOP/s as CITED context but gate on the RELATIVE win, never an absolute.
Acceptance: GPU beats CPU beyond the band at the declared matrix size.
Error/boundary: small-matrix sizes where CPU wins are reported as
parity-only, not failures. Depends on F-HP-301.

## Performance gate — batched/large FFT beats CPU above threshold
Tier: Core | Priority: medium | Slot: F-HP-602
Using F-HP-010, demonstrate that hippy.fft (F-HP-302) beats numpy.fft /
scipy.fft on 224 CPU cores beyond the noise band for BATCHED or large
N-D transforms (review note: single small 1-D transforms may never win
against FFTW-on-224-cores and are explicitly excluded from this gate).
Acceptance: GPU beats CPU beyond the band for the declared batched/
large-N-D case. Error/boundary: the single-small-transform case is
documented as parity-only/no-win, not a failure. Depends on F-HP-302.

## End-to-end drop-in validation and benchmark report
Tier: Core | Priority: high | Slot: F-HP-603
Capstone evidence that hippy/hipsci are usable drop-ins. Take 3
representative numpy/scipy programs (a finite-difference stencil step,
an SVD-based low-rank approximation, an FFT-based convolution), run each
unmodified except for `import hippy as hp` / `import hipsci as sp`,
assert results match the numpy/scipy version within tolerance, and
report end-to-end wall-clock speedup under F-HP-010. Emit a single
markdown report summarizing parity (both oracles), per-domain speedups,
and the xfail/skip taxonomy counts. Acceptance: all three programs match
within tolerance and the report is emitted with the required sections.
Error/boundary: if a program hits an unimplemented function it MUST
fail with a clear NotImplementedError (proving no silent CPU fallback),
and that gap is recorded in the report rather than masked. Depends on
F-HP-400, F-HP-600, F-HP-601, F-HP-602.
