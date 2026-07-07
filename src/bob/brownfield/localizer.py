"""BF-4 — Hierarchical Localizer: file → class/symbol → edit-site.

Agentless-style localization pipeline. Given a feature intent, narrows to
(file, symbol, lineno) before any code-write subagent fires.

Pipeline:
  Stage A — file shortlist:  BM25 over survey.db symbol/docstring/path text
  Stage B — symbol shortlist: pagerank * cosine similarity score, top-K
  Stage C — edit-site:        emit (path, start_line, end_line, scope)

Persists localization as a JSON blob to feature.localization (via
add_localization migration). Coordinator uses check_disjoint() to serialize
features that overlap on (path, scope).
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# BM25 constants
# ---------------------------------------------------------------------------

_K1 = 1.5
_B = 0.75


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric boundaries."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _tokens_from_intent(intent: dict[str, Any]) -> list[str]:
    parts = [
        intent.get("capability", ""),
        intent.get("target_subsystem", ""),
        " ".join(intent.get("keywords", [])),
    ]
    return _tokenize(" ".join(parts))


def _build_corpus(symbols: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Build a {path: [tokens]} corpus by concatenating all symbol text per file."""
    corpus: dict[str, list[str]] = defaultdict(list)
    for sym in symbols:
        text = " ".join([
            sym.get("name", ""),
            sym.get("docstring", ""),
            sym.get("path", ""),
        ])
        corpus[sym["path"]].extend(_tokenize(text))
    return dict(corpus)


def _bm25_scores(
    query_tokens: list[str],
    corpus: dict[str, list[str]],
) -> dict[str, float]:
    """Compute BM25 scores for each document in corpus against query_tokens."""
    if not query_tokens or not corpus:
        return {}

    # IDF computation
    N = len(corpus)
    df: dict[str, int] = defaultdict(int)
    avgdl = sum(len(doc) for doc in corpus.values()) / N if N > 0 else 1.0

    for doc_tokens in corpus.values():
        for term in set(doc_tokens):
            df[term] += 1

    scores: dict[str, float] = {}
    for path, doc_tokens in corpus.items():
        dl = len(doc_tokens)
        tf_map: dict[str, int] = defaultdict(int)
        for t in doc_tokens:
            tf_map[t] += 1

        score = 0.0
        for term in query_tokens:
            tf = tf_map.get(term, 0)
            if tf == 0:
                continue
            idf = math.log((N - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5) + 1)
            numerator = tf * (_K1 + 1)
            denominator = tf + _K1 * (1 - _B + _B * dl / avgdl)
            score += idf * numerator / denominator

        scores[path] = score

    return scores


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between two term-frequency vectors."""
    dot = sum(vec_a.get(t, 0.0) * v for t, v in vec_b.items())
    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _tf_vector(tokens: list[str]) -> dict[str, float]:
    vec: dict[str, float] = defaultdict(float)
    for t in tokens:
        vec[t] += 1.0
    return dict(vec)


# ---------------------------------------------------------------------------
# Stage A — file shortlist
# ---------------------------------------------------------------------------


def _shortlist_files(
    symbols: list[dict[str, Any]],
    intent: dict[str, Any],
    top_k: int,
) -> list[str]:
    """BM25 file shortlist. Returns at most top_k file paths."""
    if not symbols:
        return []

    query_tokens = _tokens_from_intent(intent)
    if not query_tokens:
        # No query → return top files by average pagerank
        path_pr: dict[str, list[float]] = defaultdict(list)
        for sym in symbols:
            path_pr[sym["path"]].append(sym.get("pagerank", 0.0))
        ranked = sorted(path_pr.keys(), key=lambda p: sum(path_pr[p]) / len(path_pr[p]), reverse=True)
        return ranked[:top_k]

    corpus = _build_corpus(symbols)
    scores = _bm25_scores(query_tokens, corpus)

    ranked = sorted(scores.keys(), key=lambda p: scores[p], reverse=True)
    return ranked[:top_k]


# ---------------------------------------------------------------------------
# Stage B — symbol shortlist (rank_symbols_by_intent)
# ---------------------------------------------------------------------------


def rank_symbols_by_intent(
    symbols: list[dict[str, Any]],
    intent: dict[str, Any],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Rank symbols by pagerank(symbol) * cosine(symbol.text, intent.text).

    Args:
        symbols: List of symbol dicts with keys: id, path, kind, name,
                 lineno, end_lineno, pagerank, docstring.
        intent:  Dict with capability, target_subsystem, keywords.
        top_k:   Maximum number of symbols to return.

    Returns:
        List of symbol dicts with an added 'score' key, sorted descending.
    """
    if not symbols:
        return []

    query_tokens = _tokens_from_intent(intent)
    query_vec = _tf_vector(query_tokens) if query_tokens else {}

    ranked: list[dict[str, Any]] = []
    for sym in symbols:
        sym_text = " ".join([
            sym.get("name", ""),
            sym.get("docstring", ""),
        ])
        sym_tokens = _tokenize(sym_text)
        sym_vec = _tf_vector(sym_tokens)

        cosine = _cosine_similarity(query_vec, sym_vec) if query_vec else 0.0
        pagerank = float(sym.get("pagerank", 0.0))

        # Combined score: pagerank component * 0.4 + cosine component * 0.6
        # Pagerank is already normalised [0,1] in BF-1; cosine is [0,1].
        score = pagerank * 0.4 + cosine * 0.6

        ranked.append({**sym, "score": score})

    ranked.sort(key=lambda s: s["score"], reverse=True)
    return ranked[:top_k]


