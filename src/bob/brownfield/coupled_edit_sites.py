"""BF-4 C++ substrate — Cross-TU coupled edit-site expansion.

BF-4's localizer (``localizer.py``) emits an edit-site as a single
``(path, start_line, end_line)`` block and, when ``end_lineno`` is absent,
falls back to ``start_line + 20`` — a Python-shaped guess that is wrong for
C++ and only ever names one file.

For C++, changing a function signature almost always requires a coordinated
edit in the header declaration AND every implementation/override. Given a
localized C++ symbol, ``expand_coupled_edit_sites`` uses the clangd index to
expand one logical change into the full set of coupled edit-sites:

  * the declaration in the header (``.h`` / ``.hpp``),
  * the definition in the ``.cc`` / ``.hip``,
  * every overriding definition (via ``overrides`` edges / LSP
    ``textDocument/implementation``),

deriving accurate ``end_line`` from clang's decl source range instead of the
``+20`` heuristic. The result is a *linked edit-site group* so the
code-writing subagent is told up-front that a header plus N implementations
must move together — preventing the classic failure of editing the ``.cpp``
signature while leaving the header declaration stale (a compile break).
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = ["expand_coupled_edit_sites", "derive_decl_end_line"]

#: Legacy Python-shaped heuristic span, used only when clang gives no range.
_DEFAULT_FALLBACK_SPAN = 20


def _range_end_line(decl: dict[str, Any]) -> Optional[int]:
    """Extract the end line from a clang decl's source range, if present.

    Accepts either a nested clang extent (``{"range": {"end": {"line": N}}}``
    or ``{"extent": {"end": {"line": N}}}``) or a flat ``end_line`` /
    ``end_lineno`` key.
    """
    for flat_key in ("end_line", "end_lineno"):
        val = decl.get(flat_key)
        if val is not None:
            return int(val)

    for range_key in ("range", "extent"):
        rng = decl.get(range_key)
        if isinstance(rng, dict):
            end = rng.get("end")
            if isinstance(end, dict) and end.get("line") is not None:
                return int(end["line"])
    return None


def _range_begin_line(decl: dict[str, Any]) -> Optional[int]:
    for flat_key in ("lineno", "line", "start_line"):
        val = decl.get(flat_key)
        if val is not None:
            return int(val)
    for range_key in ("range", "extent"):
        rng = decl.get(range_key)
        if isinstance(rng, dict):
            begin = rng.get("begin") or rng.get("start")
            if isinstance(begin, dict) and begin.get("line") is not None:
                return int(begin["line"])
    return None


def derive_decl_end_line(
    decl: dict[str, Any],
    start_line: Optional[int] = None,
    *,
    fallback_span: int = _DEFAULT_FALLBACK_SPAN,
) -> int:
    """Derive the end line of a declaration from clang's source range.

    Prefers an explicit clang extent (``range``/``extent`` end line, or a flat
    ``end_line``/``end_lineno`` key). When no range is available, falls back to
    ``start_line + fallback_span`` (the legacy Python heuristic). The result is
    never less than ``start_line``.

    Args:
        decl:          A clang decl / index entry dict.
        start_line:    The declaration's start line. If omitted, it is read
                       from the decl's begin range.
        fallback_span: Number of lines to add to ``start_line`` when no clang
                       range is present.

    Returns:
        The end line as an int.

    Raises:
        ValueError: If ``decl`` is not a dict, ``start_line`` is negative, or
            no start line can be determined (neither passed nor in the decl).
    """
    if not isinstance(decl, dict):
        raise ValueError(f"decl must be a dict, got {type(decl).__name__}")

    if start_line is None:
        start_line = _range_begin_line(decl)
        if start_line is None:
            raise ValueError(
                "start_line not provided and decl has no begin range"
            )

    if isinstance(start_line, bool) or not isinstance(start_line, int):
        raise ValueError("start_line must be an int")
    if start_line < 0:
        raise ValueError(f"start_line must be non-negative, got {start_line}")

    end = _range_end_line(decl)
    if end is None:
        end = start_line + fallback_span

    if end < start_line:
        end = start_line
    return end


def _lookup_index_entry(
    index: dict[str, Any], sym: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Find the clangd index entry for a symbol, by USR then by qualified name."""
    for key in ("usr", "id"):
        usr = sym.get(key)
        if usr is not None and usr in index:
            return index[usr]
    name = sym.get("name")
    if name is not None and name in index:
        return index[name]
    return None


