"""Bob3 CLI - Build Orchestration Bot v3.

Command-line interface using Click for managing Bob3 projects,
planning features, running builds, and checking status.
"""

import json
import logging
import os
import pathlib
import re
import shutil
import sqlite3
import uuid

import click
import yaml
from rich.console import Console
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from bob3 import __version__
from bob3 import db as _db
from bob3.db import compute_spec_hash, create_features_from_spec, get_connection, get_feature, init_database, list_calibration_alerts, list_features, query_active_regressions, query_calibration_drift_summary, query_evidence


def get_database_path():
    """Indirect accessor so that tests patching ``bob3.db.get_database_path`` work.

    Using a module-level function import would bind the name at import time
    and bypass any patches the tests apply. Routing through the module
    ensures the patch is honored at call time.
    """
    return _db.get_database_path()
from bob3.logging_config import setup_logging
from bob3.mcp_lifecycle import MCPStartupError, start_mcp_server, stop_mcp_server
from bob3.pdf_utils import extract_pdf_text
from bob3.superpowers import run_verification_checklist

logger = logging.getLogger(__name__)


def _check_runtime_dependencies() -> None:
    """Pre-flight check for Node.js + Claude Code CLI before MCP startup.

    Bob3 spawns sub-agents through the ``claude-code-sdk`` Python package,
    which itself shells out to the ``claude`` CLI binary, which in turn
    requires a Node.js >= 18 runtime. If either is missing, the failure
    surfaces deep inside an asyncio coroutine inside the SDK with an
    opaque message — by the time the user sees it, MCP is already half
    started and the error doesn't tell them what to install. Surface a
    clear, actionable message before any of that fires.

    The check is intentionally cheap (``shutil.which``); it does NOT
    invoke the binaries, so it is safe to call from every entry point
    that will subsequently spawn a sub-agent.

    Exits with code 1 (matching the rest of the CLI's pre-flight error
    code) on missing dependency. Returns None on success.
    """
    if shutil.which("node") is None:
        click.echo(
            "ERROR: Node.js is required (install Node.js >= 18). "
            "See README Requirements.",
            err=True,
        )
        raise SystemExit(1)
    if shutil.which("claude") is None:
        click.echo(
            "ERROR: Claude Code CLI is required. Install with: "
            "npm install -g @anthropic-ai/claude-code",
            err=True,
        )
        raise SystemExit(1)


@click.group()
@click.version_option(version=__version__, prog_name="bob3")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose (DEBUG) logging.")
def main(verbose):
    """Bob3 - Build Orchestration Bot v3.

    A recursive build orchestration system that uses Claude Code sub-agents
    to research, plan, and execute software projects.
    """
    setup_logging(verbose=verbose)


@main.command()
@click.argument("project_path", type=click.Path())
@click.option("--name", "-n", default=None, help="Project name (defaults to directory name).")
def init(project_path, name):
    """Initialize a new Bob3 project.

    Creates the project workspace directory, initializes the SQLite database
    with the full schema, and inserts a project record. Starts the
    bob3-memory MCP server to verify it is available.

    PROJECT_PATH is the path to the project workspace directory.
    """
    logger.info("Initializing project at %s", project_path)

    # Pre-flight: confirm the Node.js / Claude Code CLI runtime is
    # available before we try to talk to MCP, so users get an actionable
    # message rather than a deep SDK error.
    _check_runtime_dependencies()

    # Start bob3-memory MCP server (required for all operations)
    try:
        start_mcp_server()
        logger.info("bob3-memory MCP server started")
    except MCPStartupError as exc:
        logger.error("Failed to start MCP server: %s", exc)
        raise SystemExit(1)

    project_path = pathlib.Path(project_path).resolve()

    # Derive project name from directory name if not provided
    project_name = name or project_path.name

    # Step 1: Create project workspace directory
    project_path.mkdir(parents=True, exist_ok=True)
    logger.debug("Created workspace directory: %s", project_path)

    # Step 2: Initialize SQLite database with schema.
    #
    # R9-008: honor BOB3_DATABASE_PATH when set so subsequent ``bob3 plan``
    # / ``bob3 run`` / ``bob3 status`` commands (which all route through
    # ``get_database_path()`` and respect that env var) can find the
    # project. Without this, a hardened deployment that places the DB
    # outside the workspace via BOB3_DATABASE_PATH would still create a
    # second, orphan ``bob3.db`` inside the workspace at init time, and
    # every later command would report "No project found" because the
    # env-var path is empty. See README "Security considerations".
    env_db_path = os.environ.get("BOB3_DATABASE_PATH", "").strip()
    if env_db_path:
        db_path = pathlib.Path(env_db_path).expanduser()
        # Ensure the parent dir exists (the operator may have set the env
        # var to e.g. /var/lib/bob3/bob3.db without pre-creating
        # /var/lib/bob3). Idempotent.
        db_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        db_path = project_path / "bob3.db"
    init_database(db_path=db_path)
    logger.debug("Database initialized: %s", db_path)
    click.echo(f"Database initialized at {db_path}")

    # Step 3: Insert project record
    project_id = str(uuid.uuid4())
    conn = get_connection(db_path=db_path)
    try:
        conn.execute(
            "INSERT INTO projects (id, name, workspace_path, status) VALUES (?, ?, ?, ?)",
            (project_id, project_name, str(project_path), "planning"),
        )
        conn.commit()
    finally:
        conn.close()

    # Step 4: Install bob3 skills into the workspace so sub-agents can
    # discover them via Claude Code's skill search.
    from bob3.skills_installer import install_skills_to_workspace

    installed_skills = install_skills_to_workspace(project_path)
    logger.debug("Installed %d skills", len(installed_skills))

    logger.info("Project '%s' initialized at %s", project_name, project_path)
    # Step 5: Display success message
    click.echo(f"Project '{project_name}' initialized at {project_path}")
    click.echo(f"Database created: {db_path}")
    if installed_skills:
        click.echo(f"Installed {len(installed_skills)} bob3 skills for sub-agents")


