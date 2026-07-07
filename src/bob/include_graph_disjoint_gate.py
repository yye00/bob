"""Include-graph-aware disjoint-surface gate for the coordinator.

The base :func:`bob.brownfield.localizer.check_disjoint` decides two features
are safe to run in parallel when their edit-sites never share a ``path`` whose
``[start_line, end_line]`` ranges intersect. That model is line-range-only and
misses the dominant conflict mode in C/C++:

  * Two features edit *different* ``.cpp`` files but both ``#include`` the same
    header (e.g. a core RCCL public header). Editing that header from one
    feature can break the other's compilation, yet a line-range check calls the
    surfaces disjoint and bob dispatches them concurrently.

This module extends disjointness to be *compilation-graph aware*:

  1. Two edit-site groups conflict if they touch the **same header**.
  2. They conflict if one edits a **header** the other's translation unit
     ``#include``\\ s (consulted via ``include_graph``).
  3. They conflict if they touch different definitions of the **same USR**
     (unified symbol resolution id) — the same logical symbol in two files.
  4. They conflict across a **header/impl pair** (``foo.h`` <-> ``foo.cpp``).

:func:`flag_high_fanout_header` uses per-feature blast-radius / include fan-out
to flag high-fan-out header edits for single-threaded execution or tighter
review.

Public API
----------
check_disjoint_include_aware(loc_a, loc_b, *, include_graph, header_impl_pairs)
    Return True when the two localizations conflict (NOT safe to parallelize).
flag_high_fanout_header(edit_sites, *, include_graph, blast_radius, threshold)
    Return the subset of header edit-sites whose fan-out exceeds ``threshold``.
"""

from __future__ import annotations

from typing import Any

__all__ = ["check_disjoint_include_aware", "flag_high_fanout_header"]

#: Suffixes treated as C/C++ header files.
_HEADER_SUFFIXES = (".h", ".hpp", ".hh", ".hxx", ".h++", ".inl", ".ipp", ".cuh")


def _is_header(path: str) -> bool:
    p = path.lower()
    return any(p.endswith(suf) for suf in _HEADER_SUFFIXES)


def _ranges_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return max(a["start_line"], b["start_line"]) <= min(a["end_line"], b["end_line"])


def _paths(sites: list[dict[str, Any]]) -> set[str]:
    return {s["path"] for s in sites if "path" in s}


def check_disjoint_include_aware(
    loc_a: dict[str, Any],
    loc_b: dict[str, Any],
    *,
    include_graph: dict[str, list[str]] | None = None,
    header_impl_pairs: dict[str, str] | None = None,
) -> bool:
    """Return True if loc_a and loc_b conflict (unsafe to run concurrently).

    Extends the line-range disjointness check with compilation-graph awareness.
    Two localizations conflict when ANY of the following hold:

      * same path with intersecting line ranges (base behavior);
      * both touch the same header file;
      * one edits a header that a TU edited by the other ``#include``\\ s
        (from ``include_graph``: maps TU path -> list of included headers);
      * both touch the same USR (``usr`` key on an edit-site);
      * they touch a matched header/impl pair (``header_impl_pairs``).

    Args:
        loc_a: localize() result dict with an ``edit_sites`` list.
        loc_b: localize() result dict with an ``edit_sites`` list.
        include_graph: Optional map of TU path -> list of ``#include``\\ d headers.
        header_impl_pairs: Optional map of header path -> impl path (or vice
            versa) pairing headers with their implementation files.

    Returns:
        True if they conflict (not disjoint), False if safe to parallelize.

    Raises:
        ValueError: If loc_a/loc_b are not dicts, or include_graph /
            header_impl_pairs are provided but not dicts.
    """
    if not isinstance(loc_a, dict):
        raise ValueError(f"loc_a must be a dict, got {type(loc_a).__name__!r}")
    if not isinstance(loc_b, dict):
        raise ValueError(f"loc_b must be a dict, got {type(loc_b).__name__!r}")
    if include_graph is not None and not isinstance(include_graph, dict):
        raise ValueError(
            f"include_graph must be a dict, got {type(include_graph).__name__!r}"
        )
    if header_impl_pairs is not None and not isinstance(header_impl_pairs, dict):
        raise ValueError(
            f"header_impl_pairs must be a dict, got {type(header_impl_pairs).__name__!r}"
        )

    sites_a = loc_a.get("edit_sites", []) or []
    sites_b = loc_b.get("edit_sites", []) or []

    # 1. Base line-range overlap on shared paths.
    for a in sites_a:
        for b in sites_b:
            if a.get("path") == b.get("path") and _ranges_overlap(a, b):
                return True

    paths_a = _paths(sites_a)
    paths_b = _paths(sites_b)

    # 2. Both touch the same header (any line range).
    for p in paths_a & paths_b:
        if _is_header(p):
            return True

    # 3. One edits a header included by a TU the other edits.
    if include_graph:
        headers_a = {p for p in paths_a if _is_header(p)}
        headers_b = {p for p in paths_b if _is_header(p)}
        # A edits a header that a TU in B includes.
        for tu in paths_b:
            for hdr in include_graph.get(tu, []):
                if hdr in headers_a:
                    return True
        # symmetric: B edits a header a TU in A includes.
        for tu in paths_a:
            for hdr in include_graph.get(tu, []):
                if hdr in headers_b:
                    return True

    # 4. Header/impl pairing coupling.
    if header_impl_pairs:
        for hdr, impl in header_impl_pairs.items():
            pair = {hdr, impl}
            if (paths_a & pair) and (paths_b & pair):
                return True

    # 5. Same USR touched from different definitions.
    usrs_a = {s["usr"] for s in sites_a if s.get("usr")}
    usrs_b = {s["usr"] for s in sites_b if s.get("usr")}
    if usrs_a & usrs_b:
        return True

    return False


