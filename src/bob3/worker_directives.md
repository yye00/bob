# Worker Directives — F-R7-609 (SWE-Bench Cheap Wins)

This file documents the four standing directives injected into every worker
system prompt. Each is toggleable via feature YAML (defaults ON).

---

## (A) Repository Tree

Before editing any files, you will receive a capped directory tree (≤ 200 lines)
of the workspace under the heading **Repository Tree (repo\_tree — F-R7-609)**.

Use it to orient yourself: identify the right module, avoid editing the wrong
abstraction, and confirm the package layout before writing import paths.

**Toggle:** `feature.skip_repo_tree: true` disables injection for this feature.

---

## (B) STANDING DIRECTIVE — Write a Failing Repro Test First

Before editing any source file:
1. Write a failing test that captures the bug or missing behaviour.
2. Run it and confirm it is RED (fails as expected).
3. Make your edits to the source.
4. Run the test again and confirm it is GREEN (passes).

This applies to all AC kinds except structural. For structural ACs
(file_exists, grep-literal, etc.) skip this directive
(feature.skip_repro_test: true in the YAML overrides it at the feature level).

**Research basis:** Anthropic SWE-Bench scaffold +pp prompt addendum (Sonnet 4.5 77.2%, high-comp 82.0%).

**Toggle:** `feature.skip_repro_test: true` disables this directive.

---

## (C) Adaptive Edit Mode

The dispatcher selects the edit strategy based on the localizer output:

- **string-replace** (default): fewer than 4 edit sites AND span ≤ 40 lines.
- **whole-file rewrite**: more than 3 edit sites OR span > 40 lines.

The chosen mode is emitted as `{"event":"EDIT_MODE","mode":"replace|rewrite","sites":N,"span":L}`.

**Research basis:** SWE-Edit (NeurIPS 2025): +2.1% accuracy, −17.9% cost.

**Toggle:** Always active; thresholds configurable via dispatcher constants.

---

## (D) Mutation-Pass Check

After you report test-pass, the dispatcher flips one constant or negates one
boolean in the edited region and re-runs the target test. If the test still
passes, the feature is flagged with:

```json
{"event": "WEAK_TEST_DETECTED", "feature_id": "..."}
```

A stronger AC will be required before the feature is marked complete.

**Research basis:** ICSE 2026 false-pass study: 12–22% of "passing" patches are
logically wrong because tests under-specify behaviour.

**Toggle:** `feature.skip_mutation_check: true` disables this check.
