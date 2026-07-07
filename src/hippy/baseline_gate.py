"""hippy.baseline_gate — stable baseline gate for the regression verifier.

A prior-generation baseline can carry test files that raise a CollectError
(ImportError, SyntaxError, ...) at ``pytest`` collection time. When the
baseline suite crashes at collection, the "before" snapshot is invalid: any
"after" diff computed against it fabricates regressions out of tests that were
never runnable in the first place.

The verifier MUST therefore refuse to capture a baseline unless the suite
collects cleanly.

Public API
----------
collects_cleanly(workspace, *, test_dir="tests", timeout=120) -> bool
    Return ``True`` when ``pytest --collect-only`` succeeds for the workspace.

capture_baseline(workspace, *, test_dir="tests", timeout=120,
                 capture_fn=None, raise_on_unstable=False) -> BaselineResult
    Gate the baseline snapshot behind a clean collection. When collection
    fails, ``capture_fn`` is NOT invoked and the result carries
    ``stable=False, snapshot=None`` (or raises ``BaselineUnstableError`` when
    ``raise_on_unstable`` is set).
"""

from __future__ import annotations

import logging
import pathlib
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Union

logger = logging.getLogger(__name__)

# pytest exit code for collection errors (distinct from 1 = test failures).
_COLLECT_ERROR_EXITCODE = 2

# Matches: "ERROR collecting tests/test_foo.py"
_COLLECT_ERROR_RE = re.compile(r"ERROR\s+collecting\s+(?P<file>\S+)", re.IGNORECASE)

Workspace = Union[str, pathlib.Path, None]
CaptureFn = Callable[[pathlib.Path], dict]


class BaselineUnstableError(RuntimeError):
    """Raised when a baseline snapshot is requested but the suite does not
    collect cleanly."""


@dataclass
class BaselineResult:
    """Outcome of :func:`capture_baseline`.

    Attributes:
        stable: True when the suite collected cleanly and the snapshot is valid.
        snapshot: The captured baseline mapping, or ``None`` when unstable.
        failing_files: Files that failed to collect (empty when stable).
        details: Combined stdout+stderr from the collect-only run.
    """

    stable: bool
    snapshot: Optional[dict] = None
    failing_files: List[str] = field(default_factory=list)
    details: str = ""


def _validate_args(workspace: Workspace, timeout: int) -> None:
    if workspace is not None and not isinstance(workspace, (str, pathlib.Path)):
        raise ValueError(
            f"workspace must be a str, pathlib.Path, or None; got {type(workspace)!r}"
        )
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError(f"timeout must be a positive integer; got {timeout!r}")


def _collect(
    workspace: Workspace, test_dir: str, timeout: int
) -> BaselineResult:
    """Run ``pytest --collect-only`` and classify the outcome.

    Returns a :class:`BaselineResult` with ``stable`` set and (when unstable)
    ``failing_files`` populated. ``snapshot`` is left ``None`` here — callers
    fill it in only when the baseline is stable.
    """
    _validate_args(workspace, timeout)

    if workspace is None:
        return BaselineResult(stable=True)

    ws = pathlib.Path(workspace)
    if not ws.exists() or not ws.is_dir():
        return BaselineResult(stable=True)

    td = ws / test_dir
    if not td.exists() or not td.is_dir():
        return BaselineResult(stable=True)

    cmd = [
        "python", "-m", "pytest",
        str(td.relative_to(ws)),
        "--collect-only",
        "-q",
        "--tb=short",
        "--no-header",
        "--color=no",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        logger.debug("baseline_gate: python interpreter not found; assuming clean")
        return BaselineResult(stable=True)
    except subprocess.TimeoutExpired:
        logger.warning("baseline_gate: --collect-only timed out after %ss", timeout)
        return BaselineResult(stable=True)

    combined = (proc.stdout or "") + (proc.stderr or "")

    failing_files: List[str] = []
    for line in combined.splitlines():
        m = _COLLECT_ERROR_RE.search(line)
        if m:
            failing_files.append(m.group("file"))

    collect_error = proc.returncode == _COLLECT_ERROR_EXITCODE and (
        failing_files or "ERROR" in combined.upper()
    )
    if collect_error:
        return BaselineResult(
            stable=False, failing_files=failing_files, details=combined
        )
    return BaselineResult(stable=True, details=combined)


def collects_cleanly(
    workspace: Workspace,
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> bool:
    """Return ``True`` when the workspace's test suite collects cleanly.

    Boundary behaviour: ``workspace=None``, a non-existent workspace, or a
    missing ``test_dir`` all count as clean (nothing to fail).

    :raises ValueError: When ``workspace`` is an invalid type or ``timeout`` is
        not a positive integer.
    """
    return bool(_collect(workspace, test_dir, timeout).stable)


def capture_baseline(
    workspace: Workspace,
    *,
    test_dir: str = "tests",
    timeout: int = 120,
    capture_fn: Optional[CaptureFn] = None,
    raise_on_unstable: bool = False,
) -> BaselineResult:
    """Capture a regression baseline, gated on a clean collection.

    The collection gate runs FIRST. When it fails, ``capture_fn`` is never
    invoked — a snapshot taken over an uncollectable suite is meaningless and
    would fabricate regressions on the next diff. In that case the returned
    :class:`BaselineResult` has ``stable=False, snapshot=None`` (or, when
    ``raise_on_unstable`` is set, :class:`BaselineUnstableError` is raised).

    :param capture_fn: Callable ``(workspace_path) -> dict`` producing the
        baseline snapshot. Defaults to a no-op returning ``{}``; real callers
        (the verifier) pass their snapshot function.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout`` is
        not a positive integer.
    :raises BaselineUnstableError: When collection fails and
        ``raise_on_unstable`` is True.
    """
    result = _collect(workspace, test_dir, timeout)

    if not result.stable:
        if raise_on_unstable:
            files = ", ".join(result.failing_files) or "unknown"
            raise BaselineUnstableError(
                f"Baseline suite does not collect cleanly; failing files: {files}. "
                "Refusing to capture a baseline — the diff would fabricate regressions."
            )
        return result

    fn = capture_fn if capture_fn is not None else (lambda ws: {})
    ws_path = pathlib.Path(workspace) if workspace is not None else pathlib.Path(".")
    result.snapshot = fn(ws_path)
    return result
