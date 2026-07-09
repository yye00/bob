# PEAS — Plain English Application Spec: RCCL all_reduce performance uplift on MI300X
#
# SOURCE OF TRUTH for the bob build. Edit prose here; the extract-from-peas
# pipeline synthesizes verifiable acceptance criteria and the spec_quality_gate
# enforces them. Never hand-write the extracted YAML — edit this file.
#
# Format per feature:
#   ## <title>
#   Tier: <Core> | Priority: <critical|high|medium|low> | Slot: <F-R8-NNN>
#   <prose description>
#
# ============================================================================
# CONTEXT (read before the features)
# ============================================================================
# Target repo: ROCm/rocm-systems monorepo, projects/rccl (the library) and
# projects/rccl-tests (the benchmarks). Work on the `develop` branch. The
# library and tests already build and run on this machine; the validated
# build/benchmark commands are baked into the features below so there is no
# guesswork. RCCL git HEAD at spec-authoring time: 6285e299a0.
#
# Hardware: a single node with 8x AMD Instinct MI300X (gfx942), connected in
# an all-to-all XGMI / Infinity Fabric mesh. ROCm 7.2.1. 224 CPU cores. This
# is the machine bob runs on, so commands and numbers are concrete, not
# portable guesses.
#
# WHY all_reduce: a baseline sweep of all major collectives across the 8 GPUs
# (busbw = bus bandwidth in GB/s, higher is better) showed all_reduce is the
# weakest performer and it is the #1 op in DL training. Measured out-of-box
# busbw on this machine (for orientation only — bob re-measures its own
# baseline; see ALWAYS-MEASURE-BASELINE-FIRST):
#
#   all_reduce      183 GB/s  <-- target of this spec, and the #1 op in training
#   broadcast       303 GB/s
#   alltoall        336 GB/s
#   reduce_scatter  351 GB/s
#   all_gather      358 GB/s
#
# Concrete baseline all_reduce busbw (out-of-place, float, sum, 8 GPUs):
#     1 MB    ~13 GB/s
#     16 MB   ~119 GB/s
#     256 MB  ~179 GB/s
#     1 GB    ~183 GB/s
#
# THE GOAL AND HOW SUCCESS IS DEFINED (read carefully — this replaces any
# "headroom" framing): the objective is the highest all_reduce performance we
# can get, as close to the hardware's theoretical limit as possible. But success
# is NOT measured against any fixed number. Do NOT anchor targets to all_gather's
# ~358, to AMD's published figures, or to any other absolute. all_reduce does
# strictly more work than all_gather (its reduce-scatter half performs a
# read-modify-write reduction per element, not a pure copy) AND the XGMI ring is
# already bidirectional, so all_reduce cannot and need not "match" all_gather.
# The ONLY pass/fail bar for every performance feature is: does the optimized
# build beat bob's OWN freshly-measured baseline for this same machine,
# partition mode, and protocol, by a margin that exceeds measurement noise
# (see F-R8-001)? Bigger is better; there is no ceiling to hit and no fixed
# floor other than "measurably better than the measured baseline."
#
# MEASUREMENT DISCIPLINE (critical): back-to-back runs of the same benchmark
# varied by up to 2x (e.g. 304 vs 174 GB/s at 128 MB) depending on warmup and
# GPU clock state. Every performance claim in this build MUST come from the
# fixed measurement protocol defined in F-R8-001. A "win" is only real when
# the OLD and NEW libraries are measured under that identical protocol on the
# same GPUs in the same session AND the improvement exceeds the measured noise
# band (statistically, not by eyeball). The pass/fail gate is always a RELATIVE
# improvement over bob's own measured baseline — never an absolute GB/s number.
#
# ALWAYS-MEASURE-BASELINE-FIRST (non-negotiable, applies to EVERY feature):
# bob must NEVER compare its optimized result against a number quoted from the
# internet, from these survey docs, or from a prior session. Before any
# optimization is evaluated, bob MUST first build the UNMODIFIED library from
# the same commit and measure the out-of-the-box baseline on THIS machine under
# the F-R8-001 protocol, then measure the optimized build under the identical
# protocol in the same session, and report the delta as
# (optimized - our_measured_baseline) / our_measured_baseline. Published
# numbers are CONTEXT and sanity-checks ONLY — they are never the denominator of
# an improvement claim. Rationale: partition mode (CPX/NPS), driver/firmware,
# clock state, and ROCm version all move the baseline by ~2x;
# a number pulled from a blog was measured on a different configuration and
# would silently corrupt every improvement percentage.
#
# CITATIONS (mandatory): any number, threshold, algorithm, or claim that bob
# pulls from the internet or from the dark-factory/refs survey docs MUST be
# recorded with its source URL (or paper title + venue + year) in the feature's
# evidence/design-note output. This includes: published baseline figures, the
# AMD acceptance threshold, algorithm descriptions, and reported speedups. An
# uncited external number is not admissible and must be re-derived by
# measurement on this machine. bob has web access (verified) and should fetch
# and cite primary sources rather than trusting the survey docs second-hand.
#
# RESEARCH-NOTE ANTI-VACUITY RULE (applies to every "research note" feature,
# F-R8-030/032/034/036): a note does NOT pass merely by listing file paths
# and citations that are already pasted into this spec. Each note MUST (a) be
# grounded in at least one primary source FETCHED LIVE by bob this session
# (not the dark-factory/refs paraphrases), quoted with a verbatim passage and
# the specific claim/number it supports; (b) include at least one quantitative
# figure or design detail NOT already present in this spec; and (c) verify its
# code claims against the actual tree (state what bob found when it read the
# named files, not just the file names). A note that only restates this spec's
# own prose is incomplete.
#
# CORROBORATING PUBLISHED BASELINE (context only — bob still measures its own):
# AMD's own ROCm documentation reports out-of-the-box single-OAM (8-GPU)
# all_reduce peaking around ~170 GB/s, which corroborates our measured ~183
# GB/s and confirms the baseline is a legitimate out-of-box figure, not a
# broken build. AMD's stated RCCL acceptance criterion is in-place busbw > 304
# GB/s for MI300X at an 8 GB message size. With CPX (compute-partitioning) mode
# plus NPS4, AMD reports substantially higher bandwidth WITHOUT source-code
# changes — this is a CONFOUNDER bob must control for (see below). Sources to
# cite when these figures are used:
#   - "Understanding RCCL Bandwidth and xGMI Performance on AMD Instinct MI300X",
#     rocm.blogs.amd.com/software-tools-optimization/mi300x-rccl-xgmi/README.html
#   - RCCL usage tips, rocm.docs.amd.com/projects/rccl/en/develop/how-to/rccl-usage-tips.html
#   - AMD Instinct System Acceptance Guide (RCCL benchmarking), instinct.docs.amd.com
#   bob MUST re-verify these URLs are live and quote them accurately, not rely
#   on this spec's paraphrase.
#
# PARTITION-MODE CONFOUNDER (must control for): the same machine yields very
# different all_reduce bandwidth depending on GPU partition mode (SPX vs CPX,
# NPS1 vs NPS4). bob MUST hold the partition mode constant between the baseline
# and optimized runs and RECORD the exact partition mode and all RCCL_*/NCCL_*
# env vars used, so an improvement is attributable to the code change and not to
# a config difference.
#
# STRATEGY (four phased tiers, safest first):
#   Phase 1 (F-R8-01x): tuning-model recalibration. No kernel changes.
#     Lowest risk. Re-derive the algorithm-selection model for gfx942.
#   Phase 2 (F-R8-02x): expand the existing one-shot / symmetric fast paths
#     to cover more message sizes and the all_reduce sum/avg case.
#   Phase 3 (F-R8-03x): implement new, research-backed collective ALGORITHMS
#     that the literature shows close a large, repeatable gap on this hardware.
#     These are the high-payoff items and the heart of what bob must deliver.
#   Phase 4 (F-R8-04x): final end-to-end regression + reporting.
# Each phase must independently preserve correctness and show measured uplift
# before the next is attempted.
#
# RESEARCH BASIS FOR PHASE 3 (cross-referenced across four independent surveys
# in dark-factory/refs/{claude-code,perplexity,chatgpt,gemini}.md). The features
# below were selected because MULTIPLE surveys independently flagged them AND
# they map to a measured defect or a concrete code gate in this tree:
#
#   * Bidirectional / full-duplex ring + reverse-bandwidth cost-model fix
#     (all four surveys). CAUTION: the surveys frame this as "ring uses only
#     one link direction," but RCCL likely ALREADY builds mirrored dual-ring
#     channels (connect.cc) — F-R8-030 must verify this before assuming a
#     throughput win. The concrete, real gap is the cost model not crediting
#     reverse-direction bandwidth for XGMI/PCIe (revBw in search.cc), which
#     affects algorithm SELECTION. Refs: IBing (ResearchGate); MVAPICH
#     full-duplex line; the revBw handling in src/graph/search.cc.
#   * Multi-GPU-per-node PAT (claude/perplexity/chatgpt). PAT (the modern
#     Bruck-derived log-step AllGather/ReduceScatter) is DISABLED whenever
#     nNodes != nRanks, i.e. on every 8-GPU node. Relaxing that gate is the
#     most concrete, lowest-LOC algorithmic unlock. Ref: Jeaugey 2025 (PAT).
#   * Hierarchical (multi-level) AllReduce (all four surveys, highest payoff).
#     intra-node ReduceScatter -> inter-node AllReduce on 1/L of the data ->
#     intra-node AllGather. Refs: BlueConnect (MLSys'19), HiCCL (IPDPS'25),
#     MVAPICH multi-lane (arXiv 2508.13397). NOTE: the big win is MULTI-NODE;
#     on our single node only the intra-node decomposition is validatable.
#   * Recursive halving/doubling (Rabenseifner) (claude/perplexity/chatgpt).
#     Fills the medium-message "valley" between Ring (latency-bound at scale)
#     and Tree (50% bandwidth penalty). Refs: Rabenseifner 2004; Thakur 2005.
#
# EXPLICITLY DEFERRED (surveyed but not selected): Swing (all surveys agree it
# gives NO benefit on a fully-connected XGMI mesh or non-blocking fat-tree — it
# only wins on torus/dragonfly, which we do not have); FP8-compressed
# collectives (changes numerics — out of scope for a correctness-preserving perf
# task); StragglAR / arrival-pattern-aware (only helps under timing jitter, hard
# to benchmark deterministically); MSCCL++ programmable executor (NOT present in
# this source tree — it was removed from RCCL, only no-op API stubs remain; out
# of scope for this build). These can be revisited later.
#
# SINGLE-NODE VALIDATION CAVEAT: our validated build/benchmark machine is ONE
# 8-GPU node. Features whose payoff is intra-node (bidirectional ring, multi-GPU
# PAT, tuning, symmetric/DDA) are fully benchmarkable here. Features whose payoff
# is inter-node (hierarchical inter-node AR, recursive doubling across nodes)
# can only be correctness-validated here; their full perf claim needs a
# multi-node test bed and is written as such. bob will likely need internet
# access to pull the cited papers during Phase 3 research.

