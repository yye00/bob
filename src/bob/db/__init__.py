"""Database connection and initialization for Bob.

Provides SQLite database access with WAL mode, foreign key enforcement,
schema initialization from schema.sql, and CRUD operations.
"""

import hashlib
import importlib.metadata
import json
import logging
import os
import pathlib
import platform
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from bob import get_package_dir
from bob.models import BugLedger, CalibrationAlert, CalibrationData, ConfidenceHistory, EvidenceArtifact, ExecutionLog, Feature, FeatureDependency, FeatureReviewIssue, FlakyTestRun, ForgettingEvent, Project, ReadinessHistory, RegressionEvent, ResourceCheckpoint, RollbackEvent, ResearchResult, ReviewHistory, ScopeChange, SubAgentRun, Task

logger = logging.getLogger(__name__)


def get_database_path() -> pathlib.Path:
    """Return the database file path.

    Uses ``BOB_DATABASE_PATH`` env var if set, otherwise defaults to
    ``Path.cwd() / "bob.db"`` so that ``bob init ./my-project`` followed
    by ``cd ./my-project`` resolves to the database created inside that
    workspace. The previous default (the package install location) was
    incorrect for any user-facing flow because pip installs land outside
    the user's project directory.
    """
    env_path = os.environ.get("BOB_DATABASE_PATH")
    if env_path:
        return pathlib.Path(env_path)
    return pathlib.Path.cwd() / "bob.db"


def get_connection(*, db_path: pathlib.Path | None = None) -> sqlite3.Connection:
    """Open and return a configured SQLite connection.

    Enables WAL journal mode and foreign key enforcement. Also sets a
    generous ``busy_timeout`` (and matching Python-level ``timeout``) so
    that concurrent ``bob run`` invocations and overlapping ``bob status``
    queries during a long ``bob run`` do not crash with
    ``OperationalError: database is locked``. With WAL the writer/reader
    contention window is small, but bursty workloads on slow disks can
    still hit it; 30s is a comfortable upper bound that keeps the loop
    correct without hanging the CLI for long if something is genuinely
    deadlocked at the OS level.
    """
    if db_path is None:
        db_path = get_database_path()
    # ``timeout`` here controls how long sqlite3 will wait when the file
    # itself is locked at connect time / for the implicit BEGIN. It is
    # complementary to PRAGMA busy_timeout (which the driver also honours
    # for subsequent statements). We set both for belt-and-suspenders
    # behaviour against concurrent bob invocations.
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database(*, db_path: pathlib.Path | None = None) -> None:
    """Initialize the database by executing schema.sql.

    Creates all tables, indexes, and views. Safe to call multiple times
    (schema uses IF NOT EXISTS).
    """
    schema_path = get_package_dir() / "schema.sql"
    schema_sql = schema_path.read_text()
    conn = get_connection(db_path=db_path)
    try:
        conn.executescript(schema_sql)
    finally:
        conn.close()


