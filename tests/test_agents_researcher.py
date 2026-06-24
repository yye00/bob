"""Tests for src/bob3/agents/researcher.py (BF-2 hide-the-ticket pattern).

AC: pytest: tests/test_agents_researcher.py

Verifies:
  - File exists: src/bob3/agents/researcher.py
  - dispatch() returns the correct payload structure
  - Prompt never contains ticket/intent text
  - cache_hit logic delegates correctly to should_skip_research
  - get_role() returns the RESEARCHER Role descriptor
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_SRC_FILE = Path(__file__).parent.parent / "src" / "bob3" / "agents" / "researcher.py"


class TestFileExists:
    def test_source_file_exists(self):
        assert _SRC_FILE.exists(), f"researcher.py missing: {_SRC_FILE}"

    def test_module_importable(self):
        from bob3.agents import researcher  # noqa: F401


class TestGetRole:
    def test_returns_researcher_role(self):
        from bob3.agents.researcher import get_role
        role = get_role()
        assert role.name == "researcher"

    def test_hide_intent_true(self):
        from bob3.agents.researcher import get_role
        role = get_role()
        assert role.hide_intent is True

    def test_cacheable_true(self):
        from bob3.agents.researcher import get_role
        role = get_role()
        assert role.cacheable is True

    def test_output_key_is_research_notes(self):
        from bob3.agents.researcher import get_role
        role = get_role()
        assert role.output_key == "research_notes"


class TestDispatch:
    def test_returns_dict(self, tmp_path):
        from bob3.agents.researcher import dispatch
        result = dispatch(
            feature_id="feat-001",
            path_glob="src/bob3/**",
            symbol_shortlist=["run_loop"],
            workspace=tmp_path,
        )
        assert isinstance(result, dict)

    def test_keys_present(self, tmp_path):
        from bob3.agents.researcher import dispatch
        result = dispatch(
            feature_id="feat-002",
            path_glob="src/**",
            symbol_shortlist=[],
            workspace=tmp_path,
        )
        assert "role" in result
        assert "prompt" in result
        assert "output_path" in result
        assert "cache_hit" in result

    def test_prompt_contains_path_glob(self, tmp_path):
        from bob3.agents.researcher import dispatch
        result = dispatch(
            feature_id="feat-003",
            path_glob="src/bob3/orchestrator/**",
            symbol_shortlist=["dispatch"],
            workspace=tmp_path,
        )
        assert "src/bob3/orchestrator/**" in result["prompt"]

    def test_prompt_contains_symbols(self, tmp_path):
        from bob3.agents.researcher import dispatch
        result = dispatch(
            feature_id="feat-004",
            path_glob="src/**",
            symbol_shortlist=["alpha", "beta"],
            workspace=tmp_path,
        )
        assert "alpha" in result["prompt"]
        assert "beta" in result["prompt"]

    def test_prompt_excludes_ticket_words(self, tmp_path):
        from bob3.agents.researcher import dispatch
        result = dispatch(
            feature_id="feat-005",
            path_glob="src/**",
            symbol_shortlist=[],
            workspace=tmp_path,
        )
        prompt_lower = result["prompt"].lower()
        assert "implement the feature" not in prompt_lower
        assert "ticket" not in prompt_lower

    def test_output_path_contains_feature_id(self, tmp_path):
        from bob3.agents.researcher import dispatch
        result = dispatch(
            feature_id="my-feat-id",
            path_glob="src/**",
            symbol_shortlist=[],
            workspace=tmp_path,
        )
        assert "my-feat-id" in result["output_path"]
        assert "research_notes.md" in result["output_path"]

    def test_cache_hit_false_when_no_notes(self, tmp_path):
        from bob3.agents.researcher import dispatch
        result = dispatch(
            feature_id="feat-nocache",
            path_glob="src/**",
            symbol_shortlist=[],
            survey_sha="sha123",
            workspace=tmp_path,
        )
        assert result["cache_hit"] is False

    def test_cache_hit_true_when_notes_match(self, tmp_path):
        from bob3.agents.researcher import dispatch
        from bob3.agents.roles import research_notes_path
        fid = "feat-cached"
        sha = "abc123"
        glob = "src/bob3/**"
        notes = research_notes_path(fid, tmp_path)
        notes.parent.mkdir(parents=True)
        notes.write_text(
            f"---\nsurvey_sha: {sha}\npath_glob: {glob}\n---\n\nContent.\n",
            encoding="utf-8",
        )
        result = dispatch(
            feature_id=fid,
            path_glob=glob,
            symbol_shortlist=[],
            survey_sha=sha,
            workspace=tmp_path,
        )
        assert result["cache_hit"] is True

    def test_invalid_symbol_shortlist_raises(self, tmp_path):
        from bob3.agents.researcher import dispatch
        with pytest.raises(TypeError):
            dispatch(
                feature_id="feat-bad",
                path_glob="src/**",
                symbol_shortlist="not-a-list",  # type: ignore[arg-type]
                workspace=tmp_path,
            )

    def test_role_is_researcher(self, tmp_path):
        from bob3.agents.researcher import dispatch
        result = dispatch(
            feature_id="feat-role",
            path_glob="src/**",
            symbol_shortlist=[],
            workspace=tmp_path,
        )
        assert result["role"].name == "researcher"
        assert result["role"].hide_intent is True


class TestOrchestratorIntegration:
    """Verify that bob3.orchestrator can reference researcher dispatch."""

    def test_coordinator_importable(self):
        from bob3 import coordinator  # noqa: F401

    def test_researcher_importable_from_agents(self):
        from bob3.agents import researcher
        assert hasattr(researcher, "dispatch")
        assert hasattr(researcher, "get_role")

    def test_dispatch_callable(self):
        from bob3.agents.researcher import dispatch
        assert callable(dispatch)
