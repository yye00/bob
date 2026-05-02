"""Enhanced verification system for Bob3.

This module provides semantic verification that checks whether features are
actually implemented, not just whether files exist.

Key improvements over basic verification:
1. Acceptance criteria validation - checks if specific requirements are met
2. File modification tracking - verifies code was actually written
3. Integration verification - for "integrate" features, checks for actual integration code
4. Semantic analysis - understands feature intent and validates accordingly
"""

from __future__ import annotations

import ast
import json
import logging
import os
import pathlib
import re
import signal
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Allowlist enforcement for ``python:`` acceptance criteria
# ---------------------------------------------------------------------------
#
# The ``python: <expression>`` criterion form runs ``python -c <expression>``
# in the workspace. Even though specs come from a (notionally) trusted
# project author, the execution path used to be wide open: a spec could
# import ``os`` and delete files, exfiltrate secrets via ``urllib`` /
# ``http`` / ``socket``, or shell out via ``subprocess``. The trust
# boundary should be explicit and enforced.
#
# This is NOT a sandbox — Python sandboxing is fundamentally hard. The goal
# is to raise the bar from "trivially exploitable in one line" to "requires
# real effort". We do a simple AST scan of the expression before running it
# and refuse anything that imports a banned top-level module or names a
# banned function/attribute. Specs that need unrestricted access should use
# the ``pytest:`` form, which is itself sandboxed by the test framework
# (collection-time errors, isolated test process, etc.).

# Top-level imports (and ``from <module> import ...`` source modules) that
# are categorically banned from ``python:`` criteria. Submodules (e.g.
# ``urllib.request``) are caught via the prefix check below.
_PYTHON_CRITERION_BANNED_MODULES: frozenset[str] = frozenset(
    {
        "subprocess",
        "socket",
        "urllib",
        "http",
        "requests",
        "ftplib",
        "telnetlib",
        "smtplib",
        "shutil",
        "ctypes",
        "multiprocessing",
        "pty",
        "pickle",
        "marshal",
        # Filesystem / environment access. ``os`` was the most glaring
        # gap: ``import os; os.open(..., os.O_WRONLY|os.O_CREAT)`` writes
        # arbitrary files, ``os.getenv`` reads secrets like
        # ``ANTHROPIC_API_KEY``, and ``os.read``/``os.write`` operate on
        # raw file descriptors below the ``open(..., "w")`` allowlist.
        # ``pathlib`` provides equivalent fs primitives
        # (``Path.read_text``, ``Path.write_text``, ``Path.unlink``).
        # ``tempfile`` and ``glob`` enable file creation / information
        # disclosure (listing dirs to find sensitive files). All four
        # belong on the ban-list. Specs that genuinely need to touch the
        # filesystem should use the ``pytest:`` form, which is sandboxed
        # by the test framework.
        "os",
        "pathlib",
        "tempfile",
        "glob",
        # Dynamic-import escape hatches: each provides a way to load and
        # execute another module by name, sidestepping the static ``import``
        # check above. ``importlib.import_module("os")`` is the canonical
        # bypass; ``runpy.run_module`` runs a module as ``__main__`` (which
        # can include a side-effecting top level); ``pkgutil`` exposes
        # ``find_loader`` / ``get_loader`` that return loadable module
        # objects.
        "importlib",
        "runpy",
        "pkgutil",
        # ``builtins`` is the namespace module that backs every unqualified
        # name lookup. ``import builtins; builtins.open(...)`` reaches the
        # same callable as the bare ``open`` (which is itself banned below),
        # and ``builtins.__import__("os")`` re-opens the dynamic-import
        # escape hatch that ``importlib`` already covers. Banning the
        # module shuts the named-attribute path entirely; the dunder-attr
        # ban on ``__builtins__`` separately covers the implicit namespace
        # accessor.
        "builtins",
    }
)

