# Getting Started with BOB

## Introduction

**BOB (Build Orchestration Bot)** is a production-ready autonomous coding framework that orchestrates AI agents to implement features across multiple projects. BOB extends the [Anthropic Autonomous Coding Quickstart](https://github.com/anthropics/claude-code/tree/main/claude-quickstarts/autonomous-coding) into a full-featured framework.

## Prerequisites

- **Python 3.10+** (3.11 or 3.12 recommended)
- **Anthropic API Key** (required)
- **Perplexity API Key** (optional, for research features)
- **Git** (recommended for version control)

## Installation

### Method 1: Quick Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/yye00/bob.git
cd bob

# Run the setup script
./init.sh

# Activate the virtual environment
source venv/bin/activate
```

### Method 2: Manual Setup

```bash
# Clone the repository
git clone https://github.com/yye00/bob.git
cd bob

# Create virtual environment with uv
uv venv

# Install dependencies
uv pip install -e .

# Activate virtual environment
source .venv/bin/activate
```

### Set Up API Keys

Add your API keys to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
export ANTHROPIC_API_KEY='your_anthropic_key_here'
export PERPLEXITY_API_KEY='your_perplexity_key_here'  # Optional
```

Or create a `.env` file in the BOB directory:

```bash
ANTHROPIC_API_KEY=your_anthropic_key_here
PERPLEXITY_API_KEY=your_perplexity_key_here  # Optional
```

## Verify Installation

```bash
# Check BOB version
bob --version

# View help
bob --help

# Initialize BOB directory
bob init
```

This creates `~/.bob/` with:
- `config.yaml` - Global configuration
- `state.json` - Active project tracking
- `bob.db` - Project database

## Your First Project

### Step 1: Create a Spec File

Create `my-spec.yaml`:

```yaml
name: Hello BOB
description: A simple first project to test BOB

tasks:
  - id: hello-world
    title: Create Hello World Script
    description: Create a simple Python script that prints "Hello, BOB!"
    acceptance_criteria:
      - Script exists at hello.py
      - Running 'python hello.py' prints "Hello, BOB!"
      - Script has proper shebang and is executable
    steps:
      - Create hello.py file
      - Add shebang line
      - Add print statement
      - Make file executable
    priority: critical
    category: functional
```

### Step 2: Create a Project

```bash
# Create project with local spec file
bob project create hello-world ./workspace file://my-spec.yaml \
  --description "My first BOB project"

# Verify project was created
bob project list

# View project details
bob project status
```

### Step 3: Run the Agent

```bash
# Run on the active project
bob run

# Or specify project explicitly
bob run --project hello-world

# Run with custom max iterations
bob run --max-iterations 5
```

The agent will:
1. Load the spec file
2. Analyze tasks and dependencies
3. Execute tasks in order
4. Create checkpoints for resume
5. Track costs and progress

### Step 4: Monitor Progress

While the agent runs, open another terminal:

```bash
# Watch logs in real-time
bob logs --follow

# Check project status
bob project status

# View task status
bob task list

# View costs
bob costs
```

### Step 5: Review Results

After the agent completes:

```bash
# Check final status
bob project status

# List completed tasks
bob task list --status completed

# View detailed logs
bob logs --session <session-id>

# Check the workspace
ls -la ./workspace
cat ./workspace/hello.py
```

## Common Workflows

### Workflow 1: Create Project from GitHub Issues

```bash
# Create project from GitHub issues labeled "ai-implement"
bob project create my-github-project ./workspace \
  github://owner/repo/issues \
  --description "Project from GitHub issues"

# BOB will:
# - Fetch all open issues with the label
# - Convert them to tasks
# - Set up dependency tracking
# - Create a workspace
```

### Workflow 2: Multiple Projects

```bash
# Create multiple projects
bob project create frontend ./frontend file://frontend-spec.yaml
bob project create backend ./backend file://backend-spec.yaml
bob project create mobile ./mobile file://mobile-spec.yaml

# List all projects
bob project list

# Switch active project
bob project use backend

# Check which project is active
bob project status

# Work on specific project
bob run --project frontend
```

### Workflow 3: Parallel Execution

```bash
# Run multiple independent tasks in parallel
bob run --parallel --max-workers 3

# BOB will:
# - Analyze task dependencies
# - Execute independent tasks in parallel
# - Wait for dependencies before starting dependent tasks
# - Track costs per parallel session
```

### Workflow 4: Research-First Development

```bash
# Tasks marked with research_required will:
# 1. Use Perplexity to research the topic
# 2. Store research findings
# 3. Use findings to implement the feature

# View tasks needing research
bob task list --needs-research

# Run research phase only
bob research --task-id user-auth

# Review research findings
bob research --show --task-id user-auth

# Implement after research
bob run --task-id user-auth
```

## Understanding BOB's Workflow

### Agent Lifecycle

1. **Initialization** (First run)
   - Parse spec file
   - Create tasks in database
   - Set up project workspace
   - Initialize state

2. **Execution** (Each iteration)
   - Load pending tasks
   - Check dependencies (DAG)
   - Select next task(s)
   - Execute with coding agent
   - Track progress and costs
   - Create checkpoints

3. **Escalation** (On failures)
   - Sonnet fails → Try Opus
   - Opus fails → Run diagnosis
   - Diagnosis → Research or decompose
   - Research → Implement with findings
   - Decompose → Break into subtasks

4. **Completion**
   - All tasks completed or failed
   - Generate summary report
   - Final checkpoint saved

### Task States

- **pending**: Not yet started
- **in_progress**: Currently executing
- **blocked**: Waiting on dependencies
- **research_needed**: Needs research before implementation
- **research_complete**: Research done, ready for implementation
- **completed**: Successfully finished
- **failed**: Failed after retries
- **skipped**: Skipped due to configuration

## Configuration

### Global Config (`~/.bob/config.yaml`)

```yaml
models:
  default: claude-sonnet-4
  escalation: claude-opus-4
  research: claude-opus-4

database:
  path: ~/.bob/bob.db
  backup_interval: 3600

limits:
  max_cost_per_project: 50.00
  max_iterations: 100
  max_retries: 3

logging:
  level: INFO
  format: json
  directory: ~/.bob/logs

escalation:
  enabled: true
  strategy: smart  # smart, aggressive, conservative
  max_escalations: 3
```

### Project Config (`.bob/project.yaml`)

Overrides global settings for this project:

```yaml
name: my-project
description: Project-specific configuration

models:
  default: claude-sonnet-4  # Override for this project

limits:
  max_cost_per_project: 25.00  # Lower limit for this project
  max_iterations: 50

escalation:
  enabled: false  # Disable escalation for this project
```

## Next Steps

- Read [Configuration Guide](configuration.md) for detailed config options
- Learn about [Spec Formats](spec-formats.md) for writing specs
- Understand [Escalation](escalation.md) for handling failures
- Explore [Research-First Workflow](research-first.md) for complex tasks
- Review [CLI Reference](cli-reference.md) for all commands
- Study [Architecture](architecture.md) to understand internals

## Troubleshooting

### Agent Not Starting

```bash
# Check if API key is set
echo $ANTHROPIC_API_KEY

# Verify installation
bob --version

# Check logs
bob logs --level ERROR
```

### Tasks Not Executing

```bash
# Check task dependencies
bob task list --status blocked

# View specific task
bob task show <task-id>

# Check if tasks are waiting on research
bob task list --needs-research
```

### High Costs

```bash
# Check current costs
bob costs

# Set lower budget
bob config set limits.max_cost_per_project 10.00

# Use cheaper model
bob config set models.default claude-sonnet-4
```

### Database Issues

```bash
# Check database integrity
sqlite3 ~/.bob/bob.db "PRAGMA integrity_check;"

# Backup database
cp ~/.bob/bob.db ~/.bob/bob.db.backup

# Reset if corrupted
rm ~/.bob/bob.db
bob init
```

## Getting Help

- **CLI Help**: `bob --help` or `bob <command> --help`
- **Documentation**: See `docs/` directory
- **Issues**: https://github.com/yye00/bob/issues
- **Examples**: See `examples/` directory

## Quick Reference

```bash
# Project Management
bob project create <name> <workspace> <spec>
bob project list
bob project use <name>
bob project status
bob project delete <name>

# Task Management
bob task list
bob task show <task-id>
bob task list --status pending
bob task list --needs-research

# Execution
bob run
bob run --parallel
bob run --max-iterations 10
bob research --task-id <id>

# Monitoring
bob status
bob logs --follow
bob costs
bob costs --project <name>

# Configuration
bob config show
bob config set <key> <value>

# Checkpointing
bob checkpoint list
bob checkpoint restore <checkpoint-id>
```

---

**You're ready to start using BOB!** Begin with the simple Hello World example above, then explore more complex projects with dependencies, research requirements, and parallel execution.
