# Power spec 2 migration and implementation handoff

Planning baseline revision 1, 2026-09-21. **The owner's 2026-09-22 direct work
order is finished within local scope:** see [actual progress](IMPLEMENTATION_PROGRESS.md)
for implemented slices, installed test results, offline dependency closure and
remaining owner gates. No slice is currently IN_PROGRESS.
The planning JSON below remains a baseline, not runtime acceptance or scientific qualification.

[Bob controllers are stopped](SUPERVISED_RUN.md). Controller 04 reached the API
but lacked credit; no campaign was relaunched. Artifact networking is available,
and the owner authorized direct Codex implementation while funding is unresolved.

This is the current migration entrypoint for `bob/` and `third_party/`. The supplied
[`power-spec-2/`](../../../power-spec-2/README.md) v0.4.1 documents supersede
`power-spec/` for new implementation. These local plans add implementation detail;
they cannot grant permissions, fill absent normative definitions, or approve tolerances.
The user requested this planning pass before moving to a less capable implementation model.

## Read and execute in this order

1. This document: authority, sequence, boundaries and handoff rules.
2. [Source snapshot](source-snapshot.json): exact imported bytes and missing authorities.
3. [Bob changes](BOB_MIGRATION.md) and [third-party changes](../../../third_party/POWER_SPEC_2_MIGRATION.md): current code/assets, concrete changes and reuse.
4. [Validation plan](VALIDATION.md): public oracles, negative cases, deployed controls and physical gates.
5. [Planning backlog](backlog.json) and [generated task packets](TASKS.md): all 41 supplied tasks plus four local migration prerequisites/cutover tasks.
6. [Build locally before MI355](LOCAL_FIRST_BUILD.md): fresh native/package evidence,
   current Bob failures, CPU implementation order and exact target-only gates.
7. [Use Bob for the local build queue](BOB_LOCAL_BUILD_QUEUE.md): 26 concrete
   software slices, the [46-package/input inventory](../../../third_party/planning/power-spec-2/PACKAGE_READINESS.md)
   and [acquisition work](../../../third_party/PRE_MI355_ACQUISITION.md) needed
   before target migration. Start here for the downgraded model's next code task.

The local-first cross-check rebuilt/tested retained native packages and the current
Bob wheel. Its [separate receipts](../../../third_party/receipts/local-readiness-2026-09-21/README.md)
supersede historical operability assumptions for the tested configurations only.
Every backlog task now names its pre-MI355 work and remaining input/device/deployment
gate. Canonical task status remains PLANNED; the separate
[local queue](BUILD_QUEUE.md) records implemented, partial and owner-blocked slices.
Local builds do not confer scientific acceptance.

`backlog.json` is a **local planning projection**, not the missing release's
`evidence/backlog.json`, a Bob runnable feature spec, or a controller-admitted packet.
The source table's dependencies are preserved separately from additional migration
and conditional gates. All tasks remain PLANNED and `dispatch_ready` is false.
Packets must be narrowed to actual file paths, approved policies, runnable native
commands and a distinct validator before dispatch. Never feed this whole roadmap
to `bob run --all` or use a freeform feature synthesizer to invent missing contracts.

## Source intake: what exists and what does not

The import has nine flattened Markdown files. It does not contain `docs/`,
`evidence/`, `schemas/`, `agent_tasks/`, `tools/`, `tests/`, `archive/`,
`IMPLEMENTATION_STATUS.md`, the referenced normative contract, or the QA logs.
The old `power-spec/normative-contract.md` is not the new missing contract.
In particular W0/W1/W3 and C0/C1 must not be reconstructed from old E-profile names.
The imported QA report's “53 tests / 15 groups” is a historical reported result;
the code and logs to reproduce it are absent. No supplied-provider execution is
established by those checks.

For the supplied substantive documents flattened at the root, use their actual
paths rather than the absent `docs/`, `qa/` or `evidence/` paths advertised in links.
Preserve source bytes; the snapshot maps these relocations. The plan checker verifies
the mapping and source identities. It reports missing original authorities as known
gaps; passing the plan checker cannot turn those gaps into fulfilled requirements.

