"""RepoMapper MCP server launcher — BF-1 scope reduction (F-R7-611).

Vendors RepoMapper as a stdio MCP server instead of reimplementing
tree-sitter + PageRank from scratch. Bob is a thin MCP client;
RepoMapper does the symbol-graph and PageRank heavy lifting.

Public entry point: run_repomapper_mcp(workspace) → RepoMapperHandle
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from bob.brownfield.survey import (
    RepoMapperHandle,
    launch_repomapper_mcp,
    run_repomapper_mcp as _run_repomapper_mcp,
)

__all__ = [
    "RepoMapperHandle",
    "run_repomapper_mcp",
    "launch_repomapper_mcp",
]


def run_repomapper_mcp(
    workspace: Path,
    repomapper_cmd: Optional[list[str]] = None,
) -> RepoMapperHandle:
    """Launch the RepoMapper MCP server against *workspace* and return a live handle.

    BF-1 scope reduction (F-R7-611): Delegates symbol-graph + PageRank
    computation to RepoMapper rather than reimplementing tree-sitter + PageRank.
    Token saving: ~2K LoC custom impl → ~200 LoC MCP wrapper.

    The caller is responsible for calling handle.close() when done.

    Args:
        workspace: Root directory of the repo to map.
        repomapper_cmd: Override the RepoMapper MCP command. Defaults to
            ['repomapper-mcp'] when None.

    Returns:
        RepoMapperHandle wrapping the live stdio MCP server process.
    """
    return _run_repomapper_mcp(workspace, repomapper_cmd=repomapper_cmd)
