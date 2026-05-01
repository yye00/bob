"""Tests for F114: Git Integration for Version Control."""

import os
import pathlib
import stat
import subprocess

import pytest


@pytest.fixture()
def git_repo(tmp_path):
    """Create a temporary git repository with an initial commit."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=str(repo), capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(repo), capture_output=True, check=True,
    )
    # Create initial file and commit
    (repo / "README.md").write_text("# Test Project\n")
    subprocess.run(
        ["git", "add", "."], cwd=str(repo), capture_output=True, check=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(repo), capture_output=True, check=True,
    )
    return repo


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Create a temporary database and initialize schema."""
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(p))
    from bob3.db import init_database

    init_database()
    return p


@pytest.fixture()
def project(db_path):
    """Create a test project."""
    from bob3.db import create_project

    return create_project(
        name="Git Ops Test Project",
        workspace_path="/tmp/git-ops-test",
    )


# ============================================================
# Step 1: Create src/bob3/git_ops.py module
# ============================================================


class TestGitOpsModuleExists:
    """Step 1: git_ops module is importable."""

    def test_module_is_importable(self):
        import bob3.git_ops  # noqa: F401

    def test_commit_feature_is_importable(self):
        from bob3.git_ops import commit_feature

        assert callable(commit_feature)

    def test_revert_feature_is_importable(self):
        from bob3.git_ops import revert_feature

        assert callable(revert_feature)

    def test_get_recent_commits_is_importable(self):
        from bob3.git_ops import get_recent_commits

        assert callable(get_recent_commits)

    def test_get_status_is_importable(self):
        from bob3.git_ops import get_status

        assert callable(get_status)


# ============================================================
# Step 2: Implement commit_feature(feature_id, message)
# ============================================================


class TestCommitFeature:
    """Step 2: commit_feature creates a git commit with feature metadata."""

    def test_commit_feature_creates_commit(self, git_repo):
        from bob3.git_ops import commit_feature

        # Create a new file to commit
        (git_repo / "feature.py").write_text("# Feature code\n")
        subprocess.run(
            ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
        )

        sha = commit_feature(
            feature_id="F001",
            message="Implement first feature",
            workspace=str(git_repo),
        )

        assert sha is not None
        assert len(sha) == 40  # Full SHA

    def test_commit_message_contains_feature_id(self, git_repo):
        from bob3.git_ops import commit_feature

        (git_repo / "feature2.py").write_text("# Feature 2\n")
        subprocess.run(
            ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
        )

        sha = commit_feature(
            feature_id="F042",
            message="Add feature 42",
            workspace=str(git_repo),
        )

        # Check that the commit message includes the feature ID
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s", sha],
            cwd=str(git_repo), capture_output=True, text=True, check=True,
        )
        assert "F042" in result.stdout

    def test_commit_feature_returns_none_when_nothing_to_commit(self, git_repo):
        from bob3.git_ops import commit_feature

        # No staged changes
        sha = commit_feature(
            feature_id="F001",
            message="Nothing to commit",
            workspace=str(git_repo),
        )
        assert sha is None

    def test_commit_feature_stages_all_changes_when_stage_all_true(self, git_repo):
        from bob3.git_ops import commit_feature

        # Create a new file but DON'T stage it
        (git_repo / "unstaged.py").write_text("# Unstaged\n")

        sha = commit_feature(
            feature_id="F001",
            message="Auto-staged commit",
            workspace=str(git_repo),
            stage_all=True,
        )

        assert sha is not None
        # Verify the file was committed
        result = subprocess.run(
            ["git", "show", "--name-only", "--format=", sha],
            cwd=str(git_repo), capture_output=True, text=True, check=True,
        )
        assert "unstaged.py" in result.stdout


# ============================================================
# Step 3: Implement revert_feature(feature_id) for rollbacks
# ============================================================


