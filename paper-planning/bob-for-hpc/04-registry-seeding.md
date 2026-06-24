# Tier 4 — Findings registry seeding

The `checking-review-registry` skill works in the existing bob
because `reviews/findings.yaml` has 100+ R10-* findings discovered
over real builds. An HPC bundle launches with **none** of that
prior art.

This document is the plan for getting the HPC registry to a
useful state without waiting for organic accumulation through
builds.

## Why this matters

Each finding the registry contains is a bug bob's sub-agents
will *not* recreate when `checking-review-registry` is consulted.
A registry of 0 HPC findings means every CUDA kernel bob
generates rediscovers the textbook bugs — bank conflicts,
uncoalesced loads, warp divergence, all the standard mistakes —
at the cost of compute and human review time.

A seeded registry of 100+ HPC findings means the agent reads
*before* writing and avoids the textbook mistakes from the start.

## Source materials

In rough order of finding density (i.e., how many distinct rules
each source generates):

### CUDA / GPU

- **NVIDIA CUDA Best Practices Guide** (current ~v12.x) —
  authoritative; ~40-60 distinct rules suitable as findings
- **NVIDIA CUDA C++ Programming Guide** — overlaps with the BPG
  but covers more language semantics; ~20 additional rules
- **NVIDIA Nsight Compute documentation** — metrics + their
  meaning; useful for tagging (e.g., "low achieved bandwidth"
  patterns)
- **AMD ROCm Programming Guide** (HIP) — ~20-30 rules, many
  parallel to CUDA but with vendor-specific notes
- **GPU Gems** + **Programming Massively Parallel Processors**
  (Kirk + Hwu) — broader patterns, less rule-shaped; cherry-pick

### MPI

- **MPI Forum errata + clarifications** — the formal bug-list
  for the standard itself; ~10-20 entries, each a finding-class
- **"Using MPI" 3rd ed (Gropp, Lusk, Skjellum)** — chapter 6 on
  pitfalls; 15-20 distinct rules
- **MPI Forum's "Common Bugs" page** (when available)
- **Argonne / Oak Ridge / NERSC HPC training materials** — many
  duplicate but each typically adds 2-5 new patterns

### OpenMP / OpenACC

- **OpenMP common-mistakes lists** — mostly from training
  courses; ~15-20 rules
- **"Using OpenMP" (Chapman, Jost, van der Pas)** — chapter on
  pitfalls
- **OpenACC programming guide** — fewer rules, but specific
  data-region pitfalls are worth capturing

### Numerical methods

- **Higham, "Accuracy and Stability of Numerical Algorithms"**
  — densest source for stability findings; ~30-50 rules
  extractable
- **Trefethen, "Numerical Linear Algebra"** — condition number
  / orthogonality / iteration findings
- **LeVeque, "Finite Volume Methods for Hyperbolic Problems"** —
  shock-capturing, limiter, CFL bugs
- **Press et al., "Numerical Recipes"** — controversial source
  but pitfalls section is solid

### Mixed precision

- **NVIDIA Tensor Core documentation** — accumulator precision
  rules
- **Intel + AMD bf16 / fp16 / fp8 reference materials**
- **Higham et al. "A Survey of Numerical Methods Utilizing Mixed
  Precision Arithmetic"** — comprehensive; 10-15 finding-shaped
  entries

### Performance

- **Roofline papers** (Williams, Waterman, Patterson) — for
  arithmetic-intensity tagging
- **Cache-aware algorithms literature** — for memory-hierarchy
  pitfalls
- **NUMA placement** — vendor docs (AMD's NUMA guides; Intel's
  hwloc)

## Finding structure for HPC entries

Same schema as existing R10-* findings, with HPC-specific
conventions for tags and severity:

```yaml
- id: HPC-CUDA-001
  title: "Uncoalesced global memory access in 2D index pattern"
  pattern: uncoalesced-strided-access
  files:
    - "*.cu"
    - "*.cuh"
  severity: high
  status: open
  tags:
    - cuda-perf
    - memory-coalescing
    - gpu-bandwidth
  notes: |
    When threads in a warp access global memory in a strided
    pattern (e.g., `arr[tid * stride]` where stride > 1), the
    accesses cannot coalesce into a single transaction. Result
    is N transactions instead of 1, dropping bandwidth by ~Nx.
    
    Detection: Nsight Compute "Memory Workload Analysis"
    section, "Sectors / Req" should be ~1.0 for coalesced
    access; values like 8 or 32 indicate strided access.
    
    Fix: change data layout (AoS → SoA) or transpose access
    pattern so consecutive threads read consecutive 4-byte
    words.
    
    Reference: NVIDIA CUDA C++ Best Practices Guide §9.2.1.
```

