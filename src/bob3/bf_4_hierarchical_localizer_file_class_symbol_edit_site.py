"""BF-4 — Hierarchical Localizer (file → class/symbol → edit-site).

Agentless-style hierarchical localization. Given an intent stub, narrows
to (file, symbol, lineno) before any code-write subagent fires. Populates
feature.touches / feature.symbols / feature.edit_sites so the coordinator
can enforce disjoint write surfaces.

Pipeline:
  Stage A — file shortlist:  BM25 over survey.db symbol/docstring/path text
  Stage B — symbol shortlist: pagerank * cosine similarity score, top-K
  Stage C — edit-site:        emit (path, start_line, end_line, scope)

This module exposes the canonical entry point
``bf_4_hierarchical_localizer_file_class_symbol_edit_site`` which
orchestrates the three-stage pipeline and returns a structured localization
result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from bob3.brownfield.localizer import (
    check_disjoint,
    extract_edit_sites,
    localize,
    rank_symbols_by_intent,
)


def bf_4_hierarchical_localizer_file_class_symbol_edit_site(
    intent: Optional[dict[str, Any]] = None,
    *,
    survey_db: Optional[Path | str] = None,
    top_k_files: int = 15,
    top_k_symbols: int = 5,
) -> dict[str, Any]:
    """Hierarchical localizer: file → class/symbol → edit-site.

    Given a feature intent, runs the three-stage localization pipeline:

      Stage A — BM25 file shortlist (top_k_files).
      Stage B — pagerank*cosine symbol ranking (top_k_symbols).
      Stage C — edit-site extraction (path, start_line, end_line, scope).

    Boundary conditions:
      - Empty / None intent → returns empty result dict (no crash).
      - Invalid intent (non-dict) → raises ValueError.
      - Missing or nonexistent survey_db → returns empty result dict.

    Args:
        intent:        Feature intent dict with optional keys:
                         capability       (str)
                         target_subsystem (str)
                         keywords         (list[str])
                       None is treated as empty intent.
        survey_db:     Path to survey.db. If None or not found, returns empty.
        top_k_files:   Stage A budget.
        top_k_symbols: Stage B budget.

    Returns:
        Dict with keys:
          files:      list[str]  — shortlisted file paths
          symbols:    list[dict] — ranked symbol dicts with 'score' key
          edit_sites: list[dict] — edit-site dicts {path, start_line, end_line, scope, name}

    Raises:
        ValueError: If intent is provided but is not a dict-like mapping.
    """
    # Reject clearly invalid intent types
    if intent is not None and not isinstance(intent, dict):
        raise ValueError(
            f"intent must be a dict or None, got {type(intent).__name__!r}"
        )

    # Normalise None → empty dict
    if intent is None:
        intent = {}

    # Normalise survey_db to Path
    db_path: Optional[Path] = None
    if survey_db is not None:
        db_path = Path(survey_db)

    return localize(
        intent,
        survey_db=db_path,
        top_k_files=top_k_files,
        top_k_symbols=top_k_symbols,
    )


__all__ = [
    "bf_4_hierarchical_localizer_file_class_symbol_edit_site",
    "check_disjoint",
    "extract_edit_sites",
    "rank_symbols_by_intent",
]
