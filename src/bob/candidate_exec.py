"""Controller policy for executing untrusted candidate commands.

Bob's Python parent must never accidentally run candidate tests directly when
an external verifier boundary is required.  This module only constructs argv;
it never invokes a shell or interprets candidate text.
"""

from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path
from typing import Sequence


_PYTHON_LAUNCHER_RE = re.compile(r"python(?:\d+(?:\.\d+)*)?\Z", re.IGNORECASE)
_PYTEST_BOOTSTRAP = (
    'import sys; import pytest; sys.path.insert(0, "/workspace/app/src"); '
    "raise SystemExit(pytest.main(sys.argv[1:]))"
)
_SAFE_PYTHON_MODULES = frozenset({"bandit", "pip_audit"})


def external_verifier_required() -> bool:
    """Return the fail-closed ``BOB_EXTERNAL_VERIFIER_REQUIRED`` policy."""
    raw = os.environ.get("BOB_EXTERNAL_VERIFIER_REQUIRED")
    if raw is None or not raw.strip():
        return False
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        "BOB_EXTERNAL_VERIFIER_REQUIRED must be a boolean "
        f"(1/0, true/false, yes/no, on/off), got {raw!r}"
    )


def resolve_candidate_exec_wrapper() -> str | None:
    """Resolve and validate the optional argv-only candidate wrapper."""
    raw = os.environ.get("BOB_CANDIDATE_EXEC_WRAPPER", "").strip()
    required = external_verifier_required()
    if not raw:
        if required:
            raise RuntimeError(
                "BOB_EXTERNAL_VERIFIER_REQUIRED=1 requires an absolute "
                "BOB_CANDIDATE_EXEC_WRAPPER"
            )
        return None

    path = Path(raw)
    if not path.is_absolute():
        raise ValueError("BOB_CANDIDATE_EXEC_WRAPPER must be an absolute path")
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError(
            f"BOB_CANDIDATE_EXEC_WRAPPER is unavailable: {path}"
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("BOB_CANDIDATE_EXEC_WRAPPER must be a regular non-symlink file")
    if info.st_nlink != 1:
        raise ValueError("BOB_CANDIDATE_EXEC_WRAPPER must have exactly one hard link")
    if not os.access(path, os.X_OK):
        raise ValueError("BOB_CANDIDATE_EXEC_WRAPPER must be executable")
    return str(path)


def resolve_candidate_test_python() -> str | None:
    """Resolve the interpreter mounted into the candidate verification sandbox.

    Bob's controller interpreter is intentionally not assumed to exist inside
    the external verifier.  Hardened runs must pin an absolute executable via
    ``BOB_CANDIDATE_TEST_PYTHON`` before any Python/pytest candidate command is
    started.
    """
    raw = os.environ.get("BOB_CANDIDATE_TEST_PYTHON", "").strip()
    required = external_verifier_required()
    if not raw:
        if required:
            raise RuntimeError(
                "BOB_EXTERNAL_VERIFIER_REQUIRED=1 requires an absolute "
                "BOB_CANDIDATE_TEST_PYTHON for Python/pytest verification"
            )
        return None

    path = Path(raw)
    if not path.is_absolute():
        raise ValueError("BOB_CANDIDATE_TEST_PYTHON must be an absolute path")
    try:
        resolved = path.resolve(strict=True)
        info = resolved.stat()
    except OSError as exc:
        raise ValueError(
            f"BOB_CANDIDATE_TEST_PYTHON is unavailable: {path}"
        ) from exc
    if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK):
        raise ValueError("BOB_CANDIDATE_TEST_PYTHON must resolve to an executable file")
    return str(path)


