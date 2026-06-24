"""bob3.agent_run — thin facade for creating agent run records.

Ensures create_agent_run always targets the project's own database via an
explicit db_path, preventing the FK failure that occurs when the connection
resolves to a different file (stale repo-root bob3.db or different cwd).
"""

from __future__ import annotations

import pathlib

from bob3.db import create_agent_run as _create_agent_run
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
    """Create a new sub-agent run record in the project's database.

    The db_path parameter MUST be provided by callers that know the project's
    database path so the FK (sub_agent_runs.project_id REFERENCES projects(id))
    resolves against the same database that holds the project row.
    """
    return _create_agent_run(
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
