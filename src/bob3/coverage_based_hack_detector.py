"""Coverage-based hack detector for Bob3 (feature 8c495c04).

Rejects implementations whose passing tests cover less than a configurable
threshold (BOB3_MIN_COVERAGE, default 70%) of source lines. Uses coverage.py
data from the pytest run (JSON report format).

Public API
----------
- ``FileCoverageInfo``    — per-file coverage stats
- ``CoverageResult``      — aggregated result of a coverage check
- ``load_coverage_report(path)`` → dict | None
- ``check_coverage(report, threshold)`` → CoverageResult
- ``measure_coverage(workspace, threshold)`` → CoverageResult
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Environment variable name for configuring the minimum coverage threshold.
_ENV_VAR = "BOB3_MIN_COVERAGE"

# Default minimum line coverage percentage (inclusive lower bound).
DEFAULT_THRESHOLD = 70.0


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FileCoverageInfo:
    """Per-file line coverage statistics."""

    filename: str
    covered_lines: int
    total_lines: int

    @property
    def line_coverage_percent(self) -> float:
        if self.total_lines == 0:
            return 100.0
        return self.covered_lines / self.total_lines * 100.0


@dataclass
class CoverageResult:
    """Aggregated result of a coverage-based hack detection check.

    Attributes:
        is_flagged:       True when coverage falls below the threshold.
        coverage_percent: Overall line coverage percentage across all files.
        threshold:        The minimum coverage threshold that was applied.
        summary:          Human-readable description of the result.
        files:            Per-file breakdown (may be empty when unavailable).
    """

    is_flagged: bool
    coverage_percent: float
    threshold: float
    summary: str
    files: list[FileCoverageInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Coverage report loading
# ---------------------------------------------------------------------------


def load_coverage_report(path: Path) -> dict | None:
    """Load a coverage.py JSON report from *path*.

    Returns the parsed dict on success, or ``None`` when the file is missing
    or contains invalid JSON.
    """
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except FileNotFoundError:
        logger.debug("coverage_based_hack_detector: report not found at %s", path)
        return None
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("coverage_based_hack_detector: could not load %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Coverage analysis
# ---------------------------------------------------------------------------


def check_coverage(report: dict, *, threshold: float) -> CoverageResult:
    """Analyse a coverage.py JSON *report* dict and return a :class:`CoverageResult`.

    Args:
        report:    Parsed coverage.py JSON report (``--cov-report json`` format).
        threshold: Minimum acceptable line coverage percentage (0–100, inclusive).

    Returns:
        A :class:`CoverageResult` describing whether the implementation meets
        the coverage threshold.
    """
    files_data: dict = report.get("files", {})

    if not files_data:
        return CoverageResult(
            is_flagged=False,
            coverage_percent=100.0,
            threshold=threshold,
            summary="No source files in coverage report; nothing to check.",
            files=[],
        )

    file_infos: list[FileCoverageInfo] = []
    total_covered = 0
    total_lines = 0

    for filename, file_report in files_data.items():
        summary = file_report.get("summary", {})
        covered = int(summary.get("covered_lines", 0))
        num_statements = int(summary.get("num_statements", 0))
        file_infos.append(
            FileCoverageInfo(
                filename=filename,
                covered_lines=covered,
                total_lines=num_statements,
            )
        )
        total_covered += covered
        total_lines += num_statements

    if total_lines == 0:
        overall_pct = 100.0
    else:
        overall_pct = total_covered / total_lines * 100.0

    is_flagged = overall_pct < threshold

    if is_flagged:
        summary = (
            f"Coverage too low: {overall_pct:.1f}% < {threshold:.1f}% threshold. "
            f"({total_covered}/{total_lines} lines covered)"
        )
    else:
        summary = (
            f"Coverage OK: {overall_pct:.1f}% >= {threshold:.1f}% threshold. "
            f"({total_covered}/{total_lines} lines covered)"
        )

    return CoverageResult(
        is_flagged=is_flagged,
        coverage_percent=overall_pct,
        threshold=threshold,
        summary=summary,
        files=file_infos,
    )


# ---------------------------------------------------------------------------
# Live measurement via pytest-cov
# ---------------------------------------------------------------------------


def _resolve_threshold(threshold: float | None) -> float:
    """Return the effective threshold, reading BOB3_MIN_COVERAGE from env if needed."""
    if threshold is not None:
        return threshold
    raw = os.environ.get(_ENV_VAR)
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            logger.warning(
                "coverage_based_hack_detector: invalid %s=%r; using default %.1f",
                _ENV_VAR,
                raw,
                DEFAULT_THRESHOLD,
            )
    return DEFAULT_THRESHOLD


def measure_coverage(
    *,
    workspace: Path,
    threshold: float | None = None,
) -> CoverageResult:
    """Run pytest with coverage in *workspace* and check against *threshold*.

    Launches ``python -m pytest --cov=src --cov-report=json:<tmpfile>`` in a
    subprocess, reads the resulting JSON report, and delegates to
    :func:`check_coverage`.

    When no ``tests/`` directory exists under *workspace*, returns a clean
    result without running pytest (nothing to measure).

    The threshold defaults to the value of the ``BOB3_MIN_COVERAGE`` environment
    variable, or :data:`DEFAULT_THRESHOLD` (70.0) if the variable is unset.

    Args:
        workspace: Root of the project to measure.
        threshold: Override threshold; ``None`` reads from env / default.

    Returns:
        A :class:`CoverageResult` describing whether the implementation meets
        the threshold.
    """
    effective_threshold = _resolve_threshold(threshold)

    tests_dir = workspace / "tests"
    if not tests_dir.exists():
        return CoverageResult(
            is_flagged=False,
            coverage_percent=100.0,
            threshold=effective_threshold,
            summary="No tests/ directory found; coverage check skipped.",
            files=[],
        )

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_path = Path(tmp.name)

    try:
        cmd = [
            "python",
            "-m",
            "pytest",
            "--cov=src",
            f"--cov-report=json:{report_path}",
            "--tb=no",
            "-q",
            str(tests_dir),
        ]
        logger.debug("coverage_based_hack_detector: running %s in %s", cmd, workspace)

        subprocess.run(
            cmd,
            cwd=str(workspace),
            capture_output=True,
            check=False,
        )

        report = load_coverage_report(report_path)
        if report is None:
            return CoverageResult(
                is_flagged=False,
                coverage_percent=0.0,
                threshold=effective_threshold,
                summary="Coverage report could not be generated; check skipped.",
                files=[],
            )

        return check_coverage(report, threshold=effective_threshold)
    finally:
        try:
            report_path.unlink(missing_ok=True)
        except OSError:
            pass