@contextmanager
def connect(*, db_path: pathlib.Path | None = None):
    """Context manager that yields a database connection.

    Commits on successful exit, rolls back on exception, and always closes.
    """
    conn = get_connection(db_path=db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================
# PROJECT CRUD OPERATIONS
# ============================================================

_PROJECT_COLUMNS = (
    "id", "name", "description", "spec_path", "workspace_path", "status",
    "total_cost_usd", "max_cost_usd", "spec_hash", "spec_last_modified",
    "environment_fingerprint", "created_at", "updated_at",
)


def _row_to_project(row: tuple) -> Project:
    """Convert a database row tuple to a Project model."""
    data = dict(zip(_PROJECT_COLUMNS, row))
    for ts_field in ("spec_last_modified", "created_at", "updated_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    return Project(**data)


def create_project(
    *,
    name: str,
    workspace_path: str,
    description: str | None = None,
    spec_path: str | None = None,
    status: str = "planning",
    total_cost_usd: float = 0.0,
    max_cost_usd: float | None = None,
    db_path: pathlib.Path | None = None,
) -> Project:
    """Create a new project and persist it to the database.

    Returns the created Project model with generated ID and timestamps.

    Args:
        db_path: Explicit path to the SQLite database file. When supplied,
            the INSERT targets this exact file regardless of cwd or
            BOB_DATABASE_PATH. Callers that manage a specific project
            database MUST pass it here so the project row and subsequent
            agent_run rows target the same database.
    """
    # No bob-chain $ budget (operator directive): default the per-project cap to
    # BOB_MAX_COST_USD or effectively-unlimited, NOT the old hardcoded 500.0
    # that mass-NH'd every remaining feature once a long run approached it.
    if max_cost_usd is None:
        import math as _math
        import os as _os
        _raw = _os.environ.get("BOB_MAX_COST_USD", "")
        if not _raw or not _raw.strip():
            max_cost_usd = 1_000_000.0
        else:
            try:
                _val = float(_raw)
                max_cost_usd = 1_000_000.0 if (_math.isnan(_val) or _math.isinf(_val)) else max(0.0, _val)
            except ValueError:
                max_cost_usd = 1_000_000.0
    project_id = str(uuid.uuid4())
    now = datetime.now()

    with connect(db_path=db_path) as conn:
        conn.execute(
            """INSERT INTO projects
               (id, name, description, spec_path, workspace_path, status,
                total_cost_usd, max_cost_usd, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, name, description, spec_path, workspace_path,
             status, total_cost_usd, max_cost_usd, now.isoformat(), now.isoformat()),
        )

    return Project(
        id=project_id,
        name=name,
        description=description,
        spec_path=spec_path,
        workspace_path=workspace_path,
        status=status,
        total_cost_usd=total_cost_usd,
        max_cost_usd=max_cost_usd,
        created_at=now,
        updated_at=now,
    )


def get_project(project_id: str) -> Project | None:
    """Retrieve a project by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_PROJECT_COLUMNS)} FROM projects WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_project(row)


def update_project(project_id: str, **kwargs) -> Project | None:
    """Update a project's fields. Returns the updated Project or None if not found.

    Only fields provided as keyword arguments are updated.
    Allowed fields: name, description, spec_path, workspace_path, status,
    total_cost_usd, max_cost_usd, spec_hash, spec_last_modified,
    environment_fingerprint.
    """
    allowed = {
        "name", "description", "spec_path", "workspace_path", "status",
        "total_cost_usd", "max_cost_usd", "spec_hash", "spec_last_modified",
        "environment_fingerprint",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    updates["updated_at"] = datetime.now().isoformat()

    if not any(k in allowed for k in kwargs):
        # No real fields to update, but still refresh updated_at
        pass

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(project_id)

    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE projects SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_project(project_id)


def list_projects() -> list[Project]:
    """Return all projects ordered by creation time."""
    select = f"SELECT {', '.join(_PROJECT_COLUMNS)} FROM projects ORDER BY created_at ASC"
    with connect() as conn:
        cursor = conn.execute(select)
        rows = cursor.fetchall()
    return [_row_to_project(row) for row in rows]


def update_project_cost(*, project_id: str, cost_usd: float) -> Project | None:
    """Increment a project's total_cost_usd and enforce the cost limit.

    Atomically adds cost_usd to the project's total_cost_usd. If the new
    total exceeds max_cost_usd, sets the project status to 'resource_limited'.

    Args:
        project_id: The project to update.
        cost_usd: The cost to add (must be non-negative).

    Returns:
        The updated Project model, or None if the project does not exist.

    Raises:
        ValueError: If cost_usd is negative.
    """
    if cost_usd < 0:
        raise ValueError("cost_usd must be non-negative")

    now = datetime.now().isoformat()

    with connect() as conn:
        # Atomically increment total_cost_usd
        cursor = conn.execute(
            "UPDATE projects SET total_cost_usd = total_cost_usd + ?, updated_at = ? "
            "WHERE id = ?",
            (cost_usd, now, project_id),
        )
        if cursor.rowcount == 0:
            return None

        # Check if the new total exceeds the limit
        row = conn.execute(
            "SELECT total_cost_usd, max_cost_usd FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()

        if row is not None and row[0] > row[1]:
            conn.execute(
                "UPDATE projects SET status = 'resource_limited', updated_at = ? "
                "WHERE id = ?",
                (now, project_id),
            )

    return get_project(project_id)


# ============================================================
# FEATURE CRUD OPERATIONS
# ============================================================

_FEATURE_COLUMNS = (
    "id", "project_id", "parent_feature_id", "decomposition_depth",
    "name", "description", "acceptance_criteria", "status",
    "priority", "tdd_mode", "sub_agent_mode", "risk_category",
    "conf_spec_understanding", "conf_impl_correctness", "conf_test_adequacy",
    "readiness_score", "readiness_components",
    "refinement_attempts", "max_refinement_attempts",
    "last_improvement_type", "research_iterations",
    "original_acceptance_criteria_count", "original_task_count",
    "estimated_lines_of_code", "estimated_files_touched", "estimated_complexity",
    "exceeds_size_limits", "size_limit_justification",
    "reviewer_confidence_cap",
    "completion_mode", "tasks_completed", "tasks_total",
    "spec_slot",
    "spec_quality_score",
    "permanent_forward_carry",
    "parent_completed",
    "parent_status",
    "parent_completed_at",
    "parent_evidence_hash",
    "bootstrap_attempts",
    "model_tier",
    "provenance_spans",
    "test_files",
    "rtm_artifact_path",
    "created_at", "updated_at",
)


def _row_to_feature(row: tuple) -> Feature:
    """Convert a database row tuple to a Feature model."""
    data = dict(zip(_FEATURE_COLUMNS, row))
    for ts_field in ("created_at", "updated_at", "parent_completed_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    # SQLite stores booleans as 0/1, NULL as None
    for bool_field in ("exceeds_size_limits", "tdd_mode", "sub_agent_mode", "permanent_forward_carry"):
        if bool_field in data and data[bool_field] is not None:
            data[bool_field] = bool(data[bool_field])
    return Feature(**data)


def create_feature(
    *,
    project_id: str,
    name: str,
    feature_id: str | None = None,
    parent_feature_id: str | None = None,
    decomposition_depth: int = 0,
    description: str | None = None,
    acceptance_criteria: str | None = None,
    status: str = "pending",
    priority: int = 100,
    risk_category: str = "medium",
    tdd_mode: bool | None = None,
    sub_agent_mode: bool | None = None,
    spec_slot: str | None = None,
    test_files: str | None = None,
    permanent_forward_carry: bool = False,
    conf_spec_understanding: float = 0.0,
    conf_impl_correctness: float = 0.0,
    conf_test_adequacy: float = 0.0,
    readiness_score: float = 0.0,
    spec_quality_score: float | None = None,
) -> Feature:
    """Create a new feature and persist it to the database.

    Returns the created Feature model with generated ID and timestamps.
    """
    fid = feature_id or str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO features
               (id, project_id, parent_feature_id, decomposition_depth,
                name, description, acceptance_criteria, status,
                priority, tdd_mode, sub_agent_mode, risk_category, spec_slot, test_files,
                permanent_forward_carry,
                conf_spec_understanding, conf_impl_correctness, conf_test_adequacy, readiness_score,
                spec_quality_score,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fid, project_id, parent_feature_id, decomposition_depth,
             name, description, acceptance_criteria, status,
             priority, tdd_mode, sub_agent_mode, risk_category, spec_slot, test_files,
             permanent_forward_carry,
             conf_spec_understanding, conf_impl_correctness, conf_test_adequacy, readiness_score,
             spec_quality_score,
             now.isoformat(), now.isoformat()),
        )

    return Feature(
        id=fid,
        project_id=project_id,
        parent_feature_id=parent_feature_id,
        decomposition_depth=decomposition_depth,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        status=status,
        priority=priority,
        tdd_mode=tdd_mode,
        sub_agent_mode=sub_agent_mode,
        risk_category=risk_category,
        spec_slot=spec_slot,
        test_files=test_files,
        permanent_forward_carry=permanent_forward_carry,
        conf_spec_understanding=conf_spec_understanding,
        conf_impl_correctness=conf_impl_correctness,
        conf_test_adequacy=conf_test_adequacy,
        readiness_score=readiness_score,
        spec_quality_score=spec_quality_score,
        created_at=now,
        updated_at=now,
    )


def get_feature(feature_id: str) -> Feature | None:
    """Retrieve a feature by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_FEATURE_COLUMNS)} FROM features WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (feature_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_feature(row)


def update_feature(feature_id: str, **kwargs) -> Feature | None:
    """Update a feature's fields. Returns the updated Feature or None if not found.

    Only fields provided as keyword arguments are updated.
    """
    allowed = {
        "name", "description", "acceptance_criteria", "status",
        "priority", "risk_category", "parent_feature_id", "decomposition_depth",
        "conf_spec_understanding", "conf_impl_correctness", "conf_test_adequacy",
        "readiness_score", "readiness_components",
        "refinement_attempts", "max_refinement_attempts",
        "last_improvement_type", "research_iterations",
        "original_acceptance_criteria_count", "original_task_count",
        "estimated_lines_of_code", "estimated_files_touched", "estimated_complexity",
        "exceeds_size_limits", "size_limit_justification",
        "reviewer_confidence_cap",
        "completion_mode", "tasks_completed", "tasks_total",
        "spec_slot",
        "spec_quality_score",
        "permanent_forward_carry",
        "parent_completed",
        "parent_status", "parent_completed_at", "parent_evidence_hash",
        "bootstrap_attempts",
        "model_tier",
        "provenance_spans",
        "test_files",
        "rtm_artifact_path",
        "last_reap_at",
        "reap_count",
        "subagent_pid",
        "subagent_heartbeat_at",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    updates["updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(feature_id)

    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE features SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_feature(feature_id)


def list_features(
    *,
    project_id: str,
    status: str | None = None,
    parent_feature_id: str | None = None,
) -> list[Feature]:
    """Return features for a project, with optional filtering.

    Results are ordered by priority (ascending) then creation time.
    """
    conditions = ["project_id = ?"]
    params: list = [project_id]

    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    if parent_feature_id is not None:
        conditions.append("parent_feature_id = ?")
        params.append(parent_feature_id)

    where = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_FEATURE_COLUMNS)} FROM features "
        f"WHERE {where} ORDER BY priority ASC, created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_feature(row) for row in rows]


# ============================================================
# FEATURE DECOMPOSITION (F025)
# ============================================================

MAX_DECOMPOSITION_DEPTH = 3


def create_child_feature(
    *,
    parent_feature_id: str,
    project_id: str,
    name: str,
    feature_id: str | None = None,
    description: str | None = None,
    acceptance_criteria: str | None = None,
    status: str = "pending",
    priority: int = 100,
    risk_category: str = "medium",
) -> Feature:
    """Create a child feature under an existing parent feature.

    Looks up the parent to determine the decomposition_depth (parent depth + 1).
    Raises ValueError if the parent does not exist or if creating the child
    would exceed the maximum decomposition depth of 3.

    Returns the created Feature model.
    """
    parent = get_feature(parent_feature_id)
    if parent is None:
        raise ValueError(f"Parent feature '{parent_feature_id}' not found")

    child_depth = parent.decomposition_depth + 1
    if child_depth > MAX_DECOMPOSITION_DEPTH:
        raise ValueError(
            f"Maximum decomposition depth ({MAX_DECOMPOSITION_DEPTH}) exceeded. "
            f"Parent is at depth {parent.decomposition_depth}, child would be {child_depth}."
        )

    return create_feature(
        project_id=project_id,
        name=name,
        feature_id=feature_id,
        parent_feature_id=parent_feature_id,
        decomposition_depth=child_depth,
        description=description,
        acceptance_criteria=acceptance_criteria,
        status=status,
        priority=priority,
        risk_category=risk_category,
    )


def get_child_features(parent_feature_id: str) -> list[Feature]:
    """Return all direct child features of a given parent feature.

    Results are ordered by priority (ascending) then creation time.
    """
    select = (
        f"SELECT {', '.join(_FEATURE_COLUMNS)} FROM features "
        "WHERE parent_feature_id = ? ORDER BY priority ASC, created_at ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (parent_feature_id,))
        rows = cursor.fetchall()
    return [_row_to_feature(row) for row in rows]


def check_parent_completion(child_feature_id: str) -> bool:
    """Check if completing a child triggers parent feature completion.

    When a child feature is completed, checks whether ALL sibling children
    of the same parent are also completed. If so, transitions the parent
    feature from 'pending_decomposition' to 'completed'.

    Args:
        child_feature_id: The ID of the just-completed child feature.

    Returns:
        True if the parent was transitioned to 'completed', False otherwise.
    """
    child = get_feature(child_feature_id)
    if child is None or child.parent_feature_id is None:
        return False

    parent = get_feature(child.parent_feature_id)
    if parent is None:
        return False

    # Only auto-complete parents in 'pending_decomposition' status
    if parent.status != "pending_decomposition":
        return False

    # Check if ALL children of this parent are completed
    children = get_child_features(parent.id)
    if not children:
        return False

    all_completed = all(c.status == "completed" for c in children)
    if not all_completed:
        return False

    # All children completed — mark parent as completed
    update_feature(parent.id, status="completed")
    logger.info(
        "Parent feature %s auto-completed: all %d children completed",
        parent.id,
        len(children),
    )
    return True


# ============================================================
# FEATURE DEPENDENCY OPERATIONS
# ============================================================

_FEATURE_DEP_COLUMNS = (
    "feature_id", "depends_on_feature_id", "invalidated_at", "invalidation_reason",
)


def _row_to_feature_dependency(row: tuple) -> FeatureDependency:
    """Convert a database row tuple to a FeatureDependency model."""
    data = dict(zip(_FEATURE_DEP_COLUMNS, row))
    val = data.get("invalidated_at")
    if val is not None and isinstance(val, str):
        data["invalidated_at"] = datetime.fromisoformat(val)
    return FeatureDependency(**data)


def add_feature_dependency(
    *,
    feature_id: str,
    depends_on_feature_id: str,
) -> None:
    """Add a dependency between two features. Idempotent (duplicate inserts are ignored)."""
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO feature_dependencies
               (feature_id, depends_on_feature_id)
               VALUES (?, ?)""",
            (feature_id, depends_on_feature_id),
        )


def get_feature_dependencies(feature_id: str) -> list[FeatureDependency]:
    """Return the features that this feature depends on."""
    select = (
        f"SELECT {', '.join(_FEATURE_DEP_COLUMNS)} FROM feature_dependencies "
        "WHERE feature_id = ?"
    )
    with connect() as conn:
        cursor = conn.execute(select, (feature_id,))
        rows = cursor.fetchall()
    return [_row_to_feature_dependency(row) for row in rows]


def get_feature_dependents(feature_id: str) -> list[FeatureDependency]:
    """Return the features that depend on this feature."""
    select = (
        f"SELECT {', '.join(_FEATURE_DEP_COLUMNS)} FROM feature_dependencies "
        "WHERE depends_on_feature_id = ?"
    )
    with connect() as conn:
        cursor = conn.execute(select, (feature_id,))
        rows = cursor.fetchall()
    return [_row_to_feature_dependency(row) for row in rows]


def remove_feature_dependency(
    *,
    feature_id: str,
    depends_on_feature_id: str,
) -> None:
    """Remove a dependency between two features."""
    with connect() as conn:
        conn.execute(
            "DELETE FROM feature_dependencies WHERE feature_id = ? AND depends_on_feature_id = ?",
            (feature_id, depends_on_feature_id),
        )


def update_dependent_features_readiness(completed_feature_id: str) -> list[str]:
    """Update readiness of features that depend on the completed feature.

    When a feature completes, this function:
    1. Finds all features that depend on it
    2. For each dependent, checks if ALL its dependencies are now completed
    3. If all dependencies are satisfied, updates the feature to 'ready' status

    Args:
        completed_feature_id: The ID of the feature that just completed.

    Returns:
        List of feature IDs that were updated to 'ready' status.
    """
    updated_features = []

    with connect() as conn:
        # Find all features that depend on the completed feature
        dependents = get_feature_dependents(completed_feature_id)

        for dep in dependents:
            feature_id = dep.feature_id

            # Get all dependencies for this feature
            cursor = conn.execute(
                """
                SELECT fd.depends_on_feature_id, f.status
                FROM feature_dependencies fd
                JOIN features f ON fd.depends_on_feature_id = f.id
                WHERE fd.feature_id = ?
                """,
                (feature_id,)
            )
            dependencies = cursor.fetchall()

            if not dependencies:
                continue

            # Check if ALL dependencies are completed
            all_completed = all(dep_status == 'completed' for _, dep_status in dependencies)

            if all_completed:
                # Update this feature to ready
                # NOTE: Do NOT auto-set confidence scores to 1.0!
                # Confidence should be assessed based on feature content,
                # not just dependency completion.
                # Leave confidence at default (0.0) to trigger proper assessment.
                update_cursor = conn.execute(
                    """
                    UPDATE features
                    SET status = 'ready'
                    WHERE id = ? AND status = 'pending'
                    """,
                    (feature_id,)
                )

                if update_cursor.rowcount == 1:
                    updated_features.append(feature_id)

    return updated_features


def complete_feature_and_cascade(feature_id: str) -> list[str]:
    """Atomically mark a feature 'completed' and cascade dependents to 'ready'.

    Both the feature status update and the dependent-readiness cascade run
    inside a SINGLE ``connect()`` transaction so a process crash mid-way
    cannot leave the project in an inconsistent state where the feature is
    'completed' but its dependents stay 'pending' forever.

    The cascade logic mirrors ``update_dependent_features_readiness``: for
    each feature that depends on ``feature_id``, if all of ITS dependencies
    are now 'completed', it is transitioned from 'pending' to 'ready'.
    Confidence scores are intentionally NOT auto-set; they are assessed
    later from the feature's content.

    Args:
        feature_id: The ID of the feature that just succeeded.

    Returns:
        List of feature IDs that were transitioned to 'ready' as a result
        of the cascade. Same return shape as
        ``update_dependent_features_readiness``.
    """
    updated_features: list[str] = []
    now_iso = datetime.now().isoformat()

    with connect() as conn:
        # 1. Mark the feature itself as completed.
        cursor = conn.execute(
            "UPDATE features SET status = ?, updated_at = ? WHERE id = ?",
            ("completed", now_iso, feature_id),
        )
        if cursor.rowcount == 0:
            # Feature does not exist; nothing to cascade against.
            return updated_features

        # 2. Cascade: find features that depend on this one and check if
        # all THEIR dependencies are now completed. If so, flip from
        # 'pending' to 'ready'. Doing this on the same connection means
        # the whole thing rolls back together on any exception.
        dep_cursor = conn.execute(
            """
            SELECT feature_id, depends_on_feature_id
            FROM feature_dependencies
            WHERE depends_on_feature_id = ?
            """,
            (feature_id,),
        )
        dependents = dep_cursor.fetchall()

        for dep_row in dependents:
            dependent_feature_id = dep_row[0]

            all_deps_cursor = conn.execute(
                """
                SELECT fd.depends_on_feature_id, f.status
                FROM feature_dependencies fd
                JOIN features f ON fd.depends_on_feature_id = f.id
                WHERE fd.feature_id = ?
                """,
                (dependent_feature_id,),
            )
            dep_rows = all_deps_cursor.fetchall()
            if not dep_rows:
                continue

            all_completed = all(
                dep_status == "completed" for _, dep_status in dep_rows
            )
            if not all_completed:
                continue

            update_cursor = conn.execute(
                """
                UPDATE features
                SET status = 'ready', updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now_iso, dependent_feature_id),
            )
            if update_cursor.rowcount == 1:
                updated_features.append(dependent_feature_id)

    return updated_features


def rollback_feature_cascade(
    feature_id: str,
    *,
    target_status: str = "needs_human",
) -> list[str]:
    """Atomically roll back a previously cascaded feature completion.

    Companion to :func:`complete_feature_and_cascade`. When a feature has been
    marked completed and its dependents promoted to ``ready`` (e.g. via the
    F123 cascade in ``handle_execution_result``) but a *later* step decides
    the feature isn't actually done after all — the canonical example being a
    pre-commit hook rejecting the commit — we need to undo BOTH writes
    together. Doing them as separate transactions (``update_feature`` + a
    Python loop calling ``update_feature`` per dependent) leaves a
    partial-state window: a crash mid-loop leaves some dependents flipped
    back to ``pending`` while others remain ``ready``.

    This function performs the entire rollback inside a single
    ``connect()`` block so a process crash anywhere during the rollback
    leaves the database exactly as it was *before* the call.

    Specifically, in one transaction:
      1. The feature itself is set to ``target_status``.
      2. Every dependent that is currently in ``ready`` status because of
         the (now-being-undone) cascade is reverted to ``pending``.

    Note: only dependents in ``ready`` status are touched. Dependents that
    have already moved past ``ready`` (e.g. ``in_progress``, ``completed``)
    are intentionally left alone — flipping a running or finished feature
    back to ``pending`` would itself corrupt state.

    Args:
        feature_id: The ID of the feature whose completion is being undone.
        target_status: The status to assign to the feature itself. Defaults
            to ``"needs_human"`` since the typical caller is a hook-failure
            path where the implementation looks valid but couldn't be
            committed.

    Returns:
        List of dependent feature IDs that were reverted from ``ready`` to
        ``pending``. Empty list if the feature didn't exist or had no
        ready-state dependents.
    """
    reverted: list[str] = []
    now_iso = datetime.now().isoformat()

    with connect() as conn:
        # 1. Update the feature itself.
        cursor = conn.execute(
            "UPDATE features SET status = ?, updated_at = ? WHERE id = ?",
            (target_status, now_iso, feature_id),
        )
        if cursor.rowcount == 0:
            # No such feature — nothing to roll back. Still return cleanly
            # rather than raise; the caller is already in an error path.
            return reverted

        # 2. Find every dependent currently in 'ready' and flip it back to
        # 'pending'. The WHERE-status guard makes this idempotent and safe
        # against dependents that have already advanced past 'ready'.
        #
        # R9-010: split into SELECT-then-UPDATE rather than using SQL's
        # ``RETURNING`` clause. ``RETURNING`` requires SQLite >= 3.35.0
        # (March 2021); Python 3.11 on Ubuntu 20.04 ships with SQLite
        # 3.31.1, where ``RETURNING`` produces ``OperationalError: near
        # "RETURNING": syntax error``. Doing the SELECT first inside the
        # same ``with connect()`` block keeps the read-modify-write atomic
        # (the surrounding transaction commits on context-manager exit and
        # rolls back on exception) without depending on a newer SQLite.
        cursor = conn.execute(
            """
            SELECT id FROM features
            WHERE status = 'ready'
              AND id IN (
                  SELECT feature_id FROM feature_dependencies
                  WHERE depends_on_feature_id = ?
              )
            """,
            (feature_id,),
        )
        reverted = [row[0] for row in cursor.fetchall()]

        if reverted:
            placeholders = ",".join("?" * len(reverted))
            conn.execute(
                f"UPDATE features "
                f"SET status = 'pending', updated_at = ? "
                f"WHERE id IN ({placeholders})",
                [now_iso, *reverted],
            )

    return reverted


def find_orphaned_pending_features(project_id: str) -> list[str]:
    """Return IDs of pending features whose all dependencies are completed.

    A "pending" feature whose declared dependencies have ALL transitioned
    to 'completed' is an orphan: it should have been promoted to 'ready'
    by the cascade but wasn't (typically because of a crash between the
    feature status update and the dependent cascade in some prior version
    of the code).

    Implemented as a single SQL query (no N+1 round-trips) so it stays
    cheap on the resume-recovery scan even with thousands of pending
    features. Specifically:

    * ``EXISTS (... feature_dependencies fd ...)`` — only consider
      features that actually have at least one declared dependency. A
      'pending' feature with no deps is genuinely pending (e.g. it has
      not yet met its readiness threshold) and must be left alone.
    * ``NOT EXISTS (... dep.status != 'completed' ...)`` — every
      dependency is 'completed'. Combined with the EXISTS clause above,
      this gives "has at least one dep AND no incomplete deps".

    Args:
        project_id: The project to scan.

    Returns:
        List of feature IDs (strings) that are orphaned pending and
        ready to be promoted to 'ready'. Empty list if none.
    """
    sql = """
        SELECT f.id FROM features f
        WHERE f.project_id = ?
          AND f.status = 'pending'
          AND EXISTS (
              SELECT 1 FROM feature_dependencies fd
              WHERE fd.feature_id = f.id
          )
          AND NOT EXISTS (
              SELECT 1 FROM feature_dependencies fd
              JOIN features dep ON fd.depends_on_feature_id = dep.id
              WHERE fd.feature_id = f.id
                AND dep.status != 'completed'
          )
    """
    with connect() as conn:
        rows = conn.execute(sql, (project_id,)).fetchall()
    return [row[0] for row in rows]


def find_pending_features_without_deps(project_id: str) -> list[str]:
    """Return IDs of pending features that have no declared dependencies.

    These are root features (e.g. the ``F001`` of a freshly-planned spec)
    whose ``feature_dependencies`` table has no rows. The orchestrator's
    main-loop ``find_next_ready_feature`` queries the ``features_ready``
    view, which requires ``status='ready'`` — so a brand-new project
    where every feature was just created in ``status='pending'`` exits
    ``ALL_BLOCKED`` immediately because nothing is ever promoted.

    The companion to ``find_orphaned_pending_features`` (which only
    targets pending features with declared deps that all completed):
    together they cover every case where a feature is "ready to run"
    but lives in the wrong status column. Kept as a separate function
    so the original orphan semantic — "stuck because of a missed
    cascade" — stays unchanged and the existing F116 regression tests
    remain meaningful.

    Args:
        project_id: The project to scan.

    Returns:
        List of feature IDs (strings) that have no declared dependencies
        and are still ``status='pending'``. Empty list if none.
    """
    sql = """
        SELECT f.id FROM features f
        WHERE f.project_id = ?
          AND f.status = 'pending'
          AND NOT EXISTS (
              SELECT 1 FROM feature_dependencies fd
              WHERE fd.feature_id = f.id
          )
    """
    with connect() as conn:
        rows = conn.execute(sql, (project_id,)).fetchall()
    return [row[0] for row in rows]


def bulk_promote_features_to_ready(feature_ids: list[str]) -> int:
    """Promote a batch of pending features to 'ready' in a single transaction.

    Replaces the previous N-transaction loop in
    ``OrchestrationLoop._recover_orphaned_pending_features``. With one UPDATE
    statement guarded by ``status='pending'`` we get atomicity (all-or-nothing
    if anything goes wrong) and a single round-trip regardless of batch size.

    Only rows currently in ``status='pending'`` are touched, so the call is
    safe to retry — and so a feature that has already moved on (e.g. someone
    flipped it manually between the orphan scan and this promotion) is left
    alone rather than being yanked back to ``ready``.

    Args:
        feature_ids: IDs of features to promote. Empty list is a no-op.

    Returns:
        The number of rows actually updated (i.e. were 'pending' and matched).
    """
    if not feature_ids:
        return 0
    placeholders = ",".join("?" * len(feature_ids))
    now = datetime.now().isoformat()
    with connect() as conn:
        # Seed readiness from the EARNED spec_quality_score at promotion. A
        # feature only reaches this call after clearing the 0.85 spec-quality
        # gate, so it has demonstrably-good ACs — but the features_ready view
        # ALSO gates on readiness_score >= the risk threshold (medium 0.80).
        # Previously this UPDATE set status='ready' WITHOUT touching readiness,
        # so every promoted feature sat at readiness_score=0.0 → the view
        # returned nothing → 0 features executed despite 57 passing the gate
        # (the bob72 readiness deadlock; see memory readiness-score-deadlock).
        # Derive readiness + the three confidence sub-scores from the earned
        # spec_quality_score, floored at 0.95 so a just-passing feature clears
        # every risk threshold it qualifies for, and only RAISE (MAX) so we
        # never lower a real prior assessment.
        cur = conn.execute(
            f"UPDATE features SET status='ready', updated_at=?, "
            f"readiness_score=MAX(COALESCE(readiness_score,0), "
            f"  MAX(0.95, COALESCE(spec_quality_score,0.95))), "
            f"conf_spec_understanding=MAX(COALESCE(conf_spec_understanding,0), "
            f"  MAX(0.95, COALESCE(spec_quality_score,0.95))), "
            f"conf_impl_correctness=MAX(COALESCE(conf_impl_correctness,0), "
            f"  MAX(0.95, COALESCE(spec_quality_score,0.95))), "
            f"conf_test_adequacy=MAX(COALESCE(conf_test_adequacy,0), "
            f"  MAX(0.95, COALESCE(spec_quality_score,0.95))) "
            f"WHERE id IN ({placeholders}) AND status='pending'",
            [now, *feature_ids],
        )
        return cur.rowcount


def assess_feature_confidence(feature_id: str) -> dict[str, float]:
    """Assess confidence scores for a feature based on its description and criteria.

    This function analyzes the feature to determine:
    - conf_spec_understanding: How well-specified the feature is
    - conf_impl_correctness: Whether we have enough info to implement correctly
    - readiness_score: Overall readiness to execute

    Heuristics:
    - Features with detailed acceptance criteria score higher
    - Integration features (integrate/hook/connect) score lower (need research)
    - Features with clear technical specs score higher

    Returns:
        Dict with keys: conf_spec_understanding, conf_impl_correctness,
                       conf_test_adequacy, readiness_score
    """
    feature = get_feature(feature_id)
    if not feature:
        return {
            "conf_spec_understanding": 0.0,
            "conf_impl_correctness": 0.0,
            "conf_test_adequacy": 0.0,
            "readiness_score": 0.0,
        }

    spec_score = 0.0
    impl_score = 0.0
    test_score = 0.0

    # Parse acceptance criteria
    import json
    criteria_list = []
    if feature.acceptance_criteria:
        try:
            criteria_list = json.loads(feature.acceptance_criteria)
        except (json.JSONDecodeError, TypeError):
            criteria_list = []

    # Score based on criteria count and quality
    if len(criteria_list) >= 3:
        spec_score = 0.7  # Good criteria count
    elif len(criteria_list) >= 1:
        spec_score = 0.5
    else:
        spec_score = 0.2  # Weak spec

    # Check for integration keywords (these need research)
    description_lower = (feature.description or "").lower()
    name_lower = (feature.name or "").lower()
    integration_keywords = ["integrate", "hook", "connect", "call", "invoke", "wire"]
    is_integration = any(kw in description_lower or kw in name_lower for kw in integration_keywords)

    if is_integration:
        # Integration features need research to find hookpoints
        impl_score = 0.3  # Low confidence without research
        spec_score = min(spec_score, 0.5)  # Cap spec understanding
    else:
        # Standalone features can be implemented with good spec
        impl_score = spec_score

    # Test adequacy: assume testable if well-specified
    test_score = spec_score * 0.8

    # Readiness: derive from the DEMONSTRATED spec_quality_score the feature
    # already earned at the ready-promotion gate (the 8-metric composite), NOT
    # from the conservative min() of the AC-count heuristic. A feature that
    # passed the spec_quality gate has provably high-quality ACs; capping its
    # readiness at 0.56 (old min()-of-test_score behaviour) deadlocked every
    # such feature at 0.0 because nothing re-assessed it above the claim gate.
    # Quality is preserved: integration features still land far below the 0.80
    # medium-risk threshold (pending research), and a bare-pass composite (0.85)
    # lands just under 0.80 — only genuinely high-quality specs become claimable.
    sq = getattr(feature, "spec_quality_score", None)
    if sq is not None and sq > 0.0:
        impl_factor = 0.3 if is_integration else 0.92
        readiness = round(min(1.0, sq * impl_factor), 10)
    else:
        # No demonstrated composite yet — fall back to the AC-count heuristic.
        readiness = min(spec_score, impl_score, test_score)

    return {
        "conf_spec_understanding": spec_score,
        "conf_impl_correctness": impl_score,
        "conf_test_adequacy": test_score,
        "readiness_score": readiness,
    }


def validate_dependencies(project_id: str) -> tuple[bool, list[str]]:
    """Validate that feature dependencies form a DAG (no cycles).

    Uses DFS-based cycle detection on all features within the given project.

    Returns:
        A tuple of (is_valid, cycle) where is_valid is True if the dependency
        graph is acyclic, and cycle is a list of feature IDs forming the cycle
        (empty if no cycle exists).
    """
    with connect() as conn:
        # Get all feature IDs for this project
        cursor = conn.execute(
            "SELECT id FROM features WHERE project_id = ?", (project_id,)
        )
        feature_ids = {row[0] for row in cursor.fetchall()}

        if not feature_ids:
            return (True, [])

        # Build adjacency list: feature_id -> list of features it depends on
        cursor = conn.execute(
            "SELECT feature_id, depends_on_feature_id FROM feature_dependencies "
            "WHERE feature_id IN ({})".format(",".join("?" * len(feature_ids))),
            list(feature_ids),
        )
        adjacency: dict[str, list[str]] = {fid: [] for fid in feature_ids}
        for row in cursor.fetchall():
            adjacency[row[0]].append(row[1])

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {fid: WHITE for fid in feature_ids}
    parent: dict[str, str | None] = {fid: None for fid in feature_ids}

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        for neighbor in adjacency.get(node, []):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                # Found a cycle - reconstruct it
                cycle = [neighbor, node]
                current = parent[node]
                while current is not None and current != neighbor:
                    cycle.append(current)
                    current = parent[current]
                return cycle
            if color[neighbor] == WHITE:
                parent[neighbor] = node
                result = dfs(neighbor)
                if result is not None:
                    return result
        color[node] = BLACK
        return None

    for fid in feature_ids:
        if color[fid] == WHITE:
            cycle = dfs(fid)
            if cycle is not None:
                return (False, cycle)

    return (True, [])


def get_all_predecessors(feature_id: str) -> set[str]:
    """Get all transitive dependency predecessors of a feature.

    Returns the set of all feature IDs that the given feature transitively
    depends on (direct and indirect dependencies).
    """
    visited: set[str] = set()
    stack = [feature_id]

    with connect() as conn:
        while stack:
            current = stack.pop()
            cursor = conn.execute(
                "SELECT depends_on_feature_id FROM feature_dependencies "
                "WHERE feature_id = ?",
                (current,),
            )
            for row in cursor.fetchall():
                dep_id = row[0]
                if dep_id not in visited:
                    visited.add(dep_id)
                    stack.append(dep_id)

    return visited


# ============================================================
# SPEC-TO-FEATURES (F075)
# ============================================================


# Mapping from priority strings to integer values used by the priority column.
# Higher integer = higher priority (so "critical" sorts ahead of "low").
_PRIORITY_STRING_MAP: dict[str, int] = {
    "critical": 1000,
    "high": 500,
    "medium": 100,
    "low": 10,
}


def _coerce_priority(raw: object, default: int) -> int:
    """Coerce a priority value (int or known string) to an int.

    Accepts:
        - int / bool: returned as int (bool first because bool is an int subclass)
        - None / missing: caller passes ``default``
        - str: looked up in :data:`_PRIORITY_STRING_MAP` (case-insensitive),
          or parsed as a numeric string. Unknown strings raise ``ValueError``
          with a clear message.

    Raises:
        ValueError: If the priority is a string that is not a known label
            and not numeric.
        TypeError: If the priority is some other type entirely.
    """
    if raw is None:
        return default
    if isinstance(raw, bool):
        # bool is a subclass of int — treat True/False as ints to be safe
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        key = raw.strip().lower()
        if key in _PRIORITY_STRING_MAP:
            return _PRIORITY_STRING_MAP[key]
        # Allow numeric strings like "42"
        try:
            return int(key)
        except ValueError:
            allowed = ", ".join(sorted(_PRIORITY_STRING_MAP))
            raise ValueError(
                f"Invalid priority {raw!r}: must be an integer or one of "
                f"{{{allowed}}}"
            ) from None
    raise TypeError(
        f"Invalid priority type {type(raw).__name__}: must be int or str"
    )


def create_features_from_spec(
    *,
    project_id: str,
    spec: dict,
) -> list[Feature]:
    """Create feature records in the database from a parsed YAML spec.

    For each feature in the spec, creates a Feature row with priority and
    acceptance criteria. Then resolves depends_on references and creates
    FeatureDependency rows.

    Two YAML formats are supported:

    1. **List-of-dicts** (legacy)::

        features:
          - name: Auth
            description: ...
            depends_on: [Database]

    2. **Dict-of-dicts** (used by the shipped example specs)::

        features:
          F001:
            title: Project skeleton
            description: ...
            priority: critical
            depends_on: []
          F002:
            title: ...
            depends_on: [F001]

       In this form the YAML key ("F001") is used as the spec ID and is
       the value referenced by ``depends_on``. The human-readable feature
       name is taken from ``title`` (preferred) or ``name``.

    Priority may be an integer or one of the strings ``critical``, ``high``,
    ``medium``, ``low`` (mapped to 1000/500/100/10 — higher = sooner).
    Plain features specified as strings are also supported.

    Args:
        project_id: The project to attach features to.
        spec: The parsed YAML spec dict (may contain a 'features' key).

    Returns:
        A list of created Feature models, in spec order.

    Raises:
        ValueError: If a priority string is not recognized.
    """
    raw_features = spec.get("features")

    # Normalize to an ordered list of (spec_key, feat_value) pairs.
    # spec_key is the canonical reference used by depends_on:
    #   - dict-of-dicts: the YAML key (e.g. "F001")
    #   - list-of-dicts: the resolved feature title/name
    #   - list-of-strings: the string itself
    items: list[tuple[str | None, object]] = []
    if isinstance(raw_features, dict):
        for key, value in raw_features.items():
            items.append((str(key), value))
    elif isinstance(raw_features, list):
        for feat in raw_features:
            items.append((None, feat))
    elif raw_features is None:
        items = []
    else:
        items = []

    created: list[Feature] = []
    # Maps both the spec key (e.g. "F001") and the resolved feature name
    # to the created feature's UUID, so depends_on can reference either.
    spec_id_to_uuid: dict[str, str] = {}

    for idx, (spec_key, feat) in enumerate(items):
        default_priority = (idx + 1) * 100

        if isinstance(feat, str):
            feat_name = feat
            feat_desc = None
            feat_priority = default_priority
            feat_criteria = None
            feat_tdd_mode = None
            feat_sub_agent_mode = None
            feat_perm_carry = False
        elif isinstance(feat, dict):
            # Prefer title (used by example specs); fall back to name.
            feat_name = (
                feat.get("title")
                or feat.get("name")
                or (spec_key if spec_key is not None else f"Feature {idx + 1}")
            )
            feat_desc = feat.get("description")
            feat_priority = _coerce_priority(
                feat.get("priority"), default_priority
            )
            raw_criteria = feat.get("acceptance_criteria")
            if raw_criteria is None:
                feat_criteria = None
            elif isinstance(raw_criteria, list):
                feat_criteria = json.dumps(raw_criteria)
            else:
                # Single string criterion — wrap in a list
                feat_criteria = json.dumps([str(raw_criteria)])

            # Extract execution mode overrides from YAML
            feat_tdd_mode = feat.get("tdd_mode")
            feat_sub_agent_mode = feat.get("sub_agent_mode")
            feat_perm_carry = bool(feat.get("permanent_forward_carry", False))
        else:
            continue

        # spec_slot is the YAML dict key (e.g. "F-R1-100") in dict-of-dicts format,
        # OR the 'key' field in list-of-dicts format (PEAS extractor output).
        if spec_key is not None:
            feat_spec_slot = spec_key
        elif isinstance(feat, dict):
            feat_spec_slot = feat.get("key") or feat.get("id")
        else:
            feat_spec_slot = None

        feature = create_feature(
            project_id=project_id,
            name=feat_name,
            description=feat_desc,
            priority=feat_priority,
            acceptance_criteria=feat_criteria,
            tdd_mode=feat_tdd_mode,
            sub_agent_mode=feat_sub_agent_mode,
            spec_slot=feat_spec_slot,
            permanent_forward_carry=feat_perm_carry,
        )
        created.append(feature)
        # Both the YAML key (if any) and the resolved name resolve to this UUID.
        if spec_key is not None:
            spec_id_to_uuid[spec_key] = feature.id
        # List-of-dicts format (PEAS extractor output) carries the slot in the
        # feature's own "key"/"id" field, not the YAML mapping key; map it too so
        # depends_on references like "F-HP-009" resolve to a real UUID.
        if isinstance(feat, dict):
            for slot_field in ("key", "id"):
                slot_val = feat.get(slot_field)
                if slot_val:
                    spec_id_to_uuid[str(slot_val)] = feature.id
        if feat_spec_slot:
            spec_id_to_uuid[str(feat_spec_slot)] = feature.id
        spec_id_to_uuid[feat_name] = feature.id

    # Second pass: create dependencies. Allow depends_on entries to
    # reference either the YAML key (e.g. "F001") or the feature title.
    for idx, (_spec_key, feat) in enumerate(items):
        if not isinstance(feat, dict):
            continue
        depends_on = feat.get("depends_on") or []
        if idx >= len(created):
            continue
        feature_id = created[idx].id
        for dep_ref in depends_on:
            dep_id = spec_id_to_uuid.get(str(dep_ref))
            if dep_id is not None:
                add_feature_dependency(
                    feature_id=feature_id,
                    depends_on_feature_id=dep_id,
                )

    return created


# ============================================================
# TASK CRUD OPERATIONS
# ============================================================

_TASK_COLUMNS = (
    "id", "feature_id", "project_id", "type", "subtype", "task_class",
    "title", "description", "acceptance_criteria", "expected_outputs", "verify_script",
    "status",
    "conf_spec_understanding", "conf_impl_correctness", "conf_test_adequacy",
    "readiness_score",
    "attempts", "max_attempts",
    "is_human_authored", "original_assertion_count", "current_assertion_count",
    "original_coverage_percent", "current_coverage_percent",
    "is_flaky", "flaky_pass_rate",
    "created_at", "updated_at",
)


def _row_to_task(row: tuple) -> Task:
    """Convert a database row tuple to a Task model."""
    data = dict(zip(_TASK_COLUMNS, row))
    for ts_field in ("created_at", "updated_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    # SQLite stores booleans as 0/1
    for bool_field in ("is_human_authored", "is_flaky"):
        if bool_field in data:
            data[bool_field] = bool(data[bool_field])
    return Task(**data)


def create_task(
    *,
    feature_id: str,
    project_id: str,
    type: str,
    title: str,
    task_id: str | None = None,
    subtype: str | None = None,
    task_class: str | None = None,
    description: str | None = None,
    acceptance_criteria: str | None = None,
    expected_outputs: str | None = None,
    verify_script: str | None = None,
    status: str = "pending",
) -> Task:
    """Create a new task and persist it to the database.

    Returns the created Task model with generated ID and timestamps.
    """
    tid = task_id or str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO tasks
               (id, feature_id, project_id, type, subtype, task_class,
                title, description, acceptance_criteria, expected_outputs, verify_script,
                status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tid, feature_id, project_id, type, subtype, task_class,
             title, description, acceptance_criteria, expected_outputs, verify_script,
             status, now.isoformat(), now.isoformat()),
        )

    return Task(
        id=tid,
        feature_id=feature_id,
        project_id=project_id,
        type=type,
        subtype=subtype,
        task_class=task_class,
        title=title,
        description=description,
        acceptance_criteria=acceptance_criteria,
        expected_outputs=expected_outputs,
        verify_script=verify_script,
        status=status,
        created_at=now,
        updated_at=now,
    )


def get_task(task_id: str) -> Task | None:
    """Retrieve a task by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_TASK_COLUMNS)} FROM tasks WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (task_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_task(row)


def update_task(task_id: str, **kwargs) -> Task | None:
    """Update a task's fields. Returns the updated Task or None if not found.

    Only fields provided as keyword arguments are updated.
    """
    allowed = {
        "title", "description", "acceptance_criteria", "expected_outputs",
        "verify_script", "status", "subtype", "task_class",
        "conf_spec_understanding", "conf_impl_correctness", "conf_test_adequacy",
        "readiness_score",
        "attempts", "max_attempts",
        "is_human_authored", "original_assertion_count", "current_assertion_count",
        "original_coverage_percent", "current_coverage_percent",
        "is_flaky", "flaky_pass_rate",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    updates["updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(task_id)

    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_task(task_id)


def list_tasks(
    *,
    feature_id: str | None = None,
    project_id: str | None = None,
    status: str | None = None,
) -> list[Task]:
    """Return tasks with optional filtering by feature, project, and/or status.

    At least one of feature_id or project_id must be provided.
    Results are ordered by creation time (ascending).
    """
    if feature_id is None and project_id is None:
        raise ValueError("At least one of feature_id or project_id must be provided")

    conditions: list[str] = []
    params: list = []

    if feature_id is not None:
        conditions.append("feature_id = ?")
        params.append(feature_id)

    if project_id is not None:
        conditions.append("project_id = ?")
        params.append(project_id)

    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    where = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_TASK_COLUMNS)} FROM tasks "
        f"WHERE {where} ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_task(row) for row in rows]


# ============================================================
# TASK ATTEMPT TRACKING (F027)
# ============================================================


def increment_task_attempts(task_id: str) -> Task | None:
    """Increment the attempts counter for a task by one.

    Atomically increments the attempts field in the database and returns
    the updated Task. Returns None if the task does not exist.
    """
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE tasks SET attempts = attempts + 1, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task_id),
        )
        if cursor.rowcount == 0:
            return None

    return get_task(task_id)


