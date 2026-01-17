# CLI Reference

Complete reference for all BOB commands.

## Global Options

Available for all commands:

```bash
bob [GLOBAL OPTIONS] COMMAND [ARGS]

Global Options:
  --db PATH          Database path (default: ~/.bob/bob.db)
  --project NAME     Specify project (overrides active)
  -v, --verbose      Verbose output
  -q, --quiet        Quiet mode (errors only)
  --json-output      Output as JSON
  --help             Show help
  --version          Show version
```

## Commands

### bob init

Initialize BOB configuration.

```bash
bob init [OPTIONS]

Options:
  --force            Overwrite existing configuration

Examples:
  bob init
  bob init --force
```

### bob project

Manage projects.

#### bob project create

```bash
bob project create NAME WORKSPACE SPEC_SOURCE [OPTIONS]

Arguments:
  NAME               Project name (slug format)
  WORKSPACE          Workspace directory path
  SPEC_SOURCE        Spec source URI

Options:
  -d, --description TEXT  Project description
  --config PATH          Custom project config file

Examples:
  bob project create my-app ./workspace file://spec.yaml
  bob project create api ~/api github://org/repo/issues
  bob project create web /opt/web file://spec.json -d "Web app"
```

#### bob project list

```bash
bob project list [OPTIONS]

Options:
  --json-output      Output as JSON
  --status STATUS    Filter by status

Examples:
  bob project list
  bob project list --status active
  bob project list --json-output
```

#### bob project use

```bash
bob project use NAME|ID

Examples:
  bob project use my-app
  bob project use proj-abc123
```

#### bob project status

```bash
bob project status [NAME|ID] [OPTIONS]

Options:
  --json-output      Output as JSON

Examples:
  bob project status
  bob project status my-app
  bob project status --json-output
```

#### bob project delete

```bash
bob project delete NAME|ID [OPTIONS]

Options:
  -y, --yes          Skip confirmation

Examples:
  bob project delete my-app
  bob project delete proj-abc123 --yes
```

### bob task

Manage tasks.

#### bob task list

```bash
bob task list [OPTIONS]

Options:
  --status STATUS          Filter by status
  --priority PRIORITY      Filter by priority
  --category CATEGORY      Filter by category
  --needs-research         Show only tasks needing research
  --json                   Output as JSON
  --limit INTEGER          Max results (default: 100)

Examples:
  bob task list
  bob task list --status pending
  bob task list --priority high
  bob task list --needs-research
  bob task list --json
```

#### bob task show

```bash
bob task show TASK_ID [OPTIONS]

Options:
  --json-output      Output as JSON

Examples:
  bob task show task-123
  bob task show task-123 --json-output
```

### bob run

Execute agent on project.

```bash
bob run [OPTIONS]

Options:
  --project NAME            Project to run on
  --task-id ID              Run specific task
  --parallel                Execute independent tasks in parallel
  --max-workers INTEGER     Max parallel workers (default: 3)
  --max-iterations INTEGER  Max iterations (default: 100)
  --model MODEL             Override model
  --checkpoint-id ID        Resume from checkpoint

Examples:
  bob run
  bob run --project my-app
  bob run --task-id task-123
  bob run --parallel --max-workers 5
  bob run --max-iterations 50
  bob run --checkpoint-id ckpt-xyz
```

### bob research

Run research on tasks.

```bash
bob research [OPTIONS]

Options:
  --task-id ID       Task to research
  --all              Research all tasks needing it
  --show             Show research findings
  --query TEXT       Custom research query
  --clear-cache      Clear research cache
  --json             Output as JSON

Examples:
  bob research --task-id task-123
  bob research --all
  bob research --show --task-id task-123
  bob research --task-id task-123 --query "Custom query"
  bob research --clear-cache
```

### bob sync

Sync with spec source.

