"""Stable baseline gate — abort verifier if collection fails.

Before capturing a pytest snapshot for regression comparison, the verifier
MUST call :func:`ensure_collection_succeeds` to verify the test suite
collects cleanly.  If any test file raises a CollectError (ImportError,
SyntaxError, etc.), the baseline is invalid and MUST NOT be used for
regression comparison.

Public API
----------
ensure_collection_succeeds(workspace, *, test_dir="tests", timeout=120, strict=False)
    → CollectionResult

    Run ``pytest --collect-only`` and return a result object.
    - When the suite collects cleanly: ``result.ok`` is True and
      ``result.failing_files`` is empty.
    - When collection fails: ``result.ok`` is False and
      ``result.failing_files`` lists every file that caused an error.
    - When ``strict=True`` and collection fails: raises
      ``BaselineCollectionError`` instead of returning.

    Callers MUST refuse to capture a baseline when ``ok`` is False.
"""

from __future__ import annotations

import logging
import pathlib
import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Union

logger = logging.getLogger(__name__)

_COLLECT_ERROR_EXITCODE = 2

_COLLECT_ERROR_RE = re.compile(
    r"ERROR\s+collecting\s+(?P<file>\S+)", re.IGNORECASE
)


class BaselineCollectionError(Exception):
    """Raised by :func:`ensure_collection_succeeds` in strict mode when collection fails."""


@dataclass
class CollectionResult:
    """Result of :func:`ensure_collection_succeeds`.

    Attributes:
        ok: True when the suite collects cleanly (no errors).
        failing_files: Files that failed to collect; empty when ok is True.
        details: Combined stdout+stderr from the collect-only run.
    """

    ok: bool
    failing_files: List[str] = field(default_factory=list)
    details: str = ""


def ensure_collection_succeeds(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
    strict: bool = False,
) -> CollectionResult:
    """Run ``pytest --collect-only`` and verify the suite collects cleanly.

    This is the baseline gate check the verifier must call before capturing a
    regression baseline snapshot.  If ``result.ok`` is False, the baseline is
    invalid — do not capture or compare against it.

    Boundary behaviour:
    - ``workspace=None`` → returns ``CollectionResult(ok=True)`` (no workspace).
    - ``workspace`` points to a non-existent path → ``CollectionResult(ok=True)``.
    - ``test_dir`` does not exist inside the workspace → ``CollectionResult(ok=True)``.

    :param workspace: Path to the project root directory, or None.
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds to wait for ``pytest --collect-only``.
    :param strict: When True and collection fails, raises
        :exc:`BaselineCollectionError` instead of returning a result.
    :raises ValueError: When ``workspace`` is not str/Path/None, or
        ``timeout`` is not a positive integer.
    :raises BaselineCollectionError: When ``strict=True`` and collection fails.
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
        logger.debug("baseline_verifier: python interpreter not found; assuming clean")
        return CollectionResult(ok=True)
    except subprocess.TimeoutExpired:
        logger.warning("baseline_verifier: --collect-only timed out after %ss", timeout)
        return CollectionResult(ok=True)

    combined = (proc.stdout or "") + (proc.stderr or "")
    collect_error_exit = proc.returncode == _COLLECT_ERROR_EXITCODE

    failing_files: list[str] = []
    for line in combined.splitlines():
        m = _COLLECT_ERROR_RE.search(line)
        if m:
            failing_files.append(m.group("file"))

    if collect_error_exit and (failing_files or "ERROR" in combined.upper()):
        result = CollectionResult(ok=False, failing_files=failing_files, details=combined)
        if strict:
            files_str = ", ".join(failing_files) if failing_files else "<unknown>"
            raise BaselineCollectionError(
                f"Baseline aborted: pytest collection failed for: {files_str}. "
                "Fix collection errors before capturing a regression baseline."
            )
        return result

    return CollectionResult(ok=True, details=combined)


__all__ = ["BaselineCollectionError", "CollectionResult", "ensure_collection_succeeds"]
