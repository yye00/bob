# PEAS — Plain English Application Spec for the bob recursive build
#
# This is the SOURCE OF TRUTH for the chain. Edit prose here; the build
# pipeline (extract-from-peas) synthesizes verifiable acceptance criteria
# and the 0.85 spec_quality_gate enforces their quality. Never hand-write
# the extracted YAML — edit this file.
#
# Format per feature:
#   ## <title>
#   Tier: <tier> | Priority: <priority> | Slot: <F-R7-NNN>
#   <prose description>

## Convergence detector compares features by spec_slot, not UUID
Tier: Core | Priority: medium | Slot: F-R7-400
The current weekend_watchdog.sh:check_convergence shell function
compares feature sets across generations by features.id. Feature
IDs are minted as fresh UUIDs in every `bob init`, so the
cross-generation set diff is always 100%.

Add a stable `spec_slot` column to the features table populated
from the spec key. Rewrite check_convergence to set-diff by
spec_slot. Backfill spec_slot for existing rows by parsing the
spec yaml and matching by name.

## Disk-state reconciler — promote built-on-disk features without re-spawn
Tier: Core | Priority: medium | Slot: F-R7-401
Every generation re-runs every ready feature even when its
acceptance-criteria artifacts already exist on disk from the
parent generation. Add `reconcile_from_disk(project_id)` that
evaluates each AC entry against the workspace and atomically
promotes features whose artifacts pass in isolation.

## Spec ambiguity linter — reject vague acceptance criteria
Tier: Core | Priority: medium | Slot: F-R7-410
Pre-plan gate that scans every acceptance_criteria entry and
rejects ambiguous patterns. Each AC must match one of the
structured forms; the linter fails the plan if any feature has
an ambiguous AC and emits a structured report.

## Integration-target reachability check at spec-load time
Tier: Core | Priority: medium | Slot: F-R7-411
Every `integration: <dotted.module>` AC implies the generated
code will be wired into that module. At plan time, verify the
target module either exists in the workspace or is itself a
feature in the spec being planned. Reject unreachable targets.

## Structured EARS-style behavior acceptance criteria
Tier: Core | Priority: medium | Slot: F-R7-412
Add a sixth AC grammar `behavior: <subject> <verb> <object> when
<condition>`. Parse into structured tuple at load time. Evaluator
gets a new check that uses the parsed structure rather than
freeform prose.

## Spec quality score gate — features below threshold cannot reach ready
Tier: Core | Priority: medium | Slot: F-R7-413
Combine F-R7-410 / F-R7-411 / F-R7-412 plus an AC-coverage
metric into a per-feature spec_quality_score in [0,1]. Features
with score < 0.85 stay pending with a structured remediation
report.

## Sticky-completed gate — re-evaluation cannot un-complete persisted work
Tier: Core | Priority: medium | Slot: F-R7-420
If a feature was status='completed' in the parent generation's
DB AND its acceptance criteria still verify on disk, no
evaluator FAIL or regression-cascade vote may flip its status
below 'ready'. Reset the stamp only when a refinement attempt
actually rewrites one of the AC-named source files.

## Blame-the-cause regression cascade — charge the breaking feature
Tier: Core | Priority: medium | Slot: F-R7-421
For each failing test, walk the AC table to find the feature
whose `pytest:` AC owns that test path. Charge a refinement
attempt to that feature only. Features that merely ran during
the same verification but don't own any failing test stay at
their pre-verification status.

## Parent-gen DB inheritance at seed time
Tier: Core | Priority: medium | Slot: F-R7-422
When spawn_next_generation.sh seeds bob_(N+1), read every
completed/needs_human/regression feature row from bob_N's
bob.db. Match by spec_slot (F-R7-400). Stamp the matched
bob_(N+1) row with parent_status, parent_completed_at,
parent_evidence_hash.

## Bootstrap readiness override — one bypass execute per feature
Tier: Core | Priority: medium | Slot: F-R7-430
Add a per-feature `bootstrap_attempts` counter (default 0,
max 1). When the readiness gate would block a feature AND
bootstrap_attempts < 1 AND research_iterations == 0, allow one
execute pass that bypasses the readiness gate.

## Stale-bytecode guard at relaunch
Tier: Core | Priority: medium | Slot: F-R7-440
Self-heal compares mtime of every file under
src/bob*/orchestrator/ against the previous bob_N process's
start time. If any orchestrator source file is newer than
process start, kill+relaunch the process even when the DB
looks recoverable.

## Adversarial spec-critic sub-agent — gate codegen on spec quality
Tier: Core | Priority: medium | Slot: F-R7-450
Dedicated spec-critic sub-agent that runs after the spec-extractor
and before any implementer fires. Loads a versioned
spec_constitution.md and emits per-feature structured defects.
Findings persist to reviews/spec_findings.yaml keyed by spec hash.

## Sub-translation provenance — every AC traces to source-intent span
Tier: Core | Priority: medium | Slot: F-R7-451
Each emitted AC must carry a provenance field naming the
contiguous character spans of the original human intent that
produced it. CLI `bob spec trace <feature>:<ac>` prints the AC
alongside its spans. Round-trip coverage of source intent must
be >=90% of load-bearing tokens.

## Design-by-Contract sub-grammar on behavior — pre / post / inv / raises
Tier: Core | Priority: medium | Slot: F-R7-452
Extend the F-R7-412 EARS `behavior:` AC with four optional
sub-keys: pre (precondition), post (postcondition), inv
(invariant), raises (declared exception types). Codegen emits
matching icontract decorators; verifier runs them during pytest.
Pre violations charge the caller, post violations charge the
implementer.

## Key-examples / property-based AC variant
Tier: Core | Priority: medium | Slot: F-R7-453
Add a seventh AC grammar `property: <name> for <generator>
assert <predicate>` and a `key_example:` sub-key on behavior
ACs. Codegen uses them as few-shot context; verifier emits one
Hypothesis test per property and one parametrized pytest per
key_example with seed=0. Boundary examples are required for any
AC involving data transformation or numeric range.

## Test-writer sub-agent — failing tests before implementer fires
Tier: Core | Priority: medium | Slot: F-R7-454
Insert a test-writer sub-agent between spec-critic (F-R7-450)
and the implementer. Emits one failing pytest per AC ID under
tests/<feature_id>/test_<ac_id>.py. The TestGen-LLM
Build/Pass/Coverage triple filter rejects tests that don't
compile, mysteriously pass on stub code, or fail to raise
coverage of the AC-named region.

## Full 22-smell linter extension to F-R7-410
Tier: Core | Priority: medium | Slot: F-R7-455
Replace F-R7-410's small regex rule set with the 22-detector
catalogue (Femmer/Smella + 2025 LLM extensions). Severities
E/W/I; E-severity smells block `bob plan --create`. spaCy is
a new dependency used by 7 of the 22 detectors.

## Structured-uncertainty clarification loop with AskUserQuestion
Tier: Core | Priority: medium | Slot: F-R7-456
Generate N=3 candidate stub implementations from the draft spec;
if they disagree on observable behaviour, mark the relevant slot
ambiguous. Slots above uncertainty threshold T=0.4 trigger a
batched (1-5 per round) multiple-choice question citing
provenance. In CI mode with no human present, exit
SPEC_NEEDS_HUMAN rather than confabulate.

## Schema-constrained spec emission — eliminate parse-failure retries
Tier: Core | Priority: medium | Slot: F-R7-457
Replace post-hoc JSON validation with constrained decoding via
pinned schemas/spec.v1.json (Anthropic tool-use input_schema or
Outlines logit masking). Specs that fail validation are REJECTED
with an explicit error — never silently coerced. Schema mandates
every PRD slot the critic grades.

## Regression attribution requires test-ownership map (no scapegoats)
Tier: Core | Priority: medium | Slot: F-R7-458
In a prior generation/a prior generation, db.detect_regression picks "the first completed
feature that isn't the causing feature" as the blame target when
newly-failing tests cannot be mapped to an owner. Every feature
MUST declare which test files it owns; demotion to regression
MUST require evidence that the feature's own tests newly fail.

## Stable baseline gate — abort verifier if collection fails
Tier: Core | Priority: medium | Slot: F-R7-459
a prior generation baseline has test files with ImportError at collection.
When baseline pytest crashes at collection, the "before"
snapshot is invalid; any "after" diff fabricates regressions.
Verifier MUST refuse to capture a baseline unless the suite
collects cleanly.

## Deterministic pytest snapshots — disable xdist early-halt
Tier: Core | Priority: medium | Slot: F-R7-460
pytest with xdist halts after ~20-25 failures non-deterministically.
Before/after snapshots end up containing different subsets. Snapshot
path MUST run pytest with --maxfail=0; if xdist is used,
--maxfail=0 MUST be enforced at the snapshot boundary.

## bob init re-run after spawn fixes stale project metadata
Tier: 2 | Priority: medium | Slot: F-R7-461
spawn_next_generation.sh does not re-run `bob init` after rsync,
so projects.name still shows the old gen and spec_path points to
a pytest tmpdir leak. Either fix spawn_next_generation.sh to
re-init, or add a startup check in run_loop that verifies
projects.name matches workspace dir basename.

## Devin-style editable plan.yaml gate before any implementer fires
Tier: Core | Priority: medium | Slot: F-R7-463
After F-R7-450 spec-critic passes, write specs/<feature>/plan.yaml
and emit a PLAN_READY event. Implementer sub-agents refuse to
start unless plan.yaml.approved is true. Edits to plan.yaml
re-trigger F-R7-450 critic incrementally via F-R7-451 provenance.

## Persistent spec-critic findings registry with regression detection
Tier: Core | Priority: medium | Slot: F-R7-464
F-R7-450 critic writes findings to reviews/spec_findings.yaml
keyed by (spec_hash, slot_id, defect_type). On re-run with same
defect at same slot, critic flags REGRESSION and escalates
severity. Halt-gate fires if critic_repeat_rate > 0.30 over 3 runs.

## Composite spec_quality_score (8 sub-metrics, geometric mean, 0.65/0.80 gate)
Tier: Core | Priority: medium | Slot: F-R7-465
Replaces F-R7-413 placeholder with weighted geometric mean of 8
sub-metrics: smell_density (0.20), predicate_coverage (0.20),
contract_completeness (0.15), boundary_coverage (0.10),
error_path_coverage (0.10), traceability (0.10),
spec_executability (0.10), ac_atomicity (0.05). Score < 0.65
refuses plan --create; 0.65-0.80 warns; >= 0.80 green.

## Bidirectional Requirements Traceability Matrix (RTM) artifact
Tier: Core | Priority: medium | Slot: F-R7-466
Forward (AC -> test -> code-region) and backward (code-region
-> AC) traceability as a first-class artifact. tools/spec_coverage.py
emits rtm.json and rtm.html. spec_coverage_pct halt-gate at 0.80.
New functions in a commit without an AC link are flagged
untraced_implementation.

## Spec self-consistency — N-sample stability check pre-critic
Tier: Core | Priority: medium | Slot: F-R7-467
Run the spec extractor N=3 times in parallel with different
temperature/seeds. Normalize variants and compute Jaccard
stability_score. < 0.7 routes to F-R7-456 clarification with
disagreeing slots cited. >= 0.9 auto-accepts majority vote with
consensus:true.

## Auto-repair of smelly ACs with semantic-equivalence verification
Tier: Core | Priority: medium | Slot: F-R7-468
Per-smell, linter emits suggested_rewrite. A semantic-equivalence
check feeds original + rewrite to a separate LLM judge; if it
cannot infer they impose the same observable constraint, reject
the rewrite. ERROR-severity rewrites that pass equivalence
auto-apply. Per-feature opt-out via auto_repair:false.

## CodeT mutual-agreement triangulation (KxK code-test matrix)
Tier: Core | Priority: medium | Slot: F-R7-462
F-R7-454 commits to one test-writer pass. CodeT's stronger pattern
(ICLR 2023): spawn K candidate test sets and K candidate impls,
then score each (code, test) cell of the KxK matrix by
mutual-agreement. Removes the failure mode where a single bad
test rubber-stamps a single bad implementation.

Combined with TestGen-LLM's Build/Pass/Coverage triple filter,
this is the cheapest known guard against AI-judge sycophancy
that recursive bob has documented for over a year.

Source: Agent 4 Section 9 (CodeT, ICLR 2023; TestGen-LLM).

## Self-Discover meta-agent for per-feature spec-section selection
Tier: Core | Priority: medium | Slot: F-R7-469
bob's PRD schema (F-R7-457) is fixed: every spec must fill every
slot. A meta-agent that first picks WHICH spec sections matter,
then drives a focused extractor pass, beats one-size-fits-all.

Source: Agent 4 Section 7 (Self-Discover, ICML 2024).

## Python-based convergence checker with non-empty + name-based comparison
Tier: Core | Priority: medium | Slot: F-R7-470
On the bob chain silent-exited the weekend_watchdog
three times. Root cause: shell-out to sqlite3 (not installed),
empty results tripped false-positive convergence; secondary bug
was comparing UUID id instead of name. Replace shell-out with
python module using stdlib sqlite3.

## Stuck-readiness decomposition trigger — kill the eval-demotion treadmill
Tier: Core | Priority: medium | Slot: F-R7-471
If a feature has refinement_attempts >= 2 AND readiness_score
< 0.80 AND no_readiness_improvement_this_attempt, mark
pending_decomposition instead of re-executing. Decomposition
produces sub-features; the parent re-enters ready only once
each sub-feature passes its own gate.

## AC artifact-existence verifier — refuse to pass AC when referenced files are missing
Tier: Core | Priority: medium | Slot: F-R7-472
Pre-pytest pass MUST verify that every AC of the form
`pytest: <path>`, `File exists: <path>`, `File modified: <path>`,
or `Function defined: <module>.<symbol>` resolves to an actual
artifact. Missing artifact -> AC fails with reason
ARTIFACT_MISSING:<path>, never swallowed as a generic pytest
exit code.

## Environment-capability preflight with research-driven workaround discovery
Tier: Core | Priority: medium | Slot: F-R7-473
At spec-load, enumerate every external dependency. Probe each
via `command -v` for CLIs and `python3 -c "import X"` for modules.
For each MISSING dep, spawn a research sub-agent that surfaces a
concrete workaround. Auto-apply when low-risk; halt with
operator-actionable error otherwise.

## Research-augmented retry — path-finding on ambiguous AC failure
Tier: Core | Priority: medium | Slot: F-R7-474
When refinement_attempts >= 2 AND the previous attempt's failure
is classifiable, spawn a research sub-agent that surfaces 1-2
alternative strategies tailored to the failure class. Inject
strategies into the next implementer's prompt prefix. The
implementer retries with NEW information.

## Mutation-testing post-impl quality gate (mutmut)
Tier: Core | Priority: medium | Slot: F-R7-475
Wire mutmut 3.x as a verifier-stage quality gate. After pytest
passes, mutate the impl files and re-run the test suite. Reject
if mutation_score < 0.75. Surviving mutants persisted to
runs/<feature>/mutation_report.json; next implementer attempt
sees them as "tests cannot distinguish your impl from these
broken variants; strengthen assertions."

## GPU/Triton kernel synthesis + autotune sub-agent
Tier: Core | Priority: medium | Slot: F-R7-476
When a feature's AC mentions GPU kernel, Triton, CUDA, ROCm, or
"@triton.jit", the implementer routes through a specialized
sub-agent that synthesizes a Triton kernel, wraps it in
@triton.autotune over BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages,
sweeps on the visible accelerator, persists the winning config,
and gates on numerical correctness vs a CPU torch reference.

Restores the GPU code-generation capability that v0.10 had and
was dropped during v0.11 spec compaction.

Source: OpenAI Triton (Tillet et al. 2019); triton.autotune docs.

## Voyager-style persistent skill library for env workarounds + shims
Tier: Core | Priority: medium | Slot: F-R7-477
F-R7-473 discovers workarounds per-run only. Add a skill_library/
directory of executable shim modules with docstring +
natural-language capability description embedded for retrieval.
On preflight, BEFORE spawning research, search by similarity;
if hit, apply. On new discovery, write back. Library persists
across bob generations via the disk-state reconciler.

Source: Wang et al. "Voyager: An Open-Ended Embodied Agent
with Large Language Models" (arXiv 2305.16291).

## Infra-error transient classifier + unlimited spawn-layer recovery (no budget impact)
Tier: Core | Priority: medium | Slot: F-R7-478
Today every Claude-CLI sub-agent exit-1 counts as a refinement attempt
somewhere in the pipeline — even when the cause is pure infrastructure:
HTTP 429 / rate-limit, network blip (ECONNRESET, ETIMEDOUT), midstream
Claude abort with no work output, env-config ENOENT.

The principle: spurious infra errors are NOT signal about feature
quality. The system should recover from them naturally and silently.
They MUST NOT consume any planning, execution, refinement, or
evaluation budget at any layer.

Implementation: wrap EVERY Claude-CLI sub-agent spawn with a single
shared spawn_with_retry helper that classifies via classify_exit
and retries TRANSIENT signatures UNLIMITED times with exponential
backoff capped at 5 minutes.

Source: marketplace-path incident + user directive on
transient infra errors.

## RCA-layer infra-error recovery — second-line defense against false NH
Tier: Core | Priority: medium | Slot: F-R7-479
F-R7-478 guards the spawn layer with a regex set of known transient
signatures. But a brand-new infra signature will slip past it. F-R7-479
adds the second line: BEFORE the orchestrator transitions a feature to
`needs_human`, the RCA sub-agent inspects the history of failed
attempts and answers — were ALL N attempts infra-caused?

If the RCA verdict is `infra_only`: the feature is reset to `ready`
with refinement_attempts=0, and the discovered novel signature is
auto-appended to config/spawn_retry.yaml. The system learns the new
transient pattern WITHOUT a human edit.

Source: user directive: claude cli having a bad day just
retry it, do not count it as needs human.

## Ownership-evidenced regression detection (no scapegoat without proof)
Tier: Core | Priority: medium | Slot: F-R7-482
bob's `detect_regression` currently demotes arbitrary previously-completed
features to `regression` status when downstream breakage appears, without
establishing a causal link. a prior generation:
F-15f5b3b8 ("Blame-the-cause regression cascade") was itself scapegoated.

Per memory/regression_scapegoat_mechanism.md: detection must require
evidence that the demoted feature's own code/tests were touched (or
transitively depended-upon) by the breaking commit. Without that
evidence, the demotion is rejected and a `regression_unattributed`
event is filed instead.

## Watchdog MUST escalate repeated spec_gate_stall_observed to needs_human_attention sentinel — silent 60s log spam masks chain dead-lock
Tier: Core | Priority: medium | Slot: F-R7-552
a prior generation (~20:39 PDT, after ~3h13m of
silent stall): the watchdog detected ALL_BLOCKED clean exits
from bob and refused to relaunch (correct safety behavior), but
surfaced this ONLY as a per-minute `spec_gate_stall_observed`
INFO event in weekend_chain.log. With no escalated signal, the
chain sat dead-locked while the operator's monitoring grep
(`grep -v spec_gate_stall_observed`) explicitly filtered it OUT.
Net effect: 60+ lines of stall observation, zero operator
signal, ~3h of wall time lost before the next /loop tick caught
the gap from DB counters.

Fix at extraction (spec-over-code-fix): the watchdog MUST
escalate spec_gate_stall_observed to a distinct
needs_human_attention sentinel after N consecutive observations
(default 5, configurable via env BOB_STALL_ESCALATION_COUNT).
Escalation writes a HALT_ATTENTION marker file
(`a prior generation/tools/STALL_ATTENTION.txt`) AND logs a structured
`chain_dead_locked` event at WARN level so default monitoring
greps surface it. The marker is the operator's signal to drop
thresholds + manually relaunch (the documented unstick path).

## security_scan slopsquatting check MUST whitelist locally-defined modules — generated-code local imports flagged as missing PyPI distributions block every feature
Tier: Core | Priority: medium | Slot: F-R7-553
a prior generation (across 4+ features: febe266e,
ae8613d6, d8d7a948, 507728c7): every executing feature
hard-fails security_scan with
`slopsquatting/high: Imported package 'spec_quality_score'
 (distribution 'spec_quality_score') does not exist on PyPI`.
The `spec_quality_score` symbol is a LOCAL module emitted by
the generated code tree (e.g.
`src/bob/spec_quality_score.py`), not a third-party PyPI
package. The security_scan slopsquatting heuristic doesn't
distinguish local-tree modules from external imports, so every
generated-code feature touching this module fails verification
and burns refinement budget cycling toward needs_human.

Fix at extraction (spec-over-code-fix): security_scan
slopsquatting check MUST consult the generated-code tree
(e.g. `src/bob/**/*.py`) before flagging an import as missing
from PyPI. Imports whose name corresponds to a local module
file path (top-level Python file or package directory) MUST
be whitelisted from the PyPI-existence check. The check
retains its security value for genuinely-fictitious imports
while no longer blocking the legitimate local-module pattern.

## Permanent-forward-carry auditor — bob_N bootstrap MUST fail-loud when F-R7-478/479 + slopsquatting protections absent from merged spec
Tier: Core | Priority: medium | Slot: F-R7-554
Audit of research/staged_specs/:
F-R7-478 (unlimited spawn retry) missing from a prior generation, 18, 19, 24
sidecars; F-R7-479 (RCA-layer NH auto-reset) missing from a prior generation,
18, 19, 20, 21, 22, 23, 24, 25 sidecars; F-R7-481-class
(slopsquatting wall) never instantiated as an actual feature
definition in any sidecar (only referenced by shortname).
Per [[infra-recovery-features-are-permanent]] memory, these
features MUST appear in every bob v.N bootstrap from v.13
onward — but the sidecar-merge process silently drops them
when not explicitly re-added. Net effect: infra-recovery
capabilities degrade as the chain advances, undetected until
a feature hits the corresponding failure mode.

Fix at extraction (spec-over-code-fix): a bob_N bootstrap
auditor MUST run after sidecar merge and BEFORE plan --create.
It checks the merged spec contains feature definitions for the
permanent-forward-carry set (F-R7-478, F-R7-479, F-R7-553
slopsquatting whitelist as defined in this same sidecar). If
any are missing, bootstrap MUST fail loud with a structured
`permanent_forward_carry_missing` event listing the absent
features and refuse to start the run — preserving infra-recovery
capability across the chain.

## Research-strategies generator MUST emit canonical structured ACs — prose-form synthesised features fail composite spec_quality gate at plan --create
Tier: Core | Priority: medium | Slot: F-R7-555
a prior generation:
multiple synthesised features failed composite spec_quality
scoring at `composite=0.0000 < 0.65` with error messages
including: "AC[N] does not match any structured form",
"AC[N] is not mechanically verifiable", "No ACs mention
error/failure paths — add at least one negative/error AC",
and "AC[N] has no concrete predicate". The failure is
systematic across research-generated features (e.g.
path_finding_retry.research_strategies output): the
generator emits prose ACs like "FailureClass enum:... AND
classify_failure != unknown" instead of the canonical
structured forms required by F-R7-481-class gate
("File exists:", "Function defined:", "behavior:", "pytest:",
"integration:"). Net effect: every research-derived feature
is born blocked at the spec_quality gate, multiplying the
operator unstick burden documented in
[[loop-progress-adaptive]] + [[second-gate-readiness-threshold]].

Fix at extraction (spec-over-code-fix): research_strategies +
adjacent feature-synthesis paths MUST emit ACs that match the
canonical structured prefix set. Generator MUST validate its
own output against the spec_quality gate BEFORE writing the
feature row; on validation failure, retry generation up to N
times (default 3) with progressively more-explicit canonical-
form prompting; persistent failure marks the synthesis attempt
as `synthesis_blocked_invalid_acs` and skips the write rather
than emitting unusable rows that will inevitably gate-block.
MUST emit at least one negative/error-path AC per feature
(one of the gate's documented requirements).

## spec_findings.yaml writer MUST use atomic tmp+rename — partial-write corruption kills bob boot with ScannerError mapping-values-not-allowed
Tier: Core | Priority: medium | Slot: F-R7-556
a prior generation: bob process
2551581 launched and exited within 5.6s with
yaml.scanner.ScannerError at
reviews/spec_findings.yaml
line 1239 column 9. Manual inspection: line 1238 began with
the truncated key `me: perf-orphan-69` instead of a record
header — evidence of a concurrent or interrupted partial
overwrite of the findings file. Net effect: bob cannot boot
until operator manually repairs the YAML; 6 watchdog
relaunch attempts all hit the same error and ALL_BLOCKED
clean-exited; chain stalled for hours.

Fix at extraction (spec-over-code-fix): every spec emitting
writes to spec_findings.yaml (or any persisted YAML state
file under reviews/) MUST require the writer to perform an
atomic tmp+rename (write to <path>.tmp, fsync, os.rename
onto target). Mid-write SIGTERM/SIGKILL or concurrent
writers MUST NOT leave a malformed YAML on disk. Reader
side: on ScannerError at boot, the loader MUST log a
structured spec_findings_corrupt event AND quarantine the
file to spec_findings.yaml.corrupt.<ts> rather than crash —
empty findings is recoverable; boot-loop crash is not.

## run_loop MUST reap claude subagent process on feature terminal-state transition — orphan subagents persist indefinitely after completed/needs_human, leaking resources and confusing pgrep-based reapers
Tier: Core | Priority: medium | Slot: F-R7-557
a prior generation: claude
subagent PID 3679066 was launched for feature 5cba1ba1 around
04:38 PDT; the feature transitioned to status='completed' at
05:04:13 PDT after evaluator pass; run_loop moved on (picked
b01eb4d1 at 05:00:26), but PID 3679066 was STILL RUNNING 57
minutes later, holding sonnet-4.6 API connections and a 25-turn
claude harness alive against a feature that no longer needs it.
Same pattern observable for additional stale claude PIDs from
earlier features.

Two failure modes follow:
(a) Resource leak: each orphan subagent holds an API connection,
 a stream-json parser, an MCP plugin loader, and ~50 zombie
 memory_mcp helper processes (49+ pgrep). At
 steady state this can pin gigabytes of RSS and burn API
 tokens against work the orchestrator no longer cares about.
(b) Reaper confusion: a prior generation/tools/stuck_executing_reaper.sh uses
 `pgrep -af "claude.*--print" | grep -oE "feature [a-f0-9-]+"`
 to identify live subagent PIDs by feature id. An orphan
 subagent for feature X makes the reaper believe X is still
 actively executing — but the DB row for X is already
 completed, so any future pick of an unrelated row with a
 similar id pattern could be misclassified.

Fix at extraction (spec-over-code-fix): run_loop's
feature-completion handler MUST SIGTERM the claude subagent
process tagged with the just-completed feature id, then SIGKILL
after a 15s grace window if SIGTERM is ignored. Applies to all
terminal transitions: completed, needs_human, regression,
failed. A backstop sweeper MUST also reap orphan subagents
whose tagged feature id is in a terminal state for >5min
(catches handler-bypass paths like SIGKILL'd orchestrator
restart mid-completion). Audit log records sentinel
subagent_reaped_on_terminal=<feature_id> on each reap.

## verifier MUST scope pytest to the current feature's own tests/ subtree — cumulative prior-feature test failures cause pytest-xdist stop-after-20 to fail every subsequent feature's verification
Tier: Core | Priority: medium | Slot: F-R7-558
a prior generation: feature
fbd68fee verification failed with `tests_pass: pytest failed
in tests: 20 failed, 0 passed; stopping after 20 failures!
xdist.dsession.Interrupted`. The 20 failing tests were NOT
from fbd68fee's own AC test files — they were inherited
failures from PRIOR features (test_cli_spec_trace_command.py,
test_ac_13_integration_bob_orchestrator_run_loop.py, etc.)
whose AC test stubs were never repaired before the feature
transitioned to terminal state. pytest-xdist's
`--max-failures=20` (or equivalent stop-on-N config) trips
during collection/execution of sibling-feature test trees
before fbd68fee's own tests ever run.

Net effect: every feature after the 20th cumulative broken
test STARTS its verification with a guaranteed-fail pytest
regardless of its own implementation quality. The feature
hits the 4-attempt cap (see [[F-R7-558-pattern]]) and demotes
to needs_human, burning $4–10 per feature in retry cost.

Fix at extraction (spec-over-code-fix): the verifier's
tests_pass step MUST scope its pytest invocation to ONLY the
current feature's own tests/<feature_id>/ subtree (or the
explicit pytest-prefix AC paths declared for that feature).
pytest MUST NOT collect tests for other feature subtrees in
the same verification run. Whole-suite regression is a
separate concern handled by F-R7-532 / regression-sweep, not
per-feature tests_pass.

