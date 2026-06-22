"""Researcher sub-agent prompt template for BF-2 (hide-the-ticket pattern).

This module exposes the prompt template used by the coordinator when
dispatching the researcher sub-agent.  The template intentionally excludes
any ticket or intent text — the researcher sees ONLY the target subsystem
path glob and the survey.db symbol shortlist.

Usage::

    from bob3.agents.researcher_prompt import render_researcher_prompt

    prompt = render_researcher_prompt(
        path_glob="src/bob3/orchestrator/**",
        symbol_shortlist=["run_loop", "dispatch"],
        survey_sha="abc123",
    )
"""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Template file
# ---------------------------------------------------------------------------

_TEMPLATE_PATH = Path(__file__).parent / "prompts" / "researcher.txt"


def _load_template() -> str:
    """Return the raw template string from prompts/researcher.txt."""
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def render_researcher_prompt(
    *,
    path_glob: str,
    symbol_shortlist: list[str],
    survey_sha: str = "<sha>",
) -> str:
    """Render the researcher prompt for a specific subsystem and symbol set.

    Args:
        path_glob:        Subsystem path glob from the localizer.
        symbol_shortlist: Symbol names from survey.db to focus on.
        survey_sha:       SHA of the survey.db snapshot (for cache frontmatter).

    Returns:
        Rendered prompt string with no ticket/intent text included.

    Raises:
        TypeError: If symbol_shortlist is not a list.
    """
    if not isinstance(symbol_shortlist, list):
        raise TypeError(
            f"symbol_shortlist must be a list, got {type(symbol_shortlist).__name__!r}"
        )
    template = _load_template()
    symbols_block = (
        "\n".join(f"  - {s}" for s in symbol_shortlist)
        if symbol_shortlist
        else "  (none)"
    )
    return template.format(
        path_glob=path_glob,
        symbols_block=symbols_block,
        survey_sha=survey_sha,
    )


__all__ = ["render_researcher_prompt"]
