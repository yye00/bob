"""Tests for security module - bash command validation."""

import pytest
from bob.security import (
    bash_security_hook,
    get_allowed_commands,
    extract_commands,
    DEFAULT_ALLOWED_COMMANDS,
)


class TestGetAllowedCommands:
    """Test get_allowed_commands configuration."""

    def test_no_config_returns_defaults(self):
        allowed = get_allowed_commands(None)
        assert "ls" in allowed
        assert "git" in allowed
        assert allowed == DEFAULT_ALLOWED_COMMANDS

    def test_additional_commands(self):
        config = {"security": {"allowed_commands": ["custom-tool"]}}
        allowed = get_allowed_commands(config)
        assert "custom-tool" in allowed
        assert "ls" in allowed

    def test_blocked_commands(self):
        config = {"security": {"blocked_commands": ["rm", "git"]}}
        allowed = get_allowed_commands(config)
        assert "rm" not in allowed
        assert "git" not in allowed
        assert "ls" in allowed


class TestBashSecurityHook:
    """Test bash_security_hook integration."""

    @pytest.mark.asyncio
    async def test_allowed_command(self):
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"}
        }
        result = await bash_security_hook(input_data)
        assert result == {}

    @pytest.mark.asyncio
    async def test_blocked_command(self):
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "reboot"}
        }
        result = await bash_security_hook(input_data)
        assert result["decision"] == "block"

    @pytest.mark.asyncio
    async def test_custom_config_allows_command(self):
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "custom-tool"}
        }
        config = {"security": {"allowed_commands": ["custom-tool"]}}
        result = await bash_security_hook(input_data, project_config=config)
        assert result == {}