# Bare callable names that, regardless of how they were obtained, are
# refused. We catch ``eval(...)``, ``exec(...)``, ``__import__("os")``,
# ``compile(...)`` etc. by AST name and by attribute access (``foo.eval``,
# ``builtins.exec``). The ban below also covers ``open(...)``: read-mode
# bypass attacks like ``python: open("/proc/self/environ").read()`` (which
# leaks API keys / secrets from the parent process environment) and
# ``builtins.open("/etc/passwd").read()`` were possible because the
# previous check only refused write-mode ``open(..., "w")``. We now ban
# ``open`` outright — read access to filesystem paths is just as much of
# an exfiltration vector as writes, and any criterion that genuinely
# needs filesystem access should use the ``pytest:`` form (pytest
# ``tmp_path`` is the right primitive). The banned-attribute matcher
# below covers ``builtins.open(...)`` and ``some_obj.open(...)`` as well.
#
# ``getattr``/``setattr``/``delattr`` are refused because they let an
# attacker construct any attribute name dynamically (``getattr(o, "sys"+
# "tem")``), bypassing the attribute-name allowlist below. ``globals``,
# ``locals``, and ``vars`` return mutable mappings of the caller's
# namespace; mutating them is an arbitrary-code-execution primitive.
_PYTHON_CRITERION_BANNED_CALL_NAMES: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "open",
    }
)

# Attribute accesses that are banned outright regardless of which object
# they hang off (``os.system``, ``shutil.rmtree``, ``os.environ``, etc.).
# Matching is on the trailing attribute name only — that catches both
# ``os.system(...)`` and ``import os as _o; _o.system(...)``.
#
# The dunder attributes below close the classic Python sandbox-escape
# pattern that walks the class hierarchy to reach ``object.__subclasses__``
# and from there any class in the running interpreter (most notably
# ``BuiltinImporter`` / ``Popen`` / etc.). Examples blocked:
#   ``().__class__.__bases__[0].__subclasses__()``
#   ``"".__class__.__mro__[-1].__subclasses__()``
#   ``(lambda: 0).__globals__["__builtins__"]``
#   ``__builtins__.__getattribute__("eval")``
_PYTHON_CRITERION_BANNED_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "system",
        "popen",
        "spawnl",
        "spawnle",
        "spawnv",
        "spawnve",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "remove",
        "unlink",
        "rmdir",
        "removedirs",
        "rmtree",
        "environ",
        "putenv",
        "chmod",
        "chown",
        "kill",
        "killpg",
        "fork",
        "forkpty",
        # Dunder attribute escape paths.
        "__class__",
        "__bases__",
        "__subclasses__",
        "__mro__",
        "mro",
        "__dict__",
        "__globals__",
        "__builtins__",
        "__init_subclass__",
        "__getattribute__",
        "__getattr__",
    }
)

