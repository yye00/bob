"""Tests demonstrating Voyager pattern: two features sharing xxd workaround via skill library.

Simulates the full cross-feature skill reuse workflow in a temporary worktree:
1. Feature A (first) encounters missing xxd, discovers workaround, writes to library.
2. Feature B (second) searches library, finds the workaround, applies it without research spawn.
"""

import pathlib
import pytest

from bob3.skill_library.registry import (
    add_skill,
    apply_skill,
    persist_new_workaround,
    search_skills,
    survive_generation_spawn,
    mirrored_via_disk_reconciler,
    SkillHit,
)


XXD_PYTHON_SHIM = '''\
"""Shim: Python stdlib xxd replacement — hex dump bytes.

Capability: hex dump a binary file or byte sequence using Python stdlib,
replacing the xxd CLI tool when it is absent from the environment.
"""


def apply(context):
    data = context.get("data", b"")
    if isinstance(data, str):
        data = data.encode("latin-1")
    return " ".join(f"{b:02x}" for b in data)
'''

XXD_COMPARE_SHIM = '''\
"""Shim: compare two hex dumps using Python stdlib, replacing diff <(xxd ...).

Capability: compare two binary byte sequences by hex-dumping both and
checking for equality, replacing the xxd+diff pattern.
"""


def apply(context):
    a = context.get("a", b"")
    b = context.get("b", b"")

    def to_hex(data):
        if isinstance(data, str):
            data = data.encode("latin-1")
        return " ".join(f"{byte:02x}" for byte in data)

    return to_hex(a) == to_hex(b)
'''


def test_feature_a_writes_xxd_shim_to_library(tmp_path):
    """Feature A: discovers xxd workaround and persists it."""
    skill_id = persist_new_workaround(
        capability_description="hex dump binary file using Python stdlib as xxd replacement",
        shim_module_src=XXD_PYTHON_SHIM,
        workspace=tmp_path,
    )
    assert isinstance(skill_id, str)
    # Verify it's on disk
    shim_path = tmp_path / "skill_library" / f"{skill_id}.py"
    assert shim_path.exists()


def test_feature_b_finds_xxd_shim_without_new_research(tmp_path):
    """Feature B: finds existing xxd shim via similarity search — no research needed."""
    # Feature A ran first, wrote the shim
    persist_new_workaround(
        capability_description="hex dump binary file using Python stdlib as xxd replacement",
        shim_module_src=XXD_PYTHON_SHIM,
        workspace=tmp_path,
    )

    # Feature B searches before spawning research
    hits = search_skills(
        query="xxd binary comparison hex dump CLI missing workaround",
        workspace=tmp_path,
        threshold=0.0,
    )
    assert len(hits) > 0, "Feature B should find xxd workaround via library"


def test_feature_b_applies_shim_successfully(tmp_path):
    """Feature B applies the found shim and gets correct output."""
    persist_new_workaround(
        capability_description="hex dump binary file using Python stdlib as xxd replacement",
        shim_module_src=XXD_PYTHON_SHIM,
        workspace=tmp_path,
    )
    hits = search_skills(
        query="xxd binary hex dump workaround",
        workspace=tmp_path,
        threshold=0.0,
    )
    result = apply_skill(hits[0], context={"data": b"\xca\xfe\xba\xbe"})
    assert result.success is True
    assert "ca" in result.output
    assert "fe" in result.output


def test_library_persists_across_feature_boundaries(tmp_path):
    """Skill written during feature A is still present when feature B runs."""
    # Feature A writes
    id_a = add_skill(
        capability_description="hex dump binary file as xxd CLI replacement",
        shim_module_src=XXD_PYTHON_SHIM,
        workspace=tmp_path,
    )
    # Feature B reads (no additional writes)
    hits = search_skills(
        query="hex dump xxd replacement binary",
        workspace=tmp_path,
        threshold=0.0,
    )
    assert any(h.skill_id == id_a for h in hits)


def test_survive_generation_spawn_returns_true():
    assert survive_generation_spawn() is True


def test_mirrored_via_disk_reconciler_returns_true():
    assert mirrored_via_disk_reconciler() is True


def test_two_features_total_research_spawns(tmp_path):
    """End-to-end: only 1 research spawn total across 2 features requiring xxd."""
    research_spawns = 0

    # Feature A: library miss -> research spawn -> write shim
    hits_a = search_skills(
        query="xxd hex dump workaround",
        workspace=tmp_path,
        threshold=0.0,
    )
    if not hits_a:
        research_spawns += 1  # miss: spawn research
        persist_new_workaround(
            capability_description="hex dump binary file using Python as xxd workaround",
            shim_module_src=XXD_PYTHON_SHIM,
            workspace=tmp_path,
        )

    # Feature B: library hit -> no research spawn
    hits_b = search_skills(
        query="hex dump binary comparison xxd missing",
        workspace=tmp_path,
        threshold=0.0,
    )
    if not hits_b:
        research_spawns += 1  # miss: would spawn research

    assert research_spawns == 1, (
        f"Expected exactly 1 research spawn across 2 features, got {research_spawns}"
    )
    assert len(hits_b) > 0, "Feature B should hit the library without research"
