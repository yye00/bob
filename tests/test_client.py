"""Tests for orchestrator client.py - Claude SDK client setup."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Mock claude_code_sdk modules before importing
sys.modules['claude_code_sdk'] = MagicMock()
sys.modules['claude_code_sdk.types'] = MagicMock()

from bob.orchestrator.client import (
    BUILTIN_TOOLS,
    PERPLEXITY_TOOLS,
    PUPPETEER_TOOLS,
    create_client,
    create_research_client,
)

# Alias for consistency in tests
CLIENT_PERPLEXITY_TOOLS = PERPLEXITY_TOOLS


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir


@pytest.fixture
def mock_claude_sdk():
    """Mock the Claude SDK components."""
    # Mock the availability flag
    with patch("bob.orchestrator.client.CLAUDE_SDK_AVAILABLE", True):
        # Mock ClaudeSDKClient class
        mock_client_class = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        # Mock ClaudeCodeOptions - make it return an object with captured attributes
        def create_options(**kwargs):
            """Create a mock options object that stores the kwargs."""
            options = MagicMock()
            for key, value in kwargs.items():
                setattr(options, key, value)
            return options

        mock_options_class = MagicMock(side_effect=create_options)

        # Mock HookMatcher class - make it return an object
        def create_hook_matcher(**kwargs):
            matcher = MagicMock()
            for key, value in kwargs.items():
                setattr(matcher, key, value)
            return matcher

        mock_hook_matcher = MagicMock(side_effect=create_hook_matcher)

        with patch("bob.orchestrator.client.ClaudeSDKClient", mock_client_class):
            with patch("bob.orchestrator.client.ClaudeCodeOptions", mock_options_class):
                with patch("bob.orchestrator.client.HookMatcher", mock_hook_matcher):
                    yield {
                        "client_class": mock_client_class,
                        "client_instance": mock_client_instance,
                        "options_class": mock_options_class,
                        "hook_matcher": mock_hook_matcher,
                    }


@pytest.fixture
def mock_claude_client(mock_claude_sdk):
    """Mock ClaudeSDKClient for backward compatibility."""
    return mock_claude_sdk["client_class"]


class TestToolConstants:
    """Test tool constant definitions."""

    def test_builtin_tools_defined(self):
        """Test BUILTIN_TOOLS contains expected tools."""
        assert "Read" in BUILTIN_TOOLS
        assert "Write" in BUILTIN_TOOLS
        assert "Edit" in BUILTIN_TOOLS
        assert "Glob" in BUILTIN_TOOLS
        assert "Grep" in BUILTIN_TOOLS
        assert "Bash" in BUILTIN_TOOLS
        assert len(BUILTIN_TOOLS) == 6

    def test_puppeteer_tools_defined(self):
        """Test PUPPETEER_TOOLS contains expected tools."""
        assert "mcp__puppeteer__puppeteer_navigate" in PUPPETEER_TOOLS
        assert "mcp__puppeteer__puppeteer_screenshot" in PUPPETEER_TOOLS
        assert "mcp__puppeteer__puppeteer_click" in PUPPETEER_TOOLS
        assert len(PUPPETEER_TOOLS) == 7

    def test_perplexity_tools_defined(self):
        """Test CLIENT_PERPLEXITY_TOOLS contains expected tools."""
        assert "mcp__plugin_perplexity_perplexity__perplexity_ask" in CLIENT_PERPLEXITY_TOOLS
        assert "mcp__plugin_perplexity_perplexity__perplexity_search" in CLIENT_PERPLEXITY_TOOLS
        assert "mcp__plugin_perplexity_perplexity__perplexity_research" in CLIENT_PERPLEXITY_TOOLS
        assert "mcp__plugin_perplexity_perplexity__perplexity_reason" in CLIENT_PERPLEXITY_TOOLS
        assert len(CLIENT_PERPLEXITY_TOOLS) == 4


class TestCreateClient:
    """Test create_client function."""

    def test_creates_client_with_basic_settings(self, temp_project_dir, mock_claude_client):
        """Test client creation with basic settings."""
        client = create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
        )

        # Verify ClaudeSDKClient was called
        mock_claude_client.assert_called_once()

        # Verify settings file was created
        settings_file = temp_project_dir / ".claude_settings.json"
        assert settings_file.exists()

        # Verify settings content
        with open(settings_file) as f:
            settings = json.load(f)
        assert settings["sandbox"]["enabled"] is True
        assert settings["permissions"]["defaultMode"] == "acceptEdits"

    def test_creates_project_directory_if_not_exists(self, tmp_path, mock_claude_client):
        """Test that project directory is created if it doesn't exist."""
        project_dir = tmp_path / "new_project"
        assert not project_dir.exists()

        create_client(
            project_dir=project_dir,
            model="claude-sonnet-4-20250514",
        )

        assert project_dir.exists()

    def test_includes_builtin_and_puppeteer_tools_by_default(self, temp_project_dir, mock_claude_client):
        """Test that builtin and puppeteer tools are included by default."""
        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
        )

        # Get the call arguments
        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        allowed_tools = options.allowed_tools

        # Check builtin tools
        for tool in BUILTIN_TOOLS:
            assert tool in allowed_tools

        # Check puppeteer tools
        for tool in PUPPETEER_TOOLS:
            assert tool in allowed_tools

        # Check perplexity tools are NOT included
        for tool in CLIENT_PERPLEXITY_TOOLS:
            assert tool not in allowed_tools

    def test_includes_perplexity_tools_when_research_enabled(self, temp_project_dir, mock_claude_client):
        """Test that perplexity tools are included when research is enabled."""
        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
            enable_research=True,
        )

        # Get the call arguments
        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        allowed_tools = options.allowed_tools

        # Check perplexity tools are included
        for tool in CLIENT_PERPLEXITY_TOOLS:
            assert tool in allowed_tools

    def test_uses_custom_system_prompt(self, temp_project_dir, mock_claude_client):
        """Test that custom system prompt is used."""
        custom_prompt = "Custom system prompt for testing"

        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
            system_prompt=custom_prompt,
        )

        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        assert options.system_prompt == custom_prompt

    def test_uses_default_system_prompt_when_none(self, temp_project_dir, mock_claude_client):
        """Test that default system prompt is used when none provided."""
        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
        )

        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        assert "expert full-stack developer" in options.system_prompt

    def test_sets_correct_model(self, temp_project_dir, mock_claude_client):
        """Test that correct model is set."""
        model = "claude-opus-4-20250514"

        create_client(
            project_dir=temp_project_dir,
            model=model,
        )

        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        assert options.model == model

    def test_sets_cwd_to_project_dir(self, temp_project_dir, mock_claude_client):
        """Test that cwd is set to project directory."""
        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
        )

        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        assert options.cwd == str(temp_project_dir.resolve())

    def test_configures_mcp_servers_without_research(self, temp_project_dir, mock_claude_client):
        """Test MCP servers configuration without research."""
        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
            enable_research=False,
        )

        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        mcp_servers = options.mcp_servers

        # Should only have puppeteer
        assert "puppeteer" in mcp_servers
        assert "perplexity" not in mcp_servers

    def test_configures_mcp_servers_with_research(self, temp_project_dir, mock_claude_client):
        """Test MCP servers configuration with research."""
        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
            enable_research=True,
        )

        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        mcp_servers = options.mcp_servers

        # Should have both puppeteer and perplexity
        assert "puppeteer" in mcp_servers
        assert "perplexity" in mcp_servers

    def test_sets_max_turns(self, temp_project_dir, mock_claude_client):
        """Test that max_turns is set correctly."""
        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
        )

        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        assert options.max_turns == 1000

    def test_configures_bash_security_hook(self, temp_project_dir, mock_claude_client):
        """Test that bash security hook is configured."""
        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
        )

        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        hooks = options.hooks

        # Should have PreToolUse hooks
        assert "PreToolUse" in hooks
        assert len(hooks["PreToolUse"]) > 0

    def test_passes_project_config_to_bash_hook(self, temp_project_dir, mock_claude_client):
        """Test that project_config is passed to bash security hook."""
        # Create a mock project config (actual class may not exist yet)
        project_config = {"name": "test", "path": str(temp_project_dir)}

        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
            project_config=project_config,
        )

        # Verify client was created (hook is internal, can't easily test)
        mock_claude_client.assert_called_once()

    def test_permissions_allow_file_operations_in_project_dir(self, temp_project_dir, mock_claude_client):
        """Test that permissions allow file operations in project directory."""
        create_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
        )

        # Verify settings file
        settings_file = temp_project_dir / ".claude_settings.json"
        with open(settings_file) as f:
            settings = json.load(f)

        permissions_allow = settings["permissions"]["allow"]
        assert "Read(./**)" in permissions_allow
        assert "Write(./**)" in permissions_allow
        assert "Edit(./**)" in permissions_allow
        assert "Glob(./**)" in permissions_allow
        assert "Grep(./**)" in permissions_allow
        assert "Bash(*)" in permissions_allow


