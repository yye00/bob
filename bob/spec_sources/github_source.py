"""GitHub Issues spec source implementation.

Pulls task specifications from GitHub Issues, allowing BOB to manage
development tasks directly from GitHub's issue tracker.
"""

import re
from datetime import datetime
from typing import Any, Optional

import httpx

from bob.spec_sources.base import (
    SpecSource,
    SpecSourceError,
    SyncResult,
    TaskSpec,
)


class GitHubIssuesSource(SpecSource):
    """Spec source that reads from GitHub Issues.

    URI format: github://owner/repo/issues?labels=label1,label2&state=open

    Configuration options:
    - token: GitHub Personal Access Token (required for private repos)
    - labels: Comma-separated list of labels to filter issues
    - state: Issue state filter (open, closed, all) - default: open
    - milestone: Filter by milestone number or title

    Issue Format:
    - Issue title becomes the task title
    - Issue body is parsed for description, acceptance criteria, and steps
    - Issue number becomes the spec_id
    - Labels are mapped to task labels
    - Dependencies can be specified with "Depends on: #123, #124" in the body
    - Priority can be specified with label "priority:high" or in body
    - Category defaults to "functional" but can be set via label "category:infrastructure"

    Example issue body:
    ```markdown
    Description of the feature.

    ## Acceptance Criteria
    - Criterion 1
    - Criterion 2

    ## Steps
    1. Step 1
    2. Step 2

    Depends on: #42, #43
    Priority: high
    Category: functional
    ```
    """

    def __init__(self, source_uri: str, config: Optional[dict[str, Any]] = None):
        """Initialize GitHubIssuesSource.

        Args:
            source_uri: URI in format "github://owner/repo/issues?labels=..."
            config: Optional configuration dict with:
                - token: GitHub API token (optional, for private repos)
                - labels: Labels to filter (overrides URI query)
                - state: Issue state (overrides URI query)
                - milestone: Milestone filter

        Raises:
            SpecSourceError: If URI is invalid
        """
        super().__init__(source_uri, config)

        # Parse URI
        if not source_uri.startswith("github://"):
            raise SpecSourceError(
                f"Invalid GitHub URI '{source_uri}': must start with 'github://'"
            )

        # Extract owner/repo from URI
        # Format: github://owner/repo/issues?labels=...
        uri_parts = source_uri.replace("github://", "").split("?", 1)
        path = uri_parts[0]
        query = uri_parts[1] if len(uri_parts) > 1 else ""

        # Parse path (should be owner/repo/issues)
        path_parts = path.rstrip("/").split("/")
        if len(path_parts) < 2:
            raise SpecSourceError(
                f"Invalid GitHub URI '{source_uri}': expected format 'github://owner/repo/issues'"
            )

        self.owner = path_parts[0]
        self.repo = path_parts[1]

        # Parse query parameters
        query_params = self._parse_query_string(query)

        # Get configuration (config overrides URI query)
        self.token = self.config.get("token")
        self.labels = self.config.get("labels", query_params.get("labels", "")).split(",")
        self.labels = [label.strip() for label in self.labels if label.strip()]
        self.state = self.config.get("state", query_params.get("state", "open"))
        self.milestone = self.config.get("milestone", query_params.get("milestone"))

        # API base URL
        self.api_base = "https://api.github.com"

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

        # Cache for issue tracking
        self._known_issues: dict[int, dict[str, Any]] = {}

    def _parse_query_string(self, query: str) -> dict[str, str]:
        """Parse query string into dict.

        Args:
            query: Query string (e.g., "labels=bug,feature&state=open")

        Returns:
            Dict of query parameters
        """
        params = {}
        if not query:
            return params

        for pair in query.split("&"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                params[key] = value

        return params

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client.

        Returns:
            Configured AsyncClient
        """
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "BOB-Framework",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            self._client = httpx.AsyncClient(
                base_url=self.api_base,
                headers=headers,
                timeout=30.0,
            )

        return self._client

    async def _fetch_issues(
        self,
        state: Optional[str] = None,
        labels: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Fetch issues from GitHub API.

        Args:
            state: Issue state filter (open, closed, all)
            labels: List of labels to filter by

        Returns:
            List of issue dicts from GitHub API

        Raises:
            SpecSourceError: If API request fails
        """
        client = self._get_client()

        # Build request parameters
        params: dict[str, Any] = {
            "state": state or self.state,
            "per_page": 100,
        }

        if labels or self.labels:
            label_list = labels if labels is not None else self.labels
            params["labels"] = ",".join(label_list)

        if self.milestone:
            params["milestone"] = self.milestone

        # Fetch issues
        all_issues = []
        page = 1

        try:
            while True:
                params["page"] = page
                response = await client.get(
                    f"/repos/{self.owner}/{self.repo}/issues",
                    params=params,
                )
                response.raise_for_status()

                issues = response.json()
                if not issues:
                    break

                # Filter out pull requests (they appear in issues API)
                issues = [issue for issue in issues if "pull_request" not in issue]

                all_issues.extend(issues)

                # Check if there are more pages
                if len(issues) < params["per_page"]:
                    break

                page += 1

        except httpx.HTTPStatusError as e:
            raise SpecSourceError(
                f"GitHub API error: {e.response.status_code} - {e.response.text}"
            )
        except httpx.RequestError as e:
            raise SpecSourceError(f"GitHub API request failed: {e}")

        return all_issues

    def _parse_issue_body(self, body: str) -> dict[str, Any]:
        """Parse issue body to extract structured information.

        Looks for sections like:
        - ## Acceptance Criteria
        - ## Steps
        - Depends on: #123, #124
        - Priority: high
        - Category: functional

        Args:
            body: Issue body text

        Returns:
            Dict with parsed fields
        """
        if not body:
            body = ""

        parsed = {
            "description": "",
            "acceptance_criteria": [],
            "steps": [],
            "depends_on": [],
            "priority": "medium",
            "category": "functional",
        }

        # First, extract metadata from the entire body (can appear anywhere)
        for line in body.split("\n"):
            line_lower = line.strip().lower()
            if line_lower.startswith("depends on:"):
                # Extract issue numbers
                depends_match = re.findall(r'#(\d+)', line)
                parsed["depends_on"] = [f"#{num}" for num in depends_match]
            elif line_lower.startswith("priority:"):
                priority = line.split(":", 1)[1].strip().lower()
                if priority in ("critical", "high", "medium", "low"):
                    parsed["priority"] = priority
            elif line_lower.startswith("category:"):
                category = line.split(":", 1)[1].strip().lower()
                parsed["category"] = category

        # Split by ## headers
        sections = re.split(r'^## (.+)$', body, flags=re.MULTILINE)

        # First section is the main description
        main_section = sections[0].strip()

        # Extract description (remove metadata lines)
        description_lines = []
        for line in main_section.split("\n"):
            line_lower = line.strip().lower()
            # Skip metadata lines
            if not (line_lower.startswith("depends on:") or
                    line_lower.startswith("priority:") or
                    line_lower.startswith("category:")):
                description_lines.append(line)

        # Description is everything except metadata
        parsed["description"] = "\n".join(description_lines).strip()

        # Process remaining sections (pairs of title and content)
        for i in range(1, len(sections), 2):
            if i + 1 >= len(sections):
                break

            section_title = sections[i].strip().lower()
            section_content = sections[i + 1].strip()

            # Extract metadata from section content too
            content_lines = []
            for line in section_content.split("\n"):
                line_lower = line.strip().lower()
                # Skip metadata lines in section content
                if not (line_lower.startswith("depends on:") or
                        line_lower.startswith("priority:") or
                        line_lower.startswith("category:")):
                    content_lines.append(line)

            clean_content = "\n".join(content_lines).strip()

            if "acceptance" in section_title or "criteria" in section_title:
                parsed["acceptance_criteria"] = self._parse_markdown_list(clean_content)
            elif "step" in section_title or "implementation" in section_title:
                parsed["steps"] = self._parse_markdown_list(clean_content)

        return parsed

    def _parse_markdown_list(self, content: str) -> list[str]:
        """Parse markdown list into items.

        Args:
            content: List content

        Returns:
            List of items without bullets/numbers
        """
        items = []

        # Match lines starting with -, *, or numbers followed by .
        list_pattern = re.compile(r'^(?:\s*[-*]\s+|\s*\d+\.\s+)(.+)$', re.MULTILINE)

        for match in list_pattern.finditer(content):
            item = match.group(1).strip()
            if item:
                items.append(item)

        return items

    def _extract_labels_metadata(self, labels: list[dict[str, Any]]) -> dict[str, Any]:
        """Extract metadata from issue labels.

        Supports labels like:
        - priority:high
        - category:infrastructure
        - research-required

        Args:
            labels: List of label dicts from GitHub API

        Returns:
            Dict with extracted metadata
        """
        metadata = {
            "priority": None,
            "category": None,
            "research_required": False,
        }

        label_names = [label["name"].lower() for label in labels]

        for name in label_names:
            if name.startswith("priority:"):
                priority = name.split(":", 1)[1]
                if priority in ("critical", "high", "medium", "low"):
                    metadata["priority"] = priority
            elif name.startswith("category:"):
                category = name.split(":", 1)[1]
                metadata["category"] = category
            elif name in ("research-required", "research_needed", "needs-research"):
                metadata["research_required"] = True

        return metadata

    def _issue_to_task_spec(self, issue: dict[str, Any]) -> TaskSpec:
        """Convert a GitHub issue to a TaskSpec.

        Args:
            issue: Issue dict from GitHub API

        Returns:
            TaskSpec instance
        """
        # Parse issue body
        body_data = self._parse_issue_body(issue.get("body", ""))

        # Extract metadata from labels
        label_metadata = self._extract_labels_metadata(issue.get("labels", []))

        # Combine metadata (labels override body)
        priority = label_metadata["priority"] or body_data["priority"]
        category = label_metadata["category"] or body_data["category"]
        research_required = label_metadata["research_required"]

        # Get label names (excluding metadata labels)
        labels = []
        for label in issue.get("labels", []):
            name = label["name"]
            # Skip metadata labels
            if not (name.startswith("priority:") or name.startswith("category:") or
                    name in ("research-required", "research_needed", "needs-research")):
                labels.append(name)

        # Build TaskSpec
        return TaskSpec(
            spec_id=f"#{issue['number']}",
            title=issue["title"],
            description=body_data["description"],
            acceptance_criteria=body_data["acceptance_criteria"],
            steps=body_data["steps"],
            depends_on=body_data["depends_on"],
            priority=priority,
            category=category,
            labels=labels,
            research_required=research_required,
            research_queries=[],
            metadata={
                "github_id": issue["id"],
                "github_number": issue["number"],
                "github_url": issue["html_url"],
                "github_state": issue["state"],
                "github_created_at": issue["created_at"],
                "github_updated_at": issue["updated_at"],
                "github_user": issue["user"]["login"],
            },
            spec_version=1,
            deprecated=issue["state"] == "closed",
        )

    async def fetch_tasks(self) -> list[TaskSpec]:
        """Fetch all tasks from GitHub Issues.

        Returns:
            List of TaskSpec objects

        Raises:
            SpecSourceError: If API request fails
        """
        # Fetch issues
        issues = await self._fetch_issues()

        # Convert to TaskSpecs
        tasks = []
        for issue in issues:
            task = self._issue_to_task_spec(issue)
            tasks.append(task)

            # Cache issue for sync
            self._known_issues[issue["number"]] = issue

        # Update tracking
        self._last_sync = datetime.now()
        self._last_spec_version = 1

        return tasks

    async def sync(self, known_tasks: dict[str, int]) -> SyncResult:
        """Sync tasks with GitHub Issues.

        Args:
            known_tasks: Dict mapping spec_id to spec_version

        Returns:
            SyncResult with changes detected

        Raises:
            SpecSourceError: If API request fails
        """
        result = SyncResult()

        try:
            # Fetch current issues (open and closed to detect state changes)
            issues = await self._fetch_issues(state="all")
        except SpecSourceError as e:
            result.errors.append(str(e))
            return result

        # Build current issue map
        current_map = {}
        for issue in issues:
            task = self._issue_to_task_spec(issue)
            current_map[task.spec_id] = task

        current_ids = set(current_map.keys())
        known_ids = set(known_tasks.keys())

        # Added tasks (new issues)
        added_ids = current_ids - known_ids
        result.added = [current_map[tid] for tid in added_ids]

        # Removed tasks (deleted issues - rare, but possible)
        result.removed = list(known_ids - current_ids)

        # Modified tasks (check if issue was updated)
        for tid in current_ids & known_ids:
            task = current_map[tid]
            # Check if issue metadata indicates it was updated
            issue_num = int(tid.replace("#", ""))
            old_issue = self._known_issues.get(issue_num)

            # If we have the old issue cached, compare updated_at
            if old_issue:
                old_updated = old_issue.get("updated_at")
                new_updated = task.metadata.get("github_updated_at")

                if old_updated != new_updated:
                    result.modified.append(task)
            else:
                # No cache, consider it modified if state changed to closed
                if task.deprecated:
                    result.modified.append(task)

        # Update cache
        for issue in issues:
            self._known_issues[issue["number"]] = issue

        # Update tracking
        result.spec_version = 1
        self._last_sync = datetime.now()

        return result

    async def mark_completed(
        self, spec_id: str, metadata: Optional[dict[str, Any]] = None
    ) -> bool:
        """Mark a task as completed by closing the GitHub issue.

        Adds a comment with completion metadata and closes the issue.

        Args:
            spec_id: The task spec ID (e.g., "#123")
            metadata: Optional metadata about completion (e.g., PR link)

        Returns:
            True if successfully closed, False otherwise
        """
        # Extract issue number from spec_id
        if not spec_id.startswith("#"):
            return False

        try:
            issue_number = int(spec_id.replace("#", ""))
        except ValueError:
            return False

        client = self._get_client()

        try:
            # Add completion comment
            comment_body = "✅ Task completed by BOB Framework"

            if metadata:
                comment_body += "\n\n**Completion Details:**\n"
                for key, value in metadata.items():
                    comment_body += f"- {key}: {value}\n"

            await client.post(
                f"/repos/{self.owner}/{self.repo}/issues/{issue_number}/comments",
                json={"body": comment_body},
            )

            # Close the issue
            await client.patch(
                f"/repos/{self.owner}/{self.repo}/issues/{issue_number}",
                json={"state": "closed"},
            )

            return True

        except (httpx.HTTPStatusError, httpx.RequestError):
            return False

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup client."""
        if self._client:
            await self._client.aclose()
            self._client = None
