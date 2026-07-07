"""bob.survey — semantic code-survey backends.

This package hosts survey backends that populate bob's ``survey.db``
(``symbols`` / ``edges`` / ``file_hashes`` tables — see
:mod:`bob.brownfield.schema`).

The default BF-1 backend (:mod:`bob.brownfield.survey`) uses Python ``ast``
and resolves edges by textual name-matching, which is the greenfield path.

:mod:`bob.survey.clangd_backend` adds a C++-aware backend that drives
``clangd-indexer`` / ``clangd`` / ``libclang`` against a
``compile_commands.json`` to emit a *semantic* index keyed on stable clang
USRs, giving true cross-TU call graphs. It falls back to tree-sitter-cpp /
the BF-1 path when clangd is not available.
"""

from __future__ import annotations

from bob.survey.clangd_backend import (
    ClangdAvailability,
    build_clangd_index,
    detect_clangd_availability,
)
from bob.header_impl_pairing import (  # noqa: F401 — integration AC bd36773c
    HEADER_EXTENSIONS,
    IMPL_EXTENSIONS,
    build_include_graph,
    compute_blast_radius,
    is_header,
    is_impl,
    pair_header_impl,
    switch_source_header,
)

__all__ = [
    "ClangdAvailability",
    "build_clangd_index",
    "detect_clangd_availability",
    "HEADER_EXTENSIONS",
    "IMPL_EXTENSIONS",
    "build_include_graph",
    "compute_blast_radius",
    "is_header",
    "is_impl",
    "pair_header_impl",
    "switch_source_header",
]
