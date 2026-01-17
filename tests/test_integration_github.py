"""Integration tests for GitHub Issues as spec source.

This module tests the complete GitHub issues integration workflow:
- Project creation with GitHub source
- Task synchronization from issues
- Task execution and completion
- GitHub issue updates and closure
- Sync detection of new issues

Note: These tests use mocked GitHub API responses to avoid requiring actual
GitHub credentials and repository access.
"""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models.base import Project, ProjectStatus, Task, TaskStatus
from bob.spec_sources.github_source import GitHubIssuesSource


# Sample GitHub issue responses
SAMPLE_GITHUB_ISSUES = [
    {
        "id": 123456,
        "number": 1,
        "title": "Setup project structure",
        "body": """Initialize the basic project structure.

## Steps
1. Create directory structure
2. Add configuration files
3. Setup version control

Priority: high
Category: infrastructure
""",
        "state": "open",
        "labels": [
            {"id": 1, "name": "bob-task"},
            {"id": 2, "name": "setup"},
        ],
        "html_url": "https://github.com/test-owner/test-repo/issues/1",
        "created_at": "2024-01-01T10:00:00Z",
        "updated_at": "2024-01-01T10:00:00Z",
        "user": {"login": "testuser"},
    },
    {
        "id": 123457,
        "number": 2,
        "title": "Implement user authentication",
        "body": """Add user login functionality.

## Acceptance Criteria
- Users can log in with email/password
- Sessions are maintained securely
- Password reset functionality

## Steps
1. Create user model
2. Implement login endpoint
3. Add session management
4. Add password reset

Depends on: #1
Priority: critical
Category: functional
""",
        "state": "open",
        "labels": [
            {"id": 1, "name": "bob-task"},
            {"id": 2, "name": "feature"},
        ],
        "html_url": "https://github.com/test-owner/test-repo/issues/2",
        "created_at": "2024-01-01T11:00:00Z",
        "updated_at": "2024-01-01T11:00:00Z",
        "user": {"login": "testuser"},
    },
]

NEW_GITHUB_ISSUE = {
    "id": 123458,
    "number": 3,
    "title": "Add dashboard",
    "body": "Create admin dashboard for monitoring.",
    "state": "open",
    "labels": [
        {"id": 1, "name": "bob-task"},
        {"id": 2, "name": "feature"},
    ],
    "html_url": "https://github.com/test-owner/test-repo/issues/3",
    "created_at": "2024-01-02T10:00:00Z",
    "updated_at": "2024-01-02T10:00:00Z",
    "user": {"login": "testuser"},
}


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database for testing.

    Args:
        tmp_path: Pytest temporary directory

    Returns:
        Path to temporary database file
    """
    db_path = tmp_path / "test_github.db"
    return db_path


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner.

    Returns:
        Click CliRunner instance
    """
    return CliRunner()


