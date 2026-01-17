"""Log viewing and filtering commands for BOB CLI.

This module implements the 'bob logs' command for viewing structured logs.
"""

import json
import sys
import time
from pathlib import Path
from typing import Iterator, List, Optional

import click

from bob.database.manager import DatabaseManager
from bob.state import StateManager


def _read_log_files(log_dir: Path) -> Iterator[dict]:
    """Read all JSON log files in a directory.

    Args:
        log_dir: Directory containing log files

    Yields:
        Parsed log entries as dictionaries
    """
    if not log_dir.exists():
        return

    # Get all .log files sorted by modification time
    log_files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)

    for log_file in log_files:
        try:
            with open(log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        yield entry
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue
        except Exception:
            # Skip files we can't read
            continue


def _filter_log_entry(
    entry: dict,
    session_id: Optional[str] = None,
    level: Optional[str] = None,
    event_type: Optional[str] = None,
) -> bool:
    """Check if a log entry matches filter criteria.

    Args:
        entry: Log entry dictionary
        session_id: Filter by session ID
        level: Filter by log level
        event_type: Filter by event type

    Returns:
        True if entry matches all filters, False otherwise
    """
    # Check session ID
    if session_id:
        context = entry.get("context", {})
        if context.get("session_id") != session_id:
            return False

    # Check level
    if level:
        if entry.get("level") != level.upper():
            return False

    # Check event type
    if event_type:
        if entry.get("event_type") != event_type:
            return False

    return True


def _format_log_entry(entry: dict, use_json: bool = False) -> str:
    """Format a log entry for display.

    Args:
        entry: Log entry dictionary
        use_json: If True, return raw JSON

    Returns:
        Formatted log string
    """
    if use_json:
        return json.dumps(entry)

    # Human-readable format
    timestamp = entry.get("timestamp", "")[:19]  # Trim microseconds and 'Z'
    level = entry.get("level", "INFO")
    message = entry.get("message", "")
    event_type = entry.get("event_type", "")
    context = entry.get("context", {})

    # Color codes for levels
    level_colors = {
        "DEBUG": "blue",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
    }
    level_color = level_colors.get(level, "white")

    # Build formatted string
    parts = [
        click.style(timestamp, fg="cyan"),
        click.style(f"[{level}]", fg=level_color, bold=True),
    ]

    # Add event type if present
    if event_type:
        parts.append(click.style(f"({event_type})", fg="magenta"))

    parts.append(message)

    # Add context info
    if context:
        context_parts = []
        if "project_id" in context:
            context_parts.append(f"project={context['project_id']}")
        if "task_id" in context:
            context_parts.append(f"task={context['task_id']}")
        if "session_id" in context:
            context_parts.append(f"session={context['session_id'][:8]}...")

        if context_parts:
            parts.append(click.style(f"[{', '.join(context_parts)}]", dim=True))

    # Add exception if present
    if "exception" in entry:
        parts.append("\n" + click.style(entry["exception"], fg="red"))

    return " ".join(parts)


def _follow_logs(
    log_dir: Path,
    session_id: Optional[str] = None,
    level: Optional[str] = None,
    event_type: Optional[str] = None,
    use_json: bool = False,
) -> None:
    """Follow logs in real-time (like tail -f).

    Args:
        log_dir: Directory containing log files
        session_id: Filter by session ID
        level: Filter by log level
        event_type: Filter by event type
        use_json: Output raw JSON
    """
    # Get all log files
    if not log_dir.exists():
        click.echo(f"✗ Log directory not found: {log_dir}", err=True)
        sys.exit(1)

    log_files = list(log_dir.glob("*.log"))
    if not log_files:
        click.echo(f"✗ No log files found in {log_dir}", err=True)
        sys.exit(1)

    # Get the most recent log file
    log_file = max(log_files, key=lambda p: p.stat().st_mtime)

    # Open file and seek to end
    with open(log_file, "r") as f:
        # Go to end of file
        f.seek(0, 2)

        try:
            while True:
                line = f.readline()
                if line:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            if _filter_log_entry(entry, session_id, level, event_type):
                                click.echo(_format_log_entry(entry, use_json))
                        except json.JSONDecodeError:
                            pass
                else:
                    time.sleep(0.1)  # Wait for new content
        except KeyboardInterrupt:
            # Clean exit on Ctrl+C
            pass


@click.command()
@click.option(
    "--follow",
    "-f",
    is_flag=True,
    help="Follow log output (like tail -f)",
)
@click.option(
    "--session",
    "-s",
    "session_id",
    help="Filter by session ID",
)
@click.option(
    "--level",
    "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Filter by log level",
)
@click.option(
    "--event",
    "-e",
    "event_type",
    help="Filter by event type (e.g., task_started, task_completed)",
)
@click.option(
    "--json",
    "use_json",
    is_flag=True,
    help="Output raw JSON (one entry per line)",
)
@click.option(
    "--tail",
    "-n",
    type=int,
    default=100,
    help="Show last N entries (default: 100)",
)
@click.pass_context
def logs(
    ctx: click.Context,
    follow: bool,
    session_id: Optional[str],
    level: Optional[str],
    event_type: Optional[str],
    use_json: bool,
    tail: int,
) -> None:
    """View structured logs for the active project.

    \b
    Examples:
        bob logs                           # Show last 100 log entries
        bob logs --follow                  # Stream logs in real-time
        bob logs --session sess-abc123     # Show logs for specific session
        bob logs --level ERROR             # Show only errors
        bob logs --event task_started      # Show task start events
        bob logs --json                    # Output raw JSON
        bob logs --tail 50                 # Show last 50 entries

    Displays structured JSON logs with:
        - Timestamp (UTC)
        - Log level (DEBUG, INFO, WARNING, ERROR)
        - Event type (task_started, session_ended, etc.)
        - Message
        - Context (project_id, task_id, session_id)
        - Exception traces (for errors)
    """
    # Get database path from context
    db_path = ctx.obj.db_path

    # Initialize state manager to get active project
    # StateManager expects a directory - use parent of db file
    state_dir = db_path.parent
    state = StateManager(state_dir)
    active_project = state.get_active_project()

    if not active_project:
        click.echo("✗ No active project. Use 'bob project use <name>' first.", err=True)
        sys.exit(1)

    # Initialize database manager
    db = DatabaseManager(db_path)
    project = db.get_project(active_project)

    if not project:
        click.echo(f"✗ Project not found: {active_project}", err=True)
        sys.exit(1)

    # Get log directory
    log_dir = Path(project.workspace_dir) / ".bob" / "logs"

    if not log_dir.exists():
        click.echo(f"✗ No logs found for project '{project.name}'", err=True)
        click.echo(f"  Log directory: {log_dir}", err=True)
        sys.exit(1)

    # Follow mode (real-time streaming)
    if follow:
        _follow_logs(log_dir, session_id, level, event_type, use_json)
        return

    # Regular mode (read all logs and filter)
    entries: List[dict] = []

    for entry in _read_log_files(log_dir):
        if _filter_log_entry(entry, session_id, level, event_type):
            entries.append(entry)

    if not entries:
        click.echo("No matching log entries found.")
        return

    # Show last N entries
    entries = entries[-tail:]

    # Display entries
    for entry in entries:
        click.echo(_format_log_entry(entry, use_json))
