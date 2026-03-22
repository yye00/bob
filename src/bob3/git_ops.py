"""Git operations for version control during Bob3 execution (F114).

Provides functions for:
- Committing feature work after successful completion
- Reverting feature commits during rollback operations
- Retrieving recent commit history for sub-agent orientation
- Checking working tree status for pre-execution verification
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


def _run_git(
    args: list[str],
    *,
    workspace: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in the given workspace.

    Args:
        args: Git sub-command and arguments (e.g. ["status", "--porcelain"]).
        workspace: Working directory for the git command.
        check: Whether to raise on non-zero exit code.

    Returns:
        The CompletedProcess result.
    """
    cmd = ["git"] + args
    return subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
        check=check,
    )


def commit_feature(
    *,
    feature_id: str,
    message: str,
    workspace: str,
    stage_all: bool = False,
) -> str | None:
    """Create a git commit for a completed feature.

    Args:
        feature_id: The feature ID (e.g. "F114") to include in the commit message.
        message: A human-readable commit message describing the change.
        workspace: Path to the git repository.
        stage_all: If True, stages all changes (git add -A) before committing.

    Returns:
        The full 40-character SHA of the new commit, or None if there was
        nothing to commit.
    """
    if stage_all:
        _run_git(["add", "-A"], workspace=workspace)

    # Check if there are staged changes
    result = _run_git(["diff", "--cached", "--quiet"], workspace=workspace, check=False)
    if result.returncode == 0:
        logger.info("No staged changes to commit for %s", feature_id)
        return None

    commit_msg = f"[{feature_id}] {message}"
    _run_git(["commit", "-m", commit_msg], workspace=workspace)

    # Get the SHA of the new commit
    sha_result = _run_git(["rev-parse", "HEAD"], workspace=workspace)
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
        The full 40-character SHA of the revert commit, or None if the
        revert failed (e.g. due to merge conflicts).
    """
    result = _run_git(
        ["revert", "--no-edit", commit_sha],
        workspace=workspace,
        check=False,
    )

    if result.returncode != 0:
        logger.warning(
            "Git revert failed for feature %s (commit %s): %s",
            feature_id, commit_sha[:8], result.stderr.strip(),
        )
        # Abort the revert if it left us in a conflicted state
        _run_git(["revert", "--abort"], workspace=workspace, check=False)
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
        check=False,
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
        check=False,
    )
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""

    # Get current HEAD SHA
    sha_result = _run_git(
        ["rev-parse", "HEAD"],
        workspace=workspace,
        check=False,
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
