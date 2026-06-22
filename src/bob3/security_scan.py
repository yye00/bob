"""Public API for security scan local-module whitelisting.

Exposes ``whitelist_local_modules`` and ``slopsquatting_check`` — the
canonical entry points for the slopsquatting detection feature.

``whitelist_local_modules`` returns the set of import names that are
locally-defined in the generated-code tree and must never be probed
against PyPI for slopsquatting detection.

``slopsquatting_check`` runs the slopsquatting sub-check, consulting
the workspace's generated-code tree first so that locally-defined
modules are whitelisted before any PyPI probe is issued.

This module is the fix for the recurring false-positive where a local
module (e.g. ``spec_quality_score``) is flagged as a missing PyPI
distribution because the slopsquatting heuristic cannot distinguish a
locally-defined module from a third-party package name.
"""
from __future__ import annotations

from pathlib import Path

from bob3.security_checks import _read_first_party_packages, _run_slopsquatting, _pypi_package_exists
from bob3.models import SecurityFinding


def whitelist_local_modules(workspace: Path) -> set[str]:
    """Return the set of import names that are locally defined in the workspace.

    These names must be excluded from any PyPI existence check (slopsquatting)
    because they are files or packages that exist within the generated-code
    tree, not third-party distributions.

    Parameters
    ----------
    workspace:
        Root directory of the workspace (must be an existing directory).

    Returns
    -------
    set[str]
        Import names (top-level package / module stems) that are present
        in the workspace's own code tree. PyPI probes for these names are
        invalid and must be skipped.

    Raises
    ------
    TypeError
        If ``workspace`` is not a ``pathlib.Path`` instance.
    ValueError
        If ``workspace`` does not exist or is not a directory.
    """
    if not isinstance(workspace, Path):
        raise TypeError(f"workspace must be a pathlib.Path, got {type(workspace).__name__!r}")
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
    first-party module whitelist before probing PyPI. Import names that
    correspond to locally-defined modules (files or packages present in
    the workspace's own code tree) are excluded from the PyPI existence
    check, preventing false-positives for legitimate local imports such
    as ``spec_quality_score``.

    Parameters
    ----------
    workspace:
        Root directory of the workspace (must be an existing directory).
    diff:
        Optional unified-diff text of the change set under review. When
        None, the check falls back to a full tree walk of the workspace.
    timeout:
        Per-request timeout in seconds (default 30).

    Returns
    -------
    tuple[list[SecurityFinding], str | None]
        A ``(findings, tool_failure_message)`` pair. ``findings`` lists
        any slopsquatting findings (packages in the diff / tree that do
        not exist on PyPI). ``tool_failure_message`` is non-None when
        the check could not run (e.g. network unavailable); this is
        never a hard-fail by itself.

    Raises
    ------
    TypeError
        If ``workspace`` is not a ``pathlib.Path`` instance.
    ValueError
        If ``workspace`` does not exist or is not a directory.
    """
    if not isinstance(workspace, Path):
        raise TypeError(f"workspace must be a pathlib.Path, got {type(workspace).__name__!r}")
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")

    return _run_slopsquatting(workspace, diff, timeout=timeout)


def get_local_modules(workspace: Path) -> set[str]:
    """Return the set of locally-defined module names in the workspace.

    Alias for ``whitelist_local_modules`` that uses the canonical name
    expected by the feature's acceptance criteria.  All modules found
    in the generated-code tree (``src/``, ``tools/``, root-level ``.py``
    files, etc.) are returned so callers can test membership before
    issuing a PyPI probe.

    Parameters
    ----------
    workspace:
        Root directory of the workspace (must be an existing directory).

    Returns
    -------
    set[str]
        Import-name stems for every locally-defined module or package.

    Raises
    ------
    TypeError
        If ``workspace`` is not a ``pathlib.Path`` instance.
    ValueError
        If ``workspace`` does not exist or is not a directory.
    """
    return whitelist_local_modules(workspace)


def is_slopsquatting_violation(
    import_name: str,
    workspace: Path,
    *,
    timeout: int = 10,
) -> bool:
    """Return True if ``import_name`` is a genuine slopsquatting candidate.

    A slopsquatting violation occurs when an import name:
    1. Is NOT present in the workspace's locally-defined module tree, AND
    2. Does NOT exist on PyPI (HTTP 404 from the JSON API).

    Names that are locally defined (found by ``get_local_modules``) are
    never violations, regardless of their PyPI status. Names for which
    the PyPI probe fails with a network error are conservatively treated
    as non-violations (``False``) so a transient network issue cannot
    hard-fail a feature.

    Parameters
    ----------
    import_name:
        Top-level package/module name from an import statement.
    workspace:
        Root directory of the workspace for the local-module whitelist.
    timeout:
        Per-request network timeout in seconds (default 10).

    Returns
    -------
    bool
        ``True`` iff the import is a slopsquatting violation.

    Raises
    ------
    TypeError
        If ``workspace`` is not a ``pathlib.Path`` instance.
    ValueError
        If ``import_name`` is empty or ``workspace`` is invalid.
    """
    if not isinstance(workspace, Path):
        raise TypeError(f"workspace must be a pathlib.Path, got {type(workspace).__name__!r}")
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")
    if not import_name:
        raise ValueError("import_name must be a non-empty string")

    local_modules = get_local_modules(workspace)
    if import_name in local_modules:
        return False

    exists = _pypi_package_exists(import_name, timeout=timeout)
    if exists is None:
        return False
    return not exists
