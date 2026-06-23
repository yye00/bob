"""Bob3 review-findings registry.

Persistent, version-controlled record of every adversarial-review finding.
Lets review agents check whether a bug or anti-pattern they're about to
report has already been seen before — and surfaces recurring patterns
across the codebase.

Backing store: ``reviews/findings.yaml`` at the repository root.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _registry_path() -> Path:
    """Locate the findings.yaml file by walking up from this module."""
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        candidate = parent / "reviews" / "findings.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Could not locate reviews/findings.yaml")


@dataclass
class Finding:
    """One review finding."""

    id: str
    title: str
    pattern: str
    files: list[str]
    severity: str
    status: str
    tags: list[str] = field(default_factory=list)
    fixed_in: str | None = None
    fixed_at: str | None = None
    related: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def round(self) -> str:
        """Return the round prefix from the id (e.g. 'R2' from 'R2-005')."""
        match = re.match(r"^(R\d+)-", self.id)
        return match.group(1) if match else "R?"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "pattern": self.pattern,
            "files": list(self.files),
            "severity": self.severity,
            "status": self.status,
        }
        if self.tags:
            out["tags"] = list(self.tags)
        if self.fixed_in:
            out["fixed_in"] = self.fixed_in
        if self.fixed_at:
            out["fixed_at"] = self.fixed_at
        if self.related:
            out["related"] = list(self.related)
        if self.notes:
            out["notes"] = self.notes
        return out


@dataclass
class RecurringPattern:
    tag: str
    occurrences: list[str]
    summary: str


@dataclass
class Registry:
    findings: list[Finding]
    recurring_patterns: list[RecurringPattern]
    schema_version: int = 1

    def by_id(self, finding_id: str) -> Finding | None:
        for f in self.findings:
            if f.id == finding_id:
                return f
        return None

    def search(
        self,
        query: str | None = None,
        *,
        status: str | None = None,
        severity: str | None = None,
        tag: str | None = None,
        files_glob: str | None = None,
        limit: int = 20,
    ) -> list[Finding]:
        """Filter findings.

        Args:
            query: Substring matched (case-insensitive) against title,
                pattern, and notes.
            status: Filter to one status (open, in_progress, fixed, etc.).
            severity: Filter to one severity (critical/high/medium/low).
            tag: Require this tag.
            files_glob: Substring (not glob) matched against any file path.
            limit: Max results.
        """
        results: list[Finding] = []
        q = (query or "").lower()
        for f in self.findings:
            if status and f.status != status:
                continue
            if severity and f.severity != severity:
                continue
            if tag and tag not in f.tags:
                continue
            if files_glob and not any(files_glob in path for path in f.files):
                continue
            if q:
                hay = " ".join([f.title, f.pattern, f.notes]).lower()
                if q not in hay:
                    continue
            results.append(f)
            if len(results) >= limit:
                break
        return results

    def patterns_for_tag(self, tag: str) -> RecurringPattern | None:
        for p in self.recurring_patterns:
            if p.tag == tag:
                return p
        return None

    def recurring_tags(self) -> list[str]:
        return [p.tag for p in self.recurring_patterns]


def load_registry(path: Path | str | None = None) -> Registry:
    """Load the findings registry from disk."""
    p = Path(path) if path else _registry_path()
    with open(p) as fh:
        data = yaml.safe_load(fh) or {}

    findings_raw = data.get("findings") or []
    findings = [
        Finding(
            id=item["id"],
            title=item["title"],
            pattern=item.get("pattern", ""),
            files=list(item.get("files") or []),
            severity=item.get("severity", "medium"),
            status=item.get("status", "open"),
            tags=list(item.get("tags") or []),
            fixed_in=item.get("fixed_in"),
            fixed_at=item.get("fixed_at"),
            related=list(item.get("related") or []),
            notes=item.get("notes", ""),
        )
        for item in findings_raw
    ]

    patterns_raw = data.get("recurring_patterns") or []
    patterns = [
        RecurringPattern(
            tag=item["tag"],
            occurrences=list(item.get("occurrences") or []),
            summary=item.get("summary", ""),
        )
        for item in patterns_raw
    ]

    return Registry(
        findings=findings,
        recurring_patterns=patterns,
        schema_version=int(data.get("schema_version", 1)),
    )


def save_registry(registry: Registry, path: Path | str | None = None) -> None:
    """Write the registry back to disk in a stable order."""
    p = Path(path) if path else _registry_path()
    data = {
        "schema_version": registry.schema_version,
        "findings": [f.to_dict() for f in registry.findings],
        "recurring_patterns": [
            {"tag": rp.tag, "occurrences": rp.occurrences, "summary": rp.summary}
            for rp in registry.recurring_patterns
        ],
    }
    with open(p, "w") as fh:
        yaml.safe_dump(
            data, fh, sort_keys=False, indent=2, allow_unicode=True, width=88
        )


def next_finding_id(registry: Registry, round_prefix: str) -> str:
    """Return the next sequential ID in a given round (e.g. 'R4-001')."""
    pattern = re.compile(rf"^{re.escape(round_prefix)}-(\d+)$")
    max_seq = 0
    for f in registry.findings:
        m = pattern.match(f.id)
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    return f"{round_prefix}-{max_seq + 1:03d}"


def add_finding(
    registry: Registry,
    *,
    round_prefix: str,
    title: str,
    pattern: str,
    files: list[str],
    severity: str,
    status: str = "open",
    tags: list[str] | None = None,
    related: list[str] | None = None,
    notes: str = "",
) -> Finding:
    """Append a new finding to the registry. Caller must save_registry()."""
    finding = Finding(
        id=next_finding_id(registry, round_prefix),
        title=title,
        pattern=pattern,
        files=list(files),
        severity=severity,
        status=status,
        tags=list(tags or []),
        related=list(related or []),
        notes=notes,
    )
    registry.findings.append(finding)
    return finding


def mark_fixed(
    registry: Registry,
    finding_id: str,
    *,
    commit: str,
    fixed_at: str | None = None,
) -> bool:
    """Mark a finding as fixed in a given commit."""
    finding = registry.by_id(finding_id)
    if finding is None:
        return False
    finding.status = "fixed"
    finding.fixed_in = commit
    finding.fixed_at = fixed_at or date.today().isoformat()
    return True


def summarize_status(registry: Registry) -> dict[str, int]:
    """Counts of findings by status."""
    counts: dict[str, int] = {}
    for f in registry.findings:
        counts[f.status] = counts.get(f.status, 0) + 1
    return counts


def summarize_severity(registry: Registry) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in registry.findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts


def render_summary(registry: Registry) -> str:
    """Human-readable text summary of the registry."""
    lines: list[str] = []
    status = summarize_status(registry)
    severity = summarize_severity(registry)
    lines.append(f"Total findings: {len(registry.findings)}")
    lines.append(
        "Status: " + ", ".join(f"{k}={v}" for k, v in sorted(status.items()))
    )
    lines.append(
        "Severity: " + ", ".join(f"{k}={v}" for k, v in sorted(severity.items()))
    )
    if registry.recurring_patterns:
        lines.append("")
        lines.append("Recurring patterns:")
        for rp in registry.recurring_patterns:
            lines.append(f"  - {rp.tag} (×{len(rp.occurrences)}): {rp.occurrences}")
    return "\n".join(lines)
