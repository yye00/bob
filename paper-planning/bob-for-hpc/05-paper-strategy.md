# Paper strategy

What claim do we make, where do we submit, what evidence do we
need, what baselines do we beat?

This document is the strategic frame around the
[plan](01-plan.md). Tactics live in the other docs; this is
where the larger choices are deliberate.

## The defensible claim

Working hypothesis (subject to revision after Tier 1 lands):

> **An HPC-specific skill bundle, persistent finding registry,
> and hardware-aware verification harness, layered onto an
> agentic build orchestrator (bob3), enables AI-assisted
> generation of validated HPC kernels that are competitive with
> hand-written reference implementations on a single accelerator.
> The contribution is the *integration*: the skill content, the
> seeded registry, and the verification harness work together
> in a way that none of them does alone.**

What this claim DOES say:
- Single accelerator (not cluster)
- Validated (not just generated)
- Competitive with hand-written (a measurable goalpost)
- The integration is the contribution (not bob3 alone, not
  skills alone, not registry alone)

What this claim does NOT say:
- "Replaces HPC engineers"
- "Scales to production cluster workloads"
- "Generalizes across all HPC domains"

The narrower the claim, the more defensible.

## Venue analysis

### Top candidates

#### **SC (International Conference for High Performance Computing, Networking, Storage, and Analysis)**

- **Audience:** HPC practitioners, vendors, lab researchers
- **Bar for systems papers:** moderate; needs scaling evidence
  even if narrow scope
- **Risk:** reviewers will demand multi-node evaluation; if we
  stay single-accelerator, we get desk-rejected for "scope too
  narrow for SC"
- **Verdict:** Stretch goal, not first paper

#### **ISC (International Supercomputing Conference)**

- Similar audience to SC, slightly more European
- Same risk profile
- **Verdict:** Same as SC

#### **ICS (ACM International Conference on Supercomputing)**

- More academic than SC; performance-focused
- Single-accelerator papers do appear
- **Verdict:** Possible target if we land strong perf numbers

#### **PPoPP (Principles and Practice of Parallel Programming)**

- Focuses on parallel programming abstractions
- A skill-bundle-as-DSL angle could play well here
- **Verdict:** Reasonable target

#### **HPDC (High-Performance Parallel and Distributed Computing)**

- Broader than just HPC; systems-y
- Tools and frameworks papers welcome
- **Verdict:** Strong fit for the integration claim

### Workshops at major venues (lower bar, faster cycle)

- **AI4S / ML-for-Science workshops** at NeurIPS / ICML — frame
  as "ML system for science software generation"
- **Workshops at SC** (ML4HPC, Software Engineering for HPC, etc.)
  — these accept incremental work and short papers
- **PASC (Platform for Advanced Scientific Computing)** — Swiss
  conference, narrower audience, more focused

### arXiv tech report

Very reasonable first move. Stake the priority claim, get it in
front of the community, iterate based on feedback before formal
submission.

### Recommended sequence

1. **Initial work + arXiv tech report** (~6 months from start)
2. **Workshop paper at one of: AI4S/NeurIPS, ML4HPC@SC, SE4HPC**
   (fits the 4–8-page format, lower review bar)
3. **Full paper at HPDC or PPoPP** (after the demonstration scales
   to multiple problem classes)
4. **SC or ISC submission** only if we've extended to
   multi-accelerator or multi-node by that point

## Evaluation pyramid

What evidence does each level of paper need?

### arXiv tech report

- One worked example (the demonstration build)
- Cost numbers (compute + wall clock)
- Qualitative correctness (reference comparison)
- Reproducibility appendix

**Tier 1 + Tier 4 + the first demonstration is sufficient.**

### Workshop paper

- Above + at least one ablation:
  - "skills bundle vs no skills" — does the bundle move the
    needle?
  - "registry on vs registry off" — does prior-art consultation
    help?
- Quantitative correctness on the reference benchmark
- Performance measurement (peak bandwidth fraction or FLOPS)

**Adds: 2–4 weeks of evaluation work on top of the arXiv state.**

### Full conference paper (HPDC, PPoPP, ICS)

- Above + breadth across at least 3 problem classes:
  - One algebraic (e.g., sparse triangular solve)
  - One stencil-based (e.g., FV solver for hyperbolic PDE)
  - One reduction-heavy (e.g., particle-in-cell, n-body)
- Performance comparison vs at least one hand-written reference
  (AMReX, Kokkos kernels, hand-CUDA from a paper)
- Statistical significance: each measurement averaged over N≥5
  runs; reported with confidence intervals
