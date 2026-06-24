"""Tests for A/B comparison CLI (feature 0e83f503-66c6-4305-bbeb-0294986d046b).

Acceptance criteria:
- File exists: src/bob/a_b_comparison_cli.py
- pytest: tests/test_a_b_comparison_cli.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(path: Path, runs: list[dict], features: list[dict] | None = None) -> None:
    """Create a minimal SQLite DB with sub_agent_runs and related tables."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sub_agent_runs (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            parent_run_id TEXT,
            purpose TEXT,
            target_type TEXT,
            target_id TEXT,
            status TEXT DEFAULT 'running',
            prompt_summary TEXT,
            result_summary TEXT,
            tokens_in INTEGER,
            tokens_out INTEGER,
            cost_usd REAL,
            duration_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS features (
            id TEXT PRIMARY KEY,
            name TEXT,
            status TEXT DEFAULT 'pending',
            refinement_attempts INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reward_hacking_verdicts (
            id TEXT PRIMARY KEY,
            feature_id TEXT,
            verdict TEXT,
            overall_score REAL,
            attack_vectors TEXT,
            reasoning TEXT,
            confidence REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibration_data (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            task_class TEXT,
            confidence_bucket TEXT,
            total_attempts INTEGER DEFAULT 0,
            total_passes INTEGER DEFAULT 0,
            total_failures INTEGER DEFAULT 0,
            empirical_pass_rate REAL,
            expected_pass_rate REAL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    for run in runs:
        conn.execute(
            """INSERT INTO sub_agent_runs
               (id, project_id, purpose, target_type, target_id, status,
                cost_usd, duration_ms, tokens_in, tokens_out)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run["id"],
                run.get("project_id", "proj-1"),
                run.get("purpose", "implement_feature"),
                run.get("target_type", "feature"),
                run.get("target_id", "feat-1"),
                run.get("status", "completed"),
                run.get("cost_usd"),
                run.get("duration_ms"),
                run.get("tokens_in"),
                run.get("tokens_out"),
            ),
        )

    for feat in (features or []):
        conn.execute(
            "INSERT INTO features (id, name, status, refinement_attempts) VALUES (?, ?, ?, ?)",
            (feat["id"], feat.get("name", ""), feat.get("status", "completed"), feat.get("refinement_attempts", 0)),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


def test_module_importable():
    from bob.a_b_comparison_cli import compare_runs
    assert callable(compare_runs)


def test_run_telemetry_importable():
    from bob.a_b_comparison_cli import load_run_telemetry
    assert callable(load_run_telemetry)


def test_format_comparison_importable():
    from bob.a_b_comparison_cli import format_comparison
    assert callable(format_comparison)


# ---------------------------------------------------------------------------
# load_run_telemetry
# ---------------------------------------------------------------------------


def test_load_run_telemetry_basic(tmp_path):
    from bob.a_b_comparison_cli import load_run_telemetry

    db = tmp_path / "bob.db"
    _make_db(db, runs=[
        {"id": "run-a", "cost_usd": 1.5, "duration_ms": 10000, "status": "completed"},
    ])
    result = load_run_telemetry("run-a", db_path=str(db))
    assert result["id"] == "run-a"
    assert result["cost_usd"] == pytest.approx(1.5)
    assert result["duration_ms"] == 10000
    assert result["status"] == "completed"


def test_load_run_telemetry_missing_returns_none(tmp_path):
    from bob.a_b_comparison_cli import load_run_telemetry

    db = tmp_path / "bob.db"
    _make_db(db, runs=[])
    result = load_run_telemetry("nonexistent-run", db_path=str(db))
    assert result is None


def test_load_run_telemetry_null_cost(tmp_path):
    from bob.a_b_comparison_cli import load_run_telemetry

    db = tmp_path / "bob.db"
    _make_db(db, runs=[{"id": "run-b", "cost_usd": None, "duration_ms": None, "status": "failed"}])
    result = load_run_telemetry("run-b", db_path=str(db))
    assert result is not None
    assert result["cost_usd"] is None


# ---------------------------------------------------------------------------
# compute_run_stats — aggregated metrics for a run
# ---------------------------------------------------------------------------


def test_compute_run_stats_success_rate(tmp_path):
    from bob.a_b_comparison_cli import compute_run_stats

    db = tmp_path / "bob.db"
    _make_db(db, runs=[
        {"id": "run-a", "project_id": "proj-1", "status": "completed", "cost_usd": 1.0, "duration_ms": 1000, "target_id": "feat-1"},
        {"id": "run-b", "project_id": "proj-1", "status": "failed",    "cost_usd": 0.5, "duration_ms": 500,  "target_id": "feat-2"},
        {"id": "run-c", "project_id": "proj-1", "status": "completed", "cost_usd": 2.0, "duration_ms": 2000, "target_id": "feat-3"},
    ], features=[
        {"id": "feat-1", "name": "Feature 1"},
        {"id": "feat-2", "name": "Feature 2"},
        {"id": "feat-3", "name": "Feature 3"},
    ])
    # Compute stats for multiple runs
    stats = compute_run_stats(["run-a", "run-b", "run-c"], db_path=str(db))
    # 2 out of 3 completed => 0.666...
    assert stats["success_rate"] == pytest.approx(2 / 3)
    assert stats["total_cost_usd"] == pytest.approx(3.5)
    assert stats["run_count"] == 3


def test_compute_run_stats_empty():
    from bob.a_b_comparison_cli import compute_run_stats

    stats = compute_run_stats([], db_path=":memory:")
    assert stats["run_count"] == 0
    assert stats["success_rate"] == 0.0
    assert stats["total_cost_usd"] == 0.0


def test_compute_run_stats_hack_detection_rate(tmp_path):
    from bob.a_b_comparison_cli import compute_run_stats

    db = tmp_path / "bob.db"
    _make_db(db, runs=[
        {"id": "run-a", "status": "completed", "cost_usd": 1.0, "duration_ms": 1000, "target_id": "feat-1"},
        {"id": "run-b", "status": "completed", "cost_usd": 1.0, "duration_ms": 1000, "target_id": "feat-2"},
    ], features=[
        {"id": "feat-1"},
        {"id": "feat-2"},
    ])
    # Add reward hacking verdict for feat-2 only
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO reward_hacking_verdicts (id, feature_id, verdict, overall_score, attack_vectors, confidence) VALUES (?, ?, ?, ?, ?, ?)",
        ("v1", "feat-2", "hacking", 0.9, "[]", 0.95),
    )
    conn.commit()
    conn.close()

    stats = compute_run_stats(["run-a", "run-b"], db_path=str(db))
    # 1 out of 2 features flagged as hacking
    assert stats["hack_detection_rate"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# format_comparison
# ---------------------------------------------------------------------------


def test_format_comparison_contains_run_ids():
    from bob.a_b_comparison_cli import format_comparison

    stats_a = {"run_id": "run-a", "run_count": 5, "success_rate": 0.8, "total_cost_usd": 10.0,
               "avg_cost_usd": 2.0, "hack_detection_rate": 0.2, "calibration_ece": 0.05,
               "per_feature_outcomes": {}}
    stats_b = {"run_id": "run-b", "run_count": 5, "success_rate": 0.6, "total_cost_usd": 8.0,
               "avg_cost_usd": 1.6, "hack_detection_rate": 0.4, "calibration_ece": 0.1,
               "per_feature_outcomes": {}}

    output = format_comparison(stats_a, stats_b)
    assert "run-a" in output
    assert "run-b" in output


def test_format_comparison_shows_success_rate():
    from bob.a_b_comparison_cli import format_comparison

    stats_a = {"run_id": "run-a", "run_count": 2, "success_rate": 0.75, "total_cost_usd": 5.0,
               "avg_cost_usd": 2.5, "hack_detection_rate": 0.0, "calibration_ece": 0.0,
               "per_feature_outcomes": {}}
    stats_b = {"run_id": "run-b", "run_count": 2, "success_rate": 0.50, "total_cost_usd": 3.0,
               "avg_cost_usd": 1.5, "hack_detection_rate": 0.0, "calibration_ece": 0.0,
               "per_feature_outcomes": {}}

    output = format_comparison(stats_a, stats_b)
    # Should show success rates somewhere
    assert "75" in output or "0.75" in output
    assert "50" in output or "0.50" in output or "0.5" in output


def test_format_comparison_shows_cost():
    from bob.a_b_comparison_cli import format_comparison

    stats_a = {"run_id": "run-a", "run_count": 1, "success_rate": 1.0, "total_cost_usd": 12.34,
               "avg_cost_usd": 12.34, "hack_detection_rate": 0.0, "calibration_ece": 0.0,
               "per_feature_outcomes": {}}
    stats_b = {"run_id": "run-b", "run_count": 1, "success_rate": 1.0, "total_cost_usd": 5.67,
               "avg_cost_usd": 5.67, "hack_detection_rate": 0.0, "calibration_ece": 0.0,
               "per_feature_outcomes": {}}

    output = format_comparison(stats_a, stats_b)
    assert "12.34" in output
    assert "5.67" in output


def test_format_comparison_returns_string():
    from bob.a_b_comparison_cli import format_comparison

    stats_a = {"run_id": "run-a", "run_count": 0, "success_rate": 0.0, "total_cost_usd": 0.0,
               "avg_cost_usd": 0.0, "hack_detection_rate": 0.0, "calibration_ece": 0.0,
               "per_feature_outcomes": {}}
    stats_b = {**stats_a, "run_id": "run-b"}

    output = format_comparison(stats_a, stats_b)
    assert isinstance(output, str)
    assert len(output) > 0


# ---------------------------------------------------------------------------
# compare_runs — high-level entry point
# ---------------------------------------------------------------------------


def test_compare_runs_returns_string(tmp_path):
    from bob.a_b_comparison_cli import compare_runs

    db = tmp_path / "bob.db"
    _make_db(db, runs=[
        {"id": "run-a", "status": "completed", "cost_usd": 1.0, "duration_ms": 1000, "target_id": "feat-1"},
        {"id": "run-b", "status": "failed",    "cost_usd": 0.5, "duration_ms": 500,  "target_id": "feat-2"},
    ])
    result = compare_runs("run-a", "run-b", db_path=str(db))
    assert isinstance(result, str)
    assert "run-a" in result
    assert "run-b" in result


def test_compare_runs_missing_run_a(tmp_path):
    from bob.a_b_comparison_cli import compare_runs, RunNotFoundError

    db = tmp_path / "bob.db"
    _make_db(db, runs=[
        {"id": "run-b", "status": "completed", "cost_usd": 1.0, "duration_ms": 1000},
    ])
    with pytest.raises(RunNotFoundError):
        compare_runs("nonexistent", "run-b", db_path=str(db))


def test_compare_runs_missing_run_b(tmp_path):
    from bob.a_b_comparison_cli import compare_runs, RunNotFoundError

    db = tmp_path / "bob.db"
    _make_db(db, runs=[
        {"id": "run-a", "status": "completed", "cost_usd": 1.0, "duration_ms": 1000},
    ])
    with pytest.raises(RunNotFoundError):
        compare_runs("run-a", "nonexistent", db_path=str(db))


def test_compare_runs_side_by_side_structure(tmp_path):
    from bob.a_b_comparison_cli import compare_runs

    db = tmp_path / "bob.db"
    _make_db(db, runs=[
        {"id": "run-a", "status": "completed", "cost_usd": 2.0, "duration_ms": 5000, "target_id": "feat-1"},
        {"id": "run-b", "status": "completed", "cost_usd": 1.0, "duration_ms": 3000, "target_id": "feat-1"},
    ])
    output = compare_runs("run-a", "run-b", db_path=str(db))
    # Should have both run IDs and key metrics
    assert "run-a" in output
    assert "run-b" in output
    assert "cost" in output.lower() or "Cost" in output


def test_compare_runs_per_feature_outcomes(tmp_path):
    from bob.a_b_comparison_cli import compare_runs

    db = tmp_path / "bob.db"
    _make_db(db, runs=[
        {"id": "run-a", "status": "completed", "cost_usd": 1.0, "duration_ms": 1000, "target_id": "feat-1"},
        {"id": "run-b", "status": "failed",    "cost_usd": 0.5, "duration_ms": 500,  "target_id": "feat-1"},
    ], features=[
        {"id": "feat-1", "name": "My Feature"},
    ])
    output = compare_runs("run-a", "run-b", db_path=str(db))
    # Should mention the feature or its outcome
    assert "feat-1" in output or "My Feature" in output or "completed" in output