MIG-00 must locate the complete v0.4.1 release in approved local sources first,
or record which artifacts require the owner/source custodian. Reconcile its actual
backlog, schemas, policy vocabulary and task packets against this projection before
schema-dependent implementation. Discovery, existing native-test inventory and
bounded public fixtures can continue independently. A missing dependency blocks
only dependent work, not all D1 discovery.

## Material changes from the previous plan

| Previous direction or assumption | New implementation obligation |
| --- | --- |
| Old DF/M0/P0–P3 and 200 F-R10 factory packages drive scope | New 41-task D1–D6 graph drives scope; old tasks/attempts remain historical with explicit mapping or retirement |
| Thermal solver, training/ranking-first drift | No thermal workstream; ordinary observed environmental state may delimit experiments; no new training or ranking product |
| Large factory rebuild / witnessed regeneration of every helper | Reuse Bob/CI, native tests, harness, parsers and proven helpers; independently qualify them for the new purpose |
| Mandatory model/vendor or Opus identity and unbounded continuation | Versioned executor task interface; explicitly selected model and finite repair/resource/reveal policy; no silent fallback |
| SST/IPPM as universal hosts | Reuse existing AMD SST first where suitable; an open non-IPPM power path is required; other providers need not embed into SST |
| Native compilation or local synthetic pass implies target readiness | Distinct documentation, operability, physical output and blind-transfer evidence levels |
| Same-card clock holdout treated as architecture transfer | X-01…X-05 is first-class D2a frequency falsification, with actual controls, work invariance and joint uncertainty |
| Timing input can be called timing prediction | Field/ancestor-level W/C exposure contract; measured timing and power-equivalent inputs change the claim |
| Extra reviewer identity suffices for independence | Separate deployed credentials, storage, worktrees and privileges; deterministic scoring and fresh reproduction |
| High-current mixed with ordinary control | D4 follows single-GPU qualification; D5 requires both B-04 and H-01; D6 follows D5 |

Keep existing anti-leakage, hash binding and failure retention where useful. Replacing
the old authority does not authorize exposing labels, dropping tests or rewriting
signed history. No old success automatically closes a new task; reuse needs exact
identity, scope and independent revalidation.

## Planning decisions and unresolved facts

These are implementation choices for this handoff, not newly discovered spec rules:

- Keep Bob generic. Add a versioned power-spec-2 task/profile adapter and policy gate
  around its existing runner; leave unrelated projects' behavior compatible.
- Keep application adapters/model/scorer code outside Bob core. MIG-00 identifies
  the actual existing application repository/worktree before choosing its layout.
  The legacy lock's `app/src/power_sim/contracts/unit_profile.py` names one historical
  child only; it does not establish the new project's source root.
- Version replacement contracts rather than silently reinterpreting `ppat.*.v1`,
  legacy databases, digests or frozen receipts. No in-place historical DB rewrite.
- Use the existing Python test ecosystem and standard schemas/isolation/statistics;
  choose the smallest applicable provider subset after native evidence.
- The lower-cost implementation model is selected at execution time. Record its exact
  provider/model/runtime, run its task-profile preflight, and keep that identity in
  each attempt. No fixed model name or budget is invented here.

| Gap | Resolution owner and route | Work gated |
| --- | --- | --- |
| Complete normative contract, evidence profiles, schemas, registry and official backlog absent | MIG-00 source discovery; obtain missing original artifacts if unavailable | Final envelope semantics, automatic dispatch, qualification |
| Actual application tree, private SST model, physical harness and MI355 configuration not established | F-02/F-03/F-04 inspect approved repositories and native interfaces | Target adapter/control and physical claims |
| Approved precision/tolerances/cost limits/feedback budget absent | Q-01 proposes from independent pilots and utility policy; appropriate owner approves once | QUALIFIED status; descriptive evidence proceeds |
| Hardware host/clock-setting authority absent | A-02/X-01 discover policy and capabilities; explicit missing authority to owner | Device use and mutations; no hardware commands in this planning pass |
| Missing-policy status differs between supplied documents | F-01 resolve `INSUFFICIENT_ACCEPTANCE_POLICY` versus `UNAPPROVED_ACCEPTANCE` in a reviewed contract | Authoritative enum emission; both mean no qualification meanwhile |
| Existing source locks/receipts predate the migration | MIG-02/F-10 inventory and qualify a new manifest separately | New dispatch/build admission; historical bytes remain intact |
| Legacy Bob model aliases override requested downgrade | MIG-01/A-01 inspect `bob_build.env`, environment/profile plumbing and tests | New model dispatch until exact identity check passes |

