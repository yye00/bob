"""Focused tests for hermetic Claude roles and uncapped RCA execution."""

from __future__ import annotations

import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob.orchestrator import run_loop
from bob.orchestrator.claude_executor import ExecutionResult, SpawnResult

HERMETIC_ARGS = {
    "setting-sources": "",
    "strict-mcp-config": None,
    "no-session-persistence": None,
    "bare": None,
}


@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_hermetic_builder_adds_exact_cli_flags_and_preserves_caller_args(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    from bob.orchestrator.claude_executor import build_sub_agent_options

    monkeypatch.setenv("BOB_CLAUDE_HERMETIC", value)
    caller_args = {
        "tools": "Read",
        "custom-flag": "value",
        # The security policy must win over a conflicting caller value.
        "setting-sources": "user,project,local",
    }

    options = build_sub_agent_options(extra_args=caller_args)

    assert options.extra_args == {
        **caller_args,
        **HERMETIC_ARGS,
    }
    assert "disable-slash-commands" not in options.extra_args
    assert caller_args["setting-sources"] == "user,project,local"


@pytest.mark.parametrize("value", ["0", "false", "NO", " off "])
def test_explicit_nonhermetic_mode_retains_legacy_builder_behavior(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    from bob.orchestrator.claude_executor import build_sub_agent_options

    monkeypatch.setenv("BOB_CLAUDE_HERMETIC", value)

    options = build_sub_agent_options(extra_args={"tools": "Read"})

    assert options.extra_args == {"tools": "Read"}


@pytest.mark.parametrize("value", ["", "maybe", "enabled", "2"])
def test_invalid_hermetic_bool_fails_before_workspace_or_sdk_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path, value: str
) -> None:
    import bob.orchestrator.claude_executor as executor

    monkeypatch.setenv("BOB_CLAUDE_HERMETIC", value)
    install = MagicMock()
    verify = MagicMock()
    constructor = MagicMock()

    with (
        patch("bob.skills_installer.install_skills_to_workspace", install),
        patch("bob.skills_installer.verify_skills_integrity", verify),
        patch.object(executor, "ClaudeCodeOptions", constructor),
        pytest.raises(ValueError, match="BOB_CLAUDE_HERMETIC"),
    ):
        executor.build_sub_agent_options(cwd=tmp_path)

    install.assert_not_called()
    verify.assert_not_called()
    constructor.assert_not_called()


def test_stderr_capture_preserves_hermetic_and_later_planner_flags(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    from bob.orchestrator.claude_executor import (
        _attach_stderr_capture,
        build_sub_agent_options,
    )

    monkeypatch.setenv("BOB_CLAUDE_HERMETIC", "1")
    options = build_sub_agent_options(
        extra_args={"restricted": None, "tools": "Read"}
    )

    with tempfile.NamedTemporaryFile(mode="w+") as stderr_buffer:
        effective = _attach_stderr_capture(options, stderr_buffer)

    assert {key: effective.extra_args[key] for key in HERMETIC_ARGS} == HERMETIC_ARGS
    assert effective.extra_args["restricted"] is None
    assert effective.extra_args["tools"] == "Read"
    assert effective.extra_args["debug-to-stderr"] is None


@pytest.mark.asyncio
async def test_all_runtime_role_builders_receive_hermetic_cli_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Exercise every generic runtime role that constructs options centrally."""

    import bob.orchestrator.claude_executor as executor

    class StopAfterOptions(RuntimeError):
        pass

    captured = []

    async def capture_spawn(**kwargs):
        captured.append(kwargs["options"])
        raise StopAfterOptions

    monkeypatch.setenv("BOB_CLAUDE_HERMETIC", "1")
    monkeypatch.setenv("BOB_RESEARCH_MODE", "enabled")
    monkeypatch.delenv("BOB_RCA_MAX_TURNS", raising=False)
    monkeypatch.setattr(executor, "spawn_sub_agent", capture_spawn)
    monkeypatch.setattr(run_loop, "spawn_sub_agent", capture_spawn)
    monkeypatch.setattr(
        "bob.orchestrator.mcp_config.build_perplexity_mcp_dict", dict
    )
    monkeypatch.setattr(
        "bob.orchestrator.mcp_config.build_puppeteer_mcp_dict", dict
    )
    monkeypatch.setattr(
        "bob.skills_installer.install_skills_to_workspace", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "bob.skills_installer.verify_skills_integrity", lambda *a, **k: None
    )

    role_calls = [
        executor.spawn_research_agent(project_id="project", query="research"),
        executor.spawn_puppeteer_agent(
            project_id="project", url="https://example.invalid"
        ),
        executor.spawn_rca_agent(
            project_id="project",
            failure_evidence="failure",
            error_type="test_failure",
            error_message="assertion failed",
        ),
        executor.spawn_evaluator_agent(
            project_id="project",
            feature_spec="feature",
            acceptance_criteria="criterion",
            diff="diff",
            workspace=tmp_path,
        ),
        run_loop.handle_decomposition(
            project_id="project",
            feature=SimpleNamespace(
                id="feature",
                name="Feature",
                description="Description",
                acceptance_criteria="criterion",
                size_limit_justification="oversized",
            ),
            workspace=str(tmp_path),
        ),
    ]

    for role_call in role_calls:
        with pytest.raises(StopAfterOptions):
            await role_call

    assert len(captured) == len(role_calls)
    for options in captured:
        assert {key: options.extra_args[key] for key in HERMETIC_ARGS} == HERMETIC_ARGS
        assert "disable-slash-commands" not in options.extra_args


@pytest.mark.parametrize("value", ["unlimited", "none", " UNLIMITED "])
def test_unlimited_rca_turns_and_timeout_resolve_to_no_cap(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    from bob.orchestrator.claude_executor import resolve_rca_max_turns
    from bob.orchestrator.run_loop import _resolve_rca_timeout_seconds

    monkeypatch.setenv("BOB_RCA_MAX_TURNS", value)
    monkeypatch.setenv("BOB_RCA_TIMEOUT_SECONDS", value)

    assert resolve_rca_max_turns() is None
    assert _resolve_rca_timeout_seconds() is None


def test_unset_rca_controls_retain_legacy_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bob.orchestrator.claude_executor import resolve_rca_max_turns
    from bob.orchestrator.run_loop import _resolve_rca_timeout_seconds

    monkeypatch.delenv("BOB_RCA_MAX_TURNS", raising=False)
    monkeypatch.delenv("BOB_RCA_TIMEOUT_SECONDS", raising=False)

    assert resolve_rca_max_turns() == 10
    assert _resolve_rca_timeout_seconds() == 600.0


@pytest.mark.parametrize("value", ["forever", "0", "-1", "1.5"])
def test_invalid_rca_turn_control_fails_closed(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    from bob.orchestrator.claude_executor import resolve_rca_max_turns

    monkeypatch.setenv("BOB_RCA_MAX_TURNS", value)

    with pytest.raises(ValueError, match="BOB_RCA_MAX_TURNS"):
        resolve_rca_max_turns()


@pytest.mark.parametrize("value", ["forever", "0", "-1", "nan", "inf"])
def test_invalid_rca_timeout_control_fails_closed(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    from bob.orchestrator.run_loop import _resolve_rca_timeout_seconds

    monkeypatch.setenv("BOB_RCA_TIMEOUT_SECONDS", value)

    with pytest.raises(ValueError, match="BOB_RCA_TIMEOUT_SECONDS"):
        _resolve_rca_timeout_seconds()


def _uncapped_rca_loop_fixture():
    loop = object.__new__(run_loop.OrchestrationLoop)
    loop.project_id = "project"
    loop._rca_cooldown_active = lambda feature_id: False
    loop.budget_exceeded = lambda: False
    loop._increment_cost = MagicMock()
    feature = SimpleNamespace(id="feature-1", refinement_attempts=2)
    failure = ExecutionResult(
        text="implementation failed",
        is_error=True,
        error_message="assertion failed",
        total_cost_usd=0.0,
        num_turns=1,
    )
    rca_result = SpawnResult(
        execution_result=ExecutionResult(
            text=(
                '```json\n{"blame_target":"implementation",'
                '"recommended_action":"retry","root_cause":"bug"}\n```'
            ),
            is_error=False,
            total_cost_usd=0.0,
            num_turns=1,
        ),
        agent_run=SimpleNamespace(id="rca-run"),
    )
    return run_loop, loop, feature, failure, rca_result


@pytest.mark.asyncio
async def test_actual_rca_path_omits_both_unlimited_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_loop, loop, feature, failure, rca_result = _uncapped_rca_loop_fixture()
    monkeypatch.setenv("BOB_RCA_ENABLED", "1")
    monkeypatch.setenv("BOB_RCA_MAX_TURNS", "unlimited")
    monkeypatch.setenv("BOB_RCA_TIMEOUT_SECONDS", "none")
    spawn = AsyncMock(return_value=rca_result)
    wait_for = MagicMock(side_effect=AssertionError("unexpected timeout wrapper"))
    monkeypatch.setattr(run_loop, "spawn_rca_agent", spawn)
    monkeypatch.setattr(run_loop.asyncio, "wait_for", wait_for)
    monkeypatch.setattr(run_loop.db, "create_evidence", MagicMock())

    result = await loop._maybe_run_rca(feature=feature, result=failure)

    assert result is not None
    assert result["recommended_action"] == "retry"
    assert spawn.await_args.kwargs["max_turns"] is None
    wait_for.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_rca_policy_prevents_actual_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_loop, loop, feature, failure, _ = _uncapped_rca_loop_fixture()
    monkeypatch.setenv("BOB_RCA_ENABLED", "1")
    monkeypatch.setenv("BOB_RCA_MAX_TURNS", "typo")
    spawn = AsyncMock()
    monkeypatch.setattr(run_loop, "spawn_rca_agent", spawn)

    with pytest.raises(ValueError, match="BOB_RCA_MAX_TURNS"):
        await loop._maybe_run_rca(feature=feature, result=failure)

    spawn.assert_not_awaited()
