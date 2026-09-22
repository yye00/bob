# Implementation progress

Started 2026-09-21 after the owner authorized moving from planning to work.
The [local queue](BUILD_QUEUE.md) records local execution status as of the owner
instruction on 2026-09-22; the canonical backlog remains a planning baseline. No
canonical scientific task is accepted by these software results.

## Current round 2: D04 → R00 → D00 finished within local scope

The owner chose the latest stable matching SST releases and accepted this machine
as the R00 host on 2026-09-22. D04 is complete locally: verified Core/Elements
16.0.0 sources, serial Core and only merlin/memHierarchy. **207 Core passes,
20 declared skips, nine Elements passes, 17 recipe tests and four caught mutations**.
[The D04 receipt](../../../third_party/receipts/implementation-2026-09-22-round2/D04/README.md)
retains all failed attempts and the verified source bundle.

R00 is also complete for the accepted local scope: **four actual Docker role
UIDs, 21 policy tests, four caught mutations and 64 denial observations**, including
two roles alive together in different PID/mount/network/IPC namespaces. Existing
S01/S02/S05 components execute through the role pipeline; exact invocation
provenance and a tampered binding are checked. [R00 receipts](../../../third_party/receipts/implementation-2026-09-22-round2/R00/README.md)
record the Podman uid-map failure and explicit trust limits: host controller,
Docker daemon and administrators remain trusted; no separate user namespace or
independent scientific acceptance is claimed.

D00's exact Hypothesis source gap is closed. The frozen compiler image rebuilds
Hypothesis, SST, DRAMPower and MGPUSim offline: **70 native Hypothesis tests +
361 installed application tests**, **207 Core + nine Elements passes** (20 Core
skips), **336 DRAMPower tests**, and **23 MGPUSim test packages** (MCCL excluded).
Sixteen recipe tests and four caught mutations pass. A fresh 159-file bundle
restoration repeats the Hypothesis/application checks; exact original source,
registry crates, 71 signed Debian packages and compiler archives are retained.
[D00 round-2 receipts](../../../third_party/receipts/implementation-2026-09-22-round2/D00/README.md)
record all failed attempts and remaining full source-bootstrap/target boundaries.
D00 remains PARTIAL for those broader boundaries; no slice is IN_PROGRESS.
No Git commands ran in the operator-managed root or Bob repositories. D05/S07, D07/D10 and
R01/R02 remain outside this work order.

## Round 1 status: 2026-09-22 direct work complete within local scope

The owner's requested order is finished: Bob provider-error fix → S05 → S00 →
S01 → S02 → D00 → D02 → D01 → D08 → D03 → D06 → D09. No slice remains
IN_PROGRESS. The final application suite passes **361 installed-wheel tests**;
the clean offline Bob environment passes **183 installed tests**. These totals
overlap earlier checkpoints and must not be added to them. Native provider,
negative-control and mutation results are recorded in each slice's receipt below.

S00 and S01 are PARTIAL only for missing complete normative authority; their
local workspace/contracts are implemented. At the end of round 1, D00 was PARTIAL for unavailable exact Hypothesis source
and native/target closure, D04/R00 were owner-blocked, and selected binary
environments installed offline. **The round-2 section above supersedes those
Hypothesis, D04 and R00 blockers.** Current owner blockers are D05/S07 (AMD SST
model), D07/D10 (target platform) and R01/R02 (funded model key/handoff; R02 also
requires the target).

All Bob controllers are stopped per the owner's 2026-09-22 report. Controller 04
reached the API and received insufficient credit; its ledger is preserved.
Artifact networking is now available. No Bob campaign was relaunched during
this direct work. Code and receipts are **direct Codex work, not Bob-authored or
independent acceptance**. S03/S04/S06 retain their earlier public implementations
and PLANNED queue status; this work order did not start new work on those slices.

See the [current results index](../../../third_party/planning/power-spec-2/LOCAL_BUILD_RESULTS_2026-09-22.md),
[ordered status log](../../../third_party/runs/power-spec-2/codex-direct-build-2026-09-22/progress.log)
and [owner blockers](../../../third_party/receipts/implementation-2026-09-22/owner-blocked/README.md).
The following 2026-09-21 entries are historical checkpoints; the dated 2026-09-22
entries supersede their dependency and controller status.

