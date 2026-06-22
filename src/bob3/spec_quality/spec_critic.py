"""Adversarial spec-critic sub-agent — gate codegen on spec quality (F-17b01ded).

Loads a versioned ``spec_constitution.md`` (Constitutional-AI style list of
spec-quality principles) and emits, per feature, a structured list of defects:

    {feature_id, ac_index, defect_type, rationale, suggested_fix}

where ``defect_type`` ∈ {ambiguity, missing_edge_case, untestable,
implementation_leak, vague_quantifier, missing_actor, unreachable_integration}.

Findings persist to ``reviews/spec_findings.yaml`` keyed by spec hash so
repeat runs surface regressions.

On non-empty critic output the caller should run one revise pass; second-round
defects escalate to F-R7-456 clarification.

Public API::

    from bob3.spec_quality.spec_critic import critique_feature, persist_findings

    defects = critique_feature(
        feature_id="abc123",
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py", "pytest: tests/test_foo.py"],
    )
    persist_findings(defects)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConstitutionMissingError(FileNotFoundError):
    """Raised when spec_constitution.md cannot be found."""

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defect type literals
# ---------------------------------------------------------------------------

DEFECT_TYPES = frozenset(
    {
        "ambiguity",
        "missing_edge_case",
        "untestable",
        "implementation_leak",
        "vague_quantifier",
        "missing_actor",
        "unreachable_integration",
    }
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SpecDefect:
    """One structured defect emitted by the spec critic."""

    feature_id: str
    ac_index: int  # -1 means the defect applies to the feature as a whole
    defect_type: str
    rationale: str
    suggested_fix: str

    def __post_init__(self) -> None:
        if self.defect_type not in DEFECT_TYPES:
            raise ValueError(
                f"unknown defect_type {self.defect_type!r}; "
                f"must be one of {sorted(DEFECT_TYPES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "ac_index": self.ac_index,
            "defect_type": self.defect_type,
            "rationale": self.rationale,
            "suggested_fix": self.suggested_fix,
        }


# ---------------------------------------------------------------------------
# Constitution loading
# ---------------------------------------------------------------------------

_CONSTITUTION_PATH = Path(__file__).parent / "spec_constitution.md"


def _load_constitution(path: Path | None = None) -> str:
    """Return the raw text of the spec constitution."""
    p = path or _CONSTITUTION_PATH
    if not p.exists():
        raise ConstitutionMissingError(
            f"spec_constitution.md not found at {p}; "
            "create the file to enable the spec critic."
        )
    return p.read_text(encoding="utf-8")


def _constitution_version(path: Path | None = None) -> str:
    """Return the version string declared in the constitution."""
    text = _load_constitution(path)
    m = re.search(r'version:\s*"([^"]+)"', text)
    return m.group(1) if m else "unknown"


# ---------------------------------------------------------------------------
# Spec hash
# ---------------------------------------------------------------------------


def _spec_hash(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> str:
    """Deterministic SHA-256 (truncated to 16 hex chars) of the spec content."""
    payload = json.dumps(
        {
            "feature_id": feature_id,
            "name": name,
            "description": description,
            "acceptance_criteria": sorted(acceptance_criteria),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Individual defect detectors
# ---------------------------------------------------------------------------

_VAGUE_WORDS = re.compile(
    r"\b(works\s+correctly|works\s+properly|handles\s+properly|"
    r"is\s+correct|is\s+good|is\s+nice|looks\s+good|user[- ]friendly|"
    r"intuitive|seamlessly|appropriately|properly|correctly)\b",
    re.IGNORECASE,
)

_VAGUE_QUANTIFIERS = re.compile(
    r"\b(fast|slow|large|small|big|few|many|reasonable|acceptable|"
    r"adequate|sufficient|appropriate|optimal|better|worse)\b",
    re.IGNORECASE,
)

_IMPL_LEAK_PATTERNS = re.compile(
    r"\b(uses?\s+a\s+\w+map|calls?\s+subprocess|inherits?\s+from|"
    r"extends?\s+\w+|via\s+\w+\.py|uses?\s+redis|uses?\s+sqlite|"
    r"stored\s+in\s+\w+list|stored\s+in\s+\w+dict)\b",
    re.IGNORECASE,
)

_MISSING_ACTOR_RE = re.compile(
    r"^(shall|must|should|will|can)\s+\w+",
    re.IGNORECASE,
)

_STRUCTURED_FORMS = re.compile(
    r"^(File\s+exists|Function\s+defined|Class\s+defined|pytest|"
    r"integration|behavior|python|Field\s+exists)",
    re.IGNORECASE,
)

_INTEGRATION_AC = re.compile(r"^integration\s*:\s*([\w./:-]+)", re.IGNORECASE)

_FAILURE_PATH_RE = re.compile(
    r"(error|fail|reject|invalid|missing|empty|none|null|raise|exception|"
    r"boundary|edge|negative|zero|overflow|timeout|unavailable)",
    re.IGNORECASE,
)


def _detect_ambiguity(feature_id: str, ac_index: int, ac: str) -> SpecDefect | None:
    """Return a defect if the AC is ambiguous (vague or non-structured)."""
    stripped = ac.strip()
    if not stripped:
        return SpecDefect(
            feature_id=feature_id,
            ac_index=ac_index,
            defect_type="ambiguity",
            rationale="Empty acceptance criterion.",
            suggested_fix="Remove or replace with a concrete, verifiable criterion.",
        )
    if _VAGUE_WORDS.search(stripped) and not _STRUCTURED_FORMS.match(stripped):
        match = _VAGUE_WORDS.search(stripped)
        vague = match.group(0) if match else "vague phrase"
        return SpecDefect(
            feature_id=feature_id,
            ac_index=ac_index,
            defect_type="ambiguity",
            rationale=f"Contains vague phrase {vague!r} without a measurable outcome.",
            suggested_fix=(
                f"Replace '{vague}' with a concrete observable predicate "
                "(e.g. 'pytest: tests/test_X.py' or 'File exists: src/X.py')."
            ),
        )
    return None


def _detect_untestable(feature_id: str, ac_index: int, ac: str) -> SpecDefect | None:
    """Return a defect if the AC cannot be machine-verified."""
    stripped = ac.strip()
    untestable_phrases = re.compile(
        r"\b(looks\s+good|user[- ]friendly|intuitive|beautiful|elegant|"
        r"readable|maintainable|clean\s+code|well[- ]structured)\b",
        re.IGNORECASE,
    )
    if untestable_phrases.search(stripped):
        m = untestable_phrases.search(stripped)
        phrase = m.group(0) if m else "subjective phrase"
        return SpecDefect(
            feature_id=feature_id,
            ac_index=ac_index,
            defect_type="untestable",
            rationale=f"Criterion contains subjective phrase {phrase!r} that requires human judgment.",
            suggested_fix="Replace with a machine-verifiable predicate such as 'pytest: tests/test_X.py'.",
        )
    return None


def _detect_implementation_leak(
    feature_id: str, ac_index: int, ac: str
) -> SpecDefect | None:
    """Return a defect if the AC leaks implementation details."""
    stripped = ac.strip()
    m = _IMPL_LEAK_PATTERNS.search(stripped)
    if m:
        leak = m.group(0)
        return SpecDefect(
            feature_id=feature_id,
            ac_index=ac_index,
            defect_type="implementation_leak",
            rationale=f"Criterion prescribes implementation detail {leak!r} rather than observable behaviour.",
            suggested_fix=f"Remove the implementation detail '{leak}' and express the criterion as an observable outcome.",
        )
    return None


def _detect_vague_quantifier(
    feature_id: str, ac_index: int, ac: str
) -> SpecDefect | None:
    """Return a defect if the AC uses a vague quantifier."""
    stripped = ac.strip()
    # Only check non-structured ACs for vague quantifiers
    if _STRUCTURED_FORMS.match(stripped):
        return None
    m = _VAGUE_QUANTIFIERS.search(stripped)
    if m:
        quantifier = m.group(0)
        return SpecDefect(
            feature_id=feature_id,
            ac_index=ac_index,
            defect_type="vague_quantifier",
            suggested_fix=f"Replace '{quantifier}' with a concrete numeric threshold or measurable bound.",
            rationale=f"Quantifier {quantifier!r} is vague — no numeric bound or specific measurement given.",
        )
    return None


def _detect_missing_actor(
    feature_id: str, ac_index: int, ac: str
) -> SpecDefect | None:
    """Return a defect if the AC has no named actor/subject."""
    stripped = ac.strip()
    if _STRUCTURED_FORMS.match(stripped):
        return None
    if _MISSING_ACTOR_RE.match(stripped):
        return SpecDefect(
            feature_id=feature_id,
            ac_index=ac_index,
            defect_type="missing_actor",
            rationale="Criterion begins with a modal verb without naming who or what performs the action.",
            suggested_fix="Name the actor explicitly, e.g. 'The spec-critic shall …' or use a structured form like 'pytest: …'.",
        )
    return None


def _detect_unreachable_integration(
    feature_id: str,
    ac_index: int,
    ac: str,
    workspace: Path,
) -> SpecDefect | None:
    """Return a defect if an integration: AC references an unreachable module."""
    m = _INTEGRATION_AC.match(ac.strip())
    if not m:
        return None
    module = m.group(1).strip()
    rel = module.replace(".", "/")
    candidates = [
        workspace / "src" / f"{rel}.py",
        workspace / f"{rel}.py",
        workspace / "src" / rel / "__init__.py",
        workspace / rel / "__init__.py",
    ]
    if any(p.exists() for p in candidates):
        return None
    return SpecDefect(
        feature_id=feature_id,
        ac_index=ac_index,
        defect_type="unreachable_integration",
        rationale=f"Integration target '{module}' has no corresponding source file in the workspace.",
        suggested_fix=(
            f"Either create the module at src/{rel}.py or correct the module path."
        ),
    )


def _detect_missing_edge_case(
    feature_id: str,
    acceptance_criteria: list[str],
) -> SpecDefect | None:
    """Return a defect if the spec has no failure/edge-case coverage."""
    if not acceptance_criteria:
        return None
    for ac in acceptance_criteria:
        if _FAILURE_PATH_RE.search(ac):
            return None
    return SpecDefect(
        feature_id=feature_id,
        ac_index=-1,
        defect_type="missing_edge_case",
        rationale="All acceptance criteria cover only happy-path behaviour; no error path, boundary, or failure case is specified.",
        suggested_fix="Add at least one criterion covering a failure path, e.g. 'pytest: tests/test_X_invalid_input.py'.",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def critique_feature(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    workspace: Path | None = None,
    constitution_path: Path | None = None,
) -> list[SpecDefect]:
    """Run all critic rules against a feature and return structured defects.

    Parameters
    ----------
    feature_id:
        Unique identifier for the feature (used in defect records).
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

    Returns
    -------
    list[SpecDefect]
        Possibly-empty list of defects found.
    """
    if workspace is None:
        # Walk up from src/bob3/spec_quality/ → bob12/
        workspace = Path(__file__).resolve().parents[3]

    # Load constitution to confirm it is valid (raises if missing)
    _load_constitution(constitution_path)

    defects: list[SpecDefect] = []

    for idx, ac in enumerate(acceptance_criteria):
        for detector in (
            _detect_untestable,
            _detect_ambiguity,
            _detect_implementation_leak,
            _detect_vague_quantifier,
            _detect_missing_actor,
        ):
            d = detector(feature_id, idx, ac)
            if d is not None:
                defects.append(d)
                break  # one defect per AC (highest-priority wins)

        # Unreachable integration is additive (can stack with others)
        d = _detect_unreachable_integration(feature_id, idx, ac, workspace)
        if d is not None:
            defects.append(d)

    # Feature-level check (not per-AC)
    missing_edge = _detect_missing_edge_case(feature_id, acceptance_criteria)
    if missing_edge:
        defects.append(missing_edge)

    if defects:
        logger.info(
            "spec-critic found %d defect(s) for feature %s (%s)",
            len(defects),
            feature_id[:8],
            name,
        )
    else:
        logger.debug("spec-critic: no defects for feature %s (%s)", feature_id[:8], name)

    return defects


# ---------------------------------------------------------------------------
# Findings persistence
# ---------------------------------------------------------------------------

_SPEC_FINDINGS_PATH = Path(__file__).resolve().parents[3] / "reviews" / "spec_findings.yaml"


def _findings_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return _SPEC_FINDINGS_PATH


def _load_spec_findings(path: Path) -> dict[str, Any]:
    """Load spec_findings.yaml, returning a dict keyed by spec_hash."""
    from bob3.reviews.spec_findings_writer import load_spec_findings_safe

    data = load_spec_findings_safe(path)
    return data.get("findings_by_hash", {})


def _save_spec_findings(findings_by_hash: dict[str, Any], path: Path) -> None:
    from bob3.reviews.spec_findings_writer import atomic_write_yaml

    data = {
        "schema_version": 1,
        "findings_by_hash": findings_by_hash,
    }
    atomic_write_yaml(data, path)


def persist_findings(
    defects: list[SpecDefect],
    *,
    feature_id: str = "",
    name: str = "",
    description: str = "",
    acceptance_criteria: list[str] | None = None,
    path: Path | None = None,
) -> str:
    """Persist defects to reviews/spec_findings.yaml keyed by spec hash.

    Parameters
    ----------
    defects:
        Defects returned by :func:`critique_feature`.
    feature_id, name, description, acceptance_criteria:
        The spec data used to derive the hash key.  When *defects* is
        non-empty these should be provided; if omitted they default to
        empty strings / lists and the hash will reflect that.
    path:
        Override the output path; mainly for testing.

    Returns
    -------
    str
        The spec hash under which this batch was stored.
    """
    acs = acceptance_criteria or []
    spec_hash = _spec_hash(feature_id, name, description, acs)

    p = _findings_path(path)
    findings_by_hash = _load_spec_findings(p)

    entry: dict[str, Any] = {
        "feature_id": feature_id,
        "feature_name": name,
        "date": date.today().isoformat(),
        "defect_count": len(defects),
        "defects": [d.to_dict() for d in defects],
    }

    if spec_hash in findings_by_hash:
        existing = findings_by_hash[spec_hash]
        prior_count = existing.get("defect_count", 0)
        entry["regression"] = len(defects) > prior_count
        entry["prior_defect_count"] = prior_count
    else:
        entry["regression"] = False

    findings_by_hash[spec_hash] = entry
    _save_spec_findings(findings_by_hash, p)

    # Also record each defect in the persistent spec_findings_registry
    # (keyed by spec_hash + slot_id + defect_type for per-defect regression tracking)
    try:
        from bob3.spec_quality.spec_findings_registry import record as _sfr_record

        for defect in defects:
            slot_id = f"AC-{defect.ac_index}" if defect.ac_index >= 0 else "FEATURE"
            _sfr_record(
                spec_hash=spec_hash,
                slot_id=slot_id,
                defect_type=defect.defect_type,
                feature_id=feature_id,
                name=name,
                rationale=defect.rationale,
                suggested_fix=defect.suggested_fix,
            )
    except Exception:  # noqa: BLE001  — registry failure must not break codegen
        logger.debug("spec-critic: spec_findings_registry record failed", exc_info=True)

    logger.debug(
        "spec-critic: persisted %d defect(s) under hash %s for feature %s",
        len(defects),
        spec_hash,
        feature_id[:8] if feature_id else "?",
    )
    return spec_hash


# ---------------------------------------------------------------------------
# Higher-level helpers (used by orchestrator run_loop)
# ---------------------------------------------------------------------------

#: Clarification feature reference for second-round escalation
_CLARIFICATION_REF = "F-R7-456"


def run_revise_loop(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    workspace: Path | None = None,
    constitution_path: Path | None = None,
) -> tuple[list[SpecDefect], bool]:
    """Run a single bounded revise pass (max 1).

    Performs one critique.  If defects are found, returns them and signals
    that a revise pass occurred.  The caller owns second-round escalation.

    Returns
    -------
    (defects, revised)
        *defects* is the list from the single critique call.
        *revised* is True when the first pass found defects (i.e. a revise
        pass would be needed); False on a clean spec.
    """
    defects = critique_feature(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
        constitution_path=constitution_path,
    )
    return defects, bool(defects)


def escalates_to_clarification_on_second_round(
    second_round_defects: list[SpecDefect],
) -> bool:
    """Return True when second-round defects should escalate to clarification.

    Escalation target is *F-R7-456* per the spec.  This function always
    returns True when *second_round_defects* is non-empty (the decision to
    escalate is unconditional; the caller decides when to call this function).
    """
    return bool(second_round_defects)


def handle_empty_constitution(constitution_path: Path | None = None) -> None:
    """Raise ConstitutionMissingError when spec_constitution.md is absent.

    This thin wrapper exists so the orchestrator can express the guard as a
    named function call rather than inlining the path check.

    Raises
    ------
    ConstitutionMissingError
        When the constitution file does not exist at *constitution_path* (or
        the default location if *constitution_path* is None).
    """
    _load_constitution(constitution_path)


def defect_type_is_known(defect_type: str) -> bool:
    """Return True when *defect_type* is in the canonical defect-type set.

    The canonical set is:
    ``ambiguity``, ``missing_edge_case``, ``untestable``,
    ``implementation_leak``, ``vague_quantifier``, ``missing_actor``,
    ``unreachable_integration``.
    """
    return defect_type in DEFECT_TYPES


def run_auto_repair(
    feature_id: str,
    acceptance_criteria: list[str],
    auto_repair: bool = True,
    repairs_log: Path | None = None,
) -> dict:
    """Run ac_auto_repair on the given ACs and return the repair result dict.

    Delegates to :func:`bob3.spec_quality.ac_auto_repair.repair_feature_acs`.
    Provides the integration point between spec_critic and ac_auto_repair.
    """
    from bob3.spec_quality.ac_auto_repair import repair_feature_acs  # noqa: PLC0415

    return repair_feature_acs(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        auto_repair=auto_repair,
        repairs_log=repairs_log,
    )
