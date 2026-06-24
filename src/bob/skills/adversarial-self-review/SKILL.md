---
name: adversarial-self-review
description: Use before declaring any feature complete. Before bob's verification layer checks your work, review it adversarially yourself. Find the bugs you would exploit if you were trying to game the acceptance criteria. The goal is to break your own code before it reaches review.
---

# Adversarial self-review

Before you declare a feature done, spend 5 minutes trying to break it.

You just implemented something. Your brain is in "make it work" mode. Switch into "how would I exploit this" mode. The bugs you find here are bugs bob's verifier or the next feature's agent won't have to find — and won't roll your work back for.

## The adversarial mindset

Pretend you are a hostile reviewer who:
- Suspects you cheated
- Knows every acceptance criterion you had
- Has a stake in finding fault
- Will get credit for every real bug they find

Now review your own diff with that perspective.

## The checklist

### 1. Did I actually solve the problem, or did I pattern-match to make tests green?

Look at your implementation. If you deleted it and tried to re-derive it from the acceptance criteria, would you arrive at the same code? Or did you work backwards from "what makes the test pass"?

If the latter: the test is testing your *implementation*, not the *requirement*. Rewrite the test from the criterion, re-RED, re-GREEN.

### 2. Are my tests independent of my implementation?

Ask: if someone else reimplemented this function correctly but differently (different variable names, different control flow, same observable behavior), would my tests still pass?

If the tests inspect internal state, mock internal calls, or assert on specific iteration orders — they're coupled. Decouple them: assert on inputs and outputs, not mechanics.

### 3. What inputs would break my code?

Go through every argument to every new function and ask:
- Empty? (list, string, dict)
- None? (if the annotation allows it)
- Zero?
- Negative?
- NaN / Inf? (for numerical code)
- Unicode / non-ASCII? (for string code)
- Very large? (1e9 items)
- Malformed? (JSON that isn't JSON, YAML with tabs, file that isn't UTF-8)

For each case: does the code behave sensibly, or blow up with a confusing error? At minimum, add tests for the edge cases that matter.

### 4. Am I hiding bugs in `try/except`?

Search your diff for `except`. For each one:
- Am I catching a specific exception, or `Exception`?
- Am I logging the exception, or swallowing it?
- Does the caller have any way to know something went wrong?
- Could this mask a real bug?

A bare `except:` that logs at DEBUG and returns a default is almost always a bug-hiding pattern. If the failure mode is truly expected, catch the specific exception and handle it explicitly.

### 5. Did I introduce races or ordering bugs?

For concurrent/async code:
- Read-modify-write patterns on shared state → race condition
- Database `SELECT then UPDATE` without a transaction → lost writes
- `os.path.exists(x)` then `open(x)` → TOCTOU race
- Signal handlers that touch shared state without locks

For sequential code:
- Any function depending on dict iteration order?
- Any function depending on filesystem order (`os.listdir` is not sorted)?

### 6. Can the verifier be gamed by my code?

Bob's verifier checks:
- Files exist in `src/`
- Files modified in the last hour
- No stub patterns in AST
- Acceptance criteria appear to be met

A hostile implementation could: touch a file to update mtime, write one `pass`-like function that still technically avoids the stub detector, hardcode return values to make assertion-based tests pass.

**Ask: if I saw this code in someone else's diff, would I catch it as fake?** If the answer is "I'd have to look carefully," you're on the wrong side of the line.

### 7. Did I change something I wasn't supposed to?

`git diff` the full change. Any modifications outside the feature's scope?
- Changed a shared utility? That's now a breaking change for other features.
- Changed a test I didn't author? Suspicious; double-check.
- Deleted code? Was it unreachable, or did I just not want to deal with it?

### 8. Did I break existing tests?

Run the full suite. Not just the new tests. Not just the ones in the file you touched. The whole thing.

If anything that was green is now red: you regressed something. Don't declare done.

## The deliverable of self-review

Write down, out loud or in a scratch file:

- **Bugs I found and fixed**: list them
- **Bugs I found but cannot fix in scope**: record as lessons with `memory_add(pool="lessons")` so the next agent sees them
- **Edge cases I tested**: list them
- **Edge cases I consciously skipped**: list them and *why*

If this list is empty or trivial, you didn't try hard enough. Go again.

## When to stop

You stop when:
- The full test suite passes
- You have specific tests for every criterion
- You've tried to exploit the feature and can't find a gap
- `git diff` shows only the changes you intended

You do NOT stop when:
- "Tests pass" but you haven't checked which tests
- "It works on my input" but you didn't try edge cases
- "The acceptance criteria seem satisfied" but you didn't encode them as tests

If in doubt, ask another sub-agent to review. It's cheaper than rollback.
