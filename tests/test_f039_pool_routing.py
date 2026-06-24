"""Tests for F039: Bob3 memory pool routing (formerly TITANS).

Validates that _classify_pool() (formerly route_to_pool):
- Step 1: Add _classify_pool() function
- Step 2: facts: default pool for content that doesn't match other categories
- Step 3: lessons: Bug fixes, debugging patterns, solutions (contains
  "bug", "fix", "debug", "error", "exception", "failure", "lesson")
- Step 4: preferences: User preferences, project conventions (contains
  "prefer", "style", "always use", "never use", "convention")
- Step 5: context: Session state, feature progress (contains "currently",
  "working on", "session", "in progress", "right now")
- Step 6: Test: Add different content types, verify correct pool
"""

import pytest


# ===================================================================
# Step 1: _classify_pool() function exists
# ===================================================================


class TestClassifyPoolExists:
    """Step 1: _classify_pool() must be importable and callable."""

    def test_function_importable(self):
        from bob3.memory import _classify_pool

        assert callable(_classify_pool)

    def test_returns_string(self):
        from bob3.memory import _classify_pool

        result = _classify_pool("some content")
        assert isinstance(result, str)

    def test_returns_valid_pool_name(self):
        from bob3.memory import VALID_POOLS, _classify_pool

        result = _classify_pool("some content")
        assert result in VALID_POOLS

    def test_empty_string_defaults_to_facts(self):
        from bob3.memory import _classify_pool

        # New heuristic: default is facts
        assert _classify_pool("") == "facts"

    def test_whitespace_only_defaults_to_facts(self):
        from bob3.memory import _classify_pool

        assert _classify_pool("   ") == "facts"

    def test_no_keywords_defaults_to_facts(self):
        from bob3.memory import _classify_pool

        result = _classify_pool("the quick brown fox jumps over the lazy dog")
        assert result == "facts"


# ===================================================================
# Step 2: facts: default for content that doesn't match categories
# ===================================================================


class TestFactsPoolRouting:
    """Step 2: Content that doesn't match other categories routes to facts."""

    def test_api_behavior_routes_to_facts(self):
        from bob3.memory import _classify_pool

        content = "The API returns a 200 status code for successful requests"
        assert _classify_pool(content) == "facts"

    def test_library_usage_routes_to_facts(self):
        from bob3.memory import _classify_pool

        content = "The library provides a function for parsing JSON responses"
        assert _classify_pool(content) == "facts"

    def test_neutral_statement_routes_to_facts(self):
        from bob3.memory import _classify_pool

        content = "The dependency requires import of the schema module"
        assert _classify_pool(content) == "facts"


# ===================================================================
# Step 3: lessons: Bug fixes, debugging patterns, solutions
# ===================================================================


class TestLessonsPoolRouting:
    """Step 3: Content about bugs, fixes, and debugging routes to lessons."""

    def test_bug_content_routes_to_lessons(self):
        from bob3.memory import _classify_pool

        content = "Bug: The error was caused by a null pointer"
        assert _classify_pool(content) == "lessons"

    def test_fix_content_routes_to_lessons(self):
        from bob3.memory import _classify_pool

        content = "Here's the fix for the null pointer dereference"
        assert _classify_pool(content) == "lessons"

    def test_debug_content_routes_to_lessons(self):
        from bob3.memory import _classify_pool

        content = "Had to debug the crash for an hour"
        assert _classify_pool(content) == "lessons"

    def test_error_content_routes_to_lessons(self):
        from bob3.memory import _classify_pool

        content = "An error occurred when the handler ran"
        assert _classify_pool(content) == "lessons"

    def test_exception_content_routes_to_lessons(self):
        from bob3.memory import _classify_pool

        content = "An unhandled exception was raised"
        assert _classify_pool(content) == "lessons"

    def test_failure_content_routes_to_lessons(self):
        from bob3.memory import _classify_pool

        content = "The failure occurred during integration testing"
        assert _classify_pool(content) == "lessons"

    def test_lesson_content_routes_to_lessons(self):
        from bob3.memory import _classify_pool

        content = "Here is a lesson I learned today"
        assert _classify_pool(content) == "lessons"


# ===================================================================
# Step 4: preferences: User preferences, project conventions
# ===================================================================


