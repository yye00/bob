# Bob migration to PowerPerformance Twin v0.4.1

Status: implementation handoff, 2026-09-21. This document changes the plan only.
Start with the [migration index](README.md), then the supplied
[agent workflow](../../../power-spec-2/agent-execution-and-independent-validation.md)
and [trusted evaluation contract](../../../power-spec-2/blind_evaluation_component.md).
The shared backlog and validation matrix in this directory control task ordering;
the Bob work slices below refine those tasks, rather than create another backlog.

The subsequent [local-first build cross-check](LOCAL_FIRST_BUILD.md) adds actual
current wheel/runtime tests. It found eight failing admitted-packet tests caused
by incomplete custody/materialization construction, three executor-group failures,
and the atomic planner's separate `claude-opus-4-8`/unlimited-turn hardpin. These are
local repair prerequisites before a downgraded implementation campaign; the earlier
70-test baseline below did not cover those paths. The current wheel builds and
runs with existing dependencies, but clean offline dependency closure remains open.

## Authority and discovery boundary

`bob/` is a separate Git repository, represented by a gitlink in the parent.
The audit found 3,652 tracked Bob files and a clean Bob working tree before these
planning edits. Capture the actual Bob commit, parent commit, local diff and
installed package identity at implementation start. A parent `git diff` alone
does not show uncommitted changes inside Bob. Do not reset another repository or
replace the existing Bob database to manufacture a clean campaign.

The supplied `power-spec-2/` contains nine flattened Markdown files. References to
`docs/normative-contract.md`, `evidence/backlog.json`, `schemas/`, `agent_tasks/`,
`tools/check_release.py`, `tests/` and the full W/C exposure definitions do not
exist in that supplied directory. This handoff records requirements visible in
the supplied documents; it cannot assert the missing package was audited. The
local migration backlog is a derived planning artifact, not the missing upstream
backlog. Obtain the missing governing material or resolve a bounded contract
before an affected interface or qualification task becomes READY. Unaffected
read-only inventory and public synthetic tests can proceed.

No physical outcomes, secret stores, credentials or Bob runtime database were
read during this audit. Counts below describe tracked paths, not validated
implementation completeness. A matching module name is only a reuse lead.

## Changes in the implementation contract

| Existing Bob capability or assumption | Required Power spec 2 treatment |
|---|---|
| Self-improving orchestrator, research expansion and recursively generated feature YAML | Use the existing executor for bounded versioned packets. Do not create another scheduler, orchestrator, simulator, power language or generic inference engine. Do not let research expand the approved scope. |
| Generic software features become `completed` after local verification | Keep task execution, independent validation and scientific qualification separate. Code completion, native operability and same-target/blind numerical acceptance are different levels. |
| `BOB_AGENT_ROLE` and `role=verifier` in text identify reviewers | These are provenance hints, not separate principals. A developer cannot self-authorize a verifier role or acquire label/scorer write privileges by changing task prose. |
| Subagents default to `bypassPermissions`; existing GPU containers can run directly on the host when Docker is absent | New prediction/validation profiles require an externally enforced capability boundary and fail closed if it is unavailable. A hermetic CLI configuration is not a label vault. |
| Generic memory, prompts, artifacts and transcripts are shared for learning | Partition by role and exposure. Do not place sealed labels, raw combined traces, private residuals or private test seeds in developer memory, logs, bundles or caches. |
| Default escalation is `sonnet,opus`; `bob_build.env` maps every alias to Opus 4.7 | Implementer model selection is explicit and recorded. A downgraded-model run must resolve to the requested model, without an inherited alias silently selecting Opus. No model is chosen by this planning document. |
| Unlimited attempts, unlimited RCA/turn settings and effectively unlimited cost are supported | Every Power packet has finite attempt, wall-time, cost/resource and reveal limits. Retry/restart/relabeling must not reset those limits. Generic Bob compatibility need not be removed. |
| Snapshot observers and GPU reduction goldens are called characterization | They are software correctness facilities. Physical power characterization additionally needs qualified sensors/operators, boundary, acquisition identity, all attempts, uncertainty and separation from scored outcomes. |
| Acceptance can be structural, executable Python, local pytest, warning-pass or baseline demotion | Structural checks establish structure only. Scientific scoring consumes data-only immutable bundles. Required native tests cannot pass because they are missing, skipped, timed out or already failing in a baseline. |
| Source-span `provenance` tracks an AC back to user text | Retain it for requirements traceability; add actual code/input/config/build/runner/dataset/measurement lineage. An AC span or a content hash does not prove physical origin. |
| Historical `D1`, `D2`, `D3` paper examples and HPC tier plan | Do not confuse Bob's nanoGPT/WASM/Navier–Stokes examples with current acquisition/D2a/D2b/transfer stages. Old HPC paper timelines and A100-first recommendations do not govern this migration. |
| An available generic simulator or valid native example implies target support | D1 reports actual support/gaps. FP8, MI355 mechanisms, power binding, trace coverage, timing semantics and physical accuracy require separate evidence. |

