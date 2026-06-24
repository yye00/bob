# Worker Prompt Directives — F-R7-609

This file documents the four SWE-Bench cheap-win directives injected into
every worker system prompt via `bob.dispatch.apply_cheap_wins`.

All four directives are **on by default** and toggleable per-feature via
YAML fields.

---

## (A) Repo Tree — `skip_repo_tree: false`

Before spawning a worker, `inject_repo_tree_into_prompt` prepends a capped
directory tree of the workspace:

```
## Repository Tree (repo_tree — F-R7-609)

```
<tree output capped at 200 lines>
```
```

**Why:** Addresses the #1 SWE-Bench failure mode ("right file, wrong
abstraction") and the secondary "wrong file" mode. Source: Anthropic SWE-Bench
scaffold (Sonnet 4.5 77.2%, high-comp 82.0%).

**Toggle:** Set `skip_repo_tree: true` on the feature to suppress.

---

## (B) Failing Repro Test First — `skip_repro_test: false`

The following standing directive is appended to every worker prompt when
the feature has at least one `pytest:` AC:

```
## STANDING DIRECTIVE — Write a Failing Repro Test First

Before editing any source file:
1. Write a failing test that captures the bug or missing behaviour.
2. Run it and confirm it is RED (fails as expected).
3. Make your edits to the source.
4. Run the test again and confirm it is GREEN (passes).

This applies to all AC kinds except structural. For structural ACs
(file_exists, grep-literal, etc.) skip this directive
(feature.skip_repro_test: true in the YAML overrides it at the feature level).
```

**Why:** Anthropic's own `+pp` prompt addendum. Enforces the red→green TDD
cycle, preventing workers from writing code that happens to pass on their first
try but doesn't actually fix the underlying behaviour.

**Toggle:** Set `skip_repro_test: true` on the feature, or use only structural
ACs — both suppress the directive automatically.

---

## (C) Adaptive Edit Mode — computed per feature

`select_edit_mode(edit_site_count, edit_span)` chooses the edit strategy:

| Condition | Mode |
|-----------|------|
| `edit_site_count > 3` OR `edit_span > 40` | `rewrite` (whole-file) |
| otherwise | `replace` (string-replace) |

The decision is logged as a structured event:

```json
{"event": "EDIT_MODE", "mode": "replace|rewrite", "sites": N, "span": L}
```

**Why:** SWE-Edit (NeurIPS 2025): +2.1% accuracy, -17.9% cost by switching to
whole-file rewrite only when the edit is large enough to make string-replace
fragile.

**Inputs:** `edit_site_count` and `edit_span` come from the BF-4 hierarchical
localizer (F-R7-600).

---

## (D) Mutation-Pass Check — WEAK_TEST_DETECTED

After a worker reports test-pass, `run_mutation_pass_check` flips a trivial
mutation (constant value or boolean negation) in the edited region and
re-runs the target test. If the test **still passes**, a weak-test event is
emitted:

```json
{"event": "WEAK_TEST_DETECTED", "feature_id": "...", "detail": "mutation did not flip test result"}
```

**Why:** ICSE 2026 false-pass study: 12–22% of "passing" patches are logically
wrong because tests under-specify behaviour. This costs one extra test run per
feature.

**Implementation:** `bob.dispatch.run_mutation_pass_check` /
`bob.dispatch.check_mutation_pass`.

---

## Integration Point

All four directives are wired through `bob.dispatch.apply_cheap_wins`:

```python
augmented_prompt, meta = apply_cheap_wins(
    prompt, workspace, feature,
    edit_site_count=sites,
    edit_span=span,
)
```

`meta` contains `repo_tree_injected`, `failing_repro_test_injected`, and
`edit_mode` (the full EDIT_MODE event dict).
