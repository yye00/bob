"""Git operations for version control during Bob execution (F114).

Provides functions for:
- Committing feature work after successful completion
- Reverting feature commits during rollback operations
- Retrieving recent commit history for sub-agent orientation
- Checking working tree status for pre-execution verification

Error model
-----------
``commit_feature`` distinguishes the following failure modes via specific
exception types so callers can react appropriately:

- "Nothing to commit" (clean working tree / nothing staged): returns ``None``
  without raising.
- "Hook rejected commit" (pre-commit / commit-msg hook exited non-zero):
  raises :class:`GitHookFailedError` with the hook's stderr/stdout captured.
- "Repo doesn't exist / not a git repository": raises :class:`GitRepoError`.
- Any other git failure: raises :class:`GitCommitError`.

All these exceptions carry ``returncode``, ``stdout``, ``stderr``, and
``command`` attributes for diagnostics.
"""

from __future__ import annotations

import logging
import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import PurePosixPath
from typing import Callable, Mapping, Sequence

logger = logging.getLogger(__name__)


# A well-formed git SHA is hex, 7-40 chars long. We accept both short
# (≥7) and full SHAs because callers may pass either; what we refuse is
# anything that could be a git "ref expression" — namely values starting
# with ``-`` (which git treats as a flag — e.g. ``--abort`` would put
# ``revert`` into abort mode and silently disable rollbacks), values
# containing ``~`` / ``^`` / ``..`` / ``@`` / whitespace (relative refs
# and revision walks), or empty strings. The regex below is the entire
# allowlist: hex digits only, length 7-40.
_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


# ---------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------


