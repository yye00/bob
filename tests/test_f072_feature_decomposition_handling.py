"""Tests for F072: Orchestration loop feature decomposition handling.

Validates that:
- Step 1: Check if feature exceeds_size_limits
- Step 2: Spawn decomposer sub-agent
- Step 3: Create child features from decomposition
- Step 4: Link dependencies between children
- Step 5: Test: Oversized feature gets decomposed into 3 children with dependencies
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3.db import (
    add_feature_dependency,
    check_feature_size,
    create_child_feature,
    create_feature,
    create_project,
    get_child_features,
    get_feature,
    get_feature_dependencies,
    init_database,
    update_feature,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import (
    LoopTermination,
    OrchestrationLoop,
    handle_decomposition,
    parse_decomposition_result,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "test.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def project(tmp_db):
    """Create a test project."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        return create_project(
            name="test-project",
            workspace_path="/tmp/test-project",
            max_cost_usd=100.0,
        )


@pytest.fixture
def oversized_feature(tmp_db, project):
    """Create a feature that exceeds size limits."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        f = create_feature(
            project_id=project.id,
            name="Giant Feature",
            description="A feature that is too large to implement in one pass",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            estimated_lines_of_code=1000,
            estimated_files_touched=10,
            estimated_complexity=9,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        check_feature_size(f.id)
        return get_feature(f.id)


@pytest.fixture
def normal_feature(tmp_db, project):
    """Create a feature that does NOT exceed size limits."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        f = create_feature(
            project_id=project.id,
            name="Small Feature",
            description="A small, manageable feature",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            estimated_lines_of_code=100,
            estimated_files_touched=2,
            estimated_complexity=3,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        check_feature_size(f.id)
        return get_feature(f.id)


def _make_decomposition_spawn_result(children_json: str) -> SpawnResult:
    """Helper to create a SpawnResult with decomposition output."""
    result = ExecutionResult(
        text=children_json,
        is_error=False,
        error_message="",
        duration_ms=5000,
        num_turns=3,
        total_cost_usd=0.25,
    )
    agent_run = MagicMock()
    agent_run.id = str(uuid.uuid4())
    return SpawnResult(execution_result=result, agent_run=agent_run)


def _make_failed_spawn_result() -> SpawnResult:
    """Helper to create a failed SpawnResult."""
    result = ExecutionResult(
        text="",
        is_error=True,
        error_message="Decomposition failed",
        duration_ms=2000,
        num_turns=1,
        total_cost_usd=0.10,
    )
    agent_run = MagicMock()
    agent_run.id = str(uuid.uuid4())
    return SpawnResult(execution_result=result, agent_run=agent_run)


SAMPLE_DECOMPOSITION_JSON = json.dumps({
    "children": [
        {
            "name": "Database Schema Module",
            "description": "Implement the database schema and migrations",
            "acceptance_criteria": '["Create tables", "Add indexes"]',
            "priority": 10,
            "risk_category": "low",
        },
        {
            "name": "API Endpoints Module",
            "description": "Implement REST API endpoints",
            "acceptance_criteria": '["GET endpoint", "POST endpoint"]',
            "priority": 20,
            "risk_category": "medium",
        },
        {
            "name": "Frontend Integration Module",
            "description": "Connect frontend to backend APIs",
            "acceptance_criteria": '["API calls", "Error handling"]',
            "priority": 30,
            "risk_category": "medium",
        },
    ],
    "dependencies": [
        {"from": 1, "to": 0},
        {"from": 2, "to": 1},
    ],
})


# ============================================================
# Step 1: Check if feature exceeds_size_limits
# ============================================================


class TestCheckExceedsSizeLimits:
    """Test that the orchestration loop checks exceeds_size_limits."""

    def test_oversized_feature_has_flag_set(self, tmp_db, oversized_feature):
        """Oversized feature has exceeds_size_limits=True."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            assert oversized_feature.exceeds_size_limits is True

    def test_normal_feature_does_not_have_flag(self, tmp_db, normal_feature):
        """Normal feature has exceeds_size_limits=False."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            assert normal_feature.exceeds_size_limits is False

    @pytest.mark.asyncio
    async def test_oversized_feature_triggers_decomposition(
        self, tmp_db, project, oversized_feature
    ):
        """An oversized feature triggers decomposition instead of execution."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                await loop.execute_feature(oversized_feature)

            # Parent should be set to pending_decomposition or completed
            updated = get_feature(oversized_feature.id)
            assert updated is not None
            # Parent should be marked as pending_decomposition (it was decomposed)
            assert updated.status == "pending_decomposition"

    @pytest.mark.asyncio
    async def test_normal_feature_executes_normally(
        self, tmp_db, project, normal_feature
    ):
        """A normal feature is executed, not decomposed."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            success_result = SpawnResult(
                execution_result=ExecutionResult(
                    text="Feature implemented successfully",
                    is_error=False,
                    duration_ms=5000,
                    num_turns=10,
                    total_cost_usd=0.50,
                ),
                agent_run=MagicMock(id=str(uuid.uuid4())),
            )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=success_result,
            ):
                await loop.execute_feature(normal_feature)

            updated = get_feature(normal_feature.id)
            assert updated is not None
            assert updated.status == "completed"


