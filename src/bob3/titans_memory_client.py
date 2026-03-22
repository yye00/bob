"""TITANS Memory MCP client for Bob3.

Provides a Python wrapper around the TITANS Memory MCP server tools.
Bob3's orchestrator calls these functions to store, search, and provide
feedback on memories. Internally, each operation spawns a lightweight
Claude sub-agent that invokes the corresponding MCP tool on the running
TITANS Memory server.

The MCP server must be running (managed by MCPLifecycleManager) before
calling any functions in this module.

Usage::

    from bob3.titans_memory_client import TitansMemoryClient

    client = TitansMemoryClient(workspace="/path/to/workspace")

    # Store a memory
    result = await client.add_memory(
        content="SQLite WAL mode improves concurrent reads",
        pool="facts",
    )

    # Search for relevant memories
    results = await client.search_memory(
        query="SQLite concurrency",
        pool="facts",
        limit=5,
    )

    # Record feedback on a memory
    feedback = await client.record_feedback(
        memory_id="some-memory-id",
        success=True,
    )

Memory pools:
    - facts: Factual knowledge (API behaviors, library usage)
    - preferences: User/project preferences
    - lessons: Learned patterns from debugging, failures
    - context: Session context and project state
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bob3.orchestrator.claude_executor import (
    ClaudeExecutor,
    ExecutionResult,
    build_sub_agent_options,
)
from bob3.orchestrator.mcp_config import (
    TITANS_MEMORY_MCP,
    get_allowed_tools,
)

logger = logging.getLogger(__name__)

# Valid memory pool names
VALID_POOLS = frozenset({"facts", "preferences", "lessons", "context"})

# The MCP tool names as they appear in the Claude Code environment
TOOL_TITANS_ADD = "mcp__titans-memory__titans_add"
TOOL_TITANS_SEARCH = "mcp__titans-memory__titans_search"
TOOL_TITANS_SEARCH_POOL = "mcp__titans-memory__titans_search_pool"
TOOL_TITANS_GET = "mcp__titans-memory__titans_get"
TOOL_TITANS_UPDATE = "mcp__titans-memory__titans_update"
TOOL_TITANS_DELETE = "mcp__titans-memory__titans_delete"
TOOL_TITANS_RECORD_FEEDBACK = "mcp__titans-memory__titans_record_feedback"
TOOL_TITANS_GET_CANDIDATES = "mcp__titans-memory__titans_get_candidates"
TOOL_TITANS_DEMOTE = "mcp__titans-memory__titans_demote"
TOOL_TITANS_ARCHIVE = "mcp__titans-memory__titans_archive"
TOOL_TITANS_GET_STATS = "mcp__titans-memory__titans_get_stats"
TOOL_TITANS_ROUTE = "mcp__titans-memory__titans_route"

# ---------------------------------------------------------------------------
# Pool routing keywords — used by route_to_pool() to classify content locally.
# ---------------------------------------------------------------------------

_POOL_KEYWORDS: dict[str, list[str]] = {
    "facts": [
        "api",
        "library",
        "version",
        "documentation",
        "behavior",
        "behaviour",
        "returns",
        "parameter",
        "function",
        "method",
        "endpoint",
        "response",
        "schema",
        "protocol",
        "specification",
        "external",
        "sdk",
        "package",
        "module",
        "import",
        "dependency",
        "config",
        "environment variable",
        "default value",
    ],
    "lessons": [
        "bug",
        "fix",
        "debug",
        "error",
        "exception",
        "traceback",
        "failure",
        "root cause",
        "workaround",
        "solution",
        "resolved",
        "lesson",
        "learned",
        "mistake",
        "regression",
        "crash",
        "issue",
        "patch",
        "hotfix",
        "broken",
        "trigger:",
        "lesson:",
        "solution:",
    ],
    "preferences": [
        "prefer",
        "convention",
        "style",
        "always use",
        "never use",
        "standard",
        "naming",
        "pattern",
        "practice",
        "guideline",
        "rule",
        "template",
        "format",
        "lint",
        "coding style",
        "project convention",
        "user preference",
    ],
    "context": [
        "session",
        "progress",
        "status",
        "current",
        "working on",
        "feature",
        "state",
        "milestone",
        "checkpoint",
        "blocked",
        "in progress",
        "completed",
        "next step",
        "plan",
        "backlog",
    ],
}


def route_to_pool(content: str) -> str:
    """Classify content and return the appropriate TITANS memory pool name.

    Uses keyword-based matching to determine which pool is the best fit.
    Ties are broken by pool priority (facts > lessons > preferences > context).
    Defaults to "context" if no keywords match.

    Args:
        content: The memory content to classify.

    Returns:
        One of "facts", "lessons", "preferences", or "context".
    """
    if not content or not content.strip():
        return "context"

    lower_content = content.lower()

    scores: dict[str, int] = {}
    for pool, keywords in _POOL_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower_content)
        scores[pool] = score

    priority_order = ["facts", "lessons", "preferences", "context"]

    best_pool = "context"
    best_score = 0
    for pool in priority_order:
        pool_score = scores.get(pool, 0)
        if pool_score > best_score:
            best_score = pool_score
            best_pool = pool

    return best_pool


@dataclass
class MemoryResult:
    """Result of a TITANS Memory operation.

    Attributes:
        success: Whether the operation completed without error.
        data: The parsed response data (dict or list depending on operation).
        error: Error message if success is False.
        raw_text: Raw text response from the Claude sub-agent.
    """

    success: bool
    data: Any = None
    error: str = ""
    raw_text: str = ""


def _extract_json_from_text(text: str) -> Any | None:
    """Attempt to extract a JSON object or array from Claude's response text.

    Claude sub-agents often wrap JSON in markdown code fences or include
    explanatory prose around the actual data. This function tries multiple
    strategies to extract the JSON payload.

    Returns:
        Parsed JSON data, or None if extraction fails.
    """
    if not text:
        return None

    # Strategy 1: Try parsing the entire text as JSON
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Look for JSON in code fences
    code_fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
    for match in code_fence_pattern.finditer(text):
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            continue

    # Strategy 3: Find the first { or [ and try to parse from there
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue
        end_idx = text.rfind(end_char)
        if end_idx <= start_idx:
            continue
        candidate = text[start_idx : end_idx + 1]
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue

    return None


def _validate_pool(pool: str | None) -> None:
    """Validate that the pool name is recognized.

    Args:
        pool: Pool name to validate, or None (auto-route).

    Raises:
        ValueError: If pool is not None and not in VALID_POOLS.
    """
    if pool is not None and pool not in VALID_POOLS:
        raise ValueError(
            f"Invalid memory pool '{pool}'. Must be one of: {', '.join(sorted(VALID_POOLS))}"
        )


class TitansMemoryClient:
    """High-level client for the TITANS Memory MCP server.

    Wraps MCP tool calls by spawning lightweight Claude sub-agents that
    invoke the corresponding TITANS MCP tools. Each operation sends a
    focused prompt that instructs the sub-agent to call exactly one tool
    and return the JSON result.

    Attributes:
        workspace: Path to the project workspace (used as sub-agent cwd).
        max_turns: Maximum agentic turns per MCP tool call.
    """

    def __init__(
        self,
        workspace: str | Path,
        *,
        max_turns: int = 3,
    ) -> None:
        self.workspace = str(workspace)
        self.max_turns = max_turns

    def _build_executor(self) -> ClaudeExecutor:
        """Create a ClaudeExecutor configured with TITANS MCP tools.

        Returns:
            A ClaudeExecutor instance with MCP servers and allowed tools
            configured for TITANS Memory access.
        """
        mcp_servers = {
            TITANS_MEMORY_MCP.name: {
                "command": TITANS_MEMORY_MCP.command,
            }
        }
        allowed_tools = [f"mcp__titans-memory__{t}" for t in get_allowed_tools()]

        options = build_sub_agent_options(
            cwd=self.workspace,
            max_turns=self.max_turns,
            allowed_tools=allowed_tools,
            permission_mode="bypassPermissions",
            mcp_servers=mcp_servers,
        )
        return ClaudeExecutor(default_options=options)

    async def _execute_tool_prompt(self, prompt: str) -> MemoryResult:
        """Send a prompt to a Claude sub-agent and parse the result.

        The prompt should instruct the sub-agent to call a single TITANS
        MCP tool and output the raw JSON result.

        Args:
            prompt: The instruction prompt for the sub-agent.

        Returns:
            A MemoryResult with parsed data or error information.
        """
        executor = self._build_executor()

        try:
            result: ExecutionResult = await executor.execute(prompt)
        except Exception as exc:
            logger.error("Failed to execute TITANS memory tool: %s", exc)
            return MemoryResult(
                success=False,
                error=f"Executor error: {exc}",
            )

        if result.is_error:
            logger.warning(
                "TITANS memory tool returned error: %s", result.error_message
            )
            return MemoryResult(
                success=False,
                error=result.error_message,
                raw_text=result.text,
            )

        # Parse the JSON from the sub-agent response
        parsed = _extract_json_from_text(result.text)
        if parsed is not None:
            return MemoryResult(
                success=True,
                data=parsed,
                raw_text=result.text,
            )

        # Even without parseable JSON, the operation may have succeeded
        if result.text:
            logger.debug(
                "Could not parse JSON from TITANS response, returning raw text"
            )
            return MemoryResult(
                success=True,
                data=result.text,
                raw_text=result.text,
            )

        return MemoryResult(
            success=False,
            error="Empty response from TITANS memory tool",
            raw_text="",
        )

    async def add_memory(
        self,
        content: str,
        pool: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryResult:
        """Store a new memory in the TITANS Memory system.

        Calls the ``titans_add`` MCP tool to add content to the specified
        pool with optional metadata.

        Args:
            content: The memory content to store.
            pool: Target pool (facts, preferences, lessons, context).
                If None, TITANS will auto-route based on content.
            metadata: Additional metadata key-value pairs.

        Returns:
            MemoryResult with the stored memory data including its ID.

        Raises:
            ValueError: If pool is not a valid pool name.
        """
        _validate_pool(pool)

        prompt = (
            f"Call the {TOOL_TITANS_ADD} tool with the following arguments:\n"
            f'- content: "{content}"\n'
        )
        if pool:
            prompt += f'- pool: "{pool}"\n'
        if metadata:
            prompt += f"- metadata: {json.dumps(metadata)}\n"
        prompt += (
            "\nReturn ONLY the raw JSON result from the tool call. "
            "Do not add any explanation or commentary."
        )

        logger.info("Adding memory to pool '%s': %s", pool or "auto", content[:100])
        result = await self._execute_tool_prompt(prompt)

        if result.success:
            logger.info("Memory added successfully")
        else:
            logger.warning("Failed to add memory: %s", result.error)

        return result

    async def search_memory(
        self,
        query: str,
        pool: str | None = None,
        limit: int = 10,
    ) -> MemoryResult:
        """Search for relevant memories in TITANS Memory.

        Uses ``titans_search`` (or ``titans_search_pool`` if a pool is
        specified) to find memories matching the query, ranked by TITANS
        retrieval weight.

        Args:
            query: Search query text.
            pool: Optional pool filter.
            limit: Maximum number of results to return.

        Returns:
            MemoryResult with a list of matching memories.

        Raises:
            ValueError: If pool is not a valid pool name.
        """
        _validate_pool(pool)

        if pool:
            tool_name = TOOL_TITANS_SEARCH_POOL
            prompt = (
                f"Call the {tool_name} tool with the following arguments:\n"
                f'- query: "{query}"\n'
                f'- pool: "{pool}"\n'
                f"- limit: {limit}\n"
                "\nReturn ONLY the raw JSON result from the tool call. "
                "Do not add any explanation or commentary."
            )
        else:
            tool_name = TOOL_TITANS_SEARCH
            prompt = (
                f"Call the {tool_name} tool with the following arguments:\n"
                f'- query: "{query}"\n'
                f"- limit: {limit}\n"
                "\nReturn ONLY the raw JSON result from the tool call. "
                "Do not add any explanation or commentary."
            )

        logger.info("Searching memories (pool=%s): %s", pool or "all", query[:100])
        result = await self._execute_tool_prompt(prompt)

        if result.success:
            if isinstance(result.data, list):
                logger.info("Memory search returned %d results", len(result.data))
            else:
                logger.info("Memory search completed")
        else:
            logger.warning("Memory search failed: %s", result.error)

        return result

    async def record_feedback(
        self,
        memory_id: str,
        success: bool,
    ) -> MemoryResult:
        """Record feedback on whether a memory was useful.

        Calls ``titans_record_feedback`` to update the memory's usefulness
        score based on whether it helped or not. TITANS uses this feedback
        to improve future retrieval rankings.

        Args:
            memory_id: The ID of the memory to give feedback on.
            success: True if the memory was helpful, False otherwise.

        Returns:
            MemoryResult with the updated memory data.
        """
        success_str = "true" if success else "false"

        prompt = (
            f"Call the {TOOL_TITANS_RECORD_FEEDBACK} tool with the following arguments:\n"
            f'- memory_id: "{memory_id}"\n'
            f"- success: {success_str}\n"
            "\nReturn ONLY the raw JSON result from the tool call. "
            "Do not add any explanation or commentary."
        )

        logger.info(
            "Recording feedback for memory '%s': success=%s", memory_id, success
        )
        result = await self._execute_tool_prompt(prompt)

        if result.success:
            logger.info("Feedback recorded for memory '%s'", memory_id)
        else:
            logger.warning(
                "Failed to record feedback for memory '%s': %s",
                memory_id,
                result.error,
            )

        return result

    async def get_memory(self, memory_id: str) -> MemoryResult:
        """Retrieve a specific memory by its ID.

        Args:
            memory_id: The ID of the memory to retrieve.

        Returns:
            MemoryResult with the memory data.
        """
        prompt = (
            f"Call the {TOOL_TITANS_GET} tool with the following arguments:\n"
            f'- memory_id: "{memory_id}"\n'
            "\nReturn ONLY the raw JSON result from the tool call. "
            "Do not add any explanation or commentary."
        )

        logger.debug("Getting memory '%s'", memory_id)
        return await self._execute_tool_prompt(prompt)

    async def get_stats(self) -> MemoryResult:
        """Get statistics about memory pools and TITANS metrics.

        Returns:
            MemoryResult with statistics dict.
        """
        prompt = (
            f"Call the {TOOL_TITANS_GET_STATS} tool with no arguments.\n"
            "\nReturn ONLY the raw JSON result from the tool call. "
            "Do not add any explanation or commentary."
        )

        logger.debug("Getting TITANS memory stats")
        return await self._execute_tool_prompt(prompt)

    async def archive_memory(self, memory_id: str) -> MemoryResult:
        """Archive a memory, removing it from active search results.

        Args:
            memory_id: The ID of the memory to archive.

        Returns:
            MemoryResult with the updated memory data.
        """
        prompt = (
            f"Call the {TOOL_TITANS_ARCHIVE} tool with the following arguments:\n"
            f'- memory_id: "{memory_id}"\n'
            "\nReturn ONLY the raw JSON result from the tool call. "
            "Do not add any explanation or commentary."
        )

        logger.info("Archiving memory '%s'", memory_id)
        return await self._execute_tool_prompt(prompt)

    async def demote_memory(self, memory_id: str) -> MemoryResult:
        """Demote a memory, reducing its retrieval weight.

        Args:
            memory_id: The ID of the memory to demote.

        Returns:
            MemoryResult with the updated memory data including new status.
        """
        prompt = (
            f"Call the {TOOL_TITANS_DEMOTE} tool with the following arguments:\n"
            f'- memory_id: "{memory_id}"\n'
            "\nReturn ONLY the raw JSON result from the tool call. "
            "Do not add any explanation or commentary."
        )

        logger.info("Demoting memory '%s'", memory_id)
        return await self._execute_tool_prompt(prompt)

    async def store_lesson(
        self,
        trigger_context: str,
        lesson: str,
        solution: str,
        *,
        feature_id: str | None = None,
        error_type: str | None = None,
        fix_action: str | None = None,
    ) -> MemoryResult:
        """Store a lesson learned in the TITANS Memory lessons pool.

        Args:
            trigger_context: What situation triggered this lesson.
            lesson: What was learned from the experience.
            solution: How the problem was resolved.
            feature_id: Optional feature ID this lesson relates to.
            error_type: Optional classification of the error.
            fix_action: Optional description of the fix action taken.

        Returns:
            MemoryResult with the stored lesson data including its memory ID.
        """
        content_parts = [
            f"TRIGGER: {trigger_context}",
            f"LESSON: {lesson}",
            f"SOLUTION: {solution}",
        ]
        content = "\n".join(content_parts)

        metadata: dict[str, Any] = {}
        if feature_id is not None:
            metadata["feature_id"] = feature_id
        if error_type is not None:
            metadata["error_type"] = error_type
        if fix_action is not None:
            metadata["fix_action"] = fix_action

        logger.info(
            "Storing lesson (feature=%s): %s",
            feature_id or "none",
            lesson[:100],
        )

        return await self.add_memory(
            content=content,
            pool="lessons",
            metadata=metadata if metadata else None,
        )

    async def search_relevant_knowledge(
        self,
        feature_name: str,
        description: str,
        *,
        feature_id: str | None = None,
        limit_per_pool: int = 5,
    ) -> MemoryResult:
        """Search TITANS memory for relevant knowledge before implementing a feature.

        Searches multiple memory pools (facts, lessons, context) using the
        feature context as a query, then merges and ranks all results by
        retrieval_weight for surprise-based retrieval.

        Args:
            feature_name: Name of the feature being implemented.
            description: Description of the feature.
            feature_id: Optional feature ID for more targeted search.
            limit_per_pool: Maximum results to retrieve per pool.

        Returns:
            MemoryResult with a merged, deduplicated list of memories
            sorted by retrieval_weight descending.
        """
        query_parts = [feature_name, description]
        if feature_id:
            query_parts.append(feature_id)
        query = " ".join(query_parts)

        pools = ["facts", "lessons", "context"]
        all_results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for pool in pools:
            try:
                result = await self.search_memory(
                    query=query,
                    pool=pool,
                    limit=limit_per_pool,
                )
                if result.success and isinstance(result.data, list):
                    for memory in result.data:
                        mem_id = memory.get("id")
                        if mem_id and mem_id not in seen_ids:
                            seen_ids.add(mem_id)
                            all_results.append(memory)
                else:
                    logger.warning(
                        "Search in pool '%s' failed: %s", pool, result.error
                    )
            except Exception as exc:
                logger.error("Error searching pool '%s': %s", pool, exc)

        # Sort by retrieval_weight descending (missing weight sorts last)
        all_results.sort(
            key=lambda m: m.get("retrieval_weight", 0.0),
            reverse=True,
        )

        logger.info(
            "search_relevant_knowledge for '%s': found %d results across %d pools",
            feature_name[:50],
            len(all_results),
            len(pools),
        )

        return MemoryResult(
            success=True,
            data=all_results,
            raw_text="",
        )

    async def record_memory_feedback(
        self,
        memory_id: str,
        success: bool,
        *,
        notes: str | None = None,
        feature_id: str | None = None,
    ) -> MemoryResult:
        """Record feedback on whether a retrieved memory was useful.

        Higher-level wrapper around :meth:`record_feedback` that adds
        structured logging with optional notes and feature context.
        TITANS uses this feedback to calculate usefulness scores and
        improve future retrieval rankings.

        Args:
            memory_id: The ID of the memory to give feedback on.
            success: True if the memory was helpful, False if it was
                wrong or unhelpful.
            notes: Optional free-text description of how the memory
                helped or why it was wrong.
            feature_id: Optional feature ID for context tracking.

        Returns:
            MemoryResult with the updated memory data from TITANS.
        """
        outcome = "helpful" if success else "unhelpful"
        context_parts = [f"memory='{memory_id}'", f"outcome={outcome}"]
        if feature_id:
            context_parts.append(f"feature={feature_id}")
        if notes:
            context_parts.append(f"notes='{notes}'")

        logger.info(
            "Recording memory feedback: %s",
            ", ".join(context_parts),
        )

        result = await self.record_feedback(
            memory_id=memory_id,
            success=success,
        )

        if result.success:
            logger.info(
                "Memory feedback recorded for '%s' (success=%s)",
                memory_id,
                success,
            )
        else:
            logger.warning(
                "Failed to record memory feedback for '%s': %s",
                memory_id,
                result.error,
            )

        return result

    async def get_demotion_candidates(
        self,
        *,
        limit: int = 10,
    ) -> MemoryResult:
        """Find low-value memories that are candidates for demotion.

        Calls ``titans_get_candidates`` to retrieve memories with low
        usefulness scores, which may be candidates for demotion or
        archival.

        Args:
            limit: Maximum number of candidates to return.

        Returns:
            MemoryResult with a list of low-value memory candidates.
        """
        prompt = (
            f"Call the {TOOL_TITANS_GET_CANDIDATES} tool with the following arguments:\n"
            f"- limit: {limit}\n"
            "\nReturn ONLY the raw JSON result from the tool call. "
            "Do not add any explanation or commentary."
        )

        logger.info("Getting demotion candidates (limit=%d)", limit)
        result = await self._execute_tool_prompt(prompt)

        if result.success:
            count = len(result.data) if isinstance(result.data, list) else 0
            logger.info("Found %d demotion candidates", count)
        else:
            logger.warning("Failed to get demotion candidates: %s", result.error)

        return result

    async def create_lesson_from_bug(
        self,
        bug_id: str,
    ) -> MemoryResult:
        """Create a lesson in TITANS Memory from a resolved bug's resolution.

        Extracts trigger context, root cause, and fix action from the bug
        record, formats a structured lesson, stores it in the 'lessons' pool,
        and updates the bug's titans_memory_id with the returned memory ID.

        Args:
            bug_id: ID of the bug to create a lesson from.

        Returns:
            MemoryResult with the stored lesson data. On failure (bug not
            found, TITANS unavailable), returns a MemoryResult with
            success=False.
        """
        from bob3 import db

        bug = db.get_bug(bug_id)
        if bug is None:
            return MemoryResult(
                success=False,
                error=f"Bug not found: {bug_id}",
            )

        # Step 2: Extract trigger context from bug
        trigger_parts = [f"{bug.error_type}: {bug.error_message}"]
        if bug.error_context:
            trigger_parts.append(bug.error_context)
        trigger_context = " | ".join(trigger_parts)

        # Step 3: Format lesson content
        lesson_text = bug.root_cause or bug.error_message
        solution_parts = [bug.fix_action]
        if bug.fix_details:
            solution_parts.append(bug.fix_details)
        solution_text = " - ".join(solution_parts)

        content_parts = [
            f"TRIGGER: {trigger_context}",
            f"LESSON: {lesson_text}",
            f"SOLUTION: {solution_text}",
        ]
        content = "\n".join(content_parts)

        # Step 4: Build metadata with bug_id and optional feature_id
        metadata: dict[str, Any] = {
            "bug_id": bug.id,
            "error_type": bug.error_type,
        }
        if bug.feature_id is not None:
            metadata["feature_id"] = bug.feature_id

        logger.info(
            "Creating lesson from bug '%s' (feature=%s)",
            bug_id,
            bug.feature_id or "none",
        )

        result = await self.add_memory(
            content=content,
            pool="lessons",
            metadata=metadata,
        )

        # Step 5: Store returned memory_id in bug_ledger
        if result.success and isinstance(result.data, dict):
            memory_id = result.data.get("id")
            if memory_id:
                db.update_bug(bug_id, titans_memory_id=memory_id)
                logger.info(
                    "Lesson created from bug '%s': memory_id='%s'",
                    bug_id,
                    memory_id,
                )
        elif not result.success:
            logger.warning(
                "Failed to create lesson from bug '%s': %s",
                bug_id,
                result.error,
            )

        return result
