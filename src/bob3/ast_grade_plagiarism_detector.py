"""AST-grade plagiarism detector for Bob3 — canonical entry point.

This module re-exports the full public API from the underlying implementation.
Fingerprints Python source using a normalized AST node-type sequence (Jaccard
similarity over 4-grams), and flags near-verbatim copies when similarity
exceeds a configurable threshold.  Integrates with the reward-hacking detector
verdict via ``augment_hacking_verdict``.

Public API
----------
- ``fingerprint_source(source)`` → ``ASTFingerprint | None``
- ``compute_similarity(fp_a, fp_b)`` → float in [0, 1]
- ``check_plagiarism(source, registry, threshold)`` → ``PlagiarismResult``
- ``augment_hacking_verdict(verdict, source, registry, threshold)`` → ``HackingVerdict``
- ``ReferenceRegistry`` — in-memory store of known reference fingerprints
- ``ASTFingerprint`` — normalized fingerprint dataclass
- ``PlagiarismResult`` — result dataclass from ``check_plagiarism``
"""

from bob3.plagiarism_detector import (  # noqa: F401  (re-export)
    ASTFingerprint,
    PlagiarismResult,
    ReferenceRegistry,
    augment_hacking_verdict,
    check_plagiarism,
    compute_similarity,
    fingerprint_source,
)

__all__ = [
    "ASTFingerprint",
    "PlagiarismResult",
    "ReferenceRegistry",
    "augment_hacking_verdict",
    "check_plagiarism",
    "compute_similarity",
    "fingerprint_source",
]
