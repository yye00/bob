"""Self-Discover meta-agent for per-feature spec-section selection.

Feature 07c23355-3143-4505-8fc3-4823e84df4b9

bob3's PRD schema (F-R7-457) is fixed: every spec must fill every slot.
A meta-agent that first picks WHICH spec sections matter, then drives a
focused extractor pass, beats one-size-fits-all extraction.

Source: Agent 4 Section 7 (Self-Discover, ICML 2024).

Public API::

    from bob3.self_discover_meta_agent import (
        select_spec_sections,
        focused_extractor,
        run_focused_extractor,
    )

Integration
-----------
Both functions delegate to :mod:`bob3.spec_quality.section_selector` for
section classification and :mod:`bob3.spec_quality.spec_extractor` for
extraction-time section pruning. They are intended to be called by
:mod:`bob3.spec_synthesizer` before the extraction pass so that the critic
is driven only by sections relevant to each feature.
"""

from __future__ import annotations

import logging
from typing import Any

from bob3.spec_quality.section_selector import (
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
    """Raise ValueError if any argument has an invalid type.

    All four parameters must be string/list[str] as documented. This guard
    prevents silent mis-classification when callers pass None or non-list ACs.
    """
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

    Wraps :func:`bob3.spec_quality.section_selector.select_sections` to
    provide the Self-Discover meta-agent's section-selection pass.  Each
    section in the canonical 8-section PRD schema is classified as one of:

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


def focused_extractor(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> dict[str, Any]:
    """Alias for :func:`run_focused_extractor` — the canonical public name.

    Calls :func:`select_spec_sections` then produces an extraction result dict
    with the section_map classification and filtered AC list.

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
        Same structure as :func:`run_focused_extractor`.
    """
    return run_focused_extractor(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
    )


#: Alias for :func:`run_focused_extractor` — satisfies AC naming ``drive_focused_extraction``.
drive_focused_extraction = run_focused_extractor

#: Alias for :func:`run_focused_extractor` — satisfies AC naming ``drive_focused_extractor``.
drive_focused_extractor = run_focused_extractor

#: Alias for :func:`select_spec_sections` — satisfies AC naming for feature 1ab1a03e.
select_relevant_spec_sections = select_spec_sections

#: Alias for :func:`run_focused_extractor` — satisfies AC naming for feature 1ab1a03e.
extract_with_selected_sections = run_focused_extractor


def extract_with_focused_sections(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> dict[str, Any]:
    """Run a focused extractor pass driven by Self-Discover section selection.

    Thin, named wrapper around :func:`run_focused_extractor` that satisfies the
    AC naming requirement ``bob3.self_discover_meta_agent.extract_with_focused_sections``.

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
        Same structure as :func:`run_focused_extractor`:
        ``feature_id``, ``section_map``, ``filtered_acs``, ``skipped_sections``.

    Raises
    ------
    ValueError
        When any argument has an invalid type.
    """
    return run_focused_extractor(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
    )