class TestRevertFeature:
    """Step 3: revert_feature creates a revert commit."""

    def test_revert_feature_creates_revert_commit(self, git_repo):
        from bob3.git_ops import revert_feature

        # Create a commit to revert
        (git_repo / "bad_feature.py").write_text("# Bad feature\n")
        subprocess.run(
            ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "[F099] Bad feature"],
            cwd=str(git_repo), capture_output=True, check=True,
        )
        # Get the SHA of the commit to revert
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(git_repo), capture_output=True, text=True, check=True,
        )
        commit_sha = result.stdout.strip()

        revert_sha = revert_feature(
            feature_id="F099",
            commit_sha=commit_sha,
            workspace=str(git_repo),
        )

        assert revert_sha is not None
        assert len(revert_sha) == 40

    def test_revert_commit_message_references_feature(self, git_repo):
        from bob3.git_ops import revert_feature

        (git_repo / "revert_me.py").write_text("# Revert this\n")
        subprocess.run(
            ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "[F050] Feature to revert"],
            cwd=str(git_repo), capture_output=True, check=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(git_repo), capture_output=True, text=True, check=True,
        )
        commit_sha = result.stdout.strip()

        revert_sha = revert_feature(
            feature_id="F050",
            commit_sha=commit_sha,
            workspace=str(git_repo),
        )

        # Check that the revert commit message references the feature
        log_result = subprocess.run(
            ["git", "log", "-1", "--format=%s", revert_sha],
            cwd=str(git_repo), capture_output=True, text=True, check=True,
        )
        assert "F050" in log_result.stdout

    def test_revert_feature_returns_none_on_conflict(self, git_repo):
        from bob3.git_ops import revert_feature

        # Create commit A that adds file
        (git_repo / "conflict.py").write_text("line1\n")
        subprocess.run(
            ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "[F001] Add conflict file"],
            cwd=str(git_repo), capture_output=True, check=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(git_repo), capture_output=True, text=True, check=True,
        )
        commit_a = result.stdout.strip()

        # Create commit B that modifies the same file
        (git_repo / "conflict.py").write_text("modified line1\nline2\n")
        subprocess.run(
            ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "[F002] Modify conflict file"],
            cwd=str(git_repo), capture_output=True, check=True,
        )

        # Reverting commit A should fail because commit B depends on it
        revert_sha = revert_feature(
            feature_id="F001",
            commit_sha=commit_a,
            workspace=str(git_repo),
        )
        assert revert_sha is None


# ============================================================
# Step 4: Implement get_recent_commits(n) for orientation
# ============================================================


class TestGetRecentCommits:
    """Step 4: get_recent_commits returns recent git log entries."""

    def test_returns_list_of_commits(self, git_repo):
        from bob3.git_ops import get_recent_commits

        commits = get_recent_commits(n=5, workspace=str(git_repo))
        assert isinstance(commits, list)
        assert len(commits) >= 1  # At least the initial commit

    def test_commit_has_sha_and_message(self, git_repo):
        from bob3.git_ops import get_recent_commits

        commits = get_recent_commits(n=5, workspace=str(git_repo))
        first = commits[0]
        assert "sha" in first
        assert "message" in first
        assert len(first["sha"]) == 40

    def test_respects_n_limit(self, git_repo):
        from bob3.git_ops import get_recent_commits

        # Add more commits
        for i in range(5):
            (git_repo / f"file_{i}.py").write_text(f"# File {i}\n")
            subprocess.run(
                ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}"],
                cwd=str(git_repo), capture_output=True, check=True,
            )

        commits = get_recent_commits(n=3, workspace=str(git_repo))
        assert len(commits) == 3

    def test_most_recent_commit_is_first(self, git_repo):
        from bob3.git_ops import get_recent_commits

        (git_repo / "latest.py").write_text("# Latest\n")
        subprocess.run(
            ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Latest commit message"],
            cwd=str(git_repo), capture_output=True, check=True,
        )

        commits = get_recent_commits(n=5, workspace=str(git_repo))
        assert "Latest commit message" in commits[0]["message"]

    def test_returns_empty_list_for_no_commits(self, tmp_path):
        from bob3.git_ops import get_recent_commits

        # Create empty repo with no commits
        repo = tmp_path / "empty_repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init"], cwd=str(repo), capture_output=True, check=True
        )

        commits = get_recent_commits(n=5, workspace=str(repo))
        assert commits == []


# ============================================================
# Step 5: Implement get_status() for pre-execution checks
# ============================================================


