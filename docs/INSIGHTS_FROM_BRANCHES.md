# Insights preserved from other `bob` branches

`bob91` (this tree) is the **recursive bob generation chain** and the primary working
version. The repo `github.com/yye00/bob` also carries branches from the **older
single-package `bob`** lineage (`bob/orchestrator/`, `engine.py`, `verifier.py`,
`cli/run.py`). Those branches are architecturally different and **cannot be merged
directly** into the bob chain — but their ideas are worth keeping. Each branch
remains on the remote; this doc distills the reusable insight so it can be re-specified
as bob PEAS features.

## `feat/mem0-memory-system`
- **Mem0 semantic project memory** — auto-dedup / evolution of stored lessons; graceful
  degradation when Mem0 is unavailable.
- **Test-stability tracking** — auto-detect tests that are buggy across *independent*
  implementations (a test that fails many distinct correct impls is suspect, not the code).
- **Procedural memory / recipes** — save working code patterns from successes for reuse.
- **Usefulness scoring** — retrieval count + success correlation + complexity
  (attempts-to-resolve); used to rank memories for prompt injection under a token budget.
- **MPI/HPC stderr noise filter** — strip ~20 common HPC noise patterns (psm3, OpenMPI)
  before verification so real errors aren't masked.
- **Audit fixes** — run `.py` contract files via pytest (`-k 'not test_meta_'`); unlimited
  timeout (`timeout_seconds=0`); bound error history (20 live / 50 archived, msgs truncated
  to 2000 chars); treat exit-0-with-no-stdout as PASS for spec-defined scripts.

## `feat/planning-bc-hybrid`
- **Contracts as real `.py` files** in `.bob/contracts/` instead of triple-escaped JSON
  strings; template emits pytest files with **meta-tests** that self-validate the contract.
- **AST-based contract validation** — assertion counting, trivial-contract detection,
  einsum-string validation, forbidden-import checking.
- **UnifiedDecomposer** — generate contracts *immediately per feature* during
  decomposition (unit for children → integration for parent → system for root).
- **Convergence detection** — stop decomposing when Δconfidence < 0.05 for 2 consecutive
  evaluations (replaces fixed depth-limit stopping); safety limits on depth/total-units kept.
- **Verification levels** — `VerificationLevel{unit,integration,system}`; parent contracts
  promoted UNIT→INTEGRATION when decomposed; integration contracts run post-children.
- **DAG validation** — cycle detection + orphan warnings for both flat task lists
  (pre-engine) and work-unit trees (post-engine).

## `claude/enhance-bob-ai-joR12` (planning docs only)
- **Flagship harness-hypothesis experiment spec** — six falsifiable hypotheses (H1–H6),
  V-1…V3 variant inclusion chain, 32-instance workload, ~700 runs (~$5k compute),
  threats-to-validity.
- **bob99 feature backlog** — F-101…F-157 (paper-track namespace, disjoint from bob's
  F0xx product features), tagged Block / Strong / Stretch.
- **`bob-for-hpc` track** — adversarial analysis + tiered plan for HPC code generation
  (CUDA/HIP/MPI/OpenMP), new AC types (`compile_with`, `compute_sanitizer_clean`,
  `convergence_order_at_least`, `conservation_error`, `deterministic_output`).

## How to use these
Re-express a chosen insight as acceptance criteria in `control/peas.md` so the next bob
generation builds and verifies it under the strict bar. Do **not** attempt a code-level
merge from these branches — the package layout differs.