ID convention proposal: `HPC-<DOMAIN>-<NNN>` where domain is one
of `CUDA`, `HIP`, `MPI`, `OMP`, `NUM`, `MIX`, `PERF`. This keeps
the existing `R<round>-<n>` convention for organic findings and
clearly tags pre-seeded ones.

## Tag taxonomy

Standardize tags up front so `RecurringPattern` detection works
across the corpus:

| Tag | What it covers |
|---|---|
| `cuda-perf` / `hip-perf` / `omp-perf` / `mpi-perf` | Performance bug at the framework level |
| `memory-coalescing` | Strided / unaligned access patterns |
| `bank-conflicts` | Shared-memory bank conflict patterns |
| `warp-divergence` | Branches whose predicate varies in a warp |
| `atomic-contention` | Excessive use of atomicAdd etc. |
| `occupancy` | Block size / register / shared mem trading |
| `mpi-deadlock` | Specific deadlock patterns |
| `mpi-correctness` | Tag / size mismatch, buffer aliasing |
| `mpi-scaling` | Patterns that don't scale at high rank counts |
| `omp-race` | Missing reduction, false sharing, missing critical |
| `mixed-precision-trap` | Cases where precision choice matters |
| `numerical-stability` | Catastrophic cancellation, condition number, etc. |
| `convergence-order-loss` | Discretizations that drop expected order |
| `conservation-violation` | Methods that don't conserve as advertised |
| `reproducibility` | Non-deterministic output patterns |
| `roofline-far-from-peak` | Patterns achieving low fraction of theoretical peak |
| `vendor-quirk` | Specific to NVIDIA vs AMD vs Intel |
| `numa-trap` | NUMA-naive allocation / first-touch bugs |
| `boundary-treatment` | Boundary / corner / halo bugs |

A finding can have multiple tags; the orthogonal axis (perf vs
correctness vs portability) should always be expressible from
the tag set.

## Target counts and quality bars

| Tier | Count | Quality bar |
|---|---|---|
| **Minimum to ship** | 50 | Each finding has reproducer, fix, source citation |
| **Recommended at v1** | 100 | + 5 RecurringPattern entries with summary text |
| **Mature** | 200+ | + cross-references between related findings |

Quality bar rules of thumb:

- Reproducer must be specific enough that a senior HPC engineer
  can confirm the bug from the description alone
- Fix must reference the rule from the source (e.g., "see CUDA
  BPG §9.2.1") so contributors can verify
- Severity should reflect typical *production impact*, not
  textbook severity — e.g., uncoalesced access in a hot kernel is
  high; same in a setup-only kernel is medium

## Process for converting source → findings

Per source material (e.g., one chapter of CUDA BPG):

1. Read the chapter, list every distinct rule the chapter teaches
2. For each rule, draft a Finding entry — title, pattern, tags,
   notes
3. Cross-check against existing entries — promote duplicates to
   `RecurringPattern` instead of adding both
4. Have a second person (preferably an HPC engineer who has hit
   the bug in real code) review for:
   - Technical correctness
   - Practical relevance
   - Severity calibration
5. Commit in batches of 10-20 to make review tractable

Estimated rate: ~10 minutes per finding for first draft; ~5
minutes for review pass. So a 50-finding seed is ~12 hours of
expert time spread across both phases.

## Maintenance plan

The registry decays. Architecture evolves; rules from CUDA 9 era
become irrelevant on Hopper. Plan:

- **Quarterly review:** spot-check 10 random findings for
  continued relevance. Mark obsolete ones `status: wontfix` with
  a note.
- **Per-architecture review:** when a new GPU generation ships
  (Blackwell after Hopper, etc.), re-examine all `cuda-perf` and
  `gpu-bandwidth` tagged findings for the new context.
- **Per-spec review:** when a new HPC spec is built and the
  agent hits bugs the registry didn't catch, file new findings
  for each. The organic stream supplements the seeded base.

## What we do NOT seed

- **Project-specific bugs.** Those are per-spec findings.
- **Workarounds for vendor-bug-of-the-month.** Tag those, but
  don't write them into the seed corpus — they'll be obsolete
  before they're useful.
- **Style preferences.** ("Always indent with 2 spaces.") The
  registry is for *correctness and performance bugs*, not coding
  conventions.
- **Speculative findings.** If you can't write a concrete
  reproducer, the finding isn't ready.

## Open questions

1. **License compatibility.** Some source materials (NVIDIA's
   docs, Higham's book) are copyrighted. The findings paraphrase
   rather than reproduce, but the seeding work should review
   each source's license to avoid issues.
2. **Multi-vendor parity.** Should HIP-specific findings be
   filed as "same as CUDA-001 but on AMD"? Probably file
   separately and cross-reference; vendor-specific quirks are
   real.
3. **Versioning.** Findings about CUDA 12 may be irrelevant when
   CUDA 14 ships. Tag findings with the platform version they
   apply to? Yes — add an optional `applies_to` field.