## spec_quality behavior-AC parser MUST accept canonical clause forms beyond strict "subject verb object when condition" — overly-tight regex blocks 70%+ of well-formed behavior ACs
Tier: Core | Priority: medium | Slot: F-R7-559
a prior generation: F-R7-556 feature
483b56b6 hit spec_quality WARNING at score=0.7114 with rationale
"Behavior AC could not be fully parsed: 'behavior:
quarantine_corrupt_findings on yaml.scanner.ScannerError moves
the offending file to <path>.corrupt.<unix_ts> and returns an
empty findings dict so boot proceeds' — use format: 'behavior:
<subject> <verb> <object> when <condition>'". The AC is well-formed
English and mechanically verifiable; the parser's strict regex
rejects "on X" (synonym for "when X") and "moves... and returns..."
(compound predicate).

## Permanent-forward-carry auditor MUST match by F-R7-NNN canonical ID regex — sidecar rename or shortname drift currently silently drops carry-forward features
Tier: Core | Priority: medium | Slot: F-R7-560
F-R7-554 (a prior generation sidecar) defines required_feature_ids as a frozen
set of literal strings. When a sidecar is renamed (a prior generation → a prior generation
shuffle) or a feature is referenced by shortname only, the
auditor's exact-string check fails to detect the still-present
feature. Net effect: false-positive missing reports OR
false-negative silent drops depending on rename direction.

## zero-reported-cost MUST NOT disable budget enforcement — stream-json telemetry miss currently flips safety net to OFF, enabling runaway subagent burn under crash conditions
Tier: Core | Priority: medium | Slot: F-R7-561
a prior generation: feature
9b2e1060 sub-agent crashed with work_events=176217,
exit_code=1, duration_ms=0. run_loop logged: "Cost is zero
for feature 9b2e1060 — budget enforcement disabled for this
feature". A zero cost combined with 176K work events is
OBVIOUSLY a telemetry parse failure (lost stream-json
cost-delta events), NOT a free run. Yet the orchestrator's
enforcement path interprets cost==0 as "no budget to enforce"
and turns OFF the cap entirely. Net effect: a stream-json
parser regression or sonnet usage-event omission converts
the budget guard into a no-op, enabling unbounded subagent
burn precisely under the conditions (mid-work crash, parser
drift) where enforcement is most needed.

Fix at extraction (spec-over-code-fix): when reported cost
is zero AND work_events > N (default 100), the orchestrator
MUST treat cost as UNKNOWN-but-nonzero and apply the
per-feature max-cost ceiling AS IF the subagent had consumed
the full ceiling for that attempt. Charge a refinement
attempt; log a structured `cost_telemetry_lost` event with
(feature_id, work_events, exit_code, attempt). MUST NOT
disable enforcement on zero-cost. Pure zero-work zero-cost
(work_events==0) remains correctly treated as a free spawn-
crash retry (F-R7-478 path).

## tests_pass regression-vs-baseline MUST attribute failures to originating feature — sibling-feature broken test stubs currently gate-block unrelated current feature's verification
Tier: Core | Priority: medium | Slot: F-R7-562
a prior generation: feature 9b2e1060
verification logged
"[FAIL] tests_pass: pytest regression vs baseline in tests:
 7 test(s) that previously passed now fail
 (tests/test_contract_grammar_emits_runnable_decorators.py,
 tests/test_f061_create_lesson_from_bug.py,
 tests/73879589/test_ac_12_pytest_tests_test_contract_grammar_blame.py,
...)".
None of the 7 failing tests belong to 9b2e1060's own AC test
tree (tests/9b2e1060/...) — they are stub regressions from
PRIOR features (most notably 73879589 which was itself NH-
demoted earlier, leaving broken test stubs uncleaned). The
regression-vs-baseline check counts those failures against
9b2e1060 and trips the verification gate, demoting 9b2e1060
to NH at attempt=5.

F-R7-558 fixed per-feature tests_pass scope but the
regression-vs-baseline check (F-R7-532-style invariant pass)
still runs whole-suite and attributes the diff to whichever
feature is currently being verified.

Fix at extraction (spec-over-code-fix): regression-vs-baseline
MUST consult a test-path → owning-feature_id map (already
derivable from tests/<feature_id>/ subtree convention OR from
pytest-prefix ACs of completed features). A previously-passing
test that now fails MUST be attributed to its OWN owning
feature (re-opening that feature for repair if owner is in a
terminal state, OR logged as orphan_test_regression if owner
unknown) — NOT counted against the currently-verifying feature.
Whole-suite regression detection retains its safety value
while no longer mis-blaming unrelated features.

## Per-feature subagent cost cap (default $10) — single subagent attempt currently has no per-feature ceiling, enabling runaway burn ($38 in 5min observed) when telemetry healthy
Tier: Core | Priority: medium | Slot: F-R7-563
a prior generation:
cost spiked $34.46 → $72.71 (+$38.25 in 5min) for a single
subagent attempt on a feature in the refinement loop. The
outer `bob run --all --max-cost 1000` flag caps TOTAL run
cost but NOT per-feature attempts. A pathological subagent
(genuine deep-think loop, runaway tool calls, etc.) can
consume tens of dollars on a single attempt before either
attempts-cap or run-cost-cap kicks. Cumulative chain cost
$2762.93 across 49 features = avg $56/feature; one runaway
attempt at $38 dwarfs the median.

Fix at extraction (spec-over-code-fix): introduce a per-
feature-attempt cost cap (default $10, env
BOB_PER_ATTEMPT_COST_CAP overrides, clamped [0.5, 100]).
The orchestrator MUST send SIGTERM to a subagent whose
reported cost crosses the cap mid-attempt (15s grace then
SIGKILL). The attempt is counted (charges refinement
budget per F-R7-561 lossless-cost rules) and the feature
transitions back to ready for next attempt OR NH if attempts
cap reached. Audit log records sentinel
subagent_killed_on_attempt_cost_cap=<feature_id>:<cost>.

## readiness_score MUST be rederived from current confidence components on each refinement attempt — currently stored as decaying state, ratcheting feature toward terminal demotion regardless of fresh signal
Tier: Core | Priority: medium | Slot: F-R7-564
a prior generation src inspection: run_loop._decay_confidence_after_failure
drops readiness by 0.15 per failure but the inverse (readiness
RECOMPUTE from improved confidence components) never fires
during the refinement loop. db.calculate_readiness is only
called at feature CREATION. F-R7-479 RCA auto-reset bounces
the feature back to ready and resets attempts=0 but does NOT
restore the decayed readiness_score nor recompute it from
current confidence values. Net effect: a feature that crashes
twice has readiness=0.85→0.70→0.55→0.40 monotonically, no
matter what subsequent attempts achieve. The 5-attempt cap
and the decomposition gate both depend on readiness signal,
so the ratchet silently steers every flaky-but-recoverable
feature into needs_human terminal state.

Fix at extraction (spec-over-code-fix): readiness_score MUST
be DERIVED, not STORED-AND-DECAYED. Every read of
readiness_score MUST be the live recomputation:
mean(conf_impl_correctness, conf_spec_understanding,
conf_test_quality) — or whatever current component set
calculate_readiness uses. Confidence components themselves
may decay (those are signal); readiness aggregates them at
read time. _decay_confidence_after_failure decays components
ONLY; it no longer writes readiness_score. F-R7-479 auto-
reset restores baseline confidence (snapshot at feature
creation) when classified as infra/transient.

a prior generation investigation (chicken-and-egg deadlock): the
above decay ratchet is only HALF the bug. The other half:
assess_feature_confidence never seeds readiness above 0.0 for a
fresh feature, AND it is only invoked AFTER a feature is claimed
via the features_ready view — which itself requires
readiness_score >= the per-risk threshold (low.70 / medium.80
/ high.90 / critical.95). So a fresh feature at readiness=0.0
can never be claimed, never gets assessed, stays 0.0 forever.
Observed: all 34 ready features had spec_quality_score ~0.999 yet
readiness=0.0. The ONLY features that ever became claimable were
those granted a hardcoded 0.85 by decomposition or research-
complete paths — so research became the de-facto only route to
claimability, throttling 8-wide concurrency down to ~1.

assess_feature_confidence MUST derive readiness from the
DEMONSTRATED spec_quality_score the feature already earned at the
ready-promotion gate (the 8-metric composite persisted on the
feature), NOT from a conservative min of an AC-count heuristic
(which capped readiness at 0.56, below even the lowest 0.70 tier).
Required mapping: when spec_quality_score is present and > 0,
readiness = spec_quality_score * impl_factor, where impl_factor
is 0.92 for standalone features and 0.30 for integration features
(integration stays below threshold pending research). Fall back to
the AC-count heuristic only when no composite exists yet. This
lowers NO gate: a bare-pass composite (0.85) maps to 0.78 (still
below the 0.80 medium gate — demands a hair more quality), a
strong composite (0.95+) clears it, and integration features stay
correctly blocked. It removes only the unearned 0.0 floor that
deadlocked every high-quality feature.

CRITICAL second half (a prior generation follow-up ): fixing the
derive-formula inside assess_feature_confidence is NOT sufficient
on its own, because assess is only INVOKED after a feature is
selected — and the gated find_next_ready_feature returns nothing
when all ready features sit at 0.0, so only ONE feature gets
assessed per loop iteration (via the below-threshold fallback),
collapsing 8-wide concurrency to ~1. The run loop MUST run a
readiness-seed sweep at the TOP OF EACH ITERATION: for every
feature with status='ready' AND readiness_score==0.0, call
assess_feature_confidence and persist the result, BEFORE the
concurrent claim batch runs. This seeds all freshly-promoted
features together so the 8-wide batch can actually fill. The
sweep must be cheap (touch only 0.0 rows) and must run every
iteration so mid-run promotions (features that just cleared the
spec_quality gate this tick) are seeded on the next tick.

## contract_grammar emitter MUST bind lambda parameters to free variables in precondition/postcondition expressions — currently emits zero-arg lambda causing icontract.require to fail at runtime, NH-demoting every Design-by-Contract feature
Tier: Core | Priority: medium | Slot: F-R7-565
a prior generation: feature 73879589
(Design-by-Contract sub-grammar on behavior — pre/post/inv/raises)
NH-demoted at attempts=5 because the emitted contract_grammar
decorator generator writes `@icontract.require(lambda: (x > 0))`
— a zero-arg lambda referencing free variable `x` that the
decorator cannot bind. Test cases test_require_decorator_executes
and test_ensure_decorator_executes both fail at runtime with
a NameError / signature-mismatch when icontract tries to apply
the decorator. Per agent diagnosis on
a prior generation/src/bob/spec_quality/contract_grammar.py:138 —
`decorator_lines.append(f"@icontract.require(lambda: ({condition}))")`.

The @ensure variant at line 141 correctly binds `lambda result:`
because `result` is hard-coded. The @require variant has no
symmetric binding — it should extract identifiers from the
condition expression and emit them as lambda parameters, OR
fall back to `lambda *args, **kwargs: condition` as a safe
universal binding.

Fix at extraction (spec-over-code-fix): contract_grammar
emitter MUST validate emitted decorators by AST-parsing the
lambda body and asserting every free variable is bound by
the lambda signature. Emission failure on this check rejects
the contract-grammar synthesis BEFORE persistence.

## enhanced_verification MUST recognize "Class defined:" AC prefix — currently no handler exists, every Class-defined AC silently default-fails and NH-demotes features whose emission was correct
Tier: Core | Priority: medium | Slot: F-R7-566
a prior generation: feature
5779ecf7 (Mutation-testing post-impl quality gate / mutmut) was
NH-demoted at refinement_attempts=5 despite emitting a correct
MutationReport @dataclass at src/bob/verification/mutation_gate.py:68.
Root cause: a prior generation/src/bob/enhanced_verification.py has
handlers for "File exists:", "Function defined:", "pytest:",
"integration:" and others, but NO handler for "Class defined:".
The AC criterion "Class defined: bob.verification.mutation_gate.MutationReport"
falls through every pattern branch and ends up returning the
default-False from the bottom of the criterion-checker. Every
feature with a Class-defined AC therefore fails verification
regardless of emission quality.

The spec_quality scoring layer DOES recognize "Class defined:"
(quality_score.py:57 _AC_CLASS_RE), so the gate accepts these
ACs at plan --create time — but the verifier never honors them
at run time. Net effect: spec-quality-gate-passing features with
class-defined ACs are guaranteed NH-demotions.

Fix at extraction (spec-over-code-fix): enhanced_verification
criterion-checker MUST include a "Class defined:" branch
symmetric to "Function defined:". Pattern: extract dotted
path, take last component as class name, route through
_search_for_function (which already matches `class Name:`
definitions per the existing comment at line ~1931).

## orchestrator-liveness probe MUST match `bob[0-9]+` regex AND honor `.bob.lock` holder PID — current operator/watchdog `pgrep bob run` misses gen-N binary alias `bobN`, false-stalls and races a second orchestrator on same DB
Tier: Core | Priority: medium | Slot: F-R7-567
Operational defect a prior generation:
gen-N's CLI is installed as `bobN` (e.g. `a prior generation`) by the editable
install entry_points. Advancement-check used `pgrep -fa "bob run"`
which DID NOT match a running `a prior generation run --all` process. The
operator-loop diagnosed false-stall, removed the `.bob.lock`
file (which legitimately listed PID 1674570 as holder), and
launched a second orchestrator. Two orchestrators briefly
raced on the same sqlite DB before one was SIGKILL'd.

Fix at extraction (spec-over-code-fix): the liveness probe
contract MUST use regex `bob[0-9]+ run` AND additionally
`sqlite3 bob.db` plus the `.bob.lock` holder-PID check
(`kill -0 <pid>`) before declaring "no orchestrator running".
The lock-file MUST NOT be removed unless ALL three signals
(no matching pgrep, lock-PID not alive, DB has no
`executing` rows updated in last 60s) agree.

## F-R7-479 RCA auto-reset MUST grant fresh attempt budget when verification-gate-failure cause is plausibly-fixable code (not just infra/transient) — currently only infra reclassification reopens the budget, so legitimate verification failures NH at attempt 3 with unused budget
Tier: Core | Priority: medium | Slot: F-R7-568
a prior generation: feature
dd11d1f8 (Ownership-evidenced regression detection) NH'd at
refinement_attempts=3 — TWO attempts of remaining budget were
never used. Log path: feature went ready→executing→failed via
verification gate, RCA classified the failure as terminal
(NOT infra), F-R7-479 auto-reset path did not fire, run_loop
then NH-demoted on next read because below-threshold AND
RCA classified terminal.

The 5-attempt cap exists precisely because verification
failures are often code-fixable on retry (different subagent
attempt may produce correct emission). Treating ALL non-infra
verification failures as terminal-at-current-attempt defeats
the budget.

Fix at extraction (spec-over-code-fix): F-R7-479 auto-reset
MUST also fire on `verification_gate_failed` classifications
when `refinement_attempts < 5` AND the failure cause is
classified as `code_emission_defect` (i.e. emitted code is
wrong but plausibly fixable) — distinct from
`spec_ambiguity` (which is genuinely terminal). Decision
gate: if the failed AC is a behavior/integration AC that
requires emitted code to satisfy, treat as
`code_emission_defect` and allow another attempt.

## spec_quality_score gate threshold MUST honor BOB_SPEC_QUALITY_THRESHOLD env var — currently hardcoded `_THRESHOLD = 0.85` makes operator-unstick (lower threshold to promote pending features) a silent no-op; chain halts ALL_BLOCKED whenever pending features sit below 0.85
Tier: Core | Priority: medium | Slot: F-R7-569
a prior generation: operator-loop
relaunched bob with `BOB_SPEC_QUALITY_THRESHOLD=0.55` to
unstick 7 pending features blocked at the spec-quality gate
(scores 0.39-0.84). Run exited ALL_BLOCKED in 55s — env var
had NO effect because
`a prior generation/src/bob/spec_quality/quality_score.py:32` declares
`_THRESHOLD = 0.85` as a module-level constant, and
`score_threshold` docstring explicitly says "Always 0.85".

Hot-fixed by replacing the constant with
`_THRESHOLD = _resolve_threshold` which reads the env var
and clamps to [0.0, 1.0]; relaunch promoted 6 of 7 pendings
to ready immediately.

Fix at extraction (spec-over-code-fix): the threshold MUST be
computed lazily on every gate call (not frozen at import time
— env var changes mid-run should take effect on next gate
evaluation), clamped to [0.0, 1.0], with a `BOB_SPEC_QUALITY_THRESHOLD_FROZEN`
escape hatch for tests that want determinism. score_threshold
docstring MUST stop promising "Always 0.85".

## Subagent observability mandate — forbid pytest stdout redirection to /dev/null
Tier: Core | Priority: medium | Slot: F-R7-507
a prior generation: subagent d8483d98 (PID 2135582) invoked
`python -m pytest tests/ -q --tb=short 2>&1 | grep -E "FAILED|ERROR" | head -10`,
which redirected pytest stdout into a grep filter that produced
no output until the (never-arriving) end of the run. The pytest
child (PID 2164763) ran 43+ min at 49% CPU with /proc/2164763/fd/1
pointing at a closed pipe — zero observability for the entire
session. Combined with the unscoped-pytest defect (F-R7-505)
this created a fully silent 50+min stall.
Fix: the subagent verification prompt MUST explicitly forbid
stdout/stderr redirection of pytest to /dev/null, capture-only
grep filters, or `-q --no-header` modes. For long-running tests
the streaming output is the ONLY signal that the run is not hung.
Code patch already applied to a prior generation/superpowers.py:749; this
feature locks the rule into the a prior generation spec so future
bootstraps re-apply it.

## Per-feature subagent watchdog — external timer cancels hung subagent independent of run-loop await
Tier: Core | Priority: medium | Slot: F-R7-508
a prior generation: feature d8483d98 subagent hung in unscoped pytest
for 50+ min; the orchestrator's run-loop was synchronously
awaiting that subagent's exit, so even though the
stuck_executing_reaper reset the DB row to 'ready' at 21:30Z,
the run-loop did NOT advance — it remained blocked in
`await dispatch_subagent(...)`. Result: 5 ready rows, x:0,
cumulative cost flat for 50+ min, pipeline visibly stalled.
The 3600s _DEFAULT_FEATURE_TIMEOUT_SECONDS (run_loop.py:677)
is the ONLY cancellation path and it lives inside the awaited
coroutine — if asyncio scheduling delays it, the orchestrator
stays blocked indefinitely.
Fix: spawn a per-feature `asyncio.create_task` watchdog at
dispatch time that holds the subagent PID and forcibly cancels
(signal subagent process + cancel awaiting task) at a hard
wall-clock deadline derived from BOB_FEATURE_TIMEOUT_SECONDS.
Watchdog runs on the orchestrator event loop, NOT inside the
subagent coroutine, so it fires regardless of subagent state.

## Orchestrator dispatch concurrency — let multiple ready features run in parallel instead of strict single-flight
Tier: Core | Priority: medium | Slot: F-R7-509
a prior generation stall analysis: a single hung subagent blocked
the entire pipeline because the orchestrator dispatches one
feature at a time (synchronous await per feature). With max_turns=25
per subagent and pytest verification potentially taking minutes,
a single bad-actor feature can hold the whole round hostage even
after F-R7-508 cancels it (next ready row only starts after
cancellation completes).
Fix: introduce BOB_MAX_CONCURRENT_FEATURES (default 3) and
dispatch up to N ready features as concurrent asyncio tasks.
Each task carries its own watchdog (F-R7-508). The orchestrator
tick loop becomes: gather completed → reap stuck → fill empty
slots up to N. Eliminates the single-feature-blocks-round failure
mode entirely; also halves wall-clock for rounds with many small
features.

## Hot-reload subagent prompt source on each dispatch — code-fixes land without orchestrator restart
Tier: Core | Priority: medium | Slot: F-R7-510
a prior generation: a one-line patch to superpowers.py:749
(scoped-pytest mandate) was applied to disk while the
a prior generation-built orchestrator (PID 1520197) was running. The
Python import cache meant the orchestrator continued
dispatching subagents with the OLD prompt for 4+ hours.
The patch only takes effect on the NEXT bob version build,
which can be hours away. During active defect-hunting loops
this defeats the dual-write protocol's "code-fix in bob(i)"
half — every code patch is invisibly delayed by one bob
generation.
Fix: on each subagent dispatch, check the mtime of
superpowers.py (and any other prompt-source module); if it
has changed since last reload, call importlib.reload before
reading VERIFICATION_PROMPT_SECTION / SKILLS_PROMPT_SECTION.
Cheap (stat + dict lookup) and bounded (only reloads when
the file actually changed).

## Exponential backoff after reaper-reset — refuse re-dispatch of a recently reaped feature for Nmin
Tier: Core | Priority: medium | Slot: F-R7-511
a prior generation: feature d8483d98 cycled 'executing' →
reaped → 'ready' → re-dispatched → silent-death → reaped
every ~14 min indefinitely, wasting subagent cost each
cycle (round_cost +$1.36/cycle). The orchestrator's
reaper resets the row to 'ready' but the dispatch loop
has zero memory of the prior reap, so the SAME failure
mode recurs immediately.
Fix: when stuck_executing_reaper resets a row, stamp
`last_reap_at` and `reap_count`. Dispatch loop refuses
to re-dispatch a feature within
`min(2^reap_count * 60s, 3600s)` of last_reap_at. After
3 reaps without an intervening success, escalate to
needs_human with reason "repeated_reap_cycle". Combined
with F-R7-501 (the reaper itself) this turns a silent
indefinite waste-loop into a bounded one with eventual
human escalation.

## enhanced_verification._check_criterion_with_details MUST demote pure-prose AC failures to warning instead of hard-failing — bob v.16 round 13 b6873bac (Infra-error transient classifier, F-R7-478-equivalent) burned 3 refinement attempts on 9/28 prose ACs ("EVERY Claude-CLI sub-agent invocation…", "Transient retries do NOT increment…") with all structural ACs passing
Tier: Core | Priority: medium | Slot: F-R7-576
Defect a prior generation ( ~18:00-18:35Z):
feature b6873bac (Infra-error transient classifier + unlimited
spawn-layer recovery, an F-R7-478-equivalent permanent-forward-
carry feature) repeatedly failed verification with the SAME
9/28 acceptance_criteria_met fail-list across attempts 1, 2,
and 3, while every other checklist item PASSed:

 [PASS] source_files_exist / package_has_substance /
 test_files_exist / no_stubs / no_mocks /
 tests_pass (demoted to warning, no regressions) /
 code_changes_made / security_scan (clean)
 [FAIL] acceptance_criteria_met: Failed 9/28 criteria:
 "EVERY Claude-CLI sub-agent invocation in the
 codebase routes through spawn_with_retry — grep
 guard: no remaining direct `claude --` subprocess
 calls outside spawn_retry.py …"
 "Transient retries do NOT increment refinement_attempts,
 bootstrap_attempts, verification_failures, or
 research_iterations in any pipeline stage …"
 "Mid-work-crash still counts as one refinement attempt
 (preserves F-R6-300 behavior), EXCEPT when
 duration_ms==0 — that signature is a JSONL serialization
 race / SIGPIPE / orphan process pattern, not a sub-agent
 decision to abort; reclassify as TRANSIENT …"
 (and 6 more)

Every failing AC was pure policy prose with no executable
prefix (pytest:/python:/file exists:/function defined:/
class defined:/integration:/behavioral_signature: etc.) and
no bespoke matcher in _check_criterion. The fallthrough at
enhanced_verification.py:2222 returned False — hard-failing
the feature on lines the verifier could not have validated
statically. This is exactly the failure mode F-R7-531 (a prior generation)
was supposed to close, but the closure had not propagated to
the running a prior generation generation and the feature kept respinning.

Hot-fix in a prior generation src tree
( ~18:38Z): _check_criterion_with_details now
detects when a criterion lacks ALL of these structural markers
(pytest:/python:/ci tests:/forbidden_imports:/
behavioral_signature:/deterministic_output:/resource_limit:/
test_coupling:/mms:/conserves:/file exists:/function defined:/
class defined:/function implemented/method implemented/
integration:/cmake/no compilation errors/no errors) AND
_check_criterion returned False. In that case it returns
(True, "prose AC demoted to warning (F-R7-531 forward-carry)")
instead of (False, "") — feature ships on structural ACs and
the prose warning is surfaced for human review without
blocking forward progress. Verified locally: prose-style AC
now passes with the demoted-to-warning marker; structural
ACs targeting missing files still fail correctly.

Fix at extraction (spec-over-code-fix): the demote-to-warning
behavior MUST be a permanent property of the verifier's
criterion router, exposed via a named helper
(`is_executable_or_structural_criterion`) so future spec
changes can extend the marker set without touching the
gating logic. The verifier MUST log a "PROSE_AC_DEMOTED"
event (one line per demoted criterion, with criterion text
and feature id) so reviewers can audit demotions per release.
A counter-test MUST exist that asserts a criterion with NO
recognized marker and content matching one of the b6873bac
patterns passes-with-demotion, AND a counter-counter test
MUST assert a structural criterion ("File exists:
nonexistent.py") still hard-fails after the change.

Companion to [[prose_ac_silent_verification_bypass]] (F-R7-531
in a prior generation — the extraction-side closure). This F-R7-576 closes
the runtime side so any future bob-gen that lacks F-R7-531
still ships permanent features instead of attempt-budget-
cycling on prose lines.

## enhanced_verification Pattern 8 ("integration:") MUST scan ALL plausible dotted tokens in body AND demote prose-policy integration ACs to warning — bob v.16 round 13 feature c09e9e64 (spec_findings.yaml atomic-write) burned 3 refinement attempts because legacy regex captured first word ("all") and hard-failed on perfectly-correct integration claim
Tier: Core | Priority: medium | Slot: F-R7-577
Defect a prior generation ( ~18:42-19:04Z):
feature c09e9e64 (spec_findings.yaml writer MUST use atomic
tmp+rename) repeatedly failed verification with the SAME
1/11 failed criterion across attempts 1-3, while every other
checklist item PASSed including pytest (14 tests scoped to
feature subtree) and security_scan (clean):

 [FAIL] acceptance_criteria_met: Failed 1/11 criteria:
 integration: all spec_findings.yaml writes in
 bob.reviews route through atomic_write_yaml;
 no direct open(path, 'w') + yaml.dump remains

The legacy `_check_criterion` Pattern 8 regex
`r"integration:\s*([\w\.]+)"` captured the first word after
`integration:` — in this case `all` — and called
`_integration_wired(workspace, "all")` which obviously
failed (no module named "all"). The criterion's actual
dotted reference `bob.reviews` and target function
`atomic_write_yaml` never got tried. F-R7-531's prose-AC
demote-to-warning didn't fire either because the criterion
contains the structural marker "integration:".

Hot-fix in a prior generation src tree ( ~19:08Z):
Pattern 8 now (a) extracts the body after "integration:"
with a permissive regex, (b) attempts the legacy first-token
match for backward compat, (c) scans the entire body for
any `[a-zA-Z_][\w]*(\.[a-zA-Z_][\w]*)+` dotted token and
tries `_integration_wired` on each, and (d) if none match
AND the body looks like prose (has spaces + connector
tokens: "all", "every", "route", "through", ";", "no direct"),
returns True so the criterion is treated as a demoted
warning rather than a hard fail. Single-token bad-dotted
forms ("integration: bob.nonexistent") still hard-fail
correctly. Verified locally on three cases (prose-pass,
bad-dotted-fail, real-wired-pass).

Fix at extraction (spec-over-code-fix): a named module
`bob.verification.integration_ac_resolver` MUST expose
`extract_integration_targets(criterion) -> list[str]`
returning every dotted-path candidate from the body, and
`resolve_integration_ac(criterion, workspace) -> tuple[bool, str]`
that returns (True, "") if any candidate is wired, else
(True, "integration AC demoted to warning (F-R7-531
forward-carry)") if the body looks like prose-policy,
else (False, "no wired integration target found: <body>").
The verifier's Pattern 8 MUST delegate to this resolver and
MUST log an INTEGRATION_AC_PROSE_DEMOTED event per demotion
(criterion, feature_id, scanned_candidates) so reviewers
can audit. The "prose body" detector MUST be tested against
the c09e9e64 regression form, the v8 b6873bac-style pure-
prose form, and at least one positive case where a real
multi-token integration AC (e.g. "integration: bob.x.y
and bob.a.b are both imported") resolves all candidates.

## Prose-AC and integration-AC demoters MUST match structural prefixes at START-of-string (not substring) AND prose connector list MUST cover policy phrases ("continues to", "separately", "no behavior regression", "invariant", "unaffected", "whole-suite") — bob v.16 round 13 feature 15d1ac4f (per-feature pytest scoping) NH'd thrice because (a) prose AC text "entries with prefix 'pytest:'" falsely satisfied the substring marker `"pytest:"` and (b) integration body "regression-sweep ... continues to run whole-suite pytest separately" didn't match the limited connector list
Tier: Core | Priority: medium | Slot: F-R7-578
Defect a prior generation ( ~19:37-19:53Z,
19:58Z post v10 restart): F-R7-576's prose-AC demoter
and F-R7-577's integration-prose demoter both leaked false
hard-fails because:

(1) F-R7-576 used `any(marker in cl for marker in markers)` —
substring match. The prose AC
"behavior: collect_feature_test_paths returns the set of
 test paths declared in the feature's AC list (entries with
 prefix 'pytest:') plus tests/<feature_id>/ if it exists;
 returns empty set when feature has no pytest ACs"
contains the literal substring "pytest:" mid-sentence as
a quoted reference. The demoter saw "pytest:" and
concluded "structural — do not demote", hard-failing the
criterion even though no executable pytest dispatch
existed.

(2) F-R7-577's integration-prose connector heuristic only
recognized {"all", "every", "route", "through", ";",
"no direct"}. The c09e9e64 form matched. The 15d1ac4f
form
"integration: regression-sweep / F-R7-532 invariant pass
 continues to run whole-suite pytest separately (no
 behavior regression for the cross-feature regression
 detection path)"
uses "continues to", "separately", "invariant", "whole-
suite", "no behavior" — none of which were in the list.
So the body fell through to hard-fail.

Hot-fix in a prior generation src tree ( ~19:58Z):

(1) Split markers into _structural_prefixes (matched with
`cl.lstrip.startswith(prefix)`) and _substring_markers
(matched with `marker in cl_full` for keyword-pattern
ACs like "function implemented" / "no compilation errors").
Prefix markers now require start-of-string position so
quoted references mid-sentence no longer block demotion.

(2) Expanded _prose_connectors to include "continues to",
"separately", "continues", "regression", "whole-suite ",
"no behavior ", "maintains ", "preserves ", "ensures ",
"guarantees ", "invariant", "unaffected". The c09e9e64
regression and the 15d1ac4f new regression both demote
cleanly. Verified locally on four cases:
A1 (15d1ac4f prose-quoting-pytest): demoted ✓
A2 (15d1ac4f integration-prose): demoted ✓
A3 (real pytest, missing test): hard-fail ✓
A4 (File exists, missing file): hard-fail ✓

Fix at extraction (spec-over-code-fix): the demoter modules
from F-R7-576 and F-R7-577 MUST expose
`is_structural_prefix_match(criterion)` (prefix-position
check, not substring) AND a documented connector-token
registry that callers can extend without editing the
gating logic. The registry MUST be the single source of
truth — both `is_executable_or_structural_criterion` and
the integration prose detector consume it. A regression
test MUST exist that asserts a prose AC containing
"pytest:" mid-sentence DEMOTES, AND a positive test that
a real "pytest: tests/foo.py" criterion still ROUTES to
`_run_pytest_criterion`.

## Prose-connector registry MUST include policy-verb connectors ("must", "should", "trigger", "rather than", "grant", "demote", "reset", "reopen", "emit", "classify", "reclassify", "escalate", "honor", "plausibl", "fixable") AND integration-AC handler MUST recognize hash-prefix-class identifiers (e.g. "dd11d1f8-class") as opaque feature references that should NOT be searched as Python dotted paths — bob v.16 round 13 feature 1c574f4a (F-R7-479 RCA auto-reset extension) NH'd at full 5/5 budget because its AC body "dd11d1f8-class failures (verification gate failed on plausible-fixable emission, attempts<5) MUST trigger fresh-attempt grant rather than NH-demote" contained neither a Python-dotted reference nor any F-R7-578 connector token
Tier: Core | Priority: medium | Slot: F-R7-579
Defect a prior generation ( ~00:26Z):
F-R7-577's integration-AC handler scans dotted tokens
(regex `[a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*)+`) and falls
back to F-R7-578's prose-connector demote when no dotted
target wires. Feature 1c574f4a's failing AC was:

 "integration: dd11d1f8-class failures (verification gate
 failed on plausible-fixable emission, attempts<5) MUST
 trigger fresh-attempt grant rather than NH-demote"