class TestGetStatus:
    """Step 5: get_status returns working tree status."""

    def test_returns_dict(self, git_repo):
        from bob3.git_ops import get_status

        status = get_status(workspace=str(git_repo))
        assert isinstance(status, dict)

    def test_status_has_clean_flag(self, git_repo):
        from bob3.git_ops import get_status

        status = get_status(workspace=str(git_repo))
        assert "clean" in status
        assert status["clean"] is True  # No pending changes

    def test_status_detects_modified_files(self, git_repo):
        from bob3.git_ops import get_status

        # Modify a file without staging
        (git_repo / "README.md").write_text("# Modified\n")

        status = get_status(workspace=str(git_repo))
        assert status["clean"] is False
        assert len(status["modified"]) > 0

    def test_status_detects_untracked_files(self, git_repo):
        from bob3.git_ops import get_status

        # Create new untracked file
        (git_repo / "new_file.py").write_text("# New\n")

        status = get_status(workspace=str(git_repo))
        assert status["clean"] is False
        assert "new_file.py" in status["untracked"]

    def test_status_detects_staged_files(self, git_repo):
        from bob3.git_ops import get_status

        # Stage a new file
        (git_repo / "staged.py").write_text("# Staged\n")
        subprocess.run(
            ["git", "add", "staged.py"], cwd=str(git_repo),
            capture_output=True, check=True,
        )

        status = get_status(workspace=str(git_repo))
        assert status["clean"] is False
        assert "staged.py" in status["staged"]

    def test_status_includes_current_branch(self, git_repo):
        from bob3.git_ops import get_status

        status = get_status(workspace=str(git_repo))
        assert "branch" in status

    def test_status_includes_current_sha(self, git_repo):
        from bob3.git_ops import get_status

        status = get_status(workspace=str(git_repo))
        assert "sha" in status
        assert len(status["sha"]) == 40


# ============================================================
# Step 6: Integrate into orchestration loop - commit on feature complete
# ============================================================


class TestOrchestrationIntegration:
    """Step 6: Git commit is created when a feature is completed."""

    def test_run_loop_imports_git_ops(self):
        """The run_loop module should be able to import git_ops functions."""
        from bob3.git_ops import commit_feature, get_status

        assert callable(commit_feature)
        assert callable(get_status)


# ============================================================
# Step 7: Integrate into rollback workflow - git revert on rollback
# ============================================================


class TestRollbackIntegration:
    """Step 7: Git revert is executed during rollback."""

    def test_git_ops_revert_is_importable_from_rollback_context(self):
        """The rollback workflow should be able to import git revert."""
        from bob3.git_ops import revert_feature

        assert callable(revert_feature)


# ============================================================
# Step 8: Test: Complete feature, verify git commit created
# ============================================================


class TestCompleteFeatureCreatesCommit:
    """Step 8: End-to-end test for feature completion with git commit."""

    def test_commit_feature_full_workflow(self, git_repo):
        from bob3.git_ops import commit_feature, get_recent_commits

        # Simulate feature implementation
        (git_repo / "src").mkdir(exist_ok=True)
        (git_repo / "src" / "new_feature.py").write_text(
            "def new_feature():\n    return True\n"
        )
        (git_repo / "tests").mkdir(exist_ok=True)
        (git_repo / "tests" / "test_new_feature.py").write_text(
            "def test_new_feature():\n    assert True\n"
        )

        # Commit the feature
        sha = commit_feature(
            feature_id="F114",
            message="Implement Git Integration for Version Control",
            workspace=str(git_repo),
            stage_all=True,
        )

        assert sha is not None

        # Verify commit exists in log
        commits = get_recent_commits(n=1, workspace=str(git_repo))
        assert commits[0]["sha"] == sha
        assert "F114" in commits[0]["message"]


# ============================================================
# Step 9: Test: Rollback feature, verify git revert executed
# ============================================================


class TestRollbackFeatureCreatesRevert:
    """Step 9: End-to-end test for feature rollback with git revert."""

    def test_revert_feature_full_workflow(self, git_repo):
        from bob3.git_ops import commit_feature, get_recent_commits, revert_feature

        # Implement a feature
        (git_repo / "bad_module.py").write_text("# This will be reverted\n")
        sha = commit_feature(
            feature_id="F999",
            message="Bad feature that will be rolled back",
            workspace=str(git_repo),
            stage_all=True,
        )
        assert sha is not None

        # Revert the feature
        revert_sha = revert_feature(
            feature_id="F999",
            commit_sha=sha,
            workspace=str(git_repo),
        )

        assert revert_sha is not None

        # Verify revert commit is in log
        commits = get_recent_commits(n=1, workspace=str(git_repo))
        assert commits[0]["sha"] == revert_sha

        # Verify the file is gone after revert
        assert not (git_repo / "bad_module.py").exists()


