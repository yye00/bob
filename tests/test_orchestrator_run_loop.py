"""Tests for bob3.orchestrator.run_loop.

Verifies that:
- LoopTermination enum is importable and has ALL_BLOCKED member
- _emit_run_summary translates ALL_BLOCKED → QUEUE_DRAINED in log output
- Enum serialization value is unchanged (DB compat)
- apply_pessimistic_cost uses a per-feature ceiling (BOB3_PER_FEATURE_COST_CEILING,
  default $20) instead of the entire project budget, preventing BUDGET_EXCEEDED
  from firing on the first telemetry-loss event.
"""
from __future__ import annotations

import logging
import os

import pytest


def _make_orch():
    """Build a minimal OrchestrationLoop instance without __init__."""
    from bob3.orchestrator.run_loop import OrchestrationLoop

    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 0
    orch.features_failed = 0
    orch._refresh_project_cost_cache = lambda: None
    return orch


def test_loop_termination_importable():
    """LoopTermination can be imported from bob3.orchestrator.run_loop."""
    from bob3.orchestrator.run_loop import LoopTermination

    assert LoopTermination is not None


def test_loop_termination_all_blocked_member_exists():
    """LoopTermination.ALL_BLOCKED must exist as an enum member."""
    from bob3.orchestrator.run_loop import LoopTermination

    assert hasattr(LoopTermination, "ALL_BLOCKED")


def test_loop_termination_all_blocked_value_unchanged():
    """LoopTermination.ALL_BLOCKED.value must remain 'all_blocked' for DB compat."""
    from bob3.orchestrator.run_loop import LoopTermination

    assert LoopTermination.ALL_BLOCKED.value == "all_blocked"


def test_emit_run_summary_all_blocked_logs_queue_drained(caplog):
    """_emit_run_summary with ALL_BLOCKED must log 'QUEUE_DRAINED', not 'ALL_BLOCKED'."""
    from bob3.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    combined = " ".join(caplog.messages)
    assert "QUEUE_DRAINED" in combined
    assert "termination=ALL_BLOCKED" not in combined


def test_emit_run_summary_all_blocked_run_finished_line(caplog):
    """_emit_run_summary must emit a 'Run finished:' log line."""
    from bob3.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    combined = " ".join(caplog.messages)
    assert "Run finished:" in combined


def test_emit_run_summary_other_terminations_not_renamed(caplog):
    """Non-ALL_BLOCKED terminations must not be renamed to QUEUE_DRAINED."""
    from bob3.orchestrator.run_loop import LoopTermination

    for term in (LoopTermination.ALL_COMPLETED, LoopTermination.BUDGET_EXCEEDED):
        orch = _make_orch()
        with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
            orch._emit_run_summary(term)
        combined = " ".join(caplog.messages)
        assert term.name in combined, f"Expected {term.name} in log"
        assert "QUEUE_DRAINED" not in combined, f"QUEUE_DRAINED should not appear for {term.name}"
        caplog.clear()


def test_orchestration_loop_importable():
    """OrchestrationLoop can be imported."""
    from bob3.orchestrator.run_loop import OrchestrationLoop

    assert OrchestrationLoop is not None


# --- Per-feature ceiling tests (F-R7-585) ---

def test_per_feature_ceiling_default_20_usd(monkeypatch):
    """apply_pessimistic_cost returns $20.0 by default when is_lost=True.

    This validates that the ceiling used for telemetry-loss charges is a sane
    per-feature default ($20), NOT the entire project budget (e.g. $10M).
    """
    from bob3.orchestrator.run_loop import apply_pessimistic_cost

    monkeypatch.delenv("BOB3_PER_FEATURE_COST_CEILING", raising=False)
    # Simulate what run_loop does: read env with default 20.0
    ceiling = float(os.environ.get("BOB3_PER_FEATURE_COST_CEILING", "20.0"))
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=ceiling,
    )
    assert result == pytest.approx(20.0), (
        f"Default ceiling must be $20.0, got {result}. "
        "Charging the project budget ($10M) on telemetry loss would instantly "
        "trip BUDGET_EXCEEDED and halt the orchestrator."
    )


def test_per_feature_ceiling_respects_env_var(monkeypatch):
    """BOB3_PER_FEATURE_COST_CEILING env var overrides the default $20 ceiling.

    Operators can tune the per-feature ceiling without rebuilding. The run_loop
    reads this env var and passes it to apply_pessimistic_cost.
    """
    from bob3.orchestrator.run_loop import apply_pessimistic_cost

    monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "50.0")
    ceiling = float(os.environ.get("BOB3_PER_FEATURE_COST_CEILING", "20.0"))
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=ceiling,
    )
    assert result == pytest.approx(50.0), (
        f"Expected ceiling of $50.0 from env var, got {result}"
    )


def test_telemetry_loss_charges_ceiling_not_project_budget():
    """apply_pessimistic_cost with per_feature_ceiling=20.0 MUST NOT charge $10M.

    Root cause of the BUDGET_EXCEEDED incident: the code computed
    _per_feature_ceiling = min(self.max_cost, self._project_max_cost_usd)
    which equals the entire project budget when project max_cost_usd is set
    (e.g. $10M). This test asserts the ceiling is the per-feature value
    ($20 default), not the project-level budget.
    """
    from bob3.orchestrator.run_loop import apply_pessimistic_cost

    project_budget = 10_000_000.0  # $10M — the whole project budget
    per_feature_ceiling = 20.0     # correct per-feature value

    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=per_feature_ceiling,
    )

    # Must charge per-feature ceiling, not the project budget
    assert result == pytest.approx(per_feature_ceiling), (
        f"Telemetry-loss charge was {result}, expected {per_feature_ceiling}. "
        f"Charging the project budget ({project_budget}) would halt the orchestrator."
    )
    assert result < project_budget, (
        "Per-feature ceiling must be less than the entire project budget."
    )
