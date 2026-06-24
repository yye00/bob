# Architecture — what bob3 actually is

This is the high-level tour. It explains what each major bob3
component does and how they fit together. Use it as the index when
deciding which deeper doc to read.

> Deeper docs:
> - [`failure_handling.md`](failure_handling.md) — what happens when a sub-agent fails
> - [`adversarial_review.md`](adversarial_review.md) — the red-team loop and findings registry
> - [`swedish_circle_example.md`](swedish_circle_example.md) — a 19-feature build worked end-to-end

---

## The 30-second pitch

You write a YAML spec describing the project you want built. Bob3
reads it, decomposes it into features with dependencies, and runs a
loop:

1. Pick the highest-priority `ready` feature.
2. Maybe spawn a research sub-agent to gather context.
3. Spawn an implementation sub-agent with the right tools, skills,
   and prompts; it writes code in TDD mode.
4. Run a verification checklist on the result.
5. If verification passes, mark `completed`, cascade dependents,
   commit, and loop.
6. If anything fails, run a graduated recovery pipeline (free
   retry → confidence decay → RCA → research / decompose / escalate).

Around that loop sit:

- A **persistent SQLite database** of features, sub-agent runs,
  evidence, calibration data, and confidence history.
- A **skills system** that ships nine bundled skills into every
  sub-agent workspace.
- An **in-process semantic memory** (mem0 + FastEmbed + Qdrant) for
  cross-run lessons.
- An **MCP integration layer** that selectively enables Perplexity
  (research), Bob3 Memory (always), and Puppeteer (per-feature) for
  sub-agents.
- An **adversarial-review registry** that accumulates bug findings
  across runs and feeds them back to future sub-agents.
- A **graceful-shutdown** path that turns SIGINT into a checkpoint
  so resume actually works.

---

## Source map

```
src/bob3/
├── orchestrator/
│   ├── run_loop.py           # the main loop; ~3,500 lines
│   ├── claude_executor.py    # spawn_research/_implementation/_decomposer/_rca
│   └── mcp_config.py         # MCP plugin builders
├── superpowers.py            # the verification checklist (run after every spawn)
├── enhanced_verification.py  # acceptance-criterion DSL evaluators
├── ast_checks.py             # AST-level stub / mock detection
├── git_ops.py                # commit_feature, revert_feature, status helpers
├── memory.py                 # BobMemory (mem0 + FastEmbed + Qdrant)
├── memory_mcp.py             # exposes BobMemory as MCP tools to sub-agents
├── memory_client.py          # in-process client used by the orchestrator itself
├── reviews.py                # findings registry (Finding, RecurringPattern)
├── skills/                   # bundled skills (9 directories)
├── skills_installer.py       # wires skills into <workspace>/.claude/skills/
├── orientation.py            # builds the sub-agent system prompt
├── mcp_lifecycle.py          # starts/stops the bob3-memory MCP server
├── signal_handler.py         # async-signal-safe SIGINT/SIGTERM flag
├── db.py                     # SQLite layer
├── schema.sql                # full DB schema
├── cli.py                    # ~1,800 lines of click commands
└── models.py                 # dataclasses (Feature, AgentRun, Evidence, ...)
```

---

## The orchestration loop

Source: [`src/bob3/orchestrator/run_loop.py`](../src/bob3/orchestrator/run_loop.py).

The single class `OrchestrationLoop` is the heart of bob3. It owns
the event loop, the project lock, the cost counter, the signal
flag, and the per-feature spawn-failure tally. Its public entry
point is `run()`; everything else is internal.

What the loop does, in order, on each iteration:

1. **Shutdown / budget check** — bail out cleanly on SIGINT or
   when total cost exceeds the budget.
2. **Find next ready feature** — query the `features_ready` view,
   which checks status='ready', readiness ≥ risk threshold, no
   active reviewer veto, all dependencies completed.
3. **Confidence assessment** — if `readiness_score == 0.0` (never
   assessed), run `db.assess_feature_confidence` to set spec /
   impl / test confidence dimensions and the composite readiness.
4. **Research gate** — if `needs_research(feature)` returns True,
   spawn a research sub-agent (see *Sub-agent kinds* below).
5. **Decomposition gate** — if `feature.exceeds_size_limits`,
   spawn a decomposer sub-agent that writes child features into
   the DB instead of implementing directly.
6. **Implementation spawn** — build the prompt (orientation +
   skill bundle + acceptance criteria + memory search instructions)
   and call `spawn_implementation_agent`.
7. **Pre-execution snapshot** — capture per-test pytest verdicts so
   regression detection has a baseline.
8. **Post-execution verification** — run the checklist
   *unconditionally*, even on `is_error=True` (R10-014).
