"""Tests for F058: Implement RCA (Root Cause Analysis) sub-agent invocation.

Validates that:
- Step 1: spawn_rca_agent() function exists and is async
- Step 2: Failure evidence is passed to the RCA agent
- Step 3: RCA results (blame_target, recommended_action) are parsed
- Step 4: Results stored in sub_agent_runs.rca_blame_target and rca_recommended_action
- Step 5: Integration test: trigger RCA for test failure, verify blame and action captured
"""

import asyncio
import json
import pathlib
from unittest.mock import patch

import pytest

from bob3 import db
from bob3.models import SubAgentRun

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
EXECUTOR_PATH = SRC_DIR / "bob3" / "orchestrator" / "claude_executor.py"


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project for RCA agent spawning."""
    return db.create_project(
        name="RCA Test Project",
        workspace_path="/tmp/test-rca",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature within the project."""
    return db.create_feature(
        project_id=project.id,
        name="Test Feature",
        description="A feature that might fail",
    )


@pytest.fixture()
def task(project, feature):
    """Create a test task within the feature."""
    return db.create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="validation",
        title="Run test suite",
        task_class="test_writing",
    )


# ===================================================================
# Step 1: spawn_rca_agent() function exists and is async
# ===================================================================


class TestSpawnRcaAgentExists:
    """Step 1: spawn_rca_agent() function must exist and be async."""

    def test_function_exists(self):
        from bob3.orchestrator.claude_executor import spawn_rca_agent

        assert callable(spawn_rca_agent)

    def test_function_is_async(self):
        from bob3.orchestrator.claude_executor import spawn_rca_agent

        assert asyncio.iscoroutinefunction(spawn_rca_agent)

    def test_function_accepts_required_params(self):
        """spawn_rca_agent requires project_id, failure_evidence, and error context."""
        import inspect
        from bob3.orchestrator.claude_executor import spawn_rca_agent

        sig = inspect.signature(spawn_rca_agent)
        param_names = set(sig.parameters.keys())
        assert "project_id" in param_names
        assert "failure_evidence" in param_names
        assert "error_type" in param_names
        assert "error_message" in param_names


# ===================================================================
# Step 2: Failure evidence is passed to the RCA agent
# ===================================================================


class TestPassesFailureEvidence:
    """Step 2: Failure evidence is included in the prompt to the RCA agent."""

    @pytest.mark.asyncio
    async def test_prompt_contains_error_message(self, project):
        """The prompt sent to the agent contains the error message."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
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
            await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Test output: FAILED test_widget.py::test_create",
                error_type="test_failure",
                error_message="AssertionError: expected 42 got None",
            )

        assert "AssertionError: expected 42 got None" in captured_prompt["prompt"]

    @pytest.mark.asyncio
    async def test_prompt_contains_error_type(self, project):
        """The prompt contains the error type."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
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
            await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Build output: compilation error",
                error_type="build_failure",
                error_message="SyntaxError in module.py",
            )

        assert "build_failure" in captured_prompt["prompt"]

    @pytest.mark.asyncio
    async def test_prompt_contains_failure_evidence(self, project):
        """The prompt contains the full failure evidence."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import ResultMessage

        captured_prompt = {}
        evidence = "FAILED tests/test_auth.py::test_login_returns_token\nE  KeyError: 'token'"

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
            await spawn_rca_agent(
                project_id=project.id,
                failure_evidence=evidence,
                error_type="test_failure",
                error_message="KeyError: 'token'",
            )

        assert "KeyError: 'token'" in captured_prompt["prompt"]
        assert "test_auth.py" in captured_prompt["prompt"]

    @pytest.mark.asyncio
    async def test_optional_target_forwarded(self, project, feature, task):
        """Optional target_type and target_id are forwarded."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
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
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Test failed",
                error_type="test_failure",
                error_message="AssertionError",
                target_type="task",
                target_id=task.id,
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.target_type == "task"
        assert run.target_id == task.id


# ===================================================================
# Step 3: Parse RCA results (blame_target, recommended_action)
# ===================================================================


class TestParseRcaResults:
    """Step 3: RCA results are parsed from the agent's response."""

    def test_parse_rca_result_extracts_blame_and_action(self):
        """parse_rca_result extracts blame_target and recommended_action from JSON."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """After analyzing the failure, here is my RCA:

```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "The function returns None instead of the expected value",
    "details": "The calculate_total function is missing a return statement"
}
```
"""
        result = parse_rca_result(response_text)
        assert result["blame_target"] == "implementation"
        assert result["recommended_action"] == "fix_code"

    def test_parse_rca_result_handles_validation_blame(self):
        """parse_rca_result handles 'validation' blame_target."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "validation",
    "recommended_action": "fix_test",
    "root_cause": "Test assertions are incorrect"
}
```"""
        result = parse_rca_result(response_text)
        assert result["blame_target"] == "validation"
        assert result["recommended_action"] == "fix_test"

    def test_parse_rca_result_handles_infrastructure_blame(self):
        """parse_rca_result handles 'infrastructure' blame_target."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "infrastructure",
    "recommended_action": "retry",
    "root_cause": "Transient network error"
}
```"""
        result = parse_rca_result(response_text)
        assert result["blame_target"] == "infrastructure"
        assert result["recommended_action"] == "retry"

    def test_parse_rca_result_handles_no_json(self):
        """parse_rca_result returns defaults when no JSON is found."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = "I couldn't determine the root cause."
        result = parse_rca_result(response_text)
        assert result["blame_target"] == "unknown"
        assert result["recommended_action"] == "investigate"

    def test_parse_rca_result_handles_inline_json(self):
        """parse_rca_result extracts JSON even without code fences."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = 'The analysis result: {"blame_target": "feature_spec", "recommended_action": "clarify_spec", "root_cause": "Ambiguous requirements"}'
        result = parse_rca_result(response_text)
        assert result["blame_target"] == "feature_spec"
        assert result["recommended_action"] == "clarify_spec"

    def test_parse_rca_result_extracts_root_cause(self):
        """parse_rca_result extracts root_cause when present."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "Missing null check in handler"
}
```"""
        result = parse_rca_result(response_text)
        assert result.get("root_cause") == "Missing null check in handler"


# ===================================================================
# Step 4: Store in sub_agent_runs.rca_blame_target and rca_recommended_action
# ===================================================================


class TestStoresRcaResults:
    """Step 4: RCA results are stored in the sub_agent_runs record."""

    @pytest.mark.asyncio
    async def test_blame_target_stored_in_agent_run(self, project):
        """rca_blame_target is stored in the agent run record."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="""```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "Missing return statement"
}
```""")],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=5000,
                duration_api_ms=4000,
                is_error=False,
                num_turns=2,
                session_id="rca-1",
                total_cost_usd=0.05,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Test failed: assert 42 == None",
                error_type="test_failure",
                error_message="AssertionError",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.rca_blame_target == "implementation"

    @pytest.mark.asyncio
    async def test_recommended_action_stored_in_agent_run(self, project):
        """rca_recommended_action is stored in the agent run record."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="""```json
{
    "blame_target": "validation",
    "recommended_action": "fix_test",
    "root_cause": "Incorrect test expectation"
}
```""")],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=3000,
                duration_api_ms=2500,
                is_error=False,
                num_turns=2,
                session_id="rca-2",
                total_cost_usd=0.03,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Test output mismatch",
                error_type="test_failure",
                error_message="Expected 'hello' got 'Hello'",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.rca_recommended_action == "fix_test"

    @pytest.mark.asyncio
    async def test_purpose_is_rca_analyst(self, project):
        """The agent run has purpose='rca_analyst'."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
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
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Something failed",
                error_type="test_failure",
                error_message="Error",
            )

        assert result.agent_run.purpose == "rca_analyst"

    @pytest.mark.asyncio
    async def test_defaults_stored_when_parse_fails(self, project):
        """Default values are stored when RCA response cannot be parsed."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="I couldn't figure out the issue.")],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=2000,
                duration_api_ms=1500,
                is_error=False,
                num_turns=1,
                session_id="rca-3",
                total_cost_usd=0.02,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Unclear failure",
                error_type="unknown",
                error_message="Something went wrong",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.rca_blame_target == "unknown"
        assert run.rca_recommended_action == "investigate"

    @pytest.mark.asyncio
    async def test_rca_results_stored_on_error(self, project):
        """When the agent itself errors, defaults are stored."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent

        async def mock_query(*, prompt, options=None, transport=None):
            raise RuntimeError("SDK connection failed")
            yield  # make it async generator

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Test failed",
                error_type="test_failure",
                error_message="Error",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.status == "failed"
        assert run.rca_blame_target == "unknown"
        assert run.rca_recommended_action == "investigate"


# ===================================================================
# Step 5: Integration test: full RCA lifecycle
# ===================================================================


class TestRcaIntegration:
    """Step 5: Full integration test for RCA lifecycle."""

    @pytest.mark.asyncio
    async def test_full_rca_lifecycle(self, project, feature, task):
        """Full lifecycle: trigger RCA for test failure, verify blame and action."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent, SpawnResult
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="""After thorough analysis of the failure evidence:

The test `test_create_widget` is failing because the `create_widget` function
in `src/widgets/factory.py` does not handle the case where `widget_type` is None.

```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "create_widget() does not handle None widget_type parameter",
    "details": "Line 42 in factory.py attempts to call .upper() on widget_type without null check"
}
```

I recommend adding a None check before the .upper() call.""")],
                model="claude-sonnet-4-5-20250929",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=15000,
                duration_api_ms=12000,
                is_error=False,
                num_turns=3,
                session_id="rca-full",
                total_cost_usd=0.25,
                usage=None,
                result=None,
            )

        failure_evidence = """FAILED tests/test_widgets.py::test_create_widget
E   AttributeError: 'NoneType' object has no attribute 'upper'

src/widgets/factory.py:42: in create_widget
    normalized = widget_type.upper()
tests/test_widgets.py:15: in test_create_widget
    result = create_widget(None)"""

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence=failure_evidence,
                error_type="test_failure",
                error_message="AttributeError: 'NoneType' object has no attribute 'upper'",
                target_type="task",
                target_id=task.id,
                parent_run_id=None,
            )

        # Verify it returns a SpawnResult
        assert isinstance(result, SpawnResult)

        # Verify execution result
        assert "create_widget" in result.execution_result.text
        assert result.execution_result.is_error is False

        # Verify agent run record
        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.project_id == project.id
        assert run.purpose == "rca_analyst"
        assert run.target_type == "task"
        assert run.target_id == task.id
        assert run.status == "completed"
        assert run.completed_at is not None
        assert run.cost_usd == pytest.approx(0.25)
        assert run.duration_ms == 15000

        # Verify RCA results are stored
        assert run.rca_blame_target == "implementation"
        assert run.rca_recommended_action == "fix_code"

    @pytest.mark.asyncio
    async def test_rca_with_parent_run(self, project):
        """RCA agent respects parent_run_id for hierarchy tracking."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        parent = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text='{"blame_target": "test_flaky", "recommended_action": "retry", "root_cause": "Timing issue"}')],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=2000,
                duration_api_ms=1500,
                is_error=False,
                num_turns=1,
                session_id="rca-parent",
                total_cost_usd=0.02,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Intermittent test failure",
                error_type="test_failure",
                error_message="Timeout",
                parent_run_id=parent.id,
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.parent_run_id == parent.id
        assert run.rca_blame_target == "test_flaky"
        assert run.rca_recommended_action == "retry"

    @pytest.mark.asyncio
    async def test_rca_queryable_by_purpose(self, project):
        """RCA runs are queryable via query_agent_runs(purpose='rca_analyst')."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text='{"blame_target": "implementation", "recommended_action": "fix_code"}')],
                model="m",
            )
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
            await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Test failed",
                error_type="test_failure",
                error_message="Error",
            )

        rca_runs = db.query_agent_runs(
            project_id=project.id,
            purpose="rca_analyst",
        )
        assert len(rca_runs) == 1
        assert rca_runs[0].rca_blame_target == "implementation"


# ===================================================================
# Step 6: No forbidden patterns
# ===================================================================


class TestNoForbiddenPatterns:
    """No subprocess calls or forbidden imports in the module."""

    def test_no_subprocess_in_module(self):
        import re as _re
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
        assert not _re.search(r'^\s*(import\s+subprocess|from\s+subprocess\b)', source, _re.MULTILINE), (
            "Found forbidden subprocess import in claude_executor.py"
        )
        assert not _re.search(r'\bsubprocess\.', code_only), (
            "Found forbidden subprocess usage in claude_executor.py"
        )

    def test_no_anthropic_import(self):
        source = EXECUTOR_PATH.read_text()
        assert "from anthropic" not in source
        assert "import anthropic" not in source
