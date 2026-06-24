"""Composite spec_quality_score — 8 sub-metrics, weighted geometric mean.

Replaces the F-R7-413 placeholder with a concrete rubric:

  Sub-metric            Weight  Description
  ──────────────────    ──────  ──────────────────────────────────────────────
  smell_density         0.20    Fraction of ACs free of E-severity smells
  predicate_coverage    0.20    Fraction of ACs with a concrete, verifiable predicate
  contract_completeness 0.15    Fraction of described API surfaces covered by an AC
  boundary_coverage     0.10    Fraction of ACs that mention a boundary/edge condition
  error_path_coverage   0.10    Fraction of ACs that cover error / failure paths
  traceability          0.10    Fraction of ACs that are traceable to a named AC form
  spec_executability    0.10    Fraction of ACs that are mechanically verifiable
  ac_atomicity          0.05    Fraction of ACs that describe exactly one observable

Composite = weighted geometric mean of the 8 sub-scores.

Geometric mean semantics: one sub-score of 0.0 drives the composite to 0.0,
so a fatal flaw (e.g. every AC has an E-severity smell) cannot be averaged away.

Gate:
  composite < 0.65  → raise SystemExit(1) from bob plan --create
  0.65 ≤ composite < 0.80 → warn but proceed
  composite ≥ 0.80  → silent green

Public API::

    from tools.spec_quality_score import compute

    result = compute(
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py", "pytest: tests/test_foo.py"],
    )
    # result.composite    — float in [0, 1]
    # result.smell_density, .predicate_coverage, ... — individual sub-scores
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union


# ---------------------------------------------------------------------------
# Weights — must sum to 1.0
# ---------------------------------------------------------------------------

_WEIGHTS: dict[str, float] = {
    "smell_density": 0.20,
    "predicate_coverage": 0.20,
    "contract_completeness": 0.15,
    "boundary_coverage": 0.10,
    "error_path_coverage": 0.10,
    "traceability": 0.10,
    "spec_executability": 0.10,
    "ac_atomicity": 0.05,
}

assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"

# Gate thresholds (env-overridable for operator unstick)
import os as _os
def _env_float(k: str, default: float) -> float:
    raw = _os.environ.get(k)
    if not raw:
        return default
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return default
GATE_BLOCK = _env_float("BOB_PLAN_GATE_BLOCK", 0.65)
GATE_WARN = _env_float("BOB_PLAN_GATE_WARN", 0.80)

# Structured AC form patterns (traceable / executable forms)
_AC_FORMS: list[re.Pattern[str]] = [
    re.compile(r"^File exists\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^Function defined\s*:\s*[\w.]+", re.IGNORECASE),
    re.compile(r"^Class defined\s*:\s*[\w.]+", re.IGNORECASE),
    re.compile(r"^pytest\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^integration\s*:\s*[\w./:-]+", re.IGNORECASE),
    re.compile(r"^behavior\s*:\s*.+\bwhen\b.+", re.IGNORECASE),
    re.compile(r"^python\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^Field exists\s*.*:\s*\S+", re.IGNORECASE),
    re.compile(r"^CI tests\s*:\s*\S+", re.IGNORECASE),
]

# E-severity smell patterns (simplified subset that doesn't require spaCy)
_E_SMELL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(fast|simple|reliable|robust|friendly|intuitive|clean|good|nice|easy|"
        r"lightweight|powerful|scalable|beautiful|modern|elegant|seamless|smooth)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(works|handles|supports|manages|provides)\s+\w+\s+(correctly|properly|appropriately)\b", re.IGNORECASE),
    re.compile(r"\b(all cases|any input|every case|various|multiple)\b", re.IGNORECASE),
]

# Boundary condition indicators
_BOUNDARY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|boundary|edge case|corner case|overflow|underflow|limit)\b", re.IGNORECASE),
    re.compile(r"\b(0|0\.0|-1|INT_MAX|INT_MIN|MAX_VALUE|MIN_VALUE)\b"),
    re.compile(r"\b(boundary|edge|corner|threshold|limit|floor|ceiling)\b", re.IGNORECASE),
]

# Error path indicators
_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(error|exception|fail|invalid|reject|raise|exit non-zero|abort|refuse|block)\b", re.IGNORECASE),
    re.compile(r"\b(does not|cannot|must not|shall not)\b", re.IGNORECASE),
    re.compile(r"\b(ValueError|KeyError|TypeError|RuntimeError|PermissionError|FileNotFoundError)\b", re.IGNORECASE),
]

# Compound AC indicators (multiple predicates = not atomic)
_COMPOUND_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\band\b.*\band\b", re.IGNORECASE),  # 2+ "and"s = definitely compound
    re.compile(r";\s*\w"),                             # semicolon separator
    re.compile(r"\bAlso\b.*\b(and|while|then)\b", re.IGNORECASE),
]

# API surface mention patterns in description
_FUNC_RE = re.compile(r"\b(?:function|method|def)\s+`?(\w+)`?|\b`(\w+)\(\)`", re.IGNORECASE)
_CLASS_RE = re.compile(r"\b(?:class|model)\s+`?(\w+)`?", re.IGNORECASE)
_FILE_RE = re.compile(r"\b(?:file|module)\s+`?([\w/.\-]+\.py)`?|`([\w/.\-]+\.py)`", re.IGNORECASE)

# AC coverage patterns
_AC_FILE_RE = re.compile(r"^File exists\s*:\s*(\S+)", re.IGNORECASE)
_AC_FUNC_RE = re.compile(r"^Function defined\s*:\s*([\w.]+)", re.IGNORECASE)
_AC_CLASS_RE = re.compile(r"^Class defined\s*:\s*([\w.]+)", re.IGNORECASE)

# English stop-words shared between is_code_shaped_token and _score_contract_completeness
_SURFACE_STOPWORDS: frozenset[str] = frozenset({
    "defined", "implemented", "declared", "created", "added", "updated",
    "called", "named", "used", "the", "a", "an", "is", "be", "this",
    "that", "above", "below", "here", "it",
})

# Bare .py path pattern (no "file"/"module" keyword required) — used by extract_py_paths
_RAW_PY_PATH_RE = re.compile(r"[\w./\-]+\.py")


# ---------------------------------------------------------------------------
# Public helpers (exposed for testing and reuse)
# ---------------------------------------------------------------------------

def _is_code_identifier(token: str) -> bool:
    """Return True when *token* looks like a code identifier rather than prose.

    The contract_completeness sub-metric uses this to decide whether a word
    extracted from a description is an API surface that must be covered by an
    AC. Plain English words ("defined", "name", "gate", "correctly") are NOT
    code-shaped; real symbols have an underscore, a dot, internal CamelCase,
    or a .py extension.

    Rules (applied in order):
    1. Empty string → False.
    2. Token is in ``_SURFACE_STOPWORDS`` → False (English filler words).
    3. All-uppercase token (NAME, TODO, FOO) → False (prose emphasis/placeholders).
    4. Pluralised acronym (e.g. "ACs", "IDs") → False.
    5. Has underscore, dot, ``.py`` suffix, or internal CamelCase (BOTH upper
       and lower letters required, so "RetryCounter" qualifies but "NAME" does
       not) → True.
    6. Otherwise → False (bare lowercase dictionary word).
    """
    if not token:
        return False
    if token.lower() in _SURFACE_STOPWORDS:
        return False
    # All-uppercase tokens (NAME, TODO, FOO, UPPER_CASE) are prose emphasis or
    # template placeholders — not real code symbols requiring AC coverage.
    if token.isupper():
        return False
    # Pluralised acronym: trailing 's', body all-caps (e.g. "ACs", "IDs")
    if len(token) > 1 and token.endswith("s") and token[:-1].isupper():
        return False
    # CamelCase requires BOTH an uppercase letter and a lowercase letter so that
    # pure acronyms embedded mid-word don't qualify as "CamelCase".
    has_camel = any(c.isupper() for c in token[1:]) and any(c.islower() for c in token)
    return ("_" in token) or ("." in token) or token.endswith(".py") or has_camel


# Public alias for backwards compatibility and external callers
is_code_shaped_token = _is_code_identifier

# AC-required alias: Function defined: spec_quality_score.is_code_shaped
is_code_shaped = _is_code_identifier


def filter_english_stopwords(tokens: list[str]) -> list[str]:
    """Return *tokens* with English stop-words and non-code-shaped tokens removed.

    A token is removed when it:
    - Is in :data:`_SURFACE_STOPWORDS` (English filler words such as "defined",
      "implemented", "name", "correctly").
    - Is all-uppercase (prose emphasis / template placeholder, e.g. ``NAME``,
      ``TODO``).
    - Is a pluralised acronym (e.g. ``ACs``, ``IDs``).
    - Is a bare lowercase dictionary word (no ``_``, ``.``, ``.py``, or CamelCase).

    This is the inverse of :func:`filter_api_surfaces` — it returns only the
    tokens that are definitively English prose, so callers can audit what was
    stripped.  For extracting code-shaped tokens, use :func:`filter_api_surfaces`
    or :func:`is_code_shaped_token`.

    Parameters
    ----------
    tokens:
        List of candidate tokens from a feature description.

    Returns
    -------
    list[str]
        Filtered list containing only non-code-shaped (English prose) tokens
        (order preserved).
    """
    return [t for t in tokens if not _is_code_identifier(t)]


def filter_api_surfaces(tokens: list[str]) -> list[str]:
    """Return only the code-shaped tokens from *tokens*, filtering out prose words.

    A token is code-shaped when it:
    - Contains an underscore (``_``), a dot (``.``), a ``.py`` extension, or
      internal CamelCase (has BOTH upper and lower letters).
    - Is NOT a bare lowercase dictionary word or an English stop-word
      (see :data:`_SURFACE_STOPWORDS`).
    - Is NOT an all-uppercase token (prose emphasis / template placeholder).
    - Is NOT a pluralised acronym (e.g. ``ACs``, ``IDs``).

    This is the public companion to :func:`is_code_shaped_token` that operates
    on a list of tokens and is used by :func:`_score_contract_completeness` to
    decide which words in a description are real API surfaces that must be
    covered by an AC.

    Parameters
    ----------
    tokens:
        List of candidate surface tokens extracted from a feature description.

    Returns
    -------
    list[str]
        Filtered list containing only code-shaped tokens (order preserved).
    """
    return [t for t in tokens if _is_code_identifier(t)]


# AC-required alias: Function defined: spec_quality_score.filter_code_surfaces
filter_code_surfaces = filter_api_surfaces

# AC-required alias: Function defined: spec_quality_score.filter_code_shaped_surfaces
filter_code_shaped_surfaces = filter_api_surfaces


def extract_concrete_py_paths(description: str) -> list[str]:
    """Return sorted, deduplicated list of concrete ``.py`` paths named in *description*.

    Public alias for :func:`extract_py_paths` — same semantics, canonical name
    used by the spec synthesizer and scorer to satisfy the
    ``Function defined: spec_quality_score.extract_concrete_py_paths`` AC.

    Only paths with a ``/`` separator or starting with ``test`` are kept
    (bare filenames without a directory component are ambiguous and skipped).

    Parameters
    ----------
    description:
        Free-form feature description text.

    Returns
    -------
    list[str]
        Sorted, deduplicated concrete ``.py`` paths from the description.
    """
    return extract_py_paths(description)


# Public alias matching AC: Function defined: spec_quality_score.extract_py_paths_from_description
def extract_py_paths_from_description(description: str) -> list[str]:
    """Return sorted, deduplicated concrete ``.py`` paths named in *description*.

    Alias for :func:`extract_py_paths` — canonical name used by the spec
    synthesizer AC ``Function defined: spec_quality_score.extract_py_paths_from_description``.

    Parameters
    ----------
    description:
        Free-form feature description text.

    Returns
    -------
    list[str]
        Sorted, deduplicated concrete ``.py`` paths from the description.
    """
    return extract_py_paths(description)


def extract_py_paths(description: str) -> list[str]:
    """Return sorted, deduplicated list of concrete ``.py`` paths named in *description*.

    Only paths that contain a ``/`` separator or start with ``test`` are kept
    (bare filenames like ``foo.py`` without a directory component are skipped
    because they are ambiguous). This mirrors the heuristic used by
    :func:`_ensure_described_files_covered` in the spec synthesizer.

    Parameters
    ----------
    description:
        Free-form feature description text.

    Returns
    -------
    list[str]
        Sorted, deduplicated list of ``.py`` paths that are concrete enough to
        emit a ``File exists:`` AC for.
    """
    if not description:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for path in _RAW_PY_PATH_RE.findall(description):
        if path in seen:
            continue
        # Keep only paths with a directory component or test_ prefix
        if "/" not in path and not path.startswith("test"):
            continue
        seen.add(path)
        result.append(path)
    return sorted(result)


def check_contract_completeness(
    description: str | None,
    acceptance_criteria: list[str],
) -> tuple[float, list[str]]:
    """Public wrapper around :func:`_score_contract_completeness`.

    Returns ``(score, hints)`` where *score* is the fraction of described API
    surfaces covered by an AC and *hints* lists any uncovered surfaces.

    Only code-shaped tokens (containing ``_``, ``.``, ``.py``, or internal
    CamelCase) are treated as API surfaces — plain English prose words are
    ignored.

    Parameters
    ----------
    description:
        Feature description text (may be ``None``).
    acceptance_criteria:
        List of AC strings to check coverage against.

    Returns
    -------
    tuple[float, list[str]]
        ``(score, hints)`` where ``score`` is in ``[0.0, 1.0]``.
    """
    return _score_contract_completeness(description, acceptance_criteria)


# Public alias matching the AC name: Function defined: spec_quality_score.score_contract_completeness
score_contract_completeness = check_contract_completeness


def emit_file_exists_acs(
    criteria: list[str],
    description: str,
) -> tuple[list[str], list[str]]:
    """Inject ``File exists: <path>`` ACs for .py paths named in *description*.

    Post-synthesis helper: scans *description* for concrete ``.py`` paths
    (those containing a ``/`` separator or starting with ``test``). For each
    path not already covered by an existing AC, a ``File exists: <path>`` AC
    is appended to *criteria*.

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


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CompositeScore:
    """Result of spec_quality_score.compute()."""

    # Sub-metrics
    smell_density: float
    predicate_coverage: float
    contract_completeness: float
    boundary_coverage: float
    error_path_coverage: float
    traceability: float
    spec_executability: float
    ac_atomicity: float

    # Composite weighted geometric mean
    composite: float

    # Human-readable rationale when blocked
    rationale: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "composite": self.composite,
            "sub_metrics": {
                "smell_density": self.smell_density,
                "predicate_coverage": self.predicate_coverage,
                "contract_completeness": self.contract_completeness,
                "boundary_coverage": self.boundary_coverage,
                "error_path_coverage": self.error_path_coverage,
                "traceability": self.traceability,
                "spec_executability": self.spec_executability,
                "ac_atomicity": self.ac_atomicity,
            },
            "weights": _WEIGHTS,
            "gate_block": GATE_BLOCK,
            "gate_warn": GATE_WARN,
        }


