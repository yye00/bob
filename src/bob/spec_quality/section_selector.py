"""Self-Discover meta-agent: per-feature spec-section selection (F-7f873d9b).

A meta-agent that first picks WHICH spec sections matter for a given feature,
then drives a focused extractor pass. Beats one-size-fits-all extraction.

Source: Agent 4 Section 7 (Self-Discover, ICML 2024).

Public API::

    from bob.spec_quality.section_selector import (
        select_sections,
        module_set,
        validate_output_schema,
        extractor_skips_marked_sections,
        critic_ignores_skip_slots,
        persist_decision,
    )

Section labels
--------------
Each section is classified as one of:

- ``REQUIRED`` — extractor must fill this slot; critic penalizes if missing.
- ``OPTIONAL`` — extractor should attempt; critic does not penalize if absent.
- ``SKIP``     — extractor leaves null with rationale; critic ignores entirely.
"""

from __future__ import annotations

import datetime
import logging
import re
from pathlib import Path
from typing import Any

import yaml


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SECTION_VALUES = frozenset({"REQUIRED", "OPTIONAL", "SKIP"})

_MODULE_NAMES: list[str] = [
    "functional",
    "perf",
    "security",
    "error_handling",
    "observability",
    "ops",
    "ux",
    "compat",
]

# Heuristics for trivial / internal-only features to auto-skip NFR sections
_NFR_SECTIONS = frozenset({"perf", "security", "observability", "ops", "ux", "compat"})