class GitCommitError(Exception):
    """A git operation failed in a way the caller should know about.

    Attributes:
        returncode: The git process exit code.
        stdout: Captured stdout of the failed command (may be empty).
        stderr: Captured stderr of the failed command (may be empty).
        command: The full command line (list of args including ``git``).
    """

    def __init__(
        self,
        message: str,
        *,
        returncode: int,
        stdout: str,
        stderr: str,
        command: list[str],
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.command = command


class GitHookFailedError(GitCommitError):
    """A git hook (pre-commit, commit-msg, etc.) rejected the commit.

    The hook's stderr/stdout is captured on the exception so callers can
    surface it to the human operator.
    """


class GitRepoError(GitCommitError):
    """The target directory is not a git repository (or has no .git)."""


# ---------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------


# Substrings that, when found in git stderr/stdout after a `git commit`
# failure, indicate a hook rejection rather than a generic git error.
# Match is case-insensitive. ONLY actual hook markers belong here — do
# not add generic git error fragments. Misclassifying infrastructure
# errors (stale lockfiles, missing LFS, merge conflicts, etc.) as hook
# failures routes them to the wrong recovery path.
_HOOK_REJECTION_MARKERS = (
    "hook failed",
    "hook exited",
    "hook declined",
    "hook script failed",
    "pre-commit hook",
    "commit-msg hook",
    "pre-push hook",
    "pre-receive hook",
    # Common pre-commit framework outputs:
    "files were modified by this hook",
    "the .pre-commit-config.yaml file is not staged",
)

# Substrings that indicate a non-hook infrastructure failure: stale
# lockfiles, missing executables, permissions issues, merge conflicts,
# remote rejections, etc. These should be reported as GitCommitError —
# they are not hook problems and the caller should not treat them as
# such. Match is case-insensitive.
_INFRASTRUCTURE_ERROR_MARKERS = (
    "index.lock",
    "could not lock",
    "no such file or directory",
    "permission denied",
    "remote rejected",
    "merge conflict",
    "would be overwritten",
)

# Substrings indicating the directory isn't a git repository.
_NOT_A_REPO_MARKERS = (
    "not a git repository",
    "fatal: not a git repository",
)


def _looks_like_hook_failure(stderr: str, stdout: str) -> bool:
    blob = f"{stderr}\n{stdout}".lower()
    return any(marker in blob for marker in _HOOK_REJECTION_MARKERS)


def _looks_like_infrastructure_error(stderr: str, stdout: str) -> bool:
    blob = f"{stderr}\n{stdout}".lower()
    return any(marker in blob for marker in _INFRASTRUCTURE_ERROR_MARKERS)


def _looks_like_not_a_repo(stderr: str, stdout: str, *, workspace: str) -> bool:
    blob = f"{stderr}\n{stdout}".lower()
    if any(marker in blob for marker in _NOT_A_REPO_MARKERS):
        return True
    # If the workspace dir doesn't exist or has no .git directory, treat
    # this as a repo error regardless of git's exact stderr wording.
    if not os.path.isdir(workspace):
        return True
    return False


def _run_git(
    args: list[str],
    *,
    workspace: str,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in the given workspace and capture output.

    Always captures stdout and stderr. Never raises ``CalledProcessError``;
    callers are expected to inspect ``returncode`` and decide what to do.

    Args:
        args: Git sub-command and arguments (e.g. ``["status", "--porcelain"]``).
        workspace: Working directory for the git command.

    Returns:
        The CompletedProcess result with ``stdout`` and ``stderr`` populated.
    """
    cmd = ["git"] + args
    return subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )


def _exact_git_command(args: Sequence[str]) -> list[str]:
    """Build a hook-free, literal-pathspec Git command for hardened commits.

    ``update-ref`` may run ``reference-transaction`` hooks, so ``--no-verify``
    on a porcelain commit is not enough.  Every command in the exact path is
    given a controller-owned empty hooks path.  Literal pathspec handling also
    prevents a candidate filename such as ``:(glob)**`` from widening the
    controller's authorized path set.
    """

    return [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "--literal-pathspecs",
        *args,
    ]


def _run_exact_git(
    args: Sequence[str], *, workspace: str, index_file: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = _exact_git_environment(index_file=index_file)
    return subprocess.run(
        _exact_git_command(args),
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _run_exact_git_bytes(
    args: Sequence[str], *, workspace: str, index_file: str | None = None
) -> subprocess.CompletedProcess[bytes]:
    env = _exact_git_environment(index_file=index_file)
    return subprocess.run(
        _exact_git_command(args),
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )


def _exact_git_environment(*, index_file: str | None = None) -> dict[str, str]:
    """Build a controller-owned environment for exact Git plumbing.

    Inherited ``GIT_*`` variables can redirect object, ref, work-tree, index,
    config, or hook resolution.  Preserve ordinary process settings but drop
    every Git control variable, then install only Bob's fixed noninteractive
    identity/config policy and (when requested) its private temporary index.
    """

    env = {
            # Resolve only system controller executables; inherited PATH and
            # dynamic-loader/Python variables are code-injection surfaces.
            "PATH": os.defpath,
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_LITERAL_PATHSPECS": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_AUTHOR_NAME": "Bob Controller",
            "GIT_AUTHOR_EMAIL": "bob-controller@localhost",
            "GIT_COMMITTER_NAME": "Bob Controller",
            "GIT_COMMITTER_EMAIL": "bob-controller@localhost",
    }
    if index_file is not None:
        env["GIT_INDEX_FILE"] = index_file
    return env


def _validate_exact_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"unsafe exact stage path: {value!r}")
    return path.as_posix()


def _parse_nul_paths(raw: bytes) -> tuple[str, ...]:
    return tuple(
        item.decode("utf-8", errors="strict")
        for item in raw.split(b"\0")
        if item
    )


def _validate_commit_proof_bindings(
    proof: Mapping[str, object],
    *,
    expected_file_sha256: Mapping[str, str | None],
    expected_file_modes: Mapping[str, str | None],
) -> None:
    entries = {
        str(item["path"]): item
        for item in proof.get("entries", ())
        if isinstance(item, dict) and item.get("path")
    }
    if set(entries) != set(expected_file_sha256):
        raise GitCommitError(
            "commit proof does not cover the exact expected path set",
            returncode=1,
            stdout=repr(sorted(entries)),
            stderr=repr(sorted(expected_file_sha256)),
            command=["git", "ls-tree"],
        )
    for path, wanted_hash in expected_file_sha256.items():
        entry = entries[path]
        if wanted_hash is None:
            valid = entry.get("operation") == "deleted"
        else:
            valid = (
                entry.get("operation") == "present"
                and entry.get("object_type") == "blob"
                and entry.get("content_sha256") == wanted_hash
                and entry.get("mode") == expected_file_modes[path]
            )
        if not valid:
            raise GitCommitError(
                f"commit proof differs from expected hash/type/mode for {path}",
                returncode=1,
                stdout=repr(entry),
                stderr=(
                    f"expected_sha256={wanted_hash} "
                    f"expected_mode={expected_file_modes[path]}"
                ),
                command=["git", "ls-tree", str(proof.get("commit_sha")), "--", path],
            )


def _ensure_repo(workspace: str) -> None:
    """Raise GitRepoError if ``workspace`` is not inside a git repo."""
    if not os.path.isdir(workspace):
        raise GitRepoError(
            f"Workspace does not exist: {workspace}",
            returncode=-1,
            stdout="",
            stderr=f"workspace does not exist: {workspace}",
            command=["git", "rev-parse", "--git-dir"],
        )
    result = _run_git(["rev-parse", "--git-dir"], workspace=workspace)
    if result.returncode != 0:
        raise GitRepoError(
            f"Not a git repository: {workspace}",
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            command=["git", "rev-parse", "--git-dir"],
        )


def _ensure_exact_repo_root(workspace: str) -> str:
    """Return the canonical workspace and require it is the repository root."""

    try:
        canonical = os.path.realpath(workspace, strict=True)
    except OSError as exc:
        raise GitRepoError(
            f"Exact workspace is unavailable: {workspace}",
            returncode=-1,
            stdout="",
            stderr=str(exc),
            command=["git", "rev-parse", "--show-toplevel"],
        ) from exc
    root = _run_exact_git(
        ["rev-parse", "--show-toplevel"], workspace=canonical
    )
    if root.returncode != 0:
        raise GitRepoError(
            f"Not a git repository: {canonical}",
            returncode=root.returncode,
            stdout=root.stdout,
            stderr=root.stderr,
            command=["git", "rev-parse", "--show-toplevel"],
        )
    reported = os.path.realpath(root.stdout.strip(), strict=True)
    if reported != canonical:
        raise GitRepoError(
            "Hardened exact commits require workspace to be the repository root",
            returncode=1,
            stdout=reported,
            stderr=f"workspace={canonical}",
            command=["git", "rev-parse", "--show-toplevel"],
        )
    return canonical


# ---------------------------------------------------------------
# Public API
# ---------------------------------------------------------------


def commit_feature(
    *,
    feature_id: str,
    message: str,
    workspace: str,
    stage_all: bool = False,
    stage_paths: Sequence[str] | None = None,
    expected_file_sha256: Mapping[str, str | None] | None = None,
    expected_file_modes: Mapping[str, str | None] | None = None,
    expected_parent_sha: str | None = None,
    expected_parent_tree_sha: str | None = None,
    skip_hooks: bool = False,
    on_exact_commit_planned: Callable[[Mapping[str, object]], None] | None = None,
) -> str | None:
    """Create a git commit for a completed feature.

    Args:
        feature_id: The feature ID (e.g. ``"F114"``) to include in the commit
            message.
        message: A human-readable commit message describing the change.
        workspace: Path to the git repository.
        stage_all: If True, stages all changes (``git add -A``) before
            committing.

    Returns:
        The full 40-character SHA of the new commit, or ``None`` if there
        was nothing to commit.

    Raises:
        GitRepoError: ``workspace`` is not a git repository.
        GitHookFailedError: A git hook rejected the commit.
        GitCommitError: Some other git operation failed.
    """
    if stage_all and stage_paths is not None:
        raise ValueError("stage_all and stage_paths are mutually exclusive")
    if on_exact_commit_planned is not None and stage_paths is None:
        raise ValueError("commit planning callback requires exact stage_paths")
    if (expected_parent_sha is None) != (expected_parent_tree_sha is None):
        raise ValueError("expected exact parent commit and tree must be supplied together")
    if expected_parent_sha is not None and stage_paths is None:
        raise ValueError("expected exact parent requires exact stage_paths")
    for label, value in (
        ("expected_parent_sha", expected_parent_sha),
        ("expected_parent_tree_sha", expected_parent_tree_sha),
    ):
        if value is not None and re.fullmatch(r"[0-9a-f]{40,64}", value) is None:
            raise ValueError(f"{label} must be a full literal object ID")
    if stage_paths is not None:
        workspace = _ensure_exact_repo_root(workspace)
    else:
        # Legacy porcelain paths preserve the historical environment and
        # inside-repository behavior; hardened exact paths use the stricter
        # sanitized/root-only check above.
        _ensure_repo(workspace)

    exact_paths: tuple[str, ...] | None = None
    exact_parent_sha: str | None = None
    exact_parent_tree_sha: str | None = None
    exact_tree_sha: str | None = None
    exact_index_dir: tempfile.TemporaryDirectory[str] | None = None
    exact_index_file: str | None = None
    if stage_paths is not None:
        normalised: list[str] = []
        for value in stage_paths:
            normalised.append(_validate_exact_path(value))
        if len(set(normalised)) != len(normalised):
            raise ValueError("exact stage paths contain duplicates")
        exact_paths = tuple(sorted(normalised))
        parent_result = _run_exact_git(["rev-parse", "HEAD"], workspace=workspace)
        if parent_result.returncode != 0:
            raise GitCommitError(
                "could not bind exact commit parent",
                returncode=parent_result.returncode,
                stdout=parent_result.stdout,
                stderr=parent_result.stderr,
                command=["git", "rev-parse", "HEAD"],
            )
        exact_parent_sha = parent_result.stdout.strip()
        if (
            expected_parent_sha is not None
            and exact_parent_sha != expected_parent_sha
        ):
            raise GitCommitError(
                "exact commit parent differs from the authenticated attempt base",
                returncode=1,
                stdout=exact_parent_sha,
                stderr=f"expected_parent={expected_parent_sha}",
                command=["git", "rev-parse", "HEAD"],
            )
        parent_tree_result = _run_exact_git(
            ["rev-parse", "--verify", f"{exact_parent_sha}^{{tree}}"],
            workspace=workspace,
        )
        exact_parent_tree_sha = parent_tree_result.stdout.strip()
        if (
            parent_tree_result.returncode != 0
            or re.fullmatch(r"[0-9a-f]{40,64}", exact_parent_tree_sha) is None
            or (
                expected_parent_tree_sha is not None
                and exact_parent_tree_sha != expected_parent_tree_sha
            )
        ):
            raise GitCommitError(
                "exact commit parent tree differs from the authenticated attempt base",
                returncode=parent_tree_result.returncode or 1,
                stdout=parent_tree_result.stdout,
                stderr=parent_tree_result.stderr
                or f"expected_parent_tree={expected_parent_tree_sha}",
                command=["git", "rev-parse", "--verify", f"{exact_parent_sha}^{{tree}}"],
            )
        exact_index_dir = tempfile.TemporaryDirectory(prefix="bob-exact-index-")
        exact_index_file = os.path.join(exact_index_dir.name, "index")
        seeded = _run_exact_git(
            ["read-tree", exact_parent_sha],
            workspace=workspace,
            index_file=exact_index_file,
        )
        if seeded.returncode != 0:
            raise GitCommitError(
                "could not seed controller-owned exact index",
                returncode=seeded.returncode,
                stdout=seeded.stdout,
                stderr=seeded.stderr,
                command=["git", "read-tree", exact_parent_sha],
            )
        expected = dict(expected_file_sha256 or {})
        expected_modes = dict(expected_file_modes or {})
        if set(expected) != set(exact_paths):
            raise ValueError("expected file hashes must exactly cover stage_paths")
        if set(expected_modes) != set(exact_paths):
            raise ValueError("expected file modes must exactly cover stage_paths")

        if exact_paths:
            add_args = ["add", "-A", "--", *exact_paths]
            add_result = _run_exact_git(
                add_args, workspace=workspace, index_file=exact_index_file
            )
            if add_result.returncode != 0:
                raise GitCommitError(
                    f"exact git add failed: {add_result.stderr.strip()}",
                    returncode=add_result.returncode,
                    stdout=add_result.stdout,
                    stderr=add_result.stderr,
                    command=["git", *add_args],
                )

        staged = _run_exact_git_bytes(
            ["diff", "--cached", "--name-only", "--no-renames", "-z"],
            workspace=workspace,
            index_file=exact_index_file,
        )
        staged_paths = set(_parse_nul_paths(staged.stdout))
        if staged.returncode != 0 or staged_paths != set(exact_paths):
            raise GitCommitError(
                "staged index does not exactly match the authorized feature bundle",
                returncode=staged.returncode or 1,
                stdout=staged.stdout.decode("utf-8", errors="replace"),
                stderr=staged.stderr.decode("utf-8", errors="replace")
                or f"expected={sorted(exact_paths)!r} actual={sorted(staged_paths)!r}",
                command=["git", "diff", "--cached", "--name-only", "--no-renames", "-z"],
            )
        for path, wanted_sha256 in expected.items():
            listed = _run_exact_git_bytes(
                ["ls-files", "-s", "-z", "--", path],
                workspace=workspace,
                index_file=exact_index_file,
            )
            if listed.returncode != 0:
                raise GitCommitError(
                    f"could not inspect staged path {path}",
                    returncode=listed.returncode,
                    stdout="",
                    stderr=listed.stderr.decode("utf-8", errors="replace"),
                    command=["git", "ls-files", "-s", "-z", "--", path],
                )
            records = [item for item in listed.stdout.split(b"\0") if item]
            if wanted_sha256 is None:
                if records:
                    raise GitCommitError(
                        f"deleted path remains in staged index: {path}",
                        returncode=1,
                        stdout="",
                        stderr="staged index still contains the path",
                        command=["git", "ls-files", "-s", "-z", "--", path],
                    )
                continue
            if len(records) != 1 or b"\t" not in records[0]:
                raise GitCommitError(
                    f"staged index entry is ambiguous for {path}",
                    returncode=1,
                    stdout="",
                    stderr=repr(records),
                    command=["git", "ls-files", "-s", "-z", "--", path],
                )
            metadata, literal = records[0].split(b"\t", 1)
            fields = metadata.decode("ascii", errors="strict").split()
            if len(fields) != 3 or literal.decode("utf-8", errors="strict") != path:
                raise GitCommitError(
                    f"staged index returned an unexpected entry for {path}",
                    returncode=1,
                    stdout="",
                    stderr=records[0].decode("utf-8", errors="replace"),
                    command=["git", "ls-files", "-s", "-z", "--", path],
                )
            staged_mode, blob_sha, stage_number = fields
            if stage_number != "0" or not re.fullmatch(r"[0-9a-f]{40,64}", blob_sha):
                raise GitCommitError(
                    f"staged index entry is not a normal blob for {path}",
                    returncode=1,
                    stdout="",
                    stderr=metadata.decode("ascii", errors="replace"),
                    command=["git", "ls-files", "-s", "-z", "--", path],
                )
            blob = _run_exact_git_bytes(
                ["cat-file", "blob", blob_sha], workspace=workspace
            )
            actual_sha256 = hashlib.sha256(blob.stdout).hexdigest()
            if blob.returncode != 0 or actual_sha256 != wanted_sha256:
                raise GitCommitError(
                    f"staged blob hash mismatch for {path}",
                    returncode=blob.returncode or 1,
                    stdout="",
                    stderr=(
                        f"expected_sha256={wanted_sha256} actual_sha256={actual_sha256}"
                    ),
                    command=["git", "cat-file", "blob", blob_sha],
                )
            if staged_mode != expected_modes[path]:
                raise GitCommitError(
                    f"staged mode mismatch for {path}",
                    returncode=1,
                    stdout="",
                    stderr=f"expected_mode={expected_modes[path]} actual_mode={staged_mode}",
                    command=["git", "ls-files", "-s", "--", path],
                )

    if stage_all:
        add_result = _run_git(["add", "-A"], workspace=workspace)
        if add_result.returncode != 0:
            raise GitCommitError(
                f"git add -A failed: {add_result.stderr.strip()}",
                returncode=add_result.returncode,
                stdout=add_result.stdout,
                stderr=add_result.stderr,
                command=["git", "add", "-A"],
            )

    # Check if there are staged changes. exit 0 = no diff (nothing staged).
    diff_result = (
        _run_exact_git(
            ["diff", "--cached", "--quiet"],
            workspace=workspace,
            index_file=exact_index_file,
        )
        if exact_paths is not None
        else _run_git(["diff", "--cached", "--quiet"], workspace=workspace)
    )
    if diff_result.returncode == 0:
        logger.info("No staged changes to commit for %s", feature_id)
        return None
    # `git diff --cached --quiet` returns 1 when there *is* a diff. Any other
    # non-zero (e.g. 128) means git itself failed.
    if diff_result.returncode not in (0, 1):
        raise GitCommitError(
            f"git diff --cached failed: {diff_result.stderr.strip()}",
            returncode=diff_result.returncode,
            stdout=diff_result.stdout,
            stderr=diff_result.stderr,
            command=["git", "diff", "--cached", "--quiet"],
        )

    commit_msg = f"[{feature_id}] {message}"
    if exact_paths is not None:
        write_tree = _run_exact_git(
            ["write-tree"], workspace=workspace, index_file=exact_index_file
        )
        if write_tree.returncode != 0:
            raise GitCommitError(
                "git write-tree failed for exact commit",
                returncode=write_tree.returncode,
                stdout=write_tree.stdout,
                stderr=write_tree.stderr,
                command=["git", "write-tree"],
            )
        exact_tree_sha = write_tree.stdout.strip()
        assert exact_parent_sha is not None
        commit_cmd = [
            "commit-tree",
            exact_tree_sha,
            "-p",
            exact_parent_sha,
            "-m",
            commit_msg,
        ]
        commit_result = _run_exact_git(commit_cmd, workspace=workspace)
        if commit_result.returncode == 0:
            new_sha = commit_result.stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{40,64}", new_sha):
                raise GitCommitError(
                    "git commit-tree returned an invalid object id",
                    returncode=1,
                    stdout=commit_result.stdout,
                    stderr=commit_result.stderr,
                    command=["git", *commit_cmd],
                )
            pre_cas_proof = get_commit_proof(
                commit_sha=new_sha,
                workspace=workspace,
                expected_paths=exact_paths,
            )
            _validate_commit_proof_bindings(
                pre_cas_proof,
                expected_file_sha256=expected,
                expected_file_modes=expected_modes,
            )
            if on_exact_commit_planned is not None:
                on_exact_commit_planned(
                    {
                        "commit_sha": new_sha,
                        "parent_sha": exact_parent_sha,
                        "parent_tree_sha": exact_parent_tree_sha,
                        "tree_sha": exact_tree_sha,
                        "paths": list(exact_paths),
                    }
                )
            update_ref = _run_exact_git(
                ["update-ref", "HEAD", new_sha, exact_parent_sha],
                workspace=workspace,
            )
            if update_ref.returncode != 0:
                raise GitCommitError(
                    "atomic HEAD update failed for exact commit",
                    returncode=update_ref.returncode,
                    stdout=update_ref.stdout,
                    stderr=update_ref.stderr,
                    command=["git", "update-ref", "HEAD", new_sha, exact_parent_sha],
                )
    else:
        commit_cmd = ["commit"]
        if skip_hooks:
            commit_cmd.append("--no-verify")
        commit_cmd.extend(["-m", commit_msg])
        commit_result = _run_git(commit_cmd, workspace=workspace)

    if commit_result.returncode != 0:
        full_cmd = ["git"] + commit_cmd
        # Distinguish: repo error vs. hook rejection vs. infrastructure
        # vs. anything else. Order matters: a missing repo always wins
        # because almost every other check would also match.
        if _looks_like_not_a_repo(
            commit_result.stderr, commit_result.stdout, workspace=workspace
        ):
            raise GitRepoError(
                f"git commit failed: not a git repository ({workspace})",
                returncode=commit_result.returncode,
                stdout=commit_result.stdout,
                stderr=commit_result.stderr,
                command=full_cmd,
            )
        # Only classify as a hook failure when stderr/stdout actually
        # contains a recognized hook marker. There is no heuristic
        # fallback — silent failures and unrecognized output are
        # generic GitCommitError. This avoids misclassifying
        # infrastructure errors (stale lock files, missing LFS,
        # permission denials, merge conflicts, etc.) as hook
        # rejections.
        if _looks_like_hook_failure(commit_result.stderr, commit_result.stdout):
            raise GitHookFailedError(
                f"git commit rejected by hook (rc={commit_result.returncode}): "
                f"{commit_result.stderr.strip() or commit_result.stdout.strip()}",
                returncode=commit_result.returncode,
                stdout=commit_result.stdout,
                stderr=commit_result.stderr,
                command=full_cmd,
            )
        # Infrastructure errors (lockfile, missing tool, permissions,
        # merge conflict, etc.) — surfaced as GitCommitError so the
        # caller can apply the correct recovery (retry / wait / human
        # intervention) rather than the hook-rejection path.
        combined = (commit_result.stderr + commit_result.stdout).strip()
        if _looks_like_infrastructure_error(
            commit_result.stderr, commit_result.stdout
        ):
            raise GitCommitError(
                f"git commit failed (rc={commit_result.returncode}): "
                f"{combined or 'infrastructure error'}",
                returncode=commit_result.returncode,
                stdout=commit_result.stdout,
                stderr=commit_result.stderr,
                command=full_cmd,
            )
        # Anything else: generic git failure. We do NOT promote this to
        # GitHookFailedError just because output is non-empty.
        raise GitCommitError(
            f"git commit failed (rc={commit_result.returncode})"
            + (f": {combined}" if combined else " with no output"),
            returncode=commit_result.returncode,
            stdout=commit_result.stdout,
            stderr=commit_result.stderr,
            command=full_cmd,
        )

    # Get the SHA of the new commit
    sha_result = (
        _run_exact_git(["rev-parse", "HEAD"], workspace=workspace)
        if exact_paths is not None
        else _run_git(["rev-parse", "HEAD"], workspace=workspace)
    )
    if sha_result.returncode != 0:
        raise GitCommitError(
            f"git rev-parse HEAD failed: {sha_result.stderr.strip()}",
            returncode=sha_result.returncode,
            stdout=sha_result.stdout,
            stderr=sha_result.stderr,
            command=["git", "rev-parse", "HEAD"],
        )
    sha = sha_result.stdout.strip()
    if exact_paths is not None:
        if sha != commit_result.stdout.strip():
            raise GitCommitError(
                "HEAD does not identify the exact commit-tree object",
                returncode=1,
                stdout=sha,
                stderr=commit_result.stdout,
                command=["git", "rev-parse", "HEAD"],
            )
        parent_check = _run_exact_git(["rev-parse", f"{sha}^"], workspace=workspace)
        tree_check = _run_exact_git(["rev-parse", f"{sha}^{{tree}}"], workspace=workspace)
        if (
            parent_check.returncode != 0
            or tree_check.returncode != 0
            or parent_check.stdout.strip() != exact_parent_sha
            or tree_check.stdout.strip() != exact_tree_sha
        ):
            raise GitCommitError(
                "exact commit parent/tree proof failed",
                returncode=1,
                stdout=parent_check.stdout + tree_check.stdout,
                stderr=parent_check.stderr + tree_check.stderr,
                command=["git", "rev-parse", sha],
            )
        committed = _run_exact_git_bytes(
            ["diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-z", "-r", sha],
            workspace=workspace,
        )
        committed_paths = set(_parse_nul_paths(committed.stdout))
        if committed.returncode != 0 or committed_paths != set(exact_paths):
            raise GitCommitError(
                "created commit tree does not match the authorized feature bundle",
                returncode=committed.returncode or 1,
                stdout=committed.stdout.decode("utf-8", errors="replace"),
                stderr=committed.stderr.decode("utf-8", errors="replace")
                or f"expected={sorted(exact_paths)!r} actual={sorted(committed_paths)!r}",
                command=["git", "diff-tree", "--name-only", sha],
            )
        sync_index = _run_exact_git(["read-tree", sha], workspace=workspace)
        if sync_index.returncode != 0:
            raise GitCommitError(
                "could not synchronize the working index to the exact commit",
                returncode=sync_index.returncode,
                stdout=sync_index.stdout,
                stderr=sync_index.stderr,
                command=["git", "read-tree", sha],
            )
    logger.info("Created commit %s for feature %s", sha[:8], feature_id)
    return sha


def get_commit_proof(
    *, commit_sha: str, workspace: str, expected_paths: Sequence[str]
) -> dict[str, object]:
    """Return and verify an exact parent/tree/blob/mode witness for a commit."""
    workspace = _ensure_exact_repo_root(workspace)
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit_sha):
        raise ValueError("commit proof requires a full literal object ID")
    expected = tuple(sorted(_validate_exact_path(path) for path in expected_paths))
    if len(set(expected)) != len(expected):
        raise ValueError("commit proof paths contain duplicates")
    parent = _run_exact_git(["rev-parse", f"{commit_sha}^"], workspace=workspace)
    tree = _run_exact_git(["rev-parse", f"{commit_sha}^{{tree}}"], workspace=workspace)
    changed = _run_exact_git_bytes(
        [
            "diff-tree", "--root", "--no-commit-id", "--name-only",
            "--no-renames", "-z", "-r", commit_sha,
        ],
        workspace=workspace,
    )
    if parent.returncode != 0 or tree.returncode != 0 or changed.returncode != 0:
        raise GitCommitError(
            "could not construct commit proof",
            returncode=parent.returncode or tree.returncode or changed.returncode,
            stdout=parent.stdout + tree.stdout,
            stderr=(
                parent.stderr
                or tree.stderr
                or changed.stderr.decode("utf-8", errors="replace")
            ),
            command=["git", "diff-tree", commit_sha],
        )
    paths = tuple(sorted(_parse_nul_paths(changed.stdout)))
    if paths != expected:
        raise GitCommitError(
            "commit proof path set differs from authorized paths",
            returncode=1,
            stdout=repr(paths),
            stderr=f"expected={expected!r}",
            command=["git", "diff-tree", commit_sha],
        )
    entries: list[dict[str, str]] = []
    for path in paths:
        listed = _run_exact_git_bytes(
            ["ls-tree", "-z", commit_sha, "--", path],
            workspace=workspace,
        )
        if listed.returncode != 0:
            raise GitCommitError(
                f"could not inspect committed path {path}",
                returncode=listed.returncode,
                stdout="",
                stderr=listed.stderr.decode("utf-8", errors="replace"),
                command=["git", "ls-tree", commit_sha, "--", path],
            )
        if not listed.stdout:
            entries.append({"path": path, "operation": "deleted"})
            continue
        metadata, literal = listed.stdout.rstrip(b"\0").split(b"\t", 1)
        mode, object_type, blob_sha = metadata.decode("ascii").split()
        if literal.decode("utf-8", errors="strict") != path:
            raise GitCommitError(
                "git ls-tree returned an unexpected literal path",
                returncode=1,
                stdout="",
                stderr=path,
                command=["git", "ls-tree", commit_sha, "--", path],
            )
        if object_type != "blob":
            raise GitCommitError(
                f"committed path is not a blob: {path}",
                returncode=1,
                stdout=object_type,
                stderr=path,
                command=["git", "ls-tree", commit_sha, "--", path],
            )
        blob = _run_exact_git_bytes(
            ["cat-file", "blob", blob_sha], workspace=workspace
        )
        if blob.returncode != 0:
            raise GitCommitError(
                f"could not read committed blob {path}",
                returncode=blob.returncode,
                stdout="",
                stderr=blob.stderr.decode("utf-8", errors="replace"),
                command=["git", "cat-file", "blob", blob_sha],
            )
        entries.append(
            {
                "path": path,
                "operation": "present",
                "mode": mode,
                "object_type": object_type,
                "blob_sha": blob_sha,
                "content_sha256": hashlib.sha256(blob.stdout).hexdigest(),
            }
        )
    return {
        "commit_sha": commit_sha,
        "parent_sha": parent.stdout.strip() if parent.returncode == 0 else None,
        "tree_sha": tree.stdout.strip(),
        "paths": list(paths),
        "entries": entries,
    }


def finalize_exact_commit_intent(
    *,
    commit_sha: str,
    parent_sha: str,
    tree_sha: str,
    expected_paths: Sequence[str],
    expected_file_sha256: Mapping[str, str | None],
    expected_file_modes: Mapping[str, str | None],
    workspace: str,
    expected_parent_sha: str | None = None,
    expected_parent_tree_sha: str | None = None,
) -> dict[str, object]:
    """Reconcile a durable exact-commit intent after a controller restart.

    The commit object was created before the intent was persisted.  Therefore
    recovery has only two authorized repository states: HEAD still names the
    expected parent (perform the original compare-and-swap), or HEAD already
    names the planned commit (the process crashed after the compare-and-swap).
    Any other HEAD fails closed.
    """

    workspace = _ensure_exact_repo_root(workspace)
    for label, value in (
        ("commit_sha", commit_sha),
        ("parent_sha", parent_sha),
        ("tree_sha", tree_sha),
    ):
        if not re.fullmatch(r"[0-9a-f]{40,64}", value):
            raise ValueError(f"{label} must be a full literal object ID")
    if (expected_parent_sha is None) != (expected_parent_tree_sha is None):
        raise ValueError("expected exact parent commit and tree must be supplied together")
    for label, value in (
        ("expected_parent_sha", expected_parent_sha),
        ("expected_parent_tree_sha", expected_parent_tree_sha),
    ):
        if value is not None and re.fullmatch(r"[0-9a-f]{40,64}", value) is None:
            raise ValueError(f"{label} must be a full literal object ID")
    if expected_parent_sha is not None and parent_sha != expected_parent_sha:
        raise GitCommitError(
            "durable exact commit parent differs from the authenticated attempt base",
            returncode=1,
            stdout=parent_sha,
            stderr=f"expected_parent={expected_parent_sha}",
            command=["git", "rev-parse", commit_sha],
        )
    expected = tuple(sorted(_validate_exact_path(path) for path in expected_paths))
    if len(set(expected)) != len(expected):
        raise ValueError("exact commit intent paths contain duplicates")
    if set(expected_file_sha256) != set(expected) or set(
        expected_file_modes
    ) != set(expected):
        raise ValueError(
            "exact commit intent hash/mode maps must cover the exact path set"
        )

    actual_parent = _run_exact_git(
        ["rev-parse", f"{commit_sha}^"], workspace=workspace
    )
    actual_tree = _run_exact_git(
        ["rev-parse", f"{commit_sha}^{{tree}}"], workspace=workspace
    )
    actual_parent_tree = _run_exact_git(
        ["rev-parse", f"{parent_sha}^{{tree}}"], workspace=workspace
    )
    if (
        actual_parent.returncode != 0
        or actual_tree.returncode != 0
        or actual_parent_tree.returncode != 0
        or actual_parent.stdout.strip() != parent_sha
        or actual_tree.stdout.strip() != tree_sha
        or (
            expected_parent_tree_sha is not None
            and actual_parent_tree.stdout.strip() != expected_parent_tree_sha
        )
    ):
        raise GitCommitError(
            "planned commit object no longer matches its intent",
            returncode=(
                actual_parent.returncode
                or actual_tree.returncode
                or actual_parent_tree.returncode
                or 1
            ),
            stdout=actual_parent.stdout + actual_tree.stdout + actual_parent_tree.stdout,
            stderr=actual_parent.stderr + actual_tree.stderr + actual_parent_tree.stderr,
            command=["git", "rev-parse", commit_sha],
        )

    # Prove the immutable planned object against the full durable content,
    # mode, and deletion witness *before* a compare-and-swap can move HEAD.
    proof = get_commit_proof(
        commit_sha=commit_sha,
        workspace=workspace,
        expected_paths=expected,
    )
    if proof["parent_sha"] != parent_sha or proof["tree_sha"] != tree_sha:
        raise GitCommitError(
            "planned commit proof differs from its durable intent",
            returncode=1,
            stdout=repr(proof),
            stderr=f"parent={parent_sha} tree={tree_sha}",
            command=["git", "rev-parse", commit_sha],
        )
    _validate_commit_proof_bindings(
        proof,
        expected_file_sha256=expected_file_sha256,
        expected_file_modes=expected_file_modes,
    )

    head = _run_exact_git(["rev-parse", "HEAD"], workspace=workspace)
    if head.returncode != 0:
        raise GitCommitError(
            "could not inspect HEAD while reconciling commit intent",
            returncode=head.returncode,
            stdout=head.stdout,
            stderr=head.stderr,
            command=["git", "rev-parse", "HEAD"],
        )
    current = head.stdout.strip()
    if current == parent_sha:
        updated = _run_exact_git(
            ["update-ref", "HEAD", commit_sha, parent_sha], workspace=workspace
        )
        if updated.returncode != 0:
            raise GitCommitError(
                "atomic HEAD recovery update failed",
                returncode=updated.returncode,
                stdout=updated.stdout,
                stderr=updated.stderr,
                command=["git", "update-ref", "HEAD", commit_sha, parent_sha],
            )
    elif current != commit_sha:
        raise GitCommitError(
            "HEAD diverged from both the exact parent and planned commit",
            returncode=1,
            stdout=current,
            stderr=f"parent={parent_sha} planned={commit_sha}",
            command=["git", "rev-parse", "HEAD"],
        )

    sync_index = _run_exact_git(["read-tree", commit_sha], workspace=workspace)
    if sync_index.returncode != 0:
        raise GitCommitError(
            "could not synchronize index during exact-commit recovery",
            returncode=sync_index.returncode,
            stdout=sync_index.stdout,
            stderr=sync_index.stderr,
            command=["git", "read-tree", commit_sha],
        )
    return proof


def revert_feature(
    *,
    feature_id: str,
    commit_sha: str,
    workspace: str,
) -> str | None:
    """Revert a feature's commit for rollback operations.

    Uses ``git revert --no-edit`` to create a new commit that undoes the
    changes from the specified commit.

    Args:
        feature_id: The feature ID being rolled back.
        commit_sha: The SHA of the commit to revert.
        workspace: Path to the git repository.

    Returns:
        The full 40-character SHA of the revert commit, or ``None`` if the
        revert failed (e.g. due to merge conflicts).

    Raises:
        GitCommitError: ``commit_sha`` is not a well-formed git object name
            (i.e. not 7-40 hex chars). This is a deliberate guard against
            argument injection: a value like ``--abort`` would be parsed by
            ``git revert`` as a flag (silently disabling rollbacks), and
            ref expressions like ``HEAD~5`` would let a compromised caller
            revert arbitrary commits. We require a literal SHA so the only
            commits ever passed to ``git revert`` are ones the caller
            already knows about.
    """
    if not isinstance(commit_sha, str) or not _FULL_SHA_RE.match(commit_sha):
        raise GitCommitError(
            f"refusing to revert: commit_sha={commit_sha!r} is not a "
            f"well-formed git SHA (expected 7-40 hex chars). Refs like "
            f"'HEAD~5' or flags like '--abort' are not accepted because "
            f"they alter git's behavior and could be used for argument "
            f"injection.",
            returncode=-1,
            stdout="",
            stderr=f"invalid commit_sha: {commit_sha!r}",
            command=["git", "revert", "--no-edit", str(commit_sha)],
        )

    result = _run_git(
        ["revert", "--no-edit", commit_sha],
        workspace=workspace,
    )

    if result.returncode != 0:
        logger.warning(
            "Git revert failed for feature %s (commit %s): %s",
            feature_id, commit_sha[:8], result.stderr.strip(),
        )
        # Abort the revert if it left us in a conflicted state
        _run_git(["revert", "--abort"], workspace=workspace)
        return None

    sha_result = _run_git(["rev-parse", "HEAD"], workspace=workspace)
    sha = sha_result.stdout.strip()
    logger.info(
        "Created revert commit %s for feature %s (reverted %s)",
        sha[:8], feature_id, commit_sha[:8],
    )
    return sha


def get_recent_commits(
    *,
    n: int = 10,
    workspace: str,
) -> list[dict[str, str]]:
    """Get the most recent git commits for orientation context.

    Args:
        n: Maximum number of commits to return.
        workspace: Path to the git repository.

    Returns:
        A list of dicts with "sha" and "message" keys, most recent first.
        Returns an empty list if there are no commits.
    """
    result = _run_git(
        ["log", f"-{n}", "--format=%H\t%s"],
        workspace=workspace,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return []

    commits = []
    for line in result.stdout.strip().split("\n"):
        if "\t" in line:
            sha, message = line.split("\t", 1)
            commits.append({"sha": sha, "message": message})
    return commits


def get_status(*, workspace: str) -> dict:
    """Get the current git working tree status.

    Args:
        workspace: Path to the git repository.

    Returns:
        A dict with keys:
        - clean (bool): True if the working tree has no changes.
        - branch (str): Current branch name.
        - sha (str): Current HEAD commit SHA.
        - staged (list[str]): Files staged for commit.
        - modified (list[str]): Modified but unstaged files.
        - untracked (list[str]): Untracked files.
    """
    staged: list[str] = []
    modified: list[str] = []
    untracked: list[str] = []

    # Parse porcelain status
    status_result = _run_git(
        ["status", "--porcelain"],
        workspace=workspace,
    )
    for line in status_result.stdout.split("\n"):
        if not line:
            continue
        index_status = line[0]
        work_status = line[1]
        filename = line[3:]

        if index_status in ("A", "M", "D", "R"):
            staged.append(filename)
        if work_status in ("M", "D"):
            modified.append(filename)
        if index_status == "?" and work_status == "?":
            untracked.append(filename)

    # Get current branch
    branch_result = _run_git(
        ["rev-parse", "--abbrev-ref", "HEAD"],
        workspace=workspace,
    )
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""

    # Get current HEAD SHA
    sha_result = _run_git(
        ["rev-parse", "HEAD"],
        workspace=workspace,
    )
    sha = sha_result.stdout.strip() if sha_result.returncode == 0 else ""

    clean = not staged and not modified and not untracked

    return {
        "clean": clean,
        "branch": branch,
        "sha": sha,
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
    }


def get_exact_workspace_base(*, workspace: str) -> dict[str, object]:
    """Return the hook/config-isolated HEAD, tree, and cleanliness proof.

    This is the dispatch-time counterpart to exact commit custody.  It is used
    to bind a controller-selected packet attempt to the precise cumulative
    candidate base after any authenticated sibling integrations.
    """

    canonical = _ensure_exact_repo_root(workspace)
    head = _run_exact_git(["rev-parse", "--verify", "HEAD^{commit}"], workspace=canonical)
    tree = _run_exact_git(["rev-parse", "--verify", "HEAD^{tree}"], workspace=canonical)
    status_result = _run_exact_git(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        workspace=canonical,
    )
    for label, result, command in (
        ("HEAD", head, ["git", "rev-parse", "--verify", "HEAD^{commit}"]),
        ("HEAD tree", tree, ["git", "rev-parse", "--verify", "HEAD^{tree}"]),
        ("workspace status", status_result, ["git", "status", "--porcelain=v1"]),
    ):
        if result.returncode != 0:
            raise GitRepoError(
                f"Could not resolve exact {label}",
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                command=command,
            )
    commit = head.stdout.strip()
    tree_id = tree.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40,64}", commit) is None or re.fullmatch(
        r"[0-9a-f]{40,64}", tree_id
    ) is None:
        raise GitRepoError(
            "Exact workspace base returned malformed object identities",
            returncode=1,
            stdout=f"commit={commit} tree={tree_id}",
            stderr="",
            command=["git", "rev-parse"],
        )
    return {
        "commit": commit,
        "tree": tree_id,
        "clean": status_result.stdout == "",
    }
