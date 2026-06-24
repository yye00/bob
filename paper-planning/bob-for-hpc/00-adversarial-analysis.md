# Adversarial analysis — bob3 for HPC

This document captures the honest critique of the "bob3 generates
HPC code" claim. It exists to keep us from drifting into
marketing.

The arguments below were generated under explicit instruction to
be adversarial — they are not balanced; they are the case
*against*. Read them, weigh them, and only commit to the plan if
you have answers for the parts that actually bite.

---

## 1. The swedish-circle case study does not support the HPC claim

The 19-feature swedish-circle build is the strongest existing
evidence for bob3. Examined for HPC relevance, it tested:

| HPC requirement | Tested in swedish-circle? |
|---|---|
| MPI message-passing patterns | No |
| OpenMP / CUDA / HIP / SYCL kernels | No |
| Memory-hierarchy / NUMA / cache reasoning | No |
| Communication-computation overlap | No |
| Scheduler integration | No |
| Multi-node filesystem coordination | No |
| Reproducibility under non-deterministic reductions | No |
| Mixed precision sensitivity | No |
| Roofline / arithmetic-intensity analysis | No |
| Convergence order verification (L2 error ∝ h^p) | No — used point-value tolerances |
| Conservation laws | No |
| Method of manufactured solutions | No |
| Weak / strong scaling studies | No |

What was tested: pure-Python numerics on one core, with a Qt GUI.
That's "engineering software", not HPC. **No bullet from the
swedish-circle results generalizes to a claim about HPC code
generation.** Carrying that case study into an HPC paper would
weaken, not strengthen, the contribution.

---

## 2. The validation gap is the central problem and skills don't fix it

> If you ship a `cuda-kernel-design` skill with no actual GPU in
> the verification path, the agent will produce kernels with bank
> conflicts and 8% bandwidth utilization — and the verifier will
> pass them.

A skill teaches the agent to *aim for* coalesced access and high
occupancy. It does not *verify* the resulting code achieves
either. You can verify those properties three ways:

| Method | Cost | Coverage |
|---|---|---|
| Run on a real GPU + Nsight Compute | Hardware needed; minutes per kernel | Excellent |
| `compute-sanitizer` / `cuda-memcheck` | Hardware needed; faster | Race / memory only, not perf |
| Static analysis (PolyMage, CFG inspection) | Free | Brittle, vendor-specific, narrow |
| LLM "review the kernel" | Cheap | Unreliable; rationalizes |

**This is the central claim adversarial review can't make in
this regime.** The existing `adversarial-self-review` works
because Python code's correctness is verifiable from disk + a
unit test. CUDA correctness at the level that matters is **not**
verifiable without hardware.

The implication for the plan: **Tier 1 (skills) without Tier 2
(verification harness with GPU access) is hollow.** The agent
will write plausible-looking code; nothing will catch the bugs
that matter.

---

## 3. The intellectual heavy-lifting in HPC is design, not coding

Pick any real HPC codebase — PETSc, Trilinos, AMReX, FEniCS,
deal.II — and look at where the value lives:

