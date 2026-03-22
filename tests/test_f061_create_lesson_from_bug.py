"""Tests for F061: Create lesson from bug resolution (TITANS Memory).

Validates that:
- Step 1: create_lesson_from_bug() function exists on TitansMemoryClient
- Step 2: Extract trigger_context from bug (error_type, error_message, error_context)
- Step 3: Format lesson: trigger + error + solution
- Step 4: Call titans_add with pool='lessons' and metadata (bug_id, feature_id)
- Step 5: Store returned memory_id in bug_ledger.titans_memory_id
- Step 6: Integration: Resolve bug, create lesson in TITANS, verify searchable
"""

import json
import pathlib
from unittest.mock import patch

import pytest

from bob3 import db
from bob3.models import BugLedger

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


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
        name="F061 Test Project",
        workspace_path="/tmp/test-f061",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature within the project."""
    return db.create_feature(
        project_id=project.id,
        name="Test Feature for Lesson Creation",
        description="A feature whose bug resolution creates a lesson",
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


@pytest.fixture()
def resolved_bug(project, feature, task):
    """Create a resolved bug with full RCA fields."""
    bug = db.create_bug(
        project_id=project.id,
        feature_id=feature.id,
        task_id=task.id,
        error_type="AssertionError",
        error_message="expected 42 got None",
        error_context="FAILED tests/test_calc.py::test_sum",
        evidence_artifacts=json.dumps(["ev-trace-001", "ev-log-002"]),
        blame_target="implementation",
        root_cause="Missing return statement in calculate()",
        fix_action="fix_code",
        fix_details="Added return statement to calculate() function",
    )
    resolved = db.resolve_bug(bug.id, fix_evidence="All tests pass after fix")
    return resolved


@pytest.fixture()
def unresolved_bug(project, feature, task):
    """Create an unresolved bug."""
    return db.create_bug(
        project_id=project.id,
        feature_id=feature.id,
        task_id=task.id,
        error_type="TypeError",
        error_message="expected str got int",
        evidence_artifacts=json.dumps(["ev-001"]),
        fix_action="investigate",
    )


# ===================================================================
# Step 1: create_lesson_from_bug() function exists
# ===================================================================


class TestCreateLessonFromBugExists:
    """Step 1: create_lesson_from_bug() must exist on TitansMemoryClient."""

    def test_method_exists(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        assert hasattr(client, "create_lesson_from_bug")
        assert callable(client.create_lesson_from_bug)

    def test_method_is_async(self):
        import inspect

        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        assert inspect.iscoroutinefunction(client.create_lesson_from_bug)

    @pytest.mark.asyncio
    async def test_accepts_bug_id_parameter(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fake_add(content, pool=None, metadata=None):
            return MemoryResult(
                success=True,
                data={"id": "mem-lesson-001", "content": content},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=fake_add):
            result = await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_returns_memory_result(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fake_add(content, pool=None, metadata=None):
            return MemoryResult(
                success=True,
                data={"id": "mem-lesson-001", "content": content},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=fake_add):
            result = await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        assert isinstance(result, MemoryResult)


# ===================================================================
# Step 2: Extract trigger_context from bug
# ===================================================================


class TestExtractTriggerContext:
    """Step 2: Extracts trigger_context from bug error fields."""

    @pytest.mark.asyncio
    async def test_trigger_includes_error_type(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        content = add_memory_calls[0]
        assert "AssertionError" in content

    @pytest.mark.asyncio
    async def test_trigger_includes_error_message(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        content = add_memory_calls[0]
        assert "expected 42 got None" in content

    @pytest.mark.asyncio
    async def test_trigger_includes_error_context_when_present(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        content = add_memory_calls[0]
        assert "FAILED tests/test_calc.py::test_sum" in content

    @pytest.mark.asyncio
    async def test_trigger_without_error_context(self, project):
        """When error_context is None, trigger still works from error_type + message."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        bug = db.create_bug(
            project_id=project.id,
            error_type="ImportError",
            error_message="No module named 'foo'",
            evidence_artifacts=json.dumps(["ev-001"]),
            fix_action="install_dependency",
            root_cause="Missing dependency",
        )
        db.resolve_bug(bug.id, fix_evidence="Installed foo")

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=bug.id)

        content = add_memory_calls[0]
        assert "ImportError" in content
        assert "No module named 'foo'" in content