## Historical 2026-09-21: completed local bootstrap work

| Slice | Actual change | Verification and limit |
| --- | --- | --- |
| B00 | Rebuilt Bob's PEP 660 editable installation from its current `setup.py`. The old `.pth` exposed only `src/`; the current package map already includes `tools` and standalone runtime modules. Removed the obsolete handwritten dual-root `.pth` workaround from `install.sh` and added isolated/outside-checkout CLI checks. | Editable CLI/version/help and `pip check` pass. Fifteen installation tests pass. A fresh current wheel is separately built and tested with local dependency reuse; a portable offline wheelhouse is still D01. |
| B01, local lifecycle | Split read-only `LoadedAdmittedPacketContext` from materialized `AdmittedPacketContext`. Authenticate the clean Git base before creating target leaves; publish a controller-side witness; bind/recheck target and ancestor identity, permissions, ownership and link count. Resume requires a controller-supplied witness digest. The run loop validates the feature and execution policy before materialization. | Sixty-five packet tests pass, including the original 39 and 26 added lifecycle/defect cases. The combined seven-file affected suite passes 274 tests. Actual OS mounts, distinct principals and full deployed recovery still require R00/R01 integration. |
| B02, local software | Added opt-in finite model/cost/turn/attempt/wall profile, shared durable reservation ledger, versioned admitted-profile and planner provenance bindings, actual SDK budget forwarding, no automatic finite transport retries, and no promotion of failed finite attempts. | Fifty finite-profile tests pass, including a fresh-controller-process restart and real SDK/local synthetic CLI success/timeout. Exact live endpoint/model/spend selection remains a preflight gate. |
| B03, local software | Removed process-name subprocess cleanup in favor of the SDK transport's own process; close SDK streams in their owning task. Fixed the dispatch import cycle that left stale MCP module bindings. Corrected source-policy tests to inspect executable AST nodes and distinguish the SDK transport from direct subprocess imports. | The original 193-test executor group passes within the 18-file combined suite: **609 passed, zero failed/skipped**, two deprecation warnings. Existing immutable-manifest/test-freeze/commit recovery tests pass. Deployed independent principals and an actual bounded public Bob campaign remain R00/R01. |

This is direct interactive bootstrap maintenance, **not Bob-authored code**.
The broken CLI/admitted path could not be assumed to repair itself, and no live
finite spec-2 model endpoint is yet qualified. No Bob model/provider call, paid
implementation campaign, dependency download, device access or clock mutation
occurred. Subsequent automated implementation requires the live endpoint preflight,
deployed controller boundary and appropriate dependency inputs.

See [the implementation receipt](../../../third_party/receipts/implementation-2026-09-21/bootstrap/README.md)
for commands, wheel identity, JUnit, retained failures, source diff and hashes.
The earlier [readiness audit](LOCAL_FIRST_BUILD.md) remains a dated before-state.

## B01 controller integration contract

1. `load_admitted_packet_context(...)` without a resume digest validates input
   documents/routes and baseline paths without writing the workspace. It returns
   a loaded assignment, which cannot issue a model prompt or execution binding.
2. After feature/attempt and execution-policy checks, call
   `materialize_admitted_packet_targets(loaded)`. It authenticates exact Git
   commit/tree/cleanliness, creates only admitted absent leaves, leaves existing
   baseline content intact and returns a materialized context.
3. A successful controller dispatch binding includes
   `target_materialization_sha256`. The witness is written outside the candidate
   workspace beside the controller execution profile as
   `bob-target-materialization.json`, with mode `0400` and one link.
4. For an authorized restart, set
   `BOB_PACKET_TARGET_MATERIALIZATION_SHA256` to the digest from the **successful
   protected controller binding**. Loading revalidates the witness and custody;
   preparation allows only authorized changed paths at the original attempt base.
   Never compute a digest from a discovered file to bless a failed/unknown attempt.
5. Implementation can change target content in place. Replacing target/ancestor
   identity, changing mode/owner, adding hardlinks or substituting symlinks fails
   custody checks. The first materialization handoff also requires original bytes.
6. A crash before a valid protected binding leaves partial files for diagnosis.
   It does not authorize cleanup, witness overwriting or automatic resume. The
   controller must recover or start an explicitly authorized fresh attempt.
