"""Integration tests for F-R6-300: ``run_loop`` consumes the classifier.

These tests exercise the contract that the orchestrator must honour
*after* the F-R6-300 hotfix: when a sub-agent reports duration_ms=0
and num_turns=0 BUT ``.bob3/progress.jsonl`` shows work events, the
orchestrator must charge a ``refinement_attempt`` instead of granting
a free retry.

Pre-hotfix this scenario caused F-R5-202 to infinite-loop on the same
feature without ever incrementing ``refinement_attempts``.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3.db import (
    create_feature,
    create_project,
    get_feature,
    init_database,
    update_feature,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import OrchestrationLoop


# ---------------------------------------------------------------------------
# Fixtures (kept self-contained — no cross-file conftest dependency)
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def project(tmp_db):
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        return create_project(
            name="test-project",
            workspace_path="/tmp/test-project",
            max_cost_usd=100.0,
        )


@pytest.fixture
def feature(tmp_db, project):
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        f = create_feature(
            project_id=project.id,
            name="Mid-work-crash Feature",
            description=(
                "A feature whose sub-agent crashes during shutdown "
                "after producing work."
            ),
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        return get_feature(f.id)


def _seed_progress_jsonl(workspace: Path, feature_id: str) -> Path:
    """Write a realistic mid-work progress.jsonl into the workspace.

    The presence of these ``progress_updated`` events is the on-disk
    evidence the classifier uses to flip the verdict from
    ``spawn_failure`` to ``mid_work_crash``.
    """
    progress_dir = workspace / ".bob3"
    progress_dir.mkdir(parents=True, exist_ok=True)
    progress_path = progress_dir / "progress.jsonl"
    events = [
        {
            "timestamp": "2026-05-19T10:00:00+00:00",
            "event_type": "progress_updated",
            "project_id": "",
            "feature_id": feature_id,
            "attempt_number": 1,
            "payload": {
                "feature_name": "Mid-work-crash Feature",
                "outcome": "in_progress",
                "blockers": None,
            },
        },
        {
            "timestamp": "2026-05-19T10:01:30+00:00",
            "event_type": "progress_updated",
            "project_id": "",
            "feature_id": feature_id,
            "attempt_number": 1,
            "payload": {
                "feature_name": "Mid-work-crash Feature",
                "outcome": "in_progress",
                "blockers": None,
            },
        },
    ]
    with progress_path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")
    return progress_path


# ---------------------------------------------------------------------------
# Regression test: the bug F-R6-300 fixes
# ---------------------------------------------------------------------------


class TestMidWorkCrashChargesRefinementAttempt:
    """Pre-hotfix: free retry, infinite loop. Post-hotfix: charges a
    refinement attempt because ``progress.jsonl`` proves the sub-agent
    did real work before claude-code crashed during shutdown."""

    @pytest.mark.asyncio
    async def test_progress_jsonl_with_work_events_charges_refinement_attempt(
        self, tmp_db, project, feature, tmp_path: Path
    ) -> None:
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            workspace = tmp_path / "workspace"
            workspace.mkdir()
            # On-disk evidence of mid-work crash: progress.jsonl with
            # two real work events. The bug was that the old heuristic
            # ignored this file entirely.
            _seed_progress_jsonl(workspace, feature.id)

            loop = OrchestrationLoop(
                project_id=project.id, workspace=str(workspace)
            )

            # The SDK signature claude-code shows on shutdown crash:
            # duration_ms=0, num_turns=0, "Command failed with exit
            # code 1". Old heuristic: spawn_failure (free retry). New
            # classifier: mid_work_crash (charges attempt).
            mock_result = ExecutionResult(
                text="",
                is_error=True,
                error_message=(
                    "Fatal error in message reader: "
                    "Command failed with exit code 1"
                ),
                duration_ms=0,
                num_turns=0,
                total_cost_usd=None,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run
                ),
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                return_value={
                    "passed": False,
                    "summary": "no source",
                    "checks": [],
                },
            ):
                await loop.execute_feature(feature)

            updated = get_feature(feature.id)
            # F-R6-300 regression: mid_work_crash MUST charge a real
            # refinement attempt. If this assertion ever drops back to
            # 0, the bug has returned and the orchestrator will
            # infinite-loop on this feature.
            assert updated.refinement_attempts == 1, (
                "F-R6-300 regression: a sub-agent shutdown crash with "
                "on-disk progress.jsonl evidence MUST charge a "
                "refinement attempt (mid_work_crash), not be treated "
                "as a spawn_failure free retry."
            )
            # The free-retry counter must NOT have been touched — this
            # is the load-bearing assertion that distinguishes the new
            # behavior from the old.
            assert feature.id not in loop._spawn_failure_counts, (
                "F-R6-300 regression: a mid_work_crash must NOT bump "
                "the spawn-failure counter."
            )

    @pytest.mark.asyncio
    async def test_no_progress_jsonl_still_gets_free_retry(
        self, tmp_db, project, feature, tmp_path: Path
    ) -> None:
        """Negative control: the fix must NOT regress the legitimate
        spawn-failure free-retry path. When .bob3/progress.jsonl does
        NOT exist, the orchestrator still grants a free retry."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            workspace = tmp_path / "workspace"
            workspace.mkdir()
            # NB: no progress.jsonl written.

            loop = OrchestrationLoop(
                project_id=project.id, workspace=str(workspace)
            )

            mock_result = ExecutionResult(
                text="",
                is_error=True,
                error_message="Command failed with exit code 1",
                duration_ms=0,
                num_turns=0,
                total_cost_usd=None,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run
                ),
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                return_value={
                    "passed": False,
                    "summary": "no source",
                    "checks": [],
                },
            ):
                await loop.execute_feature(feature)

            updated = get_feature(feature.id)
            assert updated.refinement_attempts == 0, (
                "R10-015 must still hold: a true spawn failure "
                "(no progress.jsonl, no tool calls) is a free retry."
            )
            assert loop._spawn_failure_counts.get(feature.id) == 1, (
                "R10-015 must still hold: the spawn-failure counter "
                "must increment on a true spawn failure."
            )
