"""Spec critic package — exposes the persistent findings registry and run_critic.

Public API::

    from spec_critic import registry, run_critic

    # Gate codegen on spec quality
    result = run_critic(
        feature_id="abc123",
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py", "pytest: tests/test_foo_error.py"],
    )
    if not result["gate_passed"]:
        raise RuntimeError(f"Spec critic blocked codegen: {result['defects']}")

    # Persistent findings registry
    registry.write_findings(...)
    registry.detect_regression(...)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_critic import registry
from bob.spec_quality.spec_critic import (
    ConstitutionMissingError,
    SpecDefect,
    critique_feature,
    persist_findings,
)


def run_critic(
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

    Integrates with ``bob.spec_quality.spec_extractor`` — call this after
    spec extraction completes and before any implementer agent is dispatched.

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

    defects = critique_feature(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
        constitution_path=constitution_path,
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


__all__ = ["registry", "run_critic", "ConstitutionMissingError", "SpecDefect"]
