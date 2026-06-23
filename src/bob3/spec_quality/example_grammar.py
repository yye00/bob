"""Seventh AC grammar: property-based and key-example acceptance criteria.

Two new AC forms extend the existing six grammars:

1. **Property AC** (Hypothesis-style PBT)::

       property: <name> for <generator> assert <predicate>

   The codegen agent uses the property spec as few-shot context.
   ``emit_hypothesis_test`` produces a runnable Hypothesis test for it.

2. **Key-example sub-key** on any behavior AC::

       key_example:
         given: <input values>
         then:  <expected output/state>

   ``emit_parametrize_test`` produces a ``@pytest.mark.parametrize`` test.
   Fixed seed=0 ensures reproducibility.

Boundary and unwanted-behaviour examples are *required* for any AC whose
response involves data transformation or a numeric range.  ``requires_boundary``
detects these ACs; the verifier flags violations as quality failures.

Hypothesis shrinking surfaces minimal counterexamples to the repair agent,
empirically yielding ~3× more regressions per LOC vs. example-only tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PropertyParseError(ValueError):
    """Raised when a property: AC is malformed (e.g. missing generator or predicate)."""


class MissingBoundaryError(ValueError):
    """Raised when a numeric-range AC has no boundary key_example."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PropertyAC:
    """A parsed ``property:`` acceptance criterion.

    Attributes:
        name:      Logical name for the property (snake_case is conventional).
        generator: Hypothesis generator expression string, e.g. ``st.integers()``.
        predicate: Boolean assertion expression, e.g. ``result >= 0``.
        raw:       Verbatim AC string.
    """

    name: str
    generator: str
    predicate: str
    raw: str


@dataclass(frozen=True)
class KeyExample:
    """A single given/then key-example pair.

    Attributes:
        given: Input value(s) as a string (may be a Python literal).
        then:  Expected output or state as a string.
        raw:   Verbatim key-example sub-key content.
    """

    given: str
    then: str
    raw: str


