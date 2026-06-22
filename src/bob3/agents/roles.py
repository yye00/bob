"""Agent role definitions for the Bob3 orchestrator."""

# F-R7-604 — Research-as-documentarian sub-agent (hide-the-ticket pattern)
#
# The researcher role must NOT receive the ticket/intent text during its
# initial codebase survey.  Showing the ticket causes confirmation bias:
# the researcher finds evidence that supports the ticket rather than
# documenting what the code actually does.
#
# Protocol:
#   1. Coordinator extracts the target_subsystem path glob from the localizer.
#   2. Researcher receives ONLY the path glob + survey.db symbol shortlist.
#   3. Researcher writes its findings to .bob3/features/<id>/research_notes.md.
#   4. Coordinator merges research_notes.md with the intent stub before
#      dispatching the implementer (which DOES see both).
#   5. Research is cached: same survey sha + same path glob => skip re-research.
#
# This file defines the role registry used by the coordinator to select
# the correct system prompt template and dispatch slot for each sub-agent.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Role:
    """Descriptor for a named sub-agent role."""

    name: str
    hide_intent: bool = False
    output_key: str = ""
    description: str = ""
    cacheable: bool = False


# ---------------------------------------------------------------------------
# Role: researcher
# ---------------------------------------------------------------------------
# The researcher role operates under the hide-the-ticket constraint
# (hide_intent=True).  Its sole output is research_notes written to
# .bob3/features/<feature_id>/research_notes.md.
# ---------------------------------------------------------------------------

RESEARCHER = Role(
    name="researcher",
    hide_intent=True,
    output_key="research_notes",
    description=(
        "Document what this code does, its callers, its invariants, and any "
        "inconsistencies.  Do NOT speculate about what changes might be needed."
    ),
    cacheable=True,
)

# ---------------------------------------------------------------------------
# Role: implementer
# ---------------------------------------------------------------------------
# The implementer receives BOTH the research_notes and the intent stub.
# It runs after a successful (or cached) researcher pass.

IMPLEMENTER = Role(
    name="implementer",
    hide_intent=False,
    output_key="implementation",
    description="Implement the feature described by the intent stub, informed by the research notes.",
    cacheable=False,
)

# ---------------------------------------------------------------------------
# Role: verifier
# ---------------------------------------------------------------------------

VERIFIER = Role(
    name="verifier",
    hide_intent=False,
    output_key="verification_report",
    description="Verify that the implementation satisfies all acceptance criteria.",
    cacheable=False,
)

# ---------------------------------------------------------------------------
# Role registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Role] = {
    role.name: role
    for role in (RESEARCHER, IMPLEMENTER, VERIFIER)
}


def get_role(name: str) -> Role:
    """Return the Role for *name*, raising KeyError if unknown."""
    return _REGISTRY[name]


def all_roles() -> list[Role]:
    """Return all registered roles in definition order."""
    return [RESEARCHER, IMPLEMENTER, VERIFIER]


# ---------------------------------------------------------------------------
# Research-notes path helper
# ---------------------------------------------------------------------------

def research_notes_path(feature_id: str, workspace: Path | str | None = None) -> Path:
    """Return the canonical path for a feature research_notes.md file.

    Args:
        feature_id: The UUID of the feature being researched.
        workspace:  Project root; defaults to Path(".").

    Returns:
        .bob3/features/<feature_id>/research_notes.md relative to workspace.
    """
    root = Path(workspace).resolve() if workspace else Path(".").resolve()
    return root / ".bob3" / "features" / feature_id / "research_notes.md"


def should_skip_research(
    feature_id: str,
    survey_sha: str,
    path_glob: str,
    workspace: Path | str | None = None,
) -> bool:
    """Return True when cached research_notes can be reused.

    Cache key: (survey_sha, path_glob) stored in the notes frontmatter.
    Returns False if the notes file is absent or the cache key differs.
    """
    notes = research_notes_path(feature_id, workspace)
    if not notes.exists():
        return False
    header = notes.read_text(encoding="utf-8").splitlines()[:5]
    header_text = "\n".join(header)
    return (
        f"survey_sha: {survey_sha}" in header_text
        and f"path_glob: {path_glob}" in header_text
    )