@main.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option(
    "--create",
    is_flag=True,
    default=False,
    help="Create features in the database from the spec.",
)
def plan(spec_file, create):
    """Generate an execution plan from a YAML spec file.

    Reads SPEC_FILE (a YAML file), parses the project specification,
    and displays a summary of the project name, version, and features.
    Use --create to persist the features to the database.
    """
    logger.info("Loading spec file: %s", spec_file)
    console = Console()
    spec_path = pathlib.Path(spec_file)

    try:
        with open(spec_path) as f:
            spec = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        logger.error("Invalid YAML in %s: %s", spec_path.name, exc)
        console.print(f"[red]Error: Invalid YAML in {spec_path.name}: {exc}[/red]")
        raise SystemExit(1)

    if spec is None:
        spec = {}

    project_name = spec.get("name", spec_path.stem)
    name_from_spec = "name" in spec
    version = spec.get("version", "")
    features = spec.get("features") or []

    # Display spec summary
    console.print(f"[bold]Spec file:[/bold] {spec_path.name}")

    info_table = Table(title=f"Plan: {project_name}", show_header=False)
    info_table.add_column("Field", style="bold")
    info_table.add_column("Value")
    info_table.add_row("Name", project_name)
    if version:
        info_table.add_row("Version", str(version))
    info_table.add_row("Features", str(len(features)))
    console.print(info_table)

    if features:
        # Normalize features into an ordered list of (spec_id, name, description)
        # tuples regardless of whether the YAML uses list-of-dicts or
        # dict-of-dicts (the form shipped in examples/03_simple_calculator_spec.yaml).
        # The previous implementation iterated a dict, which yielded the YAML
        # keys ("F001", "F002") as the value of `feat` — so the rendered Name
        # column was the spec ID and Description was always empty (R10-001).
        feat_rows: list[tuple[str, str, str]] = []
        if isinstance(features, dict):
            for idx, (spec_key, feat) in enumerate(features.items(), 1):
                if isinstance(feat, dict):
                    name = (
                        feat.get("title")
                        or feat.get("name")
                        or str(spec_key)
                    )
                    desc = feat.get("description", "") or ""
                else:
                    name = str(spec_key)
                    desc = str(feat) if feat is not None else ""
                feat_rows.append((str(spec_key), str(name), str(desc)))
        elif isinstance(features, list):
            for i, feat in enumerate(features, 1):
                if isinstance(feat, dict):
                    name = (
                        feat.get("title")
                        or feat.get("name")
                        or f"Feature {i}"
                    )
                    desc = feat.get("description", "") or ""
                else:
                    name = str(feat) if feat is not None else f"Feature {i}"
                    desc = ""
                feat_rows.append((str(i), str(name), str(desc)))

        feat_table = Table(title="Features")
        feat_table.add_column("#", justify="right", style="dim")
        feat_table.add_column("Name")
        feat_table.add_column("Description", max_width=60)
        for row_id, row_name, row_desc in feat_rows:
            feat_table.add_row(row_id, row_name, row_desc)
        console.print(feat_table)

    # Store spec hash for change detection (F115)
    spec_hash = compute_spec_hash(spec_path)
    logger.info("Spec hash computed: %s", spec_hash[:12])

    # Update project record with spec hash if a project exists.
    # Silently skip when no database or projects table exists — this lets
    # `bob3 plan <spec>` work as a pure preview without requiring `bob3 init`.
    db_path = get_database_path()
    conn = get_connection(db_path=db_path)
    try:
        try:
            row = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            row = None
        if row:
            conn.execute(
                "UPDATE projects SET spec_hash = ?, spec_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (spec_hash, str(spec_path.resolve()), row[0]),
            )
            conn.commit()
            logger.info("Stored spec hash on project %s", row[0])
    finally:
        conn.close()

    # Create features in database (F075)
    if create and features:
        db_path = get_database_path()
        conn = get_connection(db_path=db_path)
        try:
            row = conn.execute("SELECT id, name FROM projects LIMIT 1").fetchone()
        finally:
            conn.close()
        if row:
            project_id, db_project_name = row[0], row[1]

            # Validate spec name matches project name to prevent loading wrong spec
            # If the YAML had no explicit 'name' field, fall back to the DB project name
            if project_name != db_project_name:
                if not name_from_spec:
                    project_name = db_project_name
                    logger.info(
                        "Spec has no 'name' field; using project name '%s' from database",
                        db_project_name,
                    )
                else:
                    console.print(
                        f"[red bold]⚠️  ERROR: Spec name mismatch![/red bold]\n"
                        f"[yellow]Spec name:[/yellow] {project_name}\n"
                        f"[yellow]Database project:[/yellow] {db_project_name}\n\n"
                        f"[red]This spec appears to be for a different project![/red]\n"
                        f"Loading the wrong spec will pollute the database with incorrect features.\n\n"
                        f"To fix: re-initialize with "
                        f"`bob3 init <path> --name <spec-name>`, where <spec-name> "
                        f"is the `name:` field in your spec (here: '{project_name}').\n"
                        f"Alternatively, rename the spec's `name:` field to match the project."
                    )
                    logger.error(
                        "Spec name '%s' does not match project name '%s'",
                        project_name,
                        db_project_name,
                    )
                    raise SystemExit(1)

            created = create_features_from_spec(project_id=project_id, spec=spec)
            console.print(
                f"[green]Created {len(created)} features in database.[/green]"
            )
            logger.info("Created %d features from spec", len(created))
        else:
            console.print("[yellow]No project found. Run 'bob3 init' first.[/yellow]")