def check_task_attempt_limit(task_id: str) -> bool | None:
    """Check whether a task has reached or exceeded its max attempts.

    Returns True if attempts >= max_attempts, False if still within limit,
    or None if the task does not exist.
    """
    task = get_task(task_id)
    if task is None:
        return None
    return task.attempts >= task.max_attempts


# ============================================================
# FEATURE REFINEMENT TRACKING (F024)
# ============================================================


def increment_refinement_attempts(feature_id: str) -> Feature | None:
    """Increment the refinement_attempts counter for a feature by one.

    Atomically increments the refinement_attempts field in the database.
    If the new count reaches or exceeds max_refinement_attempts, the
    feature's status is automatically set to 'needs_human'.

    Returns the updated Feature, or None if the feature does not exist.
    """
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE features SET refinement_attempts = refinement_attempts + 1, "
            "updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), feature_id),
        )
        if cursor.rowcount == 0:
            return None

    # Check if the limit has been reached and update status if needed
    feature = get_feature(feature_id)
    if feature is not None and feature.refinement_attempts >= feature.max_refinement_attempts:
        update_feature(feature_id, status="needs_human")
        feature = get_feature(feature_id)

    return feature


def check_refinement_limit(feature_id: str) -> bool | None:
    """Check whether a feature has reached or exceeded its max refinement attempts.

    Returns True if refinement_attempts >= max_refinement_attempts,
    False if still within the limit, or None if the feature does not exist.
    """
    feature = get_feature(feature_id)
    if feature is None:
        return None
    return feature.refinement_attempts >= feature.max_refinement_attempts


# ============================================================
# FEATURE SIZE LIMIT CHECKING (F026)
# ============================================================

SIZE_LIMITS = {
    "estimated_lines_of_code": 500,
    "estimated_files_touched": 5,
    "estimated_complexity": 8,
}


def check_feature_size(feature_id: str) -> dict | None:
    """Check whether a feature exceeds size limits.

    Evaluates the feature's estimated_lines_of_code, estimated_files_touched,
    and estimated_complexity against their respective thresholds (500, 5, 8).
    A feature exceeds size limits if ANY estimate exceeds its threshold.
    None/unset estimates are treated as within limits.

    Persists the exceeds_size_limits flag and size_limit_justification to the
    database.

    Returns a dict with keys:
        - exceeds_size_limits: bool
        - violations: list of dicts with 'field', 'value', 'limit'
        - estimated_lines_of_code: int | None
        - estimated_files_touched: int | None
        - estimated_complexity: int | None

    Returns None if the feature does not exist.
    """
    feature = get_feature(feature_id)
    if feature is None:
        return None

    violations = []
    estimates = {
        "estimated_lines_of_code": feature.estimated_lines_of_code,
        "estimated_files_touched": feature.estimated_files_touched,
        "estimated_complexity": feature.estimated_complexity,
    }

    for field, limit in SIZE_LIMITS.items():
        value = estimates[field]
        if value is not None and value > limit:
            violations.append({"field": field, "value": value, "limit": limit})

    exceeds = len(violations) > 0

    # Build justification string
    if exceeds:
        parts = [
            f"{v['field']}={v['value']} exceeds limit of {v['limit']}"
            for v in violations
        ]
        justification = "; ".join(parts)
    else:
        justification = None

    # Persist to database
    update_feature(
        feature_id,
        exceeds_size_limits=exceeds,
        size_limit_justification=justification,
    )

    return {
        "exceeds_size_limits": exceeds,
        "violations": violations,
        "estimated_lines_of_code": feature.estimated_lines_of_code,
        "estimated_files_touched": feature.estimated_files_touched,
        "estimated_complexity": feature.estimated_complexity,
    }


# ============================================================
# READY FEATURES VIEW QUERY (F023)
# ============================================================


