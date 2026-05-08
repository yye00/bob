# Tier 1 — HPC skill specifications

Concrete starter outlines for each skill in the HPC bundle. Each
section gives:

- **Frontmatter description** — what the skill is for, in
  one-sentence form (matches the existing bob3 skill style)
- **When applied** — at what point in the agent's workflow
- **Rule set** — the durable content the agent reads (this is
  the actual work to author)
- **What it doesn't catch** — honest scope limits

These are outlines. Full skills are `SKILL.md` files of 1–3
pages. Author them iteratively; ship 4 good ones before drafting
8 mediocre ones.

---

## `mms-driven-development`

**Frontmatter:** *Use when implementing a numerical method
(solver, kernel, integrator). Write a manufactured solution and
its source term FIRST; verify the implementation reproduces the
analytical solution at the claimed convergence order before
optimizing.*

**When applied:** Before the agent writes the kernel or solver.
Replaces (or supplements) `test-driven-development` for numerical
work.

**Rule set:**

1. Pick a manufactured solution u(x, t) — typically a smooth
   trig or polynomial form whose derivatives you can write by
   hand or symbolically (sympy is fine).
2. Substitute into the PDE → derive the source term s(x, t)
   needed so u is the exact solution.
3. Write a test that runs the solver on N grid resolutions
   (e.g., h, h/2, h/4, h/8) and computes L2 error against u.
4. Assert the convergence order: `log(err_h / err_h2) / log(2) ≈
   p` where p is the claimed order. Tolerance ±0.2 typical.
5. If the order is wrong, the implementation is wrong — even if
   tests for individual cases pass.

**What it doesn't catch:**

- Performance bugs (use `cuda-kernel-design` + `roofline-checks`)
- Boundary-condition errors that vanish on smooth manufactured
  solutions (need a separate boundary-stressing case)
- Stability under stiff coefficients (need a stability suite)

---

## `cuda-kernel-design`

**Frontmatter:** *Use when writing CUDA kernels. Apply the
disciplined patterns for grid sizing, shared memory, occupancy,
coalesced access, and bank conflict avoidance.*

**When applied:** Whenever the agent is generating CUDA / C++
code with `__global__` or `__device__` annotations.

**Rule set:**

1. **Grid + block sizing:** start with `blockDim.x = 256`. Tune
   only after measurement. Ensure `gridDim` covers the work
   without launching empty blocks; use `(N + 255) / 256` patterns.
2. **Memory access:** every load from global memory should be
   coalesced (consecutive threads load consecutive 4-byte words).
   If you find yourself indexing as `arr[tid * stride]`, you're
   strided — change layout to AoS-of-SoA or transpose.
3. **Shared memory:** budget per block is 48 KB on most modern
   GPUs (96 KB on H100 with opt-in). Pad inner dimensions by 1 to
   avoid bank conflicts on 32-bank shared. Document the budget
   inline with a comment.
4. **Occupancy:** target ≥ 50% theoretical occupancy. If register
   pressure pushes you below that, refactor before adding
   features. Use `__launch_bounds__` to control register
   allocation.
5. **Warp divergence:** avoid `if`-branches whose predicate
   varies across threads in a warp. Push divergent work to
   separate kernel launches when possible.
6. **Atomics:** use `atomicAdd` only when contention is bounded
   (e.g., per-warp reductions are fine; per-block totals via
   atomics across all threads are not). Prefer `__shfl_xor_sync`
   reductions inside warps.
7. **Asynchronous copies:** prefer `cudaMemcpyAsync` with a
   stream over synchronous copy. Overlap transfer with compute
   when the data flow allows it.

**What it doesn't catch:**

- Algorithmic correctness (the kernel is fast and wrong)
- Race conditions (use `compute-sanitizer` in Tier 2)
- Performance regression vs prior implementation (need
  measurement + memory of past perf)

---

## `hip-portability`

**Frontmatter:** *Use when emitting code that must run on both
NVIDIA (CUDA) and AMD (ROCm/HIP) GPUs. Apply the rules for
writing HIP-portable code from the start, rather than porting
later.*

**When applied:** When the spec calls for portability between
NVIDIA and AMD GPUs, or when generating new HPC code that should
not lock in a vendor.

**Rule set:**

1. Use HIP API calls directly (`hipMalloc`, `hipMemcpy`,
   `hipLaunchKernelGGL`) — they compile through `hipcc` for both
   vendors.
