"""Coordinator for the research-as-documentarian pipeline (BF-2).

The coordinator is responsible for:
  1. Dispatching the researcher sub-agent (which never sees ticket/intent text).
  2. Merging the researcher's notes with the feature intent stub.
  3. Passing the merged context to the implementer sub-agent.

The core invariant is the hide-the-ticket pattern: the researcher receives
ONLY the target subsystem path glob and a symbol shortlist — no intent text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def merge_research_and_intent(
    research_notes: str,
    intent_stub: str,
    *,
    feature_id: str = "",
    research_notes_path: str | Path | None = None,
) -> dict[str, Any]:
    """Merge researcher output with the feature intent stub for the implementer.

    The researcher sub-agent produces research_notes without seeing the ticket.
    This function combines those notes with the intent_stub so the implementer
    sub-agent receives the full picture.

    Args:
        research_notes:      Raw text of research_notes.md written by researcher.
        intent_stub:         Feature description / ticket text the implementer needs.
        feature_id:          UUID of the feature (informational, included in output).
        research_notes_path: Optional path where notes were loaded from (for audit).

    Returns:
        dict with keys:
            merged_context     — combined string ready for implementer dispatch
            research_notes     — the original researcher output (str)
            intent_stub        — the original intent text (str)
            feature_id         — as supplied
            research_notes_path — str path if supplied, else ""

    Raises:
        ValueError: If research_notes or intent_stub are not strings.
    """
    if not isinstance(research_notes, str):
        raise ValueError(
            f"research_notes must be a str, got {type(research_notes).__name__!r}"
        )
    if not isinstance(intent_stub, str):
        raise ValueError(
            f"intent_stub must be a str, got {type(intent_stub).__name__!r}"
        )

    notes_path_str = str(research_notes_path) if research_notes_path is not None else ""

    separator = "\n\n" + "=" * 72 + "\n"

    merged_parts = []
    if research_notes.strip():
        merged_parts.append(
            "## Codebase Research (documentarian output — written without seeing ticket)\n\n"
            + research_notes
        )
    else:
        merged_parts.append("## Codebase Research\n\n(no research notes available)")

    merged_parts.append(
        "## Feature Intent\n\n" + (intent_stub if intent_stub.strip() else "(no intent provided)")
    )

    merged_context = separator.join(merged_parts)

    return {
        "merged_context": merged_context,
        "research_notes": research_notes,
        "intent_stub": intent_stub,
        "feature_id": feature_id,
        "research_notes_path": notes_path_str,
    }


__all__ = ["merge_research_and_intent"]
