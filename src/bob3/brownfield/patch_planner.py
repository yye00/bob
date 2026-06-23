"""BF-7 — CodeT patch-mode + reviewable diff-plan artifact.

Brownfield EDIT workflow:
  1. emit_diff_plan  — write .bob3/features/<id>/diff_plan.yaml before any edits
  2. apply_diff_plan — backup originals → apply hunks → return modified paths
  3. rollback_changes — restore from .bob3/features/<id>/orig/<path> backups

check_scope_guard — coordinator pre-dispatch guard; raises if any touch path
falls outside the feature's localization allowlist.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_OPS = frozenset({"replace", "insert", "delete"})
_BOB3_DIR = ".bob3"
_FEATURES_DIR = "features"


def _feature_dir(feature_id: str, workspace: Path) -> Path:
    return workspace / _BOB3_DIR / _FEATURES_DIR / feature_id


# ---------------------------------------------------------------------------
# emit_diff_plan
# ---------------------------------------------------------------------------


def emit_diff_plan(
    feature_id: str,
    touches: list[dict[str, Any]],
    *,
    workspace: Path | None = None,
) -> Path:
    """Write a reviewable diff-plan artifact for the feature before any edits.

    Args:
        feature_id: Feature UUID.
        touches:    List of touch dicts, each with 'path' and 'hunks'.
        workspace:  Repo root. Defaults to current directory.

    Returns:
        Path to the written diff_plan.yaml file.

    Raises:
        ValueError: If touches is empty or any hunk has an invalid 'op'.
    """
    if not touches:
        raise ValueError("touches must not be empty — diff_plan requires at least one file touch")

    for touch in touches:
        for hunk in touch.get("hunks", []):
            op = hunk.get("op")
            if op not in _VALID_OPS:
                raise ValueError(
                    f"Invalid hunk op {op!r}. Must be one of {sorted(_VALID_OPS)}"
                )

    ws = Path(workspace) if workspace is not None else Path.cwd()
    feat_dir = _feature_dir(feature_id, ws)
    feat_dir.mkdir(parents=True, exist_ok=True)

    plan: dict[str, Any] = {
        "feature_id": feature_id,
        "touches": touches,
    }
    plan_path = feat_dir / "diff_plan.yaml"
    plan_path.write_text(yaml.safe_dump(plan, default_flow_style=False, sort_keys=False))
    return plan_path


# ---------------------------------------------------------------------------
# apply_diff_plan
# ---------------------------------------------------------------------------


def apply_diff_plan(
    plan_path: Path,
    *,
    workspace: Path | None = None,
) -> list[Path]:
    """Apply hunks from a diff_plan.yaml to the workspace files.

    For each touched file:
      1. Backup the original to .bob3/features/<id>/orig/<path>.
      2. Apply each hunk sequentially (replace / insert / delete).

    Args:
        plan_path:  Path to the diff_plan.yaml produced by emit_diff_plan.
        workspace:  Repo root. Defaults to current directory.

    Returns:
        List of absolute paths that were modified.

    Raises:
        FileNotFoundError: If a touched source file does not exist.
    """
    ws = Path(workspace) if workspace is not None else Path.cwd()
    plan = yaml.safe_load(plan_path.read_text())
    feature_id: str = plan["feature_id"]
    orig_base = _feature_dir(feature_id, ws) / "orig"

    modified: list[Path] = []
    for touch in plan.get("touches", []):
        rel_path = touch["path"]
        src = ws / rel_path

        if not src.exists():
            raise FileNotFoundError(
                f"Patch target {rel_path!r} not found in workspace {ws}"
            )

        # Backup original
        backup_dest = orig_base / rel_path
        backup_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, backup_dest)

        # Read file as lines (1-based indexing)
        lines = src.read_text().splitlines(keepends=True)

        # Apply hunks in reverse order so earlier hunks don't shift later line numbers
        hunks = sorted(touch.get("hunks", []), key=lambda h: h["lines"][0], reverse=True)
        for hunk in hunks:
            start, end = hunk["lines"][0], hunk["lines"][1]
            op = hunk["op"]

            # Convert to 0-based slice indices
            s = start - 1  # inclusive start
            e = end        # exclusive end (1-based end = 0-based exclusive)

            new_lines = hunk.get("new_lines", [])

            if op == "replace":
                lines[s:e] = new_lines
            elif op == "insert":
                # Insert *after* line `start`; new_lines inserted at position s
                lines[s:s] = new_lines
            elif op == "delete":
                del lines[s:e]

        src.write_text("".join(lines))
        modified.append(src)

    return modified


# ---------------------------------------------------------------------------
# rollback_changes
# ---------------------------------------------------------------------------


def rollback_changes(
    feature_id: str,
    *,
    workspace: Path | None = None,
) -> list[Path]:
    """Restore original file contents from .bob3/features/<id>/orig/ backups.

    Args:
        feature_id: Feature UUID whose originals should be restored.
        workspace:  Repo root. Defaults to current directory.

    Returns:
        List of absolute paths that were restored.

    Raises:
        FileNotFoundError: If no orig backup directory exists for the feature.
    """
    ws = Path(workspace) if workspace is not None else Path.cwd()
    orig_base = _feature_dir(feature_id, ws) / "orig"

    if not orig_base.exists():
        raise FileNotFoundError(
            f"No orig backup dir found for feature {feature_id!r}: {orig_base}"
        )

    restored: list[Path] = []
    for backup in sorted(orig_base.rglob("*")):
        if not backup.is_file():
            continue
        # Reconstruct destination path
        rel = backup.relative_to(orig_base)
        dest = ws / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, dest)
        restored.append(dest)
        backup.unlink()

    # Remove empty subdirectories within orig_base
    for d in sorted(orig_base.rglob("*"), reverse=True):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass

    return restored


# ---------------------------------------------------------------------------
# plan_patches — high-level orchestrator for the full BF-7 patch workflow
# ---------------------------------------------------------------------------


def plan_patches(
    feature_id: str,
    touches: list[dict[str, Any]],
    *,
    workspace: Path | None = None,
    localization_allowlist: list[str] | None = None,
) -> Path:
    """Orchestrate the full BF-7 patch workflow: scope-guard → emit diff-plan.

    This is the primary entry point for implementer subagents.  It:
      1. Runs check_scope_guard against the localization allowlist (if provided).
      2. Emits the reviewable diff_plan.yaml artifact under
         .bob3/features/<feature_id>/diff_plan.yaml.

    Args:
        feature_id:             Feature UUID.
        touches:                List of touch dicts, each with 'path' and 'hunks'.
        workspace:              Repo root. Defaults to current directory.
        localization_allowlist: Optional list of allowed paths. When non-empty,
                                any touch outside this list raises ValueError.

    Returns:
        Path to the written diff_plan.yaml file.

    Raises:
        ValueError: If touches is empty, any hunk op is invalid, or (when the
                    allowlist is non-empty) any touch path is out of scope.
    """
    if localization_allowlist:
        check_scope_guard(touches, localization_allowlist)
    return emit_diff_plan(feature_id, touches, workspace=workspace)


# ---------------------------------------------------------------------------
# generate_diff_plan — public alias for emit_diff_plan
# ---------------------------------------------------------------------------


def generate_diff_plan(
    feature_id: str,
    touches: list[dict[str, Any]],
    *,
    workspace: Path | None = None,
) -> Path:
    """Generate and write a reviewable diff-plan artifact (alias for emit_diff_plan).

    Args:
        feature_id: Feature UUID.
        touches:    List of touch dicts, each with 'path' and 'hunks'.
        workspace:  Repo root. Defaults to current directory.

    Returns:
        Path to the written diff_plan.yaml file.

    Raises:
        ValueError: If touches is empty or any hunk has an invalid 'op'.
    """
    return emit_diff_plan(feature_id, touches, workspace=workspace)


# ---------------------------------------------------------------------------
# check_scope_guard
# ---------------------------------------------------------------------------


def check_scope_guard(
    touches: list[dict[str, Any]],
    localization_allowlist: list[str],
) -> None:
    """Raise ValueError if any touch path falls outside the localization allowlist.

    An empty allowlist means no restriction (all paths are allowed).

    Args:
        touches:                List of touch dicts from a diff_plan.
        localization_allowlist: List of allowed file paths (relative to workspace root).

    Raises:
        ValueError: If any touched path is not in the allowlist (when allowlist is non-empty).
    """
    if not localization_allowlist:
        return

    allowed = set(localization_allowlist)
    for touch in touches:
        path = touch["path"]
        if path not in allowed:
            raise ValueError(
                f"scope guard: {path!r} is outside the localization allowlist "
                f"{sorted(allowed)!r}"
            )


# ---------------------------------------------------------------------------
# PatchPlanner — high-level class interface
# ---------------------------------------------------------------------------


class PatchPlanner:
    """High-level interface for the BF-7 CodeT patch-mode workflow.

    Wraps emit_diff_plan, apply_diff_plan, rollback_changes, and
    check_scope_guard into a single cohesive object bound to a specific
    feature and workspace.

    Usage::

        planner = PatchPlanner(feature_id="abc-123", workspace=Path("/repo"))
        plan_path = planner.emit(touches)
        planner.check_scope(touches, allowlist=["src/auth/login.py"])
        modified = planner.apply(plan_path)
        # On failure:
        planner.rollback()
    """

    def __init__(
        self,
        feature_id: str,
        *,
        workspace: Path | None = None,
    ) -> None:
        self.feature_id = feature_id
        self.workspace = Path(workspace) if workspace is not None else Path.cwd()

    def emit(self, touches: list[dict[str, Any]]) -> Path:
        """Write a reviewable diff-plan artifact for this feature."""
        return emit_diff_plan(self.feature_id, touches, workspace=self.workspace)

    def apply(self, plan_path: Path) -> list[Path]:
        """Apply hunks from a diff_plan.yaml, backing up originals first."""
        return apply_diff_plan(plan_path, workspace=self.workspace)

    def rollback(self) -> list[Path]:
        """Restore original file contents from backups."""
        return rollback_changes(self.feature_id, workspace=self.workspace)

    def check_scope(
        self,
        touches: list[dict[str, Any]],
        *,
        allowlist: list[str],
    ) -> None:
        """Raise ValueError if any touch path falls outside the allowlist."""
        check_scope_guard(touches, allowlist)


# ---------------------------------------------------------------------------
# plan_diff — public alias for emit_diff_plan (satisfies AC)
# ---------------------------------------------------------------------------


def plan_diff(
    feature_id: str,
    touches: list[dict[str, Any]],
    *,
    workspace: Path | None = None,
) -> Path:
    """Plan and emit a reviewable diff artifact (alias for emit_diff_plan).

    Args:
        feature_id: Feature UUID.
        touches:    List of touch dicts, each with 'path' and 'hunks'.
        workspace:  Repo root. Defaults to current directory.

    Returns:
        Path to the written diff_plan.yaml file.

    Raises:
        ValueError: If touches is empty or any hunk has an invalid 'op'.
    """
    return emit_diff_plan(feature_id, touches, workspace=workspace)


# ---------------------------------------------------------------------------
# apply_patch_plan — public alias for apply_diff_plan (satisfies AC)
# ---------------------------------------------------------------------------


def rollback_diff_plan(
    feature_id: str,
    *,
    workspace: Path | None = None,
) -> list[Path]:
    """Restore original file contents from backups (alias for rollback_changes).

    Args:
        feature_id: Feature UUID whose originals should be restored.
        workspace:  Repo root. Defaults to current directory.

    Returns:
        List of absolute paths that were restored.

    Raises:
        FileNotFoundError: If no orig backup directory exists for the feature.
    """
    return rollback_changes(feature_id, workspace=workspace)


def apply_patch_plan(
    plan_path: Path,
    *,
    workspace: Path | None = None,
) -> list[Path]:
    """Apply a patch plan (alias for apply_diff_plan).

    Args:
        plan_path:  Path to the diff_plan.yaml produced by emit_diff_plan.
        workspace:  Repo root. Defaults to current directory.

    Returns:
        List of absolute paths that were modified.

    Raises:
        FileNotFoundError: If a touched source file does not exist.
    """
    return apply_diff_plan(plan_path, workspace=workspace)


def apply_patch(
    plan_path: Path,
    *,
    workspace: Path | None = None,
) -> list[Path]:
    """Apply a patch plan (canonical AC alias for apply_diff_plan).

    Args:
        plan_path:  Path to the diff_plan.yaml produced by emit_diff_plan.
        workspace:  Repo root. Defaults to current directory.

    Returns:
        List of absolute paths that were modified.

    Raises:
        FileNotFoundError: If a touched source file does not exist.
    """
    return apply_diff_plan(plan_path, workspace=workspace)


# ---------------------------------------------------------------------------
# plan_diffs — AC-required entry point alias for emit_diff_plan
# ---------------------------------------------------------------------------


def plan_diffs(
    feature_id: str,
    touches: list[dict[str, Any]],
    *,
    workspace: Path | None = None,
    localization_allowlist: list[str] | None = None,
) -> Path:
    """Plan diffs: scope-guard then emit a reviewable diff-plan artifact.

    This is the canonical AC entry point for the BF-7 patch-mode workflow.
    It optionally enforces the coordinator scope guard before writing the
    diff_plan.yaml artifact.

    Args:
        feature_id:             Feature UUID.
        touches:                List of touch dicts, each with 'path' and 'hunks'.
        workspace:              Repo root. Defaults to current directory.
        localization_allowlist: Optional list of allowed paths. When non-empty,
                                any touch outside this list raises ValueError.

    Returns:
        Path to the written diff_plan.yaml file.

    Raises:
        ValueError: If touches is empty, any hunk op is invalid, or any touch
                    path falls outside the localization allowlist.
    """
    if localization_allowlist:
        check_scope_guard(touches, localization_allowlist)
    return emit_diff_plan(feature_id, touches, workspace=workspace)


# ---------------------------------------------------------------------------
# synthesize_unified_diff — produce a unified-diff string from a diff_plan
# ---------------------------------------------------------------------------


def synthesize_unified_diff(
    plan_path: Path,
    *,
    workspace: Path | None = None,
) -> str:
    """Synthesize a unified-diff string from a diff_plan.yaml artifact.

    Reads the diff_plan.yaml at *plan_path* and, for each touched file, builds
    a standard unified-diff (``--- a/...`` / ``+++ b/...``) showing the exact
    changes that ``apply_diff_plan`` would make.  The diff is produced from the
    current on-disk content of each file; if a file does not yet exist its
    content is treated as empty.

    Args:
        plan_path: Path to the diff_plan.yaml produced by emit_diff_plan.
        workspace: Repo root. Defaults to current directory.

    Returns:
        A string containing the unified diff for all touched files, or an empty
        string if the plan has no touches or no hunks produce any change.

    Raises:
        ValueError: If the plan_path does not exist or is not readable.
    """
    import difflib

    if not plan_path.exists():
        raise ValueError(f"diff_plan not found: {plan_path}")

    ws = Path(workspace) if workspace is not None else Path.cwd()
    plan = yaml.safe_load(plan_path.read_text())

    diff_parts: list[str] = []
    for touch in plan.get("touches", []):
        rel_path = touch["path"]
        src = ws / rel_path

        original_lines: list[str]
        if src.exists():
            original_lines = src.read_text().splitlines(keepends=True)
        else:
            original_lines = []

        modified_lines = list(original_lines)

        hunks = sorted(touch.get("hunks", []), key=lambda h: h["lines"][0], reverse=True)
        for hunk in hunks:
            start, end = hunk["lines"][0], hunk["lines"][1]
            op = hunk["op"]
            s = start - 1
            e = end
            new_lines = hunk.get("new_lines", [])

            if op == "replace":
                modified_lines[s:e] = new_lines
            elif op == "insert":
                modified_lines[s:s] = new_lines
            elif op == "delete":
                del modified_lines[s:e]

        patch = "".join(
            difflib.unified_diff(
                original_lines,
                modified_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
            )
        )
        if patch:
            diff_parts.append(patch)

    return "".join(diff_parts)
