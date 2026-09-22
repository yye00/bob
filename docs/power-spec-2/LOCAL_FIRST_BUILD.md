# Build locally before the MI355 handoff

Cross-check: 2026-09-21. This extends the [migration plan](README.md) with actual
local build/test evidence and an implementation-location split. It does not
implement the new simulator or accept any of the 41 scientific tasks. Every
task in [TASKS.md](TASKS.md) now states its pre-MI355 work and remaining gate.

The follow-up [Bob local build queue](BOB_LOCAL_BUILD_QUEUE.md) breaks this into
26 implementation slices tied to a [46-package/input inventory](../../../third_party/planning/power-spec-2/PACKAGE_READINESS.md).
Use that queue and the [acquisition plan](../../../third_party/PRE_MI355_ACQUISITION.md)
for the missing downloads, environment closure and concrete code/build tasks.
New entrypoint probes find the existing editable Bob CLI fails importing `tools`
from both workspace and Bob cwd; the installed-wheel result below covers a
different installation mode. GitHub source resolution also fails in this session.

**Most software construction should happen here.** Bob execution repair,
packaging, dependency closure, contracts, adapters, provenance, deterministic
scoring, synthetic frequency/control tests and uncertainty math are local work.
MI355 is needed for actual target capability discovery, workload capture,
measurement/characterization and physical qualification. Missing source,
libraries, contracts or deployment privileges are separate blockers; moving to
a GPU host does not fix them automatically.

Actual commands, all failed attempts, native logs and identities are in the
[local-readiness receipt index](../../../third_party/receipts/local-readiness-2026-09-21/README.md).
The [initial planning receipt](PLANNING_CHECKS.md) predates these native runs and
remains a record of that earlier pass.

## What we have, cross-checked against Bob

| Capability | Existing local asset | Bob/application connection and remaining work |
| --- | --- | --- |
| Coding/task executor | Current `bob/` at `84c9f420…`; Python 3.14.2 environment with declared runtime distributions | Reuse executor/admission machinery; fix packet custody and model/budget profile first. Generic software verification is not scientific scoring. |
| Installed Bob package | Fresh current wheel built offline; CLI/import/resources work with existing dependency overlay | Old rejected wheel is historical. Current package needs a complete clean offline dependency installation before portable handoff. |
| Actual application baseline | `third_party/work/ppat-development`, clean commit `2d8de941…`; exactly three tracked application files | One canonical-unit module, public fixture and five tests. It is not an existing full simulator, provider adapter, waveform scorer or workload IR. |
| CPU memory-model reference | DRAMPower 6.0.0 source and seven archived inputs, local compiler/CMake/Ninja and embedding adapters | Use optional DDR/LPDDR native/reference tests. It has no HBM power model; do not make it the required MI355 memory backend. |
| CPU GPU-simulator reference | MGPUSim 4.2.0, Go module cache and generated mock inputs | Build and run supported native numerical/grid/activity cases locally. Its MI300A/gfx942 spot checks do not establish MI355/gfx950 support. |
| Exact adapter reference corpus | Eight public cases in `power-spec/simulator-reference-tests/` | Reuse source-bound numerical/mask/DDR4 fixtures after scope review. Its old thermal/factory instructions remain historical; its checker is not execution provenance. |
| PAPI C integration | Existing PAPI 7.2.0 private prefix plus sources | Header/link and CPU component integration are local. Sensor origin, target counters, permissions and power observations need target qualification. |
| Numerical libraries | SALib 1.5.2 / NumPy 2.3.5 / SciPy 1.18.1 in the existing Python 3.13.12 environment | Reuse selected sensitivity/statistics routines. Implement application likelihood, covariance, score/observation operators and uncertainty policy; SALib is not a power model. |
| JSON and software tests | Bob environment has pytest, Pydantic, PyYAML and JSON Schema | Good starting point for public envelope/oracle tests. Hypothesis was not installed in the three inspected environments; obtain/pin it if selected. |
| AMD acquisition sources | Selected ROCm Systems/AMD SMI/ROCprofiler source custody | AMD SMI configure currently stops at missing `libdrm`; SDK dependency gitlinks/closure remain incomplete. These are provisioning tasks before hardware use. |
| Isolation tooling | `bwrap`, `unshare`, `setpriv`, Docker/Podman commands present | Tool presence is insufficient: the attempted network namespace probe was denied in this sandbox. Qualify on an authorized capable local host/CI deployment before accepting separation. |

