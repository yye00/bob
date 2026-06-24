# bob3 for HPC — paper planning

This directory holds working materials for taking bob3 in the
direction of generating high-performance scientific and technical
computing code (CUDA / HIP / MPI / OpenMP / Kokkos / numerical
methods).

The contents are deliberately *adversarial* — assumptions are
challenged, not assumed. Cheerleading goes elsewhere; this is
where we figure out what's actually defensible.

## Documents in reading order

1. [`00-adversarial-analysis.md`](00-adversarial-analysis.md) —
   honest critique of the "bob3 generates HPC code" claim. What
   the swedish-circle build does and doesn't support; where bob3's
   core abstractions break in the HPC regime; the validation gap
   and why it doesn't go away by adding skills.
2. [`01-plan.md`](01-plan.md) — tiered execution plan: Tier 1
   skills, Tier 2 verification harness, Tier 3 scheduler
   integration, Tier 4 registry seeding. Effort estimates,
   hardware requirements, value-per-effort.
3. [`02-skill-specs.md`](02-skill-specs.md) — concrete outlines
   of the Tier 1 HPC skill bundle. Each skill: name, when to
   apply, rule set, what it doesn't catch.
4. [`03-verification-harness.md`](03-verification-harness.md) —
   Tier 2 design. New acceptance-criterion types, hardware
   integration, sanitizer + Nsight wiring.
5. [`04-registry-seeding.md`](04-registry-seeding.md) — Tier 4
   plan. Source materials, finding structure, target count, how
   to keep it current as architectures evolve.
6. [`05-paper-strategy.md`](05-paper-strategy.md) — venue choice,
   defensible claim, evaluation pyramid, baselines.

## Status

| Decision | Status |
|---|---|
| Direction (HPC code generation, not HPC orchestration) | Committed |
| Tier 1 skills + Tier 4 registry seeding | Plan only |
| Tier 2 verification harness | Plan only — needs hardware access decision |
| Tier 3 scheduler integration | Deferred — separate project |
| Paper venue | Open — see 05-paper-strategy.md |

## Open questions to resolve before we start writing skills

1. **Do we have GPU access during build?** Hard yes/no answer
   needed before Tier 2 design lands. Tier 1 is hollow without it.
2. **Who writes the skill content?** Each Tier 1 skill encodes
   real expertise. We need to identify the contributor for each.
3. **What's the first evaluation target?** A single problem class
   we'll demonstrate end-to-end. Recommendation: 2D Euler solver
   in Kokkos, validated via Sod's tube + MMS, on a single A100.
4. **What's the baseline?** What gets compared against bob3 to
   show the contribution? Plain LLM via Aider? Hand-tuned
   reference (AMReX, Kokkos kernels)?
