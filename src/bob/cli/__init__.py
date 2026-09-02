"""Bob CLI - Build Orchestration Bot v3.

Command-line interface using Click for managing Bob projects,
planning features, running builds, and checking status.
"""

import hashlib
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

from bob import __version__
from bob import db as _db
from bob.db import compute_spec_hash, create_features_from_spec, get_connection, get_feature, init_database, list_calibration_alerts, list_features, query_active_regressions, query_calibration_drift_summary, query_evidence
from bob.feature_planner import (
    FeaturePlanValidationError,
    PLANNER_ALLOWED_TOOLS,
    PLANNER_CLI_EXTRA_ARGS,
    PLANNER_DISALLOWED_TOOLS,
    PLANNER_SOURCE_PRECEDENCE_ENV,
    PlannerSourceFile,
    build_file_backed_feature_planner_prompt,
    create_ephemeral_planner_environment,
    materialize_feature_planner_sources,
    parse_and_validate_feature_plan,
    planner_source_manifest_sha256,
    project_name_from_source,
    resolve_planner_source_precedence,
    sanitize_planner_diagnostic,
)
from bob.models import resolve_max_cost_usd
from bob.progress_events import get_progress_path


def get_database_path():
    """Indirect accessor so that tests patching ``bob.db.get_database_path`` work.

    Using a module-level function import would bind the name at import time
    and bypass any patches the tests apply. Routing through the module
    ensures the patch is honored at call time.
    """
    return _db.get_database_path()
import bob.cli.init as _cli_init_module  # noqa: F401 — integration wiring
import bob.cli.run as _cli_run_module  # noqa: F401 — env_preflight integration wiring
from bob.cli.spec_trace import spec_trace as _spec_trace_handler
from bob.logging_config import setup_logging
from bob.mcp_lifecycle import MCPStartupError, start_mcp_server, stop_mcp_server
from bob.pdf_utils import extract_pdf_text
from bob.superpowers import run_verification_checklist

logger = logging.getLogger(__name__)


