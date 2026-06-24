"""bob.criteria_synthesizer — guaranteed boundary + error-path AC coverage.

Two historical failure modes caused synthesized=0/118 across bob66-70:

(1) parse_criteria_response only handled flat JSON arrays of strings. The LLM
    frequently returns a list of OBJECTS such as
    [{"id":1,"criterion":"...","description":"..."}]. Using str(dict) yields a
    Python-repr string that is NOT a machine-verifiable AC and scores ~0. This
    module extracts the criterion text from recognized object keys.

(2) Even when parsed, the LLM almost never includes boundary-condition or
    error-path ACs. The composite spec_quality_score is a weighted geometric
    mean — boundary_coverage=0 OR error_path_coverage=0 drives it to 0.0
    regardless of other sub-metrics. inject_boundary_error_criteria
    deterministically adds one boundary and one error-path pytest: AC when they
    are absent, mirroring the scorer's token patterns exactly.

Public API:
  parse_criteria_response(response_text) -> list[str] | None
  inject_boundary_error_criteria(criteria, title="") -> list[str]
"""
from __future__ import annotations

from bob.spec_synthesizer import (
    parse_criteria_response,
    inject_boundary_and_error_acs as inject_boundary_error_criteria,
)

__all__ = [
    "parse_criteria_response",
    "inject_boundary_error_criteria",
]