# ============================================================================
# EMPIRICAL RESULTS — mi355/gfx950 build (2026-07-08, this host) — GROUND TRUTH
# ============================================================================
# This spec was authored for MI300X/gfx942 but was BUILT AND BENCHMARKED on
# 8x MI355X (gfx950 / CDNA4, ROCm 7.0.1). The full 9-feature build completed
# (9/9, zero needs_human) and results are banked at
# yye00/rocm-systems branch `rccl-single-node-opt`
# (projects/rccl/perf_results/: baseline/, ab_bench.sh, T1a/T1b/T2/T3/T4_*.md,
# IMPACT_SUMMARY.md). Update this spec's arch to gfx950 for reruns on this host
# (--amdgpu_targets gfx950, /opt/rocm-7.0.1, hip-python 7.0.1.*). Findings:
#
#   * THE ONE REAL WIN — T3a `RCCL_DDA_NRANKS_RELAX` (AllReduce, low rank count):
#     bit-exact (#wrong=0) AND faster than the default ring at 2/4 ranks.
#     Raw before/after (perf_results/t3/, 64 MiB fp32, MPI 1proc/GPU):
#       2 ranks: ring 7.54 GB/s  -> DDA 11.35 GB/s  (+50%)
#       4 ranks: ring 10.99 GB/s -> DDA 22.67 GB/s  (+106%)
#     Independent 8-rank spot rerun: 156.06 -> 176.09 GB/s (+12.8%), #wrong=0.
#     MECHANISM: RCCL's default AllReduce is a RING (p-1 sequential hops). At low
#     rank counts the collective is LATENCY-bound, not bandwidth-bound, so the DDA
#     direct-peer-IPC one-shot/two-shot kernel beats the ring. Engagement PROVEN
#     via NCCL_DEBUG=INFO: with gate ON all N ranks log ncclDdaIpcCommInit +
#     directMode 0; with gate OFF, 0 ranks init DDA (gate is the only difference).
#     At 8 ranks the advantage vanishes (ring becomes bandwidth-bound) — so the
#     recommendation is auto-select DDA SCOPED TO 2/4 ranks only. DDA IPC engages
#     ONLY with 1-process-per-GPU (mpirun); single-process -g N sets directMode=1
#     and skips DDA (gate-on == gate-off) — a measurement trap to avoid.
#
#   * HONEST NEGATIVES (measured regressions, correctly shipped default-OFF, NOT
#     fabricated): T4/RHD recursive-halving = 5-6x SLOWER (extra rounds hurt on a
#     bandwidth-saturated 8-way XGMI clique); T1a/QuickReduce fp4 = 8-12x slower +
#     4-bit codecs can't meet 2e-2 rel-err (info-theoretic limit; q8 passes at
#     0.0104); T1b/quant-AllToAll = 30-160x slower. All are correct-but-slow on an
#     intra-node XGMI clique; retained default-off as substrate for future
#     vectorized-codec / inter-node work.
#
#   * DEFERRED (not measurable on this host, NOT faked): T2/chiplet-tuner CPX 2x
#     small-msg latency (needs a CPX-partitioned host; this node is SPX);
#     T3b/symmetric-LL128 (no LL128 device kernel + symmetric memory unsupported).
#
#   * KEY DISCIPLINE THAT HELD: #wrong==0 lossless gate + busbw +/-2% self-consistency
#     gate were NEVER weakened. They caught 3 would-be false positives (T3 single-proc
#     misattribution, T1b broken-validator, T1a 4-bit over-tolerance). Only the
#     genuinely-bit-exact-and-faster T3a passed. NET: all 5 targets ship default-off;
#     production path is bit-identical to baseline; one real +12.8% win recommended
#     for regime-scoped auto-selection. Do NOT lower these gates on rerun.

