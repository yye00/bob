# Use Bob to complete the local software before MI355

Start with the [26-slice queue](BUILD_QUEUE.md), backed by
[local-build-queue.json](local-build-queue.json), and the cross-checked
[46-package/input inventory](../../../third_party/planning/power-spec-2/PACKAGE_READINESS.md).
The [acquisition plan](../../../third_party/PRE_MI355_ACQUISITION.md) names the
missing sources and transitive closure work. This is the detailed handoff for the
implementation model; no Bob campaign was started during planning. Subsequent
[implementation progress](IMPLEMENTATION_PROGRESS.md) records actual bootstrap
repairs separately from the before-state and planned work below.

## First executable work

1. **B00–B03: repair the runner.** The console entrypoint currently raises
   `ModuleNotFoundError: No module named 'tools'` both from the parent workspace
   and `bob/`. The current wheel works with a temporary dependency overlay, which
   is a different installation mode. Diagnose editable packaging instead of
   accepting `PYTHONPATH` as the portable fix. Repair admitted-packet custody,
   selected-model/finite-budget plumbing and the executor regressions next.
2. **D00–D02: make dependency closure reconstructible.** Write reviewed acquisition
   and offline-build recipes, recover existing artifacts, and fetch missing
   selected inputs on a network-capable acquisition host. Freeze separate Bob and
   application environments. Do not move all providers into Bob's Python 3.14.
3. **D03–D10: build selected native paths locally.** Open-power comparison,
   compatible SST and owner model, Perfetto, AMD source builds, scoped old native
   adapters, CPU scientific reference and target workload preparation have
   separate acceptance checks. Each provider gets its own bounded child.
4. **S00–S07: implement the application.** Recover complete contracts and choose
   the app root; implement schemas, projections, provenance, immutable submission,
   deterministic scores, UQ, control replay and native action binding. Reuse the
   exact public oracles in [VALIDATION.md](VALIDATION.md).
5. **R00–R02: rehearse the result.** Verify deployed roles on capable local CI,
   run the synthetic application through bounded Bob execution, then reconstruct
   the selected software from a portable handoff bundle.

The queue is a software-work decomposition under the original 41 tasks plus
migration tasks. Its local prerequisites do not change scientific dependencies.
For example, an upstream package can compile before complete F-01 schemas exist;
that compilation cannot claim canonical F-04 acceptance prematurely. A synthetic
pipeline can exercise P-01 interfaces without qualifying P-01 predictions.

S03's pure scoring functions and S06's public control replay can be developed
before the missing schemas arrive. Their final app bindings wait for S01 through
separate `integration_requires_tasks`. Likewise, D00/D02 dependencies refer to the
particular child's required artifacts, not completion of every acquisition in the
catalog. Existing local numerical tools can support early oracle work while the
portable environment and property-test additions are being prepared.

## Bootstrap without a circular dependency

The broken admitted-packet path cannot be assumed to execute its own repair.
Use a working, independently bounded public Bob maintenance route if its actual
model and resource controls pass preflight. The tested installed wheel is a
candidate bootstrap artifact, not proof of a healthy model execution path.
If no bounded Bob route is usable, perform the narrowly scoped bootstrap repair
with the downgraded interactive coding model, record the maintenance exception,
then have repaired Bob execute the remaining queue. Do not create another generic
orchestration platform or label direct maintenance as a Bob-authored attempt.

`atomic_packet_planner.py` currently pins `claude-opus-4-8` and uses unlimited
turns in the historical profile. Editing model aliases in `bob_build.env` is
insufficient. B02 must prove that the exact selected model and finite limits reach
the real call sites. The runtime requirement is currently **claude-code-sdk**;
an absent **claude-agent-sdk** distribution is not evidence that the declared
SDK dependency is missing and does not justify an unrelated SDK migration.

## Materialize one bounded child at a time

Use the existing Bob packet/runner interfaces after bootstrap; these planning
JSON files are not directly accepted Bob runtime packets. Before dispatch, the
controller resolves the following fields using the recovered contracts and
healthy versioned spec-2 profile:

