"""
Bob3 - Build Orchestration Bot v3.

A recursive build orchestration system that uses Claude Code sub-agents
to research, plan, and execute software projects.

Bob3 extends Bob2 with:
- MCP Plugin Integration (Perplexity, Puppeteer, Superpowers)
- Automatic feature generation from natural language + PDFs
- Sub-agent orientation protocol for context recovery
- Research-enabled sub-agents for when implementation is stuck
"""

__version__ = "0.2.0"
__app_name__ = "Bob3"

import importlib
import pathlib


def get_package_dir() -> pathlib.Path:
    """Return the root directory of the bob3 package."""
    return pathlib.Path(__file__).parent


def get_version() -> str:
    """Return the current bob3 version string."""
    return __version__


def get_schema_path() -> pathlib.Path:
    """Return the path to the SQL schema file used by bob3."""
    return get_package_dir() / "schema.sql"


def has_subpackage(name: str) -> bool:
    """Check whether a bob3 subpackage (e.g. 'orchestrator') is available."""
    try:
        importlib.import_module(f"bob3.{name}")
        return True
    except ImportError:
        return False
