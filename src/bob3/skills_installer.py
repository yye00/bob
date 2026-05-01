"""Install bob3 skills into sub-agent workspaces.

Bob3 ships a set of skills at ``src/bob3/skills/``. When a sub-agent is
spawned with ``cwd=<workspace>``, Claude Code discovers skills at
``<workspace>/.claude/skills/``. This module links bob3's bundled skills
into that directory so sub-agents can find them.

Called from ``bob3 init`` (one-time per workspace) and defensively from
the sub-agent spawn path (so upgrades of bob3 pick up new skills even on
existing workspaces).
"""

from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path

logger = logging.getLogger(__name__)


def get_bundled_skills_dir() -> Path:
    """Return the filesystem path to bob3's bundled skills directory."""
    # importlib.resources.files works both for editable installs and wheels.
    skills_root = resources.files("bob3") / "skills"
    return Path(str(skills_root))


def list_bundled_skills() -> list[str]:
    """Return the names of all bob3-bundled skills."""
    skills_dir = get_bundled_skills_dir()
    if not skills_dir.is_dir():
        return []
    return sorted(
        p.name
        for p in skills_dir.iterdir()
        if p.is_dir() and (p / "SKILL.md").is_file()
    )


def install_skills_to_workspace(workspace: str | Path) -> list[str]:
    """Install all bob3 skills into ``<workspace>/.claude/skills/``.

    Each skill is symlinked if possible (to stay in sync with bob3
    upgrades); falls back to a directory copy if symlinking fails (e.g.
    Windows without admin, or a filesystem that doesn't support them).

    Returns the list of skill names installed. Idempotent: re-running
    refreshes symlinks but does not touch user-added skills that aren't
    bob3-bundled.
    """
    workspace_path = Path(workspace).resolve()
    target_dir = workspace_path / ".claude" / "skills"
    target_dir.mkdir(parents=True, exist_ok=True)

    source_dir = get_bundled_skills_dir()
    if not source_dir.is_dir():
        logger.warning("No bundled skills dir at %s; nothing to install", source_dir)
        return []

    installed: list[str] = []
    for skill_src in source_dir.iterdir():
        if not skill_src.is_dir():
            continue
        if not (skill_src / "SKILL.md").is_file():
            continue

        dest = target_dir / skill_src.name

        # Refresh: remove an existing symlink or bob3-bundled copy so we
        # always point at the currently-installed bob3 skills. Don't touch
        # user-added skills that happen to share a name but aren't from us
        # — if dest exists as a regular directory that isn't one of ours,
        # skip it.
        if dest.is_symlink():
            try:
                dest.unlink()
            except OSError as exc:
                logger.warning("Could not remove stale symlink %s: %s", dest, exc)
                continue
        elif dest.exists() and dest.is_dir():
            # Only replace if it looks like a prior bob3-installed copy
            # (heuristic: presence of SKILL.md with our matching content
            # would be too strict; instead we skip to be safe).
            logger.debug("Skipping %s; existing directory is not a symlink", dest)
            continue

        try:
            dest.symlink_to(skill_src.resolve(), target_is_directory=True)
            installed.append(skill_src.name)
        except OSError as exc:
            # Fall back to a copy if symlinks aren't supported here.
            logger.debug("Symlink failed (%s); falling back to copy for %s", exc, dest)
            import shutil
            try:
                shutil.copytree(skill_src, dest)
                installed.append(skill_src.name)
            except OSError as copy_exc:
                logger.warning(
                    "Could not install skill %s to %s: %s", skill_src.name, dest, copy_exc
                )

    logger.info("Installed %d skills into %s", len(installed), target_dir)
    return installed