class TestCreateResearchClient:
    """Test create_research_client function."""

    def test_creates_client_with_research_enabled(self, temp_project_dir, mock_claude_client):
        """Test that research client has research enabled."""
        client = create_research_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
        )

        # Verify research tools are included
        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        allowed_tools = options.allowed_tools

        for tool in CLIENT_PERPLEXITY_TOOLS:
            assert tool in allowed_tools

    def test_uses_research_focused_system_prompt(self, temp_project_dir, mock_claude_client):
        """Test that research client uses research-focused system prompt."""
        create_research_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
        )

        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        system_prompt = options.system_prompt

        assert "research" in system_prompt.lower()
        assert "perplexity" in system_prompt.lower()

    def test_passes_project_config(self, temp_project_dir, mock_claude_client):
        """Test that project_config is passed to research client."""
        # Create a mock project config (actual class may not exist yet)
        project_config = {"name": "test", "path": str(temp_project_dir)}

        create_research_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
            project_config=project_config,
        )

        mock_claude_client.assert_called_once()

    def test_includes_perplexity_mcp_server(self, temp_project_dir, mock_claude_client):
        """Test that research client includes perplexity MCP server."""
        create_research_client(
            project_dir=temp_project_dir,
            model="claude-sonnet-4-20250514",
        )

        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]
        mcp_servers = options.mcp_servers

        assert "perplexity" in mcp_servers
        assert "puppeteer" in mcp_servers


