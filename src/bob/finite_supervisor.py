"""Supervise one finite public Bob feature using Bob's existing CLI and ledger.

No queue rewriting, budget renewal, automatic failed-attempt retry or scientific
acceptance is performed here. Run in the foreground under a process service or
the tool-managed session. A status file reports waiting separately from building.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import signal
import sqlite3
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from bob.finite_budget import DIGEST_ENV, PROFILE_ENV, load_finite_profile

SCHEMA = "bob.public-feature-supervisor.v2"
PREFLIGHT_TIMEOUT_SECONDS = 60


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as file:
        json.dump(value, file, indent=2, sort_keys=True, allow_nan=False)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)


def load_config(path, digest):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path or path.is_symlink():
        raise ValueError("configuration must be an absolute non-symlink path")
    metadata, parent = path.stat(), path.parent.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o400
        or stat.S_IMODE(parent.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
        or parent.st_uid != os.getuid()
    ):
        raise ValueError("configuration requires controller-owned private custody")
    raw = path.read_bytes()
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("configuration hash/size mismatch")

    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate configuration key")
            result[key] = value
        return result

    config = json.loads(raw, object_pairs_hook=unique)
    fields = {
        "schema_version",
        "workspace",
        "database",
        "feature_id",
        "profile",
        "profile_sha256",
        "max_wall_seconds",
        "poll_seconds",
        "endpoint",
        "verification",
    }
    if (
        not isinstance(config, dict)
        or set(config) != fields
        or config["schema_version"] != SCHEMA
    ):
        raise ValueError("unsupported supervisor configuration")
    for key in ("workspace", "database", "profile"):
        value = config[key]
        if (
            not isinstance(value, str)
            or not Path(value).is_absolute()
            or Path(value).resolve() != Path(value)
        ):
            raise ValueError(f"{key} must be an absolute canonical path")
    if not isinstance(config["feature_id"], str) or not config["feature_id"]:
        raise ValueError("one explicit feature identity is required")
    for key, minimum, maximum in (
        ("poll_seconds", 0.1, 60),
        ("max_wall_seconds", 1, 86400),
    ):
        value = config[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not minimum <= value <= maximum
        ):
            raise ValueError(f"invalid finite {key}")
    endpoint = urlsplit(config["endpoint"])
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
    ):
        raise ValueError(
            "endpoint must be an explicit HTTPS origin without credentials"
        )
    if not Path(config["workspace"]).is_dir() or not Path(config["database"]).is_file():
        raise ValueError("prepared workspace and Bob database are required")
    if path.parent.is_relative_to(Path(config["workspace"])):
        raise ValueError("supervisor/controller must be outside candidate workspace")
    verification = config["verification"]
    if not isinstance(verification, dict) or set(verification) != {
        "source_dir",
        "test_dir",
        "python",
    }:
        raise ValueError(
            "explicit public source/test/interpreter selection is required"
        )
    workspace = Path(config["workspace"])
    for key in ("source_dir", "test_dir"):
        value = verification[key]
        if (
            not isinstance(value, str)
            or not value
            or Path(value).is_absolute()
            or ".." in Path(value).parts
            or not (workspace / value).resolve().is_relative_to(workspace)
            or not (workspace / value).is_dir()
        ):
            raise ValueError("verification directories must exist inside the workspace")
    interpreter = verification["python"]
    if (
        not isinstance(interpreter, str)
        or not Path(interpreter).is_absolute()
        or not Path(interpreter).is_file()
        or not os.access(interpreter, os.X_OK)
    ):
        raise ValueError("public verification requires an explicit executable Python")
    config["controller"] = str(path.parent)
    config["config_path"] = str(path)
    config["config_sha256"] = digest
    return config


def child_environment(config):
    # The legacy self-build environment must not change this public task's route.
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("BOB_")
    }
    for key in (
        "PERPLEXITY_API_KEY",
        "CLAUDE_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "PYTHONPATH",
        "PYTHONHOME",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    ):
        env.pop(key, None)
    env.update(
        {
            PROFILE_ENV: config["profile"],
            DIGEST_ENV: config["profile_sha256"],
            "BOB_DATABASE_PATH": config["database"],
            "BOB_RESEARCH_MODE": "disabled",
            "BOB_MAX_CONCURRENT_FEATURES": "1",
            "BOB_SUB_AGENT_MAX_TURNS": "25",
            "BOB_EVALUATOR_MAX_TURNS": "8",
            "BOB_RCA_MAX_TURNS": "5",
            "BOB_EVALUATOR_REQUIRED": "1",
            "BOB_EVALUATOR_ENABLED": "1",
            "BOB_CLAUDE_HERMETIC": "1",
            "BOB_PUBLIC_EXECUTION_CONFIG": config["config_path"],
            "BOB_PUBLIC_EXECUTION_CONFIG_SHA256": config["config_sha256"],
            "ANTHROPIC_BASE_URL": config["endpoint"],
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTEST_ADDOPTS": "-p no:cacheprovider",
        }
    )
    return env


def feature_snapshot(config):
    connection = sqlite3.connect(
        Path(config["database"]).as_uri() + "?mode=ro", uri=True, timeout=2
    )
    try:
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute(
            "SELECT f.status,p.workspace_path,p.total_cost_usd FROM features f "
            "JOIN projects p ON p.id=f.project_id WHERE f.id=?",
            (config["feature_id"],),
        ).fetchone()
        if row is None or Path(row[1]).resolve() != Path(config["workspace"]):
            raise ValueError("feature/workspace binding mismatch")
        return {"status": row[0], "recorded_project_cost_usd": row[2]}
    finally:
        connection.close()


def network_probe(endpoint):
    """Unauthenticated TLS probe with an external deadline, including DNS."""
    host, port = urlsplit(endpoint).hostname, urlsplit(endpoint).port or 443
    script = (
        "import socket,ssl,sys; "
        "s=socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=3); "
        "s=ssl.create_default_context().wrap_socket(s,server_hostname=sys.argv[1]); s.close()"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script, host, str(port)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "DNS/TLS probe exceeded five seconds"
    if result.returncode:
        # Last exception line only; this subprocess never receives credentials in argv.
        return False, result.stderr.decode(errors="replace").splitlines()[-1][:300]
    return True, "TLS connection established; provider/model preflight still required"


def worker_argv(config):
    return [
        str(Path(sys.executable).parent / "bob"),
        "run",
        "--feature",
        config["feature_id"],
        "--no-mcp",
        "--max-concurrent-features",
        "1",
    ]


def preflight_argv(config):
    return [
        sys.executable,
        "-I",
        "-B",
        "-m",
        "bob.finite_supervisor",
        "--config",
        config["config_path"],
        "--sha256",
        config["config_sha256"],
        "--provider-preflight",
    ]


async def provider_preflight(config):
    """One no-tool request through the actual finite Bob SDK path."""
    from claude_code_sdk import AssistantMessage, ClaudeCodeOptions

    from bob.orchestrator.claude_executor import ClaudeExecutor

    profile = load_finite_profile()
    if profile is None or profile.sha256 != config["profile_sha256"]:
        raise ValueError("preflight requires the selected finite profile")
    receipt = Path(config["controller"]) / "provider-preflight.json"
    if receipt.exists():
        raise ValueError("preflight already attempted; preserve its receipt")
    expected = "BOB_PREFLIGHT_" + config["config_sha256"][:16]
    options = ClaudeCodeOptions(
        cwd=config["workspace"],
        model=profile.model_id,
        max_turns=1,
        permission_mode="dontAsk",
        allowed_tools=[],
        disallowed_tools=[
            "Bash",
            "Read",
            "Edit",
            "Write",
            "Glob",
            "Grep",
            "WebFetch",
            "WebSearch",
            "Task",
            "Agent",
        ],
        extra_args={"tools": ""},
    )
    record = {
        "claim": "live_provider_connectivity_only",
        "config_sha256": config["config_sha256"],
        "model": profile.model_id,
        "passed": False,
    }
    try:
        result = await ClaudeExecutor().execute(
            f"Reply with exactly {expected}. Do not use tools or inspect files.",
            options=options,
        )
        models = sorted(
            {
                message.model
                for message in result.messages
                if isinstance(message, AssistantMessage)
            }
        )
        passed = (
            not result.is_error
            and not result.budget_error
            and not result.tool_uses
            and result.text.strip() == expected
            and models == [profile.model_id]
        )
        record.update(
            passed=passed,
            provider_models=models,
            cost_usd=result.total_cost_usd,
            turns=result.num_turns,
            response_sha256=hashlib.sha256(result.text.encode()).hexdigest(),
        )
        write_json(receipt, record)
        return 0 if passed else 2
    except BaseException as exc:
        record["error_type"] = type(exc).__name__
        from bob.finite_budget import FiniteProviderError
        if isinstance(exc, FiniteProviderError):
            record.update(error_category=exc.category, error_message=str(exc))
        write_json(receipt, record)
        raise


@contextmanager
def exclusive_lock(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def stop_owned_process(child):
    """Only this supervisor's newly created process group can be signalled."""
    if child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)


