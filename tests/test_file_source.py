"""Tests for FileSpecSource."""

import json
from pathlib import Path

import pytest
import yaml

from bob.spec_sources import FileSpecSource, SpecSourceError, get_registry


# Sample spec data
SAMPLE_SPEC = {
    "spec_version": 1,
    "tasks": [
        {
            "id": "F001",
            "title": "Task 1",
            "description": "First task",
            "acceptance_criteria": ["Criterion 1", "Criterion 2"],
            "steps": ["Step 1", "Step 2"],
            "depends_on": [],
            "priority": "high",
            "category": "functional",
            "labels": ["backend"],
            "research_required": False,
            "research_queries": [],
            "deprecated": False,
            "spec_version": 1,
        },
        {
            "id": "F002",
            "title": "Task 2",
            "description": "Second task with research needed",
            "steps": ["Investigate the best approach"],
            "depends_on": ["F001"],
            "priority": "medium",
            "category": "functional",
            "research_required": False,  # Will be auto-detected
            "deprecated": False,
        },
    ],
}


class TestFileSpecSourceInit:
    """Tests for FileSpecSource initialization."""

    def test_init_yaml_file(self, tmp_path):
        """Test initializing with a YAML file."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")

        assert source.source_uri == f"file://{spec_file}"
        assert source.file_path == spec_file
        assert source.format == "yaml"

    def test_init_yml_extension(self, tmp_path):
        """Test .yml extension is recognized as YAML."""
        spec_file = tmp_path / "spec.yml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")
        assert source.format == "yaml"

    def test_init_json_file(self, tmp_path):
        """Test initializing with a JSON file."""
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")

        assert source.file_path == spec_file
        assert source.format == "json"

    def test_init_invalid_uri_scheme(self, tmp_path):
        """Test invalid URI scheme raises error."""
        with pytest.raises(SpecSourceError, match="must start with 'file://'"):
            FileSpecSource("http://example.com/spec.yaml")

    def test_init_file_not_found(self):
        """Test non-existent file raises error."""
        with pytest.raises(SpecSourceError, match="not found"):
            FileSpecSource("file:///nonexistent/spec.yaml")

    def test_init_unsupported_format(self, tmp_path):
        """Test unsupported file format raises error."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("data")

        with pytest.raises(SpecSourceError, match="Unsupported file format"):
            FileSpecSource(f"file://{spec_file}")


class TestFileSpecSourceFetch:
    """Tests for fetch_tasks()."""

    @pytest.mark.asyncio
    async def test_fetch_tasks_yaml(self, tmp_path):
        """Test fetching tasks from YAML file."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert len(tasks) == 2
        assert tasks[0].spec_id == "F001"
        assert tasks[0].title == "Task 1"
        assert tasks[0].description == "First task"
        assert tasks[0].acceptance_criteria == ["Criterion 1", "Criterion 2"]
        assert tasks[0].steps == ["Step 1", "Step 2"]
        assert tasks[0].depends_on == []
        assert tasks[0].priority == "high"
        assert tasks[0].category == "functional"
        assert tasks[0].labels == ["backend"]
        assert tasks[0].research_required is False
        assert tasks[0].deprecated is False
        assert tasks[0].spec_version == 1

    @pytest.mark.asyncio
    async def test_fetch_tasks_json(self, tmp_path):
        """Test fetching tasks from JSON file."""
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert len(tasks) == 2
        assert tasks[0].spec_id == "F001"
        assert tasks[1].spec_id == "F002"

    @pytest.mark.asyncio
    async def test_fetch_tasks_with_defaults(self, tmp_path):
        """Test tasks with minimal fields get defaults."""
        spec = {
            "tasks": [
                {
                    "id": "F001",
                    "title": "Minimal Task",
                    "description": "Description only",
                }
            ]
        }
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(spec))

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert len(tasks) == 1
        task = tasks[0]
        assert task.spec_id == "F001"
        assert task.acceptance_criteria == []
        assert task.steps == []
        assert task.depends_on == []
        assert task.priority == "medium"
        assert task.category == "functional"
        assert task.labels == []
        assert task.research_required is False
        assert task.research_queries == []
        assert task.deprecated is False

    @pytest.mark.asyncio
    async def test_fetch_tasks_missing_required_field(self, tmp_path):
        """Test missing required fields raises error."""
        spec = {
            "tasks": [
                {
                    "id": "F001",
                    "title": "Task without description",
                    # Missing description
                }
            ]
        }
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(spec))

        source = FileSpecSource(f"file://{spec_file}")

        with pytest.raises(SpecSourceError, match="missing required fields"):
            await source.fetch_tasks()

    @pytest.mark.asyncio
    async def test_fetch_tasks_invalid_yaml(self, tmp_path):
        """Test invalid YAML raises error."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("invalid: yaml: [unclosed")

        source = FileSpecSource(f"file://{spec_file}")

        with pytest.raises(SpecSourceError, match="YAML parsing error"):
            await source.fetch_tasks()

    @pytest.mark.asyncio
    async def test_fetch_tasks_invalid_json(self, tmp_path):
        """Test invalid JSON raises error."""
        spec_file = tmp_path / "spec.json"
        spec_file.write_text("{invalid json")

        source = FileSpecSource(f"file://{spec_file}")

        with pytest.raises(SpecSourceError, match="JSON parsing error"):
            await source.fetch_tasks()

    @pytest.mark.asyncio
    async def test_fetch_tasks_not_dict(self, tmp_path):
        """Test non-dict root raises error."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("- item1\n- item2")

        source = FileSpecSource(f"file://{spec_file}")

        with pytest.raises(SpecSourceError, match="expected dict"):
            await source.fetch_tasks()

    @pytest.mark.asyncio
    async def test_fetch_tasks_invalid_tasks_field(self, tmp_path):
        """Test non-list tasks field raises error."""
        spec = {"tasks": "not a list"}
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(spec))

        source = FileSpecSource(f"file://{spec_file}")

        with pytest.raises(SpecSourceError, match="expected list"):
            await source.fetch_tasks()

    @pytest.mark.asyncio
    async def test_fetch_tasks_updates_tracking(self, tmp_path):
        """Test that fetch_tasks updates last_sync and version."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")

        assert source.last_sync is None
        assert source.last_spec_version == 0

        await source.fetch_tasks()

        assert source.last_sync is not None
        assert source.last_spec_version == 1


