# Finite local execution profile

This is Bob's development-only B02 extension, not a missing PPAT normative
schema or an acceptance policy. It is opt-in; historical v1 packet behavior is
unchanged when no finite profile is configured. Local tests use public synthetic
providers. The [first staged supervisor](SUPERVISED_RUN.md) now selects an exact
model and finite limits; its live endpoint preflight remains blocked by network
access. The tests do not establish paid endpoint qualification.

## Controller configuration

Create a separate controller directory, owned by the controller, mode `0700`,
outside every candidate workspace. Place a single-link, non-symlink JSON file
there, mode `0400`, with exactly these fields:

```json
{
  "schema_version": "bob.finite-execution-profile.v1",
  "model_id": "<exact supported model ID; no alias>",
  "max_cost_usd": null,
  "max_turns": null,
  "max_attempts": null,
  "max_wall_seconds": null
}
```

The placeholders deliberately cannot run. Select positive finite limits; turns
and attempts must be integers. `max_attempts` counts all provider sessions across
all roles, including failed sessions and repair attempts, not just implementer
retries. Allow enough sessions for planning, writing, implementation and review.
Set `BOB_FINITE_EXECUTION_PROFILE` to the absolute file path and
`BOB_FINITE_EXECUTION_PROFILE_SHA256` to its exact byte hash in the controller
process. Do not source the historical `bob_build.env`.

An existing `BOB_REQUIRED_MODEL` must match the exact selected ID. Explicit
feature-planner model overrides must also match. Unset model-escalation aliases
cannot override the profile. The profile applies to feature planning, packet
compilation/review, and the common SDK executor used by implementation, independent
test writing and evaluation. Provider-reported model mismatches fail closed.

The finite route disables nested `Task`/`Agent` tools and rejects MCP servers,
model fallback, session resume and conflicting CLI model/turn switches. External
MCP spend is not accounted by this profile. Configure `BOB_RESEARCH_MODE=disabled`
for the local campaign, and do not request browser/research MCP roles. An ambient
Perplexity key can still request legacy automatic MCP injection; final dispatch
rejects it rather than granting an unbudgeted call. The old direct-CLI worker
route in `bob.dispatch` rejects the finite profile before writing worker files.

## Ledger and failure semantics

The controller creates `bob-finite-budget.jsonl` beside the profile at first
dispatch. Every event is flushed and fsynced. A nonblocking OS lock serializes
sessions across processes. The header binds the profile hash, boot ID and
monotonic start time. The ledger therefore survives controller restarts on the
same boot without obtaining another budget; a reboot requires explicit recovery.

Before every SDK call Bob reserves all remaining cost/turn allowance and one
attempt. It forwards the remaining cost through the installed SDK's
`--max-budget-usd` path and clamps `max_turns` to the remaining total. Successful
stream termination with valid terminal usage releases unused reservations.
Reported-error sessions retain their outcome and charge their known usage.
Missing/nonfinite/negative/over-limit usage, interrupted streams, cancellation,
or uncertain cleanup retain the full reservation and stop further dispatch.
Observed usage is retained separately when a stream fails after reporting it.

There are no automatic parent-side transport retries in this route. A fresh
explicit attempt may use the remaining ledger only after a fully accounted
session and within the original attempt/time limits. An unfinished reservation,
truncated ledger or failed event blocks reuse. Never delete, replace, relocate,
truncate or regenerate the ledger to recover an interrupted campaign.

Wall time includes time between sessions after the first reservation. A controller
watchdog checks the deadline at most every 100 ms and kills only that SDK
transport's process. It continues through cleanup so a process attached after
the deadline cannot escape the first kill. SDK iteration and closure stay in the
same task to respect AnyIO cancel scopes. A finite implementer error stops the
run loop before legacy file-verification promotion, independent evaluation or
commit. It retains failure evidence and marks the feature `needs_human`.

The ledger is controller state, not an independently signed spend receipt. Real
separate principals, supervisor termination, mounts and a provider-enforced
billing limit remain deployment requirements. CLI budget forwarding and post-call
overspend rejection do not prove that a provider cannot overshoot a dollar limit
within one billed turn. A bounded endpoint preflight is required before paid work.

## Admitted packet binding

The Bob-local profile schema `bob.packet-execution-profile.v2` extends the existing
packet profile with `finite_execution_profile_sha256`. Its model must match the
finite profile; its provider capability is `controller-brokered-pinned-model`.
`resource_profile` binds `semantic_turn_cap`, `semantic_cost_cap`,
`semantic_attempt_cap` and `semantic_wall_seconds` to the same finite limits.
All existing route, target, base, test, lineage and capability checks still apply.
The finite route rejects a legacy packet profile before target materialization.

Packet compiler/reviewer provenance uses the respective Bob provenance `.v2`
schema and records the finite profile hash and exact model. A proposal from
another profile cannot be silently reviewed under this one. These observations
remain unsigned and require the existing independent controller attestation.

## Validation and remaining gates

`tests/test_finite_budget.py` covers actual option construction/cloning, the
installed SDK's generated command, public compiler/reviewer/planner paths,
cross-role remaining budgets, restart/lock/exhaustion behavior, custody failures,
unknown cost, billable interruption, wrong model, cancellation, consumer failure,
and no success promotion. Two cases exercise the installed SDK against a real
local synthetic CLI process, including a hung process; neither contacts a provider.

The affected combined suite also covers the original admitted packet lifecycle,
immutable candidate manifests, independent test freeze, exact commits/recovery,
and the seven-file B03 executor baseline. See
[implementation progress](IMPLEMENTATION_PROGRESS.md) for exact counts and receipts.
R00/R01 still require a deployed controller/validator boundary and one real,
explicitly budgeted public Bob task. No scientific task is accepted by these checks.