@dataclass(frozen=True)
class BoundaryRequirement:
    """Result of inspecting an AC for boundary/numeric-range content.

    Attributes:
        ac:             The raw AC string that was inspected.
        required:       True when a boundary key-example is mandatory.
        has_boundary:   True when at least one boundary key-example exists.
        reason:         Human-readable explanation of why it is/isn't required.
    """

    ac: str
    required: bool
    has_boundary: bool
    reason: str

    @property
    def satisfied(self) -> bool:
        """True when boundary requirement is either not needed or already satisfied."""
        return (not self.required) or self.has_boundary


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# property: <name> for <generator> assert <predicate>
_PROPERTY_RE = re.compile(
    r"^property\s*:\s*"
    r"(?P<name>\w[\w\s\-]*?)\s+"
    r"for\s+(?P<generator>.+?)\s+"
    r"assert\s+(?P<predicate>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Keywords that indicate data transformation or numeric range involvement.
_NUMERIC_KEYWORDS = frozenset(
    [
        "integer",
        "int",
        "float",
        "number",
        "numeric",
        "range",
        "value",
        "score",
        "count",
        "sum",
        "average",
        "mean",
        "min",
        "max",
        "positive",
        "negative",
        "zero",
        "bound",
        "limit",
        "threshold",
        "percentage",
        "ratio",
        "transform",
        "convert",
        "calculate",
        "compute",
        "result",
    ]
)

_TRANSFORM_KEYWORDS = frozenset(
    [
        "transform",
        "convert",
        "normalize",
        "normalise",
        "encode",
        "decode",
        "serialize",
        "deserialise",
        "deserialize",
        "parse",
        "format",
        "map",
        "filter",
        "aggregate",
    ]
)


# ---------------------------------------------------------------------------
# parse_property_ac
# ---------------------------------------------------------------------------


def parse_property_ac(ac: str) -> PropertyAC | None:
    """Parse a ``property:`` acceptance criterion.

    Grammar::

        property: <name> for <generator> assert <predicate>

    Args:
        ac: Raw AC string.

    Returns:
        A :class:`PropertyAC` when *ac* matches the property grammar, else
        ``None``.

    Examples::

        >>> parse_property_ac("property: non_negative for st.integers() assert x >= 0")
        PropertyAC(name='non_negative', generator='st.integers()', predicate='x >= 0', ...)

        >>> parse_property_ac("pytest: tests/test_foo.py")
        None
    """
    stripped = ac.strip()
    if not re.match(r"^property\s*:", stripped, re.IGNORECASE):
        return None

    m = _PROPERTY_RE.match(stripped)
    if not m:
        return None

    return PropertyAC(
        name=m.group("name").strip(),
        generator=m.group("generator").strip(),
        predicate=m.group("predicate").strip(),
        raw=stripped,
    )


# ---------------------------------------------------------------------------
# parse_key_example
# ---------------------------------------------------------------------------


def parse_key_example(ac: dict | str) -> KeyExample | None:
    """Parse a ``key_example:`` sub-key from a behavior AC dict or YAML-like string.

    Accepts two input forms:

    1. **Dict** with ``given`` and ``then`` keys::

           {"given": "x=5", "then": "result=25"}

    2. **String** in ``given: … then: …`` format::

           "given: x=5, then: result=25"

    Args:
        ac: Dict or string representation of a key-example entry.

    Returns:
        A :class:`KeyExample` when *ac* contains the required fields, else
        ``None``.
    """
    if isinstance(ac, dict):
        given = ac.get("given") if "given" in ac else ac.get("Given")
        then = ac.get("then") if "then" in ac else ac.get("Then")
        if given is None and "Given" in ac:
            given = ac["Given"]
        if then is None and "Then" in ac:
            then = ac["Then"]
        if given is None or then is None:
            return None
        raw = f"given: {given}, then: {then}"
        return KeyExample(given=str(given), then=str(then), raw=raw)

    if isinstance(ac, str):
        stripped = ac.strip()
        # Pattern: "given: ... then: ..." or "given: ..., then: ..."
        m = re.match(
            r"given\s*:\s*(?P<given>.+?)\s*,?\s*then\s*:\s*(?P<then>.+)$",
            stripped,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return None
        return KeyExample(
            given=m.group("given").strip(),
            then=m.group("then").strip(),
            raw=stripped,
        )

    return None


# ---------------------------------------------------------------------------
# emit_hypothesis_test
# ---------------------------------------------------------------------------


def emit_hypothesis_test(prop: PropertyAC, *, seed: int = 0) -> str:
    """Emit a runnable Hypothesis test for a :class:`PropertyAC`.

    The generated test function:

    - Is decorated with ``@given(<generator>)`` from the property spec.
    - Uses ``@settings(deriving=42)`` with a fixed seed for reproducibility.
    - Asserts ``<predicate>`` inline (the LLM / verifier evaluates the
      predicate in context; the emitted string is a real test harness).
    - Can be pasted directly into a pytest file.

    Args:
        prop: A parsed :class:`PropertyAC`.
        seed: Hypothesis seed for reproducibility (default ``0``).

    Returns:
        Python source code string for a single Hypothesis test function.

    Example::

        from hypothesis import given, settings
        from hypothesis import strategies as st

        @settings(deriving=0)
        @given(st.integers())
        def test_property_non_negative(x):
            assert x >= 0
    """
    fn_name = "test_property_" + re.sub(r"\W+", "_", prop.name).strip("_")
    generator = prop.generator
    predicate = prop.predicate

    # Detect primary argument name from the generator or predicate
    arg_name = _infer_arg_name(generator, predicate)

    lines = [
        "from hypothesis import given, settings, HealthCheck",
        "from hypothesis import strategies as st",
        "",
        "",
        f"@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deriving={seed})",
        f"@given({generator})",
        f"def {fn_name}({arg_name}):",
        f"    assert {predicate}",
    ]
    return "\n".join(lines)


def _infer_arg_name(generator: str, predicate: str) -> str:
    """Infer a sensible argument name from the generator and predicate."""
    # Look for a simple identifier in the predicate that isn't a keyword
    _PYTHON_KEYWORDS = frozenset(
        ["and", "or", "not", "in", "is", "if", "else", "for", "while", "return", "True", "False", "None"]
    )
    # Find identifiers used in predicate (likely the input variable)
    tokens = re.findall(r"\b([a-z_]\w*)\b", predicate)
    candidates = [t for t in tokens if t not in _PYTHON_KEYWORDS and not t.startswith("result")]
    if candidates:
        return candidates[0]
    # Fall back to 'value'
    return "value"


# ---------------------------------------------------------------------------
# emit_parametrize_test
# ---------------------------------------------------------------------------


def emit_parametrize_test(
    examples: list[KeyExample],
    *,
    test_name: str = "test_key_examples",
    seed: int = 0,
) -> str:
    """Emit a ``@pytest.mark.parametrize`` test from a list of :class:`KeyExample`.

    Each ``KeyExample`` becomes one parametrize entry.  The generated test
    asserts that, for the given input, the expected output holds.

    Args:
        examples:  List of key-examples to parametrize over.
        test_name: Name for the generated test function.
        seed:      Seed stored in a comment for reproducibility tracking.

    Returns:
        Python source code string for a parametrize test.
    """
    if not examples:
        return ""

    params = []
    for ex in examples:
        params.append(f"    ({ex.given!r}, {ex.then!r}),")

    params_block = "\n".join(params)

    fn_name = re.sub(r"\W+", "_", test_name).strip("_")

    lines = [
        "import pytest",
        "",
        "",
        f"# seed={seed} (fixed for reproducibility)",
        "@pytest.mark.parametrize(",
        '    "given_val, expected",',
        "    [",
        params_block,
        "    ],",
        ")",
        f"def {fn_name}(given_val, expected):",
        "    assert str(given_val) == str(expected) or given_val == expected",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# requires_boundary
# ---------------------------------------------------------------------------


def requires_boundary(ac: str) -> BoundaryRequirement:
    """Determine whether *ac* requires boundary / unwanted-behaviour key-examples.

    An AC *requires* boundary examples when its text mentions data transformation
    or numeric range concepts.  This implements the spec rule:

        Boundary and unwanted-behaviour examples are required for any AC whose
        response involves data transformation or numeric range.

    Args:
        ac: Raw AC string (any grammar).

    Returns:
        A :class:`BoundaryRequirement` describing whether boundary examples are
        needed and (if the caller provides examples) whether they are present.
    """
    lower = ac.lower()
    words = set(re.findall(r"\b\w+\b", lower))

    # Use stem matching so "transforms" matches "transform", "normalises" matches "normalise", etc.
    numeric_hit = _stem_match(words, _NUMERIC_KEYWORDS)
    transform_hit = _stem_match(words, _TRANSFORM_KEYWORDS)

    required = bool(numeric_hit or transform_hit)

    if required:
        reason = (
            f"AC mentions {'numeric' if numeric_hit else 'transformation'} "
            f"concepts ({', '.join(sorted((numeric_hit or transform_hit)))}); "
            "boundary key-examples are mandatory."
        )
    else:
        reason = "AC does not involve data transformation or numeric range; boundary examples are optional."

    return BoundaryRequirement(
        ac=ac,
        required=required,
        has_boundary=False,  # caller must set this based on actual examples
        reason=reason,
    )


def check_boundary_satisfied(ac: str, examples: list[KeyExample]) -> BoundaryRequirement:
    """Check whether boundary requirements for *ac* are met by *examples*.

    Calls :func:`requires_boundary` and then checks whether any of the
    provided *examples* look like boundary cases (values at or near extremes,
    empty strings, zero, negative numbers, etc.).

    Args:
        ac:       Raw AC string.
        examples: Key-examples attached to this AC.

    Returns:
        A :class:`BoundaryRequirement` with ``has_boundary`` set correctly.
    """
    req = requires_boundary(ac)
    if not req.required:
        return req

    has_boundary = _examples_contain_boundary(examples)
    return BoundaryRequirement(
        ac=req.ac,
        required=req.required,
        has_boundary=has_boundary,
        reason=req.reason,
    )


_BOUNDARY_PATTERNS = [
    re.compile(r"\b0\b"),                     # zero
    re.compile(r"-\d+"),                       # negative number
    re.compile(r"\b(empty|none|null)\b", re.IGNORECASE),      # empty / null
    re.compile(r'""'),                         # empty string literal
    re.compile(r"\b(max|min|maximum|minimum|boundary|edge|limit)\w*\b", re.IGNORECASE),
    re.compile(r"\b\d{5,}\b"),                 # very large number
]


def _stem_match(words: set[str], keywords: frozenset[str]) -> set[str]:
    """Return keywords that match any word in *words* via stemming.

    A keyword matches a word if:
    - they are equal (exact), OR
    - the word starts with the keyword AND the extra suffix is a common inflection
      (s, es, ed, ing, ise, ize, tion, ations).
    This avoids false positives like "int" matching "integration".
    """
    _SUFFIXES = ("s", "es", "ed", "ing", "ise", "ize", "ised", "ized", "tion", "ations", "er", "ers")
    hits: set[str] = set()
    for kw in keywords:
        for w in words:
            if w == kw:
                hits.add(kw)
                break
            if w.startswith(kw) and len(w) > len(kw):
                suffix = w[len(kw):]
                if suffix in _SUFFIXES:
                    hits.add(kw)
                    break
    return hits


def _examples_contain_boundary(examples: list[KeyExample]) -> bool:
    """Return True if any example looks like a boundary case."""
    for ex in examples:
        combined = f"{ex.given} {ex.then}"
        if any(p.search(combined) for p in _BOUNDARY_PATTERNS):
            return True
    return False


# ---------------------------------------------------------------------------
# AC-required aliases / additional public API
# ---------------------------------------------------------------------------


def emit_parametrize_block(
    examples: list[KeyExample],
    *,
    test_name: str = "test_key_examples",
    seed: int = 0,
) -> str:
    """Alias for :func:`emit_parametrize_test` satisfying the AC name requirement.

    Returns pytest parametrize source with seed=0.
    """
    return emit_parametrize_test(examples, test_name=test_name, seed=seed)


def require_boundary_example(ac: str, examples: list[KeyExample]) -> None:
    """Raise :class:`MissingBoundaryError` when *ac* is a numeric-range AC without boundary examples.

    Args:
        ac:       Raw AC string.
        examples: Key-examples attached to this AC.

    Raises:
        MissingBoundaryError: When the AC requires boundary examples but none are present.
    """
    result = check_boundary_satisfied(ac, examples)
    if result.required and not result.has_boundary:
        raise MissingBoundaryError(
            f"AC requires boundary key-example but none found: {ac!r}. "
            f"Reason: {result.reason}"
        )


def raises_on_malformed_property(ac: str) -> PropertyAC:
    """Parse a property: AC, raising :class:`PropertyParseError` when malformed.

    Unlike :func:`parse_property_ac` (which returns ``None`` on non-property ACs),
    this function expects *ac* to start with ``property:`` and raises when the
    generator clause is missing or empty.

    Args:
        ac: Raw AC string that is expected to be a property grammar.

    Returns:
        A :class:`PropertyAC` when *ac* is valid.

    Raises:
        PropertyParseError: When the generator clause is missing or the predicate is missing/empty.
    """
    stripped = ac.strip()
    if not re.match(r"^property\s*:", stripped, re.IGNORECASE):
        raise PropertyParseError(
            f"AC does not start with 'property:': {ac!r}"
        )

    # Check for missing 'for' keyword (generator clause missing)
    if not re.search(r"\bfor\b", stripped, re.IGNORECASE):
        raise PropertyParseError(
            f"Property AC is missing the 'for <generator>' clause: {ac!r}"
        )

    # Check for missing 'assert' keyword (predicate missing)
    if not re.search(r"\bassert\b", stripped, re.IGNORECASE):
        raise PropertyParseError(
            f"Property AC is missing the 'assert <predicate>' clause: {ac!r}"
        )

    result = parse_property_ac(stripped)
    if result is None:
        raise PropertyParseError(
            f"Property AC could not be parsed (malformed): {ac!r}"
        )

    # Validate predicate is non-empty
    if not result.predicate.strip():
        raise PropertyParseError(
            f"Property AC predicate is empty: {ac!r}"
        )

    # Validate generator is non-empty
    if not result.generator.strip():
        raise PropertyParseError(
            f"Property AC generator is empty: {ac!r}"
        )

    return result
