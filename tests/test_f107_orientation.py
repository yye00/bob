"""Tests for F107: Sub-agent orientation protocol with TITANS memory.

Tests the orientation module that provides mandatory context recovery
for all sub-agents, including TITANS memory search integration and
bootstrap detection for F016/F017.
"""

import textwrap

import pytest

from bob3.orientation import (
    BOOTSTRAP_FEATURE_IDS,
    get_memory_search_prompt,
    get_orientation_prompt,
    get_post_completion_prompt,
    is_bootstrap_feature,
    wrap_prompt_with_orientation,
)


# ============================================================
# Step 7: Bootstrap detection
# ============================================================


class TestIsBootstrapFeature:
    """Test bootstrap feature detection for F016/F017."""

    def test_f016_is_bootstrap(self):
        assert is_bootstrap_feature("F016") is True

    def test_f017_is_bootstrap(self):
        assert is_bootstrap_feature("F017") is True

    def test_regular_feature_not_bootstrap(self):
        assert is_bootstrap_feature("F107") is False

    def test_f001_not_bootstrap(self):
        assert is_bootstrap_feature("F001") is False

    def test_none_not_bootstrap(self):
        assert is_bootstrap_feature(None) is False

    def test_empty_string_not_bootstrap(self):
        assert is_bootstrap_feature("") is False

    def test_bootstrap_ids_constant_contains_f016_f017(self):
        assert "F016" in BOOTSTRAP_FEATURE_IDS
        assert "F017" in BOOTSTRAP_FEATURE_IDS


# ============================================================
# Step 1 + 2: get_orientation_prompt with TITANS search
# ============================================================


class TestGetOrientationPrompt:
    """Test orientation prompt generation."""

    def test_returns_string(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/test-workspace",
        )
        assert isinstance(result, str)

    def test_includes_pwd_command(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/test-workspace",
        )
        assert "pwd" in result

    def test_includes_ls_command(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/test-workspace",
        )
        assert "ls" in result

    def test_includes_app_spec_reading(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/test-workspace",
        )
        assert "app_spec" in result

    def test_includes_feature_status_query(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/test-workspace",
        )
        assert "F107" in result

    def test_includes_progress_file_reading(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/test-workspace",
        )
        assert "claude-progress" in result

    def test_includes_git_log(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/test-workspace",
        )
        assert "git log" in result

    def test_includes_workspace_path(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/my/workspace",
        )
        assert "/my/workspace" in result


# ============================================================
# Step 4: Memory search for feature context
# ============================================================


class TestGetMemorySearchPrompt:
    """Test TITANS memory search prompt generation."""

    def test_returns_string(self):
        result = get_memory_search_prompt(
            feature_id="F107",
            feature_name="Orientation protocol",
            feature_description="Creates orientation module",
        )
        assert isinstance(result, str)

    def test_searches_lessons_pool(self):
        result = get_memory_search_prompt(
            feature_id="F107",
            feature_name="Orientation protocol",
            feature_description="Creates orientation module",
        )
        assert "lessons" in result

    def test_searches_facts_pool(self):
        result = get_memory_search_prompt(
            feature_id="F107",
            feature_name="Orientation protocol",
            feature_description="Creates orientation module",
        )
        assert "facts" in result

    def test_searches_context_pool(self):
        result = get_memory_search_prompt(
            feature_id="F107",
            feature_name="Orientation protocol",
            feature_description="Creates orientation module",
        )
        assert "context" in result

    def test_includes_feature_name_in_search(self):
        result = get_memory_search_prompt(
            feature_id="F107",
            feature_name="Orientation protocol",
            feature_description="Creates orientation module",
        )
        assert "Orientation protocol" in result

    def test_includes_feature_id(self):
        result = get_memory_search_prompt(
            feature_id="F107",
            feature_name="Orientation protocol",
            feature_description="Creates orientation module",
        )
        assert "F107" in result


# ============================================================
# Step 2 continued: TITANS integration in orientation
# ============================================================


class TestOrientationWithTitans:
    """Test that orientation includes TITANS search for non-bootstrap features."""

    def test_non_bootstrap_includes_titans_search(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/workspace",
        )
        assert "memory_search" in result

    def test_bootstrap_f016_skips_titans(self):
        result = get_orientation_prompt(
            feature_id="F016",
            workspace="/tmp/workspace",
        )
        assert "memory_search" not in result

    def test_bootstrap_f017_skips_titans(self):
        result = get_orientation_prompt(
            feature_id="F017",
            workspace="/tmp/workspace",
        )
        assert "memory_search" not in result

    def test_bootstrap_includes_skip_explanation(self):
        result = get_orientation_prompt(
            feature_id="F016",
            workspace="/tmp/workspace",
        )
        # Should explain why TITANS is skipped
        assert "bootstrap" in result.lower() or "skip" in result.lower()


# ============================================================
# Step 6: is_retry flag for debugging additions
# ============================================================