def _check_runtime_dependencies() -> None:
    """Pre-flight check for Node.js + Claude Code CLI before MCP startup.

    Bob spawns sub-agents through the ``claude-code-sdk`` Python package,
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
@click.version_option(version=__version__, prog_name="bob")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose (DEBUG) logging.")
def main(verbose):
    """Bob - Build Orchestration Bot v3.

    A recursive build orchestration system that uses Claude Code sub-agents
    to research, plan, and execute software projects.
    """
    setup_logging(verbose=verbose)


@main.command()
@click.argument("project_path", type=click.Path())
@click.option("--name", "-n", default=None, help="Project name (defaults to directory name).")
@click.option("--spec", default=None, help="Path to the spec YAML to record as spec_path in the project row.")
@click.option("--brownfield", is_flag=True, default=False, help="Run a brownfield survey after init to index existing code.")
def init(project_path, name, spec, brownfield):
    """Initialize a new Bob project.

    Creates the project workspace directory, initializes the SQLite database
    with the full schema, and inserts a project record. Starts the
    bob-memory MCP server to verify it is available.

    PROJECT_PATH is the path to the project workspace directory.
    """
    logger.info("Initializing project at %s", project_path)

    # Pre-flight: confirm the Node.js / Claude Code CLI runtime is
    # available before we try to talk to MCP, so users get an actionable
    # message rather than a deep SDK error.
    _check_runtime_dependencies()

    # Start bob-memory MCP server (required for all operations)
    try:
        start_mcp_server()
        logger.info("bob-memory MCP server started")
    except MCPStartupError as exc:
        logger.error("Failed to start MCP server: %s", exc)
        raise SystemExit(1)

    project_path = pathlib.Path(project_path).resolve()

    # Derive project name from directory name if not provided
    project_name = name or project_path.name

    # Resolve spec path relative to CWD if provided
    spec_path_str: str | None = None
    if spec:
        spec_path_resolved = pathlib.Path(spec).resolve()
        spec_path_str = str(spec_path_resolved)

    # Step 1: Create project workspace directory
    project_path.mkdir(parents=True, exist_ok=True)
    logger.debug("Created workspace directory: %s", project_path)

    # Step 2: Initialize SQLite database with schema.
    #
    # R9-008: honor BOB_DATABASE_PATH when set so subsequent ``bob plan``
    # / ``bob run`` / ``bob status`` commands (which all route through
    # ``get_database_path()`` and respect that env var) can find the
    # project. Without this, a hardened deployment that places the DB
    # outside the workspace via BOB_DATABASE_PATH would still create a
    # second, orphan ``bob.db`` inside the workspace at init time, and
    # every later command would report "No project found" because the
    # env-var path is empty. See README "Security considerations".
    env_db_path = os.environ.get("BOB_DATABASE_PATH", "").strip()
    if env_db_path:
        db_path = pathlib.Path(env_db_path).expanduser()
        # Ensure the parent dir exists (the operator may have set the env
        # var to e.g. /var/lib/bob/bob.db without pre-creating
        # /var/lib/bob). Idempotent.
        db_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        db_path = project_path / "bob.db"

    # If the DB already exists (re-init after spawn), update the stale
    # project row rather than inserting a duplicate. This closes the
    # spec-name-convergence-pitfall: rsync copies the parent's DB which
    # still has the parent's name/spec_path; re-running init with the
    # correct --name and --spec rewrites those fields so the child row
    # reflects the real generation.
    init_database(db_path=db_path)
    logger.debug("Database initialized: %s", db_path)
    click.echo(f"Database initialized at {db_path}")

    # Step 3: Insert project record, or update existing row if the DB was
    # inherited from a parent generation via rsync.
    conn = get_connection(db_path=db_path)
    try:
        existing = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
        if existing:
            # Re-init: update stale name and spec_path from the parent gen.
            project_id = existing[0]
            update_fields: list = [project_name, str(project_path)]
            set_clause = "name = ?, workspace_path = ?"
            if spec_path_str is not None:
                set_clause += ", spec_path = ?"
                update_fields.append(spec_path_str)
            update_fields.append(project_id)
            conn.execute(
                f"UPDATE projects SET {set_clause} WHERE id = ?",
                update_fields,
            )
            conn.commit()
            logger.info(
                "Re-init: updated project row %s — name=%s spec_path=%s",
                project_id, project_name, spec_path_str,
            )
        else:
            project_id = str(uuid.uuid4())
            # Use the shared resolver so ``unlimited`` / ``none`` and numeric
            # values persist exactly as they do through create_project().
            _max_cost = resolve_max_cost_usd()
            conn.execute(
                "INSERT INTO projects (id, name, workspace_path, spec_path, status, max_cost_usd) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, project_name, str(project_path), spec_path_str, "planning", _max_cost),
            )
            conn.commit()
    finally:
        conn.close()

    # Step 4: Install bob skills into the workspace so sub-agents can
    # discover them via Claude Code's skill search.
    from bob.skills_installer import install_skills_to_workspace

    installed_skills = install_skills_to_workspace(project_path)
    logger.debug("Installed %d skills", len(installed_skills))

    logger.info("Project '%s' initialized at %s", project_name, project_path)
    # Step 5: Display success message
    click.echo(f"Project '{project_name}' initialized at {project_path}")
    click.echo(f"Database created: {db_path}")
    if spec_path_str:
        click.echo(f"Spec path recorded: {spec_path_str}")
    if installed_skills:
        click.echo(f"Installed {len(installed_skills)} bob skills for sub-agents")

    if brownfield:
        import pathlib as _pathlib
        from bob.brownfield.survey import build_survey
        click.echo(f"Running brownfield survey of {project_path}…")
        candidates = build_survey(project_path)
        click.echo(f"Brownfield survey complete. {len(candidates)} implicit feature candidate(s) found.")


@main.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option(
    "--create",
    is_flag=True,
    default=False,
    help="Create features in the database from the spec.",
)
@click.option(
    "--round",
    "round_num",
    default=None,
    type=int,
    help="Run all research agents for this round and surface a summary before planning.",
)
def plan(spec_file, create, round_num):
    """Generate an execution plan from a YAML spec file.

    Reads SPEC_FILE (a YAML file), parses the project specification,
    and displays a summary of the project name, version, and features.
    Use --create to persist the features to the database.
    Pass --round N to automatically run all research agents in parallel
    before planning, writing proposals to docs/recursion/roundN/research/.
    """
    logger.info("Loading spec file: %s", spec_file)
    console = Console()
    spec_path = pathlib.Path(spec_file)

    # Auto-trigger research harness when --round N is supplied.
    if round_num is not None:
        try:
            from bob.orchestrator.research_trigger import fire_research_for_round
            console.print(
                f"[bold cyan]Running research agents for round {round_num}...[/bold cyan]"
            )
            workspace = spec_path.parent.parent
            summary = fire_research_for_round(round_num=round_num, workspace=workspace)
            console.print(
                f"[green]Research complete:[/green] "
                f"{summary['total_proposals']} proposal(s) across "
                f"{len(summary['agent_counts'])} agent(s). "
                f"Output: {summary['output_dir']}"
            )
            if summary.get("high_impact_proposals"):
                console.print("[yellow]High-impact proposals:[/yellow]")
                for title in summary["high_impact_proposals"]:
                    console.print(f"  • {title}")
        except Exception as _exc:
            logger.warning("Research trigger failed: %s", _exc)
            console.print(
                f"[yellow]Research trigger failed ({_exc}); proceeding with plan.[/yellow]"
            )

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
    # `bob plan <spec>` work as a pure preview without requiring `bob init`.
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

    # Permanent-forward-carry audit (F-R7-permanent-carry-auditor).
    # Runs immediately after the spec is loaded (sidecar merge point) and
    # BEFORE feature insertion. Blocks plan --create when the merged spec is
    # missing required infra-recovery feature definitions (F-R7-478, F-R7-479,
    # F-R7-553). Sidecars that already carry these features pass silently.
    if create:
        try:
            from bob.bootstrap.permanent_forward_carry_auditor import (
                BootstrapAuditError,
                audit_merged_spec,
                fail_loud_on_missing,
            )
            _pfc_missing = audit_merged_spec(spec)
            if _pfc_missing:
                logger.warning(
                    "permanent_forward_carry_missing event: %s",
                    ", ".join(sorted(_pfc_missing)),
                )
                console.print(
                    "[red bold]plan --create ABORTED:[/red bold] "
                    "[red]permanent_forward_carry_missing — "
                    f"spec is missing required feature definition(s): "
                    f"{', '.join(sorted(_pfc_missing))}. "
                    "Add the missing feature(s) to bob4/research/staged_specs/ "
                    "and re-merge before running plan --create.[/red]"
                )
                fail_loud_on_missing(_pfc_missing)
        except BootstrapAuditError:
            raise SystemExit(1)
        except SystemExit:
            raise
        except Exception as _pfc_exc:
            logger.warning("permanent-forward-carry audit failed unexpectedly: %s", _pfc_exc)
            console.print(
                f"[yellow]permanent-forward-carry audit error ({_pfc_exc}); proceeding.[/yellow]"
            )

    # F-R1-011: Auto-sanitize spec on `--create` when any feature has a
    # TBD/TODO/FIXME/XXX placeholder acceptance_criteria. Synthesizes
    # concrete criteria via a Haiku sub-agent and rewrites SPEC_FILE in
    # place BEFORE features are inserted into the DB. Without this, every
    # placeholder ride forward into features.acceptance_criteria and gets
    # rejected by the independent evaluator with INSUFFICIENT_EVIDENCE.
    if create and features:
        try:
            from bob.spec_synthesizer import find_placeholder_features
            spec_check = yaml.safe_load(open(spec_path)) or {}
            if find_placeholder_features(spec_check):
                console.print(
                    "[yellow]Spec has placeholder acceptance_criteria; "
                    "running synthesizer (F-R1-011) before persist...[/yellow]"
                )
                import asyncio as _asyncio
                from bob.spec_synthesizer import sanitize_spec_file
                # Need project_id for sub-agent tracking. Look it up now;
                # if no project yet, skip synthesis (--create will create
                # features with placeholder ACs, which is the legacy
                # behavior and at least won't crash).
                try:
                    _conn = get_connection(db_path=get_database_path())
                    _row = _conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
                    _conn.close()
                    _pid = _row[0] if _row else None
                except Exception:
                    _pid = None
                if _pid:
                    _report = _asyncio.run(sanitize_spec_file(
                        spec_path,
                        project_id=_pid,
                        workspace=spec_path.parent.parent,
                    ))
                    console.print(
                        f"[green]Spec sanitized:[/green] "
                        f"synthesized={_report['synthesized']}/"
                        f"{_report['total']} "
                        f"fallback={_report['fell_back']}"
                    )
                    # Reload spec from the rewritten file so the insert below
                    # picks up the new criteria.
                    with open(spec_path) as f:
                        spec = yaml.safe_load(f) or {}
                    features = spec.get("features") or []
                else:
                    console.print(
                        "[yellow]Skipping synthesizer: no project found "
                        "(run bob init first). Features will be created "
                        "with placeholder ACs.[/yellow]"
                    )
        except Exception as _exc:
            logger.warning("spec sanitize failed: %s", _exc)
            console.print(
                f"[yellow]Spec sanitize failed ({_exc}); proceeding "
                "with original spec.[/yellow]"
            )
    # Composite spec_quality_score gate (F-R7-413 replacement)
    # Run before persisting features so bad specs are rejected early.
    if create and features:
        try:
            from bob.cli.plan import run_composite_score_gate
            _gate_workspace = spec_path.parent.parent
            _all_passed = run_composite_score_gate(
                features if isinstance(features, list) else list(features.values()),
                console,
                workspace=_gate_workspace,
            )
            if not _all_passed:
                console.print(
                    "[red bold]plan --create ABORTED: one or more features "
                    "failed the composite spec_quality_score gate (< 0.65). "
                    "Fix the spec and re-run.[/red bold]"
                )
                raise SystemExit(1)
        except SystemExit:
            raise
        except Exception as _exc:
            logger.warning("composite score gate failed unexpectedly: %s", _exc)
            console.print(
                f"[yellow]spec_quality_score gate error ({_exc}); proceeding.[/yellow]"
            )

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
                        f"`bob init <path> --name <spec-name>`, where <spec-name> "
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
            console.print("[yellow]No project found. Run 'bob init' first.[/yellow]")


@main.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Show what would change; do not write.")
@click.option("--no-update-db", is_flag=True, help="Skip updating feature rows in bob.db.")
@click.option(
    "--concurrency", default=4, show_default=True,
    help="How many features to synthesize in parallel.",
)
def sanitize(spec_file, dry_run, no_update_db, concurrency):
    """Synthesize concrete acceptance_criteria for placeholder features (F-R1-011).

    Reads SPEC_FILE (a YAML spec), finds every feature whose
    `acceptance_criteria` is a TBD/TODO/FIXME/XXX placeholder, calls a
    Haiku sub-agent to generate concrete machine-checkable criteria, and
    rewrites SPEC_FILE in place. Also updates the corresponding rows in
    `bob.db` (matched by feature name) unless --no-update-db.

    Run this after `bob init` and before `bob run --all` when the spec
    was authored with deferred ACs.
    """
    import asyncio
    from bob.spec_synthesizer import (
        sanitize_spec_file,
        iter_features,
    )

    spec_path = pathlib.Path(spec_file)
    console = Console()

    db_path = get_database_path()
    try:
        conn = get_connection(db_path=db_path)
        row = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
        conn.close()
    except Exception:
        row = None
    if not row:
        console.print(
            "[red]Error: no project found in bob.db. "
            "Run 'bob init <project_path>' first.[/red]"
        )
        raise SystemExit(1)
    project_id = row[0]

    try:
        report = asyncio.run(sanitize_spec_file(
            spec_path,
            project_id=project_id,
            workspace=spec_path.parent.parent,
            dry_run=dry_run,
            concurrency=concurrency,
        ))
    except Exception as exc:
        logger.error("Sanitize failed: %s", exc, exc_info=True)
        console.print(f"[red]Error: sanitize failed: {exc}[/red]")
        raise SystemExit(1)

    suffix = " [yellow](dry-run, no write)[/yellow]" if dry_run else ""
    console.print(
        f"[green]Sanitize report:[/green] total={report['total']} "
        f"synthesized={report['synthesized']} "
        f"fell_back={report['fell_back']} "
        f"written={report['written']}" + suffix
    )

    # Update DB rows to match the rewritten YAML (match by feature name).
    if not dry_run and not no_update_db and report.get("written"):
        with open(spec_path) as f:
            new_spec = yaml.safe_load(f) or {}
        updates = []
        for key, feat in iter_features(new_spec):
            ac = feat.get("acceptance_criteria")
            if not isinstance(ac, list):
                continue
            name = feat.get("title") or feat.get("name") or key
            updates.append((json.dumps(ac), name, project_id))
        if updates:
            conn = get_connection(db_path=db_path)
            try:
                updated = 0
                for ac_json, name, pid in updates:
                    cur = conn.execute(
                        "UPDATE features SET acceptance_criteria=?, "
                        "updated_at=CURRENT_TIMESTAMP "
                        "WHERE project_id=? AND name=?",
                        (ac_json, pid, name),
                    )
                    updated += cur.rowcount
                conn.commit()
                console.print(
                    f"[green]Updated {updated} feature row(s) in bob.db.[/green]"
                )
            finally:
                conn.close()


def _run_orchestration_loop(
    project_id: str,
    max_cost: float | None = None,
    fresh: bool = False,
    target_feature_id: str | None = None,
    force_unlock: bool = False,
    max_concurrent_features: int = 1,
) -> "LoopTermination":
    """Run the orchestration loop synchronously.

    Wraps the async OrchestrationLoop.run() for use from Click commands.

    Args:
        project_id: The project to build.
        max_cost: Optional maximum cost in USD.
        fresh: If True, skip resume and reset all interrupted features.
        target_feature_id: If set, the loop runs only this single feature
            and exits after one iteration regardless of outcome.
        force_unlock: If True, forcibly clear a stale ``.bob.lock`` whose
            holder PID is dead before acquiring (R10-006).

    Returns:
        The LoopTermination reason.

    Raises:
        SystemExit(1): if another ``bob run`` already holds the
            per-project lock. The error is printed to stderr in a form
            suitable for the user.
    """
    import asyncio

    from bob.orchestrator.run_loop import (
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
        max_concurrent_features=max_concurrent_features,
    )

    try:
        return asyncio.run(loop.run())
    except AlreadyRunningError as exc:
        # Another bob run is in flight for this project. Print a clear
        # message (the exception's str carries the lock path so the user
        # can see WHICH project is locked) and exit 1.
        click.echo(str(exc), err=True)
        raise SystemExit(1)


def format_queue_drained_message() -> str:
    """Return the user-facing CLI message for an ALL_BLOCKED (queue-drained) termination.

    The message clarifies that ALL_BLOCKED does not mean "stuck" — the ready
    queue is simply empty (remaining features are needs_human/executing/blocked).
    """
    return "Queue drained — no ready features left to claim (remaining are needs_human/executing/blocked)."


def _build_exit_codes() -> dict:
    """Build the LoopTermination -> POSIX exit code map.

    Imported lazily because LoopTermination lives in
    ``bob.orchestrator.run_loop``, which we don't want to drag into the
    CLI module's import cost on every invocation. Resolving on demand
    also keeps test patches honoured.
    """
    from bob.orchestrator.run_loop import LoopTermination

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

CI scripts that chain commands ('bob run --all && deploy.sh') can rely on
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
    help="Skip starting the bob-memory MCP server (for environments where embeddings are unavailable).",
)
@click.option(
    "--force-unlock",
    is_flag=True,
    default=False,
    help=(
        "Forcibly clear a stale .bob.lock whose holder PID is dead "
        "(recovery from a SIGKILL/OOM-killed prior run). Has no effect "
        "if a real bob run is currently active."
    ),
)
@click.option(
    "--ablation-mode",
    type=click.Choice(["V-1", "V0", "V1", "V2", "V3"], case_sensitive=False),
    default=None,
    help=(
        "Ablation study mode controlling which capabilities are active "
        "(V-1: no AI; V0: baseline; V1: +memory; V2: +research; V3: all). "
        "Overrides the BOB_ABLATION_MODE environment variable."
    ),
)
@click.option(
    "--max-concurrent-features",
    "max_concurrent_features",
    type=int,
    default=1,
    show_default=True,
    help=(
        "Maximum number of features to execute concurrently. "
        "Default 1 = sequential (backward compatible). "
        "Production target is 4-8."
    ),
)
def run(feature, run_all, max_cost, fresh, no_mcp, force_unlock, ablation_mode, max_concurrent_features):
    """Execute the build plan using Claude Code sub-agents.

    Spawns sub-agents to implement features and run tests.
    Starts the bob-memory MCP server before any operations (unless --no-mcp).
    Automatically resumes interrupted work unless --fresh is specified.

    --feature ID  runs ONLY that single feature and exits after one iteration,
                  regardless of outcome. Other ready features in the same
                  project are NOT touched. The feature must be runnable
                  (status='ready' or 'pending' with all dependencies
                  completed); otherwise the run terminates with ALL_BLOCKED.
    --all         runs the continuous orchestration loop, picking the
                  highest-priority ready feature each iteration until all
                  features are completed/blocked or the budget is exceeded.
    --force-unlock  recovers from a stale .bob.lock left behind by a
                  SIGKILLed / OOM-killed previous run. Only takes effect
                  if the lock holder PID is dead.

    The process exit code reflects how the loop terminated; see the
    Exit codes section below. CI pipelines should treat anything other
    than 0 as "do not deploy".
    """
    logger.info("Starting build run")
    console = Console()

    # Wire --ablation-mode CLI flag into the environment so all downstream
    # code (including sub-agents) picks it up via get_ablation_mode().
    if ablation_mode is not None:
        os.environ["BOB_ABLATION_MODE"] = ablation_mode.upper()

    from bob.ablation import get_ablation_mode as _get_ablation_mode
    _active_ablation_mode = _get_ablation_mode()
    logger.info("Ablation mode: %s", _active_ablation_mode.value)

    # Defense-in-depth: refuse to start if another orchestrator process
    # matching bob[0-9]+ run is detected in /proc, even if .bob.lock is
    # absent (guards against a second-instance race when the lock file was
    # incorrectly removed by a watchdog/operator using a naive pgrep).
    from bob.orchestrator.liveness_probe import is_orchestrator_alive as _is_alive
    if _is_alive():
        console.print(
            "[red]Another orchestrator (bob[0-9]+ run) is already running. "
            "Refusing to start a second instance to prevent DB races.[/red]"
        )
        raise SystemExit(1)

    # Pre-flight: confirm the Node.js / Claude Code CLI runtime is
    # available before we try to talk to MCP, so users get an actionable
    # message rather than a deep SDK error.
    _check_runtime_dependencies()

    # Pre-flight: surface which auth path will be used so users get a clear
    # signal before MCP startup or sub-agent spawning. We do not fail here:
    # an OAuth-authenticated Claude Code CLI session works without an env
    # var, and the SDK will surface a more specific error if neither path
    # is available at call time.
    from bob.orchestrator.claude_executor import validate_api_key

    key = validate_api_key()
    if key is None:
        click.echo(
            "Note: no ANTHROPIC_API_KEY set. Will use Claude Code Max Pro OAuth "
            "if available."
        )
    else:
        logger.debug("ANTHROPIC_API_KEY/CLAUDE_API_KEY detected; using API key auth")

    # Start bob-memory MCP server (required for all operations)
    if not no_mcp:
        try:
            start_mcp_server()
            logger.info("bob-memory MCP server started")
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
        from bob.orchestrator.run_loop import LoopTermination

        termination = _run_orchestration_loop(
            project_id,
            max_cost=max_cost,
            fresh=fresh,
            target_feature_id=feature,
            force_unlock=force_unlock,
            max_concurrent_features=max_concurrent_features,
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
                    "See `bob status --feature` for details.[/yellow]"
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
        # (e.g. ``bob run --feature X && deploy.sh``) do not treat a
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
            console.print("[yellow]No project found. Run 'bob init' first.[/yellow]")
            raise SystemExit(1)

        project_id = row[0]

        # Spec change detection (F115)
        from bob.db import check_spec_changed, detect_spec_changes

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

        from bob.orchestrator.run_loop import LoopTermination
        from bob.supervisor_loop import supervise_run

        _TERMINATION_MESSAGES = {
            LoopTermination.ALL_COMPLETED: "[green]All features completed![/green]",
            LoopTermination.ALL_BLOCKED: "[yellow]Queue drained — no ready features left to claim (remaining are needs_human/executing/blocked).[/yellow]",
            LoopTermination.BUDGET_EXCEEDED: "[red]Budget limit exceeded.[/red]",
            LoopTermination.SHUTDOWN_REQUESTED: "[yellow]Shutdown requested.[/yellow]",
        }

        # Feature 27e4c777 — unattended-build supervisor loop. When the
        # orchestration loop drains the queue (ALL_BLOCKED / QUEUE_DRAINED) but
        # runnable-or-recoverable pending features remain, reset the recoverable
        # transient-failed siblings and re-enter the loop instead of exiting for
        # a human to re-run. Budget/shutdown terminations are never auto-resumed.
        while True:
            termination = _run_orchestration_loop(
                project_id,
                max_cost=max_cost,
                fresh=fresh,
                force_unlock=force_unlock,
                max_concurrent_features=max_concurrent_features,
            )

            if termination is LoopTermination.ALL_BLOCKED:
                decision = supervise_run(project_id)
                if decision.should_resume:
                    if decision.reset_feature_ids:
                        console.print(
                            f"[cyan]Supervisor: reset "
                            f"{len(decision.reset_feature_ids)} recoverable "
                            f"feature(s); resuming build.[/cyan]"
                        )
                    else:
                        console.print(
                            "[cyan]Supervisor: runnable pending work remains; "
                            "resuming build.[/cyan]"
                        )
                    # Subsequent passes must not re-wipe partial WIP.
                    fresh = False
                    force_unlock = False
                    continue
            break

        console.print(_TERMINATION_MESSAGES.get(termination, str(termination)))
        # Map termination reason to a non-zero exit code so CI pipelines
        # (e.g. ``bob run --all && deploy.sh``) do not treat a
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
    # ``bob status`` is the first command an operator will run after a
    # crash / cleanup script blew the DB away, and a stack trace there
    # is actively confusing — it suggests the CLI itself is broken.
    if not db_path.exists():
        console.print(
            f"[yellow]No bob database found at {db_path}.[/yellow]\n"
            f"[dim]Run [bold]bob init <path>[/bold] to create one, "
            f"or set BOB_DATABASE_PATH to point at an existing project.[/dim]"
        )
        raise SystemExit(1)

    try:
        conn = get_connection(db_path=db_path)
    except sqlite3.DatabaseError as exc:
        console.print(
            f"[red]Failed to open bob database at {db_path}: {exc}.[/red]\n"
            f"[dim]The file exists but is not a valid SQLite database. "
            f"Restore from backup, or delete it and re-run "
            f"[bold]bob init[/bold] to start fresh.[/dim]"
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
                    f"[red]bob database at {db_path} is missing expected "
                    f"tables ({exc}).[/red]\n"
                    f"[dim]Re-run [bold]bob init[/bold] to recreate the "
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
    1. BOB_COST_PER_TURN_PROXY env var set explicitly.
    2. Recent execution evidence shows cost_usd=null with num_turns > 0
       (indicates the SDK returned None for at least one run).
    """
    env_proxy = os.environ.get("BOB_COST_PER_TURN_PROXY")
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
        console.print("[yellow]No project found. Run 'bob init' first.[/yellow]")
        return

    project_name = row["name"]
    project_status = row["status"]
    total_cost = row["total_cost_usd"] or 0.0
    from bob.models import resolve_max_cost_usd as _resolve_max_cost_usd
    max_cost = row["max_cost_usd"] or _resolve_max_cost_usd()

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
    model: str | None = None,
    source_precedence: str | None = None,
) -> list[dict]:
    """Spawn a planning sub-agent and return a validated feature DAG.

    ``spec_content`` is free-form requirement text, not trusted YAML or Bob
    configuration.  The model response is parsed under the strict planner
    contract before any caller can persist it.

    In production, this spawns a real Claude sub-agent. For testing, this
    function is mocked.

    Args:
        spec_content: Raw Markdown, plain text, or YAML application description.
        ref_texts: Optional list of extracted text from reference PDFs.
        model: Optional Claude model ID/alias.  Defaults to
            ``BOB_FEATURE_PLANNER_MODEL`` or exact ``claude-opus-4-8``.

    Returns:
        A validated list of feature mappings forming an acyclic DAG.

    Raises:
        FeaturePlanValidationError: If the model output is missing, ambiguous,
            malformed, or violates the feature-DAG contract.
        ValueError: If the configured planner model is unknown.
    """
    import asyncio
    import tempfile

    from bob.orchestrator.claude_executor import (
        ClaudeExecutor,
        _attach_stderr_capture,
        _format_spawn_exception,
        build_sub_agent_options,
        resolve_model_name,
    )

    source_precedence = resolve_planner_source_precedence(source_precedence)
    configured_model = model or os.environ.get(
        "BOB_FEATURE_PLANNER_MODEL", "claude-opus-4-8"
    )
    if not isinstance(configured_model, str) or not configured_model.strip():
        raise ValueError("feature planner model must be a non-empty string")
    # Resolve first so a typo fails closed.  ``build_sub_agent_options`` has a
    # compatibility fallback for ordinary workers, which is inappropriate for
    # a planner explicitly pinned by an autonomous campaign.
    resolved_model = resolve_model_name(configured_model.strip())
    if resolved_model is None:  # defensive: non-empty input always resolves
        raise ValueError("feature planner model did not resolve")

    # Always file-back requirement sources.  Claude Code transports the user
    # prompt as one argv element, whose Linux ceiling is typically 128 KiB;
    # PPAT's spec + review corpus legitimately exceeds it.  A private ephemeral
    # cwd also gives the planning agent only the sources it must read.
    with tempfile.TemporaryDirectory(prefix="bob-feature-planner-") as temp_dir:
        planner_workspace = pathlib.Path(temp_dir)
        sources = materialize_feature_planner_sources(
            planner_workspace,
            spec_content,
            ref_texts,
            source_precedence=source_precedence,
        )
        prompt = build_file_backed_feature_planner_prompt(
            sources, source_precedence=source_precedence
        )
        planner_env = create_ephemeral_planner_environment(planner_workspace)

        base_options = build_sub_agent_options(
            cwd=planner_workspace,
            model=resolved_model,
            allowed_tools=list(PLANNER_ALLOWED_TOOLS),
            disallowed_tools=list(PLANNER_DISALLOWED_TOOLS),
            permission_mode="default",
            mcp_servers={},
            env=planner_env,
            agent_role="planner",
        )
        base_options.extra_args = {
            **(dict(base_options.extra_args) if base_options.extra_args else {}),
            **dict(PLANNER_CLI_EXTRA_ARGS),
        }
        with tempfile.NamedTemporaryFile(
            mode="w+",
            encoding="utf-8",
            errors="replace",
            prefix="bob-feature-planner-stderr-",
            suffix=".log",
        ) as stderr_buffer:
            os.chmod(stderr_buffer.name, 0o600)
            options = _attach_stderr_capture(base_options, stderr_buffer)
            executor = ClaudeExecutor(default_options=options)

            async def _run():
                result = await executor.execute(prompt)
                if result.is_error:
                    raise RuntimeError(
                        result.error_message or "Claude planner returned an error result"
                    )
                # Only the final response text crosses out of the ephemeral
                # source workspace; Read results are never appended here.
                return result.text

            try:
                response_text = asyncio.run(_run())
            except Exception as exc:
                # Read a bounded head+tail from the real file-backed stream. The
                # SDK requires fileno(), so StringIO cannot be used here.
                try:
                    stderr_buffer.flush()
                    with open(stderr_buffer.name, "rb") as capture_reader:
                        capture_reader.seek(0, os.SEEK_END)
                        capture_size = capture_reader.tell()
                        capture_reader.seek(0)
                        if capture_size <= 32 * 1024:
                            captured_bytes = capture_reader.read()
                        else:
                            head = capture_reader.read(16 * 1024)
                            capture_reader.seek(-16 * 1024, os.SEEK_END)
                            tail = capture_reader.read(16 * 1024)
                            captured_bytes = (
                                head
                                + b"\n<stderr capture middle omitted>\n"
                                + tail
                            )
                    captured_stderr = captured_bytes.decode(
                        "utf-8", errors="replace"
                    )
                except OSError:
                    captured_stderr = ""

                raw_diagnostic = _format_spawn_exception(
                    exc,
                    captured_stderr=captured_stderr,
                    max_stderr_chars=2000,
                )
                safe_diagnostic = sanitize_planner_diagnostic(
                    raw_diagnostic,
                    prompt=prompt,
                    source_texts=(spec_content, *(ref_texts or ())),
                    workspace=planner_workspace,
                )
                raise FeaturePlanValidationError(
                    "Claude planner execution failed:\n" + safe_diagnostic
                ) from exc

    return parse_and_validate_feature_plan(response_text, sources=sources)


