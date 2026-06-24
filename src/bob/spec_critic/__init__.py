"""bob.spec_critic — adversarial spec-critic with persistent findings registry.

F-R7-450: critic writes findings to reviews/spec_findings.yaml keyed by
(spec_hash, slot_id, defect_type). On re-run with same defect at same slot,
critic flags REGRESSION and escalates severity. Halt-gate fires if
critic_repeat_rate > 0.30 over 3 runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.orchestrator.plan_gate import emit_plan_ready_event as _emit_plan_ready_event
from bob.spec_critic import findings_registry
from bob.spec_critic.findings_registry import (
    write_findings,
    detect_regression,
    check_repeat_rate_halt_gate,
)
from bob.spec_quality.spec_critic import (
    ConstitutionMissingError,
    SpecDefect,
    critique_feature,
    persist_findings,
)

_CONSTITUTION_PATH = Path(__file__).parent.parent / "spec_quality" / "spec_constitution.md"


def load_spec_constitution(path: Path | None = None) -> str:
    """Load and return the versioned spec_constitution.md text.

    Parameters
    ----------
    path:
        Explicit path to ``spec_constitution.md``.  When omitted searches
        ``spec_quality/spec_constitution.md`` relative to this package.

    Returns
    -------
    str
        Raw text of the constitution document.

    Raises
    ------
    ConstitutionMissingError
        When no constitution file can be located.
    """
    resolved = path if path is not None else _CONSTITUTION_PATH
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
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError("feature_id must be a non-empty string")
        if not isinstance(acceptance_criteria, list):
            raise ValueError("acceptance_criteria must be a list")

        eff_constitution = constitution_path or self._constitution_path
        eff_findings = findings_path or self._findings_path
        eff_workspace = workspace or self._workspace

        defects = critique_feature(
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            workspace=eff_workspace,
            constitution_path=eff_constitution,
        )
        spec_hash = persist_findings(
            defects,
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            path=eff_findings,
        )
        return {
            "gate_passed": len(defects) == 0,
            "defects": [d.to_dict() for d in defects],
            "spec_hash": spec_hash,
        }


def run_spec_critic(
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

    Loads the versioned ``spec_constitution.md`` and emits per-feature structured
    defects.  Findings persist to ``reviews/spec_findings.yaml`` keyed by spec
    hash so repeat runs surface regressions.

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
        Override path to ``spec_constitution.md``; defaults to the canonical
        ``spec_quality/spec_constitution.md`` location.
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
            16-char SHA-256 prefix of the spec content.

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

    resolved_constitution = constitution_path if constitution_path is not None else _CONSTITUTION_PATH

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


def emit_defects(
    defects: list[Any],
    *,
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    findings_path: Path | None = None,
) -> str:
    """Emit per-feature structured defects to ``reviews/spec_findings.yaml``.

    Persists structured defect records keyed by spec hash to the findings file
    so downstream gates and regression-detection can read them.

    Parameters
    ----------
    defects:
        List of :class:`SpecDefect` instances (or dicts with the same keys)
        to persist.  An empty list records a clean-spec entry.
    feature_id:
        Unique identifier for the feature.
    name:
        Human-readable feature name.
    description:
        Full feature description text.
    acceptance_criteria:
        List of AC strings for this feature.
    findings_path:
        Override path to ``spec_findings.yaml``; defaults to
        ``reviews/spec_findings.yaml`` in the workspace root.

    Returns
    -------
    str
        16-char SHA-256 prefix of the spec content (the ``spec_hash`` key).

    Raises
    ------
    ValueError
        When ``feature_id`` is empty or ``acceptance_criteria`` is not a list.
    """
    if not isinstance(feature_id, str) or not feature_id:
        raise ValueError("feature_id must be a non-empty string")
    if not isinstance(acceptance_criteria, list):
        raise ValueError("acceptance_criteria must be a list")

    # Accept either SpecDefect instances or plain dicts (idiomatic for callers
    # that build defect records manually without importing SpecDefect).
    defect_objects: list[SpecDefect] = []
    for item in defects:
        if isinstance(item, SpecDefect):
            defect_objects.append(item)
        else:
            defect_objects.append(
                SpecDefect(
                    feature_id=item.get("feature_id", feature_id),
                    ac_index=item.get("ac_index", 0),
                    defect_type=item.get("defect_type", "ambiguity"),
                    rationale=item.get("rationale", ""),
                    suggested_fix=item.get("suggested_fix", ""),
                )
            )

    return persist_findings(
        defect_objects,
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        path=findings_path,
    )


def emit_plan_ready(
    feature_id: str,
    plan_path: str,
    approved: bool,
    workspace: Path | None = None,
) -> None:
    """Emit a PLAN_READY event after spec-critic passes (F-R7-450).

    Raises
    ------
    ValueError
        When ``feature_id`` is empty or None.
    """
    if not isinstance(feature_id, str) or not feature_id:
        raise ValueError("feature_id must be a non-empty string")
    _emit_plan_ready_event(feature_id, plan_path, approved, workspace)


# AC alias: "Function defined: bob.spec_critic.load_constitution"
load_constitution = load_spec_constitution

__all__ = [
    "findings_registry",
    "write_findings",
    "detect_regression",
    "check_repeat_rate_halt_gate",
    "emit_defects",
    "emit_plan_ready",
    "load_constitution",
    "load_spec_constitution",
    "run_spec_critic",
    "SpecCritic",
    "ConstitutionMissingError",
    "SpecDefect",
]