# ===================================================================
# Step 3: Format lesson: trigger + error + solution
# ===================================================================


class TestLessonFormat:
    """Step 3: Content formatted as TRIGGER + LESSON + SOLUTION."""

    @pytest.mark.asyncio
    async def test_content_has_trigger_section(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        content = add_memory_calls[0]
        assert "TRIGGER:" in content

    @pytest.mark.asyncio
    async def test_content_has_lesson_section(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        content = add_memory_calls[0]
        assert "LESSON:" in content

    @pytest.mark.asyncio
    async def test_content_has_solution_section(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        content = add_memory_calls[0]
        assert "SOLUTION:" in content

    @pytest.mark.asyncio
    async def test_lesson_includes_root_cause(self, resolved_bug):
        """The LESSON section should include the root_cause from the bug."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        content = add_memory_calls[0]
        assert "Missing return statement in calculate()" in content

    @pytest.mark.asyncio
    async def test_solution_includes_fix_action(self, resolved_bug):
        """The SOLUTION section should include the fix_action."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        content = add_memory_calls[0]
        assert "fix_code" in content

    @pytest.mark.asyncio
    async def test_content_sections_on_separate_lines(self, resolved_bug):
        """Each section should be on a separate line."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        content = add_memory_calls[0]
        lines = content.strip().split("\n")
        assert len(lines) == 3
        assert lines[0].startswith("TRIGGER:")
        assert lines[1].startswith("LESSON:")
        assert lines[2].startswith("SOLUTION:")


# ===================================================================
# Step 4: Call titans_add with pool='lessons' and metadata
# ===================================================================


class TestTitansAddCall:
    """Step 4: titans_add called with pool='lessons' and metadata (bug_id, feature_id)."""

    @pytest.mark.asyncio
    async def test_pool_is_lessons(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"pool": pool, "metadata": metadata})
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        assert add_memory_calls[0]["pool"] == "lessons"

    @pytest.mark.asyncio
    async def test_metadata_includes_bug_id(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        meta = add_memory_calls[0]["metadata"]
        assert meta is not None
        assert meta["bug_id"] == resolved_bug.id

    @pytest.mark.asyncio
    async def test_metadata_includes_feature_id(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        meta = add_memory_calls[0]["metadata"]
        assert meta is not None
        assert meta["feature_id"] == resolved_bug.feature_id

    @pytest.mark.asyncio
    async def test_metadata_includes_error_type(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        meta = add_memory_calls[0]["metadata"]
        assert meta is not None
        assert meta["error_type"] == "AssertionError"

    @pytest.mark.asyncio
    async def test_metadata_without_feature_id(self, project):
        """When bug has no feature_id, metadata should not include it."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        bug = db.create_bug(
            project_id=project.id,
            error_type="RuntimeError",
            error_message="crash",
            evidence_artifacts=json.dumps(["ev-001"]),
            fix_action="fix",
            root_cause="Bad code",
        )
        db.resolve_bug(bug.id, fix_evidence="Fixed")

        client = TitansMemoryClient(workspace="/tmp/test")
        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(
                success=True,
                data={"id": "mem-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture):
            await client.create_lesson_from_bug(bug_id=bug.id)

        meta = add_memory_calls[0]["metadata"]
        assert meta is not None
        assert "bug_id" in meta
        assert "feature_id" not in meta


# ===================================================================
# Step 5: Store returned memory_id in bug_ledger.titans_memory_id
# ===================================================================


class TestStoreMemoryIdInBugLedger:
    """Step 5: The memory_id from titans_add is stored in bug_ledger.titans_memory_id."""

    @pytest.mark.asyncio
    async def test_titans_memory_id_stored_on_success(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fake_add(content, pool=None, metadata=None):
            return MemoryResult(
                success=True,
                data={"id": "mem-lesson-xyz"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=fake_add):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        # Fetch the bug from DB and check titans_memory_id was updated
        updated_bug = db.get_bug(resolved_bug.id)
        assert updated_bug.titans_memory_id == "mem-lesson-xyz"

    @pytest.mark.asyncio
    async def test_titans_memory_id_not_stored_on_failure(self, resolved_bug):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fail_add(content, pool=None, metadata=None):
            return MemoryResult(
                success=False,
                error="MCP server unavailable",
            )

        with patch.object(client, "add_memory", side_effect=fail_add):
            result = await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        assert result.success is False
        # Bug should not have titans_memory_id updated
        updated_bug = db.get_bug(resolved_bug.id)
        assert updated_bug.titans_memory_id is None

    @pytest.mark.asyncio
    async def test_extracts_memory_id_from_dict_data(self, resolved_bug):
        """When data is a dict with 'id' key, extract memory_id from it."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fake_add(content, pool=None, metadata=None):
            return MemoryResult(
                success=True,
                data={"id": "mem-dict-id", "content": "stored"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=fake_add):
            await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        updated_bug = db.get_bug(resolved_bug.id)
        assert updated_bug.titans_memory_id == "mem-dict-id"

    @pytest.mark.asyncio
    async def test_bug_not_found_returns_error(self):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        result = await client.create_lesson_from_bug(bug_id="nonexistent-bug-id")

        assert result.success is False
        assert "not found" in result.error.lower()


# ===================================================================
# Step 6: Integration: resolve bug, create lesson, verify searchable
# ===================================================================


class TestFullIntegration:
    """Step 6: Full lifecycle - resolve bug, create lesson in TITANS, verify."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, project, feature, task):
        """Create bug -> resolve -> create lesson -> verify lesson content + DB update."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        # Create and resolve a bug
        bug = db.create_bug(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            error_type="test_failure",
            error_message="AttributeError: 'NoneType' has no attribute 'upper'",
            error_context="FAILED tests/test_widgets.py::test_create_widget",
            evidence_artifacts=json.dumps(["ev-trace-001", "ev-log-002"]),
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
                data={"id": "mem-widget-lesson-001", "content": content},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture_add):
            result = await client.create_lesson_from_bug(bug_id=bug.id)

        # Verify result
        assert result.success is True
        assert result.data["id"] == "mem-widget-lesson-001"

        # Verify content formatting
        content = stored_content[0]
        assert "TRIGGER:" in content
        assert "test_failure" in content
        assert "'NoneType' has no attribute 'upper'" in content
        assert "LESSON:" in content
        assert "create_widget() does not handle None widget_type" in content
        assert "SOLUTION:" in content
        assert "fix_code" in content

        # Verify pool
        assert stored_metadata[0]["pool"] == "lessons"

        # Verify metadata
        meta = stored_metadata[0]["metadata"]
        assert meta["bug_id"] == bug.id
        assert meta["feature_id"] == feature.id
        assert meta["error_type"] == "test_failure"

        # Verify DB was updated with titans_memory_id
        updated_bug = db.get_bug(bug.id)
        assert updated_bug.titans_memory_id == "mem-widget-lesson-001"

    @pytest.mark.asyncio
    async def test_lesson_from_bug_without_root_cause(self, project):
        """Lesson creation works even without a root_cause."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        bug = db.create_bug(
            project_id=project.id,
            error_type="Error",
            error_message="something broke",
            evidence_artifacts=json.dumps(["ev-001"]),
            fix_action="investigate",
        )
        db.resolve_bug(bug.id, fix_evidence="Investigated and fixed")

        client = TitansMemoryClient(workspace="/tmp/test")
        stored_content = []

        async def capture_add(content, pool=None, metadata=None):
            stored_content.append(content)
            return MemoryResult(
                success=True,
                data={"id": "mem-no-root-001"},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture_add):
            result = await client.create_lesson_from_bug(bug_id=bug.id)

        assert result.success is True
        content = stored_content[0]
        assert "TRIGGER:" in content
        assert "LESSON:" in content
        assert "SOLUTION:" in content

    @pytest.mark.asyncio
    async def test_lesson_failure_does_not_corrupt_bug(self, resolved_bug):
        """If TITANS fails, the bug record remains unchanged."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        original_bug = db.get_bug(resolved_bug.id)
        assert original_bug.titans_memory_id is None

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fail_add(content, pool=None, metadata=None):
            return MemoryResult(
                success=False,
                error="Connection refused",
            )

        with patch.object(client, "add_memory", side_effect=fail_add):
            result = await client.create_lesson_from_bug(bug_id=resolved_bug.id)

        assert result.success is False
        # Bug should remain unchanged
        unchanged_bug = db.get_bug(resolved_bug.id)
        assert unchanged_bug.titans_memory_id is None
        assert unchanged_bug.resolved is True
