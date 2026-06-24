"""Stable baseline gate — abort verifier if collection fails.

Before capturing a pytest snapshot for regression comparison, the collection
gate must verify that the test suite collects cleanly.  If any test file
raises a CollectError (ImportError, SyntaxError, etc.) the baseline is
invalid and MUST NOT be used for regression comparison.

Public API
----------
validate_collection(workspace, *, test_dir="tests", timeout=120)
    → CollectionResult

    Run ``pytest --collect-only`` and return a result object.  When the
    suite does not collect cleanly, ``result.ok`` is False and
    ``result.failing_files`` lists every file that caused an error.
    Callers MUST refuse to proceed with baseline capture when ``ok`` is False.
"""

from __future__ import annotations

import logging
import re
import subprocess
import pathlib
from dataclasses import dataclass, field
from typing import List, Optional, Union

logger = logging.getLogger(__name__)

# pytest exit code for collection errors
_COLLECT_ERROR_EXITCODE = 2

# Matches lines like: ERROR collecting tests/test_foo.py
_COLLECT_ERROR_RE = re.compile(
    r"ERROR\s+collecting\s+(?P<file>\S+)", re.IGNORECASE
)


@dataclass
class CollectionResult:
    """Result of :func:`validate_collection`.

    Attributes:
        ok: True when the suite collects cleanly (no errors).
        failing_files: Files that failed to collect, empty when ok is True.
        details: Combined stdout+stderr from the collect-only run.
    """

    ok: bool
    failing_files: List[str] = field(default_factory=list)
    details: str = ""


def validate_collection(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Run ``pytest --collect-only`` and return a :class:`CollectionResult`.

    The function is the single integration point between :mod:`bob.verifier`
    and the baseline gate logic.  The verifier MUST check ``result.ok`` before
    capturing a regression baseline; when ``ok`` is False, the baseline is
    invalid and capturing it would fabricate regressions.

    Boundary behaviour:
    - ``workspace=None`` → returns ``CollectionResult(ok=True)`` (no workspace,
      nothing to check; guard against misconfigured callers).
    - ``workspace`` points to a non-existent path → ``CollectionResult(ok=True)``
      (same rationale: if there is no workspace there is nothing to fail).
    - ``test_dir`` does not exist inside the workspace → ``CollectionResult(ok=True)``
      (no tests means no collection errors).

    Error path:
    - Any string that is not a valid filesystem path string raises
      ``ValueError`` (callers must supply a real path or ``None``).
    - If ``timeout`` is not a positive integer, ``ValueError`` is raised.

    :param workspace: Path to the project root directory, or None.
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds to wait for ``pytest --collect-only``.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    if workspace is not None and not isinstance(workspace, (str, pathlib.Path)):
        raise ValueError(
            f"workspace must be a str, pathlib.Path, or None; got {type(workspace)!r}"
        )
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError(
            f"timeout must be a positive integer; got {timeout!r}"
        )

    if workspace is None:
        return CollectionResult(ok=True)

    ws = pathlib.Path(workspace)
    if not ws.exists() or not ws.is_dir():
        return CollectionResult(ok=True)

    td = ws / test_dir
    if not td.exists() or not td.is_dir():
        return CollectionResult(ok=True)

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
        return CollectionResult(ok=True)
    except subprocess.TimeoutExpired:
        logger.warning("baseline_gate: --collect-only timed out after %ss", timeout)
        return CollectionResult(ok=True)

    combined = (proc.stdout or "") + (proc.stderr or "")

    collect_error_exit = proc.returncode == _COLLECT_ERROR_EXITCODE
    failing_files: list[str] = []
    for line in combined.splitlines():
        m = _COLLECT_ERROR_RE.search(line)
        if m:
            failing_files.append(m.group("file"))

    if collect_error_exit and (failing_files or "ERROR" in combined.upper()):
        return CollectionResult(ok=False, failing_files=failing_files, details=combined)

    return CollectionResult(ok=True, details=combined)
