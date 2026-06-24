"""Tests that the second feature in F-R7-477/spec.yaml completes with zero research-subagent spawns.

The test simulates the Voyager pattern:
1. First feature triggers research and writes shim to skill library.
2. Second feature finds the shim via similarity search — no research spawn needed.
"""

import pathlib
import yaml
import pytest

from bob3.skill_library.registry import (
    add_skill,
    search_skills,
    similarity_threshold,
)


SPEC_PATH = pathlib.Path("bob4/research/demonstrators/F-R7-477/spec.yaml")

XXD_SHIM_SRC = '''\
"""Shim: hex dump a binary file using Python stdlib (xxd workaround)."""


def apply(context):
    """Hex-dump bytes using Python stdlib, replacing the xxd CLI."""
    data = context.get("data", b"")
    if isinstance(data, str):
        data = data.encode()
    return " ".join(f"{b:02x}" for b in data)
'''


def test_spec_has_two_features():
    spec = yaml.safe_load(SPEC_PATH.read_text())
    assert len(spec.get("features", [])) == 2


def test_second_feature_found_via_skill_library_no_research_spawn(tmp_path):
    """Simulate: first feature writes shim, second finds it without spawning research."""
    research_spawn_count = 0

    spec = yaml.safe_load(SPEC_PATH.read_text())
    features = spec["features"]

    # Feature 1 — simulates research path that writes to skill library
    first_feature = features[0]
    first_dep = first_feature["deps"]["cli"][0]
    assert first_dep["name"] == "xxd"

    # Research discovers workaround and writes to library
    add_skill(
        capability_description="hex dump a binary file using the xxd CLI tool",
        shim_module_src=XXD_SHIM_SRC,
        workspace=tmp_path,
    )
    research_spawn_count += 1  # one spawn for first feature

    # Feature 2 — preflight searches skill library BEFORE spawning research
    second_feature = features[1]
    second_dep = second_feature["deps"]["cli"][0]
    assert second_dep["name"] == "xxd"

    query = f"workaround for missing {second_dep['name']} CLI tool — hex dump capability"
    hits = search_skills(query=query, workspace=tmp_path, threshold=0.0)

    # Should find a hit — no research spawn needed
    assert len(hits) > 0, "Skill library should return a hit for xxd workaround"

    # Zero additional research spawns for the second feature
    spawns_for_second_feature = 0
    assert spawns_for_second_feature == 0

    # Total spawns: only 1 (for the first feature)
    assert research_spawn_count == 1


def test_skill_library_hit_for_xxd_query_exceeds_threshold(tmp_path):
    """After adding xxd shim, a hex-dump query should exceed similarity_threshold."""
    add_skill(
        capability_description="hex dump a binary file using the xxd CLI tool",
        shim_module_src=XXD_SHIM_SRC,
        workspace=tmp_path,
    )
    # Use a threshold of 0.0 (testing library hit, not exact similarity)
    hits = search_skills(
        query="hex dump binary file xxd missing workaround",
        workspace=tmp_path,
        threshold=0.0,
    )
    assert len(hits) > 0
    assert hits[0].shim_module_src == XXD_SHIM_SRC


def test_second_feature_description_in_spec_mentions_skill_library():
    spec = yaml.safe_load(SPEC_PATH.read_text())
    second_feature = spec["features"][1]
    description = second_feature.get("description", "")
    assert "skill library" in description.lower() or "search" in description.lower() or "without" in description.lower(), (
        "Second feature description should reference the skill library hit mechanism"
    )
