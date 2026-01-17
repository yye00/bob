"""Tests for GitHubIssuesSource."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from bob.spec_sources import SpecSourceError
from bob.spec_sources.github_source import GitHubIssuesSource


# Sample GitHub issue response
SAMPLE_ISSUE = {
    "id": 123456,
    "number": 42,
    "title": "Add user authentication",
    "body": """Implement user login and registration.

## Acceptance Criteria
- Users can register with email/password
- Users can log in with credentials
- Sessions are maintained securely

## Steps
1. Create user model and database schema
2. Implement registration endpoint
3. Implement login endpoint
4. Add session management

Depends on: #40, #41
Priority: high
Category: functional
""",
    "state": "open",
    "labels": [
        {"id": 1, "name": "feature"},
        {"id": 2, "name": "backend"},
    ],
    "html_url": "https://github.com/owner/repo/issues/42",
    "created_at": "2024-01-01T10:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z",
    "user": {"login": "testuser"},
}

SAMPLE_ISSUE_WITH_LABELS = {
    "id": 123457,
    "number": 43,
    "title": "Optimize database queries",
    "body": "Improve query performance in the user service.",
    "state": "open",
    "labels": [
        {"id": 1, "name": "priority:critical"},
        {"id": 2, "name": "category:infrastructure"},
        {"id": 3, "name": "research-required"},
        {"id": 4, "name": "performance"},
    ],
    "html_url": "https://github.com/owner/repo/issues/43",
    "created_at": "2024-01-01T11:00:00Z",
    "updated_at": "2024-01-01T11:00:00Z",
    "user": {"login": "testuser"},
}

SAMPLE_CLOSED_ISSUE = {
    "id": 123458,
    "number": 44,
    "title": "Fix login bug",
    "body": "Login fails with invalid credentials.",
    "state": "closed",
    "labels": [{"id": 1, "name": "bug"}],
    "html_url": "https://github.com/owner/repo/issues/44",
    "created_at": "2024-01-01T09:00:00Z",
    "updated_at": "2024-01-02T10:00:00Z",
    "user": {"login": "testuser"},
}


class TestGitHubIssuesSourceInit:
    """Tests for GitHubIssuesSource initialization."""

    def test_init_basic_uri(self):
        """Test initializing with basic URI."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        assert source.owner == "owner"
        assert source.repo == "repo"
        assert source.state == "open"
        assert source.labels == []

    def test_init_uri_with_labels(self):
        """Test initializing with labels in URI."""
        source = GitHubIssuesSource("github://owner/repo/issues?labels=bug,feature")

        assert source.owner == "owner"
        assert source.repo == "repo"
        assert source.labels == ["bug", "feature"]

    def test_init_uri_with_state(self):
        """Test initializing with state in URI."""
        source = GitHubIssuesSource("github://owner/repo/issues?state=all")

        assert source.state == "all"

    def test_init_uri_with_multiple_params(self):
        """Test initializing with multiple query parameters."""
        source = GitHubIssuesSource(
            "github://owner/repo/issues?labels=bug,feature&state=closed&milestone=1.0"
        )

        assert source.labels == ["bug", "feature"]
        assert source.state == "closed"
        assert source.milestone == "1.0"

    def test_init_with_config_overrides(self):
        """Test config overrides URI parameters."""
        source = GitHubIssuesSource(
            "github://owner/repo/issues?labels=bug&state=open",
            config={
                "labels": "feature,enhancement",
                "state": "closed",
                "token": "test_token",
            },
        )

        assert source.labels == ["feature", "enhancement"]
        assert source.state == "closed"
        assert source.token == "test_token"

    def test_init_invalid_uri_scheme(self):
        """Test invalid URI scheme raises error."""
        with pytest.raises(SpecSourceError, match="must start with 'github://'"):
            GitHubIssuesSource("file://spec.yaml")

    def test_init_invalid_uri_format(self):
        """Test invalid URI format raises error."""
        with pytest.raises(SpecSourceError, match="expected format"):
            GitHubIssuesSource("github://invalid")


