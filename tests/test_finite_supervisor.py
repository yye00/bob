"""Public local process fixtures; no model endpoint, hardware or paid calls."""

import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest

from bob import finite_supervisor as supervisor
from bob.finite_budget import DIGEST_ENV, PROFILE_ENV


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    controller = tmp_path / "controller"
    controller.mkdir(mode=0o700)
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    (workspace / "app/src").mkdir(parents=True)
    (workspace / "app/tests/public").mkdir(parents=True)
    database = controller / "bob.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE projects(id TEXT,workspace_path TEXT,total_cost_usd REAL); "
            "CREATE TABLE features(id TEXT,project_id TEXT,status TEXT);"
        )
        connection.execute(
            "INSERT INTO projects VALUES (?,?,?)", ("project", str(workspace), 0)
        )
        connection.execute(
            "INSERT INTO features VALUES (?,?,?)", ("feature", "project", "pending")
        )
    profile = controller / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "schema_version": "bob.finite-execution-profile.v1",
                "model_id": "claude-haiku-4-5-20251001",
                "max_cost_usd": 1,
                "max_turns": 10,
                "max_attempts": 3,
                "max_wall_seconds": 60,
            }
        )
    )
    profile.chmod(0o400)
    payload = {
        "schema_version": supervisor.SCHEMA,
        "workspace": str(workspace),
        "database": str(database),
        "feature_id": "feature",
        "profile": str(profile),
        "profile_sha256": hashlib.sha256(profile.read_bytes()).hexdigest(),
        "max_wall_seconds": 1,
        "poll_seconds": 0.1,
        "endpoint": "https://api.anthropic.com",
        "verification": {
            "source_dir": "app/src",
            "test_dir": "app/tests/public",
            "python": sys.executable,
        },
    }
    path = controller / "campaign.json"
    path.write_text(json.dumps(payload))
    path.chmod(0o400)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "public-test-not-a-real-key")
    return supervisor.load_config(path, digest)


def read_state(config):
    return json.loads(
        (Path(config["controller"]) / "supervisor-state.json").read_text()
    )


@pytest.mark.asyncio
async def test_preflight_retains_auth_billing_category(campaign, monkeypatch):
    from bob.finite_budget import FiniteAuthBillingError
    from bob.orchestrator.claude_executor import ClaudeExecutor

    monkeypatch.setenv(PROFILE_ENV, campaign["profile"])
    monkeypatch.setenv(DIGEST_ENV, campaign["profile_sha256"])

    async def reject(self, *args, **kwargs):
        raise FiniteAuthBillingError("provider authentication or billing failure: Your credit balance is too low")

    monkeypatch.setattr(ClaudeExecutor, "execute", reject)
    with pytest.raises(FiniteAuthBillingError):
        await supervisor.provider_preflight(campaign)
    receipt = json.loads((Path(campaign["controller"]) / "provider-preflight.json").read_text())
    assert receipt["passed"] is False
    assert receipt["error_category"] == "auth_or_billing"
    assert "credit balance is too low" in receipt["error_message"]


def successful_preflight(config):
    target = str(Path(config["controller"]) / "provider-preflight.json")
    result = {"passed": True, "config_sha256": config["config_sha256"]}
    return [
        sys.executable,
        "-I",
        "-c",
        f"from pathlib import Path; Path({target!r}).write_text({json.dumps(result)!r})",
    ]


def successful_worker(config):
    return [
        sys.executable,
        "-I",
        "-c",
        "import sqlite3; c=sqlite3.connect(" + repr(config["database"]) + "); "
        "c.execute(\"UPDATE features SET status='completed' WHERE id='feature'\"); c.commit()",
    ]


def test_network_waiting_is_not_reported_building_and_never_dispatches(
    campaign, monkeypatch
):
    monkeypatch.setattr(
        supervisor, "network_probe", lambda endpoint: (False, "synthetic DNS denial")
    )
    monkeypatch.setattr(
        supervisor, "preflight_argv", lambda config: pytest.fail("must not dispatch")
    )
    assert supervisor.supervise(campaign) == 3
    state = read_state(campaign)
    assert state["status"] == "wall_limit" and state["network_probes"] > 1
    assert state["worker_pid"] is None and state["provider_sessions_started"] is False
    events = (Path(campaign["controller"]) / "supervisor-events.jsonl").read_text()
    assert (
        '"status": "blocked_network"' in events and '"status": "building"' not in events
    )
    assert not (Path(campaign["controller"]) / "bob-finite-budget.jsonl").exists()
    assert supervisor.feature_snapshot(campaign)["status"] == "pending"


def test_missing_auth_does_not_substitute_oauth_or_probe_network(campaign, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "synthetic-oauth-not-used")
    monkeypatch.setattr(
        supervisor, "network_probe", lambda endpoint: pytest.fail("missing auth")
    )
    assert supervisor.supervise(campaign) == 3
    assert read_state(campaign)["network_probes"] == 0
    assert (
        '"status": "blocked_auth"'
        in (Path(campaign["controller"]) / "supervisor-events.jsonl").read_text()
    )


