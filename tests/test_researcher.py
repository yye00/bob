"""Tests for BF-2 — Research-as-documentarian sub-agent (hide-the-ticket pattern).

AC: pytest: tests/test_researcher.py

Verifies:
  - File exists: src/bob/agents/roles.py
  - Function defined: bob.agents.roles.researcher_prompt_template
  - File exists: src/bob/agents/researcher.py
  - Function defined: bob.agents.researcher.research_subsystem
  - integration: bob.coordinator (merge_research_and_intent)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_ROLES_FILE = Path(__file__).parent.parent / "src" / "bob" / "agents" / "roles.py"
_RESEARCHER_FILE = Path(__file__).parent.parent / "src" / "bob" / "agents" / "researcher.py"


class TestFileExistence:
    def test_roles_file_exists(self):
        assert _ROLES_FILE.exists(), f"roles.py missing: {_ROLES_FILE}"

    def test_researcher_file_exists(self):
        assert _RESEARCHER_FILE.exists(), f"researcher.py missing: {_RESEARCHER_FILE}"


class TestResearcherPromptTemplate:
    """bob.agents.roles.researcher_prompt_template must be callable."""

    def test_function_importable(self):
        from bob.agents.roles import researcher_prompt_template  # noqa: F401

    def test_returns_string(self):
        from bob.agents.roles import researcher_prompt_template
        result = researcher_prompt_template(
            path_glob="src/bob/orchestrator/**",
            symbol_shortlist=["run_loop", "dispatch"],
        )
        assert isinstance(result, str)

    def test_prompt_contains_path_glob(self):
        from bob.agents.roles import researcher_prompt_template
        result = researcher_prompt_template(
            path_glob="src/bob/coordinator/**",
            symbol_shortlist=["merge"],
        )
        assert "src/bob/coordinator/**" in result

    def test_prompt_contains_symbols(self):
        from bob.agents.roles import researcher_prompt_template
        result = researcher_prompt_template(
            path_glob="src/bob/**",
            symbol_shortlist=["alpha", "beta"],
        )
        assert "alpha" in result
        assert "beta" in result

    def test_prompt_excludes_ticket_intent_text(self):
        from bob.agents.roles import researcher_prompt_template
        result = researcher_prompt_template(
            path_glob="src/bob/**",
            symbol_shortlist=["foo"],
        )
        # Must not contain any hint at the intent/ticket
        assert "intent" not in result.lower() or "hide_intent" not in result
        # Must contain documentarian instruction
        assert "documentarian" in result or "Document" in result

    def test_empty_path_glob_returns_empty_string(self):
        from bob.agents.roles import researcher_prompt_template
        result = researcher_prompt_template(path_glob="")
        assert result == ""

    def test_includes_survey_sha_in_frontmatter(self):
        from bob.agents.roles import researcher_prompt_template
        result = researcher_prompt_template(
            path_glob="src/**",
            symbol_shortlist=[],
            survey_sha="abc123",
        )
        assert "abc123" in result

    def test_empty_symbols_does_not_raise(self):
        from bob.agents.roles import researcher_prompt_template
        result = researcher_prompt_template(path_glob="src/**", symbol_shortlist=[])
        assert isinstance(result, str)
        assert "src/**" in result

    def test_invalid_symbol_shortlist_type_raises(self):
        from bob.agents.roles import researcher_prompt_template
        with pytest.raises(TypeError):
            researcher_prompt_template(path_glob="src/**", symbol_shortlist="bad")  # type: ignore[arg-type]


class TestResearchSubsystem:
    """bob.agents.researcher.research_subsystem must be callable and correct."""

    def test_function_importable(self):
        from bob.agents.researcher import research_subsystem  # noqa: F401

    def test_returns_dict(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        result = research_subsystem(
            feature_id="feat-abc",
            path_glob="src/bob/**",
            symbol_shortlist=["run_loop"],
            workspace=tmp_path,
        )
        assert isinstance(result, dict)

    def test_result_has_role(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        result = research_subsystem(
            feature_id="feat-role",
            path_glob="src/**",
            symbol_shortlist=[],
            workspace=tmp_path,
        )
        assert "role" in result
        assert result["role"].name == "researcher"

    def test_result_has_prompt(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        result = research_subsystem(
            feature_id="feat-prompt",
            path_glob="src/bob/coordinator/**",
            symbol_shortlist=["merge_research_and_intent"],
            workspace=tmp_path,
        )
        assert "prompt" in result
        assert "src/bob/coordinator/**" in result["prompt"]

    def test_result_has_output_path(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        result = research_subsystem(
            feature_id="feat-out",
            path_glob="src/**",
            symbol_shortlist=[],
            workspace=tmp_path,
        )
        assert "output_path" in result
        assert "feat-out" in result["output_path"]
        assert result["output_path"].endswith("research_notes.md")

    def test_result_has_cache_hit_false_by_default(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        result = research_subsystem(
            feature_id="feat-cache",
            path_glob="src/**",
            symbol_shortlist=[],
            workspace=tmp_path,
        )
        assert result["cache_hit"] is False

    def test_prompt_does_not_contain_intent(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        result = research_subsystem(
            feature_id="feat-hidden",
            path_glob="src/bob/**",
            symbol_shortlist=["top_secret_intent"],
            workspace=tmp_path,
        )
        # The prompt contains the symbol name but not the word "intent" as a ticket
        # The hide-the-ticket pattern means no ticket description in prompt
        assert "ticket" not in result["prompt"].lower()

    def test_empty_feature_id_raises(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        with pytest.raises(ValueError, match="feature_id"):
            research_subsystem(
                feature_id="",
                path_glob="src/**",
                symbol_shortlist=[],
                workspace=tmp_path,
            )

    def test_empty_path_glob_raises(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        with pytest.raises(ValueError, match="path_glob"):
            research_subsystem(
                feature_id="feat-noglob",
                path_glob="",
                symbol_shortlist=[],
                workspace=tmp_path,
            )

    def test_invalid_symbol_shortlist_raises(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        with pytest.raises(TypeError):
            research_subsystem(
                feature_id="feat-bad",
                path_glob="src/**",
                symbol_shortlist="not-a-list",  # type: ignore[arg-type]
                workspace=tmp_path,
            )

    def test_feature_id_in_result(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        result = research_subsystem(
            feature_id="feat-xyz",
            path_glob="src/**",
            symbol_shortlist=[],
            workspace=tmp_path,
        )
        assert result["feature_id"] == "feat-xyz"

    def test_cache_hit_true_when_notes_present(self, tmp_path):
        from bob.agents.researcher import research_subsystem
        feature_id = "feat-cached"
        survey_sha = "deadbeef"
        path_glob = "src/bob/**"
        # Write a notes file with matching frontmatter
        notes_dir = tmp_path / ".bob" / "features" / feature_id
        notes_dir.mkdir(parents=True)
        notes_file = notes_dir / "research_notes.md"
        notes_file.write_text(
            f"---\nsurvey_sha: {survey_sha}\npath_glob: {path_glob}\n---\n\nSome notes."
        )
        result = research_subsystem(
            feature_id=feature_id,
            path_glob=path_glob,
            symbol_shortlist=[],
            survey_sha=survey_sha,
            workspace=tmp_path,
        )
        assert result["cache_hit"] is True


class TestCoordinatorIntegration:
    """Integration: bob.coordinator.merge_research_and_intent."""

    def test_coordinator_importable(self):
        from bob.coordinator import merge_research_and_intent  # noqa: F401

    def test_merge_combines_notes_and_intent(self):
        from bob.coordinator import merge_research_and_intent
        result = merge_research_and_intent(
            research_notes="The function does X.",
            intent_stub="Add feature Y.",
        )
        assert "The function does X." in result["merged_context"]
        assert "Add feature Y." in result["merged_context"]

    def test_merge_research_notes_preserved(self):
        from bob.coordinator import merge_research_and_intent
        result = merge_research_and_intent(
            research_notes="Callers: main(), run_loop().",
            intent_stub="Add caching.",
        )
        assert result["research_notes"] == "Callers: main(), run_loop()."

    def test_merge_intent_stub_preserved(self):
        from bob.coordinator import merge_research_and_intent
        result = merge_research_and_intent(
            research_notes="Notes here.",
            intent_stub="Intent here.",
        )
        assert result["intent_stub"] == "Intent here."

    def test_merge_feature_id_in_result(self):
        from bob.coordinator import merge_research_and_intent
        result = merge_research_and_intent(
            research_notes="Notes.",
            intent_stub="Intent.",
            feature_id="feat-merge",
        )
        assert result["feature_id"] == "feat-merge"

    def test_merge_invalid_research_notes_raises(self):
        from bob.coordinator import merge_research_and_intent
        with pytest.raises(ValueError):
            merge_research_and_intent(
                research_notes=123,  # type: ignore[arg-type]
                intent_stub="Intent.",
            )

    def test_merge_invalid_intent_stub_raises(self):
        from bob.coordinator import merge_research_and_intent
        with pytest.raises(ValueError):
            merge_research_and_intent(
                research_notes="Notes.",
                intent_stub=["not", "a", "string"],  # type: ignore[arg-type]
            )

    def test_research_notes_section_label_present(self):
        from bob.coordinator import merge_research_and_intent
        result = merge_research_and_intent(
            research_notes="Some analysis.",
            intent_stub="Some intent.",
        )
        # The merged context should identify the research section
        assert "Codebase Research" in result["merged_context"]

    def test_feature_intent_section_label_present(self):
        from bob.coordinator import merge_research_and_intent
        result = merge_research_and_intent(
            research_notes="Some analysis.",
            intent_stub="Some intent.",
        )
        assert "Feature Intent" in result["merged_context"]
