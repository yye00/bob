"""
Task Decomposition for BOB Framework (Runtime / DB-backed)
===========================================================

Breaks large, complex tasks into smaller, manageable sub-tasks
with clear dependencies. Creates sub-tasks in the database.

Used when tasks fail repeatedly due to complexity during EXECUTION.

NOTE: There are two decomposer implementations:

  1. THIS FILE (orchestrator/task_decomposer.py)
     - Database-backed, creates Task records in SQLite
     - Used by engine.py during runtime task execution
     - Operates on Task model objects

  2. decomposers/task_decomposer.py (+ unified_decomposer.py)
     - WorkUnit-based, operates in-memory during planning
     - Used by DecompositionEngine during `bob plan`
     - Operates on WorkUnit objects with confidence scores
     - Generates verification contracts

They share the same decomposition prompt patterns but serve
different lifecycle stages (planning vs execution).
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from bob.models.base import Task, TaskStatus
from bob.database.manager import DatabaseManager


@dataclass
class SubTask:
    """A sub-task created from decomposition."""
    spec_id: str
    title: str
    description: str
    steps: list[str]
    depends_on: list[str]
    parent_spec_id: str
    priority: str = "medium"
    category: str = "functional"
    created_from_decomposition: bool = True
    # Verification fields inherited from parent
    verify_script: str = ""
    expected_outputs: list = field(default_factory=list)
    acceptance_criteria: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "spec_id": self.spec_id,
            "title": self.title,
            "description": self.description,
            "steps": self.steps,
            "depends_on": self.depends_on,
            "parent_spec_id": self.parent_spec_id,
            "priority": self.priority,
            "category": self.category,
            "created_from_decomposition": self.created_from_decomposition,
            "verify_script": self.verify_script,
            "expected_outputs": self.expected_outputs,
            "acceptance_criteria": self.acceptance_criteria,
        }


@dataclass
class DecompositionResult:
    """Result of task decomposition."""
    parent_task_id: str
    parent_spec_id: str
    sub_tasks: list[SubTask]
    reasoning: str
    success: bool
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "parent_task_id": self.parent_task_id,
            "parent_spec_id": self.parent_spec_id,
            "sub_tasks": [st.to_dict() for st in self.sub_tasks],
            "reasoning": self.reasoning,
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class TaskDecomposer:
    """
    Decomposes complex tasks into smaller sub-tasks.

    Uses the BOB database to track tasks and decomposition history.
    """

    def __init__(self, db_manager: DatabaseManager):
        """Initialize the decomposer with a database manager.

        Args:
            db_manager: DatabaseManager instance for task operations
        """
        self.db_manager = db_manager

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """Get a specific task by ID.

        Args:
            task_id: The task ID to retrieve

        Returns:
            Task object or None if not found
        """
        return self.db_manager.get_task(task_id)

    def get_next_spec_id(self, project_id: str) -> int:
        """Get the next available spec ID number for a project.

        Args:
            project_id: The project ID

        Returns:
            Next available spec ID number (e.g., 76 for F076)
        """
        tasks = self.db_manager.list_tasks(project_id)
        max_id = 0
        for task in tasks:
            match = re.match(r"F(\d+)", task.spec_id)
            if match:
                max_id = max(max_id, int(match.group(1)))
        return max_id + 1

    def decompose_task(
        self,
        task_id: str,
        sub_tasks: list[dict],
        reasoning: str,
    ) -> DecompositionResult:
        """
        Decompose a task into sub-tasks.

        Args:
            task_id: ID of the task to decompose
            sub_tasks: List of sub-task specs with:
                - title: Sub-task title
                - description: Sub-task description
                - steps: List of steps
                - internal_name: Used for internal dependency references
                - internal_deps: List of internal_name dependencies
                - priority: Priority (critical, high, medium, low)
                - category: Category (functional, infrastructure, etc.)
            reasoning: Explanation of the decomposition

        Returns:
            DecompositionResult with details of the decomposition
        """
        parent = self.get_task_by_id(task_id)

        if parent is None:
            return DecompositionResult(
                parent_task_id=task_id,
                parent_spec_id="unknown",
                sub_tasks=[],
                reasoning=reasoning,
                success=False,
                error=f"Task {task_id} not found",
            )

        # Create sub-tasks with spec IDs derived from parent (T001a, T001b, ...)
        created_subs: list[SubTask] = []
        id_mapping: dict[str, str] = {}  # internal_name -> actual_spec_id

        # First pass: assign spec IDs using parent's ID + letter suffix
        for i, st_spec in enumerate(sub_tasks):
            internal_name = st_spec.get("internal_name", f"sub_{i+1}")
            suffix = chr(ord('a') + i)  # a, b, c, ...
            new_spec_id = f"{parent.spec_id}{suffix}"
            id_mapping[internal_name] = new_spec_id

        # Second pass: create sub-tasks with proper dependencies
        for i, st_spec in enumerate(sub_tasks):
            internal_name = st_spec.get("internal_name", f"sub_{i+1}")
            new_spec_id = id_mapping[internal_name]

            # Resolve dependencies
            internal_deps = st_spec.get("internal_deps", [])
            resolved_deps = []
            for dep in internal_deps:
                if dep in id_mapping:
                    resolved_deps.append(id_mapping[dep])
                elif dep.startswith("F"):
                    resolved_deps.append(dep)  # Already a spec ID

            # Include parent's dependencies unless they're being replaced
            parent_deps = parent.depends_on
            for pd in parent_deps:
                if pd not in resolved_deps:
                    resolved_deps.append(pd)

            sub = SubTask(
                spec_id=new_spec_id,
                title=st_spec.get("title", f"Sub-task of {parent.spec_id}"),
                description=st_spec.get("description", f"Sub-task of {parent.title}"),
                steps=st_spec.get("steps", []),
                depends_on=resolved_deps,
                parent_spec_id=parent.spec_id,
                priority=st_spec.get("priority", parent.priority),
                category=st_spec.get("category", parent.category),
                verify_script=st_spec.get("verify_script", ""),
                expected_outputs=st_spec.get("expected_outputs", []),
                acceptance_criteria=st_spec.get("acceptance_criteria",
                                                st_spec.get("steps", [])),
            )
            created_subs.append(sub)

        # Add sub-tasks to the database
        for sub in created_subs:
            new_task = Task(
                id=f"task-{uuid.uuid4().hex[:12]}",
                project_id=parent.project_id,
                spec_id=sub.spec_id,
                title=sub.title,
                description=sub.description,
                acceptance_criteria=sub.acceptance_criteria,
                steps=sub.steps,
                depends_on=sub.depends_on,
                priority=sub.priority,
                category=sub.category,
                labels=parent.labels + ["decomposed-subtask"],
                expected_outputs=sub.expected_outputs,
                verify_script=sub.verify_script,
            )
            self.db_manager.create_task(new_task)

        # Create an INTEGRATION task that depends on ALL sub-tasks
        # and runs the parent's original verify_script + tests
        integration_spec_id = f"{parent.spec_id}-integration"
        integration_deps = [sub.spec_id for sub in created_subs]

        # Build integration verify script that runs the original parent's full verification
        integration_verify = parent.verify_script or ""

        # Build integration description
        sub_list = "\n".join(f"  - {s.spec_id}: {s.title}" for s in created_subs)
        integration_desc = (
            f"Integration task for {parent.spec_id} ({parent.title}).\n\n"
            f"This task verifies that all sub-tasks work together correctly.\n"
            f"Sub-tasks:\n{sub_list}\n\n"
            f"Run the original verify script and all verification tests from the "
            f"parent task to ensure the pieces integrate properly.\n"
            f"If integration fails, examine the interfaces between sub-tasks "
            f"and fix any incompatibilities."
        )

        integration_task = Task(
            id=f"task-{uuid.uuid4().hex[:12]}",
            project_id=parent.project_id,
            spec_id=integration_spec_id,
            title=f"Integration: {parent.title}",
            description=integration_desc,
            acceptance_criteria=parent.acceptance_criteria,
            steps=[
                f"Review code from all sub-tasks: {', '.join(s.spec_id for s in created_subs)}",
                "Ensure all modules import and work together",
                "Fix any interface mismatches between sub-task outputs",
                "Run the full verify script to confirm integration",
            ],
            depends_on=integration_deps,
            priority=parent.priority,
            category=parent.category,
            labels=parent.labels + ["integration-task"],
            expected_outputs=parent.expected_outputs,
            verify_script=integration_verify,
            numerical_tests=parent.numerical_tests,
            algorithmic_tests=parent.algorithmic_tests,
            convergence_tests=parent.convergence_tests,
        )
        self.db_manager.create_task(integration_task)

        # Mark parent as decomposed
        self.db_manager.update_task(
            task_id=task_id,
            status=TaskStatus.DECOMPOSED,
        )

        # Store decomposition metadata on parent for reference
        decomp_meta = parent.research_findings.copy() if parent.research_findings else {}
        decomp_meta["decomposition"] = {
            "sub_tasks": [s.spec_id for s in created_subs],
            "integration_task": integration_spec_id,
            "reasoning": reasoning,
            "timestamp": datetime.now().isoformat(),
        }
        self.db_manager.update_task(task_id, research_findings=decomp_meta)

        # Return result (include integration task in sub_tasks list)
        integration_sub = SubTask(
            spec_id=integration_spec_id,
            title=f"Integration: {parent.title}",
            description=integration_desc,
            steps=integration_task.steps,
            depends_on=integration_deps,
            parent_spec_id=parent.spec_id,
            priority=parent.priority,
            verify_script=integration_verify,
            expected_outputs=parent.expected_outputs,
            acceptance_criteria=parent.acceptance_criteria,
        )

        result = DecompositionResult(
            parent_task_id=task_id,
            parent_spec_id=parent.spec_id,
            sub_tasks=created_subs + [integration_sub],
            reasoning=reasoning,
            success=True,
        )

        return result


def generate_decomposition_prompt(task: Task, error_context: str) -> str:
    """
    Generate a prompt for the agent to decompose a task.

    Args:
        task: The task to decompose
        error_context: Context about why decomposition is needed

    Returns:
        Prompt string for decomposition
    """
    return f"""# Task Decomposition Request