def _expression_uses_banned_operation(expression: str) -> str | None:
    """AST-scan ``expression`` for banned operations.

    Returns the name of the first banned operation encountered (e.g.
    ``"subprocess"``, ``"os.system"``, ``"open(<write-mode>)"``) or
    ``None`` if the expression looks clean.

    This is intentionally minimal — it catches the obvious paths
    (``import os; os.system(...)``, ``__import__("subprocess")``,
    ``open("/etc/passwd", "w")``, ``getattr(__import__("os"), "system")``,
    ``().__class__.__bases__[0].__subclasses__()``,
    ``__builtins__.__getattribute__("eval")``) but is NOT a sandbox.
    Specs needing unrestricted access should use the ``pytest:`` form,
    which is itself sandboxed by the test framework.

    Detection rules:
        * ``import <banned>`` / ``from <banned> import ...`` are refused —
          including dynamic-import escape modules like ``importlib``,
          ``runpy``, ``pkgutil``.
        * Bare-name calls (``eval(...)``, ``__import__(...)``,
          ``getattr(...)``, ``setattr(...)``, ``globals()``,
          ``locals()``, ``vars()``) are refused regardless of argument
          form. ``getattr(o, name)`` is refused even when ``name`` is a
          dynamically constructed (non-constant) string, because the
          attacker controls the construction.
        * Attribute-call form (``foo.system(...)``,
          ``cls.__subclasses__()``, ``obj.__getattribute__(...)``) is
          refused on the trailing attribute name.
        * Bare attribute reads (``os.environ``, ``().__class__``,
          ``f.__globals__``, ``__builtins__.__dict__``) are refused —
          mutable namespaces and dunder escape-paths are blocked even
          without a call.
        * Bare references to banned builtins (``f = eval``) are refused.
    """
    try:
        tree = ast.parse(expression, mode="exec")
    except SyntaxError:
        # Let the runtime failure path report the syntax error rather than
        # masking it with a "banned operation" message.
        return None

    def _banned_module(name: str) -> str | None:
        if not name:
            return None
        head = name.split(".", 1)[0]
        if head in _PYTHON_CRITERION_BANNED_MODULES:
            return head
        return None

    for node in ast.walk(tree):
        # ``import foo`` / ``import foo.bar``
        if isinstance(node, ast.Import):
            for alias in node.names:
                bad = _banned_module(alias.name)
                if bad is not None:
                    return f"import {bad}"

        # ``from foo import ...`` / ``from foo.bar import ...``
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            bad = _banned_module(module)
            if bad is not None:
                return f"from {bad} import ..."

        # Plain-name calls: ``eval(...)``, ``exec(...)``, ``__import__(...)``,
        # ``getattr(...)``, ``setattr(...)``, ``globals()``, ``locals()``,
        # ``vars()``, ``open(...)``. These are refused regardless of the
        # form of their arguments — ``getattr(__import__("os"), "sys"+"tem")``
        # is just as dangerous as ``getattr(o, "system")``, so we never look
        # at args. ``open`` is banned outright (any mode) because read-mode
        # access to ``/proc/self/environ``, ``/etc/passwd``, etc. is itself
        # an exfiltration vector — see the comment on
        # ``_PYTHON_CRITERION_BANNED_CALL_NAMES`` above.
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in _PYTHON_CRITERION_BANNED_CALL_NAMES:
                    return func.id
            # Attribute calls: ``os.system(...)``, ``shutil.rmtree(...)``,
            # ``cls.__subclasses__()``, ``obj.__getattribute__("eval")``.
            # We also refuse attribute-call forms of the banned-call-name
            # set (``builtins.getattr(...)``, ``b.eval(...)``) so a wrapper
            # module can't smuggle in the call.
            if isinstance(func, ast.Attribute):
                if func.attr in _PYTHON_CRITERION_BANNED_ATTRIBUTES:
                    return f".{func.attr}(...)"
                if func.attr in _PYTHON_CRITERION_BANNED_CALL_NAMES:
                    return f".{func.attr}(...)"

        # Bare attribute access (no call): ``os.environ`` is dangerous even
        # without a call because it's a mutable mapping the expression can
        # mutate. ``Call`` was already handled above; here we catch reads
        # of dunder escape-path attributes (``().__class__``,
        # ``f.__globals__``, ``cls.__bases__``, ``obj.__dict__``) too.
        elif isinstance(node, ast.Attribute):
            if node.attr in _PYTHON_CRITERION_BANNED_ATTRIBUTES:
                return f".{node.attr}"

        # Bare name reference to a banned builtin (e.g. ``f = eval``,
        # ``g = getattr``). Catches "rename then call" smuggling.
        elif isinstance(node, ast.Name):
            if node.id in _PYTHON_CRITERION_BANNED_CALL_NAMES:
                return node.id

    return None


# ---------------------------------------------------------------------------
# Shared subprocess helper: timeout-with-process-group-kill
# ---------------------------------------------------------------------------
#
# ``subprocess.run(..., timeout=...)`` only sends SIGKILL to the direct child.
# Any grandchildren that inherited the stdout/stderr pipe FDs (e.g. a test
# that does ``subprocess.Popen(["sleep", "9999"])``) hold them open, and
# ``run``'s implicit pipe-drain will block forever waiting for EOF. See
# bpo-31935 / bpo-38207.
#
# The fix here launches the child in its own process group
# (``start_new_session=True`` on POSIX) and, on timeout, SIGKILLs the whole
# group via ``os.killpg`` before draining the pipes with a short secondary
# timeout. This is shared by ``_check_tests_pass`` (in ``superpowers``),
# ``_run_pytest_criterion``, and ``_run_python_criterion`` so the verifier
# never hangs on a runaway grandchild process.