class TestGitHubIntegrationProjectCreation:
    """Tests for creating projects with GitHub issues source."""

    @pytest.mark.asyncio
    async def test_create_project_with_github_source(self, temp_db: Path, runner: CliRunner):
        """Test creating a project with GitHub issues as source."""
        # Mock GitHub API responses
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_GITHUB_ISSUES
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.post.return_value = MagicMock()
            mock_client.patch.return_value = MagicMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Create database manager (synchronous initialization)
            db_manager = DatabaseManager(str(temp_db))

            # Create GitHub source
            source = GitHubIssuesSource(
                "github://test-owner/test-repo/issues?labels=bob-task"
            )

            # Set the mocked client
            source._client = mock_client

            # Fetch tasks
            tasks = await source.fetch_tasks()

            # Verify tasks were fetched
            assert len(tasks) == 2
            assert tasks[0].spec_id == "#1"
            assert tasks[0].title == "Setup project structure"
            assert tasks[0].priority == "high"
            assert tasks[0].category == "infrastructure"
            assert len(tasks[0].steps) == 3

            assert tasks[1].spec_id == "#2"
            assert tasks[1].title == "Implement user authentication"
            assert tasks[1].priority == "critical"
            assert tasks[1].category == "functional"
            assert tasks[1].depends_on == ["#1"]
            assert len(tasks[1].acceptance_criteria) == 3
            assert len(tasks[1].steps) == 4

            # Create project in database
            project = Project(
                id="proj_github_test",
                name="github-test",
                description="Test GitHub integration project",
                workspace_dir=str(temp_db.parent / "workspace"),
                spec_source="github://test-owner/test-repo/issues?labels=bob-task",
                status=ProjectStatus.ACTIVE,
            )
            db_manager.create_project(project)

            # Create tasks in database
            for i, task_spec in enumerate(tasks):
                task = Task(
                    id=f"task_{i+1}",
                    project_id=project.id,
                    spec_id=task_spec.spec_id,
                    title=task_spec.title,
                    description=task_spec.description,
                    status=TaskStatus.PENDING,
                    priority=task_spec.priority,
                    category=task_spec.category,
                    depends_on=task_spec.depends_on,
                    labels=task_spec.labels,
                )
                db_manager.create_task(task)

            # Verify tasks were saved
            saved_tasks = db_manager.list_tasks(project_id=project.id)
            assert len(saved_tasks) == 2

    @pytest.mark.asyncio
    async def test_github_source_with_labels_filter(self):
        """Test GitHub source with label filtering."""
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_GITHUB_ISSUES
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source = GitHubIssuesSource(
            "github://test-owner/test-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        tasks = await source.fetch_tasks()

        # Verify API was called with labels parameter
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["labels"] == "bob-task"

        # Verify tasks fetched
        assert len(tasks) == 2


class TestGitHubIntegrationSync:
    """Tests for syncing tasks with GitHub issues."""

    @pytest.mark.asyncio
    async def test_sync_detects_new_issues(self):
        """Test that sync detects new GitHub issues."""
        # Initial fetch
        mock_response_initial = MagicMock()
        mock_response_initial.json.return_value = SAMPLE_GITHUB_ISSUES
        mock_response_initial.raise_for_status = MagicMock()

        # Sync with new issue
        all_issues = SAMPLE_GITHUB_ISSUES + [NEW_GITHUB_ISSUE]
        mock_response_sync = MagicMock()
        mock_response_sync.json.return_value = all_issues
        mock_response_sync.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        # First call for initial fetch, second for sync
        mock_client.get.side_effect = [mock_response_initial, mock_response_sync]

        source = GitHubIssuesSource(
            "github://test-owner/test-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        # Initial fetch
        tasks = await source.fetch_tasks()
        assert len(tasks) == 2

        # Sync
        known_tasks = {"#1": 1, "#2": 1}
        sync_result = await source.sync(known_tasks)

        # Verify new issue was detected
        assert len(sync_result.added) == 1
        assert sync_result.added[0].spec_id == "#3"
        assert sync_result.added[0].title == "Add dashboard"
        assert sync_result.has_changes

    @pytest.mark.asyncio
    async def test_sync_detects_modified_issues(self):
        """Test that sync detects modified GitHub issues."""
        # Initial issue
        initial_issue = SAMPLE_GITHUB_ISSUES[0].copy()
        initial_issue["updated_at"] = "2024-01-01T10:00:00Z"

        # Modified issue (same issue but updated)
        modified_issue = SAMPLE_GITHUB_ISSUES[0].copy()
        modified_issue["updated_at"] = "2024-01-02T15:00:00Z"
        modified_issue["body"] = modified_issue["body"] + "\n\n**UPDATED**"

        mock_response_initial = MagicMock()
        mock_response_initial.json.return_value = [initial_issue]
        mock_response_initial.raise_for_status = MagicMock()

        mock_response_sync = MagicMock()
        mock_response_sync.json.return_value = [modified_issue]
        mock_response_sync.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.side_effect = [mock_response_initial, mock_response_sync]

        source = GitHubIssuesSource(
            "github://test-owner/test-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        # Initial fetch
        tasks = await source.fetch_tasks()
        assert len(tasks) == 1

        # Sync
        sync_result = await source.sync({"#1": 1})

        # Verify modified issue was detected
        assert len(sync_result.modified) == 1
        assert sync_result.modified[0].spec_id == "#1"
        assert sync_result.has_changes

    @pytest.mark.asyncio
    async def test_sync_detects_closed_issues(self):
        """Test that sync detects closed GitHub issues."""
        # Open issue
        open_issue = SAMPLE_GITHUB_ISSUES[0].copy()

        # Closed issue
        closed_issue = SAMPLE_GITHUB_ISSUES[0].copy()
        closed_issue["state"] = "closed"
        closed_issue["updated_at"] = "2024-01-02T10:00:00Z"

        mock_response_initial = MagicMock()
        mock_response_initial.json.return_value = [open_issue]
        mock_response_initial.raise_for_status = MagicMock()

        mock_response_sync = MagicMock()
        mock_response_sync.json.return_value = [closed_issue]
        mock_response_sync.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.side_effect = [mock_response_initial, mock_response_sync]

        source = GitHubIssuesSource(
            "github://test-owner/test-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        # Initial fetch
        tasks = await source.fetch_tasks()
        assert len(tasks) == 1
        assert tasks[0].deprecated is False

        # Sync (fetch with state=all to see closed issues)
        sync_result = await source.sync({"#1": 1})

        # Verify closed issue is marked as deprecated
        assert len(sync_result.modified) == 1
        assert sync_result.modified[0].deprecated is True


class TestGitHubIntegrationMarkCompleted:
    """Tests for marking tasks completed and updating GitHub issues."""

    @pytest.mark.asyncio
    async def test_mark_task_completed_closes_issue(self):
        """Test that marking a task completed closes the GitHub issue."""
        mock_comment_response = MagicMock()
        mock_comment_response.raise_for_status = MagicMock()

        mock_close_response = MagicMock()
        mock_close_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_comment_response
        mock_client.patch.return_value = mock_close_response

        source = GitHubIssuesSource(
            "github://test-owner/test-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        # Mark task as completed
        metadata = {
            "session_id": "sess_123",
            "completed_at": "2024-01-02T10:00:00Z",
        }
        result = await source.mark_completed("#1", metadata)

        # Verify it succeeded
        assert result is True

        # Verify comment was posted
        assert mock_client.post.called
        comment_call = mock_client.post.call_args
        assert "/repos/test-owner/test-repo/issues/1/comments" in comment_call[0][0]
        comment_body = comment_call[1]["json"]["body"]
        assert "BOB Framework" in comment_body
        assert "session_id" in comment_body
        assert "completed_at" in comment_body

        # Verify issue was closed
        assert mock_client.patch.called
        close_call = mock_client.patch.call_args
        assert "/repos/test-owner/test-repo/issues/1" in close_call[0][0]
        assert close_call[1]["json"]["state"] == "closed"

    @pytest.mark.asyncio
    async def test_mark_completed_with_pr_link(self):
        """Test marking completed with pull request link."""
        mock_comment_response = MagicMock()
        mock_comment_response.raise_for_status = MagicMock()

        mock_close_response = MagicMock()
        mock_close_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_comment_response
        mock_client.patch.return_value = mock_close_response

        source = GitHubIssuesSource(
            "github://test-owner/test-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        # Mark task as completed with PR link
        metadata = {"pr_url": "https://github.com/test-owner/test-repo/pull/100"}
        result = await source.mark_completed("#1", metadata)

        assert result is True

        # Verify PR link is in comment
        comment_call = mock_client.post.call_args
        comment_body = comment_call[1]["json"]["body"]
        assert "pr_url" in comment_body
        assert "pull/100" in comment_body


class TestGitHubIntegrationEndToEnd:
    """End-to-end integration tests for GitHub workflow."""

    @pytest.mark.asyncio
    async def test_full_github_workflow(self, temp_db: Path):
        """Test complete workflow: create project, sync, complete task, verify update."""
        # Setup mocks
        mock_response_initial = MagicMock()
        mock_response_initial.json.return_value = SAMPLE_GITHUB_ISSUES
        mock_response_initial.raise_for_status = MagicMock()

        # After completion, issue should be closed with updated timestamp
        closed_issue = SAMPLE_GITHUB_ISSUES[0].copy()
        closed_issue["state"] = "closed"
        closed_issue["updated_at"] = "2024-01-02T15:00:00Z"  # Different from original

        mock_response_after_completion = MagicMock()
        mock_response_after_completion.json.return_value = [
            closed_issue,
            SAMPLE_GITHUB_ISSUES[1],
        ]
        mock_response_after_completion.raise_for_status = MagicMock()

        # Sync should detect new issue
        all_issues = [closed_issue, SAMPLE_GITHUB_ISSUES[1], NEW_GITHUB_ISSUE]
        mock_response_sync = MagicMock()
        mock_response_sync.json.return_value = all_issues
        mock_response_sync.raise_for_status = MagicMock()

        mock_comment_response = MagicMock()
        mock_comment_response.raise_for_status = MagicMock()

        mock_close_response = MagicMock()
        mock_close_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            mock_response_initial,
            mock_response_after_completion,
            mock_response_sync,
        ]
        mock_client.post.return_value = mock_comment_response
        mock_client.patch.return_value = mock_close_response

        # Initialize database (synchronous)
        db_manager = DatabaseManager(str(temp_db))

        # Step 1: Create project with GitHub source
        source = GitHubIssuesSource(
            "github://test-owner/test-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        tasks = await source.fetch_tasks()
        assert len(tasks) == 2

        # Cache the initial issues for sync detection
        source._known_issues = {
            1: SAMPLE_GITHUB_ISSUES[0],
            2: SAMPLE_GITHUB_ISSUES[1],
        }

        project = Project(
            id="proj_github_workflow",
            name="github-test",
            description="Test GitHub workflow",
            workspace_dir=str(temp_db.parent / "workspace"),
            spec_source="github://test-owner/test-repo/issues?labels=bob-task",
            status=ProjectStatus.ACTIVE,
        )
        db_manager.create_project(project)

        # Create tasks
        for i, task_spec in enumerate(tasks):
            task = Task(
                id=f"task_wf_{i+1}",
                project_id=project.id,
                spec_id=task_spec.spec_id,
                title=task_spec.title,
                description=task_spec.description,
                status=TaskStatus.PENDING,
                priority=task_spec.priority,
                category=task_spec.category,
            )
            db_manager.create_task(task)

        # Step 2: Simulate completing first task
        saved_tasks = db_manager.list_tasks(project_id=project.id)
        task_to_complete = [t for t in saved_tasks if t.spec_id == "#1"][0]
        task_to_complete.status = TaskStatus.COMPLETED
        db_manager.update_task(task_to_complete)

        # Step 3: Mark completed on GitHub
        result = await source.mark_completed("#1", {"task_id": task_to_complete.id})
        assert result is True

        # Verify GitHub API was called to close issue
        assert mock_client.post.called  # Comment posted
        assert mock_client.patch.called  # Issue closed

        # Step 4: Sync to verify issue was closed
        sync_result = await source.sync({"#1": 1, "#2": 1})
        assert len(sync_result.modified) >= 1
        closed_task = [t for t in sync_result.modified if t.spec_id == "#1"]
        if closed_task:
            assert closed_task[0].deprecated is True

        # Step 5: Sync again to detect new issue
        all_sync_result = await source.sync({"#1": 1, "#2": 1})
        assert len(all_sync_result.added) == 1
        assert all_sync_result.added[0].spec_id == "#3"
        assert all_sync_result.added[0].title == "Add dashboard"

    @pytest.mark.asyncio
    async def test_github_workflow_with_dependencies(self, temp_db: Path):
        """Test GitHub workflow respects task dependencies."""
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_GITHUB_ISSUES
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        # Database manager (synchronous initialization)
        db_manager = DatabaseManager(str(temp_db))

        # Create project
        source = GitHubIssuesSource(
            "github://test-owner/test-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        tasks = await source.fetch_tasks()

        # Verify dependencies
        task1 = [t for t in tasks if t.spec_id == "#1"][0]
        task2 = [t for t in tasks if t.spec_id == "#2"][0]

        assert task1.depends_on == []
        assert task2.depends_on == ["#1"]

        # Task 2 should not be executed before task 1
        # This would be enforced by the task scheduler


class TestGitHubIntegrationErrorHandling:
    """Tests for error handling in GitHub integration."""

    @pytest.mark.asyncio
    async def test_handle_api_rate_limiting(self):
        """Test handling of GitHub API rate limiting."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Rate limit", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source = GitHubIssuesSource(
            "github://test-owner/test-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        # Should raise SpecSourceError
        from bob.spec_sources import SpecSourceError

        with pytest.raises(SpecSourceError, match="GitHub API error"):
            await source.fetch_tasks()

    @pytest.mark.asyncio
    async def test_handle_invalid_repository(self):
        """Test handling of invalid repository (404)."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source = GitHubIssuesSource(
            "github://test-owner/nonexistent-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        from bob.spec_sources import SpecSourceError

        with pytest.raises(SpecSourceError, match="GitHub API error"):
            await source.fetch_tasks()

    @pytest.mark.asyncio
    async def test_sync_continues_on_error(self):
        """Test that sync returns errors gracefully without crashing."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source = GitHubIssuesSource(
            "github://test-owner/test-repo/issues?labels=bob-task"
        )
        source._client = mock_client

        # Sync should not crash, but return error
        result = await source.sync({"#1": 1})

        assert len(result.errors) > 0
        assert not result.has_changes
