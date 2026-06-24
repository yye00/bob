"""Reproducibility bundle exporter for Bob3.

Exports a self-contained tarball for a given run-id containing:
  - spec.yaml      — the project spec at time of run
  - transcript.txt — the agent run summary / result
  - diff.patch     — git diff captured from the run's evidence artifacts
  - telemetry.jsonl — matching telemetry lines for the run
  - env_lockfile.txt — Python package versions for environment reproducibility

The bundle is designed to be self-contained: an operator can unpack it,
inspect all artifacts, and re-run verification without needing the
original database or workspace.
"""

import importlib.metadata
import json
import pathlib
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from typing import Any

from bob3.db import get_connection, get_database_path


def _get_env_lockfile() -> str:
    """Return a pip freeze-style listing of installed packages."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    # Fallback: use importlib.metadata to list installed packages
    lines = []
    try:
        for dist in sorted(
            importlib.metadata.distributions(),
            key=lambda d: d.metadata["Name"].lower(),
        ):
            name = dist.metadata["Name"]
            version = dist.metadata["Version"]
            lines.append(f"{name}=={version}")
    except Exception:
        lines.append("# Could not enumerate packages")
    return "\n".join(lines)


def _get_telemetry_lines(run_id: str, run_jsonl_path: pathlib.Path) -> str:
    """Extract telemetry lines matching run_id from run.jsonl."""
    if not run_jsonl_path.exists():
        return ""
    matched = []
    try:
        with run_jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("run_id") == run_id or record.get("feature_id") == run_id:
                        matched.append(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return "\n".join(matched)


def _get_spec_content(conn: sqlite3.Connection) -> str:
    """Return the project spec YAML content, or an empty string if unavailable."""
    try:
        row = conn.execute("SELECT spec_path FROM projects LIMIT 1").fetchone()
        if row and row[0]:
            spec_path = pathlib.Path(row[0])
            if spec_path.exists():
                return spec_path.read_text(encoding="utf-8")
    except (sqlite3.Error, OSError):
        pass
    return ""


def _get_agent_run_transcript(conn: sqlite3.Connection, run_id: str) -> str:
    """Return the transcript/summary for the agent run."""
    lines = []
    try:
        row = conn.execute(
            "SELECT id, purpose, target_id, status, prompt_summary, result_summary, "
            "cost_usd, duration_ms, created_at, completed_at "
            "FROM sub_agent_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row:
            lines.append(f"Run ID: {row[0]}")
            lines.append(f"Purpose: {row[1]}")
            lines.append(f"Target ID: {row[2]}")
            lines.append(f"Status: {row[3]}")
            lines.append(f"Created: {row[8]}")
            lines.append(f"Completed: {row[9]}")
            lines.append(f"Cost USD: {row[6]}")
            lines.append(f"Duration ms: {row[7]}")
            lines.append("")
            if row[4]:
                lines.append("--- Prompt Summary ---")
                lines.append(row[4])
                lines.append("")
            if row[5]:
                lines.append("--- Result Summary ---")
                lines.append(row[5])
                lines.append("")
    except sqlite3.Error:
        pass

    # Collect execution log lines for this run
    try:
        log_rows = conn.execute(
            "SELECT level, event, details, created_at FROM execution_logs "
            "WHERE sub_agent_run_id = ? ORDER BY created_at ASC",
            (run_id,),
        ).fetchall()
        if log_rows:
            lines.append("--- Execution Logs ---")
            for log_row in log_rows:
                lines.append(f"[{log_row[3]}] {log_row[0].upper()} {log_row[1]}: {log_row[2] or ''}")
    except sqlite3.Error:
        pass

    return "\n".join(lines) if lines else ""


def _get_diff_content(conn: sqlite3.Connection, run_id: str) -> str:
    """Return git diff content from evidence artifacts for the run."""
    # Try to find diff artifacts in evidence_artifacts
    diff_content = ""
    try:
        # Look for diff-type evidence associated with the run's target feature
        target_row = conn.execute(
            "SELECT target_id FROM sub_agent_runs WHERE id = ?", (run_id,)
        ).fetchone()
        feature_id = target_row[0] if target_row else None

        if feature_id:
            rows = conn.execute(
                "SELECT content FROM evidence_artifacts "
                "WHERE feature_id = ? AND type IN ('diff', 'git_diff', 'patch') "
                "ORDER BY created_at DESC LIMIT 1",
                (feature_id,),
            ).fetchall()
            if rows:
                diff_content = rows[0][0] or ""
    except sqlite3.Error:
        pass

    if diff_content:
        return diff_content

    # Fallback: try to get current git diff from workspace
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    return ""


def _lookup_run_by_feature(conn: sqlite3.Connection, feature_id: str) -> str | None:
    """Find the most recent sub_agent_run ID for a given feature_id."""
    try:
        row = conn.execute(
            "SELECT id FROM sub_agent_runs WHERE target_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (feature_id,),
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def create_bundle(
    run_id: str,
    output_dir: pathlib.Path | None = None,
    run_jsonl_path: pathlib.Path | None = None,
) -> pathlib.Path:
    """Create a reproducibility bundle tarball for the given run_id.

    Args:
        run_id: The sub_agent_run ID (or feature ID — in that case the most
            recent agent run for that feature is used).
        output_dir: Directory to write the bundle into. Defaults to the
            current working directory.
        run_jsonl_path: Path to run.jsonl for telemetry extraction.
            Defaults to .bob3/run.jsonl in the current working directory.

    Returns:
        Path to the created tarball file.

    Raises:
        ValueError: If the run_id is not found in the database.
        OSError: If the bundle cannot be written.
    """
    if output_dir is None:
        output_dir = pathlib.Path.cwd()
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if run_jsonl_path is None:
        run_jsonl_path = pathlib.Path(".bob3") / "run.jsonl"

    db_path = get_database_path()
    conn = get_connection(db_path=db_path)

    try:
        # Check if run_id is a sub_agent_run ID directly
        agent_row = conn.execute(
            "SELECT id FROM sub_agent_runs WHERE id = ?", (run_id,)
        ).fetchone()

        resolved_run_id = run_id
        if agent_row is None:
            # Try treating run_id as a feature_id and find the most recent run
            resolved_run_id = _lookup_run_by_feature(conn, run_id)
            if resolved_run_id is None:
                raise ValueError(
                    f"run-id '{run_id}' not found as a sub_agent_run or feature ID"
                )

        # Collect all bundle components
        spec_content = _get_spec_content(conn)
        transcript = _get_agent_run_transcript(conn, resolved_run_id)
        diff_content = _get_diff_content(conn, resolved_run_id)
        telemetry = _get_telemetry_lines(resolved_run_id, run_jsonl_path)
        env_lock = _get_env_lockfile()
    finally:
        conn.close()

    # Build the bundle name
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_name = f"bundle_{resolved_run_id[:8]}_{ts}.tar.gz"
    bundle_path = output_dir / bundle_name

    # Write all files into a temporary directory, then tar it
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir) / f"bundle_{resolved_run_id[:8]}"
        tmp.mkdir()

        # Write bundle manifest
        manifest: dict[str, Any] = {
            "bundle_version": "1",
            "run_id": resolved_run_id,
            "original_run_id_arg": run_id,
            "created_at": ts,
            "python_version": sys.version,
            "files": ["manifest.json", "spec.yaml", "transcript.txt", "diff.patch",
                      "telemetry.jsonl", "env_lockfile.txt"],
        }
        (tmp / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        # Write each component
        (tmp / "spec.yaml").write_text(spec_content, encoding="utf-8")
        (tmp / "transcript.txt").write_text(transcript, encoding="utf-8")
        (tmp / "diff.patch").write_text(diff_content, encoding="utf-8")
        (tmp / "telemetry.jsonl").write_text(telemetry, encoding="utf-8")
        (tmp / "env_lockfile.txt").write_text(env_lock, encoding="utf-8")

        # Create the tarball
        with tarfile.open(bundle_path, "w:gz") as tar:
            tar.add(tmp, arcname=f"bundle_{resolved_run_id[:8]}")

    return bundle_path
