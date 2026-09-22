# Supervised public Bob run

## Current state: stopped, awaiting owner funding

The owner reported on 2026-09-22 that controllers 03/04 ran as host systemd user
units, then stopped with ledgers intact and $0 spent. Controller 04 reached the
live API, which rejected the request with "Your credit balance is too low".
Artifact networking is now enabled. Do not interpret the historical network
failure or stale heartbeat below as a current running controller.

The finite route now classifies synthetic assistant API errors as truthful
auth/billing failures before checking model identity. Regression tests and
native local SDK cleanup checks are in the
[provider-error receipt](../../../third_party/receipts/implementation-2026-09-22/bob-provider-errors/README.md).
The [D01 environment](../../../third_party/receipts/implementation-2026-09-22/D01/README.md)
includes this repair and passes 183 installed tests without paid calls.

The owner instructed direct sequential implementation while Bob is unfunded.
[That work order is complete within local scope](IMPLEMENTATION_PROGRESS.md),
including S05. No campaign was relaunched and no reservation was reset. Further
live model work requires owner funding and a valid finite preflight; offline
tests do not establish provider qualification.

Standalone/uv Python TLS uses the owner-provided configuration:
`OPENSSL_CONF=/home/captain/work/AI/power/third_party/runs/power-spec-2/supervised-2026-09-22-04/controller/openssl-minimal.cnf`.
The portable D01 environment retains its own copy. This addresses the bundled
OpenSSL/Fedora configuration incompatibility; TLS verification remains enabled.

## Historical 2026-09-21 launch and operation

The remainder records the earlier launch. Its present-tense status descriptions,
tool session identifiers and persistence limitations apply to that checkpoint.

The current controller is the second explicit launch, after repairing native
dispatch and verification integration. The first controller was stopped cleanly
before any provider session; its state and logs remain retained. The new monitor
has advancing heartbeats but is still **blocked_network**, with a pending feature,
no model worker and no budget ledger. Read current state before making a live
status claim; a running monitor is not an executing model or completed feature.
The [three-turn capability audit](../../../third_party/receipts/implementation-2026-09-21/blocked-capabilities/README.md)
records the current goal blocker. The finite monitor is retained, with its wall
deadline recorded there; the goal has not been completed.

Controller:
`third_party/runs/power-spec-2/supervised-2026-09-21-02/controller/`

The original database and finite profile remain in the `supervised-2026-09-21-01`
controller directory. The ledger path and budget identity are unchanged. The
second controller does not reset feature state or renew a model reservation.

Candidate:
`third_party/work/power-spec-2-supervised-01/`

The feature is `power-spec2-s05-public-energy-accounting`: a bounded S05 child for
the public 5 J baseline + 2 J compute + 3 J memory = 10 J oracle, with explicit
ownership, exact term coverage, canonical units and invalid/overflow rejection.
Its eight criteria retain all checks; a native-linter format correction raised
the computed spec-quality score from 0.78125 to 1.0. Readiness/confidence values
were not fabricated. The prepared candidate's 132 existing tests pass and its
source is committed separately from the original development checkout.

## Execution behavior

`python -m bob.finite_supervisor --config <absolute-campaign.json> --sha256 <digest>`
supervises exactly one feature through the existing `bob run --feature` command.
It does not replace Bob's scheduler, rewrite queue statuses or retry failed model
sessions. Its controller-owned config is immutable, hash-bound and outside the
candidate. Only the owned child process group is terminated on stop/deadline.

The version-2 controller config also pins source/test directories and the app's
Python interpreter. Its explicit public route passes Bob's native policy check
without claiming an independent boundary. Requests for external verification,
independent test writing or admitted-packet execution still fail closed if mixed
with this public route. Legacy profiles keep their existing policy.
The separate external route now also honors a valid finite profile's exact model
while retaining all of its boundary requirements; see the
[follow-up policy receipt](../../../third_party/receipts/implementation-2026-09-21/finite-external-policy/README.md).

Bob's native snapshot and test gate now exercise `app/tests/public` using the
selected Python. The finite public gate rejects failures, collection errors,
skips and empty suites; it cannot demote them to warnings. The controller's native
preflight collected and passed all 132 original tests before the relaunch.

