"""Tests for the researcher agent role and prompt template (BF-2).

Verifies:
  - src/bob/agents/roles.py defines RESEARCHER with correct attributes
  - bob.agents.roles.researcher function/constant is importable
  - src/bob/agents/prompts/researcher.txt exists and contains required content
  - researcher prompt template excludes intent/ticket content
  - researcher prompt template includes subsystem placeholders
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

PROMPTS_DIR = Path(__file__).parent.parent / "src" / "bob" / "agents" / "prompts"
RESEARCHER_PROMPT_FILE = PROMPTS_DIR / "researcher.txt"


class TestResearcherRoleFile:
    def test_roles_file_exists(self):
        roles_file = Path(__file__).parent.parent / "src" / "bob" / "agents" / "roles.py"
        assert roles_file.exists(), f"roles.py missing: {roles_file}"

    def test_researcher_importable(self):
        from bob.agents.roles import RESEARCHER
        assert RESEARCHER is not None

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

    def test_get_role_returns_researcher(self):
        from bob.agents.roles import get_role
        role = get_role("researcher")
        assert role.name == "researcher"
        assert role.hide_intent is True

    def test_all_roles_includes_researcher(self):
        from bob.agents.roles import all_roles
        names = [r.name for r in all_roles()]
        assert "researcher" in names


class TestResearcherPromptFile:
    def test_prompt_file_exists(self):
        assert RESEARCHER_PROMPT_FILE.exists(), (
            f"Prompt template missing: {RESEARCHER_PROMPT_FILE}"
        )

    def test_prompt_file_contains_path_glob_placeholder(self):
        content = RESEARCHER_PROMPT_FILE.read_text(encoding="utf-8")
        assert "{path_glob}" in content

    def test_prompt_file_contains_symbols_block_placeholder(self):
        content = RESEARCHER_PROMPT_FILE.read_text(encoding="utf-8")
        assert "{symbols_block}" in content

    def test_prompt_file_contains_documentarian_instruction(self):
        content = RESEARCHER_PROMPT_FILE.read_text(encoding="utf-8")
        assert "Do NOT speculate" in content

    def test_prompt_file_excludes_implement_instruction(self):
        content = RESEARCHER_PROMPT_FILE.read_text(encoding="utf-8")
        assert "implement" not in content.lower() or "do not implement" in content.lower()

    def test_prompt_file_references_research_notes(self):
        content = RESEARCHER_PROMPT_FILE.read_text(encoding="utf-8")
        assert "research_notes" in content

    def test_prompt_file_references_yaml_frontmatter(self):
        content = RESEARCHER_PROMPT_FILE.read_text(encoding="utf-8")
        assert "survey_sha" in content


class TestBuildResearcherPrompt:
    def test_build_prompt_with_glob(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(
            path_glob="src/bob/orchestrator/**",
            symbol_shortlist=["run_loop", "dispatch"],
        )
        assert "src/bob/orchestrator/**" in prompt
        assert "run_loop" in prompt
        assert "dispatch" in prompt
        assert "Do NOT speculate" in prompt

    def test_build_prompt_empty_symbols(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(
            path_glob="src/bob/**",
            symbol_shortlist=[],
        )
        assert "src/bob/**" in prompt
        assert "Do NOT speculate" in prompt

    def test_build_prompt_no_intent_text(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(
            path_glob="src/bob/agents/**",
            symbol_shortlist=["RESEARCHER"],
        )
        assert "implement the feature" not in prompt.lower()
        assert "ticket" not in prompt.lower()
        assert "intent" not in prompt.lower()

    def test_build_prompt_contains_frontmatter_hint(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(
            path_glob="src/**",
            symbol_shortlist=[],
        )
        assert "survey_sha" in prompt
        assert "path_glob" in prompt


class TestResearchNotesPath:
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


class TestShouldSkipResearch:
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