# ============================================================
# Step 2: Spawn decomposer sub-agent
# ============================================================


class TestSpawnDecomposerAgent:
    """Test that a decomposer sub-agent is spawned for oversized features."""

    @pytest.mark.asyncio
    async def test_decomposer_agent_spawned(
        self, tmp_db, project, oversized_feature
    ):
        """A decomposer sub-agent is spawned for oversized features."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            spawn_mock = AsyncMock(return_value=mock_result)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                spawn_mock,
            ):
                result = await handle_decomposition(
                    project_id=project.id,
                    feature=oversized_feature,
                )

            # spawn_sub_agent should have been called
            assert spawn_mock.called
            call_kwargs = spawn_mock.call_args
            assert call_kwargs[1]["purpose"] == "decompose_feature"
            assert call_kwargs[1]["target_type"] == "feature"
            assert call_kwargs[1]["target_id"] == oversized_feature.id

    @pytest.mark.asyncio
    async def test_decomposer_prompt_includes_feature_info(
        self, tmp_db, project, oversized_feature
    ):
        """The decomposer prompt includes the feature name and description."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            spawn_mock = AsyncMock(return_value=mock_result)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                spawn_mock,
            ):
                await handle_decomposition(
                    project_id=project.id,
                    feature=oversized_feature,
                )

            prompt = spawn_mock.call_args[1]["prompt"]
            assert oversized_feature.name in prompt
            assert oversized_feature.description in prompt


# ============================================================
# Step 3: Create child features from decomposition
# ============================================================


class TestCreateChildFeatures:
    """Test that child features are created from decomposition results."""

    @pytest.mark.asyncio
    async def test_children_created(self, tmp_db, project, oversized_feature):
        """Child features are created from decomposition results."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                result = await handle_decomposition(
                    project_id=project.id,
                    feature=oversized_feature,
                )

            # Should have created 3 children
            children = get_child_features(oversized_feature.id)
            assert len(children) == 3

    @pytest.mark.asyncio
    async def test_children_have_correct_names(
        self, tmp_db, project, oversized_feature
    ):
        """Child features have the correct names from decomposition."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                await handle_decomposition(
                    project_id=project.id,
                    feature=oversized_feature,
                )

            children = get_child_features(oversized_feature.id)
            child_names = {c.name for c in children}
            assert "Database Schema Module" in child_names
            assert "API Endpoints Module" in child_names
            assert "Frontend Integration Module" in child_names

    @pytest.mark.asyncio
    async def test_children_inherit_project_id(
        self, tmp_db, project, oversized_feature
    ):
        """Child features inherit the project_id from the parent."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                await handle_decomposition(
                    project_id=project.id,
                    feature=oversized_feature,
                )

            children = get_child_features(oversized_feature.id)
            for child in children:
                assert child.project_id == project.id

    @pytest.mark.asyncio
    async def test_children_have_ready_status(
        self, tmp_db, project, oversized_feature
    ):
        """Child features are created with status='ready'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                await handle_decomposition(
                    project_id=project.id,
                    feature=oversized_feature,
                )

            children = get_child_features(oversized_feature.id)
            for child in children:
                assert child.status == "ready"

    @pytest.mark.asyncio
    async def test_children_have_decomposition_depth_1(
        self, tmp_db, project, oversized_feature
    ):
        """Child features have decomposition_depth=1."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                await handle_decomposition(
                    project_id=project.id,
                    feature=oversized_feature,
                )

            children = get_child_features(oversized_feature.id)
            for child in children:
                assert child.decomposition_depth == 1


# ============================================================
# Step 4: Link dependencies between children
# ============================================================


class TestLinkDependenciesBetweenChildren:
    """Test that dependencies are linked between child features."""

    @pytest.mark.asyncio
    async def test_dependencies_created(self, tmp_db, project, oversized_feature):
        """Dependencies are created between child features."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                await handle_decomposition(
                    project_id=project.id,
                    feature=oversized_feature,
                )

            children = get_child_features(oversized_feature.id)
            # Sort by priority to match order
            children.sort(key=lambda c: c.priority)

            # Child[1] ("API Endpoints") depends on child[0] ("Database Schema")
            deps_1 = get_feature_dependencies(children[1].id)
            dep_ids_1 = {d.depends_on_feature_id for d in deps_1}
            assert children[0].id in dep_ids_1

            # Child[2] ("Frontend Integration") depends on child[1] ("API Endpoints")
            deps_2 = get_feature_dependencies(children[2].id)
            dep_ids_2 = {d.depends_on_feature_id for d in deps_2}
            assert children[1].id in dep_ids_2


