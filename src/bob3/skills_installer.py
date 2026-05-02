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
import shutil
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


def _is_bob3_managed(dest: Path, bundled_skills_dir: Path) -> bool:
    """Return True if ``dest`` is a bob3-managed install (symlink or copy).

    A path counts as bob3-managed if:
    - It is a symlink that resolves INTO the current bob3 bundled
      skills directory (i.e. a link we installed). User-created
      symlinks pointing at their own external skill dir are NOT
      considered ours.
    - It is a real directory containing the ``.bob3-installed`` marker
      file (copy-fallback installs we own), provided the skill name
      matches a bundled skill.

    For safety, we err on the side of *not* deleting unless we are sure.
    """
    if dest.is_symlink():
        return _symlink_resolves_into(dest, bundled_skills_dir)
    marker = dest / ".bob3-installed"
    if dest.is_dir() and marker.is_file():
        # Cross-check that the skill name matches a bundled skill.
        bundled = bundled_skills_dir / dest.name
        return bundled.is_dir() and (bundled / "SKILL.md").is_file()
    return False


def _symlink_resolves_into(dest: Path, expected_dir: Path) -> bool:
    """Return True iff ``dest`` is a symlink resolving inside ``expected_dir``.

    Uses ``resolve(strict=True)`` so a broken symlink raises and we
    return False. We also require the resolved target to live under the
    given bob3 bundled skills dir so an old workspace pointing at a
    deleted bob3 install is detected as stale.
    """
    if not dest.is_symlink():
        return False
    try:
        resolved = dest.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    try:
        resolved.relative_to(expected_dir.resolve())
    except ValueError:
        return False
    return resolved.is_dir() and (resolved / "SKILL.md").is_file()


def _remove_dest(dest: Path) -> bool:
    """Best-effort removal of ``dest`` (symlink or directory).

    Returns True on success, False on failure (with a logged warning).
    """
    try:
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)
        return True
    except OSError as exc:
        logger.warning("Could not remove %s: %s", dest, exc)
        return False


def _verify_install(dest: Path) -> bool:
    """Verify that ``dest`` resolves to a directory containing SKILL.md."""
    try:
        resolved = dest.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    if not resolved.is_dir():
        return False
    return (resolved / "SKILL.md").is_file()


def _install_one(skill_src: Path, dest: Path) -> bool:
    """Install a single skill at ``dest`` from ``skill_src``.

    Tries a symlink first, falls back to a directory copy. Verifies the
    install resolves cleanly and contains a SKILL.md before returning
    True. On failure, attempts to clean up and returns False.
    """
    # Attempt 1: symlink
    try:
        dest.symlink_to(skill_src.resolve(), target_is_directory=True)
    except OSError as exc:
        logger.debug("Symlink failed (%s); falling back to copy for %s", exc, dest)
    else:
        if _verify_install(dest):
            return True
        # Symlink created but doesn't resolve to a usable directory —
        # remove and fall through to copy.
        logger.warning(
            "Symlink at %s did not resolve to a readable skill dir; falling back to copy",
            dest,
        )
        _remove_dest(dest)

    # Attempt 2: directory copy
    try:
        shutil.copytree(skill_src, dest)
        # Drop a marker so we know this is a bob3-managed copy and may
        # safely refresh it on subsequent runs.
        try:
            (dest / ".bob3-installed").write_text("bob3\n")
        except OSError:
            # Non-fatal: marker is a nice-to-have. If we can't write it
            # the directory is still usable; we just won't auto-refresh.
            logger.debug("Could not write .bob3-installed marker in %s", dest)
    except OSError as copy_exc:
        logger.warning(
            "Could not install skill %s to %s: %s", skill_src.name, dest, copy_exc
        )
        return False

    if not _verify_install(dest):
        logger.warning("Copied skill at %s did not verify; removing", dest)
        _remove_dest(dest)
        return False
    return True


