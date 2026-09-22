"""Opt-in controller budget for local spec-2 work; never a scoring policy.

One private, append-only ledger is shared by every semantic role and restart.
Reserve before dispatch. An interrupted/unknown session spends its reservation
and stops the campaign. There is deliberately no automatic transport retry.
The controller must keep this directory inaccessible to candidate principals.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import time
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

PROFILE_ENV = "BOB_FINITE_EXECUTION_PROFILE"
DIGEST_ENV = "BOB_FINITE_EXECUTION_PROFILE_SHA256"
SCHEMA = "bob.finite-execution-profile.v1"


class FiniteBudgetError(ValueError):
    """Invalid, exhausted, or uncertain controller budget."""


class FiniteProviderError(FiniteBudgetError):
    """Provider/CLI failure; reservation remains uncertain and cannot be reused."""

    category = "provider_error"


class FiniteAuthBillingError(FiniteProviderError):
    """Provider explicitly rejected authentication, authorization or billing."""

    category = "auth_or_billing"


def auth_billing_error(text):
    """Classify error-channel text, never ordinary assistant prose.

    Use fixed messages so provider diagnostics cannot leak credentials into
    controller receipts. Unknown errors must not acquire an invented cause.
    """
    lowered = text.lower()
    reasons = (
        (("credit balance is too low", "insufficient credit"), "Your credit balance is too low"),
        (("authentication_error", "invalid x-api-key", "invalid api key"), "provider rejected API credentials"),
        (("permission_error",), "provider denied account authorization"),
        (("billing_error", "billing error"), "provider reported a billing error"),
    )
    for markers, reason in reasons:
        if any(marker in lowered for marker in markers):
            return FiniteAuthBillingError(f"provider authentication or billing failure: {reason}")
    return None


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise FiniteBudgetError("duplicate budget JSON key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def _positive(value, label, *, integer=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, int if integer else (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise FiniteBudgetError(f"{label} must be positive and finite")
    return value


@dataclass(frozen=True)
class FiniteProfile:
    path: Path
    sha256: str
    model_id: str
    max_cost_usd: float
    max_turns: int
    max_attempts: int
    max_wall_seconds: float

    @property
    def ledger_path(self):
        return self.path.parent / "bob-finite-budget.jsonl"

    def assert_outside(self, workspace):
        if workspace is not None and self.path.parent.is_relative_to(
            Path(workspace).resolve()
        ):
            raise FiniteBudgetError(
                "budget custody must be outside the candidate workspace"
            )

    def options(self, options, *, cost=None, turns=None):
        """Recheck caller options; never silently change an explicit model."""
        if options.model != self.model_id:
            raise FiniteBudgetError("finite profile requires its exact model ID")
        env = dict(options.env or {})
        if env.get(DIGEST_ENV, self.sha256) != self.sha256:
            raise FiniteBudgetError("options bind a different finite profile")
        env[DIGEST_ENV] = self.sha256
        self.assert_outside(options.cwd)
        extra = dict(options.extra_args or {})
        forbidden = {
            "model",
            "fallback-model",
            "max-turns",
            "resume",
            "continue",
            "agents",
        }
        if (
            forbidden.intersection(extra)
            or getattr(options, "resume", None)
            or getattr(options, "continue_conversation", False)
        ):
            raise FiniteBudgetError(
                "finite profile forbids model/budget/session overrides"
            )
        if options.mcp_servers:
            raise FiniteBudgetError(
                "finite profile does not account external MCP spend"
            )
        limit = self.max_turns if turns is None else turns
        if options.max_turns is not None:
            _positive(options.max_turns, "max_turns", integer=True)
            limit = min(limit, options.max_turns)
        extra.update(
            {
                "max-budget-usd": str(self.max_cost_usd if cost is None else cost),
                "setting-sources": "",
                "strict-mcp-config": None,
                "no-session-persistence": None,
                "bare": None,
            }
        )
        # A nested worker could acquire an unaccounted session of its own.
        disallowed = list(
            dict.fromkeys([*(options.disallowed_tools or []), "Task", "Agent"])
        )
        return replace(
            options,
            max_turns=limit,
            extra_args=extra,
            disallowed_tools=disallowed,
            env=env,
        )


def load_finite_profile(environ=None) -> FiniteProfile | None:
    environment = os.environ if environ is None else environ
    path, digest = environment.get(PROFILE_ENV), environment.get(DIGEST_ENV)
    if path is None and digest is None:
        return None
    if not path or not digest or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise FiniteBudgetError("finite profile needs a path and exact SHA256")
    source = Path(path)
    if not source.is_absolute() or source.resolve() != source:
        raise FiniteBudgetError("finite profile needs an absolute non-symlink path")
    parent = source.parent.stat()
    if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) & 0o077:
        raise FiniteBudgetError(
            "finite profile parent must be controller-owned mode 0700"
        )
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o400
            or info.st_size > 16384
        ):
            raise FiniteBudgetError(
                "finite profile must be a private immutable single-link file"
            )
        raw = os.read(fd, 16385)
    finally:
        os.close(fd)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise FiniteBudgetError("finite profile SHA256 mismatch")
    value = _json(raw)
    keys = {
        "schema_version",
        "model_id",
        "max_cost_usd",
        "max_turns",
        "max_attempts",
        "max_wall_seconds",
    }
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or value["schema_version"] != SCHEMA
    ):
        raise FiniteBudgetError("unsupported finite profile schema")
    # Resolve through the installed adapter, with no fallback and no aliases.
    from bob.orchestrator.claude_executor import MODEL_ALIASES, resolve_model_name

    model = value["model_id"]
    if (
        not isinstance(model, str)
        or model.lower() in MODEL_ALIASES
        or resolve_model_name(model) != model
    ):
        raise FiniteBudgetError(
            "finite profile model must resolve exactly, without an alias"
        )
    for key in keys - {"schema_version", "model_id"}:
        _positive(value[key], key, integer=key in {"max_turns", "max_attempts"})
    return FiniteProfile(
        source, digest, **{k: value[k] for k in keys - {"schema_version"}}
    )


class BudgetReservation:
    def __init__(self, file, cost, turns, seconds):
        self.file, self.cost, self.turns, self.seconds = file, cost, turns, seconds
        self.finished = False
        self.observed_cost = None
        self.observed_turns = None

    def append(self, value):
        raw = (
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        )
        self.file.write(raw)
        self.file.flush()
        os.fsync(self.file.fileno())

    def validate_usage(self, *, cost, turns):
        if (
            isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or not math.isfinite(cost)
            or cost < 0
            or Decimal(str(cost)) > self.cost
            or isinstance(turns, bool)
            or not isinstance(turns, int)
            or not 0 <= turns <= self.turns
        ):
            raise FiniteBudgetError(
                "missing, invalid, or over-limit provider usage; reservation retained"
            )

    def finish(self, *, cost, turns, is_error):
        self.validate_usage(cost=cost, turns=turns)
        self.append(
            {
                "event": "finish",
                "cost_usd": str(cost),
                "turns": turns,
                "is_error": bool(is_error),
            }
        )
        self.finished = True


@contextlib.contextmanager
def reserve(profile: FiniteProfile, *, role: str, prompt_sha256: str):
    """Serialize calls across processes; a dangling reservation fails closed."""
    try:
        fd = os.open(
            profile.ledger_path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        created = True
    except FileExistsError:
        fd = os.open(profile.ledger_path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        created = False
    with os.fdopen(fd, "r+", encoding="utf-8") as file:
        info = os.fstat(file.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise FiniteBudgetError("budget ledger custody mismatch")
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise FiniteBudgetError(
                "finite budget already has an active session"
            ) from exc
        now = time.monotonic()
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        writer = BudgetReservation(
            file,
            Decimal(str(profile.max_cost_usd)),
            profile.max_turns,
            profile.max_wall_seconds,
        )
        if created:
            writer.append(
                {
                    "event": "start",
                    "profile_sha256": profile.sha256,
                    "boot_id": boot,
                    "started": now,
                }
            )
            directory = os.open(profile.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        file.seek(0)
        raw = file.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024 or not raw.endswith("\n"):
            raise FiniteBudgetError("budget ledger is incomplete or oversized")
        rows = [_json(line) for line in raw.splitlines()]
        if (
            not rows
            or rows[0].get("event") != "start"
            or rows[0].get("profile_sha256") != profile.sha256
            or rows[0].get("boot_id") != boot
        ):
            raise FiniteBudgetError("budget ledger profile/boot mismatch")
        started = rows[0].get("started")
        _positive(started, "ledger monotonic start")
        if now < started:
            raise FiniteBudgetError("budget ledger clock regressed")
        pending = False
        attempts = 0
        for row in rows[1:]:
            if row.get("event") == "reserve" and not pending:
                if (
                    row.get("cost_usd") != str(writer.cost)
                    or row.get("turns") != writer.turns
                ):
                    raise FiniteBudgetError("budget ledger reservation mismatch")
                pending = True
                attempts += 1
            elif row.get("event") == "finish" and pending:
                cost, turns = Decimal(row["cost_usd"]), row["turns"]
                if (
                    not cost.is_finite()
                    or not 0 <= cost <= writer.cost
                    or type(turns) is not int
                    or not 0 <= turns <= writer.turns
                ):
                    raise FiniteBudgetError("budget ledger usage mismatch")
                writer.cost -= cost
                writer.turns -= turns
                pending = False
            else:
                raise FiniteBudgetError(
                    "budget ledger contains a failed or invalid attempt"
                )
        if pending:
            raise FiniteBudgetError(
                "previous session usage is unknown; reservation retained"
            )
        writer.seconds = profile.max_wall_seconds - (now - started)
        if (
            writer.cost <= 0
            or writer.turns <= 0
            or writer.seconds <= 0
            or attempts >= profile.max_attempts
        ):
            raise FiniteBudgetError("finite campaign budget exhausted")
        file.seek(0, 2)
        writer.append(
            {
                "event": "reserve",
                "cost_usd": str(writer.cost),
                "turns": writer.turns,
                "role": role,
                "prompt_sha256": prompt_sha256,
                "attempt": attempts + 1,
            }
        )
        try:
            yield writer
        finally:
            if not writer.finished:
                writer.append(
                    {
                        "event": "failed",
                        "reason": "usage_or_cleanup_uncertain",
                        "reserved_cost_usd": str(writer.cost),
                        "reserved_turns": writer.turns,
                        "observed_cost_usd": writer.observed_cost,
                        "observed_turns": writer.observed_turns,
                    }
                )
