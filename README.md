# Bob3 — Build Orchestration Bot v3

A recursive build orchestration system that uses Claude Code sub-agents to research, plan, and execute software projects from a YAML specification.

Bob3 reads a spec describing the project you want built, decomposes it into features with dependencies, then drives a continuous loop that spawns Claude sub-agents to implement, test, verify, and commit each feature. It tracks cost, detects regressions, handles interrupts, and persists lessons learned across sessions.

## What makes it different

- **MCP plugin integration** — Sub-agents can use Perplexity (web research), Puppeteer (browser automation), and Bob3 Memory (local semantic memory backed by mem0ai + Ollama + Qdrant).
- **Semantic verification** — Completed features are checked against acceptance criteria with stub/mock detection, not just "did tests pass."
- **Research fallback** — Stuck features automatically trigger a research agent that queries the web before another implementation attempt.
- **Feature decomposition** — Oversized features are split into sub-features on demand.
- **Resume on interrupt** — SIGINT/SIGTERM triggers checkpoint creation; work continues on the next `bob3 run`.
- **Self-verifiable** — The included `examples/00_bootstrap_spec.yaml` is the spec that describes bob3 itself.

## Requirements

- Python >= 3.11
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
| `BOB3_MEMORY_DIR` | No | Override the on-disk path where Qdrant stores the bob3 memory collection (default: `~/.local/share/bob3`) |
| `PERPLEXITY_API_KEY` | No | Enables the Perplexity research MCP |
| `ANTHROPIC_API_KEY` | Conditional | Required only if you do not have a Claude Code OAuth subscription. With an OAuth subscription (e.g. Max Pro), the SDK uses your existing credentials and this variable is unused. `CLAUDE_API_KEY` is also accepted as an alias. |
| `BOB3_DATABASE_PATH` | No | Override the SQLite database file location (default: `<workspace>/bob3.db`). Set this when running bob3 from a directory other than the project workspace. |
| `BOB3_COST_PER_TURN_PROXY` | No | Per-turn cost proxy in USD used when the Claude Code SDK returns `total_cost_usd=None` (typical for Max Pro / OAuth subscriptions). Default: `0.05`. |
| `BOB3_CRITERION_EXEC_TIMEOUT` | No | Timeout in seconds for executable acceptance criteria (`pytest:` and `python:` prefixed criteria) evaluated by the enhanced verification layer. Default: `60`. |
| `BOB3_TEST_RUN_TIMEOUT` | No | Timeout in seconds for the auto-pytest run executed during the verification superpowers checklist. Default: `300`. |

Add to your shell profile if needed:

```bash
export PERPLEXITY_API_KEY="pplx-..."  # optional
```

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

```bash
bob3 init ./my-geomech --name "geomech-sim"
cd ./my-geomech
```

This creates a workspace directory and a SQLite database (`bob3.db`) for tracking state.

### 3. Load the spec

```bash
bob3 plan /path/to/bob3/examples/01_geomech_simulator_spec.yaml --create
```

This parses the spec and persists its features to the database. Drop `--create` to just preview.

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
├── memory.py                       # Bob3 Memory backend (mem0 + Ollama + Qdrant)
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
- **Bob3 Memory for knowledge** — Lessons, facts, and cross-session context live in the local Qdrant store (via mem0ai + Ollama), not the local DB.
- **Feature-level git commits** — Each completed feature gets its own commit for easy rollback.
- **Graceful shutdown** — SIGINT/SIGTERM checkpoints state so `bob3 run` resumes cleanly.

## License

MIT — see [LICENSE](LICENSE).