class TestResearchDetection:
    """Tests for automatic research requirement detection."""

    @pytest.mark.asyncio
    async def test_detect_research_from_keyword_investigate(self, tmp_path):
        """Test 'investigate' keyword triggers research_required."""
        spec = {
            "tasks": [
                {
                    "id": "F001",
                    "title": "Task",
                    "description": "Investigate the best approach",
                }
            ]
        }
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(spec))

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert tasks[0].research_required is True

    @pytest.mark.asyncio
    async def test_detect_research_from_keyword_explore(self, tmp_path):
        """Test 'explore' keyword triggers research_required."""
        spec = {
            "tasks": [
                {
                    "id": "F001",
                    "title": "Explore options",
                    "description": "Task description",
                }
            ]
        }
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(spec))

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert tasks[0].research_required is True

    @pytest.mark.asyncio
    async def test_detect_research_from_steps(self, tmp_path):
        """Test research detection from steps."""
        spec = {
            "tasks": [
                {
                    "id": "F001",
                    "title": "Task",
                    "description": "Description",
                    "steps": ["Look into the best solution"],
                }
            ]
        }
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(spec))

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert tasks[0].research_required is True

    @pytest.mark.asyncio
    async def test_explicit_research_not_overridden(self, tmp_path):
        """Test explicit research_required is not overridden."""
        spec = {
            "tasks": [
                {
                    "id": "F001",
                    "title": "Task",
                    "description": "Simple task, no research",
                    "research_required": True,  # Explicitly set
                }
            ]
        }
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(spec))

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert tasks[0].research_required is True

    @pytest.mark.asyncio
    async def test_no_research_when_not_needed(self, tmp_path):
        """Test research_required stays false when not needed."""
        spec = {
            "tasks": [
                {
                    "id": "F001",
                    "title": "Implement feature",
                    "description": "Add button to UI",
                }
            ]
        }
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(spec))

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert tasks[0].research_required is False