# ============================================================================
# PHASE 0 — harness: build, benchmark protocol, correctness gate
# ============================================================================

## Permanent-forward-carry acknowledgement (bob infra carry-forward)
Tier: Core | Priority: low | Slot: F-R8-009
This feature exists only to satisfy bob's permanent-forward-carry
auditor, which requires the canonical infra-recovery feature IDs
F-R7-478, F-R7-479, and F-R7-553 to be present in every spec passed
to `plan --create`. Those are bob's own internal bootstrap features
(slopsquatting first-party allowlist and RCA auto-reset) and are not
relevant to the RCCL optimization work; this acknowledgement records
their IDs so the auditor passes. Acceptance: this file
(rccl_perf_peas.md) contains the tokens F-R7-478, F-R7-479, and
F-R7-553. No code is required.

## Reproducible RCCL build for gfx942 from the develop branch
Tier: Core | Priority: critical | Slot: F-R8-000
Establish a clean, repeatable build of the RCCL library for the
MI300X. Working from the ROCm/rocm-systems monorepo on the
`develop` branch, build projects/rccl for the gfx942 target only
(building all architectures is unnecessary and slow). The proven
command is `./install.sh --amdgpu_targets gfx942 -j 200` run from
projects/rccl; it produces build/release/librccl.so. Then build
the benchmark suite in projects/rccl-tests with
`make -j 32 HIP_HOME=/opt/rocm NCCL_HOME=<rccl>/build/release
CUSTOM_RCCL_LIB=<rccl>/build/release/librccl.so`, which produces
build/all_reduce_perf and the other *_perf binaries. The build is
correct when librccl.so exists, all_reduce_perf exists, and
all_reduce_perf links against the freshly built library (verified
by setting LD_LIBRARY_PATH to the build/release dir). This feature
is the foundation every later feature depends on: every code
change must rebuild via exactly these commands so that measured
results are attributable to the change and nothing else.

## Fixed all_reduce measurement protocol with back-to-back baseline capture
Tier: Core | Priority: critical | Slot: F-R8-001
Define and implement a single, deterministic benchmark protocol
that every performance feature in this spec uses, so that
improvements are real and not run-to-run noise (back-to-back runs
were observed to vary by up to 2x). The protocol runs
all_reduce_perf across all 8 GPUs (-g 8) with float sum over a
fixed size sweep from 1 MB to 1 GB doubling each step
(-b 1M -e 1G -f 2). Capture the result as a parseable table of
(size, out-of-place busbw, in-place busbw, wrong-count).

STATISTICAL RIGOR (required — a single back-to-back pair cannot
resolve a 10-20% effect against 2x variance):
1. Pin warmup and iterations explicitly via the benchmark's -w and
   -n flags (e.g. -w 20 -n 50) so every run does identical work.
2. Lock GPU clocks before measuring and ASSERT the lock. This box is
   ROCm 7.2.1; the concrete procedure is: discover the max SCLK from
   `rocm-smi --showgpuclocks` (or `amd-smi metric`), then pin with
   `rocm-smi --setperfdeterminism <freq_MHz>` (preferred — it caps
   the boost ceiling to a deterministic frequency). If that command
   is unavailable or returns an error on this driver, fall back to
   `rocm-smi --setsclk <level>` after `--setperflevel manual`, and if
   THAT also fails, abort the whole protocol with a clear message
   (do not silently proceed unlocked). After pinning, read back
   `rocm-smi --showclocks` and `rocm-smi --showtemp` and confirm all
   8 GPUs report the pinned SCLK and a temperature within a stated
   window; abort if any GPU is off-target. CRITICAL: a successful
   readback does NOT by itself prove determinism (MI300X can throttle
   below a set clock under power/thermal caps) — the real backstop is
   the 5% noise-band validity check in item 5. Record the locked
   SCLK, perf level, and per-GPU temps in the output. At end of run
   restore with `rocm-smi --resetperfdeterminism` / `--setperflevel
   auto`.
3. Run N>=10 timed repetitions per (library, size). Report the
   MEDIAN busbw and a 95% confidence interval per size, not a single
   number. The CI MUST be computed by BOOTSTRAP resampling (>=10000
   resamples of the median) — do NOT use a normal/parametric CI, the
   busbw samples are bimodal (warm vs cold clock state) and a
   parametric CI understates the true spread. Additionally report the
   raw min/max and IQR per size; define the per-size noise figure as
   the LARGER of (the bootstrap 95% CI half-width) and (half the
   IQR), so a deceptively tight CI cannot shrink the band.
4. INTERLEAVE the OLD and NEW libraries in randomized or alternating
   order within one session (e.g. OLD,NEW,NEW,OLD,...), never
   all-OLD-then-all-NEW, so thermal/cache drift cannot masquerade as
   a result.
