"""
Research Controller for BOB Framework
======================================

Implements the research-first workflow where tasks with research_required=True
are researched before implementation.

This controller:
1. Checks if research is needed (research_required and not research_complete)
2. Executes research using Perplexity MCP (if available) or web search
3. Documents findings in task.research_findings
4. Marks research_complete when done
5. Provides research context for implementation prompts

Research-First Workflow:
1. Task fails or is marked with research_required=True
2. ResearchController.should_research(task) → True
3. ResearchController.run_research(task) → executes research
4. Task.research_complete set to True
5. ResearchController.get_implementation_context(task) → research findings
6. Coding agent receives research context in prompt
7. Task implementation proceeds with research insights
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import json

import httpx

from bob.database.manager import DatabaseManager
from bob.models.base import Task, TaskStatus
from bob.orchestrator.research_agent import (
    ResearchContext,
    ResearchResult,
    ResearchTracker,
)


class ResearchController:
    """
    Controls the research-first workflow for tasks.

    Determines when research is needed, executes research operations,
    and provides research context for implementation.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        workspace_dir: Path,
        perplexity_available: bool = True,
    ):
        """Initialize research controller.

        Args:
            db_manager: Database manager instance
            workspace_dir: Path to project workspace directory
            perplexity_available: Whether Perplexity MCP is available
        """
        self.db_manager = db_manager
        self.workspace_dir = Path(workspace_dir)
        self.perplexity_available = perplexity_available
        self.research_tracker = ResearchTracker(self.workspace_dir)

        # Check for Perplexity API key
        if not os.getenv("PERPLEXITY_API_KEY"):
            self.perplexity_available = False

    def should_research(self, task: Task) -> bool:
        """Check if a task needs research.

        Args:
            task: Task to check

        Returns:
            True if research is needed, False otherwise
        """
        # Research needed if:
        # 1. Task has research_required=True
        # 2. Research not yet completed
        # 3. Task has research queries to investigate
        return (
            task.research_required
            and not task.research_complete
            and len(task.research_queries) > 0
        )

    def run_research(
        self,
        task: Task,
        research_type: str = "quick",
        max_queries: int = 3,
    ) -> bool:
        """Execute research for a task.

        This method would normally integrate with Perplexity MCP or web search.
        For now, it simulates research by creating placeholder findings.

        Args:
            task: Task to research
            research_type: Type of research ("quick", "deep", "experimental")
            max_queries: Maximum number of queries to execute

        Returns:
            True if research completed successfully, False otherwise
        """
        if not self.should_research(task):
            return False

        # Initialize research context
        context = ResearchContext(self.workspace_dir, task.id)

        # Filter to untried queries
        untried_queries = self.research_tracker.get_untried_queries(
            task.id, task.research_queries
        )

        if not untried_queries:
            # All queries already tried
            task.research_complete = True
            self.db_manager.update_task(
                task.id,
                research_complete=True,
            )
            return True

        # Limit to max_queries
        queries_to_try = untried_queries[:max_queries]

        # Execute research for each query
        findings_dict: dict[str, Any] = {}

        for query in queries_to_try:
            # Record query attempt
            self.research_tracker.record_query(task.id, query)

            # In production, this would call Perplexity MCP or web search
            # For now, create placeholder result
            result = self._execute_research_query(query, research_type)

            # Add to context
            context.add_research(result)

            # Store in findings dict
            findings_dict[query] = {
                "findings": result.findings,
                "sources": result.sources,
                "suggestions": result.suggestions,
                "code_examples": result.code_examples,
                "timestamp": result.timestamp,
                "success": result.success,
            }

        # Update task with findings
        research_findings = task.research_findings.copy() if task.research_findings else {}
        research_findings.update(findings_dict)

        # Mark research complete
        task.research_complete = True
        task.research_findings = research_findings

        # Update database
        self.db_manager.update_task(
            task.id,
            research_complete=True,
            research_findings=research_findings,
        )

        return True

    def _execute_research_query(
        self,
        query: str,
        research_type: str,
    ) -> ResearchResult:
        """Execute a single research query using Perplexity API.

        Makes a real HTTP request to Perplexity's research API and parses results.

        Args:
            query: Research query to execute
            research_type: Type of research (affects model selection)

        Returns:
            ResearchResult with findings from Perplexity
        """
        # Check for API key
        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            return ResearchResult(
                query=query,
                findings=f"Research needed for: {query}\n\nPerplexity API key not configured.",
                sources=[],
                suggestions=["Set PERPLEXITY_API_KEY environment variable"],
                code_examples=[],
                success=False,
                error="PERPLEXITY_API_KEY not set",
            )

        # Select model based on research type
        model_map = {
            "quick": "sonar",
            "deep": "sonar-reasoning",
            "experimental": "sonar-reasoning",
        }
        model = model_map.get(research_type, "sonar")

        # Prepare API request
        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Construct research-focused prompt
        research_prompt = f"""Research the following question and provide:
1. Key findings and information
2. Relevant sources and documentation
3. Practical suggestions for implementation
4. Code examples if applicable

Question: {query}

Please provide detailed, actionable research findings."""

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a technical research assistant. Provide thorough, accurate research with sources and practical examples.",
                },
                {
                    "role": "user",
                    "content": research_prompt,
                },
            ],
            "temperature": 0.2,
            "max_tokens": 2000,
        }

        try:
            # Make API request with timeout
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()

            # Parse response
            data = response.json()

            # Extract content from response
            if "choices" not in data or len(data["choices"]) == 0:
                return ResearchResult(
                    query=query,
                    findings="No results returned from Perplexity API",
                    sources=[],
                    suggestions=[],
                    code_examples=[],
                    success=False,
                    error="Empty response from API",
                )

            content = data["choices"][0]["message"]["content"]

            # Parse citations/sources if available
            sources = []
            if "citations" in data:
                sources = data["citations"][:5]  # Limit to top 5 sources

            # Extract code examples from content (simple heuristic)
            code_examples = []
            if "```" in content:
                parts = content.split("```")
                for i in range(1, len(parts), 2):
                    code_block = parts[i]
                    # Remove language identifier if present
                    lines = code_block.split("\n")
                    if lines[0].strip() and not lines[0].strip().startswith(("python", "javascript", "typescript", "bash", "sh")):
                        code_examples.append(code_block.strip())
                    elif len(lines) > 1:
                        code_examples.append("\n".join(lines[1:]).strip())

            # Extract suggestions (look for numbered lists or bullet points)
            suggestions = []
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith(("- ", "* ", "• ")) or (line and line[0].isdigit() and "." in line[:3]):
                    suggestion = line.lstrip("- *•0123456789. ")
                    if len(suggestion) > 10 and len(suggestion) < 200:
                        suggestions.append(suggestion)
                        if len(suggestions) >= 5:
                            break

            return ResearchResult(
                query=query,
                findings=content,
                sources=sources,
                suggestions=suggestions if suggestions else [
                    "Review the research findings above",
                    "Check official documentation",
                    "Consider implementation approaches",
                ],
                code_examples=code_examples,
                success=True,
            )

        except httpx.TimeoutException:
            return ResearchResult(
                query=query,
                findings=f"Research request timed out for: {query}",
                sources=[],
                suggestions=["Try again with a simpler query", "Check network connection"],
                code_examples=[],
                success=False,
                error="Request timeout",
            )

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}"
            if e.response.status_code == 429:
                error_msg = "Rate limit exceeded"
                suggestions = ["Wait before retrying", "Check API quota"]
            elif e.response.status_code == 401:
                error_msg = "Invalid API key"
                suggestions = ["Check PERPLEXITY_API_KEY is valid"]
            else:
                suggestions = ["Check API status", "Verify request format"]

            return ResearchResult(
                query=query,
                findings=f"API request failed: {error_msg}",
                sources=[],
                suggestions=suggestions,
                code_examples=[],
                success=False,
                error=error_msg,
            )

        except Exception as e:
            return ResearchResult(
                query=query,
                findings=f"Research failed for: {query}",
                sources=[],
                suggestions=["Check logs for details", "Verify API configuration"],
                code_examples=[],
                success=False,
                error=str(e),
            )

    def get_implementation_context(self, task: Task) -> str:
        """Get research context to inject into implementation prompt.

        Args:
            task: Task to get context for

        Returns:
            Formatted research context string
        """
        if not task.research_complete or not task.research_findings:
            return ""

        lines = [
            "## Research Findings",
            "",
            "The following research has been conducted for this task:",
            "",
        ]

        for query, findings in task.research_findings.items():
            lines.append(f"### Query: {query}")
            lines.append("")

            if findings.get("success", True):
                lines.append(findings.get("findings", "No findings available"))
                lines.append("")

                if findings.get("sources"):
                    lines.append("**Sources:**")
                    for source in findings["sources"][:3]:
                        lines.append(f"- {source}")
                    lines.append("")

                if findings.get("suggestions"):
                    lines.append("**Recommendations:**")
                    for suggestion in findings["suggestions"][:3]:
                        lines.append(f"- {suggestion}")
                    lines.append("")

                if findings.get("code_examples"):
                    lines.append("**Code Examples:**")
                    for i, example in enumerate(findings["code_examples"][:2], 1):
                        lines.append(f"```")
                        lines.append(example)
                        lines.append(f"```")
                    lines.append("")
            else:
                error = findings.get("error", "Research failed")
                lines.append(f"⚠️  Research failed: {error}")
                lines.append("")

        lines.append("---")
        lines.append(
            "Use these research findings to inform your implementation approach."
        )
        lines.append("")

        return "\n".join(lines)

    def reset_research(self, task: Task) -> None:
        """Reset research state for a task.

        Useful when task requirements change or research needs to be redone.

        Args:
            task: Task to reset research for
        """
        task.research_complete = False
        task.research_findings = {}

        # Update database
        self.db_manager.update_task(
            task.id,
            research_complete=False,
            research_findings={},
        )

        # Clear research tracker
        self.research_tracker.reset_task(task.id)

        # Clear research context file
        context = ResearchContext(self.workspace_dir, task.id)
        if context.context_file.exists():
            context.context_file.unlink()

    def get_research_summary(self, task: Task) -> str:
        """Get a summary of research conducted for a task.

        Args:
            task: Task to get summary for

        Returns:
            Human-readable research summary
        """
        context = ResearchContext(self.workspace_dir, task.id)
        return context.get_research_summary()

    def has_perplexity_available(self) -> bool:
        """Check if Perplexity MCP is available.

        Returns:
            True if Perplexity is available, False otherwise
        """
        return self.perplexity_available and bool(os.getenv("PERPLEXITY_API_KEY"))