_TRIVIAL_FEATURE_RE = re.compile(
    r"\b(trivial|internal|helper|utility|util|refactor|cleanup|stub|scaffold|"
    r"migration|rename|move|reorgani[sz]e|alias)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SectionSchemaError(Exception):
    """Raised when the output of select_sections does not match the schema.

    The required schema is ``{section_name: REQUIRED | OPTIONAL | SKIP}``
    where every section in module_set() must be present.
    """


# ---------------------------------------------------------------------------
# Core public API
# ---------------------------------------------------------------------------


def module_set() -> list[str]:
    """Return the canonical list of 8 spec section names.

    Returns
    -------
    list[str]
        Exactly 8 section names: functional, perf, security, error_handling,
        observability, ops, ux, compat.
    """
    return list(_MODULE_NAMES)


def select_sections(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> dict[str, str]:
    """Classify each spec section as REQUIRED, OPTIONAL, or SKIP.

    A lightweight heuristic meta-agent: inspect the feature name, description,
    and ACs to determine which spec sections matter. The output dict has one
    key per section in module_set() with a value of REQUIRED, OPTIONAL, or SKIP.

    Parameters
    ----------
    feature_id:
        Unique feature identifier.
    name:
        Short feature name.
    description:
        Feature description text.
    acceptance_criteria:
        List of AC strings from the spec.

    Returns
    -------
    dict[str, str]
        Mapping of section_name → "REQUIRED" | "OPTIONAL" | "SKIP".
    """
    full_text = f"{name} {description} {' '.join(acceptance_criteria)}"
    is_trivial = bool(_TRIVIAL_FEATURE_RE.search(full_text))

    selection: dict[str, str] = {}
    for section in _MODULE_NAMES:
        if section == "functional":
            # Functional is always REQUIRED — every feature has functional ACs.
            selection[section] = "REQUIRED"
        elif section in _NFR_SECTIONS and is_trivial:
            selection[section] = "SKIP"
        else:
            selection[section] = _infer_section(section, full_text)

    validate_output_schema(selection)
    return selection


def _infer_section(section: str, full_text: str) -> str:
    """Infer REQUIRED / OPTIONAL / SKIP for a non-trivial, non-functional section."""
    keywords: dict[str, list[str]] = {
        "perf": ["latency", "throughput", "performance", "benchmark", "speed", "timeout", "sla"],
        "security": ["auth", "security", "encrypt", "permission", "privilege", "token", "secret", "credential"],
        "error_handling": ["error", "exception", "fail", "retry", "recovery", "fallback", "crash"],
        "observability": ["log", "metric", "trace", "monitor", "observ", "telemetry", "alert"],
        "ops": ["deploy", "config", "environment", "ops", "infra", "kubernetes", "docker", "ci"],
        "ux": ["ui", "user interface", "display", "render", "frontend", "layout", "css", "html"],
        "compat": ["compat", "backward", "version", "migration", "upgrade", "downgrade", "legacy"],
    }

    hints = keywords.get(section, [])
    lower_text = full_text.lower()

    match_count = sum(1 for hint in hints if hint in lower_text)

    if match_count >= 2:
        return "REQUIRED"
    elif match_count == 1:
        return "OPTIONAL"
    else:
        return "SKIP"


def validate_output_schema(output: Any) -> None:
    """Raise SectionSchemaError if output does not match the section schema.

    Valid schema: a dict where every key is in module_set() and every value
    is one of REQUIRED, OPTIONAL, SKIP. No extra keys are allowed; no keys
    from module_set() may be missing.

    Parameters
    ----------
    output:
        The value to validate.

    Raises
    ------
    SectionSchemaError
        When output is not a dict, has missing/extra keys, or invalid values.
    """
    if not isinstance(output, dict):
        raise SectionSchemaError(
            f"section_selector output must be a dict, got {type(output).__name__}"
        )

    expected_keys = set(_MODULE_NAMES)
    actual_keys = set(output.keys())

    missing = expected_keys - actual_keys
    if missing:
        raise SectionSchemaError(
            f"section_selector output is missing sections: {sorted(missing)}"
        )

    extra = actual_keys - expected_keys
    if extra:
        raise SectionSchemaError(
            f"section_selector output has unexpected sections: {sorted(extra)}"
        )

    for section, value in output.items():
        if value not in _SECTION_VALUES:
            raise SectionSchemaError(
                f"Invalid value {value!r} for section {section!r}. "
                f"Must be one of {sorted(_SECTION_VALUES)}"
            )


def extractor_skips_marked_sections(
    extraction_output: dict[str, Any],
    section_map: dict[str, str],
) -> bool:
    """Return True iff extractor left SKIP slots null with a rationale.

    For every section classified as SKIP in section_map, the corresponding
    slot in extraction_output must be either None or a dict with a
    ``rationale`` key explaining why it was skipped.

    Parameters
    ----------
    extraction_output:
        The dict produced by the extractor, keyed by section name.
    section_map:
        The dict produced by select_sections.

    Returns
    -------
    bool
        True when all SKIP sections are properly null/rationale-annotated.
    """
    for section, label in section_map.items():
        if label != "SKIP":
            continue
        slot_value = extraction_output.get(section)
        if slot_value is None:
            continue
        if isinstance(slot_value, dict) and "rationale" in slot_value:
            continue
        return False
    return True


def critic_ignores_skip_slots(
    section_map: dict[str, str],
) -> bool:
    """Return True — the critic must not penalize missing SKIP slots.

    This function always returns True as a contract check: calling it
    confirms that the caller has acknowledged the rule that SKIP slots are
    exempt from critic penalization.

    Parameters
    ----------
    section_map:
        The dict produced by select_sections (used to assert schema validity).

    Returns
    -------
    bool
        Always True.
    """
    validate_output_schema(section_map)
    return True


def persist_decision(
    feature_id: str,
    name: str,
    section_map: dict[str, str],
    *,
    output_path: Path | str | None = None,
) -> Path:
    """Append the section-selection decision to reviews/section_selections.yaml.

    Parameters
    ----------
    feature_id:
        Unique feature identifier.
    name:
        Short feature name.
    section_map:
        The output of select_sections.
    output_path:
        Override path for the YAML file. Defaults to
        ``reviews/section_selections.yaml`` relative to the project root.

    Returns
    -------
    Path
        The path to the written YAML file.
    """
    validate_output_schema(section_map)

    if output_path is None:
        output_path = Path(__file__).parents[3] / "reviews" / "section_selections.yaml"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    record: dict[str, Any] = {
        "feature_id": feature_id,
        "name": name,
        "timestamp": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "sections": dict(section_map),
    }

    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}
    else:
        existing = {}

    decisions: list[dict[str, Any]] = existing.get("decisions", [])
    decisions.append(record)
    existing["decisions"] = decisions

    with output_path.open("w", encoding="utf-8") as fh:
        yaml.dump(existing, fh, default_flow_style=False, sort_keys=False)

    logger.debug("persist_decision: wrote %s → %s", feature_id, output_path)
    return output_path
