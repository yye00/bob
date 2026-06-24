"""Pydantic data models for all Bob3 database entities.

Each model mirrors its corresponding table in schema.sql, with proper
type hints, defaults, and validation constraints.
"""

import os
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# Default per-project cost ceiling (USD). Env-overridable: bob-chain dev work has
# no $ budget (operator directive — never NH a feature merely for projected cost).
# The old hardcoded 500.0 mass-NH'd every remaining feature once a long run
# approached it. Set BOB3_MAX_COST_USD very high (or leave the high default) to
# disable cost-based NH; the per-attempt cap (BOB3_PER_ATTEMPT_COST_CAP) still
# guards runaway single sub-agents.
def resolve_max_cost_usd() -> float:
    """Return the effective per-project cost ceiling read from BOB3_MAX_COST_USD.

    An absent, empty, whitespace-only, non-numeric, NaN, or Inf value returns
    the effectively-unlimited default (1_000_000.0).  A valid numeric value is
    clamped to >= 0.0 and returned.  Never returns 0.0 from a malformed env var
    (which would block every spawn).
    """
    import math as _math
    raw = os.environ.get("BOB3_MAX_COST_USD", "")
    if not raw or not raw.strip():
        return 1_000_000.0
    try:
        val = float(raw)
        if _math.isnan(val) or _math.isinf(val):
            return 1_000_000.0
        return max(0.0, val)
    except ValueError:
        return 1_000_000.0


def _default_max_cost_usd() -> float:
    return resolve_max_cost_usd()


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
    max_cost_usd: float = Field(default_factory=_default_max_cost_usd, ge=0.0)

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

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority(cls, v):
        if v is None:
            return 100
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            pmap = {"low": 30, "medium": 50, "high": 70, "critical": 90}
            return pmap.get(v.lower(), 100)
        return 100

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

    spec_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)

    # When True, this feature is permanently exempt from the spec_quality_score gate.
    # Set for infra features (F-R7-478, F-R7-479, F-R7-481) that carry forward across
    # generations with intentionally terse ACs scoring in the 0.6-0.75 range.
    permanent_forward_carry: bool = False

    # Stable cross-generation identifier derived from the spec key (e.g. "F-R6-200").
    # Used by the convergence detector to compare generations without UUID churn.
    spec_slot: str | None = None

    def spec_slot_layer(self) -> str | None:
        """Return the spec layer string parsed from spec_slot, e.g. 'R7' from 'F-R7-400'.

        Returns None when spec_slot is None or does not match the 'F-Rn-nnn' pattern.
        """
        if self.spec_slot is None:
            return None
        import re
        m = re.match(r"^F-(R\d+)-\d+$", self.spec_slot)
        return m.group(1) if m else None

    # True when this feature was status='completed' in the parent generation's DB
    # at seed time. Guards against evaluator-FAIL or regression-cascade stripping
    # an already-validated-elsewhere stamp (sticky-completed gate, eb3c74d9).
    parent_completed: bool = False

    # Parent-generation provenance fields (e1b5bacb — F-R7-420 prerequisite).
    # Stamped at seed time by inherit_from_parent_db when a matching spec_slot
    # is found in the parent DB with status in completed/needs_human/regression.
    parent_status: str | None = None
    parent_completed_at: datetime | None = None
    parent_evidence_hash: str | None = None

    # Bootstrap override counter (73d63cdc — F-R6-305 deadlock fix).
    # Allows one execution bypass when research_iterations==0 blocks the
    # readiness gate before any execution signal exists to seed research.
    bootstrap_attempts: int = 0

    # F-R7-633: current position in the model-escalation ladder
    # (BOB3_MODEL_ESCALATION_LADDER). 0 = first/least-capable model. Bumped when
    # the feature exhausts attempts on its current model. See bob3.model_escalation.
    model_tier: int = 0

    # Sub-translation provenance (10cfd424 — F-S2).
    # JSON array of per-AC provenance records: [{ac, spans: [{start, end}]}].
    # NULL = provenance not yet computed. Empty spans on a record = unresolved.
    provenance_spans: str | None = None

    # Test-ownership map (63ce7239 — F-S3: regression-treadmill fix).
    # JSON array of test_*.py paths owned by this feature, e.g.
    # ["tests/test_foo.py", "tests/test_bar.py"].
    # NULL = not declared (legacy or not yet assigned).
    test_files: str | None = None

    # RTM artifact path (a5a3bb43 — bidirectional RTM).
    # Filesystem path to the generated runs/<feature_id>/rtm.json artifact.
    # NULL = RTM not yet generated for this feature.
    rtm_artifact_path: str | None = None

    # Reap backoff fields (7fa3f533 — exponential backoff after reaper-reset).
    # Stamped by stuck_executing_reaper when it resets a feature from
    # 'executing' → 'ready'. The dispatch loop uses these to refuse
    # re-dispatch within min(2^reap_count * 60s, 3600s) of last_reap_at.
    # After 3 reaps without an intervening success, feature escalates to
    # needs_human with reason="repeated_reap_cycle".
    last_reap_at: datetime | None = None
    reap_count: int = 0

    # Stuck-executing reaper fields (b596a38a).
    # subagent_pid: OS PID of the currently-running claude subagent, set at spawn.
    # subagent_heartbeat_at: last wall-clock timestamp the subagent reported alive.
    subagent_pid: int | None = None
    subagent_heartbeat_at: datetime | None = None

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
# MEMORY FORGETTING AUDIT
# ============================================================


