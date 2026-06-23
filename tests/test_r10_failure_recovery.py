"""Regression tests for R10-009 / R10-010 / R10-011.

R10-009: ``spawn_rca_agent`` is invoked from ``execute_feature`` after a
         failed attempt (gated by 24h cooldown + budget).

R10-010: ``BOB3_FAILURE_THRESHOLD_FOR_RESEARCH`` controls when
         ``needs_research`` Trigger 2 fires; default lowered from 3 → 2.

R10-011: Confidence scores decay by ``BOB3_CONFIDENCE_DECAY_PER_FAILURE``
         (default 0.15) after each failed feature attempt so the
         low-confidence research trigger can re-fire on retry.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3.db import (
    create_feature,
    create_project,
    get_feature,
    init_database,
    update_feature,
)
from bob3.models import Feature
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import (
    OrchestrationLoop,
    _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE,
    _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH,
    _decay_confidence_after_failure,
    _resolve_confidence_decay_per_failure,
    _resolve_failure_threshold_for_research,
    needs_research,
)


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def project(tmp_db):
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        return create_project(
            name="r10-test",
            workspace_path="/tmp/test-r10",
            max_cost_usd=100.0,
        )


@pytest.fixture
def feature(tmp_db, project):
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        f = create_feature(
            project_id=project.id,
            name="R10 Feature",
            description="A feature for failure-recovery testing",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.7,
            conf_impl_correctness=0.7,
            conf_test_adequacy=0.9,
            readiness_score=0.7,
        )
        return get_feature(f.id)


def _make_spawn_result(*, is_error: bool, error_message: str = "") -> SpawnResult:
    result = ExecutionResult(
        text="error output" if is_error else "success output",
        is_error=is_error,
        error_message=error_message,
        duration_ms=2000,
        num_turns=5,
        total_cost_usd=0.01,
    )
    agent_run = MagicMock()
    agent_run.id = str(uuid.uuid4())
    return SpawnResult(execution_result=result, agent_run=agent_run)


# ============================================================
# R10-010: failure threshold for research
# ============================================================


class TestR10010FailureThresholdDefault:
    """The default failure threshold is 2 (down from 3)."""

    def test_default_constant_is_two(self):
        assert _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH == 2

    def test_resolver_returns_two_by_default(self, monkeypatch):
        monkeypatch.delenv("BOB3_FAILURE_THRESHOLD_FOR_RESEARCH", raising=False)
        assert _resolve_failure_threshold_for_research() == 2

    def test_env_override_to_three(self, monkeypatch):
        monkeypatch.setenv("BOB3_FAILURE_THRESHOLD_FOR_RESEARCH", "3")
        assert _resolve_failure_threshold_for_research() == 3

    def test_env_override_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("BOB3_FAILURE_THRESHOLD_FOR_RESEARCH", "not-a-number")
        assert _resolve_failure_threshold_for_research() == 2

    def test_env_override_zero_falls_back(self, monkeypatch):
        monkeypatch.setenv("BOB3_FAILURE_THRESHOLD_FOR_RESEARCH", "0")
        assert _resolve_failure_threshold_for_research() == 2

    def test_env_override_negative_falls_back(self, monkeypatch):
        monkeypatch.setenv("BOB3_FAILURE_THRESHOLD_FOR_RESEARCH", "-1")
        assert _resolve_failure_threshold_for_research() == 2


class TestR10010NeedsResearchUsesEnvThreshold:
    """needs_research Trigger 2 fires at the configured threshold."""

    def test_two_failures_trigger_research_at_default(
        self, tmp_db, project, feature, monkeypatch
    ):
        """At default threshold=2, two recorded failures should trip Trigger 2."""
        monkeypatch.delenv("BOB3_FAILURE_THRESHOLD_FOR_RESEARCH", raising=False)
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            with patch(
                "bob3.orchestrator.run_loop.count_feature_failures",
                return_value=2,
            ):
                # Use confidence high enough to skip Trigger 3.
                f2 = get_feature(feature.id)
                f2 = f2.model_copy(
                    update={
                        "conf_spec_understanding": 0.9,
                        "conf_impl_correctness": 0.9,
                        "readiness_score": 0.9,
                    }
                )
                assert needs_research(f2, project.id) is True

    def test_one_failure_does_not_trigger_at_default(
        self, tmp_db, project, feature, monkeypatch
    ):
        monkeypatch.delenv("BOB3_FAILURE_THRESHOLD_FOR_RESEARCH", raising=False)
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            with patch(
                "bob3.orchestrator.run_loop.count_feature_failures",
                return_value=1,
            ):
                f2 = get_feature(feature.id)
                f2 = f2.model_copy(
                    update={
                        "conf_spec_understanding": 0.9,
                        "conf_impl_correctness": 0.9,
                        "readiness_score": 0.9,
                    }
                )
                assert needs_research(f2, project.id) is False

    def test_threshold_three_requires_three_failures(
        self, tmp_db, project, feature, monkeypatch
    ):
        monkeypatch.setenv("BOB3_FAILURE_THRESHOLD_FOR_RESEARCH", "3")
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f2 = get_feature(feature.id).model_copy(
                update={
                    "conf_spec_understanding": 0.9,
                    "conf_impl_correctness": 0.9,
                    "readiness_score": 0.9,
                }
            )
            with patch(
                "bob3.orchestrator.run_loop.count_feature_failures",
                return_value=2,
            ):
                assert needs_research(f2, project.id) is False
            with patch(
                "bob3.orchestrator.run_loop.count_feature_failures",
                return_value=3,
            ):
                assert needs_research(f2, project.id) is True


# ============================================================
# R10-011: confidence decay
# ============================================================


class TestR10011DecayResolver:
    def test_default_decay_is_point_one_five(self):
        assert _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE == 0.15

    def test_resolver_returns_default(self, monkeypatch):
        monkeypatch.delenv("BOB3_CONFIDENCE_DECAY_PER_FAILURE", raising=False)
        assert _resolve_confidence_decay_per_failure() == 0.15

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("BOB3_CONFIDENCE_DECAY_PER_FAILURE", "0.25")
        assert _resolve_confidence_decay_per_failure() == 0.25

    def test_invalid_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("BOB3_CONFIDENCE_DECAY_PER_FAILURE", "huh")
        assert _resolve_confidence_decay_per_failure() == 0.15

    def test_negative_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("BOB3_CONFIDENCE_DECAY_PER_FAILURE", "-0.5")
        assert _resolve_confidence_decay_per_failure() == 0.15

    def test_zero_disables_decay(self, monkeypatch, tmp_db, project, feature):
        monkeypatch.setenv("BOB3_CONFIDENCE_DECAY_PER_FAILURE", "0")
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = _decay_confidence_after_failure(feature.id)
            assert result is None
            after = get_feature(feature.id)
            # Confidence must be unchanged.
            assert after.conf_impl_correctness == pytest.approx(0.7)
            assert after.conf_spec_understanding == pytest.approx(0.7)
            assert after.readiness_score == pytest.approx(0.7)


@pytest.fixture
def _decay_default(monkeypatch):
    """Restore the production default decay (0.15) for a single test.

    The autouse fixture in conftest.py defaults
    ``BOB3_CONFIDENCE_DECAY_PER_FAILURE=0`` so pre-existing retry tests
    don't accidentally trip the low-confidence research trigger and
    spawn a real research sub-agent. Tests in
    ``TestR10011DecayApplication`` need the production default back.
    """
    monkeypatch.delenv("BOB3_CONFIDENCE_DECAY_PER_FAILURE", raising=False)


class TestR10011DecayApplication:
    def test_single_failure_drops_each_score_by_decay(
        self, tmp_db, project, feature, _decay_default
    ):
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            updated = _decay_confidence_after_failure(feature.id)
            assert updated is not None
            assert updated.conf_impl_correctness == pytest.approx(0.55)
            assert updated.conf_spec_understanding == pytest.approx(0.55)
            assert updated.readiness_score == pytest.approx(0.55)

    def test_two_failures_drop_each_score_by_two_decays(
        self, tmp_db, project, feature, _decay_default
    ):
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            _decay_confidence_after_failure(feature.id)
            updated = _decay_confidence_after_failure(feature.id)
            assert updated is not None
            assert updated.conf_impl_correctness == pytest.approx(0.40)
            assert updated.conf_spec_understanding == pytest.approx(0.40)
            assert updated.readiness_score == pytest.approx(0.40)

    def test_floor_at_zero(self, tmp_db, project, feature, monkeypatch):
        monkeypatch.setenv("BOB3_CONFIDENCE_DECAY_PER_FAILURE", "0.5")
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # 0.7 - 0.5 = 0.2; - 0.5 = -0.3 -> floor 0.0
            _decay_confidence_after_failure(feature.id)
            _decay_confidence_after_failure(feature.id)
            after = get_feature(feature.id)
            assert after.conf_impl_correctness == pytest.approx(0.0)
            assert after.conf_spec_understanding == pytest.approx(0.0)
            assert after.readiness_score == pytest.approx(0.0)

    def test_one_failure_at_default_does_not_cross_threshold(
        self, tmp_db, project, feature, _decay_default
    ):
        """0.7 - 0.15 = 0.55 — still above the 0.5 research threshold."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            _decay_confidence_after_failure(feature.id)
            after = get_feature(feature.id)
            assert after.conf_impl_correctness > 0.5
            assert after.conf_spec_understanding > 0.5
            assert after.readiness_score > 0.5

    def test_two_failures_cross_threshold(
        self, tmp_db, project, feature, _decay_default
    ):
        """0.7 → 0.55 → 0.40 — Trigger 3 should now fire on the next attempt."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            _decay_confidence_after_failure(feature.id)
            _decay_confidence_after_failure(feature.id)
            after = get_feature(feature.id)
            # All three confidence dimensions are now below the 0.5
            # research threshold, so Trigger 3 must fire on the next
            # call to needs_research (with research_iterations still 0).
            assert after.conf_impl_correctness < 0.5
            assert after.conf_spec_understanding < 0.5
            assert after.readiness_score < 0.5
            # And needs_research should agree.
            with patch(
                "bob3.orchestrator.run_loop.count_feature_failures",
                return_value=0,
            ):
                assert needs_research(after, project.id) is True


# ============================================================
# Decay applied via execute_feature failure path
# ============================================================


class TestR10011DecayInFailurePath:
    """A failure inside execute_feature should decay confidence."""

    @pytest.mark.asyncio
    async def test_one_failure_decays_via_execute_feature(
        self, tmp_db, project, feature, _decay_default
    ):
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            fail_result = _make_spawn_result(
                is_error=True, error_message="boom"
            )
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ):
                # Block RCA so this test only covers the decay path.
                with patch.object(
                    OrchestrationLoop, "_maybe_run_rca",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    await loop.execute_feature(feature)

            updated = get_feature(feature.id)
            assert updated is not None
            assert updated.refinement_attempts == 1
            assert updated.conf_impl_correctness == pytest.approx(0.55)
            assert updated.conf_spec_understanding == pytest.approx(0.55)
            assert updated.readiness_score == pytest.approx(0.55)


# ============================================================
# R10-009: spawn_rca_agent wired into the failure path
# ============================================================


def _stub_rca_spawn(action: str, *, blame: str = "implementation",
                    root_cause: str = "stub root cause") -> SpawnResult:
    import json as _json
    payload = "```json\n" + _json.dumps({
        "blame_target": blame,
        "recommended_action": action,
        "root_cause": root_cause,
    }) + "\n```"
    result = ExecutionResult(
        text=payload,
        is_error=False,
        error_message=None,
        duration_ms=1000,
        num_turns=2,
        total_cost_usd=0.01,
    )
    agent_run = MagicMock()
    agent_run.id = str(uuid.uuid4())
    return SpawnResult(execution_result=result, agent_run=agent_run)


@pytest.fixture
def _rca_enabled(monkeypatch):
    """Re-enable RCA wiring for the R10-009 test class.

    The autouse fixture in conftest.py disables RCA by default to
    keep pre-existing failure-path tests off the SDK; tests in this
    class exercise the wiring directly.
    """
    monkeypatch.setenv("BOB3_RCA_ENABLED", "1")


class TestR10009RcaWiring:
    """RCA must be invoked from the failure path past the first attempt."""

    @pytest.mark.asyncio
    async def test_first_failure_does_not_run_rca(
        self, tmp_db, project, feature, _rca_enabled
    ):
        """The first failure (refinement_attempts becomes 1) must not invoke spawn_rca_agent."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            fail_result = _make_spawn_result(
                is_error=True, error_message="boom"
            )
            spawn_spy = AsyncMock(return_value=_stub_rca_spawn("retry"))
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ), patch(
                "bob3.orchestrator.run_loop.spawn_rca_agent", spawn_spy,
            ):
                await loop.execute_feature(feature)

            # Feature was at attempts=0; failure increments to 1; gate
            # requires >=2, so spawn_rca_agent must NOT have been called.
            spawn_spy.assert_not_awaited()
            updated = get_feature(feature.id)
            assert updated.refinement_attempts == 1

    @pytest.mark.asyncio
    async def test_real_gate_skips_when_refinement_attempts_one(
        self, tmp_db, project, feature, _rca_enabled
    ):
        """``_maybe_run_rca`` returns None when the feature has no PRIOR failures."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            spawn_spy = AsyncMock()
            with patch(
                "bob3.orchestrator.run_loop.spawn_rca_agent", spawn_spy,
            ):
                fail_result = _make_spawn_result(
                    is_error=True, error_message="x"
                )
                # refinement_attempts==1 (post-increment of first failure)
                f2 = feature.model_copy(update={"refinement_attempts": 1})
                rca = await loop._maybe_run_rca(
                    feature=f2, result=fail_result.execution_result,
                )
                assert rca is None
                spawn_spy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_real_gate_runs_when_refinement_attempts_two(
        self, tmp_db, project, feature, _rca_enabled
    ):
        """``_maybe_run_rca`` invokes ``spawn_rca_agent`` once attempt >= 2."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            spawn_spy = AsyncMock(return_value=_stub_rca_spawn("retry"))
            with patch(
                "bob3.orchestrator.run_loop.spawn_rca_agent", spawn_spy,
            ):
                fail_result = _make_spawn_result(
                    is_error=True, error_message="x"
                )
                f2 = feature.model_copy(update={"refinement_attempts": 2})
                rca = await loop._maybe_run_rca(
                    feature=f2, result=fail_result.execution_result,
                )
            assert rca is not None
            assert rca["recommended_action"] == "retry"
            spawn_spy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rca_decompose_sets_exceeds_size_limits(
        self, tmp_db, project, feature, _rca_enabled
    ):
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            fail_result = _make_spawn_result(
                is_error=True, error_message="too big"
            )
            # Pre-bump refinement_attempts so the gate fires.
            update_feature(feature.id, refinement_attempts=2)
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ), patch(
                "bob3.orchestrator.run_loop.spawn_rca_agent",
                new_callable=AsyncMock,
                return_value=_stub_rca_spawn("decompose"),
            ):
                await loop.execute_feature(get_feature(feature.id))

            after = get_feature(feature.id)
            assert after.exceeds_size_limits is True
            assert after.status == "ready"

    @pytest.mark.asyncio
    async def test_rca_mark_needs_human_short_circuits_retry(
        self, tmp_db, project, feature, _rca_enabled
    ):
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            fail_result = _make_spawn_result(
                is_error=True, error_message="external API gone"
            )
            update_feature(feature.id, refinement_attempts=2)
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ), patch(
                "bob3.orchestrator.run_loop.spawn_rca_agent",
                new_callable=AsyncMock,
                return_value=_stub_rca_spawn("mark_needs_human"),
            ):
                await loop.execute_feature(get_feature(feature.id))

            after = get_feature(feature.id)
            assert after.status == "needs_human"
            assert loop.features_failed == 1

    @pytest.mark.asyncio
    async def test_rca_research_action_calls_force_research(
        self, tmp_db, project, feature, _rca_enabled
    ):
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            fail_result = _make_spawn_result(
                is_error=True, error_message="needs research"
            )
            update_feature(feature.id, refinement_attempts=2)
            force_spy = AsyncMock()
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ), patch(
                "bob3.orchestrator.run_loop.spawn_rca_agent",
                new_callable=AsyncMock,
                return_value=_stub_rca_spawn("research"),
            ), patch.object(
                OrchestrationLoop, "_force_research_for_feature", force_spy,
            ):
                await loop.execute_feature(get_feature(feature.id))

            force_spy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rca_evidence_artifact_recorded(
        self, tmp_db, project, feature, _rca_enabled
    ):
        from bob3.db import query_evidence
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            update_feature(feature.id, refinement_attempts=2)
            fail_result = _make_spawn_result(
                is_error=True, error_message="x"
            )
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ), patch(
                "bob3.orchestrator.run_loop.spawn_rca_agent",
                new_callable=AsyncMock,
                return_value=_stub_rca_spawn("retry"),
            ):
                await loop.execute_feature(get_feature(feature.id))

            ev = [
                e for e in query_evidence(feature_id=feature.id)
                if e.type == "rca_analysis"
            ]
            assert len(ev) == 1, f"expected one rca_analysis evidence, got {ev}"

    @pytest.mark.asyncio
    async def test_rca_cooldown_blocks_second_run(
        self, tmp_db, project, feature, _rca_enabled
    ):
        """A second failure within the cooldown window must NOT re-spawn RCA."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            update_feature(feature.id, refinement_attempts=2)
            fail_result = _make_spawn_result(
                is_error=True, error_message="x"
            )
            spawn_spy = AsyncMock(return_value=_stub_rca_spawn("retry"))
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=fail_result,
            ), patch(
                "bob3.orchestrator.run_loop.spawn_rca_agent", spawn_spy,
            ):
                # First failure: RCA runs.
                await loop.execute_feature(get_feature(feature.id))
                assert spawn_spy.await_count == 1

                # Bump refinement_attempts so the gate would otherwise allow it.
                update_feature(
                    feature.id, status="ready", refinement_attempts=2,
                )
                # Second failure inside the cooldown: RCA must NOT re-run.
                await loop.execute_feature(get_feature(feature.id))
                assert spawn_spy.await_count == 1