The working host has 32 logical CPUs and sufficient space for the bounded native
rebuilds attempted here. It exposes no `/dev/kfd`, `/dev/dri` or `/opt/rocm` in this
environment; `nvidia-smi` could not communicate with its driver. This establishes
no accessible GPU execution path here, not an inventory of physically installed
cards. Builders used small explicit parallelism and isolated output directories.

## New-spec providers that are not yet ready locally

The inspected `third_party` roots, package environments and executable search did
not establish these as available build inputs. Headers mentioning a package and
old candidate-list entries are not installed provider implementations.

| Missing or incomplete item | Action before MI355 | What remains hardware-dependent |
| --- | --- | --- |
| Owner AMD SST model/native tests | Locate the actual approved source/config repository first; build its supported CPU-native examples; audit required activity/control hooks | Actual MI355 mechanism and calibration validity |
| Open non-IPPM power path | Acquire/pin one justified Accelergy/HWComponents comparison and native example, then choose the minimal supported path | AMD action/component characterization and measured accuracy |
| Existing physical acquisition harness | Obtain actual code and public export samples; implement only missing adapters and observation tests | Sensor calibration, clean/profile overhead and real channel behavior |
| Perfetto Trace Processor/runtime | Resolve standalone binary or Python API plus its native binary/data closure; do not infer it from ROCprofiler headers | Validation of complete real target exports and channel timing |
| vLLM/model fixture | Resolve exact source/runtime/checkpoint/tokenizer/prompt/precision/KV/kernel inputs and license/storage requirements | Actual requested single-GPU workload and replay equivalence |
| Optional Accel-Sim/AISimulate/EnergAIzer | Select bounded reference branch, acquire matching source/config/data and run available CPU artifact tests | Fresh reference measurement may need supported NVIDIA hardware, which is distinct from MI355 |
| AMD SMI system dependencies | Provision pinned development libraries or an approved build image/sysroot; build source without needing a live card | Real device enumeration/control/readback and restoration |
| ROCprofiler SDK closure | Resolve required gitlinks or exact system replacements, compiler/HSA dependencies and build image | Collection compatibility/overhead and actual event availability |
| Complete v0.4.1 contracts | Recover missing original normative/evidence/schema/registry files; reconcile the local planning projection | No inherent GPU requirement; do this before final schema-dependent implementation |

This audit did not download providers or install system packages. Keep acquisition
separate from offline builds and do not select every optional package. The absence
of these inputs is not a reason to postpone unrelated public software work.

## Fresh local results and their limits

| Check | Observed result | Meaning |
| --- | --- | --- |
| Bob current wheel | Build/install succeeds; installed CLI, 13 imports and four resources succeed using existing dependencies | Package structure improved relative to old receipt; dependency overlay is not a clean portable install |
| Bob clean no-dependency install | CLI fails on missing Click; all 14 declared runtime distributions absent | Expected negative control; still need wheelhouse/runtime closure, not a source-code fix for absent dependencies |
| Bob admitted packet + atomic planner suites | 99 passed, eight failed | All eight fail on missing materialization/custody constructor fields; atomic planner alone is 68 passed |
| Bob executor group | 190 passed, three failed; one failing node passes isolated | Two subprocess-policy assertion conflicts and one unresolved suite-order/state issue; not a healthy all-green executor baseline |
| Existing unit application | Five tests passed | Twelve canonical mappings and rejection behavior only |
| Public native-reference checker | 13 tests passed; eight source-bound cases verified | Explicit `ppat_comparison: not_run`; no application adapter comparison was fabricated |
| DRAMPower fresh native build/test | Build passed; 336/336 tests, zero skips; four matching CLI fixtures and benchmark smoke | Fresh extraction and actual tests, never HBM or MI355 power qualification |
| DRAMPower installed consumer | Both package-config and direct public-header consumer probes still fail | Use qualified source embedding if selected; package installation is not repaired |
| MGPUSim offline native build | Passed after explicitly disabling Git VCS stamping for the manifest-bound source copy | Build is independent of GPU availability; source identity retained separately |
| MGPUSim vectoradd | CDNA3 emulation and MI300A timing verification passed with `-disable-rtm` | No localhost monitor permission needed; actual timing output is SQLite, not assumed CSV; not MI355 evidence |
| MGPUSim broader native suite | 23 test packages passed, 93 had no tests; MCCL explicitly excluded | Previous stalled collective path remains unqualified; exclusions cannot become a full-suite pass |
| SALib native suite | 190 passed, one xfailed, 28 warnings; 191 collected | Pinned Python 3.13.12/NumPy 2.3.5 context; scoped native operability |
| SALib seeded smoke | Expected `x3 > x2 > x1 > x4` ordering | Synthetic sensitivity oracle, not calibrated power or physical UQ |
| PAPI consumer | Fresh strict C compile/link and execution passed against existing private prefix; three components enumerated | CPU integration evidence; uncore privilege unavailable and no configured AMD GPU channel |
| AMD SMI fresh configuration | Blocked by missing `libdrm` | A local dependency gap, not proof that compilation requires an MI355 |
| Separate network namespace probe | Denied | Current sandbox cannot establish production isolation; never fall back and call it isolated |

