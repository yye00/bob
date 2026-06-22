"""Adversarial spec-critic sub-agent — top-level bob3 module.

Thin wrapper around :mod:`bob3.spec_quality.spec_critic` that exposes a
``critique_spec`` entry point matching the bob3.spec_critic AC contract.

Public API::

    from bob3.spec_critic import critique_spec

    result = critique_spec(
        feature_id="abc123",
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py", "pytest: tests/test_foo_error.py"],
    )
    if not result["gate_passed"]:
        raise RuntimeError(f"Spec critic blocked codegen: {result['defects']}")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.orchestrator.plan_gate import emit_plan_ready_event as _emit_plan_ready_event
from bob3.spec_quality.spec_critic import (
    ConstitutionMissingError,
    SpecDefect,
    critique_feature,
    persist_findings,
)

__all__ = [
    "critique_spec",
    "run_spec_critic",
    "emit_plan_ready",
    "ConstitutionMissingError",
    "SpecDefect",
    "SpecCritic",
    "load_spec_constitution",
]

_CONSTITUTION_PATH = Path(__file__).parent / "spec_constitution.md"


def load_spec_constitution(path: Path | None = None) -> str:
    """Load and return the versioned spec_constitution.md text.

    Parameters
    ----------
    path:
        Explicit path to ``spec_constitution.md``.  When omitted the function
        searches: sibling ``spec_constitution.md`` → ``spec_quality/spec_constitution.md``.

    Returns
    -------
    str
        Raw text of the constitution document.

    Raises
    ------
    ConstitutionMissingError
        When no constitution file can be located.
    """
    resolved = path
    if resolved is None:
        if _CONSTITUTION_PATH.exists():
            resolved = _CONSTITUTION_PATH
        else:
            candidate = Path(__file__).parent / "spec_quality" / "spec_constitution.md"
            resolved = candidate

    if not resolved.exists():
        raise ConstitutionMissingError(
            f"spec_constitution.md not found at {resolved}; "
            "set SPEC_CONSTITUTION_PATH or pass constitution_path= explicitly"
        )
    return resolved.read_text(encoding="utf-8")


class SpecCritic:
    """Adversarial spec-critic sub-agent: gate codegen on spec quality.

    Loads a versioned ``spec_constitution.md`` and emits per-feature structured
    defects.  Findings persist to ``reviews/spec_findings.yaml`` keyed by spec
    hash so repeat runs surface regressions.

    Usage::

        critic = SpecCritic()
        result = critic.critique(
            feature_id="abc123",
            name="My feature",
            description="...",
            acceptance_criteria=["File exists: src/foo.py", "pytest: tests/test_foo_error.py"],
        )
        if not result["gate_passed"]:
            raise RuntimeError(f"Spec critic blocked codegen: {result['defects']}")
    """

    def __init__(
        self,
        *,
        constitution_path: Path | None = None,
        findings_path: Path | None = None,
        workspace: Path | None = None,
    ) -> None:
        self._constitution_path = constitution_path
        self._findings_path = findings_path
        self._workspace = workspace

    def critique(
        self,
        feature_id: str,
        name: str,
        description: str,
        acceptance_criteria: list[str],
        *,
        constitution_path: Path | None = None,
        findings_path: Path | None = None,
        workspace: Path | None = None,
    ) -> dict[str, Any]:
        """Run the adversarial spec critic for a single feature.

        Parameters
        ----------
        feature_id:
            Unique identifier for the feature.
        name:
            Human-readable feature name.
        description:
            Full feature description text.
        acceptance_criteria:
            List of AC strings for this feature.
        constitution_path:
            Override constitution path (takes precedence over instance default).
        findings_path:
            Override findings path (takes precedence over instance default).
        workspace:
            Override workspace root (takes precedence over instance default).

        Returns
        -------
        dict with keys:
            gate_passed : bool
            defects : list[dict]
            spec_hash : str

        Raises
        ------
        ConstitutionMissingError
            When ``spec_constitution.md`` cannot be found.
        ValueError
            When ``feature_id`` is empty or ``acceptance_criteria`` is not a list.
        """
        return critique_spec(
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            workspace=workspace or self._workspace,
            constitution_path=constitution_path or self._constitution_path,
            findings_path=findings_path or self._findings_path,
        )


def critique_spec(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    workspace: Path | None = None,
    constitution_path: Path | None = None,
    findings_path: Path | None = None,
) -> dict[str, Any]:
    """Run the adversarial spec critic and gate codegen on spec quality.

    Loads the versioned ``spec_constitution.md`` (Constitutional-AI style
    quality principles) and emits per-feature structured defects.
    Findings persist to ``reviews/spec_findings.yaml`` keyed by spec hash
    so repeat runs surface regressions.

    Parameters
    ----------
    feature_id:
        Unique identifier for the feature.
    name:
        Human-readable feature name.
    description:
        Full feature description text.
    acceptance_criteria:
        List of AC strings for this feature.
    workspace:
        Repository root directory; defaults to the grandparent of this file.
    constitution_path:
        Override path to ``spec_constitution.md``; mainly for testing.
        Falls back to the ``spec_constitution.md`` co-located with this module,
        then to ``src/bob3/spec_quality/spec_constitution.md``.
    findings_path:
        Override path to ``spec_findings.yaml``; mainly for testing.

    Returns
    -------
    dict with keys:
        gate_passed : bool
            True when no defects found (codegen may proceed).
        defects : list[dict]
            Structured defect records (empty on clean spec).
        spec_hash : str
            16-char SHA-256 of the spec content.

    Raises
    ------
    ConstitutionMissingError
        When ``spec_constitution.md`` cannot be found.
    ValueError
        When ``feature_id`` is empty or ``acceptance_criteria`` is not a list.
    """
    if not isinstance(feature_id, str) or not feature_id:
        raise ValueError("feature_id must be a non-empty string")
    if not isinstance(acceptance_criteria, list):
        raise ValueError("acceptance_criteria must be a list")

    # Resolve constitution path: caller override → sibling spec_constitution.md
    # → spec_quality/spec_constitution.md (canonical location)
    resolved_constitution = constitution_path
    if resolved_constitution is None:
        if _CONSTITUTION_PATH.exists():
            resolved_constitution = _CONSTITUTION_PATH
        else:
            resolved_constitution = Path(__file__).parent / "spec_quality" / "spec_constitution.md"

    defects = critique_feature(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
        constitution_path=resolved_constitution,
    )

    spec_hash = persist_findings(
        defects,
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        path=findings_path,
    )

    return {
        "gate_passed": len(defects) == 0,
        "defects": [d.to_dict() for d in defects],
        "spec_hash": spec_hash,
    }


def emit_plan_ready(
    feature_id: str,
    plan_path: str,
    approved: bool,
    workspace: Path | None = None,
) -> None:
    """Emit a PLAN_READY event after spec-critic passes (F-R7-450).

    Appends a structured JSON event to runs/events.jsonl signalling that
    plan.yaml has been written and is ready for implementer review.

    Parameters
    ----------
    feature_id:
        UUID of the feature.
    plan_path:
        Absolute or relative path to the written plan.yaml.
    approved:
        Current approval state of plan.yaml.
    workspace:
        Override for the workspace root (defaults to CWD).

    Raises
    ------
    ValueError
        When ``feature_id`` is empty or None.
    """
    if not isinstance(feature_id, str) or not feature_id:
        raise ValueError("feature_id must be a non-empty string")
    _emit_plan_ready_event(feature_id, plan_path, approved, workspace)


# Canonical entry point aliases — AC contract requires both names
run_spec_critic = critique_spec
run_spec_critique = critique_spec
