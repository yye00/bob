#!/usr/bin/env python3
"""Tests for example spec files."""

import yaml
from pathlib import Path

import pytest


class TestExampleSpecs:
    """Test that all example specs are valid."""

    @pytest.fixture
    def examples_dir(self):
        """Get examples directory."""
        return Path(__file__).parent.parent / "examples"

    def test_examples_directory_exists(self, examples_dir):
        """Test that examples directory exists."""
        assert examples_dir.exists()
        assert examples_dir.is_dir()

    def test_simple_webapp_example_exists(self, examples_dir):
        """Test that simple-webapp example exists."""
        webapp_dir = examples_dir / "simple-webapp"
        assert webapp_dir.exists()
        assert (webapp_dir / "spec.yaml").exists()
        assert (webapp_dir / "README.md").exists()

    def test_cli_tool_example_exists(self, examples_dir):
        """Test that cli-tool example exists."""
        cli_dir = examples_dir / "cli-tool"
        assert cli_dir.exists()
        assert (cli_dir / "spec.yaml").exists()
        assert (cli_dir / "README.md").exists()

    def test_research_heavy_example_exists(self, examples_dir):
        """Test that research-heavy example exists."""
        research_dir = examples_dir / "research-heavy"
        assert research_dir.exists()
        assert (research_dir / "spec.yaml").exists()
        assert (research_dir / "README.md").exists()

    def test_parallel_tasks_example_exists(self, examples_dir):
        """Test that parallel-tasks example exists."""
        parallel_dir = examples_dir / "parallel-tasks"
        assert parallel_dir.exists()
        assert (parallel_dir / "spec.yaml").exists()
        assert (parallel_dir / "README.md").exists()

    def test_simple_webapp_spec_valid_yaml(self, examples_dir):
        """Test that simple-webapp spec is valid YAML."""
        spec_file = examples_dir / "simple-webapp" / "spec.yaml"
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        assert isinstance(spec, dict)
        assert "name" in spec
        assert "description" in spec
        assert "tasks" in spec
        assert isinstance(spec["tasks"], list)
        assert len(spec["tasks"]) > 0

    def test_cli_tool_spec_valid_yaml(self, examples_dir):
        """Test that cli-tool spec is valid YAML."""
        spec_file = examples_dir / "cli-tool" / "spec.yaml"
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        assert isinstance(spec, dict)
        assert "name" in spec
        assert spec["name"] == "File Analyzer CLI"
        assert "tasks" in spec
        assert isinstance(spec["tasks"], list)
        assert len(spec["tasks"]) > 0

    def test_research_heavy_spec_valid_yaml(self, examples_dir):
        """Test that research-heavy spec is valid YAML."""
        spec_file = examples_dir / "research-heavy" / "spec.yaml"
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        assert isinstance(spec, dict)
        assert "name" in spec
        assert spec["name"] == "Modern API Gateway"
        assert "tasks" in spec
        assert isinstance(spec["tasks"], list)
        assert len(spec["tasks"]) > 0

    def test_parallel_tasks_spec_valid_yaml(self, examples_dir):
        """Test that parallel-tasks spec is valid YAML."""
        spec_file = examples_dir / "parallel-tasks" / "spec.yaml"
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        assert isinstance(spec, dict)
        assert "name" in spec
        assert spec["name"] == "Microservices Platform"
        assert "tasks" in spec
        assert isinstance(spec["tasks"], list)
        assert len(spec["tasks"]) > 0

    def test_research_heavy_has_research_tasks(self, examples_dir):
        """Test that research-heavy example has tasks with research_required."""
        spec_file = examples_dir / "research-heavy" / "spec.yaml"
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        research_tasks = [
            task for task in spec["tasks"]
            if task.get("research_required", False)
        ]

        assert len(research_tasks) > 0, "Research-heavy example should have research tasks"

        # Check that research tasks have research_queries
        for task in research_tasks:
            assert "research_queries" in task
            assert isinstance(task["research_queries"], list)
            assert len(task["research_queries"]) > 0

    def test_parallel_tasks_has_parallel_structure(self, examples_dir):
        """Test that parallel-tasks example has tasks that can run in parallel."""
        spec_file = examples_dir / "parallel-tasks" / "spec.yaml"
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        # Find tasks that depend on shared-lib
        shared_lib_deps = [
            task for task in spec["tasks"]
            if task.get("depends_on") == ["shared-lib"]
        ]

        # Should have multiple tasks that only depend on shared-lib (can run in parallel)
        assert len(shared_lib_deps) >= 5, "Should have multiple tasks that can run in parallel"

    def test_all_tasks_have_required_fields(self, examples_dir):
        """Test that all tasks in all examples have required fields."""
        required_fields = ["id", "title", "description", "acceptance_criteria", "steps"]

        for example in ["simple-webapp", "cli-tool", "research-heavy", "parallel-tasks"]:
            spec_file = examples_dir / example / "spec.yaml"
            with open(spec_file) as f:
                spec = yaml.safe_load(f)

            for task in spec["tasks"]:
                for field in required_fields:
                    assert field in task, f"{example}: Task {task.get('id', 'unknown')} missing {field}"

    def test_all_task_ids_unique_per_spec(self, examples_dir):
        """Test that task IDs are unique within each spec."""
        for example in ["simple-webapp", "cli-tool", "research-heavy", "parallel-tasks"]:
            spec_file = examples_dir / example / "spec.yaml"
            with open(spec_file) as f:
                spec = yaml.safe_load(f)

            task_ids = [task["id"] for task in spec["tasks"]]
            assert len(task_ids) == len(set(task_ids)), f"{example}: Duplicate task IDs found"

    def test_task_dependencies_exist(self, examples_dir):
        """Test that task dependencies reference existing task IDs."""
        for example in ["simple-webapp", "cli-tool", "research-heavy", "parallel-tasks"]:
            spec_file = examples_dir / example / "spec.yaml"
            with open(spec_file) as f:
                spec = yaml.safe_load(f)

            task_ids = {task["id"] for task in spec["tasks"]}

            for task in spec["tasks"]:
                if "depends_on" in task:
                    for dep in task["depends_on"]:
                        assert dep in task_ids, \
                            f"{example}: Task {task['id']} depends on non-existent task {dep}"

    def test_all_readmes_have_required_sections(self, examples_dir):
        """Test that all READMEs have required sections."""
        required_sections = [
            "What This Example Shows",
            "Running This Example with BOB",
            "Expected Outcome",
            "Learning from This Example"
        ]

        for example in ["simple-webapp", "cli-tool", "research-heavy", "parallel-tasks"]:
            readme_file = examples_dir / example / "README.md"
            with open(readme_file) as f:
                content = f.read()

            for section in required_sections:
                assert section in content, \
                    f"{example}: README missing section '{section}'"

    def test_cli_tool_has_cli_specific_content(self, examples_dir):
        """Test that cli-tool example has CLI-specific tasks."""
        spec_file = examples_dir / "cli-tool" / "spec.yaml"
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        # Should have CLI framework task
        task_titles = [task["title"].lower() for task in spec["tasks"]]
        assert any("cli" in title for title in task_titles)

    def test_parallel_tasks_has_labeled_groups(self, examples_dir):
        """Test that parallel-tasks example has parallel group labels."""
        spec_file = examples_dir / "parallel-tasks" / "spec.yaml"
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        # Find tasks with parallel-group labels
        parallel_labeled = [
            task for task in spec["tasks"]
            if any("parallel-group" in label for label in task.get("labels", []))
        ]

        assert len(parallel_labeled) > 0, "Should have tasks labeled with parallel-group"

    def test_research_queries_format(self, examples_dir):
        """Test that research queries are properly formatted."""
        spec_file = examples_dir / "research-heavy" / "spec.yaml"
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        for task in spec["tasks"]:
            if "research_queries" in task:
                for query in task["research_queries"]:
                    assert isinstance(query, str)
                    assert len(query) > 10, "Research queries should be descriptive"

    def test_acceptance_criteria_not_empty(self, examples_dir):
        """Test that acceptance criteria are not empty."""
        for example in ["simple-webapp", "cli-tool", "research-heavy", "parallel-tasks"]:
            spec_file = examples_dir / example / "spec.yaml"
            with open(spec_file) as f:
                spec = yaml.safe_load(f)

            for task in spec["tasks"]:
                criteria = task.get("acceptance_criteria", [])
                assert isinstance(criteria, list)
                assert len(criteria) > 0, \
                    f"{example}: Task {task['id']} has no acceptance criteria"
                # Each criterion should be a string
                for criterion in criteria:
                    assert isinstance(criterion, str)
                    assert len(criterion) > 5

    def test_steps_not_empty(self, examples_dir):
        """Test that steps are not empty."""
        for example in ["simple-webapp", "cli-tool", "research-heavy", "parallel-tasks"]:
            spec_file = examples_dir / example / "spec.yaml"
            with open(spec_file) as f:
                spec = yaml.safe_load(f)

            for task in spec["tasks"]:
                steps = task.get("steps", [])
                assert isinstance(steps, list)
                assert len(steps) > 0, \
                    f"{example}: Task {task['id']} has no steps"
                # Each step should be a string
                for step in steps:
                    assert isinstance(step, str)
                    assert len(step) > 3
