"""
Bob - Build Orchestration Bot v3.

A recursive build orchestration system that uses Claude Code sub-agents
to research, plan, and execute software projects.

Bob extends Bob2 with:
- MCP Plugin Integration (Perplexity, Puppeteer, Superpowers)
- Automatic feature generation from natural language + PDFs
- Sub-agent orientation protocol for context recovery
- Research-enabled sub-agents for when implementation is stuck
"""

__version__ = "0.2.0"
__app_name__ = "Bob"

import importlib
import pathlib


def get_package_dir() -> pathlib.Path:
    """Return the root directory of the bob package."""
    return pathlib.Path(__file__).parent


def get_version() -> str:
    """Return the current bob version string."""
    return __version__


def get_schema_path() -> pathlib.Path:
    """Return the path to the SQL schema file used by bob."""
    return get_package_dir() / "schema.sql"


def has_subpackage(name: str) -> bool:
    """Check whether a bob subpackage (e.g. 'orchestrator') is available."""
    try:
        importlib.import_module(f"bob.{name}")
        return True
    except ImportError:
        return False


from bob.regression_attribution import detect_regression  # noqa: E402