def validate_candidate_execution_policy(*, workspace: str | Path | None = None) -> None:
    """Validate hardened execution controls before any candidate work starts."""
    hardened_members = {
        "BOB_EXTERNAL_VERIFIER_REQUIRED": external_verifier_required(),
        "BOB_INDEPENDENT_TEST_WRITER": os.environ.get(
            "BOB_INDEPENDENT_TEST_WRITER", ""
        ).strip().lower()
        in {"required", "1", "true", "yes", "on"},
        "BOB_EVALUATOR_REQUIRED": os.environ.get(
            "BOB_EVALUATOR_REQUIRED", ""
        ).strip().lower()
        in {"1", "true", "yes", "on"},
        "BOB_CLAUDE_HERMETIC": os.environ.get(
            "BOB_CLAUDE_HERMETIC", ""
        ).strip().lower()
        in {"1", "true", "yes", "on"},
        "BOB_DYNAMIC_DECOMPOSITION": os.environ.get(
            "BOB_DYNAMIC_DECOMPOSITION", ""
        ).strip().lower()
        in {"disabled", "0", "false", "no", "off"},
        "BOB_REQUIRED_MODEL": bool(
            os.environ.get("BOB_REQUIRED_MODEL", "").strip()
        ),
        "BOB_CANDIDATE_EXEC_WRAPPER": bool(
            os.environ.get("BOB_CANDIDATE_EXEC_WRAPPER", "").strip()
        ),
        "BOB_CANDIDATE_TEST_PYTHON": bool(
            os.environ.get("BOB_CANDIDATE_TEST_PYTHON", "").strip()
        ),
        "BOB_ADMITTED_PACKET_REQUIRED": (
            bool(os.environ.get("BOB_ADMITTED_PACKET_REQUIRED", "").strip())
            and os.environ.get("BOB_ADMITTED_PACKET_REQUIRED", "").strip().lower()
            not in {"disabled", "0", "false", "no", "off"}
        ),
        "BOB_PACKET_PROFILE_PRESENT": any(
            os.environ.get(name, "").strip()
            for name in (
                "BOB_PACKET_PROJECTION",
                "BOB_PACKET_PROJECTION_SHA256",
                "BOB_PACKET_EXECUTION_PROFILE",
                "BOB_PACKET_EXECUTION_PROFILE_SHA256",
            )
        ),
    }
    if not any(hardened_members.values()):
        return
    if not hardened_members["BOB_EXTERNAL_VERIFIER_REQUIRED"]:
        active = ", ".join(
            name for name, enabled in hardened_members.items() if enabled
        )
        raise RuntimeError(
            "partial hardened candidate policy is forbidden; set the complete "
            "profile including BOB_EXTERNAL_VERIFIER_REQUIRED=1 "
            f"(active: {active})"
        )

    if external_verifier_required():
        wrapper = Path(resolve_candidate_exec_wrapper() or "")
        test_python = Path(resolve_candidate_test_python() or "")
        required_values = {
            "BOB_INDEPENDENT_TEST_WRITER": {"required", "1", "true", "yes", "on"},
            "BOB_EVALUATOR_REQUIRED": {"1", "true", "yes", "on"},
            "BOB_CLAUDE_HERMETIC": {"1", "true", "yes", "on"},
            "BOB_DYNAMIC_DECOMPOSITION": {"disabled", "0", "false", "no", "off"},
        }
        if hardened_members["BOB_ADMITTED_PACKET_REQUIRED"]:
            required_values["BOB_ADMITTED_PACKET_REQUIRED"] = {
                "required", "1", "true", "yes", "on"
            }
        for name, allowed in required_values.items():
            value = os.environ.get(name, "").strip().lower()
            if value not in allowed:
                raise RuntimeError(
                    "hardened candidate execution requires a coherent policy: "
                    f"{name} is missing or incompatible"
                )
        model = os.environ.get("BOB_REQUIRED_MODEL", "").strip().lower()
        if model != "claude-opus-4-8":
            raise RuntimeError(
                "hardened candidate execution requires "
                "BOB_REQUIRED_MODEL=claude-opus-4-8"
            )

        if workspace is not None:
            candidate_root = Path(workspace).resolve(strict=True)

            def _outside_candidate(path: Path, *, name: str) -> None:
                resolved = path.resolve(strict=True)
                if resolved == candidate_root or candidate_root in resolved.parents:
                    raise RuntimeError(
                        f"{name} must be controller-owned outside the candidate workspace"
                    )

            _outside_candidate(wrapper, name="BOB_CANDIDATE_EXEC_WRAPPER")
            _outside_candidate(test_python, name="BOB_CANDIDATE_TEST_PYTHON")
            for name in ("BOB_DATABASE_PATH", "BOB_SESSIONS_ROOT"):
                raw = os.environ.get(name, "").strip()
                if not raw or not Path(raw).is_absolute():
                    raise RuntimeError(
                        f"hardened candidate execution requires absolute {name}"
                    )
                path = Path(raw)
                # The sessions directory may be created lazily; its nearest
                # existing parent is still required to be controller-owned.
                probe = path
                while not probe.exists() and probe != probe.parent:
                    probe = probe.parent
                _outside_candidate(probe, name=name)
            if hardened_members["BOB_ADMITTED_PACKET_REQUIRED"]:
                for name in (
                    "BOB_PACKET_PROJECTION",
                    "BOB_PACKET_EXECUTION_PROFILE",
                ):
                    raw = os.environ.get(name, "").strip()
                    if not raw or not Path(raw).is_absolute():
                        raise RuntimeError(
                            f"admitted packet execution requires absolute {name}"
                        )
                    _outside_candidate(Path(raw), name=name)


