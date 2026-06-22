"""Research notes generation for BF-2 — Research-as-documentarian sub-agent.

Provides generate_research_notes(), the canonical entry point for producing
a structured research_notes.md document from the hide-the-ticket research
protocol.  The researcher sub-agent calls this after surveying the target
subsystem so the coordinator can merge the output with the intent stub for
the implementer.
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


def generate_research_notes(
    *,
    feature_id: str = "",
    path_glob: str = "",
    symbol_shortlist: list[str] | None = None,
    survey_sha: str = "",
    content: str = "",
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Generate a research_notes.md document for a feature subsystem survey.

    This is the primary entry point for the BF-2 documentarian protocol.
    The researcher sub-agent receives ONLY the path glob and symbol shortlist
    (never the ticket/intent text) and writes its findings here.

    When ``content`` is provided and ``feature_id`` is set, the notes are
    written to ``.bob3/features/<feature_id>/research_notes.md`` with a YAML
    frontmatter header encoding the cache key (survey_sha + path_glob).

    Args:
        feature_id:       UUID of the feature being researched (optional).
        path_glob:        Subsystem glob from the localizer, e.g. "src/bob3/**".
        symbol_shortlist: Symbol names from survey.db to focus on.
        survey_sha:       SHA of the survey snapshot; used for cache invalidation.
        content:          The researcher's findings as raw text.  When supplied
                          alongside feature_id, the notes file is written to disk.
        workspace:        Project root directory; defaults to Path(".").

    Returns:
        dict with keys:
            researcher_role    — "researcher"
            hide_intent        — True (invariant: researcher never sees ticket)
            researcher_prompt  — prompt fragment sent to the researcher sub-agent
            output_path        — str path where research_notes.md was (or would be) written
            cache_hit          — True when cached notes were reused
            written            — True if the notes file was actually written this call
            content            — the notes content (raw text)
            feature_id         — as supplied
            path_glob          — as supplied
            symbol_shortlist   — as supplied (or [])

    Raises:
        ValueError: If symbol_shortlist contains non-string elements.
        TypeError:  If workspace cannot be coerced to a Path.
    """
    symbols: list[str] = symbol_shortlist if symbol_shortlist is not None else []

    if workspace is not None and not isinstance(workspace, (str, Path)):
        raise TypeError(
            f"workspace must be a str, Path, or None, got {type(workspace).__name__!r}"
        )

    # Validate symbol_shortlist element types
    for sym in symbols:
        if not isinstance(sym, str):
            raise ValueError(
                f"symbol_shortlist elements must be str, got {type(sym).__name__!r}"
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

    # Write notes to disk when content + feature_id are provided and no cache hit
    written = False
    if content and feature_id and not cache_hit:
        notes_path_obj = research_notes_path(feature_id, workspace)
        notes_path_obj.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = (
            "---\n"
            f"survey_sha: {survey_sha or 'unknown'}\n"
            f"path_glob: {path_glob or ''}\n"
            "---\n\n"
        )
        notes_path_obj.write_text(frontmatter + content, encoding="utf-8")
        written = True

    return {
        "researcher_role": RESEARCHER.name,
        "hide_intent": RESEARCHER.hide_intent,
        "researcher_prompt": prompt,
        "output_path": output_path_str,
        "cache_hit": cache_hit,
        "written": written,
        "content": content,
        "feature_id": feature_id,
        "path_glob": path_glob,
        "symbol_shortlist": symbols,
    }


__all__ = ["generate_research_notes"]