def _run_orchestration_loop(
    project_id: str,
    max_cost: float | None = None,
    fresh: bool = False,
    target_feature_id: str | None = None,
    force_unlock: bool = False,
) -> "LoopTermination":
    """Run the orchestration loop synchronously.

    Wraps the async OrchestrationLoop.run() for use from Click commands.

    Args:
        project_id: The project to build.
        max_cost: Optional maximum cost in USD.
        fresh: If True, skip resume and reset all interrupted features.
        target_feature_id: If set, the loop runs only this single feature
            and exits after one iteration regardless of outcome.
        force_unlock: If True, forcibly clear a stale ``.bob3.lock`` whose
            holder PID is dead before acquiring (R10-006).

    Returns:
        The LoopTermination reason.

    Raises:
        SystemExit(1): if another ``bob3 run`` already holds the
            per-project lock. The error is printed to stderr in a form
            suitable for the user.
    """
    import asyncio

    from bob3.orchestrator.run_loop import (
        AlreadyRunningError,
        LoopTermination,
        OrchestrationLoop,
    )

    conn = get_connection()
    try:
        project = conn.execute(
            "SELECT workspace_path FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()
    workspace = project[0] if project else ""

    loop = OrchestrationLoop(
        project_id=project_id,
        max_cost=max_cost,
        workspace=workspace,
        fresh=fresh,
        target_feature_id=target_feature_id,
        force_unlock=force_unlock,
    )

    try:
        return asyncio.run(loop.run())
    except AlreadyRunningError as exc:
        # Another bob3 run is in flight for this project. Print a clear
        # message (the exception's str carries the lock path so the user
        # can see WHICH project is locked) and exit 1.
        click.echo(str(exc), err=True)
        raise SystemExit(1)


def _build_exit_codes() -> dict:
    """Build the LoopTermination -> POSIX exit code map.

    Imported lazily because LoopTermination lives in
    ``bob3.orchestrator.run_loop``, which we don't want to drag into the
    CLI module's import cost on every invocation. Resolving on demand
    also keeps test patches honoured.
    """
    from bob3.orchestrator.run_loop import LoopTermination

    return {
        LoopTermination.ALL_COMPLETED: 0,
        LoopTermination.ALL_BLOCKED: 2,
        LoopTermination.BUDGET_EXCEEDED: 3,
        # SIGINT exit code by widely-used convention (128 + 2). Use the
        # same value for any graceful shutdown so operators can detect
        # interrupted runs in shell pipelines without parsing logs.
        LoopTermination.SHUTDOWN_REQUESTED: 130,
    }


class _LazyExitCodes:
    """Dict-like proxy that materialises the exit-code map on first read."""

    def __init__(self) -> None:
        self._cache: dict | None = None

    def _load(self) -> dict:
        if self._cache is None:
            self._cache = _build_exit_codes()
        return self._cache

    def get(self, key, default=None):
        return self._load().get(key, default)

    def __getitem__(self, key):
        return self._load()[key]

    def __contains__(self, key) -> bool:
        return key in self._load()


_EXIT_CODES = _LazyExitCodes()


_RUN_EPILOG = """\
Exit codes:

\b
  0   ALL_COMPLETED       all targeted features completed successfully
  2   ALL_BLOCKED         all remaining features are blocked / not runnable
  3   BUDGET_EXCEEDED     loop stopped because the budget was exhausted
  130 SHUTDOWN_REQUESTED  graceful shutdown (SIGINT / SIGTERM)

CI scripts that chain commands ('bob3 run --all && deploy.sh') can rely on
these codes — only exit 0 means "build is healthy and complete".
"""


@main.command(epilog=_RUN_EPILOG)
@click.option("--feature", "-f", help="Run a specific feature by ID.")
@click.option("--all", "run_all", is_flag=True, help="Run all ready features.")
@click.option(
    "--max-cost",
    type=float,
    default=None,
    help="Maximum cost in USD for this run.",
)
@click.option(
    "--fresh",
    is_flag=True,
    default=False,
    help="Force restart without resuming interrupted work.",
)
@click.option(
    "--no-mcp",
    is_flag=True,
    default=False,
    help="Skip starting the bob3-memory MCP server (for environments where embeddings are unavailable).",
)
@click.option(
    "--force-unlock",
    is_flag=True,
    default=False,
    help=(
        "Forcibly clear a stale .bob3.lock whose holder PID is dead "
        "(recovery from a SIGKILL/OOM-killed prior run). Has no effect "
        "if a real bob3 run is currently active."
    ),
)
def run(feature, run_all, max_cost, fresh, no_mcp, force_unlock):
    """Execute the build plan using Claude Code sub-agents.

    Spawns sub-agents to implement features and run tests.
    Starts the bob3-memory MCP server before any operations (unless --no-mcp).
    Automatically resumes interrupted work unless --fresh is specified.

    --feature ID  runs ONLY that single feature and exits after one iteration,
                  regardless of outcome. Other ready features in the same
                  project are NOT touched. The feature must be runnable
                  (status='ready' or 'pending' with all dependencies
                  completed); otherwise the run terminates with ALL_BLOCKED.
    --all         runs the continuous orchestration loop, picking the
                  highest-priority ready feature each iteration until all
                  features are completed/blocked or the budget is exceeded.
    --force-unlock  recovers from a stale .bob3.lock left behind by a
                  SIGKILLed / OOM-killed previous run. Only takes effect
                  if the lock holder PID is dead.

    The process exit code reflects how the loop terminated; see the
    Exit codes section below. CI pipelines should treat anything other
    than 0 as "do not deploy".
    """
    logger.info("Starting build run")
    console = Console()

    # Pre-flight: confirm the Node.js / Claude Code CLI runtime is
    # available before we try to talk to MCP, so users get an actionable
    # message rather than a deep SDK error.
    _check_runtime_dependencies()

    # Pre-flight: surface which auth path will be used so users get a clear
    # signal before MCP startup or sub-agent spawning. We do not fail here:
    # an OAuth-authenticated Claude Code CLI session works without an env
    # var, and the SDK will surface a more specific error if neither path
    # is available at call time.
    from bob3.orchestrator.claude_executor import validate_api_key

    key = validate_api_key()
    if key is None:
        click.echo(
            "Note: no ANTHROPIC_API_KEY set. Will use Claude Code Max Pro OAuth "
            "if available."
        )
    else:
        logger.debug("ANTHROPIC_API_KEY/CLAUDE_API_KEY detected; using API key auth")

    # Start bob3-memory MCP server (required for all operations)
    if not no_mcp:
        try:
            start_mcp_server()
            logger.info("bob3-memory MCP server started")
        except MCPStartupError as exc:
            logger.error("Failed to start MCP server: %s", exc)
            raise SystemExit(1)
    else:
        logger.info("Skipping MCP server startup (--no-mcp flag)")

    if max_cost is not None:
        click.echo(f"Max cost: ${max_cost:.2f}")

    if feature:
        # --feature runs ONLY the target feature and exits after one
        # iteration. The orchestration loop is scoped via target_feature_id;
        # no other ready features in the project are processed.
        logger.info(
            "Running single feature %s (single-feature scope)",
            feature,
        )
        click.echo(
            f"Running single feature {feature} (only this feature will run)"
        )

        # Get the project and feature
        db_path = get_database_path()
        conn = get_connection(db_path=db_path)
        try:
            # Look up the feature's project explicitly so --feature scopes
            # to that feature's project, not whichever happens to be first.
            feature_row = conn.execute(
                "SELECT project_id, status FROM features WHERE id = ?",
                (feature,),
            ).fetchone()
            if feature_row is None:
                console.print(f"[red]Feature {feature} not found.[/red]")
                raise SystemExit(1)

            project_id = feature_row[0]
        finally:
            conn.close()

        # Run the orchestration loop scoped to a single feature.
        from bob3.orchestrator.run_loop import LoopTermination

        termination = _run_orchestration_loop(
            project_id,
            max_cost=max_cost,
            fresh=fresh,
            target_feature_id=feature,
            force_unlock=force_unlock,
        )

        # R10-008: Re-read the feature's actual final status so the
        # user-facing message reflects what really happened. Previously
        # ALL_BLOCKED could mean "not runnable" OR "ran but ended
        # needs_human" (since R10-007 made the latter map to
        # ALL_BLOCKED) — print the specific status to disambiguate.
        feature_status = None
        try:
            db_path2 = get_database_path()
            conn2 = get_connection(db_path=db_path2)
            try:
                row = conn2.execute(
                    "SELECT status FROM features WHERE id = ?",
                    (feature,),
                ).fetchone()
                if row is not None:
                    feature_status = row[0]
            finally:
                conn2.close()
        except Exception:
            logger.debug(
                "Could not re-read feature status post-run", exc_info=True
            )

        if termination == LoopTermination.ALL_COMPLETED:
            console.print("[green]Feature completed![/green]")
        elif termination == LoopTermination.ALL_BLOCKED:
            if feature_status == "needs_human":
                console.print(
                    "[yellow]Feature ended: needs_human "
                    "(verification, hook, or sub-agent error). "
                    "See `bob3 status --feature` for details.[/yellow]"
                )
            elif feature_status in {"failed", "interrupted"}:
                console.print(
                    f"[yellow]Feature ended: {feature_status}.[/yellow]"
                )
            else:
                console.print(
                    f"[yellow]Feature is blocked "
                    f"(status={feature_status or 'unknown'}).[/yellow]"
                )
        elif termination == LoopTermination.BUDGET_EXCEEDED:
            console.print("[red]Budget limit exceeded.[/red]")
        elif termination == LoopTermination.SHUTDOWN_REQUESTED:
            console.print("[yellow]Shutdown requested.[/yellow]")
        else:
            console.print(str(termination))
        # Map termination reason to a non-zero exit code so CI pipelines
        # (e.g. ``bob3 run --feature X && deploy.sh``) do not treat a
        # budget-exceeded or blocked run as success. ALL_COMPLETED is the
        # only outcome that exits cleanly with 0.
        exit_code = _EXIT_CODES.get(termination, 1)
        if exit_code != 0:
            raise SystemExit(exit_code)
    elif run_all:
        logger.info("Running all ready features")
        click.echo("Running all ready features...")

        # Get the project
        db_path = get_database_path()
        conn = get_connection(db_path=db_path)
        try:
            row = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
        finally:
            conn.close()

        if row is None:
            console.print("[yellow]No project found. Run 'bob3 init' first.[/yellow]")
            raise SystemExit(1)

        project_id = row[0]

        # Spec change detection (F115)
        from bob3.db import check_spec_changed, detect_spec_changes

        changed, old_hash, new_hash = check_spec_changed(project_id)
        if changed:
            console.print("[yellow]Spec file has changed since last run.[/yellow]")
            logger.info("Spec change detected (old=%s, new=%s)", old_hash, new_hash)
            changes = detect_spec_changes(project_id)
            if changes:
                if changes["added"]:
                    console.print(
                        f"  [green]+{len(changes['added'])} new feature(s)[/green]"
                    )
                if changes["modified"]:
                    console.print(
                        f"  [yellow]~{len(changes['modified'])} modified feature(s)[/yellow]"
                    )
                if changes["removed"]:
                    console.print(
                        f"  [red]-{len(changes['removed'])} removed feature(s)[/red]"
                    )

        from bob3.orchestrator.run_loop import LoopTermination

        termination = _run_orchestration_loop(
            project_id,
            max_cost=max_cost,
            fresh=fresh,
            force_unlock=force_unlock,
        )

        _TERMINATION_MESSAGES = {
            LoopTermination.ALL_COMPLETED: "[green]All features completed![/green]",
            LoopTermination.ALL_BLOCKED: "[yellow]All remaining features are blocked.[/yellow]",
            LoopTermination.BUDGET_EXCEEDED: "[red]Budget limit exceeded.[/red]",
            LoopTermination.SHUTDOWN_REQUESTED: "[yellow]Shutdown requested.[/yellow]",
        }
        console.print(_TERMINATION_MESSAGES.get(termination, str(termination)))
        # Map termination reason to a non-zero exit code so CI pipelines
        # (e.g. ``bob3 run --all && deploy.sh``) do not treat a
        # budget-exceeded or blocked run as success. ALL_COMPLETED is the
        # only outcome that exits cleanly with 0.
        exit_code = _EXIT_CODES.get(termination, 1)
        if exit_code != 0:
            raise SystemExit(exit_code)
    else:
        click.echo("No feature specified. Use --feature or --all.")


@main.command()
@click.option("--feature", "-f", help="Show status for a specific feature.")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed status.")
def status(feature, verbose):
    """Show project and feature status.

    Displays progress, confidence scores, and readiness.
    """
    logger.info("Checking project status")
    console = Console()
    db_path = get_database_path()

    # R10-004: Print a friendly hint if the DB file is missing or
    # corrupt, instead of letting a raw sqlite3 traceback bubble up.
    # ``bob3 status`` is the first command an operator will run after a
    # crash / cleanup script blew the DB away, and a stack trace there
    # is actively confusing — it suggests the CLI itself is broken.
    if not db_path.exists():
        console.print(
            f"[yellow]No bob3 database found at {db_path}.[/yellow]\n"
            f"[dim]Run [bold]bob3 init <path>[/bold] to create one, "
            f"or set BOB3_DATABASE_PATH to point at an existing project.[/dim]"
        )
        raise SystemExit(1)

    try:
        conn = get_connection(db_path=db_path)
    except sqlite3.DatabaseError as exc:
        console.print(
            f"[red]Failed to open bob3 database at {db_path}: {exc}.[/red]\n"
            f"[dim]The file exists but is not a valid SQLite database. "
            f"Restore from backup, or delete it and re-run "
            f"[bold]bob3 init[/bold] to start fresh.[/dim]"
        )
        raise SystemExit(1) from exc

    conn.row_factory = sqlite3.Row

    try:
        if feature:
            _show_feature_status(console, conn, feature)
        else:
            try:
                _show_project_status(console, conn, verbose)
            except sqlite3.OperationalError as exc:
                # The file is a real SQLite DB but the schema is missing
                # / partial (e.g. someone created a 0-byte file by hand).
                console.print(
                    f"[red]bob3 database at {db_path} is missing expected "
                    f"tables ({exc}).[/red]\n"
                    f"[dim]Re-run [bold]bob3 init[/bold] to recreate the "
                    f"schema, or restore from backup.[/dim]"
                )
                raise SystemExit(1) from exc
    finally:
        conn.close()


_STATUS_COLORS = {
    "completed": "green",
    "executing": "cyan",
    "ready": "blue",
    "pending": "yellow",
    "failed": "red",
    "blocked_by_reviewer": "red",
    "blocked_by_dependency": "red",
    "needs_human": "magenta",
    "resource_limited": "red",
    "rolled_back": "red",
    "regression": "red",
    "interrupted": "yellow",
}


def _styled_status(status_text):
    """Return a Rich Text object with color based on feature status."""
    color = _STATUS_COLORS.get(status_text, "white")
    return Text(status_text, style=color)


def _detect_cost_proxy_status(conn, project_id: str) -> str | None:
    """Detect whether cost tracking is using the turn-count proxy.

    Returns a human-readable note for the status table, or None if the
    proxy doesn't appear to be in use.

    Signals:
    1. BOB3_COST_PER_TURN_PROXY env var set explicitly.
    2. Recent execution evidence shows cost_usd=null with num_turns > 0
       (indicates the SDK returned None for at least one run).
    """
    env_proxy = os.environ.get("BOB3_COST_PER_TURN_PROXY")
    proxy_rate = env_proxy if env_proxy is not None else "0.05"

    # Scan recent execution evidence for cost_usd=null markers.
    proxy_used = False
    try:
        rows = conn.execute(
            "SELECT content FROM evidence_artifacts "
            "WHERE project_id = ? AND type IN ('execution_output', 'execution_error') "
            "ORDER BY created_at DESC LIMIT 20",
            (project_id,),
        ).fetchall()
        for r in rows:
            try:
                payload = json.loads(r["content"])
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if payload.get("cost_usd") is None and (payload.get("num_turns") or 0) > 0:
                proxy_used = True
                break
    except sqlite3.Error:
        # Schema mismatch or DB issue — silently skip; it's an info row.
        pass

    if proxy_used:
        return (
            f"[yellow]turn-count proxy active (${proxy_rate}/turn) — "
            f"SDK is not reporting cost (likely Max Pro)[/yellow]"
        )
    if env_proxy is not None:
        return f"[dim]turn-count proxy configured (${proxy_rate}/turn)[/dim]"
    return None


def _show_project_status(console, conn, verbose):
    """Display overall project status with feature counts, progress bar, and cost warnings."""
    row = conn.execute("SELECT * FROM projects LIMIT 1").fetchone()
    if row is None:
        console.print("[yellow]No project found. Run 'bob3 init' first.[/yellow]")
        return

    project_name = row["name"]
    project_status = row["status"]
    total_cost = row["total_cost_usd"] or 0.0
    max_cost = row["max_cost_usd"] or 500.0

    # Cost warning
    cost_pct = (total_cost / max_cost * 100) if max_cost > 0 else 0.0
    cost_display = f"${total_cost:.2f} / ${max_cost:.2f} ({cost_pct:.0f}%)"
    if cost_pct >= 90:
        cost_display += "  [red bold]!! CRITICAL: near budget limit !![/red bold]"
    elif cost_pct >= 80:
        cost_display += "  [yellow bold]! WARNING: approaching budget limit ![/yellow bold]"

    # Project info table
    info_table = Table(title=f"Project: {project_name}", show_header=False)
    info_table.add_column("Field", style="bold")
    info_table.add_column("Value")
    info_table.add_row("Status", project_status)
    info_table.add_row("Cost", cost_display)

    # Cost-tracking mode: surface when the turn-count proxy is in use
    # (Claude Max Pro / OAuth subscriptions return total_cost_usd=None).
    proxy_note = _detect_cost_proxy_status(conn, row["id"])
    if proxy_note is not None:
        info_table.add_row("Cost tracking", proxy_note)

    console.print(info_table)

    # Feature counts by status
    feature_rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM features WHERE project_id = ? GROUP BY status",
        (row["id"],),
    ).fetchall()

    total_features = sum(r["cnt"] for r in feature_rows)
    counts = {r["status"]: r["cnt"] for r in feature_rows}
    completed_count = counts.get("completed", 0)
    completion_pct = (completed_count / total_features * 100) if total_features > 0 else 0.0

    feat_table = Table(title="Features")
    feat_table.add_column("Status", style="bold")
    feat_table.add_column("Count", justify="right")
    for s in sorted(counts.keys()):
        feat_table.add_row(_styled_status(s), str(counts[s]))
    feat_table.add_row(Text("Total", style="bold"), str(total_features), style="bold")
    console.print(feat_table)

    # Progress bar for completion
    bar = ProgressBar(total=100, completed=completion_pct, width=40)
    console.print()
    console.print(f"  Progress: ", end="")
    console.print(bar, end="")
    console.print(f"  {completion_pct:.0f}% ({completed_count}/{total_features})")
    console.print()

    if verbose:
        # Show individual features
        features = conn.execute(
            "SELECT id, name, status, priority FROM features WHERE project_id = ? ORDER BY priority ASC",
            (row["id"],),
        ).fetchall()
        if features:
            detail_table = Table(title="Feature Details")
            detail_table.add_column("ID", style="dim", max_width=12)
            detail_table.add_column("Name")
            detail_table.add_column("Status")
            detail_table.add_column("Priority", justify="right")
            for f in features:
                detail_table.add_row(
                    f["id"][:12],
                    f["name"],
                    _styled_status(f["status"]),
                    str(f["priority"]),
                )
            console.print(detail_table)

    # Show calibration alerts (unacknowledged)
    alerts = list_calibration_alerts(project_id=row["id"], unacknowledged_only=True)
    if alerts:
        alert_table = Table(title="Calibration Alerts")
        alert_table.add_column("Direction", style="bold")
        alert_table.add_column("Task Class")
        alert_table.add_column("Bucket")
        alert_table.add_column("Drift", justify="right")
        alert_table.add_column("Samples", justify="right")
        for a in alerts:
            direction_style = "red" if a.direction == "overconfident" else "yellow"
            alert_table.add_row(
                Text(a.direction, style=direction_style),
                a.task_class,
                a.confidence_bucket,
                f"{a.drift_amount:+.2f}",
                str(a.sample_size),
            )
        console.print(alert_table)


