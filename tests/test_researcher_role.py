"""Tests for bob.agents.roles.researcher (BF-2 — hide-the-ticket pattern).

AC: pytest: tests/test_researcher_role.py

Verifies the researcher role and its integration with the coordinator:
  - RESEARCHER role has correct attributes (hide_intent=True, cacheable=True)
  - researcher() callable is importable from bob.agents.roles
  - researcher() returns the RESEARCHER Role instance
  - research_notes_path() produces the canonical .bob/features/<id>/research_notes.md path
  - should_skip_research() correctly detects cache hits and misses
  - build_researcher_prompt() produces a prompt with no ticket/intent text
  - Coordinator integration: merge_research_and_intent() merges notes + intent for implementer
  - Orchestrator integration: roles module accessible from orchestrator layer
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# researcher() callable — AC: Function defined: bob.agents.roles.researcher
# ---------------------------------------------------------------------------


class TestResearcherCallable:
    """The researcher() function must be importable and return RESEARCHER."""

    def test_researcher_importable(self):
        from bob.agents.roles import researcher
        assert callable(researcher)

    def test_researcher_returns_role(self):
        from bob.agents.roles import researcher, RESEARCHER
        role = researcher()
        assert role is RESEARCHER

    def test_researcher_with_path_glob_returns_researcher_role(self):
        from bob.agents.roles import researcher, RESEARCHER
        role = researcher(path_glob="src/bob/**")
        assert role is RESEARCHER

    def test_researcher_with_symbol_shortlist_returns_researcher_role(self):
        from bob.agents.roles import researcher, RESEARCHER
        role = researcher(symbol_shortlist=["foo", "bar"])
        assert role is RESEARCHER

    def test_researcher_with_all_args_returns_researcher_role(self):
        from bob.agents.roles import researcher, RESEARCHER
        role = researcher(path_glob="src/**", symbol_shortlist=["x"])
        assert role is RESEARCHER


# ---------------------------------------------------------------------------
# RESEARCHER role attributes
# ---------------------------------------------------------------------------


class TestResearcherRoleAttributes:
    """RESEARCHER must have hide_intent=True (core constraint of BF-2)."""

    def test_researcher_name(self):
        from bob.agents.roles import RESEARCHER
        assert RESEARCHER.name == "researcher"

    def test_researcher_hide_intent_true(self):
        from bob.agents.roles import RESEARCHER
        assert RESEARCHER.hide_intent is True

    def test_researcher_cacheable_true(self):
        from bob.agents.roles import RESEARCHER
        assert RESEARCHER.cacheable is True

    def test_researcher_output_key(self):
        from bob.agents.roles import RESEARCHER
        assert RESEARCHER.output_key == "research_notes"

    def test_researcher_description_no_speculation(self):
        from bob.agents.roles import RESEARCHER
        assert "Do NOT speculate" in RESEARCHER.description

    def test_researcher_is_frozen(self):
        from bob.agents.roles import RESEARCHER
        with pytest.raises((AttributeError, TypeError)):
            RESEARCHER.hide_intent = False  # type: ignore[misc]

    def test_get_role_returns_researcher(self):
        from bob.agents.roles import get_role
        role = get_role("researcher")
        assert role.name == "researcher"
        assert role.hide_intent is True

    def test_all_roles_includes_researcher(self):
        from bob.agents.roles import all_roles
        names = [r.name for r in all_roles()]
        assert "researcher" in names


# ---------------------------------------------------------------------------
# research_notes_path()
# ---------------------------------------------------------------------------


class TestResearchNotesPath:
    """Canonical path for research_notes.md must follow convention."""

    def test_path_structure(self, tmp_path):
        from bob.agents.roles import research_notes_path
        path = research_notes_path("my-feature-id", tmp_path)
        assert path.name == "research_notes.md"
        assert "my-feature-id" in str(path)
        assert ".bob" in str(path)
        assert "features" in str(path)

    def test_path_absolute(self, tmp_path):
        from bob.agents.roles import research_notes_path
        path = research_notes_path("feat-abc", tmp_path)
        assert path.is_absolute()

    def test_path_with_string_workspace(self, tmp_path):
        from bob.agents.roles import research_notes_path
        path = research_notes_path("feat-str", str(tmp_path))
        assert path.name == "research_notes.md"

    def test_path_with_none_workspace(self):
        from bob.agents.roles import research_notes_path
        path = research_notes_path("feat-none", None)
        assert path.name == "research_notes.md"
        assert "feat-none" in str(path)


# ---------------------------------------------------------------------------
# should_skip_research()
# ---------------------------------------------------------------------------


class TestShouldSkipResearch:
    """Cache hit/miss detection for research notes."""

    def test_returns_false_when_no_file(self, tmp_path):
        from bob.agents.roles import should_skip_research
        result = should_skip_research("feat-1", "sha1", "src/**", tmp_path)
        assert result is False

    def test_returns_true_when_cache_matches(self, tmp_path):
        from bob.agents.roles import should_skip_research, research_notes_path
        fid = "feat-cached"
        sha = "abc123"
        glob = "src/bob/**"
        notes = research_notes_path(fid, tmp_path)
        notes.parent.mkdir(parents=True)
        notes.write_text(
            f"---\nsurvey_sha: {sha}\npath_glob: {glob}\n---\n\nContent.\n",
            encoding="utf-8",
        )
        assert should_skip_research(fid, sha, glob, tmp_path) is True

    def test_returns_false_when_sha_differs(self, tmp_path):
        from bob.agents.roles import should_skip_research, research_notes_path
        fid = "feat-sha-miss"
        glob = "src/**"
        notes = research_notes_path(fid, tmp_path)
        notes.parent.mkdir(parents=True)
        notes.write_text(
            f"---\nsurvey_sha: OLD\npath_glob: {glob}\n---\n",
            encoding="utf-8",
        )
        assert should_skip_research(fid, "NEW", glob, tmp_path) is False

    def test_returns_false_when_glob_differs(self, tmp_path):
        from bob.agents.roles import should_skip_research, research_notes_path
        fid = "feat-glob-miss"
        sha = "sha123"
        notes = research_notes_path(fid, tmp_path)
        notes.parent.mkdir(parents=True)
        notes.write_text(
            f"---\nsurvey_sha: {sha}\npath_glob: src/old/**\n---\n",
            encoding="utf-8",
        )
        assert should_skip_research(fid, sha, "src/new/**", tmp_path) is False

    def test_returns_false_for_empty_feature_id(self, tmp_path):
        from bob.agents.roles import should_skip_research
        result = should_skip_research("", "sha", "src/**", tmp_path)
        assert result is False


# ---------------------------------------------------------------------------
# build_researcher_prompt()
# ---------------------------------------------------------------------------


class TestBuildResearcherPrompt:
    """Prompt must include subsystem info but exclude ticket/intent text."""

    def test_prompt_contains_path_glob(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(
            path_glob="src/bob/orchestrator/**",
            symbol_shortlist=["run_loop"],
        )
        assert "src/bob/orchestrator/**" in prompt

    def test_prompt_contains_symbols(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(
            path_glob="src/**",
            symbol_shortlist=["dispatch", "coordinator"],
        )
        assert "dispatch" in prompt
        assert "coordinator" in prompt

    def test_prompt_contains_no_speculation_instruction(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(path_glob="src/**", symbol_shortlist=[])
        assert "Do NOT speculate" in prompt

    def test_prompt_excludes_implement_the_feature(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(path_glob="src/**", symbol_shortlist=[])
        assert "implement the feature" not in prompt.lower()

    def test_prompt_excludes_ticket_or_intent(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(path_glob="src/**", symbol_shortlist=[])
        assert "ticket" not in prompt.lower()
        assert "intent" not in prompt.lower()

    def test_prompt_contains_frontmatter_hint(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(path_glob="src/**", symbol_shortlist=[])
        assert "survey_sha" in prompt

    def test_invalid_symbol_shortlist_raises_type_error(self):
        from bob.agents.roles import build_researcher_prompt
        with pytest.raises(TypeError):
            build_researcher_prompt(
                path_glob="src/**",
                symbol_shortlist="bad",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Integration: coordinator — merge_research_and_intent
# ---------------------------------------------------------------------------


class TestCoordinatorIntegration:
    """The coordinator merges research notes + intent stub for the implementer."""

    def test_merge_returns_dict(self):
        from bob.coordinator import merge_research_and_intent
        result = merge_research_and_intent("Research text.", "Intent text.")
        assert isinstance(result, dict)

    def test_merge_contains_research_notes(self):
        from bob.coordinator import merge_research_and_intent
        result = merge_research_and_intent("Research text.", "Intent text.")
        assert "Research text." in result["merged_context"]

    def test_merge_contains_intent_stub(self):
        from bob.coordinator import merge_research_and_intent
        result = merge_research_and_intent("Research text.", "Intent text.")
        assert "Intent text." in result["merged_context"]

    def test_merge_researcher_never_saw_ticket(self):
        """The research_notes key must be the unmodified documentarian output."""
        from bob.coordinator import merge_research_and_intent
        raw_notes = "Code does X; invariant Y; callers Z."
        result = merge_research_and_intent(raw_notes, "Ticket: add feature W.")
        assert result["research_notes"] == raw_notes

    def test_merge_invalid_research_notes_raises_value_error(self):
        from bob.coordinator import merge_research_and_intent
        with pytest.raises(ValueError):
            merge_research_and_intent(123, "intent")  # type: ignore[arg-type]

    def test_merge_invalid_intent_stub_raises_value_error(self):
        from bob.coordinator import merge_research_and_intent
        with pytest.raises(ValueError):
            merge_research_and_intent("notes", 456)  # type: ignore[arg-type]

    def test_merge_with_feature_id(self):
        from bob.coordinator import merge_research_and_intent
        result = merge_research_and_intent(
            "Notes.", "Intent.", feature_id="feat-xyz"
        )
        assert result["feature_id"] == "feat-xyz"


# ---------------------------------------------------------------------------
# Integration: orchestrator — roles accessible from orchestrator layer
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    """The orchestrator layer must be able to import and use roles."""

    def test_roles_importable_from_agents(self):
        from bob.agents import roles as roles_module
        assert hasattr(roles_module, "RESEARCHER")
        assert hasattr(roles_module, "researcher")
        assert hasattr(roles_module, "get_role")

    def test_orchestrator_can_select_researcher_role(self):
        from bob.agents.roles import get_role
        role = get_role("researcher")
        assert role.hide_intent is True
        assert role.cacheable is True

    def test_researcher_role_not_visible_to_implementer(self):
        """Implementer role has hide_intent=False — the inverse of researcher."""
        from bob.agents.roles import RESEARCHER, IMPLEMENTER
        assert RESEARCHER.hide_intent is True
        assert IMPLEMENTER.hide_intent is False