- Choosing the discretization (FV vs FE vs DG vs spectral)
- Choosing the solver (matrix-free vs matrix? Krylov vs multigrid? algebraic vs geometric?)
- Choosing the parallelization strategy (where to decompose, when to communicate, what to overlap)
- Choosing the data layout (AoS vs SoA, blocking factors, padding)
- Choosing the precision (where mixed-precision is safe, where it isn't)

These are **design decisions made by senior people before any
code is written.** If you write a spec detailed enough for bob3
to "just code it," you've already done the hard work. You haven't
replaced the analyst; you've added a typing assistant.

The swedish-circle spec is a clean example. It told the agent the
method (Bishop's Simplified), the discretization (50 vertical
slices), the convergence target (FoS within 2% of textbook). All
the math was specified. The agent just *typed it*. That doesn't
generalize to a regime where the design choices are themselves
the contribution.

---

## 4. The current skill bundle is software-engineering wisdom, not numerical wisdom

Look at the nine bundled skills:

| Skill | Useful for HPC? |
|---|---|
| TDD | Wrong shape — manufactured solutions instead, not red-green-refactor |
| no-stubs-no-mocks | Doesn't catch GPU bank conflicts or warp divergence |
| systematic-debugging | F106 IRON LAW protocol is fine; failure modes (OOM, deadlock, non-deterministic reduction) need different debug techniques |
| adversarial-self-review | Six-point checklist asks "what inputs break my code" — answer for HPC is always "non-trivial scale" which the agent can't test |
| brainstorming-approaches | Useful but content-empty without numerical-analysis priors |
| researching-unknowns | Perplexity won't surface "this Kokkos kernel pattern has a 30% slowdown on V100 vs A100" |
| using-bob3-memory | The four pools don't carve up HPC knowledge |
| checking-review-registry | Registry is empty of HPC findings — would take many runs to populate |
| implementing-acceptance-criteria | The DSL doesn't express HPC-shaped criteria |

The honest read: **you're keeping the skills *system*
(auto-installation, integrity audit) and replacing the *content*
with HPC-specific skills.** That replacement is then your
contribution, not bob3-as-it-stands. Bob3 is the substrate; the
new bundle does the work.

This is fine, but it changes the framing of any paper. The
contribution is "an HPC-specific skill+registry pack on top of an
agentic build orchestrator", not "bob3 is good for HPC."

---

## 5. The acceptance-criteria DSL doesn't reach where HPC validation lives

Current DSL:

- `File exists: <path>`
- `Function defined: <module.func>`
- `pytest: tests/...::test_x`
- `python: <expression>` (sandboxed)

What HPC needs:

- `convergence_order_at_least: 2.0` — requires running on N grid resolutions and curve-fitting
- `weak_scaling_efficiency: 0.85 from 1 to 64 nodes` — requires a cluster
- `peak_bandwidth_fraction: 0.4` — requires GPU + Nsight Compute
- `roundoff_safe: yes` — requires precision-perturbation studies
- `conservation_error: < 1e-12` — requires running the actual simulation
- `compute_sanitizer_clean: yes` — requires GPU + sanitizer tooling

You can extend the DSL syntactically (add new criterion types).
You **cannot** extend it semantically without hardware access.
Either the DSL grows hardware-aware criteria (and we're back to
Tier 2 + hardware), or it stays surface-only and the deep
correctness goes untested.

---

## 6. The "dark factory" analogy is a category error

Manufacturing dark factories work because:

1. The product is **identical** across runs
2. The process is **verified at calibration time**
3. **No re-validation per unit** — calibration is the warranty

HPC code is the **opposite** on every axis:

1. Each code is **bespoke** (different physics, different boundaries, different scales)
2. Validation cost is **per-code**, not per-process
3. **Every code requires deep re-validation** before deployment

There's no "calibrate once, run dark forever" regime in HPC. The
analogy implies amortization that doesn't exist. Marketing the
project under "dark factory HPC code" sets expectations the work
cannot meet.

Recommended reframe: **"AI-assisted generation of validated
HPC code with persistent cross-run learning."** Less catchy,
honest about what's actually possible.

---

## 7. The competition isn't "humans" — it's existing libraries and other AI tools

If the goal is "produce a CUDA Euler solver," AMReX already has
one, written by people who understand it. PETSc has a sparse
solver. OpenFOAM has a CFD framework. The hard problems in HPC
software are:

1. **Library composition** — using PETSc + libCEED + Kokkos coherently
2. **Domain extension** — implementing new physics on top of an existing framework
3. **Performance porting** — moving a CPU code to GPU, or one GPU vendor to another

Of these, **#3 is the most defensible "AI dark factory" story.**
Translation tasks have:

- Clear input (the source code)
- Clear output (the target code)
- Verifiable equivalence (run both, compare outputs)
- Established reference implementations (Kokkos / RAJA / SYCL ports of canonical codes)

If the claim narrowed to *"bob3 ports CPU codes to GPU using
Kokkos with reproducible correctness and >40% peak bandwidth,"*
that's tractable, evaluable, paper-worthy.

Other AI-for-HPC tools to be aware of:

- NVIDIA's various Codium-style CUDA assistants
- Cerebras / Groq AI-assisted kernel generation (proprietary)
- Berkeley + MIT + ETH academic groups on AI-for-numerical-methods
- Polyhedral compilation projects (Polly, MLIR, IREE) — different angle but same outcome space

Bob3 is not entering an empty market. The differentiator can't
be "we generate HPC code"; it has to be the orchestration +
registry + recovery loop applied to HPC.

---

## 8. Empirical reality check on AI-generated HPC code (as of late 2025/early 2026)

Published evidence:

- AI-generated HPC code lags hand-tuned by **5–100×** in performance on real benchmarks
- Has **correctness issues at scale** that small unit tests miss
- Doesn't reason about hardware — it pattern-matches kernel idioms it saw during training

Bob3 does not change any of these. It does not add hardware
reasoning, formal verification, or new training data. It adds
orchestration, which is the easy part of the AI-for-HPC problem.

**A defensible bob3 contribution must make orchestration matter
*more* than usual.** That argues for emphasizing the
findings-registry feedback loop (registry value compounds
across runs in a way one-shot generation doesn't), the graduated
recovery pipeline (cost-aware retry economics), and the
integration with hardware-aware verification (when Tier 2 ships).

---

## 9. "Submit jobs at scale" is a re-architecture, not a feature

The user originally suggested adding HPC-specific skills "and
submit jobs at scale." The first half is incremental; the second
half breaks bob3's core synchronous loop assumption.

Currently:

```
spawn sub-agent → await result (minutes) → verify → next iteration
```

Job submission at scale means:

```
spawn sub-agent → it generates code + Slurm script
→ submit job → poll queue (hours) → fetch results (gigabytes)
→ analyze (minutes) → verify → next iteration
```

What breaks:

- The orchestration loop is synchronous — needs an event-driven persistent state machine that outlives a `bob3 run` invocation
- `BOB3_FEATURE_TIMEOUT_SECONDS=3600` (1-hour wall) is wrong by an order of magnitude or more
- RCA's 24-hour cooldown is too short when each attempt takes >24 hours
- Cost accounting changes — node-hours, not API tokens
- Sub-agent state lifetime extends — current agents die after 15 minutes
- Failure modes multiply — queue rejection, walltime exhaust, node failure, filesystem issues, license server timeouts

**Recommendation: defer Tier 3 (scheduler integration) entirely
for the first paper.** It's a 3–6 month engineering project
touching every core module. Doing it concurrently with skill
work guarantees both will be half-done.

---

## 10. What this analysis does NOT say

To be clear, none of the above means "don't do this." The
defensible reading is:

- The HPC direction is real but narrower than the marketing implies
- The skills system is a usable substrate; the content has to be written
- The validation gap is the binding constraint and dictates Tier 2 priority
- A narrow first demonstration (one problem class, one architecture, GPU access for verification) is achievable
- A broad "dark factory HPC code" story is not achievable from where we stand

If you commit to the narrow path with eyes open, this becomes a
real research contribution. If you commit to the broad path
without addressing the validation gap, this becomes a press
release.
