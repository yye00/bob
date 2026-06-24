"""Tests for F104: MCP configuration module.

Validates that the MCP configuration module:
- Defines MCPServerConfig dataclass with required fields
- Configures BOB3_MEMORY_MCP with managed_by_bob3=True
- Configures PERPLEXITY_MCP with managed_by_bob3=False
- Configures PUPPETEER_MCP with managed_by_bob3=False
- Provides get_mcp_config() helper
- Provides get_bob3_managed_servers() helper
- build_perplexity_mcp_dict warns when PERPLEXITY_API_KEY is missing/empty
- validate_perplexity_available reports missing/empty PERPLEXITY_API_KEY
"""

import logging
import pathlib
from dataclasses import fields as dataclass_fields

import pytest

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
MODULE_PATH = SRC_DIR / "bob3" / "orchestrator" / "mcp_config.py"


# ===================================================================
# Step 1: File exists
# ===================================================================


class TestFileExists:
    """Step 1: src/bob3/orchestrator/mcp_config.py must exist."""

    def test_module_file_exists(self):
        assert MODULE_PATH.is_file(), f"Expected {MODULE_PATH} to exist"

    def test_module_is_non_empty(self):
        content = MODULE_PATH.read_text()
        assert len(content.strip()) > 100, "Module appears to be a stub"


# ===================================================================
# Step 2: MCPServerConfig dataclass
# ===================================================================


class TestMCPServerConfigDataclass:
    """Step 2: MCPServerConfig dataclass with required fields."""

    def test_is_dataclass(self):
        import dataclasses
        from bob3.orchestrator.mcp_config import MCPServerConfig

        assert dataclasses.is_dataclass(MCPServerConfig)

    def test_has_name_field(self):
        from bob3.orchestrator.mcp_config import MCPServerConfig

        field_names = {f.name for f in dataclass_fields(MCPServerConfig)}
        assert "name" in field_names

    def test_has_command_field(self):
        from bob3.orchestrator.mcp_config import MCPServerConfig

        field_names = {f.name for f in dataclass_fields(MCPServerConfig)}
        assert "command" in field_names

    def test_has_env_vars_field(self):
        from bob3.orchestrator.mcp_config import MCPServerConfig

        field_names = {f.name for f in dataclass_fields(MCPServerConfig)}
        assert "env_vars" in field_names

    def test_has_required_field(self):
        from bob3.orchestrator.mcp_config import MCPServerConfig

        field_names = {f.name for f in dataclass_fields(MCPServerConfig)}
        assert "required" in field_names

    def test_has_managed_by_bob3_field(self):
        from bob3.orchestrator.mcp_config import MCPServerConfig

        field_names = {f.name for f in dataclass_fields(MCPServerConfig)}
        assert "managed_by_bob3" in field_names

    def test_can_create_config(self):
        from bob3.orchestrator.mcp_config import MCPServerConfig

        config = MCPServerConfig(
            name="test-server",
            command=["echo", "hello"],
            env_vars=["TEST_VAR"],
            required=False,
            managed_by_bob3=True,
        )
        assert config.name == "test-server"
        assert config.command == ["echo", "hello"]
        assert config.env_vars == ["TEST_VAR"]
        assert config.required is False
        assert config.managed_by_bob3 is True


# ===================================================================
# Step 3: BOB3_MEMORY_MCP config (formerly TITANS_MEMORY_MCP)
# ===================================================================


class TestBob3MemoryMCPConfig:
    """Step 3: BOB3_MEMORY_MCP config with managed_by_bob3=True."""

    def test_memory_config_exists(self):
        from bob3.orchestrator.mcp_config import BOB3_MEMORY_MCP

        assert BOB3_MEMORY_MCP is not None

    def test_memory_is_mcp_server_config(self):
        from bob3.orchestrator.mcp_config import BOB3_MEMORY_MCP, MCPServerConfig

        assert isinstance(BOB3_MEMORY_MCP, MCPServerConfig)

    def test_memory_name(self):
        from bob3.orchestrator.mcp_config import BOB3_MEMORY_MCP

        assert BOB3_MEMORY_MCP.name == "bob3-memory"

    def test_memory_command(self):
        from bob3.orchestrator.mcp_config import BOB3_MEMORY_MCP

        import sys

        assert BOB3_MEMORY_MCP.command == [sys.executable, "-m", "bob3.memory_mcp"]

    def test_memory_managed_by_bob3(self):
        from bob3.orchestrator.mcp_config import BOB3_MEMORY_MCP

        assert BOB3_MEMORY_MCP.managed_by_bob3 is True

    def test_memory_env_vars_empty(self):
        """Bob3 Memory no longer requires OPENAI_API_KEY — everything is local."""
        from bob3.orchestrator.mcp_config import BOB3_MEMORY_MCP

        assert BOB3_MEMORY_MCP.env_vars == []

    def test_memory_is_required(self):
        from bob3.orchestrator.mcp_config import BOB3_MEMORY_MCP

        assert BOB3_MEMORY_MCP.required is True


