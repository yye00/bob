"""Spec source plugin system.

This package provides the pluggable architecture for pulling task specifications
from various sources (files, GitHub, Jira, etc.).
"""

from bob.spec_sources.base import (
    SpecSource,
    SpecSourceError,
    SpecSourceRegistry,
    SyncResult,
    TaskSpec,
    get_registry,
)
from bob.spec_sources.file_source import FileSpecSource

# Auto-register file spec source
_registry = get_registry()
_registry.register("file", FileSpecSource)

__all__ = [
    "SpecSource",
    "SpecSourceError",
    "SpecSourceRegistry",
    "SyncResult",
    "TaskSpec",
    "get_registry",
    "FileSpecSource",
]