class ForgettingEvent(BaseModel):
    """Audit log for bob3 memory forgetting actions.

    Note: table/column names retain the legacy 'titans' prefix from the
    pre-bob3-memory schema; only docs/labels have been updated.
    """

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


# ============================================================
# SECURITY VERIFICATION (Round 0 Task 2 — Check #9)
# ============================================================


class SecurityFinding(BaseModel):
    """Single finding emitted by one of the four security sub-checks.

    See ``bob3.security_checks.run_security_checks`` for the runner and
    ``docs/recursion/round1/research/gap_02_security_scanning.md`` for the
    design.
    """

    tool: Literal["pip-audit", "detect-secrets", "bandit", "slopsquatting"]
    severity: Literal["high", "medium", "low", "info"]
    message: str
    file: str | None = None
    line: int | None = None
    cve_or_rule_id: str | None = None


class SecurityResult(BaseModel):
    """Aggregate result of a Check #9 invocation.

    ``hard_fail`` honours the tiered severity policy in PLAN.md AC4:
    secrets and slopsquatting findings are hard-fail; bandit ``high`` is
    hard-fail; everything else (pip-audit at any severity, bandit
    medium/low, ``info``-level tool_failed records) is a warning.
    """

    hard_fail: bool
    findings: list[SecurityFinding] = Field(default_factory=list)
    tool_failures: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0


# ============================================================
# INDEPENDENT EVALUATOR (Round 0 Task 1 — Gap #1)
# ============================================================


class EvaluatorVerdict(BaseModel):
    """Structured verdict from the independent evaluator sub-agent.

    The evaluator is a fresh Claude sub-agent with no access to the
    implementation agent's transcript or session id. It reads the feature
    spec, acceptance criteria, and the workspace diff, then returns this
    verdict. See ``bob3.orchestrator.claude_executor.spawn_evaluator_agent``
    for the runner and
    ``docs/recursion/round1/research/gap_01_10_independent_evaluator_and_ui_verification.md``
    for the design source.

    Fields:
        verdict: Top-level outcome.
            - ``PASS``: every acceptance criterion was met with sufficient
              evidence; the feature is safe to commit.
            - ``FAIL``: at least one acceptance criterion was not met or
              the evaluator found a defect that warrants re-implementation.
            - ``INSUFFICIENT_EVIDENCE``: the evaluator could not establish
              PASS or FAIL from the materials available; treat as a soft
              FAIL — the feature is NOT committed and the orchestrator
              should retry or escalate to a human.
        findings: Free-form list of bullet findings. On FAIL each entry
            should be an actionable defect statement that the next
            implementation attempt can address.
        confidence: Evaluator's self-rated confidence in the verdict on
            ``[0.0, 1.0]``. Implementations should treat low-confidence
            PASS the same as INSUFFICIENT_EVIDENCE.
        evidence: Map of claim -> evidence string. Evidence strings are
            either ``file:line`` references in the workspace, captured
            command output snippets, or evidence-artifact ids. Used by
            reviewers to spot-check the evaluator's reasoning.
    """

    verdict: Literal["PASS", "FAIL", "INSUFFICIENT_EVIDENCE"]
    findings: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: dict[str, str] = Field(default_factory=dict)