# ===================================================================
# Step 4: PERPLEXITY_MCP config
# ===================================================================


class TestPerplexityMCPConfig:
    """Step 4: PERPLEXITY_MCP config with managed_by_bob3=False."""

    def test_perplexity_config_exists(self):
        from bob3.orchestrator.mcp_config import PERPLEXITY_MCP

        assert PERPLEXITY_MCP is not None

    def test_perplexity_is_mcp_server_config(self):
        from bob3.orchestrator.mcp_config import PERPLEXITY_MCP, MCPServerConfig

        assert isinstance(PERPLEXITY_MCP, MCPServerConfig)

    def test_perplexity_not_managed_by_bob3(self):
        from bob3.orchestrator.mcp_config import PERPLEXITY_MCP

        assert PERPLEXITY_MCP.managed_by_bob3 is False

    def test_perplexity_name(self):
        from bob3.orchestrator.mcp_config import PERPLEXITY_MCP

        assert "perplexity" in PERPLEXITY_MCP.name.lower()


# ===================================================================
# Step 5: PUPPETEER_MCP config
# ===================================================================


class TestPuppeteerMCPConfig:
    """Step 5: PUPPETEER_MCP config with managed_by_bob3=False."""

    def test_puppeteer_config_exists(self):
        from bob3.orchestrator.mcp_config import PUPPETEER_MCP

        assert PUPPETEER_MCP is not None

    def test_puppeteer_is_mcp_server_config(self):
        from bob3.orchestrator.mcp_config import PUPPETEER_MCP, MCPServerConfig

        assert isinstance(PUPPETEER_MCP, MCPServerConfig)

    def test_puppeteer_not_managed_by_bob3(self):
        from bob3.orchestrator.mcp_config import PUPPETEER_MCP

        assert PUPPETEER_MCP.managed_by_bob3 is False

    def test_puppeteer_name(self):
        from bob3.orchestrator.mcp_config import PUPPETEER_MCP

        assert "puppeteer" in PUPPETEER_MCP.name.lower()


# ===================================================================
# Step 6: get_mcp_config() helper
# ===================================================================


class TestGetMCPConfig:
    """Step 6: get_mcp_config() returns all MCP server configs."""

    def test_get_mcp_config_returns_dict(self):
        from bob3.orchestrator.mcp_config import get_mcp_config

        result = get_mcp_config()
        assert isinstance(result, dict)

    def test_get_mcp_config_contains_bob3_memory(self):
        from bob3.orchestrator.mcp_config import get_mcp_config

        result = get_mcp_config()
        names = {config.name for config in result.values()}
        assert "bob3-memory" in names

    def test_get_mcp_config_contains_perplexity(self):
        from bob3.orchestrator.mcp_config import get_mcp_config

        result = get_mcp_config()
        names = {config.name for config in result.values()}
        assert any("perplexity" in n.lower() for n in names)

    def test_get_mcp_config_contains_puppeteer(self):
        from bob3.orchestrator.mcp_config import get_mcp_config

        result = get_mcp_config()
        names = {config.name for config in result.values()}
        assert any("puppeteer" in n.lower() for n in names)

    def test_get_mcp_config_values_are_mcp_server_configs(self):
        from bob3.orchestrator.mcp_config import get_mcp_config, MCPServerConfig

        result = get_mcp_config()
        for config in result.values():
            assert isinstance(config, MCPServerConfig)

    def test_get_mcp_config_keys_are_server_names(self):
        from bob3.orchestrator.mcp_config import get_mcp_config

        result = get_mcp_config()
        for key, config in result.items():
            assert key == config.name


# ===================================================================
# Step 7: get_bob3_managed_servers() helper
# ===================================================================


class TestGetBob3ManagedServers:
    """Step 7: get_bob3_managed_servers() returns only servers Bob3 manages."""

    def test_returns_list(self):
        from bob3.orchestrator.mcp_config import get_bob3_managed_servers

        result = get_bob3_managed_servers()
        assert isinstance(result, list)

    def test_contains_bob3_memory(self):
        from bob3.orchestrator.mcp_config import get_bob3_managed_servers

        result = get_bob3_managed_servers()
        names = [config.name for config in result]
        assert "bob3-memory" in names

    def test_does_not_contain_perplexity(self):
        from bob3.orchestrator.mcp_config import get_bob3_managed_servers

        result = get_bob3_managed_servers()
        names = [config.name for config in result]
        assert not any("perplexity" in n.lower() for n in names)

    def test_does_not_contain_puppeteer(self):
        from bob3.orchestrator.mcp_config import get_bob3_managed_servers

        result = get_bob3_managed_servers()
        names = [config.name for config in result]
        assert not any("puppeteer" in n.lower() for n in names)

    def test_all_results_are_managed(self):
        from bob3.orchestrator.mcp_config import get_bob3_managed_servers

        result = get_bob3_managed_servers()
        for config in result:
            assert config.managed_by_bob3 is True

    def test_results_are_mcp_server_configs(self):
        from bob3.orchestrator.mcp_config import (
            get_bob3_managed_servers,
            MCPServerConfig,
        )

        result = get_bob3_managed_servers()
        for config in result:
            assert isinstance(config, MCPServerConfig)


