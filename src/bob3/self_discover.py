"""Self-Discover meta-agent for per-feature spec-section selection.

Feature d322b8cc-e778-44b7-b355-ff93dc155fc6

bob3's PRD schema (F-R7-457) is fixed: every spec must fill every slot.
A meta-agent that first picks WHICH spec sections matter, then drives a
focused extractor pass, beats one-size-fits-all extraction.

Source: Agent 4 Section 7 (Self-Discover, ICML 2024).

Public API::

    from bob3.self_discover import (
        select_spec_sections,
        focused_extractor_pass,
    )
"""

from __future__ import annotations

import logging
from typing import Any

from bob3.spec_quality.section_selector import (
    module_set,
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

    Each section in the canonical PRD schema is classified as one of:

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
        all sections in the canonical module set.

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


def run_focused_extractor(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> dict[str, Any]:
    """Run a focused extractor pass driven by per-feature section selection.

    First calls :func:`select_spec_sections` to determine which sections are
    relevant. Then produces an extraction result dict that includes the
    section_map decision and a filtered view of the ACs — enabling downstream
    critics to skip sections classified as SKIP.

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
        When any argument has an invalid type.
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


# Alias matching the public API documented in this module's docstring.
focused_extractor_pass = run_focused_extractor


class SelfDiscoverAgent:
    """Meta-agent that selects relevant spec sections then runs a focused extractor.

    Implements the Self-Discover pattern (ICML 2024 Agent 4 Section 7):
    first determine WHICH spec sections matter for a given feature, then
    drive a focused extractor pass limited to those sections.

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
    """

    def __init__(
        self,
        feature_id: str,
        name: str,
        description: str,
        acceptance_criteria: list[str],
    ) -> None:
        _validate_inputs(feature_id, name, description, acceptance_criteria)
        self.feature_id = feature_id
        self.name = name
        self.description = description
        self.acceptance_criteria = list(acceptance_criteria)

    def select_sections(self) -> dict[str, str]:
        """Return REQUIRED/OPTIONAL/SKIP classification for each spec section."""
        return select_spec_sections(
            feature_id=self.feature_id,
            name=self.name,
            description=self.description,
            acceptance_criteria=self.acceptance_criteria,
        )

    def run(self) -> dict[str, Any]:
        """Execute the Self-Discover meta-agent: select sections then extract.

        Returns
        -------
        dict[str, Any]
            Same structure as :func:`run_focused_extractor`.
        """
        return run_focused_extractor(
            feature_id=self.feature_id,
            name=self.name,
            description=self.description,
            acceptance_criteria=self.acceptance_criteria,
        )
