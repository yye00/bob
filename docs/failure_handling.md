# When implementations fail — bob3's recovery pipeline

A naive build orchestrator does one of two things when a sub-agent
fails: retry blindly, or escalate to a human immediately. Both are
expensive in different ways. Bob3 sits between them: it classifies
each failure, applies a graduated set of recovery actions, and only
escalates when the cheaper paths are exhausted.

This doc explains exactly what happens after a sub-agent finishes —
successfully or otherwise — and how each recovery mechanism is
gated.

> Code references in this doc point at
> [`src/bob3/orchestrator/run_loop.py`](../src/bob3/orchestrator/run_loop.py)
> unless noted.

---

## The post-execution pipeline at a glance

```
sub-agent finishes
       │
       ├──► spawn-failure detector ───► free retry (R10-015)
       │     duration_ms < 100ms,
       │     num_turns == 0
       │
       ├──► verification checklist (always — R10-014)
       │     source files, tests pass, AC met,
       │     no stubs, recent file changes...
       │
       ├──► success path
       │     verification passed AND sub-agent succeeded
       │     → status='completed', cascade dependents to 'ready'
       │
       └──► failure path
             ├── increment refinement_attempts
             ├── decay confidence (R10-011)
             ├── if attempt ≥ 2 and not in cooldown:
             │     spawn RCA agent (R10-009)
             │       └─► route on RCA recommended_action:
             │             ├── research / clarify_spec → force research, retry
             │             ├── decompose → flag for size split, retry
             │             ├── mark_needs_human / skip / escalate → retire
             │             └── (anything else)             → fall through
             ├── if refinement_attempts < max → status='ready' (retry)
             └── else → status='needs_human'
```

Every branch exists because the alternative was tried and burned
budget. The R10-* tags are review-registry entries; many of the
gates exist precisely because earlier versions of bob3 failed in
those specific ways.

---

## Stage 1 — distinguishing "didn't run" from "ran and failed"

The first thing the loop does after a sub-agent returns is check
whether the agent **actually ran**. The signal is at
[`run_loop.py:245`](../src/bob3/orchestrator/run_loop.py):

```python
def _looks_like_spawn_failure(result):
    return result.is_error and result.num_turns == 0 \
                           and result.duration_ms < 100
```

A sub-agent that died at process-spawn time (typically: SDK
connection error, OOM kill, missing CLI on PATH) has zero turns and
a sub-100 ms wall clock. A sub-agent that ran for 25 turns and then
errored has both fields populated.

These two cases are routed differently:

| Detected as | Action |
|---|---|
| Spawn-time failure | **Free retry** — `refinement_attempts` *not* incremented; capped at `_MAX_SPAWN_RETRIES = 3` per feature so a permanently-broken environment can't infinite-loop |
| Real sub-agent failure | Goes to Stage 2 (verification + RCA) |

This is R10-015. Without it, a transient OOM on a long-running
build (which we hit several times during the swedish-circle case
study) burns one of the feature's three refinement attempts before
the agent has even started doing work.

---

## Stage 2 — verify before deciding

After the spawn check, bob3 runs the verification checklist
**unconditionally** — even if the sub-agent reported `is_error=True`.
This is R10-014. The reasoning: a sub-agent might fail on its very
last turn (e.g., SDK connection drops while writing the summary)
after having already written correct code to disk. Marking the
feature `needs_human` based purely on the sub-agent's exit code
would throw that work away.

The checklist (in [`superpowers.py`](../src/bob3/superpowers.py)):

1. `source_files_exist` — at least one Python file in src/
2. `package_has_substance` — non-`__init__` modules in the package
3. `test_files_exist` — at least one `tests/test_*.py`
4. `no_stubs_in_source` — AST scan for `pass`, `...`, `raise NotImplementedError`
5. `no_mocks_in_source` — `mock` imports must live only in tests/
6. `tests_pass` — full pytest run with a project-size-aware timeout (R10-020)
7. `code_changes_made` — recently-modified files in src/ or tests/
8. `acceptance_criteria_met` — every criterion evaluated individually