class TestFileSpecSourceSync:
    """Tests for sync()."""

    @pytest.mark.asyncio
    async def test_sync_no_changes(self, tmp_path):
        """Test sync with no file changes."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")

        # Initial fetch
        await source.fetch_tasks()

        # Sync with known tasks
        result = await source.sync({"F001": 1, "F002": 1})

        assert result.has_changes is False
        assert len(result.added) == 0
        assert len(result.modified) == 0
        assert len(result.removed) == 0

    @pytest.mark.asyncio
    async def test_sync_added_tasks(self, tmp_path):
        """Test sync detects added tasks."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")

        # Sync with partial known tasks
        result = await source.sync({"F001": 1})

        assert result.has_changes is True
        assert len(result.added) == 1
        assert result.added[0].spec_id == "F002"
        assert len(result.modified) == 0
        assert len(result.removed) == 0

    @pytest.mark.asyncio
    async def test_sync_removed_tasks(self, tmp_path):
        """Test sync detects removed tasks."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")

        # Sync with extra known tasks
        result = await source.sync({"F001": 1, "F002": 1, "F003": 1})

        assert result.has_changes is True
        assert len(result.added) == 0
        assert len(result.modified) == 0
        assert len(result.removed) == 1
        assert "F003" in result.removed

    @pytest.mark.asyncio
    async def test_sync_modified_tasks(self, tmp_path):
        """Test sync detects modified tasks."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")

        # Sync with old version
        result = await source.sync({"F001": 0, "F002": 0})

        assert result.has_changes is True
        assert len(result.added) == 0
        assert len(result.modified) == 2
        assert result.modified[0].spec_id in ["F001", "F002"]
        assert len(result.removed) == 0

    @pytest.mark.asyncio
    async def test_sync_file_modified(self, tmp_path):
        """Test sync detects file modifications."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")

        # Initial fetch
        await source.fetch_tasks()

        # Modify file
        modified_spec = SAMPLE_SPEC.copy()
        modified_spec["spec_version"] = 2
        spec_file.write_text(yaml.dump(modified_spec))

        # Sync should detect file change
        result = await source.sync({"F001": 1, "F002": 1})

        # Even with same tasks, file change triggers recheck
        assert source.last_spec_version == 2

    @pytest.mark.asyncio
    async def test_sync_error_handling(self, tmp_path):
        """Test sync handles errors gracefully."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")
        await source.fetch_tasks()

        # Corrupt file
        spec_file.write_text("invalid: yaml: [")

        result = await source.sync({"F001": 1})

        assert len(result.errors) > 0
        assert "parsing error" in result.errors[0].lower()


class TestFileSpecSourceMarkCompleted:
    """Tests for mark_completed()."""

    @pytest.mark.asyncio
    async def test_mark_completed_not_supported(self, tmp_path):
        """Test mark_completed returns False (not supported)."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")

        result = await source.mark_completed("F001")
        assert result is False


class TestFileSpecSourceRegistry:
    """Tests for FileSpecSource registration."""

    def test_file_source_auto_registered(self):
        """Test FileSpecSource is auto-registered."""
        registry = get_registry()

        assert registry.is_registered("file")
        assert registry.get("file") == FileSpecSource

    def test_create_file_source_from_registry(self, tmp_path):
        """Test creating FileSpecSource via registry."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        registry = get_registry()
        source = registry.create(f"file://{spec_file}")

        assert isinstance(source, FileSpecSource)
        assert source.file_path == spec_file


class TestFileSpecSourceMetadata:
    """Tests for task metadata."""

    @pytest.mark.asyncio
    async def test_task_includes_source_metadata(self, tmp_path):
        """Test tasks include source file metadata."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(SAMPLE_SPEC))

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        task = tasks[0]
        assert "source_file" in task.metadata
        assert task.metadata["source_file"] == str(spec_file)
        assert task.metadata["format"] == "yaml"


class TestMarkdownFormat:
    """Tests for Markdown format support."""

    def test_init_markdown_file(self, tmp_path):
        """Test initializing with a .md file."""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("## F001: Test Task\n\nDescription here.")

        source = FileSpecSource(f"file://{spec_file}")

        assert source.file_path == spec_file
        assert source.format == "markdown"

    def test_init_markdown_extension(self, tmp_path):
        """Test .markdown extension is recognized."""
        spec_file = tmp_path / "spec.markdown"
        spec_file.write_text("## F001: Test Task\n\nDescription here.")

        source = FileSpecSource(f"file://{spec_file}")
        assert source.format == "markdown"

    @pytest.mark.asyncio
    async def test_fetch_tasks_markdown_basic(self, tmp_path):
        """Test fetching tasks from basic Markdown file."""
        markdown_content = """
## F001: First Task

This is the task description.

### Acceptance Criteria
- Must work correctly
- Must be tested

### Steps
1. Implement feature
2. Write tests
3. Deploy

## F002: Second Task [priority:high] [category:backend]

