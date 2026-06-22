"""Embedded reproducer per registry finding.

Each registry finding (bug, security issue, hack verdict) can store a
minimal failing case: the smallest diff that reproduces the finding, plus
the fix diff. This enables test-driven regression prevention in future
spawns by giving a concrete, runnable repro alongside every finding.

Public API
----------
Reproducer            — dataclass holding failing_diff, fix_diff, description,
                        test_command
attach_reproducer(finding, reproducer) -> None
    Validate and attach a Reproducer to a Finding. Sets finding.reproducer
    and monkey-patches to_dict() so the reproducer is serialised.
get_reproducer(finding) -> Reproducer | None
    Return the attached Reproducer, or None.
list_reproducers(findings) -> list[tuple[Finding, Reproducer]]
    Filter to findings that have an attached Reproducer.
validate_reproducer(reproducer) -> None
    Raise ReproducerValidationError if the reproducer is invalid.
ReproducerValidationError — ValueError subclass for validation failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bob3.reviews import Finding


class ReproducerValidationError(ValueError):
    """Raised when a Reproducer fails validation."""


@dataclass
class Reproducer:
    """Minimal failing case attached to a registry finding.

    Attributes:
        failing_diff: Unified diff that introduces the defect (the
            smallest change that makes the bug reproducible).
        fix_diff: Unified diff that fixes the defect.
        description: Human-readable explanation of what the reproducer
            demonstrates and why the defect occurs.
        test_command: Shell command (e.g. a pytest invocation) that
            demonstrates the failure when the failing_diff is applied.
    """

    failing_diff: str
    fix_diff: str
    description: str = field(default="")
    test_command: str = field(default="")

    def to_dict(self) -> dict[str, Any]:
        return {
            "failing_diff": self.failing_diff,
            "fix_diff": self.fix_diff,
            "description": self.description,
            "test_command": self.test_command,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reproducer":
        return cls(
            failing_diff=data["failing_diff"],
            fix_diff=data["fix_diff"],
            description=data.get("description", ""),
            test_command=data.get("test_command", ""),
        )


def validate_reproducer(reproducer: Reproducer) -> None:
    """Raise ReproducerValidationError if the reproducer is not usable.

    Rules:
    - failing_diff must be non-empty and look like a unified diff (starts
      with '---').
    - fix_diff must be non-empty.
    """
    if not reproducer.failing_diff:
        raise ReproducerValidationError(
            "failing_diff must not be empty"
        )
    if not reproducer.fix_diff:
        raise ReproducerValidationError(
            "fix_diff must not be empty"
        )
    if not reproducer.failing_diff.lstrip().startswith("---"):
        raise ReproducerValidationError(
            "failing_diff does not look like a unified diff (expected to start with '---')"
        )


def attach_reproducer(finding: Finding, reproducer: Reproducer) -> None:
    """Validate and attach a Reproducer to a Finding.

    After calling this:
    - finding.reproducer → the Reproducer instance
    - finding.to_dict() includes a 'reproducer' key

    Raises:
        ReproducerValidationError: if the reproducer fails validation.
    """
    validate_reproducer(reproducer)
    finding.reproducer = reproducer  # type: ignore[attr-defined]

    # Patch to_dict so the reproducer is included in YAML serialisation.
    original_to_dict = finding.__class__.to_dict

    def _patched_to_dict(self: Finding) -> dict[str, Any]:
        out = original_to_dict(self)
        r: Reproducer | None = getattr(self, "reproducer", None)
        if r is not None:
            out["reproducer"] = r.to_dict()
        return out

    # Only patch the class once; guard against re-entrant patching.
    if not getattr(finding.__class__, "_reproducer_patch_applied", False):
        finding.__class__.to_dict = _patched_to_dict  # type: ignore[method-assign]
        finding.__class__._reproducer_patch_applied = True  # type: ignore[attr-defined]


def get_reproducer(finding: Finding) -> Reproducer | None:
    """Return the Reproducer attached to this finding, or None."""
    return getattr(finding, "reproducer", None)


def list_reproducers(
    findings: list[Finding],
) -> list[tuple[Finding, Reproducer]]:
    """Return (finding, reproducer) pairs for every finding that has one."""
    result: list[tuple[Finding, Reproducer]] = []
    for f in findings:
        r = get_reproducer(f)
        if r is not None:
            result.append((f, r))
    return result
