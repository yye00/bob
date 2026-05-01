-- ============================================
-- Bob3 v2.1 Database Schema
-- ============================================
-- Includes both core Bob2 tables and Bob3-specific additions.
-- NOTE: project_memory and lessons_learned are handled by bob3-memory (MCP),
--       not stored in this local database.
-- ============================================

-- ============================================
-- CORE ENTITIES
-- ============================================

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    spec_path TEXT,
    workspace_path TEXT NOT NULL,
    status TEXT DEFAULT 'planning',

    -- Resource tracking
    total_cost_usd REAL DEFAULT 0.0,
    max_cost_usd REAL DEFAULT 500.0,

    -- Spec change detection (F115)
    spec_hash TEXT,                    -- SHA256 of spec file for change detection
    spec_last_modified TIMESTAMP,      -- Last modification time of spec file

    -- Environment fingerprint
    environment_fingerprint TEXT,      -- JSON: {python_version, deps_hash, os_info}

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS features (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    parent_feature_id TEXT REFERENCES features(id),  -- For decomposed features
    decomposition_depth INTEGER DEFAULT 0,           -- CORNER CASE #17

    name TEXT NOT NULL,
    description TEXT,
    acceptance_criteria TEXT,          -- JSON array of feature-level criteria
    status TEXT DEFAULT 'pending',
    -- Status values: pending|pending_decomposition|refining|ready|executing|completed|failed|
    --                blocked_by_reviewer|blocked_by_dependency|needs_human|
    --                resource_limited|rolled_back|regression|partially_completed|interrupted
    -- NOTE: 'interrupted' status (F117) means graceful shutdown occurred mid-execution

    -- Feature priority (lower = higher priority)
    priority INTEGER DEFAULT 100,

    -- Execution mode overrides (from YAML)
    tdd_mode BOOLEAN DEFAULT NULL,         -- NULL = auto-detect, TRUE/FALSE = explicit override
    sub_agent_mode BOOLEAN DEFAULT NULL,   -- NULL = auto-detect, TRUE/FALSE = explicit override

    risk_category TEXT DEFAULT 'medium',

    -- Split confidence dimensions
    conf_spec_understanding REAL DEFAULT 0.0,
    conf_impl_correctness REAL DEFAULT 0.0,
    conf_test_adequacy REAL DEFAULT 0.0,

    -- Composite readiness
    readiness_score REAL DEFAULT 0.0,
    readiness_components TEXT,         -- JSON

    -- Refinement tracking
    refinement_attempts INTEGER DEFAULT 0,
    max_refinement_attempts INTEGER DEFAULT 5,
    last_improvement_type TEXT,
    research_iterations INTEGER DEFAULT 0,           -- CORNER CASE #18

    -- Scope tracking (CORNER CASE #19)
    original_acceptance_criteria_count INTEGER,
    original_task_count INTEGER,

    -- Feature size limits
    estimated_lines_of_code INTEGER,
    estimated_files_touched INTEGER,
    estimated_complexity INTEGER,      -- 1-10 scale
    exceeds_size_limits BOOLEAN DEFAULT FALSE,
    size_limit_justification TEXT,     -- If soft limit exceeded with justification

    -- Reviewer state
    reviewer_confidence_cap REAL,

    -- Completion tracking (CORNER CASE #14)
    completion_mode TEXT DEFAULT 'all_or_nothing',
    tasks_completed INTEGER DEFAULT 0,
    tasks_total INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL REFERENCES features(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    type TEXT NOT NULL,                -- implementation|validation
    subtype TEXT,                      -- numerical|algorithmic|convergence|structural
    task_class TEXT,                   -- greenfield_impl|refactor|bug_fix|test_writing|infrastructure

    title TEXT NOT NULL,
    description TEXT,
    acceptance_criteria TEXT,          -- JSON array
    expected_outputs TEXT,             -- JSON array
    verify_script TEXT,

    status TEXT DEFAULT 'pending',

    -- Split confidence
    conf_spec_understanding REAL DEFAULT 0.0,
    conf_impl_correctness REAL DEFAULT 0.0,
    conf_test_adequacy REAL DEFAULT 0.0,

    readiness_score REAL DEFAULT 0.0,

    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 5,

    -- Validation integrity tracking (CORNER CASE #27)
    is_human_authored BOOLEAN DEFAULT FALSE,
    original_assertion_count INTEGER,
    current_assertion_count INTEGER,
    original_coverage_percent REAL,
    current_coverage_percent REAL,

    -- Flaky test tracking (CORNER CASE #30)
    is_flaky BOOLEAN DEFAULT FALSE,
    flaky_pass_rate REAL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- DEPENDENCY GRAPHS
-- ============================================

CREATE TABLE IF NOT EXISTS feature_dependencies (
    feature_id TEXT NOT NULL REFERENCES features(id),
    depends_on_feature_id TEXT NOT NULL REFERENCES features(id),

    -- CORNER CASE #11: Cascade tracking
    invalidated_at TIMESTAMP,
    invalidation_reason TEXT,

    PRIMARY KEY (feature_id, depends_on_feature_id)
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(id),
    depends_on_task_id TEXT NOT NULL REFERENCES tasks(id),
    PRIMARY KEY (task_id, depends_on_task_id)
);

-- ============================================
-- EVIDENCE ARTIFACTS
-- ============================================

CREATE TABLE IF NOT EXISTS evidence_artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    feature_id TEXT REFERENCES features(id),
    task_id TEXT REFERENCES tasks(id),
    attempt_number INTEGER,

    type TEXT NOT NULL,
    content TEXT NOT NULL,             -- JSON

    -- CORNER CASE #26: Verification
    output_hash TEXT,                  -- SHA256 of actual output
    reproducible BOOLEAN,
    verification_run_at TIMESTAMP,
    verification_passed BOOLEAN,

    -- CORNER CASE #20: Staleness
    is_current BOOLEAN DEFAULT TRUE,
    iteration_created INTEGER,

    -- CORNER CASE #22: Environment
    environment_fingerprint TEXT,      -- JSON
    environment_matches_current BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- REVIEW SYSTEM
-- ============================================

CREATE TABLE IF NOT EXISTS review_history (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    feature_id TEXT NOT NULL REFERENCES features(id),

    reviewer_id TEXT NOT NULL,
    reviewer_type TEXT DEFAULT 'human',
    reviewer_seniority INTEGER DEFAULT 0,  -- CORNER CASE #16: For senior_wins policy

    verdict TEXT,                      -- NULL=pending, approve|request_changes|block

    confidence_cap REAL,
    veto_active BOOLEAN DEFAULT FALSE,

    issues_flagged TEXT,               -- JSON array
    required_validations TEXT,         -- JSON array
    notes TEXT,

    issues_resolved TEXT,
    resolved_at TIMESTAMP,

    -- CORNER CASE #21: Timeout tracking
    review_requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    review_timeout_hours INTEGER DEFAULT 48,
    timeout_action_taken TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feature_review_issues (
    id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL REFERENCES features(id),
    review_id TEXT NOT NULL REFERENCES review_history(id),

    issue_description TEXT NOT NULL,
    severity TEXT DEFAULT 'medium',

    resolved BOOLEAN DEFAULT FALSE,
    resolved_by_attempt INTEGER,
    resolution_evidence TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

-- ============================================
-- NOTE: Project memory is handled by the bob3-memory MCP server.
-- No local project_memory table needed - use memory_add, memory_search, etc.
-- ============================================

-- ============================================
-- NOTE: Lessons are stored in bob3-memory (lessons pool)
-- No local lessons_learned table - use memory_add, memory_search, etc.
-- ============================================

CREATE TABLE IF NOT EXISTS bug_ledger (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    feature_id TEXT REFERENCES features(id),
    task_id TEXT REFERENCES tasks(id),

    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    error_context TEXT,

    evidence_artifacts TEXT NOT NULL,  -- JSON array

    -- RCA results
    blame_target TEXT,                 -- implementation|validation|feature_spec|infrastructure|external|test_flaky
    root_cause TEXT,
    fix_action TEXT NOT NULL,
    fix_details TEXT,
    fix_evidence TEXT,

    resolved BOOLEAN DEFAULT FALSE,
    resolution_attempts INTEGER DEFAULT 1,

    -- Link to bob3-memory lesson (if created)
    titans_memory_id TEXT,  -- legacy column name; ID from memory_add response

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

-- ============================================
-- CALIBRATION SYSTEM
-- ============================================

CREATE TABLE IF NOT EXISTS calibration_data (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),

    task_class TEXT NOT NULL,
    confidence_bucket TEXT NOT NULL,

    total_attempts INTEGER DEFAULT 0,
    total_passes INTEGER DEFAULT 0,
    total_failures INTEGER DEFAULT 0,

    empirical_pass_rate REAL,
    expected_pass_rate REAL,
    drift REAL,

    adjusted_threshold REAL,

    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(project_id, task_class, confidence_bucket)
);

CREATE TABLE IF NOT EXISTS calibration_alerts (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),
    task_class TEXT NOT NULL,
    confidence_bucket TEXT NOT NULL,

    drift_amount REAL NOT NULL,
    direction TEXT NOT NULL,           -- overconfident|underconfident
    sample_size INTEGER NOT NULL,

    acknowledged BOOLEAN DEFAULT FALSE,
    action_taken TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- REGRESSION & ROLLBACK
-- ============================================

-- CORNER CASE #13: Regression tracking
CREATE TABLE IF NOT EXISTS regression_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),

    affected_feature_id TEXT NOT NULL REFERENCES features(id),
    causing_feature_id TEXT NOT NULL REFERENCES features(id),

    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    affected_tests TEXT,               -- JSON array of test IDs that started failing
    evidence_artifacts TEXT,           -- JSON array

    status TEXT DEFAULT 'detected',    -- detected|investigating|fixing|resolved|rolled_back
    resolution TEXT,

    resolved_at TIMESTAMP
);

-- CORNER CASE #28: Rollback tracking
CREATE TABLE IF NOT EXISTS rollback_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    feature_id TEXT NOT NULL REFERENCES features(id),

    trigger TEXT NOT NULL,             -- regression|human_request|critical_bug
    regression_event_id TEXT REFERENCES regression_events(id),

    commit_before TEXT NOT NULL,       -- Commit SHA before feature
    commit_after TEXT NOT NULL,        -- Commit SHA after feature (being rolled back)

    rollback_commit TEXT,              -- Commit SHA of rollback

    artifacts_preserved TEXT,          -- JSON array of preserved artifact IDs
    titans_memory_id TEXT,             -- legacy column name; Lesson ID from bob3-memory

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- RESOURCE MANAGEMENT
-- ============================================

-- CORNER CASE #29: Checkpointing
CREATE TABLE IF NOT EXISTS resource_checkpoints (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    feature_id TEXT NOT NULL REFERENCES features(id),
    task_id TEXT REFERENCES tasks(id),

    checkpoint_type TEXT NOT NULL,     -- task_completion|resource_limit|manual

    state_snapshot TEXT NOT NULL,      -- JSON: current state of feature/task
    files_snapshot TEXT,               -- JSON: list of files and their hashes

    cost_at_checkpoint REAL,
    duration_at_checkpoint_ms INTEGER,

    can_resume BOOLEAN DEFAULT TRUE,
    resumed_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- FLAKY TEST TRACKING
-- ============================================

-- CORNER CASE #30
CREATE TABLE IF NOT EXISTS flaky_test_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),

    run_number INTEGER NOT NULL,
    passed BOOLEAN NOT NULL,
    output TEXT,
    duration_ms INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- SUB-AGENT TRACKING
-- ============================================

CREATE TABLE IF NOT EXISTS sub_agent_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    parent_run_id TEXT REFERENCES sub_agent_runs(id),

    purpose TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,

    status TEXT DEFAULT 'running',

    prompt_summary TEXT,
    result_summary TEXT,

    -- RCA results (for rca_analyst agents)
    rca_blame_target TEXT,
    rca_recommended_action TEXT,

    evidence_artifacts_produced TEXT,

    improvement_type TEXT,
    improvement_evidence TEXT,

    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    duration_ms INTEGER,

    -- Bob3 addition: MCP plugin tracking
    mcp_enabled TEXT,                  -- JSON: ["perplexity", "puppeteer"]

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- ============================================
-- CONFIDENCE & READINESS HISTORY
-- ============================================

CREATE TABLE IF NOT EXISTS confidence_history (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    feature_id TEXT REFERENCES features(id),
    task_id TEXT REFERENCES tasks(id),

    conf_spec_understanding REAL,
    conf_impl_correctness REAL,
    conf_test_adequacy REAL,

    rated_by TEXT NOT NULL,
    rationale TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS readiness_history (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    feature_id TEXT NOT NULL REFERENCES features(id),

    readiness_score REAL NOT NULL,
    opus_confidence_component REAL,
    test_pass_rate_component REAL,
    evidence_score_component REAL,
    diff_quality_component REAL,
    reviewer_adjustment_component REAL,

    change_reason TEXT,
    rules_applied TEXT,                -- JSON array

    computed_by TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- SCOPE CHANGE TRACKING (CORNER CASE #19)
-- ============================================

CREATE TABLE IF NOT EXISTS scope_changes (
    id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL REFERENCES features(id),

    change_type TEXT NOT NULL,         -- acceptance_criteria_added|task_added|description_changed

    before_value TEXT,
    after_value TEXT,

    growth_percent REAL,               -- How much did scope grow?

    requires_approval BOOLEAN DEFAULT FALSE,
    approved_by TEXT,
    approved_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- MEMORY FORGETTING AUDIT (bob3-memory)
-- ============================================

CREATE TABLE IF NOT EXISTS forgetting_events (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),

    target_type TEXT NOT NULL,         -- lesson|memory
    target_id TEXT NOT NULL,

    action TEXT NOT NULL,              -- demote|archive|purge|restore
    reason TEXT NOT NULL,

    -- State before action
    previous_status TEXT,
    previous_usefulness_score REAL,
    previous_retrieval_weight REAL,

    -- Backup info (for purge)
    backup_path TEXT,
    backup_content TEXT,               -- JSON snapshot of deleted item

    -- Audit
    triggered_by TEXT,                 -- schedule|manual|system
    approved_by TEXT,                  -- Human who approved (for purge)

    can_restore BOOLEAN DEFAULT TRUE,
    restored_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- EXECUTION LOGS
-- ============================================

CREATE TABLE IF NOT EXISTS execution_logs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    sub_agent_run_id TEXT REFERENCES sub_agent_runs(id),

    level TEXT DEFAULT 'info',
    event TEXT NOT NULL,
    details TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- INDEXES
-- ============================================

-- Features indexes
CREATE INDEX IF NOT EXISTS idx_features_project ON features(project_id);
CREATE INDEX IF NOT EXISTS idx_features_status ON features(status);
CREATE INDEX IF NOT EXISTS idx_features_risk ON features(risk_category);
CREATE INDEX IF NOT EXISTS idx_features_readiness ON features(readiness_score);
CREATE INDEX IF NOT EXISTS idx_features_parent ON features(parent_feature_id);
CREATE INDEX IF NOT EXISTS idx_features_priority ON features(priority);

-- Tasks indexes
CREATE INDEX IF NOT EXISTS idx_tasks_feature ON tasks(feature_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_class ON tasks(task_class);
CREATE INDEX IF NOT EXISTS idx_tasks_flaky ON tasks(is_flaky);

-- Evidence indexes
CREATE INDEX IF NOT EXISTS idx_evidence_feature ON evidence_artifacts(feature_id);
CREATE INDEX IF NOT EXISTS idx_evidence_task ON evidence_artifacts(task_id);
CREATE INDEX IF NOT EXISTS idx_evidence_current ON evidence_artifacts(is_current);
CREATE INDEX IF NOT EXISTS idx_evidence_env_match ON evidence_artifacts(environment_matches_current);

-- Review indexes
CREATE INDEX IF NOT EXISTS idx_review_history_feature ON review_history(feature_id);
CREATE INDEX IF NOT EXISTS idx_review_history_verdict ON review_history(verdict);
CREATE INDEX IF NOT EXISTS idx_review_history_timeout ON review_history(review_requested_at);

CREATE INDEX IF NOT EXISTS idx_review_issues_feature ON feature_review_issues(feature_id);
CREATE INDEX IF NOT EXISTS idx_review_issues_resolved ON feature_review_issues(resolved);

-- NOTE: Lessons indexes removed - lessons stored in bob3-memory (MCP)

-- Calibration indexes
CREATE INDEX IF NOT EXISTS idx_calibration_class ON calibration_data(task_class);

-- Bug ledger indexes
CREATE INDEX IF NOT EXISTS idx_bug_ledger_project ON bug_ledger(project_id);
CREATE INDEX IF NOT EXISTS idx_bug_ledger_blame ON bug_ledger(blame_target);

-- Regression indexes
CREATE INDEX IF NOT EXISTS idx_regression_affected ON regression_events(affected_feature_id);
CREATE INDEX IF NOT EXISTS idx_regression_causing ON regression_events(causing_feature_id);

-- Rollback indexes
CREATE INDEX IF NOT EXISTS idx_rollback_feature ON rollback_events(feature_id);

-- Checkpoint indexes
CREATE INDEX IF NOT EXISTS idx_checkpoints_feature ON resource_checkpoints(feature_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_resumable ON resource_checkpoints(can_resume);

-- Flaky test indexes
CREATE INDEX IF NOT EXISTS idx_flaky_runs_task ON flaky_test_runs(task_id);

-- Sub-agent indexes
CREATE INDEX IF NOT EXISTS idx_sub_agent_runs_project ON sub_agent_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_sub_agent_runs_purpose ON sub_agent_runs(purpose);
CREATE INDEX IF NOT EXISTS idx_sub_agent_runs_parent ON sub_agent_runs(parent_run_id);
CREATE INDEX IF NOT EXISTS idx_sub_agent_runs_lookup
ON sub_agent_runs(project_id, target_id, purpose, status);

-- Readiness history indexes
CREATE INDEX IF NOT EXISTS idx_readiness_history_feature ON readiness_history(feature_id);

-- Scope change indexes
CREATE INDEX IF NOT EXISTS idx_scope_changes_feature ON scope_changes(feature_id);
CREATE INDEX IF NOT EXISTS idx_scope_changes_approval ON scope_changes(requires_approval);

-- Execution log indexes
CREATE INDEX IF NOT EXISTS idx_execution_logs_project ON execution_logs(project_id);

-- Forgetting event indexes
CREATE INDEX IF NOT EXISTS idx_forgetting_project ON forgetting_events(project_id);
CREATE INDEX IF NOT EXISTS idx_forgetting_target ON forgetting_events(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_forgetting_action ON forgetting_events(action);

-- ============================================
-- VIEWS
-- ============================================

-- Features ready for implementation (ordered by priority)
CREATE VIEW IF NOT EXISTS features_ready AS
SELECT f.*,
       CASE f.risk_category
           WHEN 'low' THEN 0.70
           WHEN 'medium' THEN 0.80
           WHEN 'high' THEN 0.90
           WHEN 'critical' THEN 0.95
       END as required_threshold
FROM features f
WHERE f.readiness_score >= (
    CASE f.risk_category
        WHEN 'low' THEN 0.70
        WHEN 'medium' THEN 0.80
        WHEN 'high' THEN 0.90
        WHEN 'critical' THEN 0.95
    END
)
AND f.status = 'ready'
AND NOT EXISTS (
    SELECT 1 FROM review_history r
    WHERE r.feature_id = f.id
    AND r.veto_active = TRUE
)
AND NOT EXISTS (
    SELECT 1 FROM feature_dependencies fd
    JOIN features dep ON dep.id = fd.depends_on_feature_id
    WHERE fd.feature_id = f.id
    AND dep.status != 'completed'
)
ORDER BY f.priority ASC, f.created_at ASC;

-- Features needing refinement
CREATE VIEW IF NOT EXISTS features_needing_refinement AS
SELECT f.* FROM features f
WHERE f.readiness_score < (
    CASE f.risk_category
        WHEN 'low' THEN 0.70
        WHEN 'medium' THEN 0.80
        WHEN 'high' THEN 0.90
        WHEN 'critical' THEN 0.95
    END
)
AND f.refinement_attempts < f.max_refinement_attempts
AND f.status NOT IN ('needs_human', 'blocked_by_reviewer', 'blocked_by_dependency', 'resource_limited', 'pending_decomposition')
ORDER BY f.priority ASC;

-- Features pending decomposition (too large)
CREATE VIEW IF NOT EXISTS features_pending_decomposition AS
SELECT f.* FROM features f
WHERE f.status = 'pending_decomposition'
   OR f.exceeds_size_limits = TRUE
ORDER BY f.priority ASC;

-- Features blocked by various reasons
CREATE VIEW IF NOT EXISTS features_blocked AS
SELECT f.id, f.name, f.status,
       CASE
           WHEN f.status = 'blocked_by_reviewer' THEN 'Reviewer veto active'
           WHEN f.status = 'blocked_by_dependency' THEN 'Dependency not completed'
           WHEN f.status = 'needs_human' THEN 'Requires human intervention'
           WHEN f.status = 'resource_limited' THEN 'Resource limit reached'
       END as block_reason
FROM features f
WHERE f.status IN ('blocked_by_reviewer', 'blocked_by_dependency', 'needs_human', 'resource_limited');

-- Features needing human intervention
CREATE VIEW IF NOT EXISTS features_needs_human AS
SELECT f.* FROM features f
WHERE f.status = 'needs_human'
   OR f.refinement_attempts >= f.max_refinement_attempts
   OR f.research_iterations >= 3
   OR f.decomposition_depth >= 3
   OR (f.risk_category = 'critical' AND NOT EXISTS (
       SELECT 1 FROM review_history r
       WHERE r.feature_id = f.id
       AND r.verdict = 'approve'
       AND r.reviewer_type = 'human'
   ));

-- Unresolved review issues
CREATE VIEW IF NOT EXISTS unresolved_issues AS
SELECT f.id as feature_id, f.name as feature_name,
       COUNT(fri.id) as issue_count,
       GROUP_CONCAT(fri.issue_description, '; ') as issues
FROM features f
JOIN feature_review_issues fri ON fri.feature_id = f.id
WHERE fri.resolved = FALSE
GROUP BY f.id;

-- Pending reviews (awaiting verdict)
CREATE VIEW IF NOT EXISTS reviews_pending AS
SELECT r.*, f.name as feature_name, f.risk_category, f.priority,
       (julianday('now') - julianday(r.review_requested_at)) * 24 as hours_waiting
FROM review_history r
JOIN features f ON f.id = r.feature_id
WHERE r.verdict IS NULL
ORDER BY f.priority ASC, r.review_requested_at ASC;

-- Review timeouts
CREATE VIEW IF NOT EXISTS review_timeouts AS
SELECT r.*, f.name as feature_name, f.risk_category,
       (julianday('now') - julianday(r.review_requested_at)) * 24 as hours_waiting
FROM review_history r
JOIN features f ON f.id = r.feature_id
WHERE r.verdict IS NULL
AND (julianday('now') - julianday(r.review_requested_at)) * 24 > r.review_timeout_hours;

-- Stale evidence
CREATE VIEW IF NOT EXISTS stale_evidence AS
SELECT ea.*, f.name as feature_name
FROM evidence_artifacts ea
JOIN features f ON f.id = ea.feature_id
WHERE ea.is_current = TRUE
AND (
    ea.iteration_created < (SELECT MAX(iteration_created) FROM evidence_artifacts WHERE feature_id = ea.feature_id) - 2
    OR ea.environment_matches_current = FALSE
);

-- Calibration drift summary
CREATE VIEW IF NOT EXISTS calibration_drift_summary AS
SELECT task_class, confidence_bucket,
       empirical_pass_rate, expected_pass_rate, drift,
       total_attempts,
       CASE
           WHEN drift > 0.15 THEN 'underconfident'
           WHEN drift < -0.15 THEN 'overconfident'
           ELSE 'calibrated'
       END as status
FROM calibration_data
WHERE total_attempts >= 10
ORDER BY ABS(drift) DESC;

-- Active regressions
CREATE VIEW IF NOT EXISTS active_regressions AS
SELECT re.*,
       af.name as affected_feature_name,
       cf.name as causing_feature_name
FROM regression_events re
JOIN features af ON af.id = re.affected_feature_id
JOIN features cf ON cf.id = re.causing_feature_id
WHERE re.status NOT IN ('resolved', 'rolled_back');

-- Flaky tests needing attention
CREATE VIEW IF NOT EXISTS flaky_tests_pending AS
SELECT t.*, f.name as feature_name,
       (SELECT COUNT(*) FROM flaky_test_runs WHERE task_id = t.id AND passed = TRUE) as pass_count,
       (SELECT COUNT(*) FROM flaky_test_runs WHERE task_id = t.id) as total_runs
FROM tasks t
JOIN features f ON f.id = t.feature_id
WHERE t.is_flaky = TRUE
AND t.status != 'completed';

-- Scope creep alerts
CREATE VIEW IF NOT EXISTS scope_creep_alerts AS
SELECT f.id, f.name,
       f.original_acceptance_criteria_count,
       (SELECT COUNT(*) FROM json_each(f.description)) as current_criteria_count,
       f.original_task_count,
       (SELECT COUNT(*) FROM tasks WHERE feature_id = f.id) as current_task_count
FROM features f
WHERE f.original_task_count > 0
AND (SELECT COUNT(*) FROM tasks WHERE feature_id = f.id) > f.original_task_count * 2;

-- NOTE: Memory/lesson conflicts handled by bob3-memory (MCP)
-- Use memory_search for retrieval, memory_get_candidates for maintenance

-- Gaming detection
CREATE VIEW IF NOT EXISTS potential_gaming AS
SELECT ch.feature_id, ch.task_id,
       ch.conf_impl_correctness,
       COUNT(*) as times_reported
FROM confidence_history ch
GROUP BY ch.feature_id, ch.task_id, ch.conf_impl_correctness
HAVING COUNT(*) >= 3;

-- Test integrity violations
CREATE VIEW IF NOT EXISTS test_integrity_violations AS
SELECT t.id, t.title, f.name as feature_name,
       t.original_assertion_count, t.current_assertion_count,
       t.original_coverage_percent, t.current_coverage_percent
FROM tasks t
JOIN features f ON f.id = t.feature_id
WHERE t.type = 'validation'
AND (
    t.current_assertion_count < t.original_assertion_count
    OR t.current_coverage_percent < t.original_coverage_percent - 5
);

-- Resource usage summary
CREATE VIEW IF NOT EXISTS resource_usage AS
SELECT p.id, p.name,
       p.total_cost_usd, p.max_cost_usd,
       (p.total_cost_usd / p.max_cost_usd) * 100 as cost_percent_used,
       (SELECT COUNT(*) FROM features WHERE project_id = p.id AND status = 'completed') as features_completed,
       (SELECT COUNT(*) FROM features WHERE project_id = p.id) as features_total
FROM projects p;

-- NOTE: All lesson views removed - lessons stored in bob3-memory (MCP)
-- Use memory_search for lesson retrieval
-- Use memory_get_candidates for demotion/archival candidates

-- Active bugs
CREATE VIEW IF NOT EXISTS active_bugs AS
SELECT bl.*, f.name as feature_name
FROM bug_ledger bl
LEFT JOIN features f ON f.id = bl.feature_id
WHERE bl.resolved = FALSE
ORDER BY bl.created_at DESC;

-- Orphaned features (parent abandoned)
CREATE VIEW IF NOT EXISTS orphaned_features AS
SELECT f.*
FROM features f
JOIN features parent ON parent.id = f.parent_feature_id
WHERE parent.status IN ('failed', 'needs_human', 'rolled_back')
AND f.status NOT IN ('completed', 'failed', 'rolled_back');

-- Oversized features needing decomposition
CREATE VIEW IF NOT EXISTS oversized_features AS
SELECT f.id, f.name, f.status,
       (SELECT COUNT(*) FROM tasks WHERE feature_id = f.id AND type = 'implementation') as impl_tasks,
       (SELECT COUNT(*) FROM tasks WHERE feature_id = f.id AND type = 'validation') as validation_tasks,
       (SELECT COUNT(*) FROM tasks WHERE feature_id = f.id) as total_tasks,
       f.estimated_lines_of_code,
       f.estimated_files_touched,
       f.estimated_complexity,
       CASE
           WHEN (SELECT COUNT(*) FROM tasks WHERE feature_id = f.id) > 10 THEN 'too_many_tasks'
           WHEN f.estimated_lines_of_code > 500 THEN 'too_many_lines'
           WHEN f.estimated_files_touched > 5 THEN 'too_many_files'
           WHEN f.estimated_complexity > 8 THEN 'too_complex'
       END as limit_exceeded
FROM features f
WHERE f.exceeds_size_limits = TRUE
   OR (SELECT COUNT(*) FROM tasks WHERE feature_id = f.id) > 10
   OR f.estimated_lines_of_code > 500
   OR f.estimated_files_touched > 5
   OR f.estimated_complexity > 8;

-- ============================================
-- BOB3-SPECIFIC TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS research_results (
    id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL REFERENCES features(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    agent_run_id TEXT REFERENCES sub_agent_runs(id),
    query TEXT NOT NULL,
    findings TEXT,
    sources TEXT,              -- JSON array of URLs
    code_examples TEXT,        -- JSON array of code snippets
    applied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reference_documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    file_path TEXT NOT NULL,
    title TEXT,
    extracted_text TEXT,
    page_count INTEGER,
    sections TEXT,             -- JSON: [{page, heading, content}, ...]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feature_references (
    feature_id TEXT NOT NULL REFERENCES features(id),
    reference_id TEXT NOT NULL REFERENCES reference_documents(id),
    section_hint TEXT,
    PRIMARY KEY (feature_id, reference_id)
);