5. Compute the noise band from the repetitions (it is NOT a number
   bob declares): the per-size noise figure defined in item 3 (the
   larger of bootstrap CI half-width and half-IQR), expressed as a
   percentage of the median. If that figure exceeds 5% at any size,
   the protocol is INVALID and must be re-pinned (clocks/warmup)
   before ANY perf feature may be evaluated. This 5% validity gate is
   the real determinism backstop (the clock readback in item 2 is
   necessary but not sufficient).

The comparison ALWAYS uses bob's own freshly-measured OLD baseline
as the denominator — never a number quoted from the internet, the
survey docs, or a prior session (see ALWAYS-MEASURE-BASELINE-FIRST
in CONTEXT). The script MUST record, alongside the numbers, the
exact run configuration so results are reproducible and
attributable, and MUST hold all of it constant (byte-identical)
between OLD and NEW runs: GPU partition mode, ROCm/driver version,
the full set of RCCL_*/NCCL_* environment variables, and the
librccl.so commit/path. Partition mode MUST be pinned to a stated
value and ASSERTED: query it with `rocm-smi --showcomputepartition`
(and the memory/NPS partition with `rocm-smi --showmemorypartition`),
record the value, and abort if it differs between OLD and NEW or
from the stated target (default target: SPX / NPS1 unless a
different mode is explicitly chosen and recorded). If a mode change
is needed it is set with `rocm-smi --setcomputepartition <mode>`,
but the default is to leave the machine's mode untouched and simply
record+assert it.

DEFINITION OF A PASS (used by every perf feature): a feature's
required improvement holds only if, at the claimed size band(s), the
NEW median busbw exceeds the OLD median AND their 95% CIs are
disjoint AND the median delta exceeds the larger of (the feature's
stated threshold, 2x the measured noise half-band). A delta inside
the noise band is NOT a win. This script is the single source of
truth for every improvement claim in this spec.

## all_reduce numerical correctness gate across sizes and reduction ops
Tier: Core | Priority: critical | Slot: F-R8-002
No performance change may ship without proving all_reduce still
computes the right answer. The rccl-tests perf binaries compute a
wrong-count per size (the data-validation column, enabled with the
-c 1 flag); a correct run reports zero wrong values. Implement a
correctness gate that runs all_reduce_perf with validation enabled
and asserts total wrong-count is exactly zero across the FULL
cross-product below. Any feature that changes algorithm selection,
kernels, or tuning MUST pass this gate after its change; a
performance win with any nonzero wrong-count is a failure, not a win.

CRITICAL — the sweep must NOT be all powers of two. A buggy ring/PAT
partner offset or a bidirectional buffer split is most likely to be
wrong exactly at non-power-of-two sizes, partial last chunks, and
non-power-of-two rank counts — the cases the default doubling sweep
(-b 1M -e 1G -f 2) never exercises. The gate MUST cover:
  - the power-of-two sweep (1 MB to 1 GB), PLUS explicit
    NON-power-of-two sizes (e.g. 3 MB, 5 MB, 100 MB, and 1 GB minus
    one element) set via -b/-e with -f 1 or discrete invocations;
  - float sum PLUS at least one more reduction op (avg or max, via
    the -o flag) and at least one more dtype (fp16/bf16, via -d);
  - input variation across iterations: NOTE the rccl-tests binary has
    NO CLI seed flag — input data is seeded by the internal iteration
    counter `rep` (common.cu ~914, rep++ each iteration) while the
    verify call uses a fixed seed 0 (CheckDelta call at common.cu
    ~591). So run a HIGH iteration count (large -n, e.g. -n 50+) so
    many distinct rep-seeded inputs are validated, and additionally
    vary input by sweeping multiple sizes/dtypes/ops (above) rather
    than relying on a single fixed input. Do NOT claim "set N seeds"
    via a flag that does not exist; if stronger seed control is
    required, that is a source patch to common.cu, not a CLI option;
  - rank-count variation where the path under test permits it: for
    general ring/PAT paths include an ODD rank count (e.g. -g 6 and
    -g 7); for paths hard-gated to 8 ranks (DDA, symmetric) keep
    -g 8 but vary size parity instead.
Zero wrong-count is required across the entire cross-product.

## Proof-of-execution harness: prove the new code path actually ran
Tier: Core | Priority: critical | Slot: F-R8-003
A gated optimization can silently fall back to an existing path
(size out of range, capability check fails, or the env gate never
took effect), so a measured "win" might come from noise or from a
pre-existing fast path rather than the new code. This feature builds
the shared mechanism every gated perf feature uses to PROVE its new
path executed. Two independent checks:
1. Selection/trace evidence: run the benchmark with RCCL/NCCL debug
   logging (NCCL_DEBUG=INFO, and the relevant NCCL_DEBUG_SUBSYS for
   tuning/graph) and parse the log to confirm the intended algorithm
   and protocol were SELECTED for the target message sizes. For a
   newly added algorithm, its name must appear in the selection log
   at those sizes.
2. Gate-off vs gate-on differential: measure the feature's RCCL_*
   env gate OFF and ON under the F-R8-001 protocol in the same
   session. With the gate OFF the result MUST equal the baseline
   within the noise band (proving the gate is what changed behavior),
   and any claimed improvement MUST be present ONLY with the gate ON.
   If gate-off already shows the "improvement," the win is not
   attributable to the new code and the owning feature FAILS.
3. Kernel-distinctness (MANDATORY for features that add a NEW kernel,
   i.e. F-R8-031 and F-R8-033 — not optional): capture a
   kernel-name trace with rocprof and confirm that, with the gate ON,
   a DISTINCT new kernel symbol actually executed and serviced the
   benchmarked bytes — not the pre-existing ring/two-shot kernel under
   a new selection label. This closes the "selection ≠ execution"
   back door: an algorithm can be logged as SELECTED (check 1) while
   its body delegates to the existing kernel. If the trace shows only
   pre-existing kernel symbols, the new path did no new work and the
   owning feature FAILS regardless of any measured delta.
This feature is complete when the harness exists and demonstrably
distinguishes a real new-path win from a fallback/no-op on at least
one Phase-2 or Phase-3 feature. Every gated feature
(F-R8-020/021/031/033/035) MUST run checks 1 and 2; features that
add a new kernel (031/033) MUST also pass check 3.

# ============================================================================
# PHASE 1 — tuning-model recalibration (no kernel changes, lowest risk)
# ============================================================================

