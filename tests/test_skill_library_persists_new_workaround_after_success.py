"""Tests for persist_new_workaround — verifies that new discoveries are written to the library."""

import json
import pathlib
import pytest

from bob3.skill_library.registry import (
    persist_new_workaround,
    search_skills,
    add_skill,
)


PYTHON_XXDFALLBACK_SHIM = '''\
"""Shim: Python stdlib fallback replacing the xxd CLI tool."""


def apply(context):
    data = context.get("data", b"")
    if isinstance(data, (str, bytearray)):
        data = bytes(data)
    return " ".join(f"{b:02x}" for b in data)
'''


def test_persist_new_workaround_returns_skill_id(tmp_path):
    skill_id = persist_new_workaround(
        capability_description="hex dump binary data using Python stdlib as xxd fallback",
        shim_module_src=PYTHON_XXDFALLBACK_SHIM,
        workspace=tmp_path,
    )
    assert isinstance(skill_id, str)
    assert len(skill_id) > 0


def test_persist_new_workaround_writes_shim_to_disk(tmp_path):
    skill_id = persist_new_workaround(
        capability_description="hex dump binary data using Python stdlib as xxd fallback",
        shim_module_src=PYTHON_XXDFALLBACK_SHIM,
        workspace=tmp_path,
    )
    shim_path = tmp_path / "skill_library" / f"{skill_id}.py"
    assert shim_path.exists()
    assert shim_path.read_text() == PYTHON_XXDFALLBACK_SHIM


def test_persist_new_workaround_updates_index(tmp_path):
    skill_id = persist_new_workaround(
        capability_description="hex dump binary data using Python stdlib as xxd fallback",
        shim_module_src=PYTHON_XXDFALLBACK_SHIM,
        workspace=tmp_path,
    )
    index_path = tmp_path / "skill_library" / "index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text())
    skill_ids = [s["skill_id"] for s in index.get("skills", [])]
    assert skill_id in skill_ids


def test_persisted_workaround_is_searchable(tmp_path):
    persist_new_workaround(
        capability_description="hex dump binary data as xxd replacement workaround",
        shim_module_src=PYTHON_XXDFALLBACK_SHIM,
        workspace=tmp_path,
    )
    hits = search_skills(
        query="hex dump binary xxd workaround",
        workspace=tmp_path,
        threshold=0.0,
    )
    assert len(hits) > 0
    assert hits[0].shim_module_src == PYTHON_XXDFALLBACK_SHIM


def test_persist_new_workaround_idempotent(tmp_path):
    """Calling persist twice with same description should upsert, not duplicate."""
    skill_id_1 = persist_new_workaround(
        capability_description="hex dump binary as xxd replacement",
        shim_module_src=PYTHON_XXDFALLBACK_SHIM,
        workspace=tmp_path,
    )
    skill_id_2 = persist_new_workaround(
        capability_description="hex dump binary as xxd replacement",
        shim_module_src=PYTHON_XXDFALLBACK_SHIM,
        workspace=tmp_path,
    )
    assert skill_id_1 == skill_id_2

    index_path = tmp_path / "skill_library" / "index.json"
    index = json.loads(index_path.read_text())
    matching = [s for s in index["skills"] if s["skill_id"] == skill_id_1]
    assert len(matching) == 1, "Upsert should not create duplicate entries"


def test_persist_new_workaround_library_dir_created(tmp_path):
    """Library directory is created if it doesn't exist."""
    lib_dir = tmp_path / "skill_library"
    assert not lib_dir.exists()

    persist_new_workaround(
        capability_description="some workaround capability",
        shim_module_src="def apply(context): return True",
        workspace=tmp_path,
    )
    assert lib_dir.exists()


def test_multiple_workarounds_persisted_independently(tmp_path):
    shim_b = '''\
"""Shim: run jq JSON queries via Python json module."""


def apply(context):
    import json as _json
    data = context.get("json_str", "{}")
    return _json.loads(data)
'''
    id_a = persist_new_workaround(
        capability_description="hex dump binary data xxd fallback",
        shim_module_src=PYTHON_XXDFALLBACK_SHIM,
        workspace=tmp_path,
    )
    id_b = persist_new_workaround(
        capability_description="parse JSON using Python stdlib as jq fallback",
        shim_module_src=shim_b,
        workspace=tmp_path,
    )
    assert id_a != id_b

    index_path = tmp_path / "skill_library" / "index.json"
    index = json.loads(index_path.read_text())
    skill_ids = [s["skill_id"] for s in index["skills"]]
    assert id_a in skill_ids
    assert id_b in skill_ids