# ---------------------------------------------------------------------------
# Sub-metric implementations
# ---------------------------------------------------------------------------

def _score_smell_density(criteria: list[str]) -> tuple[float, list[str]]:
    """Fraction of ACs that are free of E-severity smells."""
    if not criteria:
        return 0.0, ["No acceptance criteria — smell_density = 0"]
    hints: list[str] = []
    clean = 0
    for i, ac in enumerate(criteria):
        smelly = False
        for pat in _E_SMELL_PATTERNS:
            if pat.search(ac):
                hints.append(f"AC[{i}] has a spec smell: {ac!r}")
                smelly = True
                break
        if not smelly:
            clean += 1
    return clean / len(criteria), hints


def _score_predicate_coverage(criteria: list[str]) -> tuple[float, list[str]]:
    """Fraction of ACs with a concrete, verifiable predicate.

    A predicate is concrete when the AC matches a structured form OR contains
    a measurable assertion (a file path, module path, test path, number, etc.).
    """
    if not criteria:
        return 0.0, ["No ACs — predicate_coverage = 0"]
    hints: list[str] = []
    covered = 0
    _concrete = re.compile(r"[\w/.\-]+\.(py|yaml|yml|json|sh|txt)|tests?/|src/|\d+\.\d+|\d+%", re.IGNORECASE)
    for i, ac in enumerate(criteria):
        if any(p.match(ac.strip()) for p in _AC_FORMS) or _concrete.search(ac):
            covered += 1
        else:
            hints.append(f"AC[{i}] has no concrete predicate: {ac!r}")
    return covered / len(criteria), hints


