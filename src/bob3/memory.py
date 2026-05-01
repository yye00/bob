"""Bob3 persistent memory layer.

A thin wrapper around mem0ai that provides semantic memory storage with
pool-based categorization and feedback tracking. Uses a fully local
in-process stack: FastEmbed (ONNX, CPU) for embeddings, Qdrant on-disk for
vector storage. No external API keys, no background daemons required —
the embedding model downloads once to disk on first use.

Anthropic does not offer an embedding API, which is why mem0's embedder
slot is filled by FastEmbed rather than Claude. All sub-agent LLM calls
still go through the Claude Code SDK; only the vector embedding step is
local.

Usage:
    from bob3.memory import BobMemory

    mem = BobMemory()
    result = mem.add("Feature F006 must not use subprocess", pool="lessons")
    hits = mem.search("how should claude be invoked", pool="lessons", limit=5)
    mem.record_feedback(memory_id=hits[0]["id"], success=True)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mem0 import Memory

logger = logging.getLogger(__name__)

VALID_POOLS: frozenset[str] = frozenset({"facts", "preferences", "lessons", "context"})

# BAAI/bge-small-en-v1.5 is a compact, high-quality 384-dim English
# embedding model (~90MB ONNX). FastEmbed downloads it once to disk on
# first use and runs it entirely on CPU in-process.
DEFAULT_EMBEDDER_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_EMBEDDING_DIMS = 384
DEFAULT_USER_ID = "bob3_default"


def _bob3_data_dir() -> Path:
    """Return the persistent data directory for bob3 memory."""
    override = os.environ.get("BOB3_MEMORY_DIR")
    if override:
        path = Path(override)
    else:
        path = Path.home() / ".local" / "share" / "bob3"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _default_config() -> dict[str, Any]:
    """Build the default mem0 configuration for bob3.

    Uses FastEmbed for embeddings and Qdrant on-disk for vector storage.
    The LLM slot is present (mem0 requires it) but unused because we
    always call .add() with infer=False.
    """
    data_dir = _bob3_data_dir()
    qdrant_path = str(data_dir / "qdrant")

    embedder_model = os.environ.get("BOB3_EMBEDDER_MODEL", DEFAULT_EMBEDDER_MODEL)
    embedding_dims = int(os.environ.get("BOB3_EMBEDDING_DIMS", str(DEFAULT_EMBEDDING_DIMS)))

    return {
        "llm": {
            "provider": "openai",
            "config": {"model": "gpt-4o-mini", "api_key": "unused-infer-false"},
        },
        "embedder": {
            "provider": "fastembed",
            "config": {
                "model": embedder_model,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "bob3_memory",
                "embedding_model_dims": embedding_dims,
                "path": qdrant_path,
            },
        },
    }


@dataclass
class MemoryRecord:
    """A single memory retrieval result."""

    id: str
    content: str
    pool: str
    score: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "pool": self.pool,
            "score": self.score,
            "metadata": self.metadata,
        }


def _validate_pool(pool: str | None) -> None:
    if pool is not None and pool not in VALID_POOLS:
        raise ValueError(
            f"Invalid memory pool '{pool}'. Must be one of: {', '.join(sorted(VALID_POOLS))}"
        )


def _classify_pool(content: str) -> str:
    """Heuristic routing for content without an explicit pool.

    Simple keyword matching. If nothing matches, defaults to 'facts'.
    """
    text = content.lower()
    if any(kw in text for kw in ("bug", "fix", "debug", "error", "exception", "failure", "lesson")):
        return "lessons"
    if any(kw in text for kw in ("prefer", "style", "always use", "never use", "convention")):
        return "preferences"
    if any(kw in text for kw in ("currently", "working on", "session", "in progress", "right now")):
        return "context"
    return "facts"


class BobMemory:
    """In-process memory client backed by mem0 + FastEmbed + Qdrant.

    Thread-safe for reads. Writes are serialized by mem0 internally.
    Use this from bob3 itself. Sub-agents should call the memory MCP
    server (see memory_mcp.py) which wraps this same backend.
    """

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> None:
        self._user_id = user_id
        self._mem = Memory.from_config(config or _default_config())

    def add(
        self,
        content: str,
        *,
        pool: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store a memory. Returns the stored record.

        Args:
            content: The memory text.
            pool: One of facts/preferences/lessons/context. If None, routed
                automatically based on content keywords.
            metadata: Extra metadata keys to store alongside.
        """
        _validate_pool(pool)
        chosen_pool = pool or _classify_pool(content)
        now = datetime.now(timezone.utc).isoformat()

        meta: dict[str, Any] = {
            "pool": chosen_pool,
            "times_applied": 0,
            "times_successful": 0,
            "usefulness_score": 0.0,
            "status": "active",
            "created_at": now,
            "last_accessed_at": now,
        }
        if metadata:
            meta.update(metadata)

        # infer=False skips mem0's LLM-based fact extraction. We store raw content.
        result = self._mem.add(
            content,
            user_id=self._user_id,
            metadata=meta,
            infer=False,
        )

        # mem0 returns either a dict with 'results' or a list
        results = result.get("results", []) if isinstance(result, dict) else result
        if results and isinstance(results, list):
            first = results[0]
            return {
                "id": first.get("id"),
                "content": first.get("memory", content),
                "pool": chosen_pool,
                "metadata": meta,
            }
        logger.warning("mem0.add returned unexpected shape: %r", result)
        return {"id": None, "content": content, "pool": chosen_pool, "metadata": meta}

    def search(
        self,
        query: str,
        *,
        pool: str | None = None,
        limit: int = 10,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """Semantic search. Returns a list of memory dicts ranked by similarity."""
        _validate_pool(pool)

        raw = self._mem.search(query, user_id=self._user_id, limit=limit * 2)
        items = raw.get("results", []) if isinstance(raw, dict) else raw
        out: list[dict[str, Any]] = []
        for item in items or []:
            meta = item.get("metadata") or {}
            if not include_archived and meta.get("status") == "archived":
                continue
            if pool and meta.get("pool") != pool:
                continue
            out.append({
                "id": item.get("id"),
                "content": item.get("memory", ""),
                "pool": meta.get("pool", "facts"),
                "score": item.get("score", 0.0),
                "metadata": meta,
            })
            if len(out) >= limit:
                break
        return out

    def get(self, memory_id: str) -> dict[str, Any] | None:
        """Retrieve a single memory by id, or None if not found."""
        try:
            item = self._mem.get(memory_id)
        except Exception as exc:
            logger.debug("get(%s) failed: %s", memory_id, exc)
            return None
        if not item:
            return None
        meta = item.get("metadata") or {}
        return {
            "id": item.get("id", memory_id),
            "content": item.get("memory", ""),
            "pool": meta.get("pool", "facts"),
            "metadata": meta,
        }

    def update_metadata(self, memory_id: str, updates: dict[str, Any]) -> bool:
        """Merge updates into a memory's metadata. Returns True on success.

        mem0's public Memory.update() doesn't accept metadata, and its
        vector-store wrapper requires a vector to be provided. We use
        Qdrant's native set_payload which updates payload fields in place
        without touching the vector.
        """
        try:
            vs = self._mem.vector_store
            vs.client.set_payload(
                collection_name=vs.collection_name,
                payload=updates,
                points=[memory_id],
            )
            return True
        except Exception as exc:
            logger.warning("update_metadata(%s) failed: %s", memory_id, exc)
            return False

    def record_feedback(self, memory_id: str, success: bool) -> bool:
        """Record feedback on whether a memory was helpful.

        Updates times_applied, times_successful, and usefulness_score.
        Read-then-write; not atomic across concurrent writers.

        Reads counters directly from the Qdrant payload via
        ``_read_payload`` rather than ``self.get()``. mem0's ``.get()``
        does not reliably round-trip arbitrary payload fields like
        ``times_applied`` / ``times_successful`` / ``usefulness_score``,
        so reading through it would always return zero counters and reset
        the running totals on every feedback call (regression bug fix).
        """
        payload = self._read_payload(memory_id)
        if payload is None:
            return False
        applied = int(payload.get("times_applied", 0)) + 1
        successful = int(payload.get("times_successful", 0)) + (1 if success else 0)
        usefulness = (successful / applied) if applied > 0 else 0.0
        return self.update_metadata(
            memory_id,
            {
                "times_applied": applied,
                "times_successful": successful,
                "usefulness_score": usefulness,
                "last_accessed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _read_payload(self, memory_id: str) -> dict[str, Any] | None:
        """Read the raw Qdrant payload for a memory. Returns None if missing."""
        try:
            vs = self._mem.vector_store
            points = vs.client.retrieve(
                collection_name=vs.collection_name,
                ids=[memory_id],
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                return None
            return dict(points[0].payload or {})
        except Exception as exc:
            logger.debug("_read_payload(%s) failed: %s", memory_id, exc)
            return None

    def archive(self, memory_id: str) -> bool:
        return self.update_metadata(memory_id, {"status": "archived"})

    def demote(self, memory_id: str) -> bool:
        return self.update_metadata(memory_id, {"status": "demoted"})

    def delete(self, memory_id: str) -> bool:
        try:
            self._mem.delete(memory_id)
            return True
        except Exception as exc:
            logger.warning("delete(%s) failed: %s", memory_id, exc)
            return False

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate stats: counts per pool, per status."""
        try:
            all_memories = self._mem.get_all(user_id=self._user_id)
        except Exception as exc:
            logger.warning("get_stats failed: %s", exc)
            return {"total": 0, "pools": {}, "statuses": {}}

        items = all_memories.get("results", []) if isinstance(all_memories, dict) else all_memories
        by_pool: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for item in items or []:
            meta = item.get("metadata") or {}
            pool = meta.get("pool", "unknown")
            status = meta.get("status", "active")
            by_pool[pool] = by_pool.get(pool, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
        return {
            "total": len(items or []),
            "pools": by_pool,
            "statuses": by_status,
        }

    def get_demotion_candidates(
        self,
        *,
        min_times_applied: int = 5,
        max_usefulness: float = 0.3,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return memories that have been used enough times and performed poorly."""
        try:
            raw = self._mem.get_all(user_id=self._user_id)
        except Exception as exc:
            logger.warning("get_demotion_candidates failed: %s", exc)
            return []
        items = raw.get("results", []) if isinstance(raw, dict) else raw
        candidates = []
        for item in items or []:
            meta = item.get("metadata") or {}
            if meta.get("status") != "active":
                continue
            if int(meta.get("times_applied", 0)) < min_times_applied:
                continue
            if float(meta.get("usefulness_score", 0.0)) > max_usefulness:
                continue
            candidates.append({
                "id": item.get("id"),
                "content": item.get("memory", ""),
                "pool": meta.get("pool", "facts"),
                "metadata": meta,
            })
            if len(candidates) >= limit:
                break
        return candidates