def _looks_like_python_launcher(token: str) -> bool:
    """Return whether *token* is a Python interpreter command/path."""
    if token == sys.executable:
        return True
    try:
        if Path(token).is_absolute() and Path(token).resolve() == Path(sys.executable).resolve():
            return True
    except OSError:
        pass
    return bool(_PYTHON_LAUNCHER_RE.fullmatch(Path(token).name))


def _rewrite_python_command(command: list[str], test_python: str) -> list[str]:
    """Translate a recognized Python verifier command to the pinned runtime.

    Pytest is imported under isolated mode before the candidate source path is
    added.  This prevents a workspace ``sitecustomize`` or package named
    ``pytest`` from running during trusted verifier startup while still making
    the candidate application importable to its tests.
    """
    args = command[1:]
    try:
        module_index = args.index("-m")
    except ValueError:
        module_index = -1

    if module_index >= 0 and module_index + 1 < len(args):
        prefix = args[:module_index]
        module = args[module_index + 1]
        module_args = args[module_index + 2 :]
        if any(flag not in {"-I", "-B"} for flag in prefix):
            raise ValueError(
                "unrecognized flags before Python verifier module in hardened mode"
            )
        if module == "pytest":
            return [test_python, "-I", "-B", "-c", _PYTEST_BOOTSTRAP, *module_args]
        if module in _SAFE_PYTHON_MODULES:
            return [test_python, "-I", "-B", "-m", module, *module_args]

    if external_verifier_required():
        raise ValueError(
            "unrecognized dynamic Python command is forbidden when "
            "BOB_EXTERNAL_VERIFIER_REQUIRED=1"
        )
    command[0] = test_python
    return command


def candidate_argv(argv: Sequence[str]) -> list[str]:
    """Return a direct argv routed through the trusted wrapper when configured."""
    if not argv or not all(
        isinstance(token, str) and token and "\x00" not in token for token in argv
    ):
        raise ValueError("candidate command must be a non-empty argv of safe strings")
    command = list(argv)
    if _looks_like_python_launcher(command[0]):
        test_python = resolve_candidate_test_python()
        if test_python is not None:
            command = _rewrite_python_command(command, test_python)
    wrapper = resolve_candidate_exec_wrapper()
    return ([wrapper] if wrapper is not None else []) + command


__all__ = [
    "candidate_argv",
    "external_verifier_required",
    "resolve_candidate_exec_wrapper",
    "resolve_candidate_test_python",
    "validate_candidate_execution_policy",
]
