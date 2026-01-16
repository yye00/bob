"""
Research Agent for BOB Framework
=================================

Provides research capabilities using Perplexity MCP integration.
Used when tasks fail due to missing information or wrong assumptions.

Adapted from autonomous-coding research_agent.py with:
- Integration with BOB's Task model (research_required, research_complete)
- Database-backed research tracking
- Support for configurable MCP servers
- Structured research findings storage

Research Modes:
- Quick search: Fast lookup for specific errors or APIs
- Deep research: Comprehensive investigation of approaches
- Experimentation: Try commands/approaches with rollback
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from bob.models.base import Task


@dataclass
class ResearchResult:
    """Result from a research operation."""
    query: str
    findings: str
    sources: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    code_examples: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "query": self.query,
            "findings": self.findings,
            "sources": self.sources,
            "suggestions": self.suggestions,
            "code_examples": self.code_examples,
            "timestamp": self.timestamp,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class ExperimentResult:
    """Result from an experimental command."""
    command: str
    output: str
    success: bool
    rollback_needed: bool = False
    rollback_command: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "command": self.command,
            "output": self.output,
            "success": self.success,
            "rollback_needed": self.rollback_needed,
            "rollback_command": self.rollback_command,
            "timestamp": self.timestamp,
        }


class ResearchContext:
    """
    Manages research context and history for a task.

    Persists to workspace_dir/harness_logs/research/task_{id}.json
    """

    def __init__(self, workspace_dir: Path, task_id: str):
        """Initialize research context.

        Args:
            workspace_dir: Path to project workspace directory
            task_id: Task ID (database ID)
        """
        self.workspace_dir = Path(workspace_dir)
        self.task_id = task_id
        self.research_dir = self.workspace_dir / "harness_logs" / "research"
        self.context_file = self.research_dir / f"task_{task_id}.json"
        self.research_history: list[ResearchResult] = []
        self.experiment_history: list[ExperimentResult] = []
        self._load()

    def _load(self) -> None:
        """Load research context from file."""
        if self.context_file.exists():
            try:
                data = json.loads(self.context_file.read_text())
                for r in data.get("research_history", []):
                    self.research_history.append(ResearchResult(**r))
                for e in data.get("experiment_history", []):
                    self.experiment_history.append(ExperimentResult(**e))
            except (json.JSONDecodeError, IOError):
                pass

    def _save(self) -> None:
        """Save research context to file."""
        self.research_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "task_id": self.task_id,
            "research_history": [r.to_dict() for r in self.research_history],
            "experiment_history": [e.to_dict() for e in self.experiment_history],
            "updated_at": datetime.now().isoformat(),
        }
        self.context_file.write_text(json.dumps(data, indent=2))

    def add_research(self, result: ResearchResult) -> None:
        """Add a research result to history."""
        self.research_history.append(result)
        self._save()

    def add_experiment(self, result: ExperimentResult) -> None:
        """Add an experiment result to history."""
        self.experiment_history.append(result)
        self._save()

    def get_research_summary(self) -> str:
        """Get a summary of all research for this task."""
        if not self.research_history:
            return "No research has been conducted yet."

        lines = [f"Research Summary for Task {self.task_id}:", "=" * 50]

        for i, r in enumerate(self.research_history, 1):
            lines.append(f"\n{i}. Query: {r.query}")
            lines.append(f"   Findings: {r.findings[:200]}...")
            if r.suggestions:
                lines.append(f"   Suggestions: {', '.join(r.suggestions[:3])}")
            if r.sources:
                lines.append(f"   Sources: {len(r.sources)} found")

        return "\n".join(lines)


# Perplexity MCP tools for the agent
PERPLEXITY_TOOLS = [
    "mcp__perplexity__perplexity_ask",
    "mcp__perplexity__perplexity_search",
    "mcp__perplexity__perplexity_research",
    "mcp__perplexity__perplexity_reason",
]


def get_perplexity_mcp_config() -> dict[str, Any]:
    """
    Get MCP server configuration for Perplexity.

    Note: Requires PERPLEXITY_API_KEY environment variable.

    Returns:
        MCP server configuration dict
    """
    return {
        "perplexity": {
            "command": "npx",
            "args": ["-y", "@perplexity-ai/mcp-server"],
        }
    }


def generate_research_prompt(
    task: Task,
    queries: list[str],
    error_context: str,
    research_type: str = "quick",
) -> str:
    """
    Generate a research prompt for the agent.

    Args:
        task: The Task being researched
        queries: Research queries to investigate
        error_context: Context about errors encountered
        research_type: "quick", "deep", or "experimental"

    Returns:
        Prompt string for the agent
    """
    queries_text = "\n".join(f"  - {q}" for q in queries)

    if research_type == "quick":
        return f"""## Research Task: Quick Investigation