class TestGitHubIssuesSourceParsing:
    """Tests for parsing GitHub issues."""

    def test_parse_issue_body_with_sections(self):
        """Test parsing issue body with sections."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        parsed = source._parse_issue_body(SAMPLE_ISSUE["body"])

        assert "Implement user login and registration" in parsed["description"]
        assert len(parsed["acceptance_criteria"]) == 3
        assert "Users can register with email/password" in parsed["acceptance_criteria"]
        assert len(parsed["steps"]) == 4
        assert "Create user model and database schema" in parsed["steps"]
        assert parsed["depends_on"] == ["#40", "#41"]
        assert parsed["priority"] == "high"
        assert parsed["category"] == "functional"

    def test_parse_issue_body_empty(self):
        """Test parsing empty issue body."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        parsed = source._parse_issue_body("")

        assert parsed["description"] == ""
        assert parsed["acceptance_criteria"] == []
        assert parsed["steps"] == []
        assert parsed["depends_on"] == []
        assert parsed["priority"] == "medium"
        assert parsed["category"] == "functional"

    def test_parse_issue_body_no_sections(self):
        """Test parsing issue body without structured sections."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        body = "Simple description without sections."
        parsed = source._parse_issue_body(body)

        assert parsed["description"] == "Simple description without sections."
        assert parsed["acceptance_criteria"] == []
        assert parsed["steps"] == []

    def test_extract_labels_metadata(self):
        """Test extracting metadata from labels."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        labels = [
            {"name": "priority:high"},
            {"name": "category:infrastructure"},
            {"name": "research-required"},
            {"name": "feature"},
        ]

        metadata = source._extract_labels_metadata(labels)

        assert metadata["priority"] == "high"
        assert metadata["category"] == "infrastructure"
        assert metadata["research_required"] is True

    def test_extract_labels_metadata_no_metadata_labels(self):
        """Test extracting metadata when no metadata labels present."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        labels = [{"name": "feature"}, {"name": "backend"}]

        metadata = source._extract_labels_metadata(labels)

        assert metadata["priority"] is None
        assert metadata["category"] is None
        assert metadata["research_required"] is False

    def test_issue_to_task_spec(self):
        """Test converting GitHub issue to TaskSpec."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        task = source._issue_to_task_spec(SAMPLE_ISSUE)

        assert task.spec_id == "#42"
        assert task.title == "Add user authentication"
        assert "Implement user login and registration" in task.description
        assert len(task.acceptance_criteria) == 3
        assert len(task.steps) == 4
        assert task.depends_on == ["#40", "#41"]
        assert task.priority == "high"
        assert task.category == "functional"
        assert task.labels == ["feature", "backend"]
        assert task.metadata["github_number"] == 42
        assert task.metadata["github_url"] == "https://github.com/owner/repo/issues/42"
        assert task.deprecated is False

    def test_issue_to_task_spec_with_label_metadata(self):
        """Test converting issue with metadata in labels."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        task = source._issue_to_task_spec(SAMPLE_ISSUE_WITH_LABELS)

        assert task.spec_id == "#43"
        assert task.priority == "critical"  # From label
        assert task.category == "infrastructure"  # From label
        assert task.research_required is True  # From label
        assert task.labels == ["performance"]  # Metadata labels filtered out

    def test_issue_to_task_spec_closed(self):
        """Test converting closed issue marks task as deprecated."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        task = source._issue_to_task_spec(SAMPLE_CLOSED_ISSUE)

        assert task.spec_id == "#44"
        assert task.deprecated is True