def install_skills_to_workspace(
    workspace: str | Path, *, idempotent: bool = True
) -> list[str]:
    """Install all bob3 skills into ``<workspace>/.claude/skills/``.

    Each skill is symlinked if possible (to stay in sync with bob3
    upgrades); falls back to a directory copy if symlinking fails (e.g.
    Windows without admin, or a filesystem that doesn't support them).

    Returns the list of skill names installed. Idempotent semantics
    (when ``idempotent=True``):

    - First call: creates symlinks (or copies) for every bundled skill.
    - Subsequent calls: refreshes any stale entries (broken symlinks or
      symlinks pointing outside the current bob3 bundled skills dir),
      and leaves working entries alone.
    - If ``dest`` is a real directory with no ``.bob3-installed`` marker
      it's treated as user-owned and never modified.

    A symlink that already resolves into the current bob3 bundled skills
    dir and contains SKILL.md is considered already-installed and is
    not re-created (avoids inotify churn for watchers).

    After creating each symlink the function calls
    ``dest.resolve(strict=True)`` and verifies ``(dest / 'SKILL.md')``
    is a regular file. If verification fails, falls back to a
    ``shutil.copytree`` copy; if that also fails, the skill is logged
    and skipped.
    """
    workspace_path = Path(workspace).resolve()
    target_dir = workspace_path / ".claude" / "skills"
    target_dir.mkdir(parents=True, exist_ok=True)

    source_dir = get_bundled_skills_dir()
    if not source_dir.is_dir():
        logger.warning("No bundled skills dir at %s; nothing to install", source_dir)
        return []

    installed: list[str] = []
    for skill_src in sorted(source_dir.iterdir()):
        if not skill_src.is_dir():
            continue
        if not (skill_src / "SKILL.md").is_file():
            continue

        dest = target_dir / skill_src.name

        # Decide whether to refresh, reuse, or skip.
        needs_install = True
        if dest.is_symlink():
            if idempotent and _symlink_resolves_into(dest, source_dir):
                # Already a working bob3 symlink — leave it alone.
                installed.append(skill_src.name)
                needs_install = False
            else:
                # Stale: broken target, or pointing at a moved/deleted
                # bob3 install. Replace it.
                if not _remove_dest(dest):
                    logger.warning(
                        "Stale symlink at %s could not be removed; skipping %s",
                        dest,
                        skill_src.name,
                    )
                    continue
        elif dest.exists():
            if dest.is_dir() and _is_bob3_managed(dest, source_dir):
                # A previous copy-install we own — refresh it.
                if not _remove_dest(dest):
                    logger.warning(
                        "Could not refresh bob3 copy at %s; skipping %s",
                        dest,
                        skill_src.name,
                    )
                    continue
            else:
                # User-owned directory or file: never touch.
                logger.debug(
                    "Skipping %s; existing entry is user-owned (not bob3-managed)",
                    dest,
                )
                continue

        if needs_install:
            if _install_one(skill_src, dest):
                installed.append(skill_src.name)

    logger.info("Installed %d skills into %s", len(installed), target_dir)
    return installed