def get_ready_features(project_id: str) -> list[Feature]:
    """Return features that are ready for implementation, ordered by priority.

    Queries the features_ready view which filters for:
    - status = 'ready'
    - readiness_score >= risk-category threshold
    - no active reviewer vetoes
    - all dependencies completed

    Results are scoped to the given project and ordered by priority ASC,
    then created_at ASC.
    """
    select = (
        f"SELECT {', '.join(_FEATURE_COLUMNS)} FROM features_ready "
        "WHERE project_id = ? ORDER BY priority ASC, created_at ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [_row_to_feature(row) for row in rows]


# ============================================================
# READINESS CALCULATION (F022)
# ============================================================

RISK_THRESHOLDS: dict[str, float] = {
    "low": 0.70,
    "medium": 0.80,
    "high": 0.90,
    "critical": 0.95,
}


def calculate_readiness(feature_id: str) -> dict | None:
    """Calculate feature readiness based on risk category thresholds.

    Computes a composite readiness score from the three confidence dimensions
    (spec_understanding, impl_correctness, test_adequacy), compares it against
    the threshold for the feature's risk category, and persists the result.

    Returns a dict with keys:
        - readiness_score: float (composite score, 0.0-1.0)
        - is_ready: bool (whether score meets threshold)
        - threshold: float (required threshold for this risk category)
        - components: dict with spec_understanding, impl_correctness, test_adequacy

    Returns None if the feature does not exist.
    """
    feature = get_feature(feature_id)
    if feature is None:
        return None

    components = {
        "spec_understanding": feature.conf_spec_understanding,
        "impl_correctness": feature.conf_impl_correctness,
        "test_adequacy": feature.conf_test_adequacy,
    }

    readiness_score = round(
        (
            components["spec_understanding"]
            + components["impl_correctness"]
            + components["test_adequacy"]
        )
        / 3.0,
        10,
    )

    threshold = RISK_THRESHOLDS.get(feature.risk_category, 0.80)
    is_ready = readiness_score >= threshold

    # Persist to database
    update_feature(
        feature_id,
        readiness_score=readiness_score,
        readiness_components=json.dumps(components),
    )

    return {
        "readiness_score": readiness_score,
        "is_ready": is_ready,
        "threshold": threshold,
        "components": components,
    }


# ============================================================
# EVIDENCE ARTIFACT CRUD OPERATIONS (F014)
# ============================================================

_EVIDENCE_COLUMNS = (
    "id", "project_id", "feature_id", "task_id", "attempt_number",
    "type", "content",
    "output_hash", "reproducible", "verification_run_at", "verification_passed",
    "is_current", "iteration_created",
    "environment_fingerprint", "environment_matches_current",
    "created_at",
)


def _row_to_evidence(row: tuple) -> EvidenceArtifact:
    """Convert a database row tuple to an EvidenceArtifact model."""
    data = dict(zip(_EVIDENCE_COLUMNS, row))
    for ts_field in ("verification_run_at", "created_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    # SQLite stores booleans as 0/1
    for bool_field in ("reproducible", "verification_passed", "is_current", "environment_matches_current"):
        if bool_field in data and data[bool_field] is not None:
            data[bool_field] = bool(data[bool_field])
    return EvidenceArtifact(**data)


def create_evidence(
    *,
    project_id: str,
    type: str,
    content: str,
    evidence_id: str | None = None,
    feature_id: str | None = None,
    task_id: str | None = None,
    attempt_number: int | None = None,
    output_hash: str | None = None,
    reproducible: bool | None = None,
    is_current: bool = True,
    iteration_created: int | None = None,
    environment_fingerprint: str | None = None,
    environment_matches_current: bool = True,
) -> EvidenceArtifact:
    """Create a new evidence artifact and persist it to the database.

    Returns the created EvidenceArtifact model with generated ID and timestamp.
    """
    eid = evidence_id or str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO evidence_artifacts
               (id, project_id, feature_id, task_id, attempt_number,
                type, content,
                output_hash, reproducible,
                is_current, iteration_created,
                environment_fingerprint, environment_matches_current,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (eid, project_id, feature_id, task_id, attempt_number,
             type, content,
             output_hash, reproducible,
             is_current, iteration_created,
             environment_fingerprint, environment_matches_current,
             now.isoformat()),
        )

    return EvidenceArtifact(
        id=eid,
        project_id=project_id,
        feature_id=feature_id,
        task_id=task_id,
        attempt_number=attempt_number,
        type=type,
        content=content,
        output_hash=output_hash,
        reproducible=reproducible,
        is_current=is_current,
        iteration_created=iteration_created,
        environment_fingerprint=environment_fingerprint,
        environment_matches_current=environment_matches_current,
        created_at=now,
    )


def get_evidence(evidence_id: str) -> EvidenceArtifact | None:
    """Retrieve an evidence artifact by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_EVIDENCE_COLUMNS)} FROM evidence_artifacts WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (evidence_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_evidence(row)


def update_evidence(evidence_id: str, **kwargs) -> EvidenceArtifact | None:
    """Update an evidence artifact's fields. Returns the updated artifact or None if not found.

    Only fields provided as keyword arguments are updated.
    Allowed fields: is_current, output_hash, reproducible, verification_run_at,
    verification_passed, environment_fingerprint, environment_matches_current.
    """
    allowed = {
        "is_current", "output_hash", "reproducible",
        "verification_run_at", "verification_passed",
        "environment_fingerprint", "environment_matches_current",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}

    if not updates:
        return get_evidence(evidence_id)

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(evidence_id)

    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE evidence_artifacts SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_evidence(evidence_id)


def query_evidence(
    *,
    project_id: str | None = None,
    feature_id: str | None = None,
    task_id: str | None = None,
    is_current: bool | None = None,
) -> list[EvidenceArtifact]:
    """Query evidence artifacts with optional filtering.

    At least one of project_id, feature_id, or task_id must be provided.
    Results are ordered by creation time (ascending).
    """
    if project_id is None and feature_id is None and task_id is None:
        raise ValueError(
            "At least one of project_id, feature_id, or task_id must be provided"
        )

    conditions: list[str] = []
    params: list = []

    if project_id is not None:
        conditions.append("project_id = ?")
        params.append(project_id)

    if feature_id is not None:
        conditions.append("feature_id = ?")
        params.append(feature_id)

    if task_id is not None:
        conditions.append("task_id = ?")
        params.append(task_id)

    if is_current is not None:
        conditions.append("is_current = ?")
        params.append(is_current)

    where = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_EVIDENCE_COLUMNS)} FROM evidence_artifacts "
        f"WHERE {where} ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_evidence(row) for row in rows]


# ============================================================
# EVIDENCE VERIFICATION (F030)
# ============================================================


@dataclass
class VerificationResult:
    """Result of an evidence verification check."""

    evidence_id: str
    verified: bool
    expected_hash: str | None = None
    actual_hash: str | None = None
    reason: str | None = None


def _compute_hash(content: str) -> str:
    """Compute SHA256 hash of content string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def create_evidence_with_hash(
    *,
    project_id: str,
    type: str,
    content: str,
    evidence_id: str | None = None,
    feature_id: str | None = None,
    task_id: str | None = None,
    attempt_number: int | None = None,
    is_current: bool = True,
    iteration_created: int | None = None,
    environment_fingerprint: str | None = None,
    environment_matches_current: bool = True,
) -> EvidenceArtifact:
    """Create a new evidence artifact with an automatically computed SHA256 hash.

    Computes SHA256 of the content and stores it as output_hash.
    """
    output_hash = _compute_hash(content)
    return create_evidence(
        project_id=project_id,
        type=type,
        content=content,
        evidence_id=evidence_id,
        feature_id=feature_id,
        task_id=task_id,
        attempt_number=attempt_number,
        output_hash=output_hash,
        is_current=is_current,
        iteration_created=iteration_created,
        environment_fingerprint=environment_fingerprint,
        environment_matches_current=environment_matches_current,
    )


def verify_evidence(evidence_id: str) -> VerificationResult | None:
    """Verify an evidence artifact by recomputing its content hash.

    Returns None if the evidence does not exist.
    Returns a VerificationResult with verified=False and reason='no_hash' if
    the evidence has no stored output_hash.
    Otherwise recomputes the hash and compares it to the stored hash,
    updating verification_passed and verification_run_at in the database.
    """
    evidence = get_evidence(evidence_id)
    if evidence is None:
        return None

    if evidence.output_hash is None:
        return VerificationResult(
            evidence_id=evidence_id,
            verified=False,
            reason="no_hash",
        )

    actual_hash = _compute_hash(evidence.content)
    verified = actual_hash == evidence.output_hash
    now = datetime.now().isoformat()

    update_evidence(
        evidence_id,
        verification_passed=verified,
        verification_run_at=now,
    )

    return VerificationResult(
        evidence_id=evidence_id,
        verified=verified,
        expected_hash=evidence.output_hash,
        actual_hash=actual_hash,
    )


def check_reproducibility(evidence_id: str, new_content: str) -> bool | None:
    """Check if evidence is reproducible by comparing hashes of new content.

    Returns None if the evidence does not exist or has no stored hash.
    Returns True if the new content hash matches the stored hash, False otherwise.
    Updates the reproducible field on the evidence artifact.
    """
    evidence = get_evidence(evidence_id)
    if evidence is None:
        return None

    if evidence.output_hash is None:
        return None

    new_hash = _compute_hash(new_content)
    reproducible = new_hash == evidence.output_hash

    update_evidence(evidence_id, reproducible=reproducible)

    return reproducible


# ============================================================
# EVIDENCE STALENESS DETECTION (F031)
# ============================================================


def get_current_iteration(*, feature_id: str) -> int:
    """Return the maximum iteration_created for a feature's evidence.

    Returns 0 if no evidence exists or all have NULL iteration_created.
    """
    with connect() as conn:
        cursor = conn.execute(
            "SELECT COALESCE(MAX(iteration_created), 0) "
            "FROM evidence_artifacts WHERE feature_id = ?",
            (feature_id,),
        )
        row = cursor.fetchone()
    return row[0]


def mark_evidence_stale(
    *,
    feature_id: str,
    current_iteration: int,
    staleness_threshold: int = 2,
) -> int:
    """Mark evidence as stale (is_current=FALSE) when its iteration falls behind.

    Evidence is considered stale when:
        current_iteration - iteration_created > staleness_threshold

    Only affects evidence that is currently marked is_current=TRUE and has a
    non-NULL iteration_created value.

    Returns the number of evidence artifacts marked stale.
    """
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE evidence_artifacts "
            "SET is_current = FALSE "
            "WHERE feature_id = ? "
            "AND is_current = TRUE "
            "AND iteration_created IS NOT NULL "
            "AND (? - iteration_created) > ?",
            (feature_id, current_iteration, staleness_threshold),
        )
        return cursor.rowcount


# ============================================================
# ENVIRONMENT FINGERPRINTING (F032)
# ============================================================


def compute_environment_fingerprint() -> str:
    """Compute a JSON fingerprint of the current execution environment.

    Captures Python version, OS information, and a hash of installed
    package distributions for environment comparison.

    Returns a deterministic JSON string (sorted keys) containing:
    - python_version: e.g. "3.13.1"
    - python_implementation: e.g. "CPython"
    - os_system: e.g. "Linux"
    - os_release: kernel/OS release string
    - os_machine: e.g. "x86_64"
    - deps_hash: SHA256 of sorted installed package name==version pairs
    """
    # Collect installed package versions for dependency hashing
    dists = sorted(
        f"{d.metadata['Name']}=={d.version}"
        for d in importlib.metadata.distributions()
        if d.metadata["Name"]
    )
    deps_hash = hashlib.sha256("\n".join(dists).encode("utf-8")).hexdigest()

    fingerprint = {
        "deps_hash": deps_hash,
        "os_machine": platform.machine(),
        "os_release": platform.release(),
        "os_system": platform.system(),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
    }

    return json.dumps(fingerprint, sort_keys=True)


def compare_environments(
    current_fingerprint: str,
    evidence_fingerprint: str,
) -> dict:
    """Compare two environment fingerprints and report differences.

    Args:
        current_fingerprint: JSON fingerprint of the current environment.
        evidence_fingerprint: JSON fingerprint stored with an evidence artifact.

    Returns a dict with:
        match: bool - True if fingerprints are identical
        differences: dict - keys that differ, each mapping to
            {"current": ..., "evidence": ...}
    """
    current = json.loads(current_fingerprint)
    evidence = json.loads(evidence_fingerprint)

    differences: dict[str, dict[str, str]] = {}
    all_keys = set(current) | set(evidence)

    for key in sorted(all_keys):
        cur_val = current.get(key)
        ev_val = evidence.get(key)
        if cur_val != ev_val:
            differences[key] = {"current": cur_val, "evidence": ev_val}

    return {
        "match": len(differences) == 0,
        "differences": differences,
    }


# ============================================================
# REVIEW HISTORY CRUD OPERATIONS (F015)
# ============================================================

_REVIEW_COLUMNS = (
    "id", "project_id", "feature_id",
    "reviewer_id", "reviewer_type", "reviewer_seniority",
    "verdict",
    "confidence_cap", "veto_active",
    "issues_flagged", "required_validations", "notes",
    "issues_resolved", "resolved_at",
    "review_requested_at", "review_timeout_hours", "timeout_action_taken",
    "created_at",
)


def _row_to_review(row: tuple) -> ReviewHistory:
    """Convert a database row tuple to a ReviewHistory model."""
    data = dict(zip(_REVIEW_COLUMNS, row))
    for ts_field in ("resolved_at", "review_requested_at", "created_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    # SQLite stores booleans as 0/1
    if "veto_active" in data and data["veto_active"] is not None:
        data["veto_active"] = bool(data["veto_active"])
    return ReviewHistory(**data)


def create_review(
    *,
    project_id: str,
    feature_id: str,
    reviewer_id: str,
    review_id: str | None = None,
    reviewer_type: str = "human",
    reviewer_seniority: int = 0,
    confidence_cap: float | None = None,
    notes: str | None = None,
    review_timeout_hours: int = 48,
) -> ReviewHistory:
    """Create a new review entry and persist it to the database.

    Returns the created ReviewHistory model with generated ID and timestamps.
    """
    rid = review_id or str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO review_history
               (id, project_id, feature_id,
                reviewer_id, reviewer_type, reviewer_seniority,
                confidence_cap, notes,
                review_requested_at, review_timeout_hours,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rid, project_id, feature_id,
             reviewer_id, reviewer_type, reviewer_seniority,
             confidence_cap, notes,
             now.isoformat(), review_timeout_hours,
             now.isoformat()),
        )

    return ReviewHistory(
        id=rid,
        project_id=project_id,
        feature_id=feature_id,
        reviewer_id=reviewer_id,
        reviewer_type=reviewer_type,
        reviewer_seniority=reviewer_seniority,
        confidence_cap=confidence_cap,
        notes=notes,
        review_requested_at=now,
        review_timeout_hours=review_timeout_hours,
        created_at=now,
    )


def get_review(review_id: str) -> ReviewHistory | None:
    """Retrieve a review by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_REVIEW_COLUMNS)} FROM review_history WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (review_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_review(row)


def update_review_verdict(
    review_id: str,
    *,
    verdict: str,
    veto_active: bool | None = None,
    issues_flagged: str | None = None,
    required_validations: str | None = None,
    confidence_cap: float | None = None,
    timeout_action_taken: str | None = None,
) -> ReviewHistory | None:
    """Update a review's verdict and related fields.

    Returns the updated ReviewHistory or None if the review does not exist.
    """
    updates: dict[str, object] = {"verdict": verdict}

    if veto_active is not None:
        updates["veto_active"] = veto_active
    if issues_flagged is not None:
        updates["issues_flagged"] = issues_flagged
    if required_validations is not None:
        updates["required_validations"] = required_validations
    if confidence_cap is not None:
        updates["confidence_cap"] = confidence_cap
    if timeout_action_taken is not None:
        updates["timeout_action_taken"] = timeout_action_taken

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(review_id)

    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE review_history SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_review(review_id)


def get_pending_reviews(
    *,
    project_id: str,
    feature_id: str | None = None,
) -> list[ReviewHistory]:
    """Return reviews with NULL verdict (pending), ordered by review_requested_at.

    Filters by project_id, and optionally by feature_id.
    """
    conditions = ["project_id = ?", "verdict IS NULL"]
    params: list = [project_id]

    if feature_id is not None:
        conditions.append("feature_id = ?")
        params.append(feature_id)

    where = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_REVIEW_COLUMNS)} FROM review_history "
        f"WHERE {where} ORDER BY review_requested_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_review(row) for row in rows]


def request_review(
    *,
    project_id: str,
    feature_id: str,
    reviewer_id: str,
    review_id: str | None = None,
    reviewer_type: str = "human",
    reviewer_seniority: int = 0,
    confidence_cap: float | None = None,
    notes: str | None = None,
    review_timeout_hours: int = 48,
) -> ReviewHistory:
    """Request a review for a feature, creating a review_history record.

    Validates that the project and feature exist, then creates a new
    review_history record with verdict=NULL, sets review_requested_at
    to the current timestamp, assigns the reviewer, and starts timeout
    tracking.

    Args:
        project_id: ID of the project containing the feature.
        feature_id: ID of the feature to review.
        reviewer_id: ID of the assigned reviewer.
        review_id: Optional custom review ID.
        reviewer_type: Type of reviewer ("human" or "automated").
        reviewer_seniority: Seniority level of the reviewer (0-10).
        confidence_cap: Optional confidence cap imposed by reviewer.
        notes: Optional notes for the reviewer.
        review_timeout_hours: Hours before review times out (default 48).

    Returns:
        The created ReviewHistory record.

    Raises:
        ValueError: If the project or feature does not exist.
    """
    project = get_project(project_id)
    if project is None:
        raise ValueError(f"Project '{project_id}' not found")

    feature = get_feature(feature_id)
    if feature is None:
        raise ValueError(f"Feature '{feature_id}' not found")

    return create_review(
        project_id=project_id,
        feature_id=feature_id,
        reviewer_id=reviewer_id,
        review_id=review_id,
        reviewer_type=reviewer_type,
        reviewer_seniority=reviewer_seniority,
        confidence_cap=confidence_cap,
        notes=notes,
        review_timeout_hours=review_timeout_hours,
    )


def get_timed_out_reviews(
    *,
    project_id: str,
) -> list[ReviewHistory]:
    """Return pending reviews that have exceeded their timeout period.

    Finds reviews where verdict IS NULL and the elapsed hours since
    review_requested_at exceed review_timeout_hours.
    """
    select = (
        f"SELECT {', '.join(_REVIEW_COLUMNS)} FROM review_history "
        "WHERE project_id = ? AND verdict IS NULL "
        "AND (julianday('now') - julianday(review_requested_at)) * 24 > review_timeout_hours "
        "ORDER BY review_requested_at ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [_row_to_review(row) for row in rows]


# ============================================================
# REVIEW TIMEOUT DETECTION AND HANDLING (F036)
# ============================================================


def check_review_timeouts(
    *,
    project_id: str,
) -> list[ReviewHistory]:
    """Check for timed-out reviews and take appropriate action.

    Queries pending reviews that have exceeded their review_timeout_hours,
    and have not already had a timeout action taken.

    For low/medium risk features: auto-approves the review
    (verdict='approve', timeout_action_taken='auto_approved').

    For high/critical risk features: escalates to human
    (timeout_action_taken='escalated', feature status set to 'needs_human').

    Returns:
        List of ReviewHistory models that were processed.
    """
    # Find timed-out reviews that haven't been actioned yet.
    # We need the feature's risk_category so we join features.
    select = (
        f"SELECT {', '.join('r.' + c for c in _REVIEW_COLUMNS)}, f.risk_category "
        "FROM review_history r "
        "JOIN features f ON f.id = r.feature_id "
        "WHERE r.project_id = ? "
        "AND r.verdict IS NULL "
        "AND r.timeout_action_taken IS NULL "
        "AND (julianday('now') - julianday(r.review_requested_at)) * 24 > r.review_timeout_hours "
        "ORDER BY r.review_requested_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()

    processed: list[ReviewHistory] = []

    for row in rows:
        # Last column is risk_category from the join
        risk_category = row[-1]
        review = _row_to_review(row[:-1])

        if risk_category in ("low", "medium"):
            # Auto-approve
            updated = update_review_verdict(
                review.id,
                verdict="approve",
                timeout_action_taken="auto_approved",
            )
            if updated is not None:
                processed.append(updated)
        elif risk_category in ("high", "critical"):
            # Escalate to human
            with connect() as conn:
                conn.execute(
                    "UPDATE review_history SET timeout_action_taken = ? WHERE id = ?",
                    ("escalated", review.id),
                )
            # Update feature status to needs_human
            update_feature(review.feature_id, status="needs_human")
            updated = get_review(review.id)
            if updated is not None:
                processed.append(updated)

    return processed


# ============================================================
# REVIEW VERDICT RECORDING (F034)
# ============================================================

_VALID_VERDICTS = {"approve", "request_changes", "block"}

_VERDICT_TO_FEATURE_STATUS = {
    "approve": "ready",
    "request_changes": "refining",
    "block": "blocked_by_reviewer",
}


def record_verdict(
    review_id: str,
    *,
    verdict: str,
    issues_flagged: str | None = None,
    required_validations: str | None = None,
    confidence_cap: float | None = None,
) -> ReviewHistory | None:
    """Record a reviewer's verdict on a review and update the associated feature.

    This is the high-level function for recording review verdicts. It:
    1. Validates the verdict is one of: approve, request_changes, block
    2. Sets veto_active=True automatically for 'block' verdicts
    3. Updates the review record with the verdict and optional fields
    4. Updates the associated feature's status based on the verdict
    5. If confidence_cap is provided on approve, updates the feature's
       reviewer_confidence_cap

    Args:
        review_id: ID of the review to update.
        verdict: One of 'approve', 'request_changes', or 'block'.
        issues_flagged: Optional JSON array of issues found.
        required_validations: Optional JSON array of required validations.
        confidence_cap: Optional confidence cap imposed by reviewer.

    Returns:
        The updated ReviewHistory, or None if the review does not exist.

    Raises:
        ValueError: If verdict is not one of the valid values.
    """
    if verdict not in _VALID_VERDICTS:
        raise ValueError(
            f"Invalid verdict '{verdict}'. Must be one of: {', '.join(sorted(_VALID_VERDICTS))}"
        )

    # Look up the review to get the feature_id
    review = get_review(review_id)
    if review is None:
        return None

    # Automatically set veto_active for block verdicts
    veto_active = verdict == "block"

    # Update the review record
    updated_review = update_review_verdict(
        review_id,
        verdict=verdict,
        veto_active=veto_active,
        issues_flagged=issues_flagged,
        required_validations=required_validations,
        confidence_cap=confidence_cap,
    )

    # Update the feature status based on verdict
    feature_status = _VERDICT_TO_FEATURE_STATUS[verdict]
    feature_updates: dict[str, object] = {"status": feature_status}

    # If approving with a confidence cap, update the feature's reviewer_confidence_cap
    if verdict == "approve" and confidence_cap is not None:
        feature_updates["reviewer_confidence_cap"] = confidence_cap

    update_feature(review.feature_id, **feature_updates)

    return updated_review


# ============================================================
# REVIEWER SENIORITY & SENIOR_WINS POLICY (F037)
# ============================================================


def get_feature_reviews(*, feature_id: str) -> list[ReviewHistory]:
    """Return all reviews for a given feature, ordered by created_at ASC.

    Args:
        feature_id: ID of the feature to get reviews for.

    Returns:
        List of ReviewHistory records for the feature.
    """
    select = (
        f"SELECT {', '.join(_REVIEW_COLUMNS)} FROM review_history "
        "WHERE feature_id = ? ORDER BY created_at ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (feature_id,))
        rows = cursor.fetchall()
    return [_row_to_review(row) for row in rows]


def resolve_conflicting_reviews(*, feature_id: str) -> ReviewHistory | None:
    """Apply the senior_wins policy to resolve conflicting reviews.

    When multiple reviews exist for a feature with different verdicts,
    the review from the reviewer with the highest seniority wins.
    If seniority is tied, the most recently created review wins.

    Only reviews that have a verdict (not NULL) are considered.

    After determining the winner, updates the feature's status to match
    the winning verdict.

    Args:
        feature_id: ID of the feature with conflicting reviews.

    Returns:
        The winning ReviewHistory, or None if no reviews with verdicts exist.
    """
    # Get all reviews with verdicts, ordered by seniority DESC then created_at DESC
    select = (
        f"SELECT {', '.join(_REVIEW_COLUMNS)} FROM review_history "
        "WHERE feature_id = ? AND verdict IS NOT NULL "
        "ORDER BY reviewer_seniority DESC, created_at DESC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (feature_id,))
        rows = cursor.fetchall()

    if not rows:
        return None

    # The first row is the winner (highest seniority, latest if tied)
    winner = _row_to_review(rows[0])

    # Apply the winning verdict to the feature status
    feature_status = _VERDICT_TO_FEATURE_STATUS.get(winner.verdict)
    if feature_status is not None:
        update_feature(feature_id, status=feature_status)

    return winner


# ============================================================
# REVIEW ISSUE TRACKING (F035)
# ============================================================

_REVIEW_ISSUE_COLUMNS = (
    "id", "feature_id", "review_id",
    "issue_description", "severity",
    "resolved", "resolved_by_attempt", "resolution_evidence",
    "created_at", "resolved_at",
)


def _row_to_review_issue(row: tuple) -> FeatureReviewIssue:
    """Convert a database row tuple to a FeatureReviewIssue model."""
    data = dict(zip(_REVIEW_ISSUE_COLUMNS, row))
    for ts_field in ("created_at", "resolved_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    if "resolved" in data and data["resolved"] is not None:
        data["resolved"] = bool(data["resolved"])
    return FeatureReviewIssue(**data)


def create_review_issue(
    *,
    feature_id: str,
    review_id: str,
    issue_description: str,
    severity: str = "medium",
    issue_id: str | None = None,
) -> FeatureReviewIssue:
    """Create a new review issue and persist it to the database.

    Returns the created FeatureReviewIssue model with generated ID and timestamps.
    """
    iid = issue_id or str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO feature_review_issues
               (id, feature_id, review_id, issue_description, severity, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (iid, feature_id, review_id, issue_description, severity, now.isoformat()),
        )

    return FeatureReviewIssue(
        id=iid,
        feature_id=feature_id,
        review_id=review_id,
        issue_description=issue_description,
        severity=severity,
        created_at=now,
    )


def get_review_issue(issue_id: str) -> FeatureReviewIssue | None:
    """Retrieve a review issue by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_REVIEW_ISSUE_COLUMNS)} FROM feature_review_issues WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (issue_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_review_issue(row)


def resolve_review_issue(
    issue_id: str,
    *,
    resolved_by_attempt: int | None = None,
    resolution_evidence: str | None = None,
) -> FeatureReviewIssue | None:
    """Mark a review issue as resolved with optional attempt and evidence info.

    Sets resolved=TRUE and resolved_at to the current timestamp.
    Returns the updated FeatureReviewIssue or None if not found.
    """
    now = datetime.now()
    updates: dict[str, object] = {
        "resolved": True,
        "resolved_at": now.isoformat(),
    }
    if resolved_by_attempt is not None:
        updates["resolved_by_attempt"] = resolved_by_attempt
    if resolution_evidence is not None:
        updates["resolution_evidence"] = resolution_evidence

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(issue_id)

    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE feature_review_issues SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_review_issue(issue_id)


def get_review_issues(
    *,
    review_id: str | None = None,
    feature_id: str | None = None,
) -> list[FeatureReviewIssue]:
    """Return review issues filtered by review_id and/or feature_id.

    At least one of review_id or feature_id must be provided.
    """
    conditions: list[str] = []
    params: list = []

    if review_id is not None:
        conditions.append("review_id = ?")
        params.append(review_id)
    if feature_id is not None:
        conditions.append("feature_id = ?")
        params.append(feature_id)

    where = " AND ".join(conditions) if conditions else "1=1"
    select = (
        f"SELECT {', '.join(_REVIEW_ISSUE_COLUMNS)} FROM feature_review_issues "
        f"WHERE {where} ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_review_issue(row) for row in rows]


def get_unresolved_review_issues(
    *,
    review_id: str | None = None,
    feature_id: str | None = None,
) -> list[FeatureReviewIssue]:
    """Return unresolved review issues filtered by review_id and/or feature_id."""
    conditions: list[str] = ["resolved = 0"]
    params: list = []

    if review_id is not None:
        conditions.append("review_id = ?")
        params.append(review_id)
    if feature_id is not None:
        conditions.append("feature_id = ?")
        params.append(feature_id)

    where = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_REVIEW_ISSUE_COLUMNS)} FROM feature_review_issues "
        f"WHERE {where} ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_review_issue(row) for row in rows]


# ============================================================
# BUG LEDGER CRUD OPERATIONS (F018)
# ============================================================

_BUG_COLUMNS = (
    "id", "project_id", "feature_id", "task_id",
    "error_type", "error_message", "error_context",
    "evidence_artifacts",
    "blame_target", "root_cause", "fix_action", "fix_details", "fix_evidence",
    "resolved", "resolution_attempts",
    "titans_memory_id",
    "created_at", "resolved_at",
)


def _row_to_bug(row: tuple) -> BugLedger:
    """Convert a database row tuple to a BugLedger model."""
    data = dict(zip(_BUG_COLUMNS, row))
    for ts_field in ("created_at", "resolved_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    # SQLite stores booleans as 0/1
    if "resolved" in data and data["resolved"] is not None:
        data["resolved"] = bool(data["resolved"])
    return BugLedger(**data)


def create_bug(
    *,
    project_id: str,
    error_type: str,
    error_message: str,
    evidence_artifacts: str,
    fix_action: str,
    bug_id: str | None = None,
    feature_id: str | None = None,
    task_id: str | None = None,
    error_context: str | None = None,
    blame_target: str | None = None,
    root_cause: str | None = None,
    fix_details: str | None = None,
    fix_evidence: str | None = None,
    titans_memory_id: str | None = None,
) -> BugLedger:
    """Create a new bug ledger entry and persist it to the database.

    Returns the created BugLedger model with generated ID and timestamp.
    """
    bid = bug_id or str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO bug_ledger
               (id, project_id, feature_id, task_id,
                error_type, error_message, error_context,
                evidence_artifacts,
                blame_target, root_cause, fix_action, fix_details, fix_evidence,
                titans_memory_id,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bid, project_id, feature_id, task_id,
             error_type, error_message, error_context,
             evidence_artifacts,
             blame_target, root_cause, fix_action, fix_details, fix_evidence,
             titans_memory_id,
             now.isoformat()),
        )

    return BugLedger(
        id=bid,
        project_id=project_id,
        feature_id=feature_id,
        task_id=task_id,
        error_type=error_type,
        error_message=error_message,
        error_context=error_context,
        evidence_artifacts=evidence_artifacts,
        blame_target=blame_target,
        root_cause=root_cause,
        fix_action=fix_action,
        fix_details=fix_details,
        fix_evidence=fix_evidence,
        titans_memory_id=titans_memory_id,
        created_at=now,
    )


