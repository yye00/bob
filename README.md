# BOB: Build Orchestration Bot

<p align="center">
  <strong>A production-ready autonomous coding framework for AI-assisted software development</strong>
</p>

<p align="center">
  <a href="#installation">Installation</a> |
  <a href="#quick-start">Quick Start</a> |
  <a href="#features">Features</a> |
  <a href="#architecture">Architecture</a> |
  <a href="#cli-reference">CLI Reference</a> |
  <a href="#configuration">Configuration</a>
</p>

---

## Overview

**BOB (Build Orchestration Bot)** is a generalized, production-ready framework for autonomous AI-assisted software development. It manages multiple projects simultaneously, supports flexible specification formats, and provides robust orchestration for long-running development tasks.

BOB evolved from the [Anthropic Claude Quickstarts - Autonomous Coding Demo](https://github.com/anthropics/claude-code/tree/main/claude-quickstarts/autonomous-coding), addressing real-world production needs including multi-project management, cost tracking, parallel execution, and intelligent failure recovery.

### Why BOB?

| Capability | Traditional Approach | BOB |
|------------|---------------------|-----|
| **Project Management** | Single project, manual switching | Multi-project with isolated state |
| **Data Persistence** | Flat JSON files | SQLite with transactions & indexes |
| **Cost Control** | No visibility | Real-time tracking with budget limits |
| **Task Execution** | Sequential only | Parallel execution with dependencies |
| **Failure Handling** | Manual intervention | Automatic escalation & recovery |
| **Observability** | Text log files | Structured JSON logging & metrics |
| **Configuration** | Hardcoded values | Per-project customization |
| **Recovery** | Start over | Checkpoint & resume |

---

## Installation

### Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- An Anthropic API key or Claude Code OAuth token

### Quick Install

```bash
# Clone the repository
git clone https://github.com/yye00/bob.git
cd bob

# Run the setup script
./init.sh

# Or manually with uv:
uv venv
uv pip install -e ".[dev]"

# Or with pip:
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Environment Setup

```bash
# Required: API authentication (one of these)
export CLAUDE_CODE_OAUTH_TOKEN='...'  # When running under Claude Code
export ANTHROPIC_API_KEY='...'        # For standalone usage

# Optional: Research features
export PERPLEXITY_API_KEY='...'       # Enables Perplexity research

# Optional: GitHub integration
export GITHUB_TOKEN='...'             # For GitHub Issues spec source
```

### Verify Installation

```bash
# Check version
bob version

# Run self-test
bob --help

# Run test suite
pytest tests/ -v
```

---

## Quick Start

### 1. Initialize BOB

```bash
bob init
```

This creates the BOB data directory (`~/.bob/`) with default configuration.

### 2. Create a Project

```bash
# From a YAML spec file
bob project create my-app ./workspace file://spec.yaml

# From GitHub issues
bob project create my-app ./workspace github://owner/repo?label=ai-implement
```

### 3. Write Your Spec

Create `spec.yaml`:

```yaml
name: My Web Application
description: A full-stack web application with user authentication

defaults:
  priority: medium
  category: functional

tasks:
  - id: setup-project
    title: Initialize Project Structure
    description: |
      Create the basic project structure with:
      - Express.js backend with TypeScript
      - React frontend with Vite
      - Shared types package
    acceptance_criteria:
      - Backend server starts on port 3000
      - Frontend dev server starts on port 5173
      - TypeScript compilation succeeds
    priority: critical
    labels: [setup, infrastructure]

  - id: database-setup
    title: Configure Database
    depends_on: [setup-project]
    description: Set up PostgreSQL with Prisma ORM
    acceptance_criteria:
      - Database connection established
      - Migrations run successfully
      - Basic CRUD operations work
    priority: critical

  - id: user-authentication
    title: Implement User Authentication
    depends_on: [setup-project, database-setup]
    description: |
      JWT-based authentication system.
      REQUIRES RESEARCH on secure token storage.
    research_required: true
    research_queries:
      - "JWT refresh token best practices 2026"
      - "secure httpOnly cookie vs localStorage"
    acceptance_criteria:
      - User can register with email/password
      - User can login and receive tokens
      - Protected routes require valid token
    priority: critical
    labels: [auth, security]
```

### 4. Run the Agent

```bash
# Set active project
bob project use my-app

# Run with default settings
bob run

# Run with parallel execution
bob run --parallel 3

# Dry run to preview
bob run --dry-run
```

### 5. Monitor Progress

```bash
# Overall status
bob status

# Task list
bob task list
bob task list --status in_progress

# Real-time logs
bob logs --follow

# Cost report
bob costs
```

---

## Features

### Multi-Project Management

BOB manages multiple independent projects, each with isolated:
- Task specifications and state
- Configuration and model preferences
- Cost tracking and budgets
- Session history and checkpoints

```bash
# Create projects
bob project create frontend ./projects/frontend file://frontend-spec.yaml
bob project create backend ./projects/backend file://backend-spec.yaml
bob project create mobile ./projects/mobile github://org/mobile-app

# List all projects
bob project list

# Switch active project
bob project use frontend

# View project status
bob project status backend

# Delete a project
bob project delete old-project --yes --delete-workspace
```

### Flexible Spec Sources

#### Task Priority Values

Priority must be one of these string values:
- `critical` - Blocking issues, must be done first
- `high` - Important features, high business value
- `medium` - Standard priority (default)
- `low` - Nice-to-have, can be deferred

#### File-Based Specs (YAML, JSON, Markdown)

**YAML** (recommended):
```yaml
tasks:
  - id: feature-1
    title: My Feature
    description: Implement the feature
    priority: critical
```

**JSON**:
```json
{
  "tasks": [
    {"id": "feature-1", "title": "My Feature", "priority": "critical"}
  ]
}
```

**Markdown**:

> **Note**: Task IDs in Markdown format must follow the pattern `[A-Z]\d+` (e.g., F001, M001, A123).

```markdown
## F001: My Feature [priority:critical] [category:functional]

Implement the feature with the following requirements...

### Acceptance Criteria
- Criterion 1
- Criterion 2

### Steps
1. Step 1
2. Step 2
```

#### GitHub Issues

Sync tasks directly from GitHub issues:

```bash
bob project create my-project ./workspace \
  github://owner/repo?label=ai-implement&state=open
```

Issues are parsed for:
- Title → Task title
- Body → Description and acceptance criteria
- Labels → Task labels and priority
- Assignees → Metadata

### Intelligent Task Execution

#### Dependency-Aware Scheduling

Tasks specify dependencies that BOB respects:

```yaml
tasks:
  - id: database
    title: Set up database

  - id: api
    title: Build API
    depends_on: [database]

  - id: frontend
    title: Build frontend
    depends_on: [api]
```

BOB builds a DAG and executes tasks in valid topological order.

#### Parallel Execution

Independent tasks run concurrently:

```bash
# Run up to 3 tasks in parallel
bob run --parallel 3
```

BOB automatically identifies tasks with no blocking dependencies.

### Escalation System

When a task fails, BOB follows an intelligent escalation path:

```
┌─────────────────────────────────────────────────────────────────┐
│                      ESCALATION PIPELINE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Task Attempt                                                    │
│      │                                                           │
│      ▼                                                           │
│  ┌─────────────────────┐                                        │
│  │  SONNET             │  Fast, cost-effective                  │
│  │  (3 attempts)       │  $3/$15 per 1M tokens                  │
│  └──────────┬──────────┘                                        │
│             │ still failing                                      │
│             ▼                                                    │
│  ┌─────────────────────┐                                        │
│  │  OPUS               │  More capable                          │
│  │  (3 attempts)       │  $15/$75 per 1M tokens                 │
│  └──────────┬──────────┘                                        │
│             │ still failing                                      │
│             ▼                                                    │
│  ┌─────────────────────┐                                        │
│  │  DIAGNOSIS          │  Root cause analysis                   │
│  │                     │  Classifies failure type               │
│  └──────────┬──────────┘                                        │
│             │                                                    │
│             ▼                                                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Action based on failure type:                           │    │
│  │                                                          │    │
│  │  TOO_BIG ─────────▶ DECOMPOSE into subtasks             │    │
│  │  MISSING_INFO ────▶ RESEARCH with Perplexity            │    │
│  │  WRONG_INFRA ─────▶ REQUEST_USER for help               │    │
│  │  BAD_ASSUMPTIONS ─▶ RESTRUCTURE approach                │    │
│  │  NEEDS_RESEARCH ──▶ RESEARCH specific topics            │    │
│  │  DEPS_NOT_MET ────▶ SKIP until deps ready               │    │
│  │  UNKNOWN ─────────▶ REQUEST_USER intervention           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Failure Types

| Type | Description | Action |
|------|-------------|--------|
| `TOO_BIG` | Task is too complex | Decompose into subtasks |
| `MISSING_INFO` | Lacks domain knowledge | Research with Perplexity |
| `WRONG_INFRA` | Missing tools/packages | Request user intervention |
| `BAD_ASSUMPTIONS` | Fundamental approach wrong | Research and restructure |
| `NEEDS_RESEARCH` | Specific research needed | Research specific queries |
| `DEPS_NOT_MET` | Dependencies not satisfied | Skip until ready |
| `UNKNOWN` | Cannot determine cause | Request user help |

### Research-First Workflow

Mark tasks that need research *before* implementation:

```yaml
tasks:
  - id: optimize-database
    title: Database Query Optimization
    description: |
      Optimize slow queries identified in production.
      REQUIRES RESEARCH on PostgreSQL query optimization.
    research_required: true
    research_queries:
      - "PostgreSQL EXPLAIN ANALYZE interpretation"
      - "Index optimization strategies for large tables"
      - "Query plan caching in PostgreSQL 16"
```

Benefits:
- **Proactive**: Research happens before wasted attempts
- **Guided**: Spec authors provide domain-specific queries
- **Persistent**: Findings survive across sessions
- **Cost-efficient**: Avoids expensive Opus escalations

```bash
# View tasks needing research
bob task list --needs-research

# Manually trigger research
bob research <task-id>
```

### Cost Tracking & Budget Control

BOB tracks every token and calculates costs in real-time:

```bash
# View cost breakdown
bob costs

# Output:
# Project: my-app
# ─────────────────────────────────────
# Total Cost: $45.67
#
# By Model:
#   claude-sonnet-4-5: $32.10 (70.3%)
#   claude-opus-4-5:   $13.57 (29.7%)
#
# By Agent:
#   coding:     $38.00
#   research:   $4.50
#   diagnosis:  $3.17
#
# By Day:
#   2026-01-18: $23.45
#   2026-01-19: $22.22
```

Set budget limits in configuration:

```yaml
# ~/.bob/config.yaml
limits:
  max_cost_per_project: 100.0  # USD
  max_cost_per_session: 5.0
  warn_at_percent: 80
```

### Observability

#### Structured Logging

All events are logged as structured JSON:

```json
{
  "timestamp": "2026-01-20T10:30:00Z",
  "level": "INFO",
  "event": "task_completed",
  "project_id": "my-app",
  "task_id": "auth-login",
  "session_id": "sess_abc123",
  "duration_ms": 45000,
  "model": "claude-sonnet-4-5-20250929",
  "tokens": {
    "input": 15000,
    "output": 3000,
    "cache_read": 12000
  },
  "cost_usd": 0.045
}
```

#### Log Commands

```bash
# Stream all logs
bob logs --follow

# Filter by level
bob logs --level ERROR

# Filter by event type
bob logs --event task_failed

# View specific session
bob logs --session sess_abc123

# JSON output for scripting
bob logs --json | jq '.event'
```

### Checkpointing & Resume

Sessions are automatically checkpointed:

```bash
# Resume from last checkpoint
bob run --resume

# Resume specific checkpoint
bob run --resume <checkpoint_id>
```

### Plugin Architecture

Extend BOB with custom plugins:

```python
from bob.plugins.base import Plugin, AgentPlugin, SpecSourcePlugin

class MyCustomPlugin(AgentPlugin):
    name = "my-plugin"
    version = "1.0.0"

    async def on_load(self, bob):
        print(f"Loading {self.name}")

    def get_agent_configs(self):
        return [
            AgentConfig(
                agent_type=AgentType.CUSTOM,
                name="my-agent",
                model="claude-sonnet-4-5-20250929",
                system_prompt="You are a specialized agent...",
            )
        ]
```

```bash
# List plugins
bob plugin list

# Enable/disable plugins
bob plugin enable my-plugin
bob plugin disable my-plugin
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              BOB CLI                                     │
│                                                                          │
│  bob project | bob task | bob run | bob status | bob logs | bob costs   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────────┐ │
│  │ Project        │  │ Spec Sources   │  │ Agent Registry             │ │
│  │ Manager        │  │                │  │                            │ │
│  │                │  │ ├─ FileSource  │  │ ├─ CodingAgent             │ │
│  │ ├─ Create      │  │ │  (YAML/JSON) │  │ ├─ ResearchAgent           │ │
│  │ ├─ List        │  │ │  (Markdown)  │  │ ├─ DiagnosisAgent          │ │
│  │ ├─ Delete      │  │ ├─ GitHubSource│  │ ├─ DecompositionAgent      │ │
│  │ └─ Switch      │  │ └─ (Extensible)│  │ └─ (Custom via plugins)    │ │
│  └───────┬────────┘  └───────┬────────┘  └─────────────┬──────────────┘ │
│          │                   │                         │                 │
│  ┌───────▼───────────────────▼─────────────────────────▼───────────────┐│
│  │                    Orchestration Engine                              ││
│  │                                                                      ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  ││
│  │  │ Task Queue   │  │ Session      │  │ Escalation Controller    │  ││
│  │  │              │  │ Manager      │  │                          │  ││
│  │  │ ├─ Priority  │  │              │  │ ├─ Model tier switching  │  ││
│  │  │ ├─ DAG deps  │  │ ├─ Create    │  │ ├─ Failure classification│  ││
│  │  │ ├─ Parallel  │  │ ├─ Checkpoint│  │ ├─ Task decomposition    │  ││
│  │  │ └─ Ready set │  │ └─ Resume    │  │ └─ Research triggering   │  ││
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  ││
│  │                                                                      ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  ││
│  │  │ Research     │  │ Task         │  │ Failure Classifier       │  ││
│  │  │ Controller   │  │ Decomposer   │  │                          │  ││
│  │  │              │  │              │  │ Analyzes errors to       │  ││
│  │  │ Perplexity + │  │ Breaks large │  │ determine failure type   │  ││
│  │  │ Web Search   │  │ tasks down   │  │ and recommended action   │  ││
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │                      Persistence Layer                                ││
│  │                                                                       ││
│  │  SQLite Database (~/.bob/bob.db)                                     ││
│  │  ├─ projects      - Project definitions and config                   ││
│  │  ├─ tasks         - Task specs, state, escalation info               ││
│  │  ├─ sessions      - Session history with token/cost tracking         ││
│  │  ├─ events        - Structured event log                             ││
│  │  └─ checkpoints   - Session state for resume                         ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │                      Observability Layer                              ││
│  │                                                                       ││
│  │  ├─ Structured JSON Logger    - All events with metadata             ││
│  │  ├─ Cost Tracker              - Token usage and USD costs            ││
│  │  └─ Metrics                   - Task completion, escalations, etc.   ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Details

| Component | Location | Purpose |
|-----------|----------|---------|
| CLI | `bob/cli/` | User interface commands |
| Models | `bob/models/` | Data classes (Project, Task, Session) |
| Database | `bob/database/` | SQLite persistence layer |
| Orchestrator | `bob/orchestrator/` | Task execution engine |
| Spec Sources | `bob/spec_sources/` | Spec file parsers |
| Research | `bob/research/` | Perplexity/web search integration |
| Observability | `bob/observability/` | Logging and cost tracking |
| Plugins | `bob/plugins/` | Extension system |
| Prompts | `bob/prompts/` | Template engine for agent prompts |
| Security | `bob/security/` | Command allowlist and sandboxing |

---

## CLI Reference

### Global Options

```bash
bob [OPTIONS] COMMAND [ARGS]

Options:
  -v, --verbose       Enable verbose output
  -q, --quiet         Suppress non-essential output
  --json              Output in JSON format
  -p, --project TEXT  Override active project
  --db PATH           Custom database path
  --version           Show version
  --help              Show help
```

### Project Commands

```bash
# Create a new project
bob project create <name> <workspace> <spec-source>
bob project create my-app ./workspace file://spec.yaml
bob project create my-app ./workspace github://owner/repo?label=implement

# List all projects
bob project list
bob project list --status active
bob project list --json-output

# Show project details
bob project status <name>
bob project status my-app --json-output

# Set active project
bob project use <name>

# Delete a project
bob project delete <name>
bob project delete my-app --yes --delete-workspace
```

### Task Commands

```bash
# List tasks
bob task list
bob task list --status pending
bob task list --status failed
bob task list --priority critical
bob task list --needs-research
bob task list --json

# Show task details
bob task show <task-id>
bob task show F001 --research      # Include research findings
bob task show F001 --escalation    # Include escalation history

# Retry a failed task
bob task retry <task-id>

# Skip a task
bob task skip <task-id> --reason "Not needed for MVP"

# Add a task manually
bob task add --title "New feature" --description "..." --priority high
```

### Execution Commands

```bash
# Run the agent
bob run
bob run --task F001              # Run specific task
bob run --parallel 3             # Run 3 tasks concurrently
bob run --max-turns 50           # Limit turns per session
bob run --max-sessions 10        # Limit total sessions
bob run --model opus             # Force specific model
bob run --dry-run                # Preview without executing
bob run --resume                 # Resume from checkpoint
bob run --json                   # JSON output

# Trigger research for a task
bob research <task-id>

# Sync with spec source
bob sync
bob sync --force                 # Force full resync
```

### Monitoring Commands

```bash
# Global status
bob status
bob status --json

# View logs
bob logs
bob logs --follow                # Stream in real-time
bob logs --level ERROR           # Filter by level
bob logs --event task_completed  # Filter by event
bob logs --session <id>          # Specific session
bob logs --json                  # JSON output

# Cost breakdown
bob costs
bob costs --project my-app
bob costs --json-output
```

### Configuration Commands

```bash
# Show configuration
bob config show
bob config show --json

# Set a value
bob config set models.default claude-opus-4-5-20251101
bob config set limits.max_cost_per_project 50.0

# Edit in editor
bob config edit
```

### Plugin Commands

```bash
# List plugins
bob plugin list

# Enable/disable
bob plugin enable <name>
bob plugin disable <name>
```

### Utility Commands

```bash
# Initialize BOB
bob init

# Show version
bob version

# Show examples
bob examples
```

---

## Configuration

### Global Configuration

Location: `~/.bob/config.yaml`

```yaml
# Model configuration
models:
  default: claude-sonnet-4-5-20250929
  escalation: claude-opus-4-5-20251101

# Database settings
database:
  type: sqlite
  path: ~/.bob/bob.db

# Cost limits (USD)
limits:
  max_cost_per_project: 100.0
  max_cost_per_session: 5.0
  warn_at_percent: 80

# Escalation behavior
escalation:
  max_attempts_per_model: 3
  enable_decomposition: true
  enable_research: true

# Logging (per-project logs go to <workspace>/.bob/logs/)
logging:
  level: INFO
  format: json

# Research
research:
  engine: perplexity  # perplexity | websearch | both
  fallback_to_websearch: true
```

### Project Configuration

Location: `<project-workspace>/project.yaml`

```yaml
name: My Application
description: A full-stack web application

# Spec source
spec:
  type: file
  path: ./spec.yaml

# Workspace directory
workspace: ./workspace

# Override global model settings
models:
  default: claude-sonnet-4-5-20250929
  escalation: claude-opus-4-5-20251101

# Security settings
security:
  sandbox: true
  allowed_commands:
    - npm
    - node
    - python
    - pytest
    - git
    - docker
  filesystem_scope: ./workspace

# Agent customization
agents:
  coding:
    system_prompt: |
      You are a senior full-stack developer working on {project.name}.
      Follow these standards:
      - TypeScript for all code
      - React for frontend
      - Express for backend
      - PostgreSQL for database
    max_turns: 500

  research:
    enabled: true
    mcp_servers:
      perplexity:
        command: npx
        args: [-y, "@perplexity-ai/mcp-server"]

# Project-specific limits
limits:
  max_cost: 50.0
```

---

## Database Schema

BOB uses SQLite for persistence. Key tables:

```sql
-- Projects table
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    workspace_dir TEXT NOT NULL,
    spec_source_type TEXT NOT NULL,
    spec_source_config JSON,
    config JSON,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Tasks table
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),
    spec_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    acceptance_criteria JSON,
    steps JSON,
    depends_on JSON,
    priority TEXT DEFAULT 'medium',  -- 'critical', 'high', 'medium', 'low'
    category TEXT,
    labels JSON,
    status TEXT DEFAULT 'pending',
    assigned_agent TEXT,
    current_model TEXT,
    attempts INTEGER DEFAULT 0,
    escalation_tier INTEGER DEFAULT 0,
    failure_type TEXT,
    error_history JSON,
    research_required BOOLEAN DEFAULT FALSE,
    research_complete BOOLEAN DEFAULT FALSE,
    research_queries JSON,
    research_findings TEXT,
    parent_task_id TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Sessions table
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),
    task_id TEXT REFERENCES tasks(id),
    agent_type TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    turns INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    log_path TEXT,
    checkpoint_path TEXT
);

