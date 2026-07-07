"""Header/impl pairing and #include blast-radius graph (feature bd36773c).

C++ splits one logical symbol across a *declaration* in a header (``.h``/``.hpp``/
``.cuh``) and a *definition* in an implementation file (``.cc``/``.cpp``/``.hip``).
bob's BF-1 symbol survey stores one ``path``/``lineno`` per symbol and therefore
treats a header and its ``.cpp`` as unrelated files.  This module adds the missing
C++ notions:

1. ``pair_header_impl`` / ``switch_source_header`` — header<->source pairing via a
   stem-matching heuristic mirroring clangd's ``switchSourceHeader``.
2. ``build_include_graph`` — a preprocessor ``#include`` graph, resolving quoted and
   angle-bracket includes through the ``-I`` search paths declared in
   ``compile_commands.json``.
3. ``compute_blast_radius`` — a per-node blast-radius score: the number of distinct
   downstream files that transitively include the target through the include graph.
   A widely-included public header (e.g. ``rccl.h``) scores high; a leaf ``.cpp``
   scores zero, so touching a core header is never mistaken for a local edit.

The heuristics are intentionally clangd-independent (pure Python) so the survey can
run in environments without a clangd binary; the include resolution mirrors the
compiler's ``-I`` search order.
"""

from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Iterable

__all__ = [
    "HEADER_EXTENSIONS",
    "IMPL_EXTENSIONS",
    "is_header",
    "is_impl",
    "switch_source_header",
    "pair_header_impl",
    "build_include_graph",
    "compute_blast_radius",
]

HEADER_EXTENSIONS = frozenset({".h", ".hpp", ".hh", ".hxx", ".cuh"})
IMPL_EXTENSIONS = frozenset({".cc", ".cpp", ".cxx", ".c", ".hip", ".cu"})

_ALL_EXTENSIONS = HEADER_EXTENSIONS | IMPL_EXTENSIONS

# #include "foo.h"  or  #include <foo/bar.h>
_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*([<"])([^">]+)[">]', re.MULTILINE)
# -I<path> or -I <path> from a compile command string
_INCLUDE_FLAG_RE = re.compile(r'-I\s*("?)([^"\s]+)\1')


# ---------------------------------------------------------------------------
# Header / impl classification + pairing
# ---------------------------------------------------------------------------
def is_header(path: str | Path) -> bool:
    """Return True if *path* has a C/C++ header extension (.h/.hpp/.cuh/...)."""
    return Path(path).suffix.lower() in HEADER_EXTENSIONS


def is_impl(path: str | Path) -> bool:
    """Return True if *path* has a C/C++ implementation extension (.cpp/.cc/.hip/...)."""
    return Path(path).suffix.lower() in IMPL_EXTENSIONS


def switch_source_header(target: str | Path, candidates: Iterable[str | Path]) -> str | None:
    """Return the paired header/source for *target*, mirroring clangd switchSourceHeader.

    Given an impl file, return its matching header (same stem, header extension);
    given a header, return its matching impl.  Prefers a candidate in the same
    directory, then any candidate sharing the stem.  Returns None when no pair
    exists.

    Raises
    ------
    ValueError
        If *target* is None or not a str/Path.
    """
    if target is None or not isinstance(target, (str, Path)):
        raise ValueError(f"switch_source_header: target must be a str/Path, got {type(target).__name__!r}")

    tpath = Path(target)
    stem = tpath.stem
    if is_impl(tpath):
        wanted = HEADER_EXTENSIONS
    elif is_header(tpath):
        wanted = IMPL_EXTENSIONS
    else:
        return None

    same_dir: list[str] = []
    other_dir: list[str] = []
    for cand in candidates:
        cpath = Path(cand)
        if cpath == tpath:
            continue
        if cpath.stem != stem:
            continue
        if cpath.suffix.lower() not in wanted:
            continue
        if cpath.parent == tpath.parent:
            same_dir.append(str(cand))
        else:
            other_dir.append(str(cand))

    if same_dir:
        return sorted(same_dir)[0]
    if other_dir:
        return sorted(other_dir)[0]
    return None


def pair_header_impl(files: Iterable[str | Path]) -> list[tuple[str, str]]:
    """Return a list of ``(header, impl)`` pairs discovered among *files*.

    Uses :func:`switch_source_header` for each header and de-duplicates so a
    header/impl pair appears exactly once.

    Raises
    ------
    ValueError
        If *files* is not an iterable of paths (e.g. a bare string).
    """
    if isinstance(files, (str, bytes)) or not isinstance(files, Iterable):
        raise ValueError(f"pair_header_impl: files must be an iterable of paths, got {type(files).__name__!r}")

    file_list = [str(f) for f in files]
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for f in file_list:
        if not is_header(f):
            continue
        impl = switch_source_header(f, file_list)
        if impl is None:
            continue
        key = (f, impl)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)
    return pairs


