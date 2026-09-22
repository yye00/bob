# Planning verification receipt

Date: 2026-09-21. Scope: documentation, planning registry/renderer/checker and
read-only inventory. **No application runtime migration, provider rebuild,
hardware acquisition, production isolation qualification or blind scoring ran.**

That statement describes the initial planning pass. The user's subsequent request
to cross-check local build capability produced fresh package/native runs in a
[separate receipt](../../../third_party/receipts/local-readiness-2026-09-21/README.md).
The revised planning checker now has 29 rejection cases, adding local-evidence
false acceptance and missing target-gate tests; the original 27-case run below
remains historical evidence of this first pass.

## Baseline and changes

- Parent HEAD: `f6a580f1dabac5354d64b67a18793e314a0835d0`.
- Bob HEAD: `84c9f42062cb8db1fc1f82ab07abe8053ae3d343`; initially clean, nested Git repository.
- Pre-existing user state: untracked `power-spec-2/`, untracked
  `power-spec/simulator-reference-tests/`, modified MGPUSim `go.sum`.
- Preserved MGPUSim `go.sum` current SHA-256:
  `f9c1363f541649cf4f0a21444faa089d5ef120b5011105bd3f6dc2111e64298e`.
- This change writes Bob/third-party entrypoint documentation and this planning
  bundle only. Existing runtime/configuration, locks, receipts and vendor sources
  are preserved. No commits or gitlink updates were made.
- Source identities and known incomplete import are recorded in
  [source-snapshot.json](source-snapshot.json). It is a local byte snapshot, not
  a signed release attestation or complete copy of the advertised release.

## Executed checks

| Command/check | Actual result | Scope and limit |
| --- | --- | --- |
| `python3 bob/docs/power-spec-2/maintain_plan.py check` | PASS; nine source hashes, 41 upstream plus four migration tasks, DAG/conditional gates, 18 requirement IDs, 17 test families, generated-view freshness, matrix consistency and local links | Reports 18 absent referenced source links as known gaps; passing does not certify a complete import |
| `python3 bob/docs/power-spec-2/maintain_plan.py render` | PASS; 45 planning packets rendered | Deterministic documentation view, no dispatch |
| `python3 bob/docs/power-spec-2/maintain_plan.py self-test` | PASS; 27 deliberate rejection cases | Planning checker only; source hashes, JSON strictness, schema/source identity, task/DAG/coverage/readiness and conditional gates |
| From `bob/`: `.venv/bin/python -m pytest tests/test_ctest_runner.py tests/test_toolchain_preflight.py tests/test_verifier_sandbox.py -q` | PASS; 70 tests, 1.01 s | Existing Bob behavior baseline; includes legacy permissive behavior, not new-spec acceptance |
| `sha256sum --check third_party/drampower-6.0.0/dependencies.sha256` | PASS; seven archive hashes | Does not prove mutable extracted build inputs or provider accuracy |
| `bash -n third_party/drampower-6.0.0/verify-offline-build.sh` | PASS | Syntax only |
| AST parse of existing SALib smoke and new planning checker | PASS | No smoke import/execution, package qualification or plot regeneration |
| Existing handoff manifest check, before README edit | FAIL; eight pre-existing old-spec mismatches | Preserved legacy drift, not silently repaired |
| Same manifest after README edit | FAIL; nine mismatches | Eight pre-existing failures plus intentional `third_party/README.md` migration |
| `git diff --check` and `git -C bob diff --check` | PASS | Tracked diff formatting; new files checked separately by plan validation |

Planning checker interpreter: Python 3.14.3 (`python3`). Bob scoped-test
interpreter: Python 3.14.2 (`bob/.venv/bin/python`). The planning tool uses only
the standard library and requires Python 3.11+; no dependencies were installed.

An initial full-plan link check failed while the parallel third-party document
was not yet written. A later link inventory identified this not-yet-written
receipt. Those construction-time failures were retained as findings and resolved
by completing the intended documents; neither was a provider/model failure.

## Independent planning review

Separate agents reviewed the new/old specification delta, Bob code/test surfaces
and every third-party directory/retained asset category. Review exposed and the
plan corrected:

- Pending numerical thresholds must block qualification, not all D1 discovery.
- Intake can record verified source gaps without pretending definitions exist.
- Every relevant claim inherits C-02/U-02/Q-01 gates; P-04/H-01 name them explicitly.
- Known DatasetManifest, AllowedInputManifest, ModelSubmission, PredictionBundle,
  ScoreProfile and ScoreReport outputs are named in applicable task packets.
- Packet test families agree with the validation matrix, including native
  adaptation, accounting, control and release checks.
- Planning checks reject scalar step lists, nonexistent requirement sources,
  unknown schema versions, wrong snapshot pointers, overflow to infinity and
  omitted source-link inventory, in addition to task/graph/readiness mutations.
- Missing-acceptance status vocabulary remains an explicit F-01 contract decision.

These reviewers shared a development workspace. Their review improves the plan;
it is not the separately privileged independent scientific validation required
by A-02/F-07 or evidence of physical accuracy.

## Remaining validation work

All 41 upstream implementation tasks and four local migration tasks remain
PLANNED. All generated packets have `dispatch_ready: false`. The original release's
reported 53 unit tests / 15 check groups were not run here: its tools, tests and
logs are absent. Missing normative/exposure schemas and policy decisions gate
dependent work. The [validation plan](VALIDATION.md) and
[third-party receipt/limits](../../../third_party/POWER_SPEC_2_MIGRATION.md#5-existing-checks-versus-planned-tests)
distinguish future checks from historical or executed evidence.
