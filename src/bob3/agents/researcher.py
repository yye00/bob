"""Researcher sub-agent for BF-2 — Research-as-documentarian (hide-the-ticket pattern).

This module implements the researcher sub-agent that surveys an existing
codebase WITHOUT seeing the feature ticket or intent text.  Showing the
ticket causes confirmation bias; the researcher must document what the code
actually does, not what someone intends to change.

Protocol (BF-2):
  1. Coordinator calls ``dispatch`` with only path_glob + symbol_shortlist.
  2. Researcher prompt is built from ``bob3.agents.roles.build_researcher_prompt``
     (no ticket text included).
  3. Research output is written to .bob3/features/<id>/research_notes.md.
  4. Coordinator merges research_notes.md with the intent stub before
     dispatching the implementer sub-agent.
  5. Research is cached: same survey sha + same path glob => skip re-research.

Elicitation link (F-R7-605): the researcher's output is what the elicitation
classifier diffs against the user prompt to compute ambiguity_score.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.agents.roles import (
    RESEARCHER,
    Role,
    build_researcher_prompt,
    research_notes_path,
    should_skip_research,
)


def dispatch(
    *,
    feature_id: str,
    path_glob: str,
    symbol_shortlist: list[str],
    survey_sha: str = "",
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Build the researcher dispatch payload for the coordinator.

    The payload contains the rendered prompt (no intent text), the output
    path for research_notes.md, and a cache_hit flag so the coordinator
    can skip dispatching the sub-agent when notes are already fresh.

    Args:
        feature_id:       UUID of the feature being researched.
        path_glob:        Subsystem path glob from the localizer.
        symbol_shortlist: Symbol names from survey.db to focus on.
        survey_sha:       SHA of the survey.db snapshot (cache key).
        workspace:        Project root; defaults to Path(".").

    Returns:
        dict with keys:
            role        — the RESEARCHER Role descriptor
            prompt      — researcher prompt string (no ticket text)
            output_path — str path to write research_notes.md
            cache_hit   — True when prior notes can be reused
    """
    if not isinstance(symbol_shortlist, list):
        raise TypeError(
            f"symbol_shortlist must be a list, got {type(symbol_shortlist).__name__!r}"
        )

    root = Path(workspace).resolve() if workspace else Path(".").resolve()
    notes_path = research_notes_path(feature_id, root)

    cache_hit = False
    if survey_sha and path_glob:
        cache_hit = should_skip_research(feature_id, survey_sha, path_glob, root)

    prompt = build_researcher_prompt(path_glob, symbol_shortlist)

    return {
        "role": RESEARCHER,
        "prompt": prompt,
        "output_path": str(notes_path),
        "cache_hit": cache_hit,
    }


def get_role() -> Role:
    """Return the researcher Role descriptor."""
    return RESEARCHER


def research_subsystem(
    *,
    feature_id: str,
    path_glob: str,
    symbol_shortlist: list[str],
    survey_sha: str = "",
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Orchestrate the research phase for a feature subsystem.

    Implements the hide-the-ticket protocol: builds a researcher prompt that
    contains ONLY the path glob and symbol shortlist (no intent/ticket text),
    checks the cache to avoid redundant re-research, and returns the dispatch
    payload for the coordinator.

    This is the canonical entry point for the coordinator to call when it
    needs research notes for a given subsystem.

    Args:
        feature_id:       UUID of the feature being researched.
        path_glob:        Subsystem path glob from the localizer.
        symbol_shortlist: Symbol names from survey.db to focus on.
        survey_sha:       SHA of the survey.db snapshot (cache key).
        workspace:        Project root; defaults to Path(".").

    Returns:
        dict with keys:
            role        — the RESEARCHER Role descriptor
            prompt      — researcher prompt string (no ticket text)
            output_path — str path to write research_notes.md
            cache_hit   — True when prior notes can be reused
            feature_id  — as supplied

    Raises:
        ValueError: If feature_id or path_glob is an empty string.
        TypeError:  If symbol_shortlist is not a list.
    """
    if not feature_id:
        raise ValueError("feature_id must be a non-empty string")
    if not path_glob:
        raise ValueError("path_glob must be a non-empty string")
    if not isinstance(symbol_shortlist, list):
        raise TypeError(
            f"symbol_shortlist must be a list, got {type(symbol_shortlist).__name__!r}"
        )

    payload = dispatch(
        feature_id=feature_id,
        path_glob=path_glob,
        symbol_shortlist=symbol_shortlist,
        survey_sha=survey_sha,
        workspace=workspace,
    )
    payload["feature_id"] = feature_id
    return payload


def run_researcher(
    *,
    feature_id: str,
    path_glob: str,
    symbol_shortlist: list[str],
    survey_sha: str = "",
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Run the research phase for a feature — canonical AC-facing entry point.

    Alias for ``research_subsystem`` with identical semantics.  This name is
    required by the feature AC: "Function defined: bob3.agents.researcher.run_researcher".

    Args:
        feature_id:       UUID of the feature being researched.
        path_glob:        Subsystem path glob from the localizer.
        symbol_shortlist: Symbol names from survey.db to focus on.
        survey_sha:       SHA of the survey.db snapshot (cache key).
        workspace:        Project root; defaults to Path(".").

    Returns:
        dict with keys role, prompt, output_path, cache_hit, feature_id.

    Raises:
        ValueError: If feature_id or path_glob is an empty string.
        TypeError:  If symbol_shortlist is not a list.
    """
    return research_subsystem(
        feature_id=feature_id,
        path_glob=path_glob,
        symbol_shortlist=symbol_shortlist,
        survey_sha=survey_sha,
        workspace=workspace,
    )


def dispatch_researcher(
    *,
    feature_id: str,
    path_glob: str,
    symbol_shortlist: list[str],
    survey_sha: str = "",
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Build the researcher dispatch payload — AC-facing alias for dispatch().

    Identical to ``dispatch`` but uses the name required by the feature AC:
    "Function defined: bob3.agents.researcher.dispatch_researcher".

    Args:
        feature_id:       UUID of the feature being researched.
        path_glob:        Subsystem path glob from the localizer.
        symbol_shortlist: Symbol names from survey.db to focus on.
        survey_sha:       SHA of the survey.db snapshot (cache key).
        workspace:        Project root; defaults to Path(".").

    Returns:
        dict with keys role, prompt, output_path, cache_hit.
    """
    return dispatch(
        feature_id=feature_id,
        path_glob=path_glob,
        symbol_shortlist=symbol_shortlist,
        survey_sha=survey_sha,
        workspace=workspace,
    )


__all__ = [
    "dispatch",
    "dispatch_researcher",
    "get_role",
    "research_subsystem",
    "run_researcher",
    "RESEARCHER",
]