def test_local_child_processes_preflight_before_worker_and_complete(
    campaign, monkeypatch
):
    monkeypatch.setattr(
        supervisor, "network_probe", lambda endpoint: (True, "synthetic reachable")
    )
    monkeypatch.setattr(supervisor, "preflight_argv", successful_preflight)
    monkeypatch.setattr(supervisor, "worker_argv", successful_worker)
    assert supervisor.supervise(campaign) == 0
    state = read_state(campaign)
    assert state["status"] == "completed" and state["worker_returncode"] == 0
    assert state["feature"]["status"] == "completed"
    assert "not_independent_acceptance" in state["claim"]


@pytest.mark.parametrize(
    "variant", ["nonzero", "no_receipt", "wrong_binding", "negative_receipt"]
)
def test_preflight_failure_never_dispatches_feature(campaign, monkeypatch, variant):
    monkeypatch.setattr(
        supervisor, "network_probe", lambda endpoint: (True, "synthetic reachable")
    )
    monkeypatch.setattr(
        supervisor, "worker_argv", lambda config: pytest.fail("failed preflight")
    )
    if variant in {"nonzero", "no_receipt"}:
        command = [
            sys.executable,
            "-I",
            "-c",
            "raise SystemExit(" + ("2" if variant == "nonzero" else "0") + ")",
        ]
    else:
        receipt = {
            "passed": variant != "negative_receipt",
            "config_sha256": "wrong"
            if variant == "wrong_binding"
            else campaign["config_sha256"],
        }
        command = [
            sys.executable,
            "-I",
            "-c",
            "from pathlib import Path; Path("
            + repr(str(Path(campaign["controller"]) / "provider-preflight.json"))
            + ").write_text("
            + repr(json.dumps(receipt))
            + ")",
        ]
    monkeypatch.setattr(supervisor, "preflight_argv", lambda config: command)
    assert supervisor.supervise(campaign) == 2
    assert read_state(campaign)["status"] == "preflight_failed"
    assert supervisor.feature_snapshot(campaign)["status"] == "pending"


def test_worker_nonzero_exit_is_retained_and_not_reset_or_retried(
    campaign, monkeypatch
):
    monkeypatch.setattr(
        supervisor, "network_probe", lambda endpoint: (True, "synthetic reachable")
    )
    monkeypatch.setattr(supervisor, "preflight_argv", successful_preflight)
    monkeypatch.setattr(
        supervisor,
        "worker_argv",
        lambda config: [sys.executable, "-I", "-c", "raise SystemExit(3)"],
    )
    assert supervisor.supervise(campaign) == 2
    state = read_state(campaign)
    assert state["status"] == "worker_failed" and state["worker_returncode"] == 3
    assert supervisor.feature_snapshot(campaign)["status"] == "pending"


def test_zero_exit_without_completed_feature_is_not_success(campaign, monkeypatch):
    monkeypatch.setattr(
        supervisor, "network_probe", lambda endpoint: (True, "synthetic reachable")
    )
    monkeypatch.setattr(supervisor, "preflight_argv", successful_preflight)
    monkeypatch.setattr(
        supervisor, "worker_argv", lambda config: [sys.executable, "-I", "-c", "pass"]
    )
    assert supervisor.supervise(campaign) == 2
    assert read_state(campaign)["status"] == "worker_failed"


def test_stop_file_prevents_dispatch_and_preserves_state(campaign, monkeypatch):
    (Path(campaign["controller"]) / "STOP").touch()
    monkeypatch.setattr(
        supervisor, "network_probe", lambda endpoint: pytest.fail("stop precedes probe")
    )
    assert supervisor.supervise(campaign) == 130
    assert read_state(campaign)["status"] == "stopped"


def test_blocking_probe_cannot_start_a_worker_after_deadline(campaign, monkeypatch):
    def slow(endpoint):
        time.sleep(1.05)
        return True, "synthetic late success"

    monkeypatch.setattr(supervisor, "network_probe", slow)
    monkeypatch.setattr(
        supervisor, "preflight_argv", lambda config: pytest.fail("deadline reached")
    )
    assert supervisor.supervise(campaign) == 3
    assert read_state(campaign)["worker_pid"] is None


