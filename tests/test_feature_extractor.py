"""Tests for the feature extractor module."""

import pytest
from bob.orchestrator.feature_extractor import (
    extract_spec_metadata,
    _parse_tasks,
)


class TestExtractSpecMetadata:
    """Test spec metadata extraction."""

    def test_basic_spec(self):
        spec = {
            "name": "My App",
            "description": "Build a distributed system.",
            "tasks": [
                {"id": "T1", "title": "Task 1", "description": "Do something"},
            ],
        }
        desc, constraints, env = extract_spec_metadata(spec)
        assert "My App" in desc
        assert "Build a distributed system." in desc
        # Existing tasks should be included as hints
        assert "Task 1" in desc
        assert "reference only" in desc.lower()

    def test_constraints_extraction(self):
        spec = {
            "name": "Test",
            "description": (
                "Build X.\n"
                "CRITICAL REQUIREMENT: Must not use library Y.\n"
                "Policy: Only allowed to use numpy.\n"
                "Do not import tensorflow."
            ),
        }
        desc, constraints, env = extract_spec_metadata(spec)
        assert len(constraints) >= 2
        assert any("must not" in c.lower() for c in constraints)

    def test_empty_spec(self):
        spec = {}
        desc, constraints, env = extract_spec_metadata(spec)
        assert isinstance(desc, str)
        assert isinstance(constraints, list)
        assert isinstance(env, str)

    def test_environment_dict(self):
        spec = {
            "name": "Test",
            "description": "X",
            "environment": {"python": "3.12", "mpi": "openmpi"},
        }
        desc, constraints, env = extract_spec_metadata(spec)
        assert "python" in env
        assert "3.12" in env

    def test_environment_string(self):
        spec = {
            "name": "Test",
            "description": "X",
            "environment": "Python 3.12 with MPI",
        }
        desc, constraints, env = extract_spec_metadata(spec)
        assert "Python 3.12" in env

    def test_no_tasks_still_works(self):
        spec = {
            "name": "App",
            "description": "A complex system.",
        }
        desc, constraints, env = extract_spec_metadata(spec)
        assert "App" in desc
        assert "reference only" not in desc.lower()


class TestParseTasks:
    """Test JSON task parsing from Claude output."""

    def test_clean_json(self):
        output = '{"tasks": [{"id": "T1", "title": "Test"}]}'
        tasks = _parse_tasks(output)
        assert len(tasks) == 1
        assert tasks[0]["id"] == "T1"

    def test_json_in_markdown_fences(self):
        output = '```json\n{"tasks": [{"id": "T1", "title": "Test"}]}\n```'
        tasks = _parse_tasks(output)
        assert len(tasks) == 1

    def test_json_with_commentary(self):
        output = (
            'Here is the task list:\n\n'
            '{"tasks": [{"id": "T1", "title": "Test"}]}\n\n'
            'These tasks cover the core functionality.'
        )
        tasks = _parse_tasks(output)
        assert len(tasks) == 1

    def test_empty_output(self):
        assert _parse_tasks("") == []
        assert _parse_tasks(None) == []

    def test_no_json(self):
        assert _parse_tasks("Just some text without JSON") == []

    def test_multiple_tasks(self):
        output = '{"tasks": [{"id": "T1"}, {"id": "T2"}, {"id": "T3"}]}'
        tasks = _parse_tasks(output)
        assert len(tasks) == 3

    def test_nested_json(self):
        output = '''{
            "tasks": [
                {
                    "id": "T1",
                    "title": "Complex task",
                    "expected_outputs": [
                        {"path": "src/main.py", "min_lines": 100}
                    ]
                }
            ],
            "total_estimated_loc": 500
        }'''
        tasks = _parse_tasks(output)
        assert len(tasks) == 1
        assert tasks[0]["expected_outputs"][0]["path"] == "src/main.py"