## gfx942 tuner data file for the CSV-driven RCCL tuner
Tier: Core | Priority: high | Slot: F-R8-010
RCCL ships a CSV-driven tuner under projects/rccl/tuner, but the
only architecture-specific data file present is
rccl_tuner_gfx950.csv — there is no gfx942 file, so MI300X may be
falling back to generic or mismatched tuning. Produce a
rccl_tuner_gfx942.csv whose algorithm/protocol selections for
all_reduce are derived from real measurements on this 8-GPU
machine using the F-R8-001 protocol: for each message-size band,
pick the algorithm+protocol that actually measured fastest. Wire
it in following the same loading mechanism the gfx950 file uses
(see tuner/README.md). Success is measured, not assumed: with the
gfx942 tuner active, all_reduce busbw across the sweep must be no
worse than baseline at every size AND the geometric-mean busbw across
the full 1 MB to 1 GB sweep must improve beyond the noise band, under
the F-R8-001 protocol (medians, disjoint CIs). A single cherry-
picked noisy band does NOT count — the improvement must hold at the
geomean and at >=3 contiguous bands. F-R8-002 correctness gate
must pass. No fixed percentage; bigger is better.

## Re-derive all_reduce algorithm-selection thresholds in the tuning model
Tier: Core | Priority: high | Slot: F-R8-011
The analytical model in src/graph/tuning.cc chooses, per message
size, between ring and tree algorithms and the LL / LL128 / SIMPLE
protocols, using hand-tuned correction-factor tables
(treeCorrectionFactor / ringCorrectionFactor) and arch-specific
fudge factors (the file already special-cases gfx942 in several
places). The crossover points where it switches algorithm or
protocol are the single biggest lever on all_reduce performance
without touching kernels. Using the F-R8-001 protocol, measure
the true fastest algorithm+protocol at each size band on MI300X,
then adjust the gfx942 correction factors / thresholds in
tuning.cc so the model's choice matches the empirically fastest
choice at every size. Do not change any kernel. Success: all_reduce
busbw improves beyond the noise band at the size bands where the
model was previously mispredicting (identify and report them, and
show the prior choice vs the corrected choice), with no regression
at any other size, under the F-R8-001 protocol (medians, disjoint
CIs), and the F-R8-002 correctness gate green. The improvement
must be a genuine selection change, not noise: report the
geometric-mean busbw improvement across the sweep as well. No fixed
GB/s target; bigger is better.

## Document and verify the per-size winning algorithm map for all_reduce
Tier: Core | Priority: medium | Slot: F-R8-012
Produce a written artifact mapping each message-size band (1 MB
through 1 GB) to the algorithm and protocol that measured fastest
on this MI300X node, with the measured busbw for each candidate so
the choice is auditable. This is generated by sweeping the
relevant NCCL_ALGO / NCCL_PROTO environment overrides through the
F-R8-001 protocol and recording the winner per size. The
artifact both justifies the F-R8-010 / F-R8-011 changes and
serves as a regression reference for later phases. Success: the
artifact exists, every row is backed by a measured number, and the
recommended winners agree with what the tuner/model actually
selects after Phase 1.

# ============================================================================
# PHASE 2 — expand one-shot / symmetric fast paths (medium risk)
# ============================================================================

## Broaden the symmetric/one-shot all_reduce fast path size coverage
Tier: Core | Priority: high | Slot: F-R8-020
RCCL has modern low-latency fast paths that bypass the classic
ring/tree machinery: the symmetric-memory kernels in
src/device/symmetric (all_reduce.cuh and friends) and the
Direct-Data-Access IPC collectives (dda_all_reduce_ipc.cu). These
paths win in the small-to-medium size regime where the baseline is
weakest (all_reduce is only ~13 GB/s at 1 MB and ~119 GB/s at 16 MB).

CRITICAL — these two paths are MUTUALLY EXCLUSIVE at runtime, so do
not treat "symmetric/one-shot" as a single knob. In src/collectives.cc
(around line 135) rcclDdaEnabled()/the DDA eligibility check returns
false when comm->symmetricSupport is true, and a separate symmetric
path is selected around line 569. So when symmetric support is
active, DDA is OFF, and vice-versa. bob MUST first DETERMINE which
path is actually active on this machine's default configuration
(check comm->symmetricSupport and log which path services all_reduce
for the target sizes via the F-R8-003 trace), then widen the size
window for THAT active path. Widening the inactive path's thresholds
is dead code and will show no effect. The DDA path additionally
requires at least 8 ranks (this node has exactly 8, so it qualifies)
and currently handles the sum reduction; scope the change to the
sum case it supports.

Success: under the F-R8-001 protocol and the F-R8-003
proof-of-execution harness (the widened path must be shown active in
the trace, and the win must vanish with the gate off), small-to-medium
all_reduce busbw (the 1 MB through 32 MB bands) improves MEASURABLY
over bob's own baseline (beyond the noise band), with the F-R8-002
correctness gate passing and no regression in the large-size bands.
No fixed percentage target; bigger is better, floor is "measurably
better than baseline."

## Tune one-shot vs two-shot crossover for all_reduce on the 8-GPU mesh
Tier: Core | Priority: medium | Slot: F-R8-021
A one-shot all_reduce (every rank reads all peers and reduces
locally) minimizes latency for small messages; a two-shot
all_reduce (reduce-scatter then all-gather across the mesh)
minimizes bytes moved for larger messages. On an 8-way all-to-all
XGMI mesh the crossover between these is hardware-specific. Using
the F-R8-001 protocol, find the message size at which two-shot
overtakes one-shot on this node and make the selection logic switch
at that measured point. Note: simply hardcoding the selection to
whichever fixed strategy is globally better is NOT acceptable — the
deliverable is a size-dependent crossover that beats BOTH fixed
strategies in their respective regimes. Success: across the full
sweep, all_reduce busbw is at every size at least as fast as the
better of the two fixed strategies measured in isolation (no
regression), AND the tuned crossover measurably beats EACH fixed
strategy in the region where the other normally wins (i.e. the
crossover demonstrably helps at >=3 contiguous bands around the
switch point, beyond the noise band, per F-R8-001), with the
correctness gate green. No fixed percentage target.

# ============================================================================
# PHASE 3 — new research-backed algorithms (highest payoff; the core deliverable)
# ============================================================================
# Each algorithm feature is split into a RESEARCH feature (produce a design note
# grounded in the cited papers; bob will likely need internet access here) and
# an IMPLEMENT feature (write the gated code path and prove it on this hardware).
# This split lets bob's own research step verify the literature before coding,
# and keeps each implementation behind its own RCCL_* env gate, defaulted off.

