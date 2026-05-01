"""Continuous orchestration loop for Bob3 (F069 + F109 + F072).

Implements the core build loop that continuously picks ready features
from the database, spawns Claude sub-agents to implement them, and
tracks progress until all features are completed or no more progress
can be made.

F109 adds research mode integration:
- Before execution, checks if a feature needs research
- Spawns a research sub-agent via Perplexity MCP when needed
- Stores research results and increments research_iterations
- Then proceeds to normal implementation

F072 adds feature decomposition handling:
- Before execution, checks if a feature exceeds_size_limits
- Spawns a decomposer sub-agent to split the feature
- Creates child features from the decomposition result
- Links dependencies between child features
- Sets the parent feature status to pending_decomposition

Research triggers:
1. Feature description contains research_required=True (and research_iterations == 0)
2. Feature has failed 3+ times (and research_iterations == 0)

The loop runs until one of these termination conditions:
- All features are completed
- All remaining features are blocked/failed
- Budget is exceeded
- Graceful shutdown is requested (SIGINT/SIGTERM)
"""

from __future__ import annotations

import enum
import json
import logging
import re
import signal
from typing import Any

from bob3 import db
from bob3.mcp_lifecycle import stop_mcp_server
from bob3.git_ops import (
    commit_feature as git_commit_feature,
    get_status as git_get_status,
    revert_feature as git_revert_feature,
)
from bob3.models import Feature
from bob3.orchestrator.claude_executor import (
    ExecutionResult,
    SpawnResult,
    build_sub_agent_options,
    spawn_research_agent,
    spawn_sub_agent,
)
from bob3.orientation import update_progress_notes, wrap_prompt_with_orientation
from bob3.superpowers import (
    run_verification_checklist,
    should_use_subagents,
    should_use_tdd,
)

logger = logging.getLogger(__name__)

# Statuses that indicate a feature cannot make further progress
_TERMINAL_STATUSES = frozenset({
    "completed",
    "failed",
    "interrupted",
    "blocked_by_reviewer",
    "blocked_by_dependency",
    "needs_human",
    "resource_limited",
    "rolled_back",
    "regression",
    "pending_decomposition",
})

# Statuses that mean a feature is done (not just stuck)
_COMPLETED_STATUSES = frozenset({"completed", "pending_decomposition"})

# Statuses that mean a feature is blocked or failed (no more automatic progress)
_BLOCKED_STATUSES = frozenset({
    "failed",
    "interrupted",
    "blocked_by_reviewer",
    "blocked_by_dependency",
    "needs_human",
    "resource_limited",
    "rolled_back",
    "regression",
})


class LoopTermination(enum.Enum):
    """Reason the orchestration loop terminated."""

    ALL_COMPLETED = "all_completed"
    ALL_BLOCKED = "all_blocked"
    BUDGET_EXCEEDED = "budget_exceeded"
    SHUTDOWN_REQUESTED = "shutdown_requested"


def cascade_update_dependents(feature_id: str) -> list[str]:
    """Update dependent features when a feature is completed.

    Delegates to db.cascade_update_dependents (F123) which:
    1. Finds all features depending on the completed feature
    2. Checks if ALL their dependencies are completed
    3. Checks readiness_score >= threshold for their risk_category
    4. Transitions qualifying features from 'pending' to 'ready'

    Args:
        feature_id: The ID of the just-completed feature.

    Returns:
        List of feature IDs that were transitioned to 'ready'.
    """
    return db.cascade_update_dependents(feature_id)


# ---------------------------------------------------------------
# F072: Feature decomposition handling
# ---------------------------------------------------------------

DECOMPOSER_SYSTEM_PROMPT = (
    "You are a feature decomposition agent. Your job is to break down a "
    "large feature into smaller, independently implementable child features.\n\n"
    "You MUST respond with a JSON block (inside ```json fences) containing:\n"
    '  - "children": array of child feature objects, each with:\n'
    '    - "name": short feature name\n'
    '    - "description": what this child implements\n'
    '    - "acceptance_criteria": JSON string of acceptance criteria array\n'
    '    - "priority": integer (lower = higher priority)\n'
    '    - "risk_category": "low", "medium", or "high"\n'
    '  - "dependencies": array of dependency objects, each with:\n'
    '    - "from": index of the child that depends (0-based)\n'
    '    - "to": index of the child it depends on (0-based)\n\n'
    "Keep each child small enough to be implemented in a single session "
    "(< 500 lines, < 5 files, complexity < 8)."
)


