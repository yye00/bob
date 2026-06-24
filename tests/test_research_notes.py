"""Tests for bob3.research_notes.generate_research_notes (BF-2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestGenerateResearchNotesBasic:
    """Core behaviour of generate_research_notes."""

    def test_returns_dict(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes()
        assert isinstance(result, dict)

    def test_hide_intent_always_true(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes()
        assert result["hide_intent"] is True

    def test_researcher_role_name(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes()
        assert result["researcher_role"] == "researcher"

    def test_no_args_output_path_empty(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes()
        assert result["output_path"] == ""

    def test_no_args_cache_hit_false(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes()
        assert result["cache_hit"] is False

    def test_no_args_written_false(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes()
        assert result["written"] is False

    def test_no_args_prompt_empty(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes()
        assert result["researcher_prompt"] == ""

    def test_symbol_shortlist_defaults_to_empty_list(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes()
        assert result["symbol_shortlist"] == []


class TestGenerateResearchNotesWithPathGlob:
    """generate_research_notes builds prompt when path_glob provided."""

    def test_prompt_includes_path_glob(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes(path_glob="src/bob3/**")
        assert "src/bob3/**" in result["researcher_prompt"]

    def test_prompt_includes_symbols(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes(
            path_glob="src/bob3/**", symbol_shortlist=["Coordinator", "dispatch_slot"]
        )
        assert "Coordinator" in result["researcher_prompt"]
        assert "dispatch_slot" in result["researcher_prompt"]

    def test_prompt_excludes_intent_text(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes(path_glob="src/bob3/**")
        # hide-the-ticket: the prompt must not contain a typical intent phrase
        assert "add a feature" not in result["researcher_prompt"]

    def test_path_glob_returned(self):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes(path_glob="src/brownfield/**")
        assert result["path_glob"] == "src/brownfield/**"


class TestGenerateResearchNotesFileWrite:
    """generate_research_notes writes notes when feature_id + content given."""

    def test_writes_file_when_content_and_feature_id(self, tmp_path):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes(
            feature_id="feat-write",
            path_glob="src/**",
            survey_sha="abc123",
            content="This module does X.",
            workspace=tmp_path,
        )
        assert result["written"] is True
        notes_file = tmp_path / ".bob3" / "features" / "feat-write" / "research_notes.md"
        assert notes_file.exists()
        text = notes_file.read_text()
        assert "This module does X." in text

    def test_file_contains_frontmatter(self, tmp_path):
        from bob3.research_notes import generate_research_notes
        generate_research_notes(
            feature_id="feat-front",
            survey_sha="sha999",
            path_glob="src/bob3/**",
            content="Findings here.",
            workspace=tmp_path,
        )
        notes_file = tmp_path / ".bob3" / "features" / "feat-front" / "research_notes.md"
        text = notes_file.read_text()
        assert "survey_sha: sha999" in text
        assert "path_glob: src/bob3/**" in text

    def test_output_path_contains_feature_id(self, tmp_path):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes(feature_id="feat-path", workspace=tmp_path)
        assert "feat-path" in result["output_path"]

    def test_no_write_without_content(self, tmp_path):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes(
            feature_id="feat-nocontent",
            path_glob="src/**",
            survey_sha="sha1",
            content="",
            workspace=tmp_path,
        )
        assert result["written"] is False

    def test_no_write_without_feature_id(self, tmp_path):
        from bob3.research_notes import generate_research_notes
        result = generate_research_notes(
            feature_id="",
            path_glob="src/**",
            survey_sha="sha1",
            content="Some content.",
            workspace=tmp_path,
        )
        assert result["written"] is False


class TestGenerateResearchNotesCaching:
    """Caching behaviour: same survey_sha + path_glob => cache_hit."""

    def test_cache_hit_when_notes_exist(self, tmp_path):
        from bob3.research_notes import generate_research_notes
        # Write once
        generate_research_notes(
            feature_id="feat-cache",
            survey_sha="sha-fixed",
            path_glob="src/bob3/**",
            content="Initial notes.",
            workspace=tmp_path,
        )
        # Second call — same sha + glob => cache hit
        result = generate_research_notes(
            feature_id="feat-cache",
            survey_sha="sha-fixed",
            path_glob="src/bob3/**",
            content="Updated notes.",
            workspace=tmp_path,
        )
        assert result["cache_hit"] is True
        assert result["written"] is False  # not re-written on cache hit

    def test_no_cache_hit_when_sha_changes(self, tmp_path):
        from bob3.research_notes import generate_research_notes
        generate_research_notes(
            feature_id="feat-newsha",
            survey_sha="sha-v1",
            path_glob="src/**",
            content="V1 notes.",
            workspace=tmp_path,
        )
        result = generate_research_notes(
            feature_id="feat-newsha",
            survey_sha="sha-v2",
            path_glob="src/**",
            content="V2 notes.",
            workspace=tmp_path,
        )
        assert result["cache_hit"] is False
        assert result["written"] is True


class TestGenerateResearchNotesErrorPaths:
    """Error handling in generate_research_notes."""

    def test_invalid_symbol_type_raises_value_error(self):
        from bob3.research_notes import generate_research_notes
        with pytest.raises(ValueError):
            generate_research_notes(symbol_shortlist=[1, 2, 3])  # type: ignore[list-item]

    def test_invalid_workspace_type_raises(self):
        from bob3.research_notes import generate_research_notes
        with pytest.raises((TypeError, AttributeError, OSError)):
            generate_research_notes(feature_id="x", workspace=99)  # type: ignore[arg-type]
