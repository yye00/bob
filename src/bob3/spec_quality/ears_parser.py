"""EARS-style behavior acceptance criterion parser and evaluator.

Sixth AC grammar alongside File exists, Function defined, Class defined,
pytest, and integration:

    behavior: <subject> <verb> <object> when <condition>

``parse_behavior_ac`` extracts the structured (subject, verb, object,
condition) tuple from a raw AC string. ``evaluate_behavior_ac`` produces
a structured grading prompt that the independent evaluator can use to ask
specifically whether the generated code exhibits the exact subject-verb-object
under the exact condition, rather than consulting freeform prose.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob3.spec_quality.contract_grammar import ContractSpec


class EARSParseError(ValueError):
    """Raised when a ``behavior:`` AC string is malformed."""

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_BEHAVIOR_RE = re.compile(
    r"^behavior\s*:\s*"
    r"(?P<subject>.+?)\s+"
    r"(?P<verb>\w+(?:\s+\w+){0,2}?)\s+"
    r"(?P<object>.+?)\s+"
    r"when\s+(?P<condition>.+)$",
    re.IGNORECASE,
)

# Simpler fallback: capture everything before "when" as SVO, then condition.
_BEHAVIOR_SIMPLE_RE = re.compile(
    r"^behavior\s*:\s*(?P<svo>.+?)\s+when\s+(?P<condition>.+)$",
    re.IGNORECASE,
)

# Verb-split: split SVO around the first verb-like token (lowercase, no digits)
_VERB_SPLIT_RE = re.compile(
    r"^(?P<subject>\S+(?:\s+\S+){0,3}?)\s+(?P<verb>[a-z]\w+(?:\s+[a-z]\w+)?)\s+(?P<object>.+)$"
)


@dataclass(frozen=True)
class BehaviorAC:
    """Parsed EARS-style behavior acceptance criterion.

    Attributes:
        raw:       The verbatim AC string after stripping the ``behavior:`` prefix.
        subject:   Who/what performs the action.
        verb:      The observable action verb phrase.
        object:    What the action is performed on.
        condition: The triggering condition (the ``when …`` clause).
    """

    raw: str
    subject: str
    verb: str
    object: str
    condition: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_behavior_ac(ac: str) -> BehaviorAC | None:
    """Parse a ``behavior:`` acceptance criterion into its components.

    Returns a :class:`BehaviorAC` if *ac* matches the behavior grammar, or
    ``None`` if it does not (so callers can skip non-behavior AC strings).

    Grammar::

        behavior: <subject> <verb> <object> when <condition>

    The ``when`` keyword is mandatory; everything before it is split into
    (subject, verb, object) using a greedy verb-heuristic parse.

    Examples::

        >>> parse_behavior_ac("behavior: parser returns BehaviorAC when AC matches grammar")
        BehaviorAC(raw='parser returns BehaviorAC when AC matches grammar',
                   subject='parser', verb='returns', object='BehaviorAC',
                   condition='AC matches grammar')

        >>> parse_behavior_ac("pytest: tests/test_foo.py")
        None  # not a behavior AC
    """
    stripped = ac.strip()
    if not re.match(r"^behavior\s*:", stripped, re.IGNORECASE):
        return None

    # Try full regex first (subject verb object when condition).
    m = _BEHAVIOR_RE.match(stripped)
    if m:
        return BehaviorAC(
            raw=stripped,
            subject=m.group("subject").strip(),
            verb=m.group("verb").strip(),
            object=m.group("object").strip(),
            condition=m.group("condition").strip(),
        )

    # Fall back: split around "when", then heuristically split SVO.
    m2 = _BEHAVIOR_SIMPLE_RE.match(stripped)
    if not m2:
        return None

    svo = m2.group("svo").strip()
    condition = m2.group("condition").strip()

    # Try to split SVO into (subject, verb, object).
    m3 = _VERB_SPLIT_RE.match(svo)
    if m3:
        return BehaviorAC(
            raw=stripped,
            subject=m3.group("subject").strip(),
            verb=m3.group("verb").strip(),
            object=m3.group("object").strip(),
            condition=condition,
        )

    # Last resort: treat the entire SVO as subject with empty verb/object.
    return BehaviorAC(
        raw=stripped,
        subject=svo,
        verb="",
        object="",
        condition=condition,
    )


def evaluate_behavior_ac(bac: BehaviorAC) -> str:
    """Produce a structured grading prompt for a parsed :class:`BehaviorAC`.

    Rather than asking the evaluator to consult freeform prose, this function
    returns a targeted, structured prompt fragment that instructs the
    independent grader to verify the exact subject-verb-object under the
    exact condition.

    The returned string is intended to be embedded inside the evaluator's
    existing task section (``## Your task``) — one entry per behavior AC.

    Args:
        bac: A parsed behavior acceptance criterion from :func:`parse_behavior_ac`.

    Returns:
        A multi-line string with a structured grading question, e.g.::

            ### Behavior AC check
            Does **<subject>** **<verb>** **<object>** when **<condition>**?

            Verify each part specifically:
            - Subject: Does `<subject>` ...
            - Verb: Does it **<verb>** (not merely attempt or partially do so)?
            - Object: Is the target `<object>` affected/produced/returned?
            - Condition: Is this triggered specifically when `<condition>` holds?

            Answer YES/NO for each part, then give an overall PASS or FAIL for
            this criterion with a one-sentence rationale and a file:line reference.
    """
    subject = bac.subject or "(unspecified subject)"
    verb = bac.verb or "(unspecified verb)"
    obj = bac.object or "(unspecified object)"
    condition = bac.condition

    return (
        "### Behavior AC check\n"
        f"Does **{subject}** **{verb}** **{obj}** when **{condition}**?\n\n"
        "Verify each part specifically:\n"
        f"- Subject `{subject}`: identify the code entity responsible for this action.\n"
        f"- Verb `{verb}`: confirm the action is actually performed (not mocked, stubbed, or no-op).\n"
        f"- Object `{obj}`: confirm the target entity is affected, produced, or returned.\n"
        f"- Condition `when {condition}`: confirm the behavior is triggered only/specifically under this condition.\n\n"
        "Answer YES/NO for each part above, then give an overall PASS or FAIL "
        "for this criterion with a one-sentence rationale and a `file:line` reference."
    )


def raises_on_malformed(ac: str) -> BehaviorAC:
    """Parse a ``behavior:`` AC string, raising :class:`EARSParseError` if malformed.

    Unlike :func:`parse_behavior_ac` which returns ``None`` for non-behavior
    strings, this function is strict: it always expects a valid behavior AC
    and raises if the "when" clause is missing or the string is otherwise
    malformed.

    Args:
        ac: A raw AC string expected to conform to the behavior grammar.

    Returns:
        A :class:`BehaviorAC` on success.

    Raises:
        EARSParseError: If the "when" clause is absent, the string is empty,
            or the ``behavior:`` prefix is missing.
    """
    stripped = ac.strip()
    if not stripped:
        raise EARSParseError("AC string is empty")
    if not re.match(r"^behavior\s*:", stripped, re.IGNORECASE):
        raise EARSParseError(f"AC string does not start with 'behavior:': {stripped!r}")
    if not re.search(r"\bwhen\b", stripped, re.IGNORECASE):
        raise EARSParseError(
            f"AC string is missing the required 'when' clause: {stripped!r}"
        )
    result = parse_behavior_ac(stripped)
    if result is None:
        raise EARSParseError(f"AC string could not be parsed: {stripped!r}")
    return result


def behavior_acs_from_criteria(criteria: str | list[str]) -> list[BehaviorAC]:
    """Parse all behavior ACs from a criteria string or list.

    A criteria string may be a JSON-encoded list or newline-separated list.

    Args:
        criteria: Raw acceptance criteria text or list of AC strings.

    Returns:
        List of :class:`BehaviorAC` objects for every ``behavior:`` entry found.
    """
    import json

    items: list[str] = []
    if isinstance(criteria, list):
        items = criteria
    elif isinstance(criteria, str):
        stripped = criteria.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    items = [str(x) for x in parsed]
            except (json.JSONDecodeError, ValueError):
                pass
        if not items:
            # Newline-separated or bare string
            items = [line.strip() for line in stripped.splitlines() if line.strip()]

    result: list[BehaviorAC] = []
    for item in items:
        bac = parse_behavior_ac(item)
        if bac is not None:
            result.append(bac)
    return result


def build_behavior_ac_evaluator_section(criteria: str | list[str]) -> str:
    """Build the full evaluator section for all behavior ACs in *criteria*.

    Returns an empty string when no behavior ACs are present (so the evaluator
    prompt is unchanged for features without behavior criteria).

    Args:
        criteria: Raw acceptance criteria text or list of AC strings.

    Returns:
        A string to append to the evaluator's ``## Your task`` section, or
        ``""`` if there are no behavior ACs.
    """
    bacs = behavior_acs_from_criteria(criteria)
    if not bacs:
        return ""

    parts = [
        "\n## Structured behavior-AC checks\n\n"
        "For each behavior criterion below, follow the structured verification "
        "steps exactly — use the parsed (subject, verb, object, condition) "
        "structure rather than consulting the freeform description.\n"
    ]
    for i, bac in enumerate(bacs, start=1):
        parts.append(f"\n**Behavior AC {i}:** `{bac.raw}`\n\n")
        parts.append(evaluate_behavior_ac(bac))
        parts.append("\n")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Integration with contract_grammar
# ---------------------------------------------------------------------------


def parse_behavior_ac_with_contracts(ac_dict: dict) -> tuple[BehaviorAC | None, "ContractSpec"]:
    """Parse a behavior AC dict, extracting both the EARS string and DbC contracts.

    Bridges ears_parser and contract_grammar: a behavior AC dict may carry
    both a ``behavior:`` string under the ``"behavior"`` key and optional
    DbC sub-keys (``pre``, ``post``, ``inv``, ``raises``).

    Args:
        ac_dict: Dict with optional ``"behavior"`` key (EARS string) and
                 optional DbC sub-keys.

    Returns:
        Tuple of (BehaviorAC | None, ContractSpec). The BehaviorAC is None
        when the ``"behavior"`` key is absent or unparseable.
    """
    from bob3.spec_quality.contract_grammar import parse_contract

    contract = parse_contract(ac_dict)
    behavior_str = ac_dict.get("behavior", "")
    bac = parse_behavior_ac(str(behavior_str)) if behavior_str else None
    return bac, contract