def _show_feature_status(console, conn, feature_id):
    """Display status for a specific feature."""
    row = conn.execute(
        "SELECT * FROM features WHERE id = ?", (feature_id,)
    ).fetchone()
    if row is None:
        console.print(f"[yellow]Feature not found: {feature_id}[/yellow]")
        return

    table = Table(title=f"Feature: {row['name']}", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("ID", row["id"])
    table.add_row("Name", row["name"])
    table.add_row("Status", row["status"])
    table.add_row("Priority", str(row["priority"]))
    table.add_row("Risk", row["risk_category"])
    table.add_row("Readiness", f"{row['readiness_score']:.2f}")
    table.add_row("Spec Understanding", f"{row['conf_spec_understanding']:.2f}")
    table.add_row("Impl Correctness", f"{row['conf_impl_correctness']:.2f}")
    table.add_row("Test Adequacy", f"{row['conf_test_adequacy']:.2f}")
    console.print(table)


# ============================================================
# SHOW-EVIDENCE COMMAND (F077)
# ============================================================


@main.command("show-evidence")
@click.argument("feature_id")
def show_evidence_cmd(feature_id):
    """Show evidence artifacts for a specific feature.

    Displays all evidence artifacts associated with FEATURE_ID,
    including evidence type, content summary, and verification status.
    """
    logger.info("Showing evidence for feature: %s", feature_id)
    console = Console()

    evidence_list = query_evidence(feature_id=feature_id)

    if not evidence_list:
        console.print(f"[dim]No evidence found for feature: {feature_id}[/dim]")
        return

    console.print(f"\n[bold]Evidence for feature:[/bold] {feature_id}")
    console.print(f"[dim]Total: {len(evidence_list)} artifact(s)[/dim]\n")

    table = Table(title="Evidence Artifacts")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Type", style="bold")
    table.add_column("Content", max_width=60)
    table.add_column("Verified")
    table.add_column("Current")

    for i, ev in enumerate(evidence_list, 1):
        # Truncate content for summary display
        content_summary = ev.content
        if len(content_summary) > 80:
            content_summary = content_summary[:77] + "..."

        # Verification status
        if ev.verification_passed is True:
            verified = Text("Pass", style="green")
        elif ev.verification_passed is False:
            verified = Text("Fail", style="red")
        else:
            verified = Text("—", style="dim")

        # Current status
        current = Text("Yes", style="green") if ev.is_current else Text("No", style="dim")

        table.add_row(
            str(i),
            ev.type,
            content_summary,
            verified,
            current,
        )

    console.print(table)


# ============================================================
# GENERATE-FEATURES COMMAND (F103)
# ============================================================


def _parse_features_from_output(agent_output: str) -> list[dict]:
    """Extract features from agent output containing YAML code blocks.

    Looks for YAML code blocks (```yaml ... ```) in the agent output and
    parses them. Supports two formats:
    1. A mapping with a 'features' key containing a list
    2. A bare list of feature dicts

    Returns an empty list if no valid YAML features are found.
    """
    # Find YAML code blocks
    pattern = r"```(?:yaml|yml)\s*\n(.*?)```"
    matches = re.findall(pattern, agent_output, re.DOTALL)

    if not matches:
        return []

    for match in matches:
        try:
            parsed = yaml.safe_load(match)
        except yaml.YAMLError:
            continue

        if parsed is None:
            continue

        # Format 1: dict with 'features' key
        if isinstance(parsed, dict) and "features" in parsed:
            features = parsed["features"]
            if isinstance(features, list):
                return features

        # Format 2: bare list of feature dicts
        if isinstance(parsed, list):
            return parsed

    return []


def _run_generate_features(
    spec_content: str,
    ref_texts: list[str] | None = None,
) -> list[dict]:
    """Spawn a research sub-agent to generate features from a project spec.

    This function builds a prompt from the spec content and optional reference
    document texts, then calls the Claude Code SDK to generate features.

    In production, this spawns a real Claude sub-agent. For testing, this
    function is mocked.

    Args:
        spec_content: The raw YAML spec file content.
        ref_texts: Optional list of extracted text from reference PDFs.

    Returns:
        A list of feature dicts with keys like name, description, priority,
        acceptance_criteria.
    """
    import asyncio

    from bob3.orchestrator.claude_executor import (
        ClaudeExecutor,
        build_sub_agent_options,
    )

    prompt_parts = [
        "You are a feature generation assistant. Analyze the following project "
        "specification and generate a list of features needed to build it.\n\n"
        "For each feature, provide:\n"
        "- name: A concise feature name\n"
        "- description: What the feature does\n"
        "- priority: A number (lower = higher priority, starting at 10)\n"
        "- acceptance_criteria: A list of testable criteria\n\n"
        "Return your features in a YAML code block with a 'features' key.\n\n"
        "## Project Specification\n\n",
        spec_content,
    ]

    if ref_texts:
        prompt_parts.append("\n\n## Reference Documents\n\n")
        for i, text in enumerate(ref_texts, 1):
            prompt_parts.append(f"### Reference {i}\n\n{text}\n\n")

    prompt = "".join(prompt_parts)

    options = build_sub_agent_options(
        model="sonnet",
        max_turns=10,
    )

    executor = ClaudeExecutor(default_options=options)

    async def _run():
        result = await executor.execute(prompt)
        return _parse_features_from_output(result.text)

    return asyncio.run(_run())


@main.command("generate-features")
@click.argument("spec_file", type=click.Path(exists=True))
@click.option(
    "--refs",
    multiple=True,
    type=click.Path(),
    help="Reference document paths (PDFs) to include as context.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="features.yaml",
    help="Output YAML file path (default: features.yaml).",
)
@click.option(
    "--auto-continue",
    is_flag=True,
    default=False,
    help="Skip human review and proceed to plan automatically.",
)
def generate_features(spec_file, refs, output, auto_continue):
    """Generate features from a project spec using AI.

    Reads SPEC_FILE (a YAML file), optionally extracts content from
    reference PDFs (--refs), spawns a research sub-agent to generate
    features, and writes the result to an output YAML file.

    Usage: bob3 generate-features spec.yaml --refs paper.pdf --output features.yaml
    """
    logger.info("Generating features from spec: %s", spec_file)
    console = Console()
    spec_path = pathlib.Path(spec_file)

    # Step 1: Parse spec file
    try:
        spec_content = spec_path.read_text()
        spec = yaml.safe_load(spec_content)
    except yaml.YAMLError as exc:
        logger.error("Invalid YAML in %s: %s", spec_path.name, exc)
        console.print(f"[red]Error: Invalid YAML in {spec_path.name}: {exc}[/red]")
        raise SystemExit(1)

    if spec is None:
        spec = {}

    project_name = spec.get("name", spec_path.stem)
    console.print(f"[bold]Spec file:[/bold] {spec_path.name}")
    console.print(f"[bold]Project:[/bold] {project_name}")

    # Step 2: Extract PDF content from --refs
    ref_texts: list[str] = []
    for ref_path_str in refs:
        ref_path = pathlib.Path(ref_path_str)
        try:
            pdf_content = extract_pdf_text(ref_path)
            ref_texts.append(pdf_content.text)
            console.print(
                f"[dim]Loaded reference: {ref_path.name} "
                f"({pdf_content.metadata.get('page_count', '?')} pages)[/dim]"
            )
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"[yellow]Warning: Could not read {ref_path.name}: {exc}[/yellow]")

    # Step 3: Spawn research sub-agent
    console.print("[bold]Generating features...[/bold]")
    features = _run_generate_features(spec_content, ref_texts or None)

    # Step 4: Write output file
    output_path = pathlib.Path(output)
    output_data = {"name": project_name, "features": features}
    output_path.write_text(yaml.dump(output_data, default_flow_style=False, sort_keys=False))

    console.print(
        f"[green]Generated {len(features)} features -> {output_path}[/green]"
    )

    # Step 5: Display summary
    if features:
        feat_table = Table(title="Generated Features")
        feat_table.add_column("#", justify="right", style="dim")
        feat_table.add_column("Name")
        feat_table.add_column("Priority", justify="right")
        for i, feat in enumerate(features, 1):
            name = feat.get("name", f"Feature {i}")
            priority = str(feat.get("priority", ""))
            feat_table.add_row(str(i), name, priority)
        console.print(feat_table)

    # Step 6: Auto-continue
    if auto_continue and features:
        console.print("[bold cyan]Auto-continue: proceeding to plan...[/bold cyan]")