def get_bug(bug_id: str) -> BugLedger | None:
    """Retrieve a bug ledger entry by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_BUG_COLUMNS)} FROM bug_ledger WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (bug_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_bug(row)


def update_bug(bug_id: str, **kwargs) -> BugLedger | None:
    """Update a bug ledger entry's fields. Returns the updated entry or None if not found.

    Only fields provided as keyword arguments are updated.
    Allowed fields: blame_target, root_cause, fix_action, fix_details,
    fix_evidence, resolution_attempts, titans_memory_id, error_context.
    """
    allowed = {
        "blame_target", "root_cause", "fix_action", "fix_details",
        "fix_evidence", "resolution_attempts", "titans_memory_id",
        "error_context",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}

    if not updates:
        return get_bug(bug_id)

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(bug_id)

    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE bug_ledger SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_bug(bug_id)


def resolve_bug(
    bug_id: str,
    *,
    fix_evidence: str | None = None,
    titans_memory_id: str | None = None,
) -> BugLedger | None:
    """Mark a bug as resolved, setting resolved=True and resolved_at timestamp.

    Optionally updates fix_evidence and titans_memory_id at the same time.
    Returns the updated BugLedger or None if the bug does not exist.
    """
    now = datetime.now()

    updates: dict[str, object] = {
        "resolved": True,
        "resolved_at": now.isoformat(),
    }
    if fix_evidence is not None:
        updates["fix_evidence"] = fix_evidence
    if titans_memory_id is not None:
        updates["titans_memory_id"] = titans_memory_id

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(bug_id)

    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE bug_ledger SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_bug(bug_id)


def list_bugs(
    *,
    project_id: str,
    feature_id: str | None = None,
    resolved: bool | None = None,
) -> list[BugLedger]:
    """Return bug ledger entries for a project, with optional filtering.

    Results are ordered by creation time (descending, newest first).
    """
    conditions = ["project_id = ?"]
    params: list = [project_id]

    if feature_id is not None:
        conditions.append("feature_id = ?")
        params.append(feature_id)

    if resolved is not None:
        conditions.append("resolved = ?")
        params.append(resolved)

    where = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_BUG_COLUMNS)} FROM bug_ledger "
        f"WHERE {where} ORDER BY created_at DESC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_bug(row) for row in rows]


def create_bug_from_rca(
    *,
    project_id: str,
    error_type: str,
    error_message: str,
    rca_result: dict,
    evidence_artifacts: str,
    feature_id: str | None = None,
    task_id: str | None = None,
    error_context: str | None = None,
    titans_memory_id: str | None = None,
) -> BugLedger:
    """Create a bug ledger entry from RCA (Root Cause Analysis) results.

    Extracts blame_target, recommended_action (as fix_action), root_cause,
    and details from the rca_result dict and creates a corresponding bug record.

    Args:
        project_id: Project this bug belongs to.
        error_type: Type of error (e.g. "test_failure", "TypeError").
        error_message: The primary error message.
        rca_result: Dict from parse_rca_result() with keys:
            blame_target, recommended_action, root_cause (optional),
            details (optional).
        evidence_artifacts: JSON array of evidence artifact IDs.
        feature_id: Optional feature ID.
        task_id: Optional task ID.
        error_context: Optional additional error context.
        titans_memory_id: Optional bob-memory ID if a lesson was created.
            (Column name is legacy; backend is now bob-memory.)

    Returns:
        The created BugLedger record.
    """
    return create_bug(
        project_id=project_id,
        feature_id=feature_id,
        task_id=task_id,
        error_type=error_type,
        error_message=error_message,
        error_context=error_context,
        evidence_artifacts=evidence_artifacts,
        blame_target=rca_result.get("blame_target"),
        root_cause=rca_result.get("root_cause"),
        fix_action=rca_result.get("recommended_action", "investigate"),
        fix_details=rca_result.get("details"),
        titans_memory_id=titans_memory_id,
    )


# ============================================================
# CALIBRATION DATA CRUD OPERATIONS (F019)
# ============================================================

_CALIBRATION_COLUMNS = (
    "id", "project_id",
    "task_class", "confidence_bucket",
    "total_attempts", "total_passes", "total_failures",
    "empirical_pass_rate", "expected_pass_rate", "drift",
    "adjusted_threshold",
    "last_updated",
)


def _row_to_calibration(row: tuple) -> CalibrationData:
    """Convert a database row tuple to a CalibrationData model."""
    data = dict(zip(_CALIBRATION_COLUMNS, row))
    val = data.get("last_updated")
    if val is not None and isinstance(val, str):
        data["last_updated"] = datetime.fromisoformat(val)
    return CalibrationData(**data)


def create_or_update_calibration(
    *,
    project_id: str | None,
    task_class: str,
    confidence_bucket: str,
    passed: bool,
    expected_pass_rate: float | None = None,
) -> CalibrationData:
    """Record a task attempt outcome for calibration tracking.

    If a calibration record already exists for the given (project_id, task_class,
    confidence_bucket) combination, it updates the counters and recalculates the
    empirical pass rate. Otherwise, it creates a new record.

    Args:
        project_id: Project ID (can be None for global calibration).
        task_class: The task class (e.g., greenfield_impl, refactor, bug_fix).
        confidence_bucket: The confidence bucket (e.g., "0.8-0.9").
        passed: Whether the task attempt passed.
        expected_pass_rate: Optional expected pass rate for drift calculation.

    Returns:
        The created or updated CalibrationData model.
    """
    now = datetime.now()

    with connect() as conn:
        # Check for existing record using the unique constraint columns
        if project_id is None:
            cursor = conn.execute(
                "SELECT id, total_attempts, total_passes, total_failures, expected_pass_rate "
                "FROM calibration_data "
                "WHERE project_id IS NULL AND task_class = ? AND confidence_bucket = ?",
                (task_class, confidence_bucket),
            )
        else:
            cursor = conn.execute(
                "SELECT id, total_attempts, total_passes, total_failures, expected_pass_rate "
                "FROM calibration_data "
                "WHERE project_id = ? AND task_class = ? AND confidence_bucket = ?",
                (project_id, task_class, confidence_bucket),
            )
        existing = cursor.fetchone()

        if existing is not None:
            # Update existing record
            existing_id, attempts, passes, failures, existing_expected = existing
            attempts += 1
            if passed:
                passes += 1
            else:
                failures += 1
            empirical = passes / attempts

            # Use new expected_pass_rate if provided, otherwise keep existing
            final_expected = expected_pass_rate if expected_pass_rate is not None else existing_expected

            conn.execute(
                "UPDATE calibration_data SET "
                "total_attempts = ?, total_passes = ?, total_failures = ?, "
                "empirical_pass_rate = ?, expected_pass_rate = ?, last_updated = ? "
                "WHERE id = ?",
                (attempts, passes, failures, empirical, final_expected, now.isoformat(), existing_id),
            )
            record_id = existing_id
        else:
            # Create new record
            record_id = str(uuid.uuid4())
            attempts = 1
            passes = 1 if passed else 0
            failures = 0 if passed else 1
            empirical = 1.0 if passed else 0.0

            conn.execute(
                """INSERT INTO calibration_data
                   (id, project_id, task_class, confidence_bucket,
                    total_attempts, total_passes, total_failures,
                    empirical_pass_rate, expected_pass_rate,
                    last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record_id, project_id, task_class, confidence_bucket,
                 attempts, passes, failures,
                 empirical, expected_pass_rate,
                 now.isoformat()),
            )

    # Fetch and return the full record
    select = f"SELECT {', '.join(_CALIBRATION_COLUMNS)} FROM calibration_data WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (record_id,))
        row = cursor.fetchone()
    return _row_to_calibration(row)


def get_calibration(
    *,
    project_id: str | None,
    task_class: str,
    confidence_bucket: str,
) -> CalibrationData | None:
    """Retrieve calibration data by composite key (project_id, task_class, confidence_bucket).

    Returns None if no matching record exists.
    """
    select = f"SELECT {', '.join(_CALIBRATION_COLUMNS)} FROM calibration_data "
    if project_id is None:
        select += "WHERE project_id IS NULL AND task_class = ? AND confidence_bucket = ?"
        params = (task_class, confidence_bucket)
    else:
        select += "WHERE project_id = ? AND task_class = ? AND confidence_bucket = ?"
        params = (project_id, task_class, confidence_bucket)

    with connect() as conn:
        cursor = conn.execute(select, params)
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_calibration(row)


def calculate_drift(
    *,
    project_id: str | None,
    task_class: str,
    confidence_bucket: str,
) -> dict | None:
    """Calculate calibration drift between empirical and expected pass rates.

    Computes drift = empirical_pass_rate - expected_pass_rate and classifies
    the direction:
    - drift > 0.15: "underconfident" (passing more than expected)
    - drift < -0.15: "overconfident" (failing more than expected)
    - otherwise: "calibrated"

    Persists the computed drift to the calibration_data record.

    Returns a dict with keys:
        - empirical_pass_rate: float
        - expected_pass_rate: float
        - drift: float
        - direction: str ("overconfident", "underconfident", or "calibrated")
        - sample_size: int

    Returns None if no calibration record exists or if expected_pass_rate
    is not set.
    """
    cal = get_calibration(
        project_id=project_id,
        task_class=task_class,
        confidence_bucket=confidence_bucket,
    )
    if cal is None:
        return None
    if cal.expected_pass_rate is None:
        return None

    drift = cal.empirical_pass_rate - cal.expected_pass_rate

    if drift > 0.15:
        direction = "underconfident"
    elif drift < -0.15:
        direction = "overconfident"
    else:
        direction = "calibrated"

    # Persist drift to database
    with connect() as conn:
        conn.execute(
            "UPDATE calibration_data SET drift = ?, last_updated = ? WHERE id = ?",
            (drift, datetime.now().isoformat(), cal.id),
        )

    return {
        "empirical_pass_rate": cal.empirical_pass_rate,
        "expected_pass_rate": cal.expected_pass_rate,
        "drift": drift,
        "direction": direction,
        "sample_size": cal.total_attempts,
    }


def _bucket_midpoint(confidence_bucket: str) -> float:
    """Compute the midpoint of a confidence bucket string like '0.8-0.9'.

    For example, '0.8-0.9' returns 0.85, '0.0-0.1' returns 0.05.
    """
    lower_str, upper_str = confidence_bucket.split("-")
    return (float(lower_str) + float(upper_str)) / 2.0


def calculate_calibration_drift(
    *,
    project_id: str | None,
    task_class: str,
    confidence_bucket: str,
) -> dict | None:
    """Calculate calibration drift using the confidence bucket midpoint as expected pass rate.

    Unlike calculate_drift() which uses a stored expected_pass_rate, this function
    derives the expected pass rate from the confidence bucket midpoint. For example,
    bucket '0.8-0.9' has an expected pass rate of 0.85.

    Computes drift = empirical_pass_rate - expected_pass_rate and classifies
    the direction:
    - drift > 0.15: "underconfident" (passing more than expected)
    - drift < -0.15: "overconfident" (failing more than expected)
    - otherwise: "calibrated"

    Persists the computed drift to the calibration_data record.

    Returns a dict with keys:
        - empirical_pass_rate: float
        - expected_pass_rate: float
        - drift: float
        - direction: str ("overconfident", "underconfident", or "calibrated")
        - sample_size: int

    Returns None if no calibration record exists for the given combination.
    """
    cal = get_calibration(
        project_id=project_id,
        task_class=task_class,
        confidence_bucket=confidence_bucket,
    )
    if cal is None:
        return None

    expected_pass_rate = _bucket_midpoint(confidence_bucket)
    drift = cal.empirical_pass_rate - expected_pass_rate

    if drift > 0.15:
        direction = "underconfident"
    elif drift < -0.15:
        direction = "overconfident"
    else:
        direction = "calibrated"

    # Persist drift to database
    with connect() as conn:
        conn.execute(
            "UPDATE calibration_data SET drift = ?, last_updated = ? WHERE id = ?",
            (drift, datetime.now().isoformat(), cal.id),
        )

    return {
        "empirical_pass_rate": cal.empirical_pass_rate,
        "expected_pass_rate": expected_pass_rate,
        "drift": drift,
        "direction": direction,
        "sample_size": cal.total_attempts,
    }


# ============================================================
# CALIBRATION RECORDING (F048)
# ============================================================


def _confidence_to_bucket(confidence: float) -> str:
    """Convert a confidence value (0.0-1.0) to a bucket string like '0.8-0.9'.

    The bucket is determined by the floor of (confidence * 10) / 10.
    For example, 0.85 -> '0.8-0.9', 0.95 -> '0.9-1.0', 1.0 -> '0.9-1.0'.
    """
    if confidence >= 1.0:
        return "0.9-1.0"
    lower = int(confidence * 10) / 10.0
    upper = lower + 0.1
    return f"{lower:.1f}-{upper:.1f}"


def record_calibration_result(
    *,
    task_id: str,
    passed: bool,
) -> CalibrationData:
    """Record a calibration result after task execution.

    Looks up the task to extract task_class and confidence (from
    conf_impl_correctness), derives the confidence_bucket, and records
    the pass/fail outcome in the calibration_data table.

    The expected_pass_rate is set to the task's conf_impl_correctness value.

    Args:
        task_id: ID of the executed task.
        passed: Whether the task execution passed.

    Returns:
        The updated CalibrationData record.

    Raises:
        ValueError: If the task does not exist or has no task_class set.
    """
    task = get_task(task_id)
    if task is None:
        raise ValueError(f"Task '{task_id}' not found")

    if not task.task_class:
        raise ValueError(
            f"Task '{task_id}' has no task_class set; cannot record calibration"
        )

    confidence_bucket = _confidence_to_bucket(task.conf_impl_correctness)

    return create_or_update_calibration(
        project_id=task.project_id,
        task_class=task.task_class,
        confidence_bucket=confidence_bucket,
        passed=passed,
        expected_pass_rate=task.conf_impl_correctness,
    )


# ============================================================
# CALIBRATION ALERT CREATION (F050)
# ============================================================

_CALIBRATION_ALERT_COLUMNS = (
    "id", "project_id",
    "task_class", "confidence_bucket",
    "drift_amount", "direction", "sample_size",
    "acknowledged", "action_taken",
    "created_at",
)


def _row_to_calibration_alert(row: tuple) -> CalibrationAlert:
    """Convert a database row tuple to a CalibrationAlert model."""
    data = dict(zip(_CALIBRATION_ALERT_COLUMNS, row))
    val = data.get("created_at")
    if val is not None and isinstance(val, str):
        data["created_at"] = datetime.fromisoformat(val)
    if data.get("acknowledged") is not None:
        data["acknowledged"] = bool(data["acknowledged"])
    return CalibrationAlert(**data)


def create_calibration_alert(
    *,
    project_id: str | None,
    task_class: str,
    confidence_bucket: str,
    drift_amount: float,
    direction: str,
    sample_size: int,
) -> CalibrationAlert:
    """Create a calibration alert for large drift.

    Stores a new alert in the calibration_alerts table when calibration
    drift exceeds the acceptable threshold (|drift| > 0.15).

    Args:
        project_id: Project ID (can be None for global).
        task_class: The task class (e.g., greenfield_impl, refactor).
        confidence_bucket: The confidence bucket (e.g., "0.8-0.9").
        drift_amount: The computed drift value.
        direction: "overconfident" or "underconfident".
        sample_size: Number of attempts in the calibration data.

    Returns:
        The created CalibrationAlert model.
    """
    alert_id = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO calibration_alerts
               (id, project_id, task_class, confidence_bucket,
                drift_amount, direction, sample_size,
                acknowledged, action_taken, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (alert_id, project_id, task_class, confidence_bucket,
             drift_amount, direction, sample_size,
             False, None, now.isoformat()),
        )

    select = f"SELECT {', '.join(_CALIBRATION_ALERT_COLUMNS)} FROM calibration_alerts WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (alert_id,))
        row = cursor.fetchone()
    return _row_to_calibration_alert(row)


def check_and_create_calibration_alert(
    *,
    project_id: str | None,
    task_class: str,
    confidence_bucket: str,
) -> CalibrationAlert | None:
    """Check calibration drift and create an alert if |drift| > 0.15.

    Calculates the calibration drift for the given combination, and if
    the absolute drift exceeds 0.15, creates and returns a CalibrationAlert.

    Args:
        project_id: Project ID (can be None for global).
        task_class: The task class.
        confidence_bucket: The confidence bucket.

    Returns:
        CalibrationAlert if drift exceeds threshold, None otherwise.
    """
    drift_result = calculate_calibration_drift(
        project_id=project_id,
        task_class=task_class,
        confidence_bucket=confidence_bucket,
    )
    if drift_result is None:
        return None

    drift = drift_result["drift"]
    if abs(drift) <= 0.15:
        return None

    return create_calibration_alert(
        project_id=project_id,
        task_class=task_class,
        confidence_bucket=confidence_bucket,
        drift_amount=drift,
        direction=drift_result["direction"],
        sample_size=drift_result["sample_size"],
    )


def list_calibration_alerts(
    *,
    project_id: str,
    unacknowledged_only: bool = False,
) -> list[CalibrationAlert]:
    """Return calibration alerts for a project.

    Args:
        project_id: ID of the project.
        unacknowledged_only: If True, only return alerts not yet acknowledged.

    Returns:
        List of CalibrationAlert models ordered by creation time (newest first).
    """
    conditions = ["project_id = ?"]
    params: list = [project_id]

    if unacknowledged_only:
        conditions.append("acknowledged = 0")

    where_clause = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_CALIBRATION_ALERT_COLUMNS)} FROM calibration_alerts "
        f"WHERE {where_clause} ORDER BY created_at DESC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_calibration_alert(row) for row in rows]


# ============================================================
# SUB-AGENT RUN CRUD OPERATIONS (F020)
# ============================================================

_AGENT_RUN_COLUMNS = (
    "id", "project_id", "parent_run_id",
    "purpose", "target_type", "target_id",
    "status",
    "prompt_summary", "result_summary",
    "rca_blame_target", "rca_recommended_action",
    "evidence_artifacts_produced",
    "improvement_type", "improvement_evidence",
    "tokens_in", "tokens_out", "cost_usd", "duration_ms",
    "mcp_enabled",
    "created_at", "completed_at",
)


def _row_to_agent_run(row: tuple) -> SubAgentRun:
    """Convert a database row tuple to a SubAgentRun model."""
    data = dict(zip(_AGENT_RUN_COLUMNS, row))
    for ts_field in ("created_at", "completed_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    return SubAgentRun(**data)


def create_agent_run(
    *,
    project_id: str,
    purpose: str,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    prompt_summary: str | None = None,
    mcp_enabled: str | None = None,
    status: str = "running",
    db_path: pathlib.Path | None = None,
) -> SubAgentRun:
    """Create a new sub-agent run and persist it to the database.

    Returns the created SubAgentRun model with generated ID and timestamp.

    Args:
        db_path: Explicit path to the SQLite database file. When supplied, the
            INSERT targets this exact file regardless of cwd or
            BOB_DATABASE_PATH. Callers that already know the project's
            database path MUST pass it here so the FK
            (sub_agent_runs.project_id REFERENCES projects(id)) resolves
            against the same database that holds the project row. Omitting
            this parameter falls back to get_database_path() which may
            resolve a different file when cwd has changed.
    """
    resolved_db = db_path or get_database_path()
    logger.debug("create_agent_run: writing to database %s", resolved_db)
    rid = run_id or str(uuid.uuid4())
    now = datetime.now()

    with connect(db_path=resolved_db) as conn:
        conn.execute(
            """INSERT INTO sub_agent_runs
               (id, project_id, parent_run_id,
                purpose, target_type, target_id,
                status, prompt_summary, mcp_enabled,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rid, project_id, parent_run_id,
             purpose, target_type, target_id,
             status, prompt_summary, mcp_enabled,
             now.isoformat()),
        )

    return SubAgentRun(
        id=rid,
        project_id=project_id,
        parent_run_id=parent_run_id,
        purpose=purpose,
        target_type=target_type,
        target_id=target_id,
        status=status,
        prompt_summary=prompt_summary,
        mcp_enabled=mcp_enabled,
        created_at=now,
    )


def get_agent_run(run_id: str) -> SubAgentRun | None:
    """Retrieve a sub-agent run by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_AGENT_RUN_COLUMNS)} FROM sub_agent_runs WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (run_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_agent_run(row)


def update_agent_run(run_id: str, **kwargs) -> SubAgentRun | None:
    """Update a sub-agent run's fields. Returns the updated run or None if not found.

    Only fields provided as keyword arguments are updated.
    """
    allowed = {
        "status", "result_summary", "prompt_summary",
        "rca_blame_target", "rca_recommended_action",
        "evidence_artifacts_produced",
        "improvement_type", "improvement_evidence",
        "tokens_in", "tokens_out", "cost_usd", "duration_ms",
        "mcp_enabled", "completed_at",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}

    if not updates:
        return get_agent_run(run_id)

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(run_id)

    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE sub_agent_runs SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_agent_run(run_id)


def query_agent_runs(
    *,
    project_id: str | None = None,
    status: str | None = None,
    purpose: str | None = None,
    parent_run_id: str | None = None,
) -> list[SubAgentRun]:
    """Query sub-agent runs with optional filtering.

    At least project_id must be provided. Results are ordered by
    created_at ascending.
    """
    if project_id is None:
        raise ValueError("project_id must be provided")

    conditions: list[str] = ["project_id = ?"]
    params: list = [project_id]

    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    if purpose is not None:
        conditions.append("purpose = ?")
        params.append(purpose)

    if parent_run_id is not None:
        conditions.append("parent_run_id = ?")
        params.append(parent_run_id)

    where = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_AGENT_RUN_COLUMNS)} FROM sub_agent_runs "
        f"WHERE {where} ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_agent_run(row) for row in rows]


def count_agent_runs(
    *,
    project_id: str,
    target_id: str | None = None,
    purpose: str | None = None,
    status: str | None = None,
) -> int:
    """Count agent runs matching the given filters via SQL COUNT(*).

    Faster than fetching all rows and counting in Python; used by the
    orchestration loop's needs_research check on every feature evaluation.
    """
    where = ["project_id = ?"]
    params: list = [project_id]
    if target_id is not None:
        where.append("target_id = ?")
        params.append(target_id)
    if purpose is not None:
        where.append("purpose = ?")
        params.append(purpose)
    if status is not None:
        where.append("status = ?")
        params.append(status)
    sql = "SELECT COUNT(*) FROM sub_agent_runs WHERE " + " AND ".join(where)
    with connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def get_agent_hierarchy(run_id: str) -> list[SubAgentRun] | None:
    """Return the full sub-tree rooted at *run_id* (inclusive).

    Uses a recursive CTE to walk `parent_run_id` links downward from
    the given run. Returns a list ordered with the root first, followed
    by descendants in breadth-first order.

    Returns ``None`` if no run with the given ID exists.
    """
    cols = ", ".join(f"s.{c}" for c in _AGENT_RUN_COLUMNS)
    sql = f"""
        WITH RECURSIVE hierarchy(id) AS (
            SELECT id FROM sub_agent_runs WHERE id = ?
            UNION ALL
            SELECT s.id
            FROM sub_agent_runs s
            JOIN hierarchy h ON s.parent_run_id = h.id
        )
        SELECT {cols}
        FROM sub_agent_runs s
        JOIN hierarchy h ON s.id = h.id
        ORDER BY s.created_at ASC
    """

    with connect() as conn:
        cursor = conn.execute(sql, (run_id,))
        rows = cursor.fetchall()

    if not rows:
        return None

    result = [_row_to_agent_run(row) for row in rows]

    # Ensure the requested root is first regardless of created_at ordering
    root_idx = next((i for i, r in enumerate(result) if r.id == run_id), 0)
    if root_idx != 0:
        root = result.pop(root_idx)
        result.insert(0, root)

    return result


# ============================================================
# RESEARCH RESULTS CRUD
# ============================================================

_RESEARCH_RESULT_COLUMNS = (
    "id", "feature_id", "project_id", "agent_run_id",
    "query", "findings", "sources", "code_examples",
    "applied", "created_at",
)


def _row_to_research_result(row: tuple) -> ResearchResult:
    """Convert a database row tuple to a ResearchResult model."""
    data = dict(zip(_RESEARCH_RESULT_COLUMNS, row))
    val = data.get("created_at")
    if val is not None and isinstance(val, str):
        data["created_at"] = datetime.fromisoformat(val)
    if data.get("applied") is not None:
        data["applied"] = bool(data["applied"])
    return ResearchResult(**data)