The orchestrator now combines `(sub_agent_succeeded, verification_passed)`
into a four-way decision:

| Sub-agent | Verification | Outcome |
|---|---|---|
| ✓ | ✓ | `completed`; cascade dependents to `ready` |
| ✓ | ✗ | `needs_human` (sub-agent claimed success but couldn't prove it) |
| ✗ | ✓ | continue as success — work is on disk and passes (R10-014) |
| ✗ | ✗ | go to Stage 3 |

> Aside: `code_changes_made` is currently a hard fail (R10-021) —
> it rejects re-runs whose work was already correct on disk from a
> previous attempt. That's a known issue in the registry; the
> swedish-circle build hit it three times, recovered each via
> `bob3 verify-feature`.

---

## Stage 3 — confidence decay

When verification fails, bob3 increments
`feature.refinement_attempts` (against the cap
`max_refinement_attempts`, default 5) and then **decays the
confidence scores** ([`run_loop.py:1339`](../src/bob3/orchestrator/run_loop.py)):

```python
new_impl  = max(0.0, conf_impl_correctness  - 0.15)
new_spec  = max(0.0, conf_spec_understanding - 0.15)
new_ready = max(0.0, readiness_score        - 0.15)
```

The decay rate is `BOB3_CONFIDENCE_DECAY_PER_FAILURE` (default
0.15). This is R10-011. Without it, the low-confidence research
trigger was effectively a one-shot — the feature's confidence never
moved, so the next retry never re-fired research.

Decay flips the confidence picture so Trigger 3 of `needs_research`
(see Stage 4) can re-fire on the next attempt.

---

## Stage 4 — Root Cause Analysis

If the feature has now failed **at least twice** (i.e.
`refinement_attempts >= 2` post-increment), bob3 spawns an **RCA
sub-agent** ([`run_loop.py:2171`](../src/bob3/orchestrator/run_loop.py)).
This is R10-009 — the RCA agent existed in `claude_executor.py`
with a full system prompt and a passing test suite, but for several
versions had no production call site. Now it's wired into the
failure path.

### Gating

RCA is gated on four conditions:

1. **Feature flag** — `BOB3_RCA_ENABLED` (default 1; tests set it
   to 0 to avoid spawning real SDKs).
2. **`refinement_attempts >= 2`** — the very first failure is too
   early; one-shots are common and the normal retry path handles
   them at lower cost. RCA fires from the second attempt onward.
3. **24-hour cooldown** per feature — `_RCA_COOLDOWN_SECONDS`,
   tracked via `evidence_artifacts` of type `rca_analysis`. A
   flapping feature won't burn budget on repeated RCA spawns.
4. **Budget** — never spend post-budget budget on RCA.

### Wall-clock bound

The RCA spawn is wrapped in `asyncio.wait_for` with
`BOB3_RCA_TIMEOUT_SECONDS` (default 600 s = 10 minutes). RCA is
meant to be a quick hypothesis pass, not another implementation
budget. If the RCA sub-agent gets stuck inside a tool call, the
loop continues without its recommendation rather than parking.

### What the RCA sub-agent does

The agent receives the failure evidence (first ~4 KB of sub-agent
stdout + error message) and a system prompt
([`claude_executor.py:1162`](../src/bob3/orchestrator/claude_executor.py))
that requires it to follow the **F106 Systematic Debugging Protocol**:

```
Phase 1 — Root Cause Investigation (mandatory)
   What's the exact error? Expected vs actual? What component?
   What inputs led to this? Reproducible? What changed?

Phase 2 — Hypothesis Formation
   Form a hypothesis. List supporting evidence.

Phase 3 — Fix Recommendation
   Recommend a fix that prevents recurrence.

Phase 4 — Verification Plan
   Tests that prove the fix works.
```

The agent must respond with a JSON block containing:

- `blame_target` ∈ {`implementation`, `validation`, `feature_spec`,
  `infrastructure`, `external`, `test_flaky`, `unknown`}
- `recommended_action` (one of the routing actions below)
- `root_cause` (required when proposing a fix)
- `investigation`, `hypothesis`, `verification_plan`

A safety rail in the parser
([`claude_executor.py:1198`](../src/bob3/orchestrator/claude_executor.py))
**downgrades any "fix" action to `investigate`** if `root_cause`
is empty. This enforces the IRON LAW from the protocol: no fixes
without a root cause first.

The full RCA result is stored as an `evidence_artifacts` row of
type `rca_analysis` so the cooldown check and post-mortem queries
can find it.

---

## Stage 5 — RCA action routing

The orchestrator interprets `recommended_action` and short-circuits
the normal retry path when appropriate
([`run_loop.py:2941`](../src/bob3/orchestrator/run_loop.py)):

| RCA action | What the loop does |
|---|---|
| `mark_needs_human`, `skip`, `escalate` | mark the feature `needs_human` immediately; don't bother retrying |
| `decompose` | set `exceeds_size_limits=True`, `size_limit_justification=<RCA root_cause>`, status `ready`. The next pick-up triggers the decomposer (Stage 6) |
| `research`, `clarify_spec` | force a research pass even if the normal `needs_research` triggers don't fire. Reset to `ready` so the loop retries with fresh information |
| `fix_implementation`, `fix_code`, `fix_test`, `retry`, `investigate` | fall through to the default retry path |

The forced-research path is important. The normal `needs_research`
gate ([`run_loop.py:1383`](../src/bob3/orchestrator/run_loop.py))
won't re-fire if `research_iterations >= 1`, but RCA might
recognize that the previous research missed something specific. So
`_force_research_for_feature` calls `spawn_research_agent`
unconditionally, the way the first research call did, and lets the
research agent pull additional context.

---

## Stage 6 — Decomposition

When a feature is flagged `exceeds_size_limits` (either by the
sizing heuristics in F072 or by an RCA `decompose` recommendation),
the next time the loop picks it up it runs **decomposition** instead
of normal implementation
([`run_loop.py:2446`](../src/bob3/orchestrator/run_loop.py)):

```python
if feature.exceeds_size_limits:
    decomp_result = await handle_decomposition(
        project_id=self.project_id,
        feature=feature,
        workspace=self.workspace or None,
    )
```

The decomposer is a planning sub-agent. It analyzes the parent
feature's description and acceptance criteria, then writes child
features (`parent_feature_id` set) into the database. Each child
gets its own acceptance criteria, dependencies, and refinement
budget. The original feature stays in `ready` — once all children
complete, `parent_feature_id` cascade marks it `completed` too.

This recursion is **bounded**: features have a `decomposition_depth`
column (default cap 3 levels) so a chain of decomposers can't
infinitely subdivide. Spec-level decisions about feature size happen
once at decomposition time, not every iteration.

The decomposer also gets `cwd` access to the workspace so it can
read the existing source code when deciding how to split work — at
the cost of accepting code injection from the workspace into the
decomposer's prompt window. That trade-off is documented at the
call site ([`run_loop.py:1078`](../src/bob3/orchestrator/run_loop.py)).

---

## Stage 7 — research-without-RCA

Before *any* implementation attempt — not just retries — the loop
calls `needs_research(feature)` and may run a research sub-agent
preemptively. The triggers
([`run_loop.py:1383`](../src/bob3/orchestrator/run_loop.py)):

1. **Explicit marker** — feature description contains
   `research_required=True`.
2. **Failure threshold** — `count_feature_failures(feature) >=
   BOB3_FAILURE_THRESHOLD_FOR_RESEARCH` (default 2). If a feature
   has already failed twice, the next attempt gets research first.
3. **Low confidence** — any of `conf_impl_correctness`,
   `conf_spec_understanding`, `readiness_score` below 0.5. This is
   the trigger that interacts with confidence decay (Stage 3) — a
   feature that started high-confidence but failed several times
   eventually decays into the low-confidence band and fires
   research.

All three triggers gate on `research_iterations < 1`, so research
runs at most once per feature in this path. RCA's
`_force_research_for_feature` (Stage 5) bypasses that gate when
RCA explicitly recommends more research after a failure.

The research agent has Perplexity MCP access (when
`PERPLEXITY_API_KEY` is set), runs with a research-specific system
prompt, and writes its findings to the project's research_results
table where subsequent implementation sub-agents can see it.

After successful research, readiness is bumped to 0.85 and the
implementation sub-agent gets a fresh start.

---

## Stage 8 — exhaustion

When all of the above is exhausted — refinement attempts maxed,
RCA can't suggest anything actionable, decomposition either
completed or also failed — the feature is marked `needs_human`.
This is the terminal state for the automated loop: bob3 emits
warnings, persists the failure evidence, and continues to the next
feature.

A human can recover via:

- **`bob3 verify-feature <id>`** — re-runs the verification
  checklist on the workspace; if checks now pass, marks the feature
  `completed` and cascades. Useful after manually fixing whatever
  was broken (see swedish-circle F010/F014/F016 which all hit this).
- **Manually editing the workspace + DB** — for cases where the
  verifier itself is wrong (R10-021).
- **`bob3 run`** again — `needs_human` features are *not*
  auto-retried, but `interrupted` features are (the resume scan
  picks them back up).

---

## Confidence decay + research interaction

The dance between Stages 3 and 7 is worth re-emphasizing because
it's the most non-obvious part of the design:

| State | confidence | research_iterations | What happens next |
|---|---|---|---|
| Fresh feature, low spec confidence | 0.30 | 0 | Trigger 3 fires → research → readiness 0.85 → impl |
| Same feature failed once (post-research) | 0.85 → 0.70 | 1 | All triggers gated on `< 1`, so no re-research; refinement_attempts=1; retry directly |
| Failed twice | 0.70 → 0.55 | 1 | RCA spawns; if it recommends `research`, force pass bypasses the gate |
| Failed three times | 0.55 → 0.40 | 2 (RCA forced) | RCA fires again (cooldown clear after ≥24 h), more drastic action |
| `refinement_attempts == max` | — | — | `needs_human` |

Without the decay, the feature stays at 0.85 forever and step 3
never gets help. Without RCA, step 3 just retries the same prompt
that already failed twice. Together, the system progressively spends
more compute on harder features, and only retires features that
fundamentally need human input.

---

## Operator levers

All of the above is tunable via environment variables:

| Variable | Default | Effect |
|---|---|---|
| `BOB3_RCA_ENABLED` | `1` | Master switch for RCA spawn |
| `BOB3_RCA_TIMEOUT_SECONDS` | `600` | Wall-clock cap on a single RCA |
| `BOB3_FAILURE_THRESHOLD_FOR_RESEARCH` | `2` | Failures before research fires (Trigger 2) |
| `BOB3_CONFIDENCE_DECAY_PER_FAILURE` | `0.15` | Per-failure decay step |
| `BOB3_TEST_RUN_TIMEOUT` | (scaled) | Per-test pytest cap; otherwise scales with project test count |
| `BOB3_FEATURE_TIMEOUT_SECONDS` | `3600` | Hard wall on a single feature run |

Tighten these for cost-sensitive runs; loosen them for builds with
heavy V&V suites. Defaults are tuned for the sort of mid-sized
build the swedish-circle case study represents.

---

## Reading recovery decisions in real builds

When you're tailing `bob3 run`, the structured log lines that
matter most for failure diagnosis are:

```
[ERROR] Feature <id> failed verification: <checklist summary>
[INFO]  Sub-agent ... appears to have failed at process spawn ...
        free retry 1/3       ← Stage 1 fired
[INFO]  Feature ... has low confidence (...), triggering research
                              ← Stage 7 trigger 3 fired
[INFO]  Research completed for feature ..., boosting readiness to 0.85
                              ← Stage 7 done
[INFO]  RCA for feature ...: blame=implementation action=research
                              ← Stage 4 fired, Stage 5 routed
[INFO]  Feature ... flagged for decomposition by RCA
                              ← Stage 6 will run on next pick-up
[ERROR] Feature ... will be marked needs_human due to failed verification
                              ← Stage 8: terminal
```

The full picture for any feature is queryable from the
`evidence_artifacts` and `sub_agent_runs` tables; `bob3 status`
and `bob3 show-reviews` surface the most-relevant slices.