def _make_site(
    entry: dict[str, Any], role: str, group_id: str, *, fallback_span: int
) -> Optional[dict[str, Any]]:
    """Build one edit-site dict from a clang index entry (decl/def/override)."""
    if not isinstance(entry, dict):
        return None
    path = entry.get("path")
    if not path:
        return None
    start = _range_begin_line(entry)
    if start is None:
        start = 1
    end = derive_decl_end_line(entry, start, fallback_span=fallback_span)
    return {
        "path": path,
        "start_line": start,
        "end_line": end,
        "role": role,
        "group_id": group_id,
    }


def expand_coupled_edit_sites(
    symbol: dict[str, Any],
    *,
    index: Optional[dict[str, Any]] = None,
    fallback_span: int = _DEFAULT_FALLBACK_SPAN,
) -> dict[str, Any]:
    """Expand a localized C++ symbol into a linked group of coupled edit-sites.

    Given one logical change (a signature edit on ``symbol``), consult the
    clangd ``index`` to surface every edit-site that must move together: the
    header declaration, the ``.cc``/``.hip`` definition, and every overriding
    definition. Each site carries an accurate ``end_line`` derived from clang's
    decl source range and a shared ``group_id``.

    When no index is supplied (or the symbol is absent from it), a single
    uncoupled edit-site is returned for the symbol itself — matching the
    original single-block behaviour.

    Args:
        symbol:        Localized symbol dict. Requires ``path`` and ``lineno``;
                       ``usr``/``id``/``name`` are used to look up the index.
        index:         Optional clangd index mapping USR (or qualified name) →
                       ``{declaration, definition, overrides:[...]}``.
        fallback_span: Legacy line span used when a decl has no clang range.

    Returns:
        A dict:
          ``sites``                    — list of edit-site dicts
          ``coupled``                  — bool, True if >1 distinct site
          ``requires_coordinated_edit``— alias of ``coupled``
          ``group_id``                 — shared id linking the sites
          ``symbol``                   — the qualified name of the symbol

    Raises:
        ValueError: If ``symbol`` is not a dict, is missing ``path`` or
            ``lineno``, ``lineno`` is not a non-negative int, or ``index`` is
            not a dict.
    """
    if not isinstance(symbol, dict):
        raise ValueError(
            f"symbol must be a dict, got {type(symbol).__name__}"
        )
    path = symbol.get("path")
    if not path:
        raise ValueError("symbol must have a non-empty 'path'")
    lineno = symbol.get("lineno")
    if lineno is None:
        raise ValueError("symbol must have a 'lineno'")
    if isinstance(lineno, bool) or not isinstance(lineno, int):
        raise ValueError("symbol 'lineno' must be an int")
    if lineno < 0:
        raise ValueError(f"symbol 'lineno' must be non-negative, got {lineno}")
    if index is not None and not isinstance(index, dict):
        raise ValueError(
            f"index must be a dict, got {type(index).__name__}"
        )

    name = symbol.get("name", "")
    group_id = f"coupled::{name or path}::{lineno}"

    entry = _lookup_index_entry(index, symbol) if index else None

    if not entry:
        # No index / no match → single uncoupled site for the symbol itself.
        end = derive_decl_end_line(
            symbol, int(lineno), fallback_span=fallback_span
        )
        return {
            "symbol": name,
            "group_id": group_id,
            "coupled": False,
            "requires_coordinated_edit": False,
            "sites": [
                {
                    "path": path,
                    "start_line": int(lineno),
                    "end_line": end,
                    "role": "definition",
                    "group_id": group_id,
                }
            ],
        }

    sites: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()

    def _add(entry_dict: Any, role: str) -> None:
        site = _make_site(
            entry_dict, role, group_id, fallback_span=fallback_span
        )
        if site is None:
            return
        key = (site["path"], site["start_line"], site["end_line"])
        if key in seen:
            return
        seen.add(key)
        sites.append(site)

    _add(entry.get("declaration"), "declaration")
    _add(entry.get("definition"), "definition")
    for override in entry.get("overrides", []) or []:
        _add(override, "override")

    if not sites:
        # Entry present but empty → degrade to single uncoupled site.
        end = derive_decl_end_line(
            symbol, int(lineno), fallback_span=fallback_span
        )
        sites.append(
            {
                "path": path,
                "start_line": int(lineno),
                "end_line": end,
                "role": "definition",
                "group_id": group_id,
            }
        )

    coupled = len(sites) > 1
    return {
        "symbol": name,
        "group_id": group_id,
        "coupled": coupled,
        "requires_coordinated_edit": coupled,
        "sites": sites,
    }