@main.command("generate-features")
@click.argument("spec_file", type=click.Path(exists=True))
@click.option(
    "--refs",
    multiple=True,
    type=click.Path(),
    help="Reference paths (PDF or UTF-8 text/Markdown/YAML) to include as context.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="features.yaml",
    help="Output path: canonical JSON for .json, YAML otherwise (default: features.yaml).",
)
@click.option(
    "--auto-continue",
    is_flag=True,
    default=False,
    help="Skip human review and proceed to plan automatically.",
)
@click.option(
    "--model",
    envvar="BOB_FEATURE_PLANNER_MODEL",
    default="claude-opus-4-8",
    show_default=True,
    show_envvar=True,
    help="Claude model ID or alias used only for feature planning.",
)
@click.option(
    "--source-precedence",
    envvar=PLANNER_SOURCE_PRECEDENCE_ENV,
    default=None,
    show_envvar=True,
    help="Trusted controller rule describing precedence among requirement sources.",
)
def generate_features(
    spec_file, refs, output, auto_continue, model, source_precedence
):
    """Generate features from a project spec using AI.

    Reads SPEC_FILE as Markdown, plain text, or YAML, optionally extracts content from
    reference PDFs or UTF-8 text documents (--refs), spawns a planning
    sub-agent to generate
    features, and writes canonical JSON for a .json output or YAML otherwise.

    Usage: bob generate-features requirements.md --refs paper.pdf --output features.yaml
    """
    logger.info("Generating features from spec: %s", spec_file)
    console = Console()
    spec_path = pathlib.Path(spec_file)

    # Step 1: Read the application description as opaque requirement text.
    # YAML name extraction is best-effort only; invalid YAML is perfectly valid
    # Markdown/plain-English input for this command.
    spec_content = spec_path.read_text()
    project_name = project_name_from_source(spec_content, spec_path.stem)
    console.print(f"[bold]Spec file:[/bold] {spec_path.name}")
    console.print(f"[bold]Project:[/bold] {project_name}")

    # Step 2: Load every normative reference.  References are all-or-nothing:
    # silently dropping an unreadable review/spec would produce an apparently
    # valid plan derived from incomplete authority.
    ref_texts: list[str] = []
    for ref_path_str in refs:
        ref_path = pathlib.Path(ref_path_str)
        try:
            if ref_path.suffix.lower() == ".pdf":
                pdf_content = extract_pdf_text(ref_path)
                ref_texts.append(pdf_content.text)
                detail = f"{pdf_content.metadata.get('page_count', '?')} pages"
            else:
                text_content = ref_path.read_text(encoding="utf-8")
                ref_texts.append(text_content)
                detail = f"{len(text_content.splitlines())} lines"
            console.print(
                f"[dim]Loaded reference: {ref_path.name} ({detail})[/dim]"
            )
        except (OSError, UnicodeError, ValueError) as exc:
            logger.error("Could not read normative reference %s: %s", ref_path, exc)
            console.print(
                f"[red]Error: Could not read normative reference "
                f"{ref_path.name}: {exc}[/red]"
            )
            raise SystemExit(1)

    # Step 3: Spawn planning sub-agent
    console.print(f"[bold]Generating features with {model}...[/bold]")
    try:
        resolved_precedence = resolve_planner_source_precedence(source_precedence)
        features = _run_generate_features(
            spec_content,
            ref_texts or None,
            model=model,
            source_precedence=resolved_precedence,
        )
    except (FeaturePlanValidationError, ValueError) as exc:
        logger.error("Feature planning failed closed: %s", exc)
        console.print(f"[red]Error: feature plan rejected: {exc}[/red]")
        raise SystemExit(1)

    # Step 4: Write output file
    output_path = pathlib.Path(output)
    output_data = {"name": project_name, "features": features}
    if resolved_precedence is not None:
        source_payloads = (("spec", spec_content),) + tuple(
            (f"reference-{index}", text)
            for index, text in enumerate(ref_texts, 1)
        )
        source_provenance = [
            {
                "source_id": source_id,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "line_count": len(text.splitlines()) or 1,
            }
            for source_id, text in source_payloads
        ]
        manifest_sources = tuple(
            PlannerSourceFile(
                source_id=item["source_id"],
                filename=(
                    "application-spec.txt"
                    if item["source_id"] == "spec"
                    else f"reference-{int(item['source_id'].split('-')[1]):03d}.txt"
                ),
                sha256=item["sha256"],
                line_count=item["line_count"],
            )
            for item in source_provenance
        )
        assignment = {
            "model": model,
            "source_precedence": resolved_precedence,
            "sources": source_provenance,
        }
        output_data["planner_provenance"] = {
            "schema_version": 1,
            **assignment,
            "source_precedence_sha256": hashlib.sha256(
                resolved_precedence.encode("utf-8")
            ).hexdigest(),
            "source_manifest_sha256": planner_source_manifest_sha256(
                manifest_sources, source_precedence=resolved_precedence
            ),
            "planner_assignment_sha256": hashlib.sha256(
                json.dumps(
                    assignment, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
            "feature_plan_sha256": hashlib.sha256(
                json.dumps(
                    features, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
        }
    if output_path.suffix.lower() == ".json":
        output_path.write_text(
            json.dumps(
                output_data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        output_path.write_text(
            yaml.safe_dump(
                output_data,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

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
        console.print("[yellow]No project found. Run 'bob init' first.[/yellow]")
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
    from bob.db import complete_feature_and_cascade, get_project

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
    """Fetch lessons from bob memory.

    Args:
        scope: "global" for all lessons, "project" for project-scoped lessons,
            or None (defaults to global).

    Returns:
        A list of lesson dicts from bob-memory.
    """
    import asyncio

    from bob.memory_client import BobMemoryClient

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
    """Show lessons learned from bob memory.

    Displays lessons stored in the bob memory lessons pool,
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
        console.print("[yellow]No project found. Run 'bob init' first.[/yellow]")
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
# CALIBRATION-REPORT COMMAND (F21288838)
# ============================================================


@main.command("calibration-report")
def calibration_report_cmd():
    """Show per-task-class calibration ECE report.

    Computes Expected Calibration Error (ECE) per task class bucket using
    the calibration_data table and displays a summary table.
    ECE = mean(|predicted_conf - empirical_accuracy|) across confidence buckets.
    """
    from bob.calibration import TASK_CLASSES, compute_ece_by_bucket
    from bob.db import get_connection

    logger.info("Showing calibration ECE report by task class")
    console = Console()

    project_id = _get_current_project_id()
    if project_id is None:
        console.print("[yellow]No project found. Run 'bob init' first.[/yellow]")
        return

    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT task_class, confidence_bucket, empirical_pass_rate, expected_pass_rate, total_attempts "
            "FROM calibration_data WHERE project_id = ? AND total_attempts > 0",
            (project_id,),
        )
        rows = cursor.fetchall()

    if not rows:
        console.print("[dim]No calibration data available.[/dim]")
        return

    # Build sample list for compute_ece_by_bucket
    samples = []
    for task_class, _bucket, empirical, expected, attempts in rows:
        if empirical is None or expected is None or attempts == 0:
            continue
        # Reconstruct synthetic samples: attempts * (empirical pass rate) passed
        passes = round(empirical * attempts)
        for i in range(attempts):
            samples.append({
                "task_class": task_class,
                "predicted_conf": expected,
                "passed": i < passes,
            })

    ece_by_class = compute_ece_by_bucket(samples)

    # Aggregate total_attempts per task class for the report
    class_attempts: dict[str, int] = {}
    for task_class, _bucket, _empirical, _expected, attempts in rows:
        class_attempts[task_class] = class_attempts.get(task_class, 0) + attempts

    console.print(f"\n[bold]Calibration ECE Report — by Task Class[/bold]\n")

    table = Table(title="Expected Calibration Error (ECE) by Task Class")
    table.add_column("Task Class", style="bold", no_wrap=True)
    table.add_column("ECE", justify="right")
    table.add_column("Samples", justify="right")
    table.add_column("Status", no_wrap=True)

    all_classes = sorted(set(list(ece_by_class.keys()) + list(class_attempts.keys())))
    for tc in all_classes:
        ece = ece_by_class.get(tc)
        n = class_attempts.get(tc, 0)
        if ece is None:
            table.add_row(tc, "—", str(n), Text("no data", style="dim"))
            continue
        if ece < 0.05:
            status_text = Text("well calibrated", style="green")
        elif ece < 0.15:
            status_text = Text("acceptable", style="yellow")
        else:
            status_text = Text("miscalibrated", style="red")
        table.add_row(tc, f"{ece:.4f}", str(n), status_text)

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
        console.print("[yellow]No project found. Run 'bob init' first.[/yellow]")
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
    from bob.reviews import load_registry, render_summary

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


# ============================================================
# SKILL-ACTIVATION-REPORT COMMAND (F25d52796)
# ============================================================


@main.command("skill-activation-report")
def skill_activation_report_cmd():
    """Show which skills fired most and their correlation with feature success.

    Reads skill_activation_logged events from .bob/progress.jsonl and
    reports: how many times each skill was activated, and what fraction of
    features that activated the skill ended up completed (success rate).
    """
    console = Console()
    progress_file = get_progress_path()

    if not progress_file.exists():
        console.print("[dim]No skill-activation events found.[/dim]")
        return

    # Parse events
    activation_events: list[dict] = []
    outcome_by_feature: dict[str, str] = {}

    for line in progress_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = record.get("event_type", "")
        payload = record.get("payload", {})

        if event_type == "skill_activation_logged":
            activation_events.append(payload)
        elif event_type == "progress_updated":
            fid = payload.get("feature_id")
            outcome = payload.get("outcome")
            if fid and outcome:
                outcome_by_feature[fid] = outcome

    if not activation_events:
        console.print("[dim]No skill-activation events found.[/dim]")
        return

    # Count activations and correlate with outcomes
    skill_fire_count: dict[str, int] = {}
    skill_success_count: dict[str, int] = {}
    skill_feature_count: dict[str, int] = {}

    for event in activation_events:
        feature_id = event.get("feature_id", "")
        skills_activated = event.get("skills_activated") or []
        outcome = outcome_by_feature.get(feature_id)

        for skill in skills_activated:
            skill_fire_count[skill] = skill_fire_count.get(skill, 0) + 1
            # Track per-feature for success rate (avoid counting one feature twice)
            # Use spawn+feature as a unit; if outcome is known, count it
            if outcome is not None:
                skill_feature_count[skill] = skill_feature_count.get(skill, 0) + 1
                if outcome == "completed":
                    skill_success_count[skill] = skill_success_count.get(skill, 0) + 1

    table = Table(title="Skill Activation Report")
    table.add_column("Skill", style="bold")
    table.add_column("Fires", justify="right")
    table.add_column("Success Rate", justify="right")

    for skill in sorted(skill_fire_count, key=lambda s: -skill_fire_count[s]):
        fires = skill_fire_count[skill]
        feature_count = skill_feature_count.get(skill, 0)
        if feature_count > 0:
            success_rate = skill_success_count.get(skill, 0) / feature_count * 100
            rate_str = f"{success_rate:.0f}%"
        else:
            rate_str = "—"
        table.add_row(skill, str(fires), rate_str)

    console.print(table)


# ============================================================
# BUNDLE COMMAND (b608725e)
# ============================================================


@main.command("bundle")
@click.option("--run-id", required=True, help="Sub-agent run ID (or feature ID) to bundle.")
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(),
    help="Directory to write the bundle tarball (default: current directory).",
)
def bundle_cmd(run_id, output_dir):
    """Export a reproducibility bundle tarball for a run.

    Exports a self-contained .tar.gz containing spec.yaml, transcript.txt,
    diff.patch, telemetry.jsonl, and env_lockfile.txt for the given run.
    Re-running from the bundle reproduces the same verdict offline.
    """
    import pathlib

    from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

    output_path = pathlib.Path(output_dir) if output_dir else None
    try:
        bundle_path = export_bundle(run_id=run_id, output_dir=output_path)
        click.echo(f"Bundle created: {bundle_path}")
    except ValueError as exc:
        click.echo(f"Error: {exc}")
        raise SystemExit(1)


@main.command("spec-trace")
@click.argument("target")
@click.option(
    "--db",
    "db_path",
    default=None,
    help="Path to bob.db (defaults to BOB_DATABASE_PATH env var or bob.db).",
)
def spec_trace_cmd(target: str, db_path: str | None) -> None:
    """Print an AC alongside its source-intent provenance spans.

    TARGET is <feature_id>:<ac_index> (e.g. abc123:2 for the third AC).
    """
    from bob.spec_quality.provenance import trace_ac

    if ":" not in target:
        click.echo(
            "Error: TARGET must be <feature_id>:<ac_index> (e.g. abc123:2)",
            err=True,
        )
        raise SystemExit(1)

    feature_id, _, raw_index = target.partition(":")
    try:
        ac_index = int(raw_index)
    except ValueError:
        click.echo(f"Error: ac_index must be an integer, got {raw_index!r}", err=True)
        raise SystemExit(1)

    try:
        result = trace_ac(feature_id, ac_index, db_path=db_path)
    except KeyError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    except IndexError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    click.echo(f"Feature : {result['feature_id']}")
    click.echo(f"AC [{result['ac_index']}]: {result['ac']}")
    click.echo("")
    if result["spans"]:
        click.echo("Provenance spans:")
        for span in result["spans"]:
            click.echo(f"  span={span['start']}:{span['end']}")
    else:
        click.echo("Provenance spans: (none — AC could not be traced to a source span)")


# ============================================================
# PLAN DIFF COMMAND (F-0bf30902)
# ============================================================


@main.group("plan-gate")
def plan_gate_group():
    """Plan-gate commands: manage the editable plan.yaml approval gate."""


@plan_gate_group.command("diff")
@click.argument("feature_id")
@click.option(
    "--workspace",
    default=None,
    type=click.Path(),
    help="Workspace root (defaults to CWD).",
)
def plan_diff_cmd(feature_id: str, workspace: str | None) -> None:
    """Show drift between plan.yaml and the current spec ACs for FEATURE_ID.

    Reads specs/<feature_id>/plan.yaml and compares its acceptance_criteria
    list against the current acceptance_criteria stored in bob.db.
    Exits 0 when there is no drift; exits 1 when the plan is stale.
    """
    import json as _json

    from bob.orchestrator.plan_gate import compute_plan_vs_spec_drift, load_plan

    console = Console()

    # Fetch current AC from DB
    db_path = get_database_path()
    conn = get_connection(db_path=db_path)
    try:
        row = conn.execute(
            "SELECT name, acceptance_criteria FROM features WHERE id = ?",
            (feature_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        console.print(f"[red]Feature not found:[/red] {feature_id}")
        raise SystemExit(2)

    feature_name = row[0]
    ac_raw = row[1]
    try:
        current_ac: list[str] = _json.loads(ac_raw) if isinstance(ac_raw, str) else (ac_raw or [])
    except (ValueError, TypeError):
        current_ac = []

    ws = pathlib.Path(workspace) if workspace else None
    plan = load_plan(feature_id, ws)
    drift_report = compute_plan_vs_spec_drift(feature_id, current_ac, ws)

    console.print(f"\n[bold]Plan diff:[/bold] {feature_name} ({feature_id[:12]})")

    if plan is None:
        console.print("[yellow]  plan.yaml does not exist yet.[/yellow]")
        raise SystemExit(1)

    approved_str = "[green]yes[/green]" if plan.get("approved") else "[red]no[/red]"
    console.print(f"  approved: {approved_str}")
    console.print(f"  plan spec_hash:    {drift_report['spec_hash_plan'] or '(none)'}")
    console.print(f"  current spec_hash: {drift_report['spec_hash_current']}")

    if not drift_report["drift"]:
        console.print("[green]  No drift — plan.yaml matches current spec.[/green]")
        return

    console.print("[yellow]  Drift detected:[/yellow]")
    for ac in drift_report["added"]:
        console.print(f"  [green]+ {ac}[/green]")
    for ac in drift_report["removed"]:
        console.print(f"  [red]- {ac}[/red]")
    raise SystemExit(1)


# ============================================================
# SPEC COMMANDS (F-9f58051a — persistent spec-critic registry)
# ============================================================


@main.group("spec")
def spec_group():
    """Spec-quality commands: critic findings registry and regression detection."""


@spec_group.command("trace")
@click.argument("target")
@click.option(
    "--db",
    "db_path",
    default=None,
    help="Path to bob.db (defaults to BOB_DATABASE_PATH env var or bob.db).",
)
def spec_trace_sub_cmd(target: str, db_path: str | None) -> None:
    """Print an AC alongside its source-intent provenance spans.

    TARGET is <feature_id>:<ac_index> (e.g. abc123:2 for the third AC).
    """
    _spec_trace_handler(target, db_path)


@spec_group.command("findings")
@click.option(
    "--since",
    default=None,
    metavar="REF",
    help=(
        "Filter findings first seen or last seen on/after REF. "
        "Accepts an ISO date (YYYY-MM-DD) or a run_id string."
    ),
)
@click.option(
    "--findings-file",
    default=None,
    type=click.Path(),
    help="Path to spec_findings.yaml (defaults to reviews/spec_findings.yaml).",
)
def spec_findings_cmd(since: str | None, findings_file: str | None) -> None:
    """Show spec-critic findings from the persistent registry.

    With --since REF, only findings first seen or last seen on/after REF
    are shown.  Without --since, all findings are listed.

    Exit codes: 0 = ok, 1 = halt-gate fired (critic_repeat_rate > 0.30).
    """
    from bob.spec_quality.spec_findings_registry import (
        diff_findings_since,
        is_halt_gate_fired,
    )
    import yaml as _yaml
    from pathlib import Path as _Path

    console = Console()

    fp = _Path(findings_file) if findings_file else None

    if since is not None:
        findings = diff_findings_since(since, findings_path=fp)
    else:
        # Load all findings
        from bob.spec_quality.spec_findings_registry import _findings_path, _load_yaml
        path = _findings_path(fp)
        data = _load_yaml(path)
        raw = data.get("findings", {})
        findings = [dict(v, _key=k) for k, v in raw.items()]
        findings.sort(key=lambda e: e.get("last_seen", ""), reverse=True)

    if not findings:
        console.print("[dim]No spec-critic findings found.[/dim]")
    else:
        table = Table(title=f"Spec-critic findings ({len(findings)})")
        table.add_column("Key", style="dim", no_wrap=True)
        table.add_column("Defect type")
        table.add_column("Severity")
        table.add_column("Regression")
        table.add_column("Occurrences", justify="right")
        table.add_column("Last seen")

        for entry in findings:
            is_reg = entry.get("is_regression", False)
            reg_str = "[red]YES[/red]" if is_reg else "[green]no[/green]"
            sev = entry.get("severity", "warning")
            sev_style = {"critical": "bold red", "error": "red", "warning": "yellow"}.get(sev, "")
            table.add_row(
                entry.get("_key", ""),
                entry.get("defect_type", ""),
                f"[{sev_style}]{sev}[/{sev_style}]" if sev_style else sev,
                reg_str,
                str(entry.get("occurrence_count", 1)),
                entry.get("last_seen", ""),
            )

        console.print(table)

    halt = is_halt_gate_fired(findings_path=fp)
    if halt:
        console.print(
            "[bold red]HALT GATE FIRED:[/bold red] critic_repeat_rate > 0.30 "
            "— the spec extractor is likely broken."
        )
        raise SystemExit(1)


@main.command("survey")
@click.argument("workspace_path", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--refresh", is_flag=True, help="Incremental update: re-parse only changed files.")
@click.option("--db", "db_path", default=None, help="Path for survey.db (default: <workspace>/.bob/survey.db).")
def survey_cmd(workspace_path: str, refresh: bool, db_path: str | None) -> None:
    """Build or refresh a brownfield symbol-graph index of WORKSPACE_PATH.

    BF-1: Walks the repo, parses Python source files via AST, stores
    symbols + edges in SQLite (.bob/survey.db), computes PageRank, and
    prints any implicit feature candidates (stub/TODO/notimpl docstrings).

    Use --refresh for incremental update (re-parse only changed files).
    """
    import pathlib as _pathlib
    from bob.brownfield.survey import build_survey, refresh_survey

    workspace = _pathlib.Path(workspace_path).resolve()
    survey_db = _pathlib.Path(db_path).resolve() if db_path else None

    console = Console()
    action = "Refreshing" if refresh else "Building"
    console.print(f"[bold]{action}[/bold] brownfield index for [cyan]{workspace}[/cyan]…")

    fn = refresh_survey if refresh else build_survey
    candidates = fn(workspace, db_path=survey_db)

    if candidates:
        console.print(f"\n[yellow]Implicit feature candidates ({len(candidates)}):[/yellow]")
        table = Table(show_header=True)
        table.add_column("Name")
        table.add_column("Kind")
        table.add_column("Path")
        table.add_column("Line", justify="right")
        for c in candidates:
            table.add_row(c["name"], c["kind"], c["path"], str(c["lineno"]))
        console.print(table)
    else:
        console.print("[dim]No implicit feature candidates found.[/dim]")

    console.print(f"[green]Done.[/green] Survey stored at {survey_db or workspace / '.bob' / 'survey.db'}")


@main.command("extract-from-peas")
@click.argument("peas_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "out_file", default=None, help="Write output YAML to this path (default: stdout).")
@click.option("--workspace", default=".", show_default=True, help="Workspace root for score-gate and synthesizer context.")
@click.option("--threshold", default=0.65, show_default=True, type=float, help="Score-gate threshold (features below this are gate_failed).")
@click.option("--stubs-only", is_flag=True, default=False, help="Parse + stub with TBD ACs only; skip synthesis (let init+sanitize fill ACs against the real project).")
@click.option("--name", "spec_name", default=None, help="Top-level spec name to write into the YAML (needed by bob init).")
def extract_from_peas_cmd(peas_file: str, out_file: str | None, workspace: str, threshold: float, stubs_only: bool, spec_name: str | None) -> None:
    """Parse a PEAS prose spec markdown and produce features.yaml.

    PEAS_FILE is a markdown file with ## headings per feature, a metadata line
    (Tier / Priority / Slot / PermanentForwardCarry), and a prose description.

    Default pipeline: parse -> stub (TBD ACs) -> synthesize -> score-gate.
    With --stubs-only: parse -> stub only (TBD ACs left for init+sanitize).
    """
    import pathlib as _pathlib
    import yaml as _yaml
    from bob.extract_from_peas import run_pipeline, parse_peas_markdown, emit_stub_features

    peas_path = _pathlib.Path(peas_file).resolve()
    out_path = _pathlib.Path(out_file).resolve() if out_file else None
    ws = _pathlib.Path(workspace).resolve()

    console = Console()
    console.print(f"[bold]Extracting[/bold] features from [cyan]{peas_path}[/cyan]…")

    if stubs_only:
        parsed = parse_peas_markdown(peas_path.read_text(encoding="utf-8"))
        stubs = emit_stub_features(parsed)
        spec: dict = {}
        if spec_name:
            spec["name"] = spec_name
        spec["features"] = stubs
        yaml_text = _yaml.safe_dump(spec, sort_keys=False, default_flow_style=False, width=100, allow_unicode=True)
        if out_path:
            out_path.write_text(yaml_text, encoding="utf-8")
        else:
            click.echo(yaml_text)
        console.print(f"[green]extracted[/green]={len(stubs)} (stubs-only; ACs deferred to sanitize)")
        return

    summary = run_pipeline(
        peas_path,
        out_path=out_path,
        threshold=threshold,
        workspace=ws,
    )

    if out_path is None:
        click.echo(summary["yaml_text"])

    console.print(
        f"[green]extracted[/green]={summary['extracted']}  "
        f"[green]synthesized[/green]={summary['synthesized']}  "
        f"[green]gate_passed[/green]={summary['gate_passed']}  "
        f"[yellow]gate_failed[/yellow]={summary['gate_failed']}"
    )
    for pf in summary.get("per_feature", []):
        score_str = f"{pf['score']:.3f}" if pf.get("score") is not None else "n/a"
        console.print(f"  {pf['key']:15s}  score={score_str}  source={pf.get('source', '?')}")


# ============================================================
# EXPLAIN-GATE-BLOCK COMMAND (02785f79)
# ============================================================


@main.command("explain-gate-block")
@click.argument("feature_id_prefix")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON instead of human-readable text.")
@click.option(
    "--workspace",
    default=None,
    type=click.Path(),
    help="Workspace root for reachability checks (default: CWD).",
)
def explain_gate_block_cmd(feature_id_prefix: str, as_json: bool, workspace: str | None) -> None:
    """Surface why a feature failed the spec_quality_gate.

    Loads the feature row from bob.db, re-runs spec quality scoring on its
    current ACs, and prints a sub-dimension breakdown with cheapest-fix hints.

    FEATURE_ID_PREFIX may be the full feature UUID or the first N characters
    (e.g. the first 8). Exits with an error if the prefix is ambiguous or
    matches no feature.

    Use --json for programmatic consumption (same data, machine-readable).
    """
    import json as _json
    import pathlib as _pathlib

    from bob.enhanced_verification import explain_gate_block

    console = Console()
    db_path = get_database_path()
    conn = get_connection(db_path=db_path)

    try:
        rows = conn.execute(
            "SELECT id, name, description, acceptance_criteria FROM features "
            "WHERE id LIKE ?",
            (feature_id_prefix + "%",),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        console.print(
            f"[red]No feature found matching prefix:[/red] {feature_id_prefix!r}",
            err=True,
        )
        raise SystemExit(1)

    if len(rows) > 1:
        console.print(
            f"[red]Ambiguous prefix {feature_id_prefix!r} matches {len(rows)} features:[/red]",
            err=True,
        )
        for row in rows:
            console.print(f"  {row[0]}  {row[1]}", err=True)
        raise SystemExit(1)

    row = rows[0]
    fid, fname, fdesc, fac_raw = row[0], row[1], row[2], row[3]

    ws = _pathlib.Path(workspace) if workspace else None

    result = explain_gate_block(
        feature_id=fid,
        feature_name=fname,
        description=fdesc,
        acceptance_criteria=fac_raw or "[]",
        workspace=ws,
    )

    if as_json:
        click.echo(_json.dumps(result, indent=2))
        return

    # Human-readable output
    score = result["score"]
    threshold = result["threshold"]
    components = result["components"]
    hints = result["remediation_hints"]

    passed_str = "[green]PASSED[/green]" if score >= threshold else "[red]BLOCKED[/red]"
    console.print(f"\n[bold]Feature:[/bold] {fid} ({fname})")
    console.print(f"[bold]Score:[/bold] {score:.4f} (threshold {threshold})  {passed_str}")
    console.print()
    console.print("[bold]Sub-dimension breakdown:[/bold]")
    console.print(f"  ambiguity_score:     {components['ambiguity_score']:.4f}  (weight 0.35)")
    console.print(f"  reachability_score:  {components['reachability_score']:.4f}  (weight 0.25)")
    console.print(f"  ears_score:          {components['ears_score']:.4f}  (weight 0.15)")
    console.print(f"  ac_coverage_score:   {components['ac_coverage_score']:.4f}  (weight 0.25)")

    if hints:
        console.print()
        console.print("[bold]Remediation hints:[/bold]")
        for hint in hints:
            console.print(f"  - {hint}")


# ============================================================
# LINT-SPECS COMMAND (5c8017f9) — spec ambiguity linter
# ============================================================


@main.command("lint-specs")
@click.argument("spec_file", type=click.Path(exists=True, readable=True))
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON instead of human-readable text.")
def lint_specs_cmd(spec_file: str, as_json: bool) -> None:
    """Lint a spec YAML file for ambiguous acceptance criteria.

    Scans every acceptance_criteria entry in SPEC_FILE and rejects
    ambiguous patterns. Each AC must match one of the structured forms:

    \b
      File exists: <path>
      Function defined: <dotted.path>
      Class defined: <dotted.path>
      pytest: <test_path>
      integration: <dotted.module>
      behavior: <subject> <verb> <object> when <condition>

    Exits with code 0 if all features pass, 1 if any feature has an
    ambiguous AC.
    """
    import json as _json
    import pathlib as _pathlib

    import yaml as _yaml

    from bob.spec_quality.ambiguity_linter import lint_spec, SpecLintReport

    console = Console()
    path = _pathlib.Path(spec_file)

    try:
        raw = path.read_text(encoding="utf-8")
        features = _yaml.safe_load(raw)
        if not isinstance(features, list):
            click.echo(f"ERROR: {spec_file!r} must contain a YAML list of features.", err=True)
            raise SystemExit(1)
    except (OSError, _yaml.YAMLError) as exc:
        click.echo(f"ERROR reading {spec_file!r}: {exc}", err=True)
        raise SystemExit(1)

    report: SpecLintReport = lint_spec(features)

    if as_json:
        payload = {
            "passed": report.passed,
            "features": [
                {
                    "feature_name": r.feature_name,
                    "passed": r.passed,
                    "issues": [
                        {
                            "ac_index": i.ac_index,
                            "criterion": i.criterion,
                            "reason": i.reason,
                        }
                        for i in r.issues
                    ],
                }
                for r in report.feature_results
            ],
        }
        click.echo(_json.dumps(payload, indent=2))
        if not report.passed:
            raise SystemExit(1)
        return

    if report.passed:
        console.print("[green]Spec ambiguity lint: PASSED[/green] — all acceptance criteria are structured.")
        return

    console.print("[red]Spec ambiguity lint: FAILED[/red]")
    console.print()
    for result in report.failed_features:
        console.print(f"[bold]Feature:[/bold] {result.feature_name!r}")
        for issue in result.issues:
            console.print(f"  [yellow]AC[{issue.ac_index}][/yellow] {issue.criterion!r}: {issue.reason}")
        console.print()

    raise SystemExit(1)


@main.command("lint-spec")
@click.argument("spec_file", type=click.Path(exists=True, readable=True))
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON instead of human-readable text.")
def lint_spec_cmd(spec_file: str, as_json: bool) -> None:
    """Lint a spec YAML file for ambiguous acceptance criteria (alias for lint-specs)."""
    ctx = click.get_current_context()
    ctx.invoke(lint_specs_cmd, spec_file=spec_file, as_json=as_json)


# ============================================================
# QUALITY-GATE COMMAND GROUP (75a063f0) — mutation testing gate
# ============================================================


@main.group("quality-gate")
def quality_gate_group():
    """Quality-gate commands: run post-impl verification gates."""


@quality_gate_group.command("mutmut")
@click.option("--feature-id", required=True, help="Feature identifier.")
@click.option(
    "--src",
    "src_files",
    multiple=True,
    required=True,
    help="Source file(s) to mutate. Repeat for multiple files.",
)
@click.option("--test-dir", required=True, help="Test directory.")
@click.option(
    "--workspace",
    default=".",
    show_default=True,
    help="Project workspace root.",
)
@click.option(
    "--threshold",
    type=float,
    default=None,
    help="Mutation score threshold (default 0.75).",
)
@click.option(
    "--pytest-passed/--pytest-failed",
    default=True,
    show_default=True,
    help="Whether pytest passed before calling the gate.",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Print result as JSON.",
)
def quality_gate_mutmut(
    feature_id: str,
    src_files: tuple,
    test_dir: str,
    workspace: str,
    threshold,
    pytest_passed: bool,
    json_output: bool,
) -> None:
    """Run the mutmut post-impl quality gate for a feature.

    Mutates the source files and re-runs the test suite. Rejects the
    implementation if mutation_score < threshold (default 0.75). Surviving
    mutants are persisted to runs/<feature>/mutation_report.json.
    """
    import json as _json

    from bob.mutmut_verifier import verify_mutation_score

    try:
        result = verify_mutation_score(
            feature_id=feature_id,
            src_files=list(src_files),
            test_dir=test_dir,
            workspace=workspace,
            pytest_passed=pytest_passed,
            threshold=threshold,
        )
    except (TypeError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(2)

    if result is None:
        msg = "Gate skipped (pytest_passed=False or empty feature_id)."
        if json_output:
            click.echo(_json.dumps({"skipped": True, "reason": msg}))
        else:
            click.echo(msg)
        raise SystemExit(0)

    if json_output:
        click.echo(_json.dumps(result, indent=2))
    else:
        if result.get("skipped"):
            click.echo(f"Gate skipped: {result.get('reason', 'mutmut unavailable')}")
            raise SystemExit(0)

        score = result.get("mutation_score", 0.0)
        passed = result.get("passed", False)
        threshold_used = result.get("threshold", 0.75)

        click.echo(
            f"Mutation score: {score:.3f} | Threshold: {threshold_used} | "
            f"{'PASSED' if passed else 'REJECTED'}"
        )
        if not passed:
            click.echo(
                f"Feature {feature_id!r} rejected: mutation_score {score:.3f} "
                f"< {threshold_used}. See runs/{feature_id}/mutation_report.json."
            )
            raise SystemExit(1)


@main.command("mutation-test")
@click.option("--feature-id", required=True, help="Feature identifier.")
@click.option(
    "--src",
    "src_files",
    multiple=True,
    required=True,
    help="Source file(s) to mutate. Repeat for multiple files.",
)
@click.option("--test-dir", required=True, help="Test directory.")
@click.option(
    "--workspace",
    default=".",
    show_default=True,
    help="Project workspace root.",
)
@click.option(
    "--threshold",
    type=float,
    default=None,
    help="Mutation score threshold (default 0.75).",
)
@click.option(
    "--pytest-passed/--pytest-failed",
    default=True,
    show_default=True,
    help="Whether pytest passed before calling the gate.",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Print result as JSON.",
)
def mutation_test_cmd(
    feature_id: str,
    src_files: tuple,
    test_dir: str,
    workspace: str,
    threshold,
    pytest_passed: bool,
    json_output: bool,
) -> None:
    """Run the mutmut post-impl quality gate for a feature.

    Mutates the source files and re-runs the test suite. Rejects the
    implementation if mutation_score < threshold (default 0.75). Surviving
    mutants are persisted to runs/<feature>/mutation_report.json.
    """
    import json as _json

    from bob.mutation_testing import run_mutation_tests

    try:
        result = run_mutation_tests(
            feature_id=feature_id,
            src_files=list(src_files),
            test_dir=test_dir,
            workspace=workspace,
            pytest_passed=pytest_passed,
            threshold=threshold,
        )
    except (TypeError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(2)

    if result is None:
        msg = "Gate skipped (pytest_passed=False or empty feature_id)."
        if json_output:
            click.echo(_json.dumps({"skipped": True, "reason": msg}))
        else:
            click.echo(msg)
        raise SystemExit(0)

    if json_output:
        click.echo(_json.dumps(result, indent=2))
    else:
        if result.get("skipped"):
            click.echo(f"Gate skipped: {result.get('reason', 'mutmut unavailable')}")
            raise SystemExit(0)

        score = result.get("mutation_score", 0.0)
        passed = result.get("passed", False)
        threshold_used = result.get("threshold", 0.75)

        click.echo(
            f"Mutation score: {score:.3f} | Threshold: {threshold_used} | "
            f"{'PASSED' if passed else 'REJECTED'}"
        )
        if not passed:
            click.echo(
                f"Feature {feature_id!r} rejected: mutation_score {score:.3f} "
                f"< {threshold_used}. See runs/{feature_id}/mutation_report.json."
            )
            raise SystemExit(1)


@main.group("watchdog")
def watchdog_group():
    """Watchdog commands: stall detection and escalation."""


@watchdog_group.command("escalate-stall")
@click.option(
    "--observation-count",
    type=int,
    required=True,
    help="Number of consecutive spec_gate_stall_observed events.",
)
@click.option(
    "--marker-path",
    default=None,
    help="Path for HALT_ATTENTION marker file (default: bob4/tools/STALL_ATTENTION.txt).",
)
@click.option("--json-output", is_flag=True, default=False, help="Print result as JSON.")
def watchdog_escalate_stall(observation_count: int, marker_path: str | None, json_output: bool) -> None:
    """Escalate repeated spec_gate_stall_observed events to a needs_human_attention sentinel.

    After observation_count reaches BOB_STALL_ESCALATION_COUNT (default 5):
    writes a HALT_ATTENTION marker file and logs a chain_dead_locked WARN event.
    """
    import json as _json
    from pathlib import Path

    from bob.watchdog import escalate_stall_observation

    try:
        result = escalate_stall_observation(
            observation_count=observation_count,
            marker_path=Path(marker_path) if marker_path else None,
        )
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(2)

    if json_output:
        click.echo(_json.dumps(result, indent=2))
    else:
        if result["escalated"]:
            click.echo(
                f"ESCALATED: chain_dead_locked after {observation_count} observations "
                f"(threshold={result['threshold']}). Marker written: {result['marker_path']}"
            )
        else:
            click.echo(
                f"No escalation: {observation_count} observations < threshold {result['threshold']}."
            )


# ---------------------------------------------------------------------------
# verify group — AC: CLI command: verify mutmut
# ---------------------------------------------------------------------------


@main.group("verify")
def verify_group():
    """Verification sub-commands."""


@verify_group.command("mutmut")
@click.option("--feature-id", required=True, help="Feature identifier.")
@click.option(
    "--src",
    "src_files",
    multiple=True,
    help="Source files to mutate (may be specified multiple times).",
)
@click.option("--test-dir", default="tests", show_default=True, help="Test directory.")
@click.option("--workspace", default=".", show_default=True, help="Workspace root.")
@click.option(
    "--threshold",
    type=float,
    default=None,
    help="Mutation-score threshold (default 0.75).",
)
@click.option(
    "--pytest-passed/--no-pytest-passed",
    default=True,
    show_default=True,
    help="Whether pytest already passed.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Print result as JSON.",
)
def verify_mutmut_cmd(
    feature_id: str,
    src_files: tuple,
    test_dir: str,
    workspace: str,
    threshold,
    pytest_passed: bool,
    json_output: bool,
) -> None:
    """Run the mutmut post-impl quality gate for a feature.

    Mutates the source files and re-runs the test suite. Rejects the
    implementation if mutation_score < threshold (default 0.75). Surviving
    mutants are persisted to runs/<feature>/mutation_report.json.
    """
    import json as _json

    from bob.mutmut_gate import run_mutation_tests

    try:
        result = run_mutation_tests(
            feature_id=feature_id,
            src_files=list(src_files),
            test_dir=test_dir,
            workspace=workspace,
            pytest_passed=pytest_passed,
            threshold=threshold,
        )
    except (TypeError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(2)

    if result is None:
        msg = "Gate skipped (pytest_passed=False or empty feature_id)."
        if json_output:
            click.echo(_json.dumps({"skipped": True, "reason": msg}))
        else:
            click.echo(msg)
        raise SystemExit(0)

    if json_output:
        click.echo(_json.dumps(result, indent=2))
    else:
        if result.get("skipped"):
            click.echo(f"Gate skipped: {result.get('reason', 'mutmut unavailable')}")
            raise SystemExit(0)

        score = result.get("mutation_score", 0.0)
        passed = result.get("passed", False)
        threshold_used = result.get("threshold", 0.75)

        click.echo(
            f"Mutation score: {score:.3f} | Threshold: {threshold_used} | "
            f"{'PASSED' if passed else 'REJECTED'}"
        )
        if not passed:
            click.echo(
                f"Feature {feature_id!r} rejected: mutation_score {score:.3f} "
                f"< {threshold_used}. See runs/{feature_id}/mutation_report.json."
            )
            raise SystemExit(1)


# Proposal-only task-packet compilation/review live in a separate module so
# their strict model schemas cannot be confused with Bob's legacy feature YAML
# parser.  Registration adds commands without changing existing entry points.
from bob.atomic_packet_planner import (  # noqa: E402
    propose_task_packets_command,
    review_task_packets_command,
)

main.add_command(propose_task_packets_command)
main.add_command(review_task_packets_command)
