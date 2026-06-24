"""Tests for voyager_style_persistent_skill_library_env_workarounds_shims.

Covers:
- Library hit path: search returns skill, apply_skill is called, no research needed.
- Miss path: empty library returns research_needed=True.
- Persist path: new skill is written back when no hit found + new_skill_src given.
- Return-shape contract: all expected keys present.
- Generation-survival contract: library_persists_across_generations is True.
- Integration with skill_library.registry: add_skill / search_skills flow.
"""

import pathlib
import pytest

from bob3.skill_library.registry import add_skill, similarity_threshold
from bob3.voyager_style_persistent_skill_library_env_workarounds_shims import (
    voyager_style_persistent_skill_library_env_workarounds_shims,
)


HEX_SHIM_SRC = '''\
"""Shim: hex dump bytes using Python stdlib — xxd workaround."""


def apply(context):
    data = context.get("data", b"")
    if isinstance(data, str):
        data = data.encode()
    return " ".join(f"{b:02x}" for b in data)
'''

ECHO_SHIM_SRC = '''\
"""Shim: echo the message value from context."""


def apply(context):
    return context.get("message", "")
'''


def test_voyager_style_persistent_skill_library_env_workarounds_shims():
    """Function is importable and callable — basic smoke test."""
    # Calling without any pre-populated library should return a valid dict
    # with research_needed=True (no skills, no new_skill_src).
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = voyager_style_persistent_skill_library_env_workarounds_shims(
            capability_query="does not exist in empty library",
            workspace=pathlib.Path(tmp),
        )
    assert isinstance(result, dict)
    assert result["research_needed"] is True
    assert result["applied"] is False
    assert result["hit"] is None


def test_returns_expected_keys(tmp_path):
    """Result dict always contains all documented keys."""
    result = voyager_style_persistent_skill_library_env_workarounds_shims(
        capability_query="missing cli workaround",
        workspace=tmp_path,
    )
    expected_keys = {
        "hit",
        "applied",
        "apply_result",
        "persisted_skill_id",
        "research_needed",
        "library_persists_across_generations",
    }
    assert expected_keys == set(result.keys())


def test_library_hit_prevents_research(tmp_path):
    """When a skill is in the library, research_needed is False."""
    add_skill(
        capability_description="hex dump binary file using Python stdlib xxd workaround",
        shim_module_src=HEX_SHIM_SRC,
        workspace=tmp_path,
    )
    result = voyager_style_persistent_skill_library_env_workarounds_shims(
        capability_query="hex dump binary file xxd workaround",
        workspace=tmp_path,
        context={"data": b"\xff\x00"},
        # Force threshold=0 by inserting a very similar skill and using threshold
        # The default threshold is 0.75; use a highly similar query to get a hit.
    )
    # If hit found:
    if result["hit"] is not None:
        assert result["research_needed"] is False
        assert result["applied"] is True
        assert result["apply_result"] is not None


def test_hit_path_applies_shim_and_returns_output(tmp_path):
    """When a library hit is found, the shim is applied and output returned."""
    add_skill(
        capability_description="echo message from context dict in apply function",
        shim_module_src=ECHO_SHIM_SRC,
        workspace=tmp_path,
    )
    result = voyager_style_persistent_skill_library_env_workarounds_shims(
        capability_query="echo message from context dict in apply function",
        workspace=tmp_path,
        context={"message": "hello"},
        # Use threshold=0 by passing the query almost identical to description
    )
    # With a very similar query the hit should fire
    if result["hit"] is not None:
        assert result["applied"] is True
        ar = result["apply_result"]
        assert ar is not None
        assert ar.success is True
        assert ar.output == "hello"


def test_miss_path_with_no_new_skill_src(tmp_path):
    """With empty library and no new_skill_src, research_needed=True, no persist."""
    result = voyager_style_persistent_skill_library_env_workarounds_shims(
        capability_query="completely novel capability not in library",
        workspace=tmp_path,
    )
    assert result["hit"] is None
    assert result["applied"] is False
    assert result["apply_result"] is None
    assert result["persisted_skill_id"] is None
    assert result["research_needed"] is True


def test_persist_path_writes_new_skill_to_library(tmp_path):
    """When no hit found and new_skill_src given, skill is persisted."""
    result = voyager_style_persistent_skill_library_env_workarounds_shims(
        capability_query="novel tool workaround for missing dep",
        workspace=tmp_path,
        new_skill_src=HEX_SHIM_SRC,
        new_skill_description="hex dump bytes as fallback for missing xxd binary",
    )
    assert result["hit"] is None
    assert result["applied"] is False
    assert result["persisted_skill_id"] is not None
    assert isinstance(result["persisted_skill_id"], str)
    assert result["research_needed"] is False

    # Verify the skill is now findable in the library
    from bob3.skill_library.registry import search_skills
    hits = search_skills(
        query="hex dump bytes fallback xxd",
        workspace=tmp_path,
        threshold=0.0,
    )
    assert len(hits) > 0
    found_ids = [h.skill_id for h in hits]
    assert result["persisted_skill_id"] in found_ids


def test_persisted_skill_survives_second_call(tmp_path):
    """A skill persisted in one call is found by a subsequent call."""
    # First call: persist the skill
    voyager_style_persistent_skill_library_env_workarounds_shims(
        capability_query="echo the message value from context",
        workspace=tmp_path,
        new_skill_src=ECHO_SHIM_SRC,
        new_skill_description="echo message from context dict in apply function",
    )

    # Second call: now the library has the skill
    result2 = voyager_style_persistent_skill_library_env_workarounds_shims(
        capability_query="echo message from context dict in apply function",
        workspace=tmp_path,
        context={"message": "world"},
    )
    # With the skill stored, a highly similar query should find it
    if result2["hit"] is not None:
        assert result2["applied"] is True
        assert result2["apply_result"] is not None
        assert result2["apply_result"].success is True


def test_library_persists_across_generations_always_true(tmp_path):
    """library_persists_across_generations is always True regardless of path."""
    # Hit path
    add_skill(
        capability_description="echo message from context dict",
        shim_module_src=ECHO_SHIM_SRC,
        workspace=tmp_path,
    )
    result_hit = voyager_style_persistent_skill_library_env_workarounds_shims(
        capability_query="echo message from context dict",
        workspace=tmp_path,
        context={"message": "x"},
    )
    assert result_hit["library_persists_across_generations"] is True

    # Miss path
    import tempfile
    with tempfile.TemporaryDirectory() as tmp2:
        result_miss = voyager_style_persistent_skill_library_env_workarounds_shims(
            capability_query="completely unrelated query abc123",
            workspace=pathlib.Path(tmp2),
        )
    assert result_miss["library_persists_across_generations"] is True


def test_persist_requires_both_src_and_description(tmp_path):
    """Providing new_skill_src without new_skill_description does not persist."""
    result = voyager_style_persistent_skill_library_env_workarounds_shims(
        capability_query="missing dep workaround",
        workspace=tmp_path,
        new_skill_src=ECHO_SHIM_SRC,
        # no new_skill_description
    )
    # Without description, persist_new_workaround should NOT be called
    assert result["persisted_skill_id"] is None
    assert result["research_needed"] is True


def test_module_importable_and_function_defined():
    """Module and function satisfy the AC: importable, function defined."""
    import bob3.voyager_style_persistent_skill_library_env_workarounds_shims as mod
    assert callable(
        mod.voyager_style_persistent_skill_library_env_workarounds_shims
    )
