"""R4: Security agent — identifies security risks and hardening opportunities."""

from __future__ import annotations

import pathlib
import re

from bob.research.proposal import Proposal


_HARDCODED_SECRET_PATTERN = re.compile(
    r'(api_key|secret|password|token)\s*=\s*["\'][^"\']{8,}["\']',
    re.IGNORECASE,
)
_SHELL_INJECTION_PATTERN = re.compile(r"\bos\.system\b|\bsubprocess\.call\(.*shell\s*=\s*True")
_SQL_FORMAT_PATTERN = re.compile(r'execute\(["\'].*%s.*["\'].*%')


def run(round_num: int) -> list[Proposal]:
    """Return proposals for security hardening."""
    proposals: list[Proposal] = []

    src_root = pathlib.Path("src")
    if not src_root.exists():
        return proposals

    hardcoded_files: list[str] = []
    shell_injection_files: list[str] = []
    sql_format_files: list[str] = []

    for py_file in src_root.rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _HARDCODED_SECRET_PATTERN.search(text):
            hardcoded_files.append(str(py_file))
        if _SHELL_INJECTION_PATTERN.search(text):
            shell_injection_files.append(str(py_file))
        if _SQL_FORMAT_PATTERN.search(text):
            sql_format_files.append(str(py_file))

    if hardcoded_files:
        proposals.append(
            Proposal(
                domain="security",
                title="Remove hardcoded secrets from source",
                rationale="Hardcoded credentials in source code can be leaked via version control.",
                acceptance_criteria=[
                    "No hardcoded api_key/secret/password/token literals in src/",
                    "Secrets sourced from environment variables or a secrets manager",
                ],
                estimated_effort="small",
                estimated_impact="high",
                evidence=[f"Potential hardcoded secrets in: {', '.join(hardcoded_files[:3])}"],
            )
        )

    if shell_injection_files:
        proposals.append(
            Proposal(
                domain="security",
                title="Replace shell=True subprocess calls",
                rationale="shell=True subprocess calls are vulnerable to command injection.",
                acceptance_criteria=["No subprocess calls with shell=True in src/"],
                estimated_effort="small",
                estimated_impact="high",
                evidence=[f"Found shell=True in: {', '.join(shell_injection_files[:3])}"],
            )
        )

    gitignore = pathlib.Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8", errors="replace")
        if ".env" not in content:
            proposals.append(
                Proposal(
                    domain="security",
                    title="Add .env to .gitignore",
                    rationale=".env files containing secrets should never be committed.",
                    acceptance_criteria=[".gitignore contains .env entry"],
                    estimated_effort="trivial",
                    estimated_impact="medium",
                    evidence=[".env not found in .gitignore"],
                )
            )

    return proposals
