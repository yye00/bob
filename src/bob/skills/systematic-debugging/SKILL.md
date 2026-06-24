---
name: systematic-debugging
description: Use when a test fails, code behaves unexpectedly, or a feature gets stuck. Find the root cause before proposing a fix. Random tweaking wastes tokens and creates brittle code; disciplined debugging produces real fixes and reusable lessons.
---

# Systematic debugging

When something is wrong, the temptation is to try things until it works. Resist.

Bob runs a RCA (root cause analysis) sub-agent for persistent failures, and it costs real money. A disciplined first-pass debug by you saves both the RCA cost and a wrong "fix" that masks the real issue.

## The rule

**Reproduce → Isolate → Explain → Fix → Verify.** In that order. Skip steps and you'll skip the real bug.

## 1. Reproduce

Make the failure happen deterministically.

- Run the failing test in isolation: `pytest tests/test_foo.py::test_bar -vvs`
- Capture the exact error, stack trace, and surrounding output
- Note anything random: seeds, timestamps, paths, orderings

If you can't reproduce, you can't fix. If the failure is flaky, that itself is the bug — pursue flakiness before anything else.

## 2. Isolate

Find the smallest input or state that triggers the bug. Strip everything else.

Techniques:
- **Bisect the input**: if `compute(big_data)` fails, halve `big_data` and retry. Repeat.
- **Bisect the code**: `git bisect` for regressions, or comment out halves of recent changes
- **Bisect the call stack**: walk up the traceback, find the boundary between "working" and "broken"

Write a one-line failing test that reproduces. This becomes your regression test once fixed.

## 3. Explain

You are not allowed to write a fix until you can state *why* the bug occurs in plain English.

Bad: "I'll add a check for None here."
Good: "The loop calls `db.get_project()` inside the iteration. When the DB returns None (which happens when the project is deleted mid-run), `project.total_cost_usd` raises AttributeError. The correct guard is to re-read the project at each iteration and bail out of the loop cleanly if None."

The difference: the first is pattern-matching to error type; the second identifies the invariant that was violated.

If you can't explain, you don't understand. Go back to Isolate and dig deeper, or use `perplexity_research` / `memory_search` if a knowledge gap is blocking you.

## 4. Fix

Now write the minimal change that fixes the root cause.

- Don't wrap in try/except unless the caller can actually handle the exception meaningfully
- Don't add `if foo is None: return` guards unless None is a valid case you're choosing to handle
- Don't fix symptoms elsewhere — fix the cause where it originates

For each fix, ask: "If I remove this line in 6 months, what bug comes back?" If you can't answer, the fix might be wrong.

## 5. Verify

- Run the failing test. Passes? Good.
- Run the full test suite. Nothing regressed? Good.
- Try the variations you considered in step 2. All handled? Good.
- If the bug was about concurrency/races, stress-test it.

## Capture the lesson

This is what separates a one-off fix from durable learning. After every non-trivial debug:

```python
memory_add(
    content=(
        "Bug: bob run_loop was marking features completed before verification. "
        "Root cause: handle_execution_result wrote status=completed AND cascaded "
        "dependents to ready, but the verification checklist ran after. When "
        "verification failed the code tried to roll back to needs_human but the "
        "cascade had already fired. "
        "Fix: restructured execute_feature to run verification FIRST, then call "
        "handle_execution_result only on success. Cost tracking stays unconditional."
    ),
    pool="lessons",
    metadata={
        "feature_id": "F069",
        "category": "orchestration-flow",
        "severity": "critical",
    },
)
```

The structure: **Symptom → Root cause → Fix**. If your memory entry doesn't have all three, it's a note-to-self, not a lesson.

## Common anti-patterns to avoid

### The shotgun
Changing five things at once, hoping one fixes it. If it works, you don't know which change mattered. If it doesn't, you have five problems now.

→ Change one thing at a time.

### The cargo cult
Copying a fix pattern from somewhere else without understanding why it worked there.

→ Explain step 3 in your own words.

### The mask
Wrapping broken code in try/except to make the error go away.

→ Catch specific exceptions with handling; let unexpected ones propagate.

### The rollback
Reverting your changes and trying again from scratch. Wastes the diagnostic work you did.

→ Once you've isolated, you're close. Push through.

## When debugging a past agent's work

If you inherit a broken feature from a previous sub-agent's run:

1. `memory_search("<feature name>", pool="lessons")` — did they record anything?
2. Read the execution_logs and evidence_artifacts for the feature in the DB
3. Read git log/diff for the feature's commits
4. THEN start reproducing

Often you'll find the prior agent recorded exactly the lesson you need, or evidence showing where they got stuck.

## Stop conditions

You stop debugging when:
- You can explain the bug
- The fix addresses the explanation
- Tests pass
- No new regressions
- A lesson is recorded (if nontrivial)

You do NOT stop when:
- "The test passes now" but you don't know why
- "I changed something and it works" but you can't name the change
- "It probably doesn't matter" — if it mattered enough to debug, the fix matters

If you're truly stuck after an honest effort: record what you tried, mark the feature for human review, move on. Don't burn budget on a rabbit hole.
