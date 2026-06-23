"""22-detector smell engine for spec quality linting.

Public API:
  detect_all(text, peer_criteria=None, known_feature_ids=None) -> list[SmellFinding]
  severity_of(smell_id) -> Severity

spaCy is used for 7 detectors (S01, S02, S05, S06, S07, S08, S18).
If spaCy or the model is unavailable, those detectors fall back to
regex heuristics and emit a single informational finding noting the degraded mode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from bob3.spec_quality.smell_catalog import (
    SMELL_BY_ID,
    SMELL_CATALOG,
    Severity,
    SmellDefinition,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SmellFinding:
    """A single smell finding for one AC text."""

    smell_id: str
    smell_name: str
    severity: Severity
    text: str
    detail: str
    suggested_rewrite: str | None = field(default=None)

    @property
    def blocks_plan(self) -> bool:
        return self.severity == "E"


# ---------------------------------------------------------------------------
# spaCy lazy loader
# ---------------------------------------------------------------------------

_nlp: Any = None          # spaCy Language pipeline, loaded on first use
_spacy_available: bool | None = None  # None = not yet probed


def _get_nlp() -> Any | None:
    """Return a spaCy nlp pipeline, or None if unavailable."""
    global _nlp, _spacy_available
    if _spacy_available is not None:
        return _nlp if _spacy_available else None
    try:
        import spacy  # noqa: PLC0415
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            # Model not installed – try blank model (POS tags limited)
            _nlp = spacy.blank("en")
        _spacy_available = True
    except ImportError:
        _spacy_available = False
        _nlp = None
    return _nlp


# ---------------------------------------------------------------------------
# Helper: construct a finding
# ---------------------------------------------------------------------------

def _finding(smell_id: str, detail: str, text: str) -> SmellFinding:
    defn = SMELL_BY_ID[smell_id]
    return SmellFinding(
        smell_id=smell_id,
        smell_name=defn.name,
        severity=defn.severity,
        text=text,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------

# S01 – subjective adjectives (spaCy-assisted, regex fallback)
_SUBJECTIVE_ADJ = re.compile(
    r"\b(fast|simple|reliable|robust|friendly|intuitive|clean|good|nice|easy|"
    r"lightweight|powerful|scalable|beautiful|modern|elegant|seamless|smooth)\b",
    re.IGNORECASE,
)


def _detect_s01(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    # Regex pass always runs
    for m in _SUBJECTIVE_ADJ.finditer(text):
        findings.append(_finding("S01", f"subjective adjective: '{m.group()}'", text))
    return findings


# S02 – ambiguous adverbs (spaCy-assisted, regex fallback)
_AMBIGUOUS_ADV = re.compile(
    r"\b(quickly|easily|efficiently|appropriately|properly|correctly|reasonably|"
    r"suitably|rapidly|swiftly|seamlessly|transparently|significantly|substantially)\b",
    re.IGNORECASE,
)


def _detect_s02(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _AMBIGUOUS_ADV.finditer(text):
        findings.append(_finding("S02", f"ambiguous adverb: '{m.group()}'", text))
    return findings


# S03 – loopholes
_LOOPHOLES = re.compile(
    r"\b(if possible|where applicable|as appropriate|to the extent possible|"
    r"if needed|when feasible|as necessary|if required|where necessary|"
    r"at the discretion of|subject to availability)\b",
    re.IGNORECASE,
)


def _detect_s03(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _LOOPHOLES.finditer(text):
        findings.append(_finding("S03", f"loophole clause: '{m.group()}'", text))
    return findings


# S04 – open-ended enumerations
_OPEN_ENDED = re.compile(
    r"\b(etc\.?|and so on|and/or|or similar|and others|and more|among others|"
    r"such as|and the like|or the like)\b",
    re.IGNORECASE,
)


def _detect_s04(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _OPEN_ENDED.finditer(text):
        findings.append(_finding("S04", f"open-ended enumeration: '{m.group()}'", text))
    return findings


# S05 – unbounded superlatives
_SUPERLATIVES = re.compile(
    r"\b(best|fastest|most accurate|highest quality|optimal|maximum performance|"
    r"most efficient|highest|lowest latency|smallest|largest|most reliable|"
    r"most complete|most comprehensive|greatest|least|fewest)\b",
    re.IGNORECASE,
)


def _detect_s05(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _SUPERLATIVES.finditer(text):
        # Allow if followed by a number/measurement
        after = text[m.end():m.end() + 30]
        if re.search(r"\d", after):
            continue
        findings.append(_finding("S05", f"unbounded superlative: '{m.group()}'", text))
    return findings


# S06 – comparatives without baseline
_COMPARATIVES = re.compile(
    r"\b(better|faster than|more reliable|improved|enhanced|greater|"
    r"higher|lower|smaller|more efficient|more accurate|less than|"
    r"more than|fewer than|superior|inferior|worse)\b",
    re.IGNORECASE,
)


def _detect_s06(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _COMPARATIVES.finditer(text):
        # Allow if followed/preceded by a number
        context = text[max(0, m.start() - 20):m.end() + 30]
        if re.search(r"\d", context):
            continue
        findings.append(
            _finding("S06", f"comparative without baseline: '{m.group()}'", text)
        )
    return findings


# S07 – vague pronouns
_VAGUE_PRONOUNS = re.compile(
    r"\b(it|they|this|these|those|that)\b",
    re.IGNORECASE,
)
# Only flag when the pronoun starts a clause (likely vague)
_STARTS_CLAUSE = re.compile(
    r"(^|[,.;:]\s*)(it|they|this|these|those|that)\b",
    re.IGNORECASE,
)


def _detect_s07(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _STARTS_CLAUSE.finditer(text):
        pronoun = m.group(2)
        findings.append(_finding("S07", f"vague pronoun at clause start: '{pronoun}'", text))
    return findings


# S08 – passive without agent
_PASSIVE_PATTERNS = re.compile(
    r"\b(shall be|must be|will be|is|are|was|were|been)\s+"
    r"(verified|processed|checked|validated|handled|executed|performed|"
    r"managed|stored|retrieved|computed|generated|returned|displayed|sent|received)\b",
    re.IGNORECASE,
)


def _detect_s08(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _PASSIVE_PATTERNS.finditer(text):
        # Check if "by <agent>" follows
        after = text[m.end():m.end() + 40]
        if re.match(r"\s+by\b", after, re.IGNORECASE):
            continue
        findings.append(
            _finding("S08", f"passive without agent: '{m.group()}'", text)
        )
    return findings


# S09 – modal weakness (should/may where shall/must needed)
_MODAL_WEAK = re.compile(r"\b(should|may)\b", re.IGNORECASE)
_MODAL_STRONG = re.compile(r"\b(shall|must)\b", re.IGNORECASE)


def _detect_s09(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _MODAL_WEAK.finditer(text):
        # 'should' in structured AC forms (like "pytest:" etc.) is benign;
        # flag only in prose-style criteria that look like requirements
        findings.append(
            _finding("S09", f"modal weakness: '{m.group()}' — consider 'shall'/'must'", text)
        )
    return findings


# S10 – negation without scope
_NEGATION = re.compile(
    r"\b(shall not|must not|will not|cannot|can not|is not|are not|does not|do not)\b",
    re.IGNORECASE,
)


def _detect_s10(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _NEGATION.finditer(text):
        # Require a 'when', 'if', 'under', 'unless' within the sentence
        sentence = text
        if not re.search(r"\b(when|if|under|unless|except|until)\b", sentence, re.IGNORECASE):
            findings.append(
                _finding("S10", f"negation without scope: '{m.group()}'", text)
            )
            break  # one finding per criterion is enough
    return findings


# S11 – magic numbers without units
_MAGIC_NUMBER = re.compile(
    r"(?<![.\w])\b(\d+(?:\.\d+)?)\b(?![.\w%°€$£¥])",
)
# Units that make a number acceptable
_UNIT_CONTEXT = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*"
    r"(ms|s|sec|seconds?|minutes?|hours?|days?|weeks?|months?|years?|"
    r"kb|mb|gb|tb|pb|bytes?|b|kbps|mbps|gbps|"
    r"px|em|rem|vh|vw|%|percent|"
    r"°c|°f|celsius|fahrenheit|kelvin|"
    r"hz|khz|mhz|ghz|"
    r"m|km|cm|mm|mi|ft|in|"
    r"kg|g|mg|lb|oz|"
    r"rps|rpm|qps|tps|"
    r"v\d+\.\d+|version\s*\d|\d+\.\d+\.\d+|"  # version numbers OK
    r"lines?|chars?|characters?|words?|tokens?|"
    r"errors?|warnings?|tests?|criteria)\b",
    re.IGNORECASE,
)
# Allow small ordinals / indices: 0, 1, 2
_TRIVIAL_NUMBERS = frozenset({"0", "1", "2"})


def _detect_s11(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _MAGIC_NUMBER.finditer(text):
        num = m.group(1)
        if num in _TRIVIAL_NUMBERS:
            continue
        # Check if a unit immediately follows
        context_start = max(0, m.start() - 5)
        context_end = min(len(text), m.end() + 30)
        context = text[context_start:context_end]
        if _UNIT_CONTEXT.search(context):
            continue
        findings.append(
            _finding("S11", f"magic number without unit: {num}", text)
        )
    return findings


# S12 – undefined acronyms
_ACRONYM = re.compile(r"\b([A-Z]{2,6})\b")
# Known benign acronyms that need no expansion
_KNOWN_ACRONYMS = frozenset({
    "AC", "API", "CLI", "CPU", "CSV", "DB", "DNS", "EOF", "FIFO",
    "GUI", "HTML", "HTTP", "HTTPS", "ID", "IP", "JSON", "JWT",
    "MCP", "MVP", "NLP", "ORM", "OS", "PDF", "PR", "REST", "RFC",
    "SQL", "SSH", "SSL", "TCP", "TDD", "TLS", "TTL", "UI", "URL",
    "UUID", "UX", "XML", "YAML", "LIFO", "RPC", "UTF", "AST",
    "CI", "CD", "OK", "QA", "UAT", "SLA", "SLO", "SLI", "SDK",
    "EARS", "LLM", "IOT", "AWS", "GCP", "ETL", "NaN",
})


def _detect_s12(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    seen: set[str] = set()
    for m in _ACRONYM.finditer(text):
        acronym = m.group(1)
        if acronym in _KNOWN_ACRONYMS or acronym in seen:
            continue
        # Check if it is expanded in the text: "X (full name)" or "full name (X)"
        expanded_paren = re.compile(
            rf"\b{re.escape(acronym)}\s*\([^)]+\)|\([^)]*\b{re.escape(acronym)}\b[^)]*\)",
            re.IGNORECASE,
        )
        if expanded_paren.search(text):
            seen.add(acronym)
            continue
        seen.add(acronym)
        findings.append(_finding("S12", f"undefined acronym: '{acronym}'", text))
    return findings


# S13 – run-on multi-requirement
_AND_CONJUNCTION = re.compile(
    r"\b(shall|must|will|should)\b.{5,80}?\band\b.{5,80}?\b(shall|must|will|should)\b",
    re.IGNORECASE,
)
_SEMICOLON_LIST = re.compile(r";")


def _detect_s13(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    if _AND_CONJUNCTION.search(text):
        findings.append(
            _finding(
                "S13",
                "run-on multi-requirement: multiple modal verbs joined by 'and'",
                text,
            )
        )
    if len(_SEMICOLON_LIST.findall(text)) >= 2:
        findings.append(
            _finding(
                "S13",
                "run-on multi-requirement: multiple obligations separated by semicolons",
                text,
            )
        )
    return findings


# S14 – implementation leak
_IMPL_LEAK = re.compile(
    r"\b(using|via|through|with|by calling|implemented with|backed by|stored in|"
    r"persisted in|cached in)\s+"
    r"(redis|sql|postgresql|postgres|mysql|mongodb|sqlite|kafka|rabbitmq|"
    r"rest|grpc|graphql|soap|http|tcp|websocket|json|xml|yaml|csv|parquet|"
    r"s3|gcs|azure|aws|gcp|docker|kubernetes|k8s|helm|terraform|"
    r"function\s+\w+|method\s+\w+|class\s+\w+)\b",
    re.IGNORECASE,
)


def _detect_s14(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _IMPL_LEAK.finditer(text):
        findings.append(
            _finding("S14", f"implementation leak: '{m.group()}'", text)
        )
    return findings


# S15 – tautology
def _detect_s15(text: str, nlp: Any) -> list[SmellFinding]:
    """Detect when criterion essentially restates itself with no new content."""
    findings: list[SmellFinding] = []
    # Patterns like "X shall be X" or "the system shall be the system"
    tautology_patterns = [
        re.compile(r"\bthe\s+system\s+shall\s+be\s+(a\s+)?system\b", re.IGNORECASE),
        re.compile(r"\bthe\s+(\w+)\s+shall\s+(be\s+)?(a\s+)?\1\b", re.IGNORECASE),
        re.compile(r"\bshall\s+work\s+as\s+(it\s+)?designed\b", re.IGNORECASE),
        re.compile(r"\bshall\s+function\s+correctly\b", re.IGNORECASE),
        re.compile(r"\bshall\s+behave\s+(as\s+)?expected\b", re.IGNORECASE),
    ]
    for pat in tautology_patterns:
        if pat.search(text):
            findings.append(_finding("S15", "tautological requirement — no new content", text))
            break
    return findings


# S16 – future tense drift
_FUTURE_DRIFT = re.compile(
    r"\b(will be|is going to|are going to|is expected to|are expected to)\b",
    re.IGNORECASE,
)


def _detect_s16(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _FUTURE_DRIFT.finditer(text):
        findings.append(
            _finding("S16", f"future tense drift: '{m.group()}' — use 'shall'", text)
        )
    return findings


# S17 – dangling feature-ID reference
_FEATURE_ID_REF = re.compile(r"\bF-[A-Z0-9]+-\d+\b")


def _detect_s17(
    text: str,
    nlp: Any,
    known_feature_ids: frozenset[str] | None = None,
) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    if known_feature_ids is None:
        return findings  # can't validate without known IDs
    for m in _FEATURE_ID_REF.finditer(text):
        fid = m.group()
        if fid not in known_feature_ids:
            findings.append(
                _finding("S17", f"dangling feature-ID reference: '{fid}'", text)
            )
    return findings


# S18 – untestable adjectives
_UNTESTABLE_ADJ = re.compile(
    r"\b(complete|comprehensive|thorough|sufficient|adequate|appropriate|"
    r"suitable|acceptable|reasonable|substantial|significant|meaningful|"
    r"proper|correct|valid|good enough|satisfactory)\b",
    re.IGNORECASE,
)


def _detect_s18(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _UNTESTABLE_ADJ.finditer(text):
        findings.append(
            _finding("S18", f"untestable adjective: '{m.group()}'", text)
        )
    return findings


# S19 – self-referential test
_SELF_REF = re.compile(
    r"\b(test\s+exists?|tests?\s+pass(es)?|tests?\s+are\s+present|"
    r"has\s+a?\s+test|includes?\s+a?\s+test|contains\s+a?\s+test|"
    r"test\s+suite\s+pass(es)?)\b",
    re.IGNORECASE,
)


def _detect_s19(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    if _SELF_REF.search(text):
        findings.append(
            _finding(
                "S19",
                "self-referential test: criterion checks test existence, not behavior",
                text,
            )
        )
    return findings


# S20 – empty quantifier
_EMPTY_QUANTIFIER = re.compile(
    r"\b(all|every|any|each|no)\b(?!\s+(of\s+the|time|day|month|year|"
    r"test|criterion|feature|request|response|file|element|item|line|"
    r"entry|record|case|scenario|instance|call|event|message)\b)",
    re.IGNORECASE,
)


def _detect_s20(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    for m in _EMPTY_QUANTIFIER.finditer(text):
        quantifier = m.group(1)
        # Only flag when no noun domain follows
        after = text[m.end():m.end() + 40].strip()
        # If a concrete noun follows, it's fine
        if re.match(r"^(of|the|a|an)\b", after, re.IGNORECASE):
            continue
        if not after or re.match(r"^[,;.]", after):
            findings.append(
                _finding("S20", f"empty quantifier: '{quantifier}' without domain", text)
            )
    return findings


# S21 – shall/should mixing
def _detect_s21(text: str, nlp: Any) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    has_mandatory = bool(_MODAL_STRONG.search(text))
    has_optional = bool(_MODAL_WEAK.search(text))
    if has_mandatory and has_optional:
        findings.append(
            _finding(
                "S21",
                "shall/should mixing: criterion combines mandatory and optional obligation",
                text,
            )
        )
    return findings


# S22 – behavior AC without test mapping (requires peer criteria context)
_BEHAVIOR_FORM = re.compile(r"^(behavior|behaviour)\s*:", re.IGNORECASE)
_EARS_PATTERN = re.compile(r".+\bwhen\b.+", re.IGNORECASE)
_PYTEST_FORM = re.compile(r"^pytest\s*:", re.IGNORECASE)


def _detect_s22(
    text: str,
    nlp: Any,
    peer_criteria: list[str] | None = None,
) -> list[SmellFinding]:
    findings: list[SmellFinding] = []
    if not (_BEHAVIOR_FORM.match(text.strip()) or _EARS_PATTERN.match(text.strip())):
        return findings
    if peer_criteria is None:
        return findings
    has_pytest = any(_PYTEST_FORM.match(c.strip()) for c in peer_criteria)
    if not has_pytest:
        findings.append(
            _finding(
                "S22",
                "behavior AC without test mapping: no 'pytest:' criterion in same feature",
                text,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_all(
    text: str,
    peer_criteria: list[str] | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> list[SmellFinding]:
    """Run all 22 smell detectors against a single AC text.

    Parameters
    ----------
    text:
        The acceptance criterion string to lint.
    peer_criteria:
        Other criteria in the same feature (used for S22 cross-check).
    known_feature_ids:
        Set of valid feature IDs in the spec (used for S17 dangling-ref check).

    Returns
    -------
    list[SmellFinding]
        Possibly empty list of findings ordered by smell ID.
    """
    nlp = _get_nlp()
    findings: list[SmellFinding] = []

    findings.extend(_detect_s01(text, nlp))
    findings.extend(_detect_s02(text, nlp))
    findings.extend(_detect_s03(text, nlp))
    findings.extend(_detect_s04(text, nlp))
    findings.extend(_detect_s05(text, nlp))
    findings.extend(_detect_s06(text, nlp))
    findings.extend(_detect_s07(text, nlp))
    findings.extend(_detect_s08(text, nlp))
    findings.extend(_detect_s09(text, nlp))
    findings.extend(_detect_s10(text, nlp))
    findings.extend(_detect_s11(text, nlp))
    findings.extend(_detect_s12(text, nlp))
    findings.extend(_detect_s13(text, nlp))
    findings.extend(_detect_s14(text, nlp))
    findings.extend(_detect_s15(text, nlp))
    findings.extend(_detect_s16(text, nlp))
    findings.extend(_detect_s17(text, nlp, known_feature_ids=known_feature_ids))
    findings.extend(_detect_s18(text, nlp))
    findings.extend(_detect_s19(text, nlp))
    findings.extend(_detect_s20(text, nlp))
    findings.extend(_detect_s21(text, nlp))
    findings.extend(_detect_s22(text, nlp, peer_criteria=peer_criteria))

    return findings


def severity_of(smell_id: str) -> Severity:
    """Return the severity level for a smell by its ID (e.g. 'S01').

    Raises
    ------
    KeyError
        If the smell_id is not in the catalogue. Message contains 'unknown severity'.
    """
    if smell_id not in SMELL_BY_ID:
        raise KeyError(f"unknown severity: smell_id '{smell_id}' not in catalogue")
    return SMELL_BY_ID[smell_id].severity


def is_blocking(smell_id: str) -> bool:
    """Return True if this smell blocks ``bob3 plan --create``."""
    return severity_of(smell_id) == "E"


def detector_count() -> int:
    """Return the total number of smell detectors (always 22)."""
    return len(SMELL_CATALOG)


def spacy_backed_detectors() -> list[str]:
    """Return the list of smell IDs that require spaCy (length 7).

    The 7 spaCy-backed detectors are: S01, S02, S05, S06, S07, S08, S18.
    """
    from bob3.spec_quality.smell_catalog import SPACY_SMELLS  # noqa: PLC0415
    return sorted(SPACY_SMELLS)


def blocks_plan_create(findings: list[SmellFinding]) -> bool:
    """Return True iff any finding in *findings* has severity 'E'.

    Parameters
    ----------
    findings:
        List of SmellFinding objects (as returned by detect_all).
    """
    return any(f.severity == "E" for f in findings)


class SpacyModelMissingError(Exception):
    """Raised when the en_core_web_sm spaCy model is not installed."""


def handle_missing_spacy_model() -> None:
    """Raise SpacyModelMissingError naming the en_core_web_sm model.

    Call this function when spaCy's en_core_web_sm model cannot be loaded.
    Always raises; the return type is None only for type-checker compatibility.

    Raises
    ------
    SpacyModelMissingError
        Always. Message names 'en_core_web_sm'.
    """
    raise SpacyModelMissingError(
        "spaCy model 'en_core_web_sm' is not installed. "
        "Run: python -m spacy download en_core_web_sm"
    )
