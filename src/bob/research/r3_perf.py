"""R3: Performance agent — identifies performance bottlenecks and improvement opportunities."""

from __future__ import annotations

import pathlib
import re

from bob.research.proposal import Proposal


_SYNC_DB_PATTERN = re.compile(r"\bsqlite3\.connect\b")
_BLOCKING_SLEEP_PATTERN = re.compile(r"\btime\.sleep\b")
_LARGE_READ_PATTERN = re.compile(r"\.read\(\)")


def run(round_num: int) -> list[Proposal]:
    """Return proposals for performance improvements."""
    proposals: list[Proposal] = []

    src_root = pathlib.Path("src")
    if not src_root.exists():
        return proposals

    py_files = list(src_root.rglob("*.py"))

    sync_db_files: list[str] = []
    blocking_sleep_files: list[str] = []
    large_read_files: list[str] = []

    for py_file in py_files:
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _SYNC_DB_PATTERN.search(text):
            sync_db_files.append(str(py_file))
        if _BLOCKING_SLEEP_PATTERN.search(text):
            blocking_sleep_files.append(str(py_file))
        if _LARGE_READ_PATTERN.search(text):
            large_read_files.append(str(py_file))

    if blocking_sleep_files:
        proposals.append(
            Proposal(
                domain="performance",
                title="Replace blocking time.sleep() with asyncio.sleep()",
                rationale="Blocking sleeps in async code stall the event loop and reduce throughput.",
                acceptance_criteria=["No time.sleep() calls in async functions in src/"],
                estimated_effort="small",
                estimated_impact="medium",
                evidence=[f"Found time.sleep() in: {', '.join(blocking_sleep_files[:3])}"],
            )
        )

    if len(py_files) > 50:
        proposals.append(
            Proposal(
                domain="performance",
                title="Profile and cache hot import paths",
                rationale=f"Large codebase ({len(py_files)} source files) risks slow startup from redundant imports.",
                acceptance_criteria=["CLI startup time < 500ms measured via time bob --help"],
                estimated_effort="medium",
                estimated_impact="medium",
                evidence=[f"{len(py_files)} .py files found in src/"],
            )
        )

    return proposals
