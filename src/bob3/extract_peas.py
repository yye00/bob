"""bob3.extract_peas — public API module for the PEAS pipeline.

Exposes ``parse_peas_markdown`` and ``synthesize_features`` as the canonical
importable names satisfying the ACs for the PEAS pipeline feature.  The full
implementation lives in :mod:`bob3.extract_from_peas`; this module re-exports
the relevant symbols so that ``from bob3.extract_peas import ...`` works.
"""
from __future__ import annotations

from bob3.extract_from_peas import (
    TBD_PLACEHOLDER,
    emit_stub_features,
    extract_and_synthesize,
    parse_peas_markdown,
    run_pipeline,
    synthesize_features,
)

__all__ = [
    "TBD_PLACEHOLDER",
    "emit_stub_features",
    "extract_and_synthesize",
    "parse_peas_markdown",
    "run_pipeline",
    "synthesize_features",
]
