"""Pydantic data models for all Bob3 database entities.

Each model mirrors its corresponding table in schema.sql, with proper
type hints, defaults, and validation constraints.
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ============================================================
# CORE ENTITIES
# ============================================================


class Project(BaseModel):
    """Project entity - top-level container for a build orchestration run."""

    id: str
    name: str
    description: str | None = None
    spec_path: str | None = None
    workspace_path: str
    status: str = "planning"

    total_cost_usd: float = Field(default=0.0, ge=0.0)
    max_cost_usd: float = Field(default=500.0, ge=0.0)

    spec_hash: str | None = None
    spec_last_modified: datetime | None = None

    environment_fingerprint: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Feature(BaseModel):
    """Feature entity - a unit of work within a project."""

    id: str
    project_id: str
    parent_feature_id: str | None = None
    decomposition_depth: int = 0

    name: str
    description: str | None = None
    acceptance_criteria: str | None = None
    status: str = "pending"

    priority: int = Field(default=100, ge=0)

    # Execution mode overrides (from YAML)
    tdd_mode: bool | None = None  # NULL = auto-detect, TRUE/FALSE = explicit override
    sub_agent_mode: bool | None = None  # NULL = auto-detect, TRUE/FALSE = explicit override

    risk_category: str = "medium"

    conf_spec_understanding: float = Field(default=0.0, ge=0.0, le=1.0)
    conf_impl_correctness: float = Field(default=0.0, ge=0.0, le=1.0)
    conf_test_adequacy: float = Field(default=0.0, ge=0.0, le=1.0)

    readiness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    readiness_components: str | None = None

    refinement_attempts: int = 0
    max_refinement_attempts: int = 5
    last_improvement_type: str | None = None
    research_iterations: int = 0

    original_acceptance_criteria_count: int | None = None
    original_task_count: int | None = None

    estimated_lines_of_code: int | None = None
    estimated_files_touched: int | None = None
    estimated_complexity: int | None = None
    exceeds_size_limits: bool = False
    size_limit_justification: str | None = None

    reviewer_confidence_cap: float | None = None

    completion_mode: str = "all_or_nothing"
    tasks_completed: int = 0
    tasks_total: int = 0

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Task(BaseModel):
    """Task entity - an individual implementation or validation task."""

    id: str
    feature_id: str
    project_id: str
    type: str
    subtype: str | None = None
    task_class: str | None = None

    title: str
    description: str | None = None
    acceptance_criteria: str | None = None
    expected_outputs: str | None = None
    verify_script: str | None = None

    status: str = "pending"

    conf_spec_understanding: float = Field(default=0.0, ge=0.0, le=1.0)
    conf_impl_correctness: float = Field(default=0.0, ge=0.0, le=1.0)
    conf_test_adequacy: float = Field(default=0.0, ge=0.0, le=1.0)

    readiness_score: float = Field(default=0.0, ge=0.0, le=1.0)

    attempts: int = 0
    max_attempts: int = 5

    is_human_authored: bool = False
    original_assertion_count: int | None = None
    current_assertion_count: int | None = None
    original_coverage_percent: float | None = None
    current_coverage_percent: float | None = None

    is_flaky: bool = False
    flaky_pass_rate: float | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# DEPENDENCY GRAPHS
# ============================================================


class FeatureDependency(BaseModel):
    """Tracks dependency relationships between features."""

    feature_id: str
    depends_on_feature_id: str
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None


class TaskDependency(BaseModel):
    """Tracks dependency relationships between tasks."""

    task_id: str
    depends_on_task_id: str


# ============================================================
# EVIDENCE ARTIFACTS
# ============================================================


class EvidenceArtifact(BaseModel):
    """Evidence artifact produced during task execution."""

    id: str
    project_id: str
    feature_id: str | None = None
    task_id: str | None = None
    attempt_number: int | None = None

    type: str
    content: str

    output_hash: str | None = None
    reproducible: bool | None = None
    verification_run_at: datetime | None = None
    verification_passed: bool | None = None

    is_current: bool = True
    iteration_created: int | None = None

    environment_fingerprint: str | None = None
    environment_matches_current: bool = True

    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# REVIEW SYSTEM
# ============================================================


class ReviewHistory(BaseModel):
    """Review history entry for a feature."""

    id: str
    project_id: str
    feature_id: str

    reviewer_id: str
    reviewer_type: str = "human"
    reviewer_seniority: int = 0

    verdict: str | None = None

    confidence_cap: float | None = None
    veto_active: bool = False

    issues_flagged: str | None = None
    required_validations: str | None = None
    notes: str | None = None

    issues_resolved: str | None = None
    resolved_at: datetime | None = None

    review_requested_at: datetime = Field(default_factory=datetime.now)
    review_timeout_hours: int = 48
    timeout_action_taken: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)


class FeatureReviewIssue(BaseModel):
    """Individual issue flagged during a feature review."""

    id: str
    feature_id: str
    review_id: str

    issue_description: str
    severity: str = "medium"

    resolved: bool = False
    resolved_by_attempt: int | None = None
    resolution_evidence: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: datetime | None = None


# ============================================================
# BUG LEDGER
# ============================================================


class BugLedger(BaseModel):
    """Bug ledger entry tracking errors and their resolution."""

    id: str
    project_id: str
    feature_id: str | None = None
    task_id: str | None = None

    error_type: str
    error_message: str
    error_context: str | None = None

    evidence_artifacts: str

    blame_target: str | None = None
    root_cause: str | None = None
    fix_action: str
    fix_details: str | None = None
    fix_evidence: str | None = None

    resolved: bool = False
    resolution_attempts: int = 1

    titans_memory_id: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: datetime | None = None


# ============================================================
# CALIBRATION SYSTEM
# ============================================================


class CalibrationData(BaseModel):
    """Calibration data for confidence-to-pass-rate tracking."""

    id: str
    project_id: str | None = None

    task_class: str
    confidence_bucket: str

    total_attempts: int = 0
    total_passes: int = 0
    total_failures: int = 0

    empirical_pass_rate: float | None = None
    expected_pass_rate: float | None = None
    drift: float | None = None

    adjusted_threshold: float | None = None

    last_updated: datetime = Field(default_factory=datetime.now)


class CalibrationAlert(BaseModel):
    """Alert triggered when calibration drift exceeds threshold."""

    id: str
    project_id: str | None = None
    task_class: str
    confidence_bucket: str

    drift_amount: float
    direction: str
    sample_size: int

    acknowledged: bool = False
    action_taken: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# REGRESSION & ROLLBACK
# ============================================================


class RegressionEvent(BaseModel):
    """Regression event when a feature breaks previously passing tests."""

    id: str
    project_id: str

    affected_feature_id: str
    causing_feature_id: str

    detected_at: datetime = Field(default_factory=datetime.now)

    affected_tests: str | None = None
    evidence_artifacts: str | None = None

    status: str = "detected"
    resolution: str | None = None

    resolved_at: datetime | None = None


class RollbackEvent(BaseModel):
    """Rollback event when a feature is reverted."""

    id: str
    project_id: str
    feature_id: str

    trigger: str
    regression_event_id: str | None = None

    commit_before: str
    commit_after: str

    rollback_commit: str | None = None

    artifacts_preserved: str | None = None
    titans_memory_id: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# RESOURCE MANAGEMENT
# ============================================================


class ResourceCheckpoint(BaseModel):
    """Checkpoint for resumable task execution."""

    id: str
    project_id: str
    feature_id: str
    task_id: str | None = None

    checkpoint_type: str

    state_snapshot: str
    files_snapshot: str | None = None

    cost_at_checkpoint: float | None = None
    duration_at_checkpoint_ms: int | None = None

    can_resume: bool = True
    resumed_at: datetime | None = None

    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# FLAKY TEST TRACKING
# ============================================================


class FlakyTestRun(BaseModel):
    """Individual run of a potentially flaky test."""

    id: str
    task_id: str

    run_number: int
    passed: bool
    output: str | None = None
    duration_ms: int | None = None

    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# SUB-AGENT TRACKING
# ============================================================


class SubAgentRun(BaseModel):
    """Sub-agent execution record."""

    id: str
    project_id: str
    parent_run_id: str | None = None

    purpose: str
    target_type: str | None = None
    target_id: str | None = None

    status: str = "running"

    prompt_summary: str | None = None
    result_summary: str | None = None

    rca_blame_target: str | None = None
    rca_recommended_action: str | None = None

    evidence_artifacts_produced: str | None = None

    improvement_type: str | None = None
    improvement_evidence: str | None = None

    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None

    mcp_enabled: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


# ============================================================
# CONFIDENCE & READINESS HISTORY
# ============================================================


class ConfidenceHistory(BaseModel):
    """Snapshot of confidence scores at a point in time."""

    id: str
    project_id: str
    feature_id: str | None = None
    task_id: str | None = None

    conf_spec_understanding: float | None = None
    conf_impl_correctness: float | None = None
    conf_test_adequacy: float | None = None

    rated_by: str
    rationale: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)


class ReadinessHistory(BaseModel):
    """Snapshot of readiness calculation at a point in time."""

    id: str
    project_id: str
    feature_id: str

    readiness_score: float
    opus_confidence_component: float | None = None
    test_pass_rate_component: float | None = None
    evidence_score_component: float | None = None
    diff_quality_component: float | None = None
    reviewer_adjustment_component: float | None = None

    change_reason: str | None = None
    rules_applied: str | None = None

    computed_by: str

    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# SCOPE CHANGE TRACKING
# ============================================================


class ScopeChange(BaseModel):
    """Tracks scope changes to features for creep detection."""

    id: str
    feature_id: str

    change_type: str

    before_value: str | None = None
    after_value: str | None = None

    growth_percent: float | None = None

    requires_approval: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None

    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# TITANS FORGETTING AUDIT
# ============================================================


class ForgettingEvent(BaseModel):
    """Audit log for TITANS Memory forgetting actions."""

    id: str
    project_id: str | None = None

    target_type: str
    target_id: str

    action: str
    reason: str

    previous_status: str | None = None
    previous_usefulness_score: float | None = None
    previous_retrieval_weight: float | None = None

    backup_path: str | None = None
    backup_content: str | None = None

    triggered_by: str | None = None
    approved_by: str | None = None

    can_restore: bool = True
    restored_at: datetime | None = None

    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# EXECUTION LOGS
# ============================================================


class ExecutionLog(BaseModel):
    """Execution log entry for system events."""

    id: str
    project_id: str
    sub_agent_run_id: str | None = None

    level: str = "info"
    event: str
    details: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# BOB3-SPECIFIC TABLES
# ============================================================


class ResearchResult(BaseModel):
    """Research result from a Perplexity-enabled sub-agent."""

    id: str
    feature_id: str
    project_id: str
    agent_run_id: str | None = None
    query: str
    findings: str | None = None
    sources: str | None = None
    code_examples: str | None = None
    applied: bool = False
    created_at: datetime = Field(default_factory=datetime.now)


class ReferenceDocument(BaseModel):
    """Reference document (PDF or other) associated with a project."""

    id: str
    project_id: str
    file_path: str
    title: str | None = None
    extracted_text: str | None = None
    page_count: int | None = None
    sections: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class FeatureReference(BaseModel):
    """Links a feature to a reference document with optional section hint."""

    feature_id: str
    reference_id: str
    section_hint: str | None = None
