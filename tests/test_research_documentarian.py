"""Tests for bob.research_documentarian.document_subsystem (BF-2).

Verifies the hide-the-ticket documentarian protocol:
  - The researcher never sees intent text (hide_intent=True)
  - Prompt is built from path_glob + symbol_shortlist only
  - Cache check fires when survey_sha + path_glob are both present
  - Output path is derived from feature_id
  - Invalid workspace raises TypeError
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestDocumentSubsystemBasic:
    """Core happy-path behaviour."""

    def test_returns_dict(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem()
        assert isinstance(result, dict)

    def test_hide_intent_always_true(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem(
            feature_id="feat-1",
            path_glob="src/**",
            symbol_shortlist=["foo"],
        )
        assert result["hide_intent"] is True

    def test_researcher_role_name(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem()
        assert result["researcher_role"] == "researcher"

    def test_protocol_steps_non_empty_list(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem()
        steps = result["protocol_steps"]
        assert isinstance(steps, list)
        assert len(steps) >= 5

    def test_no_args_prompt_empty(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem()
        assert result["researcher_prompt"] == ""

    def test_no_args_cache_hit_false(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem()
        assert result["cache_hit"] is False

    def test_no_args_output_path_empty(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem()
        assert result["output_path"] == ""


class TestDocumentSubsystemPrompt:
    """Prompt contains path_glob and symbols — never intent text."""

    def test_prompt_contains_path_glob(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem(path_glob="src/bob/orchestrator/**")
        assert "src/bob/orchestrator/**" in result["researcher_prompt"]

    def test_prompt_contains_symbol(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem(
            path_glob="src/**",
            symbol_shortlist=["my_func", "MyClass"],
        )
        prompt = result["researcher_prompt"]
        assert "my_func" in prompt
        assert "MyClass" in prompt

    def test_prompt_instructs_no_speculation(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem(path_glob="src/**")
        assert "speculate" in result["researcher_prompt"].lower()

    def test_empty_path_glob_yields_empty_prompt(self):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem(path_glob="", symbol_shortlist=["sym"])
        assert result["researcher_prompt"] == ""


class TestDocumentSubsystemOutputPath:
    """Output path is derived from feature_id."""

    def test_feature_id_appears_in_output_path(self, tmp_path):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem(feature_id="feat-abc", workspace=tmp_path)
        assert "feat-abc" in result["output_path"]

    def test_output_path_ends_with_research_notes(self, tmp_path):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem(feature_id="feat-xyz", workspace=tmp_path)
        assert result["output_path"].endswith("research_notes.md")

    def test_empty_feature_id_gives_empty_output_path(self, tmp_path):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem(feature_id="", workspace=tmp_path)
        assert result["output_path"] == ""


class TestDocumentSubsystemCache:
    """Cache hit fires when notes file exists with matching frontmatter."""

    def test_cache_miss_when_no_file(self, tmp_path):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem(
            feature_id="feat-nocache",
            survey_sha="abc123",
            path_glob="src/**",
            workspace=tmp_path,
        )
        assert result["cache_hit"] is False

    def test_cache_hit_when_notes_match(self, tmp_path):
        from bob.research_documentarian import document_subsystem
        # Pre-populate notes file with matching frontmatter
        notes_dir = tmp_path / ".bob" / "features" / "feat-cached"
        notes_dir.mkdir(parents=True)
        notes_file = notes_dir / "research_notes.md"
        notes_file.write_text(
            "---\nsurvey_sha: sha999\npath_glob: src/**\n---\nSome notes.\n"
        )
        result = document_subsystem(
            feature_id="feat-cached",
            survey_sha="sha999",
            path_glob="src/**",
            workspace=tmp_path,
        )
        assert result["cache_hit"] is True

    def test_cache_miss_when_sha_differs(self, tmp_path):
        from bob.research_documentarian import document_subsystem
        notes_dir = tmp_path / ".bob" / "features" / "feat-stale"
        notes_dir.mkdir(parents=True)
        notes_file = notes_dir / "research_notes.md"
        notes_file.write_text(
            "---\nsurvey_sha: old_sha\npath_glob: src/**\n---\nStale.\n"
        )
        result = document_subsystem(
            feature_id="feat-stale",
            survey_sha="new_sha",
            path_glob="src/**",
            workspace=tmp_path,
        )
        assert result["cache_hit"] is False

    def test_no_cache_check_when_sha_empty(self, tmp_path):
        from bob.research_documentarian import document_subsystem
        result = document_subsystem(
            feature_id="feat-nosha",
            survey_sha="",
            path_glob="src/**",
            workspace=tmp_path,
        )
        assert result["cache_hit"] is False


class TestDocumentSubsystemErrorPaths:
    """Invalid inputs raise appropriate errors."""

    def test_invalid_workspace_type_raises(self):
        from bob.research_documentarian import document_subsystem
        with pytest.raises((TypeError, AttributeError, OSError)):
            document_subsystem(feature_id="feat-bad", workspace=12345)  # type: ignore[arg-type]

    def test_symbol_shortlist_string_raises(self):
        from bob.research_documentarian import document_subsystem
        # build_researcher_prompt is called with path_glob set; passing a str
        # for symbol_shortlist must propagate TypeError from build_researcher_prompt
        with pytest.raises(TypeError):
            document_subsystem(
                path_glob="src/**",
                symbol_shortlist="not_a_list",  # type: ignore[arg-type]
            )


class TestCoordinatorIntegration:
    """document_subsystem result integrates with coordinator.merge_research_and_intent."""

    def test_merge_uses_document_subsystem_output(self):
        from bob.research_documentarian import document_subsystem
        from bob.coordinator import merge_research_and_intent

        ds_result = document_subsystem(
            feature_id="feat-integ",
            path_glob="src/bob/**",
            symbol_shortlist=["my_fn"],
        )

        merged = merge_research_and_intent(
            research_notes="These are the docs.",
            intent_stub="Add feature X.",
            feature_id=ds_result["feature_id"],
        )

        assert "These are the docs." in merged["merged_context"]
        assert "Add feature X." in merged["merged_context"]
        assert merged["feature_id"] == "feat-integ"