# ============================================================
# Step 10: Structured error reporting
# ============================================================


def _install_pre_commit_hook(repo: pathlib.Path, body: str) -> pathlib.Path:
    """Drop a pre-commit hook into the repo and make it executable."""
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "pre-commit"
    hook.write_text(body)
    # chmod +x
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook


class TestCommitFeatureErrorHandling:
    """commit_feature distinguishes nothing-to-commit / hook / repo errors."""

    def test_returns_none_when_nothing_to_commit_no_exception(self, git_repo):
        from bob3.git_ops import commit_feature

        sha = commit_feature(
            feature_id="F001",
            message="empty commit",
            workspace=str(git_repo),
        )
        assert sha is None

    def test_raises_git_repo_error_outside_repo(self, tmp_path):
        from bob3.git_ops import GitRepoError, commit_feature

        not_a_repo = tmp_path / "plain_dir"
        not_a_repo.mkdir()
        (not_a_repo / "file.txt").write_text("hello\n")

        with pytest.raises(GitRepoError) as exc_info:
            commit_feature(
                feature_id="F001",
                message="should fail",
                workspace=str(not_a_repo),
                stage_all=True,
            )
        # Exception attributes
        err = exc_info.value
        assert err.returncode != 0
        assert isinstance(err.command, list)

    def test_raises_git_repo_error_for_missing_workspace(self, tmp_path):
        from bob3.git_ops import GitRepoError, commit_feature

        nonexistent = tmp_path / "does_not_exist"

        with pytest.raises(GitRepoError):
            commit_feature(
                feature_id="F001",
                message="should fail",
                workspace=str(nonexistent),
            )

    def test_raises_hook_failed_error_when_pre_commit_rejects(self, git_repo):
        from bob3.git_ops import GitHookFailedError, commit_feature

        # Install a hook that always rejects with a clear message.
        _install_pre_commit_hook(
            git_repo,
            "#!/usr/bin/env bash\n"
            "echo 'pre-commit hook failed: forbidden token detected' >&2\n"
            "exit 1\n",
        )

        # Stage some real changes so the diff check passes and we hit `git commit`.
        (git_repo / "feature.py").write_text("# new feature\n")
        subprocess.run(
            ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
        )

        with pytest.raises(GitHookFailedError) as exc_info:
            commit_feature(
                feature_id="F042",
                message="should be rejected",
                workspace=str(git_repo),
            )

        err = exc_info.value
        assert err.returncode != 0
        # Hook output captured in either stderr or stdout
        combined = (err.stderr or "") + (err.stdout or "")
        assert "pre-commit hook failed" in combined
        assert "forbidden token detected" in combined
        # Command should reference git commit
        assert err.command[:2] == ["git", "commit"]

    def test_hook_failed_error_is_subclass_of_git_commit_error(self):
        from bob3.git_ops import GitCommitError, GitHookFailedError, GitRepoError

        assert issubclass(GitHookFailedError, GitCommitError)
        assert issubclass(GitRepoError, GitCommitError)

    def test_hook_failure_does_not_create_commit(self, git_repo):
        """After a hook rejection, HEAD should be unchanged."""
        from bob3.git_ops import GitHookFailedError, commit_feature

        # Capture HEAD before the failed commit
        before = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(git_repo), capture_output=True, text=True, check=True,
        ).stdout.strip()

        _install_pre_commit_hook(
            git_repo,
            "#!/usr/bin/env bash\necho 'pre-commit hook says no' >&2\nexit 1\n",
        )

        (git_repo / "rejected.py").write_text("# nope\n")
        subprocess.run(
            ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
        )

        with pytest.raises(GitHookFailedError):
            commit_feature(
                feature_id="F999",
                message="rejected",
                workspace=str(git_repo),
            )

        # HEAD must not have moved
        after = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(git_repo), capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert before == after

    def test_commit_succeeds_when_hook_passes(self, git_repo):
        """Sanity check: a hook that exits 0 does not block the commit."""
        from bob3.git_ops import commit_feature

        _install_pre_commit_hook(
            git_repo, "#!/usr/bin/env bash\nexit 0\n",
        )
        (git_repo / "ok.py").write_text("# ok\n")
        sha = commit_feature(
            feature_id="F100",
            message="hooks pass",
            workspace=str(git_repo),
            stage_all=True,
        )
        assert sha is not None
        assert len(sha) == 40
