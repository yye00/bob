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

    async def execute_research(self, task: Task) -> bool:
        """Execute research for a task using Claude Code SDK.
        
        This method:
        1. Takes a task that has research_required=True
        2. Builds a research prompt from the task's error history and failure classification
        3. Calls Claude (via the SDK executor) with a prompt that asks it to:
           a. Search the codebase for related patterns
           b. Read any reference papers mentioned in the task description
           c. Analyze the error messages and suggest concrete fixes
        4. Stores findings in task.research_findings (a JSON dict field in the DB)
        5. Sets research_complete=True on the task

        Args:
            task: Task to research

        Returns:
            True if research completed successfully, False otherwise
        """
        if not task.research_required or task.research_complete:
            return False

        # Import SDK executor
        try:
            from bob.orchestrator.claude_sdk_executor import execute_task_with_sdk
        except ImportError:
            # Fallback to current implementation if SDK not available
            return self.run_research(task)

        # Build research prompt from task's error history and failure classification
        research_prompt = self._build_research_prompt(task)

        # Execute research using Claude SDK
        try:
            result = await execute_task_with_sdk(
                project_dir=self.workspace_dir,
                prompt=research_prompt,
                model="claude-sonnet-4-5-20250929",  # Use Sonnet for research
                timeout_seconds=1800,  # 30 minutes timeout for research
                verbose=True,  # Show tool use for monitoring
            )

            if result.success and result.output:
                # Parse the research findings from Claude's output
                findings = self._parse_research_output(result.output, task)
                
                # Store findings in task.research_findings
                task.research_findings = findings
                task.research_complete = True

                # Update database
                self.db_manager.update_task(
                    task.id,
                    research_complete=True,
                    research_findings=findings,
                )

                return True
            else:
                # Research failed - store error info
                error_findings = {
                    "error": "Research execution failed",
                    "error_details": result.error or "Unknown error",
                    "timestamp": datetime.now().isoformat(),
                }
                
                # Update database with error
                self.db_manager.update_task(
                    task.id,
                    research_findings=error_findings,
                )
                
                return False

        except Exception as e:
            # Handle unexpected errors
            error_findings = {
                "error": "Research execution exception",
                "error_details": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            
            # Update database with error
            self.db_manager.update_task(
                task.id,
                research_findings=error_findings,
            )
            
            return False

    def _build_research_prompt(self, task: Task) -> str:
        """Build a research prompt from the task's error history and failure classification."""
        prompt_lines = [
            "# Research Task",
            "",
            f"You are conducting research for the following task:",
            f"**Task ID:** {task.spec_id}",
            f"**Title:** {task.title}",
            f"**Description:** {task.description}",
            "",
        ]

        # Add acceptance criteria if available
        if task.acceptance_criteria:
            prompt_lines.extend([
                "**Acceptance Criteria:**",
                *[f"- {criterion}" for criterion in task.acceptance_criteria],
                "",
            ])

        # Add steps if available
        if task.steps:
            prompt_lines.extend([
                "**Implementation Steps:**",
                *[f"{i+1}. {step}" for i, step in enumerate(task.steps)],
                "",
            ])

        # Add error history if available
        error_history = task.research_findings.get("error_history", [])
        if error_history:
            prompt_lines.extend([
                "## Error History",
                "",
                "This task has failed multiple times. Here are the previous errors:",
                "",
            ])
            
            for i, error in enumerate(error_history[-3:], 1):  # Last 3 errors
                prompt_lines.extend([
                    f"### Error {i}",
                    f"- **Attempt:** {error.get('attempt', 'Unknown')}",
                    f"- **Model:** {error.get('model', 'Unknown')}",
                    f"- **Timestamp:** {error.get('timestamp', 'Unknown')}",
                    f"- **Error:** {error.get('error_msg', error.get('error', 'Unknown error'))}",
                    "",
                ])

        # Add failure type if available
        if task.failure_type:
            failure_type_str = task.failure_type.value if hasattr(task.failure_type, 'value') else str(task.failure_type)
            prompt_lines.extend([
                f"## Failure Classification",
                "",
                f"**Failure Type:** {failure_type_str}",
                "",
            ])

        # Add research queries if available
        if task.research_queries:
            prompt_lines.extend([
                "## Specific Research Queries",
                "",
                "Please investigate these specific questions:",
                *[f"- {query}" for query in task.research_queries],
                "",
            ])

        # Add the actual research instructions
        prompt_lines.extend([
            "## Research Instructions",
            "",
            "Please conduct thorough research to help implement this task successfully. Your research should include:",
            "",
            "1. **Codebase Analysis:**",
            "   - Search the current codebase for related patterns, functions, or modules",
            "   - Identify existing implementations that could be referenced or extended",
            "   - Look for similar functionality that already works",
            "",
            "2. **Documentation Review:**",
            "   - Read any reference papers, documentation, or specs mentioned in the task description",
            "   - Review relevant API documentation or technical specifications",
            "   - Check for existing tests that show expected behavior",
            "",
            "3. **Error Analysis:**",
            "   - Analyze the error messages from previous attempts",
            "   - Identify root causes and common failure patterns",
            "   - Suggest specific fixes for the identified issues",
            "",
            "4. **Implementation Recommendations:**",
            "   - Provide concrete, actionable implementation suggestions",
            "   - Include code examples or patterns where helpful",
            "   - Suggest the best approach based on your findings",
            "",
            "## Expected Output Format",
            "",
            "Please structure your research findings as follows:",
            "",
            "### Codebase Findings",
            "[What you found in the existing codebase]",
            "",
            "### Documentation Insights",
            "[Key insights from documentation/papers/specs]",
            "",
            "### Error Analysis",
            "[Analysis of the error patterns and root causes]",
            "",
            "### Implementation Recommendations",
            "[Specific, actionable recommendations with code examples]",
            "",
            "### Key References",
            "[Important files, functions, or documentation to reference]",
            "",
            "Be thorough but practical. Focus on actionable insights that will help implement this task successfully.",
        ])

        return "\n".join(prompt_lines)

    def _parse_research_output(self, output: str, task: Task) -> dict:
        """Parse research output from Claude and structure it as findings."""
        findings = {
            "research_conducted": True,
            "timestamp": datetime.now().isoformat(),
            "model_used": "claude-sonnet-4-5-20250929",
            "raw_output": output,
        }

        # Try to extract structured sections from the output
        sections = {
            "codebase_findings": [],
            "documentation_insights": [],
            "error_analysis": [],
            "implementation_recommendations": [],
            "key_references": [],
            "suggestions": [],
        }

        # Simple parsing - look for section headers and extract content
        lines = output.split('\n')
        current_section = None
        current_content = []

        section_map = {
            "codebase findings": "codebase_findings",
            "documentation insights": "documentation_insights", 
            "error analysis": "error_analysis",
            "implementation recommendations": "implementation_recommendations",
            "key references": "key_references",
        }

        for line in lines:
            line_lower = line.lower().strip()
            
            # Check if this line is a section header
            found_section = None
            for header, section_key in section_map.items():
                if header in line_lower and ('###' in line or '##' in line or line.startswith('#')):
                    found_section = section_key
                    break
            
            if found_section:
                # Save previous section
                if current_section and current_content:
                    content_text = '\n'.join(current_content).strip()
                    if content_text:
                        sections[current_section] = content_text
                
                # Start new section
                current_section = found_section
                current_content = []
            elif current_section:
                # Add content to current section
                current_content.append(line)

        # Save last section
        if current_section and current_content:
            content_text = '\n'.join(current_content).strip()
            if content_text:
                sections[current_section] = content_text

        # Extract actionable suggestions
        suggestions = []
        if sections.get("implementation_recommendations"):
            # Look for bullet points or numbered items
            for line in sections["implementation_recommendations"].split('\n'):
                line = line.strip()
                if line.startswith(('-', '*', '•')) or (len(line) > 0 and line[0].isdigit() and '.' in line[:5]):
                    suggestion = line.lstrip('- *•0123456789. ').strip()
                    if len(suggestion) > 10:  # Filter out very short items
                        suggestions.append(suggestion)

        # Store structured findings
        findings.update(sections)
        findings["suggestions"] = suggestions

        return findings

    def run_research(
        self,
        task: Task,
        research_type: str = "quick",
        max_queries: int = 3,
    ) -> bool:
        """Execute research for a task.

        Uses Perplexity API to perform real research queries and collect findings.

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

            # Execute research query using Perplexity API
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

        # Handle new format (from execute_research) - direct findings dict
        if "research_conducted" in task.research_findings:
            findings = task.research_findings
            
            lines.append("### Research Summary")
            lines.append("")
            
            # Add structured sections from new format
            if findings.get("codebase_findings"):
                lines.append("**Codebase Analysis:**")
                lines.append(findings["codebase_findings"])
                lines.append("")
            
            if findings.get("error_analysis"):
                lines.append("**Error Analysis:**") 
                lines.append(findings["error_analysis"])
                lines.append("")
                
            if findings.get("implementation_recommendations"):
                lines.append("**Implementation Recommendations:**")
                lines.append(findings["implementation_recommendations"])
                lines.append("")
                
            if findings.get("key_references"):
                lines.append("**Key References:**")
                lines.append(findings["key_references"])
                lines.append("")
                
            if findings.get("suggestions"):
                lines.append("**Actionable Steps:**")
                for suggestion in findings["suggestions"][:5]:
                    lines.append(f"- {suggestion}")
                lines.append("")
        
        # Handle old format (from run_research) - query->findings mapping  
        else:
            for query, findings in task.research_findings.items():
                # Skip non-query keys like error_history
                if query in ["error_history"]:
                    continue
                    
                lines.append(f"### Query: {query}")
                lines.append("")

                if isinstance(findings, dict) and findings.get("success", True):
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
                elif isinstance(findings, dict):
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
