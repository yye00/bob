"""Tests for skill-effectiveness scoring module."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from bob3.skill_effectiveness_scoring import (
    FeaturePairRecord,
    SkillScore,
    compute_skill_scores,
    load_feature_refinement_attempts,
    load_skill_activation_events,
    save_skill_scores,
    load_skill_scores,
    score_skill,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_progress_file(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def _skill_activation_event(
    feature_id: str,
    skills_activated: list[str],
    spawn_id: str = "spawn-1",
) -> dict:
    return {
        "timestamp": "2026-05-18T10:00:00+00:00",
        "event_type": "skill_activation_logged",
        "payload": {
            "spawn_id": spawn_id,
            "feature_id": feature_id,
            "skills_activated": skills_activated,
            "skills_considered": skills_activated,
            "selection_reason": "heuristic",
        },
    }


def _make_db(path: Path, features: list[dict]) -> None:
    """Create a minimal SQLite DB with a features table."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS features (
            id TEXT PRIMARY KEY,
            name TEXT,
            status TEXT DEFAULT 'completed',
            refinement_attempts INTEGER DEFAULT 0
        )"""
    )
    for feat in features:
        conn.execute(
            "INSERT INTO features (id, name, status, refinement_attempts) VALUES (?, ?, ?, ?)",
            (feat["id"], feat.get("name", ""), feat.get("status", "completed"), feat.get("refinement_attempts", 0)),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# load_skill_activation_events
# ---------------------------------------------------------------------------


def test_load_skill_activation_events_basic(tmp_path):
    """Returns list of (feature_id, skills_activated) from progress.jsonl."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"
    _make_progress_file(
        progress_file,
        [
            _skill_activation_event("f1", ["tdd", "no-stubs"]),
            _skill_activation_event("f2", ["tdd"]),
        ],
    )

    records = load_skill_activation_events(progress_file)
    assert len(records) == 2
    assert records[0].feature_id == "f1"
    assert set(records[0].skills_activated) == {"tdd", "no-stubs"}
    assert records[1].feature_id == "f2"
    assert records[1].skills_activated == ["tdd"]


def test_load_skill_activation_events_ignores_other_events(tmp_path):
    """Skips non-skill-activation events."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"
    _make_progress_file(
        progress_file,
        [
            {"event_type": "progress_updated", "payload": {"feature_id": "f1", "outcome": "completed"}},
            _skill_activation_event("f2", ["tdd"]),
        ],
    )

    records = load_skill_activation_events(progress_file)
    assert len(records) == 1
    assert records[0].feature_id == "f2"


def test_load_skill_activation_events_missing_file(tmp_path):
    """Returns empty list when file does not exist."""
    missing = tmp_path / ".bob3" / "progress.jsonl"
    records = load_skill_activation_events(missing)
    assert records == []


def test_load_skill_activation_events_empty_file(tmp_path):
    """Returns empty list for an empty file."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    progress_file.write_text("")
    records = load_skill_activation_events(progress_file)
    assert records == []


# ---------------------------------------------------------------------------
# load_feature_refinement_attempts
# ---------------------------------------------------------------------------


def test_load_feature_refinement_attempts_basic(tmp_path):
    """Returns dict mapping feature_id to refinement_attempts."""
    db_path = tmp_path / "bob3.db"
    _make_db(db_path, [
        {"id": "f1", "refinement_attempts": 2},
        {"id": "f2", "refinement_attempts": 0},
        {"id": "f3", "refinement_attempts": 5},
    ])

    result = load_feature_refinement_attempts(db_path, ["f1", "f2", "f3"])
    assert result == {"f1": 2, "f2": 0, "f3": 5}


def test_load_feature_refinement_attempts_unknown_ids(tmp_path):
    """Silently omits feature IDs not found in the DB."""
    db_path = tmp_path / "bob3.db"
    _make_db(db_path, [{"id": "f1", "refinement_attempts": 1}])

    result = load_feature_refinement_attempts(db_path, ["f1", "nonexistent"])
    assert "f1" in result
    assert "nonexistent" not in result


