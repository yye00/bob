# Bob Operator Loop Context

This file is loaded by the orchestrator (operator loop) only — NOT by feature-implementing
worker sub-agents. Workers receive a per-feature WORKER.md instead, containing only the
information relevant to their specific task.

## Orchestrator responsibilities

- Dispatch feature workers concurrently (up to 8 at a time)
- Monitor worker outcomes and update feature status in the database
- Apply ratchet/budget enforcement between rounds
- Escalate stuck or repeatedly-failing features to needs_human
- Run verification after each worker completes
- Manage the overall round lifecycle

## Worker dispatch protocol (F-R7-608)

For every spawned worker, the orchestrator MUST:
1. Write per-feature WORKER.md to .bob/features/WORKER.md (slim context)
2. Write per-feature settings.json to .bob/features/<id>/settings.json
3. Set ANTHROPIC_PROMPT_CACHING=1 in the worker environment
4. Pass --settings <path> to the claude -p invocation

See bob.dispatch.spawn_worker for the canonical entry point.

## Operator memory bullets

- Current workspace: /home/yelkhamr/dark-factory/bob73
- DB: bob.db (SQLite)
- Feature statuses: pending → ready → executing → completed/failed/needs_human
- Budget enforcement: zero_reported_cost must NOT disable budget checks
- Reaper: escalates after 3 reaps to needs_human
- Verification: scoped pytest only — never full suite
