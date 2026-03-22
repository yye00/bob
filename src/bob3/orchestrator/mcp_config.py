"""MCP (Model Context Protocol) server configuration for Bob3 sub-agents.

Defines configuration for each MCP server that Bob3 sub-agents can use.
Only TITANS-MEMORY is started and managed by Bob3 directly. Perplexity
and Puppeteer are already available in the Claude Code environment.

MCP Servers:
    TITANS-MEMORY: Persistent memory with surprise-based learning (managed by Bob3)
    PERPLEXITY: Web-grounded search and research (available via Claude Code)
    PUPPETEER: Browser automation (available via Claude Code)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for a single MCP server.

    Attributes:
        name: Unique identifier for the MCP server.
        command: Shell command to start the server (empty for unmanaged servers).
        env_vars: Environment variables required by this server.
        required: Whether this server is required for Bob3 to function.
        managed_by_bob3: Whether Bob3 is responsible for starting this server.
    """

    name: str
    command: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=list)
    required: bool = False
    managed_by_bob3: bool = False


# ---------------------------------------------------------------------------
# Server configurations
# ---------------------------------------------------------------------------

TITANS_MEMORY_MCP = MCPServerConfig(
    name="titans-memory",
    command=[
        "uv",
        "--directory",
        "/home/captain/work/AI/titans-memory",
        "run",
        "titans-memory",
    ],
    env_vars=["OPENAI_API_KEY"],
    required=True,
    managed_by_bob3=True,
)

PERPLEXITY_MCP = MCPServerConfig(
    name="perplexity",
    command=[],
    env_vars=["PERPLEXITY_API_KEY"],
    required=False,
    managed_by_bob3=False,
)

PUPPETEER_MCP = MCPServerConfig(
    name="puppeteer",
    command=[],
    env_vars=[],
    required=False,
    managed_by_bob3=False,
)

# All known MCP server configs
_ALL_CONFIGS: list[MCPServerConfig] = [
    TITANS_MEMORY_MCP,
    PERPLEXITY_MCP,
    PUPPETEER_MCP,
]

# TITANS Memory tool names that sub-agents can use
_TITANS_TOOLS: list[str] = [
    "titans_add",
    "titans_search",
    "titans_get",
    "titans_update",
    "titans_delete",
    "titans_record_feedback",
    "titans_get_candidates",
    "titans_demote",
    "titans_archive",
    "titans_get_stats",
    "titans_route",
    "titans_search_pool",
]

# Perplexity MCP tool names (available via the Claude Code MCP plugin)
_PERPLEXITY_TOOLS: list[str] = [
    "mcp__plugin_perplexity_perplexity__perplexity_ask",
    "mcp__plugin_perplexity_perplexity__perplexity_search",
    "mcp__plugin_perplexity_perplexity__perplexity_research",
    "mcp__plugin_perplexity_perplexity__perplexity_reason",
]

# Puppeteer MCP tool names (available via the @anthropic/puppeteer-mcp plugin)
_PUPPETEER_TOOLS: list[str] = [
    "mcp__puppeteer__puppeteer_navigate",
    "mcp__puppeteer__puppeteer_screenshot",
    "mcp__puppeteer__puppeteer_click",
    "mcp__puppeteer__puppeteer_fill",
    "mcp__puppeteer__puppeteer_select",
    "mcp__puppeteer__puppeteer_hover",
    "mcp__puppeteer__puppeteer_evaluate",
]


def get_mcp_config() -> dict[str, MCPServerConfig]:
    """Return all MCP server configurations keyed by server name."""
    return {config.name: config for config in _ALL_CONFIGS}


def get_bob3_managed_servers() -> list[MCPServerConfig]:
    """Return only MCP servers that Bob3 needs to start and manage."""
    return [config for config in _ALL_CONFIGS if config.managed_by_bob3]


def get_allowed_tools() -> list[str]:
    """Return the list of MCP tool names available to sub-agents.

    Currently returns TITANS Memory tools. Perplexity and Puppeteer
    tools are available automatically via the Claude Code environment.
    """
    return list(_TITANS_TOOLS)


def get_perplexity_tools() -> list[str]:
    """Return the list of Perplexity MCP tool names."""
    return list(_PERPLEXITY_TOOLS)


def get_puppeteer_tools() -> list[str]:
    """Return the list of Puppeteer MCP tool names."""
    return list(_PUPPETEER_TOOLS)


def build_perplexity_mcp_dict() -> dict[str, Any]:
    """Build an mcp_servers dict entry for the Perplexity MCP plugin.

    Returns a dict suitable for passing to ClaudeCodeOptions.mcp_servers.
    The Perplexity MCP uses npx to run the @anthropic/perplexity-mcp server.
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    return {
        PERPLEXITY_MCP.name: {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@anthropic/perplexity-mcp"],
            "env": {
                "PERPLEXITY_API_KEY": api_key,
            },
        }
    }


def build_puppeteer_mcp_dict() -> dict[str, Any]:
    """Build an mcp_servers dict entry for the Puppeteer MCP plugin.

    Returns a dict suitable for passing to ClaudeCodeOptions.mcp_servers.
    The Puppeteer MCP uses npx to run the @anthropic/puppeteer-mcp server.
    """
    return {
        PUPPETEER_MCP.name: {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@anthropic/puppeteer-mcp"],
        }
    }
