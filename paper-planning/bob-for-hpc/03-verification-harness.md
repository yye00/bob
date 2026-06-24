# Tier 2 — Verification harness for HPC code

This is the *binding constraint* on whether the rest of the plan
actually produces validated HPC code or just plausible-looking
HPC code. See [`00-adversarial-analysis.md`](00-adversarial-analysis.md)
§2 for why.

## Why this is necessary

The current bob verification layer assumes:

- The build runs locally
- Tests are pytest
- Pass/fail is binary
- Wall clock per criterion is bounded by `BOB_CRITERION_EXEC_TIMEOUT`
  (default 600 s)

For HPC code, none of these hold without changes:

- Code targets GPUs/accelerators that may not be on the build machine
- "Tests pass" is necessary but not sufficient — performance and
  correctness at scale matter
- Verification involves multi-resolution runs, sanitizer passes,
  profiling tool output parsing
- Some criteria (compute-sanitizer on a large kernel) take >10 minutes

The harness extends rather than replaces. The existing checks
still run; new HPC-shaped criteria are added.

## New criterion types

Each criterion is a string in the `acceptance_criteria` list of
a feature. The verification engine maps the criterion to a
runner.

### `compile_with: <compiler> <flags>`

The simplest new criterion. Verifies the generated source
compiles with the specified toolchain. Runs `<compiler> <flags>
<sources> -o /dev/null` and asserts exit 0.

Examples:
- `compile_with: nvcc -arch=sm_80 -std=c++17`
- `compile_with: hipcc --offload-arch=gfx90a -std=c++17`
- `compile_with: mpicxx -fopenmp`

**Implementation effort:** small. Wraps `subprocess.run` with
existing timeout / output-capture handling.

**Hardware required:** the compiler must be installed; no
runtime hardware needed.

**Caveats:**

- Compile success does not imply runtime correctness — pair with
  at least one runtime criterion
- nvcc's error messages can be noisy; capture full stderr for
  RCA evidence

### `compute_sanitizer_clean: yes`

Runs the generated code under NVIDIA's
`compute-sanitizer` (formerly cuda-memcheck) and asserts no
errors. Detects: uninitialized memory, race conditions, illegal
memory access, leak.

**Implementation:** runs `compute-sanitizer --tool=memcheck
<binary>` (or `--tool=racecheck`). Parses output for "no errors"
sentinel. Returns exit + parsed details.

**Hardware required:** NVIDIA GPU available to the build machine.

**Caveats:**

- 10–100× slowdown vs unsanitized run; budget accordingly
- Different sanitizer tools (memcheck, racecheck, initcheck,
  synccheck) catch different bug classes; consider running
  multiple
- AMD has rocgdb / amdgpu-arch-detect for similar coverage but
  different invocation; treat as separate criterion type if
  supported

### `nsight_metrics: <metric> >= <value>`

Runs the generated kernel under Nsight Compute and parses
specific metrics from the report.

Examples:
- `nsight_metrics: gpu__time_active.avg.pct_of_peak_sustained_elapsed >= 50`
- `nsight_metrics: smsp__inst_executed.avg.per_cycle_active >= 0.7`
- `nsight_metrics: dram__bytes_read.sum.per_second >= 800e9`

**Implementation:** runs `ncu --set full --csv <binary>`,
parses the CSV, extracts the named metric, compares to the
threshold.

**Hardware required:** NVIDIA GPU + Nsight Compute installed +
permissions to access GPU performance counters (typically
`sudo` or kernel module config).

**Caveats:**

- Metric names are version-dependent (NCU 2023.x vs 2024.x).
  Pin the NCU version in the build environment.
- First run is slow (NCU compiles the metric set); cache between
  runs.
- Some metrics require specific driver / CUDA versions.

### `convergence_order_at_least: <p>`

Runs the implementation on N grid resolutions, computes L2
errors against a manufactured solution (or analytical reference),
fits log(error) vs log(h), asserts the slope is at least `p` ±
0.2.

Implementation requires a companion test fixture in the spec
that defines:
- The manufactured solution (or reference)
- The resolutions to test (typically h, h/2, h/4, h/8)
- The norm (typically L2 over the domain)

**Implementation:** wraps a pytest fixture that drives the
implementation at each resolution, computes errors, fits the
slope. Returns slope + R² of the fit; asserts.

**Hardware required:** depends on the problem size. Often
runnable on the build machine for development resolutions; full
order-verification may need a GPU.

**Caveats:**

- Need at least 4 resolutions for a robust fit
- The test must use the same code path at all resolutions; if
  the impl has a special case for "small grids", that case
  doesn't validate the general case
- Convergence-order tests are sensitive to roundoff at very fine
  grids; balance grid range vs precision

### `conservation_error: <expr> < <bound>`

