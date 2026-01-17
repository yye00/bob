#!/usr/bin/env python3
"""
Template engine for BOB prompt templates.

Provides Jinja2-based template rendering with project and task context variables.
Supports loading templates from the prompts/ directory and rendering them with
dynamic data.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound, select_autoescape


class TemplateEngine:
    """
    Template engine for rendering prompt templates with project context.

    Supports Jinja2-style variable substitution with project and task variables:
    - {project.name} - Project name
    - {project.tech_stack} - Technology stack
    - {project.description} - Project description
    - {task.title} - Task title
    - {task.description} - Task description
    - {task.priority} - Task priority
    - etc.
    """

    def __init__(self, template_dir: Optional[Path] = None) -> None:
        """
        Initialize the template engine.

        Args:
            template_dir: Directory containing template files.
                         Defaults to bob/prompts/ directory.
        """
        if template_dir is None:
            # Default to bob/prompts/ directory
            template_dir = Path(__file__).parent

        self.template_dir = Path(template_dir)

        # Create Jinja2 environment
        # Don't autoescape - we're rendering markdown/text, not HTML
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Add custom filters if needed
        self._setup_filters()

    def _setup_filters(self) -> None:
        """Set up custom Jinja2 filters."""
        # Add custom filters here if needed
        # Example: self.env.filters['custom_filter'] = custom_filter_function
        pass

    def render_template(
        self,
        template_name: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Render a template with the given context.

        Args:
            template_name: Name of the template file (e.g., 'coding_prompt.md')
            context: Dictionary of variables to use in rendering

        Returns:
            Rendered template string

        Raises:
            TemplateNotFound: If template file doesn't exist
            jinja2.TemplateError: If template rendering fails
        """
        try:
            template = self.env.get_template(template_name)
            return template.render(**context)
        except TemplateNotFound:
            raise TemplateNotFound(
                f"Template '{template_name}' not found in {self.template_dir}"
            )

    def render_string(
        self,
        template_string: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Render a template string with the given context.

        Args:
            template_string: Template string to render
            context: Dictionary of variables to use in rendering

        Returns:
            Rendered template string

        Raises:
            jinja2.TemplateError: If template rendering fails
        """
        template = self.env.from_string(template_string)
        return template.render(**context)

    def list_templates(self, extension: str = ".md") -> list[str]:
        """
        List all available templates in the template directory.

        Args:
            extension: File extension to filter by (default: '.md')

        Returns:
            List of template filenames
        """
        if not self.template_dir.exists():
            return []

        templates = []
        for file_path in self.template_dir.iterdir():
            if file_path.is_file() and file_path.suffix == extension:
                templates.append(file_path.name)

        return sorted(templates)

    def template_exists(self, template_name: str) -> bool:
        """
        Check if a template exists.

        Args:
            template_name: Name of the template file

        Returns:
            True if template exists, False otherwise
        """
        template_path = self.template_dir / template_name
        return template_path.is_file()

    @staticmethod
    def create_project_context(
        project_name: str,
        tech_stack: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Create a project context dictionary for template rendering.

        Args:
            project_name: Name of the project
            tech_stack: Technology stack description
            description: Project description
            **kwargs: Additional project attributes

        Returns:
            Dictionary with 'project' key containing project context
        """
        project_context = {
            "name": project_name,
            "tech_stack": tech_stack or "Python",
            "description": description or "",
        }
        project_context.update(kwargs)

        return {"project": project_context}

    @staticmethod
    def create_task_context(
        task_title: str,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Create a task context dictionary for template rendering.

        Args:
            task_title: Title of the task
            description: Task description
            priority: Task priority (critical, high, medium, low)
            **kwargs: Additional task attributes

        Returns:
            Dictionary with 'task' key containing task context
        """
        task_context = {
            "title": task_title,
            "description": description or "",
            "priority": priority or "medium",
        }
        task_context.update(kwargs)

        return {"task": task_context}

    @staticmethod
    def merge_contexts(*contexts: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge multiple context dictionaries.

        Args:
            *contexts: Variable number of context dictionaries

        Returns:
            Merged context dictionary
        """
        merged: Dict[str, Any] = {}
        for context in contexts:
            merged.update(context)
        return merged


def create_template_engine(template_dir: Optional[Path] = None) -> TemplateEngine:
    """
    Factory function to create a template engine instance.

    Args:
        template_dir: Optional custom template directory

    Returns:
        Configured TemplateEngine instance
    """
    return TemplateEngine(template_dir=template_dir)