def test_load_feature_refinement_attempts_empty_ids(tmp_path):
    """Returns empty dict when no feature IDs are requested."""
    db_path = tmp_path / "bob3.db"
    _make_db(db_path, [{"id": "f1", "refinement_attempts": 1}])
    result = load_feature_refinement_attempts(db_path, [])
    assert result == {}


# ---------------------------------------------------------------------------
# score_skill
# ---------------------------------------------------------------------------


def test_score_skill_active_lower_refinements():
    """Positive delta when skill-active features have fewer refinements."""
    active_refinements = [0, 1, 0]    # avg = 0.33
    inactive_refinements = [2, 3, 4]  # avg = 3.0
    score = score_skill("tdd", active_refinements, inactive_refinements)
    assert isinstance(score, SkillScore)
    assert score.skill_name == "tdd"
    # delta = inactive_avg - active_avg (positive means skill helped)
    assert score.delta > 0
    assert score.active_count == 3
    assert score.inactive_count == 3
    assert abs(score.active_avg_refinements - (0 + 1 + 0) / 3) < 1e-9
    assert abs(score.inactive_avg_refinements - (2 + 3 + 4) / 3) < 1e-9


def test_score_skill_inactive_lower_refinements():
    """Negative delta when skill-active features have more refinements."""
    active_refinements = [3, 4]
    inactive_refinements = [0, 1]
    score = score_skill("tdd", active_refinements, inactive_refinements)
    assert score.delta < 0


def test_score_skill_equal_refinements():
    """Delta is zero when both groups have the same average."""
    score = score_skill("tdd", [2, 2], [2, 2])
    assert abs(score.delta) < 1e-9


def test_score_skill_one_active_no_inactive():
    """Returns score with delta=None when no inactive group to compare."""
    score = score_skill("tdd", [1, 2], [])
    assert score.delta is None


def test_score_skill_no_active_some_inactive():
    """Returns score with delta=None when no active group to compare."""
    score = score_skill("tdd", [], [1, 2])
    assert score.delta is None


def test_score_skill_both_empty():
    """Returns score with delta=None when both groups are empty."""
    score = score_skill("tdd", [], [])
    assert score.delta is None


# ---------------------------------------------------------------------------
# compute_skill_scores
# ---------------------------------------------------------------------------


def test_compute_skill_scores_basic(tmp_path):
    """Computes scores for each skill from activation events + DB."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"
    db_path = tmp_path / "bob3.db"

    _make_progress_file(
        progress_file,
        [
            _skill_activation_event("f1", ["tdd"]),
            _skill_activation_event("f2", ["tdd"]),
            _skill_activation_event("f3", []),  # no skills
        ],
    )
    _make_db(db_path, [
        {"id": "f1", "refinement_attempts": 0},
        {"id": "f2", "refinement_attempts": 1},
        {"id": "f3", "refinement_attempts": 4},
    ])

    scores = compute_skill_scores(progress_file=progress_file, db_path=db_path)
    assert "tdd" in scores
    tdd_score = scores["tdd"]
    # f1, f2 are active (avg 0.5); f3 is inactive (avg 4.0)
    assert tdd_score.active_count == 2
    assert tdd_score.inactive_count == 1
    assert tdd_score.delta > 0


def test_compute_skill_scores_no_events(tmp_path):
    """Returns empty dict when there are no activation events."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"
    progress_file.parent.mkdir(parents=True)
    progress_file.write_text("")
    db_path = tmp_path / "bob3.db"
    _make_db(db_path, [])

    scores = compute_skill_scores(progress_file=progress_file, db_path=db_path)
    assert scores == {}


def test_compute_skill_scores_multiple_skills(tmp_path):
    """Each skill gets its own score entry."""
    progress_file = tmp_path / ".bob3" / "progress.jsonl"
    db_path = tmp_path / "bob3.db"

    _make_progress_file(
        progress_file,
        [
            _skill_activation_event("f1", ["tdd", "no-stubs"]),
            _skill_activation_event("f2", ["no-stubs"]),
            _skill_activation_event("f3", []),
        ],
    )
    _make_db(db_path, [
        {"id": "f1", "refinement_attempts": 0},
        {"id": "f2", "refinement_attempts": 1},
        {"id": "f3", "refinement_attempts": 3},
    ])

    scores = compute_skill_scores(progress_file=progress_file, db_path=db_path)
    assert "tdd" in scores
    assert "no-stubs" in scores


