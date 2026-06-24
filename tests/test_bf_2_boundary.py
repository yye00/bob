"""Boundary tests for BF-2 — Research-as-documentarian sub-agent.

Each test verifies that empty, zero, or minimum input returns a well-defined
result rather than raising an exception.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestEmptyInputs:
    """No arguments — the function must return a valid dict."""

    def test_no_args_returns_dict(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2()
        assert isinstance(result, dict)

    def test_no_args_hide_intent_true(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2()
        assert result["hide_intent"] is True

    def test_no_args_output_path_empty(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2()
        assert result["output_path"] == ""

    def test_no_args_researcher_prompt_empty(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2()
        assert result["researcher_prompt"] == ""

    def test_no_args_cache_hit_false(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2()
        assert result["cache_hit"] is False

    def test_no_args_protocol_steps_list(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2()
        assert isinstance(result["protocol_steps"], list)
        assert len(result["protocol_steps"]) > 0


class TestMinimumInputs:
    """Only one argument at a time — still must return valid dict."""

    def test_only_feature_id(self, tmp_path):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2(feature_id="feat-min", workspace=tmp_path)
        assert isinstance(result, dict)
        assert "feat-min" in result["output_path"]
        assert result["cache_hit"] is False

    def test_only_path_glob(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2(path_glob="src/**")
        assert isinstance(result, dict)
        assert "src/**" in result["researcher_prompt"]

    def test_only_symbol_shortlist(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2(symbol_shortlist=["foo", "bar"])
        assert isinstance(result, dict)
        # prompt is empty because no path_glob given
        assert result["researcher_prompt"] == ""

    def test_empty_symbol_shortlist(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2(path_glob="src/**", symbol_shortlist=[])
        assert isinstance(result, dict)
        assert "src/**" in result["researcher_prompt"]

    def test_single_symbol_shortlist(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2(path_glob="src/**", symbol_shortlist=["only_one"])
        assert isinstance(result, dict)
        assert "only_one" in result["researcher_prompt"]


class TestZeroOrMinimumValues:
    """Values that are empty strings or near-zero."""

    def test_empty_string_feature_id_no_output_path(self, tmp_path):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2(feature_id="", workspace=tmp_path)
        assert result["output_path"] == ""

    def test_empty_string_path_glob_no_prompt(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        result = bf2(path_glob="")
        assert result["researcher_prompt"] == ""

    def test_empty_survey_sha_no_cache_check(self, tmp_path):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        # Even with a feature_id, no cache check if sha is empty
        result = bf2(
            feature_id="feat-nosha",
            survey_sha="",
            path_glob="src/**",
            workspace=tmp_path,
        )
        assert result["cache_hit"] is False


class TestBuildResearcherPromptBoundary:
    """Boundary cases for build_researcher_prompt."""

    def test_empty_glob_empty_symbols(self):
        from bob.agents.roles import build_researcher_prompt
        # Must not raise
        prompt = build_researcher_prompt(path_glob="", symbol_shortlist=[])
        assert isinstance(prompt, str)

    def test_empty_symbols_still_builds(self):
        from bob.agents.roles import build_researcher_prompt
        prompt = build_researcher_prompt(path_glob="src/**", symbol_shortlist=[])
        assert "src/**" in prompt
        assert isinstance(prompt, str)

    def test_many_symbols(self):
        from bob.agents.roles import build_researcher_prompt
        symbols = [f"sym_{i}" for i in range(50)]
        prompt = build_researcher_prompt(path_glob="src/**", symbol_shortlist=symbols)
        assert "sym_0" in prompt
        assert "sym_49" in prompt


class TestShouldSkipResearchBoundary:
    """Boundary cases for should_skip_research."""

    def test_empty_feature_id(self, tmp_path):
        from bob.agents.roles import should_skip_research
        result = should_skip_research("", "sha", "src/**", tmp_path)
        assert isinstance(result, bool)
        assert result is False

    def test_empty_sha_empty_glob(self, tmp_path):
        from bob.agents.roles import should_skip_research
        result = should_skip_research("feat", "", "", tmp_path)
        assert isinstance(result, bool)

    def test_none_workspace_defaults(self):
        from bob.agents.roles import should_skip_research
        # workspace=None should not raise (defaults to cwd)
        result = should_skip_research("nonexistent-feat", "sha", "src/**", None)
        assert result is False