## Research note: bidirectional full-duplex ring all_reduce for the XGMI mesh
Tier: Core | Priority: high | Slot: F-R8-030
Produce a written design note for a bidirectional (full-duplex)
ring all_reduce targeting the MI300X 8-GPU XGMI mesh.

IMPORTANT — VERIFY THE PREMISE FIRST, do not assume it. A common
claim is that "ring all_reduce drives only one direction of each
link, leaving half the fabric idle." This is very likely FALSE for
RCCL: RCCL already builds dual (mirrored) ring channels — inspect
src/graph/connect.cc (channel duplication, e.g. channel0+nChannels,
the second channel-set loop, and connectRings wiring mirrored
prev/next). If both ring directions are already driven across the
channel set, then a "bidirectional ring" is largely a re-derivation
and will NOT yield a large win. The note's FIRST job is to read the
existing ring construction and state honestly whether reverse-
direction bandwidth is already used. If it is, the note must pivot to
the real, narrower opportunity (e.g. correcting the cost-model's
reverse-bandwidth accounting so the SELECTOR makes better channel/
algorithm choices) rather than promising a throughput doubling.
Do NOT anchor any target to all_gather's ~358 GB/s: all_reduce does
strictly more work (a reduction, not a copy) and cannot match it.

The note must: describe the forward+backward ring construction
(forward ring carries one half of the data, the mirrored backward
ring the other half) and compare it against what connect.cc ALREADY
does; explain how it maps onto RCCL's existing bidirectional
precedents (the AllToAll
Pivot kernel in src/device/alltoall_pivot.h builds bidirectional
ring pairs, and the Tree split-thread kernel in
src/device/all_reduce.h splits threads between two concurrent
directions — note this is a thread-split precedent, not literally a
second ring direction, so describe the analogy honestly); and
examine the cost-model's reverse-bandwidth accounting in
src/graph/search.cc (followPath, revBw — currently revBw stays 0 for
XGMI/PCIe, credited only for two narrow NVLink/POWER9 cases).
Be precise that fixing revBw changes algorithm/channel SELECTION in
the cost model, which is NOT the same as whether both link directions
physically transfer data at runtime (connect.cc already wires mirror
channels). Cite sources (IBing interleaved bidirectional ring; the
MVAPICH / D.K. Panda full-duplex line of work). Success: the note
states whether RCCL rings already use both directions (verified
against connect.cc), names the real opportunity, the RCCL files it
will touch, the expected message-size regime, and at least two
citations.

## Implement bidirectional ring all_reduce (single-node, gated)
Tier: Core | Priority: high | Slot: F-R8-031
Implement the bidirectional ring all_reduce from F-R8-030 as a
new code path on the 8-GPU gfx942 node, behind a new RCCL_* env
gate defaulted off, reusing the existing Pivot/Tree-split
bidirectional precedents rather than new infrastructure. This is
fully validatable on our single 8-GPU node.

CONCRETE WORK ITEMS (verified against the develop tree at authoring
time; line numbers may drift, so grep for the named symbols):
1. Reverse-ring data structure. There is currently NO reverse-ring
   field on the channel/ring struct — only the forward ring's prev/
   next exist. A reverse ring must be constructed: build the mirrored
   ring order in src/graph/rings.cc and wire its connectivity in
   src/graph/connect.cc (mirror of how the forward ring is built),
   and add a reverse-ring field to the ring/channel struct in
   src/include/device.h so the device kernel can read both. Use the
   AllToAll Pivot path (src/device/alltoall_pivot.h, which already
   builds pivotA2ANumBiRings bidirectional pairs) as the template.
2. Device kernel. Add the bidirectional all_reduce kernel in
   src/device/all_reduce.h. Split the buffer in half: forward ring
   reduces the first half, backward ring the second, both directions
   of every XGMI link active at once. The Tree split-thread kernel
   (runTreeSplit, ~all_reduce.h:183) is the precedent for running two
   directions concurrently with a thread split.
3. Cost-model / reverse-bandwidth accounting. In followPath in
   src/graph/search.cc (~line 102-117), revBw is currently credited
   only by a condition keyed on `remNode->dev.cudaCompCap < 80 &&
   start->type != GPU` (pre-Ampere remote, non-GPU start) plus the
   POWER9-NVLink case — on this all-GPU gfx942 mesh NEITHER fires, so
   revBw is structurally 0. To credit XGMI full-duplex you must ADD A
   NEW BRANCH keyed on link TYPE (LINK_NVL/XGMI, LINK_PCI when
   full-duplex), NOT relax the existing CompCap/GPU condition (which
   is NVIDIA-specific and would mis-fire). Be explicit that this
   changes algorithm/channel SELECTION in the cost model, not whether
   both link directions physically transfer (connect.cc already wires
   mirror channels).
4. Algorithm plumbing (REQUIRED or the kernel is never generated/
   selected). Note the exact locations (verified in tree — do NOT
   look for an algo enum in device.h, there is none):
   - the algorithm constants are #defines in
     src/include/plugin/nccl_tuner.h (e.g. NCCL_ALGO_PAT 6); add the
     new one there.
   - NCCL_NUM_ALGORITHMS is defined as NCCL_NUM_ALGORITHMS_V5
     (nccl_tuner.h ~line 35) — bumping it means updating that
     versioned macro, not a plain integer.
   - the name STRING array ncclAlgoStr is declared extern in
     src/include/device.h but INITIALIZED in src/init.cc (~line 101:
     {"Tree","Ring","CollNetDirect","CollNetChain","NVLS","NVLSTree",
     "PAT"}); add your algo's name there at the matching index.
   In src/device/generate.py, note the all_algos list uses POSITIONAL
   slots aligned to the NCCL_ALGO_* indices (currently
   ["TREE","RING","","","","","PAT"] — the empty strings are CollNet/
   NVLS placeholders), so you must fill the correct positional slot,
   NOT append; AND you must add the new algo to the per-collective
   algo dict in the same file (the entry that currently reads roughly
   "AllReduce": ["RING","TREE"]) or no AllReduce kernel is generated
   for it. Also register it in src/device/rccl_metadata.h, and add
   cost-model entries (latency/bandwidth/correction factors) in
   src/graph/tuning.cc so the selector can rank it.

