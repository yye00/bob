# Tiered execution plan

Read [`00-adversarial-analysis.md`](00-adversarial-analysis.md)
first. This document only makes sense if you've internalized the
constraints there.

## Core decision

Split work into four tiers by what kind of effort each requires
and what they produce. Each tier can ship independently and has
defined success criteria.

```
Tier 1: HPC skill bundle           (expert-time, no hardware)
Tier 2: Verification harness       (engineering, GPU access)
Tier 3: Scheduler integration      (engineering, cluster access)  ← deferred
Tier 4: Findings-registry seeding  (expert-time, no hardware)
```

## Tier 1 — HPC skill bundle

**Goal:** every implementation sub-agent that's working on HPC
code has access to disciplined rule sets for CUDA, HIP, MPI,
OpenMP, mixed precision, MMS, numerical stability, and HPC-shaped
adversarial review.

**Deliverable:** ~8 `SKILL.md` files in
`src/bob/skills/`, each 1–3 pages of dense content. See
[`02-skill-specs.md`](02-skill-specs.md) for outlines.

**Effort:** 2–4 weeks of expert time. The work is encoding known
expertise into rule form, not research.

**Hardware:** none required.

**Success criteria:**

- Every skill compiles cleanly (frontmatter parses; markdown renders)
- An implementation sub-agent given a CUDA-flavored feature spec
  references the relevant skills in its plan
- Internal reviewer (e.g., HPC engineer not on the project) reads
  each skill and signs off that the rule set is correct and
  reasonably complete

**Risk:** the skill content is only as good as the contributor's
expertise. Cutting corners produces skills that the agent follows
into wrong patterns confidently. Better to ship four good skills
than eight mediocre ones.

## Tier 2 — Verification harness

**Goal:** bob can validate the code it generates on real
hardware *during* the build, not after deployment.

**Deliverables:**

- New criterion types in `enhanced_verification.py`:
  - `compile_with: <compiler> <flags>`
  - `compute_sanitizer_clean: yes`
  - `nsight_metrics: bandwidth_fraction >= <X>`
  - `nsight_metrics: occupancy >= <X>`
  - `convergence_order_at_least: <X>` (multi-resolution run + curve fit)
  - `conservation_error: <expr>` (run + post-process)
- Scheduler / executor integration for a single GPU node (not a
  full cluster — just hardware access, sync model)
- Caching of expensive verification runs so repeated criteria
  don't re-execute on unchanged code

**Effort:** 4–8 weeks of engineering. This is real software
work; the bob verification layer doesn't trivially extend.

**Hardware:** at least one GPU node accessible to the build
machine (NVIDIA A100/H100 strongly preferred for forward
compatibility; Volta acceptable for development).

**Success criteria:**

- A test feature with `convergence_order_at_least: 2.0` correctly
  passes when the implementation is right and fails when the
  implementation has order-1 errors
- A kernel with deliberate bank conflicts is flagged via Nsight
  metrics
- A kernel with deliberate race conditions is flagged via
  compute-sanitizer
- Verifier wall-clock per criterion stays under 5 minutes for
  development-sized problems

**Risk:** Nsight Compute parsing is brittle and version-specific;
expect to spend non-trivial time on output handling. Plan for
escape hatches (`compute_sanitizer_clean: skipped_no_hardware`)
so the same spec works for contributors without GPU access in
development mode.

## Tier 3 — Scheduler integration (DEFERRED)

**Goal:** bob can submit Slurm/PBS/LSF jobs as part of a feature
implementation and verification cycle.

**Why deferred:**

- 3–6 month re-architecture of the orchestration loop
- Touches signal handling, cost accounting, RCA gating, sub-agent
  state lifetime, every aspect of the loop
- Doing this concurrently with Tier 1+2 guarantees neither lands
  in usable form

**When to revisit:** after Tier 1+2 are landed and the first
narrow demonstration paper is in submission. Tier 3 becomes the
follow-up paper.

## Tier 4 — Registry seeding

**Goal:** the findings registry has enough HPC content that
`checking-review-registry` returns useful prior-art on the first
HPC build.

**Deliverable:** ~50–200 entries in `reviews/findings.yaml` with
the following sources:

- NVIDIA CUDA Best Practices Guide (rules → findings)
- OpenACC and OpenMP common-mistakes lists
- MPI Forum errata + classic deadlock patterns
- Kokkos / RAJA / SYCL FAQ entries
- Numerical stability classics (Higham, accuracy + stability)
- Mixed-precision papers (where to use bf16 / fp16 / fp32 / fp64)
- HPC training course materials (Argonne, NERSC, Oak Ridge curricula)

**Effort:** 2–4 weeks of expert time. Each finding takes ~10
minutes to convert from source to YAML structure. Aim for
quality + tag-discipline, not raw count.

**Hardware:** none required.

**Success criteria:**

- Registry has ≥ 50 HPC-tagged findings before Tier 1 ships
- Each finding has a meaningful tag, severity, and reproducer
  description
- ≥ 5 recurring patterns identified (so `RecurringPattern`
  detection is meaningful from day 1)
- A spot-check by an HPC engineer confirms the findings are
  technically correct and practically relevant

## Combined timeline

| Phase | What's happening | Wall clock |
|---|---|---|
| Setup | Repo prep, contributor identification, hardware access | 2 weeks |
| Tier 1 + Tier 4 in parallel | Skills + registry seeding | 4 weeks |
| Tier 2 | Verification harness | 6 weeks |
| First narrow demo build | 2D Euler in Kokkos, validate end-to-end | 2 weeks |
| Paper drafting | See `05-paper-strategy.md` | 4 weeks |
| **Total to submission-ready** | | **~18 weeks (4.5 months)** |

This assumes one expert-month of dedicated time + one
engineer-month of dedicated time. With less than that, scale up
the wall clock proportionally.

## Decision points

1. **GPU access.** Without it, Tier 2 is impossible and Tier 1 is
   hollow. **Hard decision needed before any work starts.**
2. **First demonstration target.** Recommendation: 2D Euler
   solver in Kokkos, validated via Sod's tube + MMS, on a single
   A100. Alternatives:
   - Sparse triangular solve in CUDA (smaller scope; less novel)
   - Spectral element kernel for incompressible flow (larger scope; more impactful)
   - CPU→GPU porting of an existing reference code (most defensible per `00-adversarial-analysis.md` §7)
3. **Baseline.** What does bob get compared to? Recommendation:
   plain Aider/Cursor on the same spec, plus a hand-written
   reference (probably AMReX for the Euler case).

## Out of scope for this plan

- Multi-cluster / federation
- Production-grade UI (current bob CLI is fine)
- Proprietary GPU vendors beyond NVIDIA / AMD (Tier 1 hits HIP for AMD; Intel oneAPI is later)
- Quantum, neuromorphic, or other exotic accelerators

These are not "we won't ever do them"; they are "they don't go in
this plan." Drift on scope is the most expensive failure mode.
