"""Tests for bf_2_research_documentarian_sub_agent_hide_ticket_pattern.

AC verification:
  - File exists: src/bob3/bf_2_research_documentarian_sub_agent_hide_ticket_pattern.py
  - Function defined: bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern
                        .bf_2_research_documentarian_sub_agent_hide_ticket_pattern
  - Function is callable and returns a structured dict.

Feature: BF-2 — Research-as-documentarian sub-agent (hide-the-ticket pattern).

Protocol invariants tested:
  1. researcher role has hide_intent=True (no ticket text reaches the researcher)
  2. researcher role is cacheable (same survey sha + path glob => skip re-research)
  3. researcher prompt contains NO intent/ticket text
  4. researcher prompt contains the path glob and symbol shortlist
  5. output path resolves to .bob3/features/<id>/research_notes.md
  6. cache_hit=False when no notes file exists; cache_hit=True when notes match
  7. protocol_steps list has exactly 5 entries covering the full protocol
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_MODULE = "bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern"
_FUNC = "bf_2_research_documentarian_sub_agent_hide_ticket_pattern"


# ---------------------------------------------------------------------------
# Primary AC test (required by acceptance criteria)
# ---------------------------------------------------------------------------


def test_bf_2_research_documentarian_sub_agent_hide_ticket_pattern():
    """AC: function is importable, callable, and returns a structured dict."""
    from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
        bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
    )

    result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern()

    assert isinstance(result, dict)
    # Core protocol invariant: hide_intent must be True
    assert result["hide_intent"] is True
    # Cacheable
    assert result["cacheable"] is True
    # Protocol steps list is non-empty
    assert isinstance(result["protocol_steps"], list)
    assert len(result["protocol_steps"]) >= 3
    # Role descriptor present
    assert isinstance(result["role"], dict)
    assert result["role"]["name"] == "researcher"


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


class TestModuleStructure:
    def test_source_file_exists(self):
        src = (
            Path(__file__).parent.parent
            / "src"
            / "bob3"
            / "bf_2_research_documentarian_sub_agent_hide_ticket_pattern.py"
        )
        assert src.exists(), f"Source file missing: {src}"

    def test_function_importable(self):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        assert callable(bf_2_research_documentarian_sub_agent_hide_ticket_pattern)

    def test_function_returns_dict(self):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Invariant 1: hide_intent is always True for researcher role
# ---------------------------------------------------------------------------


class TestHideIntentInvariant:
    def test_hide_intent_true_no_args(self):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern()
        assert result["hide_intent"] is True

    def test_hide_intent_true_with_feature_id(self, tmp_path):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern(
            feature_id="test-feature-id",
            workspace=tmp_path,
        )
        assert result["hide_intent"] is True

    def test_researcher_role_descriptor_matches(self):
        from bob3.agents.roles import RESEARCHER
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern()
        assert result["role"]["hide_intent"] == RESEARCHER.hide_intent
        assert result["role"]["hide_intent"] is True


# ---------------------------------------------------------------------------
# Invariant 2: researcher role is cacheable
# ---------------------------------------------------------------------------


class TestCacheableInvariant:
    def test_cacheable_true(self):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern()
        assert result["cacheable"] is True

    def test_role_cacheable_true(self):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern()
        assert result["role"]["cacheable"] is True


# ---------------------------------------------------------------------------
# Invariant 3: researcher prompt contains NO intent/ticket text
# ---------------------------------------------------------------------------


class TestResearcherPromptHidesTicket:
    def test_prompt_built_from_path_glob(self):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern(
            path_glob="src/bob3/orchestrator/**",
            symbol_shortlist=["dispatch", "coordinator"],
        )
        prompt = result["researcher_prompt"]
        assert "src/bob3/orchestrator/**" in prompt
        assert "dispatch" in prompt
        assert "coordinator" in prompt

    def test_prompt_contains_documentarian_instruction(self):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern(
            path_glob="src/bob3/agents/**",
        )
        prompt = result["researcher_prompt"]
        # Must contain the documentarian instruction (no speculation)
        assert "Do NOT speculate" in prompt

    def test_prompt_empty_when_no_path_glob(self):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern()
        assert result["researcher_prompt"] == ""


# ---------------------------------------------------------------------------
# Invariant 4: output path resolves correctly
# ---------------------------------------------------------------------------


class TestOutputPath:
    def test_output_path_empty_without_feature_id(self, tmp_path):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern(
            workspace=tmp_path
        )
        assert result["output_path"] == ""

    def test_output_path_contains_feature_id(self, tmp_path):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        fid = "abc-123"
        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern(
            feature_id=fid,
            workspace=tmp_path,
        )
        output_path = Path(result["output_path"])
        assert output_path.name == "research_notes.md"
        assert fid in str(output_path)
        assert ".bob3/features" in str(output_path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Invariant 5: cache hit/miss logic
# ---------------------------------------------------------------------------


class TestCacheLogic:
    def test_cache_miss_when_no_notes_file(self, tmp_path):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern(
            feature_id="feat-1",
            survey_sha="abc123",
            path_glob="src/**",
            workspace=tmp_path,
        )
        assert result["cache_hit"] is False

    def test_cache_hit_when_notes_match(self, tmp_path):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        fid = "feat-cache"
        sha = "deadbeef"
        glob = "src/bob3/**"

        notes_dir = tmp_path / ".bob3" / "features" / fid
        notes_dir.mkdir(parents=True)
        (notes_dir / "research_notes.md").write_text(
            f"---\nsurvey_sha: {sha}\npath_glob: {glob}\n---\n\nContent here.\n",
            encoding="utf-8",
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern(
            feature_id=fid,
            survey_sha=sha,
            path_glob=glob,
            workspace=tmp_path,
        )
        assert result["cache_hit"] is True

    def test_cache_miss_when_sha_differs(self, tmp_path):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        fid = "feat-sha-mismatch"
        glob = "src/bob3/**"

        notes_dir = tmp_path / ".bob3" / "features" / fid
        notes_dir.mkdir(parents=True)
        (notes_dir / "research_notes.md").write_text(
            f"---\nsurvey_sha: OLD_SHA\npath_glob: {glob}\n---\n",
            encoding="utf-8",
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern(
            feature_id=fid,
            survey_sha="NEW_SHA",
            path_glob=glob,
            workspace=tmp_path,
        )
        assert result["cache_hit"] is False


# ---------------------------------------------------------------------------
# Invariant 6: protocol steps list
# ---------------------------------------------------------------------------


class TestProtocolSteps:
    def test_protocol_steps_five_entries(self):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern()
        steps = result["protocol_steps"]
        assert len(steps) == 5

    def test_protocol_steps_cover_key_concepts(self):
        from bob3.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern,
        )

        result = bf_2_research_documentarian_sub_agent_hide_ticket_pattern()
        steps_text = " ".join(result["protocol_steps"]).lower()
        assert "path glob" in steps_text or "path_glob" in steps_text
        assert "research_notes" in steps_text or "research notes" in steps_text
        assert "cache" in steps_text or "cached" in steps_text


# ---------------------------------------------------------------------------
# Invariant 7: roles.py exposes researcher role correctly
# ---------------------------------------------------------------------------


class TestRolesModule:
    def test_researcher_role_exists(self):
        from bob3.agents.roles import RESEARCHER
        assert RESEARCHER.name == "researcher"

    def test_researcher_hide_intent_true(self):
        from bob3.agents.roles import RESEARCHER
        assert RESEARCHER.hide_intent is True

    def test_researcher_cacheable_true(self):
        from bob3.agents.roles import RESEARCHER
        assert RESEARCHER.cacheable is True

    def test_get_role_researcher(self):
        from bob3.agents.roles import get_role
        role = get_role("researcher")
        assert role.name == "researcher"
        assert role.hide_intent is True

    def test_build_researcher_prompt_excludes_ticket(self):
        from bob3.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(
            path_glob="src/bob3/**",
            symbol_shortlist=["foo", "bar"],
        )
        assert "src/bob3/**" in prompt
        assert "foo" in prompt
        assert "bar" in prompt
        assert "Do NOT speculate" in prompt
        # Ticket-shaped content must not appear (no "implement", no feature IDs)
        assert "implement the feature" not in prompt.lower()
