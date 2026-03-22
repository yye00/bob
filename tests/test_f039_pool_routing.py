"""Tests for F039: Implement TITANS memory pool routing.

Validates that route_to_pool():
- Step 1: Add route_to_pool() function
- Step 2: facts: API behaviors, library usage, external knowledge
- Step 3: lessons: Bug fixes, debugging patterns, solutions
- Step 4: preferences: User preferences, project conventions
- Step 5: context: Session state, feature progress
- Step 6: Test: Add different content types, verify correct pool
"""

import pytest


# ===================================================================
# Step 1: route_to_pool() function exists
# ===================================================================


class TestRouteToPoolExists:
    """Step 1: route_to_pool() must be importable and callable."""

    def test_function_importable(self):
        from bob3.titans_memory_client import route_to_pool

        assert callable(route_to_pool)

    def test_returns_string(self):
        from bob3.titans_memory_client import route_to_pool

        result = route_to_pool("some content")
        assert isinstance(result, str)

    def test_returns_valid_pool_name(self):
        from bob3.titans_memory_client import VALID_POOLS, route_to_pool

        result = route_to_pool("some content")
        assert result in VALID_POOLS

    def test_empty_string_returns_context(self):
        from bob3.titans_memory_client import route_to_pool

        assert route_to_pool("") == "context"

    def test_whitespace_only_returns_context(self):
        from bob3.titans_memory_client import route_to_pool

        assert route_to_pool("   ") == "context"

    def test_no_keywords_defaults_to_context(self):
        from bob3.titans_memory_client import route_to_pool

        result = route_to_pool("the quick brown fox jumps over the lazy dog")
        assert result == "context"


# ===================================================================
# Step 2: facts: API behaviors, library usage, external knowledge
# ===================================================================


class TestFactsPoolRouting:
    """Step 2: Content about APIs, libraries, and external knowledge routes to facts."""

    def test_api_behavior_routes_to_facts(self):
        from bob3.titans_memory_client import route_to_pool

        content = "The API returns a 200 status code for successful requests"
        assert route_to_pool(content) == "facts"

    def test_library_usage_routes_to_facts(self):
        from bob3.titans_memory_client import route_to_pool

        content = "The library provides a function for parsing JSON responses"
        assert route_to_pool(content) == "facts"

    def test_sdk_documentation_routes_to_facts(self):
        from bob3.titans_memory_client import route_to_pool

        content = "The SDK documentation describes the endpoint parameter types"
        assert route_to_pool(content) == "facts"

    def test_package_version_routes_to_facts(self):
        from bob3.titans_memory_client import route_to_pool

        content = "Package version 2.0 introduced a new module for config"
        assert route_to_pool(content) == "facts"

    def test_external_dependency_routes_to_facts(self):
        from bob3.titans_memory_client import route_to_pool

        content = "The dependency requires import of the schema module"
        assert route_to_pool(content) == "facts"

    def test_environment_variable_routes_to_facts(self):
        from bob3.titans_memory_client import route_to_pool

        content = "The environment variable controls the default value for the API endpoint"
        assert route_to_pool(content) == "facts"

    def test_protocol_specification_routes_to_facts(self):
        from bob3.titans_memory_client import route_to_pool

        content = "The protocol specification defines how the response schema works"
        assert route_to_pool(content) == "facts"


# ===================================================================
# Step 3: lessons: Bug fixes, debugging patterns, solutions
# ===================================================================


class TestLessonsPoolRouting:
    """Step 3: Content about bugs, fixes, and debugging routes to lessons."""

    def test_bug_fix_routes_to_lessons(self):
        from bob3.titans_memory_client import route_to_pool

        content = "Bug fix: The error was caused by a null pointer exception"
        assert route_to_pool(content) == "lessons"

    def test_debugging_pattern_routes_to_lessons(self):
        from bob3.titans_memory_client import route_to_pool

        content = "Debug traceback showed the failure was in the root cause analysis"
        assert route_to_pool(content) == "lessons"

    def test_error_resolution_routes_to_lessons(self):
        from bob3.titans_memory_client import route_to_pool

        content = "The exception was resolved with a workaround for the crash"
        assert route_to_pool(content) == "lessons"

    def test_lesson_learned_routes_to_lessons(self):
        from bob3.titans_memory_client import route_to_pool

        content = "Lesson learned: The mistake was using the wrong patch hotfix"
        assert route_to_pool(content) == "lessons"

    def test_trigger_lesson_solution_format_routes_to_lessons(self):
        from bob3.titans_memory_client import route_to_pool

        content = "trigger: DB connection\nlesson: Use connection pooling\nsolution: Added pool manager"
        assert route_to_pool(content) == "lessons"

    def test_regression_routes_to_lessons(self):
        from bob3.titans_memory_client import route_to_pool

        content = "The regression was caused by a broken migration"
        assert route_to_pool(content) == "lessons"


# ===================================================================
# Step 4: preferences: User preferences, project conventions
# ===================================================================


