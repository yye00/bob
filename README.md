# Bob3 - Build Orchestration Bot v3

A recursive build orchestration system that uses Claude Code sub-agents to research, plan, and execute software projects.

Bob3 extends Bob2 with:

- **MCP Plugin Integration** — Perplexity (web research), Puppeteer (browser automation), and TITANS Memory (persistent surprise-based learning)
- **Automatic feature generation** from natural language specs and PDFs
- **Sub-agent orientation protocol** for context recovery across sessions
- **Research-enabled sub-agents** for when implementation gets stuck

## Installation

### Requirements

- Python >= 3.11
- An active Claude Code Max Pro subscription (or `CLAUDE_API_KEY` / `ANTHROPIC_API_KEY`)
- [TITANS Memory MCP server](https://github.com/your-org/titans-memory) installed at `/home/captain/clawd/work/titans-memory`

### Install from source

```bash
git clone <repo-url> bob3
cd bob3
pip install -e .
```

Or install directly:

```bash
pip install bob3
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | For TITANS Memory MCP (embeddings via mem0ai) |
| `PERPLEXITY_API_KEY` | No | Enables Perplexity MCP for web research |
| `CLAUDE_API_KEY` | No | Handled automatically by Claude Code Max Pro subscription |

Set them in your shell profile:

```bash
export OPENAI_API_KEY="sk-..."
export PERPLEXITY_API_KEY="pplx-..."  # optional
```

## Usage

### Initialize a project

Create a new Bob3 project workspace with a SQLite database and project record:

```bash
bob3 init ./my-project
bob3 init ./my-project --name "My Project"
```

### Plan from a YAML spec

Parse a YAML specification file and display the execution plan. Use `--create` to persist features to the database:

```bash
bob3 plan spec.yaml
bob3 plan spec.yaml --create
```

### Generate features with AI

Use a Claude sub-agent to analyze a spec (and optional PDF references) and generate a feature list:

```bash
bob3 generate-features spec.yaml
bob3 generate-features spec.yaml --refs paper.pdf --output features.yaml
bob3 generate-features spec.yaml --auto-continue
```

### Run the build

Execute the orchestration loop. Sub-agents implement features, run tests, and track progress:

```bash
bob3 run --all
bob3 run --all --max-cost 50.00
bob3 run --feature <feature-id>
bob3 run --all --fresh  # skip resume, restart from scratch
```

The orchestration loop automatically:
- Picks the highest-priority ready feature
- Spawns a Claude sub-agent to implement it
- Runs tests and collects evidence
- Commits successful work via git
- Retries or triggers RCA on failure
- Resumes interrupted work on restart (unless `--fresh`)

### Check status

View project progress, feature counts, cost tracking, and per-feature details:

```bash
bob3 status
bob3 status --verbose
bob3 status --feature <feature-id>
```

### Global options

```bash
bob3 --version        # show version
bob3 --verbose <cmd>  # enable DEBUG logging
```

## Architecture

Bob3 is built around a **continuous orchestration loop** that coordinates Claude Code sub-agents via the `claude-code-sdk` Python package.

### Core components

```
src/bob3/
├── __init__.py              # Package metadata, version
├── cli.py                   # Click CLI (init, plan, run, status, generate-features)
├── db.py                    # SQLite database operations (CRUD, schema, queries)
├── models.py                # Pydantic data models (Feature, Task, Evidence, etc.)
├── schema.sql               # Database schema (projects, features, tasks, evidence, ...)
├── git_ops.py               # Git commit/revert per feature
├── logging_config.py        # Structured logging setup
├── mcp_lifecycle.py         # TITANS Memory MCP server start/stop
├── orientation.py           # Sub-agent orientation protocol
├── pdf_utils.py             # PDF text extraction (PyMuPDF)
├── titans_memory_client.py  # TITANS Memory MCP client helpers
├── ast_checks.py            # AST-based stub/mock detection
└── orchestrator/
    ├── __init__.py
    ├── claude_executor.py   # Claude Code SDK wrapper, sub-agent spawning
    ├── run_loop.py          # Orchestration loop (pick → execute → verify → commit)
    └── mcp_config.py        # MCP plugin configuration for sub-agents
```

### Data flow

1. **`bob3 init`** — Creates workspace directory and SQLite database
2. **`bob3 plan --create`** — Parses YAML spec, creates feature records with priorities and dependencies
3. **`bob3 run --all`** — Starts the orchestration loop:
   - Queries the `ready_features` view (dependencies met, not blocked)
   - Spawns a Claude sub-agent via `claude-code-sdk` with orientation context
   - Sub-agent implements the feature, writes code, runs tests
   - Results are parsed: evidence artifacts stored, confidence scores updated
   - On success: git commit, mark completed, cascade-update dependents
   - On failure: RCA agent diagnoses root cause, retry or escalate
4. **`bob3 status`** — Reads database to show progress, costs, and feature states

### Key design decisions

- **Claude Code SDK only** — All Claude interactions go through `claude-code-sdk`. No CLI subprocess calls, no `anthropic` SDK.
- **SQLite for state** — All project state (features, tasks, evidence, agent runs, costs) lives in a local `bob3.db` file.
- **TITANS Memory for knowledge** — Lessons, facts, and project context are stored in TITANS Memory MCP, not the local database.
- **Feature-level git commits** — Each completed feature gets its own git commit for easy rollback.
- **Graceful shutdown** — SIGINT/SIGTERM triggers checkpoint creation so work resumes on next run.

## License

See LICENSE file for details.
