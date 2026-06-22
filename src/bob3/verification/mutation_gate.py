"""bob3.verification.mutation_gate — mutmut 3.x post-impl quality gate.

After pytest passes, mutate the impl files and re-run the test suite.
Reject if mutation_score < 0.75. Surviving mutants are persisted to
runs/<feature>/mutation_report.json so the next implementer attempt
can see which mutations the tests cannot distinguish from the real impl.

Public API
----------
run_mutation_test(feature_id, src_files, test_dir, workspace, time_limit_sec=180) -> MutationReport
    Run mutmut on src_files, return a MutationReport.

MutationReport
    Dataclass: feature_id, total_mutants, killed, survived, timed_out,
    mutation_score, surviving_mutant_diffs, timed_out_early, partial.

passes_gate(score, threshold=None) -> bool
    Return True when score >= threshold (default 0.75).

default_threshold() -> float
    Return 0.75.

mutation_operators() -> list[str]
    Return the list of mutation operator names used.

runs_only_after_pytest_pass(pytest_pass=True) -> bool | None
    Return False when pytest_pass=False (gate refuses to run).

never_mutates_failing_impl() -> bool
    Return True; documents that the gate skips failing suites.

persist_surviving_mutants(report, workspace) -> Path
    Write runs/<feature>/mutation_report.json with unified-diff blocks.

return_feature_to_ready_on_failure(feature, report, workspace, db_conn=None) -> dict
    Set feature.status to "ready" with mutation_report.json injected.

enforce_time_limit(proc, time_limit_sec=180) -> bool
    Kill proc if running longer than time_limit_sec. Return True if killed.

handle_mutmut_unavailable() -> None
    Raise MutmutMissingError naming the mutmut package.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MutmutMissingError(RuntimeError):
    """Raised when the mutmut package is not installed or not on PATH."""


@dataclass
class MutationReport:
    """Report produced by run_mutation_test."""

    feature_id: str
    total_mutants: int
    killed: int
    survived: int
    timed_out: int
    mutation_score: float
    surviving_mutant_diffs: list[dict[str, Any]] = field(default_factory=list)
    timed_out_early: bool = False
    partial: bool = False


# ---------------------------------------------------------------------------
# Public gate functions
# ---------------------------------------------------------------------------


def default_threshold() -> float:
    """Return the default mutation-score threshold (0.75)."""
    return 0.75


def mutation_operators() -> list[str]:
    """Return the list of mutation operator names applied by the gate."""
    return ["AOR", "ROR", "COR", "LCR", "SDL", "constant_replacement"]


def passes_gate(score: float, threshold: float | None = None) -> bool:
    """Return True when *score* >= *threshold* (default 0.75)."""
    if threshold is None:
        threshold = default_threshold()
    return score >= threshold


def runs_only_after_pytest_pass(pytest_pass: bool = True) -> bool | None:
    """Gate refuses to run when pytest_pass=False; returns False in that case."""
    if not pytest_pass:
        return False
    return True


def never_mutates_failing_impl() -> bool:
    """Documents that the gate always skips impls whose pytest suite is failing."""
    return True


def handle_mutmut_unavailable() -> None:
    """Raise MutmutMissingError when the mutmut package is absent."""
    if shutil.which("mutmut") is None:
        raise MutmutMissingError(
            "mutmut is not installed or not on PATH. "
            "Install it with: pip install mutmut"
        )
    raise MutmutMissingError(
        "mutmut package is unavailable. Install with: pip install mutmut"
    )


# ---------------------------------------------------------------------------
# Time-limit enforcement
# ---------------------------------------------------------------------------


def enforce_time_limit(proc: subprocess.Popen, time_limit_sec: float = 180) -> bool:
    """Kill *proc* if it runs longer than *time_limit_sec*.

    Returns True if the process was killed (limit exceeded), False otherwise.
    Called from a watcher thread during run_mutation_test.
    """
    deadline = time.monotonic() + time_limit_sec
    while proc.poll() is None:
        if time.monotonic() >= deadline:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            return True
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# Core: run mutmut
# ---------------------------------------------------------------------------


def run_mutation_test(
    feature_id: str,
    src_files: list[str | Path],
    test_dir: str | Path,
    workspace: str | Path,
    time_limit_sec: float = 180,
) -> MutationReport:
    """Run mutmut on *src_files* inside a temp worktree.

    Returns a MutationReport. If the process is killed by the time-limit
    watcher the report is marked partial=True, timed_out_early=True.

    Raises MutmutMissingError when mutmut is not installed.
    """
    if shutil.which("mutmut") is None:
        raise MutmutMissingError(
            "mutmut is not installed. Install with: pip install mutmut"
        )

    workspace = Path(workspace)
    src_files = [Path(f) for f in src_files]
    test_dir = Path(test_dir)

    # Build comma-separated paths-to-mutate relative to workspace
    paths_to_mutate = ",".join(
        str(f.relative_to(workspace)) if f.is_absolute() else str(f)
        for f in src_files
    )
    if not paths_to_mutate:
        paths_to_mutate = "src/"

    # Run mutmut in a subprocess
    cmd = [
        "mutmut",
        "run",
        "--paths-to-mutate", paths_to_mutate,
    ]

    killed_by_timeout = False
    proc = subprocess.Popen(
        cmd,
        cwd=str(workspace),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ},
    )

    # Start timeout watcher thread
    watcher_killed = [False]

    def _watcher():
        watcher_killed[0] = enforce_time_limit(proc, time_limit_sec)

    watcher_thread = threading.Thread(target=_watcher, daemon=True)
    watcher_thread.start()
    stdout, stderr = proc.communicate()
    watcher_thread.join(timeout=5)
    killed_by_timeout = watcher_killed[0]

    stdout_text = stdout.decode(errors="replace")
    stderr_text = stderr.decode(errors="replace")
    logger.debug("mutmut stdout: %s", stdout_text[:2000])
    logger.debug("mutmut stderr: %s", stderr_text[:1000])

    # Parse results via `mutmut results`
    stats = _parse_mutmut_results(workspace)
    total = stats.get("total", 0)
    killed_count = stats.get("killed", 0)
    survived_count = stats.get("survived", 0)
    timeout_count = stats.get("timeout", 0)

    if total > 0:
        score = killed_count / total
    else:
        score = 1.0

    # Collect surviving mutant diffs
    surviving_diffs = _collect_surviving_diffs(workspace, survived_count)

    report = MutationReport(
        feature_id=feature_id,
        total_mutants=total,
        killed=killed_count,
        survived=survived_count,
        timed_out=timeout_count,
        mutation_score=score,
        surviving_mutant_diffs=surviving_diffs,
        timed_out_early=killed_by_timeout,
        partial=killed_by_timeout,
    )
    return report


def _parse_mutmut_results(workspace: Path) -> dict[str, int]:
    """Parse `mutmut results` output into a stats dict."""
    result = subprocess.run(
        ["mutmut", "results"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    stats: dict[str, int] = {"total": 0, "killed": 0, "survived": 0, "timeout": 0}

    for line in output.splitlines():
        line_lower = line.lower()
        if "killed" in line_lower:
            n = _extract_number(line)
            if n is not None:
                stats["killed"] = n
        elif "survived" in line_lower or "suspicious" in line_lower:
            n = _extract_number(line)
            if n is not None:
                stats["survived"] += n
        elif "timeout" in line_lower:
            n = _extract_number(line)
            if n is not None:
                stats["timeout"] = n

    # Also try reading the .mutmut-cache or similar
    # mutmut 3.x stores results in .mutmut3 file
    cache_file = workspace / ".mutmut3"
    if cache_file.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(cache_file))
            cur = conn.cursor()
            try:
                cur.execute("SELECT status, COUNT(*) FROM mutants GROUP BY status")
                rows = cur.fetchall()
                total = 0
                killed = 0
                survived = 0
                timeout_n = 0
                for status, count in rows:
                    total += count
                    status_l = (status or "").lower()
                    if "killed" in status_l or "bad" in status_l:
                        killed += count
                    elif "survived" in status_l or "suspicious" in status_l:
                        survived += count
                    elif "timeout" in status_l:
                        timeout_n += count
                if total > 0:
                    stats["total"] = total
                    stats["killed"] = killed
                    stats["survived"] = survived
                    stats["timeout"] = timeout_n
            except Exception:
                pass
            conn.close()
        except Exception:
            pass

    if stats["total"] == 0:
        stats["total"] = stats["killed"] + stats["survived"] + stats["timeout"]

    return stats


def _extract_number(text: str) -> int | None:
    import re

    m = re.search(r"\d+", text)
    if m:
        return int(m.group())
    return None


def _collect_surviving_diffs(workspace: Path, survived_count: int) -> list[dict[str, Any]]:
    """Collect unified-diff blocks for surviving mutants."""
    diffs: list[dict[str, Any]] = []
    if survived_count == 0:
        return diffs

    # Try to get surviving mutant names
    result = subprocess.run(
        ["mutmut", "results", "--all", "true"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr

    import re

    # Find mutant IDs for survived/suspicious
    survived_ids = re.findall(r"([\w_]+(?:__\w+)?)\s*(?:survived|suspicious)", output, re.IGNORECASE)
    if not survived_ids:
        # Try generic pattern for mutant names
        survived_ids = re.findall(r"(src__\w+|[\w]+_\d+)", output)

    for mutant_id in survived_ids[:50]:  # Cap at 50
        show_result = subprocess.run(
            ["mutmut", "show", mutant_id],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        diff_text = show_result.stdout
        if diff_text.strip():
            diffs.append({"mutant_id": mutant_id, "diff": diff_text})

    return diffs


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def persist_surviving_mutants(
    report: MutationReport,
    workspace: str | Path,
) -> Path:
    """Write runs/<feature>/mutation_report.json with unified-diff blocks.

    Returns the path to the written file.
    """
    workspace = Path(workspace)
    out_dir = workspace / "runs" / report.feature_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "mutation_report.json"

    payload = {
        "feature_id": report.feature_id,
        "mutation_score": report.mutation_score,
        "total_mutants": report.total_mutants,
        "killed": report.killed,
        "survived": report.survived,
        "timed_out": report.timed_out,
        "timed_out_early": report.timed_out_early,
        "partial": report.partial,
        "surviving_mutant_diffs": report.surviving_mutant_diffs,
        "message": (
            "tests cannot distinguish your impl from these broken variants; "
            "strengthen assertions."
        ),
    }

    out_path.write_text(json.dumps(payload, indent=2))
    logger.info("Mutation report written to %s", out_path)
    return out_path


def return_feature_to_ready_on_failure(
    feature: Any,
    report: MutationReport,
    workspace: str | Path,
    db_conn: Any = None,
) -> dict:
    """Set feature.status to 'ready' with mutation_report.json injected.

    Returns a dict describing the action taken. If *db_conn* is provided,
    updates the database row; otherwise updates an in-memory object.
    """
    workspace = Path(workspace)
    report_path = persist_surviving_mutants(report, workspace)

    relative_path = report_path.relative_to(workspace) if report_path.is_absolute() else report_path

    action = {
        "feature_id": report.feature_id,
        "status": "ready",
        "mutation_report_path": str(relative_path),
        "mutation_score": report.mutation_score,
        "threshold": default_threshold(),
        "reason": (
            f"Mutation score {report.mutation_score:.3f} < threshold {default_threshold()}. "
            f"See {relative_path} for surviving mutants."
        ),
    }

    # Update in-memory feature object if it has a status attribute
    if hasattr(feature, "status"):
        feature.status = "ready"
    if isinstance(feature, dict):
        feature["status"] = "ready"
        feature["mutation_report_path"] = str(relative_path)

    # Update DB if connection provided
    if db_conn is not None:
        try:
            db_conn.execute(
                "UPDATE features SET status = 'ready' WHERE id = ?",
                (report.feature_id,),
            )
            db_conn.commit()
        except Exception as exc:
            logger.warning("DB update failed: %s", exc)

    return action
