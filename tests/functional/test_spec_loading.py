"""Functional tests for spec file loading."""
import pytest
from pathlib import Path
from bob.spec_sources.file_source import FileSpecSource


class TestSpecLoadingFunctional:
    """Test spec file loading works correctly."""

    @pytest.fixture
    def spec_file(self, tmp_path):
        """Create a test spec file."""
        spec = tmp_path / "bob_spec.yaml"
        spec.write_text("""
spec_version: 1
project:
  name: test-project
  description: A test project
  tech_stack: Python

tasks:
  - id: F001
    title: First Task
    description: The first task
    priority: high
    
  - id: F002
    title: Second Task
    description: The second task
    depends_on:
      - F001
    priority: medium
""")
        return spec

    def test_load_spec_file(self, spec_file):
        """Test loading a spec file returns correct data."""
        source = FileSpecSource(f"file://{spec_file}")
        # Use _load_spec_data for synchronous loading
        spec = source._load_spec_data()
        
        assert spec is not None
        # The spec should have tasks
        assert "tasks" in spec

    def test_spec_tasks_have_required_fields(self, spec_file):
        """Test loaded tasks have all required fields."""
        source = FileSpecSource(f"file://{spec_file}")
        spec = source._load_spec_data()
        
        tasks = spec.get("tasks", [])
        assert len(tasks) == 2
        for task in tasks:
            assert "id" in task
            assert "title" in task
            
    def test_spec_dependencies_are_valid(self, spec_file):
        """Test task dependencies reference valid task IDs."""
        source = FileSpecSource(f"file://{spec_file}")
        spec = source._load_spec_data()
        
        tasks = spec.get("tasks", [])
        task_ids = {t["id"] for t in tasks}
        
        for task in tasks:
            if "depends_on" in task:
                for dep in task["depends_on"]:
                    assert dep in task_ids, f"Invalid dependency {dep} in task {task['id']}"
