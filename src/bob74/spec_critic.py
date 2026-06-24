"""Adversarial spec-critic sub-agent for bob74.

Gates codegen on spec quality by running after the spec-extractor and before
any implementer fires. Loads a versioned spec_constitution.md and emits
per-feature structured defects. Findings persist to reviews/spec_findings.yaml
keyed by spec hash.

Public API::

    from bob74.spec_critic import SpecCritic

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

    Runs after the spec-extractor and before any implementer is dispatched.
    Loads a versioned ``spec_constitution.md`` and emits per-feature
    structured defects. Findings persist to ``reviews/spec_findings.yaml``
    keyed by spec hash so repeat runs surface regressions.

    Parameters
    ----------
    workspace:
        Repository root directory; defaults to the standard bob74 root.
    constitution_path:
        Override path to ``spec_constitution.md``; mainly for testing.
    findings_path:
        Override path to ``spec_findings.yaml``; mainly for testing.
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
            workspace=self._workspace,
            constitution_path=self._constitution_path,
        )

        spec_hash = persist_findings(
            defects,
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            path=self._findings_path,
        )

        return {
            "gate_passed": len(defects) == 0,
            "defects": [d.to_dict() for d in defects],
            "spec_hash": spec_hash,
        }

    def gate_codegen(
        self,
        feature_id: str,
        name: str,
        description: str,
        acceptance_criteria: list[str],
    ) -> bool:
        """Return True when the spec passes quality gates (codegen may proceed).

        Convenience wrapper around :meth:`critique` that returns only the
        boolean gate result. Side-effects (persistence to findings.yaml) are
        the same as calling :meth:`critique` directly.
        """
        result = self.critique(
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
        )
        return result["gate_passed"]


__all__ = ["SpecCritic", "ConstitutionMissingError", "SpecDefect"]
