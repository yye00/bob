# Configuration Guide

BOB uses a hierarchical configuration system with three levels:

1. **Default Configuration** - Built-in defaults
2. **Global Configuration** - `~/.bob/config.yaml`
3. **Project Configuration** - `<workspace>/.bob/project.yaml`

Settings cascade: Project config overrides global config overrides defaults.

## Configuration Files

### Global Configuration

Location: `~/.bob/config.yaml`

Created automatically by `bob init` with sensible defaults:

```yaml
models:
  default: claude-sonnet-4-5-20250929
  escalation: claude-opus-4-20250514
  research: claude-opus-4-20250514
  diagnosis: claude-opus-4-20250514
  decomposition: claude-opus-4-20250514

database:
  path: ~/.bob/bob.db
  type: sqlite  # or postgresql
  backup_interval: 3600  # seconds
  pool_size: 5
  timeout: 30

limits:
  max_cost_per_project: 100.00  # USD
  max_cost_per_session: 10.00
  max_iterations: 100
  max_retries: 3
  max_parallel_tasks: 5

logging:
  level: INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: json  # or text
  directory: ~/.bob/logs
  rotate_size: 10485760  # 10MB
  rotate_count: 5
  console_output: true

escalation:
  enabled: true
  strategy: smart  # smart, aggressive, conservative, off
  max_escalations: 3
  auto_research: true
  auto_decompose: true

research:
  enabled: true
  provider: perplexity  # perplexity, web_search
  max_queries: 5
  cache_results: true
  cache_ttl: 86400  # 24 hours

checkpointing:
  enabled: true
  interval: 10  # Save every N iterations
  max_checkpoints: 10
  auto_cleanup: true

templating:
  templates_dir: ~/.bob/templates
  custom_prompts: {}
```

### Project Configuration

Location: `<workspace>/.bob/project.yaml`

Created when you create a project. Overrides global settings:

```yaml
name: my-awesome-project
id: proj-abc123
description: My awesome AI-implemented project
spec_source: file://spec.yaml
created_at: "2026-01-16T10:30:00Z"

# Model overrides for this project
models:
  default: claude-sonnet-4  # Use different model for this project
  escalation: claude-opus-4

# Budget limits specific to this project
limits:
  max_cost_per_project: 50.00  # Lower than global
  max_iterations: 50

# Disable escalation for this project
escalation:
  enabled: false

# Custom templates for this project
templating:
  custom_prompts:
    coding: ./prompts/custom_coding.md
    research: ./prompts/custom_research.md

# Project-specific metadata
metadata:
  team: backend-team
  environment: development
  tags: [api, microservice, python]
```

## Configuration Sections

### Models

Controls which Claude models are used for different agent types.

```yaml
models:
  # Default model for coding agent
  default: claude-sonnet-4-5-20250929

  # Model for escalation attempts
  escalation: claude-opus-4-20250514

  # Model for research agent
  research: claude-opus-4-20250514

  # Model for diagnosis (failure analysis)
  diagnosis: claude-opus-4-20250514

  # Model for task decomposition
  decomposition: claude-opus-4-20250514
```

**Available Models:**
- `claude-sonnet-4-5-20250929` - Fast, cost-effective (recommended for default)
- `claude-opus-4-20250514` - Most capable, higher cost (for complex tasks)
- `claude-haiku-4-20250514` - Fastest, cheapest (for simple tasks)

**Cost Optimization:**
```yaml
# Budget-conscious configuration
models:
  default: claude-sonnet-4
  escalation: claude-sonnet-4  # Keep using Sonnet
  research: claude-sonnet-4
  diagnosis: claude-opus-4  # Only use Opus for diagnosis
  decomposition: claude-sonnet-4
```

### Database

Configure the backend database for storing projects, tasks, and sessions.