class TestPreferencesPoolRouting:
    """Step 4: Content about preferences and conventions routes to preferences."""

    def test_prefer_content_routes_to_preferences(self):
        from bob3.memory import _classify_pool

        content = "I prefer PostgreSQL over MySQL for production"
        assert _classify_pool(content) == "preferences"

    def test_style_content_routes_to_preferences(self):
        from bob3.memory import _classify_pool

        content = "Our coding style favors short functions"
        assert _classify_pool(content) == "preferences"

    def test_convention_content_routes_to_preferences(self):
        from bob3.memory import _classify_pool

        content = "Naming convention: use snake_case for module names"
        assert _classify_pool(content) == "preferences"

    def test_always_use_content_routes_to_preferences(self):
        from bob3.memory import _classify_pool

        content = "Always use type hints on public functions"
        assert _classify_pool(content) == "preferences"

    def test_never_use_content_routes_to_preferences(self):
        from bob3.memory import _classify_pool

        content = "Never use global variables in modules"
        assert _classify_pool(content) == "preferences"


# ===================================================================
# Step 5: context: Session state, feature progress
# ===================================================================


class TestContextPoolRouting:
    """Step 5: Content about session state and progress routes to context."""

    def test_currently_content_routes_to_context(self):
        from bob3.memory import _classify_pool

        content = "Currently refactoring the memory module"
        assert _classify_pool(content) == "context"

    def test_working_on_content_routes_to_context(self):
        from bob3.memory import _classify_pool

        content = "We are working on the migration tooling"
        assert _classify_pool(content) == "context"

    def test_session_content_routes_to_context(self):
        from bob3.memory import _classify_pool

        content = "This session's outcome was shipping F039"
        assert _classify_pool(content) == "context"

    def test_in_progress_content_routes_to_context(self):
        from bob3.memory import _classify_pool

        content = "Task is in progress, ETA tomorrow"
        assert _classify_pool(content) == "context"

    def test_right_now_content_routes_to_context(self):
        from bob3.memory import _classify_pool

        content = "Right now we're waiting on the reviewer"
        assert _classify_pool(content) == "context"


# ===================================================================
# Step 6: Test: Add different content types, verify correct pool
# ===================================================================


class TestMixedContentRouting:
    """Step 6: Verify correct pool for various mixed content types."""

    def test_all_valid_pools_represented(self):
        """Each of the four valid pools must be reachable via _classify_pool."""
        from bob3.memory import VALID_POOLS, _classify_pool

        routed_pools = set()
        test_contents = {
            "facts": "The API returns a JSON response payload",
            "lessons": "Bug report: the error was caused by an exception in parsing",
            "preferences": "Our convention: always use explicit imports",
            "context": "Currently working on the import pipeline in this session",
        }

        for expected_pool, content in test_contents.items():
            result = _classify_pool(content)
            routed_pools.add(result)
            assert result == expected_pool, (
                f"Expected '{expected_pool}' for content '{content[:50]}...', got '{result}'"
            )

        assert routed_pools == VALID_POOLS

    def test_case_insensitive_matching(self):
        """Keywords should match regardless of case."""
        from bob3.memory import _classify_pool

        # Uppercase keywords should still match
        assert _classify_pool("BUG FIX: I had to debug the ERROR") == "lessons"
        assert _classify_pool("We ALWAYS USE explicit imports") == "preferences"

    def test_lessons_matches_first(self):
        """When content contains keywords from lessons, lessons wins."""
        from bob3.memory import _classify_pool

        # lessons is evaluated before preferences in _classify_pool
        content = "Always use exception handling to avoid errors"
        # Contains 'always use' (preferences), 'exception' (lessons), 'error' (lessons).
        # lessons is evaluated first, so: lessons
        assert _classify_pool(content) == "lessons"

    def test_real_world_debugging_session(self):
        """Real-world content: a debugging session."""
        from bob3.memory import _classify_pool

        content = (
            "Root cause of the bug: exception in the error handler caused a crash. "
            "The fix was a workaround."
        )
        assert _classify_pool(content) == "lessons"

    def test_real_world_team_convention(self):
        """Real-world content: team coding convention."""
        from bob3.memory import _classify_pool

        content = (
            "Our coding style guideline: prefer descriptive naming convention, "
            "always use type hints"
        )
        assert _classify_pool(content) == "preferences"

    def test_real_world_project_state(self):
        """Real-world content: project state update."""
        from bob3.memory import _classify_pool

        content = (
            "Session update: currently working on the feature backlog. "
            "In progress right now."
        )
        assert _classify_pool(content) == "context"

    def test_real_world_api_documentation(self):
        """Real-world content: API documentation (defaults to facts)."""
        from bob3.memory import _classify_pool

        content = (
            "The claude-code-sdk package provides an API endpoint that returns "
            "a response payload for each parameter"
        )
        assert _classify_pool(content) == "facts"