7. Existing exact-commit intent recovery may run before normal resumed dispatch
   rejects an advanced HEAD. Only that recovery path may validate an already
   committed result; ordinary dispatch still requires the admitted attempt base.

The external runner must consume the witness, hold the appropriate controller
locks, enforce mounts/privileges and retain its binding before starting a model.
Filesystem identity checks are not a replacement for that deployment. The local
tests do not claim a real separate-principal or GPU environment was exercised.

## Finite execution and executor repair

Read [FINITE_EXECUTION.md](FINITE_EXECUTION.md) before configuring a campaign.
The new schema is a Bob-local development extension, not an invented normative
PPAT contract. Legacy v1 remains unchanged outside the finite route. At this
checkpoint no live model or spend allowance had been selected. The later
supervised-execution entry below records the initial operational selection;
synthetic test values are not a user budget decision.

[Finite executor receipts](../../../third_party/receipts/implementation-2026-09-21/finite-executor/README.md)
record the combined suite, retained development failures, current source identities
and a newly built wheel. Native SDK tests execute a local public synthetic CLI,
not a model service. No paid Bob call was made.

The parent transport retry loophole is closed for finite profiles. Unknown usage
retains the full pre-dispatch reservation and blocks reuse; known usage survives
controller process restarts. A failed finite implementation stops before the old
verification path could clear its error and accept files. OS supervisor/isolation
and provider billing enforcement still need deployed verification.

## Historical 2026-09-21: initial D00/D01 dependency closure

The next work is recovering exact cached artifacts and writing repeatable offline
recipes. Installed packages and extracted cache directories are not original wheel
archives. A clean runtime must use retained, hashed wheels with complete transitive
closure and no dependency overlay. The new current Bob wheel is an input to that
work; it is not itself a portable runtime.

D00/D01 still need complete selected artifacts. The last public GitHub probe failed
DNS; owner SST/harness sources and the complete normative release remain missing.
Independent recipe and pure-math work can proceed as described in the queue.

### Python subset acquired and exercised

D00 metadata expansion found 101 Bob runtime packages (including extras).
Thirteen exact compatible wheel archives were recovered from the HTTP cache;
88 packages remain missing. Conflicting locally built wheel identities are
recorded and excluded, not silently selected.

D02's property-test subset now has seven original cached wheels, a full hash lock,
a fresh Python 3.13.12 offline venv with no dependency overlay, passing `pip check`,
deterministic Hypothesis shrinking/replay, two negative installation checks and
15 artifact-recipe tests. The retained wheel archive is about 2.9 MB; Python and
system libraries still require separate custody/target reconstruction.
See [the Python closure receipt](../../../third_party/receipts/implementation-2026-09-21/python-closure/README.md).
D01 and the complete numerical D02 environment remain incomplete.

### Public software slices built and reconstructed

| Slice | Implemented local subset | Executed evidence and remaining gate |
| --- | --- | --- |
| S03 | Explicit hold/linear energy integration, complete-window coverage, typed invalid/unsupported inputs and absolute residuals. Reuses the existing unit registry. | 33 new tests plus five existing unit cases; seeded interval/refinement and fixed-bias properties. Final ScoreReport/ScoreProfile serialization remains S01. |
| S04 | Trial-bound same-device factorial contrasts, assigned-cohort absolute errors, noncompliance retention, achieved-grid checks, elasticity and joint experimental-block covariance. | 44 tests. Analytic interaction 4, absolute +7 bias, variance 7, shared-noise cancellation and extreme numerical range. Only complete two-level rectangular synthetic grids are supported; no scientific policy or physical accuracy is inferred. |
| S06 | Seeded public synthetic trial replay, requested/realized controls, frozen-work capture checks, bounded timeout/cancellation cleanup, fresh restoration readback and reservation ownership. | 50 tests. Full plans and started attempts survive cancellation in an in-memory journal. Actual harness interfaces, tied-domain/voltage discovery, state settling, hardware authority and durable acquisition remain open. |

The combined suite passes **132 tests, zero failures/errors/skips**. A second run
reconstructed the archived source and a fresh Python 3.13 environment from the
seven original cached wheels, with no dependency overlay or network. All six
deliberate source defects were detected by their intended assertions. See
[the reconstruction receipt](../../../third_party/receipts/implementation-2026-09-21/public-components-reconstruction/README.md)
for exact code/recipe/wheel identities, commands, JUnit, source archive and limits.
Earlier 38/88/132 counts overlap and must not be summed.

