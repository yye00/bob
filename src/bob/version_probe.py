"""Probe and report SDK version and model ID for telemetry and pre-flight checks."""
from __future__ import annotations

import importlib.metadata
import os
import re
import warnings
from pathlib import Path
from typing import Optional

# Canonical default model used when no env override is set
_DEFAULT_MODEL_ID = "claude-sonnet-4-5-20250929"

# SDK packages to probe (in priority order)
_SDK_PACKAGES = ["anthropic", "claude-code-sdk"]


def get_sdk_version() -> str:
    """Return the installed Anthropic SDK version string.

    Tries the ``anthropic`` package first, then ``claude-code-sdk``.
    Returns ``"unknown"`` if neither is installed.
    """
    for pkg in _SDK_PACKAGES:
        try:
            return importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            continue
    return "unknown"


def get_model_id() -> str:
    """Return the active Claude model ID.

    Respects the ``ANTHROPIC_DEFAULT_SONNET_MODEL`` environment variable
    used by the claude-code-sdk gateway configuration, falling back to
    the canonical Sonnet model ID.
    """
    override = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
    if override:
        return override.strip()
    return _DEFAULT_MODEL_ID


def _get_pinned_sdk_version() -> Optional[str]:
    """Extract the pinned claude-code-sdk version from pyproject.toml.

    Returns the pinned version string (e.g. ``"0.0.25"``) or ``None``
    if pyproject.toml cannot be found or the dependency is not listed.
    """
    # Walk up from this file to find pyproject.toml
    search_path = Path(__file__).resolve()
    for parent in [search_path.parent, *search_path.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.exists():
            try:
                content = candidate.read_text(encoding="utf-8")
            except OSError:
                return None
            # Match lines like:  "claude-code-sdk>=0.0.25"  or  "anthropic==1.2.3"
            for pkg_name in ("claude-code-sdk", "anthropic"):
                pattern = re.compile(
                    rf'["\']?{re.escape(pkg_name)}["\']?\s*[><=!~]+\s*([0-9][^"\'>,\s]*)',
                    re.IGNORECASE,
                )
                m = pattern.search(content)
                if m:
                    return m.group(1)
            return None
    return None


def preflight_version_check() -> None:
    """Warn (but do not block) if the installed SDK version differs from the pinned version.

    The discrepancy is emitted as a :class:`UserWarning` so it appears in logs
    and is captured in telemetry without preventing experiment execution.
    """
    installed = get_sdk_version()
    pinned = _get_pinned_sdk_version()
    if pinned is None or installed == "unknown":
        return
    if installed != pinned:
        warnings.warn(
            f"SDK version mismatch: installed={installed!r}, pinned in pyproject.toml={pinned!r}. "
            "Experiment will run on the installed version; discrepancy noted in telemetry.",
            UserWarning,
            stacklevel=2,
        )
