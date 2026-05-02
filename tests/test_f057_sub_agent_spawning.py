"""Tests for F057: Sub-agent spawning via Claude SDK.

Validates that spawn_sub_agent():
- Creates a sub_agent_runs record with purpose and target
- Uses claude_code_sdk (no subprocess, no CLI)
- Tracks tokens_in, tokens_out, cost_usd
- Updates completed_at when done
- Returns both the execution result and the agent run record
"""

import asyncio
import ast
import pathlib
import re
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3 import db
from bob3.models import SubAgentRun

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
MODULE_PATH = SRC_DIR / "bob3" / "orchestrator" / "claude_executor.py"


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project for sub-agent spawning."""
    return db.create_project(
        name="Test Project",
        workspace_path="/tmp/test-project",
    )


# ===================================================================
# Step 1: spawn_sub_agent() function exists in claude_executor.py
# ===================================================================


class TestSpawnSubAgentExists:
    """Step 1: spawn_sub_agent() function must exist."""

    def test_function_exists(self):
        from bob3.orchestrator.claude_executor import spawn_sub_agent

        assert callable(spawn_sub_agent)

    def test_function_is_async(self):
        from bob3.orchestrator.claude_executor import spawn_sub_agent

        assert asyncio.iscoroutinefunction(spawn_sub_agent)


# ===================================================================
# Step 2: Creates sub_agent_runs record with purpose and target
# ===================================================================


class TestCreatesAgentRunRecord:
    """Step 2: spawn_sub_agent creates a sub_agent_runs record."""

    @pytest.mark.asyncio
    async def test_creates_run_record_before_execution(self, project):
        """A sub_agent_runs record is created before the agent executes."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        created_run_ids = []

        async def mock_query(*, prompt, options=None, transport=None):
            # During execution, the run record should already exist
            runs = db.query_agent_runs(project_id=project.id)
            running = [r for r in runs if r.status == "running"]
            created_run_ids.extend([r.id for r in running])
            yield AssistantMessage(
                content=[TextBlock(text="Done")], model="m"
            )
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Implement feature X",
            )

        assert len(created_run_ids) >= 1

    @pytest.mark.asyncio
    async def test_run_record_has_purpose(self, project):
        """The created run record has the correct purpose."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="rca_analyst",
                prompt="Analyze failure",
            )

        assert result.agent_run.purpose == "rca_analyst"

    @pytest.mark.asyncio
    async def test_run_record_has_target(self, project):
        """The created run record has target_type and target_id."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Implement feature F001",
                target_type="feature",
                target_id="F001",
            )

        assert result.agent_run.target_type == "feature"
        assert result.agent_run.target_id == "F001"

    @pytest.mark.asyncio
    async def test_run_record_has_prompt_summary(self, project):
        """The created run record stores a prompt summary."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Implement feature F001 with tests",
            )

        assert result.agent_run.prompt_summary is not None
        assert len(result.agent_run.prompt_summary) > 0


# ===================================================================
# Step 3: Uses ClaudeSDKClient / query() to execute agent
# ===================================================================


class TestUsesClaudeSDK:
    """Step 3: Uses claude_code_sdk.query() to execute the agent."""

    @pytest.mark.asyncio
    async def test_calls_sdk_query(self, project):
        """spawn_sub_agent calls claude_code_sdk.query."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        query_called_with = {}

        async def mock_query(*, prompt, options=None, transport=None):
            query_called_with["prompt"] = prompt
            query_called_with["options"] = options
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Do the thing",
            )

        assert "prompt" in query_called_with
        assert query_called_with["prompt"] == "Do the thing"

    @pytest.mark.asyncio
    async def test_returns_execution_result(self, project):
        """spawn_sub_agent returns a SpawnResult with execution_result."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent, ExecutionResult
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Implementation done")], model="m"
            )
            yield ResultMessage(
                subtype="success", duration_ms=500, duration_api_ms=400,
                is_error=False, num_turns=3, session_id="sess-123",
                total_cost_usd=0.05, usage=None, result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Implement it",
            )

        assert isinstance(result.execution_result, ExecutionResult)
        assert "Implementation done" in result.execution_result.text

    @pytest.mark.asyncio
    async def test_forwards_options(self, project, monkeypatch):
        """spawn_sub_agent forwards ClaudeCodeOptions to the SDK.

        The SDK call may receive a *new* ClaudeCodeOptions when bob3
        merges in MCP servers (e.g. auto-injecting Perplexity when
        ``PERPLEXITY_API_KEY`` is set). The contract is that the user's
        salient fields (model, max_turns, system_prompt, etc.) are
        preserved on whatever ClaudeCodeOptions reaches the SDK.
        """
        # Disable the Perplexity auto-inject path so we can assert
        # identity in the simple no-MCP case.
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        from bob3.orchestrator.claude_executor import spawn_sub_agent, build_sub_agent_options
        from claude_code_sdk import ResultMessage

        captured_options = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options["options"] = options
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        opts = build_sub_agent_options(model="sonnet", max_turns=10)

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Do it",
                options=opts,
            )

        passed = captured_options["options"]
        # When no MCP injection happens, identity should be preserved.
        assert passed is opts


# ===================================================================
# Step 4: Tracks tokens_in, tokens_out, cost_usd
# ===================================================================


class TestTracksTokensAndCost:
    """Step 4: Tracks tokens_in, tokens_out, cost_usd from execution."""

    @pytest.mark.asyncio
    async def test_tracks_cost_usd(self, project):
        """Cost is recorded from the ResultMessage total_cost_usd."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=500, duration_api_ms=400,
                is_error=False, num_turns=3, session_id="s1",
                total_cost_usd=1.25, usage=None, result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Do it",
            )

        # Check the persisted agent run
        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.cost_usd == pytest.approx(1.25)

    @pytest.mark.asyncio
    async def test_tracks_duration_ms(self, project):
        """Duration is recorded from the ResultMessage."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=45000, duration_api_ms=40000,
                is_error=False, num_turns=5, session_id="s1",
                total_cost_usd=0.50, usage=None, result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Do it",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.duration_ms == 45000


# ===================================================================
# Step 5: Updates completed_at when done
# ===================================================================


class TestUpdatesCompletedAt:
    """Step 5: Updates completed_at timestamp when execution finishes."""

    @pytest.mark.asyncio
    async def test_completed_at_set_on_success(self, project):
        """completed_at is set after successful execution."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Do it",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.completed_at is not None
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_status_failed_on_error(self, project):
        """Status is set to 'failed' when execution has an error."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="error", duration_ms=100, duration_api_ms=80,
                is_error=True, num_turns=0, session_id="err",
                total_cost_usd=0.01, usage=None, result="Agent failed",
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Do something that fails",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.status == "failed"
        assert run.completed_at is not None

    @pytest.mark.asyncio
    async def test_status_failed_on_exception(self, project):
        """Status is set to 'failed' when SDK raises an exception."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent

        async def mock_query(*, prompt, options=None, transport=None):
            raise RuntimeError("SDK connection failed")
            yield  # Make it an async generator

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="This will fail",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.status == "failed"
        assert run.completed_at is not None
        assert result.execution_result.is_error is True

    @pytest.mark.asyncio
    async def test_parent_run_id_forwarded(self, project):
        """parent_run_id is forwarded to the created run record."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        parent = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Do it",
                parent_run_id=parent.id,
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.parent_run_id == parent.id


# ===================================================================
# Step 6: VERIFY: No subprocess calls, only claude_code_sdk
# ===================================================================


class TestNoSubprocessInModule:
    """Step 6: MANDATORY - no subprocess, os.system, os.popen, Popen."""

    def test_no_subprocess_in_source(self):
        source = MODULE_PATH.read_text()
        # Strip comment lines before checking for forbidden patterns
        code_lines = [
            line for line in source.splitlines()
            if not line.strip().startswith("#") and not line.strip().startswith('"""') and not line.strip().startswith("'''")
        ]
        code_only = "\n".join(code_lines)
        forbidden = ["os.system(", "os.popen(", "Popen("]
        for pattern in forbidden:
            assert pattern not in code_only, (
                f"Found forbidden '{pattern}' in claude_executor.py"
            )
        # Check for actual subprocess usage (imports/calls), not mentions in comments
        assert not re.search(r'^\s*(import\s+subprocess|from\s+subprocess\b)', source, re.MULTILINE), (
            "Found forbidden subprocess import in claude_executor.py"
        )
        assert not re.search(r'\bsubprocess\.', code_only), (
            "Found forbidden subprocess usage in claude_executor.py"
        )

    def test_no_cli_invocation_patterns(self):
        source = MODULE_PATH.read_text()
        cli_patterns = [
            r"subprocess\.run",
            r"subprocess\.Popen",
            r"subprocess\.call",
            r"os\.system\(",
            r"os\.popen\(",
            r"'claude'\s*,\s*'-p'",
            r'"claude"\s*,\s*"-p"',
        ]
        for pat in cli_patterns:
            assert not re.search(pat, source), (
                f"Found forbidden CLI pattern: {pat}"
            )

    def test_no_anthropic_import(self):
        source = MODULE_PATH.read_text()
        assert "from anthropic" not in source
        assert "import anthropic" not in source