-- Events table (structured logging)
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    task_id TEXT,
    session_id TEXT,
    event_type TEXT NOT NULL,
    event_data JSON,
    created_at TIMESTAMP
);
```

---

## Development

### Project Structure

```
bob/
├── bob/                          # Main package
│   ├── __init__.py
│   ├── config.py                 # Configuration management
│   ├── state.py                  # State management
│   ├── cli/                      # CLI commands
│   │   ├── main.py               # Entry point
│   │   ├── project.py            # Project commands
│   │   ├── task.py               # Task commands
│   │   ├── run.py                # Run command
│   │   ├── status.py             # Status command
│   │   ├── logs.py               # Logs command
│   │   └── costs.py              # Costs command
│   ├── database/                 # Persistence layer
│   │   ├── manager.py            # Database operations
│   │   └── migrations.py         # Schema migrations
│   ├── models/                   # Data models
│   │   └── base.py               # Project, Task, Session, etc.
│   ├── orchestrator/             # Execution engine
│   │   ├── engine.py             # Main orchestrator
│   │   ├── client.py             # Claude SDK client
│   │   ├── escalation.py         # Escalation controller
│   │   ├── failure_classifier.py # Failure analysis
│   │   ├── task_decomposer.py    # Task breakdown
│   │   ├── task_queue.py         # Priority queue with DAG
│   │   ├── research_controller.py# Research workflow
│   │   ├── research_agent.py     # Perplexity integration
│   │   └── checkpoint.py         # Session checkpointing
│   ├── spec_sources/             # Spec parsers
│   │   ├── base.py               # Abstract base class
│   │   ├── file_source.py        # YAML/JSON/Markdown
│   │   └── github_source.py      # GitHub Issues
│   ├── observability/            # Monitoring
│   │   ├── logger.py             # Structured logging
│   │   └── cost_tracker.py       # Cost calculation
│   ├── plugins/                  # Extension system
│   │   ├── base.py               # Plugin base classes
│   │   └── __init__.py
│   ├── prompts/                  # Agent prompts
│   │   ├── loader.py             # Prompt loading
│   │   ├── template_engine.py    # Jinja2 templates
│   │   └── templates/            # Prompt templates
│   └── security/                 # Security
│       └── security.py           # Command allowlist
├── tests/                        # Test suite (1200+ tests)
├── examples/                     # Example projects
├── docs/                         # Documentation
├── init.sh                       # Setup script
├── requirements.txt              # Dependencies
├── setup.py                      # Package setup
└── README.md                     # This file
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=bob --cov-report=html