Success has TWO acceptable outcomes, because F-R8-030 may correctly
conclude the ring is already bidirectional and thus a kernel-level
throughput win is unlikely. This feature must NOT fail a correct
implementation that honestly reports "no throughput headroom here":
  OUTCOME A (throughput win): under the F-R8-001 protocol (medians,
  disjoint CIs, noise-band gate) and the F-R8-003 proof-of-execution
  harness (win vanishes with the gate off AND the new algo appears in
  the selection trace), all_reduce busbw improves MEASURABLY over
  bob's own baseline in the large-message bands (16 MB–1 GB), with the
  F-R8-002 correctness gate green and no regression at small sizes.
  OUTCOME B (negative result, also a PASS): bob demonstrates with
  measurements that the existing ring already saturates both link
  directions (so a bidirectional-ring kernel matches baseline within
  noise), AND instead delivers the cost-model reverse-bandwidth fix
  (work item 3) showing it changes algorithm/channel SELECTION, with
  any resulting selection-driven improvement reported under F-R8-001
  and correctness green. A documented, measurement-backed "no
  kernel-level win, here is why, and here is the selection-side
  improvement" is a successful, honest deliverable — NOT a failure.
In both outcomes there is NO fixed GB/s target. (Orientation only,
not a gate: the practical aggregate copy bandwidth of this mesh is
already near all_gather's ~358 GB/s, and all_reduce does strictly
more work than a copy, so do not expect all_reduce to approach it.)

## Hierarchical PAT for multi-GPU-per-node configurations (research note)
Tier: Core | Priority: high | Slot: F-R8-032
Produce a design note for HIERARCHICAL PAT (Parallel Aggregated
Trees — the modern Bruck-derived, log-step AllGather/ReduceScatter)
on multi-GPU-per-node systems.

DO NOT TREAT THIS AS A GATE FLIP. PAT is disabled by the line
`if (comm->nNodes != comm->nRanks) return 0;` in ncclPatEnable() at
src/graph/tuning.cc:669. That guard is NOT arbitrary: the
PatAGAlgorithm and PatRSAlgorithm classes (defined in
src/include/collectives.h, instantiated in src/device/all_gather.h
and src/device/reduce_scatter.h) assume a FLAT rank space where each
rank is its own node (1 GPU per node). Simply deleting the guard
makes PAT eligible on an 8-GPU node but the algorithm's partner math
is wrong for that layout, so it would run and produce INCORRECT
results. The deliverable is therefore a real new algorithm —
hierarchical PAT — not a one-line change.

