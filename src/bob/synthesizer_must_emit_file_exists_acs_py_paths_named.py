"""bob.synthesizer_must_emit_file_exists_acs_py_paths_named

Two contract_completeness fixes that restored 15 features from composite 0.0:

(1) SCORER fix: only treat CODE-SHAPED tokens (containing ``_``, ``.``, ``.py``
    extension, or internal CamelCase) as API surfaces that require AC coverage.
    Plain English words ("defined", "name", "gate", "correctly") are prose, not
    symbols.

(2) SYNTHESIZER fix: post-synthesis, scan the description for concrete ``.py``
    paths and emit a ``File exists: <path>`` AC for each not already covered.
    Bare filenames without a directory component are skipped (ambiguous).

Public API::

    from bob.synthesizer_must_emit_file_exists_acs_py_paths_named import (
        synthesizer_must_emit_file_exists_acs_py_paths_named,
    )

    result = synthesizer_must_emit_file_exists_acs_py_paths_named(
        description="...",
        acceptance_criteria=["File exists: src/bob/foo.py"],
    )
    # result["criteria"]     — augmented list[str] with File-exists ACs injected
    # result["added_paths"]  — list[str] of newly added File-exists paths
    # result["api_surfaces"] — list[str] of code-shaped tokens from description
"""

from __future__ import annotations

import re
from typing import Any

from tools.spec_quality_score import (
    extract_py_paths,
    filter_api_surfaces,
    is_code_shaped_token,
)

# Re-export for callers who import from this module
__all__ = [
    "synthesizer_must_emit_file_exists_acs_py_paths_named",
    "emit_file_exists_acs_for_py_paths",
    "extract_code_shaped_api_surfaces",
]


_FUNC_RE = re.compile(
    r"\b(?:function|method|def)\s+`?(\w+)`?|\b`(\w+)\(\)`",
    re.IGNORECASE,
)
_CLASS_RE = re.compile(r"\b(?:class|model)\s+`?(\w+)`?", re.IGNORECASE)


def extract_code_shaped_api_surfaces(description: str) -> list[str]:
    """Return code-shaped API surface tokens from *description*.

    Only tokens that are CODE-SHAPED (contain ``_``, ``.``, ``.py``, or
    internal CamelCase) and are not English stop-words are returned.  Plain
    English words like "defined", "name", "correctly" are filtered out.

    Parameters
    ----------
    description:
        Free-form feature description text.

    Returns
    -------
    list[str]
        Sorted, deduplicated code-shaped API surface tokens.
    """
    if not description:
        return []

    tokens: set[str] = set()

    for m in _FUNC_RE.finditer(description):
        sym = m.group(1) or m.group(2) or ""
        if sym and is_code_shaped_token(sym):
            tokens.add(sym)

    for m in _CLASS_RE.finditer(description):
        sym = m.group(1) or ""
        if sym and is_code_shaped_token(sym):
            tokens.add(sym)

    # Include .py paths as API surfaces
    for path in extract_py_paths(description):
        tokens.add(path)

    return sorted(tokens)


def emit_file_exists_acs_for_py_paths(
    criteria: list[str],
    description: str,
) -> tuple[list[str], list[str]]:
    """Inject ``File exists: <path>`` ACs for .py paths named in *description*.

    Scans *description* for concrete ``.py`` paths (those containing a ``/``
    separator or starting with ``test``). For each path not already covered by
    an existing AC, a ``File exists: <path>`` AC is appended to *criteria*.

    Parameters
    ----------
    criteria:
        Current list of AC strings.
    description:
        Free-form feature description that may name concrete ``.py`` paths.

    Returns
    -------
    tuple[list[str], list[str]]
        ``(augmented_criteria, added_paths)`` where *added_paths* lists the
        newly added ``File exists:`` paths (empty when nothing was added).
    """
    if not description:
        return list(criteria), []

    blob = " ".join(criteria)
    py_paths = extract_py_paths(description)

    added: list[str] = []
    augmented = list(criteria)
    for path in py_paths:
        if path in blob:
            continue
        ac = f"File exists: {path}"
        augmented.append(ac)
        added.append(path)

    return augmented, added


def synthesizer_must_emit_file_exists_acs_py_paths_named(
    description: str,
    acceptance_criteria: list[str] | None = None,
) -> dict[str, Any]:
    """Apply both contract_completeness fixes and return diagnostics.

    This is the primary entry-point that validates both fixes:

    1. SCORER fix: extract only code-shaped API surfaces from *description*
       (tokens with ``_``, ``.``, ``.py``, or CamelCase) — plain English words
       are not counted as uncovered API surfaces.

    2. SYNTHESIZER fix: inject ``File exists: <path>`` ACs for every concrete
       ``.py`` path named in *description* that is not already covered.

    Parameters
    ----------
    description:
        Feature description that may name concrete ``.py`` paths and/or
        code-shaped API surface symbols.
    acceptance_criteria:
        Current list of AC strings. Defaults to ``[]`` when ``None``.

    Returns
    -------
    dict with keys:
        ``criteria``      — augmented list[str] with File-exists ACs injected
        ``added_paths``   — list[str] of newly added File-exists paths
        ``api_surfaces``  — list[str] code-shaped tokens from description
    """
    if not isinstance(description, str):
        raise ValueError(f"description must be a str, got {type(description).__name__!r}")

    criteria: list[str] = list(acceptance_criteria) if acceptance_criteria else []

    augmented, added = emit_file_exists_acs_for_py_paths(criteria, description)
    surfaces = extract_code_shaped_api_surfaces(description)

    return {
        "criteria": augmented,
        "added_paths": added,
        "api_surfaces": surfaces,
    }