class TestPreferencesPoolRouting:
    """Step 4: Content about preferences and conventions routes to preferences."""

    def test_user_preference_routes_to_preferences(self):
        from bob3.titans_memory_client import route_to_pool

        content = "User preference: always use type hints with naming convention"
        assert route_to_pool(content) == "preferences"

    def test_project_convention_routes_to_preferences(self):
        from bob3.titans_memory_client import route_to_pool

        content = "Project convention: use snake_case naming for coding style and lint rules"
        assert route_to_pool(content) == "preferences"

    def test_style_guideline_routes_to_preferences(self):
        from bob3.titans_memory_client import route_to_pool

        content = "The guideline is to prefer standard template format for lint"
        assert route_to_pool(content) == "preferences"

    def test_coding_practice_routes_to_preferences(self):
        from bob3.titans_memory_client import route_to_pool

        content = "Best practice: never use global state, follow the naming convention"
        assert route_to_pool(content) == "preferences"


# ===================================================================
# Step 5: context: Session state, feature progress
# ===================================================================


class TestContextPoolRouting:
    """Step 5: Content about session state and progress routes to context."""

    def test_session_progress_routes_to_context(self):
        from bob3.titans_memory_client import route_to_pool

        content = "Session progress: currently working on the milestone checkpoint"
        assert route_to_pool(content) == "context"

    def test_feature_status_routes_to_context(self):
        from bob3.titans_memory_client import route_to_pool

        content = "Feature status: in progress, next step is to complete the backlog"
        assert route_to_pool(content) == "context"

    def test_blocked_state_routes_to_context(self):
        from bob3.titans_memory_client import route_to_pool

        content = "Currently blocked on the plan, need to review the current state"
        assert route_to_pool(content) == "context"

    def test_completed_milestone_routes_to_context(self):
        from bob3.titans_memory_client import route_to_pool

        content = "Milestone completed: all checkpoint items are done, next step planned"
        assert route_to_pool(content) == "context"


# ===================================================================
# Step 6: Test: Add different content types, verify correct pool
# ===================================================================


class TestMixedContentRouting:
    """Step 6: Verify correct pool for various mixed content types."""

    def test_all_valid_pools_represented(self):
        """Each of the four valid pools must be reachable via route_to_pool."""
        from bob3.titans_memory_client import VALID_POOLS, route_to_pool

        routed_pools = set()
        test_contents = {
            "facts": "The API library SDK documentation describes parameter specification",
            "lessons": "Bug fix: debug traceback exception failure root cause workaround",
            "preferences": "User preference convention style always use naming guideline rule template",
            "context": "Session progress status currently working on milestone checkpoint blocked",
        }

        for expected_pool, content in test_contents.items():
            result = route_to_pool(content)
            routed_pools.add(result)
            assert result == expected_pool, (
                f"Expected '{expected_pool}' for content '{content[:50]}...', got '{result}'"
            )

        assert routed_pools == VALID_POOLS

    def test_case_insensitive_matching(self):
        """Keywords should match regardless of case."""
        from bob3.titans_memory_client import route_to_pool

        # Uppercase keywords should still match
        assert route_to_pool("The API returns data from the LIBRARY") == "facts"
        assert route_to_pool("BUG FIX: debug TRACEBACK exception") == "lessons"

    def test_priority_facts_over_context_on_tie(self):
        """facts pool has higher priority than context when keyword counts tie."""
        from bob3.titans_memory_client import route_to_pool

        # "api" -> facts (1 hit), "current" -> context (1 hit)
        # Equal score: facts wins on priority
        content = "The api is current"
        result = route_to_pool(content)
        assert result == "facts"

    def test_higher_keyword_count_wins(self):
        """Pool with more keyword matches wins regardless of priority."""
        from bob3.titans_memory_client import route_to_pool

        # Multiple lessons keywords should outweigh a single facts keyword
        content = "The API had a bug, debug the error traceback"
        result = route_to_pool(content)
        # facts: api(1), lessons: bug(1), debug(1), error(1), traceback(1) = 4
        assert result == "lessons"

    def test_real_world_api_documentation(self):
        """Real-world content: API documentation."""
        from bob3.titans_memory_client import route_to_pool

        content = (
            "The claude-code-sdk package provides an API endpoint that returns "
            "a response with schema validation for each parameter"
        )
        assert route_to_pool(content) == "facts"

    def test_real_world_debugging_session(self):
        """Real-world content: a debugging session."""
        from bob3.titans_memory_client import route_to_pool

        content = (
            "Root cause of the bug: exception in the error handler caused a crash. "
            "The fix was a workaround that resolved the issue."
        )
        assert route_to_pool(content) == "lessons"

    def test_real_world_team_convention(self):
        """Real-world content: team coding convention."""
        from bob3.titans_memory_client import route_to_pool

        content = (
            "Our coding style guideline: prefer descriptive naming convention, "
            "always use type hints, follow the lint rule for template format"
        )
        assert route_to_pool(content) == "preferences"

    def test_real_world_project_state(self):
        """Real-world content: project state update."""
        from bob3.titans_memory_client import route_to_pool

        content = (
            "Session progress update: currently working on the feature backlog. "
            "Next step after the milestone: checkpoint the current state and plan"
        )
        assert route_to_pool(content) == "context"

    def test_pool_keywords_dict_has_all_pools(self):
        """The _POOL_KEYWORDS dict must cover all four valid pools."""
        from bob3.titans_memory_client import VALID_POOLS, _POOL_KEYWORDS

        assert set(_POOL_KEYWORDS.keys()) == VALID_POOLS

    def test_each_pool_has_keywords(self):
        """Each pool must have at least one keyword defined."""
        from bob3.titans_memory_client import _POOL_KEYWORDS

        for pool, keywords in _POOL_KEYWORDS.items():
            assert len(keywords) > 0, f"Pool '{pool}' has no keywords"
