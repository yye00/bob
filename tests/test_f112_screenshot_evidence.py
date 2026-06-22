"""Tests for F112: Screenshot Evidence Artifacts with Puppeteer.

Validates that:
- Step 1: capture_screenshot_evidence() function exists
- Step 2: Calls puppeteer_screenshot and stores result
- Step 3: Creates evidence_artifact record with type='screenshot'
- Step 4: Stores screenshot path in content field
- Step 5: Computes hash for verification
- Step 6: Test: Capture screenshot, verify evidence artifact created
"""

import hashlib
import json
import pathlib

import pytest

from bob3 import db
from bob3.models import EvidenceArtifact

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project for screenshot evidence tests."""
    return db.create_project(
        name="Screenshot Test Project",
        workspace_path="/tmp/test-screenshot",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature for screenshot evidence tests."""
    return db.create_feature(
        project_id=project.id,
        name="Screenshot Test Feature",
    )


@pytest.fixture()
def task(project, feature):
    """Create a test task for screenshot evidence tests."""
    return db.create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="validation",
        title="Screenshot Test Task",
    )


# ===================================================================
# Step 1: Add capture_screenshot_evidence() function
# ===================================================================


class TestCaptureScreenshotEvidenceExists:
    """Step 1: capture_screenshot_evidence() function is defined and callable."""

    def test_function_exists(self):
        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        assert callable(capture_screenshot_evidence)

    def test_function_is_async(self):
        import asyncio

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        assert asyncio.iscoroutinefunction(capture_screenshot_evidence)

    def test_function_accepts_required_params(self):
        import inspect

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        sig = inspect.signature(capture_screenshot_evidence)
        param_names = set(sig.parameters.keys())
        assert "project_id" in param_names
        assert "url" in param_names

    def test_function_accepts_optional_params(self):
        import inspect

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        sig = inspect.signature(capture_screenshot_evidence)
        param_names = set(sig.parameters.keys())
        assert "feature_id" in param_names
        assert "task_id" in param_names


# ===================================================================
# Step 2: Call puppeteer_screenshot and store result
# ===================================================================


class TestCallPuppeteerScreenshot:
    """Step 2: capture_screenshot_evidence spawns a puppeteer agent to take a screenshot."""

    @pytest.mark.asyncio
    async def test_spawns_puppeteer_agent(self, project, feature):
        """capture_screenshot_evidence spawns a puppeteer sub-agent."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        captured_options = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options["options"] = options
            captured_options["prompt"] = prompt
            yield AssistantMessage(
                content=[TextBlock(text="Screenshot saved to /tmp/screenshot.png")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=2000,
                duration_api_ms=1800,
                is_error=False,
                num_turns=2,
                session_id="ss-1",
                total_cost_usd=0.05,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
                feature_id=feature.id,
            )

        # Verify puppeteer MCP was configured
        opts = captured_options["options"]
        assert opts is not None
        assert opts.mcp_servers is not None
        assert "puppeteer" in opts.mcp_servers

    @pytest.mark.asyncio
    async def test_prompt_includes_screenshot_instruction(self, project):
        """The prompt sent to the agent instructs it to take a screenshot."""
        from unittest.mock import patch

        from claude_code_sdk import ResultMessage

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        captured = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured["prompt"] = prompt
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:3000",
            )

        prompt = captured["prompt"]
        assert "screenshot" in prompt.lower()
        assert "http://localhost:3000" in prompt

    @pytest.mark.asyncio
    async def test_returns_screenshot_evidence_result(self, project, feature, task):
        """capture_screenshot_evidence returns a ScreenshotEvidenceResult."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import (
            ScreenshotEvidenceResult,
            capture_screenshot_evidence,
        )

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Screenshot captured at /tmp/shot.png")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=2000,
                duration_api_ms=1800,
                is_error=False,
                num_turns=2,
                session_id="ss-2",
                total_cost_usd=0.03,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
                feature_id=feature.id,
                task_id=task.id,
            )

        assert isinstance(result, ScreenshotEvidenceResult)
        assert result.spawn_result is not None
        assert result.evidence is not None


# ===================================================================
# Step 3: Create evidence_artifact record with type='screenshot'
# ===================================================================