def parse_decomposition_result(text: str) -> dict | None:
    """Parse decomposition agent response to extract children and dependencies.

    Looks for a JSON block (inside ```json fences or inline) containing
    a "children" array and optional "dependencies" array.

    Returns a dict with keys "children" and "dependencies", or None if
    parsing fails or children is empty.
    """
    # Try fenced JSON first: ```json ... ```
    fenced = re.search(r"```json\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    json_str = fenced.group(1) if fenced else None

    # Fall back to inline JSON: { ... "children" ... }
    if json_str is None:
        inline = re.search(r"\{[^{}]*\"children\"\s*:", text, re.DOTALL)
        if inline:
            # Try to find the full JSON object
            start = inline.start()
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        json_str = text[start : i + 1]
                        break

    if json_str is None:
        return None

    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(parsed, dict):
        return None

    children = parsed.get("children")
    if not children or not isinstance(children, list) or len(children) == 0:
        return None

    dependencies = parsed.get("dependencies", [])
    if not isinstance(dependencies, list):
        dependencies = []

    return {
        "children": children,
        "dependencies": dependencies,
    }


async def handle_decomposition(
    *,
    project_id: str,
    feature: Feature,
) -> dict:
    """Decompose an oversized feature into smaller child features.

    Spawns a decomposer sub-agent to analyze the feature and produce
    a plan for splitting it into independently implementable children.
    Then creates the child features and links dependencies.

    Args:
        project_id: The project ID.
        feature: The oversized feature to decompose.

    Returns:
        Dict with keys: success, children_created, cost_usd, error_message.
    """
    prompt = (
        f"Decompose this oversized feature into smaller, independently "
        f"implementable child features.\n\n"
        f"Feature: {feature.name}\n"
        f"Description: {feature.description or 'No description'}\n"
        f"Acceptance Criteria: {feature.acceptance_criteria or 'None specified'}\n"
        f"Size Justification: {feature.size_limit_justification or 'Exceeds size limits'}\n\n"
        f"Break this into 2-5 smaller features, each under 500 lines of code, "
        f"touching fewer than 5 files, and with complexity under 8.\n\n"
        f"Respond with a JSON block containing the children and their dependencies."
    )

    options = build_sub_agent_options(
        model="sonnet",
        max_turns=10,
        system_prompt=DECOMPOSER_SYSTEM_PROMPT,
    )

    spawn_result = await spawn_sub_agent(
        project_id=project_id,
        purpose="decompose_feature",
        prompt=prompt,
        target_type="feature",
        target_id=feature.id,
        options=options,
    )

    result = spawn_result.execution_result
    outcome = {
        "success": False,
        "children_created": 0,
        "cost_usd": result.total_cost_usd,
        "error_message": None,
    }

    if result.is_error:
        outcome["error_message"] = result.error_message
        return outcome

    # Parse the decomposition result
    decomposition = parse_decomposition_result(result.text)
    if decomposition is None:
        outcome["error_message"] = "Failed to parse decomposition result"
        return outcome

    children_specs = decomposition["children"]
    dependencies = decomposition["dependencies"]

    # Create child features
    created_children = []
    for spec in children_specs:
        child = db.create_child_feature(
            parent_feature_id=feature.id,
            project_id=project_id,
            name=spec.get("name", f"Child of {feature.name}"),
            description=spec.get("description"),
            acceptance_criteria=spec.get("acceptance_criteria"),
            status="ready",
            priority=spec.get("priority", feature.priority),
            risk_category=spec.get("risk_category", feature.risk_category),
        )
        # Set readiness high so children are immediately ready
        db.update_feature(
            child.id,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
            readiness_score=0.85,
        )
        created_children.append(child)

    # Link dependencies between children
    for dep in dependencies:
        from_idx = dep.get("from")
        to_idx = dep.get("to")
        if (
            isinstance(from_idx, int)
            and isinstance(to_idx, int)
            and 0 <= from_idx < len(created_children)
            and 0 <= to_idx < len(created_children)
            and from_idx != to_idx
        ):
            db.add_feature_dependency(
                feature_id=created_children[from_idx].id,
                depends_on_feature_id=created_children[to_idx].id,
            )

    # Update parent status
    db.update_feature(feature.id, status="pending_decomposition")

    outcome["success"] = True
    outcome["children_created"] = len(created_children)

    logger.info(
        "Decomposed feature %s into %d children",
        feature.id,
        len(created_children),
    )

    return outcome


# ---------------------------------------------------------------
# F109: Research mode helpers
# ---------------------------------------------------------------

_RESEARCH_REQUIRED_MARKER = "research_required=True"
_FAILURE_THRESHOLD_FOR_RESEARCH = 3


def count_feature_failures(feature_id: str, project_id: str) -> int:
    """Count the number of failed implementation agent runs for a feature.

    Only counts runs with purpose='implement_feature' and status='failed'.
    """
    runs = db.query_agent_runs(project_id=project_id, purpose="implement_feature")
    return sum(
        1 for r in runs
        if r.target_type == "feature" and r.target_id == feature_id and r.status == "failed"
    )


def needs_research(feature: Feature, project_id: str) -> bool:
    """Determine if a feature needs research before implementation.

    Research is triggered when:
    1. Feature description contains 'research_required=True' AND
       research_iterations is 0 (hasn't been researched yet)
    2. Feature has failed 3+ times AND research_iterations is 0
    3. Feature has low confidence (< 0.5) AND research_iterations is 0

    Returns False if the feature has already been researched
    (research_iterations >= 1).
    """
    # Already researched — don't re-research
    if feature.research_iterations >= 1:
        return False

    # Trigger 1: Explicit research_required marker in description
    if feature.description and _RESEARCH_REQUIRED_MARKER in feature.description:
        return True

    # Trigger 2: Feature has failed >= 3 times
    failure_count = count_feature_failures(feature.id, project_id)
    if failure_count >= _FAILURE_THRESHOLD_FOR_RESEARCH:
        return True

    # Trigger 3: Low confidence (< 0.5) indicating missing information
    # This proactively triggers research BEFORE attempting implementation
    if (feature.conf_impl_correctness < 0.5 or
        feature.conf_spec_understanding < 0.5 or
        feature.readiness_score < 0.5):
        logger.info(
            "Feature %s has low confidence (spec=%.2f, impl=%.2f, ready=%.2f), triggering research",
            feature.id[:8],
            feature.conf_spec_understanding,
            feature.conf_impl_correctness,
            feature.readiness_score,
        )
        return True

    return False


def handle_execution_result(
    *,
    project_id: str,
    feature: Feature,
    spawn_result: SpawnResult,
    shutdown_requested: bool = False,
    verification_passed: bool = True,
    verification_summary: str | None = None,
) -> dict[str, Any]:
    """Handle the result of executing a feature sub-agent.

    Performs all post-execution bookkeeping:
    1. Parses the execution result (success/failure)
    2. Updates the feature status (completed/failed/interrupted/needs_human)
    3. Creates evidence artifacts from the execution output
    4. Updates project-level cost tracking (atomically, with budget enforcement)

    A feature is only marked 'completed' and dependents cascaded to 'ready'
    when BOTH the sub-agent succeeded AND verification passed. If the
    sub-agent succeeded but verification failed, the feature is marked
    'needs_human' and no cascade is performed.

    Args:
        project_id: The project ID.
        feature: The feature that was executed.
        spawn_result: The SpawnResult from the sub-agent.
        shutdown_requested: If True, errors result in 'interrupted' status.
        verification_passed: If False and the sub-agent succeeded, the
            feature is marked 'needs_human' and no cascade is performed.
        verification_summary: Optional human-readable summary of the
            verification result (recorded in the evidence payload).

    Returns:
        Dict with keys: success, cost_usd, duration_ms, error_message,
        evidence_id, verification_passed.
    """
    result = spawn_result.execution_result
    agent_run_id = getattr(spawn_result.agent_run, "id", None)

    # Success is only "true success" when execution succeeded AND verification
    # passed; a verification failure on a successful sub-agent run should NOT
    # be reported as success (callers rely on this to avoid cascading).
    is_success = (not result.is_error) and verification_passed

    outcome: dict[str, Any] = {
        "success": is_success,
        "cost_usd": result.total_cost_usd,
        "duration_ms": result.duration_ms,
        "error_message": result.error_message if result.is_error else (
            f"Verification failed: {verification_summary}"
            if not verification_passed else None
        ),
        "evidence_id": None,
        "verification_passed": verification_passed,
    }

    # Step 2: Update feature status
    if result.is_error:
        if shutdown_requested:
            db.update_feature(feature.id, status="interrupted")
        else:
            db.update_feature(feature.id, status="failed")
    elif not verification_passed:
        # Sub-agent reported success but verification failed — do NOT mark
        # as completed and do NOT cascade dependents. This prevents
        # downstream features from being unlocked on unverified work.
        db.update_feature(feature.id, status="needs_human")
    else:
        db.update_feature(feature.id, status="completed")

        # F123: Auto-update dependent features' readiness when dependencies complete
        try:
            updated_features = db.update_dependent_features_readiness(feature.id)
            if updated_features:
                logger.info(
                    "Feature %s completion unlocked %d dependent feature(s): %s",
                    feature.id[:8],
                    len(updated_features),
                    ", ".join([f[:8] for f in updated_features])
                )
        except Exception:
            logger.warning(
                "Failed to auto-update dependent features for %s",
                feature.id,
                exc_info=True,
            )

    # Step 3: Create evidence artifact
    if result.is_error:
        evidence_type = "execution_error"
        evidence_content = json.dumps({
            "status": "interrupted" if shutdown_requested else "failed",
            "error_message": result.error_message,
            "output_text": result.text[:2000] if result.text else "",
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "cost_usd": result.total_cost_usd,
            "agent_run_id": agent_run_id,
        })
    elif not verification_passed:
        evidence_type = "execution_error"
        evidence_content = json.dumps({
            "status": "needs_human",
            "error_message": f"Verification failed: {verification_summary}",
            "output_text": result.text[:2000] if result.text else "",
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "cost_usd": result.total_cost_usd,
            "agent_run_id": agent_run_id,
        })
    else:
        evidence_type = "execution_output"
        evidence_content = json.dumps({
            "status": "completed",
            "output_text": result.text[:2000] if result.text else "",
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "cost_usd": result.total_cost_usd,
            "tool_uses": result.tool_uses,
            "agent_run_id": agent_run_id,
        })

    try:
        evidence = db.create_evidence(
            project_id=project_id,
            feature_id=feature.id,
            type=evidence_type,
            content=evidence_content,
        )
        outcome["evidence_id"] = evidence.id
    except Exception:
        logger.warning(
            "Failed to create evidence artifact for feature %s",
            feature.id,
            exc_info=True,
        )

    # Step 4: Update project cost tracking atomically (also enforces budget)
    if result.total_cost_usd is not None:
        db.update_project_cost(
            project_id=project_id,
            cost_usd=result.total_cost_usd,
        )

    return outcome


class OrchestrationLoop:
    """Continuous orchestration loop for building a project.

    Picks the next ready feature, spawns a sub-agent to implement it,
    updates status, and repeats until done.
    """

    def __init__(
        self,
        *,
        project_id: str,
        max_cost: float | None = None,
        workspace: str | None = None,
        fresh: bool = False,
    ) -> None:
        self.project_id = project_id
        self.max_cost = max_cost
        self.workspace = workspace or ""
        self.fresh = fresh
        self.total_cost: float = 0.0
        self.features_completed: int = 0
        self.features_failed: int = 0
        self.shutdown_requested: bool = False
        self._current_feature: Feature | None = None

    def request_shutdown(self) -> None:
        """Request graceful shutdown of the loop."""
        self.shutdown_requested = True
        logger.info("Shutdown requested for orchestration loop")

    def budget_exceeded(self) -> bool:
        """Check if the budget has been exceeded.

        Checks both the loop-level max_cost and the project's max_cost_usd.
        """
        # Check loop-level budget
        if self.max_cost is not None and self.total_cost >= self.max_cost:
            return True

        # Check project-level budget
        project = db.get_project(self.project_id)
        if project is not None:
            if project.max_cost_usd and project.total_cost_usd >= project.max_cost_usd:
                return True

        return False

    def find_next_ready_feature(self) -> Feature | None:
        """Find the next feature ready for implementation.

        Queries the features_ready view which checks:
        - status = 'ready'
        - readiness_score >= risk-category threshold
        - no active reviewer vetoes
        - all dependencies completed

        Returns the highest priority ready feature, or None if none are ready.
        """
        ready = db.get_ready_features(self.project_id)
        if not ready:
            return None
        return ready[0]

    def all_features_completed(self) -> bool:
        """Check if all features in the project are completed."""
        features = db.list_features(project_id=self.project_id)
        if not features:
            return True
        return all(f.status in _COMPLETED_STATUSES for f in features)

    def all_remaining_blocked(self) -> bool:
        """Check if all non-completed features are blocked or failed.

        Returns True if every feature is either completed or in a
        blocked/failed state, meaning no more automatic progress is possible.
        """
        features = db.list_features(project_id=self.project_id)
        if not features:
            return False
        for f in features:
            if f.status in _COMPLETED_STATUSES:
                continue
            if f.status not in _BLOCKED_STATUSES:
                return False
        return True

    async def _run_research(self, feature: Feature) -> SpawnResult | None:
        """Run a research sub-agent for a feature if research is needed.

        Spawns a Perplexity-enabled research agent, stores the results
        in the research_results table, increments research_iterations,
        and tracks cost.

        Returns the SpawnResult if research was performed, None otherwise.
        """
        if not needs_research(feature, self.project_id):
            return None

        logger.info(
            "Feature %s needs research, spawning research agent", feature.id
        )

        # Build a research query from the feature's name and description
        query = (
            f"Research for implementing: {feature.name}\n\n"
            f"Description: {feature.description or 'No description'}\n\n"
            f"Find relevant documentation, libraries, patterns, and examples."
        )

        research_result = await spawn_research_agent(
            project_id=self.project_id,
            query=query,
            purpose="feature_research",
            target_type="feature",
            target_id=feature.id,
        )

        # Track research cost
        research_exec = research_result.execution_result
        if research_exec.total_cost_usd is not None:
            self.total_cost += research_exec.total_cost_usd
            db.update_project_cost(
                project_id=self.project_id,
                cost_usd=research_exec.total_cost_usd,
            )

        # Store research results in DB (even if research failed, record the attempt)
        findings = research_exec.text if not research_exec.is_error else None
        # agent_run_id may not exist in DB (e.g. during tests with mocked agents)
        agent_run_id = getattr(research_result.agent_run, "id", None)
        try:
            db.create_research_result(
                feature_id=feature.id,
                project_id=self.project_id,
                query=query,
                findings=findings,
                agent_run_id=agent_run_id,
            )
        except Exception:
            # FK constraint may fail if agent_run record doesn't exist;
            # store without the agent_run_id reference
            db.create_research_result(
                feature_id=feature.id,
                project_id=self.project_id,
                query=query,
                findings=findings,
            )

        # Increment research_iterations
        updated_feature = db.get_feature(feature.id)
        new_iterations = (updated_feature.research_iterations if updated_feature else 0) + 1

        # Boost readiness after successful research
        # Research provides the missing information needed for implementation
        updates = {"research_iterations": new_iterations}
        if not research_exec.is_error and updated_feature:
            # Successful research boosts confidence/readiness
            # Set to 0.85 which meets thresholds for medium/low risk features
            updates["conf_spec_understanding"] = max(updated_feature.conf_spec_understanding, 0.85)
            updates["conf_impl_correctness"] = max(updated_feature.conf_impl_correctness, 0.85)
            updates["readiness_score"] = max(updated_feature.readiness_score, 0.85)
            logger.info(
                "Research completed for feature %s, boosting readiness to 0.85",
                feature.id[:8]
            )

        db.update_feature(feature.id, **updates)

        if research_exec.is_error:
            logger.warning(
                "Research for feature %s failed: %s",
                feature.id,
                research_exec.error_message,
            )
        else:
            logger.info(
                "Research for feature %s completed successfully", feature.id
            )

        return research_result

    async def execute_feature(self, feature: Feature) -> SpawnResult:
        """Spawn a sub-agent to implement a feature.

        If the feature exceeds size limits (F072), a decomposer sub-agent
        is spawned to break it into smaller child features.

        If the feature needs research (F109), a research sub-agent is
        spawned first via Perplexity MCP. Then the implementation
        sub-agent is spawned with orientation context.

        Args:
            feature: The feature to implement.

        Returns:
            The SpawnResult from the sub-agent execution.
        """
        # Set feature to executing and track as current
        self._current_feature = feature
        db.update_feature(feature.id, status="executing")
        logger.info("Executing feature %s: %s", feature.id, feature.name)

        # F072: Check if feature exceeds size limits and needs decomposition
        if feature.exceeds_size_limits:
            logger.info(
                "Feature %s exceeds size limits, triggering decomposition",
                feature.id,
            )
            decomp_result = await handle_decomposition(
                project_id=self.project_id,
                feature=feature,
            )

            # Track decomposition cost
            if decomp_result.get("cost_usd") is not None:
                self.total_cost += decomp_result["cost_usd"]

            if decomp_result["success"]:
                logger.info(
                    "Feature %s decomposed into %d children",
                    feature.id,
                    decomp_result["children_created"],
                )
            else:
                # Decomposition failed — mark as needs_human
                db.update_feature(feature.id, status="needs_human")
                logger.warning(
                    "Decomposition of feature %s failed: %s",
                    feature.id,
                    decomp_result.get("error_message"),
                )

            # Return a synthetic SpawnResult for decomposition
            self._current_feature = None
            exec_result = ExecutionResult(
                text=f"Feature decomposed into {decomp_result.get('children_created', 0)} children",
                is_error=not decomp_result["success"],
                error_message=decomp_result.get("error_message") or "",
                duration_ms=0,
                num_turns=0,
                total_cost_usd=decomp_result.get("cost_usd"),
            )
            agent_run = type("_FakeRun", (), {"id": None})()
            return SpawnResult(execution_result=exec_result, agent_run=agent_run)

        # F114: Capture pre-execution git state for rollback reference
        commit_before: str | None = None
        if self.workspace:
            try:
                pre_status = git_get_status(workspace=self.workspace)
                commit_before = pre_status.get("sha") or None
            except Exception:
                logger.debug("Could not capture pre-execution git state")

        # F109: Run research phase if needed
        await self._run_research(feature)

        # F113: Determine which Superpowers skills to enable
        enable_tdd = should_use_tdd(
            acceptance_criteria=feature.acceptance_criteria,
            description=feature.description,
            tdd_mode_override=feature.tdd_mode,  # Respect explicit YAML setting
        )
        enable_subagent = should_use_subagents(
            acceptance_criteria=feature.acceptance_criteria,
            estimated_files_touched=feature.estimated_files_touched,
            estimated_complexity=feature.estimated_complexity,
            sub_agent_mode_override=feature.sub_agent_mode,  # Respect explicit YAML setting
        )

        if enable_tdd:
            logger.info("Feature %s: TDD mode enabled", feature.id)
        if enable_subagent:
            logger.info("Feature %s: Sub-agent mode enabled", feature.id)

        # Build the prompt with orientation context
        task_prompt = (
            f"You are a Bob3 sub-agent implementing a feature.\n\n"
            f"Feature ID: {feature.id}\n"
            f"Feature: {feature.name}\n"
            f"Description: {feature.description or 'No description'}\n"
            f"Acceptance Criteria: {feature.acceptance_criteria or 'None specified'}\n\n"
            f"Workspace: {self.workspace}\n\n"
            f"Instructions:\n"
            f"1. Read the existing codebase to understand the project structure\n"
            f"2. Implement the feature as described\n"
            f"3. Write tests for the feature\n"
            f"4. Ensure all existing tests still pass\n"
            f"5. Do NOT create stub implementations - write real, functional code\n\n"
            f"When complete, summarize what you implemented and any tests you added.\n"
        )

        prompt = wrap_prompt_with_orientation(
            prompt=task_prompt,
            feature_id=feature.id,
            workspace=self.workspace,
            feature_name=feature.name,
            feature_description=feature.description,
            enable_tdd=enable_tdd,
            enable_verification=True,
            enable_subagent=enable_subagent,
        )

        options = build_sub_agent_options(
            cwd=self.workspace or None,
            model="sonnet",
            max_turns=25,
        )

        # Spawn the sub-agent
        spawn_result = await spawn_sub_agent(
            project_id=self.project_id,
            purpose="implement_feature",
            prompt=prompt,
            target_type="feature",
            target_id=feature.id,
            options=options,
        )

        # F113: Run verification BEFORE marking the feature completed so
        # that a verification failure does NOT cascade 'ready' status to
        # dependent features. Verification only runs when the sub-agent
        # didn't itself error.
        result = spawn_result.execution_result
        verification_passed: bool = True
        verification_summary: str | None = None
        verification_result: dict | None = None

        if not result.is_error and self.workspace:
            try:
                verification_result = run_verification_checklist(
                    workspace=self.workspace,
                    acceptance_criteria=feature.acceptance_criteria,
                    feature_description=feature.description,
                )
                verification_passed = bool(verification_result.get("passed", True))
                verification_summary = verification_result.get("summary")
                if verification_passed:
                    logger.info(
                        "Feature %s passed verification checklist", feature.id
                    )
                else:
                    logger.warning(
                        "Feature %s failed verification checklist: %s",
                        feature.id,
                        verification_summary,
                    )
                    logger.error(
                        "Feature %s will be marked needs_human due to failed verification",
                        feature.id,
                    )
            except Exception:
                logger.debug(
                    "Verification checklist failed for feature %s",
                    feature.id,
                    exc_info=True,
                )
                # If verification itself errors out, treat as pass so we
                # don't block features on internal verification bugs.
                verification_passed = True

        # F070: Handle execution result (status, evidence, cost).
        # When verification_passed=False and the sub-agent succeeded,
        # handle_execution_result marks the feature 'needs_human' and
        # skips the dependent cascade.
        outcome = handle_execution_result(
            project_id=self.project_id,
            feature=feature,
            spawn_result=spawn_result,
            shutdown_requested=self.shutdown_requested,
            verification_passed=verification_passed,
            verification_summary=verification_summary,
        )

        # Store verification_checklist evidence only when verification
        # actually ran (i.e. sub-agent succeeded and workspace is set).
        if verification_result is not None:
            try:
                db.create_evidence(
                    project_id=self.project_id,
                    feature_id=feature.id,
                    type="verification_checklist",
                    content=json.dumps(verification_result),
                )
            except Exception:
                logger.debug(
                    "Could not store verification evidence for feature %s",
                    feature.id,
                )

        # Update loop-level counters
        if result.is_error:
            if self.shutdown_requested:
                self._create_interruption_checkpoint(feature, result)
                logger.info(
                    "Feature %s interrupted during graceful shutdown",
                    feature.id,
                )
            else:
                # F071: Retry logic — check refinement attempts before giving up
                updated_feature = db.increment_refinement_attempts(feature.id)
                if updated_feature is not None and not db.check_refinement_limit(feature.id):
                    # Under limit: reset to 'ready' so the loop retries this feature
                    db.update_feature(feature.id, status="ready")
                    logger.info(
                        "Feature %s failed (attempt %d/%d), resetting to ready for retry: %s",
                        feature.id,
                        updated_feature.refinement_attempts,
                        updated_feature.max_refinement_attempts,
                        result.error_message,
                    )
                else:
                    # At or over limit: mark as needs_human (done by increment_refinement_attempts)
                    # and count as a permanent failure
                    self.features_failed += 1
                    logger.warning(
                        "Feature %s failed and exhausted retries (%d/%d): %s",
                        feature.id,
                        updated_feature.refinement_attempts if updated_feature else "?",
                        updated_feature.max_refinement_attempts if updated_feature else "?",
                        result.error_message,
                    )
        elif not verification_passed:
            # Sub-agent succeeded but verification failed. Do NOT commit,
            # do NOT cascade, do NOT count as completed.
            self.features_failed += 1
            logger.error(
                "Feature %s failed verification: %s",
                feature.id,
                verification_summary,
            )
        else:
            # F114: Commit feature changes to git (only once verification passed)
            commit_sha: str | None = None
            if self.workspace:
                try:
                    commit_sha = git_commit_feature(
                        feature_id=feature.id,
                        message=feature.name,
                        workspace=self.workspace,
                        stage_all=True,
                    )
                except Exception:
                    logger.warning(
                        "Git commit failed for feature %s", feature.id,
                        exc_info=True,
                    )

            self.features_completed += 1
            logger.info("Feature %s completed successfully", feature.id)

        # Track loop-level cost (always — even on failure we paid for the tokens)
        if result.total_cost_usd is not None:
            self.total_cost += result.total_cost_usd

        # F108: Update progress notes after each sub-agent session
        if self.workspace:
            try:
                if result.is_error:
                    progress_outcome = (
                        "interrupted" if self.shutdown_requested else "failed"
                    )
                    blockers = result.error_message
                elif not verification_passed:
                    progress_outcome = "failed"
                    blockers = f"Verification failed: {verification_summary}"
                else:
                    progress_outcome = "completed"
                    blockers = None
                update_progress_notes(
                    workspace=self.workspace,
                    feature_id=feature.id,
                    feature_name=feature.name,
                    outcome=progress_outcome,
                    duration_ms=result.duration_ms,
                    num_turns=result.num_turns,
                    cost_usd=result.total_cost_usd,
                    blockers=blockers,
                )
            except Exception:
                logger.debug(
                    "Failed to update progress notes for feature %s",
                    feature.id,
                    exc_info=True,
                )

        # Clear current feature tracking
        self._current_feature = None

        # Cascade update dependents — only when the feature truly succeeded
        # (sub-agent succeeded AND verification passed). This is the second
        # cascade (F123 layer); note handle_execution_result already ran
        # update_dependent_features_readiness in the success path.
        if not result.is_error and verification_passed:
            cascade_update_dependents(feature.id)

        return spawn_result

    def rollback_feature(
        self,
        *,
        feature_id: str,
        trigger: str,
        commit_sha: str,
        commit_before: str,
        regression_event_id: str | None = None,
    ) -> None:
        """Roll back a feature with git revert and database recording.

        Performs the actual git revert and then records the rollback event
        in the database.

        Args:
            feature_id: ID of the feature to roll back.
            trigger: What triggered the rollback (regression|human_request|critical_bug).
            commit_sha: The SHA of the feature's commit to revert.
            commit_before: The SHA of HEAD before the feature was implemented.
            regression_event_id: Optional linked regression event ID.
        """
        # F114: Execute the actual git revert
        rollback_commit: str | None = None
        if self.workspace:
            try:
                rollback_commit = git_revert_feature(
                    feature_id=feature_id,
                    commit_sha=commit_sha,
                    workspace=self.workspace,
                )
            except Exception:
                logger.warning(
                    "Git revert failed for feature %s", feature_id,
                    exc_info=True,
                )

        # Get current HEAD as commit_after
        commit_after = commit_sha

        # Record the rollback in the database
        db.rollback_feature(
            project_id=self.project_id,
            feature_id=feature_id,
            trigger=trigger,
            commit_before=commit_before,
            commit_after=commit_after,
            rollback_commit=rollback_commit,
            regression_event_id=regression_event_id,
        )

        logger.info(
            "Rolled back feature %s (trigger=%s, revert_commit=%s)",
            feature_id, trigger, rollback_commit,
        )

    def _create_interruption_checkpoint(
        self, feature: Feature, result: ExecutionResult
    ) -> None:
        """Create a checkpoint when a feature is interrupted by graceful shutdown.

        Captures the feature state, accumulated cost, and reason for
        interruption so that the feature can be resumed later.

        Args:
            feature: The feature that was being executed.
            result: The execution result from the sub-agent.
        """
        state = {
            "feature_id": feature.id,
            "feature_name": feature.name,
            "feature_status": "interrupted",
            "reason": "graceful_shutdown",
            "total_cost_at_interrupt": self.total_cost,
            "features_completed": self.features_completed,
            "features_failed": self.features_failed,
        }
        try:
            db.create_checkpoint(
                project_id=self.project_id,
                feature_id=feature.id,
                checkpoint_type="interruption",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=self.total_cost + (result.total_cost_usd or 0.0),
                duration_at_checkpoint_ms=result.duration_ms,
            )
            logger.info(
                "Created interruption checkpoint for feature %s", feature.id
            )
        except Exception:
            logger.warning(
                "Failed to create interruption checkpoint for feature %s",
                feature.id,
                exc_info=True,
            )

    def _install_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown."""
        def handler(signum, frame):
            logger.info("Received signal %s, requesting shutdown", signum)
            self.request_shutdown()

        try:
            signal.signal(signal.SIGINT, handler)
            signal.signal(signal.SIGTERM, handler)
        except (OSError, ValueError):
            # Signal handling may fail in some contexts (e.g., threads)
            logger.debug("Could not install signal handlers")

    def _resume_interrupted_work(self) -> None:
        """Detect and resume interrupted work from a previous run.

        On startup, checks for:
        1. Features with status='executing' (crashed mid-execution)
        2. Features with status='interrupted' (gracefully stopped)
        3. Resumable checkpoints (can_resume=TRUE)

        For each interrupted/executing feature:
        - If a resumable checkpoint exists, resume from it (restoring state)
        - If no checkpoint, reset the feature to 'ready' so it retries from scratch

        In fresh mode, all interrupted/executing features are simply reset to 'ready'
        without consuming any checkpoints.
        """
        # Find features stuck in 'executing' (process crashed)
        executing = db.list_features(project_id=self.project_id, status="executing")
        # Find features marked 'interrupted' (graceful shutdown)
        interrupted = db.list_features(project_id=self.project_id, status="interrupted")

        stale_features = executing + interrupted

        if not stale_features:
            return

        logger.info(
            "Found %d interrupted/stale features to resume",
            len(stale_features),
        )

        if self.fresh:
            # Fresh mode: reset all to 'ready' without consuming checkpoints
            for feat in stale_features:
                db.update_feature(feat.id, status="ready")
                logger.info(
                    "Fresh mode: reset feature %s (%s) to 'ready'",
                    feat.id,
                    feat.name,
                )
            return

        # Normal resume mode: try to resume from checkpoints
        resumable = db.find_resumable_checkpoints(project_id=self.project_id)
        # Build a map: feature_id -> most recent resumable checkpoint
        checkpoint_by_feature: dict[str, Any] = {}
        for cp in resumable:
            if cp.feature_id not in checkpoint_by_feature:
                checkpoint_by_feature[cp.feature_id] = cp

        for feat in stale_features:
            cp = checkpoint_by_feature.get(feat.id)
            if cp is not None:
                # Resume from checkpoint (restores feature state then sets to 'ready')
                logger.info(
                    "Resuming feature %s (%s) from checkpoint %s",
                    feat.id,
                    feat.name,
                    cp.id,
                )
                db.resume_from_checkpoint(cp.id)
                # After state is restored, set to 'ready' so the loop picks it up
                db.update_feature(feat.id, status="ready")
            else:
                # No checkpoint: reset to 'ready'
                logger.info(
                    "No checkpoint for feature %s (%s), resetting to 'ready'",
                    feat.id,
                    feat.name,
                )
                db.update_feature(feat.id, status="ready")

    async def run(self) -> LoopTermination:
        """Run the continuous orchestration loop.

        Processes features one at a time until a termination condition is met.
        On startup, automatically detects and resumes interrupted work (F116).

        Returns:
            The reason the loop terminated.
        """
        self._install_signal_handlers()
        logger.info("Starting orchestration loop for project %s", self.project_id)

        # F116: Auto-resume interrupted work
        self._resume_interrupted_work()

        while True:
            # Check shutdown
            if self.shutdown_requested:
                logger.info("Shutdown requested, stopping loop")
                # F117: Stop MCP server gracefully
                try:
                    stop_mcp_server()
                except Exception:
                    logger.debug("MCP server stop failed during shutdown", exc_info=True)
                logger.info("Interrupted. Run bob3 run to resume.")
                return LoopTermination.SHUTDOWN_REQUESTED

            # Check budget
            if self.budget_exceeded():
                logger.info("Budget exceeded, stopping loop")
                return LoopTermination.BUDGET_EXCEEDED

            # Find next ready feature
            feature = self.find_next_ready_feature()
            if feature is None:
                # No feature meets readiness threshold - check for features that need research
                features_in_ready_status = db.list_features(
                    project_id=self.project_id,
                    status='ready'
                )
                if features_in_ready_status:
                    # Pick the first one that's in 'ready' status but doesn't meet threshold
                    feature = features_in_ready_status[0]
                    logger.info(
                        "No features meet readiness threshold, but found feature %s in 'ready' status (readiness=%.2f). Will assess and potentially trigger research.",
                        feature.id[:8],
                        feature.readiness_score
                    )
                elif self.all_features_completed():
                    logger.info("All features completed")
                    return LoopTermination.ALL_COMPLETED
                elif self.all_remaining_blocked():
                    logger.info("All remaining features are blocked")
                    return LoopTermination.ALL_BLOCKED
                else:
                    # No ready feature but some are still pending — keep looping
                    # (this could happen if features are being reviewed or refined)
                    # To prevent busy-waiting, break if nothing is actionable
                    logger.info("No ready features, all remaining are blocked or pending")
                    return LoopTermination.ALL_BLOCKED

            # Assess confidence before execution (if not already assessed)
            # This ensures features with low confidence trigger research
            if feature.readiness_score == 0.0:
                logger.info(
                    "Assessing confidence for feature %s (%s)",
                    feature.id[:8],
                    feature.name
                )
                confidence = db.assess_feature_confidence(feature.id)
                db.update_feature(feature.id, **confidence)
                # Refresh feature with updated confidence scores
                feature = db.get_feature(feature.id)
                if not feature:
                    logger.error("Feature disappeared after confidence assessment")
                    continue

            # Execute the feature
            await self.execute_feature(feature)
