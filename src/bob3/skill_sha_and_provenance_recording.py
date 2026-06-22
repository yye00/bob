"""Skill SHA and provenance recording for bob3.

Records the SHA-256 of each skill's SKILL.md content alongside spawn
records. A skill change mid-experiment is detectable from telemetry by
comparing the recorded SHA against the current SKILL.md content.

Public API:
    SpawnProvenance       - dataclass holding spawn provenance data
    compute_skill_sha(skill_dir) -> str | None
    compute_skill_shas(skill_names, *, skills_dir) -> dict[str, str]
    attach_skill_shas_to_event(event, *, skills_dir) -> dict
    load_spawn_provenance(progress_path) -> list[SpawnProvenance]
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SpawnProvenance:
    """Provenance record for a single sub-agent spawn."""

    spawn_id: str
    feature_id: str
    skills_activated: list[str]
    skill_shas: dict[str, str] = field(default_factory=dict)


def compute_skill_sha(skill_dir: Path) -> str | None:
    """Compute the SHA-256 hex digest of a skill's SKILL.md content.

    Args:
        skill_dir: Directory for the skill (must contain SKILL.md).

    Returns:
        64-character lowercase hex SHA-256 digest, or None if SKILL.md
        does not exist or skill_dir is not a directory.
    """
    if not skill_dir.is_dir():
        return None
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None
    content = skill_md.read_text(encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_skill_shas(
    skill_names: list[str],
    *,
    skills_dir: Path,
) -> dict[str, str]:
    """Compute SHA-256 digests for multiple skills.

    Skills whose SKILL.md is absent are omitted from the result.

    Args:
        skill_names: List of skill identifiers (directory names).
        skills_dir: Root directory containing one sub-directory per skill.

    Returns:
        Dict mapping skill_name -> SHA-256 hex digest for skills that
        have a readable SKILL.md.
    """
    result: dict[str, str] = {}
    for name in skill_names:
        sha = compute_skill_sha(skills_dir / name)
        if sha is not None:
            result[name] = sha
    return result


def attach_skill_shas_to_event(
    event: dict,
    *,
    skills_dir: Path,
) -> dict:
    """Return a copy of a skill_activation_logged event with skill SHAs added.

    Reads ``payload.skills_activated`` from the event, computes the SHA-256
    of each skill's SKILL.md relative to ``skills_dir``, and stores the
    results in ``payload.skill_shas``.  Skills without a readable SKILL.md
    are silently omitted.

    The original event dict is not mutated.

    Args:
        event: A skill_activation_logged event dict.
        skills_dir: Root directory containing one sub-directory per skill.

    Returns:
        A new dict with the same top-level keys, but with ``skill_shas``
        added inside ``payload``.
    """
    payload = dict(event.get("payload") or {})
    skills_activated: list[str] = payload.get("skills_activated") or []
    payload["skill_shas"] = compute_skill_shas(skills_activated, skills_dir=skills_dir)
    return {**event, "payload": payload}


def load_spawn_provenance(progress_path: Path) -> list[SpawnProvenance]:
    """Parse skill_activation_logged events from a progress JSONL log.

    Reads provenance data (spawn_id, feature_id, skills_activated,
    skill_shas) from each ``skill_activation_logged`` event.  Events
    without ``skill_shas`` (older format) receive an empty dict.

    Args:
        progress_path: Path to the JSONL progress event log.

    Returns:
        List of SpawnProvenance, one per skill_activation_logged event.
        Returns an empty list if the file does not exist.
    """
    if not progress_path.exists():
        return []

    records: list[SpawnProvenance] = []
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
        records.append(
            SpawnProvenance(
                spawn_id=payload.get("spawn_id", ""),
                feature_id=payload.get("feature_id", ""),
                skills_activated=list(payload.get("skills_activated") or []),
                skill_shas=dict(payload.get("skill_shas") or {}),
            )
        )

    return records
