"""Stdio MCP server exposing bob memory tools to sub-agents.

This is a thin wrapper around bob.memory.BobMemory. When bob spawns a
sub-agent via the Claude Code SDK, the sub-agent's MCP configuration
launches this server as a subprocess. The server exposes tools named
``memory_add``, ``memory_search``, ``memory_record_feedback``,
``memory_get_stats``, ``memory_archive``, and ``memory_demote``.

Run directly (e.g. via ``python -m bob.memory_mcp``) to start the
server over stdio.

Defense in depth — input-size cap on memory_add (R5-005)
--------------------------------------------------------
Sub-agents call ``memory_add`` over stdio with arbitrary content. Without
a cap, a malicious sub-agent could ``memory_add(content="X" * 10**8, ...)``
to OOM the embedder, fill the Qdrant index disk, or — more subtly — spam
many manipulative entries to poison the future-search ranking. We refuse
content larger than ``MAX_MEMORY_CONTENT_BYTES`` (default 8000 bytes,
configurable via the ``BOB_MAX_MEMORY_CONTENT_BYTES`` env var). 8000
bytes comfortably fits a focused, useful memory and is well below the
typical embedding model's input limit; a sub-agent that wants more
should be writing a doc, not a memory.
"""

import logging
import os
import uuid
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from bob.memory import BobMemory, VALID_POOLS

logger = logging.getLogger(__name__)

# Maximum size of a single memory's content (UTF-8 bytes). Configurable
# via ``BOB_MAX_MEMORY_CONTENT_BYTES``; falls back to 8000 if the env
# var is unset, non-numeric, or non-positive. Concise memories retrieve
# better, embed faster, and aren't a DoS vector — keep it tight.
_DEFAULT_MAX_MEMORY_CONTENT_BYTES = 8000


def _resolve_max_memory_content_bytes() -> int:
    """Read ``BOB_MAX_MEMORY_CONTENT_BYTES`` from the environment.

    Returns the configured cap. Falls back to
    ``_DEFAULT_MAX_MEMORY_CONTENT_BYTES`` on parse error / non-positive
    value. Resolved each call so tests can monkeypatch the env var
    without re-importing the module.
    """
    raw = os.environ.get("BOB_MAX_MEMORY_CONTENT_BYTES")
    if not raw:
        return _DEFAULT_MAX_MEMORY_CONTENT_BYTES
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_MEMORY_CONTENT_BYTES
    return value if value > 0 else _DEFAULT_MAX_MEMORY_CONTENT_BYTES


# Public alias kept stable for tests / introspection.
MAX_MEMORY_CONTENT_BYTES = _DEFAULT_MAX_MEMORY_CONTENT_BYTES

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


app = FastMCP("bob-memory")


@app.tool()
def memory_add(
    content: str,
    pool: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Store a memory.

    Args:
        content: Memory content to store. Max size is
            ``BOB_MAX_MEMORY_CONTENT_BYTES`` UTF-8 bytes (default 8000).
            Larger content is refused with a structured error.
        pool: Optional pool (facts, preferences, lessons, context).
              Auto-classified if None.
        metadata: Optional extra metadata to store alongside.
    """
    # R5-005: cap content length to avoid OOM-on-embed and disk-fill DoS
    # via the MCP surface. ``len(content.encode("utf-8"))`` measures the
    # actual on-the-wire size — Python's ``len(str)`` only counts code
    # points and undercounts non-ASCII content. Refuse with a structured
    # error rather than letting the backend handle a 100MB string.
    if not isinstance(content, str):
        return {"success": False, "error": "content must be a string"}
    cap = _resolve_max_memory_content_bytes()
    try:
        encoded_len = len(content.encode("utf-8"))
    except UnicodeError:
        return {"success": False, "error": "content is not valid UTF-8"}
    if encoded_len > cap:
        return {
            "success": False,
            "error": f"content exceeds maximum length ({cap} bytes)",
        }
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
    """Entry point for ``python -m bob.memory_mcp``."""
    app.run()


if __name__ == "__main__":
    main()