def _score_contract_completeness(
    description: str | None,
    criteria: list[str],
) -> tuple[float, list[str]]:
    """Fraction of described API surfaces that have a corresponding AC."""
    if not description:
        return 1.0, []  # nothing described → nothing missing

    mentions: set[str] = set()
    for m in _FUNC_RE.finditer(description):
        name = m.group(1) or m.group(2)
        if name and _is_code_identifier(name):
            mentions.add(name.lower())
    for m in _CLASS_RE.finditer(description):
        if m.group(1) and _is_code_identifier(m.group(1)):
            mentions.add(m.group(1).lower())
    for m in _FILE_RE.finditer(description):
        name = m.group(1) or m.group(2)
        if name:  # _FILE_RE already requires a .py, so it's code-shaped
            mentions.add(name.lower())

    if not mentions:
        return 1.0, []

    covered: set[str] = set()
    for ac in criteria:
        m = _AC_FILE_RE.match(ac.strip())
        if m:
            path = m.group(1)
            covered.add(path.lower())
            covered.add(Path(path).stem.lower())
            continue
        m = _AC_FUNC_RE.match(ac.strip())
        if m:
            full = m.group(1).lower()
            covered.add(full)
            covered.add(full.split(".")[-1])
            continue
        m = _AC_CLASS_RE.match(ac.strip())
        if m:
            full = m.group(1).lower()
            covered.add(full)
            covered.add(full.split(".")[-1])

    hints: list[str] = []
    uncovered = set()
    for mention in mentions:
        if not any(mention in c or c.endswith(mention) or mention in c.split("/")[-1] for c in covered):
            uncovered.add(mention)
            hints.append(f"API surface {mention!r} has no AC")

    if not uncovered:
        return 1.0, []
    return (len(mentions) - len(uncovered)) / len(mentions), hints


