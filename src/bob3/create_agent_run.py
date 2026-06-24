"""bob3.create_agent_run — canonical entry point for creating agent run records.

This module satisfies the AC: "File exists: src/bob3/create_agent_run.py" and
"Function defined: bob3.create_agent_run.create_agent_run".

Every caller that knows the project's database path MUST pass db_path so that
the INSERT targets the same SQLite file that holds the project row. Without an
explicit db_path the function falls back to BOB3_DATABASE_PATH (or cwd/bob3.db),
which silently diverges from the project database when the orchestrator's cwd
differs — the root cause of the synthesized=0/118 generation failure.
"""

from __future__ import annotations

import pathlib

from bob3.db import create_agent_run as _db_create_agent_run
from bob3.models import SubAgentRun


def create_agent_run(
    *,
    project_id: str,
    purpose: str,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    prompt_summary: str | None = None,
    mcp_enabled: str | None = None,
    status: str = "running",
    db_path: pathlib.Path | None = None,
) -> SubAgentRun:
    """Create a sub-agent run record, writing it to the project's own database.

    Args:
        project_id: ID of the project this run belongs to. The project row
            MUST exist in the database identified by db_path.
        purpose: Short human-readable description of what this run does.
        run_id: Override the generated UUID run ID (optional).
        parent_run_id: ID of the parent run if this is a nested sub-agent.
        target_type: Type of the target entity (e.g. "feature").
        target_id: ID of the target entity.
        prompt_summary: Short summary of the agent prompt.
        mcp_enabled: Serialised MCP configuration string.
        status: Initial status; defaults to "running".
        db_path: Absolute path to the project's SQLite database. When supplied,
            the INSERT targets this file regardless of cwd or BOB3_DATABASE_PATH.
            Callers that have resolved the project_id MUST pass the same db_path
            they used to read the project row so the FK constraint
            (sub_agent_runs.project_id REFERENCES projects(id)) is satisfied.

    Returns:
        The created SubAgentRun model with generated ID and timestamp.

    Raises:
        sqlite3.IntegrityError: If project_id does not exist in db_path (FK
            violation) or the run_id collides with an existing row.
        ValueError: If project_id or purpose are empty strings.
    """
    if not project_id:
        raise ValueError("project_id must be a non-empty string")
    if not purpose:
        raise ValueError("purpose must be a non-empty string")

    return _db_create_agent_run(
        project_id=project_id,
        purpose=purpose,
        run_id=run_id,
        parent_run_id=parent_run_id,
        target_type=target_type,
        target_id=target_id,
        prompt_summary=prompt_summary,
        mcp_enabled=mcp_enabled,
        status=status,
        db_path=db_path,
    )


__all__ = ["create_agent_run"]