9. **Result routing** — see [`failure_handling.md`](failure_handling.md)
   for the full graduated recovery pipeline.
10. **Commit** — on success, `git_ops.commit_feature` adds + commits
    with a structured message.

Two design properties matter here:

- **The loop never spawns sub-agents in parallel.** It's strictly
  serial. Concurrency-safety inside the orchestrator was repeatedly
  hard to get right (the registry has multiple `non-atomic-counter`
  findings); single-threaded execution is the cheaper invariant.
- **All cost goes through `_increment_cost`.** Earlier versions had
  three different writers updating `self.total_cost` and the DB
  in different orders; that's an entire row of the registry. Now
  there's one canonical writer, and `handle_execution_result`
  *returns* normalized cost rather than incrementing itself.

---

## Sub-agent kinds

Source: [`src/bob3/orchestrator/claude_executor.py`](../src/bob3/orchestrator/claude_executor.py).

Bob3 spawns four kinds of sub-agent. Each gets a different system
prompt, MCP set, and tool allowlist.

| Sub-agent | Spawned by | MCP set | Purpose |
|---|---|---|---|
| **Implementation** | `spawn_implementation_agent` | bob3-memory + puppeteer (opt) + perplexity (when key set) | Write the feature. Driven by orientation prompt + acceptance criteria + skills. |
| **Research** | `spawn_research_agent` | perplexity only | Web research via Perplexity MCP, returns findings as structured text. No FS access. |
| **Decomposer** | `spawn_decomposer_agent` | none (cwd has FS access for reading existing code) | Split an oversized feature into child features in the DB. |
| **RCA** | `spawn_rca_agent` | none (works from failure-evidence blob) | Run the F106 Systematic Debugging Protocol on a failed feature; return a JSON action recommendation. |

Each spawn returns a `SpawnResult` with the `ExecutionResult`
(text, is_error, num_turns, duration_ms, total_cost_usd) and an
`agent_run` row pointer in the `sub_agent_runs` DB table.

---

## The skills system

Source: [`src/bob3/skills/`](../src/bob3/skills/) and
[`src/bob3/skills_installer.py`](../src/bob3/skills_installer.py).

Skills are markdown files Claude Code auto-discovers in a project
workspace. Bob3 ships nine of them, each a `SKILL.md` with YAML
frontmatter describing when the skill applies. Before each
implementation sub-agent spawn, `skills_installer` symlinks the
bundled skills into `<workspace>/.claude/skills/` so the sub-agent
sees them.

The bundled skills:

| Skill | When the agent applies it |
|---|---|
| `using-bob3-memory` | At session start; teaches the memory_search / memory_add tool surface |
| `checking-review-registry` | Before writing code in any file; query past findings |
| `researching-unknowns` | When a fact is missing; how to use Perplexity MCP |
| `brainstorming-approaches` | When multiple plausible designs exist; structured comparison |
| `implementing-acceptance-criteria` | When a criterion is ambiguous; how to break it down |
| `test-driven-development` | Always (TDD mode); red → green → refactor |
| `no-stubs-no-mocks` | Always; what counts as a stub, how the AST scanner detects them |
| `systematic-debugging` | Whenever a test fails; F106 IRON LAW protocol |
| `adversarial-self-review` | Before declaring a feature done; six-point red team |

Skills are **bob3-managed**: the installer audits symlinks before
each spawn (`verify_skills_integrity`) and force-replaces any
entry that has been turned into a real directory or repointed to
a path outside the current bob3 install. Users who want to add
their own skills should use unique names that don't collide.

This auto-installation is why every sub-agent has the same
disciplined behavior — TDD, AST stub avoidance, registry-checking,
adversarial review — without bob3 having to inject those rules
into every prompt directly.

---

## The verification checklist

Source: [`src/bob3/superpowers.py`](../src/bob3/superpowers.py)
and [`src/bob3/enhanced_verification.py`](../src/bob3/enhanced_verification.py).

Run after **every** sub-agent spawn (R10-014: even on `is_error=True`).
Eight checks:

| Check | What it asserts |
|---|---|
| `source_files_exist` | At least one Python file in `src/` |
| `package_has_substance` | Non-`__init__` modules in the package |
| `test_files_exist` | At least one `tests/test_*.py` |
| `no_stubs_in_source` | AST scan finds no `pass`, `...`, `raise NotImplementedError`, or single-`return literal` placeholder |
| `no_mocks_in_source` | `mock` imports only in `tests/`, never in `src/` |
| `tests_pass` | Full pytest run; timeout scales with project size (R10-020) |
| `code_changes_made` | Recently-modified files in src/ or tests/ |
| `acceptance_criteria_met` | Each criterion evaluated individually |

