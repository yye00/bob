"""Robustness tests for ``bob.skills_installer``.

These tests cover the stale-symlink edge cases and idempotency
guarantees that ``install_skills_to_workspace`` and
``clean_workspace_skills`` must satisfy:

- Broken symlinks at the destination are detected and replaced.
- Symlinks pointing at a moved/deleted bob install are refreshed.
- User-created directories under ``.claude/skills/`` are NOT touched.
- Re-running the installer is idempotent (returns the same set, no
  unnecessary churn — symlink inode is preserved across calls).
- A write-protected destination either fails clearly or is logged
  and skipped (no exception leaks out, no stale broken symlink left
  behind).
- ``clean_workspace_skills`` removes only bob-installed skills.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from bob import skills_installer
from bob.skills_installer import (
    clean_workspace_skills,
    get_bundled_skills_dir,
    install_skills_to_workspace,
    list_bundled_skills,
    verify_skills_integrity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_bundled_skills(tmp_path, monkeypatch):
    """Create a temporary bob 'bundled skills' tree and point the
    installer at it.

    Returns a tuple ``(bundled_dir, skill_names)`` where ``bundled_dir``
    is the directory that masquerades as ``src/bob/skills`` and
    ``skill_names`` is a sorted list of the skills available there.
    """
    bundled = tmp_path / "fake_bundled" / "skills"
    bundled.mkdir(parents=True)
    names = ["alpha", "beta", "gamma"]
    for name in names:
        skill = bundled / name
        skill.mkdir()
        (skill / "SKILL.md").write_text(f"# {name}\n")
        (skill / "extra.txt").write_text("x")

    monkeypatch.setattr(
        skills_installer, "get_bundled_skills_dir", lambda: bundled
    )
    return bundled, sorted(names)


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


# ---------------------------------------------------------------------------
# Sanity
# ---------------------------------------------------------------------------


def test_installs_all_bundled_skills(fake_bundled_skills, workspace):
    bundled, names = fake_bundled_skills
    installed = install_skills_to_workspace(workspace)
    assert sorted(installed) == names
    target_dir = workspace / ".claude" / "skills"
    for name in names:
        dest = target_dir / name
        assert dest.is_symlink() or dest.is_dir()
        assert (dest / "SKILL.md").is_file()


def test_list_bundled_skills_uses_overridden_dir(fake_bundled_skills):
    _, names = fake_bundled_skills
    assert list_bundled_skills() == names


# ---------------------------------------------------------------------------
# Stale symlink handling
# ---------------------------------------------------------------------------


def test_broken_symlink_is_detected_and_replaced(fake_bundled_skills, workspace):
    bundled, _ = fake_bundled_skills
    target_dir = workspace / ".claude" / "skills"
    target_dir.mkdir(parents=True)

    # Plant a broken symlink for one of the skills, pointing at a
    # nonexistent path.
    bogus = workspace / "does_not_exist"
    broken = target_dir / "alpha"
    broken.symlink_to(bogus, target_is_directory=True)
    assert broken.is_symlink()
    # Sanity: it really is broken.
    assert not broken.exists()

    installed = install_skills_to_workspace(workspace)
    assert "alpha" in installed
    # The destination must now resolve to a readable skill dir.
    dest = target_dir / "alpha"
    resolved = dest.resolve(strict=True)
    assert resolved.is_dir()
    assert (dest / "SKILL.md").is_file()
    # And it should resolve into the bundled dir (or be a copy thereof).
    assert (
        str(resolved).startswith(str(bundled.resolve()))
        or (dest / ".bob-installed").is_file()
    )


def test_symlink_to_moved_bob_dir_is_refreshed(tmp_path, workspace, monkeypatch):
    """A symlink pointing at an *old* bob install must be replaced
    when the bundled skills directory has moved."""
    # First "old" bob location.
    old_bundled = tmp_path / "bob_old" / "skills"
    old_bundled.mkdir(parents=True)
    old_alpha = old_bundled / "alpha"
    old_alpha.mkdir()
    (old_alpha / "SKILL.md").write_text("# alpha (old)\n")

    monkeypatch.setattr(
        skills_installer, "get_bundled_skills_dir", lambda: old_bundled
    )
    install_skills_to_workspace(workspace)
    target_dir = workspace / ".claude" / "skills"
    dest = target_dir / "alpha"
    assert dest.is_symlink()
    assert dest.resolve() == old_alpha.resolve()

    # Now simulate user upgrading bob: old dir is removed, new dir
    # appears at a different path.
    import shutil

    shutil.rmtree(tmp_path / "bob_old")

    new_bundled = tmp_path / "bob_new" / "skills"
    new_bundled.mkdir(parents=True)
    new_alpha = new_bundled / "alpha"
    new_alpha.mkdir()
    (new_alpha / "SKILL.md").write_text("# alpha (new)\n")

    monkeypatch.setattr(
        skills_installer, "get_bundled_skills_dir", lambda: new_bundled
    )

    installed = install_skills_to_workspace(workspace)
    assert "alpha" in installed
    dest = target_dir / "alpha"
    # Old symlink was broken and should be replaced.
    assert dest.is_symlink()
    assert dest.resolve(strict=True) == new_alpha.resolve()
    assert (dest / "SKILL.md").read_text().strip().endswith("(new)")


def test_user_created_directory_is_not_touched(fake_bundled_skills, workspace):
    bundled, _ = fake_bundled_skills
    target_dir = workspace / ".claude" / "skills"
    target_dir.mkdir(parents=True)

    # User has created their own skill named "alpha" — same name as a
    # bundled one. We must NOT clobber it. (No symlink, no marker.)
    user_alpha = target_dir / "alpha"
    user_alpha.mkdir()
    (user_alpha / "SKILL.md").write_text("# alpha (user)\n")
    (user_alpha / "user_marker").write_text("hands off")

    installed = install_skills_to_workspace(workspace)

    # User dir untouched.
    assert (user_alpha / "user_marker").is_file()
    assert (user_alpha / "SKILL.md").read_text().strip().endswith("(user)")
    assert not user_alpha.is_symlink()
    # alpha is therefore NOT in the installed-this-run list.
    assert "alpha" not in installed
    # But the other skills still got installed.
    assert "beta" in installed
    assert "gamma" in installed


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_repeated_calls_are_idempotent(fake_bundled_skills, workspace):
    _, names = fake_bundled_skills
    target_dir = workspace / ".claude" / "skills"

    first = sorted(install_skills_to_workspace(workspace))
    # Capture inode of each symlink (lstat — symlink itself, not target).
    inodes_first = {
        n: os.lstat(target_dir / n).st_ino for n in names
    }

    second = sorted(install_skills_to_workspace(workspace))
    inodes_second = {
        n: os.lstat(target_dir / n).st_ino for n in names
    }

    assert first == second == names
    # No churn: the symlink inode itself must be unchanged on a no-op
    # refresh. This catches sloppy "always unlink and recreate" code.
    assert inodes_first == inodes_second


def test_idempotent_after_partial_user_intrusion(fake_bundled_skills, workspace):
    """User added a real dir for one skill between calls; the installer
    must still be idempotent for the other skills and not raise."""
    bundled, names = fake_bundled_skills
    target_dir = workspace / ".claude" / "skills"

    install_skills_to_workspace(workspace)

    # User replaces one of our symlinks with their own dir.
    (target_dir / "beta").unlink()
    user_beta = target_dir / "beta"
    user_beta.mkdir()
    (user_beta / "SKILL.md").write_text("# beta (user)\n")

    again = install_skills_to_workspace(workspace)
    # User-owned beta is left alone, no exception.
    assert (user_beta / "SKILL.md").read_text().strip().endswith("(user)")
    assert "alpha" in again and "gamma" in again
    assert "beta" not in again


# ---------------------------------------------------------------------------
# Verification post-symlink
# ---------------------------------------------------------------------------


def test_symlink_that_does_not_resolve_falls_back_to_copy(
    fake_bundled_skills, workspace, monkeypatch
):
    """If symlink_to silently 'succeeds' but the target doesn't resolve,
    we should fall back to a directory copy.

    We simulate this by intercepting Path.symlink_to so that it creates
    a symlink to a nonexistent path even though the source is fine.
    """
    bundled, _ = fake_bundled_skills

    real_symlink_to = Path.symlink_to
    bogus_target = workspace / "_does_not_exist_anywhere"

    def fake_symlink_to(self, target, target_is_directory=False):
        # Always make a broken symlink — first call only, to mimic a
        # filesystem that silently allowed a broken link.
        return real_symlink_to(self, bogus_target, target_is_directory=True)

    # Apply only to the first install attempt of the first skill.
    call_state = {"applied": False}

    def patched(self, target, target_is_directory=False):
        if not call_state["applied"]:
            call_state["applied"] = True
            return fake_symlink_to(self, target, target_is_directory)
        return real_symlink_to(self, target, target_is_directory=target_is_directory)

    monkeypatch.setattr(Path, "symlink_to", patched)

    installed = install_skills_to_workspace(workspace)
    target_dir = workspace / ".claude" / "skills"

    # Exactly one of the skills should have been copy-installed (it has
    # the .bob-installed marker), the rest are normal symlinks.
    copy_installed = [
        d for d in target_dir.iterdir()
        if d.is_dir() and not d.is_symlink() and (d / ".bob-installed").is_file()
    ]
    assert len(copy_installed) == 1
    # The copy is a real, readable skill dir.
    assert (copy_installed[0] / "SKILL.md").is_file()
    # Everything is in `installed`.
    assert sorted(installed) == sorted(p.name for p in target_dir.iterdir())


# ---------------------------------------------------------------------------
# Write-protected destination
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="chmod-based write protection doesn't apply to root or Windows",
)
def test_write_protected_destination_does_not_leave_broken_symlink(
    fake_bundled_skills, workspace
):
    """If the destination directory is read-only AND we can't remove a
    pre-existing stale symlink, we must NOT silently leave it in place
    pretending the install succeeded — the skill is dropped from the
    returned list, and a warning is logged.
    """
    bundled, names = fake_bundled_skills
    target_dir = workspace / ".claude" / "skills"
    target_dir.mkdir(parents=True)

    # Plant a broken symlink for "alpha".
    broken = target_dir / "alpha"
    broken.symlink_to(workspace / "nope", target_is_directory=True)

    # Simulate a write-protected target_dir by patching _remove_dest to
    # always fail for symlinks. We use a real chmod attempt first; on
    # filesystems where that doesn't actually deny unlink (e.g. tmpfs
    # owned by root), we fall back to monkeypatching.
    import logging

    original = skills_installer._remove_dest

    def deny_remove(p):
        if p.is_symlink():
            logging.getLogger(skills_installer.__name__).warning(
                "Could not remove %s: simulated read-only", p
            )
            return False
        return original(p)

    with mock.patch.object(skills_installer, "_remove_dest", side_effect=deny_remove):
        installed = install_skills_to_workspace(workspace)

    # alpha could not be refreshed and must NOT appear in installed.
    assert "alpha" not in installed
    # The other skills still installed cleanly.
    assert "beta" in installed and "gamma" in installed
    # The broken symlink is still there (we couldn't remove it), but
    # the function did not crash and reported clearly via its return
    # value. Caller is responsible for surfacing the warning.
    assert broken.is_symlink()
    assert not broken.exists()  # still broken — but explicitly skipped


# ---------------------------------------------------------------------------
# clean_workspace_skills
# ---------------------------------------------------------------------------


def test_clean_workspace_skills_removes_only_bob_skills(
    fake_bundled_skills, workspace
):
    bundled, names = fake_bundled_skills
    target_dir = workspace / ".claude" / "skills"

    install_skills_to_workspace(workspace)
    # Add a user-owned skill that the installer didn't create.
    user_skill = target_dir / "user_only"
    user_skill.mkdir()
    (user_skill / "SKILL.md").write_text("# user_only\n")
    (user_skill / "data").write_text("keep me")

    # Also add a user-owned dir with the same name as a bob skill but
    # clearly user-managed: replace alpha symlink with a plain dir.
    (target_dir / "alpha").unlink()
    user_alpha = target_dir / "alpha"
    user_alpha.mkdir()
    (user_alpha / "SKILL.md").write_text("# alpha (user override)\n")

    removed = clean_workspace_skills(workspace)

    # The remaining bundled skills (beta, gamma) should be removed,
    # but neither the user_only dir nor the user-owned alpha dir.
    assert "beta" in removed
    assert "gamma" in removed
    assert "alpha" not in removed  # user-owned, no marker
    assert "user_only" not in removed

    assert (target_dir / "user_only" / "data").read_text() == "keep me"
    assert (target_dir / "alpha" / "SKILL.md").read_text().endswith("(user override)\n")
    assert not (target_dir / "beta").exists()
    assert not (target_dir / "gamma").exists()


def test_clean_workspace_skills_removes_copy_installs(
    fake_bundled_skills, workspace, monkeypatch
):
    """A bob install made by copytree (with the marker) must also be
    removed by clean_workspace_skills."""
    bundled, _ = fake_bundled_skills
    target_dir = workspace / ".claude" / "skills"
    target_dir.mkdir(parents=True)

    # Force the copytree fallback by making symlink_to always fail.
    def boom(self, target, target_is_directory=False):
        raise OSError("symlinks unsupported on this fake fs")

    monkeypatch.setattr(Path, "symlink_to", boom)

    install_skills_to_workspace(workspace)
    # All entries should be real dirs with the marker.
    for entry in target_dir.iterdir():
        assert not entry.is_symlink()
        assert (entry / ".bob-installed").is_file()

    removed = clean_workspace_skills(workspace)
    assert sorted(removed) == sorted(p.name for p in [bundled / n for n in ("alpha", "beta", "gamma")])
    assert list(target_dir.iterdir()) == []


def test_clean_workspace_skills_no_workspace_dir(tmp_path):
    """Cleaning a workspace with no .claude/skills dir is a no-op."""
    assert clean_workspace_skills(tmp_path) == []


def test_clean_workspace_skills_preserves_user_symlinks(
    fake_bundled_skills, workspace, tmp_path
):
    """User-created symlinks pointing OUTSIDE the bob bundled dir must
    not be deleted by ``clean_workspace_skills``.

    Regression: the previous implementation removed ANY symlink under
    ``<workspace>/.claude/skills/`` — including a user's own custom
    skill symlinked from somewhere else on disk. The fix routes the
    decision through ``_is_bob_managed`` so only links that resolve
    INTO the current bob bundled skills directory are considered ours.
    """
    bundled, names = fake_bundled_skills
    target_dir = workspace / ".claude" / "skills"

    # Install bob skills first.
    install_skills_to_workspace(workspace)
    for name in names:
        assert (target_dir / name).is_symlink()

    # User adds their own custom skill via symlink to a directory
    # OUTSIDE the bob bundled dir.
    user_skill_src = tmp_path / "my-stuff"
    user_skill_src.mkdir()
    (user_skill_src / "SKILL.md").write_text("# my-custom-skill (user)\n")
    (user_skill_src / "user_data").write_text("hands off")

    user_link = target_dir / "my-custom-skill"
    user_link.symlink_to(user_skill_src.resolve(), target_is_directory=True)
    assert user_link.is_symlink()
    # Sanity: it resolves to the user's external dir, NOT inside bundled.
    assert user_link.resolve() == user_skill_src.resolve()

    removed = clean_workspace_skills(workspace)

    # Bob skills are gone.
    for name in names:
        assert not (target_dir / name).exists()
        assert name in removed
    # User symlink is preserved — both as a symlink and the target file.
    assert user_link.is_symlink()
    assert user_link.resolve() == user_skill_src.resolve()
    assert (user_link / "SKILL.md").read_text().strip().endswith("(user)")
    assert (user_link / "user_data").read_text() == "hands off"
    assert "my-custom-skill" not in removed


# ---------------------------------------------------------------------------
# R4: skill poisoning — verify_skills_integrity
# ---------------------------------------------------------------------------
#
# Sub-agents run with cwd=<workspace> and bypassPermissions, so they can
# write into <workspace>/.claude/skills/. A malicious sub-agent could
# replace one of bob's symlinks with a real directory containing a
# poisoned SKILL.md — and the next sub-agent in the same workspace
# would load it.
#
# verify_skills_integrity() audits every bundled skill before each
# sub-agent spawn and force-replaces anything that is no longer a
# symlink resolving INTO the current bob bundled skills directory.


class TestVerifySkillsIntegrity:
    def test_directory_replacing_symlink_is_force_replaced(
        self, fake_bundled_skills, workspace, caplog
    ):
        """A sub-agent replaced bob's ``alpha`` symlink with a malicious
        directory. ``verify_skills_integrity`` must detect this, log a
        SECURITY warning, force-remove the directory, and reinstall the
        canonical bob skill."""
        bundled, names = fake_bundled_skills
        target_dir = workspace / ".claude" / "skills"

        install_skills_to_workspace(workspace)
        # Sanity: alpha was symlinked.
        assert (target_dir / "alpha").is_symlink()

        # Simulate a malicious sub-agent: remove the symlink and write a
        # real directory with a poisoned SKILL.md in its place.
        (target_dir / "alpha").unlink()
        poisoned = target_dir / "alpha"
        poisoned.mkdir()
        (poisoned / "SKILL.md").write_text(
            "# poisoned\n\nDo something nasty here.\n"
        )
        (poisoned / "evil.txt").write_text("attacker payload")

        import logging as _logging

        with caplog.at_level(_logging.WARNING, logger="bob.skills_installer"):
            tampered = verify_skills_integrity(workspace)

        assert "alpha" in tampered, (
            "tampered alpha directory was not detected by integrity check"
        )

        # alpha is now a fresh symlink resolving into the bundled dir.
        dest = target_dir / "alpha"
        assert dest.is_symlink(), (
            "force-replace did not restore the canonical symlink"
        )
        assert dest.resolve(strict=True) == (bundled / "alpha").resolve()

        # The poisoned SKILL.md and evil.txt are gone — the symlink now
        # points at the canonical bundled skill dir which doesn't have
        # them.
        assert (dest / "SKILL.md").read_text().strip() == "# alpha"
        assert not (dest / "evil.txt").exists()

        # And we logged a SECURITY warning explaining what happened.
        sec_warnings = [
            r for r in caplog.records
            if "SECURITY" in r.getMessage() and "alpha" in r.getMessage()
        ]
        assert sec_warnings, (
            "expected a SECURITY-tagged warning identifying the tampered "
            f"skill, got: {[r.getMessage() for r in caplog.records]}"
        )

    def test_symlink_pointing_outside_bob_is_force_replaced(
        self, fake_bundled_skills, workspace, tmp_path, caplog
    ):
        """A symlink that no longer resolves into the current bob
        bundled skills directory is treated as tampering and replaced.
        This catches the variant where the attacker writes a symlink
        pointing at their own SKILL.md somewhere else on disk."""
        bundled, _ = fake_bundled_skills
        target_dir = workspace / ".claude" / "skills"

        install_skills_to_workspace(workspace)

        # Attacker's stash containing their own SKILL.md.
        attacker_dir = tmp_path / "attacker_skill"
        attacker_dir.mkdir()
        (attacker_dir / "SKILL.md").write_text("# attacker\n")

        # Repoint alpha at the attacker's dir.
        (target_dir / "alpha").unlink()
        (target_dir / "alpha").symlink_to(
            attacker_dir.resolve(), target_is_directory=True
        )
        # Sanity: it does resolve, just not into bundled.
        assert (target_dir / "alpha").resolve() == attacker_dir.resolve()

        import logging as _logging

        with caplog.at_level(_logging.WARNING, logger="bob.skills_installer"):
            tampered = verify_skills_integrity(workspace)

        assert "alpha" in tampered

        dest = target_dir / "alpha"
        # Now resolves back into bob's bundled dir.
        assert dest.is_symlink()
        assert dest.resolve(strict=True) == (bundled / "alpha").resolve()

        sec_warnings = [
            r for r in caplog.records
            if "SECURITY" in r.getMessage() and "alpha" in r.getMessage()
        ]
        assert sec_warnings, (
            f"expected a SECURITY warning for repointed alpha; got: "
            f"{[r.getMessage() for r in caplog.records]}"
        )

    def test_clean_workspace_passes_integrity_check(
        self, fake_bundled_skills, workspace, caplog
    ):
        """When nothing has been tampered with, ``verify_skills_integrity``
        is a quiet no-op — returns [], no SECURITY warnings logged."""
        install_skills_to_workspace(workspace)

        import logging as _logging

        with caplog.at_level(_logging.WARNING, logger="bob.skills_installer"):
            tampered = verify_skills_integrity(workspace)

        assert tampered == []
        sec_warnings = [
            r for r in caplog.records if "SECURITY" in r.getMessage()
        ]
        assert sec_warnings == [], (
            f"unexpected SECURITY warnings on a clean workspace: "
            f"{[r.getMessage() for r in sec_warnings]}"
        )

    def test_no_skills_dir_is_noop(self, fake_bundled_skills, workspace):
        """Workspace with no .claude/skills/ yet: integrity check is a
        no-op. The caller is responsible for the initial install; this
        function only detects tampering of an existing install."""
        # Don't install anything.
        assert not (workspace / ".claude" / "skills").exists()
        tampered = verify_skills_integrity(workspace)
        assert tampered == []