def create_research_result(
    *,
    feature_id: str,
    project_id: str,
    query: str,
    findings: str | None = None,
    sources: str | None = None,
    code_examples: str | None = None,
    agent_run_id: str | None = None,
    applied: bool = False,
) -> ResearchResult:
    """Create a new research result and persist it to the database.

    Returns the created ResearchResult model with generated ID and timestamp.
    """
    rid = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO research_results
               (id, feature_id, project_id, agent_run_id,
                query, findings, sources, code_examples,
                applied, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rid, feature_id, project_id, agent_run_id,
             query, findings, sources, code_examples,
             applied, now.isoformat()),
        )

    return ResearchResult(
        id=rid,
        feature_id=feature_id,
        project_id=project_id,
        agent_run_id=agent_run_id,
        query=query,
        findings=findings,
        sources=sources,
        code_examples=code_examples,
        applied=applied,
        created_at=now,
    )


def list_research_results(
    *,
    feature_id: str | None = None,
    project_id: str | None = None,
) -> list[ResearchResult]:
    """List research results with optional filtering.

    At least one of feature_id or project_id must be provided.
    Results are ordered by created_at ascending.
    """
    conditions: list[str] = []
    params: list = []

    if feature_id is not None:
        conditions.append("feature_id = ?")
        params.append(feature_id)

    if project_id is not None:
        conditions.append("project_id = ?")
        params.append(project_id)

    if not conditions:
        raise ValueError("At least one of feature_id or project_id must be provided")

    where = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_RESEARCH_RESULT_COLUMNS)} FROM research_results "
        f"WHERE {where} ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_research_result(row) for row in rows]


# ============================================================
# FLAKY TEST DETECTION AND TRACKING (F028)
# ============================================================

_FLAKY_RUN_COLUMNS = (
    "id", "task_id", "run_number", "passed", "output", "duration_ms", "created_at",
)


def _row_to_flaky_run(row: tuple) -> FlakyTestRun:
    """Convert a database row tuple to a FlakyTestRun model."""
    data = dict(zip(_FLAKY_RUN_COLUMNS, row))
    val = data.get("created_at")
    if val is not None and isinstance(val, str):
        data["created_at"] = datetime.fromisoformat(val)
    if data.get("passed") is not None:
        data["passed"] = bool(data["passed"])
    return FlakyTestRun(**data)


def record_test_run(
    *,
    task_id: str,
    run_number: int,
    passed: bool,
    output: str | None = None,
    duration_ms: int | None = None,
) -> FlakyTestRun:
    """Record a single test run result for flaky test tracking.

    Inserts a row into the flaky_test_runs table for the given task.

    Args:
        task_id: ID of the task being tested.
        run_number: Sequential run number.
        passed: Whether the test passed.
        output: Optional test output text.
        duration_ms: Optional duration in milliseconds.

    Returns:
        The created FlakyTestRun model.

    Raises:
        ValueError: If the task does not exist.
    """
    task = get_task(task_id)
    if task is None:
        raise ValueError(f"Task '{task_id}' not found")

    rid = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO flaky_test_runs
               (id, task_id, run_number, passed, output, duration_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rid, task_id, run_number, passed, output, duration_ms, now.isoformat()),
        )

    return FlakyTestRun(
        id=rid,
        task_id=task_id,
        run_number=run_number,
        passed=passed,
        output=output,
        duration_ms=duration_ms,
        created_at=now,
    )


def detect_flaky_test(
    *,
    task_id: str,
    last_n: int = 10,
) -> dict | None:
    """Analyze test run history and detect if a test is flaky.

    Examines the last N runs for the given task, calculates the pass rate,
    and sets the is_flaky flag if the pass rate is between 0.2 and 0.8
    (inclusive). Updates the task's is_flaky and flaky_pass_rate fields.

    Args:
        task_id: ID of the task to analyze.
        last_n: Number of most recent runs to consider (default 10).

    Returns:
        A dict with keys:
            - is_flaky: bool
            - pass_rate: float (0.0-1.0)
            - total_runs: int (number of runs analyzed)
        Returns None if the task does not exist.
    """
    task = get_task(task_id)
    if task is None:
        return None

    with connect() as conn:
        cursor = conn.execute(
            "SELECT passed FROM flaky_test_runs "
            "WHERE task_id = ? ORDER BY run_number DESC LIMIT ?",
            (task_id, last_n),
        )
        rows = cursor.fetchall()

    total_runs = len(rows)
    if total_runs == 0:
        update_task(task_id, is_flaky=False, flaky_pass_rate=0.0)
        return {"is_flaky": False, "pass_rate": 0.0, "total_runs": 0}

    pass_count = sum(1 for row in rows if row[0])
    pass_rate = pass_count / total_runs

    is_flaky = 0.2 <= pass_rate <= 0.8

    update_task(task_id, is_flaky=is_flaky, flaky_pass_rate=pass_rate)

    return {
        "is_flaky": is_flaky,
        "pass_rate": pass_rate,
        "total_runs": total_runs,
    }


# ============================================================
# VALIDATION INTEGRITY TRACKING (F029)
# ============================================================

COVERAGE_DROP_TOLERANCE = 5.0  # percentage points


def track_validation_integrity(
    *,
    task_id: str,
    assertion_count: int,
    coverage_percent: float | None = None,
) -> dict | None:
    """Track validation integrity by monitoring assertion count and coverage.

    On the first call for a task, stores the assertion_count as both
    original_assertion_count and current_assertion_count. On subsequent
    calls, updates current_assertion_count while preserving the original.

    Detects violations when:
    - current_assertion_count < original_assertion_count
    - current_coverage_percent < original_coverage_percent - 5

    Args:
        task_id: ID of the validation task to track.
        assertion_count: Current number of assertions in the test.
        coverage_percent: Optional current code coverage percentage.

    Returns:
        A dict with keys:
            - original_assertion_count: int
            - current_assertion_count: int
            - original_coverage_percent: float | None
            - current_coverage_percent: float | None
            - violation: bool (True if integrity was weakened)
        Returns None if the task does not exist.
    """
    task = get_task(task_id)
    if task is None:
        return None

    # Determine if this is the first call (original not yet set)
    if task.original_assertion_count is None:
        original_assertion = assertion_count
    else:
        original_assertion = task.original_assertion_count

    if coverage_percent is not None and task.original_coverage_percent is None:
        original_coverage = coverage_percent
    else:
        original_coverage = task.original_coverage_percent

    # Update the task
    update_kwargs: dict[str, object] = {
        "original_assertion_count": original_assertion,
        "current_assertion_count": assertion_count,
    }
    if coverage_percent is not None:
        update_kwargs["original_coverage_percent"] = original_coverage
        update_kwargs["current_coverage_percent"] = coverage_percent

    update_task(task_id, **update_kwargs)

    # Detect violations
    assertion_violation = assertion_count < original_assertion

    coverage_violation = False
    if (
        coverage_percent is not None
        and original_coverage is not None
        and coverage_percent < original_coverage - COVERAGE_DROP_TOLERANCE
    ):
        coverage_violation = True

    current_coverage = coverage_percent if coverage_percent is not None else task.current_coverage_percent

    violation = assertion_violation or coverage_violation

    # Log a warning when a violation is detected (F099)
    if violation:
        details_parts = [f"task_id={task_id}"]
        if assertion_violation:
            details_parts.append(
                f"assertion_count dropped from {original_assertion} to {assertion_count}"
            )
        if coverage_violation:
            details_parts.append(
                f"coverage dropped from {original_coverage}% to {coverage_percent}%"
            )
        log_event(
            project_id=task.project_id,
            event="Validation integrity violation detected",
            level="warning",
            details="; ".join(details_parts),
        )

    return {
        "original_assertion_count": original_assertion,
        "current_assertion_count": assertion_count,
        "original_coverage_percent": original_coverage,
        "current_coverage_percent": current_coverage,
        "violation": violation,
    }


def get_validation_integrity_violations(
    *,
    project_id: str,
) -> list[Task]:
    """Return validation tasks that have integrity violations.

    Queries for tasks where:
    - current_assertion_count < original_assertion_count, OR
    - current_coverage_percent < original_coverage_percent - 5

    This mirrors the test_integrity_violations SQL view but returns
    full Task model objects.

    Args:
        project_id: ID of the project to check.

    Returns:
        List of Task models with integrity violations.
    """
    select = (
        f"SELECT {', '.join(_TASK_COLUMNS)} FROM tasks "
        "WHERE project_id = ? AND type = 'validation' AND ("
        "  current_assertion_count < original_assertion_count"
        "  OR current_coverage_percent < original_coverage_percent - 5"
        ")"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [_row_to_task(row) for row in rows]


# ============================================================
# REGRESSION DETECTION (F051)
# ============================================================

_REGRESSION_EVENT_COLUMNS = (
    "id", "project_id",
    "affected_feature_id", "causing_feature_id",
    "detected_at",
    "affected_tests", "evidence_artifacts",
    "status", "resolution",
    "resolved_at",
)


def _row_to_regression_event(row: tuple) -> RegressionEvent:
    """Convert a database row tuple to a RegressionEvent model."""
    data = dict(zip(_REGRESSION_EVENT_COLUMNS, row))
    for ts_field in ("detected_at", "resolved_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    return RegressionEvent(**data)


def create_regression_event(
    *,
    project_id: str,
    affected_feature_id: str,
    causing_feature_id: str,
    affected_tests: str | None = None,
    evidence_artifacts: str | None = None,
    status: str = "detected",
) -> RegressionEvent:
    """Create a new regression event and persist it to the database.

    Args:
        project_id: ID of the project.
        affected_feature_id: ID of the feature whose tests broke.
        causing_feature_id: ID of the feature that caused the breakage.
        affected_tests: JSON array of test IDs that started failing.
        evidence_artifacts: JSON array of evidence artifact IDs.
        status: Initial status (default: "detected").

    Returns:
        The created RegressionEvent model.
    """
    event_id = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO regression_events
               (id, project_id, affected_feature_id, causing_feature_id,
                detected_at, affected_tests, evidence_artifacts, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, project_id, affected_feature_id, causing_feature_id,
             now.isoformat(), affected_tests, evidence_artifacts, status),
        )

    return RegressionEvent(
        id=event_id,
        project_id=project_id,
        affected_feature_id=affected_feature_id,
        causing_feature_id=causing_feature_id,
        detected_at=now,
        affected_tests=affected_tests,
        evidence_artifacts=evidence_artifacts,
        status=status,
    )


def get_regression_event(event_id: str) -> RegressionEvent | None:
    """Retrieve a regression event by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_REGRESSION_EVENT_COLUMNS)} FROM regression_events WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (event_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_regression_event(row)


def update_regression_event(event_id: str, **kwargs) -> RegressionEvent | None:
    """Update a regression event's fields.

    Allowed fields: status, resolution, resolved_at.
    Returns the updated RegressionEvent or None if not found.
    """
    allowed = {"status", "resolution", "resolved_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}

    if not updates:
        return get_regression_event(event_id)

    # Auto-set resolved_at when status becomes resolved or rolled_back
    if "status" in updates and updates["status"] in ("resolved", "rolled_back"):
        if "resolved_at" not in updates:
            updates["resolved_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values())
    values.append(event_id)

    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE regression_events SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_regression_event(event_id)


def list_regression_events(
    *,
    project_id: str,
    active_only: bool = False,
) -> list[RegressionEvent]:
    """Return regression events for a project.

    Args:
        project_id: ID of the project.
        active_only: If True, only return events not in resolved/rolled_back status.

    Returns:
        List of RegressionEvent models ordered by detection time.
    """
    conditions = ["project_id = ?"]
    params: list = [project_id]

    if active_only:
        conditions.append("status NOT IN ('resolved', 'rolled_back')")

    where_clause = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_REGRESSION_EVENT_COLUMNS)} FROM regression_events "
        f"WHERE {where_clause} ORDER BY detected_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_regression_event(row) for row in rows]


def _record_unattributed_failures(
    *,
    project_id: str,
    causing_feature_id: str,
    test_names: list[str],
) -> None:
    """Persist unmapped failures to unattributed_failures table.

    These are newly-failing tests that cannot be attributed to any feature via
    the test_to_feature_map.  They are recorded here rather than scapegoated
    onto an arbitrary completed feature.
    """
    now = datetime.now().isoformat()
    with connect() as conn:
        conn.executemany(
            """INSERT INTO unattributed_failures
               (id, project_id, causing_feature_id, test_name, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (str(uuid.uuid4()), project_id, causing_feature_id, t, now)
                for t in test_names
            ],
        )


from bob.db.detect_regression import detect_regression
from bob.db.test_ownership_map import get_test_ownership_map


# ============================================================
# ROLLBACK OPERATIONS (F052)
# ============================================================

_ROLLBACK_EVENT_COLUMNS = (
    "id", "project_id", "feature_id",
    "trigger", "regression_event_id",
    "commit_before", "commit_after",
    "rollback_commit",
    "artifacts_preserved", "titans_memory_id",
    "created_at",
)


def _row_to_rollback_event(row: tuple) -> RollbackEvent:
    """Convert a database row tuple to a RollbackEvent model."""
    data = dict(zip(_ROLLBACK_EVENT_COLUMNS, row))
    for ts_field in ("created_at",):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    return RollbackEvent(**data)


def create_rollback_event(
    *,
    project_id: str,
    feature_id: str,
    trigger: str,
    commit_before: str,
    commit_after: str,
    regression_event_id: str | None = None,
    rollback_commit: str | None = None,
    artifacts_preserved: str | None = None,
    titans_memory_id: str | None = None,
) -> RollbackEvent:
    """Create a new rollback event and persist it to the database.

    Args:
        project_id: ID of the project.
        feature_id: ID of the feature being rolled back.
        trigger: What triggered the rollback (regression|human_request|critical_bug).
        commit_before: Git commit SHA before the feature was implemented.
        commit_after: Git commit SHA after the feature (being rolled back).
        regression_event_id: Optional ID of the linked regression event.
        rollback_commit: Optional git commit SHA of the rollback itself.
        artifacts_preserved: Optional JSON array of preserved artifact IDs.
        titans_memory_id: Optional bob-memory lesson ID.
            (Column name is legacy; backend is now bob-memory.)

    Returns:
        The created RollbackEvent model.
    """
    event_id = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO rollback_events
               (id, project_id, feature_id, trigger, regression_event_id,
                commit_before, commit_after, rollback_commit,
                artifacts_preserved, titans_memory_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, project_id, feature_id, trigger, regression_event_id,
             commit_before, commit_after, rollback_commit,
             artifacts_preserved, titans_memory_id, now.isoformat()),
        )

    return RollbackEvent(
        id=event_id,
        project_id=project_id,
        feature_id=feature_id,
        trigger=trigger,
        regression_event_id=regression_event_id,
        commit_before=commit_before,
        commit_after=commit_after,
        rollback_commit=rollback_commit,
        artifacts_preserved=artifacts_preserved,
        titans_memory_id=titans_memory_id,
        created_at=now,
    )


def get_rollback_event(event_id: str) -> RollbackEvent | None:
    """Retrieve a rollback event by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_ROLLBACK_EVENT_COLUMNS)} FROM rollback_events WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (event_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_rollback_event(row)


def list_rollback_events(
    *,
    project_id: str,
    feature_id: str | None = None,
) -> list[RollbackEvent]:
    """Return rollback events for a project, optionally filtered by feature.

    Args:
        project_id: ID of the project.
        feature_id: Optional feature ID to filter by.

    Returns:
        List of RollbackEvent models ordered by creation time.
    """
    conditions = ["project_id = ?"]
    params: list = [project_id]

    if feature_id is not None:
        conditions.append("feature_id = ?")
        params.append(feature_id)

    where_clause = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_ROLLBACK_EVENT_COLUMNS)} FROM rollback_events "
        f"WHERE {where_clause} ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_rollback_event(row) for row in rows]


def rollback_feature(
    *,
    project_id: str,
    feature_id: str,
    trigger: str,
    commit_before: str,
    commit_after: str,
    rollback_commit: str | None = None,
    regression_event_id: str | None = None,
) -> RollbackEvent:
    """Roll back a failed feature.

    This function:
    1. Collects and preserves all evidence artifacts for the feature.
    2. Creates a rollback_events record with commit SHAs and preserved artifact IDs.
    3. Updates the feature's status to 'rolled_back'.
    4. If linked to a regression event, updates its status to 'rolled_back'.

    Args:
        project_id: ID of the project.
        feature_id: ID of the feature to roll back.
        trigger: What triggered the rollback (regression|human_request|critical_bug).
        commit_before: Git commit SHA before the feature was implemented.
        commit_after: Git commit SHA after the feature (being rolled back).
        rollback_commit: Optional git commit SHA of the rollback itself.
        regression_event_id: Optional ID of the linked regression event.

    Returns:
        The created RollbackEvent with preserved artifact IDs.
    """
    # Step 5: Preserve artifacts - collect all evidence artifact IDs for this feature
    with connect() as conn:
        cursor = conn.execute(
            "SELECT id FROM evidence_artifacts WHERE feature_id = ?",
            (feature_id,),
        )
        artifact_ids = [row[0] for row in cursor.fetchall()]

    artifacts_preserved = json.dumps(artifact_ids)

    # Step 4: Create rollback_events record
    event = create_rollback_event(
        project_id=project_id,
        feature_id=feature_id,
        trigger=trigger,
        commit_before=commit_before,
        commit_after=commit_after,
        rollback_commit=rollback_commit,
        regression_event_id=regression_event_id,
        artifacts_preserved=artifacts_preserved,
    )

    # Update feature status to 'rolled_back'
    update_feature(feature_id, status="rolled_back")

    # If linked to a regression event, update its status too
    if regression_event_id is not None:
        update_regression_event(regression_event_id, status="rolled_back")

    return event


# ============================================================
# CHECKPOINT CRUD OPERATIONS
# ============================================================

_CHECKPOINT_COLUMNS = (
    "id", "project_id", "feature_id", "task_id",
    "checkpoint_type",
    "state_snapshot", "files_snapshot",
    "cost_at_checkpoint", "duration_at_checkpoint_ms",
    "can_resume", "resumed_at",
    "created_at",
)


def _row_to_checkpoint(row: tuple) -> ResourceCheckpoint:
    """Convert a database row tuple to a ResourceCheckpoint model."""
    data = dict(zip(_CHECKPOINT_COLUMNS, row))
    for ts_field in ("resumed_at", "created_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    if "can_resume" in data:
        data["can_resume"] = bool(data["can_resume"])
    return ResourceCheckpoint(**data)


def create_checkpoint(
    *,
    project_id: str,
    feature_id: str,
    checkpoint_type: str,
    state_snapshot: str,
    task_id: str | None = None,
    files_snapshot: str | None = None,
    cost_at_checkpoint: float | None = None,
    duration_at_checkpoint_ms: int | None = None,
) -> ResourceCheckpoint:
    """Create a checkpoint capturing feature/task state at a point in time.

    Args:
        project_id: ID of the project.
        feature_id: ID of the feature being checkpointed.
        checkpoint_type: Type of checkpoint (task_completion|resource_limit|manual).
        state_snapshot: JSON string of current feature/task state.
        task_id: Optional task ID if checkpoint is task-level.
        files_snapshot: Optional JSON string of files and their hashes.
        cost_at_checkpoint: Optional accumulated cost at this point.
        duration_at_checkpoint_ms: Optional elapsed duration in milliseconds.

    Returns:
        The created ResourceCheckpoint model.
    """
    checkpoint_id = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO resource_checkpoints
               (id, project_id, feature_id, task_id,
                checkpoint_type,
                state_snapshot, files_snapshot,
                cost_at_checkpoint, duration_at_checkpoint_ms,
                can_resume, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (checkpoint_id, project_id, feature_id, task_id,
             checkpoint_type,
             state_snapshot, files_snapshot,
             cost_at_checkpoint, duration_at_checkpoint_ms,
             True, now.isoformat()),
        )

    return ResourceCheckpoint(
        id=checkpoint_id,
        project_id=project_id,
        feature_id=feature_id,
        task_id=task_id,
        checkpoint_type=checkpoint_type,
        state_snapshot=state_snapshot,
        files_snapshot=files_snapshot,
        cost_at_checkpoint=cost_at_checkpoint,
        duration_at_checkpoint_ms=duration_at_checkpoint_ms,
        can_resume=True,
        created_at=now,
    )


def get_checkpoint(checkpoint_id: str) -> ResourceCheckpoint | None:
    """Retrieve a checkpoint by ID. Returns None if not found."""
    select = f"SELECT {', '.join(_CHECKPOINT_COLUMNS)} FROM resource_checkpoints WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (checkpoint_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_checkpoint(row)


def list_checkpoints(
    *,
    feature_id: str,
    task_id: str | None = None,
) -> list[ResourceCheckpoint]:
    """Return checkpoints for a feature, optionally filtered by task.

    Args:
        feature_id: ID of the feature.
        task_id: Optional task ID to filter by.

    Returns:
        List of ResourceCheckpoint models ordered by creation time.
    """
    conditions = ["feature_id = ?"]
    params: list = [feature_id]

    if task_id is not None:
        conditions.append("task_id = ?")
        params.append(task_id)

    where_clause = " AND ".join(conditions)
    select = (
        f"SELECT {', '.join(_CHECKPOINT_COLUMNS)} FROM resource_checkpoints "
        f"WHERE {where_clause} ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_checkpoint(row) for row in rows]


def resume_from_checkpoint(checkpoint_id: str) -> ResourceCheckpoint:
    """Resume execution from a previously created checkpoint.

    Loads the state_snapshot, restores feature and task state, sets resumed_at
    timestamp, and marks the checkpoint as no longer resumable.

    Args:
        checkpoint_id: ID of the checkpoint to resume from.

    Returns:
        The updated ResourceCheckpoint with resumed_at set.

    Raises:
        ValueError: If the checkpoint does not exist or has already been resumed.
    """
    cp = get_checkpoint(checkpoint_id)
    if cp is None:
        raise ValueError(f"Checkpoint '{checkpoint_id}' not found")
    if not cp.can_resume:
        raise ValueError(
            f"Checkpoint '{checkpoint_id}' has already been resumed and cannot be resumed again"
        )

    state = json.loads(cp.state_snapshot)

    # Restore feature state
    feature_updates: dict = {}
    if "feature_status" in state:
        feature_updates["status"] = state["feature_status"]
    if "tasks_completed" in state:
        feature_updates["tasks_completed"] = state["tasks_completed"]
    if "tasks_total" in state:
        feature_updates["tasks_total"] = state["tasks_total"]
    if "confidence" in state:
        conf = state["confidence"]
        if "spec_understanding" in conf:
            feature_updates["conf_spec_understanding"] = conf["spec_understanding"]
        if "impl_correctness" in conf:
            feature_updates["conf_impl_correctness"] = conf["impl_correctness"]
        if "test_adequacy" in conf:
            feature_updates["conf_test_adequacy"] = conf["test_adequacy"]

    if feature_updates:
        update_feature(cp.feature_id, **feature_updates)

    # Restore task state if checkpoint is task-level
    if cp.task_id and "task_status" in state:
        update_task(cp.task_id, status=state["task_status"])

    # Mark checkpoint as resumed
    now = datetime.now()
    with connect() as conn:
        conn.execute(
            "UPDATE resource_checkpoints SET can_resume = ?, resumed_at = ? WHERE id = ?",
            (False, now.isoformat(), checkpoint_id),
        )

    return ResourceCheckpoint(
        id=cp.id,
        project_id=cp.project_id,
        feature_id=cp.feature_id,
        task_id=cp.task_id,
        checkpoint_type=cp.checkpoint_type,
        state_snapshot=cp.state_snapshot,
        files_snapshot=cp.files_snapshot,
        cost_at_checkpoint=cp.cost_at_checkpoint,
        duration_at_checkpoint_ms=cp.duration_at_checkpoint_ms,
        can_resume=False,
        resumed_at=now,
        created_at=cp.created_at,
    )


def find_resumable_checkpoints(
    *,
    project_id: str,
) -> list[ResourceCheckpoint]:
    """Find all resumable checkpoints for a project.

    Returns checkpoints where can_resume=TRUE, ordered by creation time
    descending (most recent first).

    Args:
        project_id: ID of the project.

    Returns:
        List of resumable ResourceCheckpoint models.
    """
    select = (
        f"SELECT {', '.join(_CHECKPOINT_COLUMNS)} FROM resource_checkpoints "
        f"WHERE project_id = ? AND can_resume = ? ORDER BY created_at DESC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id, True))
        rows = cursor.fetchall()
    return [_row_to_checkpoint(row) for row in rows]


# ============================================================
# SCOPE CHANGE TRACKING (F062)
# ============================================================

_SCOPE_CHANGE_COLUMNS = (
    "id", "feature_id", "change_type",
    "before_value", "after_value",
    "growth_percent",
    "requires_approval", "approved_by", "approved_at",
    "created_at",
)


def _row_to_scope_change(row: tuple) -> ScopeChange:
    """Convert a database row tuple to a ScopeChange model."""
    data = dict(zip(_SCOPE_CHANGE_COLUMNS, row))
    for ts_field in ("approved_at", "created_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    if "requires_approval" in data:
        data["requires_approval"] = bool(data["requires_approval"])
    return ScopeChange(**data)


def record_scope_change(
    *,
    feature_id: str,
    change_type: str,
    before_value: str | None = None,
    after_value: str | None = None,
    growth_percent: float | None = None,
    requires_approval: bool = False,
) -> ScopeChange:
    """Record a scope change for a feature.

    Args:
        feature_id: The feature that changed.
        change_type: Type of change (acceptance_criteria_added, task_added, description_changed).
        before_value: String representation of the value before the change.
        after_value: String representation of the value after the change.
        growth_percent: Percentage of scope growth.
        requires_approval: Whether the change needs approval (auto-set if growth > 50%).

    Returns:
        The created ScopeChange model.
    """
    sc_id = str(uuid.uuid4())
    now = datetime.now()

    # Auto-flag requires_approval if growth > 50%
    if growth_percent is not None and growth_percent > 50:
        requires_approval = True

    with connect() as conn:
        conn.execute(
            """INSERT INTO scope_changes
               (id, feature_id, change_type,
                before_value, after_value,
                growth_percent,
                requires_approval,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (sc_id, feature_id, change_type,
             before_value, after_value,
             growth_percent,
             requires_approval,
             now.isoformat()),
        )

    return ScopeChange(
        id=sc_id,
        feature_id=feature_id,
        change_type=change_type,
        before_value=before_value,
        after_value=after_value,
        growth_percent=growth_percent,
        requires_approval=requires_approval,
        created_at=now,
    )