# ============================================================
# Step 5: Oversized feature gets decomposed into 3 children
#          with dependencies (end-to-end)
# ============================================================


class TestEndToEndDecomposition:
    """End-to-end test: oversized feature decomposed into 3 children."""

    @pytest.mark.asyncio
    async def test_full_decomposition_flow(
        self, tmp_db, project, oversized_feature
    ):
        """Full flow: oversized feature → decomposer → 3 children → dependencies."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                await loop.execute_feature(oversized_feature)

            # Parent should be pending_decomposition
            parent = get_feature(oversized_feature.id)
            assert parent.status == "pending_decomposition"

            # Should have 3 children
            children = get_child_features(oversized_feature.id)
            assert len(children) == 3

            # All children should have the correct parent
            for child in children:
                assert child.parent_feature_id == oversized_feature.id
                assert child.project_id == project.id
                assert child.decomposition_depth == 1

            # Dependencies should link children in order
            children.sort(key=lambda c: c.priority)

            deps_1 = get_feature_dependencies(children[1].id)
            assert any(d.depends_on_feature_id == children[0].id for d in deps_1)

            deps_2 = get_feature_dependencies(children[2].id)
            assert any(d.depends_on_feature_id == children[1].id for d in deps_2)

    @pytest.mark.asyncio
    async def test_decomposition_failure_falls_back(
        self, tmp_db, project, oversized_feature
    ):
        """If decomposition sub-agent fails, feature status is set to needs_human."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            failed_result = _make_failed_spawn_result()

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=failed_result,
            ):
                await loop.execute_feature(oversized_feature)

            # Feature should be set to needs_human since decomposition failed
            updated = get_feature(oversized_feature.id)
            assert updated.status == "needs_human"

    @pytest.mark.asyncio
    async def test_decomposition_tracks_cost(
        self, tmp_db, project, oversized_feature
    ):
        """Decomposition cost is tracked.

        R4-002 (2026-04, follow-up): the decomposition cost used to be
        added ONLY to ``loop.total_cost`` and never to
        ``project.total_cost_usd`` — so the project budget was blind to
        decomposition. Fix: route to ``db.update_project_cost`` (atomic,
        canonical source). The DB total is the right thing to assert on.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            mock_result = _make_decomposition_spawn_result(SAMPLE_DECOMPOSITION_JSON)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                await loop.execute_feature(oversized_feature)

            # Cost is tracked atomically in the DB total (R4-002 fix).
            from bob3.db import get_project
            updated_project = get_project(project.id)
            assert updated_project.total_cost_usd >= 0.25


# ============================================================
# parse_decomposition_result tests
# ============================================================


class TestParseDecompositionResult:
    """Test the parse_decomposition_result helper."""

    def test_parse_valid_json(self):
        """Parses valid JSON with children and dependencies."""
        result = parse_decomposition_result(SAMPLE_DECOMPOSITION_JSON)
        assert result is not None
        assert len(result["children"]) == 3
        assert len(result["dependencies"]) == 2

    def test_parse_fenced_json(self):
        """Parses JSON wrapped in ```json fences."""
        text = f"Here is the decomposition:\n```json\n{SAMPLE_DECOMPOSITION_JSON}\n```\nDone."
        result = parse_decomposition_result(text)
        assert result is not None
        assert len(result["children"]) == 3

    def test_parse_invalid_json_returns_none(self):
        """Returns None for invalid JSON."""
        result = parse_decomposition_result("This is not JSON at all")
        assert result is None

    def test_parse_missing_children_returns_none(self):
        """Returns None if 'children' key is missing."""
        result = parse_decomposition_result(json.dumps({"data": "no children"}))
        assert result is None

    def test_parse_empty_children_returns_none(self):
        """Returns None if 'children' is empty."""
        result = parse_decomposition_result(json.dumps({"children": []}))
        assert result is None


# ============================================================
# R9-006: Parent feature auto-completion when all children complete
# ============================================================


class TestParentAutoCompletionOnChildrenComplete:
    """R9-006: ``check_parent_completion`` exists in db.py to auto-
    complete a parent when all its children are done — but until this
    fix, nothing in run_loop.py called it. Decomposed parents stayed
    at ``pending_decomposition`` forever, blocking any sibling
    feature that depended on the parent.
    """

    @pytest.mark.asyncio
    async def test_parent_completes_when_all_children_complete(
        self, tmp_db, project
    ):
        """When the last child of a decomposed parent completes via
        the orchestration flow, the parent must transition to
        'completed'.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.orchestrator.run_loop import handle_execution_result
            from bob3.orchestrator.claude_executor import (
                ExecutionResult, SpawnResult,
            )

            # Build the parent (pending_decomposition) + 2 children.
            parent = create_feature(
                project_id=project.id,
                name="Parent",
                description="Decomposed parent",
                status="pending_decomposition",
                priority=10,
                risk_category="medium",
            )
            child_a = create_child_feature(
                parent_feature_id=parent.id,
                project_id=project.id,
                name="Child A",
                description="First child",
                status="ready",
                priority=10,
            )
            child_b = create_child_feature(
                parent_feature_id=parent.id,
                project_id=project.id,
                name="Child B",
                description="Second child",
                status="ready",
                priority=20,
            )

            def _spawn_result_for(cost_usd: float = 0.10) -> SpawnResult:
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="done",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=1,
                        total_cost_usd=cost_usd,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            # Complete child_a via the orchestration flow.
            child_a_obj = get_feature(child_a.id)
            handle_execution_result(
                project_id=project.id,
                feature=child_a_obj,
                spawn_result=_spawn_result_for(),
                verification_passed=True,
            )

            # Parent should still be pending_decomposition because
            # child_b is not done yet.
            assert get_feature(parent.id).status == "pending_decomposition"
            assert get_feature(child_a.id).status == "completed"

            # Now complete child_b — this should trigger parent
            # auto-completion.
            child_b_obj = get_feature(child_b.id)
            handle_execution_result(
                project_id=project.id,
                feature=child_b_obj,
                spawn_result=_spawn_result_for(),
                verification_passed=True,
            )

            # Parent must now be 'completed'.
            assert get_feature(child_b.id).status == "completed"
            assert get_feature(parent.id).status == "completed", (
                "parent feature must auto-complete once all children "
                "are completed; check_parent_completion must be called "
                "from the orchestration flow"
            )

    @pytest.mark.asyncio
    async def test_parent_completion_cascades_to_dependents(
        self, tmp_db, project
    ):
        """When parent auto-completes, features that depend on the
        parent must also transition from 'pending' to 'ready'.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.orchestrator.run_loop import handle_execution_result
            from bob3.orchestrator.claude_executor import (
                ExecutionResult, SpawnResult,
            )

            parent = create_feature(
                project_id=project.id,
                name="Parent",
                description="Decomposed parent",
                status="pending_decomposition",
                priority=10,
                risk_category="medium",
            )
            child_a = create_child_feature(
                parent_feature_id=parent.id,
                project_id=project.id,
                name="Child A",
                description="First child",
                status="ready",
                priority=10,
            )
            child_b = create_child_feature(
                parent_feature_id=parent.id,
                project_id=project.id,
                name="Child B",
                description="Second child",
                status="ready",
                priority=20,
            )
            # A sibling feature depending on the parent — initially
            # pending until parent completes.
            sibling_dependent = create_feature(
                project_id=project.id,
                name="Depends on parent",
                description="Sibling that depends on parent",
                status="pending",
                priority=30,
                risk_category="medium",
            )
            add_feature_dependency(
                feature_id=sibling_dependent.id,
                depends_on_feature_id=parent.id,
            )

            def _spawn() -> SpawnResult:
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="done",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=1,
                        total_cost_usd=0.10,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            # Complete both children.
            for child_id in (child_a.id, child_b.id):
                handle_execution_result(
                    project_id=project.id,
                    feature=get_feature(child_id),
                    spawn_result=_spawn(),
                    verification_passed=True,
                )

            assert get_feature(parent.id).status == "completed"
            # The cascade from parent-completion must have promoted
            # the sibling to 'ready'.
            assert get_feature(sibling_dependent.id).status == "ready", (
                "dependent of the auto-completed parent must cascade "
                "from 'pending' to 'ready'"
            )