# ---------------------------------------------------------------------------
# Stage C — edit-site extraction
# ---------------------------------------------------------------------------


def extract_edit_sites(
    ranked_symbols: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Emit edit-site tuples for each ranked symbol.

    Args:
        ranked_symbols: Output of rank_symbols_by_intent.

    Returns:
        List of edit-site dicts: {path, start_line, end_line, scope, name}.
    """
    sites: list[dict[str, Any]] = []
    for sym in ranked_symbols:
        kind = sym.get("kind", "function")
        if kind == "class":
            scope = "class"
        elif kind in ("function", "method"):
            scope = "function"
        else:
            scope = "module"

        start_line = int(sym.get("lineno", 1))
        end_lineno = sym.get("end_lineno")
        if end_lineno is not None:
            end_line = int(end_lineno)
        else:
            # Fallback: assume a modest block of 20 lines
            end_line = start_line + 20

        if end_line < start_line:
            end_line = start_line

        sites.append({
            "path": sym["path"],
            "start_line": start_line,
            "end_line": end_line,
            "scope": scope,
            "name": sym.get("name", ""),
        })
    return sites


# ---------------------------------------------------------------------------
# Main pipeline: localize
# ---------------------------------------------------------------------------


def localize(
    intent: dict[str, Any],
    *,
    survey_db: Optional[Path] = None,
    top_k_files: int = 15,
    top_k_symbols: int = 5,
) -> dict[str, Any]:
    """Full hierarchical localization pipeline.

    Stages:
      A. File shortlist via BM25 (top_k_files).
      B. Symbol shortlist via pagerank * cosine (top_k_symbols).
      C. Edit-site extraction.

    Args:
        intent:       Dict with capability, target_subsystem, keywords.
        survey_db:    Path to survey.db. If absent or nonexistent, returns empty.
        top_k_files:  Max files in shortlist (Stage A).
        top_k_symbols: Max symbols in shortlist (Stage B).

    Returns:
        Dict with keys:
          files:      list[str]  — shortlisted file paths
          symbols:    list[dict] — ranked symbol dicts with score
          edit_sites: list[dict] — edit-site tuples {path, start_line, end_line, scope}
    """
    empty: dict[str, Any] = {"files": [], "symbols": [], "edit_sites": []}

    if survey_db is None or not Path(survey_db).exists():
        return empty

    try:
        all_symbols = _load_symbols(survey_db)
    except Exception:
        return empty

    if not all_symbols:
        return empty

    # Stage A — file shortlist
    shortlisted_files = _shortlist_files(all_symbols, intent, top_k=top_k_files)

    # Stage B — symbol shortlist (only from shortlisted files)
    candidate_symbols = [s for s in all_symbols if s["path"] in shortlisted_files]
    if not candidate_symbols:
        # Fallback: rank across all symbols
        candidate_symbols = all_symbols

    ranked_symbols = rank_symbols_by_intent(candidate_symbols, intent, top_k=top_k_symbols)

    # Stage C — edit sites
    edit_sites = extract_edit_sites(ranked_symbols)

    return {
        "files": shortlisted_files,
        "symbols": ranked_symbols,
        "edit_sites": edit_sites,
    }


def _load_symbols(db_path: Path) -> list[dict[str, Any]]:
    """Load all symbols from survey.db."""
    conn = sqlite3.connect(str(db_path))
    try:
        # Probe whether end_lineno column exists
        cols = {row[1] for row in conn.execute("PRAGMA table_info(symbols)").fetchall()}
        if "end_lineno" in cols and "docstring" in cols:
            rows = conn.execute(
                "SELECT id, path, kind, name, lineno, end_lineno, pagerank, docstring "
                "FROM symbols"
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "path": r[1],
                    "kind": r[2],
                    "name": r[3],
                    "lineno": r[4],
                    "end_lineno": r[5],
                    "pagerank": r[6] or 0.0,
                    "docstring": r[7] or "",
                }
                for r in rows
            ]
        elif "docstring" in cols:
            rows = conn.execute(
                "SELECT id, path, kind, name, lineno, pagerank, docstring "
                "FROM symbols"
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "path": r[1],
                    "kind": r[2],
                    "name": r[3],
                    "lineno": r[4],
                    "end_lineno": None,
                    "pagerank": r[5] or 0.0,
                    "docstring": r[6] or "",
                }
                for r in rows
            ]
        else:
            rows = conn.execute(
                "SELECT id, path, kind, name, lineno, pagerank "
                "FROM symbols"
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "path": r[1],
                    "kind": r[2],
                    "name": r[3],
                    "lineno": r[4],
                    "end_lineno": None,
                    "pagerank": r[5] or 0.0,
                    "docstring": "",
                }
                for r in rows
            ]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Disjointness check (Step 7 in spec)
# ---------------------------------------------------------------------------


def check_disjoint(
    loc_a: dict[str, Any],
    loc_b: dict[str, Any],
) -> bool:
    """Return True if loc_a and loc_b have overlapping edit sites.

    Two edit sites overlap when they share the same path AND their line
    ranges intersect: max(a.start, b.start) <= min(a.end, b.end).

    Args:
        loc_a: localize() result dict with 'edit_sites' key.
        loc_b: localize() result dict with 'edit_sites' key.

    Returns:
        True if they overlap (not disjoint), False if they are disjoint.
    """
    sites_a = loc_a.get("edit_sites", [])
    sites_b = loc_b.get("edit_sites", [])

    for a in sites_a:
        for b in sites_b:
            if a["path"] != b["path"]:
                continue
            # Line range overlap: [a.start, a.end] ∩ [b.start, b.end] non-empty
            if max(a["start_line"], b["start_line"]) <= min(a["end_line"], b["end_line"]):
                return True

    return False


# ---------------------------------------------------------------------------
# Coordinator integration helpers
# ---------------------------------------------------------------------------


def localize_and_persist(
    feature_id: str,
    intent: dict[str, Any],
    *,
    survey_db: Optional[Path] = None,
    top_k_files: int = 15,
    top_k_symbols: int = 5,
) -> dict[str, Any]:
    """Run localize() and persist the result to feature.localization via update_feature.

    This is the coordinator-facing entry point. It returns the localization dict
    and stores it as JSON in feature.localization.

    Args:
        feature_id:    Feature UUID.
        intent:        Intent dict from the feature spec.
        survey_db:     Path to survey.db.
        top_k_files:   Stage A budget.
        top_k_symbols: Stage B budget.

    Returns:
        The localization dict {files, symbols, edit_sites}.
    """
    result = localize(intent, survey_db=survey_db, top_k_files=top_k_files, top_k_symbols=top_k_symbols)

    try:
        from bob.db import update_feature
        update_feature(feature_id, localization=json.dumps(result))
    except Exception:
        pass  # DB update is best-effort; localization result is still returned

    return result


# ---------------------------------------------------------------------------
# Public API aliases required by AC naming convention
# ---------------------------------------------------------------------------

#: Aliases for AC-specified names and convenience callers.
rank_symbols = rank_symbols_by_intent
find_edit_sites = extract_edit_sites

# Cross-TU coupled edit-site expansion (C++ substrate). Re-exported so callers
# can go from a localized C++ symbol to the full linked group of header
# declaration + definition + overrides that must move together.
from bob.brownfield.coupled_edit_sites import (  # noqa: E402
    derive_decl_end_line,
    expand_coupled_edit_sites,
)

#: AC-required: bob.brownfield.localizer.localize_intent
localize_intent = localize

#: AC-required: bob.brownfield.localizer.localize_feature
localize_feature = localize

#: AC-required: bob.brownfield.localizer.rank_files_by_relevance
rank_files_by_relevance = _shortlist_files

#: AC-required: bob.brownfield.localizer.rank_symbols_by_relevance
rank_symbols_by_relevance = rank_symbols_by_intent


def rank_symbols_in_file(
    symbols: list[dict[Any, Any]],
    intent: dict[str, Any],
    file_path: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Rank symbols within a specific file by intent relevance.

    Stage B helper: filters symbols to those in file_path, then ranks by
    pagerank * cosine(symbol.text, intent.text).

    Args:
        symbols: List of symbol dicts from survey.db.
        intent:  Intent dict with capability, target_subsystem, keywords.
        file_path: Path to filter symbols to.
        top_k:   Maximum number of symbols to return.

    Returns:
        List of symbol dicts with 'score' key, sorted descending.
    """
    file_symbols = [s for s in symbols if s.get("path") == file_path]
    return rank_symbols_by_intent(file_symbols, intent, top_k=top_k)

#: AC-required: bob.brownfield.localizer.check_disjoint_write_surfaces
check_disjoint_write_surfaces = check_disjoint

#: AC-required: bob.brownfield.localizer.check_disjointness
check_disjointness = check_disjoint


def rank_files(
    symbols: list[dict[Any, Any]],
    intent: dict[str, Any],
    top_k: int = 15,
) -> list[str]:
    """Public alias for Stage A file shortlist via BM25.

    Args:
        symbols: List of symbol dicts from survey.db.
        intent:  Intent dict with capability, target_subsystem, keywords.
        top_k:   Maximum number of file paths to return.

    Returns:
        List of file paths sorted by BM25 score descending.
    """
    return _shortlist_files(symbols, intent, top_k=top_k)


def rank_files_by_intent(
    symbols: list[dict[Any, Any]],
    intent: dict[str, Any],
    top_k: int = 15,
) -> list[str]:
    """Stage A file shortlist via BM25, ranked by intent.

    AC-required name alias for _shortlist_files.

    Args:
        symbols: List of symbol dicts from survey.db.
        intent:  Intent dict with capability, target_subsystem, keywords.
        top_k:   Maximum number of file paths to return.

    Returns:
        List of file paths sorted by BM25 score descending.
    """
    return _shortlist_files(symbols, intent, top_k=top_k)


def hierarchical_localize(
    intent: dict[str, Any],
    *,
    survey_db: Optional[Path] = None,
    top_k_files: int = 15,
    top_k_symbols: int = 5,
) -> dict[str, Any]:
    """Full three-stage hierarchical localization pipeline.

    AC-required entry point. Alias for localize() with the canonical name.

    Args:
        intent:        Dict with capability, target_subsystem, keywords.
        survey_db:     Path to survey.db. If absent or nonexistent, returns empty.
        top_k_files:   Max files in shortlist (Stage A).
        top_k_symbols: Max symbols in shortlist (Stage B).

    Returns:
        Dict with keys:
          files:      list[str]  — shortlisted file paths
          symbols:    list[dict] — ranked symbol dicts with score
          edit_sites: list[dict] — edit-site tuples {path, start_line, end_line, scope}
    """
    return localize(intent, survey_db=survey_db, top_k_files=top_k_files, top_k_symbols=top_k_symbols)


# ---------------------------------------------------------------------------
# Localizer class (AC: bob.brownfield.localizer.Localizer)
# ---------------------------------------------------------------------------


class Localizer:
    """Hierarchical localizer: file → class/symbol → edit-site.

    Wraps the three-stage BM25 + pagerank*cosine localization pipeline.
    Instantiate with an optional survey_db path and call localize() with
    an intent dict to get {files, symbols, edit_sites}.
    """

    def __init__(
        self,
        survey_db: Optional[Path] = None,
        *,
        top_k_files: int = 15,
        top_k_symbols: int = 5,
    ) -> None:
        self._survey_db = survey_db
        self._top_k_files = top_k_files
        self._top_k_symbols = top_k_symbols

    def localize(self, intent: dict[str, Any]) -> dict[str, Any]:
        """Run the hierarchical localization pipeline for the given intent.

        Args:
            intent: Dict with optional keys: capability, target_subsystem, keywords.

        Returns:
            Dict with keys: files, symbols, edit_sites.
        """
        return localize(
            intent,
            survey_db=self._survey_db,
            top_k_files=self._top_k_files,
            top_k_symbols=self._top_k_symbols,
        )