class TestRetryFlag:
    """Test that retry flag adds debugging protocol."""

    def test_default_is_not_retry(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/workspace",
        )
        assert "debugging" not in result.lower() or "systematic" not in result.lower()

    def test_retry_includes_debugging_protocol(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/workspace",
            is_retry=True,
        )
        assert "debug" in result.lower()

    def test_retry_searches_past_fixes(self):
        result = get_orientation_prompt(
            feature_id="F107",
            workspace="/tmp/workspace",
            is_retry=True,
        )
        # Should search for past fixes/lessons
        assert "fix" in result.lower() or "past" in result.lower() or "previous" in result.lower()

    def test_retry_with_bootstrap_skips_titans_debug_search(self):
        """Even on retry, bootstrap features skip TITANS."""
        result = get_orientation_prompt(
            feature_id="F016",
            workspace="/tmp/workspace",
            is_retry=True,
        )
        assert "memory_search" not in result


# ============================================================
# Step 3: wrap_prompt_with_orientation
# ============================================================


class TestWrapPromptWithOrientation:
    """Test prompt wrapping with orientation context."""

    def test_returns_string(self):
        result = wrap_prompt_with_orientation(
            prompt="Implement feature X",
            feature_id="F107",
            workspace="/tmp/workspace",
        )
        assert isinstance(result, str)

    def test_includes_original_prompt(self):
        result = wrap_prompt_with_orientation(
            prompt="Implement feature X",
            feature_id="F107",
            workspace="/tmp/workspace",
        )
        assert "Implement feature X" in result

    def test_includes_orientation_content(self):
        result = wrap_prompt_with_orientation(
            prompt="Implement feature X",
            feature_id="F107",
            workspace="/tmp/workspace",
        )
        # Should include orientation steps
        assert "pwd" in result
        assert "git log" in result

    def test_orientation_comes_before_prompt(self):
        result = wrap_prompt_with_orientation(
            prompt="Implement feature X",
            feature_id="F107",
            workspace="/tmp/workspace",
        )
        orientation_idx = result.index("pwd")
        prompt_idx = result.index("Implement feature X")
        assert orientation_idx < prompt_idx

    def test_passes_retry_flag(self):
        result = wrap_prompt_with_orientation(
            prompt="Implement feature X",
            feature_id="F107",
            workspace="/tmp/workspace",
            is_retry=True,
        )
        assert "debug" in result.lower()

    def test_passes_bootstrap_detection(self):
        result = wrap_prompt_with_orientation(
            prompt="Implement TITANS",
            feature_id="F016",
            workspace="/tmp/workspace",
        )
        assert "memory_search" not in result

    def test_includes_feature_name_when_provided(self):
        result = wrap_prompt_with_orientation(
            prompt="Do the work",
            feature_id="F107",
            workspace="/tmp/workspace",
            feature_name="Orientation protocol",
        )
        assert "Orientation protocol" in result

    def test_includes_feature_description_when_provided(self):
        result = wrap_prompt_with_orientation(
            prompt="Do the work",
            feature_id="F107",
            workspace="/tmp/workspace",
            feature_description="Creates orientation module",
        )
        assert "Creates orientation module" in result


# ============================================================
# Step 5: Post-completion memory storage
# ============================================================


class TestGetPostCompletionPrompt:
    """Test post-completion memory storage prompt generation."""

    def test_returns_string(self):
        result = get_post_completion_prompt(feature_id="F107")
        assert isinstance(result, str)

    def test_includes_titans_add(self):
        result = get_post_completion_prompt(feature_id="F107")
        assert "memory_add" in result

    def test_includes_feedback_recording(self):
        result = get_post_completion_prompt(feature_id="F107")
        assert "memory_record_feedback" in result or "feedback" in result.lower()

    def test_includes_feature_id(self):
        result = get_post_completion_prompt(feature_id="F107")
        assert "F107" in result

    def test_bootstrap_returns_empty_or_skip(self):
        """Bootstrap features should skip post-completion TITANS ops."""
        result = get_post_completion_prompt(feature_id="F016")
        # Either returns empty string or a note about skipping
        assert result == "" or "skip" in result.lower() or "bootstrap" in result.lower()

    def test_non_bootstrap_has_substance(self):
        result = get_post_completion_prompt(feature_id="F107")
        assert len(result) > 50  # Should be a substantial prompt


# ============================================================
# Step 9: Integration test - bootstrap case
# ============================================================


class TestBootstrapIntegration:
    """Test that F016/F017 can work without TITANS."""

    def test_f016_full_orientation_has_no_titans(self):
        """F016 orientation should be complete but skip all TITANS ops."""
        result = wrap_prompt_with_orientation(
            prompt="Implement TITANS Memory MCP integration",
            feature_id="F016",
            workspace="/tmp/workspace",
        )
        assert "memory_search" not in result
        assert "memory_add" not in result
        # But should still have basic orientation
        assert "pwd" in result
        assert "git log" in result
        assert "Implement TITANS Memory MCP integration" in result

    def test_f017_full_orientation_has_no_titans(self):
        """F017 orientation should be complete but skip all TITANS ops."""
        result = wrap_prompt_with_orientation(
            prompt="Implement MCP Server Lifecycle",
            feature_id="F017",
            workspace="/tmp/workspace",
        )
        assert "memory_search" not in result
        assert "memory_add" not in result
        assert "pwd" in result
        assert "Implement MCP Server Lifecycle" in result

    def test_regular_feature_has_titans(self):
        """Non-bootstrap features should include TITANS ops."""
        result = wrap_prompt_with_orientation(
            prompt="Implement feature",
            feature_id="F107",
            workspace="/tmp/workspace",
        )
        assert "memory_search" in result
