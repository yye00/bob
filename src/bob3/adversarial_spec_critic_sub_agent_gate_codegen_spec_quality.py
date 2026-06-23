"""Adversarial spec-critic sub-agent — gate codegen on spec quality.

Runs after the spec-extractor and before any implementer fires.
Loads a versioned spec_constitution.md and emits per-feature structured
defects. Findings persist to reviews/spec_findings.yaml keyed by spec hash.

Public API::

    from bob3.adversarial_spec_critic_sub_agent_gate_codegen_spec_quality import (
        adversarial_spec_critic_sub_agent_gate_codegen_spec_quality,
    )

    result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
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

from bob3.spec_quality.spec_critic import critique_feature, persist_findings


def adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
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

    Loads a versioned ``spec_constitution.md`` (Constitutional-AI style
    quality principles) and emits per-feature structured defects.
    Findings persist to ``reviews/spec_findings.yaml`` keyed by spec hash
    so repeat runs surface regressions.

    Parameters
    ----------
    feature_id:
        Unique identifier for the feature (used in defect records and hash).
    name:
        Human-readable feature name.
    description:
        Full feature description text.
    acceptance_criteria:
        List of AC strings for this feature.
    workspace:
        Repository root directory; defaults to the grandparent of this file.
    constitution_path:
        Override path to spec_constitution.md; mainly for testing.
    findings_path:
        Override path to spec_findings.yaml; mainly for testing.

    Returns
    -------
    dict with keys:
        gate_passed: bool — True when no defects were found (codegen may proceed)
        defects: list[dict] — structured defect records (empty on clean spec)
        spec_hash: str — 16-char SHA-256 of the spec content

    Raises
    ------
    ConstitutionMissingError
        When spec_constitution.md cannot be found at the expected location.
    """
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
