"""Self-Discover meta-agent for per-feature spec-section selection.

Feature 1b00605c-e105-4f07-bfa5-5f813f9c38ef

bob's PRD schema (F-R7-457) is fixed: every spec must fill every slot.
A meta-agent that first picks WHICH spec sections matter, then drives a
focused extractor pass, beats one-size-fits-all extraction.

Source: Agent 4 Section 7 (Self-Discover, ICML 2024).

Public API::

    from bob.meta_agent import (
        select_spec_sections,
        SelfDiscoverMetaAgent,
    )

Integration
-----------
Delegates to :mod:`bob.spec_quality.section_selector` for section
classification and integrates with :mod:`bob.spec_quality.spec_extractor`
for extraction-time section pruning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from bob.spec_quality.section_selector import (
    select_sections,
    validate_output_schema,
)
from bob.spec_quality.spec_extractor import extract_acs

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


@dataclass
class SelfDiscoverMetaAgent:
    """Self-Discover meta-agent: per-feature spec-section selector and focused extractor.

    Implements the two-phase Self-Discover loop from ICML 2024, Section 7:

    Phase 1 — Section selection: classify each canonical spec section as
    REQUIRED, OPTIONAL, or SKIP based on feature name, description, and ACs.

    Phase 2 — Focused extraction: run the spec extractor only on REQUIRED
    and OPTIONAL sections, skipping SKIP sections entirely. The extraction
    result integrates with :mod:`bob.spec_quality.spec_extractor`.

    Attributes
    ----------
    feature_id:
        Unique feature identifier.
    name:
        Short feature name.
    description:
        Feature description text.
    acceptance_criteria:
        List of AC strings from the spec.
    """

    feature_id: str
    name: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_inputs(
            self.feature_id,
            self.name,
            self.description,
            self.acceptance_criteria,
        )

    def select_sections(self) -> dict[str, str]:
        """Run Phase 1: classify each spec section as REQUIRED, OPTIONAL, or SKIP.

        Returns
        -------
        dict[str, str]
            Section classification map.
        """
        return select_spec_sections(
            feature_id=self.feature_id,
            name=self.name,
            description=self.description,
            acceptance_criteria=self.acceptance_criteria,
        )

    def run(self) -> dict[str, Any]:
        """Run both phases: section selection followed by focused extraction.

        Integrates with :mod:`bob.spec_quality.spec_extractor` for the
        extraction phase, using section_map to filter the extractor pass.

        Returns
        -------
        dict[str, Any]
            Result dict with keys:

            - ``feature_id``       : echoed back for traceability.
            - ``section_map``      : per-section classification.
            - ``filtered_acs``     : extracted and normalised ACs.
            - ``skipped_sections`` : section names classified as SKIP.
        """
        section_map = self.select_sections()
        validate_output_schema(section_map)

        skipped_sections = [
            section for section, label in section_map.items() if label == "SKIP"
        ]

        filtered_acs = extract_acs(
            feature_id=self.feature_id,
            name=self.name,
            description=self.description,
            acceptance_criteria=self.acceptance_criteria,
        )

        logger.debug(
            "SelfDiscoverMetaAgent.run: feature_id=%r skipped=%r",
            self.feature_id,
            skipped_sections,
        )

        return {
            "feature_id": self.feature_id,
            "section_map": section_map,
            "filtered_acs": filtered_acs,
            "skipped_sections": skipped_sections,
        }