def _score_boundary_coverage(criteria: list[str]) -> tuple[float, list[str]]:
    """Fraction of ACs that explicitly address a boundary / edge condition."""
    if not criteria:
        return 0.0, ["No ACs — boundary_coverage = 0"]
    # Count ACs that mention any boundary/edge indicator.
    # If none of the ACs mention any boundaries at all, score = 0.
    found = sum(
        1 for ac in criteria
        if any(p.search(ac) for p in _BOUNDARY_PATTERNS)
    )
    if found == 0:
        return 0.0, ["No ACs mention boundary/edge/null/zero/max/min conditions"]
    # Score is bounded: we want at least one boundary AC per 5 ACs as ideal.
    ratio = found / len(criteria)
    # Normalize: 1+ boundary AC per 5 total → score 1.0
    score = min(1.0, ratio * 5)
    return score, []


def _score_error_path_coverage(criteria: list[str]) -> tuple[float, list[str]]:
    """Fraction of ACs that cover error / failure paths."""
    if not criteria:
        return 0.0, ["No ACs — error_path_coverage = 0"]
    found = sum(
        1 for ac in criteria
        if any(p.search(ac) for p in _ERROR_PATTERNS)
    )
    if found == 0:
        return 0.0, ["No ACs mention error/failure paths — add at least one negative/error AC"]
    ratio = found / len(criteria)
    score = min(1.0, ratio * 5)
    return score, []


