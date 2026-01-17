"""Tests for prompt loader functionality."""

import pytest
from pathlib import Path
from bob.prompts.loader import PromptLoader, create_prompt_loader


class TestPromptLoaderInit:
    """Test PromptLoader initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default global prompts directory."""
        loader = PromptLoader()
        assert loader.global_prompts_dir.exists()
        assert loader.global_prompts_dir.name == "prompts"
        assert loader.project_prompts_dir is None
        assert loader.project_engine is None

    def test_init_with_project_dir_nonexistent(self, tmp_path):
        """Test initialization with non-existent project prompts directory."""
        project_dir = tmp_path / "nonexistent"
        loader = PromptLoader(project_prompts_dir=project_dir)
        assert loader.project_prompts_dir == project_dir
        assert loader.project_engine is None  # Not created because dir doesn't exist

    def test_init_with_project_dir_existent(self, tmp_path):
        """Test initialization with existing project prompts directory."""
        project_dir = tmp_path / "prompts"
        project_dir.mkdir()
        loader = PromptLoader(project_prompts_dir=project_dir)
        assert loader.project_prompts_dir == project_dir
        assert loader.project_engine is not None

    def test_init_with_custom_global_dir(self, tmp_path):
        """Test initialization with custom global prompts directory."""
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        loader = PromptLoader(global_prompts_dir=global_dir)
        assert loader.global_prompts_dir == global_dir


class TestLoadPromptGlobal:
    """Test loading prompts from global directory."""

    def test_load_global_coding_prompt(self):
        """Test loading coding prompt from global directory."""
        loader = PromptLoader()
        context = {
            "project": {
                "name": "test-project",
                "tech_stack": "Python",
                "description": "Test project",
            },
            "task": {
                "title": "Test task",
                "description": "Test description",
                "priority": "high",
            }
        }
        prompt = loader.load_prompt("coding_prompt.md", context)
        assert "test-project" in prompt
        assert "Python" in prompt
        assert "Test task" in prompt

    def test_load_global_research_prompt(self):
        """Test loading research prompt from global directory."""
        loader = PromptLoader()
        context = {
            "project": {
                "name": "test-project",
            },
            "task": {
                "title": "Research task",
            }
        }
        prompt = loader.load_prompt("research_prompt.md", context)
        assert "test-project" in prompt
        assert "Research task" in prompt

    def test_load_nonexistent_prompt(self):
        """Test loading non-existent prompt raises error."""
        loader = PromptLoader()
        with pytest.raises(FileNotFoundError) as exc_info:
            loader.load_prompt("nonexistent.md")
        assert "not found" in str(exc_info.value)


class TestLoadPromptProjectOverride:
    """Test loading prompts with project-specific overrides."""

    def test_load_project_override(self, tmp_path):
        """Test that project prompt overrides global prompt."""
        # Create project prompts directory
        project_dir = tmp_path / "prompts"
        project_dir.mkdir()

        # Create custom coding prompt
        custom_prompt_path = project_dir / "coding_prompt.md"
        custom_prompt_path.write_text("CUSTOM CODING PROMPT for {{ project.name }}")

        # Create loader
        loader = PromptLoader(project_prompts_dir=project_dir)

        # Load prompt
        context = {"project": {"name": "my-project"}}
        prompt = loader.load_prompt("coding_prompt.md", context)

        # Should load from project directory
        assert "CUSTOM CODING PROMPT" in prompt
        assert "my-project" in prompt

    def test_load_fallback_to_global(self, tmp_path):
        """Test fallback to global prompt when not in project directory."""
        # Create project prompts directory but don't add coding_prompt
        project_dir = tmp_path / "prompts"
        project_dir.mkdir()

        # Create loader
        loader = PromptLoader(project_prompts_dir=project_dir)

        # Load prompt - should fall back to global
        context = {
            "project": {
                "name": "test-project",
                "tech_stack": "Python",
            },
            "task": {}
        }
        prompt = loader.load_prompt("coding_prompt.md", context)

        # Should load from global directory
        assert "test-project" in prompt
        assert "Coding Agent" in prompt  # Global prompt text

    def test_load_mixed_prompts(self, tmp_path):
        """Test loading mix of project and global prompts."""
        # Create project prompts directory
        project_dir = tmp_path / "prompts"
        project_dir.mkdir()

        # Override only coding prompt
        custom_coding = project_dir / "coding_prompt.md"
        custom_coding.write_text("CUSTOM: {{ project.name }}")

        # Create loader
        loader = PromptLoader(project_prompts_dir=project_dir)

        # Load coding prompt - should use project override
        context = {"project": {"name": "my-project"}, "task": {}}
        coding_prompt = loader.load_prompt("coding_prompt.md", context)
        assert "CUSTOM:" in coding_prompt

        # Load research prompt - should use global
        research_prompt = loader.load_prompt("research_prompt.md", context)
        assert "Research Agent" in research_prompt  # Global prompt text


