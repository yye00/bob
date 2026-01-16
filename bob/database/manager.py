"""Database manager for BOB framework.

This module provides the DatabaseManager class for all database operations,
including CRUD operations, transactions, and query methods.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

from bob.models.base import (
    AgentType,
    FailureType,
    ModelTier,
    Project,
    ProjectStatus,
    Session,
    SessionStatus,
    Task,
    TaskStatus,
)

from .migrations import migrate, verify_schema


class DatabaseManager:
    """Manager for all database operations.

    Provides CRUD operations, transaction support, and connection pooling
    for the BOB framework database.
    """

    def __init__(self, db_path: str | Path):
        """Initialize the database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None

        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize schema if needed
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema if it doesn't exist."""
        with self.connect() as conn:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")

            # Apply migrations
            migrate(conn)

            # Verify schema
            if not verify_schema(conn):
                raise RuntimeError("Database schema verification failed")

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection as a context manager.

        Yields:
            Database connection

        Example:
            with db.connect() as conn:
                cursor = conn.execute("SELECT * FROM projects")
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign keys
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Execute operations in a transaction with automatic commit/rollback.

        Yields:
            Database connection

        Example:
            with db.transaction() as conn:
                conn.execute("INSERT INTO projects ...")
                conn.execute("INSERT INTO tasks ...")
                # Automatically commits on success, rolls back on exception
        """
        with self.connect() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # ============================================================================
    # Project CRUD Operations
    # ============================================================================

    def create_project(self, project: Project) -> str:
        """Create a new project.

        Args:
            project: Project object to create

        Returns:
            Project ID
        """
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    id, name, description, workspace_dir, spec_source,
                    config, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    project.description,
                    project.workspace_dir,
                    project.spec_source,
                    json.dumps(project.config),
                    project.created_at.isoformat(),
                    project.status.value,
                ),
            )
        return project.id

    def get_project(self, project_id: str) -> Optional[Project]:
        """Get a project by ID.

        Args:
            project_id: Project ID

        Returns:
            Project object or None if not found
        """
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_project(row)
            return None

    def list_projects(
        self, status: Optional[ProjectStatus] = None, limit: int = 100, offset: int = 0
    ) -> list[Project]:
        """List projects with optional filtering.

        Args:
            status: Filter by project status (optional)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Project objects
        """
        with self.connect() as conn:
            if status:
                cursor = conn.execute(
                    """
                    SELECT * FROM projects
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (status.value, limit, offset),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM projects
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            return [self._row_to_project(row) for row in cursor.fetchall()]

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[ProjectStatus] = None,
        config: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Update project fields.

        Args:
            project_id: Project ID
            name: New name (optional)
            description: New description (optional)
            status: New status (optional)
            config: New config (optional)

        Returns:
            True if project was updated, False if not found
        """
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if status is not None:
            updates.append("status = ?")
            params.append(status.value)
        if config is not None:
            updates.append("config = ?")
            params.append(json.dumps(config))

        if not updates:
            return False

        params.append(project_id)

        with self.transaction() as conn:
            cursor = conn.execute(
                f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params
            )
            return cursor.rowcount > 0

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all associated data (cascading).

        Args:
            project_id: Project ID

        Returns:
            True if project was deleted, False if not found
        """
        with self.transaction() as conn:
            cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return cursor.rowcount > 0

    # ============================================================================
    # Task CRUD Operations
    # ============================================================================

    def create_task(self, task: Task) -> str:
        """Create a new task.

        Args:
            task: Task object to create

        Returns:
            Task ID
        """
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, project_id, spec_id, title, description,
                    acceptance_criteria, steps, depends_on, priority, category,
                    labels, status, assigned_agent, current_model, attempts,
                    escalation_tier, failure_type, research_required,
                    research_complete, research_queries, research_findings,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    task.id,
                    task.project_id,
                    task.spec_id,
                    task.title,
                    task.description,
                    json.dumps(task.acceptance_criteria),
                    json.dumps(task.steps),
                    json.dumps(task.depends_on),
                    task.priority,
                    task.category,
                    json.dumps(task.labels),
                    task.status.value,
                    task.assigned_agent.value if task.assigned_agent else None,
                    task.current_model,
                    task.attempts,
                    task.escalation_tier.value,
                    task.failure_type.value if task.failure_type else None,
                    1 if task.research_required else 0,
                    1 if task.research_complete else 0,
                    json.dumps(task.research_queries),
                    json.dumps(task.research_findings),
                ),
            )
        return task.id

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID.

        Args:
            task_id: Task ID

        Returns:
            Task object or None if not found
        """
        with self.connect() as conn:
            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_task(row)
            return None

    def list_tasks(
        self,
        project_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks with optional filtering.

        Args:
            project_id: Filter by project ID (optional)
            status: Filter by task status (optional)
            priority: Filter by priority (optional)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Task objects
        """
        conditions = []
        params = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if priority:
            conditions.append("priority = ?")
            params.append(priority)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        with self.connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM tasks
                {where_clause}
                ORDER BY
                    CASE priority
                        WHEN 'critical' THEN 0
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        ELSE 3
                    END,
                    created_at ASC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            return [self._row_to_task(row) for row in cursor.fetchall()]

    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        assigned_agent: Optional[AgentType] = None,
        current_model: Optional[str] = None,
        escalation_tier: Optional[ModelTier] = None,
        failure_type: Optional[FailureType] = None,
        research_required: Optional[bool] = None,
        research_complete: Optional[bool] = None,
        research_findings: Optional[dict[str, Any]] = None,
        attempts: Optional[int] = None,
    ) -> bool:
        """Update task fields.

        Args:
            task_id: Task ID
            status: New status (optional)
            assigned_agent: New assigned agent (optional)
            current_model: New current model (optional)
            escalation_tier: New escalation tier (optional)
            failure_type: New failure type (optional)
            research_required: New research required flag (optional)
            research_complete: New research complete flag (optional)
            research_findings: New research findings (optional)
            attempts: New attempt count (optional)

        Returns:
            True if task was updated, False if not found
        """
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)
        if assigned_agent is not None:
            updates.append("assigned_agent = ?")
            params.append(assigned_agent.value)
        if current_model is not None:
            updates.append("current_model = ?")
            params.append(current_model)
        if escalation_tier is not None:
            updates.append("escalation_tier = ?")
            params.append(escalation_tier.value)
        if failure_type is not None:
            updates.append("failure_type = ?")
            params.append(failure_type.value)
        if research_required is not None:
            updates.append("research_required = ?")
            params.append(1 if research_required else 0)
        if research_complete is not None:
            updates.append("research_complete = ?")
            params.append(1 if research_complete else 0)
        if research_findings is not None:
            updates.append("research_findings = ?")
            params.append(json.dumps(research_findings))
        if attempts is not None:
            updates.append("attempts = ?")
            params.append(attempts)

        if not updates:
            return False

        params.append(task_id)

        with self.transaction() as conn:
            cursor = conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
            )
            return cursor.rowcount > 0

    def update_task_spec(
        self,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        acceptance_criteria: Optional[list[str]] = None,
        steps: Optional[list[str]] = None,
        depends_on: Optional[list[str]] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        labels: Optional[list[str]] = None,
        research_required: Optional[bool] = None,
        research_queries: Optional[list[str]] = None,
    ) -> bool:
        """Update task specification fields (from spec sync).

        This is separate from update_task() which only updates execution state.
        This method updates fields that come from the spec source.

        Args:
            task_id: Task ID
            title: New title (optional)
            description: New description (optional)
            acceptance_criteria: New acceptance criteria (optional)
            steps: New steps (optional)
            depends_on: New dependencies (optional)
            priority: New priority (optional)
            category: New category (optional)
            labels: New labels (optional)
            research_required: New research required flag (optional)
            research_queries: New research queries (optional)

        Returns:
            True if task was updated, False if not found
        """
        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if acceptance_criteria is not None:
            updates.append("acceptance_criteria = ?")
            params.append(json.dumps(acceptance_criteria))
        if steps is not None:
            updates.append("steps = ?")
            params.append(json.dumps(steps))
        if depends_on is not None:
            updates.append("depends_on = ?")
            params.append(json.dumps(depends_on))
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if labels is not None:
            updates.append("labels = ?")
            params.append(json.dumps(labels))
        if research_required is not None:
            updates.append("research_required = ?")
            params.append(1 if research_required else 0)
        if research_queries is not None:
            updates.append("research_queries = ?")
            params.append(json.dumps(research_queries))

        if not updates:
            return False

        params.append(task_id)

        with self.transaction() as conn:
            cursor = conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
            )
            return cursor.rowcount > 0

    def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: Task ID

        Returns:
            True if task was deleted, False if not found
        """
        with self.transaction() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return cursor.rowcount > 0

    # ============================================================================
    # Session CRUD Operations
    # ============================================================================

    def create_session(self, session: Session) -> str:
        """Create a new session.

        Args:
            session: Session object to create

        Returns:
            Session ID
        """
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, project_id, task_id, agent_type, model,
                    started_at, ended_at, status, turns,
                    tokens_input, tokens_output, cost
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.project_id,
                    session.task_id,
                    session.agent_type.value,
                    session.model,
                    session.started_at.isoformat(),
                    session.ended_at.isoformat() if session.ended_at else None,
                    session.status.value,
                    session.turns,
                    session.tokens.get("input", 0),
                    session.tokens.get("output", 0),
                    session.cost,
                ),
            )
        return session.id

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session object or None if not found
        """
        with self.connect() as conn:
            cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_session(row)
            return None

    def list_sessions(
        self,
        project_id: Optional[str] = None,
        task_id: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Session]:
        """List sessions with optional filtering.

        Args:
            project_id: Filter by project ID (optional)
            task_id: Filter by task ID (optional)
            status: Filter by session status (optional)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Session objects
        """
        conditions = []
        params = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)
        if status:
            conditions.append("status = ?")
            params.append(status.value)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        with self.connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM sessions
                {where_clause}
                ORDER BY started_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            return [self._row_to_session(row) for row in cursor.fetchall()]

    def update_session(
        self,
        session_id: str,
        status: Optional[SessionStatus] = None,
        ended_at: Optional[datetime] = None,
        turns: Optional[int] = None,
        tokens: Optional[dict[str, int]] = None,
        cost: Optional[float] = None,
    ) -> bool:
        """Update session fields.

        Args:
            session_id: Session ID
            status: New status (optional)
            ended_at: End timestamp (optional)
            turns: Turn count (optional)
            tokens: Token usage (optional)
            cost: Cost (optional)

        Returns:
            True if session was updated, False if not found
        """
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)
        if ended_at is not None:
            updates.append("ended_at = ?")
            params.append(ended_at.isoformat())
        if turns is not None:
            updates.append("turns = ?")
            params.append(turns)
        if tokens is not None:
            updates.append("tokens_input = ?")
            updates.append("tokens_output = ?")
            params.append(tokens.get("input", 0))
            params.append(tokens.get("output", 0))
        if cost is not None:
            updates.append("cost = ?")
            params.append(cost)

        if not updates:
            return False

        params.append(session_id)

        with self.transaction() as conn:
            cursor = conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", params
            )
            return cursor.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: Session ID

        Returns:
            True if session was deleted, False if not found
        """
        with self.transaction() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return cursor.rowcount > 0

    # ============================================================================
    # Helper Methods
    # ============================================================================

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        """Convert a database row to a Project object.

        Args:
            row: Database row

        Returns:
            Project object
        """
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            workspace_dir=row["workspace_dir"],
            spec_source=row["spec_source"],
            config=json.loads(row["config"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            status=ProjectStatus(row["status"]),
        )

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """Convert a database row to a Task object.

        Args:
            row: Database row

        Returns:
            Task object
        """
        return Task(
            id=row["id"],
            project_id=row["project_id"],
            spec_id=row["spec_id"],
            title=row["title"],
            description=row["description"],
            acceptance_criteria=json.loads(row["acceptance_criteria"]),
            steps=json.loads(row["steps"]),
            depends_on=json.loads(row["depends_on"]),
            priority=row["priority"],
            category=row["category"],
            labels=json.loads(row["labels"]),
            status=TaskStatus(row["status"]),
            assigned_agent=AgentType(row["assigned_agent"]) if row["assigned_agent"] else None,
            current_model=row["current_model"],
            attempts=row["attempts"],
            escalation_tier=ModelTier(row["escalation_tier"]),
            failure_type=FailureType(row["failure_type"]) if row["failure_type"] else None,
            research_required=bool(row["research_required"]),
            research_complete=bool(row["research_complete"]),
            research_queries=json.loads(row["research_queries"]),
            research_findings=json.loads(row["research_findings"]),
        )

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        """Convert a database row to a Session object.

        Args:
            row: Database row

        Returns:
            Session object
        """
        return Session(
            id=row["id"],
            project_id=row["project_id"],
            task_id=row["task_id"],
            agent_type=AgentType(row["agent_type"]),
            model=row["model"],
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            status=SessionStatus(row["status"]),
            turns=row["turns"],
            tokens={"input": row["tokens_input"], "output": row["tokens_output"]},
            cost=row["cost"],
        )