```yaml
database:
  # SQLite (default, recommended for single-user)
  type: sqlite
  path: ~/.bob/bob.db

  # PostgreSQL (for multi-user or production)
  # type: postgresql
  # host: localhost
  # port: 5432
  # database: bob
  # user: bob_user
  # password: ${BOB_DB_PASSWORD}  # From environment

  backup_interval: 3600  # Backup every hour
  pool_size: 5  # Connection pool size
  timeout: 30  # Query timeout in seconds
```

**SQLite vs PostgreSQL:**

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| Setup | Zero config | Requires server |
| Multi-user | No | Yes |
| Performance | Good for single-user | Better for concurrent access |
| Backup | File copy | pg_dump |
| Recommended for | Local development | Production, teams |

### Limits

Budget and execution limits to prevent runaway costs.

```yaml
limits:
  # Maximum total cost per project (USD)
  max_cost_per_project: 100.00

  # Maximum cost per agent session
  max_cost_per_session: 10.00

  # Maximum coding iterations before stopping
  max_iterations: 100

  # Maximum retry attempts per task
  max_retries: 3

  # Maximum parallel tasks when using --parallel
  max_parallel_tasks: 5
```

**Budget Enforcement:**

When a limit is reached:
- Agent pauses execution
- Checkpoint is saved
- User is notified
- Can review and continue or abort

**Example - Tight Budget:**
```yaml
limits:
  max_cost_per_project: 10.00  # $10 total
  max_cost_per_session: 2.00   # $2 per session
  max_iterations: 20           # Stop after 20 iterations
```

### Logging

Control how BOB logs events and errors.

```yaml
logging:
  # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
  level: INFO

  # Format: json (structured) or text (human-readable)
  format: json

  # Where to store logs
  directory: ~/.bob/logs

  # Rotate logs when they reach this size (bytes)
  rotate_size: 10485760  # 10MB

  # Keep this many rotated log files
  rotate_count: 5

  # Also output to console
  console_output: true

  # Verbose mode (includes more details)
  verbose: false
```

**Log Levels:**
- **DEBUG**: Very detailed, includes API calls and internal state
- **INFO**: Standard operation logs (default)
- **WARNING**: Warnings that don't stop execution
- **ERROR**: Errors that affect specific operations
- **CRITICAL**: Fatal errors that stop execution

**Structured Logging (JSON format):**
```json
{
  "timestamp": "2026-01-16T10:30:45.123Z",
  "level": "INFO",
  "agent": "coding",
  "project_id": "proj-abc123",
  "session_id": "sess-xyz789",
  "task_id": "task-001",
  "message": "Task completed successfully",
  "cost": 0.0234,
  "tokens": 1500
}
```

### Escalation

Configure the escalation system for handling failures.

```yaml
escalation:
  # Enable/disable escalation system
  enabled: true

  # Escalation strategy
  # - smart: Escalate based on failure type
  # - aggressive: Escalate quickly
  # - conservative: Retry more before escalating
  # - off: No escalation (just retry with same model)
  strategy: smart

  # Maximum number of escalation steps
  max_escalations: 3

  # Automatically trigger research after diagnosis
  auto_research: true

  # Automatically decompose complex tasks after diagnosis
  auto_decompose: true
```

**Escalation Strategies:**

**Smart** (recommended):
```
Attempt 1: Sonnet
Attempt 2: Sonnet (retry)
Attempt 3: Opus (escalate)
Attempt 4: Diagnosis → Research or Decompose
```

**Aggressive** (for time-critical projects):
```
Attempt 1: Sonnet
Attempt 2: Opus (escalate immediately)
Attempt 3: Diagnosis → Research or Decompose
```

**Conservative** (for budget-conscious):
```
Attempt 1: Sonnet
Attempt 2: Sonnet (retry)
Attempt 3: Sonnet (retry again)
Attempt 4: Diagnosis (no escalation to Opus)
```

**Off** (simple retry only):
```
Attempt 1: Sonnet
Attempt 2: Sonnet (retry)
Attempt 3: Sonnet (retry)
... up to max_retries
```

### Research

Configure research capabilities using Perplexity or web search.