1. Validate the exact finite profile and database/workspace/feature binding.
2. Poll an unauthenticated TLS connectivity check with a five-second outer timeout.
   Missing auth/connectivity yields `blocked_auth`/`blocked_network`, not `building`.
3. Run a one-turn, no-tool request through the actual finite Bob SDK route. Require
   the exact model identity and nonce response, known terminal usage and no tools.
   A separate sixty-second supervisor deadline bounds this preflight.
4. Only a successful bound preflight receipt permits feature dispatch. The same
   finite ledger accounts for preflight and feature roles.
5. Record the owned worker's status, log size, feature status and project cost.
   Exit zero plus a completed feature is required for local completion. Independent
   acceptance is still separate. Nonzero exits and incomplete results stop the
   supervisor without clearing failures, increasing budgets or resetting the DB.

The staged initial task pins `claude-sonnet-4-5-20250929`, with a **$5 accounting
ceiling, 40 total turns, six provider sessions and 1,800 seconds**. These are
conservative operator-selected limits for this initial public task under the
user's launch instruction, not an approved scientific policy. The model is not
provider-qualified until the live preflight succeeds. No current model call has
been established by the offline tests or connectivity checks.

The installed Claude CLI's `--bare` mode explicitly ignores OAuth and uses the
API-key path. The supervisor therefore uses the existing `ANTHROPIC_API_KEY`,
removes alternate provider/OAuth/MCP routes from its child environment, and stores
no credentials. This Bob accounting ceiling is separate from the Codex session's
usage limit. CLI/post-call budget checks are not a provider billing guarantee.

## Monitor and stop

```sh
cat third_party/runs/power-spec-2/supervised-2026-09-21-02/controller/supervisor-state.json
tail third_party/runs/power-spec-2/supervised-2026-09-21-02/controller/supervisor-events.jsonl
```

Status is a snapshot; advancing timestamps/probe counts or process-service status
establish liveness. The recorded PID belongs to its recorded PID namespace; never
treat it as a host PID to kill by number. To stop this controller on its next poll:

```sh
touch third_party/runs/power-spec-2/supervised-2026-09-21-02/controller/STOP
```

The current process is tool session `5204`; the first session `76032` exited 130
after its explicit stop. These identifiers are local to this
interaction, not a portable service identity. Polls are ten seconds apart. A
shutdown preserves all state, logs, source, budget reservations and feature data.
Never delete the budget ledger, remove failure evidence or relaunch the old
unbounded self-build/watchdog scripts as a recovery shortcut.

## Persistence and environment limits

The foreground tool-managed process remained alive across tool calls. A detached
`start_new_session` probe did not produce a post-command heartbeat. Access to both
the user systemd bus and tmux socket was denied. Native unit verification itself
was blocked by `SO_PASSCRED: Operation not permitted`. No host service is installed,
and survival beyond the tool session/usage limit has not been demonstrated.

A concrete `bob-public-feature.service` and launcher are staged beside the config
and copied into the receipt. The unit uses finite runtime, resource ceilings and
control-group cleanup; it does not blindly restart interrupted budgets. Deployment
requires a host/session that permits a process service and model connectivity.
An existing controller state deliberately prevents an unreviewed second launch;
transfer/recovery must preserve its ledger and establish that the earlier process
has stopped. The staged service is not evidence of a deployed persistent service.

The current DNS failure also affects GitHub acquisition. A different URL, disabled
TLS, proxy credential forwarding or an alternate model is not an authorized way
to bypass the session's network boundary.

## Evidence

See [the native integration repair receipt](../../../third_party/receipts/implementation-2026-09-21/public-runner-integration/README.md)
for 198 passing affected tests, native execution of the 132-test app baseline,
retained failures, controller continuation and the cleanly rebuilt wheel.
The [external-policy follow-up](../../../third_party/receipts/implementation-2026-09-21/finite-external-policy/README.md)
contains the latest wheel and 133 passing affected checks, including 17 new cases.
The [first supervisor receipt](../../../third_party/receipts/implementation-2026-09-21/supervised-runner/README.md)
retains the initial launch, task preparation, 86-test checkpoint and environment
limitations. Test counts overlap. Neither receipt proves a live model response.
