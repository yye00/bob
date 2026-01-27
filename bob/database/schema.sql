-- BOB Framework Database Schema
-- SQLite database for managing projects, tasks, sessions, and events

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    workspace_dir TEXT NOT NULL,
    spec_source TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',  -- JSON
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'active',
    last_sync_hash TEXT,  -- Hash of spec source at last sync
    last_sync_at TIMESTAMP,  -- Timestamp of last sync
    CONSTRAINT valid_status CHECK (status IN ('active', 'paused', 'completed', 'archived'))
);

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    spec_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL DEFAULT '[]',  -- JSON array
    steps TEXT NOT NULL DEFAULT '[]',  -- JSON array
    depends_on TEXT NOT NULL DEFAULT '[]',  -- JSON array of task IDs
    priority TEXT NOT NULL DEFAULT 'medium',
    category TEXT NOT NULL DEFAULT 'functional',
    labels TEXT NOT NULL DEFAULT '[]',  -- JSON array
    status TEXT NOT NULL DEFAULT 'pending',
    assigned_agent TEXT,
    current_model TEXT NOT NULL DEFAULT 'claude-sonnet-4-5-20250929',
    attempts INTEGER NOT NULL DEFAULT 0,
    escalation_tier TEXT NOT NULL DEFAULT 'tier1',
    failure_type TEXT,
    research_required INTEGER NOT NULL DEFAULT 0,  -- SQLite boolean (0/1)
    research_complete INTEGER NOT NULL DEFAULT 0,
    research_queries TEXT NOT NULL DEFAULT '[]',  -- JSON array
    research_findings TEXT NOT NULL DEFAULT '{}',  -- JSON object
    skip_reason TEXT,  -- Reason for skipping (NULL if not skipped)
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT valid_priority CHECK (priority IN ('critical', 'high', 'medium', 'low')),
    CONSTRAINT valid_status CHECK (status IN ('pending', 'in_progress', 'blocked', 'research_needed', 'research_complete', 'completed', 'failed', 'skipped', 'deprecated')),
    CONSTRAINT valid_tier CHECK (escalation_tier IN ('tier1', 'tier2'))
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,  -- NULL for project-level sessions
    agent_type TEXT NOT NULL,
    model TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'running',
    turns INTEGER NOT NULL DEFAULT 0,
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    tokens_cache_read INTEGER NOT NULL DEFAULT 0,
    tokens_cache_write INTEGER NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0.0,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
    CONSTRAINT valid_status CHECK (status IN ('running', 'completed', 'failed', 'timeout', 'cancelled')),
    CONSTRAINT valid_agent_type CHECK (agent_type IN ('initializer', 'coding', 'feature_sync', 'research', 'diagnosis', 'escalation'))
);

-- Events table (for observability and audit trail)
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    task_id TEXT,
    session_id TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    event_data TEXT NOT NULL DEFAULT '{}',  -- JSON
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

-- Research sessions table (for tracking Perplexity research)
CREATE TABLE IF NOT EXISTS research_sessions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    query TEXT NOT NULL,
    response TEXT NOT NULL,  -- JSON
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Settings table (for storing application settings)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries

-- Task indexes
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_spec_id ON tasks(spec_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);

-- Session indexes
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_task ON sessions(task_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);

-- Event indexes
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

-- Research session indexes
CREATE INDEX IF NOT EXISTS idx_research_task ON research_sessions(task_id);
CREATE INDEX IF NOT EXISTS idx_research_session ON research_sessions(session_id);

-- Triggers to update updated_at timestamp

CREATE TRIGGER IF NOT EXISTS update_task_timestamp
AFTER UPDATE ON tasks
FOR EACH ROW
BEGIN
    UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