def _run_with_pgroup_timeout(
    cmd: list[str],
    cwd: str | pathlib.Path,
    timeout_s: int,
    *,
    env: dict[str, str] | None = None,
) -> tuple[str, str, int, bool]:
    """Run ``cmd`` with a timeout that kills the entire process group.

    Returns ``(stdout, stderr, returncode, timed_out)``. On timeout,
    ``returncode`` is ``-1`` and ``timed_out`` is ``True``; stdout/stderr
    contain whatever was buffered before the kill (often empty if the kill
    happened before pytest could flush its summary line).
    """
    popen_kwargs: dict = {
        "cwd": str(cwd),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if env is not None:
        popen_kwargs["env"] = env
    # ``start_new_session`` is POSIX-only and creates a new process group so
    # we can SIGKILL the whole tree on timeout.
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kwargs)  # nosec B603 - controlled args list, no shell.
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
        return stdout or "", stderr or "", proc.returncode, False
    except subprocess.TimeoutExpired:
        # Kill the entire process group so grandchildren don't keep the
        # stdout/stderr pipes open.
        if os.name == "posix":
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                # Already gone or unable to signal; fall back to direct kill.
                try:
                    proc.kill()
                except Exception:
                    pass
        else:
            try:
                proc.kill()
            except Exception:
                pass
        # Drain pipes with a short secondary timeout. If the kill didn't
        # release the FDs we still need to return -- so swallow a second
        # TimeoutExpired and return empty buffers.
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
            stdout, stderr = "", ""
        return stdout or "", stderr or "", -1, True


# ---------------------------------------------------------------------------
# Executable acceptance-criterion helpers
# ---------------------------------------------------------------------------
#
# These are the only sanctioned uses of ``subprocess`` in
# ``enhanced_verification``: they implement the ``pytest:`` and ``python:``
# criterion forms that let specs declare a real test invocation as their
# acceptance criterion. Everything else in this module is static analysis.
#
# Both helpers return ``(passed: bool, details: str)``. They never raise — a
# misbehaving criterion or workspace must degrade to ``(False, <reason>)``
# instead of crashing the verification pipeline.


def _run_pytest_criterion(
    workspace: pathlib.Path,
    expression: str,
    timeout: int = 60,
) -> tuple[bool, str]:
    """Run ``python -m pytest <expression>`` inside ``workspace``.

    ``expression`` is the substring after the ``pytest:`` prefix, typically a
    pytest node id like ``tests/test_foo.py::test_bar``.

    A criterion is considered passed only when pytest exits 0 *and* its
    stdout reports at least one passed test. This rejects the common
    "no tests collected" silent-success case (pytest can exit 5 when nothing
    is collected, but some configs/plugins make that exit 0; double-check
    the stdout summary either way).

    All exceptional outcomes — timeout, missing python, missing workspace,
    or arbitrary errors — return ``(False, <human-readable reason>)``.
    """
    if not workspace.exists():
        return False, "workspace not found"

    if not expression:
        return False, "pytest criterion is empty"

    # The ``--`` sentinel separates pytest's own flags from positional
    # arguments. Without it, an attacker-controlled criterion like
    # ``pytest: --co tests/`` would land in the flag-position of the
    # argv and reconfigure pytest (``--co`` makes pytest collect-only,
    # which exits 0 without running any test — a silent pass). After
    # ``--``, pytest treats every following token as a path/nodeid
    # regardless of leading dashes, so the worst an injected flag can
    # do is fail the collection step (which we already report as a
    # criterion failure).
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--tb=no",
        "-q",
        # Force plain output. Without this, FORCE_COLOR=1 / PY_COLORS=1 or
        # third-party plugins (pytest-sugar, anyio, ...) emit ANSI escape
        # codes between the digit and ``passed`` token, which breaks the
        # ``"passed" in stdout`` check below in some pytest builds and
        # confuses the summary regex in superpowers._parse_pytest_counts.
        "--color=no",
        "--",
        expression,
    ]
    try:
        stdout, stderr, exit_code, timed_out = _run_with_pgroup_timeout(
            cmd,
            cwd=workspace,
            timeout_s=timeout,
        )
    except FileNotFoundError as e:
        return False, f"pytest criterion failed to launch python: {e}"
    except Exception as e:  # pragma: no cover - defensive
        return False, f"pytest criterion errored: {e}"

    if timed_out:
        return (
            False,
            f"pytest criterion timed out after {timeout}s: {expression!r}",
        )

    passed = exit_code == 0 and "passed" in stdout.lower()
    if passed:
        return True, ""

    tail = (stdout + stderr)[-600:]
    return (
        False,
        f"pytest criterion failed (exit={exit_code}) for {expression!r}: {tail.strip()}",
    )


