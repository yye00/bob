"""Tests for add_skill and search_skills in the skill library registry."""

import pathlib
import pytest
from bob.skill_library.registry import add_skill, search_skills, SkillHit, similarity_threshold


SHIM_SRC = '''\
"""Shim: hex dump a binary file using Python stdlib."""


def apply(context):
    data = context.get("data", b"")
    return " ".join(f"{b:02x}" for b in data)
'''


def test_add_skill_returns_string_id(tmp_path):
    skill_id = add_skill(
        capability_description="hex dump a binary file using Python stdlib",
        shim_module_src=SHIM_SRC,
        workspace=tmp_path,
    )
    assert isinstance(skill_id, str)
    assert len(skill_id) > 0


def test_add_skill_writes_shim_file(tmp_path):
    skill_id = add_skill(
        capability_description="hex dump a binary file using Python stdlib",
        shim_module_src=SHIM_SRC,
        workspace=tmp_path,
    )
    shim_path = tmp_path / "skill_library" / f"{skill_id}.py"
    assert shim_path.exists()
    assert shim_path.read_text() == SHIM_SRC


def test_add_skill_writes_index(tmp_path):
    add_skill(
        capability_description="hex dump a binary file using Python stdlib",
        shim_module_src=SHIM_SRC,
        workspace=tmp_path,
    )
    index_path = tmp_path / "skill_library" / "index.json"
    assert index_path.exists()


def test_search_skills_returns_hit_for_similar_query(tmp_path):
    add_skill(
        capability_description="hex dump a binary file using Python stdlib",
        shim_module_src=SHIM_SRC,
        workspace=tmp_path,
    )
    hits = search_skills(
        query="convert binary file to hex dump",
        workspace=tmp_path,
        threshold=0.0,  # use low threshold to ensure we get a result
    )
    assert len(hits) > 0
    assert isinstance(hits[0], SkillHit)
    assert hits[0].shim_module_src == SHIM_SRC


def test_search_skills_returns_empty_when_library_empty(tmp_path):
    hits = search_skills(query="hex dump", workspace=tmp_path)
    assert hits == []


def test_search_skills_respects_threshold(tmp_path):
    add_skill(
        capability_description="hex dump a binary file using Python stdlib",
        shim_module_src=SHIM_SRC,
        workspace=tmp_path,
    )
    # Setting threshold=1.0 (perfect match required) should return no hits
    # for a non-identical query
    hits = search_skills(
        query="completely unrelated refrigerator maintenance task",
        workspace=tmp_path,
        threshold=1.0,
    )
    assert hits == []


def test_search_skills_hit_has_all_fields(tmp_path):
    skill_id = add_skill(
        capability_description="hex dump a binary file using Python stdlib",
        shim_module_src=SHIM_SRC,
        workspace=tmp_path,
    )
    hits = search_skills(
        query="hex dump binary",
        workspace=tmp_path,
        threshold=0.0,
    )
    assert len(hits) > 0
    hit = hits[0]
    assert hit.skill_id == skill_id
    assert isinstance(hit.capability_description, str)
    assert isinstance(hit.similarity, float)
    assert isinstance(hit.shim_module_src, str)


def test_add_skill_upsert_updates_description(tmp_path):
    skill_id = add_skill(
        capability_description="hex dump a binary file",
        shim_module_src=SHIM_SRC,
        workspace=tmp_path,
        skill_id="skill_manual_id",
    )
    # Upsert with same ID but updated description
    add_skill(
        capability_description="hex dump binary data to hex string output",
        shim_module_src=SHIM_SRC,
        workspace=tmp_path,
        skill_id="skill_manual_id",
    )
    hits = search_skills(
        query="hex dump binary",
        workspace=tmp_path,
        threshold=0.0,
    )
    # Should still have exactly one entry, not two
    ids = [h.skill_id for h in hits]
    assert ids.count("skill_manual_id") == 1
