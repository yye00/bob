"""Key-example sub-key extraction for behavior ACs.

Exposes ``extract_key_examples`` which parses a list of raw key-example
entries (dicts or strings) and returns structured :class:`KeyExample` objects.

Used by:

- The codegen agent to obtain few-shot context from key-examples.
- The verifier, which emits one ``@pytest.mark.parametrize`` test per
  key-example (``seed=0`` for reproducibility).

Public API
----------
- ``extract_key_examples`` — parse a list of raw key-example entries.
- ``KeyExample``            — re-exported dataclass for typed access.
"""

from __future__ import annotations

from typing import Any

from bob.spec_quality.example_grammar import (
    KeyExample,
    check_boundary_satisfied,
    emit_parametrize_test,
    parse_key_example,
    requires_boundary,
)

__all__ = [
    "KeyExample",
    "extract_key_examples",
    "emit_parametrize_tests",
    "check_boundary_requirement",
]


def extract_key_examples(
    entries: list[Any] | None,
    *,
    strict: bool = False,
) -> list[KeyExample]:
    """Parse a list of raw key-example entries.

    Each entry may be:

    - A :class:`dict` with ``given`` and ``then`` keys.
    - A :class:`str` in ``given: … then: …`` format.
    - ``None`` (silently skipped).

    Args:
        entries: List of raw key-example entries.  May be ``None`` or an
                 empty list.
        strict:  When ``True``, raise :class:`ValueError` for dict entries
                 that are non-empty but missing both ``given`` and ``then``
                 keys.  When ``False`` (the default), such entries are
                 silently skipped.

    Returns:
        A list of :class:`KeyExample` objects.  Invalid or ``None`` entries
        are dropped; the list may be empty.

    Raises:
        ValueError: When *strict* is ``True`` and a dict entry is malformed
                    (non-empty but missing ``given``/``then``).

    Examples::

        >>> extract_key_examples([{"given": "0", "then": "0"}, {"given": "1", "then": "1"}])
        [KeyExample(given='0', then='0', raw='given: 0, then: 0'),
         KeyExample(given='1', then='1', raw='given: 1, then: 1')]

        >>> extract_key_examples(None)
        []

        >>> extract_key_examples([])
        []
    """
    if not entries:
        return []

    results: list[KeyExample] = []
    for entry in entries:
        if entry is None:
            continue
        if strict and isinstance(entry, dict) and entry:
            has_given = "given" in entry or "Given" in entry
            has_then = "then" in entry or "Then" in entry
            if not has_given and not has_then:
                raise ValueError(
                    f"Key-example dict is missing both 'given' and 'then' keys: {entry!r}"
                )
        ex = parse_key_example(entry)
        if ex is not None:
            results.append(ex)

    return results


def emit_parametrize_tests(
    examples: list[KeyExample],
    *,
    test_name: str = "test_key_examples",
    seed: int = 0,
) -> str:
    """Emit a ``@pytest.mark.parametrize`` test from key-examples.

    Convenience wrapper around
    :func:`~bob.spec_quality.example_grammar.emit_parametrize_test`.

    Args:
        examples:  Key-examples to parametrize over.
        test_name: Name for the generated test function.
        seed:      Seed stored in a comment for reproducibility tracking.

    Returns:
        Python source code string, or ``""`` when *examples* is empty.
    """
    return emit_parametrize_test(examples, test_name=test_name, seed=seed)


def check_boundary_requirement(
    ac: str,
    examples: list[KeyExample],
) -> bool:
    """Return ``True`` when boundary requirements for *ac* are satisfied.

    An AC requires boundary examples when it mentions numeric range or data
    transformation keywords.  The requirement is satisfied when at least one
    of *examples* looks like a boundary case (zero, empty, negative, extreme).

    Args:
        ac:       Raw AC string.
        examples: Key-examples to check.

    Returns:
        ``True`` when boundary requirements are met (or not required).
        ``False`` when boundary examples are required but none are present.
    """
    result = check_boundary_satisfied(ac, examples)
    return result.satisfied
