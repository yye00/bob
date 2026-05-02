# Bob3 — Build Orchestration Bot v3

A recursive build orchestration system that uses Claude Code sub-agents to research, plan, and execute software projects from a YAML specification.

Bob3 reads a spec describing the project you want built, decomposes it into features with dependencies, then drives a continuous loop that spawns Claude sub-agents to implement, test, verify, and commit each feature. It tracks cost, detects regressions, handles interrupts, and persists lessons learned across sessions.

## What makes it different

- **MCP plugin integration** — Research-mode sub-agents have access to Perplexity (web research). Implementation sub-agents have access to Bob3 Memory (local semantic memory backed by mem0ai + FastEmbed + Qdrant) and, when `PERPLEXITY_API_KEY` is set, Perplexity as well. Puppeteer (browser automation) is enabled per-feature when needed.
- **Semantic verification** — Completed features are checked against acceptance criteria with stub/mock detection, not just "did tests pass."
- **Research fallback** — Stuck features automatically trigger a research agent that queries the web before another implementation attempt.
- **Feature decomposition** — Oversized features are split into sub-features on demand.
- **Resume on interrupt** — SIGINT/SIGTERM triggers checkpoint creation; work continues on the next `bob3 run`.
- **Self-verifiable** — The included `examples/00_bootstrap_spec.yaml` is the spec that describes bob3 itself.

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
| `BOB3_FEATURE_TIMEOUT_SECONDS` | No | Wall-clock timeout in seconds for a single feature's sub-agent execution. If exceeded the feature is marked `interrupted` (no cascade), and the next `bob3 run` resumes it via the F116 auto-resume path. Use to bound runaway tool calls (e.g. a hung Puppeteer / browser MCP). Default: `3600` (1 hour). |
| `BOB3_REGRESSION_DETECTION_ENABLED` | No | Toggle the per-feature pytest snapshot pair used by F051 regression detection. When set to a falsy value (`0`, `false`, `no`, `off`), both the pre- and post-execution `capture_pytest_snapshot` calls are skipped, disabling regression detection entirely. Useful when the workspace test suite is large/slow or when regression tracking is unwanted (e.g. CI bring-up). Default: enabled. |
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

The repo ships with three example specs in `examples/`. Let's walk through running one.

### 1. Pick a spec

```
examples/
├── 00_bootstrap_spec.yaml              # Bob3 itself (the harness rebuilds itself)
├── 01_geomech_simulator_spec.yaml      # FEniCSx poromechanics simulator (28 features)
└── 02_geotech_slope_stability_spec.yaml # 2D slope stability GUI app (30 features)
```

Each spec is a complete project description with features, acceptance criteria, and V&V requirements. Pick one and read through it to understand the target.

### 2. Initialize a new project

The project name must match the `name:` field in the spec you intend to load.
For `01_geomech_simulator_spec.yaml` (name: `geomech-sim`):

```bash
bob3 init ./geomech-sim --name geomech-sim
cd ./geomech-sim
```

This creates a workspace directory and a SQLite database (`bob3.db`) for tracking state.

### 3. Load the spec

```bash
bob3 plan /path/to/bob3/examples/01_geomech_simulator_spec.yaml --create
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
