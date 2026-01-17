"""
Claude SDK Client Configuration
===============================

Functions for creating and configuring the Claude Agent SDK client.

Note: This module is designed to work with the Claude Code SDK when available.
For testing and development, these can be mocked.
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from claude_code_sdk import ClaudeCodeOptions, ClaudeSDKClient
    from claude_code_sdk.types import HookMatcher
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    # For testing/development without claude_code_sdk
    CLAUDE_SDK_AVAILABLE = False
    ClaudeSDKClient = None  # type: ignore
    ClaudeCodeOptions = None  # type: ignore
    HookMatcher = None  # type: ignore

from bob.security import bash_security_hook

# ProjectConfig is optional - will be used when available
try:
    from bob.models.config import ProjectConfig
except ImportError:
    ProjectConfig = None  # type: ignore


# Puppeteer MCP tools for browser automation
PUPPETEER_TOOLS = [
    "mcp__puppeteer__puppeteer_navigate",
    "mcp__puppeteer__puppeteer_screenshot",
    "mcp__puppeteer__puppeteer_click",
    "mcp__puppeteer__puppeteer_fill",
    "mcp__puppeteer__puppeteer_select",
    "mcp__puppeteer__puppeteer_hover",
    "mcp__puppeteer__puppeteer_evaluate",
]

# Perplexity MCP tools for research
# Note: Tool names use the full MCP server name prefix
PERPLEXITY_TOOLS = [
    "mcp__plugin_perplexity_perplexity__perplexity_ask",
    "mcp__plugin_perplexity_perplexity__perplexity_search",
    "mcp__plugin_perplexity_perplexity__perplexity_research",
    "mcp__plugin_perplexity_perplexity__perplexity_reason",
]

# Built-in tools
BUILTIN_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
]


def create_client(
    project_dir: Path,
    model: str,
    enable_research: bool = False,
    system_prompt: Optional[str] = None,
    project_config: Optional[Any] = None,
) -> Any:
    """
    Create a Claude Agent SDK client with multi-layered security.

    Args:
        project_dir: Directory for the project
        model: Claude model to use
        enable_research: If True, enable Perplexity MCP for research
        system_prompt: Optional custom system prompt
        project_config: Optional ProjectConfig for security settings

    Returns:
        Configured ClaudeSDKClient

    Security layers (defense in depth):
    1. Sandbox - OS-level bash command isolation prevents filesystem escape
    2. Permissions - File operations restricted to project_dir only
    3. Security hooks - Bash commands validated against an allowlist
       (see security.py for ALLOWED_COMMANDS)

    Raises:
        ImportError: If claude_code_sdk is not available
    """
    if not CLAUDE_SDK_AVAILABLE:
        raise ImportError(
            "claude_code_sdk is not available. "
            "This module requires the Claude Code SDK environment."
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    # if not api_key:
    #     raise ValueError(
    #         "ANTHROPIC_API_KEY environment variable not set.\n"
    #         "Get your API key from: https://console.anthropic.com/"
    #     )

    # Build allowed tools list
    allowed_tools = [*BUILTIN_TOOLS, *PUPPETEER_TOOLS]
    if enable_research:
        allowed_tools.extend(PERPLEXITY_TOOLS)

    # Build permissions list
    permissions_allow = [
        # Allow all file operations within the project directory
        "Read(./**)",
        "Write(./**)",
        "Edit(./**)",
        "Glob(./**)",
        "Grep(./**)",
        # Bash permission granted here, but actual commands are validated
        # by the bash_security_hook (see security.py for allowed commands)
        "Bash(*)",
        # Allow Puppeteer MCP tools for browser automation
        *PUPPETEER_TOOLS,
    ]
    if enable_research:
        permissions_allow.extend(PERPLEXITY_TOOLS)

    # Create comprehensive security settings
    # Note: Using relative paths ("./**") restricts access to project directory
    # since cwd is set to project_dir
    security_settings = {
        "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
        "permissions": {
            "defaultMode": "acceptEdits",  # Auto-approve edits within allowed directories
            "allow": permissions_allow,
        },
    }

    # Ensure project directory exists before creating settings file
    project_dir.mkdir(parents=True, exist_ok=True)

    # Write settings to a file in the project directory
    settings_file = project_dir / ".claude_settings.json"
    with open(settings_file, "w") as f:
        json.dump(security_settings, f, indent=2)

    # Build MCP servers config
    mcp_servers = {
        "puppeteer": {"command": "npx", "args": ["puppeteer-mcp-server"]}
    }
    if enable_research:
        # Add Perplexity MCP server (requires PERPLEXITY_API_KEY env var)
        mcp_servers["perplexity"] = {
            "command": "npx",
            "args": ["-y", "@perplexity-ai/mcp-server"]
        }

    print(f"Created security settings at {settings_file}")
    print("   - Sandbox enabled (OS-level bash isolation)")
    print(f"   - Filesystem restricted to: {project_dir.resolve()}")
    print("   - Bash commands restricted to allowlist (see security.py)")
    print(f"   - MCP servers: puppeteer{', perplexity' if enable_research else ''}")
    print(f"   - Model: {model}")
    print()

    default_system_prompt = "You are an expert full-stack developer building a production-quality web application."

    # Create bash security hook with project config
    def bash_hook(hook_data):
        return bash_security_hook(hook_data, project_config)

    return ClaudeSDKClient(
        options=ClaudeCodeOptions(
            model=model,
            system_prompt=system_prompt or default_system_prompt,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers,
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher="Bash", hooks=[bash_hook]),
                ],
            },
            max_turns=1000,
            cwd=str(project_dir.resolve()),
            settings=str(settings_file.resolve()),  # Use absolute path
        )
    )


def create_research_client(
    project_dir: Path,
    model: str,
    project_config: Optional[Any] = None,
) -> Any:
    """
    Create a client configured for research mode with Perplexity enabled.

    Args:
        project_dir: Directory for the project
        model: Claude model to use
        project_config: Optional ProjectConfig for security settings

    Returns:
        ClaudeSDKClient configured for research
    """
    return create_client(
        project_dir=project_dir,
        model=model,
        enable_research=True,
        system_prompt=(
            "You are a research-focused developer investigating solutions to coding problems. "
            "Use Perplexity tools to search for documentation, examples, and solutions. "
            "Document your findings clearly and apply them to fix issues."
        ),
        project_config=project_config,
    )