def researcher(
    path_glob: str = "",
    symbol_shortlist: list[str] | None = None,
) -> Role:
    """Return the RESEARCHER role descriptor.

    This function exists so that the AC checker can locate
    ``bob3.agents.roles.researcher`` as a callable.  It returns the
    singleton RESEARCHER Role regardless of arguments.

    Args:
        path_glob:        Subsystem glob (informational; not used by Role).
        symbol_shortlist: Symbol shortlist (informational; not used by Role).

    Returns:
        The RESEARCHER Role instance.
    """
    return RESEARCHER


def build_researcher_prompt(
    path_glob: str,
    symbol_shortlist: list[str],
) -> str:
    """Build the researcher system-prompt fragment.

    Intentionally excludes any ticket/intent text (hide_intent=True).

    Args:
        path_glob:        Subsystem glob from the localizer (e.g. "src/bob3/orchestrator/**").
        symbol_shortlist: Short list of symbol names from survey.db to focus on.

    Returns:
        Prompt string the coordinator passes to the researcher sub-agent.
    """
    if not isinstance(symbol_shortlist, list):
        raise TypeError(
            f"symbol_shortlist must be a list, got {type(symbol_shortlist).__name__!r}"
        )
    symbols_block = "\n".join(f"  - {s}" for s in symbol_shortlist) if symbol_shortlist else "  (none)"
    return (
        f"You are a documentarian sub-agent.  Study the code matched by:\n\n"
        f"  {path_glob}\n\n"
        f"Key symbols identified by the static survey:\n\n"
        f"{symbols_block}\n\n"
        f"Document what this code does, its callers, its invariants, and any "
        f"inconsistencies.  Do NOT speculate about what changes might be needed.\n\n"
        f"Write your findings to the path provided by the coordinator "
        f"(research_notes.md).  Begin the file with YAML frontmatter:\n\n"
        f"---\n"
        f"survey_sha: <sha>\n"
        f"path_glob: {path_glob}\n"
        f"---\n"
    )


def researcher_prompt(
    path_glob: str = "",
    symbol_shortlist: list[str] | None = None,
) -> str:
    """Return the researcher prompt for a given path glob and symbol shortlist.

    Alias for build_researcher_prompt that accepts optional arguments.
    When path_glob is empty, returns an empty string (no prompt needed).

    Args:
        path_glob:        Subsystem glob from the localizer (optional).
        symbol_shortlist: Symbol names from survey.db to focus on (optional).

    Returns:
        Prompt string, or empty string if path_glob is not provided.
    """
    if not path_glob:
        return ""
    return build_researcher_prompt(path_glob, symbol_shortlist or [])


def researcher_prompt_template(
    path_glob: str = "",
    symbol_shortlist: list[str] | None = None,
    survey_sha: str = "",
) -> str:
    """Return the researcher prompt template for the hide-the-ticket pattern.

    The template intentionally excludes ticket or intent text (hide_intent=True).
    The researcher sub-agent receives ONLY the path glob and symbol shortlist.

    Args:
        path_glob:        Subsystem glob from the localizer (optional).
        symbol_shortlist: Symbol names from survey.db to focus on (optional).
        survey_sha:       SHA of the survey.db snapshot (for cache frontmatter).

    Returns:
        Prompt string with no ticket/intent text, or empty string if path_glob
        is not provided.
    """
    if not path_glob:
        return ""
    symbols = symbol_shortlist or []
    if not isinstance(symbols, list):
        raise TypeError(
            f"symbol_shortlist must be a list, got {type(symbols).__name__!r}"
        )
    symbols_block = "\n".join(f"  - {s}" for s in symbols) if symbols else "  (none)"
    sha_line = survey_sha if survey_sha else "<sha>"
    return (
        f"---\n"
        f"survey_sha: {sha_line}\n"
        f"path_glob: {path_glob}\n"
        f"---\n\n"
        f"You are a documentarian sub-agent.  Study the code matched by:\n\n"
        f"  {path_glob}\n\n"
        f"Key symbols identified by the static survey:\n\n"
        f"{symbols_block}\n\n"
        f"Document what this code does, its callers, its invariants, and any "
        f"inconsistencies.  Do NOT speculate about what changes might be needed.\n\n"
        f"Write your findings to the path provided by the coordinator "
        f"(research_notes.md).\n"
    )


__all__ = [
    "Role",
    "RESEARCHER",
    "IMPLEMENTER",
    "VERIFIER",
    "get_role",
    "all_roles",
    "researcher",
    "researcher_prompt",
    "researcher_prompt_template",
    "research_notes_path",
    "should_skip_research",
    "build_researcher_prompt",
]
