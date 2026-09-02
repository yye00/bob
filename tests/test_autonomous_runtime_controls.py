"""Safety controls for Bob's unattended native-Claude runtime profile."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob.orchestrator.claude_executor import ExecutionResult, SpawnResult


@pytest.mark.parametrize("model", ["claude-opus-4-8", "CLAUDE-OPUS-4-8"])
def test_exact_opus_4_8_model_id_is_supported(model):
    from bob.orchestrator.claude_executor import build_sub_agent_options

    options = build_sub_agent_options(model=model)

    assert options.model == "claude-opus-4-8"


@pytest.mark.parametrize("value", ["unlimited", "none", " UNLIMITED "])
def test_unlimited_turn_budget_omits_sdk_max_turns(monkeypatch, value):
    import bob.orchestrator.claude_executor as executor

    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", value)
    constructor = MagicMock(return_value=SimpleNamespace(max_turns=None))

    with patch.object(executor, "ClaudeCodeOptions", constructor):
        options = executor.build_sub_agent_options(model="claude-opus-4-8")

    assert options.max_turns is None
    assert "max_turns" not in constructor.call_args.kwargs


def test_default_turn_budget_remains_25(monkeypatch):
    from bob.orchestrator.claude_executor import build_sub_agent_options

    monkeypatch.delenv("BOB_SUB_AGENT_MAX_TURNS", raising=False)

    assert build_sub_agent_options().max_turns == 25


def test_required_model_pins_implicit_worker_model(monkeypatch):
    from bob.orchestrator.claude_executor import build_sub_agent_options

    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")

    assert build_sub_agent_options(model=None).model == "claude-opus-4-8"


@pytest.mark.parametrize("requested", ["sonnet", "claude-opus-4-6"])
def test_required_model_rejects_mismatch(monkeypatch, requested):
    from bob.orchestrator.claude_executor import build_sub_agent_options

    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")

    with pytest.raises(ValueError, match="does not match BOB_REQUIRED_MODEL"):
        build_sub_agent_options(model=requested)


def test_required_model_rejects_unknown_requested_model(monkeypatch):
    from bob.orchestrator.claude_executor import build_sub_agent_options

    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")

    with pytest.raises(ValueError, match="Requested model.*invalid"):
        build_sub_agent_options(model="claude-opus-99")


@pytest.mark.parametrize("required", ["", "claude-opus-99"])
def test_required_model_rejects_invalid_pin(monkeypatch, required):
    from bob.orchestrator.claude_executor import build_sub_agent_options

    monkeypatch.setenv("BOB_REQUIRED_MODEL", required)

    with pytest.raises(ValueError, match="BOB_REQUIRED_MODEL"):
        build_sub_agent_options(model="claude-opus-4-8")


def test_unknown_worker_model_keeps_legacy_fallback_without_pin(monkeypatch):
    from bob.orchestrator.claude_executor import (
        MODEL_ALIASES,
        build_sub_agent_options,
    )

    monkeypatch.delenv("BOB_REQUIRED_MODEL", raising=False)

    assert build_sub_agent_options(model="claude-opus-99").model == MODEL_ALIASES["sonnet"]


@pytest.mark.asyncio
async def test_required_model_rejects_direct_executor_options_before_query(monkeypatch):
    import bob.orchestrator.claude_executor as executor

    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")
    provider_query = MagicMock()

    with patch.object(executor, "stream_query", provider_query):
        with pytest.raises(ValueError, match="not match BOB_REQUIRED_MODEL"):
            await executor.ClaudeExecutor(
                default_options=SimpleNamespace(model="sonnet")
            ).execute("prompt")

    provider_query.assert_not_called()


@pytest.mark.asyncio
async def test_required_model_rejects_direct_spawn_options_before_side_effects(
    monkeypatch,
):
    import bob.orchestrator.claude_executor as executor

    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")

    with pytest.raises(ValueError, match="not match BOB_REQUIRED_MODEL"):
        await executor.spawn_sub_agent(
            project_id="project-1",
            purpose="test",
            prompt="prompt",
            options=SimpleNamespace(model="sonnet"),
        )


@pytest.mark.parametrize("value", ["unlimited", "none", " UNLIMITED "])
def test_unlimited_per_attempt_cost_cap_never_terminates(monkeypatch, value):
    from bob.orchestrator.per_attempt_cost_cap import (
        get_per_attempt_cap,
        should_terminate_subagent,
    )

    monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", value)

    assert get_per_attempt_cap() is None
    assert should_terminate_subagent(1_000_000.0) is False


def test_unlimited_per_attempt_direct_termination_is_noop(monkeypatch):
    import bob.orchestrator.per_attempt_cost_cap as cap

    monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "none")
    send_signal = MagicMock()
    monkeypatch.setattr(cap, "_send_signal", send_signal)

    cap.terminate_subagent_on_cost_cap(
        feature_id="feature-1", pid=12345, reported_cost=1_000_000.0
    )

    send_signal.assert_not_called()


@pytest.mark.parametrize("value", ["forever", "NaN", "inf"])
def test_malformed_per_attempt_cost_cap_fails_closed(monkeypatch, value):
    from bob.orchestrator.per_attempt_cost_cap import (
        get_per_attempt_cap,
        should_terminate_subagent,
    )

    monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", value)

    assert get_per_attempt_cap() == 10.0
    assert should_terminate_subagent(10.01) is True


@pytest.mark.parametrize("value", ["unlimited", "none", " UNLIMITED "])
def test_unlimited_evaluator_turn_budget_omits_sdk_field(monkeypatch, value):
    import bob.orchestrator.claude_executor as executor

    monkeypatch.setenv("BOB_EVALUATOR_MAX_TURNS", value)
    constructor = MagicMock(return_value=SimpleNamespace(max_turns=None))

    with patch.object(executor, "ClaudeCodeOptions", constructor):
        executor.build_sub_agent_options(
            max_turns=executor.resolve_evaluator_max_turns()
        )

    assert "max_turns" not in constructor.call_args.kwargs


def test_finite_evaluator_turn_budget_is_honored(monkeypatch):
    from bob.orchestrator.claude_executor import resolve_evaluator_max_turns

    monkeypatch.setenv("BOB_EVALUATOR_MAX_TURNS", "37")

    assert resolve_evaluator_max_turns() == 37


@pytest.mark.parametrize("value", ["forever", "0", "-1", "1.5"])
def test_malformed_evaluator_turn_budget_fails_closed(monkeypatch, value):
    from bob.orchestrator.claude_executor import resolve_evaluator_max_turns

    monkeypatch.setenv("BOB_EVALUATOR_MAX_TURNS", value)

    with pytest.raises(ValueError, match="BOB_EVALUATOR_MAX_TURNS"):
        resolve_evaluator_max_turns()


@pytest.mark.asyncio
async def test_evaluator_spawn_wires_unlimited_turns_and_required_model(
    monkeypatch, tmp_path
):
    import bob.orchestrator.claude_executor as executor

    monkeypatch.setenv("BOB_EVALUATOR_MAX_TURNS", "unlimited")
    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")
    options = SimpleNamespace()
    build_options = MagicMock(return_value=options)
    provider_spawn = AsyncMock(return_value=SimpleNamespace())

    with (
        patch.object(executor, "build_sub_agent_options", build_options),
        patch.object(executor, "spawn_sub_agent", provider_spawn),
    ):
        await executor.spawn_evaluator_agent(
            project_id="project-1",
            feature_spec="feature",
            acceptance_criteria="criterion",
            diff="diff",
            workspace=tmp_path,
        )

    assert build_options.call_args.kwargs["max_turns"] is None
    assert build_options.call_args.kwargs["model"] == "claude-opus-4-8"
    provider_spawn.assert_awaited_once()


@pytest.mark.asyncio
async def test_malformed_evaluator_turn_budget_prevents_provider_spawn(
    monkeypatch, tmp_path
):
    import bob.orchestrator.claude_executor as executor

    monkeypatch.setenv("BOB_EVALUATOR_MAX_TURNS", "unbounded-typo")
    provider_spawn = AsyncMock()

    with patch.object(executor, "spawn_sub_agent", provider_spawn):
        with pytest.raises(ValueError, match="BOB_EVALUATOR_MAX_TURNS"):
            await executor.spawn_evaluator_agent(
                project_id="project-1",
                feature_spec="feature",
                acceptance_criteria="criterion",
                diff="diff",
                workspace=tmp_path,
            )

    provider_spawn.assert_not_awaited()


@pytest.mark.asyncio
async def test_malformed_evaluator_turn_budget_blocks_commit_even_if_optional(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BOB_EVALUATOR_ENABLED", "1")
    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "0")
    monkeypatch.setenv("BOB_EVALUATOR_MAX_TURNS", "unbounded-typo")

    with patch(
        "bob.orchestrator.run_loop.spawn_evaluator_agent", AsyncMock()
    ) as provider_spawn:
        verdict = await _loop(str(tmp_path))._run_evaluator(feature=_feature())

    assert verdict is not None
    assert verdict["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "BOB_EVALUATOR_MAX_TURNS" in verdict["findings"][0]
    provider_spawn.assert_not_awaited()


@pytest.mark.parametrize("value", ["forever", "0", "-1"])
def test_invalid_turn_budget_is_rejected(monkeypatch, value):
    from bob.orchestrator.claude_executor import resolve_sub_agent_max_turns

    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", value)

    with pytest.raises(ValueError, match="BOB_SUB_AGENT_MAX_TURNS"):
        resolve_sub_agent_max_turns()


@pytest.mark.asyncio
async def test_disabled_research_mode_prevents_provider_spawn(monkeypatch):
    import bob.orchestrator.claude_executor as executor

    monkeypatch.setenv("BOB_RESEARCH_MODE", "disabled")
    provider_spawn = AsyncMock()

    with patch.object(executor, "spawn_sub_agent", provider_spawn):
        with pytest.raises(executor.ResearchDisabledError):
            await executor.spawn_research_agent(
                project_id="project-1",
                query="find current documentation",
            )

    provider_spawn.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_research_mode_fails_before_provider_spawn(monkeypatch):
    import bob.orchestrator.claude_executor as executor

    monkeypatch.setenv("BOB_RESEARCH_MODE", "disable-typo")
    provider_spawn = AsyncMock()

    with patch.object(executor, "spawn_sub_agent", provider_spawn):
        with pytest.raises(ValueError, match="BOB_RESEARCH_MODE"):
            await executor.spawn_research_agent(
                project_id="project-1",
                query="find current documentation",
            )

    provider_spawn.assert_not_awaited()


def _loop(workspace: str = "/tmp/evaluator-workspace"):
    from bob.orchestrator.run_loop import OrchestrationLoop

    loop = object.__new__(OrchestrationLoop)
    loop.project_id = "project-1"
    loop.workspace = workspace
    loop._increment_cost = MagicMock()
    return loop


def _feature():
    return SimpleNamespace(
        id="feature-1",
        name="Feature one",
        description="Implement feature one",
        acceptance_criteria="pytest: tests/test_feature_one.py",
    )


def _spawn_result(*, text: str = "", error: str | None = None) -> SpawnResult:
    return SpawnResult(
        execution_result=ExecutionResult(
            text=text,
            is_error=error is not None,
            error_message=error,
            session_id="evaluator-provider-session",
            total_cost_usd=0.0,
            num_turns=1,
        ),
        agent_run=SimpleNamespace(id="evaluator-run-1"),
    )


@pytest.mark.asyncio
async def test_required_evaluator_disabled_returns_blocking_verdict(monkeypatch):
    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "1")
    monkeypatch.setenv("BOB_EVALUATOR_ENABLED", "0")

    verdict = await _loop()._run_evaluator(feature=_feature())

    assert verdict is not None
    assert verdict["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "disabled" in verdict["findings"][0].lower()


@pytest.mark.asyncio
async def test_required_evaluator_without_workspace_returns_blocking_verdict(
    monkeypatch,
):
    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "1")
    monkeypatch.setenv("BOB_EVALUATOR_ENABLED", "1")

    verdict = await _loop("")._run_evaluator(feature=_feature())

    assert verdict is not None
    assert verdict["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "workspace" in verdict["findings"][0].lower()


@pytest.mark.asyncio
async def test_required_evaluator_timeout_returns_blocking_verdict(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "1")
    monkeypatch.setenv("BOB_EVALUATOR_ENABLED", "1")
    monkeypatch.setenv("BOB_EVALUATOR_TIMEOUT_SECONDS", "0.01")

    with patch(
        "bob.orchestrator.run_loop.spawn_evaluator_agent",
        AsyncMock(side_effect=asyncio.TimeoutError),
    ):
        verdict = await _loop(str(tmp_path))._run_evaluator(feature=_feature())

    assert verdict is not None
    assert verdict["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "timed out" in verdict["findings"][0].lower()


@pytest.mark.asyncio
async def test_required_evaluator_crash_returns_blocking_verdict(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "1")
    monkeypatch.setenv("BOB_EVALUATOR_ENABLED", "1")

    with patch(
        "bob.orchestrator.run_loop.spawn_evaluator_agent",
        AsyncMock(side_effect=RuntimeError("provider unavailable")),
    ):
        verdict = await _loop(str(tmp_path))._run_evaluator(feature=_feature())

    assert verdict is not None
    assert verdict["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "crashed" in verdict["findings"][0].lower()


@pytest.mark.asyncio
async def test_required_evaluator_unavailable_result_blocks(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "1")
    monkeypatch.setenv("BOB_EVALUATOR_ENABLED", "1")

    with patch(
        "bob.orchestrator.run_loop.spawn_evaluator_agent",
        AsyncMock(return_value=None),
    ):
        verdict = await _loop(str(tmp_path))._run_evaluator(feature=_feature())

    assert verdict is not None
    assert verdict["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "no execution result" in verdict["findings"][0].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "finding"),
    [
        (_spawn_result(text="not structured evaluator output"), "could not be parsed"),
        (_spawn_result(error="transport connection failed"), "provider/transport"),
    ],
)
async def test_required_evaluator_bad_result_blocks(monkeypatch, tmp_path, result, finding):
    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "1")
    monkeypatch.setenv("BOB_EVALUATOR_ENABLED", "1")

    with patch(
        "bob.orchestrator.run_loop.spawn_evaluator_agent",
        AsyncMock(return_value=result),
    ):
        verdict = await _loop(str(tmp_path))._run_evaluator(feature=_feature())

    assert verdict is not None
    assert verdict["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert finding in verdict["findings"][0]


def test_required_evaluator_none_cannot_authorize_commit(monkeypatch):
    from bob.orchestrator.run_loop import _evaluator_allows_commit

    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "1")

    assert _evaluator_allows_commit(None) is False


def test_optional_evaluator_preserves_legacy_none_as_pass(monkeypatch):
    from bob.orchestrator.run_loop import _evaluator_allows_commit

    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "0")

    assert _evaluator_allows_commit(None) is True


@pytest.mark.asyncio
async def test_required_evaluator_rejects_generic_note_without_per_ac_bundle_receipt(
    monkeypatch, tmp_path
):
    import hashlib
    import json
    from bob.candidate_change_manifest import (
        build_candidate_change_bundle,
        snapshot_candidate_tree,
    )

    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "1")
    monkeypatch.setenv("BOB_EVALUATOR_ENABLED", "1")
    source = tmp_path / "app.py"
    source.write_text("VALUE = 1\n")
    baseline = snapshot_candidate_tree(cwd=tmp_path)
    source.write_text("VALUE = 2\n")
    final = snapshot_candidate_tree(cwd=tmp_path)
    bundle = build_candidate_change_bundle(
        feature_id="feature-1", cwd=tmp_path, baseline=baseline, final=final
    )
    diff_sha = hashlib.sha256(bundle.canonical_json.encode("utf-8")).hexdigest()
    response = {
        "verdict": "PASS",
        "findings": [],
        "confidence": 0.9,
        "evidence": {
            "feature_id": "feature-1",
            "change_bundle_sha256": bundle.sha256,
            "diff_sha256": diff_sha,
            "note": "looks good to me",
        },
    }
    spawned = _spawn_result(text=f"```json\n{json.dumps(response)}\n```")

    with patch(
        "bob.orchestrator.run_loop.spawn_evaluator_agent",
        AsyncMock(return_value=spawned),
    ):
        verdict = await _loop(str(tmp_path))._run_evaluator(
            feature=_feature(), change_bundle=bundle
        )

    assert verdict["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "criterion_0" in verdict["findings"][0]


@pytest.mark.asyncio
async def test_required_evaluator_accepts_bound_per_ac_path_line_receipt(
    monkeypatch, tmp_path
):
    import hashlib
    import json
    from bob.candidate_change_manifest import (
        build_candidate_change_bundle,
        snapshot_candidate_tree,
    )

    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "1")
    monkeypatch.setenv("BOB_EVALUATOR_ENABLED", "1")
    source = tmp_path / "app.py"
    source.write_text("VALUE = 1\n")
    baseline = snapshot_candidate_tree(cwd=tmp_path)
    source.write_text("VALUE = 2\n")
    final = snapshot_candidate_tree(cwd=tmp_path)
    bundle = build_candidate_change_bundle(
        feature_id="feature-1", cwd=tmp_path, baseline=baseline, final=final
    )
    diff_sha = hashlib.sha256(bundle.canonical_json.encode("utf-8")).hexdigest()
    response = {
        "verdict": "PASS",
        "findings": [],
        "confidence": 0.9,
        "evidence": {
            "feature_id": "feature-1",
            "change_bundle_sha256": bundle.sha256,
            "diff_sha256": diff_sha,
            "criterion_0": "app.py:1 implements the projected behavior",
        },
    }
    spawned = _spawn_result(text=f"```json\n{json.dumps(response)}\n```")

    with patch(
        "bob.orchestrator.run_loop.spawn_evaluator_agent",
        AsyncMock(return_value=spawned),
    ), patch("bob.orchestrator.run_loop.db.create_evidence"):
        verdict = await _loop(str(tmp_path))._run_evaluator(
            feature=_feature(), change_bundle=bundle
        )

    assert verdict["verdict"] == "PASS"
    assert verdict["_provider_session_id"] == "evaluator-provider-session"