- Comparison vs at least one AI baseline (Aider with the same
  spec, or Cursor with manual prompting)

**Adds: 2–3 months of evaluation work on top of the workshop
paper.**

### SC / ISC paper

- Above + multi-node scaling
- Reproducibility checklist filled out
- Artifact evaluation (machine-readable scripts to reproduce
  every figure)

**Requires Tier 3 (scheduler integration) — punted.**

## Baselines

For a credible contribution claim, we need:

### A "no AI" baseline

- A hand-written reference implementation of the same problem,
  by a competent HPC engineer (could be from existing OSS:
  AMReX, deal.II, PETSc kernels)
- Measure: time to develop (hours of human effort), correctness
  (passes the same MMS tests), performance (peak fraction)

### A "naive AI" baseline

- Same spec given to plain Aider or Cursor without the bob3
  skill bundle / registry
- Measure: time to "completed" (some attempts will not complete),
  correctness, performance

### A "bob3 without HPC skills" baseline

- Same spec given to bob3 with the existing software-engineering
  skill bundle (no HPC additions)
- Measure: same as above

### The proposed system

- bob3 + HPC skill bundle + seeded registry + Tier 2 verification
- Measure: same metrics

The contribution is the delta between baselines and proposed.
The strongest argument is when:

- **Naive AI fails** on subtle bugs (kernel produces wrong
  answers at edge cases)
- **bob3-without-HPC-skills produces "compiles and runs" but at
  poor perf** (skills aren't the main constraint)
- **Proposed system catches both** issues and lands within (say)
  2× of the hand-written reference's performance

If the deltas are small, the paper is small. If naive AI matches
proposed, there's no contribution to publish. **Be honest about
what the deltas are when we measure.**

## Threats to the contribution

Things that could kill the paper before submission:

1. **AI base models improve.** If GPT-6 (or Claude Sonnet 5)
   ships before we publish, the "naive AI baseline fails" gap
   may close on its own. Mitigation: publish quickly; don't sit
   on results.
2. **Other groups publish first.** AI-for-HPC is a hot area.
   Mitigation: arXiv early; treat the writeup as a continuous
   process, not a final-submission burst.
3. **Deltas are small.** Possible the skills bundle adds 10%
   correctness improvement but no perf gain. Then the paper
   becomes "small but real" — workshop only, no full conference.
4. **Reviewers want multi-node.** If we get desk-rejected at HPDC
   for being single-accelerator, we have to back off to a
   workshop. Plan submission paths accordingly.
5. **The verification gap reasserts.** If Tier 2 doesn't ship
   with sufficient hardware coverage, our "validated" claim
   becomes weaker than promised. Mitigation: Tier 2 is on the
   critical path; don't try to save schedule by cutting it.

## What success looks like at each milestone

| Milestone | Indicator |
|---|---|
| Tier 1 + Tier 4 land | An impl sub-agent given a CUDA-flavored spec writes coalesced, occupancy-aware code on first attempt; `checking-review-registry` finds relevant prior art ≥ 80% of the time |
| Tier 2 lands | Verification of the demonstration build produces measurable correctness + perf signals, automatically, on a single GPU |
| First demo build complete | bob3 produces a 2D Euler solver that passes Sod's tube + MMS within 2× perf of AMReX, validated end-to-end without human intervention beyond the spec |
| arXiv tech report | All of the above, written up, reproducibility appendix included |
| Workshop submission | Above + one ablation showing the skills bundle is load-bearing |
| Conference submission | Above + 3 problem classes + AI baseline comparison |

## Honest probability estimates

(Subjective, no priors beyond the analysis in
[`00-adversarial-analysis.md`](00-adversarial-analysis.md).)

| Outcome | Probability |
|---|---|
| Tier 1 + Tier 4 ship in 6 weeks | 70% |
| Tier 2 ships with full criterion set in 12 weeks | 50% |
| First demonstration build is genuinely competitive with reference | 40% |
| arXiv tech report lands in 6 months from start | 55% |
| Workshop paper accepted in 9 months | 35% |
| Full conference paper accepted in 18 months | 20% |
| The story holds up against adversarial review at the workshop | 60% conditional on acceptance |

These are sobering on purpose. Set expectations low, deliver
high. Public timelines should be ~50% wider than internal
estimates.

## Bottom line

The paper-worthy contribution is *real* but *narrow*: an
HPC-specific skill+registry+verification stack on top of bob3,
validated on one problem class on one accelerator, with honest
baselines. Anything broader is marketing.

The single biggest risk is the validation gap — if Tier 2 is
weak or skipped, every other claim becomes thinner. Tier 2 is
not optional.