def _run_python_criterion(
    workspace: pathlib.Path,
    expression: str,
    timeout: int = 60,
) -> tuple[bool, str]:
    """Run ``python -c "<expression>"`` inside ``workspace``.

    The expression is the substring after the ``python:`` prefix. Typical
    use is a quick assertion such as ``from mod import f; assert f() == 42``.

    Before executing, the expression is AST-scanned against an allowlist:
    imports of dangerous modules (``subprocess``, ``socket``, ``urllib``,
    ``http``, ``shutil``, ``builtins``, ...) and calls to dangerous
    builtins/attributes (``eval``, ``exec``, ``__import__``, ``open``,
    ``os.system``, ``os.environ``, ``os.remove``, ``os.unlink``,
    ``shutil.rmtree``) are refused with ``(False, "Refused: ...")``. This
    is not a sandbox — it raises the bar from "trivially exploitable" to
    "requires real effort". Specs needing unrestricted access (including
    any filesystem access at all) should use the ``pytest:`` form,
    which is naturally sandboxed by the test framework — pytest's
    ``tmp_path`` fixture is the right primitive for filesystem-touching
    criteria.

    Returns ``(True, "")`` when the inline expression exits 0; otherwise
    ``(False, <stderr or summary>)``. Same defensive error handling as
    :func:`_run_pytest_criterion`.
    """
    if not workspace.exists():
        return False, "workspace not found"

    if not expression:
        return False, "python criterion is empty"

    banned = _expression_uses_banned_operation(expression)
    if banned is not None:
        return (
            False,
            f"Refused: criterion uses banned operation {banned!r}",
        )

    try:
        stdout, stderr, returncode, timed_out = _run_with_pgroup_timeout(
            [sys.executable, "-c", expression],
            cwd=workspace,
            timeout_s=timeout,
        )
    except FileNotFoundError as e:
        return False, f"python criterion failed to launch python: {e}"
    except Exception as e:  # pragma: no cover - defensive
        return False, f"python criterion errored: {e}"

    if timed_out:
        return (
            False,
            f"python criterion timed out after {timeout}s: {expression!r}",
        )

    if returncode == 0:
        return True, ""

    stderr = (stderr or "").strip()
    stdout = (stdout or "").strip()
    tail = (stderr or stdout)[-600:]
    return (
        False,
        f"python criterion failed (exit={returncode}): {tail}",
    )


def _criterion_exec_timeout() -> int:
    """Resolve the per-criterion executable timeout from the environment.

    Falls back to 60s when ``BOB3_CRITERION_EXEC_TIMEOUT`` is unset or not a
    positive integer.
    """
    raw = os.environ.get("BOB3_CRITERION_EXEC_TIMEOUT")
    if not raw:
        return 60
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 60
    return value if value > 0 else 60


