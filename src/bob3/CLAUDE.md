# Bob3 Worker Context

This file contains meta-loop guidance for bob3 worker sub-agents.
Operator memory bullets (feature-specific context, workspace state, recent
decisions) have been moved to per-feature WORKER.md files so that only the
guidance relevant to a given feature lands in worker context.

## Meta-loop guidance

- Read your feature spec and ACs before writing any code.
- Write tests before implementation (TDD: red → green → refactor).
- Never create stub implementations — write real, functional code.
- Verify all ACs pass before marking the feature complete.
- Run only the scoped pytest files listed in ACs, not the full suite.
- Do not mock in production source files; mocks belong in test files only.
- Search bob3 memory for lessons before implementing; record new lessons after.