# Run specific test file
pytest tests/test_models.py -v

# Run specific test
pytest tests/test_models.py::TestTask::test_task_creation -v
```

### Building

```bash
# Install in development mode
pip install -e ".[dev]"

# Build distribution
python setup.py sdist bdist_wheel

# Install from wheel
pip install dist/bob_framework-*.whl
```

---

## Troubleshooting

### Common Issues

**"No API key found" error**
```bash
# Set one of these environment variables:
export CLAUDE_CODE_OAUTH_TOKEN='...'  # Under Claude Code
export ANTHROPIC_API_KEY='...'        # Standalone
```

**"No active project" error**
```bash
# Set active project:
bob project use my-app

# Or specify with -p flag:
bob -p my-app task list
```

**Tasks stuck in "pending"**
```bash
# Check for dependency issues:
bob task show <task-id>

# Check for failed dependencies:
bob task list --status failed
```

**High costs**
```bash
# Check cost breakdown:
bob costs

# Set limits in config:
bob config set limits.max_cost_per_session 2.0
```

**Finding logs**
```bash
# Logs are stored per-project in <workspace>/.bob/logs/
# View log directory for current project:
bob logs

# Log files are JSON formatted with rotation (10MB max, 5 backups)
# Example log location: ./my-project/workspace/.bob/logs/bob.log
```

---

## Roadmap

### Completed

- [x] **Phase 1: Core Foundation**
  - Project model and database schema
  - Basic CLI commands
  - Escalation logic from autonomous-coding
  - File-based spec sources (YAML, JSON, Markdown)
  - Research-first workflow
  - SQLite persistence

- [x] **Phase 2: Multi-Project & Orchestration**
  - Multi-project management
  - Task queue with dependency resolution
  - Session management
  - Progress tracking

- [x] **Phase 3: Observability & Cost**
  - Structured JSON logging
  - Cost tracking per project/session/task
  - CLI status/logs/costs commands
  - Checkpointing for resume

- [x] **Phase 4: Parallel Execution**
  - Parallel task execution
  - Concurrent session management
  - Resource management

- [x] **Phase 5: Integrations** (Partial)
  - GitHub Issues spec source
  - Plugin architecture

### Planned

- [ ] Jira spec source
- [ ] Linear spec source
- [ ] Generic REST API spec source
- [ ] Web dashboard
- [ ] VS Code extension
- [ ] Prometheus metrics export

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Contribution Guide

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes and add tests
4. Run tests: `pytest tests/ -v`
5. Submit a pull request

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

BOB is built on the foundation of the [Anthropic Claude Quickstarts - Autonomous Coding Demo](https://github.com/anthropics/claude-code/tree/main/claude-quickstarts/autonomous-coding). We're grateful to the Anthropic team for their innovative work on autonomous coding agents.

---

## Links

- **Documentation**: [docs/](docs/)
- **Examples**: [examples/](examples/)
- **Issues**: [GitHub Issues](https://github.com/yye00/bob/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yye00/bob/discussions)
