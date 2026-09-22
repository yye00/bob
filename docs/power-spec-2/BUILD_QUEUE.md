# Local Bob implementation queue

Generated from [local-build-queue.json](local-build-queue.json). Read [how to run this queue](BOB_LOCAL_BUILD_QUEUE.md) first.

**26 software slices; local execution status grants no Bob dispatch or scientific acceptance.** LOCAL_DONE means the documented public software scope passed local checks; PARTIAL retains unresolved scope. APP denotes the application root selected in S00, never Bob core. Local prerequisites do not replace canonical scientific dependencies or qualification gates. Integration dependencies apply when binding standalone components to final app contracts. D00/D02 prerequisites mean the exact dependency subset consumed, not every package candidate.

| Slice | Status | Objective | Local prerequisites | Explicit external gates |
| --- | --- | --- | --- | --- |
| [B00](#b00) | LOCAL_DONE | Repair and verify Bob entrypoints | None | bounded_bootstrap |
| [B01](#b01) | LOCAL_DONE | Repair admitted-packet custody lifecycle | B00 | bounded_bootstrap |
| [B02](#b02) | LOCAL_DONE | Add scoped downgraded-model and finite-budget profile | B00 | bounded_bootstrap, selected_model |
| [B03](#b03) | LOCAL_DONE | Resolve executor regressions and submission lifecycle | B01, B02 | bounded_bootstrap |
| [D00](#d00) | PARTIAL | Prepare selected dependency closure and acquisition recipes | None | artifact_network |
| [D01](#d01) | LOCAL_DONE | Construct clean portable Bob environment | B00, D00 | artifact_network |
| [D02](#d02) | LOCAL_DONE | Freeze application numerical/test environment | D00 | artifact_network |
| [D03](#d03) | LOCAL_DONE | Build minimal Accelergy/HWComponents comparison | D00 | artifact_network |
| [D04](#d04) | BLOCKED_OWNER | Build SST Core and only required Elements | D00 | artifact_network, owner_sst_version |
| [D05](#d05) | BLOCKED_OWNER | Audit and run owner AMD SST native model | D04 | owner_sst |
| [D06](#d06) | LOCAL_DONE | Prepare Perfetto and observation import | D00 | artifact_network |
| [D07](#d07) | BLOCKED_OWNER | Complete AMD SMI and profiler build prerequisites | D00 | artifact_network, target_platform |
| [D08](#d08) | LOCAL_DONE | Turn existing native results into optional adapter fixtures | D00 | app_workspace |
| [D09](#d09) | LOCAL_DONE | Reproduce a CPU reference for V-04 selection | D00 | artifact_network, reference_data |
| [D10](#d10) | BLOCKED_OWNER | Prepare vLLM workload and compile-only target bundle | D00 | artifact_network, target_platform, workload_identity |
| [S00](#s00) | PARTIAL | Recover authority and create spec-2 application workspace | None | complete_contracts, app_workspace |
| [S01](#s01) | PARTIAL | Implement strict data contracts and allowed-input projections | S00, D02 | Shared dispatch requirements |
| [S02](#s02) | LOCAL_DONE | Implement immutable submission, provenance and attempt ledger | S01, B03 | Shared dispatch requirements |
| [S03](#s03) | PLANNED | Implement deterministic observation and absolute scoring math | D02 | Shared dispatch requirements |
| [S04](#s04) | PLANNED | Implement paired clock-response and interaction scoring | S03 | Shared dispatch requirements |
| [S05](#s05) | LOCAL_DONE | Implement UQ, calibration and reduction software fixtures | S03, D02 | Shared dispatch requirements |
| [S06](#s06) | PLANNED | Implement control protocol and trial scheduling replay | None | Shared dispatch requirements |
| [S07](#s07) | BLOCKED_OWNER | Bind open power actions to native execution | S01, D03, D05 | owner_sst |
| [R00](#r00) | BLOCKED_OWNER | Qualify local deployed role separation | B03, D01, S02 | capable_isolation_host |
| [R01](#r01) | BLOCKED_OWNER | Run local synthetic end-to-end software rehearsal | B03, D01, D02, S02, S03, S04, S05, S06, R00 | selected_model |
| [R02](#r02) | BLOCKED_OWNER | Assemble and rehearse MI355 handoff | D01, D02, D07, D10, R01 | target_platform |

## Shared dispatch requirements

- Resolve actual base/input hashes, exact output allowlist and acceptance selector before one child is admitted.
- After bootstrap, use healthy Bob profile and immutable independently validated submission; no unrestricted generic loop.
- Select exact model and positive finite max_cost_usd; limit below is a proposed ceiling, not paid-call authorization.
- Acquire dependencies outside implementer/predictor sandbox; build/test offline after custody checks.
- Split broad recipe/environment/provider work into one observable child per attempt; propagate parent coverage and limits.
- Owner 2026-09-22 authorizes sequential direct Codex public implementation while Bob is unfunded. Track local evidence without Bob authorship, dispatch authority or independent acceptance; do not relaunch campaigns.

## External gates

- **bounded_bootstrap:** Use an independently bounded public maintenance route for initial Bob repairs; broken admitted path cannot authorize its own repair. If no healthy Bob route exists, explicitly record direct maintenance exception rather than fabricate a Bob run.
- **selected_model:** Exact downgraded model ID and finite cost allowance selected at implementation dispatch, then verified at actual call site.
- **artifact_network:** Satisfied for this session by owner instruction 2026-09-22: network-enabled acquisition authorized. Retain per-artifact origin, hashes and actual transfer results; availability is not dependency admission.
- **owner_sst_version:** Owner AMD model compatibility declaration is needed before choosing SST versions; generic discovery can proceed.
- **owner_sst:** Actual owner-approved AMD model source/config/native fixtures.
- **target_platform:** Exact target OS/CPU/ABI/driver-runtime is required for target-specific binaries and images. Host native builds and portable source recipes can proceed with the host ABI recorded; mark target compatibility pending.
- **app_workspace:** Exact new application root and write allowlist resolved, preserving old baseline.
- **reference_data:** Pinned published code/config/measurements with complete external-data hashes and exposure labels.
- **workload_identity:** Authoritative exact model/precision/tokenizer/KV/request definition and selected assets.
- **complete_contracts:** Complete authoritative schemas/evidence profiles or explicit approved disposition of missing definitions.
- **capable_isolation_host:** Local/CI environment that permits the required actual separate identities and namespaces; denied here.

## B00

**Repair and verify Bob entrypoints**

Canonical parents: MIG-01, A-01. Asset IDs: bob.

Software prerequisites: None. Explicit external gates: bounded_bootstrap.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- bob/pyproject.toml packaging configuration and tools package mapping
- bob/tests: installed/editable CLI regression fixtures

Implementation:

1. Reproduce console entrypoint failure from workspace root and Bob cwd: tools.spec_quality_score is absent from editable resolution
2. Inspect actual editable metadata versus current wheel contents before changing packaging
3. Repair the supported install path and rebuild fresh wheel; avoid application import paths as a workaround

Validation:

- Fresh wheel and editable bob --version/--help run outside checkout
- No inherited PYTHONPATH, editable .pth from another installation or source cwd dependency
- 13 selected imports and four packaged resources from existing receipt still pass

Acceptance limit: CLI usability only; no model call or admitted task acceptance.

Local status: **LOCAL_DONE** — Documented local bootstrap scope tested; deployed isolation and funded live execution remain R00/R01.

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-21/bootstrap/README.md). Direct Codex work; not Bob-authored or independently accepted.

## B01

**Repair admitted-packet custody lifecycle**

Canonical parents: MIG-01, A-01, A-03. Asset IDs: bob.

Software prerequisites: B00. Explicit external gates: bounded_bootstrap.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- bob/src/bob/admitted_packet.py and direct loader/custody callers
- bob/tests/test_admitted_packet.py plus scoped lifecycle regressions

Implementation:

1. Supply authenticated workspace/materialization records at actual construction after correct lifecycle ordering
2. Implement real assert_materialized_target_custody and verify callers
3. Preserve clean-base-before-target-creation and resume custody; never use dummy defaults/remove required fields

Validation:

- All 39 existing admitted-packet cases pass, retaining the eight baseline failures as regression identifiers
- Negative changed hash/inode/owner/mode/link and path traversal tests
- Creation/crash/resume states never accept stale or unowned targets

Acceptance limit: Local custody software; operating-system access isolation remains separately deployed.

Local status: **LOCAL_DONE** — Documented local bootstrap scope tested; deployed isolation and funded live execution remain R00/R01.

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-21/bootstrap/README.md). Direct Codex work; not Bob-authored or independently accepted.

## B02

**Add scoped downgraded-model and finite-budget profile**

Canonical parents: MIG-01, A-01, A-03. Asset IDs: bob.

Software prerequisites: B00. Explicit external gates: bounded_bootstrap, selected_model.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- bob/src/bob/atomic_packet_planner.py profile plumbing and actual executor integration
- bob/tests/test_atomic_packet_planner.py and profile call-path tests

Implementation:

1. Keep legacy PACKET_MODEL behavior compatible; add explicit spec-2 profile rather than change all projects
2. Bind exact chosen model to planner/compiler/implementer/reviewer and actual SDK calls
3. Replace unbounded campaign behavior with enforced wall/turn/cost/repair ledgers; expose no secret values
4. Do not source historical bob_build.env as the new campaign default
5. Cover all three hard-pinned layers: atomic packet planning, admitted execution profile validation/capability labels, and run-loop implementer/writer options. Audit stream_query transport retries so failed sessions cannot obtain a fresh uncharged budget.

Validation:

- Existing 68 atomic-planner cases plus new profile cases
- Stub provider records actual dispatched model and finite settings
- Wrong resolved model, absent cost limit, exhausted retry and timeout reject
- Legacy alias cannot silently override downgrade
- Inject billable transport interruption: every attempted session must count toward total cost/turn/repair limits; disabling retries in the child environment alone does not alter a parent-side retry loop.

Acceptance limit: Mocked provider checks prove plumbing; chosen real endpoint needs one bounded public preflight before campaign.

Local status: **LOCAL_DONE** — Documented local bootstrap scope tested; deployed isolation and funded live execution remain R00/R01.

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/bob-provider-errors/README.md). Direct Codex work; not Bob-authored or independently accepted.

## B03

**Resolve executor regressions and submission lifecycle**

Canonical parents: MIG-01, A-01, A-03. Asset IDs: bob.

Software prerequisites: B01, B02. Explicit external gates: bounded_bootstrap.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- bob executor cleanup/hermetic MCP implementation and affected seven-file test group
- Public bounded task submission integration fixture

Implementation:

1. Reconcile two subprocess-policy test conflicts with required child cleanup; maintain explicit executable and timeout policy
2. Reproduce combined-suite hermetic MCP failure and isolate shared-state cause without dropping its assertion
3. Exercise immutable submission and validator handoff with stub model, ledger exhaustion and interrupted cleanup

Validation:

- Previously 190-pass/3-fail executor group passes with collection/exclusion accounting
- Former isolated-only pass also passes in original group
- Failed or timed-out attempt retained, no retry-selected success or self-acceptance

Acceptance limit: Real independent validator role still needs separate deployed identities.

Local status: **LOCAL_DONE** — Documented local bootstrap scope tested; deployed isolation and funded live execution remain R00/R01.

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/bob-provider-errors/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D00

**Prepare selected dependency closure and acquisition recipes**

Canonical parents: MIG-02, F-04, F-10. Asset IDs: native-tools, test-schema.

Software prerequisites: None. Explicit external gates: artifact_network.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- third_party/planning/power-spec-2: proposed selected-source manifest and dependency graph
- third_party/recipes/power-spec-2: bounded fetch/build recipe candidates

Implementation:

1. Select first-wave assets from packages.json; resolve exact commit/archive/image and compatibility before download
2. Recover available approved caches first; network fetch only in acquisition workspace
3. Enumerate build-time/runtime/test/plugin/model/data/interpreter dependencies and complete source/license closure
4. Record bytes, hashes, extraction safety, redirect identity, disk estimate, successful and failed fetches; export durable archive bundle

Validation:

- Missing transitive artifact, mutable pin, wrong hash and unresolved gitlink reject offline promotion
- Traversal/symlink archive escape and ambient-source substitution reject
- Fresh clone can recover ignored assets through retained storage identity, not local absolute paths

Acceptance limit: Selected acquisition is now authorized and evidenced as of 2026-09-22. Artifact custody is not dependency admission, clean offline runtime validation, complete native source rebuild closure or target compatibility.

Local status: **PARTIAL** — 132 pinned wheels plus runtimes/source bundle restored; 38 tests pass; Hypothesis source and native rebuild/target closure remain unresolved

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/D00/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D01

**Construct clean portable Bob environment**

Canonical parents: MIG-02, F-10. Asset IDs: bob, native-tools.

Software prerequisites: B00, D00. Explicit external gates: artifact_network.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- third_party/recipes/power-spec-2/bob-runtime.*
- Versioned runtime/interpreter lock and offline wheelhouse receipt

Implementation:

1. Use current source wheel identity, not old rejected 0.2.0 wheel
2. Resolve all runtime and build dependencies for chosen Python and platform, including claude-code-sdk and selected external CLI
3. Install offline in empty venv from hashed artifacts; test outside source without dependency overlay

Validation:

- pip check and CLI/help/version/import/resource probes
- Delete one wheel and offline install fails predictably
- Change wheel/hash/tag and fail before import
- No credential files or absolute symlink venv in archive

Acceptance limit: Clean local software installation only; no target ABI or paid model identity inference.

Local status: **LOCAL_DONE** — Clean offline Bob install; 183 installed tests and negative closure checks pass; no model calls

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/D01/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D02

**Freeze application numerical/test environment**

Canonical parents: MIG-02, F-10. Asset IDs: numerics, test-schema, hypothesis, salib.

Software prerequisites: D00. Explicit external gates: artifact_network.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- Application runtime/test dependency locks and offline recipe
- Analytic numerical and property-test fixtures

Implementation:

1. Start from qualified Python 3.13/NumPy 2.3.5/SciPy 1.18.1 evidence; retain Bob separate
2. Add schema/test libraries and Hypothesis; SALib only for selected sensitivity need
3. Do not pull PyMC/Dakota/pyMOR until justified by method; pin any necessary version change explicitly

Validation:

- Clean install, imports, pip check and native selected tests
- Analytic covariance/matrix and seeded property checks
- Missing native shared library detected; no ambient site-packages fallback

Acceptance limit: Application numeric operability; uncertainty model still needs physical adequacy tests.

Local status: **LOCAL_DONE** — Clean offline Python 3.13.12 closure; 289 app tests, 190 SALib passes plus one upstream xfail; negative controls pass

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/D02/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D03

**Build minimal Accelergy/HWComponents comparison**

Canonical parents: F-04, K-01. Asset IDs: accelergy, hwcomponents, power-content.

Software prerequisites: D00. Explicit external gates: artifact_network.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- third_party/recipes/power-spec-2/open-power comparison recipes
- Native outputs and minimal subsystem selection record

Implementation:

1. Acquire both pinned candidates only for one bounded public subsystem comparison
2. Run native tests/examples first; explicitly choose plugin/model package and config paths
3. Compare action coverage, units, leakage/baseline ownership, unsupported behavior and maintenance/build cost
4. Select one open non-IPPM production path; preserve rejected candidate rationale

Validation:

- Hand oracle: 3 read actions at 2 pJ and 4 writes at 5 pJ produce 26 pJ dynamic; 2 pW leak over 3 s adds 6 pJ if separately owned
- Missing action model and duplicate baseline reject
- Ambient plugin/config cannot change result
- No dummy model reported physical AMD content

Acceptance limit: Synthetic/native framework comparison only; actual AMD component parameters remain unqualified.

Local status: **LOCAL_DONE** — HWComponents selected for local development; both API oracles pass; Accelergy native CLI failures retained

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/D03/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D04

**Build SST Core and only required Elements**

Canonical parents: F-02, F-04. Asset IDs: sst-core, sst-elements, native-tools.

Software prerequisites: D00. Explicit external gates: artifact_network, owner_sst_version.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- third_party/recipes/power-spec-2/sst.*
- Installed core/elements native test inventory and outputs

Implementation:

1. Resolve matching owner-supported release pair; prefer release sources if avoiding absent autotools is supported
2. Build core first in private prefix, then required elements with explicit core location
3. Use bounded serial CPU configuration where valid; add MPI only for required model tests
4. Discover installed native tests and selected memHierarchy cases rather than assume suite completeness

Validation:

- sst --version, sst-test-core and selected sst-test-elements execute with nonzero collection
- Installed small configuration works outside source
- Missing element and incompatible core rejected
- Record optional disabled elements and all skipped cases

Acceptance limit: Public SST software only; missing owner model does not become a generic substitute.

Local status: **BLOCKED_OWNER** — owner SST compatibility/source

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/owner-blocked/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D05

**Audit and run owner AMD SST native model**

Canonical parents: F-02, F-04, F-09. Asset IDs: amd-sst.

Software prerequisites: D04. Explicit external gates: owner_sst.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- Owner model native build recipe and capability map
- Native activity/completion/control outputs with source identities

Implementation:

1. Inspect owner instructions/tests before adapter design
2. Build supported CPU-native case and enumerate precision/ISA/work inputs
3. Test activity counters, in-flight work and control hooks actually present
4. If a needed hook is missing, propose smallest element extension as separate child

Validation:

- Native expected counts and completion tests
- No unsupported instruction/action silently dropped
- Changing an allowed control affects intended mechanism in supported test or is explicitly unsupported

Acceptance limit: Requires owner source; physical MI355 validity remains open even when native tests pass.

Local status: **BLOCKED_OWNER** — owner SST source

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/owner-blocked/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D06

**Prepare Perfetto and observation import**

Canonical parents: F-03, F-06. Asset IDs: perfetto.

Software prerequisites: D00. Explicit external gates: artifact_network.

Final contract-integration prerequisites: S01.

Proposed outputs:

- third_party/recipes/power-spec-2/perfetto.*
- Application public trace-query adapter and export fixtures

Implementation:

1. Pin native processor and optional Python API closure; always pass explicit bin_path
2. Run native import/SQL against a tiny public trace then owner export when available
3. Map actual timestamps/slices/counters with declared boundary and missingness; reuse existing parser

Validation:

- Known slice durations/counts, duplicate events, clock discontinuity and truncated export cases
- No-device offline run with no first-use fetch
- Missing binary fails before attempting network
- SQL output preserves units and observed gaps

Acceptance limit: Real acquisition export completeness and timebase alignment remain target/harness gates.

Local status: **LOCAL_DONE** — Pinned native Perfetto and strict observation importer; 361 installed tests and native gap oracle pass

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/D06/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D07

**Complete AMD SMI and profiler build prerequisites**

Canonical parents: F-03, F-04, F-10, X-01. Asset IDs: amdsmi, amd-devlibs, rocprofiler, rocm-toolchain.

Software prerequisites: D00. Explicit external gates: artifact_network, target_platform.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- Separate AMD SMI, ROCprofiler and ROCm compile-only recipe children
- Host-only tests and installed consumer receipts

Implementation:

1. Resolve selected development libraries and SDK gitlinks from actual configure requirements
2. Bind target OS/CPU/runtime and compile architecture explicitly; do not infer from absent local GPU
3. Build AMD SMI first, SDK next as distinct attempts; no driver installation or device control in CPU build step

Validation:

- Fresh configure/build and strict header/link/import consumers
- Offline build fails on missing gitlink/library instead of fetching
- Typed no-device outcomes where supported
- Compile-only code objects inspected for intended target, never marked execution-tested

Acceptance limit: Host artifacts are not automatically compatible with target system; collection and controls remain live tests.

Local status: **BLOCKED_OWNER** — target platform

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/owner-blocked/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D08

**Turn existing native results into optional adapter fixtures**

Canonical parents: F-06, F-09, F-10. Asset IDs: drampower, mgpusim, papi, salib.

Software prerequisites: D00. Explicit external gates: app_workspace.

Final contract-integration prerequisites: S01.

Proposed outputs:

- Application adapters for specifically selected existing providers
- Public native-result fixtures and comparison receipts

Implementation:

1. Select only useful DDR/MI300A numerical references; retain baseline native identities
2. Use actual MGPUSim SQLite schema and separate Driver/CommandProcessor measurands
3. Use DRAMPower qualified source embedding; fix installed exports only if needed
4. Run native case anew for adapter comparison; static expected output alone is not native provenance

Validation:

- Eight existing reference cases only where applicable; independent masks/units/grid/count mutations
- Native/adapted result equality with explicit arithmetic tolerance
- Preserve MCCL exclusion, no-HBM and gfx942 ceilings
- Source mutation and stale result hashes reject

Acceptance limit: No inference of MI355/power support and no new authoritative acceptance from old checker.

Local status: **LOCAL_DONE** — Native optional adapters; 330 installed tests; fresh DDR and MI300A reference runs pass

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/D08/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D09

**Reproduce a CPU reference for V-04 selection**

Canonical parents: V-02, V-03, V-04. Asset IDs: aisimulate, energaizer.

Software prerequisites: D00. Explicit external gates: artifact_network, reference_data.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- Separate AISimulate and EnergAIzer small reproduction packet candidates
- One selected applicable native reference report and selection rationale

Implementation:

1. Prioritize EnergAIzer published frequency subset for D2a relevance; try AISimulate engine-only if it supplies applicable timing comparison
2. Stage one package/data closure per child; do not require both branches to complete
3. Run native example then one exact measured/config cell; label every imported target profile
4. Choose V-04 evidence from at least one completed applicable V branch; retain failures and limits

Validation:

- Native outputs, absolute timing/power errors and coverage with exact data hashes
- Missing data and mismatched config revision reject
- Unexposed/blind label cannot be assigned to public-profile reproduction

Acceptance limit: At least one applicable native branch, not all optional references; final canonical V dependencies still govern acceptance.

Local status: **LOCAL_DONE** — Four public A100 frequency cells replay exactly; 18 tests; frozen config/data rejection; full frontend excluded

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/D09/README.md). Direct Codex work; not Bob-authored or independently accepted.

## D10

**Prepare vLLM workload and compile-only target bundle**

Canonical parents: F-05, F-09, X-02. Asset IDs: vllm, pytorch, workload-assets, rocm-toolchain, transferbench, compute-bench.

Software prerequisites: D00. Explicit external gates: artifact_network, target_platform, workload_identity.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- Pinned target image or rebuild recipe with staged model/tokenizer inputs
- CPU request/work manifests and host-test results

Implementation:

1. Resolve actual requested model/precision/KV/kernel/workload and compatible software pairing
2. Build CPU-testable request parsing/tokenization/work accounting first
3. Acquire only selected HIP tools/kernels; compile with explicit target on CPU where supported
4. Bind image/source/wheel/model storage and bytes; do not download large unused model variants

Validation:

- Fixed tokenizer/prompt/request outputs with tiny public fixture
- Missing shards, dtype fallback and incomplete declared work reject
- Offline target image reconstruction or explicit remaining compile blockers
- List every GPU execution test deferred

Acceptance limit: Real tokens, precision, kernels, runtime and observation quality require MI355.

Local status: **BLOCKED_OWNER** — target platform

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/owner-blocked/README.md). Direct Codex work; not Bob-authored or independently accepted.

## S00

**Recover authority and create spec-2 application workspace**

Canonical parents: MIG-00, F-01. Asset IDs: contracts, app-baseline.

Software prerequisites: None. Explicit external gates: complete_contracts, app_workspace.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- Application layout decision and new spec-2 namespace
- Source/contract crosswalk and reusable unit module tests

Implementation:

1. Recover complete normative files and resolve status vocabulary before final schema design
2. Keep existing clean application and dirty provider work intact
3. Choose exact app root and write allowlist; reuse unit code after review
4. Map schemas/tasks/exposure definitions to local plan and retain explicit missing items

Validation:

- Authoritative hashes and conflict crosswalk
- Five old unit tests retained
- No missing authority marked present or old schema silently repurposed

Acceptance limit: Generic math/native preparation can continue without this task; final schema/dispatch cannot.

Local status: **PARTIAL** — Application workspace built; four layout and 196 installed-wheel tests pass; complete normative authority remains missing

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/S00/README.md). Direct Codex work; not Bob-authored or independently accepted.

## S01

**Implement strict data contracts and allowed-input projections**

Canonical parents: F-01, F-06, F-07, B-01. Asset IDs: contracts, test-schema, app-baseline.

Software prerequisites: S00, D02. Explicit external gates: Shared dispatch requirements.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- APP/src contracts and allowlist projection modules
- APP/tests/public contracts, provenance and leak-canary fixtures

Implementation:

1. Implement recovered DatasetManifest, AllowedInputManifest, ModelSubmission, PredictionBundle, ScoreProfile and ScoreReport semantics
2. Validate units/scope/ancestors/finite values and typed unsupported/missingness
3. Create fresh field allowlists with grouped split and duplicate-ancestor checks

Validation:

- Unknown fields, duplicate keys, nonfinite values and invalid path reject
- Change hidden labels: allowed-input projection and prediction input bytes unchanged
- Truncated output, missing work and wrong ancestor reject
- No enum or W/C definition invented from old spec

Acceptance limit: Software enforcement on public fixtures; independent deployed custody separately required.

Local status: **PARTIAL** — 58 new and 63 installed contract tests, four mutations; final normative schema/W-C binding remains owner-blocked

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/S01/README.md). Direct Codex work; not Bob-authored or independently accepted.

## S02

**Implement immutable submission, provenance and attempt ledger**

Canonical parents: A-01, A-03, F-07, F-10, B-01. Asset IDs: contracts, test-schema, attestation.

Software prerequisites: S01, B03. Explicit external gates: Shared dispatch requirements.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- APP submission/provenance/attempt components using existing libraries
- Crash/resume and tamper fixtures

Implementation:

1. Reuse existing artifact/state helpers; bind source/input/output/scorer/policy identities
2. Atomic freeze and retries retain all attempt IDs and consume finite ledger entries
3. Use existing chosen standard attestation interface if needed; no new crypto or orchestrator

Validation:

- Modified bytes, wrong parent/signer and replayed submission reject
- Crash before/after rename yields consistent state
- Failed launch consumes appropriate budget and cannot be omitted
- Developer cannot self-mark submission accepted

Acceptance limit: Mock privileges establish interface logic only; actual denials required at R00.

Local status: **LOCAL_DONE** — 35 new and 98 installed contract tests, four mutations; immutable local submissions and finite append-only attempts

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/S02/README.md). Direct Codex work; not Bob-authored or independently accepted.

## S03

**Implement deterministic observation and absolute scoring math**

Canonical parents: F-03, F-07, U-01. Asset IDs: numerics, contracts.

Software prerequisites: D02. Explicit external gates: Shared dispatch requirements.

Final contract-integration prerequisites: S01.

Proposed outputs:

- APP observation operators and deterministic scorer modules
- Independent public interval/integration/residual fixtures

Implementation:

1. Build pure interval/energy/error functions and public oracle tests from supplied spec now; bind ScoreReport/ScoreProfile serialization only after S01.
2. Implement declared hold/linear observation operators, coverage and absolute error metrics
3. Keep gaps, resets, saturation and unsupported channels typed
4. Use frozen ScoreProfile; absent approval produces non-qualified descriptive report

Validation:

- Hold intervals 10 W for 2 s then 4 W for 3 s = 32 J
- 2-to-6 W linear ramp over 2 s = 8 J; left hold = 4 J
- Splitting equal intervals preserves energy; unit/time-boundary/missing-sample mutations fail
- Replay produces same normalized report and score provenance

Acceptance limit: No physical tolerance, policy approval or sensor independence inferred from synthetic success.

## S04

**Implement paired clock-response and interaction scoring**

Canonical parents: X-05, U-01. Asset IDs: numerics, contracts.

Software prerequisites: S03. Explicit external gates: Shared dispatch requirements.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- APP paired response/contrast/elasticity scorer
- Public factorial, bias and covariance fixtures

Implementation:

1. Pair by actual experimental block and achieved controls; preserve assigned-policy cohorts
2. Compute absolute plus paired response and factorial interaction with covariance
3. Undefined elasticity and absent cells remain typed failures

Validation:

- Y=10+2c+3m+4cm gives 10,12,13,19 and interaction 4
- Add 7 everywhere: response matches but all absolute residuals are +7
- Variances 9 and 4 with covariance 3 yield contrast variance 7
- Same achieved clocks and wrong slope rejected; independent shuffle mutation detected

Acceptance limit: No same-card frequency result relabeled architectural transfer.

## S05

**Implement UQ, calibration and reduction software fixtures**

Canonical parents: U-01, U-02, K-02, C-01, C-02. Asset IDs: numerics, salib.

Software prerequisites: S03, D02. Explicit external gates: Shared dispatch requirements.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- Separate APP covariance/calibration/reduction children
- Independent analytic and coverage/sharpness cost fixtures

Implementation:

1. Use established SciPy/statistics first, preserving joint samples and experimental-block sampling units
2. Validate identifiable versus grouped parameters and baseline ownership
3. If derivatives/approximate inference are selected, compare against independent reference; if region composition selected, prove reconstruction
4. Use conditional libraries only after justified need and native tests

Validation:

- Analytic covariance and paired-noise cancellation
- Rank-deficient calibration reported unidentifiable
- 5 J baseline + 2 J compute + 3 J memory = 10 J with exactly one baseline
- Full-region accounting and error-cost comparison; missing work cannot lower error by exclusion

Acceptance limit: Synthetic coefficients never become AMD calibration; U-02/C-02/Q-01 claim gates persist.

Local status: **LOCAL_DONE** — 196 public tests and seven detected mutations; synthetic-only UQ/calibration/reduction scope

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/S05/README.md). Direct Codex work; not Bob-authored or independently accepted.

## S06

**Implement control protocol and trial scheduling replay**

Canonical parents: X-01, X-02, X-03, X-04, P-03. Asset IDs: harness, amdsmi.

Software prerequisites: None. Explicit external gates: Shared dispatch requirements.

Final contract-integration prerequisites: S01.

Proposed outputs:

- APP device-control protocol and public fake-device replay driver
- Trial ledger/work-invariance and cleanup tests

Implementation:

1. Build a standalone public protocol/fault-replay test component first; final contract serialization and real harness binding wait for their actual definitions/sources.
2. Implement requested/realized controls, units, tied domains, unsupported settings and voltage coupling from interfaces
3. Schedule frozen-work trials with fixed seeds and retain noncompliance in assigned cohort
4. Exercise success, cancellation, timeout, readback error, partial capture and restore failure
5. Bind real harness only after source/API is available; public fake is explicitly synthetic

Validation:

- API success with unchanged realized clock does not certify fixed level
- Restore attempted exactly as protocol requires on all exit paths; failure blocks continuation
- Incomplete work/profiled-vs-clean mismatch detected
- Future sensor sample cannot drive past control decision

Acceptance limit: Real feasible grid, repetitions, reset commands and clock authority remain target/policy decisions.

## S07

**Bind open power actions to native execution**

Canonical parents: F-06, K-01, P-01, P-03. Asset IDs: amd-sst, power-content.

Software prerequisites: S01, D03, D05. Explicit external gates: owner_sst.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- APP selected provider adapter and activity-to-component binding
- Native/public power-accounting comparison fixtures

Implementation:

1. Consume actual provider activity/work and bind only supported actions to selected open model
2. Track component/baseline ownership, uncertainty and unsupported coverage
3. Test in-flight causal hooks within existing provider; no new general event engine
4. Measure adapter overhead separately from native execution

Validation:

- Native vs adapted action counts and completion
- Missing action, wrong count/unit and duplicate baseline mutations
- 100 cycles at 1 GHz for 50 then 0.5 GHz for 50 = 150 ns; 25 ns gating = 175 ns on supported hook fixture
- Synthetic count-energy oracle independent of adapter implementation

Acceptance limit: Software integration only; same-target physical timing and power qualification still open.

Local status: **BLOCKED_OWNER** — owner SST integration

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/owner-blocked/README.md). Direct Codex work; not Bob-authored or independently accepted.

## R00

**Qualify local deployed role separation**

Canonical parents: A-02, F-07, B-01. Asset IDs: isolation, attestation.

Software prerequisites: B03, D01, S02. Explicit external gates: capable_isolation_host.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- Existing runner deployment profile, public canary stores and denial receipts

Implementation:

1. Use separate actual principals, storage and credentials for preparer/predictor/scorer/validator
2. Test public canaries for sealed-label paths, scorer writes, device/network access and shared cache
3. Do not equate test function mocks or role labels with privileges
4. Record denied namespace capability in this sandbox; run on authorized capable local CI instead

Validation:

- Actual OS denies all prohibited reads/writes/network/devices
- Allowed inputs still available and successful immutable submission scores
- No unrestricted-host fallback or shared writable cache

Acceptance limit: Pre-MI355 deployment gate; not scientific or GPU evidence.

Local status: **BLOCKED_OWNER** — capable isolation host

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/owner-blocked/README.md). Direct Codex work; not Bob-authored or independently accepted.

## R01

**Run local synthetic end-to-end software rehearsal**

Canonical parents: F-08, P-01, X-05, MIG-03. Asset IDs: bob, contracts, numerics.

Software prerequisites: B03, D01, D02, S02, S03, S04, S05, S06, R00. Explicit external gates: selected_model.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- Public end-to-end software receipt, frozen submission and independent verifier results

Implementation:

1. Run one finite downgraded-model public task through healthy Bob profile; no confidential data
2. Execute synthetic acquire/project/predict/freeze/score/report with real separate privileges
3. If S07 is ready, run separate native-provider variant; otherwise record native integration pending
4. Preserve failures/retries and every acceptance limitation

Validation:

- Prediction unaffected by hidden-label canary; score changes as expected
- Native result never substituted by fixture when claiming native mode
- Independent rerun on same frozen inputs
- No auto QUALIFIED status for software rehearsal

Acceptance limit: Useful pre-live software integration; cannot close F-08/P-01 scientific acceptance by itself.

Local status: **BLOCKED_OWNER** — funded model key

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/owner-blocked/README.md). Direct Codex work; not Bob-authored or independently accepted.

## R02

**Assemble and rehearse MI355 handoff**

Canonical parents: MIG-03, F-10. Asset IDs: bob, rocm-toolchain, vllm, workload-assets.

Software prerequisites: D01, D02, D07, D10, R01. Explicit external gates: target_platform.

Final contract-integration prerequisites: None beyond software prerequisites.

Proposed outputs:

- Versioned portable source/dependency/image bundle and local verification report
- Target capability probe, no-device smoke, rollback and remaining-live-test checklist

Implementation:

1. Include selected sources/patches/recipes, complete dependencies/models and checksums with no absolute local venv links
2. Recover ignored artifacts on clean host; offline rebuild or prove exact image/platform compatibility
3. Run no-device public smoke and failure/rollback paths
4. List missing owner model/harness/native integration explicitly; selected D03-D09/S07 must pass before their capability is advertised

Validation:

- Clean environment reconstructs selected software with network disabled
- Missing wheel/gitlink/native library/model shard fails preflight
- Known exclusions preserved; no hidden required GPU action in install
- Secrets and sealed labels absent from developer bundle

Acceptance limit: Transfer software only after this gate; live capability/metrology/workload/calibration/D2a/D2b/transfer tests remain on target.

Local status: **BLOCKED_OWNER** — target platform and funded independently validated handoff

Evidence: [README.md](../../../third_party/receipts/implementation-2026-09-22/owner-blocked/README.md). Direct Codex work; not Bob-authored or independently accepted.
