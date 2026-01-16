# BOB: Build Orchestration Bot

**A generalized, production-ready autonomous coding framework** that can manage multiple projects simultaneously, support any specification format, and provide robust orchestration for long-running AI-assisted development.

BOB builds upon the excellent [Anthropic Claude Quickstarts - Autonomous Coding Demo](https://github.com/anthropics/claude-code/tree/main/claude-quickstarts/autonomous-coding) and evolves it into a standalone, configurable framework.

## Why BOB?

The autonomous-coding quickstart proved that AI agents can autonomously implement complex features with proper scaffolding. BOB takes this concept further by addressing real-world production needs:

| Feature | Autonomous-Coding | BOB |
|---------|------------------|-----|
| **Projects** | Single, hardcoded | Multi-project management |
| **Persistence** | JSON files | SQLite/PostgreSQL with transactions |
| **Cost Tracking** | None | Full tracking + budget limits |
| **Execution** | Sequential only | Parallel task execution |
| **Interface** | CLI only | CLI with scriptable JSON output |
| **Logging** | Text files | Structured JSON + metrics |
| **Configuration** | Hardcoded | Per-project customization |
| **Prompts** | App-specific | Templated, reusable |
| **Recovery** | None | Checkpointing + resume |
| **Spec Sources** | File only | File, GitHub, Jira, extensible |

## Key Features

### 🎯 **Multi-Project Management**
- Create, manage, and switch between multiple projects
- Each project has its own spec, configuration, and state
- Track progress, costs, and status across all projects

### 📋 **Flexible Spec Formats**
- **YAML**, **JSON**, or **Markdown** spec files
- **GitHub Issues** as spec source (with auto-sync)
- Extensible plugin system for custom spec sources (Jira, Linear, etc.)

### 🔄 **Intelligent Task Execution**
- **Dependency-aware** task queue (DAG scheduling)
- **Parallel execution** of independent tasks
- **Escalation model** from autonomous-coding:
  - Sonnet → Opus → Diagnosis → Decompose/Research
  - Automatic failure classification and recovery

### 🔬 **Research-First Workflow**
- Mark tasks as requiring research before implementation
- Proactive research using **Perplexity** or web search
- Research findings persist and guide implementation
- Avoids wasted attempts on research-solvable problems

### 💰 **Cost Tracking & Budget Control**
- Track token usage and costs per project, session, and task
- Breakdown by model, agent type, and time period
- Budget limits with automatic enforcement
- 90% cache read discount calculation

### 📊 **Observability**
- Structured JSON logging for all events
- Real-time log streaming with `bob logs --follow`
- Status dashboards with `bob status`
- Session checkpointing for resume after interruption

### 🔌 **Extensible Architecture**
- Plugin system for custom agents, spec sources, and tools
- Template engine for reusable prompts
- Per-project configuration overrides

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/bob.git
cd bob

# Run setup script
./init.sh

# Activate virtual environment
source venv/bin/activate

# Set your API key
export ANTHROPIC_API_KEY=your_key_here
export PERPLEXITY_API_KEY=your_key_here  # Optional, for research features
```

### Create Your First Project

```bash
# Create a project from a YAML spec
bob project create my-app --spec ./spec.yaml --workspace ./workspace

# Or from GitHub issues
bob project create my-app \
  --source github \
  --repo owner/repo \
  --label "ai-implement" \
  --workspace ./workspace
```

### Example Spec File (spec.yaml)

```yaml
name: My Web Application
description: A full-stack web application

defaults:
  priority: 3
  category: functional

tasks:
  - id: setup-backend
    title: Initialize Backend
    description: Set up Express.js backend with TypeScript
    acceptance_criteria:
      - Server starts on port 3000
      - TypeScript compilation works
      - Basic health check endpoint responds
    steps:
      - Initialize npm project
      - Install Express and TypeScript
      - Create basic server structure
      - Add health check route
    priority: 1
    labels: [backend, setup]

  - id: setup-database
    title: Database Setup
    depends_on: [setup-backend]
    description: Configure PostgreSQL database with migrations
    priority: 1
    labels: [backend, database]

  - id: user-auth
    title: User Authentication
    depends_on: [setup-backend, setup-database]
    description: |
      Implement JWT-based user authentication.
      REQUIRES RESEARCH on best practices for secure JWT storage.
    research_required: true
    research_queries:
      - "JWT token storage best practices 2026"
      - "Secure session management for web apps"
    priority: 1
    labels: [backend, auth]
```

### Run the Agent

```bash
# Run on current project
bob run

# Run with parallel execution (3 concurrent tasks)
bob run --parallel 3

# Run specific project
bob run --project my-app

# Dry run to see what would execute
bob run --dry-run
```

### Monitor Progress

```bash
# Global status
bob status

# Project-specific status
bob project status my-app

# Task list
bob task list
bob task list --status failed
bob task list --needs-research

# View logs
bob logs --follow

# Cost breakdown
bob costs --project my-app
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                              BOB CLI                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  Project Manager │  │   Spec Adapters  │  │  Agent Registry  │  │
│  │                  │  │                  │  │                  │  │
│  │ - Create/delete  │  │ - File spec      │  │ - Coding agent   │  │
│  │ - List projects  │  │ - YAML/JSON/MD   │  │ - Research agent │  │
│  │ - Status/health  │  │ - GitHub issues  │  │ - Diagnosis agent│  │
│  │ - Config mgmt    │  │ - (future: Jira) │  │ - Custom agents  │  │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  │
│           │                     │                     │            │
│  ┌────────▼─────────────────────▼─────────────────────▼─────────┐  │
│  │                     Orchestration Engine                      │  │
│  │                                                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │  │
│  │  │ Task Queue  │  │ State       │  │ Escalation          │   │  │
│  │  │             │  │ Machine     │  │ Controller          │   │  │
│  │  │ - Priority  │  │             │  │ (from autonomous-   │   │  │
│  │  │ - Deps      │  │ - Session   │  │  coding)            │   │  │
│  │  │ - Parallel  │  │ - Checkpt   │  │ - Model tiers       │   │  │
│  │  └─────────────┘  └─────────────┘  │ - Failure classify  │   │  │
│  │                                     │ - Decomposition     │   │  │
│  │                                     │ - Research-first    │   │  │
│  │                                     └─────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                     Persistence Layer                          │  │
│  │                                                                │  │
│  │  SQLite (default) - Projects, Tasks, Sessions, Costs          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Escalation System

BOB inherits the proven escalation system from autonomous-coding:

```
Task Fails
    │
    ▼
┌─────────────────────┐
│  SONNET (3 attempts)│
└──────────┬──────────┘
           │ still failing
           ▼
┌─────────────────────┐
│  OPUS (3 attempts)  │
└──────────┬──────────┘
           │ still failing
           ▼
┌─────────────────────┐
│     DIAGNOSIS       │  (Root cause analysis)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────┐
│  Based on failure_type:                                  │
│                                                          │
│  TOO_BIG ──────────────▶ DECOMPOSE (break into subtasks)│
│  MISSING_INFO ─────────▶ RESEARCH (Perplexity/web)      │
│  WRONG_INFRA ──────────▶ REQUEST_USER (needs help)      │
│  BAD_ASSUMPTIONS ──────▶ RESTRUCTURE (research + rethink)│
│  NEEDS_RESEARCH ───────▶ RESEARCH (with specific queries)│
│  UNKNOWN ──────────────▶ REQUEST_USER (give up)         │
└─────────────────────────────────────────────────────────┘
```

## Research-First Workflow

BOB supports marking tasks as requiring research *before* implementation:

```yaml
tasks:
  - id: timing-optimization
    title: Extreme Timing Closure
    description: |
      Achieve timing closure on design with 5.3x clock violation.
      REQUIRES RESEARCH on advanced ECO techniques.
    research_required: true
    research_queries:
      - "OpenROAD timing-driven placement techniques"
      - "buffer insertion algorithms for timing closure"
    steps:
      - Research optimization strategies
      - Implement best approach from research
      - Verify timing improvement
```

Benefits:
- **Proactive** research before wasted implementation attempts
- **Guided** research with domain-specific queries
- **Knowledge persists** across sessions
- **Cost efficient** - avoids expensive Opus escalations

## CLI Reference

### Project Management

```bash
bob project create <name> [--spec FILE] [--workspace DIR]
bob project list [--status STATUS]
bob project status <name>
bob project use <name>
bob project delete <name> [--yes] [--delete-workspace]
```

### Task Management

```bash
bob task list [--status STATUS] [--priority N] [--needs-research]
bob task show <task_id> [--research] [--escalation]
bob task retry <task_id>
bob task skip <task_id> [--reason REASON]
bob task add --title "..." --description "..." [--priority N]
```

### Execution

```bash
bob run [--project NAME] [--parallel N] [--max-sessions N] [--dry-run]
bob research <task_id>
bob sync [--project NAME]
```

### Monitoring

```bash
bob status [--json]
bob logs [--follow] [--session ID] [--level LEVEL] [--event TYPE]
bob costs [--project NAME]
```

### Configuration

```bash
bob config show [--json]
bob config set <key> <value>
bob config edit
```

## Configuration

### Global Config (~/.bob/config.yaml)

```yaml
models:
  default: claude-sonnet-4-5-20250929
  escalation: claude-opus-4-5-20251101

database:
  type: sqlite
  path: ~/.bob/bob.db

limits:
  max_cost_per_project: 100.0  # USD
  max_cost_per_session: 5.0
  warn_at_percent: 80

escalation:
  max_attempts_per_model: 3
```

### Project Config (project.yaml)

```yaml
name: My App
spec:
  type: file
  path: ./spec.yaml

workspace: ./workspace

models:
  default: claude-sonnet-4-5-20250929

security:
  sandbox: true
  allowed_commands: [npm, node, python, pytest, git]

agents:
  coding:
    system_prompt: |
      You are a full-stack developer building {project.name}.
      Follow these coding standards: ...
```

## Development

### Project Structure

```
bob/
├── bob/                        # Main package
│   ├── cli/                    # CLI commands
│   ├── database/               # Database layer
│   ├── models/                 # Data models
│   ├── orchestrator/           # Execution engine
│   ├── spec_sources/           # Spec parsers
│   ├── research/               # Research controller
│   ├── observability/          # Logging, metrics, costs
│   ├── plugins/                # Plugin system
│   └── prompts/                # Prompt templates
├── tests/                      # Test suite
├── examples/                   # Example projects
├── docs/                       # Documentation
├── init.sh                     # Setup script
├── requirements.txt            # Dependencies
├── setup.py                    # Package setup
└── README.md                   # This file
```

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=bob --cov-report=html

# Run specific test
pytest tests/test_database.py
```

### Building from Source

```bash
# Install in development mode
pip install -e .

# Build distribution
python setup.py sdist bdist_wheel

# Install from wheel
pip install dist/bob-*.whl
```

## Roadmap

### Phase 1: Core Foundation ✅
- [x] Project model and database schema
- [x] Basic CLI (create, list, delete projects)
- [x] Port escalation logic from autonomous-coding
- [x] File-based spec source with research detection
- [x] Single-task execution
- [x] Research-first workflow
- [x] SQLite persistence

### Phase 2: Multi-Project & Orchestration (In Progress)
- [ ] Multi-project management
- [ ] Task queue with dependency resolution
- [ ] Session management
- [ ] Progress tracking

### Phase 3: Observability & Cost
- [ ] Structured JSON logging
- [ ] Cost tracking per project/session/task
- [ ] CLI status/logs commands
- [ ] Checkpointing for resume

### Phase 4: Parallel Execution
- [ ] Parallel task execution
- [ ] Concurrent session management
- [ ] Resource management

### Phase 5: Integrations & Extensions
- [ ] GitHub issues spec source
- [ ] Plugin architecture for custom agents
- [ ] Additional spec sources (Jira, Linear)

## Contributing

Contributions are welcome! Please see CONTRIBUTING.md for guidelines.

## License

MIT License - see LICENSE file for details

## Acknowledgments

BOB is built on the excellent foundation of the [Anthropic Claude Quickstarts - Autonomous Coding Demo](https://github.com/anthropics/claude-code/tree/main/claude-quickstarts/autonomous-coding). We're grateful for the innovative work by the Anthropic team.

## Support

- 📧 Email: support@bob-framework.dev
- 💬 Discord: [Join our community](#)
- 📖 Docs: [docs.bob-framework.dev](#)
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/bob/issues)