# ============================================================
# LIST-FEATURES COMMAND (F076)
# ============================================================


@main.command("list-features")
@click.option("--status", "-s", "filter_status", default=None, help="Filter by feature status.")
def list_features_cmd(filter_status):
    """List all features in the current project.

    Shows a table of all features with their ID, name, status, priority,
    and readiness score. Use --status to filter by status.
    """
    logger.info("Listing features (status filter: %s)", filter_status)
    console = Console()
    db_path = get_database_path()
    conn = get_connection(db_path=db_path)

    try:
        row = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
    finally:
        conn.close()

    if row is None:
        console.print("[yellow]No project found. Run 'bob3 init' first.[/yellow]")
        return

    project_id = row[0]
    features = list_features(project_id=project_id, status=filter_status)

    if not features:
        console.print("[dim]No features found.[/dim]")
        return

    table = Table(title="Features")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Priority", justify="right")
    table.add_column("Readiness", justify="right")

    for f in features:
        table.add_row(
            f.id[:12],
            f.name,
            _styled_status(f.status),
            str(f.priority),
            f"{f.readiness_score:.2f}",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(features)} feature(s)[/dim]")


# ============================================================
# SHOW-FEATURE COMMAND (F076)
# ============================================================


@main.command("show-feature")
@click.argument("feature_id")
def show_feature(feature_id):
    """Show detailed information about a specific feature.

    Displays all fields including confidence scores, readiness,
    risk category, and acceptance criteria.
    """
    logger.info("Showing feature: %s", feature_id)
    console = Console()

    feature = get_feature(feature_id)
    if feature is None:
        console.print(f"[yellow]Feature not found: {feature_id}[/yellow]")
        return

    table = Table(title=f"Feature: {feature.name}", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("ID", feature.id)
    table.add_row("Name", feature.name)
    table.add_row("Status", _styled_status(feature.status))
    table.add_row("Priority", str(feature.priority))
    table.add_row("Risk", feature.risk_category)
    table.add_row("Description", feature.description or "[dim]—[/dim]")

    table.add_row("", "")  # spacer
    table.add_row("Readiness", f"{feature.readiness_score:.2f}")
    table.add_row("Spec Understanding", f"{feature.conf_spec_understanding:.2f}")
    table.add_row("Impl Correctness", f"{feature.conf_impl_correctness:.2f}")
    table.add_row("Test Adequacy", f"{feature.conf_test_adequacy:.2f}")

    table.add_row("", "")  # spacer
    table.add_row("Refinement Attempts", f"{feature.refinement_attempts} / {feature.max_refinement_attempts}")
    table.add_row("Tasks", f"{feature.tasks_completed} / {feature.tasks_total}")

    if feature.parent_feature_id:
        table.add_row("Parent Feature", feature.parent_feature_id)
    if feature.decomposition_depth > 0:
        table.add_row("Decomposition Depth", str(feature.decomposition_depth))

    console.print(table)

    # Show acceptance criteria if present
    if feature.acceptance_criteria:
        import json as _json
        try:
            criteria = _json.loads(feature.acceptance_criteria)
            if isinstance(criteria, list):
                console.print("\n[bold]Acceptance Criteria:[/bold]")
                for i, c in enumerate(criteria, 1):
                    console.print(f"  {i}. {c}")
        except (_json.JSONDecodeError, TypeError):
            console.print(f"\n[bold]Acceptance Criteria:[/bold] {feature.acceptance_criteria}")


# ============================================================
# VERIFY-FEATURE COMMAND (R10-014)
# ============================================================


@main.command("verify-feature")
@click.argument("feature_id")
def verify_feature_cmd(feature_id):
    """Re-run verification on a feature's workspace.

    Useful for:
    - Manually checking a needs_human feature after fixing the underlying issue
    - Confirming work that completed despite a sub-agent crash (R10-014)

    If verification passes, marks the feature as 'completed' (and cascades
    dependents). If it fails, prints the failed checks and leaves the
    feature's status unchanged.
    """
    from bob3.db import complete_feature_and_cascade, get_project

    logger.info("Manually verifying feature: %s", feature_id)
    console = Console()

    feature = get_feature(feature_id)
    if feature is None:
        console.print(f"[red]Feature not found:[/red] {feature_id}")
        raise SystemExit(2)

    project = get_project(feature.project_id)
    if project is None:
        console.print(
            f"[red]Project {feature.project_id} not found for feature "
            f"{feature_id}[/red]"
        )
        raise SystemExit(2)

    workspace = project.workspace_path
    if not workspace:
        console.print(
            "[yellow]Project has no workspace_path; cannot run verification.[/yellow]"
        )
        raise SystemExit(2)

    console.print(f"[dim]Workspace:[/dim] {workspace}")
    console.print(f"[dim]Feature:[/dim] {feature.name} (status={feature.status})")

    try:
        verification = run_verification_checklist(
            workspace=workspace,
            acceptance_criteria=feature.acceptance_criteria,
            feature_description=feature.description,
        )
    except Exception as exc:
        console.print(f"[red]Verification crashed:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(3) from exc

    passed = bool(verification.get("passed", False))
    summary = verification.get("summary") or ""
    checks = verification.get("checks") or []

    if passed:
        console.print("[green]Verification passed.[/green]")
        if summary:
            console.print(f"  {summary}")
        # Mark completed and cascade dependents.
        try:
            unlocked = complete_feature_and_cascade(feature.id)
        except Exception as exc:
            console.print(
                f"[red]Failed to mark feature completed:[/red] "
                f"{type(exc).__name__}: {exc}"
            )
            raise SystemExit(3) from exc
        console.print(
            f"[green]Feature {feature.id} marked completed.[/green]"
        )
        if unlocked:
            console.print(
                f"  Unlocked {len(unlocked)} dependent feature(s): "
                f"{', '.join(f[:8] for f in unlocked)}"
            )
        return

    console.print("[red]Verification failed.[/red]")
    if summary:
        console.print(f"  {summary}")
    for chk in checks:
        if chk.get("passed"):
            continue
        name = chk.get("name", "?")
        details = chk.get("details", "")
        console.print(f"  [red]FAIL[/red] {name}: {details}")
    console.print(
        f"\n[yellow]Feature {feature.id} status unchanged "
        f"(currently '{feature.status}').[/yellow]"
    )
    raise SystemExit(1)


# ============================================================
# SHOW-LESSONS COMMAND (F078)
# ============================================================


def _fetch_lessons(scope: str | None = None) -> list[dict]:
    """Fetch lessons from bob3 memory.

    Args:
        scope: "global" for all lessons, "project" for project-scoped lessons,
            or None (defaults to global).

    Returns:
        A list of lesson dicts from bob3-memory.
    """
    import asyncio

    from bob3.memory_client import BobMemoryClient

    workspace = str(pathlib.Path.cwd())
    client = BobMemoryClient(workspace=workspace)

    async def _search():
        result = await client.search_memory(
            query="lessons learned",
            pool="lessons",
            limit=50,
        )
        if not result.success:
            return []
        if not isinstance(result.data, list):
            return []
        return result.data

    lessons = asyncio.run(_search())

    # Filter by scope
    if scope == "project":
        # Only include lessons that have a feature_id in metadata
        lessons = [
            lesson for lesson in lessons
            if isinstance(lesson.get("metadata"), dict)
            and lesson["metadata"].get("feature_id")
        ]

    return lessons


def _parse_lesson_content(content: str) -> dict[str, str]:
    """Parse structured lesson content into parts.

    Lesson content follows the format:
        TRIGGER: ...
        LESSON: ...
        SOLUTION: ...

    Returns dict with keys: trigger, lesson, solution.
    """
    parts = {"trigger": "", "lesson": "", "solution": ""}
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("TRIGGER:"):
            parts["trigger"] = line[len("TRIGGER:"):].strip()
        elif line.startswith("LESSON:"):
            parts["lesson"] = line[len("LESSON:"):].strip()
        elif line.startswith("SOLUTION:"):
            parts["solution"] = line[len("SOLUTION:"):].strip()
    return parts


@main.command("show-lessons")
@click.option(
    "--scope",
    type=click.Choice(["global", "project"], case_sensitive=False),
    default=None,
    help="Filter scope: 'global' for all lessons, 'project' for project-scoped lessons.",
)
def show_lessons_cmd(scope):
    """Show lessons learned from bob3 memory.

    Displays lessons stored in the bob3 memory lessons pool,
    including the lesson content, usefulness score, and times applied.

    Use --scope to filter: 'global' shows all lessons, 'project' shows
    only lessons associated with a project feature.
    """
    logger.info("Showing lessons (scope=%s)", scope or "global")
    console = Console()

    try:
        lessons = _fetch_lessons(scope)
    except Exception as exc:
        logger.error("Failed to fetch lessons: %s", exc)
        console.print(f"[red]Error: Failed to fetch lessons: {exc}[/red]")
        return

    if not lessons:
        console.print("[dim]No lessons found.[/dim]")
        return

    scope_label = scope or "global"
    console.print(f"\n[bold]Lessons[/bold] (scope: {scope_label})")
    console.print(f"[dim]Total: {len(lessons)} lesson(s)[/dim]\n")

    table = Table(title="Lessons")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Lesson", max_width=50)
    table.add_column("Usefulness", justify="right")
    table.add_column("Applied", justify="right")

    for i, lesson in enumerate(lessons, 1):
        content = lesson.get("content", "")
        parts = _parse_lesson_content(content)
        lesson_text = parts["lesson"] or content
        if len(lesson_text) > 60:
            lesson_text = lesson_text[:57] + "..."

        weight = lesson.get("retrieval_weight", 0.0)
        access_count = lesson.get("access_count", 0)

        table.add_row(
            str(i),
            lesson_text,
            f"{weight:.2f}",
            str(access_count),
        )

    console.print(table)


# ============================================================
# HELPER: Get current project ID
# ============================================================


def _get_current_project_id() -> str | None:
    """Return the ID of the first project in the database, or None."""
    db_path = get_database_path()
    conn = get_connection(db_path=db_path)
    try:
        row = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# ============================================================
# SHOW-CALIBRATION COMMAND (F079)
# ============================================================


@main.command("show-calibration")
def show_calibration_cmd():
    """Show calibration drift summary.

    Displays calibration data per task class and confidence bucket,
    including empirical vs expected pass rates, drift amount, and
    whether the system is overconfident, underconfident, or calibrated.
    """
    logger.info("Showing calibration drift summary")
    console = Console()

    project_id = _get_current_project_id()
    if project_id is None:
        console.print("[yellow]No project found. Run 'bob3 init' first.[/yellow]")
        return

    drift_data = query_calibration_drift_summary(project_id)

    if not drift_data:
        console.print("[dim]No calibration data available (need 10+ attempts per bucket).[/dim]")
        return

    console.print(f"\n[bold]Calibration Drift Summary[/bold]")
    console.print(f"[dim]Entries: {len(drift_data)}[/dim]\n")

    table = Table(title="Calibration Drift")
    table.add_column("Task Class", style="bold", no_wrap=True)
    table.add_column("Bucket")
    table.add_column("Empirical", justify="right")
    table.add_column("Expected", justify="right")
    table.add_column("Drift", justify="right")
    table.add_column("Attempts", justify="right")
    table.add_column("Status", no_wrap=True)

    for entry in drift_data:
        status = entry["status"]
        drift = entry["drift"]

        if status == "overconfident":
            status_text = Text("overconfident", style="red")
        elif status == "underconfident":
            status_text = Text("underconfident", style="yellow")
        else:
            status_text = Text("calibrated", style="green")

        table.add_row(
            entry["task_class"],
            entry["confidence_bucket"],
            f"{entry['empirical_pass_rate']:.2f}" if entry["empirical_pass_rate"] is not None else "—",
            f"{entry['expected_pass_rate']:.2f}" if entry["expected_pass_rate"] is not None else "—",
            f"{drift:+.2f}" if drift is not None else "—",
            str(entry["total_attempts"]),
            status_text,
        )

    console.print(table)


# ============================================================
# SHOW-REGRESSIONS COMMAND (F080)
# ============================================================


@main.command("show-regressions")
def show_regressions_cmd():
    """Show active regression events.

    Displays unresolved regression events, including the affected feature,
    causing feature, status, and number of affected tests.
    """
    import json as _json

    logger.info("Showing active regressions")
    console = Console()

    project_id = _get_current_project_id()
    if project_id is None:
        console.print("[yellow]No project found. Run 'bob3 init' first.[/yellow]")
        return

    regressions = query_active_regressions(project_id)

    if not regressions:
        console.print("[dim]No active regressions found.[/dim]")
        return

    console.print(f"\n[bold]Active Regressions[/bold]")
    console.print(f"[dim]Total: {len(regressions)} regression(s)[/dim]\n")

    table = Table(title="Active Regressions")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Affected Feature")
    table.add_column("Caused By")
    table.add_column("Status", no_wrap=True)
    table.add_column("Tests", justify="right")
    table.add_column("Detected At", no_wrap=True)

    for i, reg in enumerate(regressions, 1):
        status = reg.get("status", "unknown")
        status_text = Text(status, style="red" if status == "detected" else "yellow")

        # Count affected tests
        tests_str = reg.get("affected_tests") or "[]"
        try:
            tests = _json.loads(tests_str)
            test_count = str(len(tests)) if isinstance(tests, list) else "—"
        except (_json.JSONDecodeError, TypeError):
            test_count = "—"

        detected = reg.get("detected_at", "")
        if isinstance(detected, str) and len(detected) > 16:
            detected = detected[:16]

        table.add_row(
            str(i),
            reg.get("affected_feature_name", reg.get("affected_feature_id", "—")),
            reg.get("causing_feature_name", reg.get("causing_feature_id", "—")),
            status_text,
            test_count,
            str(detected),
        )

    console.print(table)


# ============================================================
# SHOW-REVIEWS COMMAND (review findings registry)
# ============================================================


@main.command("show-reviews")
@click.option("--query", "-q", default=None, help="Substring match in title/pattern/notes.")
@click.option("--tag", "-t", default=None, help="Filter by tag (e.g. allowlist-gap).")
@click.option("--severity", "-s", default=None,
              help="Filter by severity (critical/high/medium/low).")
@click.option("--status", default=None,
              help="Filter by status (open/in_progress/fixed/wontfix).")
@click.option("--file", "-f", "file_glob", default=None,
              help="Substring match against any file path in the finding.")
@click.option("--limit", default=30, help="Max results.")
@click.option("--summary", is_flag=True, help="Show registry summary instead of search results.")
def show_reviews_cmd(query, tag, severity, status, file_glob, limit, summary):
    """Show or search the adversarial-review findings registry.

    The registry lives at reviews/findings.yaml and tracks every bug or
    anti-pattern found by review passes, including links to recurring
    patterns. Use this command to look up prior findings before reporting
    a new one or to see how a class of issue has trended.
    """
    from bob3.reviews import load_registry, render_summary

    try:
        registry = load_registry()
    except FileNotFoundError:
        console = Console()
        console.print("[yellow]No registry found at reviews/findings.yaml[/yellow]")
        return

    console = Console()

    if summary:
        console.print(render_summary(registry))
        return

    results = registry.search(
        query=query,
        status=status,
        severity=severity,
        tag=tag,
        files_glob=file_glob,
        limit=limit,
    )

    if not results:
        console.print("[dim]No findings match.[/dim]")
        return

    table = Table(title=f"Review findings ({len(results)} match)")
    table.add_column("ID", style="bold")
    table.add_column("Sev", style="dim")
    table.add_column("Status")
    table.add_column("Title")
    table.add_column("Tags", style="dim")
    for f in results:
        sev_color = {
            "critical": "red bold",
            "high": "red",
            "medium": "yellow",
            "low": "dim",
        }.get(f.severity, "")
        status_color = {"fixed": "green", "open": "red"}.get(f.status, "")
        table.add_row(
            f.id,
            f"[{sev_color}]{f.severity}[/{sev_color}]" if sev_color else f.severity,
            f"[{status_color}]{f.status}[/{status_color}]" if status_color else f.status,
            f.title,
            ", ".join(f.tags[:3]) + ("…" if len(f.tags) > 3 else ""),
        )
    console.print(table)
