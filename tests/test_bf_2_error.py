"""Error-path tests for BF-2 — Research-as-documentarian sub-agent.

Verifies that invalid input raises ValueError and the function does not
silently succeed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestGetRoleErrors:
    """get_role must raise KeyError for unknown role names."""

    def test_unknown_role_raises_key_error(self):
        from bob.agents.roles import get_role
        with pytest.raises(KeyError):
            get_role("nonexistent_role")

    def test_empty_role_name_raises(self):
        from bob.agents.roles import get_role
        with pytest.raises(KeyError):
            get_role("")

    def test_misspelled_role_raises(self):
        from bob.agents.roles import get_role
        with pytest.raises(KeyError):
            get_role("Researcher")  # case-sensitive


class TestSymbolShortlistTypeErrors:
    """Passing wrong types for symbol_shortlist must raise."""

    def test_string_instead_of_list_raises(self):
        from bob.agents.roles import build_researcher_prompt
        with pytest.raises(TypeError):
            build_researcher_prompt(path_glob="src/**", symbol_shortlist="bad_string")  # type: ignore[arg-type]


class TestResearchNotesPathErrors:
    """research_notes_path with invalid workspace types."""

    def test_non_path_workspace_still_works(self, tmp_path):
        from bob.agents.roles import research_notes_path
        # str workspace should work
        path = research_notes_path("feat-str", str(tmp_path))
        assert path.name == "research_notes.md"

    def test_none_workspace_defaults_to_cwd(self):
        from bob.agents.roles import research_notes_path
        path = research_notes_path("feat-none", None)
        assert path.name == "research_notes.md"
        assert "feat-none" in str(path)


class TestRoleImmutability:
    """Role dataclass is frozen — mutation must raise."""

    def test_researcher_is_frozen(self):
        from bob.agents.roles import RESEARCHER
        with pytest.raises((AttributeError, TypeError)):
            RESEARCHER.hide_intent = False  # type: ignore[misc]

    def test_researcher_name_immutable(self):
        from bob.agents.roles import RESEARCHER
        with pytest.raises((AttributeError, TypeError)):
            RESEARCHER.name = "hacker"  # type: ignore[misc]


class TestBF2FunctionErrorPaths:
    """bf_2 function error paths: invalid workspace type raises early."""

    def test_invalid_workspace_type_raises(self):
        from bob.bf_2_research_documentarian_sub_agent_hide_ticket_pattern import (
            bf_2_research_documentarian_sub_agent_hide_ticket_pattern as bf2,
        )
        with pytest.raises((TypeError, AttributeError, OSError)):
            # Passing an integer where a path is expected must raise, not silently succeed
            bf2(feature_id="feat-bad", workspace=12345)  # type: ignore[arg-type]