def test_hanging_owned_child_is_terminated_at_wall_limit(campaign, monkeypatch):
    monkeypatch.setattr(
        supervisor, "network_probe", lambda endpoint: (True, "synthetic reachable")
    )
    monkeypatch.setattr(
        supervisor,
        "preflight_argv",
        lambda config: [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
    )
    started = time.monotonic()
    assert supervisor.supervise(campaign) == 3
    assert time.monotonic() - started < 5
    assert read_state(campaign)["status"] == "wall_limit"


def test_duplicate_supervisor_lock_rejects_before_state_mutation(campaign):
    controller = Path(campaign["controller"])
    with (
        supervisor.exclusive_lock(controller / "supervisor.lock"),
        pytest.raises(BlockingIOError),
    ):
        supervisor.supervise(campaign)
    assert not (controller / "supervisor-state.json").exists()


def test_live_preflight_has_its_own_shorter_deadline(campaign, monkeypatch):
    monkeypatch.setattr(supervisor, "PREFLIGHT_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(
        supervisor, "network_probe", lambda endpoint: (True, "synthetic reachable")
    )
    monkeypatch.setattr(
        supervisor,
        "preflight_argv",
        lambda config: [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
    )
    monkeypatch.setattr(
        supervisor, "worker_argv", lambda config: pytest.fail("preflight timed out")
    )
    assert supervisor.supervise(campaign) == 2
    assert read_state(campaign)["status"] == "preflight_failed"
    assert read_state(campaign)["elapsed_seconds"] < campaign["max_wall_seconds"]


@pytest.mark.asyncio
async def test_preflight_requires_exact_model_response_no_tools_and_profile(
    campaign, monkeypatch
):
    from types import SimpleNamespace

    from claude_code_sdk import AssistantMessage, TextBlock

    from bob.orchestrator import claude_executor

    monkeypatch.setenv(PROFILE_ENV, campaign["profile"])
    monkeypatch.setenv(DIGEST_ENV, campaign["profile_sha256"])
    expected = "BOB_PREFLIGHT_" + campaign["config_sha256"][:16]
    seen = []

    async def execute(self, prompt, *, options):
        seen.append(options)
        return SimpleNamespace(
            is_error=False,
            budget_error=False,
            tool_uses=[],
            text=expected,
            total_cost_usd=0.01,
            num_turns=1,
            messages=[
                AssistantMessage(
                    content=[TextBlock(text=expected)],
                    model="claude-haiku-4-5-20251001",
                )
            ],
        )

    monkeypatch.setattr(claude_executor.ClaudeExecutor, "execute", execute)
    assert await supervisor.provider_preflight(campaign) == 0
    assert seen[0].max_turns == 1 and seen[0].extra_args["tools"] == ""
    assert seen[0].permission_mode == "dontAsk"
    receipt = json.loads(
        (Path(campaign["controller"]) / "provider-preflight.json").read_text()
    )
    assert receipt["passed"] and receipt["provider_models"] == [
        "claude-haiku-4-5-20251001"
    ]
    with pytest.raises(ValueError, match="already attempted"):
        await supervisor.provider_preflight(campaign)


def test_prior_attempt_evidence_prevents_silent_restart(campaign):
    target = Path(campaign["controller"]) / "supervisor-state.json"
    target.write_text('{"status":"worker_failed"}')
    with pytest.raises(ValueError, match="explicit recovery"):
        supervisor.supervise(campaign)
    assert target.read_text() == '{"status":"worker_failed"}'


def test_child_environment_pins_budget_and_removes_legacy_routes(campaign, monkeypatch):
    monkeypatch.setenv("BOB_MAX_COST_USD", "unlimited")
    monkeypatch.setenv("BOB_REQUIRED_MODEL", "opus")
    monkeypatch.setenv("BOB_PACKET_EXECUTION_PROFILE", "/wrong")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "synthetic-do-not-propagate")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://wrong.example")
    env = supervisor.child_environment(campaign)
    assert (
        env[PROFILE_ENV] == campaign["profile"]
        and env[DIGEST_ENV] == campaign["profile_sha256"]
    )
    assert "BOB_PACKET_EXECUTION_PROFILE" not in env and "PERPLEXITY_API_KEY" not in env
    assert "CLAUDE_CODE_USE_BEDROCK" not in env and "BOB_REQUIRED_MODEL" not in env
    assert env["ANTHROPIC_BASE_URL"] == campaign["endpoint"]
    assert env["BOB_EVALUATOR_REQUIRED"] == "1"


@pytest.mark.parametrize("mutation", ["hash", "mode", "parent", "binding", "deadline"])
def test_configuration_and_feature_binding_fail_closed(campaign, mutation):
    path = Path(campaign["config_path"])
    if mutation == "hash":
        with pytest.raises(ValueError, match="hash"):
            supervisor.load_config(path, "0" * 64)
    elif mutation in {"mode", "parent"}:
        (path if mutation == "mode" else path.parent).chmod(
            0o600 if mutation == "mode" else 0o755
        )
        with pytest.raises(ValueError, match="custody"):
            supervisor.load_config(path, campaign["config_sha256"])
    elif mutation == "binding":
        campaign["feature_id"] = "unknown"
        with pytest.raises(ValueError, match="binding"):
            supervisor.supervise(campaign)
    else:
        campaign["max_wall_seconds"] = 61
        with pytest.raises(ValueError, match="deadline"):
            supervisor.supervise(campaign)