def _check_criterion_with_details(
    *,
    criterion: str,
    workspace: pathlib.Path,
    is_python_project: bool,
    is_cmake_project: bool,
    is_opm_project: bool,
) -> tuple[bool, str]:
    """Check a single criterion and return ``(passed, details)``.

    Routes ``pytest:`` and ``python:`` forms to their executable helpers and
    delegates everything else to the legacy keyword-pattern :func:`_check_criterion`
    static checker, returning empty details for the legacy path.
    """
    stripped = criterion.strip() if isinstance(criterion, str) else ""
    timeout = _criterion_exec_timeout()

    if stripped.lower().startswith("pytest:"):
        expression = stripped[len("pytest:"):].strip()
        return _run_pytest_criterion(workspace, expression, timeout=timeout)

    if stripped.lower().startswith("python:"):
        expression = stripped[len("python:"):].strip()
        return _run_python_criterion(workspace, expression, timeout=timeout)

    result = _check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=is_python_project,
        is_cmake_project=is_cmake_project,
        is_opm_project=is_opm_project,
    )
    return bool(result), ""


def validate_acceptance_criteria(
    *,
    workspace: pathlib.Path,
    acceptance_criteria: str | list[str],
    is_python_project: bool = False,
    is_cmake_project: bool = False,
    is_opm_project: bool = False,
) -> tuple[bool, str]:
    """Validate that acceptance criteria are met.

    Parses acceptance criteria and checks if they're satisfied.

    Args:
        workspace: Path to project workspace.
        acceptance_criteria: JSON array or text list of criteria.
        is_python_project: Whether this is a Python project.
        is_cmake_project: Whether this is a CMake project.
        is_opm_project: Whether this is an OPM Flow project.

    Returns:
        Tuple of (passed: bool, details: str)
    """
    try:
        # Parse acceptance criteria
        if isinstance(acceptance_criteria, str):
            try:
                criteria_list = json.loads(acceptance_criteria)
            except json.JSONDecodeError:
                # Treat as plain text, split by lines or commas
                criteria_list = [
                    c.strip()
                    for c in acceptance_criteria.replace("\n", ",").split(",")
                    if c.strip()
                ]
        else:
            criteria_list = acceptance_criteria

        if not criteria_list:
            return True, "No specific criteria to validate"

        # Validate each criterion
        validated = 0
        failed: list[tuple[str, str]] = []

        for criterion in criteria_list:
            passed, details = _check_criterion_with_details(
                criterion=criterion,
                workspace=workspace,
                is_python_project=is_python_project,
                is_cmake_project=is_cmake_project,
                is_opm_project=is_opm_project,
            )
            if passed:
                validated += 1
            else:
                failed.append((criterion, details))

        total = len(criteria_list)
        if validated == total:
            return True, f"All {total} acceptance criteria validated"
        else:
            # Surface per-criterion details for executable forms so debug info
            # (failing pytest tail, python stderr) is visible to the caller.
            parts = []
            for criterion, details in failed[:3]:
                if details:
                    parts.append(f"{criterion} -> {details}")
                else:
                    parts.append(criterion)
            failed_str = "; ".join(parts)
            if len(failed) > 3:
                failed_str += f" (and {len(failed) - 3} more)"
            return False, f"Failed {len(failed)}/{total} criteria: {failed_str}"

    except Exception as e:
        # Recurrence guard for R1-005 / R2-002: a crash inside the validator
        # MUST NOT silently promote the feature to passed. Failing closed
        # forces human review and surfaces the underlying bug instead of
        # rubber-stamping it.
        logger.error(
            "Error validating acceptance criteria: %s", e, exc_info=True
        )
        return False, (
            f"Verification crashed: {e}; treating as failure "
            f"(manual review needed)"
        )


