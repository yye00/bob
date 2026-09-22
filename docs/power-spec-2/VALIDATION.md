# Power-spec-2 validation and verification plan

Status: implementation handoff, planning only. This document defines work to implement and evidence to collect; it does not report execution or scientific qualification. Read the [migration entrypoint](README.md), [Bob migration inventory](BOB_MIGRATION.md), and [third-party migration plan](../../../third_party/POWER_SPEC_2_MIGRATION.md) with this plan.

Subsequent local build/test executions are recorded separately in the
[pre-MI355 cross-check](LOCAL_FIRST_BUILD.md) and its linked receipts. They do not
turn the proposed scientific tests below into executed or accepted tasks.

The governing input is the available v0.4.1 text under [power-spec-2](../../../power-spec-2/README.md). Its referenced normative contract, schemas, W/C exposure definitions, machine backlog, generated task packets, QA tools and logs are absent from this checkout. Resolve these missing authorities before freezing their dependent production contracts. The test-family IDs below are local planning identifiers, not recovered official requirement or test IDs. Do not reconstruct missing normative requirements from the retired `power-spec` corpus.

## Evidence levels and conditions for acceptance

Keep these levels separate in every task and report:

1. **Planning/document checks:** source coverage, dependency consistency, valid planning envelopes and honest blocked status. They confer no runtime or hardware claim.
2. **Synthetic/component evidence:** exact mathematical examples, properties, negative cases and fault injection. Label inputs and results `synthetic_oracle`.
3. **Native operability:** a pinned real provider builds and runs its discovered native tests and selected supported case. Success establishes only that exact configuration's operability.
4. **Deployed isolation/integration:** actual identities, storage, resource restrictions, invocation and adapter equivalence are exercised. A declared principal name or mocked denial is insufficient.
5. **Same-target physical evidence:** qualified observations and frozen predictions pass an approved ScoreProfile for declared outputs and operating domain.
6. **Protected transfer evidence:** new-workload, architecture and joint-shift cohorts satisfy their distinct frozen exposure contracts and blind scoring policy.

