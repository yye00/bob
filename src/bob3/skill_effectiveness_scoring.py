"""Skill-effectiveness scoring for bob3.

Measures the reduction in refinement attempts (delta) when a skill is
active vs. inactive across matched feature pairs. Scores are stored in
a YAML-based skills registry and surfaced via ``bob3 skill-report``.

Public API:
    FeaturePairRecord   - dataclass holding a feature's skill activation data
    SkillScore          - dataclass holding computed effectiveness metrics
    load_skill_activation_events(progress_path) -> list[FeaturePairRecord]
    load_feature_refinement_attempts(db_path, feature_ids) -> dict[str, int]
    score_skill(name, active_refinements, inactive_refinements) -> SkillScore
    compute_skill_scores(*, progress_file, db_path) -> dict[str, SkillScore]
    save_skill_scores(scores, registry_path) -> None
    load_skill_scores(registry_path) -> dict[str, SkillScore]
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class FeaturePairRecord:
    """One feature's skill-activation record extracted from progress.jsonl."""

    feature_id: str
    skills_activated: list[str] = field(default_factory=list)


@dataclass
class SkillScore:
    """Effectiveness metrics for a single skill."""

    skill_name: str
    active_count: int
    inactive_count: int
    active_avg_refinements: float
    inactive_avg_refinements: float
    # Positive delta means skill reduced refinement attempts (good).
    # None when one group is empty (insufficient data).
    delta: Optional[float]


def load_skill_activation_events(progress_path: Path) -> list[FeaturePairRecord]:
    """Read skill_activation_logged events from the progress JSONL log.

    Args:
        progress_path: Path to .bob3/progress.jsonl.

    Returns:
        List of FeaturePairRecord, one per skill_activation_logged event.
    """
    if not progress_path.exists():
        return []

    records: list[FeaturePairRecord] = []
    for line in progress_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event_type") != "skill_activation_logged":
            continue
        payload = event.get("payload") or {}
        feature_id = payload.get("feature_id", "")
        if not feature_id:
            continue
        skills_activated: list[str] = payload.get("skills_activated") or []
        records.append(FeaturePairRecord(feature_id=feature_id, skills_activated=skills_activated))

    return records


def load_feature_refinement_attempts(
    db_path: Path, feature_ids: list[str]
) -> dict[str, int]:
    """Query refinement_attempts for the given feature IDs from SQLite.

    Args:
        db_path: Path to bob3.db.
        feature_ids: List of feature UUIDs to look up.

    Returns:
        Dict mapping feature_id -> refinement_attempts (omits missing IDs).
    """
    if not feature_ids:
        return {}
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path))
    try:
        placeholders = ",".join("?" * len(feature_ids))
        cursor = conn.execute(
            f"SELECT id, refinement_attempts FROM features WHERE id IN ({placeholders})",
            feature_ids,
        )
        return {row[0]: row[1] for row in cursor.fetchall()}
    finally:
        conn.close()


def score_skill(
    skill_name: str,
    active_refinements: list[int],
    inactive_refinements: list[int],
) -> SkillScore:
    """Compute an effectiveness score for a single skill.

    Delta = inactive_avg - active_avg.  A positive delta indicates that
    features implemented with the skill required fewer refinement attempts
    on average (i.e., the skill helped).

    Args:
        skill_name: Identifier of the skill being scored.
        active_refinements: Refinement attempt counts for features where this
            skill was activated.
        inactive_refinements: Refinement attempt counts for features where this
            skill was NOT activated.

    Returns:
        SkillScore with delta=None when either group is empty.
    """
    active_count = len(active_refinements)
    inactive_count = len(inactive_refinements)

    active_avg = sum(active_refinements) / active_count if active_count else 0.0
    inactive_avg = sum(inactive_refinements) / inactive_count if inactive_count else 0.0

    if active_count == 0 or inactive_count == 0:
        delta = None
    else:
        delta = inactive_avg - active_avg

    return SkillScore(
        skill_name=skill_name,
        active_count=active_count,
        inactive_count=inactive_count,
        active_avg_refinements=active_avg,
        inactive_avg_refinements=inactive_avg,
        delta=delta,
    )


def compute_skill_scores(
    *,
    progress_file: Path,
    db_path: Path,
) -> dict[str, SkillScore]:
    """Compute effectiveness scores for all skills found in the event log.

    Algorithm:
    1. Parse skill_activation_logged events to determine which features had
       each skill active.
    2. Fetch refinement_attempts for all referenced features from the DB.
    3. Partition features for each skill into "active" and "inactive" groups.
    4. Compute delta (inactive_avg - active_avg) for each skill.

    Args:
        progress_file: Path to .bob3/progress.jsonl.
        db_path: Path to bob3.db.

    Returns:
        Dict mapping skill_name -> SkillScore.
    """
    records = load_skill_activation_events(progress_file)
    if not records:
        return {}

    all_feature_ids = [r.feature_id for r in records]
    refinement_map = load_feature_refinement_attempts(db_path, all_feature_ids)

    # Build per-skill sets of active feature IDs
    skill_active_features: dict[str, set[str]] = {}
    all_seen_feature_ids: set[str] = set()

    for rec in records:
        all_seen_feature_ids.add(rec.feature_id)
        for skill in rec.skills_activated:
            skill_active_features.setdefault(skill, set()).add(rec.feature_id)

    scores: dict[str, SkillScore] = {}
    for skill, active_ids in skill_active_features.items():
        inactive_ids = all_seen_feature_ids - active_ids

        active_refinements = [
            refinement_map[fid] for fid in active_ids if fid in refinement_map
        ]
        inactive_refinements = [
            refinement_map[fid] for fid in inactive_ids if fid in refinement_map
        ]

        scores[skill] = score_skill(skill, active_refinements, inactive_refinements)

    return scores


def save_skill_scores(scores: dict[str, SkillScore], registry_path: Path) -> None:
    """Persist skill scores to a YAML file (the skills registry).

    The file is human-readable and can be checked into version control.

    Args:
        scores: Dict mapping skill_name -> SkillScore.
        registry_path: Destination YAML file path.
    """
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    doc: dict = {}
    for skill_name, score in sorted(scores.items()):
        doc[skill_name] = {
            "active_count": score.active_count,
            "inactive_count": score.inactive_count,
            "active_avg_refinements": score.active_avg_refinements,
            "inactive_avg_refinements": score.inactive_avg_refinements,
            "delta": score.delta,
        }

    registry_path.write_text(
        yaml.dump(doc, sort_keys=True, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def load_skill_scores(registry_path: Path) -> dict[str, SkillScore]:
    """Load previously computed skill scores from the YAML registry.

    Args:
        registry_path: Path to the YAML file written by save_skill_scores.

    Returns:
        Dict mapping skill_name -> SkillScore. Empty dict if file is missing.
    """
    if not registry_path.exists():
        return {}

    doc = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    scores: dict[str, SkillScore] = {}
    for skill_name, entry in doc.items():
        scores[skill_name] = SkillScore(
            skill_name=skill_name,
            active_count=entry.get("active_count", 0),
            inactive_count=entry.get("inactive_count", 0),
            active_avg_refinements=entry.get("active_avg_refinements", 0.0),
            inactive_avg_refinements=entry.get("inactive_avg_refinements", 0.0),
            delta=entry.get("delta"),
        )
    return scores
