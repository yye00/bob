# Bob3 Worker Context

This file is the per-worker context loaded into every spawned claude -p worker.
It is generated at dispatch time for each feature by `write_feature_settings` and
`build_worker_md` in `bob3.dispatch`.

## Guidance for workers

- Read your feature spec and ACs before writing any code.
- Write tests before implementation (TDD: red → green → refactor).
- Never create stub implementations — write real, functional code.
- Verify all ACs pass before marking the feature complete.
- Run only the scoped pytest files listed in ACs, not the full suite.
- Do not mock in production source files; mocks belong in test files only.
- Search bob3 memory for lessons before implementing; record new lessons after.

## Template fields (filled at dispatch time)

The actual per-feature WORKER.md is written to:
  `.bob3/features/WORKER.md`

and contains:
- Feature title and description
- Resolved AC list (post-extraction)
- Localization shortlist (BF-4 output)
- Workspace path
