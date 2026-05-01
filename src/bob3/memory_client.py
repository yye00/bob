"""Bob3 in-process memory client.

Provides an async-compatible API over bob3.memory.BobMemory, mirroring the
shape of the old TitansMemoryClient (which went through a Claude sub-agent
to call MCP tools). This client calls BobMemory directly — no sub-agent
round-trip — because bob3 itself runs in the same process as the memory
backend. Sub-agents spawned by bob3 still use the MCP server (bob3.memory_mcp)
to access the same underlying store.

The async signatures are preserved for compatibility with the previous
TitansMemoryClient; the underlying calls are synchronous.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bob3.memory import BobMemory, VALID_POOLS

logger = logging.getLogger(__name__)


@dataclass
class MemoryResult:
    """Result of a memory operation.

    Attributes:
        success: Whether the operation completed without error.
        data: The response data (dict or list depending on operation).
        error: Error message if success is False.
        raw_text: Raw text response (kept for backward compatibility;
            always empty for the in-process client).
    """

    success: bool
    data: Any = None
    error: str = ""
    raw_text: str = ""


def _validate_pool(pool: str | None) -> None:
    if pool is not None and pool not in VALID_POOLS:
        raise ValueError(
            f"Invalid memory pool '{pool}'. Must be one of: {', '.join(sorted(VALID_POOLS))}"
        )


def _extract_weight(item: dict[str, Any]) -> float:
    """Extract a sortable weight from a memory hit.

    Prefers ``retrieval_weight`` (legacy field); falls back to ``score``
    (mem0's field); treats missing values as -1 so they sort to the end.
    """
    if not isinstance(item, dict):
        return -1.0
    if "retrieval_weight" in item:
        try:
            return float(item["retrieval_weight"])
        except (TypeError, ValueError):
            return -1.0
    if "score" in item:
        try:
            return float(item["score"])
        except (TypeError, ValueError):
            return -1.0
    return -1.0


class BobMemoryClient:
    """High-level async client for bob3 in-process memory.

    Wraps BobMemory with the async API shape expected by bob3's
    orchestration code. All methods are async but internally synchronous;
    this keeps call sites compatible with the previous sub-agent-based
    client while eliminating the spawning cost.
    """

    def __init__(
        self,
        workspace: str | Path = ".",
        *,
        max_turns: int = 3,
        backend: BobMemory | None = None,
    ) -> None:
        self.workspace = str(workspace)
        self.max_turns = max_turns  # kept for API compatibility, unused
        self._backend = backend or BobMemory()

    async def add_memory(
        self,
        content: str,
        pool: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryResult:
        """Store a memory."""
        try:
            _validate_pool(pool)
        except ValueError as exc:
            raise exc

        try:
            data = self._backend.add(content, pool=pool, metadata=metadata)
            return MemoryResult(success=True, data=data)
        except Exception as exc:
            logger.warning("add_memory failed: %s", exc)
            return MemoryResult(success=False, error=str(exc))

    async def search_memory(
        self,
        query: str,
        pool: str | None = None,
        limit: int = 10,
        include_archived: bool = False,
    ) -> MemoryResult:
        """Search memories by semantic similarity."""
        try:
            _validate_pool(pool)
        except ValueError as exc:
            raise exc

        try:
            results = self._backend.search(
                query, pool=pool, limit=limit, include_archived=include_archived
            )
            return MemoryResult(success=True, data=results)
        except Exception as exc:
            logger.warning("search_memory failed: %s", exc)
            return MemoryResult(success=False, error=str(exc))

    async def record_feedback(
        self, memory_id: str, success: bool
    ) -> MemoryResult:
        """Record feedback on whether a memory was helpful."""
        try:
            ok = self._backend.record_feedback(memory_id, success)
            return MemoryResult(success=ok, data={"updated": ok})
        except Exception as exc:
            logger.warning("record_feedback failed: %s", exc)
            return MemoryResult(success=False, error=str(exc))

    async def get_memory(self, memory_id: str) -> MemoryResult:
        try:
            data = self._backend.get(memory_id)
            if data is None:
                return MemoryResult(success=False, error="not_found")
            return MemoryResult(success=True, data=data)
        except Exception as exc:
            return MemoryResult(success=False, error=str(exc))

    async def get_stats(self) -> MemoryResult:
        try:
            return MemoryResult(success=True, data=self._backend.get_stats())
        except Exception as exc:
            return MemoryResult(success=False, error=str(exc))

    async def archive_memory(self, memory_id: str) -> MemoryResult:
        try:
            ok = self._backend.archive(memory_id)
            return MemoryResult(success=ok, data={"archived": ok})
        except Exception as exc:
            return MemoryResult(success=False, error=str(exc))

    async def demote_memory(self, memory_id: str) -> MemoryResult:
        try:
            ok = self._backend.demote(memory_id)
            return MemoryResult(success=ok, data={"demoted": ok})
        except Exception as exc:
            return MemoryResult(success=False, error=str(exc))

    # -----------------------------------------------------------------
    # Higher-level convenience methods
    # -----------------------------------------------------------------

    async def store_lesson(
        self,
        trigger_context: str | None = None,
        lesson: str | None = None,
        solution: str | None = None,
        *,
        content: str | None = None,
        feature_id: str | None = None,
        bug_id: str | None = None,
        error_type: str | None = None,
        fix_action: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryResult:
        """Store a lesson learned (pool='lessons').

        Accepts either a pre-built ``content`` string, or a structured
        ``trigger_context``/``lesson``/``solution`` triple which will be
        formatted into the canonical

            TRIGGER: ...
            LESSON: ...
            SOLUTION: ...

        layout. Optional metadata fields are attached to the memory.
        """
        if content is None:
            if trigger_context is None or lesson is None or solution is None:
                raise ValueError(
                    "store_lesson requires either content=... or "
                    "trigger_context/lesson/solution"
                )
            content = (
                f"TRIGGER: {trigger_context}\n"
                f"LESSON: {lesson}\n"
                f"SOLUTION: {solution}"
            )

        meta: dict[str, Any] | None = None
        extras: dict[str, Any] = {}
        if feature_id:
            extras["feature_id"] = feature_id
        if bug_id:
            extras["bug_id"] = bug_id
        if error_type:
            extras["error_type"] = error_type
        if fix_action:
            extras["fix_action"] = fix_action
        if metadata:
            extras.update(metadata)
        if extras:
            meta = extras

        return await self.add_memory(content, pool="lessons", metadata=meta)

    async def search_relevant_knowledge(
        self,
        feature_name: str,
        description: str,
        *,
        feature_id: str | None = None,
        pools: list[str] | None = None,
        limit_per_pool: int = 3,
    ) -> MemoryResult:
        """Search for relevant knowledge across multiple pools for a feature.

        Searches each pool with queries built from the feature context,
        merges and deduplicates the results, and returns a flat list
        sorted by retrieval_weight (or score) descending.

        Args:
            feature_name: Human-readable feature name (used in queries).
            description: Feature description (used in queries).
            feature_id: Optional feature ID (included in queries when provided).
            pools: Optional list of pools; defaults to ['facts', 'lessons', 'context'].
            limit_per_pool: Max results to request from each pool.
        """
        pools = pools or ["facts", "lessons", "context"]
        # Build query string incorporating the available feature context
        query_parts = [feature_name, description]
        if feature_id:
            query_parts.append(feature_id)
        query = " ".join(p for p in query_parts if p)

        merged: dict[str, dict[str, Any]] = {}
        for pool in pools:
            _validate_pool(pool)
            try:
                result = await self.search_memory(query, pool=pool, limit=limit_per_pool)
            except Exception as exc:
                logger.warning("pool search failed for %s: %s", pool, exc)
                continue
            if not result.success:
                logger.debug("pool %s search failed: %s", pool, result.error)
                continue
            items = result.data if isinstance(result.data, list) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                mem_id = item.get("id")
                if not mem_id:
                    continue
                if mem_id in merged:
                    existing_weight = _extract_weight(merged[mem_id])
                    new_weight = _extract_weight(item)
                    if new_weight > existing_weight:
                        merged[mem_id] = item
                else:
                    merged[mem_id] = item

        combined = sorted(
            merged.values(),
            key=lambda r: _extract_weight(r),
            reverse=True,
        )
        return MemoryResult(success=True, data=combined)

    async def record_memory_feedback(
        self,
        memory_id: str,
        success: bool,
        *,
        notes: str | None = None,
        feature_id: str | None = None,
    ) -> MemoryResult:
        """Record feedback, with optional logging context.

        Thin wrapper around record_feedback() that also logs the
        feedback with the provided notes/feature_id for auditing.
        """
        logger.info(
            "memory feedback recorded: memory_id=%s success=%s feature_id=%s notes=%s",
            memory_id,
            success,
            feature_id,
            notes,
        )
        return await self.record_feedback(memory_id, success)

    async def get_demotion_candidates(
        self,
        *,
        min_times_applied: int = 5,
        max_usefulness: float = 0.3,
        limit: int = 10,
    ) -> MemoryResult:
        """Return memories that have been used enough and perform poorly."""
        try:
            data = self._backend.get_demotion_candidates(
                min_times_applied=min_times_applied,
                max_usefulness=max_usefulness,
                limit=limit,
            )
            return MemoryResult(success=True, data=data)
        except Exception as exc:
            return MemoryResult(success=False, error=str(exc))

    async def create_lesson_from_bug(
        self,
        bug_id: str,
        *,
        db_module: Any = None,
    ) -> MemoryResult:
        """Store a lesson derived from a resolved bug.

        Looks up the bug record in the database, formats a structured
        TRIGGER/LESSON/SOLUTION lesson from the bug's error and RCA
        fields, stores it in the 'lessons' pool, and writes the returned
        memory id back onto the bug row as titans_memory_id.

        Args:
            bug_id: The bug's unique identifier.
            db_module: Optional module override (defaults to bob3.db).
                Useful for testing.
        """
        if db_module is None:
            from bob3 import db as db_module  # type: ignore

        try:
            bug = db_module.get_bug(bug_id)
        except Exception as exc:
            return MemoryResult(success=False, error=f"db error: {exc}")

        if bug is None:
            return MemoryResult(success=False, error=f"bug '{bug_id}' not found")

        error_type = getattr(bug, "error_type", None) or ""
        error_message = getattr(bug, "error_message", None) or ""
        error_context = getattr(bug, "error_context", None) or ""
        root_cause = getattr(bug, "root_cause", None) or ""
        fix_action = getattr(bug, "fix_action", None) or ""
        fix_details = getattr(bug, "fix_details", None) or ""
        feature_id = getattr(bug, "feature_id", None)

        trigger_parts = [p for p in (error_type, error_message, error_context) if p]
        trigger_text = " | ".join(trigger_parts) if trigger_parts else "(no trigger)"
        lesson_text = root_cause or "(no root cause recorded)"
        solution_parts = [p for p in (fix_action, fix_details) if p]
        solution_text = " - ".join(solution_parts) if solution_parts else "(no solution recorded)"

        content = (
            f"TRIGGER: {trigger_text}\n"
            f"LESSON: {lesson_text}\n"
            f"SOLUTION: {solution_text}"
        )

        metadata: dict[str, Any] = {"bug_id": bug_id}
        if feature_id:
            metadata["feature_id"] = feature_id
        if error_type:
            metadata["error_type"] = error_type
        if fix_action:
            metadata["fix_action"] = fix_action

        result = await self.add_memory(content, pool="lessons", metadata=metadata)

        if result.success:
            memory_id = None
            if isinstance(result.data, dict):
                memory_id = result.data.get("id")
            if memory_id and hasattr(db_module, "update_bug"):
                try:
                    # Note: `titans_memory_id` is a legacy column name from the
                    # pre-bob3-memory schema. It now holds bob3 memory IDs but
                    # the column is kept to avoid a schema/data migration.
                    db_module.update_bug(bug_id, titans_memory_id=memory_id)
                except Exception as exc:
                    logger.warning("update_bug failed: %s", exc)
        return result