Use the linked per-branch receipts for exact commands, versions, counts, hashes,
failed attempts and test exclusions. Tests are not interchangeable: the Bob suites
exercise legacy behavior, native suites exercise upstream packages, and the public
reference checker validates its own comparison logic.

## Local implementation order

These slices refine the canonical backlog and preserve its source dependencies.
They are proposed implementation work for the downgraded model; this cross-check
did not modify runtime code. Missing scientific approval blocks qualification,
not public synthetic development. Missing permission blocks only the action it covers.

### L1 — Make Bob locally usable for bounded packets (MIG-01, A-01, A-03)

1. Repair `src/bob/admitted_packet.py` and actual loader/run-loop/controller
   lifecycle. `AdmittedPacketContext` requires `workspace_path`,
   `target_materialization_path`, `target_materialization_sha256` and
   `target_materialization`; its construction omits them. `safe_model_assignment`
   references undefined `assert_materialized_target_custody`.
2. Prove clean-base authentication precedes authorized target creation. Preserve
   inode/mode/owner/link custody through mounting and resume; do not use empty
   defaults or remove required fields to turn the eight failures green.
3. Resolve exact source/runtime model identity. Besides `bob_build.env` aliases,
   `atomic_packet_planner.py` hard-pins `PACKET_MODEL = "claude-opus-4-8"`, validates
   that value and configures unlimited turns. An environment-only downgrade is
   insufficient. Version the Power profile while preserving legacy semantics.
4. Resolve the two executor subprocess assertions against intended child cleanup
   behavior and reproduce the hermetic MCP test both alone and in its failing
   group. Retain independent expected behavior; do not merely delete assertions.
5. Demonstrate local public packet prepare → writer/implementer bounds → immutable
   submission → independent validation handoff, including denied writes, crash,
   resume, exhausted budgets and stale-hash rejection. No paid model call is needed
   to test the interface; qualify the actual selected model separately at dispatch.

Exit: exact affected tests pass, negative custody/role cases still reject, actual
call path consumes the scoped model/budget, and clean package execution is proven.
No MI355 dependency applies to fixing these defects.

### L2 — Freeze build environments and selected native sources (MIG-02, F-04, F-10)

1. Retain separate Bob, numerical and native build environments. The root Python
   3.12 environment is minimal; Bob's NumPy 2.5.2 is not the qualified SALib
   NumPy 2.3.5 environment. Do not merge environments by copying package folders.
2. Build a hash-complete offline runtime/wheelhouse and perform a fresh install
   with no editable paths or symlink dependency overlay. Run installed CLI,
   resource, imports and `pip check` from outside the source tree.
3. Reuse the fresh archive extraction and source manifests from this audit;
   bind patches/generated mocks/toolchains/compiler/dependencies explicitly.
   The new DRAMPower run does not repair the old verifier script's mutable-input gap.
4. Recover preferred SST/open-power/harness sources and missing development
   libraries now, then execute their native supported examples before adapters.
5. Package source and recipes for the target OS/CPU/runtime. Rebuild there or
   independently establish ABI/image compatibility; copying this workstation's
   absolute-symlink virtualenvs is not a deployment strategy.

Exit: independently reconstructible native/reference and Bob software stack;
selected failures/skips remain explicit, including MCCL and DRAMPower install limits.

### L3 — Implement contracts, evidence and adapters on CPU (F-01, F-06, F-07, B-01)