def detect_scope_changes(*, feature_id: str) -> ScopeChange | None:
    """Detect if a feature's scope has grown beyond its original counts.

    Checks both acceptance criteria count and task count against the
    original_acceptance_criteria_count and original_task_count stored
    on the feature. If growth is detected, records a scope_change and
    returns it. If no growth, returns None.

    Args:
        feature_id: The feature to check.

    Returns:
        A ScopeChange if growth was detected, or None.
    """
    feature = get_feature(feature_id)
    if feature is None:
        return None

    # Check acceptance criteria growth
    if (
        feature.original_acceptance_criteria_count is not None
        and feature.original_acceptance_criteria_count > 0
        and feature.acceptance_criteria is not None
    ):
        try:
            current_criteria = json.loads(feature.acceptance_criteria)
            current_count = len(current_criteria)
        except (json.JSONDecodeError, TypeError):
            current_count = 0

        original = feature.original_acceptance_criteria_count
        if current_count > original:
            growth = ((current_count - original) / original) * 100
            growth_rounded = round(growth, 2)
            return record_scope_change(
                feature_id=feature_id,
                change_type="acceptance_criteria_added",
                before_value=str(original),
                after_value=str(current_count),
                growth_percent=growth_rounded,
                requires_approval=growth_rounded > 50,
            )

    # Check task count growth
    if (
        feature.original_task_count is not None
        and feature.original_task_count > 0
    ):
        tasks = list_tasks(feature_id=feature_id)
        current_task_count = len(tasks)
        original = feature.original_task_count

        if current_task_count > original:
            growth = ((current_task_count - original) / original) * 100
            growth_rounded = round(growth, 2)
            return record_scope_change(
                feature_id=feature_id,
                change_type="task_added",
                before_value=str(original),
                after_value=str(current_task_count),
                growth_percent=growth_rounded,
                requires_approval=growth_rounded > 50,
            )

    return None


def get_scope_changes(*, feature_id: str) -> list[ScopeChange]:
    """Return all scope changes for a feature, ordered by creation time.

    Args:
        feature_id: The feature to get changes for.

    Returns:
        List of ScopeChange models.
    """
    select = (
        f"SELECT {', '.join(_SCOPE_CHANGE_COLUMNS)} FROM scope_changes "
        "WHERE feature_id = ? ORDER BY created_at ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (feature_id,))
        rows = cursor.fetchall()
    return [_row_to_scope_change(row) for row in rows]


def get_pending_approvals(*, feature_id: str) -> list[ScopeChange]:
    """Return scope changes that require approval but haven't been approved yet.

    Args:
        feature_id: The feature to get pending approvals for.

    Returns:
        List of ScopeChange models needing approval.
    """
    select = (
        f"SELECT {', '.join(_SCOPE_CHANGE_COLUMNS)} FROM scope_changes "
        "WHERE feature_id = ? AND requires_approval = ? AND approved_by IS NULL "
        "ORDER BY created_at ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (feature_id, True))
        rows = cursor.fetchall()
    return [_row_to_scope_change(row) for row in rows]


def approve_scope_change(
    *,
    scope_change_id: str,
    approved_by: str,
) -> ScopeChange | None:
    """Approve a scope change.

    Args:
        scope_change_id: The scope change to approve.
        approved_by: Who approved it.

    Returns:
        The updated ScopeChange, or None if not found.
    """
    now = datetime.now()
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE scope_changes SET approved_by = ?, approved_at = ? WHERE id = ?",
            (approved_by, now.isoformat(), scope_change_id),
        )
        if cursor.rowcount == 0:
            return None

    # Fetch and return the updated record
    select = (
        f"SELECT {', '.join(_SCOPE_CHANGE_COLUMNS)} FROM scope_changes WHERE id = ?"
    )
    with connect() as conn:
        cursor = conn.execute(select, (scope_change_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_scope_change(row)


# ============================================================
# FORGETTING EVENT OPERATIONS (F063)
# ============================================================

_FORGETTING_EVENT_COLUMNS = (
    "id", "project_id",
    "target_type", "target_id",
    "action", "reason",
    "previous_status", "previous_usefulness_score", "previous_retrieval_weight",
    "backup_path", "backup_content",
    "triggered_by", "approved_by",
    "can_restore", "restored_at",
    "created_at",
)


def _row_to_forgetting_event(row: tuple) -> ForgettingEvent:
    """Convert a database row tuple to a ForgettingEvent model."""
    data = dict(zip(_FORGETTING_EVENT_COLUMNS, row))
    for ts_field in ("restored_at", "created_at"):
        val = data.get(ts_field)
        if val is not None and isinstance(val, str):
            data[ts_field] = datetime.fromisoformat(val)
    if "can_restore" in data:
        data["can_restore"] = bool(data["can_restore"])
    return ForgettingEvent(**data)


def record_forgetting_event(
    *,
    target_type: str,
    target_id: str,
    action: str,
    reason: str,
    project_id: str | None = None,
    previous_status: str | None = None,
    previous_usefulness_score: float | None = None,
    previous_retrieval_weight: float | None = None,
    backup_path: str | None = None,
    backup_content: str | None = None,
    triggered_by: str | None = None,
    approved_by: str | None = None,
    can_restore: bool = True,
) -> ForgettingEvent:
    """Record a forgetting event for the bob-memory audit trail.

    Args:
        target_type: Type of target (lesson or memory).
        target_id: ID of the bob-memory entry being acted upon.
        action: Action taken (demote, archive, purge, or restore).
        reason: Human-readable reason for the action.
        project_id: Optional project context.
        previous_status: Status before the action.
        previous_usefulness_score: Usefulness score before the action.
        previous_retrieval_weight: Retrieval weight before the action.
        backup_path: File path to backup (for purge).
        backup_content: JSON snapshot of deleted content (for purge).
        triggered_by: Who/what triggered the action (schedule, manual, system).
        approved_by: Human who approved the action (for purge).
        can_restore: Whether the item can be restored.

    Returns:
        The created ForgettingEvent model.
    """
    event_id = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO forgetting_events
               (id, project_id,
                target_type, target_id,
                action, reason,
                previous_status, previous_usefulness_score, previous_retrieval_weight,
                backup_path, backup_content,
                triggered_by, approved_by,
                can_restore, restored_at,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, project_id,
             target_type, target_id,
             action, reason,
             previous_status, previous_usefulness_score, previous_retrieval_weight,
             backup_path, backup_content,
             triggered_by, approved_by,
             can_restore, None,
             now.isoformat()),
        )

    return ForgettingEvent(
        id=event_id,
        project_id=project_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
        reason=reason,
        previous_status=previous_status,
        previous_usefulness_score=previous_usefulness_score,
        previous_retrieval_weight=previous_retrieval_weight,
        backup_path=backup_path,
        backup_content=backup_content,
        triggered_by=triggered_by,
        approved_by=approved_by,
        can_restore=can_restore,
        restored_at=None,
        created_at=now,
    )


def get_forgetting_event(event_id: str) -> ForgettingEvent | None:
    """Retrieve a single forgetting event by ID.

    Returns:
        The ForgettingEvent, or None if not found.
    """
    select = f"SELECT {', '.join(_FORGETTING_EVENT_COLUMNS)} FROM forgetting_events WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (event_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_forgetting_event(row)


def get_forgetting_events(
    *,
    project_id: str | None = None,
    target_id: str | None = None,
) -> list[ForgettingEvent]:
    """Query forgetting events, optionally filtering by project and/or target.

    Args:
        project_id: Filter by project ID.
        target_id: Filter by target ID.

    Returns:
        List of matching ForgettingEvent entries, ordered by created_at ascending.
    """
    conditions = []
    params: list = []

    if project_id is not None:
        conditions.append("project_id = ?")
        params.append(project_id)
    if target_id is not None:
        conditions.append("target_id = ?")
        params.append(target_id)

    where = ""
    if conditions:
        where = " WHERE " + " AND ".join(conditions)

    select = (
        f"SELECT {', '.join(_FORGETTING_EVENT_COLUMNS)} FROM forgetting_events"
        f"{where} ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, tuple(params))
        rows = cursor.fetchall()
    return [_row_to_forgetting_event(row) for row in rows]


def mark_forgetting_event_restored(event_id: str) -> ForgettingEvent | None:
    """Mark a forgetting event as restored by setting restored_at.

    Args:
        event_id: The ID of the forgetting event to mark as restored.

    Returns:
        The updated ForgettingEvent, or None if not found.
    """
    now = datetime.now()
    with connect() as conn:
        conn.execute(
            "UPDATE forgetting_events SET restored_at = ? WHERE id = ?",
            (now.isoformat(), event_id),
        )
    return get_forgetting_event(event_id)


def restore_from_forgetting(event_id: str) -> dict | None:
    """Restore a lesson/memory from a forgetting event's backup.

    Looks up the forgetting event by ID, verifies it has backup_content
    and has not already been restored, then:
    1. Creates a new "restore" forgetting event referencing the same target.
    2. Marks the original event with restored_at timestamp.
    3. Returns the backup_content for the caller to re-add to bob-memory.

    Args:
        event_id: The ID of the forgetting event to restore from.

    Returns:
        A dict with keys 'restore_event' (ForgettingEvent) and
        'backup_content' (str, the original JSON), or None if the event
        doesn't exist, has no backup, or was already restored.
    """
    original = get_forgetting_event(event_id)
    if original is None:
        return None

    # Cannot restore without backup content
    if not original.backup_content:
        return None

    # Cannot restore if already restored
    if original.restored_at is not None:
        return None

    # Create a restore forgetting event
    restore_event = record_forgetting_event(
        project_id=original.project_id,
        target_type=original.target_type,
        target_id=original.target_id,
        action="restore",
        reason=f"Restored from forgetting event {event_id}",
        triggered_by="system",
    )

    # Mark the original purge event as restored
    mark_forgetting_event_restored(event_id)

    return {
        "restore_event": restore_event,
        "backup_content": original.backup_content,
    }


# ============================================================
# EXECUTION LOG OPERATIONS
# ============================================================

_EXECUTION_LOG_COLUMNS = (
    "id", "project_id", "sub_agent_run_id",
    "level", "event", "details",
    "created_at",
)

_VALID_LOG_LEVELS = ("debug", "info", "warning", "error")


def _row_to_execution_log(row: tuple) -> ExecutionLog:
    """Convert a database row tuple to an ExecutionLog model."""
    data = dict(zip(_EXECUTION_LOG_COLUMNS, row))
    ts = data.get("created_at")
    if ts is not None and isinstance(ts, str):
        data["created_at"] = datetime.fromisoformat(ts)
    return ExecutionLog(**data)


def log_event(
    *,
    project_id: str,
    event: str,
    level: str = "info",
    sub_agent_run_id: str | None = None,
    details: str | None = None,
) -> ExecutionLog:
    """Log an execution event to the execution_logs table.

    Args:
        project_id: The project this log belongs to.
        event: Description of the event.
        level: Log level - one of debug, info, warning, error.
        sub_agent_run_id: Optional link to a sub-agent run.
        details: Optional additional details (free-form text or JSON).

    Returns:
        The created ExecutionLog entry.

    Raises:
        ValueError: If level is not one of the valid log levels.
    """
    if level not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"Invalid log level '{level}'. Must be one of: {', '.join(_VALID_LOG_LEVELS)}"
        )

    log_id = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO execution_logs
               (id, project_id, sub_agent_run_id, level, event, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (log_id, project_id, sub_agent_run_id, level, event, details, now.isoformat()),
        )

    return ExecutionLog(
        id=log_id,
        project_id=project_id,
        sub_agent_run_id=sub_agent_run_id,
        level=level,
        event=event,
        details=details,
        created_at=now,
    )


def get_execution_log(log_id: str) -> ExecutionLog | None:
    """Retrieve a single execution log entry by ID.

    Returns:
        The ExecutionLog, or None if not found.
    """
    select = f"SELECT {', '.join(_EXECUTION_LOG_COLUMNS)} FROM execution_logs WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (log_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_execution_log(row)


def query_execution_logs(
    *,
    project_id: str,
    level: str | None = None,
    sub_agent_run_id: str | None = None,
    limit: int = 100,
) -> list[ExecutionLog]:
    """Query execution logs with optional filters.

    Args:
        project_id: The project to query logs for.
        level: Optional filter by log level.
        sub_agent_run_id: Optional filter by sub-agent run.
        limit: Maximum number of results (default 100).

    Returns:
        List of matching ExecutionLog entries, ordered by created_at descending.
    """
    clauses = ["project_id = ?"]
    params: list = [project_id]

    if level is not None:
        clauses.append("level = ?")
        params.append(level)

    if sub_agent_run_id is not None:
        clauses.append("sub_agent_run_id = ?")
        params.append(sub_agent_run_id)

    where = " AND ".join(clauses)
    select = (
        f"SELECT {', '.join(_EXECUTION_LOG_COLUMNS)} FROM execution_logs "
        f"WHERE {where} ORDER BY created_at DESC LIMIT ?"
    )
    params.append(limit)

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_execution_log(row) for row in rows]


# ============================================================
# CONFIDENCE HISTORY OPERATIONS
# ============================================================

_CONFIDENCE_HISTORY_COLUMNS = (
    "id", "project_id", "feature_id", "task_id",
    "conf_spec_understanding", "conf_impl_correctness", "conf_test_adequacy",
    "rated_by", "rationale",
    "created_at",
)


def _row_to_confidence_history(row: tuple) -> ConfidenceHistory:
    """Convert a database row tuple to a ConfidenceHistory model."""
    data = dict(zip(_CONFIDENCE_HISTORY_COLUMNS, row))
    ts = data.get("created_at")
    if ts is not None and isinstance(ts, str):
        data["created_at"] = datetime.fromisoformat(ts)
    return ConfidenceHistory(**data)


def record_confidence(
    *,
    project_id: str,
    rated_by: str,
    feature_id: str | None = None,
    task_id: str | None = None,
    conf_spec_understanding: float | None = None,
    conf_impl_correctness: float | None = None,
    conf_test_adequacy: float | None = None,
    rationale: str | None = None,
) -> ConfidenceHistory:
    """Record a confidence snapshot to the confidence_history table.

    Args:
        project_id: The project this confidence rating belongs to.
        rated_by: Who rated the confidence (agent ID or 'human').
        feature_id: Optional feature this rating applies to.
        task_id: Optional task this rating applies to.
        conf_spec_understanding: Confidence in spec understanding (0.0-1.0).
        conf_impl_correctness: Confidence in implementation correctness (0.0-1.0).
        conf_test_adequacy: Confidence in test adequacy (0.0-1.0).
        rationale: Optional explanation for the rating.

    Returns:
        The created ConfidenceHistory entry.
    """
    entry_id = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO confidence_history
               (id, project_id, feature_id, task_id,
                conf_spec_understanding, conf_impl_correctness, conf_test_adequacy,
                rated_by, rationale, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry_id, project_id, feature_id, task_id,
             conf_spec_understanding, conf_impl_correctness, conf_test_adequacy,
             rated_by, rationale, now.isoformat()),
        )

    return ConfidenceHistory(
        id=entry_id,
        project_id=project_id,
        feature_id=feature_id,
        task_id=task_id,
        conf_spec_understanding=conf_spec_understanding,
        conf_impl_correctness=conf_impl_correctness,
        conf_test_adequacy=conf_test_adequacy,
        rated_by=rated_by,
        rationale=rationale,
        created_at=now,
    )


def get_confidence_entry(entry_id: str) -> ConfidenceHistory | None:
    """Retrieve a single confidence history entry by ID.

    Returns:
        The ConfidenceHistory, or None if not found.
    """
    select = f"SELECT {', '.join(_CONFIDENCE_HISTORY_COLUMNS)} FROM confidence_history WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (entry_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_confidence_history(row)


