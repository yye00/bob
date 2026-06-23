"""A/B comparison CLI for bob3.

Compares two sub_agent_runs side-by-side across key telemetry dimensions:
- cost (total and average per run)
- success rate
- calibration ECE
- hack detection rate
- per-feature outcomes

Usage:
    python -m bob3.a_b_comparison_cli --run-a <id> --run-b <id>

Or programmatically:
    from bob3.a_b_comparison_cli import compare_runs
    print(compare_runs("run-a-uuid", "run-b-uuid"))
"""
from __future__ import annotations

import sqlite3
from typing import Any


_DEFAULT_DB_PATH = "bob3.db"


class RunNotFoundError(ValueError):
    """Raised when a requested run ID does not exist in the database."""


def load_run_telemetry(run_id: str, db_path: str = _DEFAULT_DB_PATH) -> dict[str, Any] | None:
    """Load raw telemetry for a single sub_agent_run by ID.

    Returns a dict with run fields, or None if not found.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM sub_agent_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def _load_feature_hack_status(feature_ids: list[str], conn: sqlite3.Connection) -> dict[str, bool]:
    """Return a mapping of feature_id -> is_hacking for the given feature IDs."""
    if not feature_ids:
        return {}
    placeholders = ",".join("?" * len(feature_ids))
    rows = conn.execute(
        f"SELECT feature_id, verdict FROM reward_hacking_verdicts WHERE feature_id IN ({placeholders})",
        feature_ids,
    ).fetchall()
    return {r[0]: r[1] == "hacking" for r in rows}


def compute_run_stats(
    run_ids: list[str],
    db_path: str = _DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Aggregate telemetry statistics across a list of sub_agent_run IDs.

    Returns a dict with:
        run_count, success_rate, total_cost_usd, avg_cost_usd,
        hack_detection_rate, calibration_ece, per_feature_outcomes
    """
    if not run_ids:
        return {
            "run_count": 0,
            "success_rate": 0.0,
            "total_cost_usd": 0.0,
            "avg_cost_usd": 0.0,
            "hack_detection_rate": 0.0,
            "calibration_ece": None,
            "per_feature_outcomes": {},
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" * len(run_ids))
        rows = conn.execute(
            f"SELECT id, target_id, status, cost_usd, duration_ms FROM sub_agent_runs WHERE id IN ({placeholders})",
            run_ids,
        ).fetchall()

        total = len(rows)
        successes = sum(1 for r in rows if r["status"] == "completed")
        costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
        total_cost = sum(costs)
        avg_cost = total_cost / len(costs) if costs else 0.0

        feature_ids = [r["target_id"] for r in rows if r["target_id"]]
        hack_status = _load_feature_hack_status(feature_ids, conn)
        hacked = sum(1 for fid in feature_ids if hack_status.get(fid, False))
        hack_rate = hacked / len(feature_ids) if feature_ids else 0.0

        per_feature: dict[str, str] = {}
        for r in rows:
            fid = r["target_id"]
            if fid:
                per_feature[fid] = r["status"]

        ece = _compute_calibration_ece(conn)

    finally:
        conn.close()

    return {
        "run_count": total,
        "success_rate": successes / total if total else 0.0,
        "total_cost_usd": total_cost,
        "avg_cost_usd": avg_cost,
        "hack_detection_rate": hack_rate,
        "calibration_ece": ece,
        "per_feature_outcomes": per_feature,
    }


def _compute_calibration_ece(conn: sqlite3.Connection) -> float | None:
    """Compute overall ECE from the calibration_data table.

    ECE = mean(|expected_pass_rate - empirical_pass_rate|) over all buckets
    that have at least one attempt.
    """
    rows = conn.execute(
        "SELECT expected_pass_rate, empirical_pass_rate, total_attempts FROM calibration_data"
    ).fetchall()
    valid = [
        abs(r[0] - r[1])
        for r in rows
        if r[0] is not None and r[1] is not None and r[2] and r[2] > 0
    ]
    if not valid:
        return None
    return sum(valid) / len(valid)


def format_comparison(
    stats_a: dict[str, Any],
    stats_b: dict[str, Any],
) -> str:
    """Render a side-by-side comparison table for two run stat dicts."""
    run_a = stats_a.get("run_id", "A")
    run_b = stats_b.get("run_id", "B")

    col_w = max(len(run_a), len(run_b), 20)
    label_w = 26

    def _fmt(val: Any, is_pct: bool = False) -> str:
        if val is None:
            return "N/A"
        if is_pct:
            return f"{val * 100:.1f}%"
        if isinstance(val, float):
            return f"{val:.4f}"
        return str(val)

    def _row(label: str, a: Any, b: Any, is_pct: bool = False) -> str:
        fa = _fmt(a, is_pct)
        fb = _fmt(b, is_pct)
        return f"  {label:<{label_w}}  {fa:<{col_w}}  {fb:<{col_w}}"

    header_line = f"  {'Metric':<{label_w}}  {run_a:<{col_w}}  {run_b:<{col_w}}"
    sep = "  " + "-" * (label_w + 2 + col_w * 2 + 2)

    lines = [
        "=" * (label_w + col_w * 2 + 8),
        "A/B Telemetry Comparison",
        "=" * (label_w + col_w * 2 + 8),
        header_line,
        sep,
        _row("Run count", stats_a["run_count"], stats_b["run_count"]),
        _row("Success rate", stats_a["success_rate"], stats_b["success_rate"], is_pct=True),
        _row("Total cost (USD)", stats_a["total_cost_usd"], stats_b["total_cost_usd"]),
        _row("Avg cost / run (USD)", stats_a["avg_cost_usd"], stats_b["avg_cost_usd"]),
        _row("Hack detection rate", stats_a["hack_detection_rate"], stats_b["hack_detection_rate"], is_pct=True),
        _row("Calibration ECE", stats_a.get("calibration_ece"), stats_b.get("calibration_ece")),
        sep,
    ]

    # Per-feature outcomes section
    all_features = sorted(
        set(stats_a["per_feature_outcomes"]) | set(stats_b["per_feature_outcomes"])
    )
    if all_features:
        lines.append(f"  {'Per-feature outcomes':}")
        lines.append(sep)
        for fid in all_features:
            a_outcome = stats_a["per_feature_outcomes"].get(fid, "—")
            b_outcome = stats_b["per_feature_outcomes"].get(fid, "—")
            lines.append(_row(fid[:label_w], a_outcome, b_outcome))

    return "\n".join(lines)


def compare_runs(
    run_a_id: str,
    run_b_id: str,
    db_path: str = _DEFAULT_DB_PATH,
) -> str:
    """Compare two sub_agent_runs and return a formatted side-by-side report.

    Args:
        run_a_id: ID of run A (the baseline or control).
        run_b_id: ID of run B (the variant or treatment).
        db_path: Path to the bob3.db SQLite database.

    Returns:
        Multi-line string with side-by-side telemetry comparison.

    Raises:
        RunNotFoundError: If either run ID is not found in the database.
    """
    telem_a = load_run_telemetry(run_a_id, db_path=db_path)
    if telem_a is None:
        raise RunNotFoundError(f"Run not found: {run_a_id!r}")

    telem_b = load_run_telemetry(run_b_id, db_path=db_path)
    if telem_b is None:
        raise RunNotFoundError(f"Run not found: {run_b_id!r}")

    stats_a = compute_run_stats([run_a_id], db_path=db_path)
    stats_a["run_id"] = run_a_id

    stats_b = compute_run_stats([run_b_id], db_path=db_path)
    stats_b["run_id"] = run_b_id

    return format_comparison(stats_a, stats_b)


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Side-by-side A/B telemetry comparison for two bob3 runs."
    )
    parser.add_argument("--run-a", required=True, metavar="ID", help="Run A ID (baseline)")
    parser.add_argument("--run-b", required=True, metavar="ID", help="Run B ID (variant)")
    parser.add_argument("--db", default=_DEFAULT_DB_PATH, metavar="PATH", help="Path to bob3.db")
    args = parser.parse_args()

    try:
        output = compare_runs(args.run_a, args.run_b, db_path=args.db)
        print(output)
    except RunNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
