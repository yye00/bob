"""Sticky-completed gate for bob3.

If a feature was status='completed' in the parent generation's DB AND its
acceptance criteria still verify on disk, no evaluator FAIL or
regression-cascade vote may flip its status below 'ready'. The stamp is
reset only when a refinement attempt actually rewrites one of the AC-named
source files.

Public API
----------
should_reset_completion_stamp(feature, workspace, since_mtime) -> bool
    Returns True when the parent_completed stamp should be cleared because a
    real refinement edit touched one of the AC-named source files.

Integration: bob3.evaluator
    Import :func:`should_reset_completion_stamp` and call it after each
    refinement dispatch.  When it returns True, clear the stamp via
    :func:`bob3.orchestrator.sticky_completed.clear_stamp`.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob3.models import Feature

logger = logging.getLogger(__name__)


def should_reset_completion_stamp(
    feature: "Feature",
    *,
    workspace: pathlib.Path | None = None,
    since_mtime: float | None = None,
) -> bool:
    """Return True when the parent_completed stamp should be cleared.

    The stamp is reset only when a refinement attempt actually rewrites one
    of the AC-named source files.  This function detects such rewrites using
    a git-first strategy (``git diff --name-only HEAD~1``) and an mtime
    fallback when git is unavailable.

    Args:
        feature: The Feature model whose ACs name the source files to check.
        workspace: Workspace root used for path resolution.
            Defaults to ``pathlib.Path.cwd()``.
        since_mtime: Optional float epoch-seconds threshold for the mtime
            fallback path.  Files whose ``st_mtime`` is strictly greater than
            this value are considered modified.

    Returns:
        True  — a real edit was detected; caller should clear the stamp.
        False — no qualifying edit detected; stamp should remain.

    Raises:
        ValueError: If *feature* is None or does not have an
            ``acceptance_criteria`` attribute.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    if not hasattr(feature, "acceptance_criteria"):
        raise ValueError("feature must have an 'acceptance_criteria' attribute")

    ws = workspace or pathlib.Path.cwd()
    ac_paths = _extract_file_paths_from_acs(feature)
    if not ac_paths:
        return False

    # Git-first: check which files changed in the last commit.
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            capture_output=True,
            text=True,
            cwd=str(ws),
            timeout=10,
        )
        if result.returncode == 0:
            changed = set(result.stdout.splitlines())
            for rel in ac_paths:
                if str(rel) in changed or rel.name in changed:
                    logger.info(
                        "should_reset_completion_stamp: AC file %s changed (git); "
                        "stamp should be cleared for feature %s",
                        rel,
                        getattr(feature, "id", "?")[:8],
                    )
                    return True
            return False
    except Exception:
        pass  # git unavailable or insufficient history; fall through

    # Mtime fallback.
    if since_mtime is not None:
        for rel in ac_paths:
            abs_path = ws / rel
            try:
                if abs_path.stat().st_mtime > since_mtime:
                    logger.info(
                        "should_reset_completion_stamp: AC file %s modified after "
                        "mtime threshold; stamp should be cleared for feature %s",
                        rel,
                        getattr(feature, "id", "?")[:8],
                    )
                    return True
            except FileNotFoundError:
                pass

    return False


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_file_paths_from_acs(feature: "Feature") -> list[pathlib.Path]:
    """Return workspace-relative file paths named in the feature's ACs.

    Recognises ``File exists: <path>`` and ``pytest: <path>`` patterns.
    """
    ac_raw = getattr(feature, "acceptance_criteria", None) or "[]"
    try:
        ac_list: list[str] = json.loads(ac_raw) if isinstance(ac_raw, str) else list(ac_raw)
    except (ValueError, TypeError):
        ac_list = []

    paths: list[pathlib.Path] = []
    for criterion in ac_list:
        # "File exists: src/foo/bar.py"
        m = re.match(r"(?i)file\s+exists:\s*(.+)", criterion.strip())
        if m:
            paths.append(pathlib.Path(m.group(1).strip()))
            continue
        # "pytest: tests/test_foo.py" or "pytest: tests/test_foo.py::TestFoo"
        m = re.match(r"(?i)pytest:\s*([^\s:]+)", criterion.strip())
        if m:
            raw_path = m.group(1).strip()
            file_part = raw_path.split("::")[0]
            paths.append(pathlib.Path(file_part))

    return paths