Do not ask the owner for discoverable package versions, actual supported dtypes,
available controls or trace fields. Do ask for genuinely absent permission,
scope/utility decisions and unavailable authoritative artifacts after discovery.

## Ordered implementation waves and stopping gates

Within a wave use the dependency graph, not table order. Development and acceptance
are separate: a public synthetic implementation can be built while an external
qualification dependency is pending, but its result cannot be marked qualified.

| Wave | Work | Exit evidence |
| --- | --- | --- |
| 0 — migration baseline | MIG-00 and MIG-02; inventory all Bob/third-party directories, preserve dirty state, source gaps, old manifests and historical task/DB identities | Source/asset delta and authoritative-input availability; no fake “complete import” |
| 1 — contracts and reuse | F-01; F-02/F-03/F-04; MIG-01/A-01/A-03; F-10; native optional reference discovery | Frozen fixture/policy split, native test inventories, versioned bounded packets and model identity |
| 2 — evidence boundary and real workload | A-02/F-07; F-05/F-06/F-09; X-01/X-02; Q-01; U-01; selected V tasks/V-04 | Real privilege denials, actual work/metrology, allowlisted inputs, deterministic scorer, early UQ and costs |
| 3 — D1 gate and D2a | F-08; K-01/K-02; C-01/C-02 when applicable; P-01; X-03/X-04/X-05; P-02 | Frozen absolute predictions plus paired clock/interaction scores and approved evidence adequacy |
| 4 — D2b | P-03/P-04/P-05; U-02 only where numerical methods require it | In-flight work and ordinary PMFW causal validation, scoped single-GPU report |
| 5 — D3 | B-01 can start after F-07; B-02 and B-03 after P-05; B-04 after both | Workload, true architecture and joint heldouts with W/C and data-exposure ablations |
| 6 — later deliverables | H-01 after P-05 (can run alongside D3 under its own authority); M-01 after B-04 AND H-01; N-01 after M-01 | Distinct high-current, multi-GPU and multinode qualification |
| Migration cutover | MIG-03 after its recorded policy/workflow/evidence/dependency gates | New execution entrypoint/profile and rollback rehearsal; no implication that D2–D6 are complete |

Special edges are mandatory: V-04 selects at least one applicable completed native
reference (not all optional NVIDIA packages); C-02 gates full-workload claims using
selected-region composition; U-02 gates claims that use derivatives/approximate
inference. Q-01 gates numerical acceptance, not read-only discovery. A generic
native simulator build need not wait for every MI355 field. Optional NVIDIA failures
do not stop unrelated AMD branches. D4 requires separate experimental authorization.
These conditional rules apply to every claimed output, including P-04 and H-01,
not just the representative task edges. Preliminary K-02 fitting artifacts may
feed U-02 validation before their numerical qualification; distinguish artifact
completion from claim acceptance to avoid a circular dependency.

## Per-packet contract for the implementation model

The generated task pages are planning packets. Before assigning one implementation
slice, the controller must produce a versioned admitted packet with:

1. One objective and observable output; exact new spec passages and requirement IDs.
2. Actual base commit/tree, source/config/data hashes and resolved application root.
3. Exact input paths/fields/ancestors with access classes; exact allowed output paths.
4. Existing code to reuse, native test inventory and explicit skipped/unsupported cases.
5. Command argv, cwd, environment allowlist, executable/model identity and resource profile.
6. Approved finite attempts, timeout/cost/storage and blind-feedback limits. Every attempt
   consumes the appropriate ledger entry, including launch failure/timeout/partial output.
7. Expected artifacts, public deterministic oracle and designated independent defect tests.
8. A separately instantiated validator identity, policy version and acceptance level.
9. Typed failure/blocked conditions and cleanup requirements; no alternate success path.

Split a broad task into atomic child packets when it cannot fit these fields; keep
parent coverage and dependencies intact. The implementation model may not expand
access, invent tolerances, silently drop an acceptance item, regenerate trusted
expected outputs from its own implementation, or downgrade an existing test.

Suggested handoff prompt:

> Read `bob/docs/power-spec-2/README.md`, the assigned task in `TASKS.md`, the relevant
> migration and validation sections, and only the cited current spec files. Inspect
> and reuse the named modules/native tests. Confirm your admitted packet's exact
> input/output paths, base, model identity, policy and separate validator. Implement
> only this bounded slice. Run its positive, boundary, failure and mutation checks;
> preserve every attempt and raw result. Report changed files, actual commands,
> evidence hashes, unsupported cases and unresolved gates. Do not implement from
> historical `power-spec` instructions or mark acceptance from self-review. If a
> required definition or privilege is missing, identify that exact dependency and
> continue only independent authorized work.

## Validation and evidence contract

The validation plan defines 17 test families, used as traceability IDs in the
backlog. Every produced artifact gets cheap schema/unit/provenance/scope/exposure/
finite-output/coverage checks. Run affected component/native regressions on changes,
independent integration and security checks at the evidence boundary, and costly
physical/transfer tests only at their relevant milestones. Tests use nondegenerate
fixtures with stated assumptions; absence of a statistically significant error is
not accuracy proof.

Each attempt records: task/child/attempt IDs, status and timestamps, base/patch and
all input/output hashes, actor and runner identity, model/provider/runtime versions,
policy and scorer versions, full argv/cwd/environment identity (no secrets), raw
stdout/stderr/exit/timeout and test collection counts, native outputs, work/coverage,
cost, failures/retries/skips, cleanup, validator verdict and reproduction recipe.
Hash lineage is necessary but cannot prove sensor origin. Never commit protected
labels or credentials into these public planning files or developer worktrees.

Keep four concepts separate:

- Task progress (`PLANNED`…`SUBMITTED`…`ACCEPTED`) is workflow state.
- Evidence pipeline state (acquire…seal…freeze…score…release) controls data access.
- Native operability and synthetic/local verification are limited evidence levels.
- Scientific status (`QUALIFIED`, failure, unsupported or blocked) requires the
  approved scorer/profile and adequate independent evidence for each claimed output.

## Cutover, compatibility and rollback

Snapshot the parent repository, Bob gitlink commit, all selected submodule commits
and dirty tracked/untracked metadata before implementation. Preserve the existing
dirty MGPUSim `go.sum`; use a fresh worktree for qualification. Do not reset source
trees, delete derived histories, reuse burned attempt IDs or make a legacy receipt
attest new bytes. A new source manifest is reviewed as a new version.

Use a separate project/task namespace and database for v0.4.1, with an explicit
read-only legacy-ID crosswalk. General Bob tests and old packet rejection behavior
remain regression targets. Legacy receipts can establish only their original scope.
If compatibility conversion is required, test it against disposable copies with
backward reads, idempotency, interrupted writes and rollback; no live DB mutation
belongs in a planning or discovery step.

Cut over only the new profile/entrypoint after MIG-03 gates pass. Rollback restores
the previous software/profile reference and stops new dispatch; it never relabels
old outputs as qualified, deletes failed attempts or unseals data. Restore scripts
and `RESUME.md` still reference the historical workspace and are explicit follow-up
surfaces at cutover; this planning pass does not execute them or rewrite archives.

Bob is a nested Git repository. Review its diff with `git -C bob diff`; inspect
untracked planning artifacts as well. A future integration must record the Bob
commit and parent gitlink update together. Nothing in this planning pass is committed.

## Check and maintain this planning bundle

From the `power` workspace root, with Python 3.11+:

```bash
python3 bob/docs/power-spec-2/maintain_plan.py check
python3 bob/docs/power-spec-2/maintain_plan.py self-test
python3 bob/docs/power-spec-2/maintain_build_queue.py check
python3 bob/docs/power-spec-2/maintain_build_queue.py self-test
```

After editing `backlog.json`, regenerate the task view and recheck:

```bash
python3 bob/docs/power-spec-2/maintain_plan.py render
python3 bob/docs/power-spec-2/maintain_plan.py check
```

These commands validate planning identities, the exact 41 source rows, DAG and
conditional edges, requirements/test mappings, task completeness and generated
view freshness. They neither invoke Bob nor implement a production validator. Do
not run the missing release's advertised `tools/check_release.py` command here or
claim it passed. [Planning verification receipt](PLANNING_CHECKS.md) records only
checks actually performed in this planning pass and remaining limits.