2. Avoid CUDA-only features without explicit fallback:
   - Cooperative groups beyond block-level
   - Tensor cores via `wmma` (use rocWMMA on AMD)
   - Specific PTX inline assembly
3. Warp size differs: 32 on NVIDIA, 64 on AMD. Use
   `warpSize` (provided by HIP) instead of hardcoded 32.
4. Architecture detection: use `__HIP_PLATFORM_AMD__` and
   `__HIP_PLATFORM_NVIDIA__` for vendor-specific code paths.
   Document why a divergence exists at the ifdef site.
5. Build system: hipcc handles the dispatch, but cmake should set
   `CMAKE_HIP_ARCHITECTURES` for the target GPUs and
   `HIP_PATH`/`CUDA_PATH` for their toolchains.
6. Performance: HIP code that runs on AMD is rarely as fast as
   hand-tuned ROCm. Benchmark on both vendors before claiming
   portability + performance.

**What it doesn't catch:**

- Subtle correctness differences in math intrinsics (sin, exp on
  the two vendors are not bit-identical at the last ulp)
- Memory-access patterns optimal on one vendor but suboptimal on
  the other (different cache line sizes, different memory
  coalescing rules)

---

## `mpi-correctness`

**Frontmatter:** *Use when emitting MPI code. Apply the rules
for collective ordering, blocking semantics, deadlock avoidance,
and message correctness.*

**When applied:** Anywhere `MPI_*` calls appear in generated
code.

**Rule set:**

1. **Collectives are global:** every rank in the communicator
   must call them in the same order. Conditional collectives
   (`if (rank == 0) MPI_Bcast(...)`) deadlock immediately.
2. **Match sends and receives:** every `MPI_Send` needs a
   matching `MPI_Recv` (or `MPI_Irecv` + `MPI_Wait`). Tags must
   match. Mismatched tag = silent hang.
3. **Blocking vs non-blocking:** `MPI_Send` may or may not
   buffer; assume it doesn't. Pair every blocking send with a
   blocking receive on the other side, or use `MPI_Sendrecv` for
   neighbor-exchange patterns.
4. **Non-blocking: complete what you start.** Every `MPI_Isend`
   /`MPI_Irecv` needs an `MPI_Wait` or `MPI_Waitall` before the
   buffer is reused. Forgetting causes data corruption that
   manifests far from the cause.
5. **Reduction operators:** built-in ops (`MPI_SUM`, `MPI_MAX`)
   are safe; user-defined ops must be associative + commutative,
   or the reduction is non-deterministic.
6. **Buffer aliasing:** the send and receive buffers in
   `MPI_Allgather` etc. must not alias unless you use
   `MPI_IN_PLACE`. Aliasing without `MPI_IN_PLACE` is undefined.
7. **Deadlock patterns to avoid:**
   - Allreduce-then-Bcast without ensuring all ranks reach the barrier
   - Sendrecv where the partner doesn't reciprocate
   - Conditional collectives (rank-dependent participation)
   - Non-blocking pairs without `Wait`s on both ends
8. **Communicator hygiene:** `MPI_Comm_dup` for libraries; don't
   reuse `MPI_COMM_WORLD` for everything; `MPI_Comm_free` on
   shutdown.

**What it doesn't catch:**

- Performance issues (load imbalance, communication-computation
  overlap missed) — those need profiling
- Subtle ordering bugs that only manifest at large rank counts
- Correctness issues in user-defined reduction ops beyond
  associativity

---

## `openmp-correctness`

**Frontmatter:** *Use when emitting OpenMP code. Apply the rules
for pragma scoping, reduction clauses, false sharing avoidance,
and atomic / critical regions.*

**When applied:** Anywhere `#pragma omp` appears in generated
code.

**Rule set:**

1. **Default scoping is dangerous:** prefer
   `default(none)` and explicit `private`/`shared` clauses on
   every parallel region. The default `shared` is one of the most
   common bug sources.
2. **Reductions:** every accumulator written inside a parallel
   loop needs a `reduction(...)` clause — otherwise it's a race.
   Built-in operators: `+`, `*`, `min`, `max`, `&`, `|`, `^`,
   `&&`, `||`. User-defined reductions via `#pragma omp declare
   reduction` for custom types.
3. **Critical / atomic:** `atomic` for single-variable updates
   (faster). `critical` for code blocks. Both kill scaling if
   overused; refactor algorithm to localize state instead.