# ---------------------------------------------------------------------------
# save_skill_scores / load_skill_scores
# ---------------------------------------------------------------------------


def test_save_and_load_skill_scores(tmp_path):
    """Scores can be saved to YAML and loaded back."""
    registry_path = tmp_path / "skill_scores.yaml"
    scores = {
        "tdd": SkillScore(
            skill_name="tdd",
            active_count=3,
            inactive_count=2,
            active_avg_refinements=0.5,
            inactive_avg_refinements=2.0,
            delta=1.5,
        ),
        "no-stubs": SkillScore(
            skill_name="no-stubs",
            active_count=1,
            inactive_count=0,
            active_avg_refinements=1.0,
            inactive_avg_refinements=0.0,
            delta=None,
        ),
    }
    save_skill_scores(scores, registry_path)
    assert registry_path.exists()

    loaded = load_skill_scores(registry_path)
    assert "tdd" in loaded
    assert "no-stubs" in loaded
    assert loaded["tdd"].delta == pytest.approx(1.5)
    assert loaded["no-stubs"].delta is None
    assert loaded["tdd"].active_count == 3
    assert loaded["no-stubs"].active_count == 1


def test_save_skill_scores_creates_parent_dir(tmp_path):
    """save_skill_scores creates parent directory if it doesn't exist."""
    registry_path = tmp_path / "deep" / "nested" / "skill_scores.yaml"
    scores = {
        "tdd": SkillScore(
            skill_name="tdd",
            active_count=1,
            inactive_count=0,
            active_avg_refinements=1.0,
            inactive_avg_refinements=0.0,
            delta=None,
        )
    }
    save_skill_scores(scores, registry_path)
    assert registry_path.exists()


def test_load_skill_scores_missing_file(tmp_path):
    """Returns empty dict when registry file does not exist."""
    missing = tmp_path / "no_such_file.yaml"
    loaded = load_skill_scores(missing)
    assert loaded == {}


def test_save_skill_scores_yaml_structure(tmp_path):
    """Saved YAML is human-readable and contains expected fields."""
    registry_path = tmp_path / "skill_scores.yaml"
    scores = {
        "tdd": SkillScore(
            skill_name="tdd",
            active_count=4,
            inactive_count=6,
            active_avg_refinements=0.75,
            inactive_avg_refinements=2.5,
            delta=1.75,
        )
    }
    save_skill_scores(scores, registry_path)
    doc = yaml.safe_load(registry_path.read_text())
    assert "tdd" in doc
    entry = doc["tdd"]
    assert entry["active_count"] == 4
    assert entry["inactive_count"] == 6
    assert abs(entry["delta"] - 1.75) < 1e-9


# ---------------------------------------------------------------------------
# FeaturePairRecord
# ---------------------------------------------------------------------------


def test_feature_pair_record_fields():
    """FeaturePairRecord stores feature_id and skills_activated."""
    rec = FeaturePairRecord(feature_id="f1", skills_activated=["tdd"])
    assert rec.feature_id == "f1"
    assert rec.skills_activated == ["tdd"]


# ---------------------------------------------------------------------------
# SkillScore
# ---------------------------------------------------------------------------


def test_skill_score_fields():
    """SkillScore stores all expected fields."""
    s = SkillScore(
        skill_name="tdd",
        active_count=3,
        inactive_count=5,
        active_avg_refinements=0.5,
        inactive_avg_refinements=2.0,
        delta=1.5,
    )
    assert s.skill_name == "tdd"
    assert s.active_count == 3
    assert s.inactive_count == 5
    assert s.active_avg_refinements == pytest.approx(0.5)
    assert s.inactive_avg_refinements == pytest.approx(2.0)
    assert s.delta == pytest.approx(1.5)


def test_skill_score_delta_none():
    """SkillScore allows delta=None for insufficient data."""
    s = SkillScore(
        skill_name="tdd",
        active_count=2,
        inactive_count=0,
        active_avg_refinements=1.0,
        inactive_avg_refinements=0.0,
        delta=None,
    )
    assert s.delta is None
