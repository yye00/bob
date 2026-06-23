# Bob3 — Build Orchestration Bot v3

A recursive build orchestration system that uses Claude Code sub-agents to research, plan, and execute software projects from a YAML specification.

Bob3 reads a spec describing the project you want built, decomposes it into features with dependencies, then drives a continuous loop that spawns Claude sub-agents to implement, test, verify, and commit each feature. It tracks cost, detects regressions, handles interrupts, and persists lessons learned across sessions.

## What makes it different

A short tour of the distinctive pieces. Each bullet links to a
deeper doc; [`docs/architecture.md`](docs/architecture.md) is the
big-picture index.

- **Graduated failure recovery with RCA** — when a sub-agent fails, bob3 doesn't just retry: free-retries spawn-time crashes, runs verification even on errored runs, decays confidence between attempts, spawns a Root Cause Analysis agent past the second failure, and routes its recommendation (`research` / `decompose` / `mark_needs_human`). [`docs/failure_handling.md`](docs/failure_handling.md).
- **Adversarial-self-review skill + persistent findings registry** — every sub-agent red-teams its own diff before claiming done. Findings are filed to a version-controlled registry (`reviews/findings.yaml`); recurring patterns are aggregated; future sub-agents query the registry *before* writing code. [`docs/adversarial_review.md`](docs/adversarial_review.md).
- **Auto-installed skills system** — nine bundled skills (TDD, no-stubs-no-mocks, systematic debugging, brainstorming-approaches, researching-unknowns, implementing-acceptance-criteria, using-bob3-memory, checking-review-registry, adversarial-self-review) are symlinked into every sub-agent's `.claude/skills/` at spawn time. Integrity-audited per spawn.
- **Defense-in-depth verification checklist** — eight checks run after every sub-agent spawn (even on `is_error=True`): file existence, package substance, test files, AST-level stub detection, AST-level mock detection in source, project-size-aware pytest, recent file changes, per-criterion acceptance evaluation.
- **Acceptance-criterion DSL** — criteria are first-class: `File exists: <path>`, `Function defined: <module.func>`, `pytest: tests/...::test_x`, `python: <expression>` (sandboxed). Each criterion is evaluated individually with its own timeout.
- **In-process semantic memory** — Bob3 Memory uses mem0ai + FastEmbed (ONNX, CPU) + on-disk Qdrant. Four pools (`facts`, `preferences`, `lessons`, `context`) with semantic search across runs. No external embedding API, no daemon, no `OPENAI_API_KEY`.
- **MCP integration** — implementation sub-agents always get Bob3 Memory; research sub-agents get Perplexity (when `PERPLEXITY_API_KEY` is set); Puppeteer is enabled per-feature when a feature opts in.
- **Confidence calibration tracking** — every attempt records `(task_class, predicted_confidence, actual_outcome)`; `bob3 show-calibration` surfaces over-/under-confidence per bucket. Bob3 learns whether its own predictions are trustworthy.
- **Per-test regression detection + rollback cascade** — pre/post pytest snapshots are diffed after each feature; tests that flipped pass→fail are recorded as `regression_event`s; `db.rollback_feature_cascade` walks the dependency tree and `git_ops.revert_feature` reverts commits transactionally.
- **Resume-after-interruption** — async-signal-safe SIGINT/SIGTERM handler sets a flag; in-flight features are checkpointed as `interrupted`; the next `bob3 run` auto-resumes them via `_resume_interrupted_work`.
- **Cost normalization with turn proxy** — works with both `ANTHROPIC_API_KEY` and Claude Code Max Pro OAuth. When the SDK returns `total_cost_usd=None` (typical on OAuth), bob3 falls back to a `num_turns × $0.05` proxy so budget enforcement still works.
- **Self-verifiable bootstrap spec** — `examples/00_bootstrap_spec.yaml` is the spec describing bob3 itself, used as a stress test: changes to the loop must update the bootstrap spec to match.

For a worked end-to-end example with screenshots and cost data, see
[`docs/swedish_circle_example.md`](docs/swedish_circle_example.md).

## Requirements

- Linux or macOS. Windows is not currently supported (bob3 uses POSIX-only signal/process-group APIs such as `os.killpg` and `start_new_session=True`).
- Python >= 3.11
- Node.js >= 18 (required by `claude-code-sdk`)
- Claude Code CLI: `npm install -g @anthropic-ai/claude-code`
- Then: `claude` (or sign in to Claude Code Max Pro)
- A Claude Code OAuth subscription (e.g. Max Pro) **or** `ANTHROPIC_API_KEY` set in your environment — either works, you do not need both.

