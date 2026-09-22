# Generated planning task packets

Generated from `backlog.json` by `maintain_plan.py render`. Do not edit this view.

**Planning only: all 41 source tasks and four local migration tasks remain PLANNED; none is dispatch-ready.**
Read [README](README.md), [Bob migration](BOB_MIGRATION.md), [validation families](VALIDATION.md) and [third-party migration](../../../third_party/POWER_SPEC_2_MIGRATION.md).
Requirements and T-* families are local traceability IDs pending recovery of the original normative registry. Source-table dependencies are reproduced exactly; additional gates do not authorize work.

## Universal claim gates

- selected_region_full_workload_claim (C-02): Every full-workload claimed output composed from selected regions requires C-02, regardless of task ID. Full native runs do not inherit this requirement.
- derivative_or_approximate_inference_claim (U-02): Every claimed output using derivatives or approximate inference requires U-02. Preliminary fitting artifacts may feed U-02 before scientific qualification; split artifact completion from claim acceptance to avoid a K-02/U-02 circular workflow.
- numerical_qualification (Q-01): Every QUALIFIED numerical output requires approved policy. Native operability, synthetic tests and authorized descriptive acquisition do not imply qualification.

## Overview

| Task | Stage | Objective | Source dependencies | Migration prerequisites |
| --- | --- | --- | --- | --- |
| [F-01](#f-01) | D1 | Freeze fixture and governing policies | None | MIG-00 |
| [F-02](#f-02) | D1 | Inventory architecture and implementation fields | F-01 | MIG-00 |
| [F-03](#f-03) | D1 | Qualify harness channels and observation operators | F-01 | MIG-00 |
| [F-04](#f-04) | D1 | Build native providers and open non-IPPM path | F-01 | MIG-00, MIG-02 |
| [F-05](#f-05) | D1 | Capture real single-GPU vLLM workload | F-01, F-03 | MIG-00 |
| [F-06](#f-06) | D1 | Implement batch adapters and evidence views | F-02, F-04, F-05 | MIG-00 |
| [A-01](#a-01) | D1 | Connect existing coding agents to bounded packets | F-01 | MIG-00, MIG-01 |
| [A-02](#a-02) | D1 | Establish independent acquisition and validator identities | F-01, A-01 | MIG-00 |
| [F-07](#f-07) | D1 | Implement trusted preparer and deterministic scorer | A-02, F-03 | MIG-00 |
| [A-03](#a-03) | D1 | Implement discovery and escalation policy | A-01 | MIG-00 |
| [F-09](#f-09) | D1 | Audit kernel/precision coverage and cost preflight | F-04, F-05 | MIG-00 |
| [F-10](#f-10) | D1 | Resolve source/data pins and dependency terms | F-04 | MIG-00 |
| [V-01](#v-01) | D1-reference | Reproduce modern Accel-Sim native case | F-04, F-10 | MIG-00 |
| [V-02](#v-02) | D1-reference | Evaluate AISimulate native fixed configuration | F-04, F-10 | MIG-00 |
| [V-03](#v-03) | D1-reference | Reproduce EnergAIzer supported frequency/power experiment | F-04, F-10 | MIG-00 |
| [V-04](#v-04) | D1-D2 | Check native/adapter equivalence on selected references | F-06, F-07 | MIG-00 |
| [X-01](#x-01) | D1 | Discover clock domains, authority and coupled controls | F-02, F-03, A-02 | MIG-00 |
| [X-02](#x-02) | D1 | Establish frozen-work and native-request replay lanes | F-05, X-01 | MIG-00 |
| [Q-01](#q-01) | D1 | Approve standing measurement/accuracy/automation policies | F-01, F-03, A-03 | MIG-00 |
| [F-08](#f-08) | D1 | Release D1 capability and gap report | F-02, F-03, F-04, F-05, F-06, F-07, F-09, F-10, X-01 | MIG-00 |
| [K-01](#k-01) | D1-D2 | Collect independent action/component characterization | F-03, X-01, A-02 | MIG-00 |
| [K-02](#k-02) | D2a | Fit and qualify model content and uncertainty | K-01, F-06 | MIG-00 |
| [U-01](#u-01) | D1-D2 | Implement joint uncertainty and score diagnostics | F-07 | MIG-00 |
| [P-01](#p-01) | D2a | Predict frozen MI355 workload at controlled operating point | F-06, K-02, U-01 | MIG-00 |
| [X-03](#x-03) | D2a | Freeze randomized clock-intervention design and heldouts | X-02, Q-01, F-07 | MIG-00 |
| [X-04](#x-04) | D2a | Acquire independent frequency trials and sealed outcomes | X-03, A-02 | MIG-00 |
| [X-05](#x-05) | D2a | Score frequency responses and falsify models | X-04, P-01, U-01 | MIG-00 |
| [P-02](#p-02) | D2a | Qualify independent timing-and-power prediction | P-01, Q-01, X-05 | MIG-00 |
| [P-03](#p-03) | D2b | Implement missing runtime control and in-flight-work semantics | P-02 | MIG-00 |
| [P-04](#p-04) | D2b | Validate ordinary PMFW-managed workload | P-03, F-07 | MIG-00 |
| [P-05](#p-05) | D2 | Issue scoped single-GPU qualification | P-02, P-04 | MIG-00 |
| [B-01](#b-01) | D3-setup | Create sealed workload/architecture/exposure cohorts | F-07 | MIG-00 |
| [B-02](#b-02) | D3a | Test new workloads and W-profile ablations | P-05, B-01 | MIG-00 |
| [B-03](#b-03) | D3b | Test withheld architecture and C0/C1 exposure | P-05, B-01 | MIG-00 |
| [B-04](#b-04) | D3c | Test joint workload/architecture shifts | B-02, B-03 | MIG-00 |
| [C-01](#c-01) | cross-cutting | Profile cost and qualify multifidelity estimators | F-04 | MIG-00 |
| [C-02](#c-02) | D1-D2 | Qualify selected-region and full-workload composition | F-09, F-06 | MIG-00 |
| [U-02](#u-02) | cross-cutting | Qualify derivatives and statistical approximations where used | K-02 | MIG-00 |
| [H-01](#h-01) | D4 | Qualify high-current/protection behavior | P-05 | MIG-00 |
| [M-01](#m-01) | D5 | Extend to multi-GPU system | B-04, H-01 | MIG-00 |
| [N-01](#n-01) | D6 | Extend to multiple nodes | M-01 | MIG-00 |
| [MIG-00](#mig-00) | migration | Freeze source intake and recover missing authorities | None | None |
| [MIG-01](#mig-01) | migration | Prepare Bob profile compatibility and downgrade | MIG-00, F-01 | None |
| [MIG-02](#mig-02) | migration | Baseline all third-party assets and legacy lock drift | MIG-00 | None |
| [MIG-03](#mig-03) | migration | Cut over new execution entrypoint with rollback evidence | MIG-01, MIG-02, A-01, A-02, A-03, F-07, F-10, Q-01 | None |

## F-01

**Freeze fixture and governing policies** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-CONTRACT, R-PROVENANCE, R-RELEASE, R-COST.

Source dependencies: None. Migration prerequisites: MIG-00.

Reuse: Existing manifests and confirmed owner decisions.

Implementation steps:

1. Resolve missing authorities and the task/scientific status vocabularies.
2. Freeze exact fixture/workload/output boundaries and distinguish proposed defaults from approved policies.

Observable acceptance:

- Missing normative/exposure definitions remain explicit blockers.
- Malformed/duplicate/nonfinite policies and absent required execution permissions/resources block the affected dispatch; unapproved scientific limits block QUALIFIED, while proposed-policy freeze and authorized discovery/descriptive work remain possible.

Validation: **T-CONTRACT, T-PROVENANCE, T-RELEASE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Recover authority, freeze proposed contracts/fixture/policy split and run strict parser/readiness tests.

Remaining external/input gate: Missing original normative/evidence/schema artifacts and actual approval; neither inherently needs MI355.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): resolved application workspace: versioned contracts and fixture/policy manifests.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: ScoreProfile (proposed, unapproved). Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Contract validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## F-02

**Inventory architecture and implementation fields** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-CONTRACT, R-NATIVE, R-PROVENANCE, R-COST.

Source dependencies: F-01. Migration prerequisites: MIG-00.

Reuse: Existing AMD architecture metadata and native provider configs.

Implementation steps:

1. Inspect approved AMD architecture metadata and native provider configuration.
2. Map every required field and changed mechanism to provenance, consumer and supported/unknown status.

Observable acceptance:

- No invented MI355 configuration or default fills an unknown field.
- Each predicted quantity has a supported mechanism and input provenance or an explicit gap.

Validation: **T-CONTRACT, T-NATIVE, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Inventory approved architecture metadata and native model fields; implement provenance/support matrix.

Remaining external/input gate: MI355 source/collateral and later actual device/firmware discovery; preferred private SST source is not in inspected paths.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): approved SST model/configuration and architecture field registry.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Architecture validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## F-03

**Qualify harness channels and observation operators** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-METROLOGY, R-ACCOUNTING, R-PROVENANCE, R-CONTRACT, R-COST.

Source dependencies: F-01. Migration prerequisites: MIG-00.

Reuse: Existing harness, Perfetto/native parsers.

Implementation steps:

1. Discover existing harness channels and actual native export formats.
2. Qualify physical boundaries, operators, timing, uncertainty, overhead and independence with approved development observations.

Observable acceptance:

- Gaps/resets/saturation and clock misalignment are detected.
- Clean/profile equivalence and observation bandwidth have evidence before waveform claims.

Validation: **T-METROLOGY, T-ACCOUNTING, T-PROVENANCE, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Build observation adapters and synthetic gap/reset/synchronization/integration fixtures around the existing harness.

Remaining external/input gate: Actual channel metrology, independence, profiling overhead and target observation bandwidth require qualified physical evidence.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): existing physical harness and observation/operator adapters.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: DatasetManifest (channel/metrology and clean/profile roles). Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Acquisition validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## F-04

**Build native providers and open non-IPPM path** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-NATIVE, R-COST, R-CONTRACT, R-PROVENANCE.

Source dependencies: F-01. Migration prerequisites: MIG-00, MIG-02.

Reuse: SST native tests; selected Accelergy/HWComponents native examples.

Implementation steps:

1. Inventory SST/native test discovery and run a minimal pinned supported case.
2. Compare Accelergy and HWComponents on one justified subsystem and select an open non-IPPM path.

Observable acceptance:

- Native output, versions, exit codes and skipped/failed tests are retained.
- Successful compilation alone does not claim AMD/MI355 accuracy or native SST integration.

Validation: **T-NATIVE, T-COST, T-CONTRACT, T-PROVENANCE**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local_after_sources): Build/test available CPU native providers now; acquire missing approved SST/open-power sources and run their native examples locally.

Remaining external/input gate: Preferred SST source and Accelergy/HWComponents closure absent here; native build does not require MI355 accuracy evidence.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): third_party adoption manifests and existing native provider build/test paths.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Provider validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## F-05

**Capture real single-GPU vLLM workload** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-WORK, R-METROLOGY, R-PROVENANCE, R-CONTRACT, R-COST.

Source dependencies: F-01, F-03. Migration prerequisites: MIG-00.

Reuse: Existing harness and installed vLLM.

Implementation steps:

1. Freeze actual single-GPU vLLM fixture after residency/support discovery.
2. Capture real tokens, precision/KV/kernel/context behavior and clean/profile equivalence.

Observable acceptance:

- No precision fallback/offload/token omission or synthetic trace is represented as the requested real workload.
- Every failed/partial attempt remains visible with completion evidence.

Validation: **T-WORK, T-METROLOGY, T-PROVENANCE, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (target_acquisition): Prepare exact workload manifests, trace ingestion and completion/token/precision checks using clearly synthetic/public artifacts.

Remaining external/input gate: Actual specified vLLM workload capture and clean/profile equivalence need the configured target or independently acquired matching evidence.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): existing workload harness; approved vLLM capture and workload manifest.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: DatasetManifest (real workload capture). Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Workload validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## F-06

**Implement batch adapters and evidence views** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-ADAPTER, R-CONTRACT, R-ISOLATION, R-ACCOUNTING, R-PROVENANCE, R-COST.

Source dependencies: F-02, F-04, F-05. Migration prerequisites: MIG-00.

Reuse: Native parsers, Perfetto, JSON Schema.

Implementation steps:

1. Reuse native parsers and Perfetto to implement batch normalization.
2. Generate fresh field-allowlisted input artifacts under approved W/C contracts.

Observable acceptance:

- Independent native/normalized comparisons preserve values, units, boundaries and statuses.
- Nested metadata, lengths and label ancestors cannot bypass the approved view.

Validation: **T-ADAPTER, T-CONTRACT, T-ISOLATION, T-ACCOUNTING, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Implement native batch adapters and fresh allowlisted views; compare public native fixtures and reject label ancestry/units/status loss.

Remaining external/input gate: Missing official W/C schemas and real target export format samples; synthetic readiness alone cannot prove production exposure enforcement.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): application provider adapters and approved-view schemas.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: AllowedInputManifest, PredictionBundle (native/normalized adapter representation). Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Adapter validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## A-01

**Connect existing coding agents to bounded packets** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-WORKFLOW, R-PROVENANCE, R-ISOLATION, R-CONTRACT, R-COST.

Source dependencies: F-01. Migration prerequisites: MIG-00, MIG-01.

Reuse: Existing coding-agent executors and CI/job launcher.

Implementation steps:

1. Connect versioned bounded tasks to existing Bob/CI executor.
2. Record exact model/runtime, finite attempts, immutable artifacts and separate validation dispatch.

Observable acceptance:

- Out-of-scope writes or missing authority fail before dispatch.
- Timeout/crash/restart preserves consumed attempts and cannot silently switch models or self-accept.

Validation: **T-WORKFLOW, T-PROVENANCE, T-ISOLATION, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Repair existing packet materialization lifecycle; qualify current installed Bob wheel, exact model profile, bounded retries/state and validation dispatch.

Remaining external/input gate: Eight current packet tests fail; model hardpins and version/package closure need local repair, not MI355.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): bob/src/bob/admitted_packet.py; atomic_packet_planner.py; models.py; orchestrator/claude_executor.py and run_loop.py.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Workflow validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## A-02

**Establish independent acquisition and validator identities** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-ISOLATION, R-PROVENANCE, R-WORKFLOW, R-CONTRACT, R-COST.

Source dependencies: F-01, A-01. Migration prerequisites: MIG-00.

Reuse: Existing IAM, reservations, artifact storage and harness.

Implementation steps:

1. Instantiate acquisition/developer/preparer/predictor/scorer/validator privileges in approved existing infrastructure.
2. Run real denial and authorized positive-control probes from each deployed identity.

Observable acceptance:

- Developer/predictor cannot access labels, scored hardware, scorer policy/signers or shared writable caches.
- Role names or separate conversations cannot satisfy the permission gate.

Validation: **T-ISOLATION, T-PROVENANCE, T-WORKFLOW, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (deployment): Exercise public-canary developer/preparer/predictor/scorer isolation using existing OS/IAM infrastructure.

Remaining external/input gate: This sandbox cannot create the tested network namespace; a capable local host/CI deployment is needed, not necessarily MI355.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): existing IAM/storage/isolation launcher; Bob executor environment and validator jobs.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Security/evidence validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## F-07

**Implement trusted preparer and deterministic scorer** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-SCORE, R-ISOLATION, R-ACCOUNTING, R-PROVENANCE, R-CONTRACT, R-COST.

Source dependencies: A-02, F-03. Migration prerequisites: MIG-00.

Reuse: Standard isolation/attestation and native trace tooling.

Implementation steps:

1. Implement trusted allowlist preparer and immutable deterministic data-only scoring.
2. Freeze prediction/submission identities and implement exact public analytic oracles.

Observable acceptance:

- Hidden-label swap leaves seeded predictions unchanged while nondegenerate scores change.
- Stale predictions, unsafe outputs, malformed samples and missing policies fail with typed nonqualified results.

Validation: **T-SCORE, T-ISOLATION, T-ACCOUNTING, T-PROVENANCE, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Build data-only manifests, preparer, frozen submissions and deterministic scorer with independent synthetic oracle/mutation tests.

Remaining external/input gate: Official schemas, separate deployed identities and approved policy; real physical qualification awaits measured data.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): trusted evaluator/preparer workspace separate from developer and prediction workspace.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: DatasetManifest, AllowedInputManifest, ModelSubmission, PredictionBundle, ScoreProfile, ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Independent scorer validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## A-03

**Implement discovery and escalation policy** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-WORKFLOW, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: A-01. Migration prerequisites: MIG-00.

Reuse: Existing repository/device inventory; approved policy registry.

Implementation steps:

1. Implement discovery-first resolution with evidence-linked uncertainty.
2. Classify permission/utility gaps and apply only reversible approved defaults.

Observable acceptance:

- Known version/capability facts are resolved from tools without repeated owner questions.
- Unknown authorization or calibration facts never become inferred permissions/data.

Validation: **T-WORKFLOW, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Implement discovery-first classification, grouped missing-authority escalation and approved-default behavior.

Remaining external/input gate: Bounded runtime policy/model configuration must be resolved before automated dispatch.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): bob orientation/task-profile policy adapter and discovery records.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Policy validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## F-09

**Audit kernel/precision coverage and cost preflight** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-WORK, R-NATIVE, R-COST, R-CONTRACT, R-PROVENANCE.

Source dependencies: F-04, F-05. Migration prerequisites: MIG-00.

Reuse: Native support manifests and small representative traces.

Implementation steps:

1. Audit actual model operators, dtypes, KV behavior and early/middle/late decode contexts.
2. Run bounded representative native cases to measure runtime/trace/storage cost.

Observable acceptance:

- Unsupported FP8/operator/context coverage blocks affected claims.
- Recorded support denominator includes failed/unsupported cases and measured costs.

Validation: **T-WORK, T-NATIVE, T-COST, T-CONTRACT, T-PROVENANCE**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Audit operator/dtype/context support and measure CPU simulator cost on small representative native traces.

Remaining external/input gate: Actual target FP8/decode/workload coverage and acquisition costs require target capture; no cached generic result fills that gap.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): provider support manifests; workload coverage fixtures and cost reports.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Coverage validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## F-10

**Resolve source/data pins and dependency terms** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-PROVENANCE, R-NATIVE, R-RELEASE, R-CONTRACT, R-COST.

Source dependencies: F-04. Migration prerequisites: MIG-00.

Reuse: Native lockfiles, license tools and reproducible builds.

Implementation steps:

1. Resolve selected source/data/dependency/compiler/runtime pins and full terms closure.
2. Rebuild selected native case from verified inputs and record reproducibility bounds.

Observable acceptance:

- Null/mutable pins and unreviewed model/data/plugins cannot become admitted dependencies.
- New versioned manifests preserve historical locks and dirty-source differences.

Validation: **T-PROVENANCE, T-NATIVE, T-RELEASE, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Freeze source/runtime/wheel/license closure, fresh extraction and portable build/test recipes for selected dependencies.

Remaining external/input gate: Missing libraries/gitlinks/source artifacts require approved acquisition/provisioning, not a GPU.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): third_party/locks; receipts; drampower-6.0.0 and selected upstream checkouts.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Supply-chain validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## V-01

**Reproduce modern Accel-Sim native case** — D1-reference; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-NATIVE, R-PROVENANCE, R-COST, R-CONTRACT, R-TRANSFER.

Source dependencies: F-04, F-10. Migration prerequisites: MIG-00.

Reuse: Public matching Accel-Sim artifact; supported Hopper baseline if needed.

Implementation steps:

1. Find matching public Accel-Sim paper/code/config/data identities.
2. Reproduce one applicable native case, using supported Hopper if B200 artifacts are unavailable.

Observable acceptance:

- Report absolute native versus published results and exact unsupported cells.
- NVIDIA timing result cannot become AMD or power qualification.

Validation: **T-NATIVE, T-PROVENANCE, T-COST, T-CONTRACT, T-TRANSFER**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (reference_artifacts): Prepare selected Accel-Sim CPU reproduction from approved matching public code/config/traces after acquisition.

Remaining external/input gate: Optional matching artifacts are absent; fresh NVIDIA trace capture needs supported NVIDIA hardware, not MI355.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): selected Accel-Sim/AccelWattch native artifact in isolated acquisition/build workspace.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: NVIDIA reproduction validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## V-02

**Evaluate AISimulate native fixed configuration** — D1-reference; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-NATIVE, R-TRANSFER, R-PROVENANCE, R-CONTRACT, R-COST.

Source dependencies: F-04, F-10. Migration prerequisites: MIG-00.

Reuse: Current native estimator, support and measurement snapshots.

Implementation steps:

1. Pin AISimulate native estimator/support/measurement snapshots.
2. Evaluate exact fixed-configuration cells with imported profile exposure recorded.

Observable acceptance:

- Coverage and absolute timing failures are visible per cell.
- Target-profile reuse is never reported as target-free blind transfer.

Validation: **T-NATIVE, T-TRANSFER, T-PROVENANCE, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local_after_sources): Build/evaluate selected native AISimulate estimator on explicit published/development cells and label target-profile exposure.

Remaining external/input gate: Repository/data/runtime closure absent in inspected workspace; no need to wait for MI355 to acquire and evaluate a CPU estimator.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): selected AISimulate native reference workspace and exposure manifest.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: NVIDIA reproduction validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## V-03

**Reproduce EnergAIzer supported frequency/power experiment** — D1-reference; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-NATIVE, R-FREQUENCY, R-CALIBRATION, R-CONTRACT, R-PROVENANCE, R-COST, R-TRANSFER.

Source dependencies: F-04, F-10. Migration prerequisites: MIG-00.

Reuse: Existing native artifact and voltage-frequency data.

Implementation steps:

1. Reproduce a supported EnergAIzer voltage-frequency/power case.
2. Audit decoder/FP8/HBM/control/calibration coverage before extending methodology.

Observable acceptance:

- Native power/timing match has exact artifact/config/data identity and limits.
- Compute-frequency reproduction does not establish independent transfer-domain control or AMD accuracy.

Validation: **T-NATIVE, T-FREQUENCY, T-CALIBRATION, T-CONTRACT, T-PROVENANCE, T-COST, T-TRANSFER**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (reference_artifacts): Reproduce selected EnergAIzer numerical method using matching approved public measurements after acquisition.

Remaining external/input gate: Fresh physical reproduction needs its supported device; imported/public results cannot become blind MI355 evidence.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): selected EnergAIzer native reference workspace.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Power reproduction validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## V-04

**Check native/adapter equivalence on selected references** — D1-D2; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-NATIVE, R-ADAPTER, R-SCORE, R-CONTRACT, R-PROVENANCE, R-COST, R-TRANSFER.

Source dependencies: F-06, F-07. Migration prerequisites: MIG-00.

Reuse: Selected completed native-reference results; not every optional V task.

Implementation steps:

1. Select at least one applicable completed native reference in the task manifest.
2. Compare native/normalized results and independently acquired approved measurements where available.

Observable acceptance:

- Native/adapter discrepancy is measured against the same semantics and operators.
- Unavailable optional reference or hardware cannot be silently substituted with fake evidence.

Validation: **T-NATIVE, T-ADAPTER, T-SCORE, T-CONTRACT, T-PROVENANCE, T-COST, T-TRANSFER**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Compare at least one selected native result against adapter normalization using local public fixtures.

Remaining external/input gate: Fresh physical comparison depends on the selected supported device/evidence, not automatically MI355.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): application adapters and selected native reference result bundles.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: PredictionBundle, ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Independent reproduction validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_native_reference: At least one applicable completed native reference selected explicitly in the task manifest; optional V-01/V-02/V-03 are not all mandatory. Dependency IDs: V-01, V-02, V-03.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## X-01

**Discover clock domains, authority and coupled controls** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-FREQUENCY, R-METROLOGY, R-ISOLATION, R-CONTRACT, R-PROVENANCE, R-COST, R-CONTROL.

Source dependencies: F-02, F-03, A-02. Migration prerequisites: MIG-00.

Reuse: Native device/firmware queries and existing control tools.

Implementation steps:

1. Discover actual device/firmware control/readback domains and requested-versus-effective semantics.
2. Record feasible joint settings, quantization/units, voltage coupling, authority and restoration.

Observable acceptance:

- Soft maxima/tied domains/unsettable telemetry are not represented as independent fixed clocks.
- No generic transfer clock or unsupported clock-setting command is invented.

Validation: **T-FREQUENCY, T-METROLOGY, T-ISOLATION, T-CONTRACT, T-PROVENANCE, T-COST, T-CONTROL**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (target_acquisition): Implement capability records/parser/units and fixtures for tied domains, soft maxima, unsupported/read-only controls.

Remaining external/input gate: Discover actual MI355 domain controls, quantization, joint settings, voltage coupling and authorized restoration on target.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): acquisition control-capability manifest and existing native control/readback tools.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Acquisition/control validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## X-02

**Establish frozen-work and native-request replay lanes** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-WORK, R-FREQUENCY, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: F-05, X-01. Migration prerequisites: MIG-00.

Reuse: Existing runtime controls/traces; reusable microbenchmarks.

Implementation steps:

1. Establish separately named frozen-work and native-request replay contracts.
2. Use an existing qualified replay hook and verify actual token/work trajectories across settings.

Observable acceptance:

- Missing replay support blocks that lane without fabricating equivalence.
- Simulator recomputes timing/service and does not rescale a target-timestamp trace.

Validation: **T-WORK, T-FREQUENCY, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Prepare separately named frozen-work and native-request contracts and replay/work-equivalence checks without fixed timestamp rescaling.

Remaining external/input gate: Actual runtime replay hook and work invariance across supported target settings remain unproven.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): existing vLLM/runtime replay; functional trace and microbenchmark integration.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Workload validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## Q-01

**Approve standing measurement/accuracy/automation policies** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-CONTRACT, R-UQ, R-RELEASE, R-WORKFLOW, R-PROVENANCE, R-COST, R-SCORE.

Source dependencies: F-01, F-03, A-03. Migration prerequisites: MIG-00.

Reuse: Independent pilot statistics and existing owner policies.

Implementation steps:

1. Use independent development pilots and owner utility rules to propose metrology/accuracy/automation policy.
2. Freeze approved finite limits, repetition/coverage rules, reveal budgets and capabilities before qualification.

Observable acceptance:

- Limits are not fitted to the submitted model error.
- Unapproved policy yields descriptive evidence only and cannot emit QUALIFIED.

Validation: **T-CONTRACT, T-UQ, T-RELEASE, T-WORKFLOW, T-PROVENANCE, T-COST, T-SCORE**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Implement policy schemas, proposed/approved distinction, finite feedback/repair/sample rules and approval records.

Remaining external/input gate: Numerical utility approval and independent metrology pilot evidence remain external; do not hold all local development for them.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): policy registry and independently reviewed ScoreProfile/standing-authorization records.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: ScoreProfile (approved only by authorized policy owner). Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Policy/statistics validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## F-08

**Release D1 capability and gap report** — D1; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-RELEASE, R-NATIVE, R-WORK, R-METROLOGY, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: F-02, F-03, F-04, F-05, F-06, F-07, F-09, F-10, X-01. Migration prerequisites: MIG-00.

Reuse: Collected acquisition/native evidence.

Implementation steps:

1. Assemble D1 field/channel/provider/workload/control coverage and failure inventory.
2. Independently reproduce selected native results and publish capability/gap matrix.

Observable acceptance:

- Required gaps and optional references remain separate.
- Local or generic-provider success cannot be promoted to MI355 numerical accuracy.

Validation: **T-RELEASE, T-NATIVE, T-WORK, T-METROLOGY, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Publish measured local capability/gap report with native operability, failed tests and missing-source inventory.

Remaining external/input gate: Full D1 report must incorporate actual target/harness evidence for required branches; local progress cannot close all D1 tasks.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): D1 scoped capability report and immutable evidence index.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Independent release validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## K-01

**Collect independent action/component characterization** — D1-D2; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-CALIBRATION, R-METROLOGY, R-ACCOUNTING, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: F-03, X-01, A-02. Migration prerequisites: MIG-00.

Reuse: Existing compute/transfer benchmarks and harness.

Implementation steps:

1. Acquire approved independent action/component benchmarks over relevant operating coverage.
2. Define baseline ownership and independent calibration lineage.

Observable acceptance:

- Target outcome duplicates and same-boundary double counting are rejected.
- Missing component observability remains a gap rather than inferred truth.

Validation: **T-CALIBRATION, T-METROLOGY, T-ACCOUNTING, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (target_acquisition): Prepare action/work/baseline ownership contracts, calibration ingestion and independent-lineage tests.

Remaining external/input gate: Independent action/component energy and power characterization for the target operating envelope needs physical measurements.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): characterization harness and component action-energy/power tables.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: DatasetManifest (physical_calibration). Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Characterization validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## K-02

**Fit and qualify model content and uncertainty** — D2a; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-CALIBRATION, R-UQ, R-ACCOUNTING, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: K-01, F-06. Migration prerequisites: MIG-00.

Reuse: Selected open estimator and existing statistical libraries.

Implementation steps:

1. Fit selected open estimator with identifiable grouped parameters and residual model.
2. Validate heldout components and shared parameter/discrepancy uncertainty.

Observable acceptance:

- Unidentifiable fits and target-contaminated tables do not qualify.
- Baseline and component uncertainty compose without duplicated energy or independent-copy covariance.

Validation: **T-CALIBRATION, T-UQ, T-ACCOUNTING, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Build fitting, identifiability/grouped parameter, residual and joint uncertainty plumbing using SALib/SciPy where justified and synthetic/reference data.

Remaining external/input gate: Actual AMD coefficients and heldout component qualification await independent approved characterization.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): open power provider model content and established statistical library integration.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: ModelSubmission (parameters, characterization and exposure). Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Power/UQ validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## U-01

**Implement joint uncertainty and score diagnostics** — D1-D2; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-UQ, R-SCORE, R-FREQUENCY, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: F-07. Migration prerequisites: MIG-00.

Reuse: Established statistics/inference libraries.

Implementation steps:

1. Implement joint parameter/observation/score uncertainty with existing statistics tools.
2. Preserve pair/block dependence and report coverage, sharpness and sampling error.

Observable acceptance:

- Paired contrasts include covariance and use independent run/session/device units.
- Confidently wrong or arbitrarily broad intervals fail approved joint criteria.

Validation: **T-UQ, T-SCORE, T-FREQUENCY, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Implement paired covariance, joint samples, coverage/sharpness/subgroup and score-uncertainty oracles on CPU.

Remaining external/input gate: Approved thresholds and physical noise estimates are needed for numerical qualification, not development of the math.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): shared uncertainty representation and deterministic scorer diagnostics.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Statistics validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## P-01

**Predict frozen MI355 workload at controlled operating point** — D2a; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-NATIVE, R-SCORE, R-WORK, R-UQ, R-CONTRACT, R-PROVENANCE, R-COST, R-ADAPTER, R-FREQUENCY, R-CALIBRATION, R-ACCOUNTING.

Source dependencies: F-06, K-02, U-01. Migration prerequisites: MIG-00.

Reuse: Existing SST/compact provider with open power binding.

Implementation steps:

1. Freeze MI355 workload/input view/model/provider at a controlled operating point.
2. Emit native and normalized predictions for all claimed timing/power/energy quantities.

Observable acceptance:

- W/C conditioning and unsupported outputs are explicit before score access.
- Baseline absolute error remains visible even when frequency slopes agree.

Validation: **T-NATIVE, T-SCORE, T-WORK, T-UQ, T-CONTRACT, T-PROVENANCE, T-COST, T-ADAPTER, T-FREQUENCY, T-CALIBRATION, T-ACCOUNTING**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Connect locally built execution/open-power providers; freeze manifests and run supported native/development cases.

Remaining external/input gate: Missing MI355 model content, real workload evidence and independent calibration prevent target prediction qualification.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): selected SST/compact execution provider plus open power binding.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: ModelSubmission, PredictionBundle. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Prediction validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_region_full_workload_claim: Required only when a full-workload claim is composed from selected regions; a genuine full native run does not need this reduction gate. Dependency IDs: C-02.
- derivative_or_approximate_inference_claim: Required only when the claimed result relies on derivatives or approximate inference. Dependency IDs: U-02.
- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## X-03

**Freeze randomized clock-intervention design and heldouts** — D2a; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-FREQUENCY, R-UQ, R-PROVENANCE, R-CONTRACT, R-COST.

Source dependencies: X-02, Q-01, F-07. Migration prerequisites: MIG-00.

Reuse: Established design/statistical tooling and validator harness.

Implementation steps:

1. Freeze feasible compute by independently controllable transfer-domain design or constrained policy manifold.
2. Register blocks/randomization/baseline repeats/holdouts/noncompliance and fixed-n or approved sequential rule.

Observable acceptance:

- No impossible grid, post-score stopping change or discovery-as-blind relabeling.
- Two-level design is not claimed to establish curvature.

Validation: **T-FREQUENCY, T-UQ, T-PROVENANCE, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Build randomization/blocking/holdout/seed registries and test proposed grids and noncompliance policies synthetically.

Remaining external/input gate: Freeze physical levels/sample plan only after actual X-01/X-02 capability and Q-01 policy evidence.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): validator-owned clock experiment plan; seeds and cohort manifests.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: AllowedInputManifest (factor/holdout exposure), ScoreProfile (frozen experiment rules). Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Design validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## X-04

**Acquire independent frequency trials and sealed outcomes** — D2a; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-FREQUENCY, R-WORK, R-METROLOGY, R-ISOLATION, R-CONTRACT, R-PROVENANCE, R-COST, R-CONTROL.

Source dependencies: X-03, A-02. Migration prerequisites: MIG-00.

Reuse: Existing hardware harness and safe native controls.

Implementation steps:

1. Acquire all assigned trials through separately authorized reservation/control harness.
2. Validate achieved states, work, entire observation interval and restoration including failures.

Observable acceptance:

- Every assigned/noncompliant/failed trial appears in the evidence ledger.
- Cleanup failure is retained and prior state restoration independently checked.

Validation: **T-FREQUENCY, T-WORK, T-METROLOGY, T-ISOLATION, T-CONTRACT, T-PROVENANCE, T-COST, T-CONTROL**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (target_acquisition): Implement acquisition attempt lifecycle and restoration/cancellation/error-path tests with labeled synthetic control fixtures.

Remaining external/input gate: Actual independently reserved clock trials, full observation and sealed outcomes require target access and approved controls.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): independent acquisition workspace and sealed raw/outcome storage.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: DatasetManifest (all trial attempts and sealed outcomes). Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Acquisition validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## X-05

**Score frequency responses and falsify models** — D2a; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-FREQUENCY, R-SCORE, R-UQ, R-ACCOUNTING, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: X-04, P-01, U-01. Migration prerequisites: MIG-00.

Reuse: Deterministic scorer and paired statistical methods.

Implementation steps:

1. Score per-point absolutes, paired main effects/interactions, diagnostics and uncertainties.
2. Separate model falsification from invalid work/control/observation experiments.

Observable acceptance:

- Absolute-bias and wrong-slope mutants both fail their own gates.
- Same-realized-clock, zero-output elasticity and correlated-row pseudo-replication are rejected.

Validation: **T-FREQUENCY, T-SCORE, T-UQ, T-ACCOUNTING, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Implement absolute/contrast/interaction/elasticity/uncertainty scoring and model-versus-experiment failure classification.

Remaining external/input gate: Apply frozen scorer to independent X-04 measurements and P-01 predictions before a physical frequency-response claim.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): trusted deterministic scorer and independent scientific validation report.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Independent scientific validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## P-02

**Qualify independent timing-and-power prediction** — D2a; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-SCORE, R-RELEASE, R-ISOLATION, R-FREQUENCY, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: P-01, Q-01, X-05. Migration prerequisites: MIG-00.

Reuse: Same-target references and frozen W0/W1 input views.

Implementation steps:

1. Qualify at least one W0/W1 independent timing-and-power path after definitions/policy are resolved.
2. Combine absolute, frequency and uncertainty evidence with same-target references.

Observable acceptance:

- W3 remains diagnostic and measured target timing cannot be called predicted.
- Each required output independently satisfies approved policy with sufficient evidence.

Validation: **T-SCORE, T-RELEASE, T-ISOLATION, T-FREQUENCY, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Build reporting/gating for independent W0/W1 timing-and-power predictions and diagnostic-only conditioned paths.

Remaining external/input gate: Resolved evidence definitions, target measurements, X-05 and approved accuracy policy required.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): single-GPU D2a qualification report and approved input exposure manifests.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Independent physical validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_region_full_workload_claim: Required only when a full-workload claim is composed from selected regions; a genuine full native run does not need this reduction gate. Dependency IDs: C-02.
- derivative_or_approximate_inference_claim: Required only when the claimed result relies on derivatives or approximate inference. Dependency IDs: U-02.
- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## P-03

**Implement missing runtime control and in-flight-work semantics** — D2b; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-CONTROL, R-NATIVE, R-WORK, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: P-02. Migration prerequisites: MIG-00.

Reuse: Existing SST hooks and project-accessible PMFW models.

Implementation steps:

1. Inspect existing SST runtime hooks before the smallest required causal extension.
2. Track actual work progress through command delays, actual-state changes and gated intervals.

Observable acceptance:

- 100-cycle public oracle completes in 150 ns for the declared frequency transition.
- Gated time advances without work and no thermal solver/new general event engine is introduced.

Validation: **T-CONTROL, T-NATIVE, T-WORK, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local_after_sources): Test piecewise in-flight work/control delays/gating using existing provider hooks; add only the smallest missing hook after source audit.

Remaining external/input gate: Preferred SST source absent; physical PMFW validation is later, and stage dependencies remain intact.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): existing SST or compact provider control/activity hooks.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Control/numerical validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## P-04

**Validate ordinary PMFW-managed workload** — D2b; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-CONTROL, R-SCORE, R-METROLOGY, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: P-03, F-07. Migration prerequisites: MIG-00.

Reuse: Existing harness and approved control behavior.

Implementation steps:

1. Validate ordinary PMFW-managed heldout workload using approved harness/control semantics.
2. Distinguish commanded policy, measured conditional states and predicted states.

Observable acceptance:

- Timing/power/cap operators preserve declared physical boundaries.
- Measured control traces cannot silently change an independent prediction claim.

Validation: **T-CONTROL, T-SCORE, T-METROLOGY, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Implement ordinary-control integration tests and requested/actual/conditioned state accounting on a supported local provider.

Remaining external/input gate: Heldout physical PMFW workload and target cap/operator behavior are target gates.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): ordinary PMFW workload adapter and independent closed-loop validator.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: PredictionBundle, ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Closed-loop validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_region_full_workload_claim: Required only when a full-workload claim is composed from selected regions; a genuine full native run does not need this reduction gate. Dependency IDs: C-02.
- derivative_or_approximate_inference_claim: Required only when the claimed result relies on derivatives or approximate inference. Dependency IDs: U-02.
- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## P-05

**Issue scoped single-GPU qualification** — D2; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-RELEASE, R-SCORE, R-PROVENANCE, R-CONTRACT, R-COST.

Source dependencies: P-02, P-04. Migration prerequisites: MIG-00.

Reuse: Registry and immutable score bundles.

Implementation steps:

1. Combine separately passed D2a and D2b evidence into per-output single-GPU scope.
2. Publish immutable report with all exposure, costs, failed/unsupported domains and reproduction.

Observable acceptance:

- No best-subset aggregate hides a required failing output.
- Neither native operability nor D2a alone closes P-05.

Validation: **T-RELEASE, T-SCORE, T-PROVENANCE, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Implement scoped report aggregation, evidence completeness and independent release-decision interface.

Remaining external/input gate: P-02 and P-04 physical qualification must both close before single-GPU qualification.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): single-GPU release evidence registry.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: ScoreReport (per-output scoped qualification). Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Release validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_region_full_workload_claim: Required only when a full-workload claim is composed from selected regions; a genuine full native run does not need this reduction gate. Dependency IDs: C-02.
- derivative_or_approximate_inference_claim: Required only when the claimed result relies on derivatives or approximate inference. Dependency IDs: U-02.
- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## B-01

**Create sealed workload/architecture/exposure cohorts** — D3-setup; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-TRANSFER, R-ISOLATION, R-PROVENANCE, R-CONTRACT, R-COST.

Source dependencies: F-07. Migration prerequisites: MIG-00.

Reuse: Existing storage and lineage tooling.

Implementation steps:

1. Create sealed grouped workload/architecture/exposure cohorts with permitted ancestry.
2. Audit duplicates and imported databases and freeze finite reveal budget.

Observable acceptance:

- Related runs/windows/frequency pairs cannot straddle prohibited split boundaries.
- Public reproduction data never become private gold holdouts.

Validation: **T-TRANSFER, T-ISOLATION, T-PROVENANCE, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Implement grouped split/seal/duplicate/imported-profile/exposure/reveal accounting using public canary data.

Remaining external/input gate: Actual protected datasets and deployed independent privileges required before any blind cohort claim.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): trusted dataset registry; split manifests and exposure ledger.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: DatasetManifest (grouped split/seal roles), AllowedInputManifest. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Dataset validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## B-02

**Test new workloads and W-profile ablations** — D3a; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-TRANSFER, R-SCORE, R-UQ, R-WORK, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: P-05, B-01. Migration prerequisites: MIG-00.

Reuse: Existing providers and fresh harness evidence.

Implementation steps:

1. Evaluate genuinely new workloads under frozen W-profile ablations.
2. Score all attempts and uncertainty using fresh independent harness evidence.

Observable acceptance:

- New workload claim does not imply a new architecture.
- Measured work/timing conditioning and failures remain visible per ablation.

Validation: **T-TRANSFER, T-SCORE, T-UQ, T-WORK, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Build workload-ablation evaluation pipeline and test synthetic/new public workload handling.

Remaining external/input gate: Fresh genuinely heldout target workloads and completed P-05 required for D3a.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): D3a blind workload evaluation bundles.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: ModelSubmission, PredictionBundle, ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Blind scientific validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_region_full_workload_claim: Required only when a full-workload claim is composed from selected regions; a genuine full native run does not need this reduction gate. Dependency IDs: C-02.
- derivative_or_approximate_inference_claim: Required only when the claimed result relies on derivatives or approximate inference. Dependency IDs: U-02.
- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## B-03

**Test withheld architecture and C0/C1 exposure** — D3b; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-TRANSFER, R-NATIVE, R-SCORE, R-UQ, R-CONTRACT, R-PROVENANCE, R-COST, R-CALIBRATION.

Source dependencies: P-05, B-01. Migration prerequisites: MIG-00.

Reuse: Qualified native providers and actual architecture collateral.

Implementation steps:

1. Withhold a genuinely distinct architecture and inspect changed mechanisms.
2. Evaluate defined C0/C1 exposure with actual target collateral and matched information.

Observable acceptance:

- Same-card clock changes cannot satisfy architecture transfer.
- Absent target mechanisms or illicit target characterization block affected claims.

Validation: **T-TRANSFER, T-NATIVE, T-SCORE, T-UQ, T-CONTRACT, T-PROVENANCE, T-COST, T-CALIBRATION**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (other_architecture): Implement mechanism-delta/exposure/split logic with distinct public architecture fixtures.

Remaining external/input gate: An actually different withheld architecture and approved C0/C1 collateral/evidence required; one MI355 does not close D3b.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): D3b architecture transfer provider configurations and sealed evaluation.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: ModelSubmission, PredictionBundle, ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Blind architecture validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_region_full_workload_claim: Required only when a full-workload claim is composed from selected regions; a genuine full native run does not need this reduction gate. Dependency IDs: C-02.
- derivative_or_approximate_inference_claim: Required only when the claimed result relies on derivatives or approximate inference. Dependency IDs: U-02.
- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## B-04

**Test joint workload/architecture shifts** — D3c; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-TRANSFER, R-SCORE, R-UQ, R-COST, R-CONTRACT, R-PROVENANCE.

Source dependencies: B-02, B-03. Migration prerequisites: MIG-00.

Reuse: Matched-information existing baselines.

Implementation steps:

1. Hold out both architecture and workload axes with matched-information baselines.
2. Publish joint-shift performance/uncertainty/cost and all attempted cases.

Observable acceptance:

- Separate single-axis successes cannot substitute for joint holdout evidence.
- Data lineage and imported profile exposure remain enforced.

Validation: **T-TRANSFER, T-SCORE, T-UQ, T-COST, T-CONTRACT, T-PROVENANCE**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (other_architecture): Implement joint-axis cohort validation and matched-information baseline accounting.

Remaining external/input gate: Both heldout workloads and architecture evidence plus B-02/B-03 required.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): D3c joint-shift sealed evaluation.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: ModelSubmission, PredictionBundle, ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Blind scientific validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_region_full_workload_claim: Required only when a full-workload claim is composed from selected regions; a genuine full native run does not need this reduction gate. Dependency IDs: C-02.
- derivative_or_approximate_inference_claim: Required only when the claimed result relies on derivatives or approximate inference. Dependency IDs: U-02.
- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## C-01

**Profile cost and qualify multifidelity estimators** — cross-cutting; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-COST, R-UQ, R-NATIVE, R-CONTRACT, R-PROVENANCE.

Source dependencies: F-04. Migration prerequisites: MIG-00.

Reuse: Native profilers and established multifidelity libraries.

Implementation steps:

1. Measure native/adapted costs across representative fidelity levels.
2. Validate any chosen multifidelity estimator with explicit shared discrepancy.

Observable acceptance:

- Cost estimates come from executed bounded workloads.
- Correlated model errors are not treated as independent additional evidence.

Validation: **T-COST, T-UQ, T-NATIVE, T-CONTRACT, T-PROVENANCE**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Measure available CPU native simulator/runtime/storage cost; test selected multifidelity discrepancy accounting.

Remaining external/input gate: Representative target-trace inputs and approved error/cost policy needed for target-specific claims.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): native profiler and selected existing multifidelity/statistics integration.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Numerical/UQ validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## C-02

**Qualify selected-region and full-workload composition** — D1-D2; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-COST, R-WORK, R-ACCOUNTING, R-SCORE, R-CONTRACT, R-PROVENANCE.

Source dependencies: F-09, F-06. Migration prerequisites: MIG-00.

Reuse: Native layer/context selection and compact provider.

Implementation steps:

1. Select representative regions covering prefill and early/middle/late decode.
2. Independently compare composed full-workload prediction against full native/physical evidence.

Observable acceptance:

- Target-runtime scaling and unexplained omitted work fail.
- Full-workload claim from selected regions remains blocked until reconstruction error qualifies.

Validation: **T-COST, T-WORK, T-ACCOUNTING, T-SCORE, T-CONTRACT, T-PROVENANCE**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (hybrid): Implement weighted selected-region composition, coverage/conservation and independent reconstruction fixtures.

Remaining external/input gate: Full versus selected-workload evidence across real contexts required before composed full-workload claims.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): selected-region extraction and full-workload composition adapter.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Reduction validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## U-02

**Qualify derivatives and statistical approximations where used** — cross-cutting; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-UQ, R-CALIBRATION, R-CONTROL, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: K-02. Migration prerequisites: MIG-00.

Reuse: Existing sensitivities/AD/inference tools.

Implementation steps:

1. For actually used derivatives/inference, register smoothness/event/discrepancy assumptions.
2. Run independent directional/finite-difference and posterior diagnostics.

Observable acceptance:

- Nonsmooth transitions are not assumed differentiable.
- Approximation/sampling failures block dependent numerical claims only.

Validation: **T-UQ, T-CALIBRATION, T-CONTROL, T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Run directional/finite-difference and chosen inference convergence diagnostics with known synthetic references when those methods are used.

Remaining external/input gate: Actual model event/discrepancy assumptions and approved numerical policy must hold for qualified results.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): existing AD/sensitivity/inference library integration.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Native artifacts where applicable; immutable attempt manifest, raw test results, cost/support/failure record and independent validator report. Resolve exact output paths before admission.

Validator: Math validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## H-01

**Qualify high-current/protection behavior** — D4; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-CONTROL, R-METROLOGY, R-RELEASE, R-CONTRACT, R-PROVENANCE, R-COST, R-ACCOUNTING.

Source dependencies: P-05. Migration prerequisites: MIG-00.

Reuse: Available hardware and open/project reference models.

Implementation steps:

1. Obtain separate D4 authority and independent current/protection measurement feasibility.
2. Qualify event versus waveform outputs against matching physical bandwidth/boundary.

Observable acceptance:

- Ordinary D2b data cannot qualify high-current waveforms.
- No thermal expansion, protection bypass or unauthorized experiment.

Validation: **T-CONTROL, T-METROLOGY, T-RELEASE, T-CONTRACT, T-PROVENANCE, T-COST, T-ACCOUNTING**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (later_physical): Prepare only public safety/state/failure and event-versus-waveform contracts; retain later-stage scope.

Remaining external/input gate: Separate D4 authorization, adequate sensors/protection reference and physical target experiments after P-05.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): authorized D4 harness and open/project electrical/protection reference models.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: DatasetManifest, PredictionBundle, ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Electrical/protection validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_region_full_workload_claim: Required only when a full-workload claim is composed from selected regions; a genuine full native run does not need this reduction gate. Dependency IDs: C-02.
- derivative_or_approximate_inference_claim: Required only when the claimed result relies on derivatives or approximate inference. Dependency IDs: U-02.
- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## M-01

**Extend to multi-GPU system** — D5; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-ACCOUNTING, R-TRANSFER, R-UQ, R-NATIVE, R-CONTRACT, R-PROVENANCE, R-COST, R-RELEASE.

Source dependencies: B-04, H-01. Migration prerequisites: MIG-00.

Reuse: Existing serving/communication frameworks after overlap audit.

Implementation steps:

1. After B-04 and H-01, audit existing serving/communication infrastructure.
2. Implement only missing multi-GPU communication/overlap and per-device/system accounting.

Observable acceptance:

- Communication/computation overlap is not double counted.
- System and per-device outputs carry joint uncertainty and matched boundaries.

Validation: **T-ACCOUNTING, T-TRANSFER, T-UQ, T-NATIVE, T-CONTRACT, T-PROVENANCE, T-COST, T-RELEASE**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (later_distributed): Audit reusable communication/overlap mechanisms and accounting test plans after preceding stage choices.

Remaining external/input gate: Multiple appropriate GPUs plus B-04 and H-01; current MCCL native path remains stalled/unqualified.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): existing multi-GPU serving/collective/simulation providers.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: DatasetManifest, PredictionBundle, ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Distributed validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_region_full_workload_claim: Required only when a full-workload claim is composed from selected regions; a genuine full native run does not need this reduction gate. Dependency IDs: C-02.
- derivative_or_approximate_inference_claim: Required only when the claimed result relies on derivatives or approximate inference. Dependency IDs: U-02.
- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## N-01

**Extend to multiple nodes** — D6; PLANNED; dispatch-ready: false.

Source: `power-spec-2/implementation_plan.md#backlog`. Requirements: R-SCOPE, R-ACCOUNTING, R-TRANSFER, R-UQ, R-NATIVE, R-CONTRACT, R-PROVENANCE, R-COST, R-RELEASE.

Source dependencies: M-01. Migration prerequisites: MIG-00.

Reuse: Existing transport/collective simulators and harness.

Implementation steps:

1. After M-01, reuse existing transport/collective simulators for multinode behavior.
2. Validate end-to-end workload/network accounting against matched physical boundaries.

Observable acceptance:

- Network/collective delay and communication energy are accounted exactly once.
- Single-node success does not qualify multinode behavior.

Validation: **T-ACCOUNTING, T-TRANSFER, T-UQ, T-NATIVE, T-CONTRACT, T-PROVENANCE, T-COST, T-RELEASE**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (later_distributed): Plan reusable transport/collective interfaces and network accounting tests after M-01.

Remaining external/input gate: Multiple nodes/network evidence and completed M-01; a single MI355 host cannot close D6.

Native/public tests: Discover and record existing native/public tests before adding adapters. Commands, cwd, collection and skip/failure counts must be frozen in the admitted child packet; missing command is a dispatch blocker.

Implementation surfaces (resolve exact child paths before admission): existing multinode transport/collective/harness integration.

Input access: Current spec and task-scoped approved public/development artifacts only; separate sealed/raw authority for validator roles.

Outputs: Known v0.4.1 object types: DatasetManifest, PredictionBundle, ScoreReport. Resolve missing authoritative schema details and exact output paths before admission; do not substitute ad hoc envelopes. Also retain native artifacts, immutable attempts, raw tests, cost/support/failure record and independent validator report.

Validator: Distributed validator. Acceptance level: Independent evidence for the declared scope; local synthetic checks alone never qualify physical accuracy.

Repair/resources: Must bind approved finite attempts/resources/reveal budget before admission; no numeric budget or authority granted by this planning record.

Conditional and blocked gates:

- selected_region_full_workload_claim: Required only when a full-workload claim is composed from selected regions; a genuine full native run does not need this reduction gate. Dependency IDs: C-02.
- derivative_or_approximate_inference_claim: Required only when the claimed result relies on derivatives or approximate inference. Dependency IDs: U-02.
- numerical_qualification: Approved policy required to qualify, not to collect authorized descriptive/development evidence. Dependency IDs: Q-01.
- Missing normative/exposure/policy definitions for dependent claims; do not infer from legacy specification.

## MIG-00

**Freeze source intake and recover missing authorities** — migration; PLANNED; dispatch-ready: false.

Source: `local_migration_plan_not_official_backlog`. Requirements: R-SCOPE, R-CONTRACT, R-PROVENANCE, R-COST.

Source dependencies: None. Migration prerequisites: None.

Reuse: Existing repository metadata, source custody, Bob executor and local checks.

Implementation steps:

1. Capture parent/Bob/submodule identities and preserve dirty/untracked metadata without reading sealed contents.
2. Locate complete v0.4.1 original release and compare official backlog/schemas to this projection.
3. Resolve real application root and assign missing artifacts to source custodian.

Observable acceptance:

- Nine source hashes and known missing authorities remain explicit.
- New spec instructions cannot silently fall back to old thermal/factory requirements.
- Recovered definitions are independently reconciled before dependent dispatch.
- An inventory-only MIG-00 may be accepted with unresolved source gaps recorded; downstream discovery remains possible, while each schema/qualification task separately requires its missing authorities.

Validation: **T-CONTRACT, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Freeze source snapshot and discovered current application baseline; reconcile missing authorities without inventing them.

Remaining external/input gate: Complete original contract bundle/source custodian; inventory acceptance may retain explicit gaps.

Native/public tests: Use maintain_plan.py for plan structure only; affected Bob/native/deployed tests remain separate gates described in the migration and validation documents.

Implementation surfaces (resolve exact child paths before admission): bob/docs/power-spec-2 and approved source registry.

Input access: Read-only approved repository metadata; no sealed label or credential content.

Outputs: Versioned inventory/contract/cutover artifacts with hashes and actual command receipts; resolve bounded child output paths before runtime changes.

Validator: Independent migration reviewer. Acceptance level: Migration/workflow acceptance only; no physical numerical qualification.

Repair/resources: Bind finite approved task resource/attempt/reveal policy before dispatch; no execution authorization in this plan.

Conditional and blocked gates:

- Source/policy/principal availability gates apply only to dependent work.

## MIG-01

**Prepare Bob profile compatibility and downgrade** — migration; PLANNED; dispatch-ready: false.

Source: `local_migration_plan_not_official_backlog`. Requirements: R-SCOPE, R-WORKFLOW, R-CONTRACT, R-ISOLATION, R-PROVENANCE, R-COST.

Source dependencies: MIG-00, F-01. Migration prerequisites: None.

Reuse: Existing repository metadata, source custody, Bob executor and local checks.

Implementation steps:

1. Inventory planner/model aliases/packet schema/DB/readiness/verification surfaces in BOB_MIGRATION.md.
2. Define additive spec2 profile and exact executor model identity with finite policy and legacy namespace isolation.
3. Create public contract fixtures and compatibility tests before A-01 runtime wiring.

Observable acceptance:

- New profile refuses absent authority/model/budget while generic Bob regressions remain intact.
- Old packet receipts cannot confer new acceptance.
- No production/scorer credentials enter developer environments.

Validation: **T-WORKFLOW, T-CONTRACT, T-ISOLATION, T-PROVENANCE, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Fix current Bob packet lifecycle, resolve model hardpins and preserve generic compatibility under scoped policy.

Remaining external/input gate: Observed public regressions and installed dependency closure are local work; no MI355 requirement.

Native/public tests: Use maintain_plan.py for plan structure only; affected Bob/native/deployed tests remain separate gates described in the migration and validation documents.

Implementation surfaces (resolve exact child paths before admission): bob/src/bob; bob/bob_build.env; bob/tests and profile/CLI documentation.

Input access: Read-only approved repository metadata; no sealed label or credential content.

Outputs: Versioned inventory/contract/cutover artifacts with hashes and actual command receipts; resolve bounded child output paths before runtime changes.

Validator: Independent migration reviewer. Acceptance level: Migration/workflow acceptance only; no physical numerical qualification.

Repair/resources: Bind finite approved task resource/attempt/reveal policy before dispatch; no execution authorization in this plan.

Conditional and blocked gates:

- Source/policy/principal availability gates apply only to dependent work.

## MIG-02

**Baseline all third-party assets and legacy lock drift** — migration; PLANNED; dispatch-ready: false.

Source: `local_migration_plan_not_official_backlog`. Requirements: R-SCOPE, R-NATIVE, R-PROVENANCE, R-COST, R-CONTRACT.

Source dependencies: MIG-00. Migration prerequisites: None.

Reuse: Existing repository metadata, source custody, Bob executor and local checks.

Implementation steps:

1. Inventory every top-level third_party directory using disposition table.
2. Capture existing lock verification failures separately from planned README drift.
3. Select bounded native reuse candidates and plan fresh worktrees and manifests.

Observable acceptance:

- Pre-existing dirty MGPUSim go.sum and old receipts remain unchanged.
- Old source pins are discovery inputs, not automatic spec2 qualification.
- No blanket fetch/build of every candidate or mandatory helper rewrite.

Validation: **T-NATIVE, T-PROVENANCE, T-COST, T-CONTRACT**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (local): Rebuild selected retained dependencies from fresh verified inputs and record fail/skip/support boundaries.

Remaining external/input gate: Missing packages/sources are local acquisition/provisioning gaps, not target-device blockers.

Native/public tests: Use maintain_plan.py for plan structure only; affected Bob/native/deployed tests remain separate gates described in the migration and validation documents.

Implementation surfaces (resolve exact child paths before admission): third_party/POWER_SPEC_2_MIGRATION.md; locks and selected native source metadata.

Input access: Read-only approved repository metadata; no sealed label or credential content.

Outputs: Versioned inventory/contract/cutover artifacts with hashes and actual command receipts; resolve bounded child output paths before runtime changes.

Validator: Independent migration reviewer. Acceptance level: Migration/workflow acceptance only; no physical numerical qualification.

Repair/resources: Bind finite approved task resource/attempt/reveal policy before dispatch; no execution authorization in this plan.

Conditional and blocked gates:

- Source/policy/principal availability gates apply only to dependent work.

## MIG-03

**Cut over new execution entrypoint with rollback evidence** — migration; PLANNED; dispatch-ready: false.

Source: `local_migration_plan_not_official_backlog`. Requirements: R-SCOPE, R-WORKFLOW, R-RELEASE, R-PROVENANCE, R-ISOLATION, R-CONTRACT, R-COST.

Source dependencies: MIG-01, MIG-02, A-01, A-02, A-03, F-07, F-10, Q-01. Migration prerequisites: None.

Reuse: Existing repository metadata, source custody, Bob executor and local checks.

Implementation steps:

1. Validate new project namespace, resolved task contracts and production boundary tests.
2. Update active README/profile/restore/handoff references and maintain read-only legacy crosswalk.
3. Rehearse rollback on disposable state and record Bob commit plus parent gitlink binding.

Observable acceptance:

- No old DF/F-R10/PPAT parent status is imported as spec2 completion.
- Default new dispatch selects only reviewed spec2 policy and exact model while rollback preserves all attempts.
- Cutover certifies workflow readiness only, not D2-D6 scientific completion.

Validation: **T-WORKFLOW, T-RELEASE, T-PROVENANCE, T-ISOLATION, T-CONTRACT, T-COST**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).

Before MI355 (deployment): Rehearse clean install/entrypoint/manifest/rollback and package target handoff using a disposable local environment.

Remaining external/input gate: Real independent identity deployment and approval gates; cutover does not require fabricated physical qualification.

Native/public tests: Use maintain_plan.py for plan structure only; affected Bob/native/deployed tests remain separate gates described in the migration and validation documents.

Implementation surfaces (resolve exact child paths before admission): Bob/new project entrypoints; third_party manifests and root RESUME/.resume follow-up surfaces.

Input access: Read-only approved repository metadata; no sealed label or credential content.

Outputs: Versioned inventory/contract/cutover artifacts with hashes and actual command receipts; resolve bounded child output paths before runtime changes.

Validator: Independent migration reviewer. Acceptance level: Migration/workflow acceptance only; no physical numerical qualification.

Repair/resources: Bind finite approved task resource/attempt/reveal policy before dispatch; no execution authorization in this plan.

Conditional and blocked gates:

- Source/policy/principal availability gates apply only to dependent work.
