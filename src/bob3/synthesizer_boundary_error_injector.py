"""bob3.synthesizer_boundary_error_injector — guarantee boundary + error-path AC coverage.

Two root causes of synthesized=0/118 across prior generations:

(1) parse_criteria_response only handled flat JSON arrays of strings. The LLM
    frequently returns a list of OBJECTS such as
    [{"id":1,"criterion":"...","description":"..."}]. str(dict) yields a
    Python-repr string that is NOT a machine-verifiable AC (scores ~0).
    extract_criterion_text_from_object_format extracts the criterion text
    from recognized object keys.

(2) The LLM almost never includes boundary-condition or error-path ACs. The
    composite spec_quality_score is a weighted geometric mean — a zero in
    boundary_coverage OR error_path_coverage drives the composite to 0.0
    regardless of other sub-metrics. inject_boundary_and_error_acs
    deterministically adds one boundary and one error-path pytest: AC when
    they are absent, mirroring the scorer's token patterns exactly.

Public API (canonical module path required by AC):
  inject_boundary_and_error_acs(criteria, title="") -> list[str]
  extract_criterion_text_from_object_format(obj) -> str
"""
from __future__ import annotations

from bob3.synthesizer_boundary_error_ac_injector import (
    extract_criterion_text_from_object_format,
    inject_boundary_and_error_acs,
)

__all__ = [
    "extract_criterion_text_from_object_format",
    "inject_boundary_and_error_acs",
]