def flag_high_fanout_header(
    edit_sites: list[dict[str, Any]],
    *,
    include_graph: dict[str, list[str]] | None = None,
    blast_radius: dict[str, int] | None = None,
    threshold: int = 5,
) -> list[dict[str, Any]]:
    """Flag header edit-sites with high include fan-out for serialized execution.

    A header ``#include``\\ d by many translation units is a high-risk edit:
    changing it can break compilation across the whole tree. Such edits should
    run single-threaded (or receive tighter review) rather than in parallel.

    Fan-out for a header is either:
      * the explicit ``blast_radius[path]`` if supplied, else
      * the number of TUs in ``include_graph`` that include the header.

    Args:
        edit_sites: List of edit-site dicts (each with a ``path``).
        include_graph: Optional map of TU path -> list of included headers.
        blast_radius: Optional precomputed per-file blast-radius scores; takes
            precedence over include_graph counting when present for a path.
        threshold: Fan-out strictly greater than this flags the header
            (default 5).

    Returns:
        List of dicts ``{"path", "fanout", "single_threaded"}`` for each header
        edit-site whose fan-out exceeds ``threshold``, ordered by descending
        fan-out.

    Raises:
        ValueError: If edit_sites is not a list, include_graph/blast_radius are
            not dicts, or threshold is negative.
    """
    if not isinstance(edit_sites, list):
        raise ValueError(
            f"edit_sites must be a list, got {type(edit_sites).__name__!r}"
        )
    if include_graph is not None and not isinstance(include_graph, dict):
        raise ValueError(
            f"include_graph must be a dict, got {type(include_graph).__name__!r}"
        )
    if blast_radius is not None and not isinstance(blast_radius, dict):
        raise ValueError(
            f"blast_radius must be a dict, got {type(blast_radius).__name__!r}"
        )
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 0:
        raise ValueError(f"threshold must be a non-negative int, got {threshold!r}")

    include_graph = include_graph or {}
    blast_radius = blast_radius or {}

    # Precompute include fan-out per header from the graph.
    graph_fanout: dict[str, int] = {}
    for tu, headers in include_graph.items():
        for hdr in headers:
            graph_fanout[hdr] = graph_fanout.get(hdr, 0) + 1

    flagged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for site in edit_sites:
        path = site.get("path")
        if not path or path in seen or not _is_header(path):
            continue
        seen.add(path)

        if path in blast_radius:
            fanout = int(blast_radius[path])
        else:
            fanout = graph_fanout.get(path, 0)

        if fanout > threshold:
            flagged.append(
                {"path": path, "fanout": fanout, "single_threaded": True}
            )

    flagged.sort(key=lambda f: f["fanout"], reverse=True)
    return flagged