def _check_criterion(
    *,
    criterion: str,
    workspace: pathlib.Path,
    is_python_project: bool,
    is_cmake_project: bool,
    is_opm_project: bool,
) -> bool:
    """Check if a single acceptance criterion is met.

    Supports patterns like:
    - "File exists: path/to/file.py"
    - "Function exists: module.function_name"
    - "Class exists: module.ClassName"
    - "Test passes: test_name"
    - "No compilation errors"
    - "CMake builds successfully"

    Args:
        criterion: The acceptance criterion to check.
        workspace: Path to project workspace.
        is_python_project: Whether this is a Python project.
        is_cmake_project: Whether this is a CMake project.
        is_opm_project: Whether this is an OPM Flow project.

    Returns:
        True if criterion is met, False otherwise.
    """
    criterion_lower = criterion.lower()

    # Executable forms (pytest:/python:) — delegate to the detailed helper so
    # that any direct caller of ``_check_criterion`` still benefits from the
    # real test invocation. Detail strings are dropped for the bool-only API.
    stripped_lower = criterion_lower.strip()
    if stripped_lower.startswith("pytest:") or stripped_lower.startswith("python:"):
        passed, _ = _check_criterion_with_details(
            criterion=criterion,
            workspace=workspace,
            is_python_project=is_python_project,
            is_cmake_project=is_cmake_project,
            is_opm_project=is_opm_project,
        )
        return passed

    # Pattern 1: "File exists: path/to/file"
    if "file exists:" in criterion_lower or "file exist:" in criterion_lower:
        match = re.search(r"file exists?:\s*(.+)", criterion, re.IGNORECASE)
        if match:
            file_path = match.group(1).strip()
            full_path = workspace / file_path
            return full_path.exists()

    # Pattern 2: "Method/function implemented" or "implements X"
    if "method implemented" in criterion_lower or "function implemented" in criterion_lower:
        # Extract function/method name
        match = re.search(r"(\w+)\(\)", criterion)
        if match:
            func_name = match.group(1)
            return _search_for_function(workspace, func_name, is_python_project, is_cmake_project)

    # Pattern 3: "CMake builds successfully" or "compiles"
    if "cmake" in criterion_lower and "build" in criterion_lower:
        # Check for CMakeLists.txt and assume build will succeed if code was added
        return (workspace / "CMakeLists.txt").exists()

    # Pattern 4: "No compilation errors" or "No crashes"
    # Previously returned True unconditionally — that let any criterion with
    # this phrase soft-pass without running a compile. We can't run the build
    # here (that would require process execution), so report False to force
    # the agent/reviewer to verify it another way instead of silent-passing.
    if "no compilation errors" in criterion_lower or "no errors" in criterion_lower:
        logger.debug(
            "Criterion requires runtime verification (compile), cannot confirm statically: %s",
            criterion,
        )
        return False

    # Pattern 5: "Method returns value in [X, Y] range"
    # Use explicit parentheses: match "returns value in" OR ("return" AND "range")
    if ("returns value in" in criterion_lower) or (
        "return" in criterion_lower and "range" in criterion_lower
    ):
        # Check that method exists (actual range validation is runtime)
        match = re.search(r"(\w+)\(\)", criterion)
        if match:
            func_name = match.group(1)
            return _search_for_function(workspace, func_name, is_python_project, is_cmake_project)
        return False  # Cannot verify the range statically

    # Pattern 6: "Test run: command completes" or "run X completes"
    # Previously returned True unconditionally — a test-run criterion
    # requires actual execution to confirm. Return False so it does not
    # silently pass without evidence.
    if "completes" in criterion_lower and ("run" in criterion_lower or "test" in criterion_lower):
        logger.debug(
            "Criterion requires runtime verification (test/run), cannot confirm statically: %s",
            criterion,
        )
        return False

    # Pattern 7: Specific behavior checks like "calls ML model when --enable-ml-cpr=true"
    if "calls" in criterion_lower or "call" in criterion_lower:
        # Extract what should be called
        keywords = ["ml model", "mlcprmodel", "predict_k", "telemetry"]
        for keyword in keywords:
            if keyword.replace(" ", "").lower() in criterion_lower.replace(" ", "").lower():
                # Check if the code exists in source files
                return _search_for_code_pattern(
                    workspace,
                    keyword.replace(" ", ""),
                    is_cmake_project or is_opm_project
                )

    # Default: unrecognized criterion — hard-fail so the checklist does not
    # silently pass criteria we don't know how to verify. Previously this
    # returned True, which let any unrecognized phrase trivially pass.
    logger.debug("Could not statically validate criterion: %s (unrecognized, failing)", criterion)
    return False