The first S04 run found a real covariance-validation rounding defect (130 passed,
one failed). Its source and output remain retained. The final scalar validity
check uses standard-library exact rational arithmetic; an additional extreme-range
case is included in the final 132-test suite. No public test was removed.

Application additions live in the existing `third_party/work/ppat-development`
scratch checkout. Its three tracked unit-contract files remain unchanged. This
does not establish the missing owner application root; the source archive ensures
the additions survive a handoff that excludes ignored scratch trees. The work is
direct interactive development, not Bob-authored or independently accepted.

### Numerical closure narrowed

The exact installed NumPy 2.3.5/SciPy 1.18.1/SALib 1.5.2/pytest 9.1.1 graph has
20 packages. Seven original compatible wheels were retained (six from the HTTP
cache plus the original SALib wheel); **13 archives remain missing**, including
NumPy and SciPy. [Exact list and attempts](../../../third_party/receipts/implementation-2026-09-21/numerical-closure/README.md).
The existing numerical environment remains usable under its prior native-test
evidence, but full portable D02 closure is not complete.

## Historical 2026-09-21: supervised execution waiting for connectivity

The owner explicitly requested an ongoing goal and persistent supervised Bob
execution. That goal is active. A finite foreground supervisor was launched in
tool session `76032`; separate observations show its heartbeat and network-probe
count advancing. Its state is **blocked_network**, not building: this sandbox
cannot resolve `api.anthropic.com`, no provider session has started and the first
queued S05 feature remains pending. No model charge is evidenced.

The new supervisor reuses Bob's CLI/executor and durable finite ledger. It runs a
bounded live model preflight before feature dispatch, tracks the owned process,
stops on failure and never resets statuses/budgets or restarts unknown calls.
The affected suite passes **86 tests**; the isolated candidate baseline passes
the original **132 tests**. A current wheel includes the supervisor.

The queued public energy-accounting child has explicit source/test paths, the
10 J baseline oracle and missing/duplicate/unit/overflow rejection checks. Its
native spec-linter score is 1.0 after a retained syntax correction; confidence
values remain unmodified. The initial prepared profile selects exact Sonnet
`claude-sonnet-4-5-20250929` with $5/40-turn/six-session/30-minute ceilings. Live
model qualification is still pending, and this API-key budget is separate from
the Codex session usage limit.

Host-level persistence is not available here: systemd/tmux access is denied and
a detached-process probe did not survive. A concrete service unit is staged, but
it is not installed, and tool-session survival is not a claim of survival beyond
the usage limit. See [operating state and instructions](SUPERVISED_RUN.md) and
[the full receipt](../../../third_party/receipts/implementation-2026-09-21/supervised-runner/README.md).

### Native runner integration repaired before first dispatch

The first monitor was stopped cleanly, with no provider session or ledger, after
review found that its settings would hit the legacy partial-hardening gate.
The public app's non-default test directories also bypassed native test discovery.
An explicit version-2 public controller profile now binds those paths and the
app's Python interpreter. It preserves rejection of mixed independent/admitted
execution requests. Native tests found and fixed misplaced pytest arguments and
legacy warning promotion of failing suites on this public route.

The affected suite now passes **198 tests, zero failures/errors/skips**. Bob's
actual snapshot and full-suite gate also ran against the prepared candidate and
passed all **132 original tests**. A broad legacy F051 test omitted an already
mandatory ownership-map argument; that failure and a 120-second broad-suite
timeout remain retained, not counted as passes. The database implementation is
byte-identical to HEAD. See [the repair receipt](../../../third_party/receipts/implementation-2026-09-21/public-runner-integration/README.md).

Controller `supervised-2026-09-21-02` is running in tool session `5204`, reusing the
original task, database and finite profile/ledger path. It remains blocked by DNS;
no feature-building call has started. The prior controller and all failures are
preserved. The current wheel was built from fresh staged source with the selected
setuptools 82.0.1; an ambient-backend build was rejected and retained separately.

The [source-cache audit](../../../third_party/receipts/implementation-2026-09-21/source-cache-audit/README.md)
found 56 original source distributions in 535 pip cache bodies. All exact matches
already had retained wheels, so the missing dependency counts remain unchanged.

