#!/usr/bin/env python3
"""Tests for the template engine."""

import tempfile
from pathlib import Path

import pytest
from jinja2 import TemplateNotFound

from bob.prompts.template_engine import TemplateEngine, create_template_engine


class TestTemplateEngineInit:
    """Test TemplateEngine initialization."""

    def test_init_with_default_directory(self):
        """Test initialization with default template directory."""
        engine = TemplateEngine()
        assert engine.template_dir.exists()
        assert engine.template_dir.name == "prompts"
        assert engine.env is not None

    def test_init_with_custom_directory(self, tmp_path):
        """Test initialization with custom template directory."""
        custom_dir = tmp_path / "custom_templates"
        custom_dir.mkdir()

        engine = TemplateEngine(template_dir=custom_dir)
        assert engine.template_dir == custom_dir
        assert engine.env is not None

    def test_init_with_nonexistent_directory(self, tmp_path):
        """Test initialization with nonexistent directory."""
        nonexistent_dir = tmp_path / "nonexistent"
        engine = TemplateEngine(template_dir=nonexistent_dir)
        # Should create engine even if directory doesn't exist
        assert engine.template_dir == nonexistent_dir


class TestRenderTemplate:
    """Test template rendering from files."""

    @pytest.fixture
    def engine_with_templates(self, tmp_path):
        """Create engine with test templates."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()

        # Create test template
        simple_template = template_dir / "simple.md"
        simple_template.write_text("Hello {{ name }}!")

        # Create project template
        project_template = template_dir / "project.md"
        project_template.write_text(
            "Project: {{ project.name }}\n"
            "Tech: {{ project.tech_stack }}"
        )

        # Create task template
        task_template = template_dir / "task.md"
        task_template.write_text(
            "Task: {{ task.title }}\n"
            "Priority: {{ task.priority }}"
        )

        return TemplateEngine(template_dir=template_dir)

    def test_render_simple_template(self, engine_with_templates):
        """Test rendering a simple template."""
        result = engine_with_templates.render_template(
            "simple.md",
            {"name": "World"}
        )
        assert result == "Hello World!"

    def test_render_project_template(self, engine_with_templates):
        """Test rendering template with project context."""
        context = {
            "project": {
                "name": "MyProject",
                "tech_stack": "Python"
            }
        }
        result = engine_with_templates.render_template("project.md", context)
        assert "Project: MyProject" in result
        assert "Tech: Python" in result

    def test_render_task_template(self, engine_with_templates):
        """Test rendering template with task context."""
        context = {
            "task": {
                "title": "Implement feature",
                "priority": "high"
            }
        }
        result = engine_with_templates.render_template("task.md", context)
        assert "Task: Implement feature" in result
        assert "Priority: high" in result

    def test_render_nonexistent_template(self, engine_with_templates):
        """Test rendering nonexistent template raises error."""
        with pytest.raises(TemplateNotFound):
            engine_with_templates.render_template("nonexistent.md", {})

    def test_render_with_missing_variables(self, engine_with_templates):
        """Test rendering with missing variables."""
        # Jinja2 silently renders missing variables as empty strings
        result = engine_with_templates.render_template("simple.md", {})
        assert result == "Hello !"


class TestRenderString:
    """Test rendering template strings."""

    @pytest.fixture
    def engine(self):
        """Create basic engine."""
        return TemplateEngine()

    def test_render_simple_string(self, engine):
        """Test rendering a simple string template."""
        result = engine.render_string("Hello {{ name }}!", {"name": "World"})
        assert result == "Hello World!"

    def test_render_string_with_project_context(self, engine):
        """Test rendering string with project context."""
        template = "{{ project.name }} uses {{ project.tech_stack }}"
        context = {
            "project": {
                "name": "MyApp",
                "tech_stack": "Python"
            }
        }
        result = engine.render_string(template, context)
        assert result == "MyApp uses Python"

    def test_render_string_with_conditionals(self, engine):
        """Test rendering string with Jinja2 conditionals."""
        template = (
            "{% if project.description %}"
            "Description: {{ project.description }}"
            "{% else %}"
            "No description"
            "{% endif %}"
        )

        # With description
        context = {"project": {"description": "A test project"}}
        result = engine.render_string(template, context)
        assert "Description: A test project" in result

        # Without description
        context = {"project": {}}
        result = engine.render_string(template, context)
        assert "No description" in result

    def test_render_string_with_loops(self, engine):
        """Test rendering string with Jinja2 loops."""
        template = (
            "{% for item in items %}"
            "- {{ item }}\n"
            "{% endfor %}"
        )
        context = {"items": ["one", "two", "three"]}
        result = engine.render_string(template, context)
        assert "- one\n- two\n- three\n" == result

    def test_render_string_with_filters(self, engine):
        """Test rendering string with Jinja2 filters."""
        template = "{{ name | upper }}"
        result = engine.render_string(template, {"name": "hello"})
        assert result == "HELLO"


class TestListTemplates:
    """Test listing available templates."""

    @pytest.fixture
    def engine_with_multiple_templates(self, tmp_path):
        """Create engine with multiple templates."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()

        # Create various templates
        (template_dir / "coding_prompt.md").write_text("Coding template")
        (template_dir / "research_prompt.md").write_text("Research template")
        (template_dir / "diagnosis_prompt.md").write_text("Diagnosis template")
        (template_dir / "readme.txt").write_text("Not a template")

        return TemplateEngine(template_dir=template_dir)

    def test_list_templates_default_extension(self, engine_with_multiple_templates):
        """Test listing templates with default .md extension."""
        templates = engine_with_multiple_templates.list_templates()
        assert len(templates) == 3
        assert "coding_prompt.md" in templates
        assert "research_prompt.md" in templates
        assert "diagnosis_prompt.md" in templates
        assert "readme.txt" not in templates

    def test_list_templates_custom_extension(self, engine_with_multiple_templates):
        """Test listing templates with custom extension."""
        templates = engine_with_multiple_templates.list_templates(extension=".txt")
        assert len(templates) == 1
        assert "readme.txt" in templates

    def test_list_templates_empty_directory(self, tmp_path):
        """Test listing templates in empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        engine = TemplateEngine(template_dir=empty_dir)
        templates = engine.list_templates()
        assert templates == []

    def test_list_templates_nonexistent_directory(self, tmp_path):
        """Test listing templates in nonexistent directory."""
        nonexistent_dir = tmp_path / "nonexistent"
        engine = TemplateEngine(template_dir=nonexistent_dir)
        templates = engine.list_templates()
        assert templates == []

    def test_list_templates_sorted(self, engine_with_multiple_templates):
        """Test that templates are returned in sorted order."""
        templates = engine_with_multiple_templates.list_templates()
        assert templates == sorted(templates)


class TestTemplateExists:
    """Test checking if templates exist."""

    @pytest.fixture
    def engine_with_template(self, tmp_path):
        """Create engine with a test template."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "exists.md").write_text("I exist!")
        return TemplateEngine(template_dir=template_dir)

    def test_template_exists_true(self, engine_with_template):
        """Test that existing template is found."""
        assert engine_with_template.template_exists("exists.md") is True

    def test_template_exists_false(self, engine_with_template):
        """Test that nonexistent template is not found."""
        assert engine_with_template.template_exists("nonexistent.md") is False