Recover authoritative schema/W/C definitions before claiming conformance. Build
DatasetManifest, AllowedInputManifest, ModelSubmission, PredictionBundle,
ScoreProfile and ScoreReport with source/parent identities and typed missingness.
Use the eight public native cases for a bounded first adapter slice; add independent
size/grid/mask/unit/rounding/baseline mutations. Keep training-shaped numerical
fixtures as semantics checks, without adding a training product.

The fresh MGPUSim runner emitted SQLite (907 metric rows for the timing case),
despite older CSV-oriented text/flags. Implement against its actual retained
schema and units. Driver kernel time and CommandProcessor kernel time have
different boundaries and must not be silently merged into one timing measurand.

Implement fresh allowlisted views, grouped splits, ancestor/duplicate detection,
atomic freezes and reveal accounting with synthetic canaries. Reject wrong units,
nonfinite values, missing work, unsafe paths and data-only output violations.
Resolve the actual application layout explicitly: the clean legacy baseline is a
reuse candidate, not automatic new-spec source authority or a reason to change Bob core.

Exit: native/adapted public results agree with independently written expectations;
source and input tampering fail. No mock or copied expected result is native execution.

### L4 — Implement scientific math and falsification without a GPU (U-01, X-05, K-02, C-01/C-02, U-02)

Use [VALIDATION.md](VALIDATION.md)'s exact interval integration, piecewise work,
factorial response, absolute-bias/wrong-slope, paired covariance, elasticity and
baseline-accounting oracles. Add score replay, block-level resampling, coverage and
sharpness, identifiability and selected-region reconstruction cases. Use existing
statistics libraries, not a new sampler/optimizer. Keep fabricated fixtures labeled
synthetic; fit no AMD coefficients from them and approve no physical tolerance from
synthetic success. Conditional U-02/C-02/Q-01 gates still govern actual claims.

Exit: deterministic and property/defect tests establish math/software behavior;
measured calibration/noise and physical prediction acceptance remain open.

### L5 — Prepare acquisition and clock protocols before target access (F-03, X-01…X-04)

Reuse the real harness interface once located. Implement record/parsing logic for
requested versus realized controls, clocks versus data rates, soft maxima, tied
domains, unsupported settings and voltage coupling. Build frozen-work/native-request
lane manifests and trial scheduling/attempt retention. Exercise cleanup after
success, cancellation, timeout, partial capture, readback failure and failed reset
using explicitly synthetic control fixtures. Freeze a **proposed** design only;
actual domains/grid/repetitions depend on target discovery and approved pilot policy.

Exit: a single bounded deployment packet can run on the target without inventing
commands, control independence, metrology or hardware authority. The package must
refuse unsupported target capabilities instead of filling missing channels with zero.

### L6 — Rehearse deployment and independent access (A-02, MIG-03)

Run role separation against public canary stores on a capable approved local
host/CI system. Prove denied developer reads/writes, predictor network/raw-device
access, scorer mutation and shared-cache leakage. Keep build/network acquisition
separate from offline prediction. This restricted sandbox's denied namespace
probe is a deployment blocker, not evidence that MI355 is needed for isolation.

Prepare a portable, versioned handoff with:

- Current source/patch/Bob/gitlink identities, exact runtime and dependency closure.
- Recoverable source archives/images, license closure and offline build recipes.
- Working installed-package and native test receipts; complete known-failure list.
- Current contracts, bounded packets, public oracles, manifests and allowed inputs.
- Scorer/policy versions and provisioning references, with secrets and sealed labels
  held by their proper service identities rather than packed into developer files.
- Proposed target capability/workload/metrology/clock plan, restoration requirements,
  actual authorization prerequisites and a local no-device smoke/rollback recipe.

Exit: a clean host can reconstruct the software and run public smoke/denial checks.
That is the pre-MI355 software gate; target scientific tasks remain separate.

## What must remain for MI355 and later systems

On the actual approved target, discover device/board/firmware/driver/runtime,
partition mode and available controls; qualify observations and work completion;
capture the real specified vLLM workload; acquire independent component/action
calibration; freeze and acquire the supported frequency trials; and score absolute,
response, uncertainty and ordinary-PMFW behavior under approved policy.

Do not wait until then to discover missing build libraries, broken packet dispatch
or invalid packaging. Conversely, do not call CPU tests MI355 validation. D3b needs
an actually different architecture; D4 requires separate high-current authority;
D5 needs multiple GPUs and preceding B-04/H-01 gates; D6 needs multiple nodes.
One MI355 system does not close all later deliverables.