### External finite-model policy also repaired

The follow-up [external-policy receipt](../../../third_party/receipts/implementation-2026-09-21/finite-external-policy/README.md)
resolves the legacy Opus-only check discovered during native integration review.
An external/admitted route now requires the exact model in its valid finite
profile; legacy execution without a finite profile keeps its Opus requirement.
The wrapper, independent writer, evaluator, hermetic mode, disabled decomposition,
test interpreter, database/session custody and outside-candidate budget checks
remain mandatory. An invalid profile cannot fall back to legacy execution.

**133 affected tests pass**, including 17 new policy cases; counts overlap the
previous suites. The fixture wrappers were not executed and establish no real
isolation. A fresh wheel contains this follow-up and the prior public integration
repair. Live model identity, persistent host deployment and independent execution
remain blocked by unavailable external capabilities.

### Historical goal blocked on external capabilities

The same missing model connectivity and host-service access persisted across three
consecutive goal turns. The latest [capability audit](../../../third_party/receipts/implementation-2026-09-21/blocked-capabilities/README.md)
re-polled live tool session `5204` and repeated the denied systemd/tmux checks.
The monitor is alive within its finite deadline, but no model worker or provider
session has started; the S05 feature remains pending. The implementation goal is
blocked, not complete. More local polling cannot supply the missing capabilities.
The retained monitor may proceed if connectivity returns before its wall ceiling;
survival beyond the tool session is still unproven.

## 2026-09-22: sequential direct implementation

The owner enabled artifact networking and instructed direct Codex work, one slice at a time. This supersedes the historical running/blocked monitor descriptions above: all controllers are stopped; controller 04 reached the endpoint and was rejected for insufficient credit. No campaigns will be relaunched. This work is not Bob-authored or independent acceptance. Owner-only slices are recorded BLOCKED_OWNER in the local queue.

B02/B03 follow-up: explicit auth/billing classification now precedes model checking, and native SDK early-error cleanup is repaired. Public affected coverage passes 168 tests; a fresh wheel is retained. [Tests, failures and source evidence](../../../third_party/receipts/implementation-2026-09-22/bob-provider-errors/README.md). The local queue can now track evidence-backed software status while rejecting dispatch/acceptance claims and multiple in-progress slices.

### S05 completed locally

Energy ownership, block UQ/coverage/sharpness, SciPy calibration rank/covariance and full-region reconstruction pass **196 public tests**, including the previous 132. Seven deliberate mutations are detected. [Source, commands and retained failures](../../../third_party/receipts/implementation-2026-09-22/S05/README.md). [Decisions L002-L006](decisions-and-questions.md) specify assumptions and remaining gates. Installed dependencies are reused explicitly; D02 will close and replay the portable numerical environment. Direct Codex work, not Bob-authored or independently accepted.

### S00 local workspace complete; authoritative contract recovery partial

[application/](../../../application/README.md) now packages the public components under `power_spec2`. Four layout/authority checks and **196 installed-wheel tests** pass from outside the source tree; a fresh wheel, sdist and source snapshot are retained. Old unit tests and provider trees are preserved. Nine supplied authority files are hash-bound; 19 missing authority entries (18 unresolved referenced links) remain explicit. The old normative document is not silently adopted. [S00 receipt](../../../third_party/receipts/implementation-2026-09-22/S00/README.md). S00 is PARTIAL only for missing final authority; local workspace work is complete, and conservative development contracts can proceed.

### S01 local contracts and projections complete; normative integration partial

Six separately versioned development documents, strict JSON/path/hash checks, fresh allowed-input projection, grouped split protection and exact prediction bindings/coverage are implemented. **58 new tests, 63 installed contract tests and four detected mutations** pass. [S01 evidence](../../../third_party/receipts/implementation-2026-09-22/S01/README.md). No W/C semantics, final thresholds or acceptance signatures are invented. Complete normative compatibility and deployed custody remain blocked; local schemas explicitly cannot qualify a run. D02 will combine numerical and schema dependencies in a clean Python 3.13 replay.

### S02 local submission/provenance/attempt scope complete