| Field | Required resolution |
| --- | --- |
| Parent and objective | One queue slice, canonical parent task and one observable code/build output |
| Source authority | Exact current spec passages; actual contract version; native source and fixture identities |
| Workspace | Clean base commit/tree plus captured allowed patch; exact application or Bob root; explicit read/write paths |
| Dependencies | Actual acquired byte hashes and selected package state; no unresolved pin or missing native binary |
| Actor/model | Exact provider/model/runtime; actual dispatch verification; no alias fallback or inherited Opus default |
| Budget | Finite model turns, money, wall time, CPU/RAM/storage, repair attempts; zero blind reveals for this public queue |
| Validation | Existing native tests plus named independent positive/boundary/failure/mutation checks; expected outputs decided before code |
| Submission | Immutable output manifest, source diff, raw commands/results, attempts/skips/failures and reproduction recipe |
| Review | Separate validator identity and actual access boundary; local software acceptance level only |

The JSON suggests initial ceilings of 40 model turns, two repairs, 30 minutes,
four CPU threads and 8 GiB RAM per small child. These are planning defaults, not
cost approval or promises that every native package fits. `model_id` and
`max_cost_usd` remain null until dispatch policy selects them. Heavy provider
builds get separately reviewed finite resource profiles. Decompose oversized
work instead of silently lifting limits or permitting unbounded continuation.

A package acquisition child can fetch into its acquisition workspace. An
implementer or predictor receives approved immutable inputs and offline build
commands. Obtaining dependencies is distinct from reading sealed measurement
labels. Real confidential source must stay within its permitted environment.

Suggested per-child implementation prompt:

> Read this queue slice, its canonical task, cited current spec and exact public
> validation oracle. Confirm the packet's resolved model, finite limits, source
> hashes, input/output paths and dependency states. Reuse the identified code and
> native build/test entrypoints. Implement only this child. Run its listed tests
> plus affected regressions; preserve failures, retries and exclusions. Submit
> immutable code/results for independent review. Do not expand scope, download
> during offline validation, fabricate a native run, invent missing contract
> semantics, weaken assertions or claim physical accuracy from synthetic tests.

## Concrete validation before leaving this host

- Fresh wheel **and** supported editable CLI work from outside their checkout.
  The Bob admitted-packet and affected executor groups pass without suppressing
  failures. A real bounded public task records the intended downgraded model.
- Selected packages install/build offline from complete recoverable artifacts;
  consumer imports/links/CLIs work independently of source cwd and mutable caches.
  One removed dependency makes the corresponding verification fail.
- Native providers run supported examples before adapters; adapters preserve
  units, boundaries, work and unsupported cases. No empty native suite counts as
  verification. DRAMPower remains non-HBM; MGPUSim retains its supported ceiling.
- Exact score/response/covariance/accounting oracles pass along with injected
  wrong-unit, bias, slope, missing-work and leakage defects. Hidden-label changes
  leave predictions invariant while a nondegenerate score changes.
- Device protocol replay handles timeout, cancellation, partial capture, readback
  and restore failures. Replay is visibly synthetic; target commands and feasible
  controls are discovered on the real approved device.
- Actual local/CI permissions deny forbidden label, scorer, network, device and
  shared-cache access. This sandbox's denied namespace probe is not a passing
  isolation result; a separate capable deployment is needed.
- A clean host reconstructs the selected stack and runs no-device public smoke.
  The handoff lists remaining private-source and live-target tests rather than
  silently filling them with mock success.

## Maintain and verify the handoff

```bash
python3 bob/docs/power-spec-2/maintain_plan.py check
python3 bob/docs/power-spec-2/maintain_plan.py self-test
python3 bob/docs/power-spec-2/maintain_build_queue.py check
python3 bob/docs/power-spec-2/maintain_build_queue.py self-test
```

After changing the package inventory or local queue, run
`python3 bob/docs/power-spec-2/maintain_build_queue.py render`, then check again.
The checks establish planning consistency, not dependency admission or task
execution. Actual new probes are in the
[acquisition receipt](../../../third_party/receipts/local-readiness-2026-09-21/acquisition/README.md);
the prior expensive native suites were not rerun for this documentation change.