def get_confidence_history(
    *,
    feature_id: str | None = None,
    task_id: str | None = None,
) -> list[ConfidenceHistory]:
    """Query confidence history entries with optional filters.

    Args:
        feature_id: Filter by feature ID.
        task_id: Filter by task ID.

    Returns:
        List of matching ConfidenceHistory entries, ordered by created_at ascending.
    """
    clauses: list[str] = []
    params: list = []

    if feature_id is not None:
        clauses.append("feature_id = ?")
        params.append(feature_id)

    if task_id is not None:
        clauses.append("task_id = ?")
        params.append(task_id)

    where = " AND ".join(clauses) if clauses else "1=1"
    select = (
        f"SELECT {', '.join(_CONFIDENCE_HISTORY_COLUMNS)} FROM confidence_history "
        f"WHERE {where} ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, params)
        rows = cursor.fetchall()
    return [_row_to_confidence_history(row) for row in rows]


# ============================================================
# READINESS HISTORY CRUD OPERATIONS (F067)
# ============================================================

_READINESS_HISTORY_COLUMNS = (
    "id", "project_id", "feature_id",
    "readiness_score",
    "opus_confidence_component", "test_pass_rate_component",
    "evidence_score_component", "diff_quality_component",
    "reviewer_adjustment_component",
    "change_reason", "rules_applied",
    "computed_by",
    "created_at",
)


def _row_to_readiness_history(row: tuple) -> ReadinessHistory:
    """Convert a database row tuple to a ReadinessHistory model."""
    data = dict(zip(_READINESS_HISTORY_COLUMNS, row))
    ts = data.get("created_at")
    if ts is not None and isinstance(ts, str):
        data["created_at"] = datetime.fromisoformat(ts)
    return ReadinessHistory(**data)


def record_readiness(
    *,
    project_id: str,
    feature_id: str,
    readiness_score: float,
    computed_by: str,
    opus_confidence_component: float | None = None,
    test_pass_rate_component: float | None = None,
    evidence_score_component: float | None = None,
    diff_quality_component: float | None = None,
    reviewer_adjustment_component: float | None = None,
    change_reason: str | None = None,
    rules_applied: str | None = None,
) -> ReadinessHistory:
    """Record a readiness snapshot to the readiness_history table.

    Args:
        project_id: The project this readiness calculation belongs to.
        feature_id: The feature this readiness applies to.
        readiness_score: The composite readiness score (0.0-1.0).
        computed_by: Who computed this readiness ('orchestrator', 'human', agent ID).
        opus_confidence_component: Opus confidence component score.
        test_pass_rate_component: Test pass rate component score.
        evidence_score_component: Evidence quality component score.
        diff_quality_component: Diff quality component score.
        reviewer_adjustment_component: Reviewer adjustment component score.
        change_reason: Why readiness changed.
        rules_applied: JSON array of rules applied during computation.

    Returns:
        The created ReadinessHistory entry.
    """
    entry_id = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """INSERT INTO readiness_history
               (id, project_id, feature_id,
                readiness_score,
                opus_confidence_component, test_pass_rate_component,
                evidence_score_component, diff_quality_component,
                reviewer_adjustment_component,
                change_reason, rules_applied,
                computed_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry_id, project_id, feature_id,
             readiness_score,
             opus_confidence_component, test_pass_rate_component,
             evidence_score_component, diff_quality_component,
             reviewer_adjustment_component,
             change_reason, rules_applied,
             computed_by, now.isoformat()),
        )

    return ReadinessHistory(
        id=entry_id,
        project_id=project_id,
        feature_id=feature_id,
        readiness_score=readiness_score,
        opus_confidence_component=opus_confidence_component,
        test_pass_rate_component=test_pass_rate_component,
        evidence_score_component=evidence_score_component,
        diff_quality_component=diff_quality_component,
        reviewer_adjustment_component=reviewer_adjustment_component,
        change_reason=change_reason,
        rules_applied=rules_applied,
        computed_by=computed_by,
        created_at=now,
    )


def get_readiness_entry(entry_id: str) -> ReadinessHistory | None:
    """Retrieve a single readiness history entry by ID.

    Returns:
        The ReadinessHistory, or None if not found.
    """
    select = f"SELECT {', '.join(_READINESS_HISTORY_COLUMNS)} FROM readiness_history WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (entry_id,))
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_readiness_history(row)


def get_readiness_history(
    *,
    feature_id: str,
) -> list[ReadinessHistory]:
    """Query readiness history entries for a feature.

    Args:
        feature_id: Filter by feature ID.

    Returns:
        List of matching ReadinessHistory entries, ordered by created_at ascending.
    """
    select = (
        f"SELECT {', '.join(_READINESS_HISTORY_COLUMNS)} FROM readiness_history "
        "WHERE feature_id = ? ORDER BY created_at ASC"
    )

    with connect() as conn:
        cursor = conn.execute(select, (feature_id,))
        rows = cursor.fetchall()
    return [_row_to_readiness_history(row) for row in rows]


# ============================================================
# CASCADE UPDATE DEPENDENT FEATURES (F123)
# ============================================================


def cascade_update_dependents(feature_id: str) -> list[str]:
    """Auto-transition pending features to 'ready' when dependencies complete.

    After a feature completes, finds all features that depend on it and checks:
    1. The dependent feature has status='pending'
    2. ALL of its dependencies are now 'completed'
    3. Its readiness_score >= the threshold for its risk_category

    If all conditions are met, transitions the dependent to status='ready'.

    Args:
        feature_id: The ID of the just-completed feature.

    Returns:
        List of feature IDs that were transitioned to 'ready'.
    """
    transitioned: list[str] = []
    dependents = get_feature_dependents(feature_id)

    for dep in dependents:
        dependent_feature = get_feature(dep.feature_id)
        if dependent_feature is None:
            continue
        # Only transition features that are currently 'pending'
        if dependent_feature.status != "pending":
            continue

        # Check if ALL dependencies of this dependent are completed
        all_deps = get_feature_dependencies(dep.feature_id)
        all_completed = all(
            _dep_feature_is_completed(d.depends_on_feature_id) for d in all_deps
        )
        if not all_completed:
            continue

        # Check readiness threshold for risk category
        threshold = RISK_THRESHOLDS.get(dependent_feature.risk_category, 0.80)
        if dependent_feature.readiness_score < threshold:
            continue

        # All conditions met: transition to 'ready'
        update_feature(dep.feature_id, status="ready")
        transitioned.append(dep.feature_id)
        logger.info(
            "Cascade: transitioned feature %s to 'ready' after %s completed "
            "(readiness=%.2f, threshold=%.2f, risk=%s)",
            dep.feature_id,
            feature_id,
            dependent_feature.readiness_score,
            threshold,
            dependent_feature.risk_category,
        )

    return transitioned


def _dep_feature_is_completed(feature_id: str) -> bool:
    """Check if a dependency feature has status 'completed'."""
    feature = get_feature(feature_id)
    if feature is None:
        return False
    return feature.status == "completed"


# ============================================================
# SPEC CHANGE DETECTION (F115)
# ============================================================


def compute_spec_hash(spec_path: pathlib.Path | str) -> str:
    """Compute SHA256 hash of a spec file.

    Args:
        spec_path: Path to the spec YAML file.

    Returns:
        SHA256 hex digest string (64 characters).

    Raises:
        FileNotFoundError: If the spec file does not exist.
    """
    spec_path = pathlib.Path(spec_path)
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")
    content = spec_path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def check_spec_changed(project_id: str) -> tuple[bool, str | None, str | None]:
    """Check whether the spec file has changed since the last stored hash.

    Args:
        project_id: The project ID to check.

    Returns:
        A tuple of (changed, old_hash, new_hash).
        - changed: True if the spec has changed (or no hash was stored).
        - old_hash: The previously stored hash (None if not set).
        - new_hash: The current hash (None if no spec_path).
    """
    project = get_project(project_id)
    if project is None:
        return False, None, None

    if not project.spec_path:
        return False, None, None

    spec_path = pathlib.Path(project.spec_path)
    if not spec_path.exists():
        return False, project.spec_hash, None

    new_hash = compute_spec_hash(spec_path)
    old_hash = project.spec_hash

    if old_hash is None:
        return True, None, new_hash

    changed = old_hash != new_hash
    return changed, old_hash, new_hash


def diff_features(
    old_features: list[dict],
    new_features: list[dict],
) -> dict[str, list[dict]]:
    """Identify added, modified, and removed features by comparing two feature lists.

    Features are matched by their 'name' field.

    Args:
        old_features: List of feature dicts from the previous spec.
        new_features: List of feature dicts from the current spec.

    Returns:
        Dict with keys 'added', 'modified', 'removed', each containing
        a list of feature dicts.
    """
    # Use 'name' or fall back to 'title' or 'id' for keying features.
    def _get_feature_key(f: dict) -> str:
        return f.get("name") or f.get("title") or f.get("id") or ""
    old_by_name = {_get_feature_key(f): f for f in old_features if _get_feature_key(f)}
    new_by_name = {_get_feature_key(f): f for f in new_features if _get_feature_key(f)}

    added = [f for name, f in new_by_name.items() if name not in old_by_name]
    removed = [f for name, f in old_by_name.items() if name not in new_by_name]
    modified = []

    for name in old_by_name:
        if name in new_by_name:
            old_feat = old_by_name[name]
            new_feat = new_by_name[name]
            if old_feat != new_feat:
                modified.append(new_feat)

    return {"added": added, "modified": modified, "removed": removed}


def detect_spec_changes(project_id: str) -> dict[str, list[dict]] | None:
    """Detect spec changes and update the database accordingly.

    Re-parses the spec file, diffs features against the database,
    and applies changes: adds new features, resets modified features to
    pending, and logs all changes.

    Args:
        project_id: The project ID to check.

    Returns:
        A dict with 'added', 'modified', 'removed' feature lists,
        or None if the project has no spec_path.
    """
    import yaml

    project = get_project(project_id)
    if project is None or not project.spec_path:
        return None

    spec_path = pathlib.Path(project.spec_path)
    if not spec_path.exists():
        return None

    # Parse current spec
    try:
        with open(spec_path) as f:
            spec = yaml.safe_load(f)
    except yaml.YAMLError:
        logger.error("Failed to parse spec file: %s", spec_path)
        return None

    if spec is None:
        spec = {}

    new_spec_features = spec.get("features") or []

    # Build old features list from database
    db_features = list_features(project_id=project_id)
    old_spec_features = []
    for f in db_features:
        feat_dict = {"name": f.name}
        if f.description:
            feat_dict["description"] = f.description
        if f.priority != 100:
            feat_dict["priority"] = f.priority
        if f.acceptance_criteria:
            try:
                feat_dict["acceptance_criteria"] = json.loads(f.acceptance_criteria)
            except (json.JSONDecodeError, TypeError):
                feat_dict["acceptance_criteria"] = f.acceptance_criteria
        old_spec_features.append(feat_dict)

    # Normalize new features to dict format
    normalized_new = []
    for feat in new_spec_features:
        if isinstance(feat, dict):
            normalized_new.append(feat)
        else:
            normalized_new.append({"name": str(feat)})

    changes = diff_features(old_spec_features, normalized_new)

    has_changes = bool(changes["added"] or changes["modified"] or changes["removed"])

    if has_changes:
        # Apply added features
        def _get_feat_key(f: dict) -> str:
            return f.get("name") or f.get("title") or f.get("id") or ""

        def _parse_priority(p) -> int:
            if p is None:
                return 100
            if isinstance(p, int):
                return p
            # Map string priorities to integers
            pmap = {"low": 30, "medium": 50, "high": 70, "critical": 90}
            if isinstance(p, str):
                return pmap.get(p.lower(), 100)
            return 100

        for feat in changes["added"]:
            ac = feat.get("acceptance_criteria")
            if isinstance(ac, list):
                ac = json.dumps(ac)
            feat_name = _get_feat_key(feat)
            if not feat_name:
                continue
            create_feature(
                project_id=project_id,
                name=feat_name,
                description=feat.get("description"),
                priority=_parse_priority(feat.get("priority")),
                acceptance_criteria=ac,
                status="pending",
            )

        # Apply modified features: reset to pending
        for feat in changes["modified"]:
            feat_name = _get_feat_key(feat)
            if not feat_name:
                continue
            for db_feat in db_features:
                if db_feat.name == feat_name:
                    updates = {"status": "pending"}
                    if feat.get("description"):
                        updates["description"] = feat["description"]
                    if feat.get("priority") is not None:
                        updates["priority"] = _parse_priority(feat["priority"])
                    ac = feat.get("acceptance_criteria")
                    if ac is not None:
                        if isinstance(ac, list):
                            ac = json.dumps(ac)
                        updates["acceptance_criteria"] = ac
                    update_feature(db_feat.id, **updates)
                    break

        # Log the change
        details = json.dumps({
            "added": [_get_feat_key(f) for f in changes["added"] if _get_feat_key(f)],
            "modified": [_get_feat_key(f) for f in changes["modified"] if _get_feat_key(f)],
            "removed": [_get_feat_key(f) for f in changes["removed"] if _get_feat_key(f)],
        })
        log_event(
            project_id=project_id,
            event="spec_change_detected",
            level="info",
            details=details,
        )

    # Update stored hash
    new_hash = compute_spec_hash(spec_path)
    update_project(project_id, spec_hash=new_hash)

    return changes


# ============================================================
# VIEW QUERY FUNCTIONS (F068)
# ============================================================
# Each function queries one of the SQL views defined in schema.sql
# and returns a list of dicts for flexible status reporting.


def query_features_ready(project_id: str) -> list[dict]:
    """Query the features_ready view for features meeting readiness thresholds.

    Returns features that are:
    - status = 'ready'
    - readiness_score >= risk-category threshold
    - no active reviewer vetoes
    - all dependencies completed
    """
    select = (
        f"SELECT {', '.join(_FEATURE_COLUMNS)} FROM features_ready "
        "WHERE project_id = ? ORDER BY priority ASC, created_at ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(_FEATURE_COLUMNS, row)) for row in rows]


def query_features_needing_refinement(project_id: str) -> list[dict]:
    """Query the features_needing_refinement view.

    Returns features below their risk-category readiness threshold
    that still have refinement attempts remaining and are not in
    a blocked status.
    """
    select = (
        f"SELECT {', '.join(_FEATURE_COLUMNS)} FROM features_needing_refinement "
        "WHERE project_id = ? ORDER BY priority ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(_FEATURE_COLUMNS, row)) for row in rows]


def query_features_pending_decomposition(project_id: str) -> list[dict]:
    """Query the features_pending_decomposition view.

    Returns features with status 'pending_decomposition' or
    exceeds_size_limits = TRUE.
    """
    select = (
        f"SELECT {', '.join(_FEATURE_COLUMNS)} FROM features_pending_decomposition "
        "WHERE project_id = ? ORDER BY priority ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(_FEATURE_COLUMNS, row)) for row in rows]


def query_features_blocked(project_id: str) -> list[dict]:
    """Query the features_blocked view.

    Returns features with blocking statuses and the reason for the block.
    View columns: id, name, status, block_reason.
    """
    cols = ("id", "name", "status", "block_reason")
    select = (
        f"SELECT {', '.join(cols)} FROM features_blocked "
        "WHERE id IN (SELECT id FROM features WHERE project_id = ?)"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_features_needs_human(project_id: str) -> list[dict]:
    """Query the features_needs_human view.

    Returns features requiring human intervention due to:
    - status = 'needs_human'
    - max refinement attempts reached
    - excessive research iterations
    - deep decomposition
    - critical features without human approval
    """
    select = (
        f"SELECT {', '.join(_FEATURE_COLUMNS)} FROM features_needs_human "
        "WHERE project_id = ? ORDER BY priority ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(_FEATURE_COLUMNS, row)) for row in rows]


def query_unresolved_issues(project_id: str) -> list[dict]:
    """Query the unresolved_issues view.

    Returns features that have unresolved review issues, with
    issue count and concatenated descriptions.
    View columns: feature_id, feature_name, issue_count, issues.
    """
    cols = ("feature_id", "feature_name", "issue_count", "issues")
    select = (
        f"SELECT {', '.join(cols)} FROM unresolved_issues "
        "WHERE feature_id IN (SELECT id FROM features WHERE project_id = ?)"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_reviews_pending(project_id: str) -> list[dict]:
    """Query the reviews_pending view.

    Returns reviews awaiting a verdict, with feature info and wait time.
    """
    cols = list(_REVIEW_COLUMNS) + ["feature_name", "risk_category", "priority", "hours_waiting"]
    select = (
        f"SELECT {', '.join(cols)} FROM reviews_pending "
        "WHERE project_id = ? ORDER BY priority ASC, review_requested_at ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_review_timeouts(project_id: str) -> list[dict]:
    """Query the review_timeouts view.

    Returns reviews that have exceeded their timeout period.
    """
    cols = list(_REVIEW_COLUMNS) + ["feature_name", "risk_category", "hours_waiting"]
    select = (
        f"SELECT {', '.join(cols)} FROM review_timeouts "
        "WHERE project_id = ? ORDER BY review_requested_at ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_stale_evidence(project_id: str) -> list[dict]:
    """Query the stale_evidence view.

    Returns evidence artifacts that are marked current but may be stale
    due to iteration age or environment mismatch.
    """
    cols = list(_EVIDENCE_COLUMNS) + ["feature_name"]
    select = (
        f"SELECT {', '.join(cols)} FROM stale_evidence "
        "WHERE project_id = ? ORDER BY created_at DESC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_calibration_drift_summary(project_id: str) -> list[dict]:
    """Query the calibration_drift_summary view.

    Returns calibration data per task_class/confidence_bucket for entries
    with 10+ attempts. Includes drift status (overconfident/underconfident/calibrated).
    """
    cols = ("task_class", "confidence_bucket", "empirical_pass_rate",
            "expected_pass_rate", "drift", "total_attempts", "status")
    select = (
        f"SELECT {', '.join(cols)} FROM calibration_drift_summary "
        "WHERE (task_class, confidence_bucket) IN ("
        "  SELECT task_class, confidence_bucket FROM calibration_data WHERE project_id = ?"
        ")"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_active_regressions(project_id: str) -> list[dict]:
    """Query the active_regressions view.

    Returns unresolved regression events with feature names.
    """
    cols = list(_REGRESSION_EVENT_COLUMNS) + ["affected_feature_name", "causing_feature_name"]
    select = (
        f"SELECT {', '.join(cols)} FROM active_regressions "
        "WHERE project_id = ? ORDER BY detected_at DESC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_flaky_tests_pending(project_id: str) -> list[dict]:
    """Query the flaky_tests_pending view.

    Returns flaky tests that are not yet completed, with pass/fail counts.
    """
    cols = list(_TASK_COLUMNS) + ["feature_name", "pass_count", "total_runs"]
    select = (
        f"SELECT {', '.join(cols)} FROM flaky_tests_pending "
        "WHERE project_id = ? ORDER BY created_at DESC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_scope_creep_alerts(project_id: str) -> list[dict]:
    """Query the scope_creep_alerts view.

    Returns features where current task count exceeds 2x the original.
    """
    cols = ("id", "name", "original_acceptance_criteria_count",
            "current_criteria_count", "original_task_count", "current_task_count")
    select = (
        f"SELECT {', '.join(cols)} FROM scope_creep_alerts "
        "WHERE id IN (SELECT id FROM features WHERE project_id = ?)"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_potential_gaming(project_id: str) -> list[dict]:
    """Query the potential_gaming view.

    Returns confidence scores that have been reported identically 3+ times,
    which may indicate gaming.
    """
    cols = ("feature_id", "task_id", "conf_impl_correctness", "times_reported")
    select = (
        f"SELECT {', '.join(cols)} FROM potential_gaming "
        "WHERE feature_id IN (SELECT id FROM features WHERE project_id = ?)"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_test_integrity_violations_view(project_id: str) -> list[dict]:
    """Query the test_integrity_violations view.

    Returns validation tasks with weakened assertions or decreased coverage.
    View columns: id, title, feature_name, original_assertion_count,
    current_assertion_count, original_coverage_percent, current_coverage_percent.
    """
    cols = ("id", "title", "feature_name", "original_assertion_count",
            "current_assertion_count", "original_coverage_percent",
            "current_coverage_percent")
    select = (
        f"SELECT {', '.join(cols)} FROM test_integrity_violations "
        "WHERE id IN (SELECT id FROM tasks WHERE project_id = ?)"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_resource_usage(project_id: str) -> list[dict]:
    """Query the resource_usage view.

    Returns project resource consumption including cost percentage
    and feature completion counts.
    """
    cols = ("id", "name", "total_cost_usd", "max_cost_usd",
            "cost_percent_used", "features_completed", "features_total")
    select = f"SELECT {', '.join(cols)} FROM resource_usage WHERE id = ?"
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_active_bugs(project_id: str) -> list[dict]:
    """Query the active_bugs view.

    Returns unresolved bugs with feature name.
    """
    cols = list(_BUG_COLUMNS) + ["feature_name"]
    select = (
        f"SELECT {', '.join(cols)} FROM active_bugs "
        "WHERE project_id = ? ORDER BY created_at DESC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_orphaned_features(project_id: str) -> list[dict]:
    """Query the orphaned_features view.

    Returns child features whose parent feature has been abandoned
    (failed, needs_human, rolled_back).
    """
    select = (
        f"SELECT {', '.join(_FEATURE_COLUMNS)} FROM orphaned_features "
        "WHERE project_id = ? ORDER BY priority ASC"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(_FEATURE_COLUMNS, row)) for row in rows]


def query_oversized_features(project_id: str) -> list[dict]:
    """Query the oversized_features view.

    Returns features exceeding size limits with the reason.
    View columns: id, name, status, impl_tasks, validation_tasks,
    total_tasks, estimated_lines_of_code, estimated_files_touched,
    estimated_complexity, limit_exceeded.
    """
    cols = ("id", "name", "status", "impl_tasks", "validation_tasks",
            "total_tasks", "estimated_lines_of_code", "estimated_files_touched",
            "estimated_complexity", "limit_exceeded")
    select = (
        f"SELECT {', '.join(cols)} FROM oversized_features "
        "WHERE id IN (SELECT id FROM features WHERE project_id = ?)"
    )
    with connect() as conn:
        cursor = conn.execute(select, (project_id,))
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_all_views(project_id: str) -> dict[str, list[dict]]:
    """Query all database views and return an aggregated status report.

    Returns a dictionary keyed by view name, each containing a list of
    dicts from the corresponding view query function.
    """
    return {
        "features_ready": query_features_ready(project_id),
        "features_needing_refinement": query_features_needing_refinement(project_id),
        "features_pending_decomposition": query_features_pending_decomposition(project_id),
        "features_blocked": query_features_blocked(project_id),
        "features_needs_human": query_features_needs_human(project_id),
        "unresolved_issues": query_unresolved_issues(project_id),
        "reviews_pending": query_reviews_pending(project_id),
        "review_timeouts": query_review_timeouts(project_id),
        "stale_evidence": query_stale_evidence(project_id),
        "calibration_drift_summary": query_calibration_drift_summary(project_id),
        "active_regressions": query_active_regressions(project_id),
        "flaky_tests_pending": query_flaky_tests_pending(project_id),
        "scope_creep_alerts": query_scope_creep_alerts(project_id),
        "potential_gaming": query_potential_gaming(project_id),
        "test_integrity_violations": query_test_integrity_violations_view(project_id),
        "resource_usage": query_resource_usage(project_id),
        "active_bugs": query_active_bugs(project_id),
        "orphaned_features": query_orphaned_features(project_id),
        "oversized_features": query_oversized_features(project_id),
    }