def verify_skills_integrity(workspace: str | Path) -> list[str]:
    """Audit ``<workspace>/.claude/skills/`` for tampering and reinstall.

    Sub-agents run in the workspace with ``permission_mode='bypassPermissions'``
    and ``cwd=<workspace>``. That means a sub-agent can write into
    ``.claude/skills/`` — including replacing one of bob3's symlinks with a
    real directory containing a malicious ``SKILL.md``. A future sub-agent
    spawned in the same workspace would then load the attacker's SKILL.md
    instead of bob3's.

    This function is the defense-in-depth audit step. For every bundled
    bob3 skill it checks:

    1. The destination at ``<workspace>/.claude/skills/<name>`` exists and
       is a symlink.
    2. The symlink resolves into the *current* bob3 bundled skills
       directory (the one returned by :func:`get_bundled_skills_dir`).

    Anything that fails either check is treated as tampering: a security
    warning is logged identifying the skill and the actual on-disk state,
    and the entry is force-replaced with a fresh symlink to the canonical
    bundled skill (delegating to :func:`install_skills_to_workspace` after
    removing the offending entry).

    Returns the list of skill names that were force-replaced. An empty
    list means everything looked clean.

    This is intended to be called from the sub-agent spawn path
    (``build_sub_agent_options``) immediately before each ``query()`` call
    so a poisoned skill cannot persist across sub-agents.
    """
    workspace_path = Path(workspace).resolve()
    target_dir = workspace_path / ".claude" / "skills"
    source_dir = get_bundled_skills_dir()

    if not source_dir.is_dir():
        # Nothing to audit against.
        return []

    if not target_dir.is_dir():
        # No skills installed yet; integrity check is a no-op. The caller
        # (build_sub_agent_options) will call install_skills_to_workspace
        # separately; this function only detects *tampering*.
        return []

    tampered: list[str] = []
    for skill_src in sorted(source_dir.iterdir()):
        if not skill_src.is_dir():
            continue
        if not (skill_src / "SKILL.md").is_file():
            continue

        name = skill_src.name
        dest = target_dir / name

        if not dest.exists() and not dest.is_symlink():
            # Skill was removed entirely from the workspace. Not strictly
            # tampering, but reinstall to restore expected behavior.
            logger.warning(
                "SECURITY: bob3 skill %r missing from %s; reinstalling",
                name,
                target_dir,
            )
            tampered.append(name)
            continue

        if not dest.is_symlink():
            # A real directory (or file) is sitting where bob3's symlink
            # should be. This is the canonical poisoning shape: a
            # sub-agent wrote SKILL.md inside a directory it created at
            # the bob3 skill name. Refuse to trust it and force-replace.
            kind = "directory" if dest.is_dir() else "file"
            logger.warning(
                "SECURITY: bob3 skill %r at %s is a %s, not a symlink — "
                "possible skill poisoning. Force-replacing with the "
                "canonical bob3 skill.",
                name,
                dest,
                kind,
            )
            _remove_dest(dest)
            tampered.append(name)
            continue

        # It's a symlink — but does it resolve into THIS bob3 install?
        if not _symlink_resolves_into(dest, source_dir):
            try:
                actual = str(dest.resolve(strict=False))
            except (OSError, RuntimeError):
                actual = "<unresolvable>"
            logger.warning(
                "SECURITY: bob3 skill %r at %s resolves to %s, which is "
                "outside the current bob3 bundled skills dir %s — "
                "possible skill poisoning. Force-replacing.",
                name,
                dest,
                actual,
                source_dir,
            )
            _remove_dest(dest)
            tampered.append(name)
            continue

    if tampered:
        # Force a reinstall pass so the replaced skills are restored.
        # ``install_skills_to_workspace`` is idempotent, so untampered
        # skills are unaffected.
        install_skills_to_workspace(workspace_path)
        logger.warning(
            "SECURITY: force-replaced %d bob3 skill(s) after integrity "
            "check: %s",
            len(tampered),
            tampered,
        )

    return tampered


def clean_workspace_skills(workspace: str | Path) -> list[str]:
    """Remove only bob3-installed skills from a workspace.

    Walks ``<workspace>/.claude/skills/`` and removes only entries that
    are bob3-managed, as determined by :func:`_is_bob3_managed`:

    - symlinks that resolve into the current bob3 bundled skills
      directory (i.e. links we created), and
    - real directories that contain the ``.bob3-installed`` marker
      file (copy-fallback installs we own).

    User-created entries — including symlinks pointing at the user's
    own skills outside the bob3 bundled tree, and plain directories
    without the marker — are left alone.

    Returns the list of skill names that were removed.
    """
    workspace_path = Path(workspace).resolve()
    target_dir = workspace_path / ".claude" / "skills"
    if not target_dir.is_dir():
        return []

    source_dir = get_bundled_skills_dir()

    removed: list[str] = []
    for entry in sorted(target_dir.iterdir()):
        if _is_bob3_managed(entry, source_dir):
            if _remove_dest(entry):
                removed.append(entry.name)
        # else: user-owned, skip
    logger.info("Removed %d bob3 skills from %s", len(removed), target_dir)
    return removed