class TestCreateProjectContext:
    """Test creating project context dictionaries."""

    def test_create_project_context_minimal(self):
        """Test creating minimal project context."""
        context = TemplateEngine.create_project_context("MyProject")
        assert context["project"]["name"] == "MyProject"
        assert context["project"]["tech_stack"] == "Python"  # Default
        assert context["project"]["description"] == ""

    def test_create_project_context_full(self):
        """Test creating full project context."""
        context = TemplateEngine.create_project_context(
            project_name="MyProject",
            tech_stack="Python/FastAPI",
            description="A test project"
        )
        assert context["project"]["name"] == "MyProject"
        assert context["project"]["tech_stack"] == "Python/FastAPI"
        assert context["project"]["description"] == "A test project"

    def test_create_project_context_with_kwargs(self):
        """Test creating project context with additional kwargs."""
        context = TemplateEngine.create_project_context(
            project_name="MyProject",
            workspace_dir="/path/to/workspace",
            status="active"
        )
        assert context["project"]["name"] == "MyProject"
        assert context["project"]["workspace_dir"] == "/path/to/workspace"
        assert context["project"]["status"] == "active"


class TestCreateTaskContext:
    """Test creating task context dictionaries."""

    def test_create_task_context_minimal(self):
        """Test creating minimal task context."""
        context = TemplateEngine.create_task_context("Fix bug")
        assert context["task"]["title"] == "Fix bug"
        assert context["task"]["description"] == ""
        assert context["task"]["priority"] == "medium"  # Default

    def test_create_task_context_full(self):
        """Test creating full task context."""
        context = TemplateEngine.create_task_context(
            task_title="Fix bug",
            description="Fix the login bug",
            priority="high"
        )
        assert context["task"]["title"] == "Fix bug"
        assert context["task"]["description"] == "Fix the login bug"
        assert context["task"]["priority"] == "high"

    def test_create_task_context_with_kwargs(self):
        """Test creating task context with additional kwargs."""
        context = TemplateEngine.create_task_context(
            task_title="Fix bug",
            status="in_progress",
            assigned_to="agent-123"
        )
        assert context["task"]["title"] == "Fix bug"
        assert context["task"]["status"] == "in_progress"
        assert context["task"]["assigned_to"] == "agent-123"


