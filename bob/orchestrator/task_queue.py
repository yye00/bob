"""TaskQueue - Dependency-aware task queue for BOB orchestrator.

This module provides a task queue that respects task dependencies and priorities,
ensuring tasks are only executed when all their dependencies are satisfied.
"""

from typing import Optional

from bob.database.manager import DatabaseManager
from bob.models.base import Task, TaskStatus


class TaskQueue:
    """Dependency-aware task queue.

    The TaskQueue manages the order in which tasks are executed, ensuring that:
    1. Tasks are only executed when all dependencies are satisfied
    2. Tasks with higher priority are executed first (within ready tasks)
    3. Blocked and failed dependencies prevent task execution
    4. Deprecated tasks are excluded from execution

    Args:
        db_manager: DatabaseManager instance for querying tasks
        project_id: Project ID to filter tasks (optional)
    """

    def __init__(self, db_manager: DatabaseManager, project_id: Optional[str] = None):
        """Initialize the TaskQueue.

        Args:
            db_manager: DatabaseManager instance
            project_id: Optional project ID to filter tasks
        """
        self.db_manager = db_manager
        self.project_id = project_id

    def get_ready_tasks(self, limit: int = 10) -> list[Task]:
        """Get tasks that are ready to be executed.

        A task is ready if:
        1. Its status is PENDING
        2. All tasks in depends_on are COMPLETED
        3. No tasks in depends_on have FAILED status
        4. It is not DEPRECATED

        Tasks are returned sorted by priority (critical > high > medium > low),
        then by creation order.

        Args:
            limit: Maximum number of tasks to return (default: 10)

        Returns:
            List of ready Task objects, sorted by priority
        """
        # Get all pending tasks for the project
        pending_tasks = self.db_manager.list_tasks(
            project_id=self.project_id,
            status=TaskStatus.PENDING,
            limit=1000,  # Get all pending tasks to check dependencies
        )

        # Build a map of spec_id -> task for quick lookup
        all_tasks = self.db_manager.list_tasks(
            project_id=self.project_id,
            limit=10000,  # Get all tasks to check dependencies
        )
        tasks_by_spec_id = {task.spec_id: task for task in all_tasks}

        # Filter to tasks that are ready (all dependencies met)
        ready_tasks = []
        for task in pending_tasks:
            if self._is_task_ready(task, tasks_by_spec_id):
                ready_tasks.append(task)

        # Sort by priority (already done by list_tasks, but let's be explicit)
        ready_tasks.sort(key=self._priority_sort_key)

        # Return up to limit tasks
        return ready_tasks[:limit]

    def _is_task_ready(self, task: Task, tasks_by_spec_id: dict[str, Task]) -> bool:
        """Check if a task is ready to execute.

        A task is ready if all its dependencies are completed and none have failed.

        Args:
            task: Task to check
            tasks_by_spec_id: Map of spec_id to Task for dependency lookup

        Returns:
            True if task is ready, False otherwise
        """
        # If task has no dependencies, it's ready
        if not task.depends_on:
            return True

        # Check each dependency
        for dep_spec_id in task.depends_on:
            # Find the dependency task
            dep_task = tasks_by_spec_id.get(dep_spec_id)

            # If dependency doesn't exist, task is blocked
            if dep_task is None:
                return False

            # If dependency is not completed, task is not ready
            if dep_task.status != TaskStatus.COMPLETED:
                return False

            # If dependency failed, task is blocked
            if dep_task.status == TaskStatus.FAILED:
                return False

        # All dependencies are completed, task is ready
        return True

    def _priority_sort_key(self, task: Task) -> tuple[int, str]:
        """Generate sort key for priority-based sorting.

        Args:
            task: Task to generate key for

        Returns:
            Tuple of (priority_rank, task_id) for sorting
        """
        priority_map = {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
        }
        priority_rank = priority_map.get(task.priority.lower(), 4)
        return (priority_rank, task.id)

    def get_blocked_tasks(self, limit: int = 10) -> list[tuple[Task, list[str]]]:
        """Get tasks that are blocked by dependencies.

        Returns tasks with PENDING status that cannot proceed because
        their dependencies are not yet completed.

        Args:
            limit: Maximum number of tasks to return (default: 10)

        Returns:
            List of tuples: (blocked_task, [list of blocking spec_ids])
        """
        # Get all pending tasks
        pending_tasks = self.db_manager.list_tasks(
            project_id=self.project_id,
            status=TaskStatus.PENDING,
            limit=1000,
        )

        # Build task map
        all_tasks = self.db_manager.list_tasks(
            project_id=self.project_id,
            limit=10000,
        )
        tasks_by_spec_id = {task.spec_id: task for task in all_tasks}

        # Find blocked tasks and their blockers
        blocked_tasks = []
        for task in pending_tasks:
            if not task.depends_on:
                continue

            blocking_deps = []
            for dep_spec_id in task.depends_on:
                dep_task = tasks_by_spec_id.get(dep_spec_id)

                # Dependency doesn't exist or isn't completed
                if dep_task is None or dep_task.status != TaskStatus.COMPLETED:
                    blocking_deps.append(dep_spec_id)

            if blocking_deps:
                blocked_tasks.append((task, blocking_deps))

        # Sort by priority
        blocked_tasks.sort(key=lambda x: self._priority_sort_key(x[0]))

        return blocked_tasks[:limit]

    def get_task_dependency_chain(self, task: Task) -> list[Task]:
        """Get the full dependency chain for a task.

        Returns all tasks that this task depends on, recursively.

        Args:
            task: Task to get dependencies for

        Returns:
            List of Task objects in dependency order (deepest first)
        """
        # Build task map
        all_tasks = self.db_manager.list_tasks(
            project_id=self.project_id,
            limit=10000,
        )
        tasks_by_spec_id = {task.spec_id: task for task in all_tasks}

        # Recursively collect dependencies
        visited = set()
        dependency_chain = []

        def collect_deps(current_task: Task) -> None:
            """Recursively collect dependencies."""
            if current_task.spec_id in visited:
                return

            visited.add(current_task.spec_id)

            # Process dependencies first (depth-first)
            for dep_spec_id in current_task.depends_on:
                dep_task = tasks_by_spec_id.get(dep_spec_id)
                if dep_task:
                    collect_deps(dep_task)

            # Add current task
            dependency_chain.append(current_task)

        collect_deps(task)

        # Remove the task itself from the chain (it's the last item)
        if dependency_chain and dependency_chain[-1].spec_id == task.spec_id:
            dependency_chain.pop()

        return dependency_chain

    def get_next_task(self) -> Optional[Task]:
        """Get the next single task to execute.

        Convenience method that returns the highest-priority ready task.

        Returns:
            Next Task to execute, or None if no tasks are ready
        """
        ready_tasks = self.get_ready_tasks(limit=1)
        return ready_tasks[0] if ready_tasks else None
