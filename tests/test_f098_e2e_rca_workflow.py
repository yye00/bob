"""Tests for F098: End-to-end test - RCA workflow (failure -> RCA -> bug -> lesson).

Exercises the complete RCA lifecycle:
  Step 1: Execute task that fails
  Step 2: Spawn RCA sub-agent
  Step 3: Verify RCA identifies blame_target=implementation
  Step 4: Create bug_ledger entry from RCA
  Step 5: Resolve bug with fix
  Step 6: Create lesson in TITANS Memory from bug resolution
  Step 7: Verify titans_memory_id stored in bug_ledger
"""

import json
import pathlib
import tempfile
from unittest.mock import patch

import pytest

from bob3 import db
from bob3.models import BugLedger, SubAgentRun
from bob3.memory_client import MemoryResult, BobMemoryClient as TitansMemoryClient


@pytest.fixture()
def tmp_db(monkeypatch):
    """Create a temporary database for the e2e test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test.db"
        monkeypatch.setattr(db, "get_database_path", lambda: db_path)
        db.init_database(db_path=db_path)
        yield db_path


# ============================================================
# Step 1: Execute task that fails
# ============================================================


class TestStep1ExecuteFailingTask:
    def test_task_created_and_marked_failed(self, tmp_db):
        """Create a project/feature/task and simulate a task failure."""
        project = db.create_project(
            name="rca-e2e-project",
            workspace_path="/tmp/rca-e2e-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Widget Factory",
            description="Create widgets with type normalization",
            status="executing",
            priority=10,
        )
        task = db.create_task(
            feature_id=feature.id,
            project_id=project.id,
            type="validation",
            title="Run widget test suite",
            task_class="test_writing",
        )

        assert task.id is not None
        assert task.type == "validation"

        # Mark task as failed
        updated = db.update_task(task.id, status="failed")
        assert updated is not None
        assert updated.status == "failed"


# ============================================================
# Step 2: Spawn RCA sub-agent
# ============================================================


class TestStep2SpawnRcaAgent:
    @pytest.mark.asyncio
    async def test_rca_agent_spawned_for_failure(self, tmp_db):
        """Spawn an RCA sub-agent to analyze the task failure."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        project = db.create_project(
            name="rca-e2e-project",
            workspace_path="/tmp/rca-e2e-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Widget Factory",
            status="executing",
        )
        task = db.create_task(
            feature_id=feature.id,
            project_id=project.id,
            type="validation",
            title="Run widget test suite",
            task_class="test_writing",
        )
        db.update_task(task.id, status="failed")

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="""```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "create_widget() does not handle None widget_type",
    "details": "Line 42 in factory.py attempts .upper() on None"
}
```""")],
                model="claude-sonnet-4-5-20250929",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=5000,
                duration_api_ms=4000,
                is_error=False,
                num_turns=2,
                session_id="rca-e2e-1",
                total_cost_usd=0.05,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="FAILED tests/test_widgets.py::test_create_widget\nE   AttributeError: 'NoneType' object has no attribute 'upper'",
                error_type="test_failure",
                error_message="AttributeError: 'NoneType' object has no attribute 'upper'",
                target_type="task",
                target_id=task.id,
            )

        assert result.agent_run is not None
        assert result.agent_run.purpose == "rca_analyst"
        assert result.agent_run.status == "completed"


# ============================================================
# Step 3: Verify RCA identifies blame_target=implementation
# ============================================================


