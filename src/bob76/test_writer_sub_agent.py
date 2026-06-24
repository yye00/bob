"""bob76.test_writer_sub_agent — public re-export of the test-writer sub-agent API.

Inserts between spec-critic (F-R7-450) and the implementer sub-agent.
Emits one failing pytest per AC under tests/<feature_id>/test_<ac_id>.py.

The TestGen-LLM Build/Pass/Coverage triple filter rejects tests that:
  - don't compile (SyntaxError at collection time)
  - mysteriously pass on stub code
  - fail to raise coverage of the AC-named region

This module re-exports generate_failing_tests and the supporting types from
``bob3.orchestrator.test_writer_agent`` so that orchestrators can reference
the canonical bob76 package path.
"""

from __future__ import annotations

from bob3.orchestrator.test_writer_agent import (
    BijectionReport,
    EmittedTest,
    FilterResult,
    NoCoverageUpliftError,
    StubPassError,
    UncompilableTestError,
    emit_failing_tests,
    generate_failing_tests,
    reject_no_coverage_uplift,
    reject_passes_on_stub,
    reject_uncompilable,
    triple_filter,
    verify_bijection,
)

__all__ = [
    "BijectionReport",
    "EmittedTest",
    "FilterResult",
    "NoCoverageUpliftError",
    "StubPassError",
    "UncompilableTestError",
    "emit_failing_tests",
    "generate_failing_tests",
    "reject_no_coverage_uplift",
    "reject_passes_on_stub",
    "reject_uncompilable",
    "triple_filter",
    "verify_bijection",
]
