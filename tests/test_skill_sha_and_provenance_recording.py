"""Tests for skill SHA and provenance recording module."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bob.skill_sha_and_provenance_recording import (
    compute_skill_sha,
    compute_skill_shas,
    attach_skill_shas_to_event,
    load_spawn_provenance,
    SpawnProvenance,
)


# ---------------------------------------------------------------------------
# compute_skill_sha
# ---------------------------------------------------------------------------


def test_compute_skill_sha_returns_hex_digest(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("# My Skill\nDoes stuff.", encoding="utf-8")

    sha = compute_skill_sha(skill_dir)

    expected = hashlib.sha256("# My Skill\nDoes stuff.".encode("utf-8")).hexdigest()
    assert sha == expected


def test_compute_skill_sha_missing_skill_md_returns_none(tmp_path):
    skill_dir = tmp_path / "empty-skill"
    skill_dir.mkdir()

    sha = compute_skill_sha(skill_dir)

    assert sha is None


def test_compute_skill_sha_nonexistent_dir_returns_none(tmp_path):
    sha = compute_skill_sha(tmp_path / "nonexistent")
    assert sha is None


def test_compute_skill_sha_different_content_produces_different_sha(tmp_path):
    skill_a = tmp_path / "skill-a"
    skill_b = tmp_path / "skill-b"
    skill_a.mkdir()
    skill_b.mkdir()
    (skill_a / "SKILL.md").write_text("content A", encoding="utf-8")
    (skill_b / "SKILL.md").write_text("content B", encoding="utf-8")

    assert compute_skill_sha(skill_a) != compute_skill_sha(skill_b)


def test_compute_skill_sha_same_content_produces_same_sha(tmp_path):
    skill_a = tmp_path / "skill-a"
    skill_b = tmp_path / "skill-b"
    skill_a.mkdir()
    skill_b.mkdir()
    (skill_a / "SKILL.md").write_text("identical content", encoding="utf-8")
    (skill_b / "SKILL.md").write_text("identical content", encoding="utf-8")

    assert compute_skill_sha(skill_a) == compute_skill_sha(skill_b)


# ---------------------------------------------------------------------------
# compute_skill_shas
# ---------------------------------------------------------------------------


def test_compute_skill_shas_returns_dict_for_all_skills(tmp_path):
    skills_dir = tmp_path / "skills"
    for name, content in [
        ("skill-a", "content-A"),
        ("skill-b", "content-B"),
        ("skill-c", "content-C"),
    ]:
        d = skills_dir / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(content, encoding="utf-8")

    result = compute_skill_shas(["skill-a", "skill-b", "skill-c"], skills_dir=skills_dir)

    assert set(result.keys()) == {"skill-a", "skill-b", "skill-c"}
    for name, content in [("skill-a", "content-A"), ("skill-b", "content-B"), ("skill-c", "content-C")]:
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert result[name] == expected


def test_compute_skill_shas_missing_skill_excluded(tmp_path):
    skills_dir = tmp_path / "skills"
    (skills_dir / "present").mkdir(parents=True)
    (skills_dir / "present" / "SKILL.md").write_text("hello", encoding="utf-8")

    result = compute_skill_shas(["present", "absent"], skills_dir=skills_dir)

    assert "present" in result
    assert "absent" not in result


def test_compute_skill_shas_empty_list(tmp_path):
    result = compute_skill_shas([], skills_dir=tmp_path)
    assert result == {}


def test_compute_skill_shas_returns_64_char_hex(tmp_path):
    skills_dir = tmp_path / "skills"
    (skills_dir / "my-skill").mkdir(parents=True)
    (skills_dir / "my-skill" / "SKILL.md").write_text("content", encoding="utf-8")

    result = compute_skill_shas(["my-skill"], skills_dir=skills_dir)

    sha = result["my-skill"]
    assert len(sha) == 64
    assert all(c in "0123456789abcdef" for c in sha)


# ---------------------------------------------------------------------------
# attach_skill_shas_to_event
# ---------------------------------------------------------------------------


def test_attach_skill_shas_to_event_adds_shas_field(tmp_path):
    skills_dir = tmp_path / "skills"
    (skills_dir / "tdd").mkdir(parents=True)
    (skills_dir / "tdd" / "SKILL.md").write_text("# TDD", encoding="utf-8")

    event = {
        "event_type": "skill_activation_logged",
        "payload": {
            "spawn_id": "spawn-1",
            "feature_id": "feat-abc",
            "skills_activated": ["tdd"],
        },
    }

    enriched = attach_skill_shas_to_event(event, skills_dir=skills_dir)

    assert "skill_shas" in enriched["payload"]
    assert "tdd" in enriched["payload"]["skill_shas"]
    expected = hashlib.sha256("# TDD".encode("utf-8")).hexdigest()
    assert enriched["payload"]["skill_shas"]["tdd"] == expected


def test_attach_skill_shas_to_event_preserves_original_fields(tmp_path):
    skills_dir = tmp_path / "skills"
    (skills_dir / "sk").mkdir(parents=True)
    (skills_dir / "sk" / "SKILL.md").write_text("x", encoding="utf-8")

    event = {
        "event_type": "skill_activation_logged",
        "timestamp": "2026-01-01T00:00:00Z",
        "payload": {
            "spawn_id": "sp-1",
            "feature_id": "f-1",
            "skills_activated": ["sk"],
            "skills_considered": ["sk"],
            "selection_reason": "heuristic",
        },
    }

    enriched = attach_skill_shas_to_event(event, skills_dir=skills_dir)

    assert enriched["timestamp"] == "2026-01-01T00:00:00Z"
    assert enriched["payload"]["spawn_id"] == "sp-1"
    assert enriched["payload"]["feature_id"] == "f-1"
    assert enriched["payload"]["skills_considered"] == ["sk"]
    assert enriched["payload"]["selection_reason"] == "heuristic"


def test_attach_skill_shas_to_event_no_skills_activated(tmp_path):
    event = {
        "event_type": "skill_activation_logged",
        "payload": {
            "spawn_id": "sp",
            "feature_id": "f",
            "skills_activated": [],
        },
    }

    enriched = attach_skill_shas_to_event(event, skills_dir=tmp_path)

    assert enriched["payload"]["skill_shas"] == {}


def test_attach_skill_shas_to_event_missing_skill_md_excluded(tmp_path):
    skills_dir = tmp_path / "skills"
    # skill-a has SKILL.md; skill-b does not
    (skills_dir / "skill-a").mkdir(parents=True)
    (skills_dir / "skill-a" / "SKILL.md").write_text("A", encoding="utf-8")
    (skills_dir / "skill-b").mkdir(parents=True)

    event = {
        "event_type": "skill_activation_logged",
        "payload": {
            "skills_activated": ["skill-a", "skill-b"],
        },
    }

    enriched = attach_skill_shas_to_event(event, skills_dir=skills_dir)

    assert "skill-a" in enriched["payload"]["skill_shas"]
    assert "skill-b" not in enriched["payload"]["skill_shas"]


# ---------------------------------------------------------------------------
# SpawnProvenance dataclass
# ---------------------------------------------------------------------------


def test_spawn_provenance_has_expected_fields():
    sp = SpawnProvenance(
        spawn_id="sp-1",
        feature_id="feat-1",
        skills_activated=["tdd"],
        skill_shas={"tdd": "abc123"},
    )
    assert sp.spawn_id == "sp-1"
    assert sp.feature_id == "feat-1"
    assert sp.skills_activated == ["tdd"]
    assert sp.skill_shas == {"tdd": "abc123"}


def test_spawn_provenance_skill_shas_defaults_to_empty():
    sp = SpawnProvenance(
        spawn_id="sp-2",
        feature_id="feat-2",
        skills_activated=[],
    )
    assert sp.skill_shas == {}


# ---------------------------------------------------------------------------
# load_spawn_provenance
# ---------------------------------------------------------------------------


def _make_progress_file(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def test_load_spawn_provenance_parses_skill_shas(tmp_path):
    progress = tmp_path / ".bob" / "progress.jsonl"
    sha = hashlib.sha256("# TDD".encode("utf-8")).hexdigest()
    _make_progress_file(progress, [
        {
            "event_type": "skill_activation_logged",
            "payload": {
                "spawn_id": "sp-1",
                "feature_id": "feat-1",
                "skills_activated": ["tdd"],
                "skill_shas": {"tdd": sha},
            },
        }
    ])

    records = load_spawn_provenance(progress)

    assert len(records) == 1
    assert records[0].spawn_id == "sp-1"
    assert records[0].feature_id == "feat-1"
    assert records[0].skills_activated == ["tdd"]
    assert records[0].skill_shas == {"tdd": sha}


def test_load_spawn_provenance_empty_file(tmp_path):
    progress = tmp_path / ".bob" / "progress.jsonl"
    _make_progress_file(progress, [])

    records = load_spawn_provenance(progress)
    assert records == []


def test_load_spawn_provenance_missing_file(tmp_path):
    records = load_spawn_provenance(tmp_path / "nonexistent.jsonl")
    assert records == []


def test_load_spawn_provenance_skips_non_skill_events(tmp_path):
    progress = tmp_path / ".bob" / "progress.jsonl"
    _make_progress_file(progress, [
        {"event_type": "feature_started", "payload": {}},
        {
            "event_type": "skill_activation_logged",
            "payload": {
                "spawn_id": "sp-2",
                "feature_id": "feat-2",
                "skills_activated": [],
                "skill_shas": {},
            },
        },
        {"event_type": "cost_checkpoint", "payload": {}},
    ])

    records = load_spawn_provenance(progress)

    assert len(records) == 1
    assert records[0].spawn_id == "sp-2"


def test_load_spawn_provenance_no_skill_shas_field(tmp_path):
    """Events without skill_shas field (older format) get empty dict."""
    progress = tmp_path / ".bob" / "progress.jsonl"
    _make_progress_file(progress, [
        {
            "event_type": "skill_activation_logged",
            "payload": {
                "spawn_id": "sp-3",
                "feature_id": "feat-3",
                "skills_activated": ["some-skill"],
            },
        }
    ])

    records = load_spawn_provenance(progress)

    assert len(records) == 1
    assert records[0].skill_shas == {}


def test_load_spawn_provenance_multiple_events(tmp_path):
    progress = tmp_path / ".bob" / "progress.jsonl"
    sha1 = hashlib.sha256(b"A").hexdigest()
    sha2 = hashlib.sha256(b"B").hexdigest()
    _make_progress_file(progress, [
        {
            "event_type": "skill_activation_logged",
            "payload": {
                "spawn_id": "sp-1",
                "feature_id": "feat-1",
                "skills_activated": ["skill-a"],
                "skill_shas": {"skill-a": sha1},
            },
        },
        {
            "event_type": "skill_activation_logged",
            "payload": {
                "spawn_id": "sp-2",
                "feature_id": "feat-2",
                "skills_activated": ["skill-b"],
                "skill_shas": {"skill-b": sha2},
            },
        },
    ])

    records = load_spawn_provenance(progress)

    assert len(records) == 2
    assert records[0].skill_shas == {"skill-a": sha1}
    assert records[1].skill_shas == {"skill-b": sha2}
