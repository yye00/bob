"""Tests for F104: MCP configuration module.

Validates that the MCP configuration module:
- Defines MCPServerConfig dataclass with required fields
- Configures TITANS_MEMORY_MCP with managed_by_bob3=True
- Configures PERPLEXITY_MCP with managed_by_bob3=False
- Configures PUPPETEER_MCP with managed_by_bob3=False
- Provides get_mcp_config() helper
- Provides get_bob3_managed_servers() helper
"""

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
# Step 3: TITANS_MEMORY_MCP config
# ===================================================================


class TestTitansMemoryMCPConfig:
    """Step 3: TITANS_MEMORY_MCP config with managed_by_bob3=True."""

    def test_titans_memory_config_exists(self):
        from bob3.orchestrator.mcp_config import TITANS_MEMORY_MCP

        assert TITANS_MEMORY_MCP is not None

    def test_titans_memory_is_mcp_server_config(self):
        from bob3.orchestrator.mcp_config import TITANS_MEMORY_MCP, MCPServerConfig

        assert isinstance(TITANS_MEMORY_MCP, MCPServerConfig)

    def test_titans_memory_name(self):
        from bob3.orchestrator.mcp_config import TITANS_MEMORY_MCP

        assert "titans" in TITANS_MEMORY_MCP.name.lower()

    def test_titans_memory_command(self):
        from bob3.orchestrator.mcp_config import TITANS_MEMORY_MCP

        assert TITANS_MEMORY_MCP.command == [
            "uv",
            "--directory",
            "/home/captain/work/AI/titans-memory",
            "run",
            "titans-memory",
        ]

    def test_titans_memory_managed_by_bob3(self):
        from bob3.orchestrator.mcp_config import TITANS_MEMORY_MCP

        assert TITANS_MEMORY_MCP.managed_by_bob3 is True

    def test_titans_memory_requires_openai_key(self):
        from bob3.orchestrator.mcp_config import TITANS_MEMORY_MCP

        assert "OPENAI_API_KEY" in TITANS_MEMORY_MCP.env_vars

    def test_titans_memory_is_required(self):
        from bob3.orchestrator.mcp_config import TITANS_MEMORY_MCP

        assert TITANS_MEMORY_MCP.required is True


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

    def test_get_mcp_config_contains_titans(self):
        from bob3.orchestrator.mcp_config import get_mcp_config

        result = get_mcp_config()
        names = {config.name for config in result.values()}
        assert any("titans" in n.lower() for n in names)

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

    def test_contains_titans_memory(self):
        from bob3.orchestrator.mcp_config import get_bob3_managed_servers

        result = get_bob3_managed_servers()
        names = [config.name for config in result]
        assert any("titans" in n.lower() for n in names)

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
        from bob3.orchestrator.mcp_config import get_bob3_managed_servers, MCPServerConfig

        result = get_bob3_managed_servers()
        for config in result:
            assert isinstance(config, MCPServerConfig)


# ===================================================================
# Integration: MCP config works with claude_executor
# ===================================================================


class TestMCPConfigIntegration:
    """MCP configs can be used with build_sub_agent_options."""

    def test_titans_config_produces_valid_mcp_servers_dict(self):
        """TITANS_MEMORY_MCP can be converted to an mcp_servers dict for the SDK."""
        from bob3.orchestrator.mcp_config import TITANS_MEMORY_MCP

        mcp_dict = {
            TITANS_MEMORY_MCP.name: {
                "type": "stdio",
                "command": TITANS_MEMORY_MCP.command[0],
                "args": TITANS_MEMORY_MCP.command[1:],
            }
        }
        assert TITANS_MEMORY_MCP.name in mcp_dict
        assert mcp_dict[TITANS_MEMORY_MCP.name]["type"] == "stdio"
        assert mcp_dict[TITANS_MEMORY_MCP.name]["command"] == "uv"

    def test_get_allowed_tools_returns_list(self):
        from bob3.orchestrator.mcp_config import get_allowed_tools

        result = get_allowed_tools()
        assert isinstance(result, list)

    def test_get_allowed_tools_contains_titans_tools(self):
        from bob3.orchestrator.mcp_config import get_allowed_tools

        result = get_allowed_tools()
        assert any("titans" in tool.lower() for tool in result)