Another task description.
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert len(tasks) == 2

        # Check first task
        assert tasks[0].spec_id == "F001"
        assert tasks[0].title == "First Task"
        assert tasks[0].description == "This is the task description."
        assert tasks[0].acceptance_criteria == ["Must work correctly", "Must be tested"]
        assert tasks[0].steps == ["Implement feature", "Write tests", "Deploy"]
        assert tasks[0].priority == "medium"  # Default
        assert tasks[0].category == "functional"  # Default

        # Check second task
        assert tasks[1].spec_id == "F002"
        assert tasks[1].title == "Second Task"
        assert tasks[1].description == "Another task description."
        assert tasks[1].priority == "high"
        assert tasks[1].category == "backend"

    @pytest.mark.asyncio
    async def test_markdown_metadata_extraction(self, tmp_path):
        """Test extraction of metadata from brackets."""
        markdown_content = """
## F001: Task Title [priority:critical] [category:infrastructure] [depends:F000,F002] [labels:mvp,auth]

Task description.
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        task = tasks[0]
        assert task.priority == "critical"
        assert task.category == "infrastructure"
        assert task.depends_on == ["F000", "F002"]
        assert task.labels == ["mvp", "auth"]

    @pytest.mark.asyncio
    async def test_markdown_boolean_metadata(self, tmp_path):
        """Test boolean metadata extraction."""
        markdown_content = """
## F001: Deprecated Task [deprecated:true]

Task description.

## F002: Research Task [research_required:yes]

Another task.
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert tasks[0].deprecated is True
        assert tasks[1].research_required is True

    @pytest.mark.asyncio
    async def test_markdown_bulleted_list(self, tmp_path):
        """Test parsing bulleted lists (- and *)."""
        markdown_content = """
## F001: Test Task

Description here.

### Acceptance Criteria
- Criterion with dash
* Criterion with star
- Another criterion

### Steps
* Step with star
- Step with dash
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        task = tasks[0]
        assert len(task.acceptance_criteria) == 3
        assert task.acceptance_criteria[0] == "Criterion with dash"
        assert task.acceptance_criteria[1] == "Criterion with star"
        assert task.acceptance_criteria[2] == "Another criterion"

        assert len(task.steps) == 2
        assert task.steps[0] == "Step with star"
        assert task.steps[1] == "Step with dash"

    @pytest.mark.asyncio
    async def test_markdown_numbered_list(self, tmp_path):
        """Test parsing numbered lists."""
        markdown_content = """
## F001: Test Task

Description here.

### Steps
1. First step
2. Second step
3. Third step
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        task = tasks[0]
        assert len(task.steps) == 3
        assert task.steps[0] == "First step"
        assert task.steps[1] == "Second step"
        assert task.steps[2] == "Third step"

    @pytest.mark.asyncio
    async def test_markdown_minimal_task(self, tmp_path):
        """Test minimal markdown task (just header and description)."""
        markdown_content = """
## F001: Minimal Task

Just a description, no criteria or steps.
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        task = tasks[0]
        assert task.spec_id == "F001"
        assert task.title == "Minimal Task"
        assert task.description == "Just a description, no criteria or steps."
        assert task.acceptance_criteria == []
        assert task.steps == []
        assert task.priority == "medium"
        assert task.category == "functional"

    @pytest.mark.asyncio
    async def test_markdown_multiple_sections(self, tmp_path):
        """Test tasks with various section titles."""
        markdown_content = """
## F001: Test Task

Description here.

### Acceptance Criteria
- Criterion 1

### Implementation Steps
1. Step 1
2. Step 2
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        task = tasks[0]
        assert len(task.acceptance_criteria) == 1
        assert len(task.steps) == 2

    @pytest.mark.asyncio
    async def test_markdown_no_tasks(self, tmp_path):
        """Test markdown file with no tasks."""
        markdown_content = """
# Project Title

This is a markdown file without task headers.
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_markdown_multiline_description(self, tmp_path):
        """Test task with multiline description."""
        markdown_content = """
## F001: Test Task

This is a multiline description.
It has multiple paragraphs.

And more content here.

### Steps
1. Do something
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        task = tasks[0]
        expected_desc = "This is a multiline description.\nIt has multiple paragraphs.\n\nAnd more content here."
        assert task.description == expected_desc

    @pytest.mark.asyncio
    async def test_markdown_sync_detects_changes(self, tmp_path):
        """Test sync with markdown file changes."""
        markdown_content = """
## F001: Task One

Description.
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        await source.fetch_tasks()

        # Modify file
        new_content = """
## F001: Task One

Description.

## F002: Task Two

Another task.
"""
        spec_file.write_text(new_content)

        result = await source.sync({"F001": 1})

        assert result.has_changes is True
        assert len(result.added) == 1
        assert result.added[0].spec_id == "F002"

    @pytest.mark.asyncio
    async def test_markdown_metadata_format(self, tmp_path):
        """Test metadata is stored correctly."""
        markdown_content = """
## F001: Test Task

Description.
"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(markdown_content)

        source = FileSpecSource(f"file://{spec_file}")
        tasks = await source.fetch_tasks()

        task = tasks[0]
        assert task.metadata["format"] == "markdown"
        assert task.metadata["source_file"] == str(spec_file)