# ---------------------------------------------------------------------------
# #include graph
# ---------------------------------------------------------------------------
def _load_compile_commands(root: Path, compile_commands: Path | None) -> list[dict]:
    if compile_commands is not None:
        cc_path = Path(compile_commands)
        if not cc_path.exists():
            raise ValueError(f"build_include_graph: compile_commands not found: {cc_path}")
    else:
        cc_path = root / "compile_commands.json"
        if not cc_path.exists():
            return []
    try:
        data = json.loads(cc_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"build_include_graph: malformed compile_commands.json: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("build_include_graph: compile_commands.json must be a JSON array")
    return data


def _include_dirs_for(entry: dict, root: Path) -> list[Path]:
    """Extract -I search paths from a compile_commands entry (command or arguments)."""
    dirs: list[Path] = []
    directory = Path(entry.get("directory", root))

    tokens: list[str] = []
    if isinstance(entry.get("arguments"), list):
        tokens = [str(a) for a in entry["arguments"]]
        # join -I / value pairs handled below
        joined = " ".join(tokens)
    else:
        joined = str(entry.get("command", ""))

    for _, raw in _INCLUDE_FLAG_RE.findall(joined):
        p = Path(raw)
        dirs.append(p if p.is_absolute() else (directory / p))
    return dirs


def _collect_source_files(root: Path, cc_entries: list[dict]) -> set[Path]:
    files: set[Path] = set()
    # Files named in compile_commands (translation units)
    for entry in cc_entries:
        f = entry.get("file")
        if f:
            fp = Path(f)
            if not fp.is_absolute():
                fp = Path(entry.get("directory", root)) / fp
            if fp.exists():
                files.add(fp.resolve())
    # All C/C++ source + header files in the tree
    ignore = {".git", "__pycache__", ".venv", "node_modules", ".bob", "build"}
    for p in root.rglob("*"):
        if any(part in ignore for part in p.parts):
            continue
        if p.is_file() and p.suffix.lower() in _ALL_EXTENSIONS:
            files.add(p.resolve())
    return files


def _resolve_include(
    spec: str,
    quote: str,
    including_file: Path,
    include_dirs: list[Path],
    known: set[Path],
) -> Path | None:
    """Resolve one #include spec to an absolute path, mirroring compiler search order."""
    search: list[Path] = []
    if quote == '"':
        # quoted: current file's directory first
        search.append(including_file.parent)
    search.extend(include_dirs)
    for base in search:
        cand = (base / spec).resolve()
        if cand in known or cand.exists():
            return cand
    # last resort: match by basename among known files
    target_name = Path(spec).name
    for k in known:
        if k.name == target_name:
            return k
    return None


def build_include_graph(
    root: str | Path,
    compile_commands: str | Path | None = None,
) -> dict[str, list[str]]:
    """Build a preprocessor #include graph for the C/C++ tree at *root*.

    Returns a mapping ``{file_path: [included_file_path, ...]}`` where every C/C++
    source and header file under *root* is a node and each edge records a resolved
    ``#include`` directive.  Include directives are resolved through the ``-I``
    search paths declared in ``compile_commands.json`` (or *compile_commands* when
    given explicitly), mirroring the compiler's search order.

    An empty project (no sources, no compile database) returns ``{}``.

    Raises
    ------
    ValueError
        If *root* is None / not a str-or-Path, if an explicitly-supplied
        *compile_commands* file does not exist, or if the compile database is
        malformed JSON.
    """
    if root is None or not isinstance(root, (str, Path)):
        raise ValueError(f"build_include_graph: root must be a str/Path, got {type(root).__name__!r}")
    root_path = Path(root)

    cc_entries = _load_compile_commands(root_path, Path(compile_commands) if compile_commands is not None else None)

    files = _collect_source_files(root_path, cc_entries)
    if not files:
        return {}

    # Union of all -I dirs across the compile database (used for header->header
    # includes where the header is not itself a translation unit in the db).
    global_include_dirs: list[Path] = []
    seen_dirs: set[Path] = set()
    for entry in cc_entries:
        for d in _include_dirs_for(entry, root_path):
            rd = d.resolve()
            if rd not in seen_dirs:
                seen_dirs.add(rd)
                global_include_dirs.append(rd)

    graph: dict[str, list[str]] = {}
    for f in sorted(files):
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            graph[str(f)] = []
            continue
        edges: list[str] = []
        seen_targets: set[Path] = set()
        for quote, spec in _INCLUDE_RE.findall(text):
            resolved = _resolve_include(spec, quote, f, global_include_dirs, files)
            if resolved is None or resolved not in files:
                continue
            if resolved in seen_targets:
                continue
            seen_targets.add(resolved)
            edges.append(str(resolved))
        graph[str(f)] = edges
    return graph


def compute_blast_radius(graph: dict[str, list[str]], node: str | Path) -> int:
    """Return the blast-radius score for *node* in an include *graph*.

    The score is the number of distinct downstream files that transitively
    ``#include`` *node* (directly or through intermediate headers).  A widely
    included public header scores high; a leaf source file that nothing includes
    scores 0.  A *node* absent from the graph scores 0 (well-defined, not an error).

    Raises
    ------
    ValueError
        If *graph* is None / not a dict, or *node* is None / empty / not a str-Path.
    """
    if graph is None or not isinstance(graph, dict):
        raise ValueError(f"compute_blast_radius: graph must be a dict, got {type(graph).__name__!r}")
    if node is None or not isinstance(node, (str, Path)):
        raise ValueError(f"compute_blast_radius: node must be a str/Path, got {type(node).__name__!r}")
    node_str = str(node)
    if not node_str.strip():
        raise ValueError("compute_blast_radius: node must be a non-empty path")

    # Build reverse edges: dst -> {srcs that include dst}
    reverse: dict[str, set[str]] = {}
    for src, dsts in graph.items():
        for dst in dsts:
            reverse.setdefault(dst, set()).add(src)

    if node_str not in reverse:
        return 0

    visited: set[str] = set()
    queue: deque[str] = deque(reverse[node_str])
    while queue:
        cur = queue.popleft()
        if cur in visited:
            continue
        visited.add(cur)
        for upstream in reverse.get(cur, ()):
            if upstream not in visited:
                queue.append(upstream)
    return len(visited)
