# Worker Directives

This file is loaded into the worker context at dispatch time. It provides the
minimal context a feature-implementing worker needs. The full operator CLAUDE.md
is NOT loaded into worker contexts — it contains orchestrator-level memory (~70
bullets) that is irrelevant to feature implementation and wastes ~6K tokens.

## Feature

The feature title, description, acceptance criteria, localization shortlist, and
workspace path are provided in the per-feature WORKER.md written by
`bob3.dispatch.build_worker_md` at dispatch time. That file is placed at
`.bob3/features/WORKER.md` before the worker subprocess is launched.

## Acceptance Criteria

Each AC kind is described below:

- `File exists: <path>` — create the file if it does not exist.
- `Function defined: <module>.<function>` — implement the function.
- `pytest: <file>` — all tests in the file must pass.
- `integration: <module>` — the module must be importable and its public
  symbols present in `__all__`.

## Workspace

The workspace path is provided in the per-feature WORKER.md generated at
dispatch time. Run all test commands from the workspace root.

## Platform Fixes Applied Before Every Worker

(A) **Prompt caching** — `ANTHROPIC_PROMPT_CACHING=1` is set in the worker
environment, preventing ~378K wasted tokens per session from re-billed system
prompts (Issue #29966).

(B) **Slim context** — this WORKER.md (not the operator CLAUDE.md) is the
context root. Only feature-relevant information is loaded.

(C) **Per-worker settings** — `.bob3/features/<id>/settings.json` is written
before the worker launches and passed via `--settings` so that workers have
correct tool permissions without inheriting from the parent process
(Issue #27661).