You need to research solutions for a failing task. Use the Perplexity search tools to find answers.

**Task:** {task.spec_id} - {task.title}

**Error Context:**
{error_context[:500]}

**Research Queries:**
{queries_text}

**Instructions:**
1. Use `perplexity_search` or `perplexity_ask` for each query
2. Focus on finding:
   - Correct API usage / function signatures
   - Common solutions to the error
   - Working code examples
3. Document findings in a research_notes.md file
4. Apply findings to fix the task

Do NOT spend more than 3 searches per query. If no clear answer, report what you found.
"""

    elif research_type == "deep":
        steps_text = "\n".join(f"  {i}. {s}" for i, s in enumerate(task.steps, 1))
        return f"""## Research Task: Deep Investigation

The task has failed repeatedly despite multiple attempts. Conduct thorough research.

**Task:** {task.spec_id}
**Title:** {task.title}
**Description:** {task.description}
**Implementation Steps:**
{steps_text}

**Error Context:**
{error_context}

**Research Queries:**
{queries_text}

**Instructions:**
1. Use `perplexity_research` for comprehensive analysis
2. Investigate:
   - Alternative approaches to implementing this task
   - Best practices for similar tasks
   - Common pitfalls and how to avoid them
   - Working examples from real projects
3. Document all findings in research_notes.md
4. Create an updated implementation plan based on research
5. If the approach seems fundamentally wrong, document why and suggest alternatives

Take your time - thorough research now saves repeated failures later.
"""

    else:  # experimental
        return f"""## Research Task: Experimental Investigation

Try experimental approaches to understand why the task is failing.

**Task:** {task.spec_id} - {task.title}

**Error Context:**
{error_context[:500]}

**Instructions:**
1. First, research potential solutions using Perplexity tools
2. Then experiment with small, isolated test cases:
   - Create a minimal test file to reproduce the issue
   - Try different approaches in isolation
   - Test specific API calls or commands
3. Document what works and what doesn't
4. Keep track of any changes that need rollback

**Safety Rules:**
- Do NOT modify production code during experiments
- Create experiment files in a /experiments subdirectory
- Always test in isolation before applying to real code
- If an experiment causes issues, document and rollback
"""


def generate_research_queries_from_error(error_msg: str, context: str = "") -> list[str]:
    """
    Generate research queries from an error message.

    Args:
        error_msg: The error message to analyze
        context: Additional context (e.g., language, framework)

    Returns:
        List of research queries
    """
    queries = []

    # Extract error type
    error_match = re.search(r'(\w+Error|\w+Exception):', error_msg)
    if error_match:
        error_type = error_match.group(1)
        queries.append(f"Python {error_type} common causes and solutions")

    # Extract module/package names
    module_match = re.search(r"No module named ['\"](\w+)['\"]", error_msg)
    if module_match:
        module = module_match.group(1)
        queries.append(f"Python {module} installation and usage guide")

    # Extract function/method names
    func_match = re.search(r"(\w+)\(\).*(?:takes|expected|got)", error_msg)
    if func_match:
        func = func_match.group(1)
        queries.append(f"Python {func} function correct usage parameters")

    # Extract attribute names
    attr_match = re.search(r"has no attribute ['\"](\w+)['\"]", error_msg)
    if attr_match:
        attr = attr_match.group(1)
        queries.append(f"Python {attr} attribute alternative methods 2026")

    # Generic query if nothing specific found
    if not queries:
        # Clean up error message for query
        clean_error = re.sub(r'[^\w\s]', ' ', error_msg[:100])
        queries.append(f"Python error: {clean_error}")

    # Add context if provided
    if context:
        queries = [f"{context} {q}" for q in queries]

    return queries[:3]  # Limit to 3 queries


def parse_research_response(response: str) -> ResearchResult:
    """
    Parse a research response into structured result.

    Args:
        response: Raw response from Perplexity

    Returns:
        Structured ResearchResult
    """
    # Extract sources (URLs)
    sources = re.findall(r'https?://[^\s\)\]]+', response)

    # Extract code blocks
    code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', response, re.DOTALL)

    # Extract suggestions (lines starting with - or *)
    suggestions = re.findall(r'^[\-\*]\s+(.+)$', response, re.MULTILINE)

    return ResearchResult(
        query="(parsed from response)",
        findings=response[:2000],  # Truncate long responses
        sources=list(set(sources))[:5],  # Unique, max 5
        suggestions=suggestions[:5],
        code_examples=code_blocks[:3],
    )


def create_research_session_prompt(
    task: Task,
    classification_result: dict[str, Any],
    previous_research: Optional[str] = None,
) -> str:
    """
    Create a comprehensive research session prompt.

    Args:
        task: Task being researched
        classification_result: Result from failure_classifier
        previous_research: Summary of previous research if any

    Returns:
        Complete prompt for research session
    """
    prev_section = ""
    if previous_research:
        prev_section = f"""
