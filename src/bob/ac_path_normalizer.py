"""Canonicalize corrupted path ACs before they are persisted (feature d482fa32).

The AC synthesizer intermittently emits ``File exists:`` / ``pytest:`` path ACs
whose path token has been corrupted in a way that can NEVER be satisfied,
silently NH-ing an otherwise COMPLETE feature at attempt 5. Two observed
corruptions on the bob96 build (147/149):

  * F-R7-603 -> ``File exists: file.claude/hooks/context_budget.py``
    (spurious ``file.`` prefix; correct path is ``.claude/hooks/context_budget.py``)
  * F-R7-626 -> ``File exists: /src/bob/spec_synthesizer.py``
    (spurious leading ``/``; correct path is ``src/bob/spec_synthesizer.py``)

In both cases the CORRECT workspace-relative path was already present as a
sibling AC and the real file existed on disk — only the bogus-path AC failed.

This is the same family as F-R7-411 (reachability) and F-R7-654 (grammar). The
fix is bob CODE at synthesis/extraction time: a path-AC normalizer canonicalizes
every ``File exists:`` and ``pytest:`` path to a workspace-relative form BEFORE
the AC is persisted, and drops an AC that becomes an exact duplicate of an
existing sibling. This STRENGTHENS the gate by removing false negatives.
"""

from __future__ import annotations

import re

__all__ = ["normalize_path_ac", "normalize_path_acs"]

# The two AC prefixes that carry a filesystem path.
_PATH_PREFIXES = ("File exists:", "pytest:")

# A ``pytest:`` AC may carry a trailing " — <human description>" after the path
# (the boundary/error ACs do this). We normalize only the leading path token.
_PREFIX_RE = re.compile(r"^(?P<prefix>File exists:|pytest:)(?P<rest>.*)$", re.DOTALL)


def _canonicalize_path(path: str) -> str:
    """Strip synthesizer corruption from a single path token.

    - a spurious ``file.`` or ``file:`` prefix
    - a spurious leading ``/``
    - ``<pkg>/src/<pkg>``-style duplication
    """
    p = path
    # Strip a spurious ``file`` prefix (``file.claude/...`` -> ``.claude/...``,
    # ``file:src/...`` -> ``src/...``). Strip the literal ``file`` and an
    # immediately-following ``:``, but KEEP a following ``.`` (it belongs to a
    # dotdir like ``.claude``). Guarded by a ``/`` in the remainder so a real
    # bare filename such as ``file.py`` is never mangled.
    m = re.match(r"^file(?P<sep>[.:])(?P<rest>.+)$", p)
    if m and "/" in m.group("rest"):
        rest = m.group("rest")
        # ``file:`` -> drop the colon too; ``file.`` -> keep the dot (dotdir).
        p = rest if m.group("sep") == ":" else "." + rest

    # Strip a spurious leading ``/`` -> workspace-relative.
    if p.startswith("/"):
        p = p.lstrip("/")

    # Collapse ``<pkg>/src/<pkg>/...`` -> ``src/<pkg>/...`` (e.g. ``bob/src/bob/foo.py``).
    p = re.sub(r"^(?P<pkg>[A-Za-z0-9_]+)/src/(?P=pkg)/", r"src/\g<pkg>/", p)

    return p


def normalize_path_ac(ac: str) -> str:
    """Return ``ac`` with any corrupted ``File exists:``/``pytest:`` path repaired.

    Non-path ACs (``Function defined:``, ``integration:`` …) and already-canonical
    path ACs are returned unchanged.

    Raises
    ------
    ValueError
        If ``ac`` is not a ``str`` (e.g. ``None``, an int, or a list). The
        function never silently succeeds on a non-string input.
    """
    if not isinstance(ac, str):
        raise ValueError(f"normalize_path_ac expects a str AC, got {type(ac).__name__}")

    m = _PREFIX_RE.match(ac)
    if not m:
        return ac

    prefix = m.group("prefix")
    rest = m.group("rest")

    # Preserve the exact leading whitespace between prefix and the path token so
    # a clean AC round-trips byte-for-byte.
    lead_ws = rest[: len(rest) - len(rest.lstrip())]
    body = rest.lstrip()
    if not body:
        # Bare "File exists:" / "pytest:" — nothing to normalize.
        return ac

    # A ``pytest:`` AC can have a trailing " — description"; split only the path.
    path_token = body
    trailer = ""
    for sep in (" — ", " -- ", " - "):
        idx = body.find(sep)
        if idx != -1:
            path_token = body[:idx]
            trailer = body[idx:]
            break

    path_lead_ws = path_token[: len(path_token) - len(path_token.lstrip())]
    path_trail_ws = path_token[len(path_token.rstrip()):]
    core = path_token.strip()
    if not core:
        return ac

    canonical = _canonicalize_path(core)
    if canonical == core:
        return ac

    return f"{prefix}{lead_ws}{path_lead_ws}{canonical}{path_trail_ws}{trailer}"


def normalize_path_acs(criteria: list[str]) -> list[str]:
    """Normalize every AC in ``criteria`` and drop exact duplicates.

    After canonicalizing each path AC, a corrupted AC that collapses onto an
    existing (clean) sibling is dropped — the F-R7-603 / F-R7-626 scenario where
    both the bogus and the correct path AC are present.

    Order is preserved; the first occurrence of each distinct AC is kept.

    Raises
    ------
    ValueError
        If ``criteria`` is not a list, or any element is not a ``str``.
    """
    if not isinstance(criteria, list):
        raise ValueError(
            f"normalize_path_acs expects a list of AC strings, got {type(criteria).__name__}"
        )

    out: list[str] = []
    seen: set[str] = set()
    for ac in criteria:
        normalized = normalize_path_ac(ac)  # raises ValueError on non-str element
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out
