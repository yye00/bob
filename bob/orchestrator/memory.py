"""
Project Memory System
=====================

Persistent cross-run memory for Bob projects using Mem0.

Provides three memory layers:
1. **Semantic Memory** (Mem0) — Distilled lessons, anti-patterns, environment quirks
   with usefulness/complexity scoring and automatic dedup/evolution
2. **Test Stability** (JSON) — Per-test pass/fail tracking across implementations
   for automatic buggy-test detection
3. **Procedural Memory** (JSON) — Working code patterns from successful tasks

Architecture inspired by:
- Titans (Google, 2024): surprise-based prioritization + forgetting
- A-Mem (2025): Zettelkasten-style memory evolution
- Voyager (2023): persistent skill/recipe library
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Mem0 is optional — if unavailable, semantic memory is disabled
try:
    from mem0 import Memory
    _MEM0_AVAILABLE = True
except ImportError:
    _MEM0_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# LLM used for fact extraction inside Mem0 (cheap + fast)
_DEFAULT_EXTRACTION_MODEL = "gpt-4.1-nano-2025-04-14"

# Max memories to inject into task prompts
_MAX_PROMPT_MEMORIES = 8

# Max tokens for memory section in prompt (~1500 tokens ≈ 6000 chars)
_MAX_PROMPT_CHARS = 6000

# Novelty threshold — only store if Haiku rates novelty above this
_NOVELTY_THRESHOLD = 0.3

# Test stability: N failures with same signature across different impls = suspect
_STABILITY_FAILURE_THRESHOLD = 3


class ProjectMemory:
    """Persistent memory for a Bob project.

    Combines Mem0 (semantic search + auto-dedup) with simple JSON files
    (test stability, recipes) for a complete memory system.

    Usage:
        memory = ProjectMemory(project_dir, project_id)

        # After task verification
        await memory.extract(task, verification_result)

        # Before building task prompt
        context = memory.retrieve(task)

        # Periodic maintenance
        memory.decay_and_prune()
    """

    def __init__(
        self,
        project_dir: Path,
        project_id: str,
        *,
        extraction_model: str = _DEFAULT_EXTRACTION_MODEL,
        enable_cross_project: bool = False,
        mem0_config: Optional[dict] = None,
    ):
        self.project_dir = Path(project_dir)
        self.project_id = project_id
        self.extraction_model = extraction_model
        self.enable_cross_project = enable_cross_project

        # Ensure memory directory exists
        self.memory_dir = self.project_dir / ".bob" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Mem0 for semantic memory
        self._mem0: Optional[Any] = None
        if _MEM0_AVAILABLE:
            config = mem0_config or self._default_mem0_config()
            try:
                self._mem0 = Memory.from_config(config)
            except Exception as e:
                print(f"⚠️  Mem0 initialization failed: {e}")
                print("   Semantic memory disabled. Test stability + recipes still active.")

        # JSON-based stores
        self._test_stability_path = self.memory_dir / "test_stability.json"
        self._recipes_path = self.memory_dir / "recipes.json"
        self._knowledge_md_path = self.memory_dir / "knowledge.md"

    def _default_mem0_config(self) -> dict:
        """Build default Mem0 configuration.

        Uses on-disk Qdrant (no external service needed) and
        configures the LLM for fact extraction.
        """
        # Store Qdrant data in the project memory directory
        qdrant_path = str(self.memory_dir / "qdrant_data")

        config: dict[str, Any] = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": f"bob_{self.project_id[:12]}",
                    "path": qdrant_path,
                },
            },
        }

        # Use Anthropic if ANTHROPIC_API_KEY is set, else fall back to OpenAI
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")

        if anthropic_key:
            config["llm"] = {
                "provider": "anthropic",
                "config": {
                    "model": "claude-haiku-3-5-20241022",
                    "temperature": 0.1,
                    "api_key": anthropic_key,
                },
            }
        elif openai_key:
            config["llm"] = {
                "provider": "openai",
                "config": {
                    "model": self.extraction_model,
                    "temperature": 0.1,
                    "api_key": openai_key,
                },
            }

        return config

    # ------------------------------------------------------------------
    # Semantic Memory (Mem0)
    # ------------------------------------------------------------------

    def add_memory(
        self,
        content: str,
        *,
        task_id: str = "",
        category: str = "lesson",
        attempt: int = 0,
        success: bool = False,
        complexity: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> Optional[str]:
        """Add a memory to the semantic store.

        Mem0 handles deduplication and merging automatically — if a
        similar memory exists, it updates rather than duplicates.

        Args:
            content: The memory text (lesson learned, anti-pattern, etc.)
            task_id: Task spec_id this memory relates to
            category: One of: lesson, anti_pattern, environment, recipe, insight
            attempt: Which attempt number this was extracted from
            success: Whether the task succeeded
            complexity: 0.0-1.0 based on attempts-to-resolve
            metadata: Additional metadata dict

        Returns:
            Memory ID if stored, None if Mem0 unavailable
        """
        if not self._mem0:
            return None

        mem_metadata = {
            "task_id": task_id,
            "category": category,
            "attempt": attempt,
            "success": success,
            "complexity": complexity,
            "usefulness": 0.0,
            "retrieval_count": 0,
            "helped_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }

        # Scope to project (or global for environment memories)
        user_id = self.project_id
        if category == "environment" and self.enable_cross_project:
            user_id = "global"

        try:
            result = self._mem0.add(
                content,
                user_id=user_id,
                metadata=mem_metadata,
            )
            # Return the first memory ID if available
            if result and isinstance(result, dict):
                results = result.get("results", [])
                if results and len(results) > 0:
                    return results[0].get("id")
            return None
        except Exception as e:
            print(f"⚠️  Memory add failed: {e}")
            return None

    def search_memories(
        self,
        query: str,
        *,
        category: Optional[str] = None,
        min_usefulness: float = 0.0,
        limit: int = _MAX_PROMPT_MEMORIES,
    ) -> list[dict]:
        """Search semantic memories by relevance.

        Args:
            query: Search query (task description, error message, etc.)
            category: Filter by category
            min_usefulness: Minimum usefulness score
            limit: Maximum results

        Returns:
            List of memory dicts with 'memory', 'score', 'metadata'
        """
        if not self._mem0:
            return []

        filters: dict[str, Any] = {}
        filter_conditions = []

        if category:
            filter_conditions.append({"category": category})
        if min_usefulness > 0:
            filter_conditions.append({"usefulness": {"gte": min_usefulness}})

        if len(filter_conditions) > 1:
            filters = {"AND": filter_conditions}
        elif len(filter_conditions) == 1:
            filters = filter_conditions[0]

        try:
            # Search project-scoped memories
            results = self._mem0.search(
                query=query,
                user_id=self.project_id,
                limit=limit,
                filters=filters if filters else None,
            )

            memories = []
            if results and "results" in results:
                memories = results["results"]

            # Also search global memories if cross-project enabled
            if self.enable_cross_project:
                try:
                    global_results = self._mem0.search(
                        query=query,
                        user_id="global",
                        limit=3,
                        filters={"category": "environment"} if not filters else None,
                    )
                    if global_results and "results" in global_results:
                        memories.extend(global_results["results"])
                except Exception:
                    pass

            return memories

        except Exception as e:
            print(f"⚠️  Memory search failed: {e}")
            return []

    def update_usefulness(self, memory_id: str, helped: bool) -> None:
        """Update usefulness score after a memory was retrieved.

        Called after task verification — if the memory was injected
        into the prompt and the task succeeded, it helped.

        Args:
            memory_id: ID of the memory
            helped: Whether the task succeeded after injection
        """
        if not self._mem0:
            return

        try:
            # Get current memory to read metadata
            all_memories = self._mem0.get_all(user_id=self.project_id)
            if not all_memories:
                return
            
            target = None
            for mem in all_memories.get("results", []):
                if mem.get("id") == memory_id:
                    target = mem
                    break

            if not target:
                return

            meta = target.get("metadata", {})
            retrieval_count = meta.get("retrieval_count", 0) + 1
            helped_count = meta.get("helped_count", 0) + (1 if helped else 0)
            complexity = meta.get("complexity", 0.0)

            # Combined usefulness formula
            help_ratio = helped_count / max(retrieval_count, 1)
            usefulness = (
                0.4 * help_ratio
                + 0.3 * complexity
                + 0.3 * min(retrieval_count / 10.0, 1.0)  # More retrievals = more useful
            )

            meta["retrieval_count"] = retrieval_count
            meta["helped_count"] = helped_count
            meta["usefulness"] = round(usefulness, 3)

            self._mem0.update(memory_id, data=target.get("memory", ""), metadata=meta)

        except Exception as e:
            print(f"⚠️  Usefulness update failed: {e}")

    # ------------------------------------------------------------------
    # Test Stability (JSON)
    # ------------------------------------------------------------------

    def _load_test_stability(self) -> dict:
        """Load test stability data from JSON."""
        if self._test_stability_path.exists():
            try:
                with open(self._test_stability_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_test_stability(self, data: dict) -> None:
        """Save test stability data to JSON."""
        with open(self._test_stability_path, "w") as f:
            json.dump(data, f, indent=2)

    def record_test_result(
        self,
        test_name: str,
        task_id: str,
        passed: bool,
        error: str = "",
        impl_hash: str = "",
    ) -> None:
        """Record a single test result for stability tracking.

        When the same test fails with the same error across multiple
        independent implementations, it's likely the test itself is buggy.

        Args:
            test_name: Name of the test
            task_id: Task spec_id
            passed: Whether the test passed
            error: Error message if failed
            impl_hash: Hash of the implementation code (to detect independent impls)
        """
        stability = self._load_test_stability()

        if test_name not in stability:
            stability[test_name] = {
                "task_id": task_id,
                "results": [],
                "verdict": "unknown",
            }

        entry = stability[test_name]

        # Compute error signature for grouping
        error_sig = _hash_error_signature(error) if error else ""

        entry["results"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "passed": passed,
            "error_signature": error_sig,
            "error_preview": error[:200] if error else "",
            "impl_hash": impl_hash,
        })

        # Keep last 20 results max
        entry["results"] = entry["results"][-20:]

        # Compute verdict
        entry["verdict"], entry["reason"] = self._compute_test_verdict(entry["results"])

        self._save_test_stability(stability)

    def _compute_test_verdict(
        self, results: list[dict]
    ) -> tuple[str, str]:
        """Compute test stability verdict.

        Returns:
            Tuple of (verdict, reason)
            verdict: "stable", "flaky", "suspect_buggy", "unknown"
        """
        if len(results) < 2:
            return "unknown", "Not enough data"

        failures = [r for r in results if not r["passed"]]
        passes = [r for r in results if r["passed"]]

        if not failures:
            return "stable", f"Passed {len(passes)} times"

        if not passes and len(failures) >= _STABILITY_FAILURE_THRESHOLD:
            # Check if failures have the same error signature across different impls
            error_sigs = set(f["error_signature"] for f in failures if f["error_signature"])
            impl_hashes = set(f["impl_hash"] for f in failures if f["impl_hash"])

            if len(error_sigs) == 1 and len(impl_hashes) >= _STABILITY_FAILURE_THRESHOLD:
                return (
                    "suspect_buggy",
                    f"Same error across {len(impl_hashes)} independent implementations",
                )
            elif len(error_sigs) == 1 and len(failures) >= _STABILITY_FAILURE_THRESHOLD:
                return (
                    "suspect_buggy",
                    f"Same error in {len(failures)} consecutive failures",
                )

        if passes and failures:
            fail_rate = len(failures) / len(results)
            if fail_rate > 0.5:
                return "flaky", f"Fails {fail_rate:.0%} of the time"

        return "unknown", f"{len(failures)} failures, {len(passes)} passes"

    def get_suspect_tests(self, task_id: Optional[str] = None) -> list[dict]:
        """Get tests flagged as suspect buggy.

        Args:
            task_id: Optional filter by task

        Returns:
            List of suspect test entries
        """
        stability = self._load_test_stability()
        suspects = []

        for test_name, entry in stability.items():
            if entry.get("verdict") == "suspect_buggy":
                if task_id and entry.get("task_id") != task_id:
                    continue
                suspects.append({
                    "test_name": test_name,
                    "task_id": entry.get("task_id", ""),
                    "reason": entry.get("reason", ""),
                    "failure_count": len([r for r in entry["results"] if not r["passed"]]),
                    "error_preview": entry["results"][-1].get("error_preview", "") if entry["results"] else "",
                })

        return suspects

    # ------------------------------------------------------------------
    # Procedural Memory / Recipes (JSON)
    # ------------------------------------------------------------------

    def _load_recipes(self) -> dict:
        """Load recipe data from JSON."""
        if self._recipes_path.exists():
            try:
                with open(self._recipes_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_recipes(self, data: dict) -> None:
        """Save recipe data to JSON."""
        with open(self._recipes_path, "w") as f:
            json.dump(data, f, indent=2)

    def save_recipe(
        self,
        task_id: str,
        title: str,
        pattern: str,
        key_code: str = "",
        dependencies: Optional[list[str]] = None,
    ) -> None:
        """Save a working code pattern from a successful task.

        Args:
            task_id: Task spec_id
            title: Human-readable title for the recipe
            pattern: Description of the approach that worked
            key_code: Key code snippet (optional)
            dependencies: List of dependency task IDs
        """
        recipes = self._load_recipes()
        recipes[task_id] = {
            "title": title,
            "pattern": pattern,
            "key_code": key_code[:2000] if key_code else "",
            "dependencies": dependencies or [],
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "usefulness": 0.5,  # Start at moderate usefulness
        }
        self._save_recipes(recipes)

    def get_relevant_recipes(self, task_id: str, depends_on: list[str]) -> list[dict]:
        """Get recipes relevant to a task (from its dependencies).

        Args:
            task_id: Current task spec_id
            depends_on: List of dependency task IDs

        Returns:
            List of recipe dicts
        """
        recipes = self._load_recipes()
        relevant = []

        for dep_id in depends_on:
            if dep_id in recipes:
                recipe = recipes[dep_id].copy()
                recipe["source_task"] = dep_id
                relevant.append(recipe)

        return relevant

    # ------------------------------------------------------------------
    # Extract (post-verification)
    # ------------------------------------------------------------------

    async def extract(
        self,
        task: Any,
        verification_passed: bool,
        verification_msg: str,
        attempt_number: int,
        test_results: Optional[list[dict]] = None,
    ) -> dict:
        """Extract memories from a task attempt.

        Called after every verification, whether pass or fail.
        Uses the task's error/success to build memories.

        Args:
            task: Task object with spec_id, title, description, etc.
            verification_passed: Whether verification passed
            verification_msg: Verification output message
            attempt_number: Which attempt this was (1-based)
            test_results: Optional list of individual test results

        Returns:
            Dict with extraction summary
        """
        extracted = {
            "memories_added": 0,
            "test_results_recorded": 0,
            "recipe_saved": False,
        }

        task_id = task.spec_id if hasattr(task, "spec_id") else str(task)
        task_title = task.title if hasattr(task, "title") else ""

        # Compute complexity based on attempt number
        complexity = min(1.0, attempt_number / 10.0)

        # 1. Record test results for stability tracking
        if test_results:
            impl_hash = _compute_impl_hash(task, self.project_dir)
            for tr in test_results:
                self.record_test_result(
                    test_name=tr.get("name", "unknown"),
                    task_id=task_id,
                    passed=tr.get("passed", False),
                    error=tr.get("error", ""),
                    impl_hash=impl_hash,
                )
                extracted["test_results_recorded"] += 1

        # 2. Add semantic memory for the outcome
        if verification_passed:
            # Success — save what worked
            content = (
                f"Task '{task_title}' ({task_id}) succeeded on attempt {attempt_number}. "
                f"Approach worked after {attempt_number} attempt(s)."
            )
            if attempt_number > 1:
                content += (
                    f" This was a complex task requiring multiple attempts. "
                    f"Previous attempts failed with: {verification_msg[:300]}"
                )
            mem_id = self.add_memory(
                content,
                task_id=task_id,
                category="lesson" if attempt_number > 1 else "recipe",
                attempt=attempt_number,
                success=True,
                complexity=complexity,
            )
            if mem_id:
                extracted["memories_added"] += 1

            # Save recipe for successful tasks
            self.save_recipe(
                task_id=task_id,
                title=task_title,
                pattern=f"Succeeded on attempt {attempt_number}",
                dependencies=list(task.depends_on) if hasattr(task, "depends_on") and task.depends_on else [],
            )
            extracted["recipe_saved"] = True

        else:
            # Failure — analyze and store the lesson
            content = (
                f"Task '{task_title}' ({task_id}) failed on attempt {attempt_number}. "
                f"Error: {verification_msg[:500]}"
            )

            # Determine category based on error content
            category = "anti_pattern"
            lower_msg = verification_msg.lower()
            if any(kw in lower_msg for kw in ["path", "import", "module", "mpi", "env", "permission"]):
                category = "environment"

            mem_id = self.add_memory(
                content,
                task_id=task_id,
                category=category,
                attempt=attempt_number,
                success=False,
                complexity=complexity,
            )
            if mem_id:
                extracted["memories_added"] += 1

        return extracted

    # ------------------------------------------------------------------
    # Retrieve (pre-prompt)
    # ------------------------------------------------------------------

    def retrieve(self, task: Any) -> str:
        """Retrieve relevant memories for injection into a task prompt.

        Combines semantic memories, suspect tests, and relevant recipes
        into a formatted string ready for prompt injection.

        Args:
            task: Task object

        Returns:
            Formatted memory section for prompt injection (may be empty)
        """
        sections = []
        task_id = task.spec_id if hasattr(task, "spec_id") else ""
        task_desc = task.description if hasattr(task, "description") else ""
        task_title = task.title if hasattr(task, "title") else ""
        depends_on = list(task.depends_on) if hasattr(task, "depends_on") and task.depends_on else []

        # 1. Semantic memories
        query = f"{task_title} {task_desc}"
        memories = self.search_memories(query[:500], limit=_MAX_PROMPT_MEMORIES)
        if memories:
            lines = ["### Lessons from Previous Runs"]
            for mem in memories:
                score = mem.get("score", 0)
                text = mem.get("memory", "")
                meta = mem.get("metadata", {})
                usefulness = meta.get("usefulness", 0)
                category = meta.get("category", "")

                confidence = "HIGH" if (score > 0.8 or usefulness > 0.5) else "MEDIUM"
                prefix = f"[{confidence}]"
                if category:
                    prefix += f" [{category}]"

                lines.append(f"- **{prefix}** {text}")

                # Track this retrieval for usefulness scoring
                mem_id = mem.get("id")
                if mem_id:
                    # Don't await — fire-and-forget metadata update
                    try:
                        self.update_usefulness(mem_id, helped=False)  # Will update to True on success
                    except Exception:
                        pass

            sections.append("\n".join(lines))

        # 2. Suspect tests
        suspects = self.get_suspect_tests(task_id=task_id)
        if suspects:
            lines = ["### ⚠️ Suspect Tests (may be buggy — verify test correctness!)"]
            for s in suspects:
                lines.append(
                    f"- `{s['test_name']}`: {s['reason']}. "
                    f"Failed {s['failure_count']} times. "
                    f"Error: {s['error_preview'][:100]}"
                )
            sections.append("\n".join(lines))

        # 3. Relevant recipes from dependencies
        recipes = self.get_relevant_recipes(task_id, depends_on)
        if recipes:
            lines = ["### Working Patterns (from dependency tasks)"]
            for r in recipes:
                lines.append(f"- **{r.get('title', r['source_task'])}**: {r.get('pattern', '')}")
                if r.get("key_code"):
                    # Include a brief code snippet
                    code = r["key_code"][:300]
                    lines.append(f"  ```\n  {code}\n  ```")
            sections.append("\n".join(lines))

        if not sections:
            return ""

        # Assemble and truncate to token budget
        result = "## Project Knowledge (from previous runs)\n\n" + "\n\n".join(sections)
        if len(result) > _MAX_PROMPT_CHARS:
            result = result[:_MAX_PROMPT_CHARS] + "\n\n*(truncated — more memories available)*"

        return result

    def mark_memories_helped(self, task: Any, success: bool) -> None:
        """Mark recently-retrieved memories as having helped (or not).

        Called after task verification to update usefulness scores
        of memories that were injected into the prompt.

        Args:
            task: The task that was executed
            success: Whether the task succeeded
        """
        if not self._mem0:
            return

        task_desc = task.description if hasattr(task, "description") else ""
        task_title = task.title if hasattr(task, "title") else ""
        query = f"{task_title} {task_desc}"

        # Re-search to find what was injected (same query as retrieve)
        memories = self.search_memories(query[:500], limit=_MAX_PROMPT_MEMORIES)
        for mem in memories:
            mem_id = mem.get("id")
            if mem_id:
                try:
                    self.update_usefulness(mem_id, helped=success)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def regenerate_knowledge_md(self) -> None:
        """Regenerate human-readable knowledge.md from Mem0 memories.

        This is a convenience file for humans to review and optionally
        edit. It's regenerated from the actual memory store.
        """
        if not self._mem0:
            return

        try:
            all_memories = self._mem0.get_all(user_id=self.project_id)
            if not all_memories or "results" not in all_memories:
                return

            lines = [
                "# Project Knowledge",
                f"*Auto-generated from memory store. Last updated: {datetime.now().isoformat()}*",
                "",
            ]

            # Group by category
            by_category: dict[str, list] = {}
            for mem in all_memories["results"]:
                cat = mem.get("metadata", {}).get("category", "other")
                by_category.setdefault(cat, []).append(mem)

            for category, memories in sorted(by_category.items()):
                lines.append(f"## {category.replace('_', ' ').title()}")
                for mem in memories:
                    meta = mem.get("metadata", {})
                    usefulness = meta.get("usefulness", 0)
                    task_id = meta.get("task_id", "")
                    text = mem.get("memory", "")
                    lines.append(f"- [{task_id}] (usefulness: {usefulness:.2f}) {text}")
                lines.append("")

            self._knowledge_md_path.write_text("\n".join(lines))

        except Exception as e:
            print(f"⚠️  Knowledge MD regeneration failed: {e}")

    def get_stats(self) -> dict:
        """Get memory system statistics."""
        stats = {
            "semantic_memories": 0,
            "test_stability_entries": 0,
            "suspect_tests": 0,
            "recipes": 0,
            "mem0_available": _MEM0_AVAILABLE and self._mem0 is not None,
        }

        if self._mem0:
            try:
                all_mem = self._mem0.get_all(user_id=self.project_id)
                if all_mem and "results" in all_mem:
                    stats["semantic_memories"] = len(all_mem["results"])
            except Exception:
                pass

        stability = self._load_test_stability()
        stats["test_stability_entries"] = len(stability)
        stats["suspect_tests"] = len(self.get_suspect_tests())

        recipes = self._load_recipes()
        stats["recipes"] = len(recipes)

        return stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_error_signature(error_msg: str) -> str:
    """Create a stable hash for an error message.

    Normalizes the error to group similar failures:
    - Strips line numbers, file paths, timestamps
    - Keeps the error type and key message
    """
    import re

    # Remove file paths
    normalized = re.sub(r'(?:/[\w./]+)+', '<PATH>', error_msg)
    # Remove line numbers
    normalized = re.sub(r'line \d+', 'line N', normalized)
    # Remove timestamps
    normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '<TIME>', normalized)
    # Remove hex addresses
    normalized = re.sub(r'0x[0-9a-fA-F]+', '<ADDR>', normalized)
    # Collapse whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _compute_impl_hash(task: Any, project_dir: Path) -> str:
    """Compute a hash of the implementation files for a task.

    Used to detect whether different attempts produced different code
    (independent implementations).
    """
    hasher = hashlib.sha256()

    if hasattr(task, "expected_outputs"):
        for output in task.expected_outputs:
            fpath = project_dir / output.path
            if fpath.exists():
                try:
                    content = fpath.read_bytes()
                    hasher.update(content)
                except Exception:
                    pass

    return hasher.hexdigest()[:16]
