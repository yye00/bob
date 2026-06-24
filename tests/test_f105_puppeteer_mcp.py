"""Tests for F105: Puppeteer MCP integration for browser testing.

Validates that:
- Step 1: Add enable_puppeteer parameter to spawn_sub_agent
- Step 2: Configure Puppeteer MCP when enabled
- Step 3: Add Puppeteer tools to allowed_tools list
- Step 4: Test browser automation with simple page (spawn_puppeteer_agent)
"""

import asyncio
import inspect
import json
import pathlib
from unittest.mock import patch

import pytest

from bob import db
from bob.models import SubAgentRun

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
EXECUTOR_PATH = SRC_DIR / "bob" / "orchestrator" / "claude_executor.py"
MCP_CONFIG_PATH = SRC_DIR / "bob" / "orchestrator" / "mcp_config.py"


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project for puppeteer agent spawning."""
    return db.create_project(
        name="Puppeteer Project",
        workspace_path="/tmp/test-puppeteer",
    )


# ===================================================================
# Step 1: Add enable_puppeteer parameter to spawn_sub_agent
# ===================================================================


class TestEnablePuppeteerParameter:
    """Step 1: spawn_sub_agent accepts enable_puppeteer parameter."""

    def test_spawn_sub_agent_accepts_enable_puppeteer(self):
        from bob.orchestrator.claude_executor import spawn_sub_agent

        sig = inspect.signature(spawn_sub_agent)
        assert "enable_puppeteer" in sig.parameters

    def test_enable_puppeteer_defaults_to_false(self):
        from bob.orchestrator.claude_executor import spawn_sub_agent

        sig = inspect.signature(spawn_sub_agent)
        param = sig.parameters["enable_puppeteer"]
        assert param.default is False

    @pytest.mark.asyncio
    async def test_spawn_sub_agent_without_puppeteer(self, project):
        """When enable_puppeteer is False, no Puppeteer MCP is configured."""
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_options = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options["options"] = options
            yield AssistantMessage(
                content=[TextBlock(text="done")], model="test"
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            await spawn_sub_agent(
                project_id=project.id,
                purpose="test",
                prompt="Test prompt",
                enable_puppeteer=False,
            )

        opts = captured_options["options"]
        # When no options provided and puppeteer not enabled, mcp_servers should be None
        assert opts is None or opts.mcp_servers is None or "puppeteer" not in (opts.mcp_servers or {})

    @pytest.mark.asyncio
    async def test_spawn_sub_agent_with_puppeteer(self, project):
        """When enable_puppeteer is True, Puppeteer MCP is configured."""
        from bob.orchestrator.claude_executor import (
            build_sub_agent_options,
            spawn_sub_agent,
        )
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_options = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options["options"] = options
            yield AssistantMessage(
                content=[TextBlock(text="done")], model="test"
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

        base_opts = build_sub_agent_options(model="sonnet")

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            await spawn_sub_agent(
                project_id=project.id,
                purpose="browser_test",
                prompt="Navigate to page and take screenshot",
                options=base_opts,
                enable_puppeteer=True,
            )

        opts = captured_options["options"]
        assert opts is not None
        assert opts.mcp_servers is not None
        assert "puppeteer" in opts.mcp_servers

    @pytest.mark.asyncio
    async def test_puppeteer_mcp_enabled_tracked(self, project):
        """When enable_puppeteer=True, mcp_enabled field includes puppeteer."""
        from bob.orchestrator.claude_executor import (
            build_sub_agent_options,
            spawn_sub_agent,
        )
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

        opts = build_sub_agent_options(model="sonnet")

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="browser_test",
                prompt="Test page",
                options=opts,
                enable_puppeteer=True,
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.mcp_enabled is not None
        mcp_list = json.loads(run.mcp_enabled)
        assert "puppeteer" in mcp_list

    @pytest.mark.asyncio
    async def test_puppeteer_merges_with_existing_mcp(self, project):
        """Puppeteer MCP merges with existing mcp_servers in options."""
        from bob.orchestrator.claude_executor import (
            build_sub_agent_options,
            spawn_sub_agent,
        )
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_options = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options["options"] = options
            yield AssistantMessage(
                content=[TextBlock(text="done")], model="test"
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

        existing_mcp = {
            "test-server": {
                "type": "stdio",
                "command": "echo",
                "args": ["hello"],
            }
        }
        opts = build_sub_agent_options(model="sonnet", mcp_servers=existing_mcp)

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            await spawn_sub_agent(
                project_id=project.id,
                purpose="browser_test",
                prompt="Test with both MCPs",
                options=opts,
                enable_puppeteer=True,
            )

        opts_used = captured_options["options"]
        assert opts_used.mcp_servers is not None
        assert "puppeteer" in opts_used.mcp_servers
        assert "test-server" in opts_used.mcp_servers


# ===================================================================
# Step 2: Configure Puppeteer MCP when enabled
# ===================================================================


class TestPuppeteerMCPConfiguration:
    """Step 2: Puppeteer MCP is properly configured via mcp_config."""

    def test_build_puppeteer_mcp_dict_exists(self):
        from bob.orchestrator.mcp_config import build_puppeteer_mcp_dict

        assert callable(build_puppeteer_mcp_dict)

    def test_build_puppeteer_mcp_dict_returns_dict(self):
        from bob.orchestrator.mcp_config import build_puppeteer_mcp_dict

        result = build_puppeteer_mcp_dict()
        assert isinstance(result, dict)

    def test_build_puppeteer_mcp_dict_has_puppeteer_key(self):
        from bob.orchestrator.mcp_config import build_puppeteer_mcp_dict

        result = build_puppeteer_mcp_dict()
        assert "puppeteer" in result

    def test_build_puppeteer_mcp_dict_has_stdio_type(self):
        from bob.orchestrator.mcp_config import build_puppeteer_mcp_dict

        result = build_puppeteer_mcp_dict()
        server = result["puppeteer"]
        assert server["type"] == "stdio"

    def test_build_puppeteer_mcp_dict_uses_npx(self):
        from bob.orchestrator.mcp_config import build_puppeteer_mcp_dict

        result = build_puppeteer_mcp_dict()
        server = result["puppeteer"]
        assert server["command"] == "npx"

    def test_build_puppeteer_mcp_dict_has_puppeteer_package(self):
        from bob.orchestrator.mcp_config import build_puppeteer_mcp_dict

        result = build_puppeteer_mcp_dict()
        server = result["puppeteer"]
        args = server.get("args", [])
        assert any("puppeteer" in arg for arg in args)

    @pytest.mark.asyncio
    async def test_puppeteer_config_structure_valid_for_sdk(self, project):
        """The Puppeteer MCP dict structure matches what ClaudeCodeOptions expects."""
        from bob.orchestrator.mcp_config import build_puppeteer_mcp_dict
        from bob.orchestrator.claude_executor import build_sub_agent_options

        puppeteer_mcp = build_puppeteer_mcp_dict()
        opts = build_sub_agent_options(mcp_servers=puppeteer_mcp)
        assert opts.mcp_servers is not None
        assert "puppeteer" in opts.mcp_servers
        server = opts.mcp_servers["puppeteer"]
        assert "type" in server
        assert "command" in server


# ===================================================================
# Step 3: Add Puppeteer tools to allowed_tools list
# ===================================================================


class TestPuppeteerToolsList:
    """Step 3: Puppeteer tools are defined and accessible."""

    def test_get_puppeteer_tools_exists(self):
        from bob.orchestrator.mcp_config import get_puppeteer_tools

        assert callable(get_puppeteer_tools)

    def test_get_puppeteer_tools_returns_list(self):
        from bob.orchestrator.mcp_config import get_puppeteer_tools

        tools = get_puppeteer_tools()
        assert isinstance(tools, list)

    def test_get_puppeteer_tools_not_empty(self):
        from bob.orchestrator.mcp_config import get_puppeteer_tools

        tools = get_puppeteer_tools()
        assert len(tools) > 0

    def test_puppeteer_tools_contain_navigate(self):
        """Puppeteer tools should include navigation capability."""
        from bob.orchestrator.mcp_config import get_puppeteer_tools

        tools = get_puppeteer_tools()
        assert any("navigate" in t.lower() for t in tools)

    def test_puppeteer_tools_contain_screenshot(self):
        """Puppeteer tools should include screenshot capability."""
        from bob.orchestrator.mcp_config import get_puppeteer_tools

        tools = get_puppeteer_tools()
        assert any("screenshot" in t.lower() for t in tools)

    def test_puppeteer_tools_are_mcp_namespaced(self):
        """Puppeteer tools follow MCP naming convention."""
        from bob.orchestrator.mcp_config import get_puppeteer_tools

        tools = get_puppeteer_tools()
        for tool in tools:
            assert "puppeteer" in tool.lower(), (
                f"Tool '{tool}' should contain 'puppeteer' in its name"
            )


# ===================================================================
# Step 4: Test browser automation with spawn_puppeteer_agent
# ===================================================================


class TestSpawnPuppeteerAgent:
    """Step 4: spawn_puppeteer_agent convenience function for browser tasks."""

    def test_function_exists(self):
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent

        assert callable(spawn_puppeteer_agent)

    def test_function_is_async(self):
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent

        assert asyncio.iscoroutinefunction(spawn_puppeteer_agent)

    def test_function_accepts_required_params(self):
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent

        sig = inspect.signature(spawn_puppeteer_agent)
        param_names = set(sig.parameters.keys())
        assert "project_id" in param_names
        assert "url" in param_names

    @pytest.mark.asyncio
    async def test_configures_puppeteer_mcp(self, project):
        """spawn_puppeteer_agent configures Puppeteer MCP in options."""
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_options = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options["options"] = options
            yield AssistantMessage(
                content=[TextBlock(text="Page loaded successfully")],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=5000,
                duration_api_ms=4000,
                is_error=False,
                num_turns=2,
                session_id="pup-1",
                total_cost_usd=0.05,
                usage=None,
                result=None,
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_puppeteer_agent(
                project_id=project.id,
                url="http://localhost:8080",
            )

        opts = captured_options["options"]
        assert opts is not None
        assert opts.mcp_servers is not None
        assert "puppeteer" in opts.mcp_servers

    @pytest.mark.asyncio
    async def test_prompt_contains_url(self, project):
        """The prompt sent to the agent includes the target URL."""
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent
        from claude_code_sdk import ResultMessage

        captured_prompt = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_prompt["prompt"] = prompt
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            await spawn_puppeteer_agent(
                project_id=project.id,
                url="http://localhost:3000/dashboard",
            )

        assert "http://localhost:3000/dashboard" in captured_prompt["prompt"]

    @pytest.mark.asyncio
    async def test_custom_task_in_prompt(self, project):
        """Custom task instructions are included in the prompt."""
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent
        from claude_code_sdk import ResultMessage

        captured_prompt = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_prompt["prompt"] = prompt
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            await spawn_puppeteer_agent(
                project_id=project.id,
                url="http://localhost:8080",
                task="Click the login button and verify the form appears",
            )

        prompt = captured_prompt["prompt"]
        assert "Click the login button and verify the form appears" in prompt

    @pytest.mark.asyncio
    async def test_returns_spawn_result(self, project):
        """spawn_puppeteer_agent returns a SpawnResult."""
        from bob.orchestrator.claude_executor import (
            spawn_puppeteer_agent,
            SpawnResult,
        )
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Navigated successfully")],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=3000,
                duration_api_ms=2500,
                is_error=False,
                num_turns=2,
                session_id="pup-2",
                total_cost_usd=0.04,
                usage=None,
                result=None,
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_puppeteer_agent(
                project_id=project.id,
                url="http://localhost:8080",
            )

        assert isinstance(result, SpawnResult)
        assert "Navigated successfully" in result.execution_result.text

    @pytest.mark.asyncio
    async def test_tracks_puppeteer_in_mcp_enabled(self, project):
        """The agent run record has puppeteer in mcp_enabled."""
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_puppeteer_agent(
                project_id=project.id,
                url="http://localhost:8080",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.mcp_enabled is not None
        mcp_list = json.loads(run.mcp_enabled)
        assert "puppeteer" in mcp_list

    @pytest.mark.asyncio
    async def test_default_purpose_is_browser_test(self, project):
        """Default purpose is 'browser_test'."""
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_puppeteer_agent(
                project_id=project.id,
                url="http://localhost:8080",
            )

        assert result.agent_run.purpose == "browser_test"

    @pytest.mark.asyncio
    async def test_accepts_parent_run_id(self, project):
        """spawn_puppeteer_agent accepts parent_run_id for hierarchy."""
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_puppeteer_agent(
                project_id=project.id,
                url="http://localhost:8080",
                parent_run_id=parent.id,
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.parent_run_id == parent.id

    @pytest.mark.asyncio
    async def test_status_completed_on_success(self, project):
        """Status is 'completed' after successful browser automation."""
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Page screenshot captured")],
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_puppeteer_agent(
                project_id=project.id,
                url="http://localhost:8080",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_status_failed_on_error(self, project):
        """Status is 'failed' when browser automation errors."""
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent
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
                result="Browser automation failed",
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_puppeteer_agent(
                project_id=project.id,
                url="http://localhost:8080",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.status == "failed"

    @pytest.mark.asyncio
    async def test_accepts_target_type_and_id(self, project):
        """spawn_puppeteer_agent accepts optional target_type and target_id."""
        from bob.orchestrator.claude_executor import spawn_puppeteer_agent
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_puppeteer_agent(
                project_id=project.id,
                url="http://localhost:8080",
                target_type="feature",
                target_id="F105",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.target_type == "feature"
        assert run.target_id == "F105"
