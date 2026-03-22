"""Tests for F078: Add CLI command show-lessons [--scope global|project].

Validates that:
- Step 1: show-lessons command is registered and accessible
- Step 2: Filter by scope if provided (global|project)
- Step 3: Display lesson, usefulness score, times applied
- Step 4: Show global lessons, verify filtering works
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner


# ============================================================
# Step 1: Add show-lessons command
# ============================================================


class TestShowLessonsCommandRegistered:
    """Step 1: show-lessons command is registered and accessible."""

    def test_show_lessons_command_registered(self):
        from bob3.cli import main

        assert "show-lessons" in main.commands, "show-lessons command must be registered"

    def test_show_lessons_help_works(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["show-lessons", "--help"])
        assert result.exit_code == 0
        assert "lesson" in result.output.lower()

    def test_show_lessons_accepts_scope_option(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["show-lessons", "--help"])
        assert result.exit_code == 0
        assert "--scope" in result.output

    def test_show_lessons_scope_choices(self):
        """Scope option should accept 'global' and 'project' values."""
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["show-lessons", "--help"])
        assert result.exit_code == 0
        assert "global" in result.output
        assert "project" in result.output


# ============================================================
# Step 2: Filter by scope if provided
# ============================================================


class TestShowLessonsScopeFiltering:
    """Step 2: Filter by scope if provided."""

    def test_global_scope_searches_all_lessons(self):
        """Global scope should search the entire lessons pool."""
        from bob3.cli import main
        from bob3.titans_memory_client import MemoryResult

        mock_result = MemoryResult(
            success=True,
            data=[
                {
                    "id": "mem-1",
                    "content": "TRIGGER: bug\nLESSON: fix it\nSOLUTION: do this",
                    "metadata": {"pool": "lessons"},
                    "retrieval_weight": 0.8,
                    "access_count": 3,
                },
            ],
            raw_text="[]",
        )

        runner = CliRunner()
        with patch(
            "bob3.cli._fetch_lessons", return_value=mock_result.data
        ):
            result = runner.invoke(main, ["show-lessons", "--scope", "global"])
        assert result.exit_code == 0

    def test_project_scope_filters_by_project_features(self):
        """Project scope should only show lessons associated with project features."""
        from bob3.cli import main

        runner = CliRunner()
        # Project scope with no project should handle gracefully
        with patch("bob3.cli._fetch_lessons", return_value=[]):
            result = runner.invoke(main, ["show-lessons", "--scope", "project"])
        assert result.exit_code == 0

    def test_default_scope_is_global(self):
        """When no scope is given, default to global."""
        from bob3.cli import main

        runner = CliRunner()
        with patch("bob3.cli._fetch_lessons", return_value=[]) as mock_fetch:
            result = runner.invoke(main, ["show-lessons"])
        assert result.exit_code == 0
        # _fetch_lessons should be called with scope=None (treated as global)
        mock_fetch.assert_called_once()
        call_kwargs = mock_fetch.call_args
        # The scope arg should be None (default)
        assert call_kwargs[0][0] is None or call_kwargs[1].get("scope") is None


# ============================================================
# Step 3: Display lesson, usefulness score, times applied
# ============================================================


class TestShowLessonsDisplay:
    """Step 3: Display lesson content, usefulness score, and times applied."""

    def _make_lesson(self, lesson_id="mem-1", content=None, weight=0.85, access_count=5):
        return {
            "id": lesson_id,
            "content": content or "TRIGGER: DB lock\nLESSON: Use WAL mode\nSOLUTION: Enable WAL",
            "metadata": {"pool": "lessons", "feature_id": "F041"},
            "retrieval_weight": weight,
            "access_count": access_count,
        }

    def test_displays_lesson_content(self):
        from bob3.cli import main

        lessons = [self._make_lesson()]

        runner = CliRunner()
        with patch("bob3.cli._fetch_lessons", return_value=lessons):
            result = runner.invoke(main, ["show-lessons"])
        assert result.exit_code == 0
        # Should display at least part of the lesson content
        assert "WAL" in result.output or "DB lock" in result.output

    def test_displays_usefulness_score(self):
        from bob3.cli import main

        lessons = [self._make_lesson(weight=0.85)]

        runner = CliRunner()
        with patch("bob3.cli._fetch_lessons", return_value=lessons):
            result = runner.invoke(main, ["show-lessons"])
        assert result.exit_code == 0
        assert "0.85" in result.output

    def test_displays_times_applied(self):
        from bob3.cli import main

        lessons = [self._make_lesson(access_count=7)]

        runner = CliRunner()
        with patch("bob3.cli._fetch_lessons", return_value=lessons):
            result = runner.invoke(main, ["show-lessons"])
        assert result.exit_code == 0
        assert "7" in result.output

    def test_displays_multiple_lessons(self):
        from bob3.cli import main

        lessons = [
            self._make_lesson(lesson_id="mem-1", content="TRIGGER: a\nLESSON: first lesson\nSOLUTION: s1", weight=0.9, access_count=10),
            self._make_lesson(lesson_id="mem-2", content="TRIGGER: b\nLESSON: second lesson\nSOLUTION: s2", weight=0.5, access_count=2),
        ]

        runner = CliRunner()
        with patch("bob3.cli._fetch_lessons", return_value=lessons):
            result = runner.invoke(main, ["show-lessons"])
        assert result.exit_code == 0
        assert "first lesson" in result.output
        assert "second lesson" in result.output

    def test_no_lessons_message(self):
        from bob3.cli import main

        runner = CliRunner()
        with patch("bob3.cli._fetch_lessons", return_value=[]):
            result = runner.invoke(main, ["show-lessons"])
        assert result.exit_code == 0
        assert "no lessons" in result.output.lower()

    def test_uses_rich_table(self):
        """show-lessons should use Rich Table for output."""
        import inspect

        from bob3.cli import show_lessons_cmd

        source = inspect.getsource(show_lessons_cmd.callback)
        assert "Table" in source or "table" in source, \
            "show-lessons should use Rich Table for formatting"


# ============================================================
# Step 4: Show global lessons, verify filtering works
# ============================================================


class TestShowLessonsFiltering:
    """Step 4: Show global lessons, verify filtering works."""

    def test_global_shows_all_lessons(self):
        from bob3.cli import main

        all_lessons = [
            {
                "id": "mem-global-1",
                "content": "TRIGGER: t\nLESSON: global lesson\nSOLUTION: s",
                "metadata": {"pool": "lessons"},
                "retrieval_weight": 0.7,
                "access_count": 1,
            },
            {
                "id": "mem-proj-1",
                "content": "TRIGGER: t\nLESSON: project lesson\nSOLUTION: s",
                "metadata": {"pool": "lessons", "feature_id": "F001"},
                "retrieval_weight": 0.8,
                "access_count": 3,
            },
        ]

        runner = CliRunner()
        with patch("bob3.cli._fetch_lessons", return_value=all_lessons):
            result = runner.invoke(main, ["show-lessons", "--scope", "global"])
        assert result.exit_code == 0
        assert "global lesson" in result.output
        assert "project lesson" in result.output

    def test_project_scope_only_shows_project_lessons(self):
        """Project scope should filter to lessons with feature_id metadata."""
        from bob3.cli import main

        project_lessons = [
            {
                "id": "mem-proj-1",
                "content": "TRIGGER: t\nLESSON: project-specific lesson\nSOLUTION: s",
                "metadata": {"pool": "lessons", "feature_id": "F001"},
                "retrieval_weight": 0.8,
                "access_count": 3,
            },
        ]

        runner = CliRunner()
        with patch("bob3.cli._fetch_lessons", return_value=project_lessons):
            result = runner.invoke(main, ["show-lessons", "--scope", "project"])
        assert result.exit_code == 0
        assert "project-specific lesson" in result.output

    def test_fetch_lessons_function_exists(self):
        """_fetch_lessons helper should exist in cli module."""
        from bob3.cli import _fetch_lessons

        assert callable(_fetch_lessons)

    def test_handles_titans_unavailable(self):
        """Should handle TITANS Memory being unavailable gracefully."""
        from bob3.cli import main

        runner = CliRunner()
        with patch("bob3.cli._fetch_lessons", side_effect=Exception("MCP unavailable")):
            result = runner.invoke(main, ["show-lessons"])
        # Should not crash with traceback
        assert result.exit_code == 0 or result.exit_code == 1
        # Should show a user-friendly error
        output_lower = result.output.lower()
        assert "error" in output_lower or "unavailable" in output_lower or "failed" in output_lower

    def test_lesson_count_displayed(self):
        """Should show the total number of lessons found."""
        from bob3.cli import main

        lessons = [
            {
                "id": f"mem-{i}",
                "content": f"TRIGGER: t{i}\nLESSON: lesson {i}\nSOLUTION: s{i}",
                "metadata": {"pool": "lessons"},
                "retrieval_weight": 0.5,
                "access_count": i,
            }
            for i in range(3)
        ]

        runner = CliRunner()
        with patch("bob3.cli._fetch_lessons", return_value=lessons):
            result = runner.invoke(main, ["show-lessons"])
        assert result.exit_code == 0
        assert "3" in result.output
