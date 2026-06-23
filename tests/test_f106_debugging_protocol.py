"""Tests for F106: Superpowers systematic-debugging integration.

Validates that:
- Step 1: RCA system prompt includes the 4-phase debugging protocol
- Step 2: Phase 1 investigation checklist is included in RCA output
- Step 3: Root cause is required before fix proposals (no fix without root cause)
- Step 4: Test with sample failures to verify end-to-end protocol enforcement
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
    """Create a test project."""
    return db.create_project(
        name="Debug Protocol Test",
        workspace_path="/tmp/test-debug",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature within the project."""
    return db.create_feature(
        project_id=project.id,
        name="Test Feature",
        description="A feature for debugging protocol tests",
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
# Step 1: RCA prompt includes systematic debugging protocol
# ===================================================================


class TestRcaPromptContainsProtocol:
    """Step 1: The RCA system prompt includes the 4-phase debugging protocol."""

    def test_system_prompt_contains_iron_law(self):
        """RCA_SYSTEM_PROMPT mentions the iron law about root cause first."""
        from bob3.orchestrator.claude_executor import RCA_SYSTEM_PROMPT

        assert "IRON LAW" in RCA_SYSTEM_PROMPT
        assert "NO FIXES WITHOUT ROOT CAUSE" in RCA_SYSTEM_PROMPT

    def test_system_prompt_contains_phase1(self):
        """RCA_SYSTEM_PROMPT includes Phase 1: Root Cause Investigation."""
        from bob3.orchestrator.claude_executor import RCA_SYSTEM_PROMPT

        assert "Phase 1" in RCA_SYSTEM_PROMPT
        assert "Root Cause Investigation" in RCA_SYSTEM_PROMPT

    def test_system_prompt_contains_phase2(self):
        """RCA_SYSTEM_PROMPT includes Phase 2: Hypothesis Formation."""
        from bob3.orchestrator.claude_executor import RCA_SYSTEM_PROMPT

        assert "Phase 2" in RCA_SYSTEM_PROMPT
        assert "Hypothesis" in RCA_SYSTEM_PROMPT

    def test_system_prompt_contains_phase3(self):
        """RCA_SYSTEM_PROMPT includes Phase 3: Fix Recommendation."""
        from bob3.orchestrator.claude_executor import RCA_SYSTEM_PROMPT

        assert "Phase 3" in RCA_SYSTEM_PROMPT
        assert "Fix" in RCA_SYSTEM_PROMPT

    def test_system_prompt_contains_phase4(self):
        """RCA_SYSTEM_PROMPT includes Phase 4: Verification Plan."""
        from bob3.orchestrator.claude_executor import RCA_SYSTEM_PROMPT

        assert "Phase 4" in RCA_SYSTEM_PROMPT
        assert "Verification" in RCA_SYSTEM_PROMPT

    def test_system_prompt_requires_investigation_field(self):
        """RCA_SYSTEM_PROMPT requires 'investigation' field in output."""
        from bob3.orchestrator.claude_executor import RCA_SYSTEM_PROMPT

        assert "investigation" in RCA_SYSTEM_PROMPT

    def test_system_prompt_requires_verification_plan_field(self):
        """RCA_SYSTEM_PROMPT requires 'verification_plan' field in output."""
        from bob3.orchestrator.claude_executor import RCA_SYSTEM_PROMPT

        assert "verification_plan" in RCA_SYSTEM_PROMPT


# ===================================================================
# Step 2: Phase 1 checklist in RCA output
# ===================================================================


class TestPhase1ChecklistInOutput:
    """Step 2: Phase 1 checklist questions appear in the RCA prompt sent to the agent."""

    @pytest.mark.asyncio
    async def test_prompt_contains_phase1_checklist(self, project):
        """The prompt sent to the RCA agent contains Phase 1 checklist items."""
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
                failure_evidence="Test failed",
                error_type="test_failure",
                error_message="AssertionError",
            )

        prompt_text = captured_prompt["prompt"]
        # Verify all 6 Phase 1 checklist questions are present
        assert "exact error message" in prompt_text
        assert "expected behavior" in prompt_text
        assert "code/component" in prompt_text
        assert "inputs/state" in prompt_text
        assert "reproducible" in prompt_text
        assert "changed recently" in prompt_text

    @pytest.mark.asyncio
    async def test_prompt_mentions_systematic_debugging(self, project):
        """The prompt references the Systematic Debugging Protocol."""
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
                failure_evidence="Build failed",
                error_type="build_failure",
                error_message="SyntaxError",
            )

        assert "Systematic Debugging Protocol" in captured_prompt["prompt"]

    @pytest.mark.asyncio
    async def test_prompt_mentions_no_fix_without_root_cause(self, project):
        """The prompt reminds the agent not to propose fixes without root cause."""
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
                failure_evidence="Error occurred",
                error_type="runtime_error",
                error_message="KeyError: 'config'",
            )

        assert "root cause" in captured_prompt["prompt"].lower()

    def test_parse_extracts_investigation_details(self):
        """parse_rca_result extracts the Phase 1 investigation field."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "Missing null check in handler",
    "investigation": {
        "exact_error": "NullPointerException at line 42",
        "expected_vs_actual": "Expected non-null, got null",
        "component": "RequestHandler.process()",
        "inputs_state": "Request with missing 'user_id' field",
        "reproducible": "Yes, always when user_id is null",
        "recent_changes": "Added new validation in v2.1"
    },
    "hypothesis": "The handler does not check for null user_id",
    "verification_plan": "Add test for null user_id input"
}
```"""
        result = parse_rca_result(response_text)
        assert "investigation" in result
        # Verify it was serialized from the dict
        inv = json.loads(result["investigation"])
        assert inv["exact_error"] == "NullPointerException at line 42"

    def test_parse_extracts_hypothesis(self):
        """parse_rca_result extracts the Phase 2 hypothesis."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "Buffer overflow in parser",
    "hypothesis": "The parser does not check input length",
    "verification_plan": "Add length validation test"
}
```"""
        result = parse_rca_result(response_text)
        assert result.get("hypothesis") == "The parser does not check input length"

    def test_parse_extracts_verification_plan(self):
        """parse_rca_result extracts the Phase 4 verification plan."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "validation",
    "recommended_action": "fix_test",
    "root_cause": "Test uses wrong expected value",
    "verification_plan": "Update expected value from 42 to 43 and re-run suite"
}
```"""
        result = parse_rca_result(response_text)
        assert result.get("verification_plan") == "Update expected value from 42 to 43 and re-run suite"