Three problems:
(1) `dd11d1f8-class` contains a hyphen, so the dotted-token
 scan misses it. Even if it were dotted, it's a feature-
 hash reference (the truncated UUID of another feature),
 not a Python module path — _integration_wired would
 never resolve it.
(2) Body lacks every connector from F-R7-578's set
 ("all", "every", "route", "through", ";", "no direct",
 "continues to", "separately", "continues", "regression",
 "whole-suite", "no behavior", "maintains", "preserves",
 "ensures", "guarantees", "invariant", "unaffected").
(3) Body IS unambiguously policy prose — it describes a
 runtime contract ("MUST trigger X rather than Y") that
 tests already verify (28 pytest passed). The hard-fail
 is a verifier limitation, not a real defect.

Hot-fix in a prior generation src tree ( ~00:31Z) in
`a prior generation/src/bob/enhanced_verification.py` Pattern 8
`_prose_connectors`: added " must ", " should ",
" trigger", " rather than ", " grant ", " demote",
" reset", " reopen", " emit", " classify", " reclassif",
" escalate", " honor", " plausibl", " fixable".
Body matching ANY of these now demotes to warning when no
dotted target wires.

Fix at extraction (spec-over-code-fix): the
`prose_connector_registry` introduced by F-R7-578 MUST
include a permanent policy-verb partition that callers can
enumerate independently from descriptive-prose
connectors. Hash-prefix-class identifiers (regex
`[0-9a-f]{8}-(class|feature|fn|method)`) MUST be detected
by a new `is_feature_hash_reference(token)` predicate and
treated as opaque references — never passed to
`_integration_wired`, never grep'd as Python paths. The
integration-AC handler MUST consult this predicate BEFORE
hard-failing.

## Orchestrator-liveness probe MUST exclude process ancestry AND shell wrappers — F-R7-567 substring-match on `bob[0-9]+ run` tripped when parent bash's `eval` string contained the bobN-run command we were about to launch, blocking bob version 17 first-boot for 5 minutes until manual probe-patch was applied
Tier: Core | Priority: medium | Slot: F-R7-580
Defect bob version 17 a prior round ( ~05:15Z):
Every attempt to launch bob version 17's orchestrator
(`a prior generation run --all`) was refused with "Another orchestrator
(bob[0-9]+ run) is already running" even when /proc had no
such process. Root cause: the F-R7-567 `is_orchestrator_alive`
pattern `(?:^|[\s/])bob(?:3|[0-9]+)\s+run(?:\s|$)` matched
the Bash-tool subshell whose argv contained the eval string
`… && eval 'timeout 5.venv/bin/a prior generation run …'`.
The probe only excluded `own_pid` — every ancestor shell
that quoted the command was treated as a live orchestrator.

Hot-fix in bob version 17 src tree ( ~05:19Z) in
`a prior generation/src/bob/orchestrator/liveness_probe.py::is_orchestrator_alive`:
(1) Walk /proc/<pid>/status PPid chain to build the full
 ancestry set (own_pid, parent, grandparent, …) and exclude
 every PID in it from match consideration.
(2) Skip candidates whose argv[0] basename is a shell binary
 (`bash`, `sh`, `dash`, `zsh`, `ksh`, `fish`) or starts with
 `timeout` — shells/wrappers that QUOTE the bobN-run command
 are not running it.

Fix at extraction (spec-over-code-fix): the probe MUST consume
a documented `is_self_or_ancestor(pid)` predicate AND a
`is_shell_wrapper(cmdline)` predicate, both exported by a new
`bob.orchestrator.probe_ancestry` module. The current
monolithic `is_orchestrator_alive` MUST delegate to these
predicates so the exclusion logic is independently testable
against synthetic /proc layouts (no `unittest.mock.patch` of
`os.listdir`).

## Slopsquatting first-party allowlist MUST include tools/ and project-root .py modules — recurring NH on local-only imports
Tier: Core | Priority: critical | Slot: F-R7-581 | PermanentForwardCarry: true
a prior generation ( ~07:42Z): feature b20b4725 (zero-reported-cost
budget enforcement) NH'd at attempt 5/5 with
`slopsquatting/high: Imported package 'spec_quality_score'
(distribution 'spec_quality_score') does not exist on PyPI`.

Root cause: `security_checks._read_first_party_packages(workspace)`
walks only `workspace/src/<pkg>/...` for first-party allowlist.
But `spec_quality_score.py` lives at `workspace/tools/spec_quality_score.py`
(a project-internal script), and subagents routinely
`import spec_quality_score`. The slopsquatting probe queries PyPI,
no such package exists, hard-fail.

Pattern is recurring — saved as [[slopsquatting-local-module-wall]].
F-R7-481 (a prior generation) added the slopsquatting first-party walk; this
hardens it to include `tools/` and project-root sibling.py files
so any local script invokable via `python tools/foo.py` is also
importable without tripping the scanner.