def _score_traceability(criteria: list[str]) -> tuple[float, list[str]]:
    """Fraction of ACs that match a recognized structured form (traceable to a spec construct)."""
    if not criteria:
        return 0.0, ["No ACs — traceability = 0"]
    hints: list[str] = []
    traceable = 0
    for i, ac in enumerate(criteria):
        if any(p.match(ac.strip()) for p in _AC_FORMS):
            traceable += 1
        else:
            hints.append(f"AC[{i}] does not match any structured form: {ac!r}")
    return traceable / len(criteria), hints


def _score_spec_executability(criteria: list[str]) -> tuple[float, list[str]]:
    """Fraction of ACs that can be mechanically verified.

    An AC is executable when it matches a pytest:, File exists:, Function defined:,
    Class defined:, or Field exists: form — i.e. something a CI script can check.
    """
    if not criteria:
        return 0.0, ["No ACs — spec_executability = 0"]
    _executable_forms: list[re.Pattern[str]] = [
        re.compile(r"^pytest\s*:\s*\S+", re.IGNORECASE),
        re.compile(r"^File exists\s*:\s*\S+", re.IGNORECASE),
        re.compile(r"^Function defined\s*:\s*[\w.]+", re.IGNORECASE),
        re.compile(r"^Class defined\s*:\s*[\w.]+", re.IGNORECASE),
        re.compile(r"^Field exists\s*.*:\s*\S+", re.IGNORECASE),
        re.compile(r"^integration\s*:\s*[\w./:-]+", re.IGNORECASE),
        re.compile(r"^python\s*:\s*\S+", re.IGNORECASE),
        re.compile(r"^CI tests\s*:\s*\S+", re.IGNORECASE),
    ]
    hints: list[str] = []
    executable = 0
    for i, ac in enumerate(criteria):
        if any(p.match(ac.strip()) for p in _executable_forms):
            executable += 1
        else:
            hints.append(f"AC[{i}] is not mechanically verifiable: {ac!r}")
    return executable / len(criteria), hints


