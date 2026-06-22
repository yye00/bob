"""BF-1 — Brownfield Survey/Index (tree-sitter symbol graph + SQLite + PageRank).

Brownfield prerequisite: before bob3 can edit an existing repo it needs a
queryable map of what's already there.

Build on the Aider/Augment pattern:
  tree-sitter parse → symbol graph (defs/refs/imports) →
  SQLite cache keyed by (path, sha) →
  PageRank-ranked node ordering for context-budget triage.

This module provides the canonical entry point
``bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite`` which
orchestrates a full or incremental brownfield survey and returns a structured
summary of the results.

The heavy lifting is implemented in bob3.brownfield.survey (build_survey /
refresh_survey).  This thin façade:
  - accepts a workspace path (and optional db_path override),
  - delegates to build_survey or refresh_survey as appropriate,
  - returns a well-typed result dict suitable for AC verification.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.brownfield.survey import build_survey, refresh_survey


def bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
    workspace: Path | str | None = None,
    *,
    db_path: Path | str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Run a brownfield survey and return a structured result summary.

    Args:
        workspace:  Root directory of the repo to survey.  Defaults to cwd.
        db_path:    Explicit path for survey.db.  When omitted the survey
                    is written to <workspace>/.bob3/survey.db.
        refresh:    When True, perform an incremental update (re-parse only
                    files whose mtime/sha changed).  When False (default)
                    do a full rebuild.

    Returns:
        dict with keys:
            workspace         — resolved workspace path (str)
            db_path           — resolved path to survey.db (str)
            mode              — "full" or "incremental"
            implicit_features — list of candidate feature dicts
                                (name, path, lineno, docstring, kind)
            feature_count     — int count of implicit feature candidates
            ok                — True (raises on real failure)

    Raises:
        ValueError: if workspace does not exist or is not a directory.
    """
    if workspace is None:
        root = Path(".").resolve()
    else:
        root = Path(workspace).resolve()

    if not root.exists():
        raise ValueError(f"workspace does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"workspace is not a directory: {root}")

    resolved_db: Path | None = None
    if db_path is not None:
        resolved_db = Path(db_path).resolve()

    if refresh:
        candidates = refresh_survey(root, db_path=resolved_db)
        mode = "incremental"
    else:
        candidates = build_survey(root, db_path=resolved_db)
        mode = "full"

    if resolved_db is None:
        resolved_db = root / ".bob3" / "survey.db"

    return {
        "workspace": str(root),
        "db_path": str(resolved_db),
        "mode": mode,
        "implicit_features": candidates,
        "feature_count": len(candidates),
        "ok": True,
    }


__all__ = ["bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite"]