```yaml
research:
  # Enable/disable research features
  enabled: true

  # Research provider: perplexity, web_search
  provider: perplexity

  # Maximum research queries per task
  max_queries: 5

  # Cache research results to avoid re-querying
  cache_results: true

  # Cache TTL in seconds (86400 = 24 hours)
  cache_ttl: 86400

  # Perplexity-specific settings
  perplexity:
    model: sonar-pro  # or sonar, sonar-reasoning
    max_tokens: 4000
```

**Research Providers:**

**Perplexity** (recommended):
- Requires `PERPLEXITY_API_KEY`
- Most accurate, cites sources
- Costs ~$0.001 per query

**Web Search**:
- Uses built-in web search
- Free but less accurate
- Good for basic lookups

### Checkpointing

Configure automatic checkpointing for resume after interruption.

```yaml
checkpointing:
  # Enable/disable checkpointing
  enabled: true

  # Save checkpoint every N iterations
  interval: 10

  # Maximum number of checkpoints to keep per session
  max_checkpoints: 10

  # Automatically clean up old checkpoints
  auto_cleanup: true
```

**Checkpoint Strategy:**

Checkpoints save:
- Current task state
- Conversation history
- Agent context
- Cost tracking
- Progress metrics

Resume after interruption:
```bash
# List available checkpoints
bob checkpoint list

# Resume from specific checkpoint
bob checkpoint restore <checkpoint-id>

# Resume from latest checkpoint
bob checkpoint restore --latest
```

### Templating

Customize agent prompts with templates.

```yaml
templating:
  # Directory for custom templates
  templates_dir: ~/.bob/templates

  # Custom prompt overrides
  custom_prompts:
    coding: ./prompts/custom_coding.md
    research: ./prompts/custom_research.md
    diagnosis: ./prompts/custom_diagnosis.md
```

**Built-in Templates:**
- `coding_prompt.md` - Main coding agent instructions
- `research_prompt.md` - Research agent instructions
- `diagnosis_prompt.md` - Failure diagnosis instructions
- `decomposition_prompt.md` - Task decomposition instructions
- `escalation_prompt.md` - Escalation handling
- `remediation_prompt.md` - Applying research fixes

**Custom Templates:**

Create `~/.bob/templates/coding_custom.md`:
```markdown
You are a Python expert focusing on clean, testable code.

ALWAYS:
- Write type hints
- Add docstrings
- Include unit tests
- Follow PEP 8

NEVER:
- Use global variables
- Skip error handling
- Write code without tests

{{ base_coding_prompt }}
```

Reference in config:
```yaml
templating:
  custom_prompts:
    coding: coding_custom.md
```

## Managing Configuration

### View Configuration

```bash
# Show current configuration (merged global + project)
bob config show

# Show as JSON
bob config show --json-output

# Show specific key
bob config show models.default
```

### Update Configuration

```bash
# Set a value in global config
bob config set models.default claude-sonnet-4

# Set a nested value
bob config set limits.max_cost_per_project 50.00

# Set a boolean
bob config set escalation.enabled true

# Set in project config (when in project directory)
bob config set --project models.default claude-haiku-4
```

### Edit Configuration

```bash
# Open global config in editor
bob config edit

# Open project config in editor
bob config edit --project
```

### Reset Configuration

```bash
# Reset global config to defaults
bob config reset

# Reset specific key
bob config reset models.default
```

## Environment Variables

BOB respects environment variables for sensitive data:

```bash
# API Keys
export ANTHROPIC_API_KEY=your_key
export PERPLEXITY_API_KEY=your_key

# Database credentials (for PostgreSQL)
export BOB_DB_HOST=localhost
export BOB_DB_PORT=5432
export BOB_DB_NAME=bob
export BOB_DB_USER=bob_user
export BOB_DB_PASSWORD=secret

# Override config path
export BOB_CONFIG_DIR=~/custom/bob/config
```

Use in config file:
```yaml
database:
  type: postgresql
  host: ${BOB_DB_HOST}
  port: ${BOB_DB_PORT}
  database: ${BOB_DB_NAME}
  user: ${BOB_DB_USER}
  password: ${BOB_DB_PASSWORD}
```

