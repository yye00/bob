"""Tests for bob3.agents.roles — researcher role and related helpers.

Covers:
- Role dataclass fields and invariants
- researcher() callable returns RESEARCHER
- researcher_prompt() builds prompt or returns empty string
- build_researcher_prompt() prompt content
- research_notes_path() path construction
- should_skip_research() cache logic
- get_role() registry lookup
- all_roles() returns all three roles
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


class TestResearcherRoleConstants:
    """RESEARCHER role descriptor must have correct field values."""

    def test_researcher_name(self):
        from bob3.agents.roles import RESEARCHER
        assert RESEARCHER.name == "researcher"

    def test_researcher_hide_intent(self):
        from bob3.agents.roles import RESEARCHER
        assert RESEARCHER.hide_intent is True

    def test_researcher_output_key(self):
        from bob3.agents.roles import RESEARCHER
        assert RESEARCHER.output_key == "research_notes"

    def test_researcher_cacheable(self):
        from bob3.agents.roles import RESEARCHER
        assert RESEARCHER.cacheable is True

    def test_researcher_description_nonempty(self):
        from bob3.agents.roles import RESEARCHER
        assert len(RESEARCHER.description) > 0

    def test_researcher_description_no_speculate(self):
        from bob3.agents.roles import RESEARCHER
        assert "speculate" in RESEARCHER.description.lower()


class TestResearcherCallable:
    """researcher() must return the RESEARCHER Role singleton."""

    def test_returns_researcher_role(self):
        from bob3.agents.roles import researcher, RESEARCHER
        role = researcher()
        assert role is RESEARCHER

    def test_with_path_glob_still_returns_researcher(self):
        from bob3.agents.roles import researcher, RESEARCHER
        role = researcher(path_glob="src/**")
        assert role is RESEARCHER

    def test_with_symbol_shortlist_still_returns_researcher(self):
        from bob3.agents.roles import researcher, RESEARCHER
        role = researcher(symbol_shortlist=["foo", "bar"])
        assert role is RESEARCHER

    def test_hide_intent_is_true(self):
        from bob3.agents.roles import researcher
        role = researcher()
        assert role.hide_intent is True


class TestResearcherPromptFunction:
    """researcher_prompt() must build or return empty string."""

    def test_empty_path_glob_returns_empty(self):
        from bob3.agents.roles import researcher_prompt
        result = researcher_prompt()
        assert result == ""

    def test_with_path_glob_returns_nonempty(self):
        from bob3.agents.roles import researcher_prompt
        result = researcher_prompt(path_glob="src/bob3/**")
        assert len(result) > 0

    def test_path_glob_in_prompt(self):
        from bob3.agents.roles import researcher_prompt
        result = researcher_prompt(path_glob="src/mymodule/**")
        assert "src/mymodule/**" in result

    def test_symbol_in_prompt(self):
        from bob3.agents.roles import researcher_prompt
        result = researcher_prompt(path_glob="src/**", symbol_shortlist=["my_func"])
        assert "my_func" in result

    def test_no_intent_text_in_prompt(self):
        from bob3.agents.roles import researcher_prompt
        result = researcher_prompt(path_glob="src/**", symbol_shortlist=["sym"])
        # The prompt must NOT include ticket/intent text; verify key constraint phrase
        assert "Do NOT speculate" in result

    def test_empty_symbol_list_ok(self):
        from bob3.agents.roles import researcher_prompt
        result = researcher_prompt(path_glob="src/**", symbol_shortlist=[])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_none_symbol_list_ok(self):
        from bob3.agents.roles import researcher_prompt
        result = researcher_prompt(path_glob="src/**", symbol_shortlist=None)
        assert isinstance(result, str)
        assert len(result) > 0


class TestBuildResearcherPrompt:
    """build_researcher_prompt() core behavior."""

    def test_path_glob_in_output(self):
        from bob3.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt("src/bob3/**", [])
        assert "src/bob3/**" in prompt

    def test_symbol_in_output(self):
        from bob3.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt("src/**", ["run_loop", "dispatch"])
        assert "run_loop" in prompt
        assert "dispatch" in prompt

    def test_frontmatter_instruction(self):
        from bob3.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt("src/**", [])
        assert "research_notes.md" in prompt

    def test_documentarian_instruction(self):
        from bob3.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt("src/**", [])
        assert "documentarian" in prompt.lower()

    def test_type_error_on_bad_symbol_list(self):
        from bob3.agents.roles import build_researcher_prompt
        with pytest.raises(TypeError):
            build_researcher_prompt("src/**", "not_a_list")  # type: ignore[arg-type]


class TestResearchNotesPath:
    """research_notes_path() constructs correct paths."""

    def test_returns_path_object(self, tmp_path):
        from bob3.agents.roles import research_notes_path
        result = research_notes_path("feat-abc", tmp_path)
        assert isinstance(result, Path)

    def test_filename_is_research_notes_md(self, tmp_path):
        from bob3.agents.roles import research_notes_path
        result = research_notes_path("feat-abc", tmp_path)
        assert result.name == "research_notes.md"

    def test_feature_id_in_path(self, tmp_path):
        from bob3.agents.roles import research_notes_path
        result = research_notes_path("my-feature-id", tmp_path)
        assert "my-feature-id" in str(result)

    def test_dot_bob3_in_path(self, tmp_path):
        from bob3.agents.roles import research_notes_path
        result = research_notes_path("feat-abc", tmp_path)
        assert ".bob3" in str(result)

    def test_str_workspace_works(self, tmp_path):
        from bob3.agents.roles import research_notes_path
        result = research_notes_path("feat-str", str(tmp_path))
        assert result.name == "research_notes.md"

    def test_none_workspace_works(self):
        from bob3.agents.roles import research_notes_path
        result = research_notes_path("feat-none", None)
        assert result.name == "research_notes.md"


class TestShouldSkipResearch:
    """should_skip_research() cache hit/miss logic."""

    def test_no_file_returns_false(self, tmp_path):
        from bob3.agents.roles import should_skip_research
        assert should_skip_research("feat-x", "sha123", "src/**", tmp_path) is False

    def test_matching_sha_and_glob_returns_true(self, tmp_path):
        from bob3.agents.roles import should_skip_research, research_notes_path
        notes = research_notes_path("feat-cache", tmp_path)
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text(
            "---\nsurvey_sha: abc\npath_glob: src/**\n---\n\nContent here.",
            encoding="utf-8",
        )
        assert should_skip_research("feat-cache", "abc", "src/**", tmp_path) is True

    def test_different_sha_returns_false(self, tmp_path):
        from bob3.agents.roles import should_skip_research, research_notes_path
        notes = research_notes_path("feat-sha", tmp_path)
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text(
            "---\nsurvey_sha: sha-old\npath_glob: src/**\n---\n",
            encoding="utf-8",
        )
        assert should_skip_research("feat-sha", "sha-new", "src/**", tmp_path) is False

    def test_different_glob_returns_false(self, tmp_path):
        from bob3.agents.roles import should_skip_research, research_notes_path
        notes = research_notes_path("feat-glob", tmp_path)
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text(
            "---\nsurvey_sha: sha\npath_glob: src/old/**\n---\n",
            encoding="utf-8",
        )
        assert should_skip_research("feat-glob", "sha", "src/new/**", tmp_path) is False


class TestRoleRegistry:
    """get_role() and all_roles() registry correctness."""

    def test_get_role_researcher(self):
        from bob3.agents.roles import get_role, RESEARCHER
        assert get_role("researcher") is RESEARCHER

    def test_get_role_implementer(self):
        from bob3.agents.roles import get_role, IMPLEMENTER
        assert get_role("implementer") is IMPLEMENTER

    def test_get_role_verifier(self):
        from bob3.agents.roles import get_role, VERIFIER
        assert get_role("verifier") is VERIFIER

    def test_get_role_unknown_raises(self):
        from bob3.agents.roles import get_role
        with pytest.raises(KeyError):
            get_role("unknown_role")

    def test_all_roles_returns_three(self):
        from bob3.agents.roles import all_roles
        roles = all_roles()
        assert len(roles) == 3

    def test_all_roles_includes_researcher(self):
        from bob3.agents.roles import all_roles, RESEARCHER
        assert RESEARCHER in all_roles()


class TestOrchestratorIntegration:
    """Verify bob3.agents.roles integrates with orchestrator coordinator."""

    def test_coordinator_import(self):
        from bob3.coordinator import merge_research_and_intent
        assert callable(merge_research_and_intent)

    def test_merge_research_and_intent_basic(self):
        from bob3.coordinator import merge_research_and_intent
        result = merge_research_and_intent(
            "The code does X.", "Add feature Y."
        )
        assert "merged_context" in result
        assert "The code does X." in result["merged_context"]
        assert "Add feature Y." in result["merged_context"]

    def test_researcher_hide_intent_enforced_in_roles(self):
        from bob3.agents.roles import RESEARCHER
        assert RESEARCHER.hide_intent is True

    def test_researcher_prompt_excludes_intent(self):
        from bob3.agents.roles import researcher_prompt
        prompt = researcher_prompt(
            path_glob="src/bob3/orchestrator/**",
            symbol_shortlist=["run_loop"],
        )
        # Intent text must not appear in researcher prompt
        assert "ticket" not in prompt.lower() or "Do NOT" in prompt
        assert "Do NOT speculate" in prompt
