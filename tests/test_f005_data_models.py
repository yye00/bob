"""Tests for F005: Create models.py with Pydantic data models for all entities."""

import json
import pathlib
import sqlite3
from datetime import datetime

import pytest
from pydantic import ValidationError

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_PATH = WORKSPACE / "src" / "bob3" / "schema.sql"


# ============================================================
# Step 1: models.py file exists and is importable
# ============================================================


class TestModelsFileExists:
    """Step 1: Create src/bob3/models.py file."""

    def test_models_file_exists(self):
        models_path = WORKSPACE / "src" / "bob3" / "models.py"
        assert models_path.exists(), "src/bob3/models.py must exist"

    def test_models_module_importable(self):
        import bob3.models  # noqa: F401

    def test_models_uses_pydantic(self):
        import bob3.models
        import inspect

        source = inspect.getsource(bob3.models)
        assert "pydantic" in source.lower(), "models.py must use pydantic"


# ============================================================
# Step 2: Project model
# ============================================================


class TestProjectModel:
    """Step 2: Define Project model with all fields from schema."""

    def test_project_model_exists(self):
        from bob3.models import Project

        assert Project is not None

    def test_project_required_fields(self):
        from bob3.models import Project

        p = Project(id="proj-1", name="Test", workspace_path="/tmp/test")
        assert p.id == "proj-1"
        assert p.name == "Test"
        assert p.workspace_path == "/tmp/test"

    def test_project_optional_fields_have_defaults(self):
        from bob3.models import Project

        p = Project(id="proj-1", name="Test", workspace_path="/tmp/test")
        assert p.description is None
        assert p.spec_path is None
        assert p.status == "planning"
        assert p.total_cost_usd == 0.0
        assert p.max_cost_usd == 500.0
        assert p.spec_hash is None
        assert p.spec_last_modified is None
        assert p.environment_fingerprint is None

    def test_project_all_schema_fields_present(self):
        from bob3.models import Project

        expected_fields = {
            "id",
            "name",
            "description",
            "spec_path",
            "workspace_path",
            "status",
            "total_cost_usd",
            "max_cost_usd",
            "spec_hash",
            "spec_last_modified",
            "environment_fingerprint",
            "created_at",
            "updated_at",
        }
        actual_fields = set(Project.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"Project model is missing fields: {missing}"

    def test_project_name_required(self):
        from bob3.models import Project

        with pytest.raises(ValidationError):
            Project(id="proj-1", workspace_path="/tmp/test")

    def test_project_workspace_path_required(self):
        from bob3.models import Project

        with pytest.raises(ValidationError):
            Project(id="proj-1", name="Test")

    def test_project_timestamps_default_to_now(self):
        from bob3.models import Project

        p = Project(id="proj-1", name="Test", workspace_path="/tmp/test")
        assert p.created_at is not None
        assert p.updated_at is not None
        assert isinstance(p.created_at, datetime)


# ============================================================
# Step 3: Feature model
# ============================================================


class TestFeatureModel:
    """Step 3: Define Feature model with all fields from schema."""

    def test_feature_model_exists(self):
        from bob3.models import Feature

        assert Feature is not None

    def test_feature_required_fields(self):
        from bob3.models import Feature

        f = Feature(id="f-1", project_id="proj-1", name="My Feature")
        assert f.id == "f-1"
        assert f.project_id == "proj-1"
        assert f.name == "My Feature"

    def test_feature_optional_fields_have_defaults(self):
        from bob3.models import Feature

        f = Feature(id="f-1", project_id="proj-1", name="My Feature")
        assert f.parent_feature_id is None
        assert f.decomposition_depth == 0
        assert f.description is None
        assert f.acceptance_criteria is None
        assert f.status == "pending"
        assert f.priority == 100
        assert f.risk_category == "medium"
        assert f.conf_spec_understanding == 0.0
        assert f.conf_impl_correctness == 0.0
        assert f.conf_test_adequacy == 0.0
        assert f.readiness_score == 0.0
        assert f.readiness_components is None
        assert f.refinement_attempts == 0
        assert f.max_refinement_attempts == 5
        assert f.last_improvement_type is None
        assert f.research_iterations == 0
        assert f.exceeds_size_limits is False
        assert f.completion_mode == "all_or_nothing"
        assert f.tasks_completed == 0
        assert f.tasks_total == 0

    def test_feature_all_schema_fields_present(self):
        from bob3.models import Feature

        expected_fields = {
            "id",
            "project_id",
            "parent_feature_id",
            "decomposition_depth",
            "name",
            "description",
            "acceptance_criteria",
            "status",
            "priority",
            "risk_category",
            "conf_spec_understanding",
            "conf_impl_correctness",
            "conf_test_adequacy",
            "readiness_score",
            "readiness_components",
            "refinement_attempts",
            "max_refinement_attempts",
            "last_improvement_type",
            "research_iterations",
            "original_acceptance_criteria_count",
            "original_task_count",
            "estimated_lines_of_code",
            "estimated_files_touched",
            "estimated_complexity",
            "exceeds_size_limits",
            "size_limit_justification",
            "reviewer_confidence_cap",
            "completion_mode",
            "tasks_completed",
            "tasks_total",
            "created_at",
            "updated_at",
        }
        actual_fields = set(Feature.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"Feature model is missing fields: {missing}"

    def test_feature_acceptance_criteria_as_json(self):
        from bob3.models import Feature

        criteria = ["Step 1: Create file", "Step 2: Test it"]
        f = Feature(
            id="f-1",
            project_id="proj-1",
            name="My Feature",
            acceptance_criteria=json.dumps(criteria),
        )
        parsed = json.loads(f.acceptance_criteria)
        assert parsed == criteria


# ============================================================
# Step 4: Task model
# ============================================================


class TestTaskModel:
    """Step 4: Define Task model with all fields from schema."""

    def test_task_model_exists(self):
        from bob3.models import Task

        assert Task is not None

    def test_task_required_fields(self):
        from bob3.models import Task

        t = Task(
            id="t-1",
            feature_id="f-1",
            project_id="proj-1",
            type="implementation",
            title="Implement feature",
        )
        assert t.id == "t-1"
        assert t.feature_id == "f-1"
        assert t.project_id == "proj-1"
        assert t.type == "implementation"
        assert t.title == "Implement feature"

    def test_task_optional_fields_have_defaults(self):
        from bob3.models import Task

        t = Task(
            id="t-1",
            feature_id="f-1",
            project_id="proj-1",
            type="implementation",
            title="Implement feature",
        )
        assert t.subtype is None
        assert t.task_class is None
        assert t.description is None
        assert t.acceptance_criteria is None
        assert t.expected_outputs is None
        assert t.verify_script is None
        assert t.status == "pending"
        assert t.conf_spec_understanding == 0.0
        assert t.conf_impl_correctness == 0.0
        assert t.conf_test_adequacy == 0.0
        assert t.readiness_score == 0.0
        assert t.attempts == 0
        assert t.max_attempts == 5
        assert t.is_human_authored is False
        assert t.is_flaky is False

    def test_task_all_schema_fields_present(self):
        from bob3.models import Task

        expected_fields = {
            "id",
            "feature_id",
            "project_id",
            "type",
            "subtype",
            "task_class",
            "title",
            "description",
            "acceptance_criteria",
            "expected_outputs",
            "verify_script",
            "status",
            "conf_spec_understanding",
            "conf_impl_correctness",
            "conf_test_adequacy",
            "readiness_score",
            "attempts",
            "max_attempts",
            "is_human_authored",
            "original_assertion_count",
            "current_assertion_count",
            "original_coverage_percent",
            "current_coverage_percent",
            "is_flaky",
            "flaky_pass_rate",
            "created_at",
            "updated_at",
        }
        actual_fields = set(Task.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"Task model is missing fields: {missing}"

    def test_task_type_required(self):
        from bob3.models import Task

        with pytest.raises(ValidationError):
            Task(id="t-1", feature_id="f-1", project_id="proj-1", title="Test")

    def test_task_title_required(self):
        from bob3.models import Task

        with pytest.raises(ValidationError):
            Task(
                id="t-1",
                feature_id="f-1",
                project_id="proj-1",
                type="implementation",
            )


# ============================================================
# Step 5: Additional models
# ============================================================


class TestEvidenceArtifactModel:
    """Step 5a: EvidenceArtifact model."""

    def test_model_exists(self):
        from bob3.models import EvidenceArtifact

        assert EvidenceArtifact is not None

    def test_required_fields(self):
        from bob3.models import EvidenceArtifact

        ea = EvidenceArtifact(
            id="ea-1", project_id="proj-1", type="test_output", content="{}"
        )
        assert ea.id == "ea-1"
        assert ea.project_id == "proj-1"
        assert ea.type == "test_output"
        assert ea.content == "{}"

    def test_all_schema_fields_present(self):
        from bob3.models import EvidenceArtifact

        expected_fields = {
            "id",
            "project_id",
            "feature_id",
            "task_id",
            "attempt_number",
            "type",
            "content",
            "output_hash",
            "reproducible",
            "verification_run_at",
            "verification_passed",
            "is_current",
            "iteration_created",
            "environment_fingerprint",
            "environment_matches_current",
            "created_at",
        }
        actual_fields = set(EvidenceArtifact.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"EvidenceArtifact missing fields: {missing}"


class TestReviewHistoryModel:
    """Step 5b: ReviewHistory model."""

    def test_model_exists(self):
        from bob3.models import ReviewHistory

        assert ReviewHistory is not None

    def test_required_fields(self):
        from bob3.models import ReviewHistory

        rh = ReviewHistory(
            id="rh-1", project_id="proj-1", feature_id="f-1", reviewer_id="rev-1"
        )
        assert rh.id == "rh-1"
        assert rh.reviewer_id == "rev-1"

    def test_all_schema_fields_present(self):
        from bob3.models import ReviewHistory

        expected_fields = {
            "id",
            "project_id",
            "feature_id",
            "reviewer_id",
            "reviewer_type",
            "reviewer_seniority",
            "verdict",
            "confidence_cap",
            "veto_active",
            "issues_flagged",
            "required_validations",
            "notes",
            "issues_resolved",
            "resolved_at",
            "review_requested_at",
            "review_timeout_hours",
            "timeout_action_taken",
            "created_at",
        }
        actual_fields = set(ReviewHistory.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"ReviewHistory missing fields: {missing}"


class TestFeatureReviewIssueModel:
    """Step 5c: FeatureReviewIssue model."""

    def test_model_exists(self):
        from bob3.models import FeatureReviewIssue

        assert FeatureReviewIssue is not None

    def test_required_fields(self):
        from bob3.models import FeatureReviewIssue

        fri = FeatureReviewIssue(
            id="fri-1",
            feature_id="f-1",
            review_id="rh-1",
            issue_description="Missing test",
        )
        assert fri.id == "fri-1"
        assert fri.issue_description == "Missing test"

    def test_all_schema_fields_present(self):
        from bob3.models import FeatureReviewIssue

        expected_fields = {
            "id",
            "feature_id",
            "review_id",
            "issue_description",
            "severity",
            "resolved",
            "resolved_by_attempt",
            "resolution_evidence",
            "created_at",
            "resolved_at",
        }
        actual_fields = set(FeatureReviewIssue.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"FeatureReviewIssue missing fields: {missing}"


class TestBugLedgerModel:
    """Step 5d: BugLedger model."""

    def test_model_exists(self):
        from bob3.models import BugLedger

        assert BugLedger is not None

    def test_required_fields(self):
        from bob3.models import BugLedger

        bl = BugLedger(
            id="bl-1",
            project_id="proj-1",
            error_type="TypeError",
            error_message="NoneType has no attribute x",
            evidence_artifacts="[]",
            fix_action="Added null check",
        )
        assert bl.id == "bl-1"
        assert bl.error_type == "TypeError"

    def test_all_schema_fields_present(self):
        from bob3.models import BugLedger

        expected_fields = {
            "id",
            "project_id",
            "feature_id",
            "task_id",
            "error_type",
            "error_message",
            "error_context",
            "evidence_artifacts",
            "blame_target",
            "root_cause",
            "fix_action",
            "fix_details",
            "fix_evidence",
            "resolved",
            "resolution_attempts",
            "titans_memory_id",
            "created_at",
            "resolved_at",
        }
        actual_fields = set(BugLedger.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"BugLedger missing fields: {missing}"


class TestCalibrationDataModel:
    """Step 5e: CalibrationData model."""

    def test_model_exists(self):
        from bob3.models import CalibrationData

        assert CalibrationData is not None

    def test_required_fields(self):
        from bob3.models import CalibrationData

        cd = CalibrationData(
            id="cd-1", task_class="greenfield_impl", confidence_bucket="0.7-0.8"
        )
        assert cd.id == "cd-1"
        assert cd.task_class == "greenfield_impl"

    def test_all_schema_fields_present(self):
        from bob3.models import CalibrationData

        expected_fields = {
            "id",
            "project_id",
            "task_class",
            "confidence_bucket",
            "total_attempts",
            "total_passes",
            "total_failures",
            "empirical_pass_rate",
            "expected_pass_rate",
            "drift",
            "adjusted_threshold",
            "last_updated",
        }
        actual_fields = set(CalibrationData.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"CalibrationData missing fields: {missing}"


class TestCalibrationAlertModel:
    """Step 5f: CalibrationAlert model."""

    def test_model_exists(self):
        from bob3.models import CalibrationAlert

        assert CalibrationAlert is not None

    def test_all_schema_fields_present(self):
        from bob3.models import CalibrationAlert

        expected_fields = {
            "id",
            "project_id",
            "task_class",
            "confidence_bucket",
            "drift_amount",
            "direction",
            "sample_size",
            "acknowledged",
            "action_taken",
            "created_at",
        }
        actual_fields = set(CalibrationAlert.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"CalibrationAlert missing fields: {missing}"


class TestRegressionEventModel:
    """Step 5g: RegressionEvent model."""

    def test_model_exists(self):
        from bob3.models import RegressionEvent

        assert RegressionEvent is not None

    def test_all_schema_fields_present(self):
        from bob3.models import RegressionEvent

        expected_fields = {
            "id",
            "project_id",
            "affected_feature_id",
            "causing_feature_id",
            "detected_at",
            "affected_tests",
            "evidence_artifacts",
            "status",
            "resolution",
            "resolved_at",
        }
        actual_fields = set(RegressionEvent.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"RegressionEvent missing fields: {missing}"


class TestRollbackEventModel:
    """Step 5h: RollbackEvent model."""

    def test_model_exists(self):
        from bob3.models import RollbackEvent

        assert RollbackEvent is not None

    def test_all_schema_fields_present(self):
        from bob3.models import RollbackEvent

        expected_fields = {
            "id",
            "project_id",
            "feature_id",
            "trigger",
            "regression_event_id",
            "commit_before",
            "commit_after",
            "rollback_commit",
            "artifacts_preserved",
            "titans_memory_id",
            "created_at",
        }
        actual_fields = set(RollbackEvent.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"RollbackEvent missing fields: {missing}"


class TestResourceCheckpointModel:
    """Step 5i: ResourceCheckpoint model."""

    def test_model_exists(self):
        from bob3.models import ResourceCheckpoint

        assert ResourceCheckpoint is not None

    def test_all_schema_fields_present(self):
        from bob3.models import ResourceCheckpoint

        expected_fields = {
            "id",
            "project_id",
            "feature_id",
            "task_id",
            "checkpoint_type",
            "state_snapshot",
            "files_snapshot",
            "cost_at_checkpoint",
            "duration_at_checkpoint_ms",
            "can_resume",
            "resumed_at",
            "created_at",
        }
        actual_fields = set(ResourceCheckpoint.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"ResourceCheckpoint missing fields: {missing}"


class TestFlakyTestRunModel:
    """Step 5j: FlakyTestRun model."""

    def test_model_exists(self):
        from bob3.models import FlakyTestRun

        assert FlakyTestRun is not None

    def test_all_schema_fields_present(self):
        from bob3.models import FlakyTestRun

        expected_fields = {
            "id",
            "task_id",
            "run_number",
            "passed",
            "output",
            "duration_ms",
            "created_at",
        }
        actual_fields = set(FlakyTestRun.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"FlakyTestRun missing fields: {missing}"


class TestSubAgentRunModel:
    """Step 5k: SubAgentRun model."""

    def test_model_exists(self):
        from bob3.models import SubAgentRun

        assert SubAgentRun is not None

    def test_all_schema_fields_present(self):
        from bob3.models import SubAgentRun

        expected_fields = {
            "id",
            "project_id",
            "parent_run_id",
            "purpose",
            "target_type",
            "target_id",
            "status",
            "prompt_summary",
            "result_summary",
            "rca_blame_target",
            "rca_recommended_action",
            "evidence_artifacts_produced",
            "improvement_type",
            "improvement_evidence",
            "tokens_in",
            "tokens_out",
            "cost_usd",
            "duration_ms",
            "mcp_enabled",
            "created_at",
            "completed_at",
        }
        actual_fields = set(SubAgentRun.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"SubAgentRun missing fields: {missing}"


class TestConfidenceHistoryModel:
    """Step 5l: ConfidenceHistory model."""

    def test_model_exists(self):
        from bob3.models import ConfidenceHistory

        assert ConfidenceHistory is not None

    def test_all_schema_fields_present(self):
        from bob3.models import ConfidenceHistory

        expected_fields = {
            "id",
            "project_id",
            "feature_id",
            "task_id",
            "conf_spec_understanding",
            "conf_impl_correctness",
            "conf_test_adequacy",
            "rated_by",
            "rationale",
            "created_at",
        }
        actual_fields = set(ConfidenceHistory.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"ConfidenceHistory missing fields: {missing}"


class TestReadinessHistoryModel:
    """Step 5m: ReadinessHistory model."""

    def test_model_exists(self):
        from bob3.models import ReadinessHistory

        assert ReadinessHistory is not None

    def test_all_schema_fields_present(self):
        from bob3.models import ReadinessHistory

        expected_fields = {
            "id",
            "project_id",
            "feature_id",
            "readiness_score",
            "opus_confidence_component",
            "test_pass_rate_component",
            "evidence_score_component",
            "diff_quality_component",
            "reviewer_adjustment_component",
            "change_reason",
            "rules_applied",
            "computed_by",
            "created_at",
        }
        actual_fields = set(ReadinessHistory.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"ReadinessHistory missing fields: {missing}"


class TestScopeChangeModel:
    """Step 5n: ScopeChange model."""

    def test_model_exists(self):
        from bob3.models import ScopeChange

        assert ScopeChange is not None

    def test_all_schema_fields_present(self):
        from bob3.models import ScopeChange

        expected_fields = {
            "id",
            "feature_id",
            "change_type",
            "before_value",
            "after_value",
            "growth_percent",
            "requires_approval",
            "approved_by",
            "approved_at",
            "created_at",
        }
        actual_fields = set(ScopeChange.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"ScopeChange missing fields: {missing}"


class TestForgettingEventModel:
    """Step 5o: ForgettingEvent model."""

    def test_model_exists(self):
        from bob3.models import ForgettingEvent

        assert ForgettingEvent is not None

    def test_all_schema_fields_present(self):
        from bob3.models import ForgettingEvent

        expected_fields = {
            "id",
            "project_id",
            "target_type",
            "target_id",
            "action",
            "reason",
            "previous_status",
            "previous_usefulness_score",
            "previous_retrieval_weight",
            "backup_path",
            "backup_content",
            "triggered_by",
            "approved_by",
            "can_restore",
            "restored_at",
            "created_at",
        }
        actual_fields = set(ForgettingEvent.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"ForgettingEvent missing fields: {missing}"


class TestExecutionLogModel:
    """Step 5p: ExecutionLog model."""

    def test_model_exists(self):
        from bob3.models import ExecutionLog

        assert ExecutionLog is not None

    def test_all_schema_fields_present(self):
        from bob3.models import ExecutionLog

        expected_fields = {
            "id",
            "project_id",
            "sub_agent_run_id",
            "level",
            "event",
            "details",
            "created_at",
        }
        actual_fields = set(ExecutionLog.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"ExecutionLog missing fields: {missing}"


class TestDependencyModels:
    """Step 5q: FeatureDependency and TaskDependency models."""

    def test_feature_dependency_exists(self):
        from bob3.models import FeatureDependency

        assert FeatureDependency is not None

    def test_feature_dependency_fields(self):
        from bob3.models import FeatureDependency

        expected_fields = {
            "feature_id",
            "depends_on_feature_id",
            "invalidated_at",
            "invalidation_reason",
        }
        actual_fields = set(FeatureDependency.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"FeatureDependency missing fields: {missing}"

    def test_task_dependency_exists(self):
        from bob3.models import TaskDependency

        assert TaskDependency is not None

    def test_task_dependency_fields(self):
        from bob3.models import TaskDependency

        expected_fields = {"task_id", "depends_on_task_id"}
        actual_fields = set(TaskDependency.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"TaskDependency missing fields: {missing}"


class TestBob3SpecificModels:
    """Step 5r: Bob3-specific models (ResearchResult, ReferenceDocument, FeatureReference)."""

    def test_research_result_exists(self):
        from bob3.models import ResearchResult

        assert ResearchResult is not None

    def test_research_result_fields(self):
        from bob3.models import ResearchResult

        expected_fields = {
            "id",
            "feature_id",
            "project_id",
            "agent_run_id",
            "query",
            "findings",
            "sources",
            "code_examples",
            "applied",
            "created_at",
        }
        actual_fields = set(ResearchResult.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"ResearchResult missing fields: {missing}"

    def test_reference_document_exists(self):
        from bob3.models import ReferenceDocument

        assert ReferenceDocument is not None

    def test_reference_document_fields(self):
        from bob3.models import ReferenceDocument

        expected_fields = {
            "id",
            "project_id",
            "file_path",
            "title",
            "extracted_text",
            "page_count",
            "sections",
            "created_at",
        }
        actual_fields = set(ReferenceDocument.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"ReferenceDocument missing fields: {missing}"

    def test_feature_reference_exists(self):
        from bob3.models import FeatureReference

        assert FeatureReference is not None

    def test_feature_reference_fields(self):
        from bob3.models import FeatureReference

        expected_fields = {"feature_id", "reference_id", "section_hint"}
        actual_fields = set(FeatureReference.model_fields.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"FeatureReference missing fields: {missing}"


# ============================================================
# Step 6: Validation and type hints
# ============================================================


class TestValidationAndTypes:
    """Step 6: Add validation and type hints."""

    def test_project_cost_must_be_non_negative(self):
        from bob3.models import Project

        with pytest.raises(ValidationError):
            Project(
                id="p-1",
                name="Test",
                workspace_path="/tmp",
                total_cost_usd=-1.0,
            )

    def test_feature_confidence_clamped_0_to_1(self):
        from bob3.models import Feature

        with pytest.raises(ValidationError):
            Feature(
                id="f-1",
                project_id="p-1",
                name="Test",
                conf_spec_understanding=1.5,
            )

    def test_feature_confidence_rejects_negative(self):
        from bob3.models import Feature

        with pytest.raises(ValidationError):
            Feature(
                id="f-1",
                project_id="p-1",
                name="Test",
                conf_spec_understanding=-0.1,
            )

    def test_task_confidence_clamped_0_to_1(self):
        from bob3.models import Task

        with pytest.raises(ValidationError):
            Task(
                id="t-1",
                feature_id="f-1",
                project_id="p-1",
                type="implementation",
                title="Test",
                conf_impl_correctness=2.0,
            )

    def test_feature_priority_positive(self):
        from bob3.models import Feature

        with pytest.raises(ValidationError):
            Feature(
                id="f-1",
                project_id="p-1",
                name="Test",
                priority=-1,
            )

    def test_calibration_alert_direction_validated(self):
        from bob3.models import CalibrationAlert

        ca = CalibrationAlert(
            id="ca-1",
            task_class="greenfield_impl",
            confidence_bucket="0.7-0.8",
            drift_amount=0.2,
            direction="overconfident",
            sample_size=20,
        )
        assert ca.direction == "overconfident"

    def test_model_serialization_to_dict(self):
        from bob3.models import Project

        p = Project(id="proj-1", name="Test", workspace_path="/tmp/test")
        d = p.model_dump()
        assert isinstance(d, dict)
        assert d["id"] == "proj-1"
        assert d["name"] == "Test"

    def test_model_serialization_to_json(self):
        from bob3.models import Project

        p = Project(id="proj-1", name="Test", workspace_path="/tmp/test")
        j = p.model_dump_json()
        parsed = json.loads(j)
        assert parsed["id"] == "proj-1"


# ============================================================
# Step 7: Verify all models match database schema
# ============================================================


class TestModelsMatchSchema:
    """Step 7: Verify all models match database schema."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(self.db_path))
        schema_sql = SCHEMA_PATH.read_text()
        conn.executescript(schema_sql)
        self.conn = conn
        yield
        conn.close()

    def _get_table_columns(self, table_name: str) -> set[str]:
        cursor = self.conn.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}

    def test_project_matches_schema(self):
        from bob3.models import Project

        db_cols = self._get_table_columns("projects")
        model_fields = set(Project.model_fields.keys())
        missing_in_model = db_cols - model_fields
        assert not missing_in_model, f"Project model missing DB columns: {missing_in_model}"

    def test_feature_matches_schema(self):
        from bob3.models import Feature

        db_cols = self._get_table_columns("features")
        model_fields = set(Feature.model_fields.keys())
        missing_in_model = db_cols - model_fields
        assert not missing_in_model, f"Feature model missing DB columns: {missing_in_model}"

    def test_task_matches_schema(self):
        from bob3.models import Task

        db_cols = self._get_table_columns("tasks")
        model_fields = set(Task.model_fields.keys())
        missing_in_model = db_cols - model_fields
        assert not missing_in_model, f"Task model missing DB columns: {missing_in_model}"

    def test_evidence_artifact_matches_schema(self):
        from bob3.models import EvidenceArtifact

        db_cols = self._get_table_columns("evidence_artifacts")
        model_fields = set(EvidenceArtifact.model_fields.keys())
        missing_in_model = db_cols - model_fields
        assert not missing_in_model, f"EvidenceArtifact missing DB columns: {missing_in_model}"

    def test_review_history_matches_schema(self):
        from bob3.models import ReviewHistory

        db_cols = self._get_table_columns("review_history")
        model_fields = set(ReviewHistory.model_fields.keys())
        missing_in_model = db_cols - model_fields
        assert not missing_in_model, f"ReviewHistory missing DB columns: {missing_in_model}"

    def test_bug_ledger_matches_schema(self):
        from bob3.models import BugLedger

        db_cols = self._get_table_columns("bug_ledger")
        model_fields = set(BugLedger.model_fields.keys())
        missing_in_model = db_cols - model_fields
        assert not missing_in_model, f"BugLedger missing DB columns: {missing_in_model}"

    def test_sub_agent_run_matches_schema(self):
        from bob3.models import SubAgentRun

        db_cols = self._get_table_columns("sub_agent_runs")
        model_fields = set(SubAgentRun.model_fields.keys())
        missing_in_model = db_cols - model_fields
        assert not missing_in_model, f"SubAgentRun missing DB columns: {missing_in_model}"

    def test_research_result_matches_schema(self):
        from bob3.models import ResearchResult

        db_cols = self._get_table_columns("research_results")
        model_fields = set(ResearchResult.model_fields.keys())
        missing_in_model = db_cols - model_fields
        assert not missing_in_model, f"ResearchResult missing DB columns: {missing_in_model}"

    def test_reference_document_matches_schema(self):
        from bob3.models import ReferenceDocument

        db_cols = self._get_table_columns("reference_documents")
        model_fields = set(ReferenceDocument.model_fields.keys())
        missing_in_model = db_cols - model_fields
        assert not missing_in_model, f"ReferenceDocument missing DB columns: {missing_in_model}"

    def test_all_tables_have_models(self):
        """Every table in the schema should have a corresponding model."""
        from bob3 import models

        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        model_names = {
            name
            for name in dir(models)
            if not name.startswith("_")
            and hasattr(getattr(models, name), "model_fields")
        }

        assert len(model_names) >= 20, (
            f"Expected at least 20 Pydantic models, found {len(model_names)}: {model_names}"
        )
