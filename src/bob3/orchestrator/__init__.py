"""
Bob3 Orchestrator - Sub-agent coordination and execution.

The orchestrator package manages the lifecycle of Claude Code sub-agents,
including spawning, orientation, task assignment, and result collection.

Key responsibilities:
- Spawning Claude Code sub-agents via the claude-code-sdk
- Providing orientation context to each sub-agent
- Managing MCP plugin configuration for sub-agents
- Tracking sub-agent progress and collecting results
"""

import pathlib


ORCHESTRATOR_DIR = pathlib.Path(__file__).parent


def get_orchestrator_dir() -> pathlib.Path:
    """Return the directory path of the orchestrator package."""
    return ORCHESTRATOR_DIR


def get_orchestrator_modules() -> list[str]:
    """Return names of Python modules in the orchestrator package directory.

    Scans the orchestrator package directory for .py files (excluding
    __init__.py and __pycache__) and returns their module names.
    """
    modules = []
    for py_file in sorted(ORCHESTRATOR_DIR.glob("*.py")):
        if py_file.name != "__init__.py":
            modules.append(py_file.stem)
    return modules
