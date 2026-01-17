"""Sync commands for BOB CLI.

This module implements the 'bob sync' command for syncing tasks with spec sources.
"""

import json
import sys
import uuid
from datetime import datetime
from typing import Optional

import click

from bob.database.manager import DatabaseManager
from bob.models.base import Task, TaskStatus, AgentType, ModelTier
from bob.spec_sources import get_registry
from bob.state import StateManager
from bob.utils.sync_check import update_sync_hash


def get_active_project(db: DatabaseManager, project_id: Optional[str]) -> Optional[str]:
    """Get the active project ID.

    Args:
        db: Database manager
        project_id: Optional project ID from command line

    Returns:
        Project ID if found, None otherwise
    """
    if project_id:
        # Check if project exists
        project = db.get_project(project_id)
        if not project:
            click.echo(f"✗ Project not found: {project_id}", err=True)
            return None
        return project_id

    # Get active project from state file
    state = StateManager()
    active_project_id = state.get_active_project()

    if not active_project_id:
        click.echo("✗ No active project found", err=True)
        click.echo("  Set a project with: bob project use <name>", err=True)
        click.echo("  Or specify with: bob sync --project <name>", err=True)
        return None

    # Verify project exists in database
    project = db.get_project(active_project_id)
    if not project:
        click.echo(f"✗ Active project not found in database: {active_project_id}", err=True)
        click.echo("  The project may have been deleted.", err=True)
        click.echo("  Set a new active project with: bob project use <name>", err=True)
        return None

    return active_project_id