class TestCreateEvidenceArtifact:
    """Step 3: An evidence_artifact record is created with type='screenshot'."""

    @pytest.mark.asyncio
    async def test_evidence_type_is_screenshot(self, project, feature):
        """The created evidence artifact has type='screenshot'."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Screenshot captured at /tmp/shot.png")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=2000,
                duration_api_ms=1800,
                is_error=False,
                num_turns=2,
                session_id="ss-3",
                total_cost_usd=0.03,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
                feature_id=feature.id,
            )

        assert result.evidence.type == "screenshot"

    @pytest.mark.asyncio
    async def test_evidence_linked_to_project(self, project):
        """The evidence artifact is linked to the correct project."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Done")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
            )

        assert result.evidence.project_id == project.id

    @pytest.mark.asyncio
    async def test_evidence_linked_to_feature(self, project, feature):
        """The evidence artifact is linked to the correct feature."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Done")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
                feature_id=feature.id,
            )

        assert result.evidence.feature_id == feature.id

    @pytest.mark.asyncio
    async def test_evidence_linked_to_task(self, project, feature, task):
        """The evidence artifact is linked to the correct task."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Done")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
                feature_id=feature.id,
                task_id=task.id,
            )

        assert result.evidence.task_id == task.id

    @pytest.mark.asyncio
    async def test_evidence_persisted_in_database(self, project, feature):
        """The evidence artifact is retrievable from the database."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Screenshot at /tmp/shot.png")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
                feature_id=feature.id,
            )

        fetched = db.get_evidence(result.evidence.id)
        assert fetched is not None
        assert fetched.type == "screenshot"
        assert fetched.project_id == project.id
        assert fetched.feature_id == feature.id

    @pytest.mark.asyncio
    async def test_evidence_is_current_by_default(self, project):
        """The evidence artifact is marked is_current=True."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Done")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
            )

        assert result.evidence.is_current is True


# ===================================================================
# Step 4: Store screenshot path in content field
# ===================================================================


class TestScreenshotPathInContent:
    """Step 4: The screenshot path/URL is stored in the content field as JSON."""

    @pytest.mark.asyncio
    async def test_content_contains_url(self, project):
        """The content field includes the URL that was screenshotted."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Screenshot saved to /tmp/shot.png")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080/dashboard",
            )

        content = json.loads(result.evidence.content)
        assert content["url"] == "http://localhost:8080/dashboard"

    @pytest.mark.asyncio
    async def test_content_contains_agent_response(self, project):
        """The content field includes the agent's response text."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        response_text = "Screenshot captured successfully at /tmp/screenshot_001.png"

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text=response_text)],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
            )

        content = json.loads(result.evidence.content)
        assert "agent_response" in content
        assert response_text in content["agent_response"]

    @pytest.mark.asyncio
    async def test_content_is_valid_json(self, project):
        """The content field is valid JSON."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Done")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
            )

        # Should parse without error
        content = json.loads(result.evidence.content)
        assert isinstance(content, dict)


# ===================================================================
# Step 5: Compute hash for verification
# ===================================================================


class TestHashComputation:
    """Step 5: A SHA256 hash is computed for the evidence content."""

    @pytest.mark.asyncio
    async def test_evidence_has_output_hash(self, project, feature):
        """The evidence artifact has a non-None output_hash."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Screenshot captured")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
                feature_id=feature.id,
            )

        assert result.evidence.output_hash is not None
        assert len(result.evidence.output_hash) == 64  # SHA256 hex

    @pytest.mark.asyncio
    async def test_hash_matches_content(self, project):
        """The output_hash matches SHA256 of the content field."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Screenshot captured")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
            )

        expected_hash = hashlib.sha256(
            result.evidence.content.encode("utf-8")
        ).hexdigest()
        assert result.evidence.output_hash == expected_hash

    @pytest.mark.asyncio
    async def test_hash_verifiable_via_db(self, project, feature):
        """The hash can be verified using db.verify_evidence()."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Screenshot captured")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
                feature_id=feature.id,
            )

        verification = db.verify_evidence(result.evidence.id)
        assert verification is not None
        assert verification.verified is True


# ===================================================================
# Step 6: Full integration test
# ===================================================================


