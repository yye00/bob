"""Public stub-provider tests; no paid endpoint or acceptance claims."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import replace
from types import SimpleNamespace

import pytest
from claude_code_sdk import ResultMessage, AssistantMessage, TextBlock

from bob import finite_budget as fb
from bob.orchestrator import claude_executor as ce


@pytest.fixture
def finite(tmp_path, monkeypatch):
    directory = tmp_path / "budget-controller"
    directory.mkdir(mode=0o700)
    path = directory / "profile.json"
    payload = {
        "schema_version": fb.SCHEMA,
        "model_id": "claude-haiku-4-5-20251001",
        "max_cost_usd": 1.0,
        "max_turns": 10,
        "max_attempts": 3,
        "max_wall_seconds": 60,
    }

    def configure(**changes):
        value = {**payload, **changes}
        if path.exists():
            path.chmod(0o600)
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        path.chmod(0o400)
        monkeypatch.setenv(fb.PROFILE_ENV, str(path))
        monkeypatch.setenv(fb.DIGEST_ENV, hashlib.sha256(raw).hexdigest())
        return path

    monkeypatch.delenv("BOB_REQUIRED_MODEL", raising=False)
    configure()
    return configure


def terminal(cost=0.2, turns=2, error=False):
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=error,
        num_turns=turns,
        session_id="synthetic-session",
        total_cost_usd=cost,
    )


@pytest.fixture
def transport(monkeypatch):
    process = SimpleNamespace(returncode=None, kills=0)

    def kill():
        process.kills += 1
        process.returncode = -9

    process.kill = kill
    value = SimpleNamespace(_process=process)
    monkeypatch.setattr(ce, "_sdk_transport", lambda prompt, options: value)
    return value


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_cost_usd", None),
        ("max_cost_usd", 0),
        ("max_cost_usd", float("nan")),
        ("max_cost_usd", float("inf")),
        ("max_turns", True),
        ("max_turns", 1.2),
        ("max_attempts", 0),
        ("max_wall_seconds", -1),
        ("model_id", "haiku"),
        ("model_id", "not-a-model"),
        ("model_id", " claude-haiku-4-5-20251001"),
    ],
)
def test_invalid_profiles_reject_without_ledger(finite, field, value):
    path = finite(**{field: value})
    with pytest.raises(ValueError):
        ce.build_sub_agent_options()
    assert not (path.parent / "bob-finite-budget.jsonl").exists()


@pytest.mark.parametrize(
    "mutation", ["digest", "partial", "mode", "parent", "symlink", "hardlink"]
)
def test_profile_custody(finite, monkeypatch, mutation):
    path = finite()
    if mutation == "digest":
        monkeypatch.setenv(fb.DIGEST_ENV, "0" * 64)
    elif mutation == "partial":
        monkeypatch.delenv(fb.DIGEST_ENV)
    elif mutation == "mode":
        path.chmod(0o600)
    elif mutation == "parent":
        path.parent.chmod(0o755)
    elif mutation == "symlink":
        renamed = path.with_suffix(".saved")
        path.rename(renamed)
        path.symlink_to(renamed)
    else:
        os.link(path, path.with_suffix(".link"))
    with pytest.raises(ValueError):
        fb.load_finite_profile()


def test_model_pin_and_actual_sdk_command_survive_clones(finite, tmp_path, monkeypatch):
    from claude_code_sdk._internal.transport.subprocess_cli import (
        SubprocessCLITransport,
    )

    options = ce.build_sub_agent_options(
        model="claude-haiku-4-5-20251001", agent_role="implementer"
    )
    with (tmp_path / "stderr").open("w+") as buffer:
        options = ce._attach_stderr_capture(
            ce.with_agent_role(options, "independent_test_writer"), buffer
        )
        command = SubprocessCLITransport(
            prompt="public fixture", options=options, cli_path="/synthetic/claude"
        )._build_command()
    for flag, value in [
        ("--model", "claude-haiku-4-5-20251001"),
        ("--max-turns", "10"),
        ("--max-budget-usd", "1.0"),
    ]:
        assert command.count(flag) == 1
        assert command[command.index(flag) + 1] == value
    assert "--bare" in command and "--no-session-persistence" in command
    assert {"Task", "Agent"} <= set(options.disallowed_tools)
    monkeypatch.setenv("BOB_REQUIRED_MODEL", "opus")
    with pytest.raises(fb.FiniteBudgetError, match="conflicts"):
        ce.build_sub_agent_options()


@pytest.mark.parametrize(
    "change",
    [
        {"model": "claude-opus-4-8"},
        {"model": "haiku"},
        {"extra_args": {"fallback-model": "opus"}},
        {"extra_args": {"max-turns": "999"}},
        {"mcp_servers": {"unaccounted": {"command": "unused"}}},
        {"resume": "old-session"},
    ],
)
def test_final_boundary_rejects_override(finite, change):
    options = ce.build_sub_agent_options()
    with pytest.raises(ValueError):
        ce._enforce_required_model_on_options(replace(options, **change))


def test_bound_options_cannot_downgrade_when_parent_profile_is_lost(
    finite, monkeypatch
):
    options = ce.build_sub_agent_options()
    monkeypatch.delenv(fb.PROFILE_ENV)
    monkeypatch.delenv(fb.DIGEST_ENV)
    with pytest.raises(fb.FiniteBudgetError, match="lost"):
        ce._enforce_required_model_on_options(options)


@pytest.mark.asyncio
async def test_provider_reported_wrong_model_blocks_budget_reuse(
    finite, transport, monkeypatch
):
    async def query(**kwargs):
        yield AssistantMessage(
            content=[TextBlock(text="public")], model="claude-opus-4-8"
        )
        yield terminal()

    monkeypatch.setattr(ce, "query", query)
    with pytest.raises(fb.FiniteBudgetError, match="different model"):
        await ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute(
            "public"
        )
    assert '"event":"failed"' in fb.load_finite_profile().ledger_path.read_text()


def test_legacy_direct_cli_route_rejects_finite_profile_before_writes(finite, tmp_path):
    from bob.dispatch import spawn_worker

    target = tmp_path / "unused-bob-dir"
    with pytest.raises(fb.FiniteBudgetError, match="budgeted SDK"):
        spawn_worker(SimpleNamespace(id="public"), "public", tmp_path, bob_dir=target)
    assert not target.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "Your credit balance is too low",
    "API Error: 401 authentication_error: invalid x-api-key",
    "API Error: 403 permission_error: not authorized",
])
@pytest.mark.parametrize("source", ["synthetic", "result", "exception"])
async def test_auth_billing_failure_is_truthful_and_never_retried(
    finite, transport, monkeypatch, message, source
):
    calls = []
    closed = []

    async def query(**kwargs):
        calls.append(1)
        try:
            if source == "synthetic":
                yield AssistantMessage(content=[TextBlock(text=message)], model="<synthetic>")
            elif source == "result":
                yield replace(terminal(cost=None, error=True), result=message)
            else:
                raise RuntimeError(message)
        finally:
            closed.append(1)

    monkeypatch.setattr(ce, "query", query)
    with pytest.raises(fb.FiniteAuthBillingError, match="authentication or billing") as failure:
        await ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute("public")
    assert "different model" not in str(failure.value)
    if "credit" in message:
        assert "credit balance is too low" in str(failure.value)
    with pytest.raises(fb.FiniteBudgetError, match="failed or invalid"):
        await ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute("public")
    assert calls == closed == [1]
    assert transport._process.kills == 1
    rows = [json.loads(line) for line in fb.load_finite_profile().ledger_path.read_text().splitlines()]
    assert [row["event"] for row in rows] == ["start", "reserve", "failed"]


@pytest.mark.asyncio
async def test_unclassified_synthetic_error_does_not_invent_billing_cause(finite, transport, monkeypatch):
    async def query(**kwargs):
        yield AssistantMessage(content=[TextBlock(text="API Error: service unavailable")], model="<synthetic>")
    monkeypatch.setattr(ce, "query", query)
    with pytest.raises(fb.FiniteProviderError, match="synthetic API error") as failure:
        await ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute("public")
    assert not isinstance(failure.value, fb.FiniteAuthBillingError)
    assert "different model" not in str(failure.value)


@pytest.mark.asyncio
async def test_real_model_can_discuss_billing_without_becoming_api_error(finite, transport, monkeypatch):
    async def query(**kwargs):
        yield AssistantMessage(content=[TextBlock(text="Your credit balance is too low")], model=fb.load_finite_profile().model_id)
        yield terminal()
    monkeypatch.setattr(ce, "query", query)
    result = await ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute("public")
    assert not result.is_error


@pytest.mark.asyncio
async def test_remaining_budget_shared_across_roles_and_reloads(
    finite, transport, monkeypatch
):
    seen = []

    async def query(**kwargs):
        seen.append(kwargs["options"])
        yield terminal()

    monkeypatch.setattr(ce, "query", query)
    for role in ["packet_compiler", "independent_test_writer", "implementer"]:
        result = await ce.ClaudeExecutor(
            default_options=ce.build_sub_agent_options(agent_role=role)
        ).execute("public")
        assert not result.is_error
    assert [o.extra_args["max-budget-usd"] for o in seen] == ["1.0", "0.8", "0.6"]
    assert [o.max_turns for o in seen] == [10, 8, 6]
    with pytest.raises(fb.FiniteBudgetError, match="exhausted"):
        await ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute(
            "fourth"
        )
    assert len(seen) == 3
    rows = [
        json.loads(x)
        for x in fb.load_finite_profile().ledger_path.read_text().splitlines()
    ]
    assert [r["role"] for r in rows if r["event"] == "reserve"] == [
        "packet_compiler",
        "independent_test_writer",
        "implementer",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cost,turns",
    [(None, 2), (-1, 2), (float("nan"), 2), (1.01, 2), (0.2, 11), (0.2, True)],
)
async def test_invalid_usage_keeps_reservation_and_blocks_restart(
    finite, transport, monkeypatch, cost, turns
):
    calls = []

    async def query(**kwargs):
        calls.append(1)
        yield terminal(cost, turns)

    monkeypatch.setattr(ce, "query", query)
    for _ in range(2):
        with pytest.raises(fb.FiniteBudgetError):
            await ce.ClaudeExecutor(
                default_options=ce.build_sub_agent_options()
            ).execute("public")
    assert len(calls) == 1
    assert '"event":"failed"' in fb.load_finite_profile().ledger_path.read_text()


@pytest.mark.asyncio
async def test_billable_interruption_never_retries_even_with_parent_retry_env(
    finite, transport, monkeypatch
):
    calls = []

    async def query(**kwargs):
        calls.append(1)
        yield terminal(0.3, 3)
        raise RuntimeError("connection reset after billable result")

    monkeypatch.setattr(ce, "query", query)
    monkeypatch.setenv("BOB_SDK_TRANSPORT_RETRIES", "100")
    with pytest.raises(RuntimeError, match="connection reset"):
        await ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute(
            "public"
        )
    with pytest.raises(fb.FiniteBudgetError):
        await ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute(
            "retry"
        )
    assert calls == [1] and transport._process.kills == 1
    assert (
        '"reserved_cost_usd":"1.0"' in fb.load_finite_profile().ledger_path.read_text()
    )


@pytest.mark.asyncio
async def test_wall_deadline_kills_owned_transport_and_closes_same_task(
    finite, transport, monkeypatch
):
    finite(max_wall_seconds=0.02)
    lifecycle = []

    async def query(**kwargs):
        lifecycle.append(("open", asyncio.current_task()))
        try:
            await asyncio.sleep(100)
            yield terminal()
        finally:
            lifecycle.append(("close", asyncio.current_task()))

    monkeypatch.setattr(ce, "query", query)
    with pytest.raises(fb.FiniteBudgetError, match="wall budget"):
        await ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute(
            "public"
        )
    assert lifecycle[0][1] is lifecycle[1][1]
    assert transport._process.kills == 1
    assert '"event":"failed"' in fb.load_finite_profile().ledger_path.read_text()


def test_active_or_interrupted_reservation_cannot_reset(finite):
    profile = fb.load_finite_profile()
    with fb.reserve(profile, role="implementer", prompt_sha256="a" * 64):
        with pytest.raises(fb.FiniteBudgetError, match="active session"):
            with fb.reserve(profile, role="reviewer", prompt_sha256="b" * 64):
                pytest.fail("concurrent dispatch")
    with pytest.raises(fb.FiniteBudgetError):
        with fb.reserve(
            fb.load_finite_profile(), role="implementer", prompt_sha256="c" * 64
        ):
            pytest.fail("unknown charge got a new allowance")


@pytest.mark.parametrize("cost,turns", [(1.0, 1), (0.01, 10)])
def test_cost_or_turn_exhaustion_prevents_dispatch(finite, cost, turns):
    profile = fb.load_finite_profile()
    with fb.reserve(profile, role="implementer", prompt_sha256="a" * 64) as budget:
        budget.finish(cost=cost, turns=turns, is_error=True)
    with pytest.raises(fb.FiniteBudgetError, match="exhausted"):
        with fb.reserve(profile, role="implementer", prompt_sha256="a" * 64):
            pytest.fail("over budget")


@pytest.mark.asyncio
async def test_cancellation_retains_reservation(finite, transport, monkeypatch):
    started = asyncio.Event()
    closed = []

    async def query(**kwargs):
        started.set()
        try:
            await asyncio.sleep(100)
            yield terminal()
        finally:
            closed.append(True)

    monkeypatch.setattr(ce, "query", query)
    task = asyncio.create_task(
        ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute(
            "public"
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed and transport._process.kills == 1
    assert '"event":"failed"' in fb.load_finite_profile().ledger_path.read_text()


def test_admitted_v2_binds_finite_profile_and_v1_remains_closed(finite, tmp_path):
    from tests.test_admitted_packet import _documents, _rewrite
    from bob.admitted_packet import (
        load_admitted_packet_context,
        AdmittedPacketError,
        FINITE_EXECUTION_PROFILE_SCHEMA_VERSION,
    )

    workspace, _, path, env, _, profile = _documents(tmp_path)
    with pytest.raises(AdmittedPacketError, match="versioned"):
        load_admitted_packet_context(workspace=workspace, environ=env)
    selected = fb.load_finite_profile()
    profile.update(
        schema_version=FINITE_EXECUTION_PROFILE_SCHEMA_VERSION,
        finite_execution_profile_sha256=selected.sha256,
        model={"id": selected.model_id},
    )
    profile["capability_profile"]["provider"] = "controller-brokered-pinned-model"
    profile["resource_profile"].update(
        semantic_turn_cap=10,
        semantic_cost_cap=1.0,
        semantic_attempt_cap=3,
        semantic_wall_seconds=60,
    )
    _rewrite(path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    loaded = load_admitted_packet_context(workspace=workspace, environ=env)
    assert loaded.execution_profile["model"]["id"] == selected.model_id
    profile["resource_profile"]["semantic_cost_cap"] = 2.0
    _rewrite(path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="resource caps"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_compiler_and_reviewer_use_sdk_boundary_and_versioned_provenance(
    finite, transport, monkeypatch
):
    from tests.test_atomic_packet_planner import (
        _proposal,
        _review,
        _catalog,
        _plan,
        _fenced,
    )
    from bob.atomic_packet_planner import (
        compile_packet_family_proposal,
        review_packet_family_proposal,
        canonical_sha256,
    )

    seen = []

    async def query(**kwargs):
        seen.append(kwargs["options"])
        proposal = _proposal()
        content = proposal if len(seen) == 1 else _review(proposal)
        yield AssistantMessage(
            content=[TextBlock(text=_fenced(content))], model=kwargs["options"].model
        )
        result = terminal()
        result.session_id = f"synthetic-session-{len(seen)}"
        yield result

    monkeypatch.setattr(ce, "query", query)
    kwargs = dict(
        spec_content="Canonical unit behavior\nUnknown values reject\n",
        ref_texts=[],
        feature_plan=_plan(),
        feature_plan_sha256="2" * 64,
        public_catalog=_catalog(),
        public_catalog_projection_sha256=canonical_sha256(_catalog()),
    )
    proposal = compile_packet_family_proposal(feature_key="PPAT-M0-UNIT", **kwargs)
    review = review_packet_family_proposal(proposal_witness=proposal, **kwargs)
    assert [o.model for o in seen] == [fb.load_finite_profile().model_id] * 2
    assert seen[1].extra_args["max-budget-usd"] == "0.8"
    assert proposal["provenance"]["schema_version"].endswith("v2")
    assert (
        review["provenance"]["finite_execution_profile_sha256"]
        == fb.load_finite_profile().sha256
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("hang", [False, True, "billing"])
async def test_installed_sdk_with_real_public_stub_process(
    finite, tmp_path, monkeypatch, hang
):
    """Exercise real SDK parsing/process cleanup; the executable never networks."""
    import sys
    from claude_code_sdk._internal.transport.subprocess_cli import (
        SubprocessCLITransport,
    )

    finite(max_wall_seconds=0.3 if hang is True else 10)
    executable = tmp_path / "synthetic-cli"
    message = {
        "type": "result",
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 2,
        "session_id": "public-synthetic-cli-session",
        "total_cost_usd": 0.2,
        "result": "public synthetic response",
    }
    if hang == "billing":
        message = {"type": "assistant", "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "Your credit balance is too low"}]}}
    executable.write_text(
        f"#!{sys.executable}\nimport time\n"
        + (
            "time.sleep(100)\n"
            if hang is True
            else f"print({json.dumps(message)!r}, flush=True)\n"
        )
    )
    executable.chmod(0o700)
    instances, processes = [], []

    class RecordingTransport(SubprocessCLITransport):
        async def connect(self):
            await super().connect()
            processes.append(self._process)

    def factory(prompt, options):
        instance = RecordingTransport(
            prompt=prompt, options=options, cli_path=executable
        )
        instances.append(instance)
        return instance

    monkeypatch.setattr(ce, "_sdk_transport", factory)
    executor = ce.ClaudeExecutor(default_options=ce.build_sub_agent_options())
    if hang == "billing":
        with pytest.raises(fb.FiniteAuthBillingError, match="credit balance is too low"):
            await executor.execute("synthetic public fixture")
    elif hang:
        with pytest.raises(fb.FiniteBudgetError, match="wall budget"):
            await executor.execute("synthetic public fixture")
    else:
        result = await executor.execute("synthetic public fixture")
        assert result.total_cost_usd == 0.2 and result.num_turns == 2
    assert len(instances) == len(processes) == 1
    assert processes[0].returncode is not None


@pytest.mark.asyncio
async def test_consumer_failure_closes_owned_stream_in_same_task(
    finite, transport, monkeypatch
):
    tasks = []

    async def query(**kwargs):
        tasks.append(asyncio.current_task())
        try:
            yield AssistantMessage(
                content=[TextBlock(text="public")],
                model=fb.load_finite_profile().model_id,
            )
            yield terminal()
        finally:
            tasks.append(asyncio.current_task())

    def consumer(msg, result):
        raise RuntimeError("consumer stopped")

    monkeypatch.setattr(ce, "query", query)
    with pytest.raises(RuntimeError, match="consumer stopped"):
        await ce.ClaudeExecutor(default_options=ce.build_sub_agent_options()).execute(
            "public", on_message=consumer
        )
    assert tasks[0] is tasks[1]
    assert transport._process.kills == 1
    assert '"event":"failed"' in fb.load_finite_profile().ledger_path.read_text()


def test_cleanup_never_kills_a_sibling_transport():
    killed = []
    owned = SimpleNamespace(
        _process=SimpleNamespace(returncode=None, kill=lambda: killed.append("owned"))
    )
    sibling = SimpleNamespace(
        _process=SimpleNamespace(returncode=None, kill=lambda: killed.append("sibling"))
    )
    ce._kill_transport_process(owned)
    assert killed == ["owned"]
    assert sibling._process.returncode is None


def test_feature_planner_uses_finite_model_at_real_executor_boundary(
    finite, transport, monkeypatch
):
    from bob.cli import _run_generate_features
    from tests.test_plaintext_feature_planner import _feature

    seen = []

    async def query(**kwargs):
        seen.append(kwargs["options"])
        yield AssistantMessage(
            content=[
                TextBlock(
                    text="```yaml\n"
                    + __import__("yaml").safe_dump({"features": [_feature()]})
                    + "```\n"
                )
            ],
            model=kwargs["options"].model,
        )
        yield terminal()

    monkeypatch.setattr(ce, "query", query)
    assert _run_generate_features("Build PPAT") == [_feature()]
    assert seen[0].model == fb.load_finite_profile().model_id
    assert seen[0].extra_args["max-budget-usd"] == "1.0"


@pytest.mark.asyncio
async def test_run_loop_finite_failure_never_verifies_or_promotes(
    finite, tmp_path, monkeypatch
):
    from unittest.mock import MagicMock
    from bob.orchestrator import run_loop as rl
    from tests.test_independent_test_writer_run_loop import _feature, _loop

    workspace = tmp_path / "candidate"
    workspace.mkdir()
    loop, feature = _loop(workspace), _feature()
    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "disabled")
    monkeypatch.setenv("BOB_REGRESSION_DETECTION_ENABLED", "0")
    monkeypatch.setattr(rl, "validate_candidate_execution_policy", lambda **kw: None)
    loop._recover_hardened_commit_intent = lambda *a, **kw: None
    monkeypatch.setattr(rl.db, "update_feature", MagicMock())
    evidence = MagicMock()
    monkeypatch.setattr(rl.db, "create_evidence", evidence)
    monkeypatch.setattr(rl, "wrap_prompt_with_orientation", lambda **kw: kw["prompt"])
    monkeypatch.setattr(rl, "git_get_status", lambda **kw: {"sha": "public-base"})
    seen = []

    async def spawn(**kwargs):
        seen.append(kwargs["options"])
        return ce.SpawnResult(
            ce.ExecutionResult(
                is_error=True,
                budget_error=True,
                error_message="synthetic budget exhaustion",
            ),
            SimpleNamespace(id="public-run"),
        )

    monkeypatch.setattr(rl, "spawn_sub_agent", spawn)
    verification = MagicMock(
        side_effect=AssertionError("must not promote failed attempt")
    )
    monkeypatch.setattr(rl, "run_verification_checklist", verification)
    result = await loop.execute_feature(feature)
    assert result.execution_result.is_error and loop.shutdown_requested
    assert seen[0].model == fb.load_finite_profile().model_id
    verification.assert_not_called()
    assert evidence.call_args.kwargs["type"] == "finite_execution_failure"


def test_import_order_preserves_real_mcp_module_identity(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            "import bob.dispatch; import bob.orchestrator; import importlib; "
            "m=importlib.import_module('bob.orchestrator.mcp_config'); "
            "assert bob.orchestrator.mcp_config is m",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_fresh_controller_process_uses_remaining_ledger(finite, tmp_path):
    import subprocess
    import sys

    profile = fb.load_finite_profile()
    with fb.reserve(profile, role="planner", prompt_sha256="a" * 64) as budget:
        budget.finish(cost=0.2, turns=2, is_error=False)
    code = (
        "from bob.finite_budget import load_finite_profile, reserve\n"
        "with reserve(load_finite_profile(), role='implementer', prompt_sha256='b'*64) as budget:\n"
        "    assert str(budget.cost) == '0.8' and budget.turns == 8\n"
        "    budget.finish(cost=0.1, turns=1, is_error=False)\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    with fb.reserve(profile, role="reviewer", prompt_sha256="c" * 64) as budget:
        assert str(budget.cost) == "0.7" and budget.turns == 7
        budget.finish(cost=0.1, turns=1, is_error=False)
