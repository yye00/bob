"""Feature splitter — right-size oversized features at extraction time.

A feature that bundles many independent sub-capabilities into one AC set
(e.g. Statistics = percentile + concatenate + polyfit; hipsci.sparse = SpMV +
SpMM + SpGEMM + construction) has a long single-attempt build time that

  (a) exceeds the transport-crash MTBF (the F-R7-645 completability cliff), and
  (b) scores low on spec-stability because the AC synthesizer produces divergent
      file-path / function sets across samples.

Fix at extraction (spec-over-code): flag a feature whose acceptance criteria
enumerate N independent public entry points across M>1 target modules and
RECOMMEND splitting it into per-capability sub-features with explicit
dependencies, so each is small enough to build inside one crash-free window and
to synthesize deterministically.

This module does NOT lower any threshold — it makes large features completable
by right-sizing scope.

Companion concern — canonical-package pinning: :func:`pin_canonical_package`
rewrites every ``File exists:`` / ``Function defined:`` AC so its top-level
package is one of the project's canonical packages (e.g. ``hippy``/``hipsci``),
so synthesis never invents a ``src/<workspace-dir-name>`` package (observed:
``src/dark_factory/`` leaking from the workspace directory name).

Integration: bob.spec_extractor.

Public API::

    from bob.feature_splitter import (
        recommend_split,
        pin_canonical_package,
        SplitRecommendation,
        SubFeature,
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# A split is recommended when the AC set spans MORE THAN this many distinct
# target modules AND enumerates AT LEAST this many independent entry points.
_MIN_MODULES_FOR_SPLIT = 2  # M > 1
_MIN_ENTRY_POINTS_FOR_SPLIT = 3  # N independent public entry points


# ---------------------------------------------------------------------------
# AC parsing
# ---------------------------------------------------------------------------

# "Function defined: <module>.<name>"
_FUNCTION_DEFINED_RE = re.compile(
    r"^\s*Function\s+defined\s*:\s*(?P<dotted>[\w.]+)\s*$", re.IGNORECASE
)
# "Class defined: <module>.<name>"
_CLASS_DEFINED_RE = re.compile(
    r"^\s*Class\s+defined\s*:\s*(?P<dotted>[\w.]+)\s*$", re.IGNORECASE
)
# "File exists: <relative_path>"
_FILE_EXISTS_RE = re.compile(
    r"^\s*File\s+exists\s*:\s*(?P<path>\S+)\s*$", re.IGNORECASE
)


@dataclass
class EntryPoint:
    """One independent public entry point enumerated by an AC."""

    kind: str  # "function" | "class"
    module: str  # dotted module path (e.g. "hippy.statistics")
    name: str  # symbol name (e.g. "percentile")
    raw: str  # original AC text


@dataclass
class SubFeature:
    """A per-capability sub-feature recommended by a split."""

    module: str
    acceptance_criteria: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class SplitRecommendation:
    """Outcome of a split analysis for one feature."""

    feature_name: str = ""
    should_split: bool = False
    num_modules: int = 0
    num_entry_points: int = 0
    modules: list[str] = field(default_factory=list)
    sub_features: list[SubFeature] = field(default_factory=list)
    reason: str = ""


def _module_of(dotted: str) -> str:
    """Return the module portion of a dotted ``module.symbol`` path."""
    return dotted.rsplit(".", 1)[0] if "." in dotted else dotted


def _name_of(dotted: str) -> str:
    """Return the symbol portion of a dotted ``module.symbol`` path."""
    return dotted.rsplit(".", 1)[1] if "." in dotted else dotted


def _module_from_file_path(path: str) -> str | None:
    """Derive a dotted module from a ``src/<pkg>/.../<file>.py`` path.

    Returns None for non-source paths (e.g. tests/ or asset files) so that
    test-file ACs do not count as independent capability entry points.
    """
    p = path.strip().replace("\\", "/")
    if not p.endswith(".py"):
        return None
    if p.startswith("src/"):
        p = p[len("src/") :]
    elif p.startswith("tests/") or "/tests/" in p:
        return None
    p = p[: -len(".py")]
    parts = [seg for seg in p.split("/") if seg and seg != "__init__"]
    if not parts:
        return None
    return ".".join(parts)


def _extract_entry_points(acceptance_criteria: list[str]) -> list[EntryPoint]:
    """Extract independent public entry points from AC strings."""
    entry_points: list[EntryPoint] = []
    for ac in acceptance_criteria:
        text = str(ac)
        m = _FUNCTION_DEFINED_RE.match(text)
        if m:
            dotted = m.group("dotted")
            entry_points.append(
                EntryPoint("function", _module_of(dotted), _name_of(dotted), text)
            )
            continue
        m = _CLASS_DEFINED_RE.match(text)
        if m:
            dotted = m.group("dotted")
            entry_points.append(
                EntryPoint("class", _module_of(dotted), _name_of(dotted), text)
            )
            continue
        m = _FILE_EXISTS_RE.match(text)
        if m:
            module = _module_from_file_path(m.group("path"))
            if module is not None:
                entry_points.append(
                    EntryPoint("file", module, _name_of(module), text)
                )
    return entry_points


def recommend_split(
    feature: dict[str, Any],
    *,
    min_modules: int = _MIN_MODULES_FOR_SPLIT,
    min_entry_points: int = _MIN_ENTRY_POINTS_FOR_SPLIT,
) -> SplitRecommendation:
    """Recommend splitting an oversized feature into per-capability sub-features.

    A split is recommended WHEN the feature's acceptance criteria enumerate at
    least *min_entry_points* independent public entry points (``Function
    defined:`` / ``Class defined:`` / source ``File exists:`` ACs) spread across
    MORE THAN one target module (``> min_modules - 1``, i.e. M > 1). Each
    recommended sub-feature groups the ACs targeting one module, so it is small
    enough to build inside one crash-free window and to synthesize
    deterministically.

    Sub-features are emitted in a deterministic (sorted-by-module) order and
    given a linear ``depends_on`` chain so the extractor can encode explicit
    dependencies between the split parts.

    Parameters
    ----------
    feature:
        Feature dict with (at least) ``name`` and ``acceptance_criteria`` keys.
    min_modules:
        Minimum number of distinct target modules (default 2) required before a
        split is recommended. A feature confined to a single module is left
        intact.
    min_entry_points:
        Minimum number of independent entry points (default 3) required before a
        split is recommended.

    Returns
    -------
    SplitRecommendation
        ``should_split`` is True when the feature spans multiple modules with
        enough entry points; ``sub_features`` then contains one entry per module.

    Raises
    ------
    TypeError
        If *feature* is not a dict.
    ValueError
        If ``acceptance_criteria`` is present but not a list.
    """
    if not isinstance(feature, dict):
        raise TypeError(f"feature must be a dict, got {type(feature).__name__}")

    acs = feature.get("acceptance_criteria")
    if acs is None:
        acs = []
    if not isinstance(acs, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acs).__name__}"
        )

    name = str(feature.get("name") or "")
    result = SplitRecommendation(feature_name=name)

    entry_points = _extract_entry_points(acs)
    result.num_entry_points = len(entry_points)

    # Group entry points by module (deterministic ordering).
    by_module: dict[str, list[EntryPoint]] = {}
    for ep in entry_points:
        by_module.setdefault(ep.module, []).append(ep)

    modules = sorted(by_module)
    result.modules = modules
    result.num_modules = len(modules)

    if len(modules) < min_modules or len(entry_points) < min_entry_points:
        result.reason = (
            f"Feature {name!r} spans {len(modules)} module(s) with "
            f"{len(entry_points)} entry point(s); below the split threshold "
            f"(needs >={min_modules} modules and >={min_entry_points} entry points)."
        )
        return result

    result.should_split = True
    result.reason = (
        f"Feature {name!r} enumerates {len(entry_points)} independent public "
        f"entry points across {len(modules)} target modules "
        f"({', '.join(modules)}); recommend splitting into per-capability "
        f"sub-features so each fits inside one crash-free build window."
    )

    prev_module: str | None = None
    for module in modules:
        sub = SubFeature(
            module=module,
            acceptance_criteria=[ep.raw for ep in by_module[module]],
            depends_on=[prev_module] if prev_module else [],
        )
        result.sub_features.append(sub)
        prev_module = module

    return result


# ---------------------------------------------------------------------------
# Canonical-package pinning
# ---------------------------------------------------------------------------

_FILE_EXISTS_CAP = re.compile(
    r"^(?P<prefix>\s*File\s+exists\s*:\s*)(?P<path>\S+)(?P<suffix>\s*)$",
    re.IGNORECASE,
)
_DEFINED_CAP = re.compile(
    r"^(?P<prefix>\s*(?:Function|Class)\s+defined\s*:\s*)(?P<dotted>[\w.]+)(?P<suffix>\s*)$",
    re.IGNORECASE,
)
_INTEGRATION_CAP = re.compile(
    r"^(?P<prefix>\s*integration\s*:\s*)(?P<dotted>[\w.]+)(?P<suffix>\s*)$",
    re.IGNORECASE,
)


def _normalize_packages(canonical_packages: Any) -> list[str]:
    """Coerce the canonical-package argument into a clean list of names."""
    if isinstance(canonical_packages, str):
        raw = canonical_packages
        pkgs = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
    elif isinstance(canonical_packages, (list, tuple)):
        pkgs = [str(p).strip() for p in canonical_packages if str(p).strip()]
    else:
        raise TypeError(
            "canonical_packages must be a str, list, or tuple, got "
            f"{type(canonical_packages).__name__}"
        )
    return pkgs


def _pin_file_path(path: str, canonical: str, packages: set[str]) -> str:
    """Rewrite a ``src/<pkg>/...`` file path onto the canonical package."""
    p = path.replace("\\", "/")
    if p.startswith("src/"):
        rest = p[len("src/") :]
        parts = rest.split("/", 1)
        top = parts[0]
        if top in packages:
            return p  # already canonical
        tail = parts[1] if len(parts) > 1 else ""
        return f"src/{canonical}/{tail}" if tail else f"src/{canonical}"
    # tests/ and asset paths are left untouched.
    if p.startswith("tests/"):
        return p
    return p


def _pin_dotted(dotted: str, canonical: str, packages: set[str]) -> str:
    """Rewrite a dotted module path onto the canonical package."""
    parts = dotted.split(".")
    if not parts:
        return dotted
    if parts[0] in packages:
        return dotted  # already canonical
    parts[0] = canonical
    return ".".join(parts)


def pin_canonical_package(
    feature: dict[str, Any] | list[str],
    canonical_packages: str | list[str] | tuple[str, ...],
) -> dict[str, Any] | list[str]:
    """Pin every structural AC onto a canonical top-level package.

    Rewrites the top-level package of every ``File exists:``,
    ``Function defined:``, ``Class defined:`` and ``integration:`` AC so it lives
    under one of *canonical_packages*. When an AC already uses a canonical
    package it is left untouched; otherwise its (non-canonical) top-level package
    — typically one leaked from the workspace directory name, e.g.
    ``src/dark_factory/`` — is replaced with the FIRST canonical package.

    ``tests/`` paths and non-structural ACs (``pytest:``, ``CLI command:`` …)
    pass through unchanged.

    Parameters
    ----------
    feature:
        Either a feature dict (its ``acceptance_criteria`` list is rewritten in
        a copy) or a bare list of AC strings.
    canonical_packages:
        The allowed top-level package name(s), as a comma/space-separated string
        or a list/tuple. The first entry is used as the replacement package.

    Returns
    -------
    dict or list
        Same shape as the input, with structural ACs pinned. When a dict is
        passed a shallow copy with a rewritten ``acceptance_criteria`` list is
        returned; when a list is passed a new list is returned.

    Raises
    ------
    TypeError
        If *feature* is neither a dict nor a list, or *canonical_packages* is not
        a str/list/tuple.
    ValueError
        If *canonical_packages* yields no usable package names, or the dict's
        ``acceptance_criteria`` is not a list.
    """
    packages = _normalize_packages(canonical_packages)
    if not packages:
        raise ValueError("canonical_packages must contain at least one package name")
    canonical = packages[0]
    pkg_set = set(packages)

    def _pin_ac(ac: Any) -> str:
        text = str(ac)
        m = _FILE_EXISTS_CAP.match(text)
        if m:
            new_path = _pin_file_path(m.group("path"), canonical, pkg_set)
            return f"{m.group('prefix')}{new_path}{m.group('suffix')}"
        m = _DEFINED_CAP.match(text)
        if m:
            new_dotted = _pin_dotted(m.group("dotted"), canonical, pkg_set)
            return f"{m.group('prefix')}{new_dotted}{m.group('suffix')}"
        m = _INTEGRATION_CAP.match(text)
        if m:
            new_dotted = _pin_dotted(m.group("dotted"), canonical, pkg_set)
            return f"{m.group('prefix')}{new_dotted}{m.group('suffix')}"
        return text

    if isinstance(feature, dict):
        acs = feature.get("acceptance_criteria")
        if acs is None:
            acs = []
        if not isinstance(acs, list):
            raise ValueError(
                f"acceptance_criteria must be a list, got {type(acs).__name__}"
            )
        pinned = dict(feature)
        pinned["acceptance_criteria"] = [_pin_ac(ac) for ac in acs]
        return pinned

    if isinstance(feature, list):
        return [_pin_ac(ac) for ac in feature]

    raise TypeError(
        f"feature must be a dict or list, got {type(feature).__name__}"
    )


__all__ = [
    "recommend_split",
    "pin_canonical_package",
    "SplitRecommendation",
    "SubFeature",
    "EntryPoint",
]