## Configuration Best Practices

### 1. Start with Defaults

Don't override unless needed. Defaults are optimized for most use cases.

### 2. Use Project Configs for Variations

Keep global config minimal, customize per-project:

```yaml
# ~/.bob/config.yaml - Global defaults
limits:
  max_cost_per_project: 100.00

# Project A config - High budget
limits:
  max_cost_per_project: 200.00

# Project B config - Low budget
limits:
  max_cost_per_project: 20.00
```

### 3. Budget for Cost Control

Always set realistic budget limits:

```yaml
limits:
  max_cost_per_project: 50.00  # Cap at $50
  max_cost_per_session: 5.00   # Cap each session at $5
```

### 4. Use Escalation Wisely

For most projects, use `smart` escalation:

```yaml
escalation:
  enabled: true
  strategy: smart
  auto_research: true
```

For budget-critical projects, use `conservative`:

```yaml
escalation:
  enabled: true
  strategy: conservative
  max_escalations: 1  # Minimize Opus usage
```

### 5. Enable Checkpointing

Always enable checkpointing for long-running projects:

```yaml
checkpointing:
  enabled: true
  interval: 10  # Every 10 iterations
  max_checkpoints: 20  # Keep 20 checkpoints
```

### 6. Structure Logging

Use JSON logging for production:

```yaml
logging:
  format: json  # Structured logs
  level: INFO
  directory: ~/.bob/logs
```

Use text logging for development:

```yaml
logging:
  format: text  # Human-readable
  level: DEBUG  # More details
  console_output: true
```

## Example Configurations

### Development Setup

Fast iteration, detailed logging:

```yaml
models:
  default: claude-sonnet-4

limits:
  max_iterations: 50
  max_cost_per_session: 5.00

logging:
  level: DEBUG
  format: text
  console_output: true

escalation:
  strategy: aggressive  # Fail fast

checkpointing:
  interval: 5  # Frequent checkpoints
```

### Production Setup

Stable, cost-controlled:

```yaml
models:
  default: claude-sonnet-4
  escalation: claude-opus-4

limits:
  max_cost_per_project: 100.00
  max_cost_per_session: 10.00

logging:
  level: INFO
  format: json
  directory: /var/log/bob

database:
  type: postgresql
  host: db.example.com
  pool_size: 10

escalation:
  strategy: smart
  max_escalations: 3

checkpointing:
  enabled: true
  interval: 10
  auto_cleanup: true
```

### Budget-Conscious Setup

Minimize costs:

```yaml
models:
  default: claude-sonnet-4
  escalation: claude-sonnet-4  # No Opus
  research: claude-sonnet-4

limits:
  max_cost_per_project: 10.00
  max_iterations: 30

escalation:
  enabled: false  # No escalation
  auto_research: false  # Manual research only

research:
  provider: web_search  # Free option
```

## Troubleshooting

### Config Not Loading

```bash
# Check config file location
ls -la ~/.bob/config.yaml

# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('~/.bob/config.yaml'))"

# Reset to defaults
bob config reset
```

### API Keys Not Working

```bash
# Verify environment variables
echo $ANTHROPIC_API_KEY
echo $PERPLEXITY_API_KEY

# Set them if missing
export ANTHROPIC_API_KEY=your_key
```

### Database Connection Issues

```bash
# Test SQLite
sqlite3 ~/.bob/bob.db "SELECT 1;"

# Test PostgreSQL
psql -h localhost -U bob_user -d bob -c "SELECT 1;"
```

### Budget Limits Too Strict

```bash
# Increase limits temporarily
bob config set limits.max_cost_per_session 20.00

# Or disable limits
bob config set limits.max_cost_per_project 999999.00
```

---

For more details, see:
- [Getting Started](getting-started.md) - Initial setup
- [CLI Reference](cli-reference.md) - Config commands
- [Architecture](architecture.md) - How config is loaded
