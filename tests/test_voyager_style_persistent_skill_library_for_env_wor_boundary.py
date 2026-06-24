"""Boundary case tests for the Voyager-style persistent skill library.

AC: pytest: tests/test_voyager_style_persistent_skill_library_for_env_wor_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising.
"""

import pathlib
import pytest

from bob73.skill_library import write_skill
from bob73.preflight import search_skill_library
from bob3.skill_library.registry import (
    search_skills,
    apply_skill,
    SkillHit,
    similarity_threshold,
)


# ---------------------------------------------------------------------------
# Boundary: empty / minimal library
# ---------------------------------------------------------------------------


def test_search_skills_empty_library_returns_empty_list(tmp_path):
    """search_skills on an empty library returns [] not raises."""
    result = search_skills(query="hex dump binary file", workspace=tmp_path, threshold=0.0)
    assert result == []


def test_search_skill_library_empty_library_returns_none(tmp_path):
    """search_skill_library on an empty library returns None not raises."""
    result = search_skill_library(
        capability_query="some capability",
        workspace=tmp_path,
    )
    assert result is None


def test_search_skill_library_nonexistent_workspace_returns_none(tmp_path):
    """Searching in a workspace where skill_library dir doesn't exist returns None."""
    nonexistent = tmp_path / "no_such_dir"
    result = search_skill_library(
        capability_query="some capability",
        workspace=nonexistent,
    )
    assert result is None


def test_search_skills_threshold_zero_returns_results(tmp_path):
    """threshold=0.0 returns all skills (boundary: lowest threshold)."""
    shim_src = '"""Shim."""\ndef apply(context): return 1\n'
    write_skill("test capability abc", shim_src, workspace=tmp_path)
    results = search_skills(query="unrelated query xyz", workspace=tmp_path, threshold=0.0)
    assert len(results) >= 1


def test_search_skills_threshold_one_returns_nothing(tmp_path):
    """threshold=1.0 returns empty list unless query exactly equals stored description."""
    shim_src = '"""Shim."""\ndef apply(context): return 1\n'
    write_skill("test capability abc", shim_src, workspace=tmp_path)
    results = search_skills(query="unrelated query xyz", workspace=tmp_path, threshold=1.0)
    assert results == []


# ---------------------------------------------------------------------------
# Boundary: minimal shim input
# ---------------------------------------------------------------------------


def test_write_skill_minimal_shim_src(tmp_path):
    """Minimal valid shim (one-liner apply) is accepted without raising."""
    minimal_shim = '"""Minimal."""\ndef apply(context): return None\n'
    skill_id = write_skill(
        capability_description="minimal workaround",
        shim_module_src=minimal_shim,
        workspace=tmp_path,
    )
    assert isinstance(skill_id, str)
    assert len(skill_id) > 0


def test_write_skill_single_character_description(tmp_path):
    """Single-character capability description is stored without raising."""
    shim_src = '"""S."""\ndef apply(context): return "x"\n'
    skill_id = write_skill(
        capability_description="x",
        shim_module_src=shim_src,
        workspace=tmp_path,
    )
    assert isinstance(skill_id, str)


# ---------------------------------------------------------------------------
# Boundary: apply_skill with empty context
# ---------------------------------------------------------------------------


def test_apply_skill_empty_context(tmp_path):
    """apply_skill with empty context dict returns success (not raises)."""
    shim_src = '"""Echo shim."""\ndef apply(context): return context.get("msg", "default")\n'
    write_skill("echo capability", shim_src, workspace=tmp_path)
    hits = search_skills(query="echo capability", workspace=tmp_path, threshold=0.0)
    assert len(hits) >= 1
    result = apply_skill(hits[0], context={})
    assert result.success is True
    assert result.output == "default"


def test_apply_skill_none_context_treated_as_empty(tmp_path):
    """apply_skill with context=None defaults gracefully."""
    shim_src = '"""Echo shim."""\ndef apply(context): return context.get("msg", "none_default")\n'
    write_skill("echo with none context", shim_src, workspace=tmp_path)
    hits = search_skills(query="echo with none context", workspace=tmp_path, threshold=0.0)
    assert len(hits) >= 1
    result = apply_skill(hits[0], context=None)
    assert result.success is True
    assert result.output == "none_default"


# ---------------------------------------------------------------------------
# Boundary: similarity_threshold returns a float in [0, 1]
# ---------------------------------------------------------------------------


def test_similarity_threshold_is_in_valid_range():
    """similarity_threshold() returns a float in (0, 1)."""
    t = similarity_threshold()
    assert isinstance(t, float)
    assert 0.0 < t < 1.0


# ---------------------------------------------------------------------------
# Boundary: search_skill_library with explicit threshold=0.0
# ---------------------------------------------------------------------------


def test_search_skill_library_threshold_zero_hits(tmp_path):
    """Explicit threshold=0.0 returns a hit even if similarity is very low."""
    shim_src = '"""Shim."""\ndef apply(context): return True\n'
    write_skill("completely unrelated skill xyz", shim_src, workspace=tmp_path)
    result = search_skill_library(
        capability_query="completely unrelated skill xyz",
        workspace=tmp_path,
        threshold=0.0,
    )
    # With an exact match at threshold=0.0 we should get a hit
    assert result is not None
    assert result["research_needed"] is False


# ---------------------------------------------------------------------------
# Boundary: write_skill called with the same skill_id (upsert)
# ---------------------------------------------------------------------------


def test_write_skill_upsert_returns_same_id(tmp_path):
    """Calling write_skill with the same explicit skill_id returns that same id."""
    shim_src = '"""V1."""\ndef apply(context): return 1\n'
    shim_src_v2 = '"""V2."""\ndef apply(context): return 2\n'
    id1 = write_skill("cap", shim_src, workspace=tmp_path, skill_id="fixed_id")
    id2 = write_skill("cap", shim_src_v2, workspace=tmp_path, skill_id="fixed_id")
    assert id1 == "fixed_id"
    assert id2 == "fixed_id"
    # Latest shim is on disk
    shim_path = tmp_path / "skill_library" / "fixed_id.py"
    assert shim_path.read_text() == shim_src_v2
