"""Self-Discover meta-agent for per-feature spec-section selection.

Feature 08e256ba-bf12-40ec-9117-c2da7ccbe9b2

bob's PRD schema (F-R7-457) is fixed: every spec must fill every slot.
A meta-agent that first picks WHICH spec sections matter, then drives a
focused extractor pass, beats one-size-fits-all extraction.

Source: Agent 4 Section 7 (Self-Discover, ICML 2024).

Public API::

    from bob.meta_agent_selector import (
        select_spec_sections,
        run_focused_extraction,
    )

Integration
-----------
Delegates to :mod:`bob.spec_quality.section_selector` for section
classification. Integrates with :mod:`bob.orchestrator` as
``bob.orchestrator.select_spec_sections`` and
``bob.orchestrator.run_focused_extraction``.
"""

from __future__ import annotations

import logging
from typing import Any

from bob.spec_quality.section_selector import (
    select_sections,
    validate_output_schema,
)

logger = logging.getLogger(__name__)


def _validate_inputs(
    feature_id: object,
    name: object,
    description: object,
    acceptance_criteria: object,
) -> None:
    """Raise ValueError if any argument has an invalid type."""
    if not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a str, got {type(feature_id).__name__!r}"
        )
    if not isinstance(name, str):
        raise ValueError(
            f"name must be a str, got {type(name).__name__!r}"
        )
    if not isinstance(description, str):
        raise ValueError(
            f"description must be a str, got {type(description).__name__!r}"
        )
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )
    for i, ac in enumerate(acceptance_criteria):
        if not isinstance(ac, str):
            raise ValueError(
                f"acceptance_criteria[{i}] must be a str, got {type(ac).__name__!r}"
            )


def select_spec_sections(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> dict[str, str]:
    """Pick which spec sections matter for a given feature.

    Phase 1 of the Self-Discover meta-agent loop: classify each canonical
    spec section as REQUIRED, OPTIONAL, or SKIP based on feature name,
    description, and ACs.

    Each section in the canonical 8-section PRD schema is classified as one of:

    - ``REQUIRED`` — extractor must fill this slot.
    - ``OPTIONAL`` — extractor should attempt; critic does not penalize if absent.
    - ``SKIP``     — extractor leaves null; critic ignores entirely.

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
        Mapping of section_name → "REQUIRED" | "OPTIONAL" | "SKIP" for
        all 8 sections in the canonical module set.

    Raises
    ------
    ValueError
        When any argument has an invalid type.
    """
    _validate_inputs(feature_id, name, description, acceptance_criteria)
    section_map = select_sections(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
    )
    logger.debug(
        "select_spec_sections: feature_id=%r sections=%r",
        feature_id,
        section_map,
    )
    return section_map


def run_focused_extraction(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> dict[str, Any]:
    """Run a focused extraction pass driven by per-feature section selection.

    Implements the two-phase Self-Discover meta-agent loop from ICML 2024,
    Section 7:

    Phase 1 — Section selection: call :func:`select_spec_sections` to
    determine which sections are REQUIRED, OPTIONAL, or SKIP.

    Phase 2 — Focused extraction: produce an extraction result dict that
    includes the section_map decision and a filtered view of the ACs,
    enabling downstream critics to skip sections classified as SKIP.

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
    dict[str, Any]
        A result dict with the following keys:

        - ``feature_id``      : echoed back for traceability.
        - ``section_map``     : per-section REQUIRED/OPTIONAL/SKIP classification.
        - ``filtered_acs``    : ACs passed through unmodified (filtering is
                                section-level, not AC-level).
        - ``skipped_sections``: list of section names classified as SKIP.
        - ``active_sections`` : list of section names that are REQUIRED or OPTIONAL.

    Raises
    ------
    ValueError
        When any argument has an invalid type (delegated from
        :func:`select_spec_sections`).
    """
    section_map = select_spec_sections(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
    )

    validate_output_schema(section_map)

    skipped_sections = [
        section for section, label in section_map.items() if label == "SKIP"
    ]
    active_sections = [
        section for section, label in section_map.items() if label != "SKIP"
    ]

    logger.debug(
        "run_focused_extraction: feature_id=%r active=%r skipped=%r",
        feature_id,
        active_sections,
        skipped_sections,
    )

    return {
        "feature_id": feature_id,
        "section_map": section_map,
        "filtered_acs": list(acceptance_criteria),
        "skipped_sections": skipped_sections,
        "active_sections": active_sections,
    }


#: Alias satisfying AC: ``Function defined: bob.meta_agent_selector.focused_extract``.
focused_extract = run_focused_extraction