## Previous Research
{previous_research}

Build on this research - don't repeat queries already tried.
"""

    return f"""# Research Session for Task {task.spec_id}

## Problem Summary
**Task:** {task.title}
**Failure Type:** {classification_result.get('failure_type', 'unknown')}
**Reason:** {classification_result.get('reason', 'Unknown')}
**Confidence:** {classification_result.get('confidence', 0):.0%}

## Research Queries to Investigate
{chr(10).join(f"- {q}" for q in classification_result.get('research_queries', []))}
{prev_section}
## Tools Available
- `perplexity_ask`: Quick Q&A with web search (use for simple questions)
- `perplexity_search`: Direct web search (use for finding specific docs/examples)
- `perplexity_research`: Deep research (use for complex problems)
- `perplexity_reason`: Advanced reasoning (use for analyzing approaches)

## Instructions

1. **Research Phase** (use Perplexity tools):
   - Search for solutions to each query
   - Look for working code examples
   - Find official documentation
   - Identify common pitfalls

2. **Analysis Phase**:
   - Compare different approaches found
   - Identify the most promising solution
   - Note any prerequisites or setup needed

3. **Documentation Phase**:
   - Create/update `research_notes.md` with findings
   - Include sources and code examples
   - Document the recommended approach

4. **Application Phase**:
   - Apply the research to fix the task
   - If the approach needs to change fundamentally, document why

## Output Expected
After research, update the task implementation based on findings.
If you determine the task needs restructuring, create a research report instead of implementing.
"""


class ResearchTracker:
    """
    Track research attempts and prevent redundant searches.
    """

    def __init__(self, workspace_dir: Path):
        """Initialize research tracker.

        Args:
            workspace_dir: Path to project workspace directory
        """
        self.workspace_dir = Path(workspace_dir)
        self.tracker_file = self.workspace_dir / "harness_logs" / "research_tracker.json"
        self.queries_tried: dict[str, list[str]] = {}  # task_id -> queries
        self._load()

    def _load(self) -> None:
        """Load tracker state."""
        if self.tracker_file.exists():
            try:
                data = json.loads(self.tracker_file.read_text())
                self.queries_tried = data.get("queries_tried", {})
            except (json.JSONDecodeError, IOError):
                pass

    def _save(self) -> None:
        """Save tracker state."""
        self.tracker_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "queries_tried": self.queries_tried,
            "updated_at": datetime.now().isoformat(),
        }
        self.tracker_file.write_text(json.dumps(data, indent=2))

    def was_query_tried(self, task_id: str, query: str) -> bool:
        """Check if a query was already tried for a task.

        Args:
            task_id: Task ID
            query: Research query

        Returns:
            True if query was already tried
        """
        queries = self.queries_tried.get(task_id, [])
        # Normalize for comparison
        normalized = query.lower().strip()
        return any(q.lower().strip() == normalized for q in queries)

    def record_query(self, task_id: str, query: str) -> None:
        """Record that a query was tried.

        Args:
            task_id: Task ID
            query: Research query
        """
        if task_id not in self.queries_tried:
            self.queries_tried[task_id] = []
        self.queries_tried[task_id].append(query)
        self._save()

    def get_untried_queries(self, task_id: str, queries: list[str]) -> list[str]:
        """Filter to only queries not yet tried.

        Args:
            task_id: Task ID
            queries: List of queries to check

        Returns:
            List of queries not yet tried
        """
        return [q for q in queries if not self.was_query_tried(task_id, query=q)]

    def reset_task(self, task_id: str) -> None:
        """Reset research history for a task.

        Args:
            task_id: Task ID to reset
        """
        if task_id in self.queries_tried:
            del self.queries_tried[task_id]
            self._save()
