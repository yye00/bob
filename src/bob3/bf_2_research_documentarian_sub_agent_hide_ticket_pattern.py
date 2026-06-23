"""BF-2 — Research-as-documentarian sub-agent (hide-the-ticket pattern).

Dex Horthy / HumanLayer brownfield key tactic: when researching an existing
codebase to add a feature, the research sub-agent must NOT see the
ticket/intent text.  Showing the ticket causes confirmation bias — the
researcher finds evidence that supports the ticket rather than documenting
what the code actually does.

Protocol enforced by this module:

  1. The 'researcher' role in src/bob3/agents/roles.py has hide_intent=True.
  2. The researcher prompt template includes ONLY:
       - the target_subsystem path glob (from the localizer)
       - the survey.db symbol shortlist
       - instruction: "Document what this code does, its callers, its
         invariants, and any inconsistencies.  Do NOT speculate about
         what changes might be needed."
  3. Output is written to .bob3/features/<id>/research_notes.md.
  4. The coordinator merges research_notes.md + intent stub for the
     implementer sub-agent (which DOES see both).
  5. Research is cached: same survey sha + same path glob => skip
     re-research.

Elicitation link (F-R7-605): the researcher's output is what the
elicitation classifier diffs against the user prompt to compute
ambiguity_score.

This module provides the canonical entry point
``bf_2_research_documentarian_sub_agent_hide_ticket_pattern`` which returns
a structured summary of the hide-the-ticket protocol, suitable for use by the
coordinator and for AC verification.
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


def bf_2_research_documentarian_sub_agent_hide_ticket_pattern(
    *,
    feature_id: str = "",
    survey_sha: str = "",
    path_glob: str = "",
    symbol_shortlist: list[str] | None = None,
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Return a summary of the hide-the-ticket research protocol for BF-2.

    When called without arguments (e.g., for AC verification), returns a
    static summary of the protocol with the researcher role descriptor and
    the constraint that hide_intent is True.

    When called with feature_id / survey_sha / path_glob, also checks
    whether the cache can be reused (should_skip_research) and builds the
    researcher prompt that will be dispatched.

    Args:
        feature_id:       UUID of the feature being researched (optional).
        survey_sha:       SHA of the survey.db snapshot (optional).
        path_glob:        Subsystem path glob from the localizer (optional).
        symbol_shortlist: Symbol names from survey.db to focus on (optional).
        workspace:        Project root path; defaults to Path(".").

    Returns:
        dict with keys:
            role               — dict describing the researcher role
            hide_intent        — True (invariant: researcher never sees ticket)
            cacheable          — True (same survey sha + glob => skip re-research)
            output_path        — str path for research_notes.md (if feature_id given)
            cache_hit          — bool (True if prior notes can be reused)
            researcher_prompt  — str prompt fragment for the researcher (if path_glob given)
            protocol_steps     — list of str summarising the 5-step protocol
    """
    symbols = symbol_shortlist or []
    root = Path(workspace).resolve() if workspace else Path(".").resolve()

    role_dict = {
        "name": RESEARCHER.name,
        "hide_intent": RESEARCHER.hide_intent,
        "output_key": RESEARCHER.output_key,
        "description": RESEARCHER.description,
        "cacheable": RESEARCHER.cacheable,
    }

    output_path = ""
    cache_hit = False
    if feature_id:
        notes_path = research_notes_path(feature_id, root)
        output_path = str(notes_path)
        if survey_sha and path_glob:
            cache_hit = should_skip_research(feature_id, survey_sha, path_glob, root)

    researcher_prompt = ""
    if path_glob:
        researcher_prompt = build_researcher_prompt(path_glob, symbols)

    protocol_steps = [
        "Coordinator extracts target_subsystem path glob from the localizer.",
        "Researcher receives ONLY the path glob + survey.db symbol shortlist (hide_intent=True).",
        "Researcher writes findings to .bob3/features/<id>/research_notes.md.",
        "Coordinator merges research_notes.md + intent stub for the implementer (sees both).",
        "Research is cached: same survey sha + same path glob => skip re-research.",
    ]

    return {
        "role": role_dict,
        "hide_intent": RESEARCHER.hide_intent,
        "cacheable": RESEARCHER.cacheable,
        "output_path": output_path,
        "cache_hit": cache_hit,
        "researcher_prompt": researcher_prompt,
        "protocol_steps": protocol_steps,
    }


__all__ = ["bf_2_research_documentarian_sub_agent_hide_ticket_pattern"]