class TestGitHubIssuesSourceFetch:
    """Tests for fetching tasks from GitHub."""

    @pytest.mark.asyncio
    async def test_fetch_tasks_success(self):
        """Test successfully fetching tasks from GitHub."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.json.return_value = [SAMPLE_ISSUE, SAMPLE_ISSUE_WITH_LABELS]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source._client = mock_client

        # Fetch tasks
        tasks = await source.fetch_tasks()

        assert len(tasks) == 2
        assert tasks[0].spec_id == "#42"
        assert tasks[1].spec_id == "#43"

        # Verify API call
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "/repos/owner/repo/issues" in call_args[0][0]
        assert call_args[1]["params"]["state"] == "open"

    @pytest.mark.asyncio
    async def test_fetch_tasks_with_labels_filter(self):
        """Test fetching tasks with label filter."""
        source = GitHubIssuesSource(
            "github://owner/repo/issues", config={"labels": "bug,feature"}
        )

        mock_response = MagicMock()
        mock_response.json.return_value = [SAMPLE_ISSUE]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source._client = mock_client

        await source.fetch_tasks()

        # Verify labels were passed to API
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["labels"] == "bug,feature"

    @pytest.mark.asyncio
    async def test_fetch_tasks_pagination(self):
        """Test fetching tasks with pagination."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        # Mock paginated responses
        mock_response_page1 = MagicMock()
        mock_response_page1.json.return_value = [SAMPLE_ISSUE] * 100
        mock_response_page1.raise_for_status = MagicMock()

        mock_response_page2 = MagicMock()
        mock_response_page2.json.return_value = [SAMPLE_ISSUE_WITH_LABELS]
        mock_response_page2.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.side_effect = [mock_response_page1, mock_response_page2]

        source._client = mock_client

        tasks = await source.fetch_tasks()

        # Should have fetched from both pages
        assert len(tasks) == 101
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_tasks_filters_pull_requests(self):
        """Test that pull requests are filtered out."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        # Include a pull request in response
        pr_item = SAMPLE_ISSUE.copy()
        pr_item["pull_request"] = {"url": "https://api.github.com/repos/owner/repo/pulls/42"}

        mock_response = MagicMock()
        mock_response.json.return_value = [SAMPLE_ISSUE, pr_item, SAMPLE_ISSUE_WITH_LABELS]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source._client = mock_client

        tasks = await source.fetch_tasks()

        # PR should be filtered out
        assert len(tasks) == 2
        assert all("#42" != task.spec_id or "pull_request" not in task.metadata for task in tasks)

    @pytest.mark.asyncio
    async def test_fetch_tasks_api_error(self):
        """Test handling API errors."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source._client = mock_client

        with pytest.raises(SpecSourceError, match="GitHub API error"):
            await source.fetch_tasks()

    @pytest.mark.asyncio
    async def test_fetch_tasks_network_error(self):
        """Test handling network errors."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.RequestError("Network error", request=MagicMock())

        source._client = mock_client

        with pytest.raises(SpecSourceError, match="request failed"):
            await source.fetch_tasks()


class TestGitHubIssuesSourceSync:
    """Tests for syncing tasks."""

    @pytest.mark.asyncio
    async def test_sync_no_changes(self):
        """Test sync with no changes."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        # Set up known issues
        source._known_issues = {42: SAMPLE_ISSUE}

        mock_response = MagicMock()
        mock_response.json.return_value = [SAMPLE_ISSUE]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source._client = mock_client

        # Sync with known tasks
        result = await source.sync({"#42": 1})

        assert len(result.added) == 0
        assert len(result.modified) == 0
        assert len(result.removed) == 0
        assert not result.has_changes

    @pytest.mark.asyncio
    async def test_sync_new_issue(self):
        """Test sync detects new issues."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        mock_response = MagicMock()
        mock_response.json.return_value = [SAMPLE_ISSUE, SAMPLE_ISSUE_WITH_LABELS]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source._client = mock_client

        # Sync with only one known task
        result = await source.sync({"#42": 1})

        assert len(result.added) == 1
        assert result.added[0].spec_id == "#43"
        assert len(result.modified) == 0
        assert len(result.removed) == 0

    @pytest.mark.asyncio
    async def test_sync_removed_issue(self):
        """Test sync detects removed issues."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        mock_response = MagicMock()
        mock_response.json.return_value = [SAMPLE_ISSUE]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source._client = mock_client

        # Sync with two known tasks, but only one exists
        result = await source.sync({"#42": 1, "#43": 1})

        assert len(result.added) == 0
        assert len(result.modified) == 0
        assert len(result.removed) == 1
        assert "#43" in result.removed

    @pytest.mark.asyncio
    async def test_sync_modified_issue(self):
        """Test sync detects modified issues."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        # Set up known issue with old timestamp
        old_issue = SAMPLE_ISSUE.copy()
        old_issue["updated_at"] = "2024-01-01T10:00:00Z"
        source._known_issues = {42: old_issue}

        # New issue with updated timestamp
        updated_issue = SAMPLE_ISSUE.copy()
        updated_issue["updated_at"] = "2024-01-02T12:00:00Z"

        mock_response = MagicMock()
        mock_response.json.return_value = [updated_issue]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source._client = mock_client

        result = await source.sync({"#42": 1})

        assert len(result.added) == 0
        assert len(result.modified) == 1
        assert result.modified[0].spec_id == "#42"
        assert len(result.removed) == 0

    @pytest.mark.asyncio
    async def test_sync_closed_issue(self):
        """Test sync detects closed issues."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        mock_response = MagicMock()
        mock_response.json.return_value = [SAMPLE_CLOSED_ISSUE]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source._client = mock_client

        # Sync with issue that's now closed
        result = await source.sync({"#44": 1})

        # Closed issue should appear as modified
        assert len(result.modified) == 1
        assert result.modified[0].spec_id == "#44"
        assert result.modified[0].deprecated is True

    @pytest.mark.asyncio
    async def test_sync_api_error(self):
        """Test sync handles API errors gracefully."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        source._client = mock_client

        result = await source.sync({"#42": 1})

        # Should return result with errors
        assert len(result.errors) > 0
        assert not result.has_changes


class TestGitHubIssuesSourceMarkCompleted:
    """Tests for marking tasks completed."""

    @pytest.mark.asyncio
    async def test_mark_completed_success(self):
        """Test successfully marking task complete."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        mock_comment_response = MagicMock()
        mock_comment_response.raise_for_status = MagicMock()

        mock_close_response = MagicMock()
        mock_close_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_comment_response
        mock_client.patch.return_value = mock_close_response

        source._client = mock_client

        # Mark task complete
        result = await source.mark_completed("#42", {"pr_url": "https://github.com/owner/repo/pull/100"})

        assert result is True

        # Verify comment was posted
        assert mock_client.post.called
        comment_call = mock_client.post.call_args
        assert "/issues/42/comments" in comment_call[0][0]
        assert "BOB Framework" in comment_call[1]["json"]["body"]
        assert "pr_url" in comment_call[1]["json"]["body"]

        # Verify issue was closed
        assert mock_client.patch.called
        close_call = mock_client.patch.call_args
        assert "/issues/42" in close_call[0][0]
        assert close_call[1]["json"]["state"] == "closed"

    @pytest.mark.asyncio
    async def test_mark_completed_invalid_spec_id(self):
        """Test mark_completed with invalid spec_id."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        # Invalid spec_id (not starting with #)
        result = await source.mark_completed("42")
        assert result is False

        # Invalid spec_id (not a number)
        result = await source.mark_completed("#abc")
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_completed_api_error(self):
        """Test mark_completed handles API errors."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=MagicMock()
        )

        source._client = mock_client

        result = await source.mark_completed("#42")

        assert result is False


class TestGitHubIssuesSourceClientManagement:
    """Tests for HTTP client management."""

    def test_get_client_creates_client(self):
        """Test _get_client creates client with proper headers."""
        source = GitHubIssuesSource("github://owner/repo/issues", config={"token": "test_token"})

        client = source._get_client()

        assert client is not None
        assert client.headers["Accept"] == "application/vnd.github.v3+json"
        assert client.headers["Authorization"] == "Bearer test_token"
        assert client.headers["User-Agent"] == "BOB-Framework"

    def test_get_client_no_token(self):
        """Test _get_client without token."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        client = source._get_client()

        assert client is not None
        assert "Authorization" not in client.headers

    def test_get_client_reuses_instance(self):
        """Test _get_client reuses the same client instance."""
        source = GitHubIssuesSource("github://owner/repo/issues")

        client1 = source._get_client()
        client2 = source._get_client()

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self):
        """Test async context manager cleans up client."""
        async with GitHubIssuesSource("github://owner/repo/issues") as source:
            client = source._get_client()
            assert client is not None

        # Client should be closed after exiting context
        assert source._client is None