class TestMergeContexts:
    """Test merging context dictionaries."""

    def test_merge_empty_contexts(self):
        """Test merging empty contexts."""
        result = TemplateEngine.merge_contexts()
        assert result == {}

    def test_merge_single_context(self):
        """Test merging a single context."""
        context = {"key": "value"}
        result = TemplateEngine.merge_contexts(context)
        assert result == context

    def test_merge_multiple_contexts(self):
        """Test merging multiple contexts."""
        context1 = {"project": {"name": "MyProject"}}
        context2 = {"task": {"title": "Fix bug"}}
        context3 = {"session": {"id": "123"}}

        result = TemplateEngine.merge_contexts(context1, context2, context3)
        assert "project" in result
        assert "task" in result
        assert "session" in result
        assert result["project"]["name"] == "MyProject"
        assert result["task"]["title"] == "Fix bug"
        assert result["session"]["id"] == "123"

    def test_merge_overlapping_contexts(self):
        """Test merging contexts with overlapping keys (later wins)."""
        context1 = {"key": "value1"}
        context2 = {"key": "value2"}

        result = TemplateEngine.merge_contexts(context1, context2)
        assert result["key"] == "value2"


class TestCreateTemplateEngine:
    """Test the factory function."""

    def test_create_template_engine_default(self):
        """Test creating engine with default settings."""
        engine = create_template_engine()
        assert isinstance(engine, TemplateEngine)
        assert engine.template_dir.exists()

    def test_create_template_engine_custom_dir(self, tmp_path):
        """Test creating engine with custom directory."""
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        engine = create_template_engine(template_dir=custom_dir)
        assert isinstance(engine, TemplateEngine)
        assert engine.template_dir == custom_dir


class TestRealTemplates:
    """Test rendering the actual prompt templates."""

    @pytest.fixture
    def engine(self):
        """Create engine pointing to actual prompts directory."""
        return TemplateEngine()

    def test_render_coding_prompt(self, engine):
        """Test rendering the actual coding prompt template."""
        # Check if coding_prompt.md exists
        if not engine.template_exists("coding_prompt.md"):
            pytest.skip("coding_prompt.md not found")

        context = TemplateEngine.merge_contexts(
            TemplateEngine.create_project_context(
                "TestProject",
                tech_stack="Python",
                description="A test project"
            ),
            TemplateEngine.create_task_context(
                "Implement feature X",
                description="Add new feature",
                priority="high"
            )
        )

        result = engine.render_template("coding_prompt.md", context)
        assert "TestProject" in result
        assert "Python" in result
        assert "Implement feature X" in result
        assert "high" in result

    def test_render_research_prompt(self, engine):
        """Test rendering the actual research prompt template."""
        if not engine.template_exists("research_prompt.md"):
            pytest.skip("research_prompt.md not found")

        context = TemplateEngine.merge_contexts(
            TemplateEngine.create_project_context(
                "TestProject",
                tech_stack="Python"
            ),
            TemplateEngine.create_task_context(
                "Research async patterns",
                description="Find best practices for async/await"
            )
        )

        result = engine.render_template("research_prompt.md", context)
        assert "TestProject" in result
        assert "Research async patterns" in result

    def test_render_diagnosis_prompt(self, engine):
        """Test rendering the actual diagnosis prompt template."""
        if not engine.template_exists("diagnosis_prompt.md"):
            pytest.skip("diagnosis_prompt.md not found")

        context = TemplateEngine.merge_contexts(
            TemplateEngine.create_project_context(
                "TestProject",
                tech_stack="Python"
            ),
            TemplateEngine.create_task_context(
                "Debug authentication issue",
                description="Users can't log in"
            )
        )

        result = engine.render_template("diagnosis_prompt.md", context)
        assert "TestProject" in result
        assert "Debug authentication issue" in result

    def test_list_actual_templates(self, engine):
        """Test listing actual templates in prompts directory."""
        templates = engine.list_templates()
        # Should have at least the templates we created
        assert isinstance(templates, list)
        # May have coding_prompt.md, research_prompt.md, etc.


class TestTemplateEngineEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create engine with temp directory."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        return TemplateEngine(template_dir=template_dir)

    def test_render_with_none_values(self, engine):
        """Test rendering with None values in context."""
        template = "Value: {{ value }}"
        result = engine.render_string(template, {"value": None})
        # Jinja2 renders None as "None"
        assert result == "Value: None"

    def test_render_with_nested_context(self, engine):
        """Test rendering with deeply nested context."""
        template = "{{ level1.level2.level3.value }}"
        context = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": "deep"
                    }
                }
            }
        }
        result = engine.render_string(template, context)
        assert result == "deep"

    def test_render_with_list_access(self, engine):
        """Test rendering with list index access."""
        template = "First: {{ items[0] }}, Second: {{ items[1] }}"
        context = {"items": ["one", "two", "three"]}
        result = engine.render_string(template, context)
        assert result == "First: one, Second: two"

    def test_render_with_special_characters(self, engine):
        """Test rendering with special characters."""
        template = "Message: {{ message }}"
        context = {"message": "Hello <>&\"'"}
        result = engine.render_string(template, context)
        assert "Hello <>&\"'" in result
