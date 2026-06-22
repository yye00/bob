"""Research-as-documentarian sub-agent module (BF-2, hide-the-ticket pattern).

This module implements the documentarian protocol described by Dex Horthy /
HumanLayer: the researcher sub-agent must NOT see the ticket/intent text when
surveying an existing codebase.  Confirmation bias causes it to find evidence
that supports the ticket rather than documenting what the code actually does.

The entry point is ``document_subsystem``, which orchestrates the hide-the-ticket
protocol and returns a structured result dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.agents.roles import (
    RESEARCHER,
    build_researcher_prompt,
    research_notes_path,
    should_skip_research,
)


def document_subsystem(
    *,
    feature_id: str = "",
    path_glob: str = "",
    symbol_shortlist: list[str] | None = None,
    survey_sha: str = "",
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Run the documentarian protocol for a target subsystem.

    The researcher sub-agent receives ONLY the path glob and symbol shortlist —
    never the ticket/intent text.  This prevents confirmation bias.

    Args:
        feature_id:       UUID of the feature being researched.
        path_glob:        Subsystem glob from the localizer (e.g. "src/bob3/orchestrator/**").
        symbol_shortlist: Symbol names from survey.db to focus the researcher on.
        survey_sha:       SHA of the survey snapshot; used for cache invalidation.
        workspace:        Project root directory; defaults to Path(".").

    Returns:
        dict with keys:
            hide_intent      — True (the researcher never sees intent text)
            researcher_role  — name of the researcher role ("researcher")
            researcher_prompt — prompt fragment sent to the researcher sub-agent
            output_path      — str path to research_notes.md, or "" if feature_id empty
            cache_hit        — True when cached notes were reused
            protocol_steps   — ordered list of protocol step descriptions
            feature_id       — as supplied
            path_glob        — as supplied
            symbol_shortlist — as supplied (or [])

    Raises:
        TypeError:   If workspace cannot be coerced to a Path.
        ValueError:  If symbol_shortlist contains non-string elements.
    """
    symbols: list[str] = symbol_shortlist if symbol_shortlist is not None else []

    # Validate workspace type early — must be path-like or None
    if workspace is not None and not isinstance(workspace, (str, Path)):
        raise TypeError(
            f"workspace must be a str, Path, or None, got {type(workspace).__name__!r}"
        )

    # Compute output path
    if feature_id:
        notes_path = research_notes_path(feature_id, workspace)
        output_path_str = str(notes_path)
    else:
        output_path_str = ""

    # Check cache
    cache_hit = False
    if feature_id and survey_sha and path_glob:
        cache_hit = should_skip_research(feature_id, survey_sha, path_glob, workspace)

    # Build researcher prompt (hide intent — path_glob + symbols only)
    if path_glob:
        prompt = build_researcher_prompt(path_glob, symbols)
    else:
        prompt = ""

    protocol_steps = [
        "Coordinator extracts target_subsystem path glob from the localizer.",
        "Researcher receives ONLY the path glob + survey.db symbol shortlist (no intent text).",
        "Researcher writes findings to .bob3/features/<id>/research_notes.md.",
        "Coordinator merges research_notes.md with intent stub for the implementer.",
        "Research is cached: same survey sha + same path glob => skip re-research.",
    ]

    return {
        "hide_intent": RESEARCHER.hide_intent,
        "researcher_role": RESEARCHER.name,
        "researcher_prompt": prompt,
        "output_path": output_path_str,
        "cache_hit": cache_hit,
        "protocol_steps": protocol_steps,
        "feature_id": feature_id,
        "path_glob": path_glob,
        "symbol_shortlist": symbols,
    }


__all__ = ["document_subsystem"]