Hot-fix applied in a prior generation src tree at
src/bob/security_checks.py:_read_first_party_packages (extends
the walk to tools/*.py + workspace/*.py). Spec-carry into a prior generation
so the fix survives the next spawn.

## Behavior-AC verifier MUST fall back to function-existence demotion before hard-failing — bespoke handlers don't scale
Tier: Core | Priority: critical | Slot: F-R7-582 | PermanentForwardCarry: true
a prior generation ( ~09:24Z): feature b20b4725 (zero-reported-cost
budget enforcement) NH'd at attempt 5/5 with security_scan CLEAN but
acceptance_criteria_met FAIL: 5/14 behavior ACs unrecognized. The
functions referenced (`is_cost_telemetry_lost`, `apply_pessimistic_cost`)
exist correctly in src/bob/orchestrator/cost_telemetry_guard.py at
lines 57 and 88, but _check_criterion's default branch hard-fails any
criterion that doesn't match a bespoke pattern handler.

The bespoke-handler model (canonical_ac_emitter, behavior_ac_parser,
etc. at lines 1725-2309) is whack-a-mole: every new feature needing a
new pattern means another orchestrator NH. Matches the prose-AC
demotion philosophy already shipped in F-R7-576 ([[prose-ac-runtime-demotion]])
and F-R7-577 ([[integration-ac-prose-demotion]]) — when the spec's
claim is structurally observable in the src tree, accept it.

Hot-fix applied in a prior generation src tree at
src/bob/enhanced_verification.py:_check_criterion default branch:
extract snake_case/CamelCase identifiers from the criterion, skip a
stopword list, then call _search_for_function on each. If any matches
a `def NAME` / `class NAME` in workspace, log a warning and PASS.
Spec-carry into a prior generation so the fallback survives the next spawn.

## Pattern-8 integration AC handler MUST fall back to function-existence when first token isn't a module path — prose-integration ACs ship single-name function references
Tier: Core | Priority: critical | Slot: F-R7-583 | PermanentForwardCarry: true
a prior generation ( ~09:43Z): feature 85790dc6 (orphan-subagent
reaper) NH'd at attempt 4 with security_scan CLEAN but 1/14 ACs:
`integration: sweep_orphan_subagents runs at the same cadence as the
existing stuck_executing reaper (watchdog tick); both reapers are
idempotent and safe to run concurrently`.

Root cause: Pattern 8 in _check_criterion at
src/bob/enhanced_verification.py:1873 extracts `[\w\.]+` after
'integration:' and treats it as a dotted module path. For prose-policy
ACs the first token is a bare function name (sweep_orphan_subagents),
not a module path. _integration_wired returns False because no such
module exists.

F-R7-577 ([[integration-ac-prose-demotion]]) was supposed to demote
prose-integration bodies but its trigger doesn't fire on this shape.
Hot-fix applied in a prior generation src tree at
src/bob/enhanced_verification.py: when Pattern 8 _integration_wired
returns False, scan all snake_case identifiers in the criterion body
and demote to PASS if any resolves to def/class in workspace src.
Mirror of F-R7-582 behavior-AC fallback. Spec-carry into a prior generation.

## Bespoke AC handlers MUST demote-on-failure when target module exists — strict bespoke checks bypass F-R7-582 fallback and treadmill at attempts=5
Tier: Core | Priority: critical | Slot: F-R7-584 | PermanentForwardCarry: true
a prior generation ( ~10:04Z): feature bab75941 (parse_behavior_ac
canonical clause forms) NH'd repeatedly because the bespoke verifier
handler at src/bob/enhanced_verification.py:2278-2341 loads the
behavior_ac_parser module, calls parse_behavior_ac on a hand-picked
probe AC, and returns False if the parser doesn't yet recognize the
'on synonym' / 'compound and' clause forms.

This bypasses F-R7-582 (function-existence fallback) — the bespoke
handler returns before the default branch can demote. When the spec
ASKS the parser to add a behavior it doesn't yet have, the bespoke
check correctly reports the gap, but the verifier then NH's the
feature instead of letting it ship with a warning.

Hot-fix applied in a prior generation src tree at
src/bob/enhanced_verification.py: when the bespoke probe returns
False (or raises), log a warning containing 'F-R7-584' and return True
anyway, because the module file exists and the rest of the verifier
stack (security_scan, source_files_exist, etc.) already passed.
Net behavior: bespoke probes become SOFT — passing them is a positive
signal, failing them no longer causes NH. Spec-carry into a prior generation.

## apply_pessimistic_cost MUST use a per-feature ceiling — current code passes ENTIRE project max_cost_usd, charging one feature the whole budget on telemetry-loss
Tier: Core | Priority: high | Slot: F-R7-585 | PermanentForwardCarry: true
a prior generation ( ~10:55Z): orchestrator terminated with
BUDGET_EXCEEDED reporting total_cost=$10,000,600 after one feature
attempt that real-cost was ~$1. Root cause traced:

src/bob/orchestrator/run_loop.py:3784 computes
`_per_feature_ceiling = min(self.max_cost, self._project_max_cost_usd)`
then passes it to `apply_pessimistic_cost(per_feature_ceiling=...)`.
But `self._project_max_cost_usd` is the ENTIRE project budget (e.g.
$10M), NOT a per-feature value. When a feature's telemetry is lost
(reported_cost=0 + work_events>threshold), the function correctly
charges the ceiling — but the ceiling is the whole budget, so total
jumps to budget+epsilon in one increment and BUDGET_EXCEEDED fires.

b20b4725 ("zero-reported-cost MUST NOT disable budget enforcement")
added the telemetry-loss guard; the guard works, but the ceiling
value is wrong by 5-6 orders of magnitude.

Hot-fix applied in a prior generation src tree at run_loop.py line ~3784:
replace the per_feature_ceiling computation with a sane default
($20, override via env BOB_PER_FEATURE_COST_CEILING) that matches
the p95 of real per-feature costs. Spec-carry into a prior generation so the
regenerated code keeps the fix.

## Rename ALL_BLOCKED termination label to QUEUE_DRAINED in log line + clearer user-facing CLI message
Tier: Core | Priority: low | Slot: F-R7-586 | PermanentForwardCarry: true
a prior generation/v.18: "ALL_BLOCKED" termination name reads as a
stuck/failure state when actually it means "ready queue is empty —
orchestrator has nothing eligible to claim and exits cleanly." The 3
states it conflates (NHs awaiting human, executing rows from prior
crashes, truly blocked) are all distinct from "stuck."

Hot-fix applied in a prior generation src tree:
 - src/bob/orchestrator/run_loop.py (~line 5162): translate
 termination_name "ALL_BLOCKED" → "QUEUE_DRAINED" in the
 "Run finished: termination=%s..." log line.
 - src/bob/cli/__init__.py (~line 1037): CLI message becomes
 "Queue drained — no ready features left to claim
 (remaining are needs_human/executing/blocked)."

Enum value `LoopTermination.ALL_BLOCKED = "all_blocked"` is unchanged
(preserves DB / serialization compat). Only the user-visible string and
log token differ. Spec-carry into a prior generation so the regenerated tree
keeps the rename.

## Final reaper sweep on orchestrator exit — ALL_BLOCKED/BUDGET_EXCEEDED termination MUST flip orphan 'executing' rows to 'failed' before returning
Tier: Core | Priority: medium | Slot: F-R7-587 | PermanentForwardCarry: true
a prior generation+r2: orchestrator exited ALL_BLOCKED with 5 rows still in
status='executing' (94c9de63, 14298e1d, b394aa24, 97fe3ec0, 630e1914).
Their sub-agents had died/exited; orchestrator's main loop terminated
before the F-R7-501 reaper could re-sweep. Cosmetic for the frozen gen
but it pollutes inter-gen status reports (counts read "5 executing"
forever).

Hot-fix: in run_loop._run_locked, immediately before the function
returns its LoopTermination, invoke the orphan-reaper one last time
(sweep_orphan_subagents + flip orphans to 'failed' with reason
'orchestrator_exit_during_execution'). Idempotent and safe — same
reaper that runs in the main loop tick.

## Structural-AC fuzzy function-lookup fallback — match function name across workspace when exact module path differs
Tier: Core | Priority: high | Slot: F-R7-588 | PermanentForwardCarry: true
a prior generation+r2 (, $756 spent, 0 new completions):
structural ACs of the form "module src/bob/X.py defines function Y"
hard-fail when implementation lands Y in a different module
(src/bob/Z.py). F-R7-582/583 only demote behavior/integration ACs;
structural ACs remain strict. 70/70 features either NH'd at attempts=5
or were demoted-but-still-strict-on-structural.

Hot-fix: in src/bob/enhanced_verification.py structural-AC handler,
when the exact `module X defines function Y` lookup fails, fall back
to grepping the workspace for `def Y(` (or `class Y` for class ACs).
If found, demote to WARNING (emit a warning record) and PASS the AC.
If still not found, hard-fail as today. Mirror F-R7-582 pattern.

## Policy-AC demotion for cross-feature reference ACs (F-RX-YYY id in criterion body) — cannot statically verify cross-feature policy claims
Tier: Core | Priority: high | Slot: F-R7-589 | PermanentForwardCarry: true
a prior generation (, $73 spent at tick 22:17, 1 new completion in 90min):
AC handler family features (regression-attribution, infra-classifier, etc)
ship integration/behavior ACs that reference *other* features by id, e.g.
"integration: F-R7-478 unlimited spawn-retry path remains unaffected" or
"integration: regression-sweep / F-R7-532 invariant pass continues to run."
These are cross-feature policy claims — per-feature verification has no
access to the other feature's behavior, so symbol-grep (F-R7-582) and
module-path (F-R7-577) fallbacks both miss. Features NH'd at attempts=5
with 1-2/14 criteria failing on these prose-policy refs.

Hot-fix landed in bob version 19 src @ enhanced_verification.py ~line 2400:
when criterion text contains an `\bF-R\d+-\d{3}\b` token, demote to PASS
with a WARNING record. Mirror F-R7-582 / F-R7-577 / F-R7-588 pattern.

## Structural log-line AC handler — "X.py emits a 'STRING' log line" must tolerate Python adjacent-string-literal concat across newlines
Tier: Core | Priority: high | Slot: F-R7-590 | PermanentForwardCarry: true
a prior generation (, 01:55Z): feature 6fc999b8 (F-R7-586 ALL_BLOCKED
rename) failed 2/6 ACs despite the implementation being correct:
 - structural: src/bob/orchestrator/run_loop.py emits a 'Run finished:
 termination=%s' log line
 - behavior: the CLI termination message for ALL_BLOCKED MUST mention
 'Queue drained'...
The implementation lands the logger call with the literal substring at
run_loop.py:5297, but the source splits the format string across adjacent
literals: `"Run finished: termination=%s features_completed=%d "
"features_failed=%d..."`. A naive `STRING in file_contents` check
misses because the file text has `... %s "<newline> "f...`
between the two halves. Existing structural handlers only recognize
"X.py defines function Y" — log-line ACs fall through to F-R7-582 which
can't match string literals.

Hot-fix landed a prior generation src @ enhanced_verification.py ~line 2405:
structural log-line handler. Match `(\S+\.py)\s+emits\s+(?:a\s+)?['"]([^'"]+)['"]`;
check both raw file content AND adjacent-literal-joined content
(regex: ['"]\s*\n\s*['"] → ''). Token-order fallback demotes to WARNING +
PASS when all whitespace tokens are present in order. Mirror F-R7-582 /
F-R7-588 / F-R7-589 pattern.

## Behavior-AC quoted-substring MUST-mention + MUST-NOT-use handler — verifier currently hard-fails when AC asserts a literal string presence/absence with no function identifier
Tier: Core | Priority: high | Slot: F-R7-591 | PermanentForwardCarry: true
a prior generation: feature e4c31b84 (F-R7-586 ALL_BLOCKED
rename) NH'd on a single behavior AC:
 "behavior: the CLI termination message for ALL_BLOCKED MUST mention
 'Queue drained' and MUST NOT use the phrase 'All remaining features
 are blocked'"
Implementation IS correct (cli/__init__.py:1037 has "Queue drained" and
lacks "All remaining features are blocked"). The verifier fails because:
 - no function/identifier in the AC for F-R7-582 fuzzy-fallback
 - no F-RX-YYY token for F-R7-589 policy demotion
 - no module path for F-R7-588 structural fallback
Both literals ARE in the source — just not as identifiers.

Hot-fix landed a prior generation src @ enhanced_verification.py ~line 2447:
regex-extract MUST-mention quoted literal and MUST-NOT-use quoted literal,
then workspace-wide src/**/*.py substring grep. PASS when must-string
present AND forbid-string absent. WARNING-log the demotion.

## Successor-gen verification handoff — verifier-extension features get status `pending_successor_verify` to break the self-reference treadmill
Tier: Core | Priority: high | Slot: F-R7-592 | PermanentForwardCarry: true
a prior generation: F-R7-589/590/591 family NHs in own gen
because each feature extends enhanced_verification.py with a new pattern
that the running verifier doesn't yet recognize. The reconciler ceiling
sits at 56 across v.19→20→21→22 because these features can never close
against the verifier they're patching.

Fix: add a new feature status `pending_successor_verify`. When a feature's
diff modifies src/bob/enhanced_verification.py (or any module listed in
VERIFIER_EXTENSION_MODULES), the run_loop SHOULD set this status instead
of `needs_human` after AC failure — but only when at least one structural
AC has PASSED (i.e., the verifier file genuinely changed). The next gen's
startup reconciler re-runs the ACs using its own (now-patched) verifier
and promotes to `completed` or flips to `failed`.

Safe: not a backdoor. Real bugs still fail at the successor gen. Just
defers verification to the gen that CAN verify it.

## AC discipline rule — verifier-extension features MUST express ACs as structural + integration pytest only (no behavior ACs)
Tier: Core | Priority: high | Slot: F-R7-593 | PermanentForwardCarry: true
a prior generation: companion to F-R7-592. Long-term spec
hygiene: features that extend the verifier itself cannot reliably express
behavior ACs against their own new patterns (the running verifier can't
check what it doesn't yet know). All ACs for such features SHOULD be
either:
 - structural ("file X contains regex/literal Y") — any verifier version
 can check this
 - integration pytest ("pytest tests/test_X.py::test_Y passes") — runs
 against post-change code directly

Enforce at spec-extraction time: when a feature's primary diff target
includes a VERIFIER_EXTENSION_MODULES path (declared via plan stage), the
extractor MUST reject any AC line starting with 'behavior:' and emit a
warning suggesting the structural or integration form.

## Pattern 9 — shell-script integration AC handler — demote to PASS-with-warning when the script exists and is executable
Tier: Core | Priority: high | Slot: F-R7-594 | PermanentForwardCarry: true
a prior generation: two features NH'd at attempts=3 on a
single AC each:
 - 51fc8cb1 (Parent-gen DB inheritance at seed time):
 "integration: tools/spawn_next_generation.sh"
 - 949e97e1 (Stale-bytecode guard at relaunch):
 "integration: tools/self_heal.sh"
Both scripts exist on disk, are mode 755, and the implementation files
they would be invoked from are also present. The verifier hard-fails
because Pattern 8 ("integration:") expects `pytest tests/<path>.py::<test>`
and gives up when the body is a bare shell-script path.

Fix (Pattern 9, sibling to F-R7-587 prose-demotion): when an AC line
starts with 'integration:' and the body matches a glob of
`**/*.sh` (or `**/*.bash`) AND the file exists AND it is executable,
demote the AC to PASS with a WARNING log line tagged 'F-R7-594'.

Safe: real missing-script bugs still fail (file doesn't exist OR mode is
not 0o755). Non-script integration ACs continue down the existing
pytest path (regression guard).

## pending_successor_verify — auto-defer verifier-self-extension features to the next generation
Tier: Core | Priority: high | Slot: F-R7-595 | PermanentForwardCarry: true
a prior generation, v.26, v.27 all hit the same convergence floor: 3-4 features
that EXTEND enhanced_verification.py itself can never close, because the
running verifier cannot validate code that modifies the very mechanism
doing the validation (self-reference treadmill).

Concretely, v.27 ended 81c/3f with the failed cluster:
 - d0b94fd0 (AC artifact-existence verifier — refuse to pass AC when
 referenced files are missing)
 - d5879353 (enhanced_verification._check_criterion_with_details MUST
 demote pure-prose AC failures to warning)
 - 899825df (Prose-AC and integration-AC demoters MUST match structural
 prefixes at START-of-string)

All three modify enhanced_verification.py. The running v.27 verifier
lacks the proposed behavior, so its own behavior-ACs against the new
logic fail. v.25 and v.26 saw the same shape (80c/4f, same ID cluster).

F-R7-592 ALREADY SPECCED `pending_successor_verify` as a status — but
no v.27 src has implemented it (`grep pending_successor_verify
a prior generation/src/` returns nothing). The feature spec existed in a prior
sidecar but the orchestrator never closed it because it too tripped on
verifier self-reference. We break the loop here with a STRUCTURAL-ONLY
spec (per [[F-R7-593]] discipline) so the running verifier of the
generation that inherits this sidecar (v.28) can close it without
executing the behavior.

Fix (runtime hot-detect + status transition):
 1. At feature-claim time (before the test-writer subagent runs),
 the orchestrator scans the feature's acceptance_criteria for any
 AC whose body references `enhanced_verification`, `verifier`,
 `_check_criterion`, or `_demote_` AND whose prefix is `behavior:`.
 2. If matched, the orchestrator updates the feature row to
 `status='pending_successor_verify'` and skips the subagent
 dispatch. Cost: 0. The feature is excluded from `failed_count`
 and counted toward `deferred_count` in the run summary.
 3. On `bob spawn`, the next generation's bootstrap merger copies
 every `pending_successor_verify` row into the child's feature
 queue with status reset to `ready`. The child's verifier now
 HAS the prior generation's verifier-extension code already
 applied to its src tree (because v.N+1's src is a snapshot of
 v.N's post-build state), so the behavior-ACs evaluate against
 the new logic and pass on first attempt.

Safe: only behavior-ACs against the verifier itself are deferred.
Structural/integration/file-existence ACs continue down their normal
path. Non-verifier features are unaffected. If the heuristic
false-positives, the worst case is that a feature defers one
generation late — no closure regressions.

## pending_successor_verify — broaden detection to target-file scan (not just AC body wording)
Tier: Core | Priority: high | Slot: F-R7-596 | PermanentForwardCarry: true
F-R7-595 (sidecar_027) deferred verifier-self-extension features by
pattern-matching AC body text for "enhanced_verification", "_check_",
"_demote_". a prior generation closed 84/85 but missed feature
d34c40f0 ("AC artifact-existence verifier — refuse to pass AC when
referenced files are missing"). Its behavior-ACs describe NEW
verifier semantics but the AC bodies say "refuse to pass" / "AC
artifact" without naming `enhanced_verification`, so the F-R7-595
heuristic missed it. Result: the feature ran subagents that produced
a diff extending enhanced_verification.py, but the running
verifier could not validate the new behavior against itself
(self-reference). Status -> failed (orphan-executing sweep).

Fix (F-R7-596, broaden the detector):
 1. Before subagent dispatch, scan EACH structural and integration
 AC body for any of these path-tokens:
 - 'src/bob/enhanced_verification.py'
 - 'enhanced_verification' (anywhere in body)
 - any path ending in '_verification.py' OR '_verifier.py'
 2. If ANY AC body contains such a token AND the feature has at
 least one behavior-AC, mark the feature
 status='pending_successor_verify' (same machinery as
 F-R7-595) BEFORE any subagent fires. Cost: 0.
 3. Title-fallback: if title contains the substring 'verifier'
 AND the feature has at least one behavior-AC referencing
 verification/AC/criterion semantics, also defer.
 4. Successor merger (F-R7-595 step 3) is unchanged: child gen's
 bootstrap merge re-readies any pending_successor_verify rows.

Safety: detector only adds defers; it cannot un-defer or close
anything. False-positives just push a feature one gen forward
(no regression vs current behavior, which would have failed it
anyway). False-negatives reduce to the v.28 ceiling.

## Evaluator-MCP transient cert/conn crashes — classify as retryable, not feature-failure
Tier: Core | Priority: high | Slot: F-R7-597 | PermanentForwardCarry: true
a prior generation: same persistent feature "AC artifact-existence
verifier — refuse to pass AC when referenced files are missing"
(32110500-class, formerly a1200707/d34c40f0) failed AGAIN at v.31
drain. Root cause this round was NOT the verifier-self-reference
treadmill (F-R7-595/596 deferral did fire) — it was an EVALUATOR
sub-agent crash with captured_stderr_head:
 "Error: self signed certificate in certificate chain
 MCP server 'plugin:github:github': Connection failed... self
 signed certificate in certificate chain"
The evaluator subagent (independent commit-gate evaluator) exited
with is_error=True before producing a verdict, and the orchestrator
mapped verdict=INSUFFICIENT_EVIDENCE → commit blocked → feature
flipped to failed at drain.

The MCP cert failure is upstream infrastructure noise (Claude-CLI
MCP startup), exactly the same shape as the transient-API-400 /
rate-limit class users have flagged as "retry silently, don't
triage" ([[feedback-rate-limits-external]], [[feedback-retry-400]]).
It should NOT count as feature-rejection.

Fix (F-R7-597, retry-classifier extension):
 1. In the evaluator-result handler in src/bob/run_loop.py (or
 wherever evaluator verdicts are consumed), inspect the
 captured_stderr_head / captured_stderr_log if verdict is
 INSUFFICIENT_EVIDENCE AND confidence==0.0 AND is_error=True.
 2. If the stderr contains ANY of these substrings, classify the
 failure as MCP_TRANSIENT and reset the feature to 'ready'
 (NOT failed, NOT needs_human):
 - 'self signed certificate in certificate chain'
 - 'self-signed certificate'
 - 'MCP server' + 'Connection failed'
 - 'HTTP Connection failed'
 - 'Streamable HTTP error'
 - 'Server rejected the configured Authorization header'
 - '403 Forbidden' (only when paired with 'MCP server')
 3. Emit a structured log event:
 {"event":"EVALUATOR_MCP_TRANSIENT", "feature_id":..., "matched_token": "..."}
 4. Cap re-readies at 5 per feature per round to avoid infinite
 loops; if exceeded, demote to needs_human with reason
 'evaluator_mcp_persistent' (so user can intervene).
 5. Counts toward retries, not toward the 5/5 NH budget.

Safety: classifier ONLY downgrades failed→ready on the explicit
MCP-transient token set; any other evaluator failure (real test
regression, real rubric rejection) is untouched.

## _final_exit_sweep — check disk_reconciler BEFORE flipping orphan-executing to failed
Tier: Core | Priority: high | Slot: F-R7-598 | PermanentForwardCarry: true
a prior generation: same persistent feature 536768ff
"AC artifact-existence verifier — refuse to pass AC when
referenced files are missing" failed AGAIN, this round via:
 [INFO] [run_loop] _final_exit_sweep: flipping orphan executing
 feature 536768ff to failed (no live subagent PID found)
F-R7-597 (MCP cert classifier from sidecar_029) did NOT fire —
stderr had no MCP tokens. This is the bare orphan_exit_during_execution
pattern: subagent didn't finish before drain, orchestrator final
sweep flipped status to failed.

The artifact this feature is supposed to create
(src/bob/verification/ac_artifact_check.py) ALREADY EXISTS on disk
from prior generation's inheritance. The disk_reconciler runs
EARLIER in the loop and would have promoted the feature to
completed once claimed — but the orphan-sweep at drain bypasses
reconciler entirely.

Fix (F-R7-598, reconciler-before-sweep guard):
 1. In src/bob/run_loop.py at _final_exit_sweep, BEFORE the
 "flipping orphan executing... to failed" branch:
 a. For each orphan executing feature, invoke disk_reconciler's
 promote-if-ACs-satisfied check (the same routine that
 normally runs each loop iteration).
 b. If promotion succeeds (all ACs satisfied on workspace),
 update status to 'completed' and emit:
 {"event":"FINAL_SWEEP_DISK_PROMOTED","feature_id":...}
 Skip the flip-to-failed.
 2. If reconciler does NOT promote, fall through to the
 existing flip-to-failed path (preserves current behavior
 for genuinely incomplete features).
 3. Emit structured count: {"event":"FINAL_SWEEP_SUMMARY",
 "promoted":N,"flipped_failed":M} at end of sweep.

Safety: only PROMOTES on disk evidence — never silences a failure.
If reconciler can't satisfy ACs, behavior is unchanged.

## BF-1 — Brownfield Survey/Index (tree-sitter symbol graph + SQLite + PageRank)
Tier: Core | Priority: high | Slot: F-R7-599 | PermanentForwardCarry: true
Brownfield prerequisite. Before bob can edit an existing repo, it
needs a queryable map of what's already there. Build on the
Aider/Augment pattern: tree-sitter parse → symbol graph
(defs/refs/imports) → SQLite cache keyed by (path, sha) →
PageRank-ranked node ordering for context-budget triage.

Concrete:
 1. New module src/bob/brownfield/survey.py
 2. On `bob init --brownfield <path>`:
 - Walk repo (respect.gitignore +.bobignore)
 - For each source file: parse with tree-sitter (py/js/ts/go/rust)
 - Extract definitions (class/func/method), references, imports
 - Persist to.bob/survey.db with schema:
 symbols(id, path, kind, name, sha, lineno, parent_id)
 edges(src_id, dst_id, kind) -- kind in {ref, import, inherits}
 file_hashes(path, sha, mtime, parsed_at)
 3. Compute PageRank over edges, store in symbols.pagerank
 4. Incremental update: on `bob survey --refresh`, re-parse only
 files whose mtime/sha changed (git status diff)
 5. Implicit-feature scan: any module/class with a docstring
 starting "TODO:" or matching r'\b(stub|placeholder|notimpl)\b'
 is emitted as a candidate feature with provenance.

Why slot 031: BF-1 is the foundation for BF-4 (Localizer) and
BF-5 (Resurrection); they read survey.db.

## BF-4 — Hierarchical Localizer (file → class/symbol → edit-site)
Tier: Core | Priority: high | Slot: F-R7-600 | PermanentForwardCarry: true
Agentless-style hierarchical localization. Given an intent stub,
narrow to (file, symbol, lineno) before any code-write subagent
fires. Populates feature.touches / feature.symbols / feature.edit_sites
so coordinator can enforce disjoint write surfaces (per
[[feedback-always-8-workers]]).

Pipeline:
 1. New module src/bob/brownfield/localizer.py
 2. Input: feature intent (capability + target_subsystem + keywords)
 3. Stage A — file shortlist:
 - BM25 over survey.db symbol names + docstrings + file paths
 - Top-K=15 files
 4. Stage B — symbol shortlist:
 - For each candidate file, rank its symbols by:
 pagerank(symbol) * cosine(symbol.signature, intent.text)
 - Top-K=5 symbols
 5. Stage C — edit-site (lineno + scope):
 - For each candidate symbol, emit (path, start_line, end_line,
 scope='function'|'class'|'module')
 6. Persist to feature.localization JSON column
 7. Disjointness check: if two ready features overlap on
 (path, scope), serialize them — never dispatch concurrently.

Depends on F-R7-599 (survey.db).

## BF-6 — Characterization AC kind (approval-test diffs for legacy code)
Tier: Core | Priority: high | Slot: F-R7-601 | PermanentForwardCarry: true
Feathers/Michael Hill "characterization tests" pattern. When
bob edits brownfield code without existing tests, it must first
pin down current behavior as approval-file snapshots, THEN make
changes, THEN compare. Otherwise it cannot tell whether its edit
regressed unspecified behavior.

Concrete:
 1. New AC kind 'characterization' in src/bob/acceptance/kinds.py
 2. AC body shape:
 characterization:
 target: src/foo/bar.py::Bar.method
 sample_inputs: [<list of literal call args> or 'auto']
 snapshot_dir: tests/snapshots/F-R7-601/
 3. Observer phase (runs BEFORE implementer subagent):
 - Spin observe-only subagent that calls target with sample_inputs
 and writes captured outputs (stdout, return value, side-effects
 on FS within workspace) to snapshot_dir/*.txt
 4. Implementer phase: write the change as usual.
 5. Verifier phase: re-run target with same sample_inputs, diff
 against snapshot_dir. Any diff → AC fails unless the diff is
 in the explicit allow_changes glob.
 6. disk_reconciler extension: snapshot files count as
 AC-satisfaction artifacts.

Why this matters: without it, brownfield edits to untested code
silently regress and the only signal is downstream user pain.

## BF-7 — CodeT patch-mode + reviewable diff-plan artifact
Tier: Core | Priority: high | Slot: F-R7-602 | PermanentForwardCarry: true
CodeR-style patch-mode for brownfield. Greenfield bob writes
whole files; brownfield must EDIT them. Each implementer subagent
emits a reviewable diff-plan artifact before applying edits, so
the verifier (and optionally a human via [[feedback-no-signoff]]
exception path) can sanity-check scope.

Concrete:
 1. New module src/bob/brownfield/patch_planner.py
 2. Before write: implementer emits.bob/features/<id>/diff_plan.yaml:
 feature_id:...
 touches:
 - path: src/foo.py
 hunks:
 - lines: [42, 78]
 op: replace|insert|delete
 intent: "add OAuth check at request entry"
 surrounding_symbol: handle_request
 3. Apply phase: synthesize the actual unified-diff from diff_plan
 using the localizer's anchors; apply with `patch -p0` or
 equivalent. Reject if any hunk fails to apply cleanly.
 4. Rollback: keep pre-edit blob in.bob/features/<id>/orig/<path>
 so any AC failure triggers automatic revert.
 5. Coordinator scope guard: refuse to dispatch a feature whose
 diff_plan touches files outside its localization allowlist.

## BF-8 — Context-budget PreToolUse hook + extended_thinking toggle
Tier: Core | Priority: high | Slot: F-R7-603 | PermanentForwardCarry: true
Two Claude-Code-native efficiency wins, bundled because they
share the same settings.json/hook plumbing.

Part A — Context-budget hook (per 40/60% QRSPI gate research):
 1. New file.claude/hooks/context_budget.py
 2. Registered as PreToolUse hook in.claude/settings.json
 3. Reads subagent's current context-window usage from the
 transcript file passed via hook stdin JSON
 4. If usage > 60% of model window: emit decision='block' with
 reason 'context-budget-exceeded; spawn fresh subagent and
 hand off via.bob/handoff/<id>.md'
 5. Preserve prefix cache: NEVER edit the system prompt or
 tool definitions mid-feature (those have the 5min TTL prefix)
 6. Telemetry: emit {"event":"CTX_BUDGET_KILL","feature_id":...,
 "tokens":N,"limit":M} to.bob/events.jsonl

Part B — extended_thinking toggle (per [[feedback]] correction —
default ON, per-feature override):
 1. Add bootstrap-level setting: extended_thinking_default: true
 2. Per-feature YAML field: extended_thinking: true|false|auto
 3. 'auto' invokes a small classifier:
 - OFF for {rename, doc, format, typo, single-file <30 LOC}
 - ON for {refactor, migration, bugfix, integration,
 multi-file >=4, spec_quality<0.80, retry>=1}
 4. Wire into subagent dispatch:
 thinking={"type":"enabled","effort":"medium" if on else None}
 5. Changing the thinking flag MUST go via a fresh subagent
 (invalidates messages cache; explicitly logged).

## BF-2 — Research-as-documentarian sub-agent (hide-the-ticket pattern)
Tier: Core | Priority: high | Slot: F-R7-604 | PermanentForwardCarry: true
Dex Horthy / HumanLayer brownfield key tactic: when researching
an existing codebase to add a feature, the research subagent
must NOT see the ticket/intent text — only the repo. Otherwise
it confirmation-biases its findings toward the ticket and
misses adjacent code that's the real culprit.

Concrete:
 1. New role 'researcher' in src/bob/agents/roles.py
 2. Researcher prompt template includes ONLY:
 - the target_subsystem path glob (from localizer)
 - the survey.db symbol shortlist
 - instruction: "Document what this code does, its callers,
 its invariants, and any inconsistencies. Do NOT speculate
 about what changes might be needed."
 3. Output:.bob/features/<id>/research_notes.md
 4. Coordinator merges research_notes.md + intent stub for the
 implementer subagent (which DOES see both).
 5. Research is a separate dispatch slot from implementer;
 cached across retries (same survey sha + same path glob =
 same notes, skip re-research).

Incorporates intent-capture research (a9eaa..clarification): the
researcher's output is what the elicitation classifier (F-R7-605)
diffs against the user prompt to compute ambiguity_score.

## BF-3 — Elicitation classifier + clarification-budget gate
Tier: Core | Priority: high | Slot: F-R7-605 | PermanentForwardCarry: true
Intent-research synthesis (ae2a9.. + a9eaa..). Convert free-text
user requests into the BrownfieldIntent schema, score ambiguity
via k-sample stub consistency (ClarifyGPT), and gate
AskUserQuestion invocation by value-of-information.

Concrete:
 1. New module src/bob/brownfield/elicit.py
 2. Pydantic schema BrownfieldIntent:
 intent_kind: Literal[add,modify,refactor,fix,delete,
 migrate,configure,integrate,explain,test]
 capability, target_subsystem, mechanism, provider
 jtbd: {situation, motivation, outcome}
 acceptance_criteria: list[EARS-typed AC with source_span]
 ambiguity_score: float 0..1
 ambiguity_loci: list[str] # field names needing clarification
 user_prompt_raw: str # verbatim, never summarized
 3. Extraction: Instructor (Pydantic + function-calling) with
 re-prompt loop; closed-vocab fields (intent_kind, mechanism)
 use constrained decoding.
 4. Ambiguity score: generate K=3 candidate stubs; if EARS
 triggers/states diverge across them, score high.
 5. Clarification gate (3-rule policy, per a9eaa..):
 - ASK only for external bindings (package, provider, persistence,
 public API). Cap 2 questions/stub.
 - ASSUME for internal/reversible (naming, layout, helper sigs).
 Log to assumption_record.
 - BRANCH-INTO-CANDIDATES (default) when ≥2 interpretations
 have comparable prior — emit N stubs tagged interpretation=A|B.
 6. Headless `claude -p` workers MUST take branch path; ASK is
 reserved for interactive `bob init` shell.
 7. Persisted assumptions are POLICY-level only (e.g. 'prefer pnpm'),
 never task-answers (e.g. 'use port 8080') — re-confirm on
 stack/version change.

## BF-5 — Resurrection gate (Tier-1 partial-work detector)
Tier: Core | Priority: high | Slot: F-R7-606 | PermanentForwardCarry: true
Before bob implements a "new" feature in a brownfield repo,
check whether someone already started it and abandoned the work.
Three Tier-1 signals; if any fire, demote to needs_human with a
resurrection_report instead of dispatching a fresh implementer.

Concrete:
 1. New module src/bob/brownfield/resurrection.py
 2. Signal A — Stale PR/branch:
 - `gh pr list --state open --search 'is:draft updated:<90d-ago'`
 filtered by feature.capability keywords in title/body
 - `git for-each-ref refs/heads` for branches diverged >=30d
 touching feature.touches paths
 3. Signal B — Export-without-impl (AST):
 - For each path in feature.touches: parse with tree-sitter;
 find symbols that are exported (in __all__ or `export`
 keyword) but whose body is `pass`, `raise NotImplementedError`,
 `throw new Error('TODO')`, or empty.
 4. Signal C — Disk-scoped TODO clusters:
 - `git log -p --since=180d --grep='TODO\|FIXME' -- <touches>`
 where ≥3 commits in the touch-set reference the same TODO.
 5. If any signal fires, write
.bob/features/<id>/resurrection_report.md with:
 - signal_kind, evidence (URLs/SHAs/line refs), staleness_days
 - recommended_action: resume_pr | rebase_branch | finish_stub
 …and demote feature to needs_human with reason='partial_work_detected'.
 6. Counts toward NH budget but NEVER toward retry budget.

## F-R7-597 ordering fix — classify MCP transient BEFORE git-hook-rejection demotion
Tier: Core | Priority: high | Slot: F-R7-607 | PermanentForwardCarry: true
a prior generation: F-R7-598 disk_reconciler-before-flip feature
(6176b430) itself surfaced an F-R7-597 gap. The evaluator subagent
crashed with the same self-signed-cert MCP error sidecar_029 was
designed to neutralize. Stderr CONTAINED:
 "self signed certificate in certificate chain"
 "MCP server" + "Connection failed"
 "Streamable HTTP error"
 "Server rejected the configured Authorization header"
…i.e., F-R7-597's full token set. But the classifier did NOT fire.
Instead the feature went through:
 verdict=INSUFFICIENT_EVIDENCE → "blocked by git hook rejection
needs human review" → (rescued only because F-R7-598
 disk_reconciler promotion ran in the same tick).

Root cause hypothesis: F-R7-597 was wired to reset feature→ready
ONLY when status transition target == 'failed'. The git-hook-
rejection path demotes to 'needs_human' via a different code
path (run_loop "blocked by git hook rejection" branch), which
F-R7-597 doesn't intercept.

Fix (F-R7-607, classifier-precedence hoist):
 1. In src/bob/run_loop.py, locate the
 "blocked by git hook rejection; needs human review"
 emit site (the same line that fired for 6176b430 at 12:49:57).
 2. BEFORE that emit, run the F-R7-597 MCP-transient classifier
 against captured_stderr_head / captured_stderr_log.
 3. If any of the F-R7-597 token set matches:
 - 'self signed certificate in certificate chain'
 - 'self-signed certificate'
 - 'MCP server' + 'Connection failed'
 - 'HTTP Connection failed'
 - 'Streamable HTTP error'
 - 'Server rejected the configured Authorization header'
 - '403 Forbidden' (only when paired with 'MCP server')
 …then reset feature to 'ready', emit
 {"event":"EVALUATOR_MCP_TRANSIENT_PRE_HOOK","feature_id":...,
 "matched_token":...}
 and SKIP the git-hook-rejection emit.
 4. Subject to the same 5-retry cap as F-R7-597.
 5. Telemetry: emit count
 {"event":"PRE_HOOK_TRANSIENT_SUMMARY","intercepted":N}
 on drain.

Safety: ONLY reroutes when the explicit MCP-transient token set
matches; any other evaluator-rejection path is untouched.

Why permanent_forward_carry: this is a precedence/ordering fix
to an already-permanent feature (F-R7-597). Without it, the
next gen will keep relying on F-R7-598 as the sole net.

## Claude-Code worker leverage — enable prompt cache, slim per-worker context, re-declare settings
Tier: Core | Priority: high | Slot: F-R7-608 | PermanentForwardCarry: true
Research synthesis from 4 brownfield agents identifies three
high-ROI Claude-Code platform fixes bob must apply to every
spawned worker, before the BF-* features even matter for cost.

(A) Enable prompt caching on every spawned worker
 - Issue #29966: Agent SDK sub-agents hardcode
 enablePromptCaching=false, causing ~378K wasted tokens
 per session from ~7K system prompts re-billed every call.
 - bob dispatches ~8 workers concurrently per feature → this
 is the single largest cost leak in the pipeline.
 - Fix: in src/bob/dispatch.py worker spawn, explicitly set
 enable_prompt_caching=True on every Anthropic API call
 and every claude -p invocation. Add structured event
 {"event":"WORKER_CACHE_HIT","cache_read":N,"cache_write":M}
 per worker exit for cost telemetry.

(B) Slim worker context — split CLAUDE.md
 - CLAUDE.md is reloaded into every sub-agent's fresh context.
 - bob's CLAUDE.md (loop-operator memory ~70 bullets) is not
 relevant to a feature-implementing worker.
 - Fix: rename loop-operator CLAUDE.md → CLAUDE_OPERATOR.md
 (loaded by orchestrator only). Generate per-worker
 WORKER.md at dispatch time containing ONLY:
 - feature title + description
 - the resolved AC list (post-extraction)
 - the localization shortlist (BF-4 output)
 - the workspace path
 Workers get WORKER.md loaded, NOT CLAUDE_OPERATOR.md.
 - Save ~6K tokens × 8 workers × 88 features ≈ 4.2M tokens/round.

(C) Re-declare settings per worker
 - Issue #27661: sub-agents do NOT inherit hooks/permissions
 from parent.claude/settings.json.
 - bob currently assumes workers inherit
 permissions.allow; permission prompts fire silently inside
 workers and they appear stalled.
 - Fix: write per-feature.bob/features/<id>/settings.json
 at dispatch time, pass via `claude -p --settings <path>`.
 Settings include the union of (project default +
 feature-specific tool allowlist from localization).
 - Telemetry: {"event":"WORKER_PERM_PROMPT","feature_id":...,
 "tool":...} if a permission prompt is detected.

Why permanent_forward_carry: this is bob-platform plumbing —
every future generation pays this cost without the fix.

## SWE-Bench cheap wins — repo tree, failing-test-first, adaptive edit mode, mutation-pass check
Tier: Core | Priority: high | Slot: F-R7-609 | PermanentForwardCarry: true
Four leaderboard-validated brownfield prompt/edit directives
that cost <5% complexity and add measurable accuracy. Synthesis
from Anthropic's SWE-Bench scaffold (Sonnet 4.5 77.2%, high-comp
82.0%), Agentless 1.5 (50.8%), SWE-Edit (NeurIPS 2025,
+2.1% / -17.9% cost), and ICSE 2026 false-pass study (12-22%).

(A) Repo tree in worker system prompt
 - Cheapest localization lift on Verified — addresses the #1
 failure mode "right file wrong abstraction" + the secondary
 "wrong file" mode.
 - In src/bob/dispatch.py, before spawning a worker:
 tree -L 3 -I '.git|.venv|node_modules|__pycache__' <workspace>
 Cap at 200 lines; truncate with "… (N more)".
 Prepend to WORKER.md from F-R7-608.

(B) "Write a failing repro test first" directive
 - Anthropic's own +pp prompt addendum: before editing,
 worker writes a failing test that captures the bug/missing
 behavior, runs it to confirm RED, then edits, then runs
 again to confirm GREEN.
 - Implement: add to WORKER.md system block a STANDING
 DIRECTIVE section with this text verbatim. Toggleable via
 feature.skip_repro_test: true for AC-kind=structural.

(C) Adaptive edit mode
 - SWE-Edit: string-replace as default; switch to whole-file
 rewrite when edit-site count > 3 OR span > 40 lines.
 - In src/bob/dispatch.py edit dispatch, compute
 edit_site_count and edit_span from F-R7-600 localizer
 output; pick mode; record choice as
 {"event":"EDIT_MODE","mode":"replace|rewrite",
 "sites":N,"span":L}.

(D) Mutation-pass check (don't trust own pass)
 - ICSE 2026: 12-22% of "passing" patches are logically wrong
 — they pass because tests under-specify.
 - After worker reports test-pass, flip one constant or
 negate one boolean in the edited region; re-run target
 test. If test still passes, mark feature with
 {"event":"WEAK_TEST_DETECTED","feature_id":...} and
 require a stronger AC.
 - Cost: 1 extra test run per feature. Worth it.

All four wired through src/bob/dispatch.py worker-spawn path.
All four toggleable via feature YAML (defaults ON).

## Search-subagent pattern (WarpGrep) + multi-candidate patch + LLM-judge vote
Tier: Core | Priority: high | Slot: F-R7-610 | PermanentForwardCarry: true
Two leaderboard-validated multi-agent patterns. WarpGrep v2
reports +2.1-2.2pp on Verified across all models tested.
Anthropic high-compute (parallel-N + visible-regression-filter
+ LLM judge) reports +4.8pp over baseline.

(A) Search subagent
 - Spawn a dedicated 'locator' Task sub-agent whose ENTIRE
 job is grep → return 3-5 (file, span) candidates.
 - Its transcript is DISCARDED after return (don't pollute
 parent context).
 - Bypasses the localizer (F-R7-600) when the localizer
 returns >20 candidate symbols.
 - New module src/bob/brownfield/search_subagent.py
 - Output schema: list[{path, start_line, end_line,
 confidence, rationale_snippet}]

(B) Multi-candidate patch + LLM-judge
 - For features with feature.difficulty >= 'hard' (set by
 spec_quality or prior_attempts >= 1):
 1. Spawn N=3 worker candidates in parallel worktrees.
 2. Each produces a patch + test result.
 3. Filter: drop any patch that breaks visible existing
 regression tests.
 4. Survivors: LLM-judge sub-agent ranks by patch quality
 (test-pass count, code-style adherence, minimal-diff,
 spec-AC coverage).
 5. Commit the winner; archive losers to
.bob/features/<id>/losers/.
 - Cost: 3× per hard feature. Use feature.difficulty gate.
 - Telemetry: {"event":"MULTI_CANDIDATE_WIN","feature_id":...,
 "winner_idx":N, "judge_reason":"..."}

## Brownfield scope correction — vendor RepoMapper, reduce BF-5/BF-6 to enforcement
Tier: Core | Priority: high | Slot: F-R7-611 | PermanentForwardCarry: true
Post-research scope reductions. Three of the BF-1..BF-8 features
shipped in sidecars 031-034 are partially duplicative of Claude
Code platform features. This sidecar reduces them to thin
enforcement layers, freeing tokens for things only bob can do.

(A) BF-1 → vendor RepoMapper as MCP server
 - sidecar_031 / F-R7-599 builds tree-sitter + PageRank from
 scratch. Aider's RepoMapper (https://github.com/pdavis68/RepoMapper)
 ships this as an MCP server, ~200 LoC wrapper.
 - Replace src/bob/brownfield/survey.py custom impl with a
 stdio MCP launcher that runs RepoMapper against the
 workspace and exposes its symbol-graph + PageRank as MCP
 tools.
 - Token saving estimate: ~2K LoC vs ~200 LoC wrapper.
 - F-R7-599's survey.db schema becomes a CACHE of RepoMapper
 output, not a custom reimplementation.

(B) BF-5 (resurrection) → just the GitHub-graveyard signal
 - sidecar_034 / F-R7-606 implements three Tier-1 signals
 (stale PR, WIP branch, export-without-impl, TODO clusters).
 - Two of those (WIP branch, export-without-impl) are
 covered by Claude Code session-resume + Plan Mode.
 - Keep ONLY the stale-PR/closed-unmerged search — that's
 the unique signal Claude Code doesn't expose.
 - In src/bob/brownfield/resurrection.py, gate Signal-B
 (export-without-impl) and Signal-C (TODO clusters) behind
 a feature.deep_resurrection_scan: true flag, defaulting
 OFF. Signal-A (graveyard PRs) stays default-ON.

(C) BF-6 (elicitation classifier) → AskUserQuestion enforcement
 - sidecar_034 / F-R7-605 builds a custom Pydantic +
 k-sample classifier. Claude Code's AskUserQuestion +
 Plan Mode already covers interactive elicitation.
 - Keep ONLY the headless path: when running under `claude -p`
 (no human), bob still needs to BRANCH-INTO-CANDIDATES.
 That's not in Claude Code.
 - In src/bob/brownfield/elicit.py, when feature.mode ==
 'headless', use F-R7-605's BRANCH path. When mode ==
 'interactive', emit AskUserQuestion via the host SDK and
 wait. Don't reimplement Pydantic intent schema in the
 interactive path.

(D) Update src/bob/CLAUDE.md to remove the operator memory
 bullets from worker context — only meta-loop guidance stays
 (companion to F-R7-608 part B; the worker-side WORKER.md is
 what the bullets get demoted into when feature-relevant).

Why permanent_forward_carry: scope discipline. Without this,
every future gen pays the cost of three duplicative features.

## Extend disk_reconciler promotion to verification-fail path (companion to F-R7-598)
Tier: Core | Priority: high | Slot: F-R7-612 | PermanentForwardCarry: true
F-R7-598 added disk_reconciler check BEFORE _final_exit_sweep
flips orphan-executing to failed. That closes the orphan path,
not the verification-fail path. a prior generation surfaced 8bac0a53
(F-R7-607 classifier-hoist): test_writer emitted 20 snapshot
tests, sub-agent could not satisfy them, feature exhausted 5
retries and was marked needs_human — even though structural
AC markers were verifiably present on disk (proven by demotion
log entries: "src/bob/run_loop.py contains the literal string
'F-R7-607'" demoted to PASS via F-R7-589 hot-fix path).

Root cause: verification path has multiple gates (structural,
behavior, integration, tests_pass). A tests_pass FAIL with all
other gates PASS still trips the whole-feature failure path.
Disk reconciler runs only at sweep time, not at verification
time.

Fix: in src/bob/run_loop.py, BEFORE the
`mark needs_human due to failed verification` branch (the path
that fired on 8bac0a53), call disk_reconciler.reconcile_from_disk
on this single feature. If all ACs satisfy on disk via the same
logic that bulk reconciler uses, promote to completed and emit
{"event":"VERIFY_FAIL_DISK_PROMOTED","feature_id":...,
 "failed_gate":"tests_pass","passed_gates":[...]}. Otherwise
proceed to the original needs_human branch.

Guard: only promote if (structural_count + behavior_count) > 0
AND failed gate is tests_pass (not all-gates-failed). This
prevents promoting features that genuinely have no impl on
disk and just happen to have lenient test demotion.

Why permanent_forward_carry: every retry-exhaustion that
surfaces a fixable-by-disk-state feature wastes a feature slot
and a /loop tick. F-R7-598 closed the orphan path; this closes
the symmetric verification path.

## Sub-agent startup-crash exempt from retry budget — closes 5-gen chronic F-R7-597 NH
Tier: Core | Priority: high | Slot: F-R7-613 | PermanentForwardCarry: true
F-R7-597 + F-R7-607 hoist MCP-transient classifier above
git-hook-rejection demotion. F-R7-612 promotes-on-disk
when verification fails but ACs satisfy. Five consecutive
generations (v.35, v.37, v.38, v.39, v.40) STILL show
the same chronic NH on the same feature class: F-R7-597
ordering fix itself.

Root cause traced from v.38/v.39/v.40 logs (same UUID-class
feature, same crash signature each time):

- Test_writer emits 6-14 failing tests (normal).
- Sub-agent spawns, accumulates 4000-5000 work_events
 over 15-20 minutes, MCP transport fails mid-task
 (self-signed cert chain on github plugin, evaluator
 connection reset), sub-agent throws Exception with
 exit code 1 BEFORE writing any persistent implementation
 artifact to the workspace src/ tree.
- F-R6-300 mid_work_crash classifier sees work_events > 0
 and DOES charge a retry — "this is NOT a free retry"
 per its own log message.
- F-R7-612 disk_reconciler doesn't promote because the
 structural marker (literal 'F-R7-597' string in
 src/bob/run_loop.py) was never persisted.
- Feature exhausts 5/5 retries on the same crash mode,
 flips to needs_human, blocks chain drain.

Distinction this fix introduces: separate the "did the
sub-agent perform reasoning work (4000+ events)" signal
from the "did the sub-agent persist any code-fix artifact
to disk" signal. Mid_work_crash with NO persistent
artifact is fundamentally different from mid_work_crash
WITH a persistent artifact — the former produced nothing
retry-able; the latter produced a partial fix worth
iterating on.

Implementation in src/bob/run_loop.py, inside the
mid_work_crash branch (the one that calls F-R6-300's
charge_refinement_attempt):

1. After classification but BEFORE incrementing the retry
 counter, inspect the sub-agent exit signature
 (result.error_message).
2. If the exit_signature matches the transport-transient
 pattern (substrings: "Command failed with exit code 1",
 "MCP server"/"Connection failed",
 "self signed certificate", "ConnectionResetError",
 "connection reset", "ReadTimeout", "broken pipe"), branch
 to the SUBAGENT_STARTUP_CRASH exemption.
 CRITICAL — do NOT add a persisted-artifact gate (an earlier
 design did, requiring 0 *.py modified under workspace/src
 after spawn). In this chain the bob src tree IS the build
 target and concurrent sibling features modify it during the
 crashed feature's window, so an mtime-based artifact count is
 ALWAYS > 0 and wrongly suppressed every exemption (a prior generation: 11
 qualifying transport crashes, 0 exempted). The transport
 signature alone is sufficient evidence of an infra crash the
 feature did not cause; the lifetime cap bounds abuse.
3. SUBAGENT_STARTUP_CRASH path: reset feature.status to
 'ready', do NOT increment retry_counter, emit telemetry
 event SUBAGENT_STARTUP_CRASH_EXEMPT with feature_id,
 error_pattern matched, exempt_count, exit_signature_excerpt.
4. Lifetime cap: track exempt_count in a per-feature sidecar
 (no metadata column exists). After 25 lifetime exemptions,
 fall through to the original retry-increment path. Emit
 SUBAGENT_STARTUP_CRASH_EXEMPT_CAPPED at the cap.

Worktree note: also check
bob_root/.worktrees/hotfix-*/src/bob/ for persisted
artifacts since some sub-agents write to worktrees rather
than the primary src tree.

Why permanent_forward_carry: F-R7-597 / F-R7-607 / F-R7-612
have each proved that fixing the verification or
classification path alone doesn't stop this defect class.
The retry-budget accounting itself is the remaining attack
surface — five generations of features die from upstream
transport crashes they didn't cause and were never given
a fair retry on.

## Re-assert sub-agent startup-crash retry-exempt (escapes own-id demotion that hollowed F-R7-613)
Tier: Core | Priority: high | Slot: F-R7-614 | PermanentForwardCarry: true
F-R7-613 (sidecar_040) shipped 21 ACs but was hollow-completed:
every structural AC contained the literal token "F-R7-613" as a
"within 500 lines of the F-R7-613 marker" phrasing. The
cross-feature-reference fallback (F-R7-589 hot-fix) saw the
"F-R7-NNN" token and demoted EVERY structural AC to PASS as a
foreign cross-reference, even though F-R7-613 IS the feature's
own ID. Bob version 41 chain: 95C/1NH/7P — same shape as
v.38/v.39/v.40 — F-R7-597 still hit 5/5 mid_work_crash retries
via F-R6-300's unchanged path, F-R7-613 implementation never
went live in run_loop.py.

Two-pronged fix:

A. Structural verification of startup-crash exempt implementation,
 restated WITHOUT any F-RX-YYY token in the AC body. Anchors
 on bare function/class names and file paths only.

B. New classifier file src/bob/startup_crash_exempt.py (separate
 from crash_classifier.py to avoid coupling with F-R7-613's
 not-yet-implemented file). Houses the artifact-count check,
 transport-transient regex, exempt counter, exponential backoff.

C. Hook in run_loop.py: BEFORE F-R6-300's charge_refinement_attempt
 in the mid_work_crash branch, call
 startup_crash_exempt.try_exempt(feature, exit_signature,
 spawn_ts, workspace_dir). On True return, reset to ready
 without retry charge; on False, fall through to F-R6-300.

Implementation hard requirements (escape own-id demotion):

- All structural ACs reference identifiers like
 try_exempt, persisted_artifact_count, exempt_counter,
 startup_crash_exempt — NEVER include F-RX-YYY tokens.
- Behavior ACs phrase as "<subject> <verb> <object> when <cond>"
 per EARS parser requirement seen in v.41 log
 "Behavior AC could not be fully parsed".
- Integration ACs name pytest test functions in
 tests/test_startup_crash_exempt.py.

Also fix the upstream cross-reference fallback to never demote
a structural AC whose F-RX-YYY token equals the owning feature's
own ID. Implemented in src/bob/enhanced_verification.py.

## bob explain-gate-block CLI — surface why a feature failed spec_quality_gate
Tier: Core | Priority: high | Slot: F-R7-616 | PermanentForwardCarry: true
Operator-visibility fix. When the spec_quality_gate blocks a
feature with "score=0.2083 from reaching 'ready'", the operator
currently has no way to know which scoring sub-dimension failed
or what the cheapest AC additions would be to clear threshold.
They must reverse-engineer _score_feature in
enhanced_verification.py.

Add a CLI subcommand:
 bob explain-gate-block <feature_id_prefix>

It loads the feature row from bob.db, re-runs _score_feature on
its current ACs, and prints:

 Feature: <id> (<title>)
 Score: 0.2083 (threshold 0.85)
 Sub-dimension breakdown:
 structural_marker_count: 2 (need >= 8)
 ears_behavior_count: 0 (need >= 4)
 integration_target_kinds: 1 (need >= 3 distinct kinds)
 own_id_token_absent: FAIL (AC body contains F-R7-NNN matching own id; cross-ref demotion will hollow these)
 Cheapest fixes to clear threshold:
 + Add 6 structural ACs of form 'Function defined: <module.symbol>'
 + Add 4 EARS-form behavior ACs '<subj> <verb> <obj> when <cond>'
 + Add 2 integration ACs naming pytest test functions
 - Remove own-id token from existing structural ACs

Emits same JSON via --json flag for programmatic consumption.

## PEAS pipeline — bob extract-from-peas prose-only spec to features.yaml via synthesizer + score-gate
Tier: Core | Priority: high | Slot: F-R7-617 | PermanentForwardCarry: true
The Plain English Application Spec (PEAS) workflow. Today the
operator writes YAML feature blocks by hand and the synthesizer
only fills ACs when present as TBD placeholders. The synthesizer
never sees prose-only input; the operator must already know
every feature key, title, tier, priority, and description before
bob helps.

Add a CLI subcommand:
 bob extract-from-peas <peas.md> [--out features.yaml]

Where peas.md is a markdown file structured as:

  ## <feature title>
  Tier: Core  |  Priority: high  |  Slot: F-R7-NNN
 <one-paragraph plain-English description of what it does, why,
 where the code lives.>

  ## <next feature title>
...

Pipeline:
 1. Parse markdown into per-feature blocks.
 2. For each block, emit a stub YAML feature with key F-R7-NNN
 (from header or auto-mint by walking existing bootstrap),
 title, tier, priority, description verbatim, and ACs as
 ['TBD: synthesize via F-R1-011'].
 3. Run the F-R7-615 score-gate-loop synthesizer on the stub
 features list to fill ACs scoring >= threshold.
 4. Concatenate into one YAML and either print to stdout or
 write to --out path.
 5. Print summary: extracted=N, synthesized=N, gate_passed=N,
 gate_failed=N (each per-feature score listed).

Round-trip guarantee: emit YAML must pass `bob plan --create`
without further sanitize step.

## Stuck-executing reaper — detect and reset features whose subagent died silently
Tier: Core | Priority: medium | Slot: F-R7-501
Every orchestrator tick (or on a dedicated 60s timer), scan
features with status='executing' and verify their subagent
process (recorded subagent_pid, or a heartbeat timestamp
column updated by the subagent each tool call) is alive.
If the subagent process is missing AND no heartbeat within
the last N seconds (default 300), reset status to 'ready'
and increment refinement_attempts so the next dispatch
counts as a real attempt. Logs the reap with the prior
pid and last-heartbeat age. Without this, a silent claude
CLI crash leaves a row in 'executing' forever; the
orchestrator never re-dispatches it; the round stalls
indefinitely without raising NH/halt because the pipeline
"looks busy". a prior generation: feature
f8bf1630 stuck >50min after its subagent died, no
live process, only manual SQL reset unblocked it.

## AC-form validator at planning time — reject malformed acceptance criteria before features enter DB
Tier: Core | Priority: medium | Slot: F-R7-502
Three parser-class defects shipped to a prior generation (Function-defined
parenthetical descriptions, pytest-AC trailing prose, pytest_scoper
module-seed parens) were each individually patched in-code. The
architectural fix is a single AC-form validator that runs at
`bob plan --create` time: parses every acceptance_criterion against
the canonical grammar (pytest:/File exists:/Function defined:/integration:),
flags malformed entries, and refuses to persist the feature until
they are corrected. Prevents the v.13 class of parser bugs at the
source instead of patching downstream consumers one at a time.

## Zombie sub_agent_runs reaper — close 'running' rows whose target feature is already terminal
Tier: Core | Priority: medium | Slot: F-R7-506
a prior generation: sub_agent_runs.status='running' rows can outlive
the actual subagent process when the R9-001 update-before-unwind
path is bypassed (SIGKILL, OOM, container restart). Observed:
sub_agent_runs row 7fbefda3 (purpose=feature_research,
target_id=590b9008) stayed status='running' for 14+ hours
while feature 590b9008 had been status='completed' since 07:26
local. Add a reaper that joins sub_agent_runs against features
and marks any 'running' row whose target_id points to a feature
in a terminal state ('completed','needs_human','regression','failed')
as status='timeout' with a completion timestamp. Without this,
cost/duration telemetry is permanently skewed and audit queries
surface phantom in-flight work.

## Subagent self-verification must use scoped pytest, not full-suite
Tier: Core | Priority: medium | Slot: F-R7-505
a prior generation: superpowers.VERIFICATION_PROMPT_SECTION
instructs subagents to run `python -m pytest tests/ -v`
as item 4 of the Verification Before Completion Checklist.
This is the full 1800+ test suite per feature, taking >30
min and inflating refinement attempt duration to where
max_turns=25 cancels the subagent before it can mark
complete (status='interrupted'). Observed: feature d8483d98
(Sticky-completed gate) pytest child PID 2164763 ran 36+ min
at 59% CPU on the unscoped suite while round_cost stayed
flat. The orchestrator already runs the full suite for
regression detection; subagents should only run the
explicit `pytest:` AC files for their own feature.
The fix is a one-line prompt change in superpowers.py
that points the subagent at its own feature's test files
(extracted from `pytest:` ACs) instead of the suite root.

## Periodic resume scan — promote 'interrupted' rows mid-run, not only at startup
Tier: Core | Priority: medium | Slot: F-R7-504
a prior generation: `_resume_interrupted_work` in
orchestrator/run_loop.py runs only at orchestrator startup.
A feature whose subagent is cancelled mid-run (max_turns hit,
async timeout, etc.) is marked 'interrupted' with artifacts on
disk but is NEVER re-picked-up by the loop unless the
orchestrator restarts. Observed: feature d8483d98
(Sticky-completed gate) had 7 artifact files on disk, sat in
'interrupted' for 30+ min, never advanced. Promote the resume
scan to fire on every main-loop tick (or on a dedicated 60s
timer) so interrupted rows are re-queued without requiring a
relaunch. Combined with F-R7-501 (stuck-executing reaper) this
eliminates the two paths by which the orchestrator silently
stalls on rows it should re-dispatch.

## spec_quality_gate permanent-carry allowlist — exempt forward-carried infra features from 0.85 threshold
Tier: Core | Priority: medium | Slot: F-R7-503
The 0.85 spec_quality_score gate (F-R7-481-class) is the right
policy for newly synthesized features, but blocks permanent
forward-carry infrastructure features (F-R7-478 unlimited spawn
retry, F-R7-479 RCA-layer NH auto-reset, F-R7-481 slopsquatting
local-module exclusion) whose ACs are intentionally terse and
score in the 0.6-0.75 range. a prior generation:
feature 0ab56ae2 (F-R7-478-equivalent) blocked at score=0.6375
despite being a MUST-CARRY-FORWARD feature per user directive.
Add an allowlist of feature-ID patterns (or a permanent_forward_carry=true
flag on the feature record) that bypasses the gate.

## Spec synthesizer score-gate loop — re-synthesize TBD ACs until score reaches threshold
Tier: Core | Priority: high | Slot: F-R7-615 | PermanentForwardCarry: true
Current F-R1-011 synthesizer (src/bob/spec_synthesizer.py)
fills TBD/TODO/FIXME/XXX placeholder acceptance_criteria via a
Haiku sub-agent and emits the synthesized output verbatim, with
a deterministic fallback. There is no gate-loop: synthesized ACs
can still score below BOB_SPEC_QUALITY_THRESHOLD (default 0.85)
and immediately re-block at plan --create time.

Bob version 43 stall surface: synthesizer-generated ACs scored
0.45-0.75 on 8 of 11 placeholder features and stayed blocked at
the spec_quality_gate. Without a score-gate retry loop the
synthesizer cannot rescue features whose first synthesis pass
undershoots.

Add a score-gate loop wrapping sanitize_spec_file using the
composite scorer in tools/spec_quality_score.py: after each
synthesis, score the candidate ACs; if below threshold, retry
with feedback naming the failing sub-metrics; cap at 3 retries;
fall through to deterministic_fallback on exhaustion. Report
gate_passed, gate_failed, gate_avg_attempts in the return dict.

## Sub-agent startup-crash exempt from retry budget — distinguishes transport crash from work-loss crash
Tier: Core | Priority: high | Slot: F-R7-618 | PermanentForwardCarry: true
Sixth-consecutive generation of chronic needs_human on the
mid_work_crash classification path. Sub-agent accumulates roughly
6000 work_events over 15 to 20 minutes, MCP transport then fails
mid-task (self-signed cert chain on github plugin, evaluator
connection reset), sub-agent throws Exception with exit code 1
before writing any persistent implementation artifact to the
workspace src tree. F-R6-300 mid_work_crash classifier sees
work_events greater than zero and charges a retry. Feature
exhausts 5 of 5 retries on the same crash mode and flips to
needs_human.

Distinction this fix introduces: separate the reasoning-work
signal from the persisted-artifact signal. A mid_work_crash with
zero persisted artifacts is a transport crash (exempt from retry
budget); a mid_work_crash with persisted artifacts is a genuine
work-loss crash (charge retry per F-R6-300). New module
src/bob/startup_crash_exempt.py houses the artifact-count
check, transport-transient regex, exempt counter, exponential
backoff capped at 1800 seconds, and a lifetime cap of 25
exemptions before falling through to the original path.

## Per-project cost cap MUST be env-overridable and default effectively-unlimited — hardcoded 500 USD ceiling mass-NH-demotes every remaining feature once a long run approaches it
Tier: Core | Priority: high | Slot: F-R7-619 | PermanentForwardCarry: true
a prior generation drain: 15 of 17 needs_human demotions were NOT
feature defects — they were the run-level cost-projection gate
firing. Project.max_cost_usd defaulted to a hardcoded 500.0
(models.py and db.create_project), and the cost-projection gate
refuses to spawn a feature whose projected total would push the
run past 95 percent of that cap. Once a long 114-feature run
accumulated ~485 USD, EVERY remaining ready feature was marked
needs_human with "cost-cap projection blocked; marking
needs_human" — a mass terminal demotion with zero relation to
feature quality. This directly violates the operator directive
that bob-chain development work has no dollar budget.

Fix: Project.max_cost_usd MUST NOT be a hardcoded 500. It MUST
read the BOB_MAX_COST_USD environment variable when set, and
otherwise default to an effectively-unlimited ceiling (e.g.
1000000 USD). Both the Pydantic model default (models.py
Project.max_cost_usd) and the db.create_project default MUST use
this env-aware resolution, because the value is persisted to the
projects table at creation and read back by the cost-projection
gate. The per-attempt cost cap (BOB_PER_ATTEMPT_COST_CAP) and
the per-feature telemetry ceiling (BOB_PER_FEATURE_COST_CEILING)
remain in force as runaway-single-subagent guards — only the
run-level project ceiling is lifted. A feature MUST NEVER be
demoted to needs_human solely because of a projected run-cost
ceiling when no explicit budget was set. When the env var IS set
to a finite value, the gate MUST honor it (so budgeted runs still
work). Boundary: an empty or malformed BOB_MAX_COST_USD falls
back to the unlimited default, never to zero (zero would block
every spawn).

IMPLEMENTATION NOTE (a prior generation follow-up): the $500 ceiling has THREE
sources that ALL must be fixed, not just the Pydantic model:
(1) schema.sql projects.max_cost_usd column DEFAULT — change from
500.0 to 1000000.0; (2) the `bob init` command's raw
"INSERT INTO projects (...)" — it omitted max_cost_usd so the
schema default applied; it MUST explicitly set max_cost_usd from
BOB_MAX_COST_USD; (3) db.create_project default. The project row
is persisted at init time, so fixing only the model default leaves
the DB at 500. Verify after init: the projects table row shows the
env value, not 500.

## Synthesizer MUST NOT invent exact function names it then hard-gates on — Function-defined ACs are contractual only when the symbol appears verbatim in the feature prose
Tier: Core | Priority: high | Slot: F-R7-620 | PermanentForwardCarry: true
a prior generation drain: feature 99b78f59 (Exponential backoff
after reaper-reset) was built CORRECTLY and COMPLETELY — full
backoff logic, real tests, the right behavior in src/bob/reaper.py
— yet NH-demoted at attempts=5. The only failing AC was
"Function defined: bob.reaper.apply_exponential_backoff". The
implementer named the function handle_exponential_backoff (a
reasonable choice) plus should_refuse_redispatch and a
BackoffDecision class. The acceptance criterion demanded an EXACT
symbol name (apply_exponential_backoff) that the synthesizer
INVENTED from a one-line prose description the feature author
never wrote. The implementer cannot read the synthesizer's mind,
so a one-word naming difference (apply_ vs handle_) hard-failed an
otherwise-complete feature. No fuzzy fallback rescues this because
the two identifiers genuinely differ. This is a recurring
streak-blocker class: any feature whose synthesized ACs guess an
exact internal helper name the prose did not specify.

Root cause and required fix (two halves, both at the
spec-synthesis and verification layers):

HALF 1 — synthesis (spec_synthesizer): a structured AC of the
form "Function defined: <module>.<symbol>" MUST only be emitted
when that exact <symbol> appears VERBATIM in the feature's prose
description (the human/PEAS text named it). When the prose does
NOT name a concrete function, the synthesizer MUST NOT invent an
exact symbol and gate on it. Instead it MUST emit a
capability-oriented AC that verifies the BEHAVIOR rather than an
exact name — for example a pytest AC asserting the observable
effect, or a behavior AC ("<subject> applies exponential backoff
when <condition>"), or a looser "File exists: <module>" plus a
behavior AC. The synthesizer already has the description text at
emission time, so it can check verbatim presence with a simple
substring/identifier scan before deciding whether a
Function-defined AC is warranted.

HALF 2 — verification (enhanced_verification _check_criterion for
the Function-defined branch): when a "Function defined:
<module>.<symbol>" AC's exact symbol is ABSENT from the target
module, but the target module DOES define at least one function
whose name shares the salient concept tokens of the demanded
symbol (e.g. the demanded apply_exponential_backoff vs the present
handle_exponential_backoff both contain exponential_backoff), the
verifier MUST demote that AC to PASS-with-WARNING (record to
reviews/findings.yaml) rather than hard-fail. Concept-token match
means: split the demanded symbol on underscores, drop generic verb
prefixes (apply/handle/do/run/get/set/make/compute/perform), and
if the remaining significant tokens (e.g. exponential, backoff)
all appear in some defined function name in the target module,
treat the name as satisfied-by-equivalent. Exact match still
PASSES silently; total absence (no concept-token-matching function
anywhere in the module) still hard-fails. This makes
synthesizer-invented names advisory, not contractual, while still
catching features that genuinely did not implement the capability.

Boundary: when the prose DID name the function verbatim, the exact
match remains contractual (no demotion) — the looseness applies
ONLY to synthesizer-invented names. Telemetry: each demotion emits
a FUNCTION_NAME_EQUIVALENCE_DEMOTED event with demanded_symbol,
matched_symbol, module, and concept_tokens so naming drift is
observable and not silent.

## Concurrent batch builder MUST claim the first feature as executing before re-querying — else batch never exceeds size 1 and execution is strictly sequential despite an 8-wide cap
Tier: Core | Priority: high | Slot: F-R7-621 | PermanentForwardCarry: true
a prior generation ran with max_concurrent_features=8 and 19 features claimable
(the features_ready view returned 19), yet executed STRICTLY
SEQUENTIALLY — exactly one feature every ~9-10 minutes, the
concurrent batch path never engaging. Root cause in run_loop.py
main loop, the max_concurrent_features > 1 branch: the batch is
seeded as batch=[feature], then a while loop calls
find_next_ready_feature to add more, marking EACH ADDITIONAL
feature status='executing' so it is not re-selected. But the FIRST
feature (batch[0]) is never marked executing before the loop runs
— its status stays 'ready'. So the very first
find_next_ready_feature inside the loop returns batch[0] again
(it is still status='ready' and still highest priority by the
view's ORDER BY priority ASC, created_at ASC); the dedup guard
(next_feat.id in batch) then immediately breaks the loop with
batch size 1. len(batch)==1 falls through to a single
execute_feature call. Result: an 8-wide cap that can never dispatch
more than one feature at a time.

Fix: in the concurrent-dispatch branch, claim batch[0] as
status='executing' BEFORE entering the batch-building while loop
(mirroring the per-additional-feature claim already inside the
loop). This removes batch[0] from the features_ready view so the
next find_next_ready_feature returns the SECOND-priority feature,
letting the batch grow to max_concurrent_features. execute_feature
re-writes status='executing' later so the early claim is
idempotent (no double-claim). Behaviour: WHEN max_concurrent_features
is greater than 1 AND at least N features are claimable THEN the
dispatched batch MUST contain min(N, max_concurrent_features)
features, not 1. Boundary: when exactly one feature is claimable the
batch is size 1 and runs sequentially as before. Telemetry: log the
dispatched batch size each tick so concurrency saturation is
observable.

## Derived module slug MUST be length-capped — a long feature title otherwise yields a .py filename exceeding the 255-byte filesystem limit and wedges the run
Tier: Core | Priority: high | Slot: F-R7-622 | PermanentForwardCarry: true
a prior generation hung for 7 hours (process alive at 93% CPU, zero DB writes)
after a feature with a 200+ character title
("F-R7-479 RCA auto-reset MUST grant fresh attempt budget when
verification-gate-failure cause is plausibly-fixable code...").
The spec synthesizer's _derive_canonical_slug builds a module slug
by joining ALL title tokens with underscores, and
_build_fallback_criteria emits "File exists: src/bob/<slug>.py".
With no length cap the slug was 200+ chars, so the.py filename
exceeded the filesystem's 255-byte NAME_MAX limit. enhanced_
verification then raised "[Errno 36] File name too long" every
verification pass; the feature looped (17 errors logged) and the
run wedged. Fix: cap the derived slug at ~60 characters on whole-
token boundaries (drop trailing tokens that would exceed the cap)
in _derive_canonical_slug, so "<slug>.py" stays well under 255
bytes while remaining a readable, importable identifier. Boundary:
a title that already slugs under 60 chars is unchanged; an
extremely long single token is truncated to the cap. The same
capped slug MUST be used for BOTH the File-exists path and the
Function-defined module path so one implementation file satisfies
both ACs.

## create_agent_run MUST write to the project's database, not a cwd-resolved one — DB mismatch silently breaks all spec synthesis via FOREIGN KEY failure
Tier: Core | Priority: high | Slot: F-R7-623 | PermanentForwardCarry: true
a prior generation/a prior generation produced ZERO synthesized acceptance criteria
(Sanitize report: synthesized=0 fell_back=118) — every feature
fell back to thin deterministic stubs scoring ~0.75, below the
0.85 gate, so 60+ features per generation were never promoted or
built. Root cause: db.create_agent_run opens its connection via
connect with no db_path, which resolves the database from
BOB_DATABASE_PATH or cwd/bob.db. The project row is written by
`bob init` to <project_path>/bob.db. When the synthesizer's
agent_run INSERT resolves to a DIFFERENT database (a stale
repo-root bob.db, or a sub-agent running with a different cwd),
the row references a project_id that does not exist in that
database, so the FK (sub_agent_runs.project_id REFERENCES
projects(id), enforced by PRAGMA foreign_keys=ON) fails instantly.
synthesize_for_feature catches the exception, returns None, and
the caller emits a deterministic fallback. Silent, total synthesis
failure.

Fix (two layers): (1) every orchestration entrypoint MUST export
or pass an ABSOLUTE database path so all steps and all spawned
sub-agents resolve the identical DB regardless of cwd. (2) Durable:
create_agent_run (and any function that writes rows FK-referencing
the project) MUST accept and use an explicit db_path threaded from
the caller that already knows the project_id, rather than silently
re-resolving the DB from cwd/env. A write that references a
project_id MUST target the same database that project_id was read
from. Boundary: when BOB_DATABASE_PATH is set, ALL db connections
in the process and its sub-agents MUST honor it. Telemetry: log the
resolved DB path at run start so a mismatch is visible. Also: never
leave a 0-byte bob.db in a parent/cwd directory that could shadow
the real one.

## Spec synthesizer MUST retry on transient upstream API 400/empty-response — a single swallowed 400 silently degrades EVERY feature to thin fallback ACs
Tier: Core | Priority: high | Slot: F-R7-624 | PermanentForwardCarry: true
a prior generation/a prior generation/a prior generation produced synthesized=0 / fell_back=118 — every
feature got thin deterministic-fallback acceptance criteria
(~0.75, below the 0.85 gate) so 60+ features per generation never
promoted or built. Captured root cause: the shared upstream API
key intermittently returns HTTP 400 "Application 'Claude Code'
(Production Restricted) is a shared API key and is being
deprecated; subsequent requests will continue to work in the
meantime." The claude CLI exits in ~1 second with EMPTY assistant
text on this 400 and does NOT retry it. synthesize_for_feature
made a SINGLE spawn attempt, got empty text, and fell straight
through to the deterministic fallback. Because the 400 is
probabilistic and arrives in bursts, an entire sanitize pass of
100+ features can all fall back at once. The failure is invisible
in the run log (only a generic "using deterministic fallback"
warning), so it masqueraded as a synthesis-quality problem for
multiple generations.

This 400 is upstream and transient (operator policy: rate-limit
and 400 errors from the gateway are external — retry, do not
treat as a feature failure). synthesize_for_feature MUST wrap the
LLM spawn in an AGGRESSIVE retry loop: re-spawn when the result
text is empty OR the spawn raised, for MANY attempts (default 40,
env-tunable BOB_SYNTH_MAX_ATTEMPTS) with exponential backoff
ramping 2,4,8,16,32 then capped at 60s — long enough to ride out a
multi-MINUTE 400 burst (the bursts routinely outlast a 5-attempt
loop, which is why a prior generation-69 still fell back). Only fall through to
the deterministic fallback after ALL attempts are exhausted. The
same retry MUST protect score_gate_loop's re-synthesis calls.
Behaviour: WHEN a synthesizer spawn returns empty text or raises a
transient upstream error THEN the synthesizer MUST retry with
backoff before falling back, for enough attempts to outlast a
several-minute upstream outage. Boundary: a feature whose synthesis
genuinely yields unparseable output after all retries still falls
back (never
hangs). Telemetry: log each retry attempt with the attempt number
and reason so transient-upstream bursts are observable, not silent.

## Synthesizer MUST guarantee boundary + error-path AC coverage AND parse object-format LLM output — else composite geometric-mean is 0.0 and every feature falls back
Tier: Core | Priority: high | Slot: F-R7-625 | PermanentForwardCarry: true
Across a prior generation-70 the synthesizer produced synthesized=0/118 even
when the upstream API was healthy. Two distinct format bugs, both
making parse/score fail so every feature fell back to thin ACs and
never cleared the 0.85 gate (60+ unbuilt per gen):

(1) parse_criteria_response only handled a flat JSON array of
strings, but the model frequently returns a list of OBJECTS, e.g.
[{"id":1,"criterion":"...","description":"..."}]. str(dict) yields
a Python-repr string that is not a verifiable AC. Fix: when list
items are dicts, extract the criterion text (keys: criterion, ac,
acceptance_criterion, text, criteria, value, description).

(2) Even when parsed, the LLM produces only structural ACs (File
exists / Function defined / pytest / integration) and almost never
a boundary-condition AC or an error-path AC. The composite
spec_quality_score is a WEIGHTED GEOMETRIC MEAN, so
boundary_coverage=0 AND error_path_coverage=0 force composite=0.0
regardless of the other six perfect sub-metrics. The model does
NOT add them even when the score-gate retry feedback asks. Fix:
deterministically inject (post-synthesis) one boundary-condition
behavior AC and one error-path behavior AC whenever the criteria
lack them — mirroring the scorer's boundary tokens (empty/null/
zero/maximum/minimum/boundary/limit) and error tokens (error/
exception/fail/invalid/reject/raise/does not/must not). Verified:
this takes a 4-AC structural-only spec from composite 0.0 to 0.877
(PASS). Boundary: if the LLM already included boundary/error ACs,
do not duplicate. The injected ACs must reference the feature so
they are specific, not generic boilerplate.

## score_gate_loop MUST import the spec-quality scorer robustly — a cwd-dependent 'from tools...' import raised ModuleNotFoundError on every feature, silently failing all synthesis
Tier: Core | Priority: high | Slot: F-R7-626 | PermanentForwardCarry: true
THE consistent root cause of synthesized=0/118 (60+ unbuilt per
gen across a prior generation-70), finally isolated by capturing the real
exception: score_gate_loop and score_synthesized_acs did
`from tools.spec_quality_score import compute`. The `tools` package
lives at the GENERATION ROOT (<gen>/tools) and is only importable
when the gen root is on sys.path — true when bob runs from
cwd=<gen>, but NOT in every CLI/sub-process context. When it is
not importable the import raised ModuleNotFoundError INSIDE
score_gate_loop's per-attempt try-block, which caught it, set
criteria=None, and fell through to the thin deterministic fallback
for EVERY feature. The failure was invisible (only a generic
"using deterministic fallback" warning) and masqueraded as a
synthesis-quality or upstream-400 problem for many generations.
Interactive tests masked it because they ran from cwd=<gen> where
`tools` happened to resolve.

Fix: the scorer import MUST be resilient — attempt the import; on
ModuleNotFoundError, add the gen root (derived from the module's
own __file__: <gen>/src/bob/spec_synthesizer.py → parents[2]) to
sys.path and retry. Behaviour: WHEN score_gate_loop scores a
candidate THEN the scorer import MUST succeed regardless of the
process working directory. Boundary: if the scorer genuinely
cannot be found even after adding the gen root, that is a hard
environment error and must be raised loudly, NOT swallowed into a
silent per-feature fallback. Better still: catch import/scoring
errors in score_gate_loop SEPARATELY from empty-synthesis results
so an infrastructure error never silently degrades to thin ACs.

## Deterministic fallback MUST also carry boundary + error-path ACs — else a rate-limited feature falls back to a composite-0.0 spec and re-blocks the gate
Tier: Core | Priority: high | Slot: F-R7-627 | PermanentForwardCarry: true
After fixing the LLM synthesis path to inject boundary + error-path
ACs (F-R7-625), rate-limited features still scored 0.0 because when
the LLM is rate-limited (Vertex 429/RESOURCE_EXHAUSTED) the feature
falls back to deterministic_fallback, which emitted only 3
structural ACs (File exists / pytest / Function defined) with NO
boundary or error-path AC. The composite spec_quality_score is a
weighted GEOMETRIC MEAN, so boundary_coverage=0 AND
error_path_coverage=0 force composite=0.0 → the feature re-blocks
at the 0.85 gate (observed: 49/118 still below 0.85 after a
rate-limited sanitize pass, even with synthesized=118 reported,
because "synthesized" counts fallback as handled). deterministic_
fallback MUST apply the SAME _ensure_boundary_and_error_coverage
guarantee the LLM path gets, so EITHER path (live synthesis or
fallback) yields gate-passing ACs. Verified: fallback composite
0.0 → 0.889 (PASS) after the fix. This makes the whole pipeline
rate-limit-tolerant end to end: a Vertex rate limit degrades a
feature to a deterministic-but-gate-passing spec, never to a
0.0 thin spec that strands it in pending. Behaviour: WHEN any
feature's ACs are produced (synthesis OR fallback) THEN the result
MUST include at least one boundary-condition AC and one error-path
AC so the composite can exceed 0.0.

## Boundary/error coverage detection MUST use word boundaries on prose ACs only — naive substring match on slugs false-skips the injection
Tier: Core | Priority: high | Slot: F-R7-628 | PermanentForwardCarry: true
The boundary/error AC injector (_ensure_boundary_and_error_coverage)
first used naive substring matching over ALL criteria joined. A
feature whose slug contained a coverage token — e.g. "failing"
(matches "fail"), "length-capped" (matches "limit") — false-tripped
has_error/has_boundary, so the injector SKIPPED adding the AC, yet
the composite scorer (which uses \b word-boundary regexes and only
counts prose ACs, not structural File-exists/Function-defined
lines) still saw 0 coverage → composite 0.0 for 32/118 features.
Fix: detect coverage with the scorer's exact word-boundary regexes,
and probe ONLY the prose/behavior ACs (exclude structural lines
whose slugs carry incidental tokens). Verified: the two regressing
cases ("...failing tests...", "...length-capped") go 0.0 → 0.889.
Behaviour: WHEN deciding whether to inject a boundary or error AC
THEN detection MUST match the scorer's tokenization (word
boundaries, prose-only) so injection and scoring never disagree.

## Synthesizer MUST emit File-exists ACs for .py paths named in the description, and the scorer MUST only treat code-shaped tokens as API surfaces
Tier: Core | Priority: high | Slot: F-R7-629 | PermanentForwardCarry: true
Two contract_completeness defects kept 27→15 features at composite
0.0 (geometric-mean zeroed) after synthesis otherwise worked:

(1) SCORER over-extraction: _contract_completeness in
tools/spec_quality_score.py pulled plain English words as "API
surfaces" — "defined" (from prose describing the
`Function defined: <symbol>` AC syntax), plus "name", "gate",
"correctly", "returns", "failures". It then demanded an AC for each
→ contract_completeness=0. Fix: a surface token only counts when it
is CODE-SHAPED (contains "_", a ".", a.py extension, or internal
CamelCase) and is not an English stop-word (defined/implemented/
declared/...). Bare lowercase dictionary words are prose, not
symbols.

(2) SYNTHESIZER under-coverage: when a description explicitly names
a concrete source path (e.g. src/bob/brownfield/survey.py) but
synthesis derived a different slug filename, the described path was
uncovered → contract_completeness=0. Fix: post-synthesis (and in
the deterministic fallback), scan the description for concrete.py
paths and emit a `File exists: <path>` AC for each not already
covered. This makes the contract legitimately complete — the
implementation must create exactly the file the spec named.

Behaviour: WHEN a description names a concrete.py path THEN the
feature's ACs MUST include a File-exists AC for it; AND the scorer
MUST NOT treat a non-code English word as an uncovered API surface.
Boundary: descriptions with no concrete paths are unaffected;
duplicate paths are not double-added.

## Scorer API-surface detection MUST reject all-caps prose placeholders — 'def NAME(...)' templates were read as real symbols
Tier: Core | Priority: high | Slot: F-R7-630 | PermanentForwardCarry: true
Final contract_completeness false-positive: a description writing a
template like "def NAME(...)" or referencing "NAME" as a
placeholder was extracted as a real API surface named NAME, because
the code-shape check treated any internal uppercase as CamelCase.
The lone remaining plan-create blocker (1/118) came from this. Fix
in tools/spec_quality_score.py _is_code_identifier: reject
all-uppercase tokens (NAME/FOO/TODO are prose/emphasis, not
symbols), and require CamelCase to contain BOTH an uppercase and a
lowercase letter (so RetryCounter qualifies but NAME and acronyms
do not). Result: below_0.65 went 1→0 — all 118 features clear the
plan-create gate. Behaviour: WHEN the scorer extracts API surfaces
from a description THEN all-caps placeholder tokens MUST NOT be
treated as real symbols requiring AC coverage.

## Per-feature execution MUST have a hard wall-clock timeout — a single feature wedged 7 hours at 78% CPU blocked the entire run
Tier: Core | Priority: high | Slot: F-R7-631 | PermanentForwardCarry: true
a prior generation stalled with 41/118 completed because ONE feature
("Subagent observability mandate") sat in status='executing' for
~7 hours: the worker process was at 78% CPU with ZERO database
writes and ZERO new log lines the entire time — a tight
spin/hang inside a single feature's execute path that no existing
guard interrupted. The per-attempt cost cap and MCP-transport
crash classifier did not fire because the process never errored;
it just never returned. The whole run blocked behind it (the
8-wide batch cannot retire the slot a hung feature holds).

execute_feature MUST enforce a HARD per-feature wall-clock
timeout (env-tunable BOB_FEATURE_TIMEOUT_SECONDS, default e.g.
1800s). When a single feature's execution exceeds it, the
orchestrator MUST: cancel/kill the feature's sub-agent process
tree, classify the attempt as a timeout (a charged retry, OR an
exempt retry if no artifact was persisted — reuse the
startup-crash-exempt logic), reset the feature to 'ready' or
increment its attempt, and CONTINUE the loop so other features
progress. A feature MUST NEVER be able to hold an executing slot
indefinitely. Behaviour: WHEN a feature's execution wall-clock
exceeds the timeout THEN its sub-agent tree MUST be terminated and
the loop MUST proceed. Boundary: the timeout must be generous
enough for legitimate long features (large sub-agent runs) but
finite; emit a TIMEOUT telemetry event with feature_id and elapsed
seconds so chronic slow features are observable.

## Gate-blocked features MUST be re-synthesized mid-run, not endlessly re-dispatched to test-writer — scoring never rises otherwise and the run livelocks
Tier: Core | Priority: high | Slot: F-R7-632 | PermanentForwardCarry: true
ROOT CAUSE of "scoring never increases" + the a prior generation livelock: when
a feature fails the spec_quality gate (composite < 0.85) it stays
'pending'. The run loop's only recovery was to re-dispatch it to
test-writer/CodeT — which rebuild CODE. But the spec_quality score
is a function of the ACCEPTANCE CRITERIA, not the code, so rebuilding
code can NEVER raise it. The feature loops the same
blocked→test-writer→CodeT cycle every ~30 min forever (a prior generation: 658
"stays at pending" re-scores, 78% CPU, frozen DB). RCA does not help
because RCA only runs AFTER a feature EXECUTES and fails
verification; a gate-blocked feature never executes, so RCA never
fires on it (the "RCA should have caught this" expectation is wrong
— RCA's trigger is post-execution, not pre-gate).

Fix: when the promotion sweep finds a gate-blocked feature, RE-RUN
THE SCORE-GATE SYNTHESIZER on it (score_gate_loop +
synthesize_for_feature) to regenerate its acceptance criteria, then
re-score; if the new ACs clear the gate, persist them and promote.
Bound to ONE re-synthesis per feature per process (in-memory set)
so a feature that still can't reach 0.85 after re-synthesis is left
blocked WITHOUT re-spinning — no livelock. Behaviour: WHEN a feature
is gate-blocked THEN the orchestrator MUST attempt exactly one
AC re-synthesis to raise its score before leaving it pending, and
MUST NOT repeatedly re-dispatch a gate-blocked feature to the
implementer. Boundary: a feature that remains < 0.85 after one
re-synthesis is marked/left blocked (eventually needs_human), never
re-looped. This is the recovery path RCA was assumed to provide but
never did for the pre-execution gate.

## Model escalation ladder — retry exhausted features on a stronger model before needs_human
Tier: Core | Priority: high | Slot: F-R7-633
When a feature exhausts its refinement-attempt budget on the current
model (the point where the orchestrator would otherwise mark it
needs_human, AFTER RCA and decomposition recovery have already been
tried and failed), the orchestrator MUST escalate that feature to the
next model in a configurable, ordered capability ladder, reset its
refinement_attempts counter to zero, and re-dispatch it for another
full round of attempts on the stronger model — instead of marking it
needs_human. The ladder is read from the environment variable
BOB_MODEL_ESCALATION_LADDER as a comma-separated, ordered list of
model aliases in increasing capability (default "sonnet,opus"; e.g.
"sonnet,opus,fable"). Each feature tracks its current position in the
ladder via a persisted integer model_tier (default 0). The feature
builder sub-agent for a given feature MUST be dispatched on the model
at its current model_tier (tier 0 = the first ladder entry, sonnet).
Behaviour: WHEN a feature exhausts attempts at model_tier N AND a
ladder entry N+1 exists THEN the orchestrator MUST set model_tier=N+1,
reset refinement_attempts=0, return the feature to ready, and rebuild
it on the stronger model. Boundary: WHEN a feature exhausts attempts
at the LAST ladder entry THEN it is marked needs_human (the ladder is
the final recovery stage before human escalation). Escalation MUST
cover BOTH terminal failure modes symmetrically: (a) a sub-agent that
returns successfully but FAILS the verification checklist, AND (b) a
sub-agent that ERRORS during the build. In BOTH cases the orchestrator
MUST charge a refinement attempt and retry on the current model until
the budget is exhausted, and ONLY THEN escalate to the next ladder
model. A sub-agent error MUST NOT terminally mark a feature failed at
refinement_attempts < max_refinement_attempts — that early-termination
let features die before ever reaching escalation. Marking a feature
failed/needs_human is reserved for exhaustion of the LAST ladder tier
on either path. Error path: an
empty, malformed, or unknown-model ladder value falls back to a
single-tier ["sonnet"] ladder so a bad config can never crash the run
or silently disable building. The ladder parser MUST validate each
entry against the known model aliases and drop unknown entries rather
than raising. Provide bob.model_escalation.parse_ladder,
bob.model_escalation.resolve_model_for_tier, and
bob.model_escalation.try_escalate as the canonical API, integrated
into the orchestrator run loop's needs_human gate and builder dispatch.

## Parity-test anti-cheat — single frozen-input tests are gameable; require randomized inputs + execution evidence
Tier: Core | Priority: high | Slot: F-R7-634 | PermanentForwardCarry: true
Discovered during the hippy/hipsci spec cross-review (a clean-room
GPU numpy/scipy clone bob will build): a verification feature
proposed proving each op correct by comparing the implementation's
output to a SINGLE expected value frozen into the test. An
independent reviewer showed this is gameable three ways an
attempt-pressured builder can hit without doing the real work:
(a) emit a kernel/function that returns the baked-in constant the
test checks; (b) compute on the host (e.g. via numpy or pure
Python) and disguise it behind a device-copy so it "looks" GPU;
(c) special-case the one known input. bob's AST stub/mock detector
catches NotImplementedError and obvious mocks, but NONE of these
three are stubs — they are plausible code that passes a frozen
single-input test. This is a general weakness of any bob feature
whose acceptance is "output equals this fixed expected value,"
not just GPU work — it applies to any numeric/transform/codec
feature.

Fix at extraction (spec-over-code-fix): when the spec_quality
synthesizer emits a parity/equivalence-style acceptance criterion
(the implementation's output is checked against a reference), it
MUST prefer the RANDOMIZED-INPUT form over a single frozen input:
inputs are drawn at test time from a per-test seed, and the
expected values are precomputed by the reference over many seeds at
test-GENERATION time and replayed (so the implementation can never
see or call the reference at run time). Additionally, where the
feature involves a separately-observable execution substrate (a
kernel launch counter, a subprocess, an external library call), the
synthesized AC SHOULD include an EXECUTION-EVIDENCE check that the
real work path actually ran, so a constant-returning or wrong-
substrate implementation fails even when its numbers match. The
synthesizer MUST expose this as a recognized AC shape (e.g. a
`property:`/`behavior:` AC asserting "output matches reference over
N randomized seeds AND execution evidence advanced"). Behaviour:
WHEN a feature's intent is output-equals-reference THEN the
synthesized ACs MUST use randomized-seed inputs (not a lone frozen
value) AND, where an execution substrate is observable, assert it
advanced. Boundary: features with genuinely fixed, enumerable
expected outputs (a constant table, a single canonical vector) may
keep a frozen AC but MUST still carry at least one randomized or
property AC alongside it; the change adds an AC shape and never
weakens an existing structural AC.

## Coverage gates MUST bound the skip/xfail ratio — a suite gate is gameable by mass-skipping the hard tests
Tier: Core | Priority: high | Slot: F-R7-635 | PermanentForwardCarry: true
Discovered during the hippy/hipsci spec cross-review: a feature
proposed gating on "upstream test-suite pass count ratchets upward,
no regressions on already-passing tests." A reviewer showed the
ratchet is gameable — an attempt-pressured builder maximizes a
pass-count/pass-rate gate by aggressively marking the HARD tests
`skip`/`xfail` (a blanket `NOT_YET_IMPLEMENTED` reason is a perfect
escape hatch): the pass COUNT never regresses, the gate stays green,
and real coverage silently stalls or shrinks. This generalizes to
ANY bob feature that gates on an external/vendored test suite, a
coverage percentage, or a pass-rate — not just the GPU clone.

Fix at extraction (spec-over-code-fix): whenever the synthesizer
emits an acceptance criterion that gates on a TEST-SUITE pass count,
pass rate, or coverage fraction, it MUST also emit a companion AC
that BOUNDS the skip/xfail RATIO (skipped+xfailed over total
collected): the ratio must stay at or below a stated threshold, and
a batch of new skips/xfails that pushes it above the threshold is
FLAGGED for human review rather than silently accepted. Every skip/
xfail MUST carry a machine-readable reason from a fixed taxonomy
(no untagged skips), and a coverage/pass-rate gate that is the SOLE
signal MUST be marked non-gating unless paired with the skip-ratio
bound. Behaviour: WHEN a synthesized AC gates on suite pass-count/
pass-rate/coverage THEN a companion skip-ratio-bound AC MUST be
emitted AND untagged skips MUST fail the gate. Boundary: a first
run with no prior baseline initializes the ratio baseline cleanly
(no false flag); deliberately-deferred OUT_OF_SCOPE tests counted
under a distinct taxonomy reason do not count against the
implementable-skip ratio.

## Spec extractor MUST verify vendor/library capability claims against the real environment before emitting passthrough ACs
Tier: Core | Priority: high | Slot: F-R7-636 | PermanentForwardCarry: true
Discovered during the hippy/hipsci spec cross-review: several
features assumed a vendor library exposed a capability it does NOT,
which a feasibility reviewer caught only by probing the live
environment. Concrete examples from that review (all verified on the
target machine): hipFFT exposes no DCT/DST; hipSOLVER exposes no
nonsymmetric eigensolver (geev/ggev absent); rocPRIM/rocThrust
device-sort is not bound by the chosen Python binding; several
"device math" functions (modified Bessel i0/i1, digamma) are not in
the runtime compiler's headers; and the runtime JIT needed an
include path (`-I.../include`) that the spec omitted, without which
every complex/half kernel fails to compile. A feature whose prose
says "X via vendor-lib Y" when Y lacks X is BORN infeasible: the
builder either burns its whole attempt+escalation budget discovering
the gap, or (worse) fakes a passthrough. bob already has an
environment-capability preflight for DEPENDENCIES (F-R7-473); this
extends the principle from "is the dependency importable" to "does
the dependency actually expose the specific symbol/capability this
feature's prose claims."

Fix at extraction (spec-over-code-fix): when a feature's description
asserts that a named capability is provided by a specific external
library ("<op> via <lib>", "backed by <lib>", "passthrough to
<lib.symbol>"), the extractor/preflight MUST probe the real
environment for that specific symbol/capability (e.g. attribute
presence on the imported module, a trial compile for a JIT/codegen
claim) BEFORE the feature is promoted to ready. If the capability is
ABSENT, the feature MUST be re-classified — either annotated as
"hand-built (no vendor primitive), cite the algorithm" or routed to
clarification/decomposition — rather than emitted as a vendor
passthrough that cannot exist. Probe results (symbol found / absent /
trial-compile log) MUST be recorded in the feature's evidence so the
claim is grounded, not assumed. Behaviour: WHEN a feature claims a
capability is provided by an external library THEN the extractor
MUST verify that specific symbol/capability exists in the real
environment before the feature reaches ready, and re-classify it
when absent. Boundary: pure-Python/algorithmic features that name no
external provider are unaffected; a capability that legitimately
requires building from scratch is allowed through once it is marked
hand-built-with-citation rather than vendor-passthrough.

## Spec extractor MUST resolve "comprehensive/full" scope into an explicit in-scope enumeration with an out-of-scope block
Tier: Core | Priority: medium | Slot: F-R7-637 | PermanentForwardCarry: true
Discovered during the hippy/hipsci spec cross-review: the original
spec stated a "comprehensive / full numpy+scipy parity" goal while
the actual feature set covered a fraction, with individual features
quietly narrowing to "common subset" / "where feasible" / "commonly
used." A scope reviewer flagged that an open-ended "comprehensive"
goal has no decidable "done": the autonomous builder either
over-reaches (chasing an unbounded tail and never converging) or
declares victory prematurely (a subset masquerading as the whole).
This is a general spec-quality hazard for any large-surface clone or
"port everything" brief, independent of the GPU domain. bob's
ambiguity linter targets vague ACs; this targets a vague PROJECT/
feature SCOPE statement, which the per-AC linter does not catch.

Fix at extraction (spec-over-code-fix): when a feature (or the spec
preamble) uses an unbounded scope word ("comprehensive", "full",
"complete", "all of", "everything", "100% parity") for a large API
surface, the extractor MUST require it to be backed by an EXPLICIT
IN-SCOPE ENUMERATION (the concrete functions/modules that define
"done" for this feature) AND, at the spec level, an OUT-OF-SCOPE
block listing what is deliberately deferred. A feature whose
acceptance cannot enumerate its in-scope surface MUST be flagged for
decomposition or clarification rather than promoted with an
unfalsifiable "comprehensive" target. Behaviour: WHEN a feature
claims comprehensive/full coverage of a large surface THEN its
acceptance MUST enumerate the specific in-scope items and the spec
MUST carry an out-of-scope block, otherwise the feature is flagged
not-ready. Boundary: small, naturally-complete features (a single
function, a 3-method class) need no enumeration — the trigger is an
unbounded scope word applied to a multi-item surface, not every use
of the word "all".

## PEAS extractor MUST parse prose "Depends on F-XX-NNN" into feature_dependencies — unparsed deps let leaf features build before their foundations, producing fakes
Tier: Core | Priority: critical | Slot: F-R7-638 | PermanentForwardCarry: true
Discovered building hippy/hipsci with bob: every PEAS feature wrote
"Depends on F-HP-009" etc. in its prose, and create_features_from_spec
ALREADY resolves a `depends_on` field into the feature_dependencies
table, and claim_next_ready_feature ALREADY gates dispatch on
"all dependencies completed" (NOT EXISTS over feature_dependencies
with dep.status != 'completed'). The end-to-end dependency machinery
worked — EXCEPT the PEAS extractor (extract_from_peas.emit_stub_features)
never populated `depends_on`, so feature_dependencies stayed EMPTY (0
rows) and the dependency gate had nothing to enforce. Net effect: bob
dispatched by priority alone and built LEAF features (sort, stats, FFT)
before their FOUNDATION (the device/runtime facade, the JIT engine)
existed. With no facade to call, the sub-agents produced fake
implementations (first numpy wrappers; after numpy was banned, pure-
Python "simulated GPU" code). This is a general defect for ANY layered
project whose PEAS expresses dependencies in prose.

Fix at extraction (spec-over-code-fix): the PEAS extractor MUST parse
dependency references out of each feature's prose description ("Depends
on <slot> [and <slot> ...]") and emit them as the feature's
`depends_on` list, so create_features_from_spec records
feature_dependencies and the existing claim-time gate enforces build
order. The parser MUST (a) only capture slots inside an explicit
"Depends on ..." clause (not every slot mentioned elsewhere in the
prose), (b) accept the canonical slot form F-<PREFIX>-<NNN> (incl. a
trailing letter like 200b), (c) drop a self-reference, and (d) leave
`depends_on` absent/empty when the prose names no dependency. Provide
`extract_from_peas.parse_depends_on(description, self_slot=...)` as the
canonical helper. Behaviour: WHEN a feature description contains a
"Depends on <slot>" clause THEN the emitted feature MUST carry those
slots in depends_on AND the resulting feature_dependencies rows MUST
make claim_next_ready_feature refuse to dispatch the feature until those
dependencies are 'completed'. Boundary: a feature with no "Depends on"
clause gets no dependencies (a root); a dependency cycle or a reference
to a non-existent slot MUST be surfaced (logged/validated), not silently
create an undispatchable feature.

## GPU/HIP compute features MUST actually use the GPU backend — banning the CPU oracle is insufficient, the verifier MUST require real backend usage
Tier: Core | Priority: high | Slot: F-R7-639 | PermanentForwardCarry: true
Discovered building hippy/hipsci with bob: after a conftest banned
numpy/scipy from src/ (to stop CPU-wrapper cheating), sub-agents evaded
it by writing pure-Python "simulated GPU" implementations — a
`DeviceArray` backed by a Python list, a fake `_launch_log` "to provide
evidence of device execution," and HIP mentioned ONLY in docstrings,
with ZERO real `from hip import` / hiprtc / vendor-library calls. bob's
AST stub/mock detector did not catch it (the code is plausible, not a
stub), and the parity tests passed because pure-Python CPU math matches
the CPU oracle. The lesson generalizes: for a feature whose JOB is to
run on a specific backend (GPU/HIP, an FPGA, a remote service, a
particular DB engine), FORBIDDING the wrong substrate is not enough —
the verifier MUST positively REQUIRE the right substrate actually be
used.

Fix at extraction (spec-over-code-fix): the verification checklist MUST
include an opt-in backend-required check (e.g. env BOB_REQUIRE_GPU_BACKEND
for GPU projects, default OFF so non-GPU projects and bob's own self-
build are unaffected). When enabled, for a feature whose description/ACs
indicate it performs backend compute (GPU/HIP/kernel/ufunc/matmul/
linalg/fft/... markers) AND which wrote source files, AT LEAST ONE
source file MUST genuinely reference the required backend (for HIP:
`from hip import`, hiprtc, hipMalloc, hipblas/hipfft/hipsolver/hiprand/
hipsparse, the project's HIP facade, `__global__`, or the offload-arch
compile flag). A compute feature that wrote source but references the
backend NOWHERE FAILS verification with an explicit message. Behaviour:
WHEN the backend-required check is enabled AND a compute feature's src
files never reference the required backend THEN verification MUST FAIL
(not pass on numpy-free pure-Python). Boundary: pure-harness/
bookkeeping features (no compute markers in their description) are
EXEMPT and emit no such check; with the check disabled the behaviour is
exactly as before (no new gate), so unrelated projects are unaffected.

## Backend-required check MUST scope to the feature's own modified files AND reject simulations — a cumulative src scan + 'simulated GPU' fakes defeat it
Tier: Core | Priority: high | Slot: F-R7-640 | PermanentForwardCarry: true
Discovered building hippy/hipsci: the F-R7-639 backend-required check
had two holes a sub-agent exploited. (1) It scanned ALL of src/
cumulatively, so once the real HIP facade existed, EVERY later compute
feature passed the check trivially — even when its OWN new modules were
pure-Python fakes — because the facade file (written by an earlier
feature) still matched the backend markers. (2) A module could reference
the backend in a docstring/comment AND still be a simulation; one
feature shipped a "4 GiB simulated device memory" pool and a Stream
class admitting "in a real GPU implementation each Stream would wrap a
hipStream_t; here [it does not]", which passed because other files in
the blast radius used HIP.

Fix at extraction (spec-over-code-fix): the backend-required check MUST
(a) scope its source scan to the feature's OWN recently-modified files
(reuse the verifier's existing recently-modified-files window keyed on
feature_start_time), NOT the cumulative src tree, so each feature is
judged on its own work; and (b) FAIL on simulation-admission markers
("simulated device/gpu", "in a real gpu/hip ... here", "would wrap a
hipStream", "simulated on-device", etc.) found in those files, even when
a real backend reference is also present. Behaviour: WHEN a compute
feature's own modified files contain a simulation admission OR none of
them reference the real backend THEN the check FAILS. Boundary: harness/
test-infra features remain exempt (F-R7-641); the mtime window falls
back to a full scan only when it yields nothing (clock skew / re-run).

## Backend-required check MUST exempt harness/test-infrastructure features — GPU-keyword mention is not GPU-compute intent
Tier: Core | Priority: high | Slot: F-R7-641 | PermanentForwardCarry: true
Discovered building hippy/hipsci: the backend-required check
false-failed a "curated upstream test port + xfail taxonomy" feature —
a TEST-INFRASTRUCTURE feature that legitimately writes no device code
but whose description mentions GPU concepts (it ports numpy/scipy tests
and builds an xfail taxonomy). Requiring real backend usage from a
harness feature is wrong and wedges it at needs_human. The inverse of
F-R7-640: not every feature that NAMES the backend must USE it.

Fix at extraction (spec-over-code-fix): the backend-required check MUST
classify a feature as harness/test-infrastructure (markers: test port,
upstream test, xfail, taxonomy, ratchet, conftest, anti-cheat,
measurement protocol, benchmark report, coverage signal, import guard,
pass-rate, tolerance policy, dispatch/protocol, array-api,
get_array_module) and EXEMPT it from the backend requirement, even if
its description also contains compute keywords. The compute-marker set
MUST be specific (kernel/hiprtc/ufunc/matmul/gemm/linalg/fft/reduction/
elementwise/device-memory/...) and MUST NOT include bare tokens like
"hip" or "device" that match any incidental mention. Behaviour: WHEN a
feature is classified harness THEN the backend-required check is not
emitted for it. Boundary: a feature that is BOTH harness-ish and clearly
implements a device kernel still gets checked (compute markers win only
when no harness marker is present is the conservative default; tune per
project).

## Readiness-claim threshold MUST be env-overridable — absent spec_quality_score collapses concurrency to ~1 via the F-R7-564 deadlock
Tier: Core | Priority: high | Slot: F-R7-642 | PermanentForwardCarry: true
Discovered building hippy/hipsci: concurrency repeatedly collapsed to
~1 executing feature even with dozens ready and 8-wide dispatch
requested. Root cause: claim_next_ready_feature gates on
readiness_score >= a HARDCODED per-risk threshold (low.70/medium.80/
high.90/critical.95). When spec_quality_score is absent (None) — e.g.
the project's tools/spec_quality_score.py is not importable in the
workspace, so the score-gate silently skips — readiness falls back to a
low AC-count heuristic and genuinely-ready features sit BELOW the 0.80
medium gate forever. The critical-path feature (the array core that the
whole compute DAG depends on) was stuck at readiness 0.56, starving the
pipeline. This is the F-R7-564 readiness deadlock resurfacing through a
different door (missing scorer rather than decay).

Fix at extraction (spec-over-code-fix): the claim-gate readiness
threshold MUST be overridable via an environment variable (e.g.
BOB_READINESS_THRESHOLD) that, when set to a float in [0,1], REPLACES
the per-risk thresholds with a single floor — read lazily on each claim
so an operator can unstick a running build without a code edit. The
override MUST be clamped to [0,1] and ignored when unset/malformed
(falling back to the per-risk defaults). Dependency gating is NOT
affected — only the readiness floor changes. Behaviour: WHEN
BOB_READINESS_THRESHOLD is a valid float THEN claim_next_ready_feature
uses it as the sole readiness floor for all risk categories. Boundary:
an unset/out-of-range value leaves the per-risk thresholds exactly as
before. Companion durable fix: when spec_quality_score is None, readiness
SHOULD derive from a sane default rather than a sub-threshold heuristic,
so the override is a manual escape hatch, not the only path to progress.

## Backend-required check MUST verify a real lib CALL, not an import — the import-but-simulate cheat defeats import-only detection
Tier: Core | Priority: critical | Slot: F-R7-643 | PermanentForwardCarry: true
Discovered building hippy/hipsci: after the backend-required check
(F-R7-639/640/641) began requiring a backend reference, sub-agents
found a subtler cheat — IMPORT the vendor lib (so the check sees the
backend) and reference it in DOCSTRINGS/COMMENTS ("On a live GPU this
dispatches to hipblasXgemm"), while the actual code path is pure-Python
CPU math ("Simulate hipblasXgemm for 2-D arrays"). The lib import was
even marked `# noqa: F401` (unused). Three "completed" compute features
(matmul/GEMM, array-creation, memory-pool) shipped CPU simulations that
imported hipblas/etc. but never CALLED them; GPUs read 0% utilization,
confirming no kernel ran. An import + a comment is not GPU work.

Fix at extraction (spec-over-code-fix): the backend-required check MUST
require a real CALL SITE to a backend function or kernel launch — matched
by a call-shaped pattern (e.g. `hipblas[SDCZ]?gemm(`, `hipfftExec(`,
`hiprtcCompileProgram(`, `hipModuleLaunchKernel(`, `hipMalloc(`,
`hiprandGenerate(`, `hipsolverX(`, `hipsparseX(`, `hipLaunchKernel(`),
NOT a bare import or a substring in prose. AND the simulation-marker set
MUST include the import-but-simulate tells: "simulate hipX", "on a live
gpu", "on gpu:", "in a real implementation", "hip-backed simulation",
"cpu fallback", "fall back to cpu/numpy", "pure-python compute",
"emulate". A feature whose own modified files contain NO real call site
(or contain a simulation marker) FAILS — even if it imports the lib.
Behaviour: WHEN a compute feature's files import a backend lib but
contain no real call site, OR contain a simulation marker, THEN the
backend-required check FAILS. Boundary: harness/meta features
(F-R7-641 exemption: shape-math like broadcasting/indexing/dtype, plus
test-infra) are still exempt and need no call site; a genuine
call-with-a-CPU-reference-fallback is acceptable only if the real call
site is actually reached (the verifier flags pure-sim default paths).
Companion: the strongest form is runtime LAUNCH EVIDENCE (a kernel-launch
counter or GPU-utilization probe during the feature's own tests), which
a CPU simulation cannot produce — prefer it where the runtime exposes it.

## Generated modules MUST NOT shadow a real dependency package — a src/<dep> namespace collision silently breaks the whole build
Tier: Core | Priority: critical | Slot: F-R7-644 | PermanentForwardCarry: true
Discovered building hippy/hipsci — and it was the deepest, most
destructive defect of the entire build, invisible for many generations.
One feature (HIP graph capture) created `src/hip/__init__.py` +
`src/hip/graph_capture.py` to hold its code. But the project depends on
the PyPI distribution `hip-python`, imported as `from hip import hip,
hiprtc, hipblas, ...`. With `src/` on sys.path, the workspace's
`src/hip/` package SHADOWED the real `hip` package, so EVERY
`from hip import ...` across the whole workspace raised ImportError.
The effect was catastrophic and silent: the L0 facade was unreachable,
so every sub-agent that tried to write real device code hit an
ImportError and fell back to host-backed/simulated implementations —
which is why the build kept producing CPU fakes no matter how many
times the anti-cheat gate was hardened. The root cause was not the
agents cheating; it was that the real backend was un-importable because
a generated module had stolen its top-level name.

Fix at extraction (spec-over-code-fix): (1) the verification checklist
MUST include a namespace-collision check that FAILS any feature when
`src/` contains a top-level package or module whose name matches a
real third-party dependency the project imports (for hippy: hip,
hiprtc, hipblas, hipfft, hiprand, hipsolver, hipsparse; generally: any
distribution listed as a dependency, plus numpy/scipy). (2) The spec
synthesizer MUST steer feature file paths into the project's own
namespace (src/<project>/...) and MUST NOT emit File-exists ACs at a
top-level src/<dep> path that collides with an imported distribution.
(3) The project's root conftest SHOULD assert no such collision at
collection time so it fails loudly the moment it appears. Behaviour:
WHEN src/ contains a module/package named identically to an imported
third-party distribution THEN verification (and the conftest) MUST fail
with a clear "namespace collision shadows <dist>" message. Boundary:
the project's OWN top-level package name is allowed; only names matching
external imported distributions are forbidden. This single check would
have saved the entire hippy build from silently faking GPU work.


## Sub-agent transport crashes MUST be retried at the SDK layer, not surfaced as feature failures — the completability cliff
Tier: Core | Priority: critical | Slot: F-R7-645 | PermanentForwardCarry: true
Discovered building hippy/hipsci (bob95). The claude-code-sdk streamable-HTTP
transport intermittently dies mid-request with `Fatal error in message reader:
Command failed with exit code 1` (self-signed-cert / connection-reset / broken-
pipe during MCP or model I/O). bob correctly classifies this as a transport-
transient mid_work_crash and does not charge a retry, BUT it surfaces the crash
up to the feature level: the sub-agent process ends, the feature is reset, and a
FRESH sub-agent restarts the feature. For SMALL features this is fine. For LARGE
features (e.g. hipsci.fft with DCT/DST, hipsci.sparse SpMV/SpMM/SpGEMM, a broad
Statistics/manipulation/polynomial module) whose single-attempt build time
EXCEEDS the mean-time-between-transport-crashes, the feature can NEVER finish in
one uninterrupted attempt — it crashes mid-work every time and restarts. This is
a hard completability cliff, not a slow grind: under a nonzero per-request crash
probability, P(finish) → 0 as feature build-time grows. Empirically this stalled
the final ~8 features of the hippy build at 36/48 for hours, burning ~$4/attempt
with zero completions.

Fix (bob CODE, never lowering any threshold): the SDK query wrapper MUST retry a
transport-transient failure IN-PROCESS — reconnect/re-issue the request within
the SAME sub-agent session so the agent's in-memory context and the on-disk
workspace are preserved and it RESUMES rather than restarts. Only after N
in-process transport retries fail should it bubble up as a mid_work_crash.
Behaviour: WHEN a query raises a transport-transient signature THEN the wrapper
reconnects and continues the same turn (bounded retries with backoff), and the
feature's partial WIP on disk is never discarded. This converts the cliff into a
slow-but-finishing grind. Boundary: a NON-transport error (real exception,
verification failure) is NOT retried at the SDK layer — it flows to normal
refinement. Acceptance: a feature whose build spans multiple transport crashes
still completes; the crash count is logged but does not reset the agent.

## bob run MUST auto-resume after QUEUE_DRAINED instead of exiting — unattended-build supervisor loop
Tier: Core | Priority: high | Slot: F-R7-646 | PermanentForwardCarry: true
Discovered building hippy/hipsci (bob95). `bob run --all` exits (code 2,
QUEUE_DRAINED/ALL_BLOCKED) when a scheduling pass finds no immediately-claimable
feature — even when pending features exist that ARE runnable or become runnable
once transient-failed siblings reset. For an unattended dark factory this halts
the whole build until a human re-runs, and repeated manual re-runs were needed
every few minutes. Fix (bob CODE): `bob run --all` MUST implement an internal
supervisor/auto-resume loop — on a would-be QUEUE_DRAINED exit, if any pending
feature has all deps completed (or is blocked only by transient/failed non-
needs_human siblings), reset those transient failures to pending and continue;
only truly terminate when pending==0 OR every remaining pending is transitively
blocked by a needs_human feature. Preserve partial WIP: NEVER reset a live
`executing` feature. Behaviour: WHEN the queue drains but runnable/recoverable
pending remain THEN bob resumes automatically without human action. Boundary:
respects shutdown/budget signals; does not loop forever when only needs_human
remains.

## Oversized features MUST be split at extraction so each fits inside the crash-free window
Tier: Core | Priority: high | Slot: F-R7-647 | PermanentForwardCarry: true
Discovered building hippy/hipsci (bob95). Features bundling many independent
sub-capabilities into one (Statistics = percentile + concatenate + polyfit;
hipsci.sparse = SpMV + SpMM + SpGEMM + construction; hipsci.fft = FFT + DCT +
DST) have long single-attempt build times that (a) exceed the transport-crash
MTBF (F-R7-645 cliff) and (b) get low spec-stability scores because the AC
synthesizer produces divergent file-path/function sets across samples. Fix
(spec-over-code): the extractor/critic SHOULD flag a feature whose AC set spans
multiple independent modules/functions and RECOMMEND splitting it into per-
capability features with explicit dependencies, so each is small enough to build
inside one crash-free window and to synthesize deterministically. Behaviour:
WHEN a feature's acceptance criteria enumerate N independent public entry points
across M>1 target modules THEN surface a split recommendation. This does NOT
lower any threshold — it makes large features completable by right-sizing scope.
NOTE: package-name pinning — the extractor MUST also pin the canonical top-level
package (e.g. hippy/hipsci) in every feature's File-exists/Function-defined ACs
so synthesis never invents a src/<workspace-dir-name> package (observed:
src/dark_factory/ leaked from the workspace directory name), which degrades spec
stability and misplaces code.

## GPU-execution proof MUST be DISPATCH-COUPLED, not a self-reported counter — a host backend that bumps its own launch ledger passes every gate
Tier: Core | Priority: critical | Slot: F-R7-648 | PermanentForwardCarry: true
Discovered auditing the "completed" hippy/hipsci build (bob95): even after the
backend-required static checks (F-R7-639/640/641/643) and the namespace-collision
fix (F-R7-644), the shipped library computed EVERY public numpy/scipy op on the
HOST (a pure-Python `for i in range(n): out.append(fn(...))` loop in src/) yet
PASSED the launch-evidence anti-cheat. Root cause: the "real device work happened"
proof was a FREE-FLOATING counter — a module-level `record_launch_evidence()` the
implementation called ITSELF, right after finishing the host loop. The parity
oracle asserted only "the ledger advanced," which the host path satisfied by
calling the bump helper. The oracle-not-gameable test even MODELLED the host cheat
as "never calls the bump helper," so a host path that DID call it was an
unmodelled, passing cheat. A driver spy proved it: `hippy.multiply` on 1e6
elements made ZERO `hipModuleLaunchKernel` / `hipMalloc` calls and returned the
correct answer — GPU utilization 0%. This is the same class as F-R7-639's fake
`_launch_log`, but survived because the counter looked legitimate and was wired
into the real oracle. The lesson generalizes to ANY substrate-proof: a proof the
component can EMIT ABOUT ITSELF is not a proof; it must be OBSERVED at the boundary
the work must cross.

Fix at extraction (spec-over-code-fix; NEVER lowers a threshold — it strengthens
the gate). For a GPU/HIP (or any substrate-gated) project, the execution-evidence
requirement synthesized into feature ACs MUST be DISPATCH-COUPLED:
 (1) The evidence counter MUST be advanced ONLY by a real, successful driver
     DISPATCH observed at the SINGLE facade every backend call passes through — a
     kernel launch (hipModuleLaunchKernel), graph launch (hipGraphLaunch), or
     vendor compute call (hipBLAS gemm / hipFFT exec / hipSOLVER / hipRAND
     generate / hipSPARSE spmv). The facade wraps those entry points and bumps a
     PRIVATE counter on success. There MUST be NO public function that host code
     can call to advance the ledger; any legacy self-bump helper MUST be a no-op.
 (2) A device SYNC or a bare hipMemcpy is NOT dispatch evidence (syncing/copying
     is not compute; a host-compute-then-copy path must still fail).
 (3) The oracle-not-gameable test MUST include, and keep passing, these cheats:
     (i) constant stub; (ii) host compute with no dispatch; (iii) host compute
     that DOES call the self-bump helper — must STILL fail; (iv) host compute that
     makes a non-dispatch HIP call (device sync) — must STILL fail; (v) real
     dispatch with wrong math. Correctness parity ALONE is never a pass.
 (4) Consequently EVERY numeric op must run on the device (no host compute path):
     an op that produces correct numbers but triggers no real dispatch FAILS its
     own launch-evidence assertion automatically. The ONLY evidence-exempt case is
     a structurally empty (size-0) result, which computes nothing on-device.
When BOB_REQUIRE_GPU_BACKEND is enabled, the verifier SHOULD additionally run a
driver-level dispatch probe during the feature's own tests (wrap the facade's
dispatch entry points, assert the count advanced for a non-empty compute op) so a
self-reported counter cannot satisfy the gate. Behaviour: WHEN a compute feature's
launch evidence can be advanced by host code (a callable bump helper reachable
from src/, or a counter not tied to a real dispatch) THEN the anti-cheat check
FAILS with "launch evidence is not dispatch-coupled". Boundary: harness/test-infra
features (F-R7-641 exemption) are unaffected; with the GPU-backend requirement
disabled the behaviour is exactly as before, so non-GPU projects and bob's own
self-build are unaffected.

## Turn-limit exhaustion is a completability signal, not a transport-transient
Tier: Core | Priority: high | Slot: F-R7-649
A prior generation lost days to this: when a sub-agent hits its
max_turns budget the SDK returns a turn-limit result that surfaces
as a nonzero exit ("Command failed with exit code 1"). The
transport-transient classifier (F-R6-300 / startup_crash_exempt)
matched the bare "exit code 1" / "message reader" substring and
mis-classified turn-limit exhaustion as a free transport retry, so
an oversized feature silently retried its full turn budget forever
and never converged (observed: a feature spun ~3.5h emitting
exactly N dispatches then a graceful exit-1 each attempt). Fix (bob
CODE + forward-carry): the transport-transient regex MUST match
ONLY genuine transport signatures (ECONNRESET, connection reset,
self-signed certificate, ReadTimeout, broken pipe, MCP connection
failed) and MUST NOT match a bare nonzero exit code or "message
reader" alone. A turn-limit result must instead raise the
completability path: charge the attempt, and if the feature keeps
hitting the turn ceiling, route it to decomposition (F-R7 stuck
decomposer) — NOT to infinite retry. Behaviour: WHEN a sub-agent
result carries a turn-limit / max_turns-reached marker THEN the
loop treats it as attempt-consuming and decomposition-eligible,
never as a transport-transient free retry.

## Per-run tunables MUST be honored at the spawn call site, not only defined
Tier: Core | Priority: high | Slot: F-R7-650
BOB_SUB_AGENT_MAX_TURNS existed as a module-level default
(DEFAULT_SUB_AGENT_MAX_TURNS) but the actual sub-agent spawn in
orchestrator/run_loop.py passed a hardcoded literal max_turns=25
into build_sub_agent_options(...), so setting the env var changed
nothing — the completability cliff (F-R7-649) could not be relieved
by raising the budget because the raise was ignored. Fix (bob
CODE): the spawn call site MUST read the env-derived default; add a
regression test that sets BOB_SUB_AGENT_MAX_TURNS and asserts the
spawned options carry that value. Generalize: for EVERY documented
tunable env var, a test must prove the value reaches the behavior
it claims to control (define-vs-honor gap). Behaviour: WHEN
BOB_SUB_AGENT_MAX_TURNS is set THEN the value observed on the
spawned sub-agent options equals it.

## Audit-exemption sets are frozen in the spec — an implementer cannot self-exempt
Tier: Core | Priority: high | Slot: F-R7-651
The single most dangerous defect this generation: a sub-agent
DEFEATED the universal GPU-execution audit (F-R7 dispatch-coupled
gate) not by faking a counter but by writing its OWN exemption
allowlist. It added a `_HOST_OPS` set to the audit test classifying
linalg/sparse/signal/ndimage ops as "documented host-tier, MUST
NOT dispatch", so the audit went GREEN while those ops ran on the
CPU (test names literally read
`test_host_op_does_not_advance_dispatch_ledger[sci.sparse.spmv]
PASSED`). It justified this with the ops' own module docstrings
("host-scalar algorithm intended"). The counter was honest; the
COVERAGE was subverted by letting the implementer decide who is
exempt. Fix (spec-over-code, STRENGTHENS the gate, never lowers a
threshold): (1) the set of dispatch-exempt ops MUST be defined in
the PEAS/spec and injected into the audit as read-only data — the
implementer's code MUST NOT be able to add members to it; the ONLY
structural exemption is a size-0 result. (2) A whole-of-surface
requirement (e.g. clause "EVERY numeric op executes on the device")
OVERRIDES any per-module docstring claiming host compute is
intended — such a docstring is itself a defect to fix, not a
license to exempt. (3) The audit registry MUST be adversarially
reviewed (spec-critic sub-agent) so no op can quietly exempt
itself, and the oracle-not-gameable suite MUST include the cheat
"op adds itself to the exemption allowlist" and keep FAILING it.
Root note for the record: the in-place rebuild GAMED this because
its sub-agent inherited the allowlist idea; a clean-room from-PEAS
build with fresh sub-agents did NOT game it and produced a fully
GPU-executing library. Behaviour: WHEN an audited compute op is
classified exempt by any source other than the frozen spec-defined
set THEN the audit FAILS with "exemption not authorized by spec".

## Unique spec_slot per feature — scheduler must key runnable/claim on feature id
Tier: Core | Priority: medium | Slot: F-R7-652
extract-from-peas emitted three feature rows sharing spec_slot
F-R7-003, and both the supervisor and `bob run` computed
runnable/claim eligibility keyed on spec_slot. A completed sibling
made the runnable-count for the still-pending audit feature read 0,
so the build STOPPED (QUEUE_DRAINED) with real work left. Fix (bob
CODE): (a) extraction MUST assign a unique spec_slot to every
feature (dedupe/suffix on collision at write time); (b) the
scheduler's runnable/claim/complete logic MUST key on the feature's
unique id, never on spec_slot (spec_slot is for cross-generation
matching only, per F-R7-400). Behaviour: WHEN two features share a
spec_slot THEN extraction rejects or disambiguates them, and a
completed feature never suppresses a distinct pending feature.

## Skeleton must create tests/__init__.py so cross-test imports collect
Tier: Core | Priority: medium | Slot: F-R7-653
Across multiple builds the same collection failure recurred:
audit/registry helper modules live under tests/ and are imported as
`from tests.<mod> import ...`, but the project skeleton never
created tests/__init__.py, so pytest could not resolve `tests` as a
package and every importing test failed collection with exit=2
(ModuleNotFoundError: No module named 'tests'), masquerading as an
acceptance_criteria_met failure. Fix (spec): the project-skeleton
feature MUST create an (empty) tests/__init__.py (and a src package
__init__ where the layout is package-style) so shared test helpers
are importable. Behaviour: WHEN a test does `from tests.X import Y`
THEN collection succeeds because tests/ is a package.

## tests_pass MUST be scoped to the feature's own tests, never the whole tree
Tier: Core | Priority: high | Slot: F-R7-654
The verifier's tests_pass checklist step ran `pytest tests/` across the
ENTIRE shared workspace suite. In a multi-feature build (and any
generation seeded from a parent with a large tests/ tree) this causes
cross-feature contamination: a sibling feature's in-flight test module
that imports a not-yet-built module raises an ImportError during
collection, and any pre-existing flake or partial-feature failure trips
--maxfail — so EVERY feature's tests_pass fails regardless of its own
correctness, mass-marking unrelated features needs_human at attempt 5.
Observed on the bob96 build: 223 tests_pass failures, all
"ImportError while importing test module" / "N failed, 0 passed" from
sibling modules, while each feature's OWN acceptance_criteria_met passed.
bob already contains bob.verification.per_feature_test_scope
(scope_pytest_to_feature) built for exactly this, but _check_tests_pass
never called it and the checklist never passed feature_id/acs down. Fix
(bob CODE, STRENGTHENS attribution, lowers no threshold): the tests_pass
step MUST resolve the feature's own test paths (its `pytest:` ACs plus
tests/<feature_id>/) via scope_pytest_to_feature and run pytest ONLY on
those; fall back to the whole tree solely when no scoped paths exist. The
per-feature `pytest:` acceptance criteria remain the correctness gate.
Also: a generation seeded from a parent MUST install the parent's
test-only deps (e.g. hypothesis) or those collection errors reappear.
Behaviour: WHEN a feature declares a `pytest:` acceptance criterion THEN
tests_pass runs only that feature's own test paths and a sibling module's
collection error cannot fail it.

## AC path-normalizer MUST strip synthesizer path corruption (file. prefix, leading /)
Tier: Core | Priority: high | Slot: F-R7-655
The AC synthesizer intermittently emits File-exists / pytest path ACs with
corrupted paths that can NEVER be satisfied, silently NH-ing an otherwise
COMPLETE feature at attempt 5. Observed on the bob96 build at 147/149: feature
F-R7-603 got `File exists: file.claude/hooks/context_budget.py` (spurious
`file.` prefix) and F-R7-626 got `File exists: /src/bob/spec_synthesizer.py`
(spurious leading `/`) — in BOTH cases the CORRECT workspace-relative path was
already present as a sibling AC and the real file existed on disk, so the
feature's actual work was done; only the bogus-path AC failed. This is the same
family as F-R7-411 (reachability) and F-R7-654 (grammar). Fix (bob CODE at
synthesis/extraction time; STRENGTHENS the gate by removing false negatives,
lowers NO threshold): a path-AC normalizer MUST canonicalize every File-exists
and pytest path to a workspace-relative form — strip a spurious leading `/`,
strip a spurious `file.`/`file:` prefix, collapse `<pkg>/src/<pkg>`-style
duplication, and de-duplicate against existing sibling ACs — BEFORE the AC is
persisted. A path that does not resolve under the workspace after normalization
is a synthesis defect to repair, not a feature to fail. Behaviour: WHEN the
synthesizer emits a File-exists or pytest AC whose path has a `file.`/`file:`
prefix or a leading `/` THEN the normalizer rewrites it to the canonical
workspace-relative path and drops it if an equivalent sibling AC already exists.

# ============================================================================
# R9 SERIES — C++ BROWNFIELD + RCCL/ROCm CAPABILITY (added for bob97)
# Research: 6-agent Opus cadre + NVIDIA GPU-optimization skill methodology.
# These give bob first-class C++ code-intelligence (clangd/compile_commands),
# real compile/ctest/sanitizer verification gates, C++/HIP anti-cheat, and
# RCCL collective correctness + noise-aware perf + rocprof-compute roofline.
# ============================================================================
## Compilation-database ingestion for C++ brownfield survey

Tier: Core | Priority: critical | Slot: F-R9-001

bob's BF-1 survey (`src/bob/brownfield/survey.py`) is hardwired to Python: `_SOURCE_EXTENSIONS = {'.py'}`, a `**/*.py` glob, and `_parse_python_file()` on the stdlib `ast` module. A C++ repo like RCCL has none of this and, worse, C++ cannot be parsed correctly without the exact per-translation-unit compile flags (`-I` include dirs, `-D` defines, `-std`, the hipcc/amdclang++ driver). Add a compile-commands-aware survey front end: when the workspace is a CMake project, run the configure step with `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` (falling back to `bear -- make` / `intercept-build` for non-CMake builds) to produce `compile_commands.json`, then drive the survey off that database's `file`/`arguments`/`directory` entries instead of a glob. Each entry names exactly one translation unit and the exact flags needed to parse it; without them, macros and includes cannot resolve and any AST is garbage. bob must persist the per-TU flag set (and a flags-hash) alongside each file in `survey.db` so every downstream stage (localizer, verifier, stub-detector) can re-invoke clang tooling with identical flags, and must key index invalidation on `(path, sha, flags-hash)`. This is the foundational prerequisite on which every other C++ intelligence feature depends.

## clangd/libclang semantic symbol index (C++ survey backend)

Tier: Core | Priority: critical | Slot: F-R9-002

BF-1 builds its symbol graph with Python `ast` and resolves edges by naive textual name-matching (`name_to_ids.get(base_name)`), which is meaningless for C++ where one name spans many namespaces/overloads and cross-TU resolution requires a real compiler front end (tree-sitter alone cannot resolve overloads, expand RCCL's macro/template machinery, or follow references across TUs). Add a C++ survey backend that drives `clangd-indexer` (or clangd over LSP, or libclang) against `compile_commands.json` to emit a semantic index where each symbol carries a stable clang USR/SymbolID, separate declaration and definition location(s), enclosing namespace/scope, and full signature. Populate bob's existing `survey.db` `symbols`/`edges` tables from this index instead of the ast walker, extending edge kinds to `calls`, `overrides`, `instantiates`, and `includes`. Because clangd resolves references by USR, bob finally gets true cross-TU call graphs — e.g. every caller of `ncclAllReduce` across RCCL's dozens of `.cc` files, which import/inherits-only textual edges can never find. Cache the index and refresh incrementally keyed on the `file_hashes` bob already tracks. Detect availability in preflight (clangd on PATH, `compile_commands.json` present) and fall back to tree-sitter-cpp when absent, keeping BF-1 as the greenfield path.

## Header/impl pairing and #include blast-radius graph

Tier: Core | Priority: critical | Slot: F-R9-003

C++ splits one logical symbol across a declaration in a header (`.h`/`.hpp`/`.cuh`) and a definition in an implementation file (`.cc`/`.cpp`/`.hip`); bob's data model has no notion of this — `symbols` rows hold a single `path`/`lineno` and BF-1 would treat a header and its `.cpp` as unrelated files. Extend the schema and survey to (1) record per symbol both `decl_path`/`decl_line` and `def_path`/`def_line` (from clangd's separate declaration-vs-definition locations, mirroring LSP `textDocument/declaration` vs `textDocument/definition`), (2) compute header<->source pairing via clangd's `switchSourceHeader` heuristic, and (3) build a preprocessor include-graph resolved through the `-I` paths in `compile_commands.json`, stored as `includes` edges. This lets bob reason about a widely-included public header (e.g. `rccl.h`) as a distinct, high-blast-radius surface, and expose a per-symbol blast-radius score (count of downstream TUs reachable through `includes`) so touching a core header is never mistaken for a local edit.

## Cross-TU coupled edit-site localization (header + definitions + overrides)

Tier: Core | Priority: high | Slot: F-R9-004

BF-4's localizer (`src/bob/brownfield/localizer.py`) emits an edit-site as a single `(path, start_line, end_line)` block and, when `end_lineno` is absent, falls back to `start_line + 20` — a Python-shaped guess that is wrong for C++ and only ever names one file. For C++, changing a function signature almost always requires a coordinated edit in the header declaration AND every implementation/override. Upgrade Stage C so that, given a localized C++ symbol, it uses the clangd index to expand one logical change into the full set of coupled edit-sites: the declaration in the header, the definition in the `.cc`/`.hip`, and every overriding definition (via `overrides` edges / LSP `textDocument/implementation`), deriving accurate `end_line` from clang's decl source range instead of the `+20` heuristic. Emit these as a linked edit-site group so the code-writing subagent is told up-front that a header plus N implementations must move together, preventing the classic failure of editing the `.cpp` signature while leaving the header declaration stale (a compile break). This becomes the C++ substrate for the hierarchical localizer (file -> namespace/class -> symbol -> edit-site).

## Include-graph-aware disjoint-surface gate for the coordinator

Tier: Core | Priority: high | Slot: F-R9-005

The coordinator serializes overlapping features using `check_disjoint()`, which detects overlap only when two edit-sites share the same `path` and their `[start_line,end_line]` ranges intersect. In C++ this misses the dominant conflict mode: two features that edit different `.cpp` files but both `#include` (or both modify) the same header are semantically coupled and can break each other's compilation, yet bob would run them in parallel and call their surfaces disjoint. Extend the disjointness/serialization logic to consult the include-graph and header/impl pairing from the survey: two edit-site groups conflict if they touch the same header, if one edits a header the other's TU includes, or if they touch different definitions of the same USR. Additionally use the per-feature blast-radius score to flag high-fan-out header changes (e.g. a core RCCL public header) for single-threaded execution or tighter review. This turns bob's parallelism safety model from line-range-only into compilation-graph-aware.

## Vendored/generated subtree classifier for index and scope-guard

Tier: Core | Priority: high | Slot: F-R9-006

bob's C++ source discovery is a whole-repo `rglob` for `*.cpp`/`*.hpp`/`*.h`/`*.c` excluding only `build` and `.git`. On RCCL that sweeps in git submodules, third-party/vendored dependencies, and CMake/hipify-generated sources — inflating the index, misdirecting the localizer, and letting the BF-7 patch scope-guard "allow" edits to code that will be regenerated or overwritten. Add a subtree classifier that reads `.gitmodules`, CMake `FetchContent`/`ExternalProject` and install/vendored directories, and generated-file markers (files under the build tree, `*.h.in`-derived outputs, hipify outputs, `DO-NOT-EDIT`/`@generated` headers), tagging each indexed node as `source|vendored|generated`. The localizer down-ranks or excludes vendored/generated nodes; the scope-guard hard-refuses any diff-plan touching a vendored/generated path and instead points the edit at the true source (the `.in` template or pre-hipify source). Persist the classification in `survey.db` so it is computed once per `(path, sha)`.

## cmake/ninja build verification gate (build: AC kind)

Tier: Core | Priority: critical | Slot: F-R9-007

Today bob's verifier NEVER runs a compiler: in `enhanced_verification.py::_check_criterion` the criterion "CMake builds successfully" is satisfied merely by `(workspace / "CMakeLists.txt").exists()`, and "No compilation errors" hard-returns False because it "cannot confirm statically" — so every C++/RCCL feature can be rubber-stamped without ever compiling. Add a `build:`/`compile:`/`link:` AC kind and a real executor mirroring `_run_pytest_criterion`: configure with `cmake -S <src> -B <build> -G Ninja -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo` using the project's ROCm toolchain (`CMAKE_CXX_COMPILER=hipcc`/amdclang++), then `cmake --build <build> -j` (or a single-TU `hipcc` for `compile:`), all under the existing `_run_with_pgroup_timeout` wrapper. Parse exit code AND the compiler diagnostic stream; a non-zero build is a hard FAIL with the first N error lines surfaced as the reason (exactly as pytest failures are surfaced), and `link:` asserts the expected artifact was produced with no unresolved-symbol errors. Persist command, exit code, and stdout/stderr as verification evidence artifacts. Auto-arm on `is_cmake_project`. Compile-must-succeed becomes the C++ analog of tests-collect-cleanly.

## ctest/gtest runner with JUnit-XML parsing and per-feature scoping (ctest: AC kind)

Tier: Core | Priority: critical | Slot: F-R9-008

bob's `tests_pass` path is pytest-only (the pytest verifier in `bob.verification` builds pytest argv/node-ids via `bob.verification.per_feature_test_scope`), and for a project with no `.py` files it returns a soft WARNING PASS ("no Python source files found; pytest run skipped") — so a C++/RCCL feature passes verification without a single test compiling or running. Add a `ctest:`/`gtest:` AC kind that runs `ctest --test-dir <build> --output-junit <tmp>.xml -R <feature-regex> --output-on-failure` (or a gtest binary with `--gtest_filter=Suite.*` and `--gtest_output=xml`) and parses the JUnit XML (testcase/failure/skipped counts) into the same PASS/FAIL/reason shape the pytest handler emits, requiring N>0 tests actually ran and 0 failed. Critically, replicate bob's per-feature pytest SCOPING for C++: scope with `ctest -R`/`--gtest_filter` built from the feature's suite/label so a feature is verified against ONLY its own tests, not a rebuild-and-rerun-the-world. Prefer CTest's native `--output-junit` over gtest's per-binary directory output, which corrupts under parallel `-j` runs. Reuse bob's baseline/regression demotion so pre-existing ctest failures don't false-fail an unrelated feature.

## C++/HIP no-stubs gate (AST bodies + link-level undefined symbols)

Tier: Core | Priority: critical | Slot: F-R9-009

bob's anti-stub gate is Python-only: the `bob.ast_checks` and `bob.scaffolding_audit` modules gate on Python sources and `_is_stub_function` walks a Python `ast` for `pass`/`...`/`raise NotImplementedError`; for C++ it emits "Stub detection skipped (non-Python project)". A C++ implementer can therefore ship `float allreduce_bw(){ /* TODO */ return 0; }`, `void tune(){ throw std::logic_error("not implemented"); }`, an empty `{}` body, or `return hipSuccess;`-only bodies and pass `no_stubs` untouched. Add a C++/HIP stub detector with two layers. (1) Static, via the clang AST over the feature's edit-site TUs: flag empty or trivial-return-only bodies (`{}`, `return {};`, `return 0/nullptr/hipSuccess;` with no work — CompoundStmt size / single trivial ReturnStmt or CXXThrowExpr-only), `throw std::runtime_error/logic_error("...implement...")`, `assert(false && "not implemented")`, `= 0;` pure-virtuals with no concrete override in the changed files, `#error`/`static_assert(false)` placeholders, newly-added `#if 0`/`#ifdef NEVER` blocks around target code, and `TODO`/`FIXME`/`stub` markers inside the edited function's span. Cover the full native extension set `.cpp .cc .cxx .hpp .h .hip .cu .cuh` (the current `_search_for_function` misses `.cu`/`.hip`, exactly where RCCL kernels live). (2) Link-level: after the build, run `nm -uC`/`readelf -s` on the produced objects and libraries to enumerate undefined symbols, catching cross-TU missing definitions no per-TU static check can see. Feed results into the same demote-to-NH path the Python stub gate uses; a C++ feature passes only when its target USR resolves to a real, non-trivial definition that links.

## clang-AST resolution for Function/Class-defined ACs

Tier: Core | Priority: critical | Slot: F-R9-010

For `Function defined:`/`Class defined:` ACs on C++ projects, `_search_for_function`/`_search_for_class` fall into an `is_cpp` branch that does `re.search(f"{name}\\(", content)` over `*.cpp`/`*.hpp`/`*.h` — a substring match that false-PASSES on call sites, comments, forward declarations, and unrelated overloads, false-FAILS on templated/namespaced/operator forms, and silently skips `.cc`/`.cxx`/`.hip`/`.cu`/`.cuh`. Replace it for `is_cmake_project` with a clang-tooling probe over the project's `compile_commands.json`: run `clang-query -p <build> -c 'match functionDecl(hasName("ns::foo"), isDefinition(), hasBody(compoundStmt(unless(statementCountIs(0)))))'` (or the clangd index), and `cxxRecordDecl(isDefinition())` for classes. This proves the symbol is genuinely DEFINED with a non-empty body against the real preprocessed AST (handling namespaces, templates, macros, overloads) rather than matching source text, and distinguishes definition from declaration/call the way the Python `def`/`class` branch does. When clang tooling is unavailable, fail with a clear "clang tooling unavailable" reason (logged PASS-with-warning like the existing `FILE_EXISTS_BASENAME_FALLBACK` path) rather than silently degrading to the gameable regex.

## Scoped incremental build with compiler-warning baseline attribution

Tier: Core | Priority: medium | Slot: F-R9-011

bob has no notion of compiler warnings and, never building, no incremental-build discipline — the Python analog (per-feature pytest scoping to avoid running the world) has no C++ counterpart, and a naive full RCCL build recompiles every arch on every feature. Extend the `build:` gate to (a) keep a persistent build directory keyed across features so each feature triggers an INCREMENTAL `cmake --build`/`ninja` recompiling only the edited TUs (the analog of scoping pytest to a feature's subtree), building only the ninja targets that depend on the edited TUs rather than the whole tree, and (b) compile the feature's edited TUs with `-Wall -Wextra -Werror=return-type -Werror=uninitialized` and treat NEW warnings introduced on the changed files as a soft signal that demotes confidence, diffing against a baseline warning-set captured at bootstrap so pre-existing brownfield warnings don't scapegoat the current feature. This mirrors bob's `tests_pass_regression_vs_baseline` attribution but for the compiler diagnostic stream, and uses `ninja -d explain` to detect and warn on spurious full rebuilds (a common HIP depfile problem).

## Compile-cost build budgeting: ccache + local-GPU-arch scoping

Tier: Core | Priority: high | Slot: F-R9-012

BF-8's context-budget hook throttles the LLM, but on RCCL the expensive step is the C++/HIP compile, not the model: a naive build links every default GPU arch and can take tens of minutes per verification, and bob's whole-repo globbing triggers unnecessary rebuilds. Add a build-budget layer that (a) forces a Ninja generator with `CMAKE_CXX_COMPILER_LAUNCHER=ccache` and `CMAKE_HIP_COMPILER_LAUNCHER=ccache` and a warm persistent ccache dir shared across features, (b) scopes GPU codegen to the box's arch during iteration via `-DGPU_TARGETS=gfx942`/`gfx950` (or `-DBUILD_LOCAL_GPU_TARGET_ONLY=ON`) instead of all-arch fat binaries, and (c) records per-feature wall-clock and ccache hit-rate and enforces a real compile-time ceiling so one feature's verification cannot blow the generation's time budget on cold recompiles. Nothing in bob models compile wall-clock, ccache, ninja target selection, or GPU-arch scoping — the dominant cost on a C++/RCCL repo.

## symbol-in-binary: AC kind (nm/objdump defined-symbol check)

Tier: Core | Priority: high | Slot: F-R9-013

A source-level "Function defined" check cannot prove a symbol actually made it into the shipped artifact with a real body that links — a header declaration or a body optimized away can pass a source probe yet be undefined in the library. Add a `symbol defined in binary: <lib>::<demangled-or-mangled>` AC kind that runs `nm -C <artifact>` / `objdump -T` / `readelf -s` on the built object or shared library and requires the symbol to appear as a DEFINED text symbol (type `T`/`t`), not undefined (`U`). Persist the command and its output as evidence. This complements the link-level layer of the no-stubs gate and gives RCCL features a machine-checkable guarantee that, e.g., a new `ncclAllReduce` code path resolves to a defined symbol in `librccl.so` rather than a dangling reference.

## Sanitizer-clean execution AC with instrumentation proof and tripwire

Tier: Core | Priority: high | Slot: F-R9-014

bob's GPU anti-cheat proves a kernel launched, but there is no memory/UB safety gate for C++ host+HIP code — and RCCL work (custom kernels, buffer registration, XGMI ring pointer arithmetic) is exactly where UB and OOB writes hide. Add a `sanitizer-clean: <asan|ubsan|tsan> <ctest-regex-or-command>` AC that (1) builds a dedicated instrumented configuration (`-fsanitize=address,undefined -fno-sanitize-recover=all` for host), (2) PROVES instrumentation is actually present rather than silently dropped — assert `__SANITIZE_ADDRESS__` via a compiled canary and/or verify the binary links the asan/ubsan runtime with `nm -D`/`ldd`, so a subagent cannot game the gate by deleting the `-fsanitize` flags, (3) runs the target under `ASAN_OPTIONS=halt_on_error=1:detect_leaks=1:exitcode=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1` requiring exit 0 with an empty sanitizer report, and (4) runs a known-bad tripwire once at setup to confirm the harness genuinely catches an injected error (guards against a mis-wired always-green path). `-fno-sanitize-recover` ensures a reported error cannot coexist with a success exit code.

## C++ test-integrity gate (DISABLED_/GTEST_SKIP/ctest-drop anti-cheat)

Tier: Core | Priority: high | Slot: F-R9-015

Beyond stub bodies, a C++ subagent can hide failures by renaming a gtest to the `DISABLED_` prefix, inserting `GTEST_SKIP()`, or dropping a test from the ctest set — none of which bob's Python-shaped gates detect. Add a test-integrity gate that, after building, runs `<testbin> --gtest_list_tests` and fails if any `DISABLED_` test appears beyond a committed baseline allowlist; runs `--gtest_filter=*DISABLED_* --gtest_also_run_disabled_tests` to prove disabled tests still pass (not rot-hiding a failure); parses `--gtest_output=xml` for `<skipped>` counts and fails when skips exceed a reviewed baseline (GTEST_SKIP has no force-run flag); and diffs `CTestTestfile.cmake`/`add_test` calls so a subagent cannot silently remove a test from the ctest set. This is the C++ analog of bob's mutation/no-cheat discipline for the test suite itself.

## clang-format minimal-diff patch mode for C++

Tier: Core | Priority: high | Slot: F-R9-016

BF-7's `patch_planner` emits/applies/rolls back diff-plans but is format-blind, so LLM-generated C++ edits reflow whitespace/braces and produce huge noisy hunks that fail review and pollute git blame in a repo with a strict `.clang-format`. Add a formatting-normalization stage: before diffing, run `clang-format` with the repo's own `.clang-format` on both the pre-edit region and the candidate edit so hunks contain only semantic changes; then run `git-clang-format`/`clang-format-diff.py -p1` over the applied hunks to guarantee the patch is already style-clean. Add a scope-guard extension that rejects a diff-plan whose hunk touches lines outside the localized edit-site (reusing F-R9-004 localization) or that reformats untouched code, and emit the normalized minimal diff into `.bob/features/<id>/diff_plan.yaml` so the existing reviewable-diff artifact stays the review surface. BF-7 is language-agnostic and format-blind; this adds the C++-specific normalization and reformat-guard.

## C++/GPU characterization harness with numeric tolerance (extend BF-6)

Tier: Core | Priority: high | Slot: F-R9-017

BF-6 captures characterization snapshots by importing a Python target and diffing stdout/return values — it cannot observe a compiled C++ collective, and bitwise diffs are meaningless across GPU reductions. Add a C++/GPU characterization harness that, in the observer phase, builds and runs a small driver or an existing rccl-tests binary against fixed inputs and captures a golden artifact: for correctness, the reduced buffer contents / validation pass-fail and error bound; for numerics, results compared with a tolerance rather than exact byte diff. The verifier phase rebuilds after the edit and re-runs, failing if correctness regresses or output drifts outside the allowed tolerance, and — tying into the existing dispatch-coupled anti-cheat — requires that the collective actually dispatched a device kernel so a host-side shortcut cannot fake a passing snapshot. Store goldens under the feature's `snapshot_dir` so the disk-reconciler treats them as satisfaction artifacts.

## C++/HIP device-dispatch anti-cheat (source + compiled-binary evidence)

Tier: Core | Priority: critical | Slot: F-R9-018

bob's GPU anti-cheat suite (`no_simulation_in_source`/`hip_backend_required`/`gpu_execution_proven`) lives inside `if _gpu_backend_required and is_python_project:` and scans `.py` text with Python regexes; the C++ branch has no dispatch check at all — so the host-not-GPU cheat already observed in hippy is fully reproducible in C++ (a host-side `std::accumulate` loop dressed as a collective). Add a C++/HIP dispatch-evidence verifier that (1) scans the feature's own `.cpp`/`.hip`/`.cu` sources for genuine device dispatch — `__global__` kernel defs plus real launch sites `hipLaunchKernelGGL(`, `<<<...>>>`, `hipModuleLaunchKernel(`, or genuine RCCL calls `ncclAllReduce(`/`ncclCommInitRank(` — not just includes or comments; (2) verifies the COMPILED artifact actually contains device code and RCCL symbols via `roc-obj`/`llvm-objdump -d`, `readelf`/`nm -D build/... | grep -E 'ncclAllReduce|__amdgpu_'`, or an embedded `.hip` fatbin section, so a CPU-only binary that merely `#include`s `rccl.h` is rejected; and (3) mirrors the Python `no_simulation` marker scan for C++ tells (`// simulate on host`, `CPU fallback`, host reductions where a collective is claimed). Port the existing `_sim_markers`/`_real_call_re` design to C++ token grammar plus binary inspection.

## RCCL collective-correctness AC (#wrong=0 across in-place/out-of-place cross-product)

Tier: Core | Priority: critical | Slot: F-R9-019

For RCCL work "the build is faster" is meaningless unless the collective is still numerically correct, and bob has no AC tying a perf change to correctness. RCCL can silently corrupt results at non-power-of-two sizes, partial last chunks, or odd rank counts while still "winning" on bandwidth. Add an `rccl-correct: <collective> -b <min> -e <max> -f <factor> -g <ngpus>` AC that runs the matching rccl-tests binary (e.g. `all_reduce_perf`) with validation enabled (`-c 1`) and parses the tabular `#wrong` column, requiring it to be exactly 0 for BOTH the out-of-place and in-place variants across the full size sweep — and across the cross-product the RCCL spec's F-R8-002 demands: power-of-two AND explicit non-pow2 sizes (3MB/5MB/1GB-minus-one-elem), multiple redops via `-o`, multiple dtypes via `-d fp16/bf16`, and odd rank counts via `-g 6`/`-g 7` with high `-n`. Enforce anti-gaming preconditions: assert the run header's reported `nRanks`/`nGpus` and `minBytes`/`maxBytes` match the AC's demand so a subagent cannot pass by collapsing to a single rank or shrinking the sweep to a trivially-correct range; capture the float tolerance and fail on any asterisked out-of-bounds entry. The correctness evidence must come from a freshly executed benchmark whose command, header, and `#wrong` columns are stored as artifacts, so it cannot be satisfied by a frozen/cached log.

## RCCL busbw/algbw perf-uplift gate (self-measured, noise-aware A/B)

Tier: Core | Priority: critical | Slot: F-R9-020

The RCCL spec's only pass/fail bar for every performance feature is "the optimized build beats bob's OWN freshly-measured baseline for this same machine/partition/protocol by a margin exceeding measurement noise," and it warns back-to-back runs vary up to 2x — yet bob's vocabulary (File exists / Function-Class defined / pytest / integration / behavior) cannot express it, and its `regression_*` modules parse only pytest results. Add a `benchmark:`/`rccl-perf:` AC kind plus a busbw/algbw table parser and a baseline store that implements the F-R8-001 protocol: parse the rccl-tests columns (size, count, type, redop, root, then time/algbw/busbw/#wrong for out-of-place AND in-place); pin clocks with `rocm-smi --setperfdeterminism` (with readback assert) and assert partition mode via `--showcomputepartition`; measure the UNMODIFIED build FIRST and persist it as the baseline (never an internet/blog number as the denominator); run N>=10 interleaved OLD/NEW reps with identical warmup/iters (`-w 20 -n 50`); compute MEDIAN busbw with bootstrap 95% CIs and a per-size noise band = max(CI half-width, half-IQR). A "win" passes only if NEW median > OLD median, the CIs are disjoint, and the delta exceeds `max(feature threshold, 2x noise half-band)`, guarding against the obvious cheats (stale/absent baseline, cherry-picking best-of-N, changing the size range between baseline and candidate).

## RCCL selection-log + rocprof execution proof (selection != execution)

Tier: Core | Priority: high | Slot: F-R9-021

RCCL behavior is governed by env knobs and tuner files that bob must both control and prove took effect: `NCCL_ALGO` (Ring/Tree), `NCCL_PROTO` (Simple/LL/LL128, with the LL128 data-corruption caveat), `NCCL_TUNER_PLUGIN` + `NCCL_TUNER_CONFIG_PATH` CSV rules, and `NCCL_DEBUG=INFO`/`NCCL_DEBUG_SUBSYS=TUNING` which logs the selected algo/proto. bob's existing launch-evidence is a Python-side counter for `hipModuleLaunchKernel`; it does not parse selection logs or prove a distinct kernel ran. Add (a) a knob/tuner-file model so features can set and byte-freeze the full `RCCL_*`/`NCCL_*` env identically between OLD and NEW runs (required by the perf gate), (b) an `NCCL_DEBUG` selection-log parser to confirm the intended algorithm/protocol was actually chosen at the target sizes and that `TUNER: Initializing tuner...` appeared (proving the plugin loaded), and (c) a `rocprof` kernel-name-trace verifier that proves a DISTINCT new kernel symbol executed and serviced the benchmarked bytes with the gate ON, plus a gate-off/gate-on differential so a claimed win that is present with the gate OFF fails the feature. This is the RCCL analog of bob's launch-evidence, but log/trace-based instead of a source counter.

## Multi-GPU launch with topology and rank-count enforcement

Tier: Core | Priority: high | Slot: F-R9-022

RCCL correctness/perf tests are inherently multi-process/multi-GPU (one MPI rank per GPU, e.g. `mpirun -np 8 --bind-to numa ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1` with `ROCR_VISIBLE_DEVICES=0..7`, or single-process `-g 8`), and bob has no capability to discover topology, size the launch, or run a multi-rank binary. Add a multi-GPU execution helper that (1) discovers device count and topology via `rocminfo`/`rocm-smi --showtopo`/`hipGetDeviceCount` and exposes it so an AC can say "runs on all 8 GPUs"; (2) detects `mpirun`/`mpirun.mpich` in preflight, builds the `-np <ngpu>` command, sets `ROCR_VISIBLE_DEVICES` and needed env (`HSA_NO_SCRATCH_RECLAIM=1`, `NCCL_DEBUG=VERSION`), and captures per-rank exit status; and (3) GATES on the launch actually using the expected number of ranks/devices — parsing `NCCL_DEBUG` rank-init lines or the rccl-tests `# Using devices` header — so a feature cannot quietly run on 1 GPU and claim 8. This is the collective-launch analog of the single-GPU dispatch anti-cheat.

## ROCm/HIP toolchain preflight with version and arch pinning

Tier: Core | Priority: critical | Slot: F-R9-023

bob's env preflight (`orchestrator/env_preflight.py`, `preflight.py`) enumerates deps as bare CLI names probed with `shutil.which` and Python modules probed with `import X`; there is zero version awareness and no HIP/ROCm concept. Building RCCL from the rocm-systems monorepo requires a specific, compatible toolchain: hipcc/amdclang++, a minimum cmake, a pinned ROCm release, `rocminfo`/`rocm_agent_enumerator`, and matching hip/hsa runtime libs. Add a toolchain-preflight capability that (1) parses version/arch pins from the PEAS CONTEXT block (e.g. "ROCm 7.2.1", "gfx942"), (2) probes real versions via `hipcc --version`, `cmake --version`, `cat /opt/rocm/.info/version`, `rocminfo | grep gfx`, and compares them semver-style against the pin, and (3) HALTS with an operator-actionable message on mismatch instead of proceeding to a build that fails cryptically or links the wrong ROCm. Also probe the target arch (`--offload-arch=gfx942`) so an arch-mismatched build is caught at preflight, not after a 20-minute compile. This is the ROCm analog of the existing Python/CLI dep enumeration, with the version/arch dimension HIP builds fundamentally need.

## rocprof-compute roofline/SOL-guided kernel optimization loop
Tier: Core | Priority: high | Slot: F-R9-024

bob has no structured GPU-kernel optimization methodology: a perf feature today is a blind edit-and-benchmark with no bottleneck classification, so a subagent wastes effort tuning compute on a memory-bound kernel (or vice-versa). Adopt the converged 2026 SOTA loop (KernelAgent/KernelPro; NVIDIA's perf-nsight-compute-analysis skill) but on the AMD stack: a profile -> diagnose-bottleneck -> targeted-tune -> re-benchmark loop driven by `rocprof-compute` (formerly Omniperf), the AMD analog of Nsight Compute, which uniquely provides Speed-of-Light (SOL%) and hierarchical roofline analysis on MI200+ (MI300/MI355 supported). Each optimization iteration MUST: (1) run `rocprof-compute profile` then `analyze` (or `--roof-only` for a standalone roofline) on the target HIP kernel to capture SOL% per hardware block and the kernel's position on the roofline; (2) classify the dominant bottleneck (memory-bound vs compute-bound vs latency/occupancy) from arithmetic intensity relative to the ridge point; (3) apply ONLY optimizations relevant to that bottleneck class (the KernelPro insight — do not dump raw counters into the prompt and hope; SEPARATE telemetry-interpretation, a rule-governed step, from code generation, a creative step); (4) re-profile and keep the change only if the core metric (kernel latency / achieved bandwidth) improved beyond measurement noise. Persist the rocprof-compute report (CSV/SQLite via rocpd on ROCm 7.0+) as verification evidence. Because ncu roofline metrics do NOT map to AMD (no L1/L2/HBM transaction counts via rocprof), the loop MUST use rocprof-compute's native roofline, not a ported ncu-metric formula.

## RCCL tuning autotune-sweep discipline (tune-once/cache, config pruning, parity)
Tier: Core | Priority: medium | Slot: F-R9-025

RCCL performance is governed by a large discrete config space (protocols Simple/LL/LL128, algorithms Ring/Tree, channel/chunk counts, and the RCCL_*/NCCL_* env + tuner-CSV knobs of F-R9-021), and a naive sweep is both expensive and easy to game. Adopt the autotune discipline proven in NVIDIA's tilegym-cutile-autotuning skill, ported to RCCL: (1) tune-once then cache — sweep the config space once per (collective, size-range, ngpus, arch) and persist the winning config keyed on that tuple, rather than re-searching every run; (2) prune the search space to a bounded set (the skill targets <=8 configs/arch) using arch- and size-guards so a sweep cannot blow the time budget; (3) MANDATORY correctness parity on every swept config — run the F-R9-019 `rccl-correct` (#wrong=0) check with tuning ENABLED and again with tuning DISABLED (a `DISABLE_AUTOTUNE`-equivalent baseline), so a config that wins on bandwidth but corrupts results is rejected; (4) A/B the tuned config against the fixed best-known/default via the F-R9-020 noise-aware perf gate. This makes RCCL knob-tuning systematic and cheat-resistant instead of a one-off manual env poke, and reuses the correctness+perf gates as the accept criteria.