Exact content-addressed submission closure and a transactional finite attempt ledger now preserve failures, interruptions and partial artifacts. Parent identities and expected work coverage are frozen; native/normalized output replay and developer self-acceptance reject. **35 new tests, 98 installed contract tests and four detected mutations** pass, including real subprocess crash/commit boundaries and concurrent budget contention. [S02 receipts and retained failure](../../../third_party/receipts/implementation-2026-09-22/S02/README.md). Trusted external anchors, signer selection and actual separate-principal custody remain external gates; these local results do not assert independent acceptance.

### D00 first-wave artifacts acquired; native source closure partial

Network acquisition now succeeds. Retained **27 app/numerical/test wheels, 101 Bob wheels, four build-tool wheels**, available source archives, exact Python 3.13.12/3.14.2 archives and the officially hash-verified existing Claude CLI. A **391-file, 1.14 GB** relative-path bundle restores with full hash verification. **38 acquisition/archive/bundle tests pass**. [D00 evidence, source gaps and bounded failures](../../../third_party/receipts/implementation-2026-09-22/D00/README.md). Hypothesis's exact source release remains unavailable; native source rebuild/target closure is not inferred. Selected binary locks are complete and ready for D02 then D01.

### D02 complete: clean offline numerical and test closure

The exact Python 3.13.12 archive and 27 hash-locked wheels reconstruct a fresh numerical/schema/test environment. A separate frozen backend builds the app wheel. **289 combined application tests pass**, along with **190 native SALib passes and one retained upstream xfail**. `pip check`, import custody and deterministic property replay pass; missing wheel, wrong hash and missing native library reject. [D02 source, locks and execution receipts](../../../third_party/receipts/implementation-2026-09-22/D02/README.md). This replaces the prior installed-overlay limitation for combined local execution; target/physical qualification and source-rebuild limitations remain explicit.

### D01 complete: portable Bob installation and local executor validation

The exact Python 3.14.2 archive, 101 runtime wheels, current source wheel and separate test closure install offline without overlays. **183 installed tests**, 13 imports, four resources, CLI/help/version and pip check pass; missing wheel, wrong hash and wrong platform reject. [D01 receipts and portable extension](../../../third_party/receipts/implementation-2026-09-22/D01/README.md). No model campaign was launched; owner funding remains required.

### D08 complete: optional native reference adapters

Fresh hash-verified DRAMPower and MGPUSim execution now feeds strict energy/SQLite adapters. **41 new cases and 330 combined installed tests pass**, with four caught mutations; native reruns pass 336 DRAMPower tests, four CLI cases and 14 MGPUSim layer/grid specs. [D08 evidence](../../../third_party/receipts/implementation-2026-09-22/D08/README.md) preserves the generated-log preflight failure, DDR/LPDDR-only and MI300A/gfx942 ceilings, installed-SDK defects and MCCL exclusion.

### D03 complete: bounded open-component framework selection

HWComponents is the conservative development selection: 13 native tests pass and explicit models avoid ambient discovery. Both native Python APIs reproduce **26 pJ dynamic + 6 pJ baseline**; 13 comparison tests and three mutation checks pass, including fresh offline replay. [D03 receipts](../../../third_party/receipts/implementation-2026-09-22/D03/README.md) retain Accelergy’s one negative-test mismatch and two hierarchy CLI failures. No physical AMD content is claimed.

### D06 complete: native Perfetto import and gap-preserving observations

The pinned native processor runs local SQL through an explicit binary path/hash. **31 new tests and 361 combined installed tests pass**, plus four caught mutations and an installed native smoke. Two known slices/four samples preserve a declared gap that existing integration rejects. [D06 receipts](../../../third_party/receipts/implementation-2026-09-22/D06/README.md) retain the strengthened hash mutation test and exact limits: public Chrome subset only, no first-use fetch or target clock alignment claim.

### D09 complete: CPU-executed public GPU-frequency reproduction

EnergAIzer’s unchanged numerical estimator modules reproduce **4/4 A100 softmax frequency cells** in two clean environments with identical rows. **18 scoped tests and four mutations pass**; real config drift/missing-data executions reject. [D09 receipts, errors and portable packet](../../../third_party/receipts/implementation-2026-09-22/D09/README.md) disclose two lazy-import packaging changes, the blocked full Torch frontend, all imported target profiles and calibration overlap. This is public reproduction evidence, not blind or independently accepted V-04 qualification.
