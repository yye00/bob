"""Git operations for version control during Bob3 execution (F114).

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
import os
import subprocess

logger = logging.getLogger(__name__)


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


# Substrings that, when found in git stderr after a `git commit` failure,
# indicate a hook rejection rather than a generic git error.
_HOOK_REJECTION_MARKERS = (
    "pre-commit hook",
    "commit-msg hook",
    "pre-commit-msg hook",
    "prepare-commit-msg hook",
    "post-commit hook",
    "hook failed",
    "hook exited",
    "hook declined",
    "hook script",
)

# Substrings indicating the directory isn't a git repository.
_NOT_A_REPO_MARKERS = (
    "not a git repository",
    "fatal: not a git repository",
)


def _looks_like_hook_failure(stderr: str, stdout: str) -> bool:
    blob = f"{stderr}\n{stdout}".lower()
    return any(marker in blob for marker in _HOOK_REJECTION_MARKERS)


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


# ---------------------------------------------------------------
# Public API
# ---------------------------------------------------------------


def commit_feature(
    *,
    feature_id: str,
    message: str,
    workspace: str,
    stage_all: bool = False,
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
    # Verify the workspace is actually a git repo before doing anything.
    _ensure_repo(workspace)

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
    diff_result = _run_git(
        ["diff", "--cached", "--quiet"], workspace=workspace
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
    commit_cmd = ["commit", "-m", commit_msg]
    commit_result = _run_git(commit_cmd, workspace=workspace)

    if commit_result.returncode != 0:
        full_cmd = ["git"] + commit_cmd
        # Distinguish: hook rejection vs. repo error vs. anything else.
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
        if _looks_like_hook_failure(commit_result.stderr, commit_result.stdout):
            raise GitHookFailedError(
                f"git commit rejected by hook (rc={commit_result.returncode}): "
                f"{commit_result.stderr.strip() or commit_result.stdout.strip()}",
                returncode=commit_result.returncode,
                stdout=commit_result.stdout,
                stderr=commit_result.stderr,
                command=full_cmd,
            )
        # Heuristic fallback: if a commit fails with a non-zero return code
        # but the stderr is empty or short and there ARE staged changes, it's
        # most likely a hook that exited non-zero without a recognizable
        # message. Treat as hook failure rather than a generic error so the
        # caller can route it to needs_human and surface the output.
        combined = (commit_result.stderr + commit_result.stdout).strip()
        if combined:
            # Plausible hook output without a recognized marker.
            raise GitHookFailedError(
                f"git commit failed (rc={commit_result.returncode}): "
                f"{combined}",
                returncode=commit_result.returncode,
                stdout=commit_result.stdout,
                stderr=commit_result.stderr,
                command=full_cmd,
            )
        raise GitCommitError(
            f"git commit failed (rc={commit_result.returncode}) "
            f"with no output",
            returncode=commit_result.returncode,
            stdout=commit_result.stdout,
            stderr=commit_result.stderr,
            command=full_cmd,
        )

    # Get the SHA of the new commit
    sha_result = _run_git(["rev-parse", "HEAD"], workspace=workspace)
    if sha_result.returncode != 0:
        raise GitCommitError(
            f"git rev-parse HEAD failed: {sha_result.stderr.strip()}",
            returncode=sha_result.returncode,
            stdout=sha_result.stdout,
            stderr=sha_result.stderr,
            command=["git", "rev-parse", "HEAD"],
        )
    sha = sha_result.stdout.strip()
    logger.info("Created commit %s for feature %s", sha[:8], feature_id)
    return sha


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
    """
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
