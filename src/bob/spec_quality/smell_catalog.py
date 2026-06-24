"""22-smell catalogue for spec quality linting.

Implements the full Femmer/Smella + 2025 LLM-extension smell catalogue.
Each smell has: id, name, severity (E/W/I), description, and detection method.

Severity key:
  E - Error: blocks ``bob plan --create``
  W - Warning: surfaced but does not block
  I - Informational: advisory only

The 22 smells are numbered S01–S22.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


Severity = Literal["E", "W", "I"]


@dataclass(frozen=True)
class SmellDefinition:
    """Metadata for a single smell detector."""

    id: str          # e.g. "S01"
    name: str        # short kebab-case label
    severity: Severity
    description: str
    uses_spacy: bool = False  # True if spaCy NLP pipeline required


# ---------------------------------------------------------------------------
# Catalogue (22 entries)
# ---------------------------------------------------------------------------

SMELL_CATALOG: list[SmellDefinition] = [
    SmellDefinition(
        id="S01",
        name="subjective-adjective",
        severity="E",
        description=(
            "Adjectives like 'fast', 'simple', 'reliable', 'robust', 'friendly', "
            "'intuitive', 'clean', 'good', 'nice', 'easy' with no measurable criterion."
        ),
        uses_spacy=True,
    ),
    SmellDefinition(
        id="S02",
        name="ambiguous-adverb",
        severity="W",
        description=(
            "Adverbs like 'quickly', 'easily', 'efficiently', 'appropriately', "
            "'properly', 'correctly', 'reasonably', 'suitably' without a bound."
        ),
        uses_spacy=True,
    ),
    SmellDefinition(
        id="S03",
        name="loophole",
        severity="E",
        description=(
            "Escape clauses such as 'if possible', 'where applicable', "
            "'as appropriate', 'to the extent possible', 'if needed', 'when feasible'."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S04",
        name="open-ended-enumeration",
        severity="W",
        description=(
            "Lists that end with 'etc.', 'and so on', 'and/or', 'or similar', "
            "'and others' implying an incomplete set."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S05",
        name="unbounded-superlative",
        severity="E",
        description=(
            "Superlatives like 'best', 'fastest', 'most accurate', 'highest quality', "
            "'optimal', 'maximum performance' without a numeric baseline."
        ),
        uses_spacy=True,
    ),
    SmellDefinition(
        id="S06",
        name="comparative-without-baseline",
        severity="W",
        description=(
            "Comparatives like 'better', 'faster than', 'more reliable', "
            "'improved', 'enhanced', 'greater' without a stated reference point."
        ),
        uses_spacy=True,
    ),
    SmellDefinition(
        id="S07",
        name="vague-pronoun",
        severity="W",
        description=(
            "Pronouns 'it', 'they', 'this', 'these', 'those', 'that' used "
            "where no clear antecedent is present in the same sentence."
        ),
        uses_spacy=True,
    ),
    SmellDefinition(
        id="S08",
        name="passive-without-agent",
        severity="W",
        description=(
            "Passive voice constructions ('shall be verified', 'is processed', "
            "'will be checked') where the responsible actor is unspecified."
        ),
        uses_spacy=True,
    ),
    SmellDefinition(
        id="S09",
        name="modal-weakness",
        severity="E",
        description=(
            "RFC 2119 weakening: using 'should' or 'may' where 'shall'/'must' "
            "is required for a testable mandatory requirement."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S10",
        name="negation-without-scope",
        severity="W",
        description=(
            "Negation phrases 'shall not', 'must not', 'will not', 'cannot' "
            "without specifying the exact scope or condition under which they apply."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S11",
        name="magic-number-without-unit",
        severity="E",
        description=(
            "Bare numeric literals (e.g., '100', '0.5', '3') appearing without "
            "a unit of measurement or labeled context."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S12",
        name="undefined-acronym",
        severity="W",
        description=(
            "Uppercase initialisms (2–6 letters) that are not defined or expanded "
            "anywhere in the criterion text."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S13",
        name="run-on-multi-requirement",
        severity="E",
        description=(
            "A single criterion containing multiple obligations joined by 'and', "
            "'or', ';' — each obligation should be a separate criterion."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S14",
        name="implementation-leak",
        severity="W",
        description=(
            "References to internal design choices like 'using Redis', 'via REST', "
            "'through SQL', 'with PostgreSQL', 'by calling function X' in a requirement."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S15",
        name="tautology",
        severity="I",
        description=(
            "The criterion restates the feature name or description with no "
            "added testable content, e.g., 'The system shall be a system.'"
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S16",
        name="future-tense-drift",
        severity="I",
        description=(
            "Use of 'will be' or 'is going to' instead of normative 'shall'/'must' — "
            "indicates an aspirational rather than testable commitment."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S17",
        name="dangling-feature-id-reference",
        severity="W",
        description=(
            "A criterion references a feature ID (e.g., 'F-R7-410', 'F-NNN-YYY') "
            "that is not resolvable in the current spec."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S18",
        name="untestable-adjective",
        severity="E",
        description=(
            "Adjectives like 'complete', 'comprehensive', 'thorough', 'sufficient', "
            "'adequate', 'appropriate' that cannot be verified without further criteria."
        ),
        uses_spacy=True,
    ),
    SmellDefinition(
        id="S19",
        name="self-referential-test",
        severity="E",
        description=(
            "A test criterion whose only content is to check that a test exists "
            "or passes, without specifying what behavior the test verifies."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S20",
        name="empty-quantifier",
        severity="E",
        description=(
            "Quantifiers 'all', 'every', 'any', 'each', 'no' used without "
            "specifying the domain they quantify over."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S21",
        name="shall-should-mixing",
        severity="W",
        description=(
            "A single criterion uses both 'shall'/'must' and 'should'/'may', "
            "mixing mandatory and optional obligation levels."
        ),
        uses_spacy=False,
    ),
    SmellDefinition(
        id="S22",
        name="behavior-ac-without-test-mapping",
        severity="W",
        description=(
            "A 'behavior:' or EARS-style criterion that has no corresponding "
            "'pytest:' criterion in the same feature's acceptance criteria list."
        ),
        uses_spacy=False,
    ),
]

# Convenience look-up by id
SMELL_BY_ID: dict[str, SmellDefinition] = {s.id: s for s in SMELL_CATALOG}

# Smells that block plan --create (severity == "E")
BLOCKING_SMELLS: frozenset[str] = frozenset(
    s.id for s in SMELL_CATALOG if s.severity == "E"
)

# Smells that require spaCy
SPACY_SMELLS: frozenset[str] = frozenset(
    s.id for s in SMELL_CATALOG if s.uses_spacy
)