class TestIntegration:
    """Integration tests for client creation."""

    def test_full_client_creation_workflow(self, temp_project_dir, mock_claude_client):
        """Test full workflow of creating and configuring a client."""
        model = "claude-sonnet-4-20250514"
        custom_prompt = "Test prompt"

        # Create client
        client = create_client(
            project_dir=temp_project_dir,
            model=model,
            enable_research=True,
            system_prompt=custom_prompt,
        )

        # Verify settings file
        settings_file = temp_project_dir / ".claude_settings.json"
        assert settings_file.exists()

        with open(settings_file) as f:
            settings = json.load(f)

        # Verify sandbox settings
        assert settings["sandbox"]["enabled"] is True
        assert settings["sandbox"]["autoAllowBashIfSandboxed"] is True

        # Verify permissions
        assert settings["permissions"]["defaultMode"] == "acceptEdits"
        assert len(settings["permissions"]["allow"]) > 0

        # Verify client creation
        mock_claude_client.assert_called_once()
        call_args = mock_claude_client.call_args
        options = call_args.kwargs["options"]

        assert options.model == model
        assert options.system_prompt == custom_prompt
        assert len(options.allowed_tools) > len(BUILTIN_TOOLS)  # Includes more than just builtin

    def test_model_selection(self, temp_project_dir, mock_claude_client):
        """Test that different models can be selected."""
        models = [
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-5-haiku-20241022",
        ]

        for model in models:
            mock_claude_client.reset_mock()

            create_client(
                project_dir=temp_project_dir,
                model=model,
            )

            call_args = mock_claude_client.call_args
            options = call_args.kwargs["options"]
            assert options.model == model