Each check returns `{name, passed, severity, details}`. Severity is
`error` (blocks completion) or `warning` (logged, doesn't block).

The AST stub detector ([`ast_checks.py`](../src/bob3/ast_checks.py))
uses a Python parser, not regex: it ignores docstrings, recognizes
`return <literal>` as suspicious only when the function name implies
computation, and lets through legitimate empty `__init__` methods.

The acceptance-criterion DSL evaluator
([`enhanced_verification.py`](../src/bob3/enhanced_verification.py))
recognizes:

- `File exists: <path>` — direct filesystem check
- `Function defined: <module.func>` — AST search for the def
- `pytest: tests/path::test_name` — runs that single pytest node
- `pytest: tests/path` — runs all tests in the file/dir
- `python: <expression>` — evaluates with `assert` semantics, in a
  banned-operations sandbox (no subprocess, no os.system, etc.)

Per-criterion timeouts are independent of the bundled `tests_pass`
timeout. The default per-criterion timeout is `BOB3_CRITERION_EXEC_TIMEOUT`
(default 600 s).

---

## Memory — bob3-memory

Source: [`src/bob3/memory.py`](../src/bob3/memory.py),
[`src/bob3/memory_mcp.py`](../src/bob3/memory_mcp.py),
[`src/bob3/mcp_lifecycle.py`](../src/bob3/mcp_lifecycle.py).

Bob3's memory is **in-process and local**: mem0ai for the higher-level
add/search API, FastEmbed (ONNX, CPU) for embeddings via
`BAAI/bge-small-en-v1.5` (~90 MB, downloads on first use), and
Qdrant on-disk for the vector store. No external services, no
`OPENAI_API_KEY`, no daemon — everything lives in
`~/.bob3/memory/`.

The four pools:

| Pool | What goes in |
|---|---|
| `facts` | Project / domain facts, architecture decisions |
| `preferences` | User style preferences, tool choices |
| `lessons` | Things learned the hard way; debug solutions; recurring-pattern observations |
| `context` | Current-task context; goes stale; archived periodically |

The pools are **search-isolated by default** but can be queried
across-pool. Sub-agents are taught (via the `using-bob3-memory`
skill) to:

1. Search before starting work: `memory_search("<feature topic>")`
2. Add lessons after debugging: `memory_add("TRIGGER... LESSON... SOLUTION...", pool="lessons")`
3. Record feedback on retrieved memories: `memory_record_feedback(id, success=True/False)`

Memory is exposed to sub-agents as **MCP tools** (`memory_search`,
`memory_add`, etc.) via `memory_mcp.py`. The orchestrator itself
uses `memory_client.py` (a thin in-process wrapper) for non-sub-agent
operations.

The MCP server is started/stopped per-run by `mcp_lifecycle.py`;
the lifecycle log lines `bob3-memory MCP server started/stopped`
in `bob3 run` output are this.

---

## MCP integration

Source: [`src/bob3/orchestrator/mcp_config.py`](../src/bob3/orchestrator/mcp_config.py).

Bob3 supports three MCP plugins:

| Plugin | Where it runs | Sub-agents that see it |
|---|---|---|
| `bob3-memory` | Local Python subprocess | All implementation sub-agents (always) |
| `perplexity` | npx-launched node process; uses `PERPLEXITY_API_KEY` | Research sub-agents (always); implementation (when key is set) |
| `puppeteer` | npx-launched node process | Implementation sub-agents only when feature opts in (`enable_puppeteer=True`) |

The decisions of "which MCPs does this sub-agent get?" are taken
per-spawn, so research agents don't waste setup time loading memory
or puppeteer, and implementation agents don't load puppeteer
unless they need it.

---

## The findings registry

See [`adversarial_review.md`](adversarial_review.md) for the full
loop. In short:

- `reviews/findings.yaml` — version-controlled bug record, R<round>-<n> ids
- `bob3.reviews.Registry` — Python API: load, search, add, mark_fixed
- `bob3 show-reviews` — CLI for human / sub-agent search
- Bundled skill `checking-review-registry` — pre-impl query
- Bundled skill `adversarial-self-review` — post-impl red team

This is the second layer of bug-catching beyond the verifier.

---

## Calibration tracking

Source: [`src/bob3/db.py`](../src/bob3/db.py) (`create_or_update_calibration`,
`list_calibration_alerts`), CLI: `bob3 show-calibration`.

Every feature attempt is recorded with `(task_class, confidence_bucket,
predicted_outcome, actual_outcome)`. Over time, bob3 can tell you:

- *"For features in the `database-migration` class with predicted
  confidence 0.7-0.8, the actual success rate is 45%."*
- *"The overall calibration is overconfident by ~0.2 in the
  high-confidence bucket."*

Calibration alerts fire when predicted vs actual diverges past a
threshold. The data lives in the `calibration_data` and
`calibration_alerts` tables; queryable via the CLI.

This is how bob3 learns whether its own confidence estimates are
trustworthy.

---

## Regression detection + rollback cascade

Sources: pre/post pytest snapshots in
[`run_loop.py`](../src/bob3/orchestrator/run_loop.py),
`db.detect_regression`, `db.rollback_feature_cascade`,
[`git_ops.revert_feature`](../src/bob3/git_ops.py).

After each feature completes:

1. The pre-execution snapshot (per-test pass/fail verdicts) is
   compared against the post-execution snapshot.
2. Any test that flipped from pass to fail is recorded as a
   `regression_event` for this feature.
3. If a regression is detected, the operator can run
   `bob3 show-regressions` to see exactly which tests broke and
   in which feature.
4. To revert: `db.rollback_feature_cascade(feature_id)` walks the
   dependency tree, marks all affected features `rolled_back`, and
   `git_ops.revert_feature` reverts the corresponding commits in
   one transaction.

This is the safety net for sub-agents that "complete" a feature by
breaking previously-working tests in a different module.

---

## Resume after interruption

Sources: signal handler ([`signal_handler.py`](../src/bob3/signal_handler.py)),
checkpoint creation in `run_loop._create_interruption_checkpoint`,
recovery scan `_resume_interrupted_work`.

When SIGINT or SIGTERM fires:

1. The async-signal-safe handler in `signal_handler.py` sets a
   flag — and only sets a flag (no I/O, since signal handlers
   firing during `conn.commit()` would deadlock the SQLite lock).
2. The orchestration loop's main loop checks the flag at the top
   of each iteration. On the first check after the signal, the
   loop:
   - Marks any in-flight feature as `interrupted` (not `failed`).
   - Creates a checkpoint row in `resource_checkpoints`.
   - Stops the MCP server gracefully.
   - Returns from `run()`.

On the next `bob3 run`, `_resume_interrupted_work` runs first.
It finds all `interrupted` features and resets them to `ready` so
the normal scheduler picks them up again. No state is lost.

This is *not* the same as `needs_human` — interrupted features
auto-resume; needs_human ones don't. The difference is whether
bob3 thinks the work needs attention or just got cut short.

---

## Cost normalization

Source: `_normalize_cost` in
[`run_loop.py`](../src/bob3/orchestrator/run_loop.py).

The Anthropic SDK returns `total_cost_usd=None` when the sub-agent
ran on a Claude Code Max Pro OAuth subscription (no per-call
billing visible to the SDK). Bob3 still needs to enforce a budget
in those cases, so:

- If `total_cost_usd` is a real number, use it.
- If it's `None` but `num_turns` is positive, fall back to a
  proxy: `num_turns * $0.05`. This isn't an actual dollar figure
  but it tracks roughly with cost on the API plan.
- The proxy gets logged once per feature so operators don't get
  surprised by a "$0 cost" in `bob3 status`.

The single canonical writer is `_increment_cost(cost, source)`.
All four sub-agent kinds (implementation, research, decomposer,
RCA) plus the verification path route their costs through it.

---

## Self-verifiability — the bootstrap spec

Source: [`examples/00_bootstrap_spec.yaml`](../examples/00_bootstrap_spec.yaml).

The spec at `examples/00_bootstrap_spec.yaml` describes bob3
itself — the orchestration loop, the verification checklist, the
memory layer, the registry. Running `bob3 run` against
`bootstrap_spec.yaml` will rebuild bob3 from scratch (in a
separate workspace).

This isn't a marketing point; it's a stress test. The bootstrap
spec is what catches "I broke spawn_research_agent and shipped"
because bob3 fails to build itself. New features that change the
loop structure are required to update the bootstrap spec to match.

---

## Reading order for new contributors

If you're trying to understand the codebase from cold:

1. This doc (`architecture.md`) — gets you the map.
2. [`failure_handling.md`](failure_handling.md) — the most complex
   part of the loop and the densest documentation.
3. [`adversarial_review.md`](adversarial_review.md) — the
   second-line defense and the registry pattern.
4. [`swedish_circle_example.md`](swedish_circle_example.md) — see
   it all running on a real build.
5. `src/bob3/orchestrator/run_loop.py` — read top-to-bottom; the
   sections are clearly delimited and many comments reference
   specific R10-* findings.
6. `src/bob3/superpowers.py` — the verification checklist
   implementation.
7. `src/bob3/skills/*/SKILL.md` — what every sub-agent reads on
   spawn.