@click.command()
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force full re-sync (ignore cache)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be synced without making changes",
)
@click.option(
    "--json-output",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def sync(
    ctx: click.Context,
    force: bool,
    dry_run: bool,
    json_output: bool,
) -> None:
    """Sync tasks with spec source.

    \b
    Synchronizes tasks with the project's spec source (file, GitHub issues, etc.).
    Detects and applies:
      - New tasks (added)
      - Modified tasks (updated)
      - Removed tasks (marked as deprecated)

    \b
    Examples:
        bob sync                   # Sync active project
        bob sync --project my-app  # Sync specific project
        bob sync --force           # Force full re-sync
        bob sync --dry-run         # Show changes without applying

    \b
    The sync process:
        1. Loads the project and its spec source
        2. Calls spec_source.sync() to detect changes
        3. Adds new tasks to the database
        4. Updates modified tasks (preserves status and progress)
        5. Marks removed tasks as deprecated (never deletes)
        6. Displays a summary of changes
    """
    # Get database path from context
    db_path = ctx.obj.db_path

    # Initialize database manager
    db = DatabaseManager(db_path)

    # Get active project
    project_id = get_active_project(db, ctx.obj.project_id)
    if not project_id:
        sys.exit(1)

    # Get project from database
    project = db.get_project(project_id)
    if not project:
        click.echo(f"✗ Project not found: {project_id}", err=True)
        sys.exit(1)

    if not json_output:
        click.echo(f"🔄 Syncing project: {project.name} ({project.id})")
        click.echo(f"   Spec source: {project.spec_source}")
        click.echo()

    # Get spec source from registry
    registry = get_registry()
    try:
        spec_source = registry.create(project.spec_source, project.config)
    except Exception as e:
        click.echo(f"✗ Failed to create spec source: {e}", err=True)
        sys.exit(1)

    # Get existing tasks from database
    existing_tasks = db.list_tasks(project_id=project.id)

    # Build known tasks map (spec_id -> spec_version)
    # Note: We pass spec_version 1 for all known tasks since we don't track
    # spec versions in the database yet. The FileSpecSource will use file
    # hash to detect if the file has changed, and only then check spec_versions.
    known_tasks = {}
    existing_tasks_by_spec_id = {}
    for task in existing_tasks:
        existing_tasks_by_spec_id[task.spec_id] = task
        known_tasks[task.spec_id] = 1  # Assume version 1 for all existing tasks

    if force:
        # Force re-sync: treat all tasks as unknown
        known_tasks = {}
        if not json_output:
            click.echo("   Force mode: treating all tasks as new")

    # Sync with spec source
    try:
        if not json_output:
            click.echo("   Fetching changes from spec source...")

        # Use an async event loop to call the async sync method
        import asyncio
        sync_result = asyncio.run(spec_source.sync(known_tasks))
    except Exception as e:
        click.echo(f"✗ Failed to sync with spec source: {e}", err=True)
        sys.exit(1)

    # Check if there are any changes
    if not sync_result.has_changes:
        if json_output:
            click.echo(json.dumps({
                "project_id": project.id,
                "project_name": project.name,
                "changes": 0,
                "added": 0,
                "modified": 0,
                "removed": 0,
            }))
        else:
            click.echo("✓ No changes detected")
        return

    # Display summary
    if not json_output:
        click.echo(f"   Found changes:")
        click.echo(f"     Added: {len(sync_result.added)}")
        click.echo(f"     Modified: {len(sync_result.modified)}")
        click.echo(f"     Removed: {len(sync_result.removed)}")
        click.echo()

    # Dry run mode - just show what would be done
    if dry_run:
        if json_output:
            result_data = {
                "project_id": project.id,
                "project_name": project.name,
                "dry_run": True,
                "changes": sync_result.total_changes,
                "added": [{"spec_id": t.spec_id, "title": t.title} for t in sync_result.added],
                "modified": [{"spec_id": t.spec_id, "title": t.title} for t in sync_result.modified],
                "removed": [spec_id for spec_id in sync_result.removed],
            }
            click.echo(json.dumps(result_data, indent=2))
        else:
            click.echo("Dry run mode - no changes will be applied")
            click.echo()

            if sync_result.added:
                click.echo("Would add:")
                for task_spec in sync_result.added:
                    click.echo(f"  + {task_spec.spec_id}: {task_spec.title}")
                click.echo()

            if sync_result.modified:
                click.echo("Would modify:")
                for task_spec in sync_result.modified:
                    click.echo(f"  ~ {task_spec.spec_id}: {task_spec.title}")
                click.echo()

            if sync_result.removed:
                click.echo("Would deprecate:")
                for spec_id in sync_result.removed:
                    task = existing_tasks_by_spec_id.get(spec_id)
                    title = task.title if task else "Unknown"
                    click.echo(f"  - {spec_id}: {title}")
                click.echo()

        return

    # Apply changes
    added_count = 0
    modified_count = 0
    removed_count = 0

    # Add new tasks
    for task_spec in sync_result.added:
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        task = Task(
            id=task_id,
            project_id=project.id,
            spec_id=task_spec.spec_id,
            title=task_spec.title,
            description=task_spec.description,
            acceptance_criteria=task_spec.acceptance_criteria,
            steps=task_spec.steps,
            depends_on=task_spec.depends_on,
            priority=task_spec.priority,
            category=task_spec.category,
            labels=task_spec.labels,
            status=TaskStatus.PENDING,
            assigned_agent=None,
            current_model="claude-sonnet-4-5-20250929",
            attempts=0,
            escalation_tier=ModelTier.TIER1,
            failure_type=None,
            research_required=task_spec.research_required,
            research_complete=False,  # Start as incomplete
            research_queries=task_spec.research_queries,
            research_findings={},
        )

        try:
            db.create_task(task)
            added_count += 1
            if not json_output:
                click.echo(f"  + Added: {task_spec.spec_id} - {task_spec.title}")
        except Exception as e:
            click.echo(f"  ✗ Failed to add task {task_spec.spec_id}: {e}", err=True)

    # Update modified tasks
    for task_spec in sync_result.modified:
        existing_task = existing_tasks_by_spec_id.get(task_spec.spec_id)
        if not existing_task:
            click.echo(f"  ✗ Modified task not found in database: {task_spec.spec_id}", err=True)
            continue

        # Update spec fields while preserving status and progress
        try:
            db.update_task_spec(
                existing_task.id,
                title=task_spec.title,
                description=task_spec.description,
                acceptance_criteria=task_spec.acceptance_criteria,
                steps=task_spec.steps,
                depends_on=task_spec.depends_on,
                priority=task_spec.priority,
                category=task_spec.category,
                labels=task_spec.labels,
                research_required=task_spec.research_required,
                research_queries=task_spec.research_queries,
            )
            modified_count += 1
            if not json_output:
                click.echo(f"  ~ Modified: {task_spec.spec_id} - {task_spec.title}")
        except Exception as e:
            click.echo(f"  ✗ Failed to update task {task_spec.spec_id}: {e}", err=True)

    # Mark removed tasks as deprecated
    for spec_id in sync_result.removed:
        existing_task = existing_tasks_by_spec_id.get(spec_id)
        if not existing_task:
            click.echo(f"  ✗ Removed task not found in database: {spec_id}", err=True)
            continue

        try:
            db.update_task(existing_task.id, status=TaskStatus.DEPRECATED)
            removed_count += 1
            if not json_output:
                click.echo(f"  - Deprecated: {spec_id} - {existing_task.title}")
        except Exception as e:
            click.echo(f"  ✗ Failed to deprecate task {spec_id}: {e}", err=True)

    # Update last sync hash after successful sync
    update_sync_hash(db, project)

    # Display summary
    if json_output:
        result_data = {
            "project_id": project.id,
            "project_name": project.name,
            "changes": added_count + modified_count + removed_count,
            "added": added_count,
            "modified": modified_count,
            "removed": removed_count,
        }
        click.echo(json.dumps(result_data, indent=2))
    else:
        click.echo()
        click.echo("✓ Sync complete")
        click.echo(f"  Added: {added_count}")
        click.echo(f"  Modified: {modified_count}")
        click.echo(f"  Deprecated: {removed_count}")
        click.echo()

        if added_count > 0 or modified_count > 0:
            click.echo("Next steps:")
            click.echo("  1. Review tasks: bob task list")
            click.echo("  2. Run agent: bob run")
