#!/usr/bin/env python3
"""
Prompt loader for BOB.

Loads prompts from project-specific or global directories, supporting
custom prompt overrides per project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from bob.prompts.template_engine import TemplateEngine


class PromptLoader:
    """
    Prompt loader that supports project-specific prompt overrides.

    Loads prompts in this priority order:
    1. Project-specific prompts from <workspace>/.bob/prompts/
    2. Global prompts from bob/prompts/

    This allows projects to override specific agent prompts while
    falling back to global defaults.
    """

    def __init__(
        self,
        project_prompts_dir: Optional[Path] = None,
        global_prompts_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize the prompt loader.

        Args:
            project_prompts_dir: Project-specific prompts directory
                                (usually <workspace>/.bob/prompts/)
            global_prompts_dir: Global prompts directory
                               (usually bob/prompts/)
        """
        # Default global prompts directory to bob/prompts/
        if global_prompts_dir is None:
            # Get the directory where this file is located (bob/prompts/)
            global_prompts_dir = Path(__file__).parent

        self.global_prompts_dir = Path(global_prompts_dir)
        self.project_prompts_dir = Path(project_prompts_dir) if project_prompts_dir else None

        # Create template engines for each directory
        self.global_engine = TemplateEngine(template_dir=self.global_prompts_dir)

        # Only create project engine if directory is provided and exists
        self.project_engine: Optional[TemplateEngine] = None
        if self.project_prompts_dir and self.project_prompts_dir.exists():
            self.project_engine = TemplateEngine(template_dir=self.project_prompts_dir)

    def load_prompt(
        self,
        prompt_name: str,
        context: Optional[Dict] = None,
    ) -> str:
        """
        Load and render a prompt template.

        First checks project-specific prompts directory, then falls back
        to global prompts.

        Args:
            prompt_name: Name of the prompt template (e.g., 'coding_prompt.md')
            context: Context dictionary for template rendering

        Returns:
            Rendered prompt string

        Raises:
            FileNotFoundError: If prompt not found in either directory
        """
        context = context or {}

        # First try project-specific prompt
        if self.project_engine and self._prompt_exists(prompt_name, is_project=True):
            return self.project_engine.render_template(prompt_name, context)

        # Fall back to global prompt
        if self._prompt_exists(prompt_name, is_project=False):
            return self.global_engine.render_template(prompt_name, context)

        # Not found in either location
        raise FileNotFoundError(
            f"Prompt '{prompt_name}' not found in project or global prompts directories"
        )

    def _prompt_exists(self, prompt_name: str, is_project: bool) -> bool:
        """
        Check if a prompt exists in the specified location.

        Args:
            prompt_name: Name of the prompt template
            is_project: True to check project dir, False for global dir

        Returns:
            True if prompt exists, False otherwise
        """
        if is_project:
            if not self.project_engine:
                return False
            return self.project_engine.template_exists(prompt_name)
        else:
            return self.global_engine.template_exists(prompt_name)

    def get_prompt_source(self, prompt_name: str) -> str:
        """
        Get the source location of a prompt (project or global).

        Args:
            prompt_name: Name of the prompt template

        Returns:
            'project' if found in project directory,
            'global' if found in global directory,
            'not_found' if not found
        """
        if self.project_engine and self._prompt_exists(prompt_name, is_project=True):
            return "project"
        elif self._prompt_exists(prompt_name, is_project=False):
            return "global"
        else:
            return "not_found"

    def list_available_prompts(self) -> Dict[str, str]:
        """
        List all available prompts and their sources.

        Returns:
            Dictionary mapping prompt names to their source ('project' or 'global')
        """
        prompts: Dict[str, str] = {}

        # Get global prompts
        global_prompts = self.global_engine.list_templates()
        for prompt in global_prompts:
            prompts[prompt] = "global"

        # Override with project prompts if they exist
        if self.project_engine:
            project_prompts = self.project_engine.list_templates()
            for prompt in project_prompts:
                prompts[prompt] = "project"

        return prompts


def create_prompt_loader(
    project_workspace_dir: Optional[Path] = None,
) -> PromptLoader:
    """
    Factory function to create a prompt loader instance.

    Args:
        project_workspace_dir: Project workspace directory (will look for .bob/prompts/)

    Returns:
        Configured PromptLoader instance
    """
    project_prompts_dir = None
    if project_workspace_dir:
        project_prompts_dir = Path(project_workspace_dir) / ".bob" / "prompts"

    return PromptLoader(project_prompts_dir=project_prompts_dir)