The following task is too complex and needs to be broken into smaller, manageable sub-tasks.

## Task to Decompose
**ID:** {task.spec_id}
**Title:** {task.title}
**Description:** {task.description}
**Current Steps:**
{chr(10).join(f"  {i+1}. {s}" for i, s in enumerate(task.steps))}
**Dependencies:** {task.depends_on}
**Priority:** {task.priority}
**Category:** {task.category}

## Why Decomposition is Needed
{error_context}

## Instructions

Analyze this task and break it into 2-5 smaller sub-tasks that:

1. **Are atomic** - Each sub-task should be implementable and testable independently
2. **Have clear boundaries** - Each does one specific thing well
3. **Build on each other** - Dependencies between sub-tasks should be clear
4. **Preserve intent** - Together they should fully implement the original task

## Output Format

Create a JSON file `decomposition_plan.json` with this structure:

```json
{{
  "parent_task_id": "{task.id}",
  "parent_spec_id": "{task.spec_id}",
  "reasoning": "Explanation of why and how you decomposed the task",
  "sub_tasks": [
    {{
      "internal_name": "setup_base",  // Used for internal dependency references
      "title": "Set up basic infrastructure",
      "description": "Set up the basic infrastructure for...",
      "steps": [
        "Step 1...",
        "Step 2..."
      ],
      "internal_deps": [],  // References to other sub-task internal_names
      "priority": "high",
      "category": "{task.category}",
      "expected_outputs": [
        {{"path": "src/module.py", "min_lines": 50, "must_contain": ["class Foo"]}}
      ],
      "verify_script": "cd ... && python -c \\"import module; assert ...\\""
    }},
    {{
      "internal_name": "implement_core",
      "title": "Implement core logic",
      "description": "Implement the core logic for...",
      "steps": [...],
      "internal_deps": ["setup_base"],  // Depends on setup_base
      "priority": "high",
      "category": "{task.category}",
      "expected_outputs": [...],
      "verify_script": "..."
    }}
  ]
}}
```

