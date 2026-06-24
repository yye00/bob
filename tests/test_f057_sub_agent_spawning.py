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

from bob import db
from bob.models import SubAgentRun

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
MODULE_PATH = SRC_DIR / "bob" / "orchestrator" / "claude_executor.py"


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
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
        from bob.orchestrator.claude_executor import spawn_sub_agent

        assert callable(spawn_sub_agent)

    def test_function_is_async(self):
        from bob.orchestrator.claude_executor import spawn_sub_agent

        assert asyncio.iscoroutinefunction(spawn_sub_agent)


# ===================================================================
# Step 2: Creates sub_agent_runs record with purpose and target
# ===================================================================


class TestCreatesAgentRunRecord:
    """Step 2: spawn_sub_agent creates a sub_agent_runs record."""

    @pytest.mark.asyncio
    async def test_creates_run_record_before_execution(self, project):
        """A sub_agent_runs record is created before the agent executes."""
        from bob.orchestrator.claude_executor import spawn_sub_agent
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Implement feature X",
            )

        assert len(created_run_ids) >= 1

    @pytest.mark.asyncio
    async def test_run_record_has_purpose(self, project):
        """The created run record has the correct purpose."""
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="rca_analyst",
                prompt="Analyze failure",
            )

        assert result.agent_run.purpose == "rca_analyst"

    @pytest.mark.asyncio
    async def test_run_record_has_target(self, project):
        """The created run record has target_type and target_id."""
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        from bob.orchestrator.claude_executor import spawn_sub_agent
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        from bob.orchestrator.claude_executor import spawn_sub_agent, ExecutionResult
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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

        The SDK call may receive a *new* ClaudeCodeOptions when bob
        merges in MCP servers (e.g. auto-injecting Perplexity when
        ``PERPLEXITY_API_KEY`` is set). The contract is that the user's
        salient fields (model, max_turns, system_prompt, etc.) are
        preserved on whatever ClaudeCodeOptions reaches the SDK.
        """
        # Disable the Perplexity auto-inject path so we can assert
        # identity in the simple no-MCP case.
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        from bob.orchestrator.claude_executor import spawn_sub_agent, build_sub_agent_options
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Do it",
                options=opts,
            )

        passed = captured_options["options"]
        # R10-013: spawn_sub_agent now ALWAYS wraps options to install a
        # debug-stderr buffer for diagnostic capture, so identity is no
        # longer preserved. The contract under test is that the user's
        # salient fields (model, max_turns, ...) survive intact on
        # whatever options object reaches the SDK.
        assert passed is not None
        assert passed.model == opts.model
        assert passed.max_turns == opts.max_turns
        assert passed.permission_mode == opts.permission_mode
        # The R10-013 wrapping must add the debug-to-stderr extra arg so
        # the SDK actually streams subprocess stderr into the buffer.
        assert "debug-to-stderr" in (passed.extra_args or {})


# ===================================================================
# Step 4: Tracks tokens_in, tokens_out, cost_usd
# ===================================================================


class TestTracksTokensAndCost:
    """Step 4: Tracks tokens_in, tokens_out, cost_usd from execution."""

    @pytest.mark.asyncio
    async def test_tracks_cost_usd(self, project):
        """Cost is recorded from the ResultMessage total_cost_usd."""
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=500, duration_api_ms=400,
                is_error=False, num_turns=3, session_id="s1",
                total_cost_usd=1.25, usage=None, result=None,
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=45000, duration_api_ms=40000,
                is_error=False, num_turns=5, session_id="s1",
                total_cost_usd=0.50, usage=None, result=None,
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.01, usage=None, result=None,
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="error", duration_ms=100, duration_api_ms=80,
                is_error=True, num_turns=0, session_id="err",
                total_cost_usd=0.01, usage=None, result="Agent failed",
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        from bob.orchestrator.claude_executor import spawn_sub_agent

        async def mock_query(*, prompt, options=None, transport=None):
            raise RuntimeError("SDK connection failed")
            yield  # Make it an async generator

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        from bob.orchestrator.claude_executor import spawn_sub_agent
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        from bob.orchestrator.claude_executor import spawn_sub_agent
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

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        from bob.orchestrator.claude_executor import spawn_sub_agent, build_sub_agent_options
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
            "bob-memory": {"type": "stdio", "command": "echo"},
        }
        opts = build_sub_agent_options(mcp_servers=mcp_servers)

        with patch("bob.orchestrator.claude_executor.query", mock_query):
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
        assert "bob-memory" in mcp_list


# ===================================================================
# R9-001: spawn_sub_agent must finalize the agent_run row even on
# CancelledError. Previously the row was left at status='running' forever
# whenever the caller's asyncio.wait_for fired its timeout.
# ===================================================================


class TestSpawnCancellationFinalizesAgentRun:
    """R9-001: a CancelledError mid-stream must update the agent_run row
    to status='interrupted', not leave it stuck at 'running'.
    """

    @pytest.mark.asyncio
    async def test_cancellation_marks_run_interrupted(self, project):
        """A CancelledError raised mid-stream must end with the
        sub_agent_runs row at status='interrupted' (not 'running').
        """
        from bob.orchestrator.claude_executor import spawn_sub_agent

        async def mock_query(*, prompt, options=None, transport=None):
            # Raise CancelledError to simulate asyncio.wait_for firing
            # its timeout while the SDK stream is being read.
            raise asyncio.CancelledError()
            yield  # pragma: no cover — make this an async generator

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            with pytest.raises(asyncio.CancelledError):
                await spawn_sub_agent(
                    project_id=project.id,
                    purpose="implement_feature",
                    prompt="Will be cancelled",
                )

        # Find the row and assert it was finalized to 'interrupted'.
        runs = db.query_agent_runs(project_id=project.id)
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "interrupted", (
            f"expected status='interrupted' on cancellation, got {run.status!r}; "
            "the agent_run row must not be left at 'running' when the "
            "coroutine is cancelled mid-stream"
        )
        assert run.completed_at is not None

    @pytest.mark.asyncio
    async def test_cancellation_via_wait_for_timeout(self, project):
        """The integration scenario: a wait_for timeout cancels the
        spawn coroutine. The row must still end at 'interrupted'.
        """
        from bob.orchestrator.claude_executor import spawn_sub_agent

        async def mock_query(*, prompt, options=None, transport=None):
            # Block long enough that wait_for will fire its timeout.
            await asyncio.sleep(10)
            yield  # pragma: no cover

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    spawn_sub_agent(
                        project_id=project.id,
                        purpose="implement_feature",
                        prompt="Will time out",
                    ),
                    timeout=0.05,
                )

        runs = db.query_agent_runs(project_id=project.id)
        assert len(runs) == 1
        assert runs[0].status == "interrupted"
        assert runs[0].completed_at is not None


# ===================================================================
# R9-007: Research and decomposer sub-agents must run
# verify_skills_integrity on their workspace before spawning, so a
# poisoned skill from a previous sub-agent cannot leak into them.
# ===================================================================


class TestResearchAgentVerifiesSkillIntegrity:
    """spawn_research_agent must invoke verify_skills_integrity on the
    workspace before spawning. Without this, a malicious sub-agent that
    previously ran in the same workspace (with bypassPermissions) could
    have replaced a bob skill symlink with a poisoned directory; the
    next research agent would then load that poisoned skill.

    Regression test for R9-007.
    """

    @pytest.mark.asyncio
    async def test_verify_skills_integrity_called_for_research(
        self, project, tmp_path
    ):
        """Spawning a research agent with workspace= triggers
        install_skills_to_workspace and verify_skills_integrity on that
        workspace before the SDK is invoked."""
        from bob.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        # Patch the skills_installer functions imported at call-time
        # inside build_sub_agent_options.
        with patch(
            "bob.skills_installer.install_skills_to_workspace"
        ) as mock_install, patch(
            "bob.skills_installer.verify_skills_integrity"
        ) as mock_verify, patch(
            "bob.orchestrator.claude_executor.query", mock_query
        ):
            await spawn_research_agent(
                project_id=project.id,
                query="What is the airspeed velocity of an unladen swallow?",
                workspace=str(tmp_path),
            )

        # The defense-in-depth contract: verify_skills_integrity ran with
        # the given workspace before the SDK call.
        assert mock_install.called, (
            "install_skills_to_workspace must be called when workspace= "
            "is supplied to spawn_research_agent (R9-007)"
        )
        assert mock_verify.called, (
            "verify_skills_integrity must be called when workspace= "
            "is supplied to spawn_research_agent (R9-007)"
        )

        # And specifically with the workspace path we passed in.
        verify_arg = mock_verify.call_args[0][0]
        assert str(verify_arg) == str(tmp_path), (
            f"verify_skills_integrity must be called with the workspace "
            f"path; got {verify_arg!r} expected {tmp_path!r}"
        )

    @pytest.mark.asyncio
    async def test_verify_skills_integrity_skipped_when_no_workspace(
        self, project
    ):
        """Without workspace=, the integrity check is skipped (caller
        opts out, e.g. tests that don't set up a workspace). This is the
        legacy behavior — R9-007 only requires the call WHEN a workspace
        is provided."""
        from bob.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch(
            "bob.skills_installer.verify_skills_integrity"
        ) as mock_verify, patch(
            "bob.orchestrator.claude_executor.query", mock_query
        ):
            await spawn_research_agent(
                project_id=project.id,
                query="Anything",
            )

        assert not mock_verify.called, (
            "verify_skills_integrity should not run when workspace is "
            "omitted (the caller chose not to scope the agent to an FS "
            "directory)"
        )


class TestDecomposerVerifiesSkillIntegrity:
    """handle_decomposition (the decomposer agent path) must propagate
    the workspace down to build_sub_agent_options so the integrity
    check runs there too. Regression test for R9-007 on the decomposer
    branch.
    """

    @pytest.mark.asyncio
    async def test_verify_skills_integrity_called_for_decomposer(
        self, project, tmp_path
    ):
        from bob.orchestrator.run_loop import handle_decomposition
        from bob.models import Feature
        from claude_code_sdk import ResultMessage

        # Build a synthetic Feature object that the decomposer will see.
        # Only the fields the decomposer actually reads are populated.
        feat = Feature(
            id="dummy-feature",
            project_id=project.id,
            name="Big feature",
            description="Too big",
            acceptance_criteria=None,
            status="ready",
            priority=10,
            risk_category="medium",
            exceeds_size_limits=True,
            size_limit_justification="too many lines",
        )

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        with patch(
            "bob.skills_installer.install_skills_to_workspace"
        ) as mock_install, patch(
            "bob.skills_installer.verify_skills_integrity"
        ) as mock_verify, patch(
            "bob.orchestrator.claude_executor.query", mock_query
        ):
            await handle_decomposition(
                project_id=project.id,
                feature=feat,
                workspace=str(tmp_path),
            )

        assert mock_install.called, (
            "install_skills_to_workspace must be called when "
            "handle_decomposition receives a workspace (R9-007)"
        )
        assert mock_verify.called, (
            "verify_skills_integrity must be called when "
            "handle_decomposition receives a workspace (R9-007)"
        )
        verify_arg = mock_verify.call_args[0][0]
        assert str(verify_arg) == str(tmp_path)


# ===================================================================
# R10-013: Spawn-time failure stderr capture
# ===================================================================


class TestSpawnFailureStderrCapture:
    """R10-013: When the SDK process dies before yielding messages, the
    SDK's ``ProcessError`` carries the placeholder stderr
    "Check stderr output for details". bob must surface a richer
    diagnostic in ``error_message``.
    """

    @pytest.mark.asyncio
    async def test_spawn_failure_includes_stderr_in_error_message(self, project):
        """An SDK-raised ``ProcessError`` is unpacked into ``error_message``
        with exit_code, captured stderr (when present), and the exception
        type — not just the placeholder string."""
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk._errors import ProcessError

        async def mock_query(*, prompt, options=None, transport=None):
            # Simulate the SDK's spawn-time failure path: a ProcessError
            # is raised before any messages are yielded. The placeholder
            # stderr is what the SDK actually emits.
            raise ProcessError(
                "Command failed with exit code 1",
                exit_code=1,
                stderr="Check stderr output for details",
            )
            yield  # noqa: F821 — keep async-generator semantics

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="Trigger a spawn failure",
            )

        assert result.execution_result.is_error is True
        msg = result.execution_result.error_message
        # The unhelpful placeholder must NOT be the entire message.
        assert msg != (
            "Command failed with exit code 1\n"
            "Error output: Check stderr output for details"
        ), (
            "R10-013: error_message must include diagnostic context "
            f"beyond the SDK placeholder; got: {msg!r}"
        )
        # Diagnostic context: exception type and exit_code surfaced.
        assert "ProcessError" in msg, (
            f"R10-013: error_message must include exception type; got: {msg!r}"
        )
        assert "exit_code" in msg, (
            f"R10-013: error_message must include exit_code; got: {msg!r}"
        )


# ===================================================================
# R10-018: stderr capture must use a real file descriptor
# ===================================================================


class TestR10_018_StderrCaptureFileDescriptor:
    """R10-018: R10-013 wired ``options.debug_stderr = io.StringIO()`` but
    the SDK calls ``.fileno()`` on the stream to set up an OS-level
    redirect. ``io.StringIO`` raises ``UnsupportedOperation: fileno`` and
    every sub-agent spawn fails with
    ``CLIConnectionError: Failed to start Claude Code: fileno``.

    The fix is to use ``tempfile.NamedTemporaryFile`` (which has a real
    fd) and clean it up after the spawn returns.
    """

    @pytest.mark.asyncio
    async def test_spawn_succeeds_when_stderr_capture_active(self, project, tmp_path):
        """A normal spawn — no exception in the SDK — must succeed even
        though stderr capture is active. Regression for R10-018."""
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_stderr_paths: list[str] = []

        async def mock_query(*, prompt, options=None, transport=None):
            # Inspect the buffer the spawn wired in: it must have a real
            # fileno() (R10-018 regression — StringIO would raise here).
            buf = getattr(options, "debug_stderr", None)
            assert buf is not None, (
                "R10-018: spawn_sub_agent must wire options.debug_stderr"
            )
            fd = buf.fileno()
            assert isinstance(fd, int), (
                f"R10-018: debug_stderr.fileno() must return int; got {fd!r}"
            )
            # Remember the path so we can verify cleanup after spawn.
            buf_name = getattr(buf, "name", None)
            if buf_name:
                captured_stderr_paths.append(buf_name)
            yield AssistantMessage(content=[TextBlock(text="ok")], model="m")
            yield ResultMessage(
                subtype="success", duration_ms=10, duration_api_ms=8,
                is_error=False, num_turns=1, session_id="s",
                total_cost_usd=0.0, usage=None, result=None,
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="trivial prompt",
            )

        # The spawn must have succeeded — no CLIConnectionError, no
        # is_error path triggered.
        assert result.execution_result.is_error is False, (
            f"R10-018: spawn must succeed; got error: "
            f"{result.execution_result.error_message!r}"
        )
        # The tempfile-backed buffer must be cleaned up after the spawn.
        import os as _os
        assert captured_stderr_paths, (
            "R10-018 test setup: mock_query did not see a buffer with .name"
        )
        for path in captured_stderr_paths:
            assert not _os.path.exists(path), (
                f"R10-018: stderr tempfile must be cleaned up after spawn; "
                f"{path!r} still exists"
            )

    @pytest.mark.asyncio
    async def test_stderr_capture_uses_real_file_descriptor(self, project):
        """Directly verify ``options.debug_stderr.fileno()`` returns an
        int instead of raising ``UnsupportedOperation``. This is the
        narrowest regression test for R10-018: the bug was that
        ``io.StringIO.fileno()`` raises ``UnsupportedOperation`` and the
        SDK propagates it as ``CLIConnectionError``."""
        import io as _io
        from bob.orchestrator.claude_executor import spawn_sub_agent
        from claude_code_sdk import ResultMessage

        observed: dict[str, object] = {}

        async def mock_query(*, prompt, options=None, transport=None):
            buf = getattr(options, "debug_stderr", None)
            observed["buf_type"] = type(buf).__name__
            try:
                observed["fileno"] = buf.fileno()
            except _io.UnsupportedOperation as exc:
                observed["fileno_error"] = repr(exc)
            yield ResultMessage(
                subtype="success", duration_ms=1, duration_api_ms=1,
                is_error=False, num_turns=1, session_id="s",
                total_cost_usd=0.0, usage=None, result=None,
            )

        with patch("bob.orchestrator.claude_executor.query", mock_query):
            await spawn_sub_agent(
                project_id=project.id,
                purpose="implement_feature",
                prompt="probe stderr",
            )

        assert "fileno_error" not in observed, (
            f"R10-018: debug_stderr.fileno() raised "
            f"{observed.get('fileno_error')!r} — buffer is not file-backed"
        )
        assert isinstance(observed.get("fileno"), int), (
            f"R10-018: debug_stderr.fileno() must return int; "
            f"observed={observed!r}"
        )
