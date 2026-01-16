"""File-based spec source implementation.

Supports YAML and JSON files containing task specifications.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from bob.spec_sources.base import (
    SpecSource,
    SpecSourceError,
    SyncResult,
    TaskSpec,
)


class FileSpecSource(SpecSource):
    """Spec source that reads from local YAML or JSON files.

    Supports both YAML and JSON formats. The file should contain a list
    of task specifications with the following structure:

    ```yaml
    spec_version: 1
    tasks:
      - id: F001
        title: Feature Title
        description: Feature description
        acceptance_criteria:
          - Criterion 1
          - Criterion 2
        steps:
          - Step 1
          - Step 2
        depends_on:
          - F000
        priority: high
        category: functional
        labels:
          - tag1
          - tag2
        research_required: false
        research_queries: []
        deprecated: false
    ```
    """

    def __init__(self, source_uri: str, config: Optional[dict[str, Any]] = None):
        """Initialize FileSpecSource.

        Args:
            source_uri: URI in format "file://path/to/spec.yaml"
            config: Optional configuration dict

        Raises:
            SpecSourceError: If URI is invalid or file doesn't exist
        """
        super().__init__(source_uri, config)

        # Extract file path from URI
        if not source_uri.startswith("file://"):
            raise SpecSourceError(
                f"Invalid file URI '{source_uri}': must start with 'file://'"
            )

        self.file_path = Path(source_uri.replace("file://", ""))

        # Validate file exists
        if not self.file_path.exists():
            raise SpecSourceError(
                f"Spec file not found: {self.file_path}"
            )

        # Determine format from extension
        suffix = self.file_path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            self.format = "yaml"
        elif suffix == ".json":
            self.format = "json"
        else:
            raise SpecSourceError(
                f"Unsupported file format '{suffix}': use .yaml, .yml, or .json"
            )

        # Cache for file hash (for change detection)
        self._last_file_hash: Optional[str] = None

    def _compute_file_hash(self) -> str:
        """Compute SHA256 hash of the file contents.

        Returns:
            Hex string of the file hash.
        """
        with open(self.file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def _load_spec_data(self) -> dict[str, Any]:
        """Load and parse the spec file.

        Returns:
            Parsed spec data dict.

        Raises:
            SpecSourceError: If file cannot be parsed.
        """
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                if self.format == "yaml":
                    data = yaml.safe_load(f)
                else:  # json
                    data = json.load(f)

            if not isinstance(data, dict):
                raise SpecSourceError(
                    f"Invalid spec format: expected dict, got {type(data).__name__}"
                )

            return data

        except yaml.YAMLError as e:
            raise SpecSourceError(f"YAML parsing error: {e}")
        except json.JSONDecodeError as e:
            raise SpecSourceError(f"JSON parsing error: {e}")
        except Exception as e:
            raise SpecSourceError(f"Error loading spec file: {e}")

    def _parse_task(self, task_data: dict[str, Any]) -> TaskSpec:
        """Parse a task dict into a TaskSpec.

        Args:
            task_data: Dict containing task fields

        Returns:
            TaskSpec instance

        Raises:
            SpecSourceError: If required fields are missing
        """
        # Required fields
        required = ["id", "title", "description"]
        missing = [field for field in required if field not in task_data]
        if missing:
            raise SpecSourceError(
                f"Task missing required fields: {', '.join(missing)}"
            )

        # Extract all fields with defaults
        spec_id = task_data["id"]
        title = task_data["title"]
        description = task_data["description"]

        # Optional fields with defaults
        acceptance_criteria = task_data.get("acceptance_criteria", [])
        steps = task_data.get("steps", [])
        depends_on = task_data.get("depends_on", [])
        priority = task_data.get("priority", "medium")
        category = task_data.get("category", "functional")
        labels = task_data.get("labels", [])
        research_required = task_data.get("research_required", False)
        research_queries = task_data.get("research_queries", [])
        deprecated = task_data.get("deprecated", False)
        spec_version = task_data.get("spec_version", 1)

        # Auto-detect research requirements from description/steps
        if not research_required:
            research_required = self._detect_research_needed(
                title, description, steps
            )

        # Store original task data in metadata
        metadata = {
            "source_file": str(self.file_path),
            "format": self.format,
        }

        return TaskSpec(
            spec_id=spec_id,
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            steps=steps,
            depends_on=depends_on,
            priority=priority,
            category=category,
            labels=labels,
            research_required=research_required,
            research_queries=research_queries,
            metadata=metadata,
            spec_version=spec_version,
            deprecated=deprecated,
        )

    def _detect_research_needed(
        self, title: str, description: str, steps: list[str]
    ) -> bool:
        """Detect if a task requires research based on keywords.

        Args:
            title: Task title
            description: Task description
            steps: List of steps

        Returns:
            True if research keywords are found
        """
        research_keywords = [
            "requires research",
            "needs research",
            "research needed",
            "investigate",
            "explore",
            "find out",
            "look into",
            "determine how to",
        ]

        # Combine all text and lowercase
        all_text = " ".join([title, description] + steps).lower()

        # Check for any keyword
        return any(keyword in all_text for keyword in research_keywords)

    async def fetch_tasks(self) -> list[TaskSpec]:
        """Fetch all tasks from the spec file.

        Returns:
            List of TaskSpec objects.

        Raises:
            SpecSourceError: If file cannot be loaded or parsed.
        """
        data = self._load_spec_data()

        # Get tasks list
        tasks_data = data.get("tasks", [])
        if not isinstance(tasks_data, list):
            raise SpecSourceError(
                f"Invalid 'tasks' field: expected list, got {type(tasks_data).__name__}"
            )

        # Parse each task
        tasks = []
        for i, task_data in enumerate(tasks_data):
            if not isinstance(task_data, dict):
                raise SpecSourceError(
                    f"Task {i} is not a dict: {type(task_data).__name__}"
                )
            try:
                task = self._parse_task(task_data)
                tasks.append(task)
            except SpecSourceError as e:
                raise SpecSourceError(f"Error parsing task {i}: {e}")

        # Update tracking
        self._last_file_hash = self._compute_file_hash()
        self._last_sync = datetime.now()

        # Get spec version
        self._last_spec_version = data.get("spec_version", 1)

        return tasks

    async def sync(self, known_tasks: dict[str, int]) -> SyncResult:
        """Sync tasks, detecting changes via file hash.

        Args:
            known_tasks: Dict mapping spec_id to spec_version

        Returns:
            SyncResult with changes detected

        Raises:
            SpecSourceError: If file cannot be loaded
        """
        result = SyncResult()

        # Check if file has changed
        current_hash = self._compute_file_hash()

        if self._last_file_hash and current_hash == self._last_file_hash:
            # No file changes, no task changes
            result.spec_version = self._last_spec_version
            return result

        # File changed, need to check tasks
        try:
            current_tasks = await self.fetch_tasks()
        except SpecSourceError as e:
            result.errors.append(str(e))
            return result

        # Build current task map
        current_map = {task.spec_id: task for task in current_tasks}
        current_ids = set(current_map.keys())
        known_ids = set(known_tasks.keys())

        # Added tasks (in current but not in known)
        added_ids = current_ids - known_ids
        result.added = [current_map[tid] for tid in added_ids]

        # Removed tasks (in known but not in current)
        result.removed = list(known_ids - current_ids)

        # Modified tasks (in both but version changed)
        for tid in current_ids & known_ids:
            task = current_map[tid]
            if task.spec_version != known_tasks.get(tid, 0):
                result.modified.append(task)

        # Update tracking
        result.spec_version = self._last_spec_version
        self._last_sync = datetime.now()

        return result

    async def mark_completed(
        self, spec_id: str, metadata: Optional[dict[str, Any]] = None
    ) -> bool:
        """Mark task as completed.

        Note: FileSpecSource does not support marking tasks complete
        in the file itself (would require rewriting the file).
        This method always returns False.

        Args:
            spec_id: The task spec ID
            metadata: Optional completion metadata

        Returns:
            False (not supported)
        """
        return False