4. **False sharing:** when multiple threads write nearby
   addresses, cache-line bouncing kills performance. Pad
   per-thread state to cache-line size (typically 64 bytes).
   Detected with `perf c2c` or VTune.
5. **Schedule:** `schedule(static)` for uniform work,
   `schedule(dynamic, chunk)` for irregular. `schedule(guided)`
   for monotonically decreasing work. Default (`schedule(auto)`)
   is implementation-defined; specify explicitly.
6. **Nested parallelism:** off by default in most runtimes; if
   needed, `omp_set_nested(1)` and watch for thread-explosion.
   Usually the wrong call; prefer task-based decomposition.
7. **Tasks:** `#pragma omp task` is more flexible than parallel
   for, but task creation has overhead. Use `untied` only when
   you need it; `firstprivate` over `shared` for closure capture.
8. **Memory model:** atomics aren't sequentially consistent by
   default; use `seq_cst` if you need that ordering.

**What it doesn't catch:**

- Performance under heavy thread counts (need measurement)
- Correctness under specific runtime implementations (LLVM
  OpenMP vs GCC OpenMP have observable behavior differences)
- NUMA-aware allocation patterns (need `numactl` or
  hwloc-aware allocation, not just OpenMP pragmas)

---

## `mixed-precision-safety`

**Frontmatter:** *Use when generating code that mixes fp16,
bf16, fp32, and fp64. Apply the rules for where each precision
is safe, how to manage accumulation, and when summation
algorithms (Kahan, pairwise) are needed.*

**When applied:** Whenever the spec mentions mixed precision or
when generating ML / numerical code where the precision choice
affects correctness.

**Rule set:**

1. **Default to fp64 for accumulation, lower precision for
   storage.** A dot product whose inputs are fp16 should
   accumulate in fp32 minimum. NVIDIA tensor cores do this
   pattern in hardware.
2. **bf16 vs fp16:** bf16 has the dynamic range of fp32 but only
   8 bits of mantissa. fp16 has more mantissa precision but a
   tiny range (overflows above 65504). For ML training: bf16 is
   safer. For ML inference: fp16 is finer.
3. **Catastrophic cancellation:** subtractions of nearly-equal
   numbers lose all precision. If your algorithm has
   `(a + b) - a` patterns, you need higher precision for that
   subtraction or a reformulated algorithm.
4. **Kahan / Neumaier summation:** for long sums in fp32 (more
   than ~10⁴ terms), use Kahan or Neumaier compensated
   summation. The naive sum drifts by O(n × ulp) — Kahan is
   O(ulp).
5. **Pairwise summation:** for parallel sums, pairwise
   (tree-reduction) is both faster and more accurate than
   sequential. CUDA `__shfl` reductions naturally do pairwise.
6. **Conversions:** flagging conversions (`__float2half`,
   `static_cast<float>`) is good documentation. Implicit
   conversions in mixed-precision code are bug magnets.
7. **Reproducibility:** fp32 + non-deterministic reduction order
   = non-reproducible results. If reproducibility matters, force
   deterministic order (which costs perf).

**What it doesn't catch:**

- Specific cases where the algorithm's condition number is so
  large no precision saves you — that's a method choice, not a
  precision choice
- Hardware quirks (e.g., A100 tensor cores have fp32 accumulator;
  H100 has fp32 + bf16 + fp16 + tf32 + fp8)

---

## `numerical-stability-checks`

**Frontmatter:** *Use when emitting numerical code that involves
linear algebra, iteration, or floating-point accumulation. Apply
the rules for catastrophic cancellation, condition numbers, NaN
propagation, and stability analysis.*

**When applied:** Whenever generating numerical code beyond
trivial arithmetic.

**Rule set:**

1. **Condition numbers:** for linear systems Ax = b, the relative
   error in x scales with the condition number of A. If A has
   κ(A) > 10^(p) and you're using p-digit precision, the answer
   is dominated by roundoff. Document the assumed κ in code.
2. **NaN / Inf hygiene:** use `isnan` / `isinf` checks at module
   boundaries, not internally. NaN-poison spreads silently
   through code; catching it at the source costs less than
   tracking it down.
3. **Iterative methods:** test convergence with both relative
   and absolute tolerances (`||r_k|| / ||r_0|| < ε_rel` or
   `||r_k|| < ε_abs`). The relative-only variant fails when
   `r_0` is near zero.