# ===================================================================
# Step 3: Root cause required before fix proposals
# ===================================================================


class TestRootCauseRequiredBeforeFix:
    """Step 3: Fix actions are downgraded to 'investigate' when root_cause is missing."""

    def test_fix_code_without_root_cause_downgrades(self):
        """fix_code without root_cause is downgraded to investigate."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code"
}
```"""
        result = parse_rca_result(response_text)
        assert result["recommended_action"] == "investigate"

    def test_fix_test_without_root_cause_downgrades(self):
        """fix_test without root_cause is downgraded to investigate."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "validation",
    "recommended_action": "fix_test"
}
```"""
        result = parse_rca_result(response_text)
        assert result["recommended_action"] == "investigate"

    def test_clarify_spec_without_root_cause_downgrades(self):
        """clarify_spec without root_cause is downgraded to investigate."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "feature_spec",
    "recommended_action": "clarify_spec"
}
```"""
        result = parse_rca_result(response_text)
        assert result["recommended_action"] == "investigate"

    def test_fix_code_with_root_cause_preserved(self):
        """fix_code WITH root_cause is preserved as-is."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "Missing return statement on line 42"
}
```"""
        result = parse_rca_result(response_text)
        assert result["recommended_action"] == "fix_code"
        assert result["root_cause"] == "Missing return statement on line 42"

    def test_fix_test_with_root_cause_preserved(self):
        """fix_test WITH root_cause is preserved as-is."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "validation",
    "recommended_action": "fix_test",
    "root_cause": "Test expected old API response format"
}
```"""
        result = parse_rca_result(response_text)
        assert result["recommended_action"] == "fix_test"

    def test_retry_without_root_cause_not_downgraded(self):
        """Non-fix actions like retry are NOT downgraded even without root cause."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "infrastructure",
    "recommended_action": "retry"
}
```"""
        result = parse_rca_result(response_text)
        assert result["recommended_action"] == "retry"

    def test_investigate_without_root_cause_not_downgraded(self):
        """investigate is NOT downgraded (it's already the fallback)."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "unknown",
    "recommended_action": "investigate"
}
```"""
        result = parse_rca_result(response_text)
        assert result["recommended_action"] == "investigate"

    def test_escalate_without_root_cause_not_downgraded(self):
        """escalate is NOT downgraded even without root cause."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "external",
    "recommended_action": "escalate"
}
```"""
        result = parse_rca_result(response_text)
        assert result["recommended_action"] == "escalate"

    def test_empty_root_cause_treated_as_missing(self):
        """An empty string root_cause is treated as missing."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response_text = """```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": ""
}
```"""
        result = parse_rca_result(response_text)
        assert result["recommended_action"] == "investigate"

    def test_fix_actions_constant_exists(self):
        """The _FIX_ACTIONS constant is defined with the expected values."""
        from bob3.orchestrator.claude_executor import _FIX_ACTIONS

        assert "fix_code" in _FIX_ACTIONS
        assert "fix_test" in _FIX_ACTIONS
        assert "clarify_spec" in _FIX_ACTIONS
        assert "retry" not in _FIX_ACTIONS
        assert "investigate" not in _FIX_ACTIONS
        assert "escalate" not in _FIX_ACTIONS


# ===================================================================
# Step 4: Integration test with sample failure
# ===================================================================


class TestSampleFailureIntegration:
    """Step 4: End-to-end test with a sample failure verifying protocol enforcement."""

    @pytest.mark.asyncio
    async def test_full_protocol_with_all_phases(self, project, feature, task):
        """Full lifecycle: RCA with all 4 phases completed."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent, SpawnResult
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="""After thorough investigation:

## Phase 1: Root Cause Investigation
- Exact error: AttributeError: 'NoneType' object has no attribute 'upper'
- Expected: create_widget("button") returns Widget; Actual: raises AttributeError
- Component: src/widgets/factory.py:42 create_widget()
- Input/State: widget_type=None passed from test
- Reproducible: Yes, always with None input
- Recent change: Parameter validation removed in refactor commit abc123

## Phase 2: Hypothesis
The create_widget function was refactored and the null guard was removed.

## Phase 3: Fix
Add null check before .upper() call.

## Phase 4: Verification
Add test_create_widget_with_none to verify graceful handling.

```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "create_widget() null guard removed during refactor in commit abc123",
    "investigation": {
        "exact_error": "AttributeError: 'NoneType' object has no attribute 'upper'",
        "expected_vs_actual": "Expected Widget object, got AttributeError",
        "component": "src/widgets/factory.py:42 create_widget()",
        "inputs_state": "widget_type=None",
        "reproducible": "Yes, always with None input",
        "recent_changes": "Null guard removed in refactor commit abc123"
    },
    "hypothesis": "Null guard was removed during refactoring",
    "verification_plan": "Add test_create_widget_with_none to test suite"
}
```""")],
                model="claude-sonnet-4-5-20250929",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=15000,
                duration_api_ms=12000,
                is_error=False,
                num_turns=3,
                session_id="rca-protocol",
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
            )

        assert isinstance(result, SpawnResult)
        assert result.execution_result.is_error is False

        # Verify RCA results stored correctly
        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.rca_blame_target == "implementation"
        assert run.rca_recommended_action == "fix_code"

    @pytest.mark.asyncio
    async def test_fix_without_root_cause_downgraded_in_integration(self, project):
        """Integration: agent proposes fix without root cause, gets downgraded."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            # Agent proposes fix but forgets root_cause
            yield AssistantMessage(
                content=[TextBlock(text="""```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code"
}
```""")],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=5000,
                duration_api_ms=4000,
                is_error=False,
                num_turns=1,
                session_id="rca-no-root",
                total_cost_usd=0.05,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="Some test failed",
                error_type="test_failure",
                error_message="AssertionError",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        # Should be downgraded from fix_code to investigate
        assert run.rca_recommended_action == "investigate"
        assert run.rca_blame_target == "implementation"

    @pytest.mark.asyncio
    async def test_system_prompt_includes_debugging_protocol(self, project):
        """The system prompt passed to the agent includes the debugging protocol."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import ResultMessage

        captured_options = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options["options"] = options
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
                failure_evidence="Error",
                error_type="test_failure",
                error_message="Fail",
            )

        opts = captured_options["options"]
        assert opts is not None
        system_prompt = opts.system_prompt
        assert "IRON LAW" in system_prompt
        assert "Phase 1" in system_prompt
        assert "Phase 2" in system_prompt
        assert "Phase 3" in system_prompt
        assert "Phase 4" in system_prompt