## Guidelines

- Keep sub-tasks focused - if a sub-task has more than 5 steps, it might need further breakdown
- Put foundational/setup work in early sub-tasks
- User-facing features should come later, depending on infrastructure
- Each sub-task should be testable with a clear pass/fail criteria
- Don't create too many sub-tasks (2-5 is ideal)
- Each sub-task MUST have its own `expected_outputs` and `verify_script`
- Sub-task verify_scripts should test ONLY what that sub-task produces
- An integration task will be auto-generated that runs the parent's original verify_script

**IMPORTANT:** You do NOT need to create an integration task — one will be created
automatically that depends on all sub-tasks and runs the parent's full verification.
Focus on making each sub-task independently testable.

After creating the decomposition plan, write it to `decomposition_plan.json`.
"""


def analyze_task_for_decomposition(task: Task) -> dict:
    """
    Analyze a task to suggest decomposition strategy.

    Args:
        task: Task to analyze

    Returns:
        Analysis with suggested decomposition approach
    """
    steps = task.steps
    description = task.description

    analysis = {
        "should_decompose": False,
        "suggested_split_points": [],
        "complexity_factors": [],
        "suggested_sub_count": 0,
    }

    # Check step count
    if len(steps) > 8:
        analysis["should_decompose"] = True
        analysis["complexity_factors"].append(f"Many steps ({len(steps)})")
        analysis["suggested_sub_count"] = max(2, len(steps) // 4)

    # Look for natural split points in steps
    split_keywords = ["then", "after", "finally", "also", "additionally", "next"]
    for i, step in enumerate(steps):
        step_lower = step.lower()
        for kw in split_keywords:
            if kw in step_lower and i > 0:
                analysis["suggested_split_points"].append(i)
                break

    # Check for multiple concerns in description
    concern_patterns = [
        r"(?:and|,)\s*(?:also|additionally|furthermore)",
        r"both.*and",
        r"as well as",
        r"along with",
    ]
    for pattern in concern_patterns:
        if re.search(pattern, description, re.IGNORECASE):
            analysis["should_decompose"] = True
            analysis["complexity_factors"].append("Multiple concerns in description")
            break

    # Check description length
    if len(description) > 400:
        analysis["should_decompose"] = True
        analysis["complexity_factors"].append("Long description")

    # Suggest decomposition strategy
    if len(steps) >= 6:
        # Group steps into phases
        phase_size = len(steps) // 3
        analysis["suggested_phases"] = [
            {"name": "setup", "steps": steps[:phase_size]},
            {"name": "core", "steps": steps[phase_size:phase_size*2]},
            {"name": "finalize", "steps": steps[phase_size*2:]},
        ]

    return analysis


def validate_decomposition(sub_tasks: list[dict], parent: Task) -> tuple[bool, list[str]]:
    """
    Validate a proposed decomposition.

    Args:
        sub_tasks: Proposed sub-tasks
        parent: Original parent task

    Returns:
        (is_valid, list of issues)
    """
    issues = []

    if not sub_tasks:
        issues.append("No sub-tasks provided")
        return False, issues

    if len(sub_tasks) > 10:
        issues.append(f"Too many sub-tasks ({len(sub_tasks)}), should be 2-5")

    if len(sub_tasks) < 2:
        issues.append("Need at least 2 sub-tasks for decomposition")

    # Check for circular dependencies
    dep_graph: dict[str, list[str]] = {}
    for st in sub_tasks:
        name = st.get("internal_name", "")
        deps = st.get("internal_deps", [])
        dep_graph[name] = deps

    def has_cycle(node: str, visited: set, path: set) -> bool:
        visited.add(node)
        path.add(node)
        for neighbor in dep_graph.get(node, []):
            if neighbor not in visited:
                if has_cycle(neighbor, visited, path):
                    return True
            elif neighbor in path:
                return True
        path.remove(node)
        return False

    for name in dep_graph:
        if has_cycle(name, set(), set()):
            issues.append(f"Circular dependency detected involving {name}")
            break

    # Check that all dependencies reference valid sub-tasks
    valid_names = {st.get("internal_name") for st in sub_tasks}
    for st in sub_tasks:
        for dep in st.get("internal_deps", []):
            if dep not in valid_names and not dep.startswith("F"):
                issues.append(f"Invalid dependency: {dep} not found")

    # Check each sub-task has required fields
    for st in sub_tasks:
        if not st.get("title"):
            issues.append(f"Sub-task {st.get('internal_name', '?')} missing title")
        if not st.get("description"):
            issues.append(f"Sub-task {st.get('internal_name', '?')} missing description")
        if not st.get("steps"):
            issues.append(f"Sub-task {st.get('internal_name', '?')} missing steps")

    return len(issues) == 0, issues


def suggest_decomposition(task: Task) -> list[dict]:
    """
    Automatically suggest a decomposition for a task.

    This is a heuristic-based suggestion that can be refined by the agent.

    Args:
        task: Task to decompose

    Returns:
        List of suggested sub-task specs
    """
    steps = task.steps
    if len(steps) < 4:
        # Too small to decompose, suggest 2 parts
        mid = len(steps) // 2 or 1
        return [
            {
                "internal_name": "foundation",
                "title": f"Foundation for {task.title}",
                "description": f"Set up foundation for: {task.description[:50]}",
                "steps": steps[:mid],
                "internal_deps": [],
                "priority": task.priority,
                "category": task.category,
            },
            {
                "internal_name": "completion",
                "title": f"Complete {task.title}",
                "description": f"Complete implementation: {task.description[:50]}",
                "steps": steps[mid:],
                "internal_deps": ["foundation"],
                "priority": task.priority,
                "category": task.category,
            },
        ]

    # For larger tasks, try to identify logical groupings
    suggestions = []

    # Look for setup/init steps
    setup_steps = []
    core_steps = []
    finish_steps = []

    setup_keywords = ["create", "set up", "initialize", "configure", "define", "add"]
    finish_keywords = ["test", "verify", "validate", "ensure", "check", "complete"]

    for step in steps:
        step_lower = step.lower()
        if any(kw in step_lower for kw in setup_keywords) and len(setup_steps) < 3:
            setup_steps.append(step)
        elif any(kw in step_lower for kw in finish_keywords):
            finish_steps.append(step)
        else:
            core_steps.append(step)

    # Balance the groups
    if not core_steps and setup_steps:
        mid = len(setup_steps) // 2
        core_steps = setup_steps[mid:]
        setup_steps = setup_steps[:mid]

    title_short = task.title[:50]

    if setup_steps:
        suggestions.append({
            "internal_name": "setup",
            "title": f"Set up {title_short}",
            "description": f"Set up infrastructure for {task.description[:50]}",
            "steps": setup_steps,
            "internal_deps": [],
            "priority": task.priority,
            "category": task.category,
        })

    if core_steps:
        suggestions.append({
            "internal_name": "core",
            "title": f"Implement {title_short}",
            "description": f"Implement core functionality for {task.description[:50]}",
            "steps": core_steps,
            "internal_deps": ["setup"] if setup_steps else [],
            "priority": task.priority,
            "category": task.category,
        })

    if finish_steps:
        suggestions.append({
            "internal_name": "finalize",
            "title": f"Finalize {title_short}",
            "description": f"Finalize and verify {task.description[:50]}",
            "steps": finish_steps,
            "internal_deps": ["core"] if core_steps else ["setup"],
            "priority": task.priority,
            "category": task.category,
        })

    return suggestions if suggestions else [
        {
            "internal_name": "part1",
            "title": f"First part of {title_short}",
            "description": f"First part of {task.description[:50]}",
            "steps": steps[:len(steps)//2],
            "internal_deps": [],
            "priority": task.priority,
            "category": task.category,
        },
        {
            "internal_name": "part2",
            "title": f"Second part of {title_short}",
            "description": f"Second part of {task.description[:50]}",
            "steps": steps[len(steps)//2:],
            "internal_deps": ["part1"],
            "priority": task.priority,
            "category": task.category,
        },
    ]