4. **Avoid trigonometric identity tricks** for small angles;
   `sin(x) ≈ x` is fine but `1 - cos(x) ≈ x²/2` is not — write
   it as `x²/2 * (1 - x²/12 + ...)` or use the half-angle
   identity `2 sin²(x/2)`.
5. **Quadratic formula:** `(-b ± √(b² - 4ac)) / 2a` loses
   precision when `b² ≫ 4ac`. Use the alternate form for one of
   the two roots: `c / (a × (-b ∓ √discriminant))`.
6. **Stencils on shocks:** high-order stencils diverge near
   discontinuities. Limiters or essentially-non-oscillatory
   (ENO/WENO) reconstruction are needed for shock-capturing.
7. **Symplectic vs non-symplectic time integration:** for
   long-time energy conservation in Hamiltonian systems, use a
   symplectic integrator (Verlet, leapfrog). RK4 drifts.

**What it doesn't catch:**

- Algorithm-level instabilities (CFL violations, stiff systems
  with explicit methods) — those need spec-level review
- Numerical sensitivity that only emerges at extreme scales

---

## `adversarial-numerical-review`

**Frontmatter:** *Use before declaring any HPC feature complete.
Replaces `adversarial-self-review`'s six-point checklist with
HPC-specific failure modes: warp divergence, bank conflicts,
atomic contention, MPI deadlock, NaN robustness, conservation,
reproducibility.*

**When applied:** Before declaring an HPC feature done. Replaces
or supplements the existing `adversarial-self-review`.

**Rule set:**

Pretend you are a hostile reviewer who:

- Suspects the kernel runs at 5% peak bandwidth and you don't know
- Knows MPI deadlock patterns by heart
- Will get credit for every NaN propagation path you find
- Believes the convergence order test was rigged

Now review the diff with that mindset. Specifically:

1. **Bandwidth audit:** for every kernel, estimate arithmetic
   intensity (FLOPs / byte). Compare to roofline. If achieved <
   30% peak bandwidth on a memory-bound kernel, something is
   wrong (uncoalesced loads, bank conflicts, divergent threads).
2. **Race audit:** every shared-memory write shared between
   threads must be either guarded by a barrier (`__syncthreads`)
   or atomic. Run mentally through what happens at warp
   boundaries.
3. **Deadlock audit:** for every collective MPI operation, are
   all ranks calling it in the same order? For every `MPI_Isend`,
   is there a matching `MPI_Wait` somewhere in the code path?
4. **NaN audit:** if any input is NaN or Inf, what's the
   blast-radius? Does it propagate silently to every output? At
   what module boundary should NaN be detected and rejected?
5. **Conservation audit:** if your method is supposed to
   conserve mass / momentum / energy / charge, write a test that
   checks the conserved quantity stays bounded over many
   timesteps. Drift is a bug.
6. **Reproducibility audit:** does the code produce bit-identical
   results on two runs with the same input? If not, where's the
   non-determinism? (Atomic operations, parallel reductions,
   thread-pool scheduling.) Document it; don't pretend it doesn't
   exist.
7. **Boundary audit:** do the boundary cells use the right
   stencil? Are corners (in 2D) and edges/corners (in 3D)
   handled correctly? Special-case those and write boundary-only
   tests.
8. **Scale audit:** does the test suite include at least one case
   that's larger than the trivial. The bug that hides at N=8 will
   surface at N=10000.

If you find a real issue, **fix it before declaring done.** Don't
file it and move on.

**What it doesn't catch:**

- Specific bugs that only manifest at production scale (only
  hardware testing finds those)
- Subtle convergence issues that only show up over very long
  time integrations
- Vendor-specific quirks (use `compute-sanitizer` and Nsight)

---

## Summary

Eight skills, listed in dependency order:

| Skill | Depends on | Tier-1 priority |
|---|---|---|
| `adversarial-numerical-review` | none (replaces existing skill) | high |
| `mms-driven-development` | none | high |
| `cuda-kernel-design` | none | high |
| `mpi-correctness` | none | high |
| `mixed-precision-safety` | none | medium |
| `numerical-stability-checks` | none | medium |
| `openmp-correctness` | none | medium |
| `hip-portability` | depends on `cuda-kernel-design` (common patterns) | low |

**Recommended ship order:** the four "high" skills first as a
self-contained release; the four "medium / low" skills as a
follow-up. The first batch is enough to demonstrate the
contribution.
