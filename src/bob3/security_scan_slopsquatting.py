"""Slopsquatting sub-check with local-module whitelisting.

This module implements the fix for the recurring false-positive where a
locally-defined module (e.g. ``spec_quality_score``) is flagged as a
missing PyPI distribution because the slopsquatting heuristic cannot
distinguish a locally-defined module from a third-party package name.

The canonical fix: before issuing any PyPI probe, consult the workspace's
generated-code tree (``src/bob3/**/*.py``, ``tools/**/*.py``, root-level
``.py`` files, etc.) and whitelist any import whose name corresponds to a
local module file path.  Whitelisted names are never probed against PyPI,
so they cannot trigger slopsquatting hard-fails.

Public API
----------
whitelist_local_modules(workspace)
    Return the set of import names that are locally defined in the
    workspace and must be excluded from PyPI existence checks.

slopsquatting_check(workspace, diff, *, timeout)
    Run the slopsquatting sub-check with local-module whitelisting.
"""
from __future__ import annotations

from pathlib import Path

from bob3.security_checks import (
    _read_first_party_packages,
    _run_slopsquatting,
    _pypi_package_exists,
)
from bob3.models import SecurityFinding


def whitelist_local_modules(workspace: Path) -> set[str]:
    """Return the set of import names that are locally defined in the workspace.

    These names must be excluded from any PyPI existence check (slopsquatting)
    because they are files or packages that exist within the generated-code
    tree, not third-party distributions.

    The scan covers:
    - ``src/<pkg>/`` — top-level packages under ``src/``
    - ``src/<pkg>/**/*.py`` — all module stems within those packages
    - ``tools/**/*.py`` — tool scripts importable as first-party modules
    - Root-level ``*.py`` files — project-root scripts on ``sys.path``
    - The workspace directory name itself (matches ``import bob88`` etc.)

    Parameters
    ----------
    workspace:
        Root directory of the workspace. Must be an existing directory and
        must be provided as a :class:`pathlib.Path` instance.

    Returns
    -------
    set[str]
        Import names (top-level package / module stems) that are present
        in the workspace's own code tree.  PyPI probes for these names are
        invalid and must be skipped.

    Raises
    ------
    TypeError
        If ``workspace`` is not a :class:`pathlib.Path` instance.
    ValueError
        If ``workspace`` does not exist or is not a directory.
    """
    if not isinstance(workspace, Path):
        raise TypeError(
            f"workspace must be a pathlib.Path, got {type(workspace).__name__!r}"
        )
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")

    return _read_first_party_packages(workspace)


def slopsquatting_check(
    workspace: Path,
    diff: str | None = None,
    *,
    timeout: int = 30,
) -> tuple[list[SecurityFinding], str | None]:
    """Run the slopsquatting sub-check with local-module whitelisting.

    Consults the generated-code tree under ``workspace`` to build the
    first-party module whitelist before probing PyPI.  Import names that
    correspond to locally-defined modules are excluded from the PyPI
    existence check, preventing false-positives for legitimate local
    imports such as ``spec_quality_score``.

    Parameters
    ----------
    workspace:
        Root directory of the workspace. Must be an existing directory and
        must be provided as a :class:`pathlib.Path` instance.
    diff:
        Optional unified-diff text of the change set under review. When
        ``None``, the check falls back to a full tree walk of the workspace.
    timeout:
        Per-request timeout in seconds (default 30).

    Returns
    -------
    tuple[list[SecurityFinding], str | None]
        A ``(findings, tool_failure_message)`` pair.  ``findings`` lists
        any slopsquatting findings (packages in the diff / tree that do
        not exist on PyPI).  ``tool_failure_message`` is non-``None`` when
        the check could not run (e.g. network unavailable); this is never
        a hard-fail by itself.

    Raises
    ------
    TypeError
        If ``workspace`` is not a :class:`pathlib.Path` instance.
    ValueError
        If ``workspace`` does not exist or is not a directory.
    """
    if not isinstance(workspace, Path):
        raise TypeError(
            f"workspace must be a pathlib.Path, got {type(workspace).__name__!r}"
        )
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")

    return _run_slopsquatting(workspace, diff, timeout=timeout)


def is_local_module(import_name: str, workspace: Path) -> bool:
    """Return True if ``import_name`` is defined in the workspace's own code tree.

    A locally-defined module must never be probed against PyPI for
    slopsquatting detection.

    Parameters
    ----------
    import_name:
        Top-level package/module name from an import statement.
    workspace:
        Root directory of the workspace for the local-module whitelist.

    Returns
    -------
    bool
        ``True`` iff the import name is locally defined in the workspace.

    Raises
    ------
    TypeError
        If ``workspace`` is not a :class:`pathlib.Path` instance.
    ValueError
        If ``import_name`` is empty or ``workspace`` is invalid.
    """
    if not isinstance(workspace, Path):
        raise TypeError(
            f"workspace must be a pathlib.Path, got {type(workspace).__name__!r}"
        )
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")
    if not import_name:
        raise ValueError("import_name must be a non-empty string")

    return import_name in whitelist_local_modules(workspace)


__all__ = [
    "whitelist_local_modules",
    "slopsquatting_check",
    "is_local_module",
]
