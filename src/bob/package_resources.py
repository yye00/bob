"""Locations of Bob resources in source checkouts and built distributions."""

from __future__ import annotations

from pathlib import Path


_PACKAGE_DIR = Path(__file__).resolve().parent
_SOURCE_ROOT = _PACKAGE_DIR.parent.parent


def _installed_or_source(installed_name: str, source_relative: str) -> Path:
    """Prefer a resource embedded in the wheel, then the source-tree copy."""
    installed = _PACKAGE_DIR / installed_name
    if installed.is_file():
        return installed
    return _SOURCE_ROOT / source_relative


def spec_schema_path() -> Path:
    """Return the canonical pinned JSON schema path."""
    return _installed_or_source("spec.v1.json", "schemas/spec.v1.json")


def spawn_retry_config_path() -> Path:
    """Return the canonical default spawn-retry configuration path."""
    return _installed_or_source("spawn_retry.yaml", "config/spawn_retry.yaml")