For methods that should conserve a physical quantity (mass,
momentum, energy, charge), runs the simulation for N timesteps
and asserts the change in the conserved quantity is below the
bound.

Example:
- `conservation_error: max(abs(energy[t] - energy[0])) / energy[0] < 1e-12`

**Implementation:** the spec's test fixture computes the
conserved quantity at each timestep; the verifier checks the
final value against the initial.

**Hardware required:** depends on problem size.

**Caveats:**

- Some methods (e.g., 2nd-order finite-volume) conserve only
  to the discretization order, not to roundoff. Set the bound
  appropriately.
- "Conservation" only makes sense if the boundary conditions
  are conservative; check that first.

### `deterministic_output: yes`

Runs the implementation twice with identical inputs and asserts
bit-identical outputs. Detects non-deterministic reductions,
race conditions, scheduling-dependent results.

**Implementation:** runs the binary twice, captures stdout (or
output file), compares bytewise.

**Hardware required:** target hardware (CPU or GPU).

**Caveats:**

- Some legitimate parallel patterns are non-deterministic by
  design (atomic-reduce-without-ordering). For those, use a
  weaker variant: `deterministic_output: within: <tolerance>`.
- Vendor BLAS / cuBLAS may be non-deterministic; document if
  you depend on them.

## Integration with the existing verifier

The existing `_check_criterion` function in
`enhanced_verification.py` parses criterion strings prefixed by
type. Add new prefixes:

```python
CRITERION_HANDLERS = {
    "File exists": _check_file_exists,
    "Function defined": _check_function_defined,
    "pytest": _check_pytest,
    "python": _check_python,
    # New HPC criteria:
    "compile_with": _check_compile_with,
    "compute_sanitizer_clean": _check_compute_sanitizer,
    "nsight_metrics": _check_nsight_metric,
    "convergence_order_at_least": _check_convergence_order,
    "conservation_error": _check_conservation,
    "deterministic_output": _check_deterministic,
}
```

Each handler returns `{passed: bool, severity: str, details:
str}` matching the existing pattern.

## Hardware tiers for the harness

Define three execution tiers so the same spec can run with
varying hardware availability:

| Tier | Hardware | Criteria runnable | Use case |
|---|---|---|---|
| L0 — local-only | None | `compile_with`, `python:`, `pytest:` | Initial development, contributor without GPU |
| L1 — single GPU | One CUDA / HIP GPU | + `compute_sanitizer_clean`, `nsight_metrics`, `convergence_order_at_least`, `conservation_error`, `deterministic_output` | Full bob-for-HPC validation on a single accelerator |
| L2 — cluster | Slurm / PBS access | + scaling criteria, multi-node correctness | Tier 3 (deferred) |

The verifier reads `BOB_HW_TIER` (or auto-detects) and skips
criteria that need higher hardware. Skipped criteria emit a
warning (`severity: warning`) so they don't block completion in
L0 development but are visible in the verification log.

## Caching expensive verification

Sanitizer and Nsight runs can take 10+ minutes per kernel.
Re-running on unchanged code is wasteful. Cache by:

```
hash(binary_sha256, input_args, criterion_type) → cached_result
```

Cache lives in `<workspace>/.bob/verification_cache/`. Hit rate
matters when iterating on a feature: only the first build pays
the verification cost; subsequent builds with no kernel changes
reuse the cached pass/fail.

Invalidate cache when:
- Source changes (binary hash differs)
- Compiler changes (different toolchain version)
- Hardware changes (`nvidia-smi` output for the GPU model
  differs)

## Open questions

1. **Test fixture format for `convergence_order` and
   `conservation_error`.** These criteria need data from the
   running impl. Options:
    - Spec includes pytest fixtures the impl is required to use
    - Spec specifies a JSON output schema the impl writes; verifier reads
    - Spec runs a separate runner script that feeds the impl
2. **Integration with the existing process-group timeout
   machinery.** The verifier's `_run_with_pgroup_timeout` cleans
   up child processes. NCU spawns multiple sub-processes; ensure
   they're all in the same process group or extend cleanup.
3. **AMD parity.** rocgdb / rocprofiler are the AMD analogs to
   compute-sanitizer / Nsight. Should `compute_sanitizer_clean`
   become a vendor-neutral `sanitize_clean` that dispatches by
   platform? Probably yes.

## Implementation order

1. `compile_with` first — small, builds confidence
2. `deterministic_output` next — also small, useful for early bug
   detection
3. `compute_sanitizer_clean` — first criterion that genuinely
   requires hardware
4. `nsight_metrics` — most complex parsing, defer until #3 lands
5. `convergence_order_at_least` — needs companion fixture format
   decision (open question above)
6. `conservation_error` — same fixture format dependency

This order frontloads the cheap wins and pushes the
fixture-format decision late enough that we have running code
informing it.
