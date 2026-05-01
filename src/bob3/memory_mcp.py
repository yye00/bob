"""Stdio MCP server exposing bob3 memory tools to sub-agents.

This is a thin wrapper around bob3.memory.BobMemory. When bob3 spawns a
sub-agent via the Claude Code SDK, the sub-agent's MCP configuration
launches this server as a subprocess. The server exposes tools named
``memory_add``, ``memory_search``, ``memory_record_feedback``,
``memory_get_stats``, ``memory_archive``, and ``memory_demote``.

Run directly (e.g. via ``python -m bob3.memory_mcp``) to start the
server over stdio.
"""

import logging
import uuid
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from bob3.memory import BobMemory, VALID_POOLS

logger = logging.getLogger(__name__)

_memory: Optional[BobMemory] = None


def _mem() -> BobMemory:
    """Lazy-initialize the BobMemory instance on first use."""
    global _memory
    if _memory is None:
        _memory = BobMemory()
    return _memory


def _validate_memory_id(memory_id: str) -> str | None:
    """Validate that ``memory_id`` is a UUID string.

    Returns the canonical (lowercase, hyphenated) UUID string if valid,
    or ``None`` for empty / non-string / malformed input. Qdrant uses
    UUIDs as point IDs, so any other shape is a programming error or
    untrusted input that should never be forwarded to the storage layer.
    """
    if not isinstance(memory_id, str):
        return None
    candidate = memory_id.strip()
    if not candidate:
        return None
    try:
        return str(uuid.UUID(candidate))
    except (ValueError, AttributeError, TypeError):
        return None


_INVALID_MEMORY_ID_ERROR: dict[str, Any] = {
    "success": False,
    "error": "invalid memory_id: must be a UUID",
}


app = FastMCP("bob3-memory")


@app.tool()
def memory_add(
    content: str,
    pool: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Store a memory.

    Args:
        content: Memory content to store.
        pool: Optional pool (facts, preferences, lessons, context).
              Auto-classified if None.
        metadata: Optional extra metadata to store alongside.
    """
    return _mem().add(content, pool=pool, metadata=metadata)


@app.tool()
def memory_search(
    query: str,
    pool: Optional[str] = None,
    limit: int = 10,
    include_archived: bool = False,
) -> list:
    """Semantic search over memories. Returns ranked list."""
    return _mem().search(query, pool=pool, limit=limit, include_archived=include_archived)


@app.tool()
def memory_get(memory_id: str) -> dict | None:
    """Retrieve a single memory by id."""
    valid_id = _validate_memory_id(memory_id)
    if valid_id is None:
        return dict(_INVALID_MEMORY_ID_ERROR)
    return _mem().get(valid_id)


@app.tool()
def memory_record_feedback(memory_id: str, success: bool) -> dict:
    """Record feedback on a memory (True=helpful, False=not)."""
    valid_id = _validate_memory_id(memory_id)
    if valid_id is None:
        return dict(_INVALID_MEMORY_ID_ERROR)
    ok = _mem().record_feedback(valid_id, success)
    return {"success": ok}


@app.tool()
def memory_archive(memory_id: str) -> dict:
    """Archive a memory so it no longer appears in searches."""
    valid_id = _validate_memory_id(memory_id)
    if valid_id is None:
        return dict(_INVALID_MEMORY_ID_ERROR)
    return {"success": _mem().archive(valid_id)}


@app.tool()
def memory_demote(memory_id: str) -> dict:
    """Demote a memory (lowers its visibility)."""
    valid_id = _validate_memory_id(memory_id)
    if valid_id is None:
        return dict(_INVALID_MEMORY_ID_ERROR)
    return {"success": _mem().demote(valid_id)}


@app.tool()
def memory_delete(memory_id: str) -> dict:
    """Permanently delete a memory."""
    valid_id = _validate_memory_id(memory_id)
    if valid_id is None:
        return dict(_INVALID_MEMORY_ID_ERROR)
    return {"success": _mem().delete(valid_id)}


@app.tool()
def memory_get_stats() -> dict:
    """Return aggregate stats: total count, counts per pool, per status."""
    return _mem().get_stats()


@app.tool()
def memory_get_candidates(
    min_times_applied: int = 5,
    max_usefulness: float = 0.3,
    limit: int = 50,
) -> list[dict]:
    """Return memories that have been used enough and perform poorly."""
    return _mem().get_demotion_candidates(
        min_times_applied=min_times_applied,
        max_usefulness=max_usefulness,
        limit=limit,
    )


@app.tool()
def memory_list_pools() -> list:
    """Return the set of valid memory pool names."""
    return sorted(VALID_POOLS)


def main() -> None:
    """Entry point for ``python -m bob3.memory_mcp``."""
    app.run()


if __name__ == "__main__":
    main()