# ===================================================================
# Step 5: Backward compatibility with existing F058 tests
# ===================================================================


class TestBackwardCompatibility:
    """Ensure F106 changes don't break existing F058 behavior."""

    def test_parse_still_handles_no_json(self):
        """parse_rca_result still returns defaults when no JSON is found."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        result = parse_rca_result("I couldn't determine the root cause.")
        assert result["blame_target"] == "unknown"
        assert result["recommended_action"] == "investigate"

    def test_parse_still_handles_inline_json_with_root_cause(self):
        """parse_rca_result still handles inline JSON."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response = '{"blame_target": "feature_spec", "recommended_action": "clarify_spec", "root_cause": "Ambiguous requirements"}'
        result = parse_rca_result(response)
        assert result["blame_target"] == "feature_spec"
        assert result["recommended_action"] == "clarify_spec"

    def test_parse_handles_fenced_json_with_root_cause(self):
        """parse_rca_result handles fenced JSON with all fields."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response = """```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "Missing null check",
    "details": "Line 42 needs guard clause"
}
```"""
        result = parse_rca_result(response)
        assert result["blame_target"] == "implementation"
        assert result["recommended_action"] == "fix_code"
        assert result["root_cause"] == "Missing null check"

    def test_parse_infrastructure_retry_still_works(self):
        """Infrastructure/retry combos still work without root_cause."""
        from bob3.orchestrator.claude_executor import parse_rca_result

        response = """```json
{
    "blame_target": "infrastructure",
    "recommended_action": "retry",
    "root_cause": "Transient network error"
}
```"""
        result = parse_rca_result(response)
        assert result["blame_target"] == "infrastructure"
        assert result["recommended_action"] == "retry"


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
