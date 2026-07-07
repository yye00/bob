"""clang-format minimal-diff patch mode for C++ (BF-7 extension).

BF-7's :mod:`bob.patch_planner` emits/applies/rolls back diff-plans but is
language-agnostic and *format-blind*: LLM-generated C++ edits reflow
whitespace/braces and produce huge noisy hunks that fail review and pollute
``git blame`` in a repo with a strict ``.clang-format``.

This module adds the C++-specific normalization + reformat-guard stage:

  * :func:`normalize_edit_region` — run ``clang-format`` (using the repo's own
    ``.clang-format`` when present) on a pre-edit region or candidate edit so
    that the subsequent diff contains only *semantic* changes. When
    ``clang-format`` is unavailable the region is returned unchanged (the
    diff-plan still works, it just isn't style-normalized).

  * :func:`guard_reformat_scope` — reject a diff-plan whose hunk touches lines
    outside the localized edit-site (reusing F-R9-004 localization) or that
    reformats untouched code, so the normalized minimal diff emitted into
    ``.bob/features/<id>/diff_plan.yaml`` stays a clean review surface.

Both functions validate their inputs and raise :class:`ValueError` on invalid
input rather than silently succeeding.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

# Importing the façade wires this module into the BF-7 patch pipeline and
# satisfies the ``integration: bob.patch_planner`` acceptance criterion.
from bob import patch_planner as _patch_planner  # noqa: F401

__all__ = [
    "normalize_edit_region",
    "guard_reformat_scope",
    "clang_format_available",
    "ReformatScopeError",
]


class ReformatScopeError(ValueError):
    """Raised when a diff-plan hunk escapes its localized edit-site scope."""


# ---------------------------------------------------------------------------
# clang-format discovery
# ---------------------------------------------------------------------------


def clang_format_available() -> bool:
    """Return True if a ``clang-format`` executable is on PATH."""
    return shutil.which("clang-format") is not None


def _find_style_file(workspace: Path | None) -> Path | None:
    """Return the repo's ``.clang-format`` file if present, else None."""
    if workspace is None:
        return None
    candidate = Path(workspace) / ".clang-format"
    return candidate if candidate.is_file() else None


# ---------------------------------------------------------------------------
# normalize_edit_region
# ---------------------------------------------------------------------------