# ===================================================================
# Integration: MCP config works with claude_executor
# ===================================================================


class TestMCPConfigIntegration:
    """MCP configs can be used with build_sub_agent_options."""

    def test_memory_config_produces_valid_mcp_servers_dict(self):
        """BOB3_MEMORY_MCP can be converted to an mcp_servers dict for the SDK."""
        from bob3.orchestrator.mcp_config import BOB3_MEMORY_MCP

        mcp_dict = {
            BOB3_MEMORY_MCP.name: {
                "type": "stdio",
                "command": BOB3_MEMORY_MCP.command[0],
                "args": BOB3_MEMORY_MCP.command[1:],
            }
        }
        assert BOB3_MEMORY_MCP.name in mcp_dict
        assert mcp_dict[BOB3_MEMORY_MCP.name]["type"] == "stdio"
        import sys

        assert mcp_dict[BOB3_MEMORY_MCP.name]["command"] == sys.executable

    def test_get_allowed_tools_returns_list(self):
        from bob3.orchestrator.mcp_config import get_allowed_tools

        result = get_allowed_tools()
        assert isinstance(result, list)

    def test_get_allowed_tools_contains_memory_tools(self):
        from bob3.orchestrator.mcp_config import get_allowed_tools

        result = get_allowed_tools()
        # Tools are named memory_* in the new configuration
        assert any("memory" in tool.lower() for tool in result)

    def test_get_allowed_tools_contains_expected_memory_tools(self):
        """The allowed tools list should contain the full set of memory_* tools."""
        from bob3.orchestrator.mcp_config import get_allowed_tools

        result = get_allowed_tools()
        expected = {
            "memory_add",
            "memory_search",
            "memory_get",
            "memory_record_feedback",
            "memory_archive",
            "memory_demote",
            "memory_delete",
            "memory_get_stats",
            "memory_get_candidates",
            "memory_list_pools",
        }
        assert expected.issubset(set(result))


# ===================================================================
# Perplexity API key validation
# ===================================================================


class TestPerplexityApiKeyValidation:
    """build_perplexity_mcp_dict / validate_perplexity_available behavior
    when PERPLEXITY_API_KEY is missing or empty.

    The MCP subprocess will start regardless, but every call would fail
    with an auth error at runtime. We need a clear warning so operators
    don't burn turns and budget on silent auth failures.
    """

    def test_warns_when_perplexity_api_key_missing(self, monkeypatch, caplog):
        from bob3.orchestrator.mcp_config import build_perplexity_mcp_dict

        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.mcp_config"):
            result = build_perplexity_mcp_dict()

        assert any(
            "PERPLEXITY_API_KEY" in record.getMessage()
            and record.levelno >= logging.WARNING
            for record in caplog.records
        ), f"Expected warning about PERPLEXITY_API_KEY in {caplog.records!r}"
        assert isinstance(result, dict)

    def test_warns_when_perplexity_api_key_empty(self, monkeypatch, caplog):
        from bob3.orchestrator.mcp_config import build_perplexity_mcp_dict

        monkeypatch.setenv("PERPLEXITY_API_KEY", "")
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.mcp_config"):
            build_perplexity_mcp_dict()

        assert any(
            "PERPLEXITY_API_KEY" in record.getMessage()
            and record.levelno >= logging.WARNING
            for record in caplog.records
        )

    def test_does_not_warn_when_perplexity_api_key_set(self, monkeypatch, caplog):
        from bob3.orchestrator.mcp_config import build_perplexity_mcp_dict

        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.mcp_config"):
            result = build_perplexity_mcp_dict()

        assert not any(
            "PERPLEXITY_API_KEY" in record.getMessage()
            and record.levelno >= logging.WARNING
            for record in caplog.records
        )
        # API key should be propagated into the MCP env block.
        from bob3.orchestrator.mcp_config import PERPLEXITY_MCP

        assert result[PERPLEXITY_MCP.name]["env"]["PERPLEXITY_API_KEY"] == "pplx-test-key"

    def test_validate_perplexity_available_missing(self, monkeypatch):
        from bob3.orchestrator.mcp_config import validate_perplexity_available

        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        ok, message = validate_perplexity_available()
        assert ok is False
        assert "PERPLEXITY_API_KEY" in message

    def test_validate_perplexity_available_empty(self, monkeypatch):
        from bob3.orchestrator.mcp_config import validate_perplexity_available

        monkeypatch.setenv("PERPLEXITY_API_KEY", "")
        ok, message = validate_perplexity_available()
        assert ok is False
        assert "PERPLEXITY_API_KEY" in message

    def test_validate_perplexity_available_set(self, monkeypatch):
        from bob3.orchestrator.mcp_config import validate_perplexity_available

        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
        ok, message = validate_perplexity_available()
        assert ok is True
        assert message == ""