class TestScreenshotEvidenceIntegration:
    """Step 6: End-to-end test capturing screenshot and verifying artifact."""

    @pytest.mark.asyncio
    async def test_full_capture_and_verify(self, project, feature, task):
        """Full workflow: capture screenshot, verify evidence artifact created."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import (
            ScreenshotEvidenceResult,
            capture_screenshot_evidence,
        )

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[
                    TextBlock(
                        text="Navigated to http://localhost:8080/dashboard. "
                        "Screenshot saved to /tmp/evidence/screenshot_001.png. "
                        "Page shows the main dashboard with metrics."
                    )
                ],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=5000,
                duration_api_ms=4500,
                is_error=False,
                num_turns=3,
                session_id="ss-full",
                total_cost_usd=0.08,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080/dashboard",
                feature_id=feature.id,
                task_id=task.id,
            )

        # Verify result type
        assert isinstance(result, ScreenshotEvidenceResult)

        # Verify evidence artifact was created
        assert result.evidence is not None
        assert result.evidence.type == "screenshot"
        assert result.evidence.project_id == project.id
        assert result.evidence.feature_id == feature.id
        assert result.evidence.task_id == task.id

        # Verify content contains URL and response
        content = json.loads(result.evidence.content)
        assert content["url"] == "http://localhost:8080/dashboard"
        assert "agent_response" in content

        # Verify hash was computed
        assert result.evidence.output_hash is not None
        expected_hash = hashlib.sha256(
            result.evidence.content.encode("utf-8")
        ).hexdigest()
        assert result.evidence.output_hash == expected_hash

        # Verify evidence is persisted and retrievable
        fetched = db.get_evidence(result.evidence.id)
        assert fetched is not None
        assert fetched.type == "screenshot"

        # Verify evidence passes hash verification
        verification = db.verify_evidence(result.evidence.id)
        assert verification is not None
        assert verification.verified is True

        # Verify spawn result is included
        assert result.spawn_result is not None
        assert result.spawn_result.agent_run is not None
        assert result.spawn_result.agent_run.status == "completed"

    @pytest.mark.asyncio
    async def test_capture_on_agent_error(self, project, feature):
        """Evidence artifact is still created when agent encounters an error."""
        from unittest.mock import patch

        from claude_code_sdk import ResultMessage

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="error",
                duration_ms=100,
                duration_api_ms=80,
                is_error=True,
                num_turns=0,
                session_id="err",
                total_cost_usd=0.01,
                usage=None,
                result="Browser automation failed",
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
                feature_id=feature.id,
            )

        # Even on error, an evidence artifact should be created
        assert result.evidence is not None
        assert result.evidence.type == "screenshot"
        content = json.loads(result.evidence.content)
        assert content["url"] == "http://localhost:8080"
        # Error info should be captured
        assert content.get("error") is True or result.spawn_result.execution_result.is_error

    @pytest.mark.asyncio
    async def test_evidence_queryable_by_feature(self, project, feature):
        """Screenshot evidence can be queried via query_evidence(feature_id=...)."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Done")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
                feature_id=feature.id,
            )

        evidence_list = db.query_evidence(feature_id=feature.id)
        assert len(evidence_list) == 1
        assert evidence_list[0].type == "screenshot"

    @pytest.mark.asyncio
    async def test_multiple_screenshots_create_separate_artifacts(
        self, project, feature
    ):
        """Multiple calls create separate evidence artifacts."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Done")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            r1 = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080/page1",
                feature_id=feature.id,
            )
            r2 = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080/page2",
                feature_id=feature.id,
            )

        assert r1.evidence.id != r2.evidence.id

        evidence_list = db.query_evidence(feature_id=feature.id)
        assert len(evidence_list) == 2

        urls = {json.loads(e.content)["url"] for e in evidence_list}
        assert "http://localhost:8080/page1" in urls
        assert "http://localhost:8080/page2" in urls

    @pytest.mark.asyncio
    async def test_puppeteer_tracked_in_mcp_enabled(self, project):
        """The agent run tracks puppeteer in mcp_enabled field."""
        from unittest.mock import patch

        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        from bob3.orchestrator.claude_executor import capture_screenshot_evidence

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Done")],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await capture_screenshot_evidence(
                project_id=project.id,
                url="http://localhost:8080",
            )

        run = db.get_agent_run(result.spawn_result.agent_run.id)
        assert run is not None
        assert run.mcp_enabled is not None
        mcp_list = json.loads(run.mcp_enabled)
        assert "puppeteer" in mcp_list
