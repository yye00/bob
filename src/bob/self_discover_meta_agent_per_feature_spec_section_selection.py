"""Self-Discover meta-agent for per-feature spec-section selection.

Feature 7e4cff70-0d16-47e8-8965-75213863afa7

bob's PRD schema (F-R7-457) is fixed: every spec must fill every slot.
A meta-agent that first picks WHICH spec sections matter, then drives a
focused extractor pass, beats one-size-fits-all extraction.

Source: Agent 4 Section 7 (Self-Discover, ICML 2024).

Public API::

    from bob.self_discover_meta_agent_per_feature_spec_section_selection import (
        self_discover_meta_agent_per_feature_spec_section_selection,
    )
"""

from __future__ import annotations

import logging
from typing import Any

from bob.spec_quality.section_selector import (
    module_set,
    select_sections,
    validate_output_schema,
)

logger = logging.getLogger(__name__)


def self_discover_meta_agent_per_feature_spec_section_selection(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> dict[str, Any]:
    """Run the Self-Discover meta-agent for per-feature spec-section selection.

    Phase 1 — Section selection: classify each canonical spec section as
    REQUIRED, OPTIONAL, or SKIP based on feature name, description, and ACs.

    Phase 2 — Focused extraction: produce an extraction result dict that
    includes the section_map decision and filters the extractor pass to only
    the sections classified as REQUIRED or OPTIONAL.

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

        - ``feature_id``      : echoed for traceability.
        - ``section_map``     : per-section REQUIRED/OPTIONAL/SKIP classification.
        - ``filtered_acs``    : ACs passed through unmodified.
        - ``skipped_sections``: list of section names classified as SKIP.
        - ``active_sections`` : list of section names that are REQUIRED or OPTIONAL.
    """
    section_map = select_sections(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
    )

    validate_output_schema(section_map)

    skipped_sections = [s for s, v in section_map.items() if v == "SKIP"]
    active_sections = [s for s, v in section_map.items() if v != "SKIP"]

    logger.debug(
        "self_discover_meta_agent_per_feature_spec_section_selection: "
        "feature_id=%r active=%r skipped=%r",
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
