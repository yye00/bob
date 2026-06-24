"""SpecCritic class — adversarial spec-critic sub-agent.

Dedicated sub-agent that runs after the spec-extractor and before any
implementer fires.  Loads a versioned spec_constitution.md and emits
per-feature structured defects.  Findings persist to
reviews/spec_findings.yaml keyed by spec hash.

Public API::

    from spec_critic.critic import SpecCritic

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

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.spec_quality.spec_critic import (
    ConstitutionMissingError,
    SpecDefect,
    critique_feature,
    persist_findings,
)


class SpecCritic:
    """Adversarial spec-critic sub-agent that gates codegen on spec quality.

    Loads a versioned spec_constitution.md and evaluates per-feature
    structured defects.  Findings persist to reviews/spec_findings.yaml
    keyed by spec hash so repeat runs surface regressions.

    Integrates with spec_extractor — call :meth:`critique` after spec
    extraction completes and before any implementer agent is dispatched.

    Parameters
    ----------
    workspace:
        Repository root directory; defaults to the grandparent of the
        spec_critic package.
    constitution_path:
        Override path to spec_constitution.md; mainly for testing.
    findings_path:
        Override path to reviews/spec_findings.yaml; mainly for testing.
    """

    def __init__(
        self,
        workspace: Path | None = None,
        constitution_path: Path | None = None,
        findings_path: Path | None = None,
    ) -> None:
        self._workspace = workspace
        self._constitution_path = constitution_path
        self._findings_path = findings_path

    def critique(
        self,
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
            Override the instance workspace; defaults to the instance value.
        constitution_path:
            Override the instance constitution_path; defaults to the instance value.
        findings_path:
            Override the instance findings_path; defaults to the instance value.

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
            When spec_constitution.md cannot be found.
        ValueError
            When feature_id is empty or acceptance_criteria is not a list.
        """
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError("feature_id must be a non-empty string")
        if not isinstance(acceptance_criteria, list):
            raise ValueError("acceptance_criteria must be a list")

        ws = workspace or self._workspace
        cp = constitution_path or self._constitution_path
        fp = findings_path or self._findings_path

        defects = critique_feature(
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            workspace=ws,
            constitution_path=cp,
        )

        spec_hash = persist_findings(
            defects,
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            path=fp,
        )

        return {
            "gate_passed": len(defects) == 0,
            "defects": [d.to_dict() for d in defects],
            "spec_hash": spec_hash,
        }

    def gate_passed(self, result: dict[str, Any]) -> bool:
        """Return True when the critique result has no defects."""
        return bool(result.get("gate_passed", False))


__all__ = ["SpecCritic", "ConstitutionMissingError", "SpecDefect"]