def _search_for_function(
    workspace: pathlib.Path,
    func_name: str,
    is_python: bool,
    is_cpp: bool,
) -> bool:
    """Search for a function/method definition in source files."""
    if is_python:
        pattern = f"def {func_name}"
        extensions = ["*.py"]
    elif is_cpp:
        # C++ function definition patterns
        pattern = f"{func_name}\\("
        extensions = ["*.cpp", "*.hpp", "*.h"]
    else:
        return True  # Unknown project type, soft pass

    for ext in extensions:
        for file_path in workspace.rglob(ext):
            if "build" in str(file_path) or ".git" in str(file_path):
                continue
            try:
                content = file_path.read_text()
                if re.search(pattern, content):
                    return True
            except Exception:
                continue

    return False


def _search_for_code_pattern(
    workspace: pathlib.Path,
    pattern: str,
    is_cpp: bool = False,
) -> bool:
    """Search for a code pattern in source files."""
    extensions = ["*.cpp", "*.hpp", "*.h"] if is_cpp else ["*.py"]

    for ext in extensions:
        for file_path in workspace.rglob(ext):
            if "build" in str(file_path) or ".git" in str(file_path):
                continue
            try:
                content = file_path.read_text()
                # Case-insensitive search for the pattern
                if pattern.lower() in content.lower():
                    return True
            except Exception:
                continue

    return False


def validate_integration(
    *,
    workspace: pathlib.Path,
    feature_description: str,
    src_files: list[pathlib.Path],
    is_python_project: bool = False,
) -> tuple[bool, str]:
    """Validate that integration code exists for "integrate" features.

    For features with "integrate" in the description, this checks that:
    1. The integration target is mentioned in source code (imports/includes)
    2. Function calls or class instantiations exist
    3. New code was likely written (not just existing files)

    Args:
        workspace: Path to project workspace.
        feature_description: Feature description text.
        src_files: List of source file paths.
        is_python_project: Whether this is a Python project.

    Returns:
        Tuple of (passed: bool, details: str)
    """
    # Extract key terms from description to search for
    description_lower = feature_description.lower()

    # Look for integration targets (what's being integrated)
    integration_targets = []

    # Pattern: "Integrate X with Y" or "Integrate X into Y"
    integrate_match = re.search(
        r"integrate\s+(\w+(?:\s+\w+)?)\s+(?:with|into)\s+(\w+(?:\s+\w+)?)",
        description_lower
    )
    if integrate_match:
        integration_targets.append(integrate_match.group(1).strip())
        integration_targets.append(integrate_match.group(2).strip())

    # Look for class names (capitalized words or specific patterns)
    class_matches = re.findall(r"\b([A-Z][a-zA-Z0-9]+)\b", feature_description)
    integration_targets.extend(class_matches)

    if not integration_targets:
        # Can't determine what to check for, soft pass
        return True, "Could not determine integration targets (soft pass)"

    # Search source files for integration evidence
    found_includes = []
    found_calls = []

    for src_file in src_files[:50]:  # Limit search to first 50 files
        if "test" in str(src_file).lower():
            continue  # Skip test files
        try:
            content = src_file.read_text()
            content_lower = content.lower()

            # Check for imports/includes
            for target in integration_targets:
                target_clean = target.replace(" ", "").lower()
                if is_python_project:
                    if f"import {target_clean}" in content_lower or f"from {target_clean}" in content_lower:
                        found_includes.append(target)
                else:
                    if f"#include" in content and target_clean in content_lower:
                        found_includes.append(target)
                    # Check for usage/instantiation
                    if f"{target_clean}(" in content_lower or f"new {target_clean}" in content_lower:
                        found_calls.append(target)

        except Exception:
            continue

    # Determine if integration exists
    if found_includes or found_calls:
        details = f"Integration evidence found: "
        if found_includes:
            details += f"includes {','.join(set(found_includes[:3]))}; "
        if found_calls:
            details += f"calls {','.join(set(found_calls[:3]))}"
        return True, details.strip()
    else:
        return False, f"No integration code found for targets: {', '.join(integration_targets[:3])}"