def supervise(config):
    controller = Path(config["controller"])
    state_path, events_path = (
        controller / "supervisor-state.json",
        controller / "supervisor-events.jsonl",
    )
    env = child_environment(config)
    profile = load_finite_profile(env)
    if profile is None or config["max_wall_seconds"] > profile.max_wall_seconds:
        raise ValueError("supervisor deadline must fit the finite profile")
    profile.assert_outside(config["workspace"])
    env["BOB_REQUIRED_MODEL"] = profile.model_id
    env["BOB_MAX_COST_USD"] = str(profile.max_cost_usd)
    from bob.public_execution import load_public_execution

    load_public_execution(workspace=config["workspace"], environ=env)
    state = {
        "schema_version": SCHEMA,
        "claim": "public_development_not_independent_acceptance",
        "pid": os.getpid(),
        "pid_namespace": os.readlink("/proc/self/ns/pid"),
        "started_at": datetime.now(UTC).isoformat(),
        "config_sha256": config["config_sha256"],
        "model": profile.model_id,
        "feature_id": config["feature_id"],
        "worker_pid": None,
        "worker_returncode": None,
        "provider_sessions_started": False,
        "network_probes": 0,
        "auth_mode": "explicit_api_key_bare_cli_no_oauth",
    }
    child = None
    phase = "provider_preflight"
    child_started = None
    interrupted = False
    started = time.monotonic()
    previous_handlers = {}

    def interrupt(signum, frame):
        nonlocal interrupted
        interrupted = True

    def report(status, detail):
        changed = status != state.get("status") or detail != state.get("detail")
        state.update(
            status=status,
            detail=detail,
            heartbeat_at=datetime.now(UTC).isoformat(),
            elapsed_seconds=time.monotonic() - started,
        )
        write_json(state_path, state)
        if changed:
            with events_path.open("a") as file:
                file.write(json.dumps(state, sort_keys=True) + "\n")
                file.flush()
                os.fsync(file.fileno())
            print(
                json.dumps(
                    {
                        "status": status,
                        "detail": detail,
                        "worker_pid": state["worker_pid"],
                    }
                ),
                flush=True,
            )

    with exclusive_lock(controller / "supervisor.lock"):
        # A replacement supervisor cannot bless an interrupted/finished old attempt.
        if state_path.exists():
            raise ValueError(
                "supervisor evidence already exists; explicit recovery required"
            )
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, interrupt)
        try:
            state["feature"] = feature_snapshot(config)
            report("starting", "finite public Bob supervisor starting")
            while True:
                if interrupted or (controller / "STOP").exists():
                    report("stopping", "explicit stop requested")
                    if child is not None:
                        stop_owned_process(child)
                    report(
                        "stopped", "owned worker stopped; ledger and evidence retained"
                    )
                    return 130
                if time.monotonic() - started >= config["max_wall_seconds"]:
                    if child is not None:
                        stop_owned_process(child)
                    report(
                        "wall_limit", "supervisor deadline reached; no budget renewal"
                    )
                    return 3
                state["feature"] = feature_snapshot(config)
                if child is not None:
                    if (
                        phase == "provider_preflight"
                        and time.monotonic() - child_started
                        >= PREFLIGHT_TIMEOUT_SECONDS
                    ):
                        stop_owned_process(child)
                        report(
                            "preflight_failed",
                            "live provider preflight exceeded sixty seconds; reservation retained",
                        )
                        return 2
                    state["worker_returncode"] = child.poll()
                    if child.returncode is not None:
                        if phase == "provider_preflight":
                            receipt = controller / "provider-preflight.json"
                            evidence = (
                                json.loads(receipt.read_text())
                                if receipt.is_file()
                                else {}
                            )
                            if (
                                child.returncode != 0
                                or evidence.get("passed") is not True
                                or evidence.get("config_sha256")
                                != config["config_sha256"]
                            ):
                                report(
                                    "preflight_failed",
                                    "live model preflight failed; no feature dispatched or budget reset",
                                )
                                return 2
                            phase = "building"
                            argv = worker_argv(config)
                            state["worker_argv"] = argv
                            with (controller / "bob-worker.log").open("xb") as log:
                                child = subprocess.Popen(
                                    argv,
                                    cwd=config["workspace"],
                                    env=env,
                                    stdin=subprocess.DEVNULL,
                                    stdout=log,
                                    stderr=subprocess.STDOUT,
                                    start_new_session=True,
                                )
                            state["worker_pid"], state["worker_returncode"] = (
                                child.pid,
                                None,
                            )
                            child_started = time.monotonic()
                            report(
                                "building",
                                "live preflight passed; Bob CLI launched for exactly one feature",
                            )
                            continue
                        if (
                            child.returncode == 0
                            and state["feature"]["status"] == "completed"
                        ):
                            report(
                                "completed",
                                "Bob reports feature completed; independent acceptance remains separate",
                            )
                            return 0
                        report(
                            "worker_failed",
                            "worker exited; no automatic retry or database reset",
                        )
                        return 2
                    log_name = (
                        "bob-worker.log"
                        if phase == "building"
                        else "provider-preflight.log"
                    )
                    state["log_bytes"] = (controller / log_name).stat().st_size
                    report(
                        phase,
                        "owned Bob process alive; inspect feature and log for progress",
                    )
                elif not env.get("ANTHROPIC_API_KEY"):
                    report(
                        "blocked_auth",
                        "bare finite route requires an API key; OAuth is not silently substituted",
                    )
                else:
                    state["network_probes"] += 1
                    reachable, reason = network_probe(config["endpoint"])
                    if (
                        interrupted
                        or (controller / "STOP").exists()
                        or time.monotonic() - started >= config["max_wall_seconds"]
                    ):
                        continue
                    if not reachable:
                        report("blocked_network", reason)
                    else:
                        argv = preflight_argv(config)
                        state["worker_argv"] = argv
                        with (controller / "provider-preflight.log").open("xb") as log:
                            child = subprocess.Popen(
                                argv,
                                cwd=config["workspace"],
                                env=env,
                                stdin=subprocess.DEVNULL,
                                stdout=log,
                                stderr=subprocess.STDOUT,
                                start_new_session=True,
                            )
                        state["worker_pid"] = child.pid
                        child_started = time.monotonic()
                        state["provider_sessions_started"] = (
                            "unknown_until_budget_ledger"
                        )
                        report(
                            "provider_preflight",
                            "live no-tool Bob SDK preflight launched before feature dispatch",
                        )
                time.sleep(
                    min(
                        config["poll_seconds"],
                        max(
                            0, config["max_wall_seconds"] - (time.monotonic() - started)
                        ),
                    )
                )
        except Exception as exc:
            if child is not None:
                stop_owned_process(child)
            report("supervisor_failed", f"{type(exc).__name__}: {exc}")
            raise
        finally:
            for signum, previous in previous_handlers.items():
                signal.signal(signum, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument(
        "--provider-preflight", action="store_true", help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    config = load_config(args.config, args.sha256)
    raise SystemExit(
        asyncio.run(provider_preflight(config))
        if args.provider_preflight
        else supervise(config)
    )


if __name__ == "__main__":
    main()
