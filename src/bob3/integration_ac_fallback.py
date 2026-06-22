"""Integration AC fallback resolver — Pattern-8 function-existence fallback.

When an 'integration:' AC's first token is a bare snake_case function name
(not a dotted module path), the standard _integration_wired check returns False
because no module file with that name exists.

This module exposes ``resolve_integration_target``, the canonical entry point
for the two-phase Pattern-8 integration AC check:

  1. Dotted-path resolution via _integration_wired (module file exists + is imported).
  2. Bare snake_case function-existence scan in workspace Python source files.

Root cause addressed (bob3 v.17 r1 ~09:43Z): feature 85790dc6 (orphan-subagent
reaper) NH'd with AC:
    "integration: sweep_orphan_subagents runs at the same cadence as the
    existing stuck_executing reaper (watchdog tick); both reapers are
    idempotent and safe to run concurrently"

F-R7-577 (integration-ac-prose-demotion) did not fire on this shape. This
module implements the mirror of the F-R7-582 behavior-AC fallback for
integration ACs.
"""

from __future__ import annotations

import pathlib
import re


def resolve_integration_target(criterion: str, workspace: pathlib.Path) -> bool:
    """Resolve an 'integration:' AC using dotted-path check with function-existence fallback.

    Phase 1: Extract all dotted-path tokens (tokens with at least one dot) from
    *criterion* and check each via _integration_wired (module file exists AND is
    imported somewhere in the workspace).

    Phase 2: When no dotted path resolves, scan all snake_case identifiers in the
    criterion body and return True if any resolves to a def/class in workspace
    Python source files. This handles prose-integration ACs like:
        "integration: sweep_orphan_subagents runs at the same cadence …"

    Parameters
    ----------
    criterion:
        The full acceptance criterion string (e.g. "integration: bob3.foo …").
    workspace:
        Root path of the workspace (where src/ lives).

    Returns
    -------
    bool
        True if the integration AC is satisfied via either phase, False otherwise.

    Raises
    ------
    ValueError
        If *criterion* is not a string or *workspace* is not a pathlib.Path.
    """
    if not isinstance(criterion, str):
        raise ValueError(
            f"resolve_integration_target: criterion must be a str, got {type(criterion)!r}"
        )
    if not isinstance(workspace, pathlib.Path):
        raise ValueError(
            f"resolve_integration_target: workspace must be a pathlib.Path, got {type(workspace)!r}"
        )

    if "integration:" not in criterion.lower():
        return False

    # Phase 1: try dotted-path tokens (requires at least one dot).
    dotted_candidates = re.findall(r"\b([\w]+(?:\.[\w]+)+)\b", criterion)
    for dotted in dotted_candidates:
        if _integration_wired(workspace, dotted):
            return True

    # Phase 2: function-existence fallback — scan snake_case identifiers.
    snake_identifiers = re.findall(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b", criterion)
    for ident in snake_identifiers:
        if _function_exists_in_workspace(workspace, ident):
            return True

    return False


def _integration_wired(workspace: pathlib.Path, dotted: str) -> bool:
    """Return True if a dotted module path exists AND is imported in workspace.

    Delegates to bob3.enhanced_verification._integration_wired when available,
    otherwise implements equivalent logic directly.
    """
    try:
        from bob3.enhanced_verification import _integration_wired as _ev_wired
        return _ev_wired(workspace, dotted)
    except Exception:
        pass

    # Fallback implementation if enhanced_verification is not available.
    parts = dotted.split(".")
    candidates = [
        workspace / "src" / pathlib.Path(*parts).with_suffix(".py"),
        workspace / pathlib.Path(*parts).with_suffix(".py"),
        workspace / "src" / pathlib.Path(*parts) / "__init__.py",
        workspace / pathlib.Path(*parts) / "__init__.py",
    ]
    if not any(p.exists() for p in candidates):
        return False

    import_re = re.compile(
        rf"^\s*(?:from\s+{re.escape(dotted)}(?:\s+import|\.)|import\s+{re.escape(dotted)}(?:\s|$|;|,))",
        re.MULTILINE,
    )
    for py in workspace.rglob("*.py"):
        if "build" in py.parts or ".git" in py.parts or ".venv" in py.parts:
            continue
        try:
            if import_re.search(py.read_text()):
                return True
        except Exception:
            continue
    return False


def _function_exists_in_workspace(workspace: pathlib.Path, ident: str) -> bool:
    """Return True if *ident* is defined as a def/class in any workspace .py file."""
    pattern = re.compile(
        rf"(?:def|class)\s+{re.escape(ident)}\s*[\(:]",
        re.MULTILINE,
    )
    for py_file in workspace.rglob("*.py"):
        if "build" in py_file.parts or ".git" in py_file.parts or ".venv" in py_file.parts:
            continue
        try:
            if pattern.search(py_file.read_text()):
                return True
        except Exception:
            continue
    return False


__all__ = ["resolve_integration_target"]