The task state machine (`PLANNED` through `ACCEPTED`), evidence pipeline (acquisition through release), scientific result and provider execution status are separate fields. An accepted documentation task cannot set a provider to executed or a numerical claim to `QUALIFIED`. Sources: [acceptance levels](../../../power-spec-2/implementation_plan.md#acceptance-levels), [task states](../../../power-spec-2/agent-execution-and-independent-validation.md#minimal-execution-state-machine), [evaluation objects](../../../power-spec-2/blind_evaluation_component.md#objects-and-stages).

The available text uses `INSUFFICIENT_ACCEPTANCE_POLICY` in the agent workflow and `UNAPPROVED_ACCEPTANCE` in the blind evaluator. Preserve both source terms in the ambiguity record; resolve the canonical schema and any translation explicitly before production emission. Do not silently merge them or choose whichever enables a pass. Both forbid qualification without approved numerical limits. Other scientific classes are `FAILED_MODEL`, `INVALID_EXPERIMENT`, `UNSUPPORTED_MODEL`, `BLOCKED_PERMISSION`, `INSUFFICIENT_OBSERVABILITY`, and `INSUFFICIENT_STATISTICAL_EVIDENCE`. Distinguish a software failure from each scientific class.

## Test-family coverage

This table maps every v0.4.1 implementation task to validation work. A task can require several families; the complete packet names its exact fixtures, assertions and commands. Conditional gates supplement the published dependency graph without rewriting it.

| Family | Primary tasks | Required checks and retained evidence |
|---|---|---|
| T-CONTRACT | F-01, F-02, Q-01; all packets | Current authority and exact workload; strict envelopes; source/requirement coverage; units, finite values, supported domains, missingness, proposed versus approved policy; missing authority blocks the dependent readiness transition. |
| T-PROVENANCE | F-02, F-07, F-10, A-02, B-01; all artifacts | Exact code/data/config/image/tool identities, source ancestry, physical origin, attempt/runner binding, dependency closure and terms, immutable lineage, public versus sealed evidence. |
| T-ISOLATION | A-02, F-07, F-06, B-01 | Separate actual privileges; allowlisted views; no developer label/signing privilege; offline predictor; prohibited device/network/cache access denied; data-only scorer inputs and safe paths. |
| T-WORKFLOW | A-01, A-03, Q-01 | Bounded immutable task dispatch; authoritative dependencies; finite repair and reveal budgets; independently dispatched validation; discovery before escalation; no self-grading or retry-based pass selection. |
| T-NATIVE | F-04, F-09, F-10, V-01, V-02, V-03 | Pinned real builds and discovered native tests, native result reproduction, exact precision/operator/device/context support, all failures/skips, native costs and dependency terms. |
| T-METROLOGY | F-03, F-05, K-01, X-01, X-04, H-01 | Physical channel/boundary/operator, independence, synchronization, sample semantics, gaps/reset/saturation, overhead, uncertainty, actual control/readback and restoration. |
| T-WORK | F-05, F-09, X-02, X-04, C-02 | Actual tokens/precision/operands/operators/contexts; clean/profile equivalence; replay-lane semantics; no missing work, hidden offload or fallback; selected-region composition. |
| T-ADAPTER | F-06, V-04, P-01 | Native-to-normalized equivalence; declared units, boundaries, status and coverage; exact field/ancestor allowlist; provider input consumption and unsupported-path handling. |
| T-SCORE | F-07, Q-01, U-01, X-05, P-02, P-04 | Deterministic immutable scoring, frozen observation operators, absolute/contrast/interaction metrics, policy readiness, subgroup evidence and uncertainty; sealed replay. |
| T-FREQUENCY | X-01 through X-05, P-01, P-02 | Feasible controls, frozen work, randomized blocked experiment, realized compliance, assigned-policy cohort, paired response/interaction and holdout exposure; correct claim labels. |
| T-UQ | K-02, U-01, U-02, P-01, X-05, B-02 through B-04, M-01, N-01 | Joint predictive samples, score uncertainty, independent sampling units, coverage/sharpness/subgroups, calibration and discrepancy assumptions; conditional derivative/inference checks. |
| T-CALIBRATION | K-01, K-02, P-01, B-03 | Independent characterization lineage, baseline ownership, identifiability/grouped parameters, residuals, heldout components, operating coverage and C-profile exposure. |
| T-TRANSFER | B-01 through B-04, V-01 through V-04 | Grouped splits/duplicates/imported profiles; distinct workload/architecture/joint axes; matched-information baselines; finite reveals; reproduction never mislabeled blind transfer. |
| T-CONTROL | X-01, X-04, P-03, P-04, H-01 | Requested versus actual state, in-flight work and causal feedback, cap/operator semantics, reset/cleanup, fault handling; D4-specific authority and event/waveform separation. |
| T-ACCOUNTING | F-06, K-01, P-01, C-02, H-01, M-01, N-01 | Energy integration, work/time coverage, nonoverlapping baseline/component ownership, request/token denominators, phase totals, device/system/network boundaries and communication overlap. |
| T-COST | F-09, C-01, C-02, U-02; all runs | Actual native/adapted wall time, resources, trace/storage and numerical sampling costs; error/cost comparisons, reduction reconstruction and shared multifidelity discrepancy. |
| T-RELEASE | F-08, P-05, H-01, M-01, N-01; accepted tasks | Complete immutable evidence bundle, selected independent reproductions and designated mutations, per-output claim/support/exposure/limits, all attempts, approved policy, exact acceptance authority. |

Every artifact gets cheap checks for schema, units, provenance, scope, exposure, finite outputs and coverage. Run component checks when their implementation changes. Run expensive physical/reproduction suites at the declared milestones and affected releases. A newly proposed check must identify the risk, oracle and finite cost; exhaustive repetition of unrelated tests is not a completion requirement. Source: [every-step validation](../../../power-spec-2/agent-execution-and-independent-validation.md#every-step-validation-without-paralysis).

## Exact synthetic reference oracles

These are proposed public mathematical fixtures for the implementer and independent validator. They are exact under the stated assumptions, not physical accuracy thresholds or universal GPU laws. Set numerical comparison tolerances from arithmetic error and the chosen numeric representation, never from model residuals. The validator should implement a small independent reference or hand-derived expected table rather than call the production function to generate its own expectations.

| Fixture | Inputs, assumptions and expected result | Deliberate defects it must detect |
|---|---|---|
| Piecewise progress | 100 cycles; 1 GHz for the first 50 cycles and 0.5 GHz for the remaining 50: completion is 150 ns. A separate 25 ns gated interval contributes no cycles and increases completion to 175 ns. | Freeze the original 100 ns completion; apply the new clock retroactively; progress work during gating; confuse cycles with seconds. |
| Explicit hold integration | Half-open intervals `[0,2)` s at 10 W and `[2,5)` s at 4 W: energy is 32 J and duration is 5 s. Split either interval into equal-valued pieces: energy stays 32 J. | Integrate past the last declared interval; double count the boundary; wrong milliseconds/seconds; infer missing samples as zero. |
| Linear integration | A declared linear ramp from 2 W at 0 s to 6 W at 2 s has energy 8 J. The same endpoints under a declared left-hold operator have 4 J. Both are valid only under their own operator. | Silently use trapezoids for hold data; silently use hold semantics for linear data; choose the operator after seeing the result. |
| Factorial response | Binary compute and transfer coordinates with `Y=10+2c+3m+4cm`: `Y00=10`, `Y10=12`, `Y01=13`, `Y11=19`. Compute effects are 2 and 6, transfer effects 3 and 7, interaction 4. | Reverse a contrast sign; swap factor coordinates; assume interaction must be zero; treat missing corner as zero. |
| Correct contrasts, wrong absolute value | Add 7 to all four predictions in the factorial fixture. All main and interaction contrasts remain unchanged; each absolute residual is +7. | Qualify from response slopes alone; subtract fitted post-reveal offset. |
| Correct anchor, wrong slope | Reference values at separated clock levels are 10 and 30; predictions are 10 and 10. Anchor residual is zero; predicted contrast is 0 versus reference 20. | Qualify from one operating point; constant-table substitution; omit paired response scoring. |
| Paired covariance | `Var(YH)=9`, `Var(YL)=4`, `Cov(YH,YL)=3`: contrast variance is 7. With perfect shared offset noise, equal marginal variances and equal covariance cancel that offset in the contrast. | Drop covariance and report 13; independently shuffle samples across levels; add marginal confidence-interval widths. |
| Restricted fixed-voltage law | Synthetic compute-only 100-cycle work, no stalls/leakage/transitions, 10 W dynamic power at 1 GHz and 20 W at 2 GHz: durations 100 ns and 50 ns, dynamic energies both 1 microjoule. | Wrong scaling or units in this fixture. Do not extend the expected monotonicity/energy law to general kernels or DVFS. |
| Elasticity domain | Positive output ratio 2 and achieved frequency ratio 2 imply elasticity 1. Identical achieved clocks, nonpositive outputs or nonpositive frequencies make the expression undefined. | Divide using commanded frequencies when achieved clocks coincide; output NaN/Infinity as a valid result. |
| Additive accounting | A declared 5 J shared baseline and disjoint 2 J compute/3 J memory increments total 10 J. If component values already include the baseline, the ownership record must prevent adding it again. | Duplicated static power; overlapping device/board boundary sums; treating missing component energy as zero. |
| Label invariance | Hold approved inputs and random seed fixed; change only hidden labels. Prediction bytes/normalized predictions remain invariant; a nondegenerate score fixture changes. | Label leakage, score-state access, filename/metadata lookup and using scorer results as prediction inputs. |
| Requested/realized mismatch | Two different requested levels have identical actual clocks. Preserve the assigned-policy trials but reject a claim that they identify two achieved fixed-clock levels. | Accept API success as fixed-clock proof; compute elasticity from fictitious separation; silently discard noncompliant trials. |

Additional generated properties: unit-equivalent values normalize identically; order changes of independently keyed metadata do not change semantics; interval refinement preserves energy under the declared operator; split/recombine conserves supported work and energy; display-name changes preserve predictions only where names are contractually irrelevant. Perturb a meaningful shape, clock or architecture field only when a stated mechanism predicts dependence; require the provider to consume it or report unsupported behavior. Do not require every perturbation to change every output.

Source anchors: [frequency metrics and restricted oracles](../../../power-spec-2/frequency-intervention-validation.md#5-mathematical-falsification-metrics), [reported local toy examples](../../../power-spec-2/report.md#synthetic-behaviors-exercised). The earlier QA report describes another bundle; these fixtures are new implementation work until their actual test identities and run evidence exist here.

## Contract, provenance and task execution checks

T-CONTRACT checks must reject absent required fields, conflicting schema versions, unresolved units/domains, unsupported status conflation, nonfinite numerical values, duplicate keys and malformed types under the adopted authoritative schema. Reject unsafe YAML constructors if YAML is accepted. Examples must include valid, invalid and deliberately unready drafts. A null pin, absent permission, undefined W/C profile or missing threshold remains unresolved; no default `0`, infinity, success status or mutable `main` may satisfy it.

Once the complete release is recovered, inspect its tools and dependencies before running its local checks. Verify that the authoritative backlog, generated plan, generated packets and requirement/test mappings agree; the dependency graph is acyclic; task IDs are unique; every required task is accounted for; source manifests and preserved input hashes match. Reconcile local planning IDs with recovered requirement IDs without rewriting historical evidence. Never count a test collection that discovered zero tests as the promised QA suite.

Each bounded implementation packet must freeze:

- Objective and exact source clauses; official requirement IDs where recovered, otherwise explicitly provisional source references.
- Parent/spec task, dependency evidence and conditional claim gates; input artifacts with access classes and hashes.
- Exact permissible output paths and public/protected test ownership; reuse candidates and discovered native test commands.
- Typed output and failure behavior; positive, negative, property, oracle, mutation and reproduction cases that apply.
- Developer and separately instantiated validator identities; allowed commands/resources; finite repair and reveal budgets.
- Acceptance artifacts, explicit unsupported behavior and smallest blocking condition; who may approve any policy change.

T-WORKFLOW integration tests must exercise correct transitions and reject skipping submission/validation, developer self-acceptance, dependency spoofing, stale attempt reuse, out-of-scope writes, invalid authority, partial publication and overwrite of prior attempts. Crash/restart tests must preserve attempt identity and failure evidence. Repair exhaustion must terminate the unchanged approach while unrelated ready tasks remain dispatchable. Feedback tests must return only the approved bounded counterexample/category; detailed blind residuals stay private.

T-PROVENANCE must bind native and normalized outputs to the same input/model/provider/runner/attempt identities. Mutate each binding independently and reject replay. Retain exact command, working directory, exit status, environment/tool identity, duration and artifact hashes; a hash alone does not prove execution. Distinguish physical acquisition, public reproduction, calibration, synthetic and development-only roles throughout ingestion and reporting. Duplicate detection includes derived tables and imported profile ancestry, not just byte-identical files.

## Actual isolation and anti-shortcut qualification

Implement and independently run the [mandatory blind-evaluator challenges](../../../power-spec-2/blind_evaluation_component.md#anti-shortcut-challenge-suite). For each challenge retain the baseline/reference result, mutation identity, expected failure category, actual result and validator identity. A mutation is killed only by the intended relevant assertion or denial; a syntax/import failure is not evidence that a numerical or authorization mutant was caught.

| Attack or defect | Required observable behavior |
|---|---|
| Raw combined trace mounted into predictor | Access/view validation rejects before prediction; removing one obvious power column is insufficient. |
| Label descendants in nested metadata, query views, filenames, length/timestamps, coefficient tables, model artifacts, environment, cache or logs | Provenance and access enforcement reject the descendant or classify the input/claim under an explicitly approved exposure policy. |
| Same-boundary current and voltage offered as non-power inputs | Power-prediction exposure check rejects reconstructible labels. Requested cap remains distinguishable from measured consumption. |
| Developer attempts scorer policy/test/key/store write or label read | Actual OS/service identity denies and records the attempt; production policy remains unchanged. |
| Predictor probes target hardware, credentials, network endpoint or shared writable cache | Deployment capability tests deny/log each prohibited path, while specifically authorized model-compute resources still work. |
| Scorer receives pickle, executable payload, unsafe expression, path traversal or symlink escape | Data-only parsing and normalized path confinement reject without execution or external writes. |
| Build fetch succeeds but predictor tries fresh dependency/model fetch | Build and prediction privileges remain separate; offline prediction rejects undeclared retrieval. |
| Mock/constant implementation replaces required native provider | Unknown physically meaningful cases plus actual invocation/completion evidence expose substitution; unsupported dependence cannot silently pass. |
| Worker changes tests, skips work/precision, edits score policy or alters success subset | Independent immutable test/policy/work gates reject; all original attempts remain recorded. |
| Repeated probing of the blind cohort | Atomic reveal/exposure accounting prevents budget bypass and requires a fresh cohort when policy says so. |
| Different role names in the same privileged workspace | Deployment qualification fails until actual credentials, storage views and write/tool restrictions are independent. |

Do not store real secrets or protected labels in public tests to prove these controls. Use designated canary secrets/data and policy-approved attack endpoints for deployment challenges. Keep public developer feedback separate from private reviewer artifacts. These are tests of the adopted isolation mechanism, not instructions to build a replacement IAM or sandbox framework.

## Native providers, adapters and supply chain

For each selected provider, record its exact commit/image/compiler/runtime, configuration and dataset hashes, required/optional dependencies, license files and dependency closure, native test discovery and expected supported case. Execute the native example before implementing its adapter. Record all tests discovered, selected, passed, failed and skipped, with reasons and costs. Run a minimal independently reproduced case and compare native versus normalized outputs with declared conversion/numerical tolerances.

Support checks must cover the actual target kernel/operator, dtype/accumulator/KV behavior, precision, context and model configuration. The package building or exposing a configuration key does not establish supported execution or accuracy. Reject missing FP8/work/channel coverage and unsupported-device fallback. Pins and terms must be resolved before a qualification image is frozen; optional proprietary acquisition tools require their own existing or newly approved policy.

F-04 requires an open non-IPPM power path. Reuse existing AMD SST and inspect its hooks/content; SST is not a mandatory wrapper for every provider. Compare selected Accelergy/HWComponents native subsystem capability before committing to unnecessary integration. If a feedback hook is absent, prove the smallest component change or narrow the claim. Do not add a general engine, power language, parser/viewer, sampler, optimizer or orchestrator.

V-01, V-02 and V-03 are bounded selected evaluations, not three mandatory dependencies. Match each public/paper/code/config snapshot explicitly. Hopper fallback is a separately scoped result when matching Blackwell artifacts are absent; NVIDIA timing evidence does not qualify AMD or modern power. AISimulate imported target profiles count as exposure. EnergAIzer's supported native voltage-frequency experiment is a reuse lead, not proof of FP8 decode or independently controlled HBM coverage. V-04 requires at least one selected completed applicable native result in addition to F-06/F-07; do not invent an AND dependency on all optional references.

## Physical measurements, work equivalence and frequency trials

T-METROLOGY acceptance requires native/raw channel identity, physical boundary, observation operator, time base/synchronization, uncertainty, sample/hold/interpolation semantics, completeness and overhead evidence. The validator must detect missing intervals, reset/wrap conditions, saturation and clock discontinuity according to the adopted channel contract. Independent-looking channels that derive from the same sensor are not independent reference measurements. Preserve actual intervals; never fit sensor lag after seeing the qualification result.

F-05/X-02 work manifests freeze the actual card/partition, software/firmware, model/checkpoint/tokenizer/weights, prompts and input/output lengths, seed policy, dtype/accumulator/KV details, kernels/compiler/JIT/graphs, allocator/cache state and admission policy. Compare actual tokens and work summaries; seed equality is not execution equality. Record offload, precision fallback or changed scheduling as contractually allowed behavior or reject the fixed-work claim. Clean/profile equivalence must be measured under the approved rule, not assumed from successful exits.

Keep two lanes distinct: frozen operators/dependencies/shapes/required trajectory for mechanism tests, and native vLLM requests/configuration/stochastic policy for serving-policy response. A fixed-token replay is not silently full autoregressive generation. If vLLM lacks a qualified replay mechanism, retain that lane as blocked. Do not require identical traffic/polling counters when timing legitimately changes them; require semantic invariants. Timestamped or fixed-polling traces cannot be assumed portable across clocks; service and completion must be recomputed.

The X-01 through X-05 acceptance sequence is:

1. **Discover:** independently query actual compute/GFX, HBM/MEM, fabric/DF/SOC, copy-engine and PCIe controls. Record supported range/quantization/units, coupled constraints, settable versus observable status, voltage coupling, permission and reset behavior. An API success or soft maximum is not fixed-clock evidence.
2. **Choose feasible factors:** compute times one demonstrated independently controlled relevant transfer domain; HBM is the candidate, not a guaranteed control. Coupled controls yield a constrained-policy/manifold study. Never substitute workload intensity for a frequency factor.
3. **Freeze design:** approved finite pilot, levels/repetitions/precision rule, blocks, validator-owned seed/randomization, baseline repeats, calibration/development/qualification combinations, compliance rule and fixed-n or approved sequential stopping. A 3-by-3 grid is a proposal only; two levels cannot establish curvature.
4. **Acquire independently:** reserve/isolate device; attest initial state; apply approved settings; verify readback; settle using independent checks; capture full work interval and requested/effective clocks; retain all attempts; restore previous settings after success, failure and cancellation; independently verify restoration.
5. **Score:** frozen pre-run policy predictions use requested controls and permitted independent characterization. Report every assigned-policy trial and the preregistered compliant subset with coverage. Diagnose invalid experiment versus model error; no silent deletion of clamped/throttled/unobserved cases.

Fault-injection fixtures for the control wrapper must cover timeout, failed readback, unsupported setting, process cancellation, partial acquisition and failed restoration. Preserve failure evidence and escalate according to the approved cleanup policy. Synthetic cleanup tests do not authorize physical settings or establish real restoration. Do not implement register writes, overvolting or protection bypass.

Use `same_arch_frequency_intervention` with the appropriate `fixed_voltage_partial_effect`, `dvfs_policy_total_effect` or `measured_state_conditioned_effect` qualifier. Actual voltage/cap/protection/state changes determine interpretation. Existing temperature telemetry may bound an observed operating envelope; it does not justify adding a thermal workstream. A secondary measured-state-conditioned diagnostic cannot be relabeled independent timing/power prediction. Time-series lengths and last timestamps can leak runtime even after dropping the time column.

Score duration/throughput, phase timing, energy per request/token, mean/windowed power, waveform residuals only at supported resolution, and required component quantities. Score absolute errors at every supported point plus paired compute/transfer contrasts and interactions. Preserve absolute-time errors when adding work/phase-aligned diagnostics. Reject post-reveal cross-correlation, dynamic time warping or fitted offset/lag.

## Statistical, calibration and transfer acceptance

Q-01 supplies approved finite numerical utility limits and statistical rules, not defaults guessed by the implementer. Freeze output boundaries/operators, aggregation/subgroup rules, precision/sample/stopping rules, confidence/coverage/sharpness criteria, reveal/retry policy and exclusion criteria before qualification. Resolve numbers from approved independent measurement evidence or the appropriate owner decision. Without them, produce descriptive scores and uncertainty with the unresolved-acceptance status; do not mark `QUALIFIED`.

Use device/session/run blocks as independent sampling units when trace rows are correlated. Contrast calculations consume joint samples with shared parameter and observation structure. Report predictive uncertainty, observation uncertainty and uncertainty of estimated scores distinctly; avoid pseudoreplication and independent-marginal substitutions. Coverage alone cannot pass with arbitrarily wide intervals: apply the frozen sharpness and subgroup rules. Failure to reject a model-error null is not evidence of accuracy; use the approved, adequately powered equivalence/accuracy criterion.

K-01/K-02 characterization must be independently acquired, provenance-qualified and separate from the scored workload/clock outcome and its duplicates. Record baseline/static-energy ownership, operating coverage and joint dependencies. Test parameter identifiability; when components cannot be separated, report grouped estimates rather than physically exclusive invented components. Include heldout component cases, residual diagnosis and uncertainty/discrepancy checks before composing the target workload.

The imported files do not define complete W0/W1/W3 or C0/C1 profiles. Resolve the missing evidence policy before freezing allowed-input fields or production profile enums. What is explicit: P-02 needs at least one W0/W1 timing-and-power prediction path; W3 is diagnostic only. Independently measured action-energy tables at a heldout workload clock can be permitted in C1, yielding characterized-operating-point composition rather than uncharacterized-frequency extrapolation. Do not map these profiles from old E1 capability names.

B-01 splits must group repetitions, related frequency pairs, workload families, architectures and imported-data lineage appropriately; adjacent windows from a run are not independent holdouts. Freeze distinct calibration, development and validator-controlled qualification roles and detect derived duplicates. Public paper results are reproduction data. Online discovery of exact heldouts enters the exposure ledger and invalidates the blind claim under the adopted policy.

B-02 tests new workloads and W-profile ablations, B-03 uses an actual distinct withheld architecture with C-profile exposure and changed-mechanism audit, and B-04 withholds both axes. Use matched-information baselines and retain unsupported subgroups and all attempts. An unseen clock combination on one architecture is `operating_point_holdout`, not architecture transfer. Hypotheses selected from exploratory residuals need an independent confirmation cohort; sealed samples cannot be retargeted after score access.

U-02 applies only when derivatives or approximate inference are used. Qualify directional sensitivities against independent finite-difference/analytic checks in smooth regions, state event/discontinuity assumptions, and use the selected library's relevant convergence/posterior diagnostics. Do not demand differentiability across arbitrary discrete events or implement every inference method before initial evidence.

## Closed-loop, reduction and later-stage gates

P-03/P-04 must prove causal commands versus actual control state and correct progress of in-flight work across state changes; use the piecewise/gated synthetic oracle before physical checks. Preserve latency, cap and observation-operator semantics, and label measured-state conditioning. Ordinary PMFW validation is D2b after P-02's D2a qualification; do not fold it into a nominal fixed-point experiment or require thermal dynamics.

C-02 is an additional gate whenever selected regions support a full-workload claim. Cover early/middle/late decode and the relevant contexts; independently check reconstruction errors, weights, time/energy conservation, omitted kernels and uncertainty. Scaling by measured target completion time contaminates independent timing prediction. A truly full native run does not need the C-02 reduction gate. C-01 compares measured error/cost tradeoffs and shared discrepancy for multifidelity paths; two models using the same energy table are not independent physical evidence.

H-01 follows P-05, requires its own approved high-current/protection authority and separates event detection from waveform accuracy according to actual observability. M-01 follows both B-04 and H-01: validate per-device/system accounting, communication/compute overlap and joint uncertainty using existing framework mechanisms. N-01 follows M-01 and adds actual network/collective/end-to-end workload semantics with matched physical boundaries. No automatic extension of a single-card pass to distributed claims is allowed.

## Commands: existing discovery versus future tests

Run commands only in the stated repository/environment after checking local instructions and dependencies. This planning change has not executed provider builds, hardware acquisition, blind validation, or the future tests specified above.

Existing Bob collection is available through its current pytest configuration. During implementation, start with collection and selected tests for changed code; select additional integration/security/regression coverage from the actual discovered test nodes:

```sh
cd /home/captain/work/AI/power/bob
python -m pytest --collect-only -q
```

Record the actual interpreter/virtual environment used. The existing suite includes legacy and optional integration behavior; inspect collection and markers before execution. A focused packet must replace a placeholder test command with real discovered or newly implemented exact node IDs before dispatch. Do not fabricate a `pytest` path to make a planning packet appear ready. Use the existing regression suite appropriate to the modified runtime once focused checks pass; report environmental failures separately from introduced failures.

The specification advertises these commands for the complete release:

```sh
python tools/check_release.py
python -m unittest discover -s tests -v
python tools/render_backlog.py
```

Those scripts/test directories are absent under the current flattened `power-spec-2` import. They are **unavailable**, not passing checks. The published `53 unit-test methods` / `15 static-check groups` in `power-spec-2/report.md` are historical release assertions, not results from this workspace. Recover and inspect the matching bundle, then record any execution here separately. Do not run root/Bob tests under those names and attribute them to the specification's missing QA bundle.

Native provider commands must be discovered from the pinned provider's actual build/test interfaces and frozen in its task. No generic shell command in this planning document authorizes inference, changing clocks, downloading new dependencies, or contacting external hardware. Use the task's existing approved capabilities and standing policy; missing policy affects the dependent action while local planning and unrelated permitted discovery continue.

## Required acceptance bundle for the lower-capability implementer

For each completed packet deliver the exact patch/artifact identity; source/requirement mapping; selected native implementation and why it fits; input/output/config/runtime hashes; actual test collection and executed commands; exit statuses; all attempts/failures/skips; positive/negative/property/oracle results; designated mutant results; selected independent reproduction; unsupported cases; measured cost; limitations; and validator result with identity and policy version.

Include a per-output table naming physical boundary/operator, exposure/conditioning, supported workload/architecture/operating range, evidence level and scientific status. Freeze predictions before accessing score outputs. Release only approved public/post-reveal artifacts; retain sealed replay materials under the proper service identity. A separately reviewed scorer/oracle correction creates a new version and explicitly invalidates/re-scores affected results instead of editing history.

Acceptance must fail when any mandatory evidence is missing, the validator shares developer authority, a required mutant survives, observed data are represented as predicted, numerical limits remain unapproved, or the claimed domain exceeds demonstrated support. Report the smallest missing authority, evidence or capability and the independent tasks still ready. Neither an LLM review, successful process exit, synthetic test count, nor artifact hash is a substitute for the appropriate evidence level.
