"""Tests for per-spawn skill-activation logging and CLI report command."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from bob3.skills_installer import log_skill_activation
from bob3.cli import main


# ---------------------------------------------------------------------------
# log_skill_activation tests
# ---------------------------------------------------------------------------


def test_log_skill_activation_writes_event(tmp_path):
    """log_skill_activation writes a skill_activation_logged event to progress.jsonl."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"

    with patch("bob3.skills_installer.get_progress_path", return_value=progress_file):
        log_skill_activation(
            spawn_id="spawn-abc",
            feature_id="feat-123",
            skills_activated=["tdd", "no-stubs"],
            skills_considered=["tdd", "no-stubs", "adversarial-self-review"],
            selection_reason="heuristic",
        )

    assert progress_file.exists()
    lines = progress_file.read_text().strip().splitlines()
    assert len(lines) == 1

    event = json.loads(lines[0])
    assert event["event_type"] == "skill_activation_logged"
    assert event["payload"]["spawn_id"] == "spawn-abc"
    assert event["payload"]["feature_id"] == "feat-123"
    assert event["payload"]["skills_activated"] == ["tdd", "no-stubs"]
    assert event["payload"]["skills_considered"] == ["tdd", "no-stubs", "adversarial-self-review"]
    assert event["payload"]["selection_reason"] == "heuristic"
    assert "timestamp" in event


def test_log_skill_activation_appends(tmp_path):
    """Multiple calls append separate events."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"

    with patch("bob3.skills_installer.get_progress_path", return_value=progress_file):
        log_skill_activation("s1", "f1", ["tdd"], ["tdd"], "heuristic")
        log_skill_activation("s2", "f2", ["no-stubs"], ["no-stubs", "tdd"], "registry-driven")

    lines = progress_file.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["payload"]["spawn_id"] == "s1"
    assert json.loads(lines[1])["payload"]["spawn_id"] == "s2"


def test_log_skill_activation_creates_parent_dir(tmp_path):
    """log_skill_activation creates .bob3/ if it doesn't exist."""
    progress_file = tmp_path / "deep" / "nested" / ".bob3" / "progress.jsonl"

    with patch("bob3.skills_installer.get_progress_path", return_value=progress_file):
        log_skill_activation("s1", "f1", [], [], "heuristic")

    assert progress_file.exists()


def test_log_skill_activation_empty_lists(tmp_path):
    """log_skill_activation handles empty skill lists gracefully."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"

    with patch("bob3.skills_installer.get_progress_path", return_value=progress_file):
        log_skill_activation("s1", "f1", [], [], "heuristic")

    event = json.loads(progress_file.read_text().strip())
    assert event["payload"]["skills_activated"] == []
    assert event["payload"]["skills_considered"] == []


def test_log_skill_activation_registry_driven_reason(tmp_path):
    """log_skill_activation accepts registry-driven selection_reason."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"

    with patch("bob3.skills_installer.get_progress_path", return_value=progress_file):
        log_skill_activation("s1", "f1", ["tdd"], ["tdd"], "registry-driven")

    event = json.loads(progress_file.read_text().strip())
    assert event["payload"]["selection_reason"] == "registry-driven"


# ---------------------------------------------------------------------------
# skill-activation-report CLI tests
# ---------------------------------------------------------------------------


def _make_progress_file(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def _skill_activation_event(
    spawn_id: str,
    feature_id: str,
    skills_activated: list[str],
    skills_considered: list[str] | None = None,
    selection_reason: str = "heuristic",
) -> dict:
    return {
        "timestamp": "2026-05-16T10:00:00+00:00",
        "event_type": "skill_activation_logged",
        "payload": {
            "spawn_id": spawn_id,
            "feature_id": feature_id,
            "skills_activated": skills_activated,
            "skills_considered": skills_considered or skills_activated,
            "selection_reason": selection_reason,
        },
    }


def _outcome_event(feature_id: str, outcome: str) -> dict:
    return {
        "timestamp": "2026-05-16T10:05:00+00:00",
        "event_type": "progress_updated",
        "payload": {
            "feature_id": feature_id,
            "outcome": outcome,
        },
    }


def test_skill_activation_report_basic(tmp_path):
    """skill-activation-report shows skills and their fire counts."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"
    _make_progress_file(
        progress_file,
        [
            _skill_activation_event("s1", "f1", ["tdd", "no-stubs"]),
            _skill_activation_event("s2", "f2", ["tdd"]),
        ],
    )

    runner = CliRunner()
    with patch("bob3.cli.get_progress_path", return_value=progress_file):
        result = runner.invoke(main, ["skill-activation-report"])

    assert result.exit_code == 0
    assert "tdd" in result.output
    # tdd fired in 2 spawns, no-stubs in 1
    assert "2" in result.output


def test_skill_activation_report_empty(tmp_path):
    """skill-activation-report handles no activation events gracefully."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"
    progress_file.parent.mkdir(parents=True)
    progress_file.write_text("")

    runner = CliRunner()
    with patch("bob3.cli.get_progress_path", return_value=progress_file):
        result = runner.invoke(main, ["skill-activation-report"])

    assert result.exit_code == 0
    assert "No skill-activation events" in result.output


def test_skill_activation_report_no_file(tmp_path):
    """skill-activation-report handles missing progress.jsonl gracefully."""
    missing = tmp_path / ".bob3" / "progress.jsonl"

    runner = CliRunner()
    with patch("bob3.cli.get_progress_path", return_value=missing):
        result = runner.invoke(main, ["skill-activation-report"])

    assert result.exit_code == 0
    assert "No skill-activation events" in result.output


def test_skill_activation_report_with_outcomes(tmp_path):
    """skill-activation-report correlates skill activation with feature success."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"
    _make_progress_file(
        progress_file,
        [
            _skill_activation_event("s1", "f1", ["tdd"]),
            _outcome_event("f1", "completed"),
            _skill_activation_event("s2", "f2", ["tdd"]),
            _outcome_event("f2", "failed"),
        ],
    )

    runner = CliRunner()
    with patch("bob3.cli.get_progress_path", return_value=progress_file):
        result = runner.invoke(main, ["skill-activation-report"])

    assert result.exit_code == 0
    # Should show tdd and some success rate info
    assert "tdd" in result.output
    # 1 success out of 2 features → 50%
    assert "50" in result.output


def test_skill_activation_report_ignores_non_activation_events(tmp_path):
    """skill-activation-report skips unrelated event types."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"
    _make_progress_file(
        progress_file,
        [
            {"event_type": "feature_started", "payload": {"feature_id": "f1"}},
            _skill_activation_event("s1", "f1", ["tdd"]),
        ],
    )

    runner = CliRunner()
    with patch("bob3.cli.get_progress_path", return_value=progress_file):
        result = runner.invoke(main, ["skill-activation-report"])

    assert result.exit_code == 0
    assert "tdd" in result.output
