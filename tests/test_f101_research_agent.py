"""Tests for F101: spawn_research_agent() function with Perplexity MCP.

Validates that:
- Step 1: Perplexity MCP tools are defined in mcp_config.py
- Step 2: spawn_research_agent() exists and is async
- Step 3: spawn_research_agent() configures Perplexity MCP tools
- Step 4: spawn_research_agent() tracks MCP usage in sub_agent_runs table
- Step 5: spawn_research_agent() returns SpawnResult with research data
"""

import asyncio
import json
import pathlib
import re
from unittest.mock import patch

import pytest

from bob3 import db
from bob3.models import SubAgentRun

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
EXECUTOR_PATH = SRC_DIR / "bob3" / "orchestrator" / "claude_executor.py"
MCP_CONFIG_PATH = SRC_DIR / "bob3" / "orchestrator" / "mcp_config.py"


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project for research agent spawning."""
    return db.create_project(
        name="Research Project",
        workspace_path="/tmp/test-research",
    )


# ===================================================================
# Step 1: Perplexity MCP tools are defined in mcp_config.py
# ===================================================================


class TestPerplexityToolsDefined:
    """Step 1: Perplexity tool names are available in mcp_config."""

    def test_perplexity_tools_list_exists(self):
        from bob3.orchestrator.mcp_config import get_perplexity_tools

        tools = get_perplexity_tools()
        assert isinstance(tools, list)

    def test_perplexity_tools_contains_ask(self):
        from bob3.orchestrator.mcp_config import get_perplexity_tools

        tools = get_perplexity_tools()
        assert any("ask" in t for t in tools)

    def test_perplexity_tools_contains_search(self):
        from bob3.orchestrator.mcp_config import get_perplexity_tools

        tools = get_perplexity_tools()
        assert any("search" in t for t in tools)

    def test_perplexity_tools_are_mcp_namespaced(self):
        """Perplexity tools should follow MCP naming convention."""
        from bob3.orchestrator.mcp_config import get_perplexity_tools

        tools = get_perplexity_tools()
        for tool in tools:
            assert "perplexity" in tool.lower(), (
                f"Tool '{tool}' should contain 'perplexity' in its name"
            )

    def test_build_perplexity_mcp_dict_returns_dict(self):
        """build_perplexity_mcp_dict() returns a dict suitable for mcp_servers."""
        from bob3.orchestrator.mcp_config import build_perplexity_mcp_dict

        result = build_perplexity_mcp_dict()
        assert isinstance(result, dict)
        assert "perplexity" in result

    def test_build_perplexity_mcp_dict_has_correct_structure(self):
        """The dict has type, command, args, env keys."""
        from bob3.orchestrator.mcp_config import build_perplexity_mcp_dict

        result = build_perplexity_mcp_dict()
        server = result["perplexity"]
        assert "type" in server
        assert server["type"] == "stdio"
        assert "command" in server


# ===================================================================
# Step 2: spawn_research_agent() exists and is async
# ===================================================================


class TestSpawnResearchAgentExists:
    """Step 2: spawn_research_agent() function must exist and be async."""

    def test_function_exists(self):
        from bob3.orchestrator.claude_executor import spawn_research_agent

        assert callable(spawn_research_agent)

    def test_function_is_async(self):
        from bob3.orchestrator.claude_executor import spawn_research_agent

        assert asyncio.iscoroutinefunction(spawn_research_agent)

    def test_function_accepts_required_params(self):
        """spawn_research_agent requires project_id, query, and purpose."""
        import inspect
        from bob3.orchestrator.claude_executor import spawn_research_agent

        sig = inspect.signature(spawn_research_agent)
        param_names = set(sig.parameters.keys())
        assert "project_id" in param_names
        assert "query" in param_names


# ===================================================================
# Step 3: spawn_research_agent() configures Perplexity MCP
# ===================================================================


class TestResearchAgentConfiguresPerplexity:
    """Step 3: The research agent is configured with Perplexity MCP tools."""

    @pytest.mark.asyncio
    async def test_passes_perplexity_mcp_to_query(self, project):
        """spawn_research_agent passes Perplexity MCP config to the SDK."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_options = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options["options"] = options
            yield AssistantMessage(
                content=[TextBlock(text="Research result: Python 3.12 released")],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=5000,
                duration_api_ms=4000,
                is_error=False,
                num_turns=2,
                session_id="research-1",
                total_cost_usd=0.05,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_research_agent(
                project_id=project.id,
                query="What is the latest version of Python?",
            )

        assert captured_options["options"] is not None
        opts = captured_options["options"]
        assert opts.mcp_servers is not None
        assert "perplexity" in opts.mcp_servers

    @pytest.mark.asyncio
    async def test_prompt_contains_research_query(self, project):
        """The prompt sent to the SDK contains the research query."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import ResultMessage

        captured_prompt = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_prompt["prompt"] = prompt
            yield ResultMessage(
                subtype="success",
                duration_ms=1000,
                duration_api_ms=800,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            await spawn_research_agent(
                project_id=project.id,
                query="How does asyncio work in Python?",
            )

        assert "How does asyncio work in Python?" in captured_prompt["prompt"]

    @pytest.mark.asyncio
    async def test_uses_default_purpose_research(self, project):
        """Default purpose is 'research' when not specified."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
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
            result = await spawn_research_agent(
                project_id=project.id,
                query="Research something",
            )

        assert result.agent_run.purpose == "research"


# ===================================================================
# Step 4: Tracks MCP usage in sub_agent_runs table
# ===================================================================


class TestTracksMCPUsage:
    """Step 4: MCP usage is tracked in the sub_agent_runs table."""

    @pytest.mark.asyncio
    async def test_mcp_enabled_field_contains_perplexity(self, project):
        """The agent run record has perplexity in mcp_enabled."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
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
            result = await spawn_research_agent(
                project_id=project.id,
                query="Test query",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.mcp_enabled is not None
        mcp_list = json.loads(run.mcp_enabled)
        assert "perplexity" in mcp_list

    @pytest.mark.asyncio
    async def test_tracks_cost_and_duration(self, project):
        """Cost and duration are tracked from the research execution."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success",
                duration_ms=8000,
                duration_api_ms=7000,
                is_error=False,
                num_turns=3,
                session_id="s1",
                total_cost_usd=0.15,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_research_agent(
                project_id=project.id,
                query="Research topic",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.cost_usd == pytest.approx(0.15)
        assert run.duration_ms == 8000

    @pytest.mark.asyncio
    async def test_status_completed_on_success(self, project):
        """Status is set to completed after successful research."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Found the answer")],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=2000,
                duration_api_ms=1800,
                is_error=False,
                num_turns=2,
                session_id="s1",
                total_cost_usd=0.05,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_research_agent(
                project_id=project.id,
                query="Simple query",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.status == "completed"
        assert run.completed_at is not None

    @pytest.mark.asyncio
    async def test_status_failed_on_error(self, project):
        """Status is set to failed when research encounters an error."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import ResultMessage

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
                result="Research failed",
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_research_agent(
                project_id=project.id,
                query="Failing query",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.status == "failed"

    @pytest.mark.asyncio
    async def test_status_failed_on_exception(self, project):
        """Status is set to failed when SDK raises an exception."""
        from bob3.orchestrator.claude_executor import spawn_research_agent

        async def mock_query(*, prompt, options=None, transport=None):
            raise RuntimeError("Perplexity MCP unavailable")
            yield  # make it an async generator

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_research_agent(
                project_id=project.id,
                query="This will fail",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.status == "failed"
        assert result.execution_result.is_error is True


# ===================================================================
# Step 5: Returns SpawnResult with research data
# ===================================================================


class TestReturnsSpawnResult:
    """Step 5: spawn_research_agent returns a SpawnResult."""

    @pytest.mark.asyncio
    async def test_returns_spawn_result(self, project):
        """spawn_research_agent returns a SpawnResult object."""
        from bob3.orchestrator.claude_executor import (
            spawn_research_agent,
            SpawnResult,
        )
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Research findings here")],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=5000,
                duration_api_ms=4000,
                is_error=False,
                num_turns=2,
                session_id="s1",
                total_cost_usd=0.05,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_research_agent(
                project_id=project.id,
                query="Research this topic",
            )

        assert isinstance(result, SpawnResult)
        assert "Research findings here" in result.execution_result.text

    @pytest.mark.asyncio
    async def test_accepts_optional_target(self, project):
        """spawn_research_agent accepts optional target_type and target_id."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
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
            result = await spawn_research_agent(
                project_id=project.id,
                query="Investigate this feature",
                target_type="feature",
                target_id="F101",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.target_type == "feature"
        assert run.target_id == "F101"

    @pytest.mark.asyncio
    async def test_accepts_custom_purpose(self, project):
        """spawn_research_agent accepts a custom purpose."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
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
            result = await spawn_research_agent(
                project_id=project.id,
                query="RCA investigation",
                purpose="rca_research",
            )

        assert result.agent_run.purpose == "rca_research"

    @pytest.mark.asyncio
    async def test_accepts_parent_run_id(self, project):
        """spawn_research_agent accepts parent_run_id for hierarchy."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import ResultMessage

        parent = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )

        async def mock_query(*, prompt, options=None, transport=None):
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
            result = await spawn_research_agent(
                project_id=project.id,
                query="Child research task",
                parent_run_id=parent.id,
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.parent_run_id == parent.id


# ===================================================================
# Step 6: No subprocess or forbidden imports
# ===================================================================


class TestNoForbiddenPatterns:
    """Step 6: No subprocess calls or forbidden imports in the module."""

    def test_no_subprocess_in_module(self):
        source = EXECUTOR_PATH.read_text()
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

    def test_no_anthropic_import(self):
        source = EXECUTOR_PATH.read_text()
        assert "from anthropic" not in source
        assert "import anthropic" not in source