```bash
bob sync [OPTIONS]

Options:
  enable             Enable auto-sync
  disable            Disable auto-sync
  run                Run sync now
  status             Show sync status

Examples:
  bob sync enable --source github
  bob sync run
  bob sync status
```

### bob status

Show overall status.

```bash
bob status [OPTIONS]

Options:
  --json-output      Output as JSON

Examples:
  bob status
  bob status --json-output
```

### bob logs

View logs.

```bash
bob logs [OPTIONS]

Options:
  --follow, -f        Follow log output
  --session ID        Filter by session
  --level LEVEL       Filter by level (DEBUG, INFO, WARNING, ERROR)
  --lines INTEGER     Number of lines (default: 100)
  --json              Output as JSON

Examples:
  bob logs
  bob logs --follow
  bob logs --session sess-123
  bob logs --level ERROR
  bob logs --lines 50
```

### bob costs

View costs.

```bash
bob costs [OPTIONS]

Options:
  --project NAME       Filter by project
  --session ID         Filter by session
  --by-model           Breakdown by model
  --by-agent           Breakdown by agent type
  --json-output        Output as JSON

Examples:
  bob costs
  bob costs --project my-app
  bob costs --by-model
  bob costs --by-agent
  bob costs --json-output
```

### bob checkpoint

Manage checkpoints.

```bash
bob checkpoint COMMAND [OPTIONS]

Commands:
  list               List checkpoints
  restore ID         Restore from checkpoint
  delete ID          Delete checkpoint
  export ID PATH     Export checkpoint
  import PATH        Import checkpoint

Examples:
  bob checkpoint list
  bob checkpoint restore --latest
  bob checkpoint restore ckpt-123
  bob checkpoint delete ckpt-123
  bob checkpoint export ckpt-123 ./backup.json
  bob checkpoint import ./backup.json
```

### bob config

Manage configuration.

```bash
bob config COMMAND [OPTIONS]

Commands:
  show [KEY]         Show configuration
  set KEY VALUE      Set configuration value
  reset [KEY]        Reset to defaults
  edit               Open in editor

Options:
  --project          Use project config
  --json-output      Output as JSON

Examples:
  bob config show
  bob config show models.default
  bob config set models.default claude-sonnet-4
  bob config set limits.max_cost_per_project 50.00
  bob config reset
  bob config edit
  bob config edit --project
```

## Exit Codes

- **0** - Success
- **1** - General error
- **2** - Invalid arguments
- **3** - Budget limit reached
- **4** - Task failed
- **5** - Interrupted by user

## Environment Variables

```bash
# API Keys
ANTHROPIC_API_KEY      Required for all agent operations
PERPLEXITY_API_KEY     Optional, for research features

# Database
BOB_DB_HOST            PostgreSQL host
BOB_DB_PORT            PostgreSQL port
BOB_DB_NAME            Database name
BOB_DB_USER            Database user
BOB_DB_PASSWORD        Database password

# Paths
BOB_CONFIG_DIR         Config directory (default: ~/.bob)
BOB_DB_PATH            Database path (default: ~/.bob/bob.db)

# Behavior
BOB_LOG_LEVEL          Log level (DEBUG, INFO, WARNING, ERROR)
BOB_MODEL              Default model
```

## Common Workflows

### Create and Run Project

```bash
bob project create my-app ./workspace file://spec.yaml
bob run
```

### Monitor Progress

```bash
# Terminal 1
bob run

# Terminal 2
bob logs --follow
bob status
```

### Parallel Execution

```bash
bob run --parallel --max-workers 5
```

### Resume After Interruption

```bash
bob checkpoint restore --latest
bob run
```

### Research and Implement

```bash
bob research --task-id task-123
bob research --show --task-id task-123
bob run --task-id task-123
```

### Cost Tracking

```bash
bob costs
bob costs --by-model
bob costs --project my-app
```

---

For detailed guides, see:
- [Getting Started](getting-started.md)
- [Configuration](configuration.md)
- [Spec Formats](spec-formats.md)