Bob3 Memory is fully local and in-process: it uses [FastEmbed](https://github.com/qdrant/fastembed) (ONNX, CPU) for text embeddings and [Qdrant](https://qdrant.tech/) on-disk for the vector store. The default embedding model (`BAAI/bge-small-en-v1.5`, ~90 MB) downloads automatically on first use. No external embedding API, no background daemon, no `OPENAI_API_KEY` required.

## Installation

```bash
git clone https://github.com/yye00/bob.git bob3
cd bob3
pip install -e .
```

Verify the install:

```bash
bob3 --version
bob3 --help
```

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `BOB3_EMBEDDER_MODEL` | No | Override the FastEmbed model (default: `BAAI/bge-small-en-v1.5`) |
| `BOB3_EMBEDDING_DIMS` | No | Embedding vector dimensionality used by the Qdrant collection (default: `384`, matching `BAAI/bge-small-en-v1.5`). Must match `BOB3_EMBEDDER_MODEL`; if you change the model, change this too. |
| `BOB3_MEMORY_DIR` | No | Override the on-disk path where Qdrant stores the bob3 memory collection (default: `~/.local/share/bob3`) |
| `PERPLEXITY_API_KEY` | No | Enables the Perplexity research MCP |
| `ANTHROPIC_API_KEY` | Conditional | Required only if you do not have a Claude Code OAuth subscription. With an OAuth subscription (e.g. Max Pro), the SDK uses your existing credentials and this variable is unused. `CLAUDE_API_KEY` is also accepted as an alias. |
| `BOB3_DATABASE_PATH` | No | Override the SQLite database file location (default: `<workspace>/bob3.db`). Set this when running bob3 from a directory other than the project workspace. |
| `BOB3_COST_PER_TURN_PROXY` | No | Per-turn cost proxy in USD used when the Claude Code SDK returns `total_cost_usd=None` (typical for Max Pro / OAuth subscriptions). Default: `0.05`. |
| `BOB3_CRITERION_EXEC_TIMEOUT` | No | Timeout in seconds for executable acceptance criteria (`pytest:` and `python:` prefixed criteria) evaluated by the enhanced verification layer. Default: `60`. |
| `BOB3_TEST_RUN_TIMEOUT` | No | Timeout in seconds for the auto-pytest run executed during the verification superpowers checklist. Default: `300`. |
| `BOB3_SNAPSHOT_TIMEOUT` | No | Per-snapshot pytest timeout in seconds used by the F051 regression detection capture. Falls back to `BOB3_TEST_RUN_TIMEOUT` when unset, then to `300`. |
| `BOB3_FEATURE_TIMEOUT_SECONDS` | No | Wall-clock timeout in seconds for a single feature's sub-agent execution. If exceeded the feature is marked `interrupted` (no cascade), and the next `bob3 run` resumes it via the F116 auto-resume path. Use to bound runaway tool calls (e.g. a hung Puppeteer / browser MCP). Default: `3600` (1 hour). |
| `BOB3_REGRESSION_DETECTION_ENABLED` | No | Toggle the per-feature pytest snapshot pair used by F051 regression detection. When set to a falsy value (`0`, `false`, `no`, `off`), both the pre- and post-execution `capture_pytest_snapshot` calls are skipped, disabling regression detection entirely. Useful when the workspace test suite is large/slow or when regression tracking is unwanted (e.g. CI bring-up). Default: enabled. |
| `BOB3_FAILURE_THRESHOLD_FOR_RESEARCH` | No | Number of consecutive failed feature attempts before `needs_research` Trigger 2 fires (R10-010). After 2 failures (vs the previous 3), research becomes more responsive — by failure 2 we've already burned ~2× the feature's expected cost; an expensive V&V feature needs research sooner than a cheap one. Default: `2`. Set higher (e.g. `3`) for the legacy behaviour. |
| `BOB3_CONFIDENCE_DECAY_PER_FAILURE` | No | Amount to subtract from `conf_impl_correctness`, `conf_spec_understanding`, and `readiness_score` after each failed feature attempt (R10-011). Default: `0.15`. Setting to `0.0` disables decay entirely (a feature with `conf=0.7` will retain `0.7` across all retries, recreating the previous behaviour where Trigger 3 of `needs_research` could only fire once per feature). With the default and a starting confidence of `0.7`, the second retry has `conf=0.40` which is below the `0.5` low-confidence research threshold. |
| `BOB3_RCA_ENABLED` | No | Toggle the Root Cause Analysis (RCA) sub-agent invocation from the orchestration loop's failure path (R10-009). When set to a falsy value (`0`, `false`, `no`, `off`), the loop skips `spawn_rca_agent` entirely and the failure path behaves as it did before R10-009 was wired in. Default: enabled (`1`). |
| `BOB3_RCA_TIMEOUT_SECONDS` | No | Wall-clock timeout for a single RCA sub-agent spawned by R10-009 wiring. RCA is meant to be a hypothesis-only Phase 1-4 pass, not another implementation budget; a stuck RCA must not park the orchestration loop. Default: `600` (10 minutes). |
| `BOB3_MAX_MEMORY_CONTENT_BYTES` | No | Maximum size in UTF-8 bytes accepted by the `memory_add` MCP tool. Memories above this are refused with a structured error. Default: `8000`. Tighter caps reduce the risk of a sub-agent flooding the embedder / Qdrant index, at the cost of less verbose memory entries. |

Add to your shell profile if needed:

```bash
export PERPLEXITY_API_KEY="pplx-..."  # optional
```

### Security considerations

Bob3 spawns sub-agents via the Claude Code SDK with
`permission_mode=bypassPermissions` and `cwd=<workspace>`, so a sub-agent
has full read/write access to anything inside the project workspace. The
orchestrator includes several defense-in-depth measures (cost-tampering
detection, lock-file symlink hardening, `python:` criterion allowlist,
`memory_add` size cap), but these are mitigations, not a sandbox. For
hardened deployments:

- **Place `bob3.db` outside the workspace.** Sub-agents can write to
  files in the workspace, which is fine for the source tree but means
  the SQLite database used for budget / status tracking is also
  reachable. Set `BOB3_DATABASE_PATH=/secure/path/bob3.db` (e.g. under
  your home directory) so sub-agents cannot reach the DB at all. With
  this in place, the cost-tampering detection is a defense-in-depth
  backstop, not the primary defense. **`bob3 init` honors
  `BOB3_DATABASE_PATH`:** when the env var is set, `bob3 init <project>`
  creates the database at that path (the parent directory is created
  if it doesn't exist) instead of inside the workspace. This keeps
  later `bob3 plan` / `bob3 run` / `bob3 status` commands consistent
  — they all route through the same `BOB3_DATABASE_PATH` lookup, so
  there is no way for `init` to drop a `bob3.db` inside the workspace
  that subsequent commands then can't find.
- **Run sub-agents under a confined user / container.** The trust model
  assumes the workspace is yours; if it isn't, run bob3 under a
  dedicated user account (or a container) so workspace writes can't
  reach `~/.ssh`, `~/.aws`, etc.
- **Treat workspace-scoped secrets as compromised.** Any environment
  variable inherited by `bob3 run` is visible to sub-agents (e.g. via
  the `pytest:` criterion form, which spawns a real subprocess).
  Don't put long-lived secrets in `.env` next to the workspace.

## Quickstart

The repo ships with example specs in `examples/`. The recommended starting point is `03_simple_calculator_spec.yaml` — it has stdlib-only dependencies and runs end-to-end on any machine.

### 1. Pick a spec

```
examples/
├── 00_bootstrap_spec.yaml              # Bob3 itself (the harness rebuilds itself).
│                                       # NOTE: edit `workspace:` to a path on your machine before running.
├── 01_geomech_simulator_spec.yaml      # FEniCSx poromechanics simulator (28 features).
│                                       # ASPIRATIONAL: needs fenics-dolfinx, petsc4py, mpi4py
│                                       # — HPC stack, not pip-installable on most machines.
├── 02_geotech_slope_stability_spec.yaml # 2D slope stability GUI app (30 features).
│                                       # ASPIRATIONAL: needs PyQt6 — fails on headless servers.
└── 03_simple_calculator_spec.yaml      # Simple calculator library — stdlib-only, runs anywhere.
                                        # RECOMMENDED FIRST RUN.
```

The 01 / 02 specs are kept as illustrative examples of "what a real project spec looks like"; treat them as references rather than out-of-the-box quickstart targets unless you already have the specialized dependencies on your machine.

Each spec is a complete project description with features, acceptance criteria, and V&V requirements. Pick one and read through it to understand the target.

### 2. Initialize a new project

The project name must match the `name:` field in the spec you intend to load.
For `03_simple_calculator_spec.yaml` (name: `calculator`):

```bash
bob3 init ./calculator --name calculator
cd ./calculator
```

This creates a workspace directory and a SQLite database (`bob3.db`) for tracking state.

### 3. Load the spec

```bash
bob3 plan /path/to/bob3/examples/03_simple_calculator_spec.yaml --create
```

This parses the spec and persists its features to the database. Drop `--create` to just preview.

If the spec's `name:` field doesn't match the project name from `bob3 init`, the command will exit with a "Spec name mismatch" error. Re-initialize the project with the matching name and try again.

### 4. Check what's planned

```bash
bob3 status
bob3 list-features
```

You should see all features in `pending` status with their dependency graph.

### 5. Run the orchestration loop

```bash
bob3 run --all --max-cost 50.00
```

Bob3 will:
1. Pick the highest-priority ready feature (dependencies satisfied)
2. Spawn a Claude sub-agent with orientation context + MCP tools
3. Wait for the agent to implement, write tests, and run them
4. Verify acceptance criteria were actually met (not just stubs)
5. Commit the result to git and mark the feature complete
6. Move to the next ready feature

Use `Ctrl+C` to checkpoint and stop. Re-run `bob3 run --all` to resume.

### 6. Inspect results

```bash
bob3 status --verbose
bob3 show-feature <feature-id>
bob3 show-evidence <feature-id>
bob3 show-lessons
bob3 show-calibration
bob3 show-regressions
```

## Usage

See the Quickstart above for a full walkthrough and the Commands section below for the complete reference.

## Commands

| Command | Purpose |
|---|---|
| `bob3 init <path>` | Create a new project workspace |
| `bob3 plan <spec.yaml>` | Parse a spec file (add `--create` to persist) |
| `bob3 generate-features <spec>` | Use an AI agent to generate features from a freeform spec |
| `bob3 run --all` | Start the orchestration loop |
| `bob3 run --feature <id>` | Execute a single feature |
| `bob3 status` | Show project progress and costs |
| `bob3 list-features` | List all features with their status |
| `bob3 show-feature <id>` | Detailed view of one feature |
| `bob3 show-evidence <id>` | Evidence artifacts for a feature |
| `bob3 show-lessons` | Lessons stored in Bob3 Memory |
| `bob3 show-calibration` | Confidence calibration drift |
| `bob3 show-regressions` | Active regression events |
| `bob3 show-reviews` | Search the adversarial-review findings registry |

Global options: `--version`, `-v/--verbose` (DEBUG logging), `--help`.

### Exit codes

`bob3 run` (and `bob3 run --feature`) maps the orchestration loop's
termination reason to a POSIX exit code so CI pipelines can chain
commands safely. Only `0` means "build is healthy and complete":

| Code | Termination reason | Meaning |
|---|---|---|
| `0` | `ALL_COMPLETED` | All targeted features completed successfully |
| `2` | `ALL_BLOCKED` | All remaining features are blocked / not runnable |
| `3` | `BUDGET_EXCEEDED` | The loop stopped because `--max-cost` (or the project budget) was exhausted |
| `130` | `SHUTDOWN_REQUESTED` | Graceful shutdown via SIGINT / SIGTERM (the conventional `128 + signum` for SIGINT) |
| `1` | misc errors | MCP startup failure, unknown feature ID, lock contention, invalid spec, etc. |

A common gotcha this avoids:

```bash
# Old CLI exited 0 on BUDGET_EXCEEDED, so deploy.sh ran on a partial build.
# Now: non-zero exit on BUDGET_EXCEEDED / ALL_BLOCKED stops the chain.
bob3 run --all && deploy.sh
```

### Resuming after interruption

Bob3 is designed so that interruptions (Ctrl-C, SIGTERM, machine reboot,
hung sub-agent) never lose work-in-flight irrecoverably. The recovery
pieces are:

- **Where checkpoints live.** Checkpoint state is persisted to the
  ``resource_checkpoints`` table inside ``bob3.db`` (the SQLite database
  that ``bob3 init`` creates next to your workspace, or wherever
  ``BOB3_DATABASE_PATH`` points). The signal handler writes a checkpoint
  row when a graceful shutdown is requested mid-feature.
- **What's in a checkpoint.** A JSON state snapshot with the
  ``feature_id`` that was executing, the project's
  ``total_cost_at_interrupt``, the running totals
  (``features_completed`` / ``features_failed``), and the reason
  (``graceful_shutdown``). Features that were ``executing`` at the time
  are flipped to ``interrupted`` so they're picked up on resume.
- **How to resume.** Just re-run ``bob3 run --all``. The orchestrator
  auto-detects the latest checkpoint for the project, replays the
  totals into its in-memory state, and dispatches ``interrupted``
  features back through the loop. No special flag is needed; resume
  is the default.
- **How to retry a single failed feature.** Use
  ``bob3 run --feature <id> --fresh``. ``--feature`` scopes the loop to
  exactly one feature and exits after that one iteration; ``--fresh``
  bypasses the resume path so the feature is run from scratch (existing
  evidence and prior partial commits remain in the DB / git history,
  but the in-memory loop state is not preloaded from a checkpoint).
- **Force a clean restart.** ``bob3 run --all --fresh`` skips the
  resume path entirely and resets ``interrupted`` features to
  ``ready``. Use this if you suspect the in-flight state for a feature
  was bogus (e.g. it was hung on a tool call that no longer makes
  sense) and want to start it over rather than resume mid-run.

**Troubleshooting checkpoint / DB issues.** Bob3 protects ``bob3.db``
with two layers — a per-project advisory file lock
(``<workspace>/.bob3.lock``, used by ``bob3 run`` to refuse concurrent
invocations on the same project) and SQLite's WAL journal mode (so a
crash during a write leaves the DB consistent and the WAL replays on
the next open). If the DB file alone is recovered (e.g. the WAL was
truncated by an aggressive cleanup script) it is still openable, you
just lose the most recent uncommitted transactions. To recover from a
truly corrupted DB, restore ``bob3.db`` (and the matching ``.bob3.lock``,
if you keep one) from your backup; do **not** delete the lock file by
hand while a run is in flight.

## Writing your own spec

A bob3 spec is a YAML file with a `features` section. Each feature needs a title, description, priority, dependencies, and acceptance criteria:

```yaml
name: my-project
version: "0.1.0"
description: |
  What you want built.

workspace: ~/projects/my-project   # absolute path to where bob3 should work

features:
  F001:
    title: "Short feature title"
    description: |
      Longer description of what the agent should implement.
      Include algorithm details, formulas, file names, constraints.
    priority: critical     # critical | high | medium | low
    depends_on: []         # list of feature IDs
    acceptance_criteria:
      - "Concrete, testable statement 1"
      - "Concrete, testable statement 2"
```

**Tips for good specs:**
- Make acceptance criteria numerical when possible (e.g., "L2 error < 1e-3 for fine mesh") — the verification layer can check these.
- Include V&V features that compare against analytical solutions or published benchmarks.
- Keep dependency chains shallow; deep chains mean fewer features can run in parallel.
- See `examples/` for full-scale examples.

## Built with bob3 — slope stability example

`examples/04_swedish_circle_spec.yaml` is a 19-feature spec for a 2-D
limit-equilibrium slope stability tool (Fellenius / Bishop's Simplified
on circular slip surfaces, with critical-circle search and a PyQt6 GUI).
Bob3 built it end-to-end from the spec, including V&V tests against
Taylor's stability chart and Abramson's textbook example.

For the full case study — what the Swedish Circle method is, how the
build was driven, what got escalated, which bob3 features it
exercised, and a per-shot walkthrough — see
[`docs/swedish_circle_example.md`](docs/swedish_circle_example.md).

The screenshots below were captured from the GUI bob3 produced — a
PyQt6 desktop application with menus, toolbar, dockable property panel,
zoomable/pannable canvas, drawing tools, file I/O, and a background
search engine.

**Empty MainWindow on launch** — menus (File / Edit / View / Analysis /
Help), toolbar with primary actions, dockable Properties panel showing
the current state (default material, no slope yet), and a status bar
that shows the grid spacing as you zoom.

![Empty main window](docs/screenshots/01_empty_window.png)

**Abramson textbook slope loaded** — 2H:1V slope, 10 m height, with a
flat bench beyond the crest. Properties panel updates with geometry
and material parameters as soon as the slope is set.

![Slope loaded](docs/screenshots/02_slope_geometry.png)

**Bishop critical-circle result** — slip surface in red, per-slice
boundaries drawn through the failure mass. Properties panel shows the
analysis results live: FoS = 1.902, critical center, radius, and how
many circles were evaluated.

![Critical circle result](docs/screenshots/03_critical_circle.png)

**Full FoS heatmap** — same analysis with the smooth FoS contour
overlay turned on. Red marks where critical (low-FoS) circle centers
cluster; green marks safe centers; the colormap is RdYlGn-reversed and
the heatmap is hole-filled to the immediate halo of valid centers
rather than bleeding across the entire search box.

![FoS contour heatmap](docs/screenshots/04_fos_contour.png)

**Multi-bench cut slope with phreatic surface** — seven-vertex
geometry (toe → bench → mid-crest → bench → upper plateau, 16 m
overall), water table running through the lower benches, stiff-clay
material (c′=75 kPa, φ′=20°). The properties panel reflects the new
state in full. Bishop's search returns FoS = 2.71 for this much
heavier-section problem.

![Multi-bench slope](docs/screenshots/05_multi_bench.png)

**Steeper 1.5H:1V slope** — different geometry and material (c′=15
kPa, φ′=18°). The critical surface is shallower and FoS drops to 1.46,
showing how a small geometry change shifts the result.

![Steeper slope result](docs/screenshots/06_steeper_slope.png)

**Material editor** — Mohr-Coulomb soil parameters with a preset
library, unit-aware spinbox inputs, and OK / Cancel commit semantics.

![Material dialog](docs/screenshots/07_material_dialog.png)

The build encountered (and exposed) several real bugs along the way —
documented in `reviews/findings.yaml` as `R10-*` entries. They include
recurring patterns like "verifier-correct work rejected because mtimes
were stale on a re-run" and "fixed test-run timeout doesn't scale with
project size." Each is filed with a reproducer and a fix; the registry
itself is part of how bob3 learns across runs.

To regenerate the screenshots from a freshly-built workspace:
```bash
# from inside a workspace where swedish-circle is installed
QT_QPA_PLATFORM=offscreen python /path/to/bob3.1/docs/screenshots/capture.py docs/screenshots
```

## Development

### Running the test suite

```bash
pip install -e ".[dev]"  # if dev extras are defined
pytest                   # full suite (~5 minutes, 2825 tests)
pytest tests/test_f007_cli.py -v    # a single file
pytest -k "bishop" -v               # match test names
```

### Architecture

```
src/bob3/
├── cli.py                          # Click CLI entry point
├── db.py                           # SQLite operations
├── models.py                       # Pydantic data models
├── schema.sql                      # Database schema
├── git_ops.py                      # Per-feature git commits
├── logging_config.py               # Structured logging
├── mcp_lifecycle.py                # MCP server start/stop
├── orientation.py                  # Sub-agent orientation protocol
├── pdf_utils.py                    # PDF extraction
├── memory.py                       # Bob3 Memory backend (mem0 + FastEmbed + Qdrant)
├── memory_client.py                # Async in-process memory client
├── memory_mcp.py                   # Memory MCP server for sub-agents
├── superpowers.py                  # Verification checklist + TDD detection
├── enhanced_verification.py        # Acceptance criteria validation
├── ast_checks.py                   # Stub/mock detection
├── signal_handler.py               # Graceful shutdown
└── orchestrator/
    ├── claude_executor.py          # Claude Code SDK wrapper
    ├── run_loop.py                 # Main orchestration loop
    └── mcp_config.py               # MCP configuration for sub-agents
```

### Data flow

```
spec.yaml                     examples/
    │                             │
    ▼                             ▼
bob3 plan --create   ─▶   features table (SQLite)
                              │
                              ▼
                        bob3 run --all
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
        pick ready feature          checkpoint on interrupt
                 │
                 ▼
   spawn Claude sub-agent (claude-code-sdk)
                 │
        ┌────────┴────────┐
        ▼                 ▼
   MCP tools:         feature work:
   - Perplexity       - write code
   - Puppeteer        - write tests
   - Bob3 Memory      - run tests
                 │
                 ▼
   verify acceptance criteria
                 │
        ┌────────┴────────┐
        ▼                 ▼
     passed             failed
        │                 │
        ▼                 ▼
   git commit       RCA agent → retry or escalate
```

### Key design decisions

- **Claude Code SDK only** — All Claude interactions go through `claude-code-sdk`. No subprocess CLI calls, no direct `anthropic` SDK usage.
- **SQLite for state** — Project state (features, tasks, evidence, agent runs, costs) lives in `bob3.db`.
- **Bob3 Memory for knowledge** — Lessons, facts, and cross-session context live in the local Qdrant store (via mem0ai + FastEmbed, all in-process), not the local DB.
- **Feature-level git commits** — Each completed feature gets its own commit for easy rollback.
- **Graceful shutdown** — SIGINT/SIGTERM checkpoints state so `bob3 run` resumes cleanly.

## License

MIT — see [LICENSE](LICENSE).
