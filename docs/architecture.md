# Architecture

## Overview

BOB is built on a modular architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                     CLI Layer                            │
│  (click commands, argument parsing, output formatting)   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  Orchestration Layer                     │
│  (agent lifecycle, escalation, checkpointing)            │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    Agent Layer                           │
│  (coding, research, diagnosis, decomposition)            │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   Service Layer                          │
│  (database, templates, config, state)                    │
└─────────────────────────────────────────────────────────┘
```

## Core Components

### CLI Layer (`bob/cli/`)

- **main.py** - Main CLI entry point
- **project.py** - Project management commands
- **task.py** - Task management commands
- **run.py** - Agent execution commands
- **sync.py** - Spec synchronization
- **logs.py** - Log viewing
- **costs.py** - Cost tracking
- **config.py** - Configuration management

### Database Layer (`bob/database/`)

- **manager.py** - Database operations (CRUD)
- **schema.py** - Database schema definitions
- **migrations.py** - Schema migrations

Schema:
```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    spec_source TEXT,
    workspace_dir TEXT,
    created_at TEXT
);

CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    title TEXT,
    status TEXT,
    priority TEXT,
    depends_on TEXT,  -- JSON array
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    agent_type TEXT,
    status TEXT,
    cost REAL,
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
```

### Models (`bob/models/`)

- **base.py** - Core data models (Project, Task, Session)
- **config.py** - Configuration models
- **spec.py** - Spec format models

### Orchestration (`bob/orchestration/`)

- **agent.py** - Main orchestration loop
- **escalation.py** - Escalation controller
- **checkpoint.py** - Checkpointing manager
- **task_queue.py** - Task scheduling (DAG)

### Agents (`bob/agents/`)

- **coding.py** - Main coding agent
- **research.py** - Research agent (Perplexity)
- **diagnosis.py** - Failure diagnosis
- **decomposition.py** - Task decomposition

### Services (`bob/services/`)

- **template_engine.py** - Jinja2 template rendering
- **config_manager.py** - Config loading/merging
- **state.py** - Active project state
- **cost_tracker.py** - Cost calculation

## Data Flow

### Project Creation

```
User: bob project create my-app ./workspace file://spec.yaml
  ↓
CLI: Parse arguments
  ↓
DatabaseManager: Create project record
  ↓
Workspace: Create directory structure
  ↓
SpecParser: Parse spec file
  ↓
DatabaseManager: Create task records
  ↓
StateManager: Set as active project
```

### Task Execution

```
User: bob run
  ↓
Orchestrator: Load active project
  ↓
TaskQueue: Get next task (DAG-aware)
  ↓
Agent: Execute task with Claude
  ↓
[Success] → Mark complete, update costs
[Failure] → Escalation controller
  ↓
Escalation: Try Opus → Diagnose → Research/Decompose
  ↓
Checkpoint: Save state
  ↓
Loop: Next task
```

## Plugin System

Plugins extend BOB via standardized interfaces:

```python
class Plugin(ABC):
    @abstractmethod
    def on_load(self) -> None:
        """Called when plugin is loaded."""
        pass

    @abstractmethod
    def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        pass

class SpecSourcePlugin(Plugin):
    @abstractmethod
    def fetch_tasks(self, source_uri: str) -> list[dict]:
        """Fetch tasks from custom source."""
        pass

class AgentPlugin(Plugin):
    @abstractmethod
    def execute(self, task: dict, context: dict) -> dict:
        """Execute custom agent logic."""
        pass
```

## Configuration Hierarchy

```
1. Built-in defaults (bob/config/defaults.yaml)
   ↓
2. Global config (~/.bob/config.yaml)
   ↓
3. Project config (<workspace>/.bob/project.yaml)
   ↓
4. Environment variables (BOB_*)
   ↓
5. CLI flags (--model, --max-iterations)
```

## Key Design Patterns

### 1. Dependency Injection

Services injected via constructors:

```python
class Orchestrator:
    def __init__(
        self,
        db: DatabaseManager,
        config: ConfigManager,
        cost_tracker: CostTracker,
    ):
        self.db = db
        self.config = config
        self.cost_tracker = cost_tracker
```

### 2. Strategy Pattern

Escalation strategies:

```python
class EscalationStrategy(ABC):
    @abstractmethod
    def should_escalate(self, attempt: int, failure: dict) -> bool:
        pass

class SmartStrategy(EscalationStrategy):
    def should_escalate(self, attempt: int, failure: dict) -> bool:
        # Smart logic
        return attempt >= 2

class AggressiveStrategy(EscalationStrategy):
    def should_escalate(self, attempt: int, failure: dict) -> bool:
        # Escalate immediately
        return attempt >= 1
```

### 3. Observer Pattern

Event listeners for logging, metrics:

```python
class EventBus:
    def emit(self, event: str, data: dict) -> None:
        for listener in self.listeners[event]:
            listener.handle(event, data)

# Usage
events.emit("task.completed", {"task_id": "task-1", "cost": 0.05})
```

### 4. Template Method

Agent execution:

```python
class Agent(ABC):
    def execute(self, task: dict) -> dict:
        self.before_execute(task)
        result = self.do_execute(task)  # Subclass implements
        self.after_execute(task, result)
        return result
```

## Testing Architecture

```
tests/
├── unit/
│   ├── test_database.py
│   ├── test_models.py
│   └── test_services.py
├── integration/
│   ├── test_cli.py
│   ├── test_orchestration.py
│   └── test_end_to_end.py
└── fixtures/
    ├── sample_specs/
    └── mock_responses/
```

## Performance Considerations

### Database

- SQLite: Uses Write-Ahead Logging (WAL) for concurrency
- Indexes on: project_id, task_id, status
- Connection pooling for PostgreSQL

### Caching

- Research results cached (TTL: 24h)
- Config loaded once per session
- Template compilation cached

### Async Operations

- Parallel task execution uses asyncio
- Database operations are async-capable
- API calls batched where possible

---

For implementation details, see the source code in `bob/` directory.