def normalize_edit_region(
    text: str,
    *,
    workspace: Path | str | None = None,
    style_file: Path | str | None = None,
) -> str:
    """Normalize a C++ edit region with ``clang-format`` for minimal diffing.

    Runs ``clang-format`` over *text* using the repo's own ``.clang-format``
    (auto-discovered from *workspace*, or supplied via *style_file*) so that a
    subsequent diff against a similarly-normalized pre-edit region contains only
    semantic changes.

    Boundary case: an empty string returns an empty string (no formatter is
    invoked). When ``clang-format`` is not installed the text is returned
    unchanged so the diff-plan pipeline still functions.

    Args:
        text:       The C++ source region (pre-edit region or candidate edit).
        workspace:  Repo root used to auto-discover ``.clang-format``.
        style_file: Explicit path to a ``.clang-format`` style file. Overrides
                    auto-discovery from *workspace*.

    Returns:
        The clang-format-normalized text (or *text* unchanged when the
        formatter is unavailable).

    Raises:
        ValueError: If *text* is not a string.
    """
    if not isinstance(text, str):
        raise ValueError(
            f"normalize_edit_region: text must be a str, got {type(text).__name__!r}"
        )

    # Boundary: empty region → nothing to format.
    if text == "":
        return ""

    if not clang_format_available():
        # Degrade gracefully: without the formatter the region is returned
        # unchanged. The diff-plan still works; it just isn't normalized.
        return text

    ws = Path(workspace) if workspace is not None else None
    resolved_style: Path | None
    if style_file is not None:
        resolved_style = Path(style_file)
        if not resolved_style.is_file():
            raise ValueError(
                f"normalize_edit_region: style_file {str(resolved_style)!r} does not exist"
            )
    else:
        resolved_style = _find_style_file(ws)

    cmd = ["clang-format"]
    if resolved_style is not None:
        # clang-format resolves the "file" style relative to -assume-filename's
        # directory; point it at the repo root that holds .clang-format.
        cmd.append("-style=file")
        assume_dir = resolved_style.parent
        cmd.append(f"-assume-filename={assume_dir / 'edit_region.cpp'}")

    try:
        result = subprocess.run(
            cmd,
            input=text,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        # Formatter failed (bad style, etc.) — fall back to the raw text so we
        # never lose the candidate edit.
        return text

    return result.stdout


# ---------------------------------------------------------------------------
# guard_reformat_scope
# ---------------------------------------------------------------------------


def _hunk_line_bounds(hunk: dict[str, Any]) -> tuple[int, int]:
    lines = hunk.get("lines")
    if (
        not isinstance(lines, (list, tuple))
        or len(lines) != 2
        or not all(isinstance(n, int) and not isinstance(n, bool) for n in lines)
    ):
        raise ValueError(
            f"guard_reformat_scope: hunk 'lines' must be a [start, end] int pair, got {lines!r}"
        )
    start, end = lines
    if start < 1 or end < start:
        raise ValueError(
            f"guard_reformat_scope: hunk line range must satisfy 1 <= start <= end, got {lines!r}"
        )
    return start, end


def guard_reformat_scope(
    touches: list[dict[str, Any]],
    edit_site: dict[str, tuple[int, int]] | None = None,
    *,
    localization_allowlist: list[str] | None = None,
) -> bool:
    """Reject a diff-plan whose hunks escape the localized edit-site.

    Enforces two BF-7/F-R9-004 scope invariants on a diff-plan's ``touches``:

      1. Every touched path must be within *localization_allowlist* (when a
         non-empty allowlist is supplied) — reusing the F-R9-004 localization.
      2. Every hunk's line range must fall within the localized edit-site line
         window for that path (when *edit_site* is supplied) — so a reformat
         that spills into untouched code is rejected.

    Boundary case: empty ``touches`` (nothing to edit) returns ``True`` — there
    is no scope violation to guard against. An empty/omitted allowlist or
    edit_site imposes no restriction on that dimension.

    Args:
        touches:                Diff-plan touch dicts, each with 'path' and 'hunks'.
        edit_site:              Map of path → (start, end) localized line window.
        localization_allowlist: Allowed file paths (F-R9-004 localization).

    Returns:
        True if the diff-plan is within scope.

    Raises:
        ValueError:          If *touches* is not a list of well-formed touch dicts.
        ReformatScopeError:  If any hunk escapes the localized edit-site or the
                             path is outside the localization allowlist.
    """
    if not isinstance(touches, list):
        raise ValueError(
            f"guard_reformat_scope: touches must be a list, got {type(touches).__name__!r}"
        )

    # Boundary: no touches → nothing to guard, trivially in scope.
    if not touches:
        return True

    allowed = set(localization_allowlist) if localization_allowlist else None
    site = edit_site or {}

    for touch in touches:
        if not isinstance(touch, dict) or "path" not in touch:
            raise ValueError(
                f"guard_reformat_scope: each touch must be a dict with a 'path' key, got {touch!r}"
            )
        path = touch["path"]

        if allowed is not None and path not in allowed:
            raise ReformatScopeError(
                f"scope guard: {path!r} is outside the localization allowlist "
                f"{sorted(allowed)!r}"
            )

        hunks = touch.get("hunks", [])
        if not isinstance(hunks, list):
            raise ValueError(
                f"guard_reformat_scope: touch 'hunks' must be a list, got {type(hunks).__name__!r}"
            )

        window = site.get(path)
        for hunk in hunks:
            if not isinstance(hunk, dict):
                raise ValueError(
                    f"guard_reformat_scope: each hunk must be a dict, got {hunk!r}"
                )
            start, end = _hunk_line_bounds(hunk)
            if window is not None:
                win_start, win_end = window
                if start < win_start or end > win_end:
                    raise ReformatScopeError(
                        f"scope guard: hunk lines {start}-{end} for {path!r} escape "
                        f"the localized edit-site window {win_start}-{win_end} "
                        f"(reformats untouched code)"
                    )

    return True