class TestStep3VerifyBlameTarget:
    @pytest.mark.asyncio
    async def test_rca_blame_target_is_implementation(self, tmp_db):
        """RCA result identifies blame_target as 'implementation'."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        project = db.create_project(
            name="rca-e2e-project",
            workspace_path="/tmp/rca-e2e-ws",
        )

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="""```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "create_widget() does not handle None widget_type"
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
                session_id="rca-e2e-2",
                total_cost_usd=0.03,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="FAILED test_create_widget",
                error_type="test_failure",
                error_message="AttributeError",
            )

        run = db.get_agent_run(result.agent_run.id)
        assert run is not None
        assert run.rca_blame_target == "implementation"
        assert run.rca_recommended_action == "fix_code"


# ============================================================
# Step 4: Create bug_ledger entry from RCA
# ============================================================


class TestStep4CreateBugFromRca:
    def test_bug_created_from_rca_result(self, tmp_db):
        """Create a bug_ledger entry using the RCA results."""
        project = db.create_project(
            name="rca-e2e-project",
            workspace_path="/tmp/rca-e2e-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Widget Factory",
            status="executing",
        )
        task = db.create_task(
            feature_id=feature.id,
            project_id=project.id,
            type="validation",
            title="Run widget test suite",
            task_class="test_writing",
        )

        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "create_widget() does not handle None widget_type",
            "details": "Line 42 in factory.py attempts .upper() on None",
        }

        bug = db.create_bug_from_rca(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="test_failure",
            error_message="AttributeError: 'NoneType' object has no attribute 'upper'",
            error_context="FAILED tests/test_widgets.py::test_create_widget",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-trace-001", "ev-log-002"]),
        )

        assert isinstance(bug, BugLedger)
        assert bug.blame_target == "implementation"
        assert bug.fix_action == "fix_code"
        assert bug.root_cause == "create_widget() does not handle None widget_type"
        assert bug.resolved is False


# ============================================================
# Step 5: Resolve bug with fix
# ============================================================


class TestStep5ResolveBug:
    def test_bug_resolved_after_fix(self, tmp_db):
        """Resolve the bug after applying a fix."""
        project = db.create_project(
            name="rca-e2e-project",
            workspace_path="/tmp/rca-e2e-ws",
        )

        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "create_widget() does not handle None widget_type",
        }

        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="test_failure",
            error_message="AttributeError: 'NoneType' has no attribute 'upper'",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-trace-001"]),
        )
        assert bug.resolved is False

        resolved = db.resolve_bug(
            bug.id,
            fix_evidence="Added null check in create_widget(). All tests pass.",
        )
        assert resolved is not None
        assert resolved.resolved is True
        assert resolved.resolved_at is not None
        assert "null check" in resolved.fix_evidence


# ============================================================
# Step 6: Create lesson in TITANS Memory from bug resolution
# ============================================================


class TestStep6CreateLessonFromBug:
    @pytest.mark.asyncio
    async def test_lesson_created_from_resolved_bug(self, tmp_db):
        """Create a lesson in TITANS Memory from the resolved bug."""
        project = db.create_project(
            name="rca-e2e-project",
            workspace_path="/tmp/rca-e2e-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Widget Factory",
            status="executing",
        )
        task = db.create_task(
            feature_id=feature.id,
            project_id=project.id,
            type="validation",
            title="Run widget test suite",
            task_class="test_writing",
        )

        bug = db.create_bug(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="test_failure",
            error_message="AttributeError: 'NoneType' has no attribute 'upper'",
            error_context="FAILED tests/test_widgets.py::test_create_widget",
            evidence_artifacts=json.dumps(["ev-trace-001"]),
            blame_target="implementation",
            root_cause="create_widget() does not handle None widget_type",
            fix_action="fix_code",
            fix_details="Added null check before calling .upper()",
        )
        db.resolve_bug(bug.id, fix_evidence="All widget tests pass now")

        client = TitansMemoryClient(workspace="/tmp/test")
        stored_content = []
        stored_metadata = []

        async def capture_add(content, pool=None, metadata=None):
            stored_content.append(content)
            stored_metadata.append({"pool": pool, "metadata": metadata})
            return MemoryResult(
                success=True,
                data={"id": "mem-rca-lesson-001", "content": content},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture_add):
            result = await client.create_lesson_from_bug(bug_id=bug.id)

        assert result.success is True
        assert result.data["id"] == "mem-rca-lesson-001"

        # Verify lesson content
        content = stored_content[0]
        assert "TRIGGER:" in content
        assert "test_failure" in content
        assert "LESSON:" in content
        assert "create_widget()" in content
        assert "SOLUTION:" in content
        assert "fix_code" in content

        # Verify pool and metadata
        assert stored_metadata[0]["pool"] == "lessons"
        meta = stored_metadata[0]["metadata"]
        assert meta["bug_id"] == bug.id
        assert meta["feature_id"] == feature.id


# ============================================================
# Step 7: Verify titans_memory_id stored in bug_ledger
# ============================================================


class TestStep7VerifyTitansMemoryId:
    @pytest.mark.asyncio
    async def test_titans_memory_id_stored_in_bug(self, tmp_db):
        """Verify titans_memory_id is stored in the bug_ledger after lesson creation."""
        project = db.create_project(
            name="rca-e2e-project",
            workspace_path="/tmp/rca-e2e-ws",
        )

        bug = db.create_bug(
            project_id=project.id,
            error_type="test_failure",
            error_message="AttributeError: 'NoneType' has no attribute 'upper'",
            evidence_artifacts=json.dumps(["ev-trace-001"]),
            blame_target="implementation",
            root_cause="create_widget() does not handle None widget_type",
            fix_action="fix_code",
        )
        db.resolve_bug(bug.id, fix_evidence="Fixed")

        # Before lesson creation: no titans_memory_id
        assert db.get_bug(bug.id).titans_memory_id is None

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fake_add(content, pool=None, metadata=None):
            return MemoryResult(
                success=True,
                data={"id": "mem-rca-lesson-002", "content": content},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=fake_add):
            await client.create_lesson_from_bug(bug_id=bug.id)

        # After lesson creation: titans_memory_id should be set
        updated_bug = db.get_bug(bug.id)
        assert updated_bug.titans_memory_id == "mem-rca-lesson-002"


# ============================================================
# Full E2E: All 7 steps in a single test
# ============================================================


class TestFullRcaWorkflowE2E:
    @pytest.mark.asyncio
    async def test_complete_rca_workflow(self, tmp_db):
        """End-to-end: failure -> RCA -> bug -> fix -> lesson -> verify memory link.

        Exercises the full acceptance criteria in a single sequential workflow:
          Step 1: Execute task that fails
          Step 2: Spawn RCA sub-agent
          Step 3: Verify RCA identifies blame_target=implementation
          Step 4: Create bug_ledger entry from RCA
          Step 5: Resolve bug with fix
          Step 6: Create lesson in TITANS Memory from bug resolution
          Step 7: Verify titans_memory_id stored in bug_ledger
        """
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        # ---- Step 1: Execute task that fails ----
        project = db.create_project(
            name="e2e-rca-project",
            workspace_path="/tmp/e2e-rca-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Widget Factory Feature",
            description="Create widgets with type normalization",
            acceptance_criteria=json.dumps(["Widget creation handles all types"]),
            status="executing",
            priority=10,
            risk_category="medium",
        )
        task = db.create_task(
            feature_id=feature.id,
            project_id=project.id,
            type="validation",
            title="Run widget test suite",
            task_class="test_writing",
        )

        # Simulate task failure
        db.update_task(task.id, status="failed")
        failed_task = db.get_task(task.id)
        assert failed_task.status == "failed"

        failure_evidence = (
            "FAILED tests/test_widgets.py::test_create_widget\n"
            "E   AttributeError: 'NoneType' object has no attribute 'upper'\n"
            "\n"
            "src/widgets/factory.py:42: in create_widget\n"
            "    normalized = widget_type.upper()\n"
            "tests/test_widgets.py:15: in test_create_widget\n"
            "    result = create_widget(None)"
        )

        # ---- Step 2: Spawn RCA sub-agent ----
        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="""After thorough analysis following the Systematic Debugging Protocol:

Phase 1 Investigation:
- Exact error: AttributeError on NoneType.upper()
- Expected: create_widget handles None gracefully
- Component: src/widgets/factory.py:42
- Root cause: Missing null check

```json
{
    "blame_target": "implementation",
    "recommended_action": "fix_code",
    "root_cause": "create_widget() does not handle None widget_type parameter",
    "details": "Line 42 in factory.py attempts to call .upper() on widget_type without null check",
    "investigation": {
        "exact_error": "AttributeError: 'NoneType' object has no attribute 'upper'",
        "expected_behavior": "create_widget should handle None gracefully",
        "component": "src/widgets/factory.py:42"
    },
    "hypothesis": "The function lacks a null check before calling .upper()",
    "verification_plan": "Add test for None input, verify existing tests still pass"
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
                session_id="rca-e2e-full",
                total_cost_usd=0.25,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            rca_spawn_result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence=failure_evidence,
                error_type="test_failure",
                error_message="AttributeError: 'NoneType' object has no attribute 'upper'",
                target_type="task",
                target_id=task.id,
            )

        # Verify sub-agent was spawned and completed
        assert rca_spawn_result.agent_run is not None
        assert rca_spawn_result.agent_run.purpose == "rca_analyst"
        assert rca_spawn_result.agent_run.status == "completed"
        assert rca_spawn_result.execution_result.is_error is False

        # ---- Step 3: Verify RCA identifies blame_target=implementation ----
        rca_run = db.get_agent_run(rca_spawn_result.agent_run.id)
        assert rca_run is not None
        assert rca_run.rca_blame_target == "implementation"
        assert rca_run.rca_recommended_action == "fix_code"
        assert rca_run.target_type == "task"
        assert rca_run.target_id == task.id

        # ---- Step 4: Create bug_ledger entry from RCA ----
        rca_result = {
            "blame_target": rca_run.rca_blame_target,
            "recommended_action": rca_run.rca_recommended_action,
            "root_cause": "create_widget() does not handle None widget_type parameter",
            "details": "Line 42 in factory.py attempts to call .upper() on widget_type without null check",
        }

        bug = db.create_bug_from_rca(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="test_failure",
            error_message="AttributeError: 'NoneType' object has no attribute 'upper'",
            error_context="FAILED tests/test_widgets.py::test_create_widget",
            rca_result=rca_result,
            evidence_artifacts=json.dumps([
                "ev-trace-001",
                "ev-log-002",
                rca_spawn_result.agent_run.id,
            ]),
        )

        assert isinstance(bug, BugLedger)
        assert bug.project_id == project.id
        assert bug.feature_id == feature.id
        assert bug.task_id == task.id
        assert bug.blame_target == "implementation"
        assert bug.fix_action == "fix_code"
        assert bug.root_cause == "create_widget() does not handle None widget_type parameter"
        assert bug.fix_details == "Line 42 in factory.py attempts to call .upper() on widget_type without null check"
        assert bug.resolved is False
        assert bug.titans_memory_id is None

        # Verify bug persisted to database
        persisted_bug = db.get_bug(bug.id)
        assert persisted_bug is not None
        assert persisted_bug.blame_target == "implementation"

        # ---- Step 5: Resolve bug with fix ----
        resolved_bug = db.resolve_bug(
            bug.id,
            fix_evidence="Added null check in create_widget(). All 15 widget tests pass.",
        )

        assert resolved_bug is not None
        assert resolved_bug.resolved is True
        assert resolved_bug.resolved_at is not None
        assert "null check" in resolved_bug.fix_evidence
        assert "All 15 widget tests pass" in resolved_bug.fix_evidence

        # ---- Step 6: Create lesson in TITANS Memory from bug resolution ----
        client = TitansMemoryClient(workspace="/tmp/test")
        stored_content = []
        stored_metadata = []

        async def capture_add(content, pool=None, metadata=None):
            stored_content.append(content)
            stored_metadata.append({"pool": pool, "metadata": metadata})
            return MemoryResult(
                success=True,
                data={"id": "mem-widget-lesson-e2e", "content": content},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture_add):
            lesson_result = await client.create_lesson_from_bug(bug_id=bug.id)

        # Verify lesson was created successfully
        assert lesson_result.success is True
        assert lesson_result.data["id"] == "mem-widget-lesson-e2e"

        # Verify lesson content formatting
        content = stored_content[0]
        assert "TRIGGER:" in content
        assert "test_failure" in content
        assert "AttributeError" in content
        assert "LESSON:" in content
        assert "create_widget()" in content
        assert "SOLUTION:" in content
        assert "fix_code" in content

        # Verify lesson pool and metadata
        assert stored_metadata[0]["pool"] == "lessons"
        meta = stored_metadata[0]["metadata"]
        assert meta["bug_id"] == bug.id
        assert meta["feature_id"] == feature.id
        assert meta["error_type"] == "test_failure"

        # ---- Step 7: Verify titans_memory_id stored in bug_ledger ----
        final_bug = db.get_bug(bug.id)
        assert final_bug is not None
        assert final_bug.titans_memory_id == "mem-widget-lesson-e2e"
        assert final_bug.resolved is True
        assert final_bug.blame_target == "implementation"
        assert final_bug.fix_action == "fix_code"

        # Verify the RCA agent run is still queryable
        rca_runs = db.query_agent_runs(
            project_id=project.id,
            purpose="rca_analyst",
        )
        assert len(rca_runs) >= 1
        assert any(r.id == rca_spawn_result.agent_run.id for r in rca_runs)

        # Verify the full bug list contains our bug
        all_bugs = db.list_bugs(project_id=project.id)
        assert len(all_bugs) == 1
        assert all_bugs[0].id == bug.id
        assert all_bugs[0].titans_memory_id == "mem-widget-lesson-e2e"

    @pytest.mark.asyncio
    async def test_rca_workflow_with_infrastructure_blame(self, tmp_db):
        """Alternative workflow: RCA blames infrastructure, bug still tracked."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        project = db.create_project(
            name="infra-rca-project",
            workspace_path="/tmp/infra-rca-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="API Integration",
            status="executing",
        )
        task = db.create_task(
            feature_id=feature.id,
            project_id=project.id,
            type="validation",
            title="Run integration tests",
            task_class="test_writing",
        )

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="""```json
{
    "blame_target": "infrastructure",
    "recommended_action": "retry",
    "root_cause": "DNS resolution timeout during CI run"
}
```""")],
                model="m",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=2000,
                duration_api_ms=1500,
                is_error=False,
                num_turns=1,
                session_id="rca-infra",
                total_cost_usd=0.02,
                usage=None,
                result=None,
            )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            rca_result = await spawn_rca_agent(
                project_id=project.id,
                failure_evidence="ConnectionError: DNS resolution failed",
                error_type="connection_failure",
                error_message="ConnectionError: DNS timeout",
                target_type="task",
                target_id=task.id,
            )

        # RCA blames infrastructure
        run = db.get_agent_run(rca_result.agent_run.id)
        assert run.rca_blame_target == "infrastructure"
        assert run.rca_recommended_action == "retry"

        # Still create a bug to track it
        rca_parsed = {
            "blame_target": run.rca_blame_target,
            "recommended_action": run.rca_recommended_action,
            "root_cause": "DNS resolution timeout during CI run",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="connection_failure",
            error_message="ConnectionError: DNS timeout",
            rca_result=rca_parsed,
            evidence_artifacts=json.dumps(["ev-conn-001"]),
        )
        assert bug.blame_target == "infrastructure"
        assert bug.fix_action == "retry"

        # Resolve as transient
        resolved = db.resolve_bug(bug.id, fix_evidence="Retried successfully")
        assert resolved.resolved is True

        # Create lesson
        client = TitansMemoryClient(workspace="/tmp/test")

        async def fake_add(content, pool=None, metadata=None):
            return MemoryResult(
                success=True,
                data={"id": "mem-infra-lesson"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=fake_add):
            lesson = await client.create_lesson_from_bug(bug_id=bug.id)

        assert lesson.success is True
        assert db.get_bug(bug.id).titans_memory_id == "mem-infra-lesson"

    @pytest.mark.asyncio
    async def test_rca_workflow_lesson_failure_does_not_corrupt_bug(self, tmp_db):
        """If TITANS Memory is unavailable, the bug record remains intact."""
        project = db.create_project(
            name="lesson-fail-project",
            workspace_path="/tmp/lesson-fail-ws",
        )

        rca_result = {
            "blame_target": "implementation",
            "recommended_action": "fix_code",
            "root_cause": "Missing return statement",
        }
        bug = db.create_bug_from_rca(
            project_id=project.id,
            error_type="AssertionError",
            error_message="got None expected 42",
            rca_result=rca_result,
            evidence_artifacts=json.dumps(["ev-001"]),
        )
        db.resolve_bug(bug.id, fix_evidence="Added return statement")

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fail_add(content, pool=None, metadata=None):
            return MemoryResult(
                success=False,
                error="MCP server unavailable",
            )

        with patch.object(client, "add_memory", side_effect=fail_add):
            result = await client.create_lesson_from_bug(bug_id=bug.id)

        # Lesson creation failed
        assert result.success is False

        # Bug should remain intact and resolved, without titans_memory_id
        final_bug = db.get_bug(bug.id)
        assert final_bug.resolved is True
        assert final_bug.titans_memory_id is None
        assert final_bug.blame_target == "implementation"
        assert final_bug.fix_action == "fix_code"
