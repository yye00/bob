"""Self-Discover selector — per-feature spec-section selection.

Feature e10c6a19-fb0f-4d55-bfdd-743253367c61

bob3's PRD schema (F-R7-457) is fixed: every spec must fill every slot.
This module provides a meta-agent pass that first picks WHICH spec sections
matter, then drives a focused extractor pass — beating one-size-fits-all.

Source: Agent 4 Section 7 (Self-Discover, ICML 2024).

Public API::

    from bob3.self_discover_selector import select_spec_sections

    section_map = select_spec_sections(
        feature_id="abc-123",
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py"],
    )
    # section_map: {"functional": "REQUIRED", "perf": "SKIP", ...}

Integration with bob3.spec_critic
----------------------------------
Pass ``section_map`` into the spec critic so it only evaluates the sections
that are relevant to the feature::

    from bob3.spec_critic import SpecCritic
    from bob3.self_discover_selector import select_spec_sections

    section_map = select_spec_sections(feature_id, name, description, acs)
    critic = SpecCritic()
    result = critic.critique(feature_id, name, description, acs,
                             section_map=section_map)
"""

from __future__ import annotations

import logging
from typing import Any

from bob3.spec_quality.section_selector import (
    module_set,
    select_sections,
    validate_output_schema,
)

__all__ = ["select_spec_sections", "run_focused_extractor"]

logger = logging.getLogger(__name__)


def _validate_inputs(
    feature_id: object,
    name: object,
    description: object,
    acceptance_criteria: object,
) -> None:
    if not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a str, got {type(feature_id).__name__!r}"
        )
    if not isinstance(name, str):
        raise ValueError(f"name must be a str, got {type(name).__name__!r}")
    if not isinstance(description, str):
        raise ValueError(
            f"description must be a str, got {type(description).__name__!r}"
        )
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, "
            f"got {type(acceptance_criteria).__name__!r}"
        )
    for i, ac in enumerate(acceptance_criteria):
        if not isinstance(ac, str):
            raise ValueError(
                f"acceptance_criteria[{i}] must be a str, "
                f"got {type(ac).__name__!r}"
            )


def select_spec_sections(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> dict[str, str]:
    """Pick which spec sections matter for a given feature.

    Each section in the canonical PRD schema is classified as one of:

    - ``REQUIRED`` — extractor must fill this slot.
    - ``OPTIONAL`` — extractor should attempt; critic does not penalize if absent.
    - ``SKIP``     — extractor leaves null; critic ignores entirely.

    The ``functional`` section is always ``REQUIRED``.

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
        every section in :func:`bob3.spec_quality.section_selector.module_set`.

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

    validate_output_schema(section_map)

    logger.debug(
        "select_spec_sections: feature_id=%r active=%r skipped=%r",
        feature_id,
        [s for s, v in section_map.items() if v != "SKIP"],
        [s for s, v in section_map.items() if v == "SKIP"],
    )

    return section_map


def run_focused_extractor(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> dict[str, Any]:
    """Run a focused extractor pass driven by per-feature section selection.

    First calls :func:`select_spec_sections` to determine which sections are
    relevant. Returns an extraction result dict that includes the section_map
    decision and a filtered view of the ACs — enabling downstream critics to
    skip sections classified as SKIP.

    Parameters
    ----------
    feature_id:
        Unique feature identifier.
    name:
        Short feature name.
    description:
        Feature description.
    acceptance_criteria:
        List of AC strings.

    Returns
    -------
    dict[str, Any]
        A result dict with the following keys:

        - ``feature_id``      : echoed back for traceability.
        - ``section_map``     : per-section REQUIRED/OPTIONAL/SKIP classification.
        - ``filtered_acs``    : ACs passed through unmodified (filtering is
                                section-level, not AC-level).
        - ``skipped_sections``: list of section names classified as SKIP.

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

    skipped_sections = [
        section for section, label in section_map.items() if label == "SKIP"
    ]

    logger.debug(
        "run_focused_extractor: feature_id=%r skipped=%r",
        feature_id,
        skipped_sections,
    )

    return {
        "feature_id": feature_id,
        "section_map": section_map,
        "filtered_acs": list(acceptance_criteria),
        "skipped_sections": skipped_sections,
    }