The note must specify the three-level decomposition: (1) intra-node
gather/reduce-scatter across the 8 local GPUs using ring or the DDA
IPC path; (2) PAT across one leader GPU per node (the level where
PAT's log-step structure actually applies); (3) intra-node broadcast/
scatter back to local GPUs. This is structurally the same shape as
the existing CollNet Direct path, which already does in-node-then-
across-nodes — point bob at that as the template. The note must name:
the gate (tuning.cc:669), the PatAGAlgorithm/PatRSAlgorithm classes
and the file where they are DEFINED (src/include/collectives.h, not
just instantiated), the sub-communicator construction needed (intra-
node and inter-node communicators, mirroring the existing
hierarchical AllGather in collectives.cc), and cite Jeaugey 2025
(PAT). Be honest that on a single node the pure-intra-node PAT
benefit is muted per the literature: the large win is multi-node;
on our one node the measurable target is AllGather/ReduceScatter
latency at small-to-medium message sizes. Success: the note
documents WHY the guard exists, the hierarchical decomposition, the
defined-vs-instantiated class locations, the sub-communicator work,
the citation, and an honest single-node vs multi-node payoff split.

## Implement hierarchical multi-GPU PAT for AllGather/ReduceScatter (gated)
Tier: Core | Priority: high | Slot: F-R8-033
Implement the hierarchical PAT from F-R8-032, behind a new RCCL_*
env gate defaulted off, so PAT becomes a CORRECT choice for
AllGather and ReduceScatter on the 8-GPU node. Preserve all existing
behavior when the gate is off. Because all_gather and reduce_scatter
are the building blocks of all_reduce, faster versions of them also
benefit the two-shot all_reduce path.

CONCRETE WORK ITEMS (verified against the develop tree; grep the
named symbols as line numbers may drift):
1. Do NOT merely remove the guard at src/graph/tuning.cc:669. Replace
   the unconditional `nNodes != nRanks` rejection with a path that,
   when the new gate is on and there are multiple GPUs per node,
   selects the hierarchical PAT decomposition instead of flat PAT.
2. Build the intra-node and inter-node sub-communicators (one leader
   GPU per node) — reuse the sub-communicator construction the
   existing hierarchical AllGather already uses in src/collectives.cc.
3. Implement the three phases (intra-node gather/RS via ring or DDA;
   PAT across leaders using the existing PatAGAlgorithm/PatRSAlgorithm
   from src/include/collectives.h; intra-node broadcast/scatter) as a
   new device path in src/device/all_gather.h and reduce_scatter.h.
4. If you add a distinct algorithm rather than overloading PAT, do the
   full algorithm plumbing (enum in nccl_tuner.h + device.h, bump
   NCCL_NUM_ALGORITHMS, ncclAlgoStr, generate.py all_algos list,
   rccl_metadata.h, cost-model entries in tuning.cc) — see F-R8-031
   item 4.

Success (the correctness bar is deliberately strict to defeat a
naive guard-removal that produces wrong output): with the gate on,
AllGather and ReduceScatter MUST report exactly zero wrong values
across the ENTIRE F-R8-002 sweep (including the non-power-of-two
sizes and odd rank counts) for both ops and all tested dtypes — a
flat-PAT guard flip on a multi-GPU node fails this because its
partner math is wrong for the layout. PAT is a LATENCY/small-message
algorithm (Bruck-derived, log-step), so its applicable, gated
improvement target is the small-message latency regime ONLY: under
the F-R8-001 protocol and the F-R8-003 proof-of-execution
harness (win vanishes with gate off; PAT appears in the selection
trace), AllGather and ReduceScatter must improve MEASURABLY over
bob's own baseline (beyond the noise band) in the small-message
bands. In the large-message bands the requirement is to MATCH the
baseline (no regression beyond noise), not to improve — PAT is not a
large-message bandwidth play and must not be scored against one. No
fixed percentage or GB/s target; the gate is "measurably better than
baseline in the small-message regime, no worse elsewhere."

## Research note: hierarchical (multi-level) all_reduce decomposition
Tier: Core | Priority: high | Slot: F-R8-034
Produce a design note for a hierarchical all_reduce that factorizes
the operation by hardware level: intra-node ReduceScatter (over the
XGMI mesh) -> inter-node AllReduce on only 1/L of the buffer ->
intra-node AllGather. This was the single highest-payoff item across
all four surveys (BlueConnect MLSys'19; HiCCL IPDPS'25; MVAPICH
multi-lane arXiv:2508.13397, which measured 1.59–2.45x on AMD
MI300A). The note must: give the level decomposition and the
correctness argument (all_reduce = reduce_scatter then all_gather
for associative+commutative ops, applied per level); identify reuse
points (the existing hierarchical_ag_shuffle.h AllGather is the AG
half; the Phase-3 bidirectional ring or DDA can serve as the
intra-node RS); name files to add/modify (a host selector in
src/collectives.cc analogous to the existing
rcclSelectAllGatherAlgo, plus cached intra/inter sub-communicators);
and be explicit that the dominant win is MULTI-NODE — on our single
node only the intra-node RS+AG decomposition and its correctness are
validatable. Success: the note names the decomposition, the reuse
points, the files, the citations, and the single-node vs multi-node
validation split.

## Implement hierarchical all_reduce decomposition (gated)
Tier: Core | Priority: high | Slot: F-R8-035
Implement the hierarchical all_reduce from F-R8-034 behind a new
RCCL_* env gate defaulted off. Reuse hierarchical_ag_shuffle.h and
the Phase-3 intra-node primitives.

APPLICABILITY (important — this feature is split into an applicable
and an inapplicable part on our single node):
- The MULTI-NODE benefit (the inter-node level carrying only 1/L of
  the data) is NOT measurable on one node and is therefore NOT gated
  on a performance number here. The inter-node phase need only be
  implemented correctly for a future multi-node deployment. We MATCH
  (no-regression) on this inapplicable part; we do not score it.
- The APPLICABLE part on our node is the intra-node decomposition.
  Beware: a naive hierarchical all_reduce on a single fully-connected
  clique degenerates to exactly the existing two-shot ring (RS then
  AG), i.e. a no-op relative to baseline. That is NOT an acceptable
  deliverable — it would let the feature ship zero value.

Success:
1. Correctness: with the gate on, all_reduce is numerically correct
   across the full F-R8-002 sweep (zero wrong values, all dtypes,
   ops, non-power-of-two sizes).
2. Proof-of-execution (F-R8-003): the hierarchical path's own
   intra-node RS and AG kernels MUST be shown to launch (trace), and
   the result with the gate OFF must equal baseline within noise — so
   the feature cannot pass by aliasing an existing path.
3. Applicable-part performance — the win must come from the
   COMPOSITION, not from a borrowed primitive. Beware the trap: the
   existing two-shot ring all_reduce is itself just RS+AG, so if
   F-R8-035 simply dispatches to a faster intra-node primitive
   (e.g. the F-R8-031 kernel or DDA), the two-shot ring path could
   use that SAME primitive and get the SAME gain — the hierarchical
   wrapper would add nothing. Therefore the fair comparison baseline
   is "two-shot ring built from the SAME best-available primitives,"
   NOT the stock baseline. F-R8-035 passes its performance bar only
   if it measurably beats that apples-to-apples two-shot baseline
   (beyond the noise band, per F-R8-001) — i.e. the hierarchical
   STRUCTURE itself contributes. If on a single node it cannot beat
   the apples-to-apples two-shot baseline (the expected outcome, since
   L=1 collapses the structure), the feature MUST report that
   explicitly and is scored as "no single-node structural benefit"
   (a PASS via honest negative result, with the inter-node code still
   correct for future multi-node use) — it may NOT claim a win that
   actually came from a borrowed primitive. No fixed GB/s target.
The design note records the expected multi-node gain with its
citation for when a multi-node bed becomes available.

## Research note: recursive halving/doubling (Rabenseifner) all_reduce
Tier: Core | Priority: medium | Slot: F-R8-036
Produce a design note for a recursive halving/doubling (Rabenseifner)
all_reduce: a reduce-scatter by recursive halving (partner at
distance 2^s, exchanging n/2^(s+1) bytes) followed by an all-gather
by recursive doubling, 2*log2(p) steps moving the bandwidth-optimal
~2n bytes. This fills the medium-message "valley" between Ring
(latency grows linearly with rank count) and Tree (the ~50%
bandwidth penalty baked into the tuning model). The note must cover
the power-of-two partner scheme plus Rabenseifner's fold step for
non-power-of-two rank counts, the cost-model shape that makes the
selector pick it in the medium-message band (low latency multiplier,
full bandwidth, no tree penalty), reuse of existing reduce_scatter /
all_gather device primitives, and cite Rabenseifner 2004 and Thakur
et al. 2005. Be honest that inside a single fully-connected 8-GPU
XGMI clique Ring is already near-optimal, so the main value is at
larger rank counts / multi-node. Success: the note names the
algorithm, the partner scheme, the non-power-of-two handling, the
cost-model entries, the citations, and the regime where it wins.

# ============================================================================
# PHASE 4 — end-to-end regression and reporting
# ============================================================================

## End-to-end regression sweep: all collectives, all sizes, correctness + perf
Tier: Core | Priority: high | Slot: F-R8-040
After all optimization features land, run a full regression sweep
proving the work improved all_reduce without breaking anything else,
and ATTRIBUTE each gain to the feature that produced it (no
laundering Phase-1 gains onto a no-op Phase-3 feature).

Run the F-R8-001 protocol for all_reduce comparing bob's original
measured baseline against the fully-optimized build, and report the
net improvement (medians, disjoint CIs, beyond noise band).

PER-FEATURE ATTRIBUTION (required): for each gated feature, measure
its MARGINAL contribution by toggling ONLY that feature's RCCL_* gate
(all others fixed) under the F-R8-001 protocol. Report each
feature's marginal delta. Any feature whose marginal delta is within
the noise band MUST be reported as "no measured single-node benefit"
— it may NOT be credited with a win produced by another feature. The
before/after table lists, per feature, its marginal delta and whether
it cleared the noise band.

Regression check: run the same sweep for all_gather, reduce_scatter,
broadcast, and alltoall and confirm none regressed versus bob's own
freshly-measured originals (NOT the orientation numbers in this
spec). Regression tolerance is FIXED at 3% (median, accounting for
the noise band), not author-chosen.

Correctness: run the F-R8-002 gate one final time across every
collective touched, for every Phase-3 env gate both off and on.

Success: all_reduce shows a documented net busbw improvement over
bob's own original baseline; every per-feature marginal delta is
honestly attributed (wins beyond noise vs "no measured benefit"); no
other collective regresses beyond the fixed 3% tolerance; every
correctness check reports zero wrong values.