## Complete directory disposition

The intent of “revise everything” is a reviewed disposition of the entire tree,
not rewriting unrelated working code or historical inputs. Explicitly inspect
the call path before editing a candidate. Preserve compatibility fixtures unless
the Power task demonstrates why they must change.

| Bob area (tracked count at audit) | Disposition and implementation obligation |
|---|---|
| `README.md`, `WORKER.md`, `BOB_GREENFIELD_GAP_ANALYSIS.md`, `spec_constitution.md` | Add current migration entrypoint; implement a Power-specific worker context under A-01. Keep generic/history content distinguishable from current authority. Never load the entire old feature history as the Power contract. |
| `docs/` (14 before this plan) | Keep generic architecture/failure/review documentation; use `docs/power-spec-2/` for this migration and future evidence pointers. Do not claim legacy diagrams establish independent security. |
| `config/` (1), `bob_build.env`, `bob_supervisor.sh`, `stall_watcher.sh`, `install.sh`, `spawn_next_generation.sh` | Audit launch chain, environment, model aliases, restart behavior and budgets. Use a scoped Power launch profile; do not launch recursive self-build/supervisor scripts for scientific qualification. |
| `pyproject.toml`, `setup.py`, `MANIFEST.in`, `uv.lock` | Keep reproducible dependency/package identity. Confirm any new adapter resources are packaged; do not add every candidate provider or numerical library to Bob. Native providers keep their own builds. |
| `schemas/` (1), `features.yaml`, `specs/` (199) | Existing `spec.v1.json` and feature inventory are generic Bob inputs, not the new scientific contracts. Add a versioned packet adapter/schema only after missing-contract resolution; retain historical files without bulk renaming D/F IDs. |
| `src/` (1,288) | Primary integration is `src/bob/`; inspect transitive dependencies before editing `hippy`, legacy generation packages or shims. Make minimal changes to real execution paths and add a scoped adapter, not parallel copies of the loop. |
| `tests/` (2,073), `conftest.py` | Reuse scoped suites and namespace guard. Add public synthetic, integration and external-principal verification at the appropriate layer. Never put private challenge cases in developer-readable tests. |
| `tools/` (17) | Reuse maintenance/coverage tools where applicable. A plan renderer/checker is documentation tooling, not an execution or authorization system. |
| `migrations/` (1), `sql/` (1), `src/bob/migrations/`, `src/bob/schema.sql` | Inspect actual database ownership before adding task-state/evidence references. Migrate additively with old DB compatibility and rollback evidence; never read or migrate sealed outcomes into Bob. |
| `examples/` (13) | Keep historical examples; add only clearly labeled Power contract/synthetic examples if required. No physical gold, commercial prerequisites or implied hardware authorization in example YAML. |
| `paper-planning/` (7) | Historical HPC-code-generation direction and 18-week staffing plan are not Power delivery commitments. Reuse relevant defect ideas, not its scope or calendar. |
| `generation/` (10), `workspace/` (1) | Historical/generated copies; exclude from automatic source authority and instruction context. Change only if import/call tracing proves runtime dependence. |
| `skill_library/` (4), `src/bob/skills/`, `.claude/` (4), `.bob3/` (1) | Inspect allowlisted tracked templates as needed. Validate skill provenance and keep bounded Power instructions distinct from generic memory/research/self-review advice. Do not inspect private runtime state to populate a plan. |
| `.bob/`, `.venv/`, `.hypothesis/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `bob.db` | Local runtime/cache/database artifacts are not requirements or approved blind inputs. No bulk cleanup, blind inheritance or copying into submissions. Use an isolated test/campaign workspace. |
| `.git/`, `.gitignore`, `LICENSE` | Preserve repository/history/license boundaries. Capture commits/diffs and required terms; do not alter Git internals as part of this migration. |

## Concrete runtime entrypoints and gaps

Paths in this section are relative to `bob/`. They are inspection targets, not
instructions to edit every file. Aliases and historical modules are common:
prove that a change reaches dispatch and validation before declaring completion.

| Concern / task mapping | Existing paths to inspect and reuse | Required change or boundary |
|---|---|---|
| Packet loading and scope, F-01/A-01/A-03 | `schemas/spec.v1.json`, `src/bob/spec_loader.py`, `src/bob/spec_provenance.py`, `src/bob/atomic_packet_planner.py`, `src/bob/dispatch.py`, `src/bob/cli/plan.py` | Preserve source task IDs/dependencies and requirement mappings. A packet must name inputs/access class, permitted writes, native tests, oracle, defects, validator, command/resource profile, finite repair/reveal budget and blocked reasons. Reject unknown/schema-incompatible fields rather than silently dropping policy. |
| Executor/model identity, A-01 | `src/bob/orchestrator/claude_executor.py`, `src/bob/model_escalation.py`, `bob_build.env`, `src/bob/dispatch.py`, `WORKER.md` | Reuse `BOB_REQUIRED_MODEL` resolution and role records. Validate the actual resolved model before side effects; record requested alias and provider response identity. Unknown model fallback and unapproved escalation must not enter a pinned campaign. Keep agent-vendor adapter ownership narrow. |
| State/retry/cost, A-01/A-03 | `src/bob/models.py`, `src/bob/db.py`, `src/bob/schema.sql`, `src/bob/orchestrator/run_loop.py`, `src/bob/spawn_retry.py`, `src/bob/orchestrator/spawn_retry.py`, `src/bob/orchestrator/rca_attempt_budget.py`, `src/bob/per_attempt_cost_cap.py`, `src/bob/telemetry.py`, `src/bob/bundle.py` | Map current states to the spec state machine through explicit records. Persist attempts atomically and bind submissions/validation to exact parents. Enforce a finite outer campaign budget even for transient transport retries, crashes, RCA and resume. Record measured versus proxy cost. |
| Principal isolation, A-02/F-07 | `src/bob/container_runner.py`, `src/bob/orchestrator/claude_executor.py`, `src/bob/orchestrator/verifier_sandbox.py`, `src/bob/skills_installer.py`, existing external launcher/IAM/storage | Use approved existing OS/container/IAM enforcement. Separate developer, acquisition, preparer/scorer, predictor, independent validator and release capabilities. Builder default `bypassPermissions`, role environment variables and writable worktrees do not implement this. |
| Memory/input exposure, A-02/F-06/F-07/B-01 | `src/bob/memory.py`, `src/bob/memory_client.py`, `src/bob/memory_mcp.py`, `src/bob/workflow_memory_spec_attempt_outcome_traces.py`, `src/bob/dispatch.py`, `src/bob/bundle.py` | Allowlist contexts and approved-view artifacts. Deny raw combined traces, label descendants, shared writable caches, scorer credentials, raw devices and unnecessary network. Retain private review separately from developer feedback; implement finite reveal accounting across restarts. |
| Native build/test evidence, F-04/F-09/F-10/V-01..V-04 | `src/bob/toolchain_preflight.py`, `src/bob/build_verification.py`, `src/bob/verification/ctest_runner.py`, `src/bob/enhanced_verification.py`, `src/bob/cpp_test_integrity_gate.py` | Keep exact native argv/cwd/env allowlist, build/runtime identity, selected-test inventory, logs/status, hashes, skipped/failed cases and actual work completion. A missing pin is discovery, not qualification. Reuse provider-native tests before adapters. |
| Generic artifacts/provenance, F-06/F-07/F-08 | `src/bob/artifact_verifier.py`, `src/bob/verification/ac_artifact_check.py`, `src/bob/provenance.py`, `src/bob/provenance_tracker.py`, `src/bob/acceptance/disk_reconciler.py`, `src/bob/disk_state_reconciler.py`, `src/bob/bundle.py` | File existence and intent spans are insufficient for physical provenance. Add schema/units/finite values, identities, native-normalized correspondence, full work/attempt coverage, field ancestry and independent attestations in a domain adapter. Disk reconciliation must not promote a scientific claim from files alone. |
| Characterization, F-03/K-01/K-02 | `src/bob/acceptance/kinds.py`, `src/bob/acceptance/characterization.py`, `src/bob/acceptance/characterization_observer.py`, `src/bob/cpp_gpu_characterization_harness.py`, actual existing physical harness outside Bob | Reuse process/artifact handling only after audit. A callable result and software launch counter do not prove sensor origin, calibration or measurement uncertainty. Keep physical acquisition and calibration roles outside developer self-observation. |
| Independent release, F-07/F-08/P-05 | Current verifier integration in `src/bob/orchestrator/run_loop.py` and external verifier launcher, generic reports/bundles | Bob submits immutable artifacts and receives an authenticated scoped decision. The deterministic scorer/policy and private checks remain under separate ownership. Do not import arbitrary Python acceptance code from a scientific submission. |
| Frequency path, X-01..X-05/P-01/P-02/U-01 | Existing native device tools, physical harness and selected providers; Bob dispatch/evidence interfaces above | No native frequency protocol was found in the inspected Bob runtime. Represent the five ordered tasks explicitly. Discover first; preserve work; freeze trial design; acquire independently; score absolute and paired/joint effects. Do not implement clock writes during planning or assume HBM/GFX independence. |

`src/bob/research/harness.py` is a research-proposal runner, not the physical
acquisition harness. `src/bob/provenance.py` is AC-source-span tracking, not an
attestation library. `src/bob/d1_d2_d3_yaml_specs_paper_artifact_stub.py` contains
nanoGPT/WASM/Navier–Stokes paper tasks. These name collisions must not cause a
lower-capability implementer to reuse the wrong abstraction.

## Bounded implementation slices

Implement each slice only once its shared backlog prerequisites are satisfied.
These slices fit within A-01/A-02/A-03 and related F/X tasks; they do not alter
the source task dependency graph. Each PR names its slice and source task IDs.

### B1 — Authoritative packet adapter (A-01, F-01)

1. Trace one public synthetic packet through the actual loader, dispatcher and
   worker context. Record the authoritative source hashes and original IDs.
2. Define the minimal adapter from the resolved packet schema to Bob's feature
   model. Keep policy fields intact; do not translate executable native commands
   into vague prose ACs. Keep command arguments structured and shell-free where
   possible; apply cwd, output and resource constraints outside the prompt.
3. Make plan generation deterministic and idempotent. Unknown dependency,
   cycle, duplicate ID, missing validator, traversal/symlink output, incompatible
   schema, unauthorized command profile or absent budget must prevent dispatch.
4. Test one denied and one permitted synthetic dispatch, and verify the selected
   tests, output paths and IDs match the frozen packet. No agent credentials or
   physical execution are needed for public contract tests.

### B2 — Finite model/execution profile (A-01, A-03)

1. Add a Power profile at the existing executor boundary. Preserve generic Bob
   defaults outside that profile. Set exact model policy, permitted escalation,
   capabilities, finite turns/time/attempt/cost budgets and immutable input IDs.
2. Test that `bob_build.env` alias overrides cannot silently violate a requested
   model pin. Reject unsupported model IDs before filesystem/SDK effects; record
   the actually executed model. Do not assume the word `sonnet` means cheaper.
3. Exercise timeout, cancellation, startup failure, transient retry, RCA,
   process death and resume. Every attempt is retained; exhausted budgets remain
   exhausted across restart. No unlimited sentinel or malformed env override can
   widen the packet. Unrelated READY tasks remain runnable.
4. Test monotone execution history and atomic submission. An old success record
   must not satisfy a new code/input/policy identity. A crash before publication
   leaves a partial attempt, not an accepted artifact.

### B3 — Real principal separation (A-02)

1. Inventory the existing launcher/IAM/storage interfaces and choose their
   smallest reusable capability profile. First use synthetic canary stores;
   developers must not inspect a sealed production label store to test isolation.
2. Establish separate identities/worktrees and read/write grants. Predictor input
   is a fresh allowlisted artifact, never a raw combined trace plus a promise to
   ignore fields. Dataset/scorer versions and private seed policy are immutable.
3. Deny predictor access to the scored device, external acquisition credentials,
   writable shared caches and unneeded network. Authorize model-evaluation compute
   separately when needed. Never fall back from required isolation to host execution.
4. Independent validator executes deployed denial tests under actual identities:
   file/symlink traversal, scorer modification, raw-device access, environment or
   cache leak, unauthorized network and forged role tags. Mocked subprocess tests
   are useful unit tests but do not complete this slice.

### B4 — Strict native evidence adapter (F-04/F-06/F-09/F-10)

1. Keep native commands and tests explicit in a provider manifest; do not force
   every provider through CMake or SST. Record test discovery separately from
   execution. Cache only when all effective code/config/tool/input identities match.
2. Wrap current build/test result handling so required qualification never inherits
   soft-success paths. CTest currently returns passing warnings when tools/build
   directories/XML are unavailable; all skipped tests can also yield `passed=True`.
   Baseline demotion compares failure counts, not the identity of failing tests.
3. A strict task requires actual selected test execution, completion proof and raw
   result preservation. Timeout, exit/XML disagreement, no XML, zero executed
   tests, all-skipped or required-test failure is not success. Developer regression
   attribution may remain a separate report; it cannot erase qualification failures.
4. Validate native-normalized equality on public fixtures, support manifests,
   missing/unsupported channels and units. Never substitute missing power with zero,
   a host compiler for a pinned device compiler, or a constant/mock provider.

### B5 — Immutable evidence and independent decision interface (F-07/F-08)

1. Integrate the six specified data objects: DatasetManifest, AllowedInputManifest,
   ModelSubmission, PredictionBundle, ScoreProfile and ScoreReport. Resolve missing
   authoritative schema details before claiming schema conformance.
2. Preserve native and normalized artifacts, all attempts, status, units, boundary,
   observation operator, time/work coverage, uncertainty, cost and parent identities.
   Use standard hashing/storage/attestation tools; do not invent cryptography.
3. Do not overload generic `completed` with `QUALIFIED`. Keep the execution state
   machine `PLANNED → DISCOVERING → READY → IMPLEMENTING/RUNNING → SUBMITTED →
   VALIDATING → ACCEPTED | NEEDS_REPAIR | BLOCKED | REJECTED` and a separate
   per-output scientific result. Preserve FAILED_MODEL, INVALID_EXPERIMENT,
   UNSUPPORTED_MODEL, BLOCKED_PERMISSION, INSUFFICIENT_OBSERVABILITY,
   INSUFFICIENT_STATISTICAL_EVIDENCE and UNAPPROVED_ACCEPTANCE as source vocabulary.
   The workflow document instead names INSUFFICIENT_ACCEPTANCE_POLICY for missing
   acceptance policy. F-01 must resolve that difference in a reviewed versioned
   contract before authoritative enum emission; this plan chooses no mapping.
   Neither unresolved spelling can yield QUALIFIED.
4. Run deterministic replay and tampering checks with independently constructed
   synthetic oracles. Labels changed under identical allowed inputs leave a seeded
   predictor unchanged, while a nondegenerate score changes. Reject stale hashes,
   direct/derived label leaks, NaN/Inf, missing work, executable payloads and feedback
   beyond the frozen reveal budget. Release decisions must bind to the actual
   validator/scorer identity and immutable policy, not a worker's self-report.

### B6 — Controlled frequency task integration (X-01..X-05, U-01, P-02)

1. X-01 is discovery of real domain controls, joint constraints, readback, units,
   voltage coupling, supported resets and authorization. HBM is a candidate, not
   an assumed independent transfer clock. Record unsupported controls explicitly.
2. X-02 freezes either semantic work/kernel replay or native request policy; token
   forcing is separately labeled. Keep requested and realized operating states
   distinct. Timestamps/trace lengths can leak runtime even after columns are removed.
3. X-03 freezes a feasible randomized blocked design, baseline repeats, pilot versus
   qualification cohorts, sample rule, seed and combination/range holdouts. A 3×3
   grid is only a planning default. Approved numeric limits cannot be chosen after
   observing model residuals.
4. X-04 is independent authorized acquisition with all attempts, work/control checks,
   actual intervals and restoration on normal/error/cancel paths. The packet is not
   permission to change clocks. Keep D4 high-current authority separate.
5. X-05 scores absolute duration/power/energy and compute/transfer/interaction
   contrasts, paired covariance, UQ coverage and score uncertainty. Test additive
   bias with correct slopes, wrong slopes with correct baseline, tied realized
   clocks and omitted work. Never assume global monotonicity, resample trace rows
   as independent runs or use post-reveal warping to hide timing error.
6. Report `same_arch_frequency_intervention`, with fixed-voltage, policy-total or
   measured-state conditioning as appropriate. An operating-point holdout does
   not satisfy architecture transfer; D3 and C0/C1 definitions remain separate.

### B7 — Regression and release handoff (A-01/F-08/P-05)

1. Run affected legacy suites plus new strict-profile tests. Explicitly retain
   legacy behavior tests when the new policy is profile-specific; do not rewrite
   tests merely to make the current implementation green.
2. Verify installed/wheel resources as well as in-tree imports when packaging
   changes. `setup.py` includes selected sibling packages and copies canonical
   resources, so assuming all of `src/` is packaged is incorrect.
3. Have a fresh independent validator reproduce a selected result and designated
   defects with separate privileges. Public unit tests close code-contract gates;
   they do not close hardware, isolation, scientific or blind-release gates.
4. Submit a bounded record: changed paths, before/after behavior, exact commands,
   hashes, counts, raw failures/skips, attempts/cost, artifact locations, unsupported
   cases, validator decision and smallest remaining block. No fabricated calendar,
   omitted failed runs or pending criteria represented as infinite tolerance.

## Existing validation to reuse

Run from `bob/` using the existing environment. These files exist at audit time;
they exercise legacy behavior and must be reviewed before being counted as a
new-spec gate. They do not require provider download merely to read or collect.

| Area | Existing scoped command / test files | What it establishes and does not establish |
|---|---|---|
| Native test parsing, toolchain pins, verifier guard | `.venv/bin/python -m pytest tests/test_ctest_runner.py tests/test_toolchain_preflight.py tests/test_verifier_sandbox.py -q` | Legacy local semantics. In particular it may verify permissive behaviors that Power qualification must exclude. No real provider or identity-separation claim. |
| Dispatch and executor | `.venv/bin/python -m pytest tests/test_dispatch.py tests/test_f006_claude_executor.py tests/test_hermetic_rca_controls.py tests/test_model_escalation.py -q` | Prompt/option/model/retry compatibility. Hermetic flags and role strings are not deployed access control. Review mocked SDK boundaries before running. |
| Execution budgets | `tests/test_per_attempt_cost_cap.py`, `tests/test_budget_enforcement_zero_cost.py`, `tests/test_rca_attempt_budget_caps_at_5.py`, `tests/test_model_escalation_ladder_boundary.py`, `tests/test_spawn_with_retry_unlimited_on_transient.py` | Reuse timeout/cost/attempt fixtures. The last test covers historical unlimited retries, which the new outer packet budget must bound. |
| Native build and GPU evidence | `tests/test_build_verification.py`, `tests/test_cpp_gpu_characterization_harness.py`, `tests/test_cpp_hip_device_dispatch_anticheat.py`, `tests/test_gpu_sandbox.py`, `tests/test_dispatch_coupled_evidence.py` | Existing build/dispatch/snapshot behavior. The GPU sandbox tests explicitly accept host fallback; passing them is not evidence of secured prediction. |
| Artifacts and lineage | `tests/test_f014_evidence_artifacts.py`, `tests/test_f030_evidence_verification.py`, `tests/test_f031_evidence_staleness.py`, `tests/test_ac_provenance.py`, `tests/test_disk_reconciler_records_evidence_artifacts.py` | Software evidence references/intent spans. Add physical identity, exposure and freeze-binding tests separately. |
| Scoped software regression | `tests/test_concurrent_executor_isolation.py`, `tests/test_f118_e2e_interrupt_resume_spec_change.py`, `tests/test_f124_e2e_verification_gates_resume.py` | Existing concurrency/resume behavior; inspect credentials/external processes and use isolated temporary workspaces before running integration suites. |

New checks are specified by behavior in B1–B7 and the shared validation matrix.
Do not execute invented paths such as `power-spec-2/tools/check_release.py` or
claim those upstream tests passed: they are absent in the supplied release.
Discover each selected provider's native tests and required build/environment
before freezing its executable packet.

Executed during this planning audit: the first scoped command above completed
with **70 passed in 1.01s** on 2026-09-21. This is a legacy behavior baseline,
not a Power spec 2 acceptance run. No provider, physical hardware, production
isolation or blind evaluation was executed. The other commands are handoff
instructions, not claims of execution.

## Implementation handoff rules for a smaller model

Read only the current migration index, the assigned source task, its specific
authority excerpts and the files on its allowlist. Never concatenate old specs,
all of `features.yaml`, historical research and downloaded README instructions
into governing context. Before coding, state the concrete input/output contract,
reuse path, expected counterexample and completion level in the task record.

Work one bounded slice at a time. A normal software developer may write public
synthetic fixtures and adapter tests; it may not inspect sealed outcomes, issue
itself a validator credential, change a released scorer/test or widen hardware
scope. Use the discovery/escalation policy to resolve factual gaps autonomously.
Escalate only actual missing authority, unavailable evidence/capability, utility
limits or a contract ambiguity that affects the claim, and continue unrelated
ready tasks. Record a proposed value separately from an approved policy.

Do not report “done” from file existence, agent confidence, a mocked native
command, an empty test set, an exit code alone or a passed mean on selected runs.
Every completion cites executed evidence at the appropriate level and all
remaining limitations. The lower-cost implementer is not its own independent
scientific validator, regardless of how many reviewer agents it spawns.