class TestPromptExists:
    """Test prompt existence checking."""

    def test_prompt_exists_global(self):
        """Test checking if global prompt exists."""
        loader = PromptLoader()
        assert loader._prompt_exists("coding_prompt.md", is_project=False)
        assert not loader._prompt_exists("nonexistent.md", is_project=False)

    def test_prompt_exists_project_no_dir(self):
        """Test checking project prompt when no project directory."""
        loader = PromptLoader()
        assert not loader._prompt_exists("coding_prompt.md", is_project=True)

    def test_prompt_exists_project_with_dir(self, tmp_path):
        """Test checking project prompt with project directory."""
        project_dir = tmp_path / "prompts"
        project_dir.mkdir()
        custom_prompt = project_dir / "custom.md"
        custom_prompt.write_text("Custom prompt")

        loader = PromptLoader(project_prompts_dir=project_dir)
        assert loader._prompt_exists("custom.md", is_project=True)
        assert not loader._prompt_exists("nonexistent.md", is_project=True)


class TestGetPromptSource:
    """Test getting prompt source location."""

    def test_get_source_global(self):
        """Test getting source for global prompt."""
        loader = PromptLoader()
        assert loader.get_prompt_source("coding_prompt.md") == "global"
        assert loader.get_prompt_source("research_prompt.md") == "global"

    def test_get_source_not_found(self):
        """Test getting source for non-existent prompt."""
        loader = PromptLoader()
        assert loader.get_prompt_source("nonexistent.md") == "not_found"

    def test_get_source_project_override(self, tmp_path):
        """Test getting source when project overrides global."""
        project_dir = tmp_path / "prompts"
        project_dir.mkdir()
        custom_prompt = project_dir / "coding_prompt.md"
        custom_prompt.write_text("Custom")

        loader = PromptLoader(project_prompts_dir=project_dir)

        # Overridden prompt should show as project
        assert loader.get_prompt_source("coding_prompt.md") == "project"

        # Non-overridden prompt should show as global
        assert loader.get_prompt_source("research_prompt.md") == "global"


class TestListAvailablePrompts:
    """Test listing available prompts."""

    def test_list_global_only(self):
        """Test listing prompts with only global directory."""
        loader = PromptLoader()
        prompts = loader.list_available_prompts()

        # Should have standard prompts
        assert "coding_prompt.md" in prompts
        assert "research_prompt.md" in prompts
        assert prompts["coding_prompt.md"] == "global"

    def test_list_with_project_overrides(self, tmp_path):
        """Test listing prompts with project overrides."""
        project_dir = tmp_path / "prompts"
        project_dir.mkdir()

        # Create custom coding prompt
        (project_dir / "coding_prompt.md").write_text("Custom")
        # Create new custom prompt
        (project_dir / "custom.md").write_text("Custom prompt")

        loader = PromptLoader(project_prompts_dir=project_dir)
        prompts = loader.list_available_prompts()

        # Overridden prompt should show as project
        assert prompts["coding_prompt.md"] == "project"

        # New custom prompt should show as project
        assert prompts["custom.md"] == "project"

        # Non-overridden prompts should show as global
        assert prompts["research_prompt.md"] == "global"


class TestCreatePromptLoader:
    """Test factory function for creating prompt loader."""

    def test_create_without_project(self):
        """Test creating loader without project workspace."""
        loader = create_prompt_loader()
        assert loader.project_prompts_dir is None
        assert loader.project_engine is None

    def test_create_with_project_workspace(self, tmp_path):
        """Test creating loader with project workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create .bob/prompts directory
        prompts_dir = workspace / ".bob" / "prompts"
        prompts_dir.mkdir(parents=True)

        loader = create_prompt_loader(project_workspace_dir=workspace)
        assert loader.project_prompts_dir == prompts_dir
        assert loader.project_engine is not None

    def test_create_with_nonexistent_workspace(self, tmp_path):
        """Test creating loader with non-existent workspace."""
        workspace = tmp_path / "nonexistent"
        loader = create_prompt_loader(project_workspace_dir=workspace)

        # Should set project_prompts_dir but not create engine
        expected_dir = workspace / ".bob" / "prompts"
        assert loader.project_prompts_dir == expected_dir
        assert loader.project_engine is None


class TestPromptLoaderIntegration:
    """Integration tests for prompt loader."""

    def test_full_workflow_with_custom_prompts(self, tmp_path):
        """Test complete workflow with custom project prompts."""
        # Set up project workspace
        workspace = tmp_path / "my-project"
        bob_dir = workspace / ".bob"
        prompts_dir = bob_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        # Create custom coding prompt
        custom_coding = prompts_dir / "coding_prompt.md"
        custom_coding.write_text(
            """# Custom Coding Instructions
Project: {{ project.name }}
Tech: {{ project.tech_stack }}

Custom instructions here.
"""
        )

        # Create prompt loader
        loader = create_prompt_loader(project_workspace_dir=workspace)

        # Load coding prompt with context
        context = {
            "project": {
                "name": "my-awesome-app",
                "tech_stack": "Python/FastAPI",
            }
        }
        coding_prompt = loader.load_prompt("coding_prompt.md", context)

        # Verify custom prompt was loaded
        assert "Custom Coding Instructions" in coding_prompt
        assert "my-awesome-app" in coding_prompt
        assert "Python/FastAPI" in coding_prompt

        # Load research prompt (should use global)
        context_with_task = {
            "project": {
                "name": "my-awesome-app",
                "tech_stack": "Python/FastAPI",
            },
            "task": {}
        }
        research_prompt = loader.load_prompt("research_prompt.md", context_with_task)
        assert "my-awesome-app" in research_prompt
        assert "Research Agent" in research_prompt

        # Verify prompt sources
        assert loader.get_prompt_source("coding_prompt.md") == "project"
        assert loader.get_prompt_source("research_prompt.md") == "global"