def _score_ac_atomicity(criteria: list[str]) -> tuple[float, list[str]]:
    """Fraction of ACs that describe exactly one observable behavior (atomic)."""
    if not criteria:
        return 0.0, ["No ACs — ac_atomicity = 0"]
    hints: list[str] = []
    atomic = 0
    for i, ac in enumerate(criteria):
        compound = any(p.search(ac) for p in _COMPOUND_PATTERNS)
        if not compound:
            atomic += 1
        else:
            hints.append(f"AC[{i}] appears compound (multiple observables): {ac!r}")
    return atomic / len(criteria), hints


# ---------------------------------------------------------------------------
# Weighted geometric mean
# ---------------------------------------------------------------------------

def _weighted_geometric_mean(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Compute weighted geometric mean: prod(s_i ^ w_i).

    If any score is 0, the result is 0 (one fatal flaw dominates).
    """
    product = 1.0
    for key, weight in weights.items():
        score = scores[key]
        if score <= 0.0:
            return 0.0
        product *= score ** weight
    return round(min(1.0, max(0.0, product)), 6)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Path | str | None = None,
) -> CompositeScore:
    """Compute the composite spec quality score for a single feature.

    Returns a :class:`CompositeScore` with all 8 sub-metrics and the composite
    weighted geometric mean.

    Parameters
    ----------
    name:
        Feature name (used in hints).
    description:
        Feature description (used for contract_completeness).
    acceptance_criteria:
        List of AC strings, or JSON-encoded list, or newline-separated string.
    workspace:
        Project root (unused currently; reserved for future integration checks).
    """
    import json as _json

    # Normalize acceptance_criteria to list[str]
    criteria: list[str]
    if isinstance(acceptance_criteria, list):
        criteria = [str(c) for c in acceptance_criteria]
    elif isinstance(acceptance_criteria, str):
        stripped = acceptance_criteria.strip()
        if stripped.startswith("["):
            try:
                parsed = _json.loads(stripped)
                criteria = [str(c) for c in parsed] if isinstance(parsed, list) else [stripped]
            except (_json.JSONDecodeError, ValueError):
                criteria = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        else:
            criteria = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    else:
        criteria = []

    rationale: list[str] = []

    if not criteria:
        zero = CompositeScore(
            smell_density=0.0,
            predicate_coverage=0.0,
            contract_completeness=0.0,
            boundary_coverage=0.0,
            error_path_coverage=0.0,
            traceability=0.0,
            spec_executability=0.0,
            ac_atomicity=0.0,
            composite=0.0,
            rationale=["No acceptance criteria provided."],
        )
        return zero

    smell, smell_hints = _score_smell_density(criteria)
    predicate, pred_hints = _score_predicate_coverage(criteria)
    contract, contract_hints = _score_contract_completeness(description, criteria)
    boundary, boundary_hints = _score_boundary_coverage(criteria)
    error, error_hints = _score_error_path_coverage(criteria)
    trace, trace_hints = _score_traceability(criteria)
    executability, exec_hints = _score_spec_executability(criteria)
    atomicity, atom_hints = _score_ac_atomicity(criteria)

    scores = {
        "smell_density": smell,
        "predicate_coverage": predicate,
        "contract_completeness": contract,
        "boundary_coverage": boundary,
        "error_path_coverage": error,
        "traceability": trace,
        "spec_executability": executability,
        "ac_atomicity": atomicity,
    }

    composite = _weighted_geometric_mean(scores, _WEIGHTS)

    all_hints = (
        smell_hints + pred_hints + contract_hints + boundary_hints
        + error_hints + trace_hints + exec_hints + atom_hints
    )

    return CompositeScore(
        smell_density=smell,
        predicate_coverage=predicate,
        contract_completeness=contract,
        boundary_coverage=boundary,
        error_path_coverage=error,
        traceability=trace,
        spec_executability=executability,
        ac_atomicity=atomicity,
        composite=composite,
        rationale=all_hints,
    )