# ===================================================================
# Step 7: Integration test - spawn agent, verify record and completion
# ===================================================================


class TestSpawnIntegration:
    """Step 7: Integration test for full spawn lifecycle."""

    @pytest.mark.asyncio
    async def test_full_spawn_lifecycle(self, project):
        """Full lifecycle: spawn -> execute -> complete with tracked costs."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Feature implemented successfully")],
                model="claude-sonnet-4-5-20250929",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=120000,
                duration_api_ms=100000,
                is_error=False,
                num_turns=15,
                session_id="full-lifecycle-sess",
                total_cost_usd=2.50,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Implement the database schema for feature F001",
                target_type="feature",
                target_id="F001",
            )

        # Verify execution result
        assert "Feature implemented successfully" in result.execution_result.text
        assert result.execution_result.is_error is False
        assert result.execution_result.num_turns == 15

        # Verify agent run record
        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.project_id == project.id
        assert run.purpose == "implement_feature"
        assert run.target_type == "feature"
        assert run.target_id == "F001"
        assert run.status == "completed"
        assert run.completed_at is not None
        assert run.cost_usd == pytest.approx(2.50)
        assert run.duration_ms == 120000

    @pytest.mark.asyncio
    async def test_spawn_with_mcp_servers(self, project):
        """spawn_sub_agent tracks MCP-enabled plugins."""
        from bob3.orchestrator.claude_executor import spawn_sub_agent, build_sub_agent_options
        from claude_code_sdk import ResultMessage

        import json

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        mcp_servers = {
            "perplexity": {"type": "stdio", "command": "echo"},
            "bob3-memory": {"type": "stdio", "command": "echo"},
        }
        opts = build_sub_agent_options(mcp_servers=mcp_servers)

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="research",
                prompt="Research topic",
                options=opts,
                mcp_enabled=json.dumps(list(mcp_servers.keys())),
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        mcp_list = json.loads(run.mcp_enabled)
        assert "perplexity" in mcp_list
        assert "bob3-memory" in mcp_list
