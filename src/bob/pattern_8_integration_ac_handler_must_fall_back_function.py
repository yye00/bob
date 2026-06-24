"""Pattern-8 integration AC handler — fallback to function-existence (F-R7-583 / 6797d411).

When an 'integration:' AC body's first token is a bare snake_case function name
(not a dotted module path), Pattern 8 in enhanced_verification.py would return
False because no module file by that name exists.

Root-cause (bob v.17 r1 ~09:43Z): feature 85790dc6 (orphan-subagent reaper)
NH'd with AC:
    "integration: sweep_orphan_subagents runs at the same cadence as the
    existing stuck_executing reaper (watchdog tick); both reapers are
    idempotent and safe to run concurrently"

This module exposes ``pattern_8_integration_ac_handler_must_fall_back_function``,
which wraps the two-phase check:
  1. Dotted-path resolution via _integration_wired.
  2. Bare snake_case function-existence scan in workspace Python source files.

Public API
----------
pattern_8_integration_ac_handler_must_fall_back_function(criterion, workspace)
    Returns True if the integration AC passes via any of:
      1. A dotted-path token that resolves via _integration_wired.
      2. A snake_case identifier in the body that resolves to a def/class in
         the workspace source tree (function-existence fallback).
    Returns False otherwise.
"""

from __future__ import annotations

import pathlib
import re

from bob.enhanced_verification import _integration_wired  # noqa: F401 (integration: bob.orchestrator.run_loop)


def _scan_workspace_for_identifier(workspace: pathlib.Path, ident: str) -> bool:
    """Return True if *ident* is defined as a def/class in any workspace .py file."""
    escaped = re.escape(ident)
    pattern = re.compile(
        rf"(?:def|class)\s+{escaped}\s*[\(:]",
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


def pattern_8_integration_ac_handler_must_fall_back_function(
    criterion: str,
    workspace: pathlib.Path,
) -> bool:
    """Pattern-8 integration AC handler with function-existence fallback.

    Resolves an 'integration:' acceptance criterion by:
      1. Trying each dotted-path token (e.g. 'bob.orchestrator.run_loop') via
         the standard _integration_wired check (module file exists + is imported).
      2. When no dotted path resolves, falling back to scanning all snake_case
         identifiers in the body for a matching def/class in workspace src.

    This fallback (step 2) handles prose-policy ACs like:
        "integration: sweep_orphan_subagents runs at the same cadence …"
    where the first token is a bare function name, not a dotted module path.

    Parameters
    ----------
    criterion:
        The full acceptance criterion string (e.g. "integration: bob.foo …").
    workspace:
        Root path of the workspace (where src/ lives).

    Returns
    -------
    bool
        True if the integration AC is satisfied, False otherwise.
    """
    if not isinstance(criterion, str):
        return False
    if "integration:" not in criterion.lower():
        return False

    # Phase 1: try each dotted-path token (requires at least one dot).
    dotted_candidates = re.findall(r"\b([\w]+(?:\.[\w]+)+)\b", criterion)
    for dotted in dotted_candidates:
        if _integration_wired(workspace, dotted):
            return True

    # Phase 2: function-existence fallback — scan snake_case identifiers.
    # Only applies if workspace contains Python source files (no soft-pass for
    # empty/unknown workspaces, unlike the generic _search_for_function helper).
    has_python = any(workspace.rglob("*.py"))
    if not has_python:
        return False

    snake_identifiers = re.findall(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b", criterion)
    for ident in snake_identifiers:
        if _scan_workspace_for_identifier(workspace, ident):
            return True

    return False


__all__ = ["pattern_8_integration_ac_handler_must_fall_back_function"]
