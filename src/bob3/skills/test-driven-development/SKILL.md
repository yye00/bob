---
name: test-driven-development
description: Use when implementing any feature or bug fix, before writing production code. Write the test first, verify it fails for the right reason, then implement until it passes. Bob3's verification layer rewards TDD; the AST stub detector punishes shortcuts.
---

# Test-driven development for bob3 sub-agents

Write the test first. Verify it fails. Then write the minimum code to make it pass.

This is not a stylistic preference — bob3 specifically runs verification checks that reward TDD: `test_files_exist`, `code_changes_made`, `no_stubs_in_source`, and `acceptance_criteria_met`. Tests written after the fact tend to pattern-match on the implementation instead of encoding the requirement.

## The loop

### Step 1 — Read

Read the feature's acceptance criteria. Identify the observable behavior each one describes. (See the `implementing-acceptance-criteria` skill for how criteria map to tests.)

### Step 2 — RED: write the failing test

For each behavior, write a test that asserts it. Make the test **specific and small**:

```python
def test_bishop_converges_within_50_iterations_for_homogeneous_slope():
    """Regression: Bishop's implicit FoS equation must converge quickly."""
    slope = make_homogeneous_slope(c=20, phi=20, gamma=18, H=10)
    fos, iterations = bishop_simplified(slope, return_iterations=True)
    assert iterations <= 50
    assert 1.0 < fos < 2.0  # sanity bound, exact value tested elsewhere
```

Run the test. **Verify it fails with the right error** — a "function not defined" error is fine; a syntax error in the test itself is not. The test must fail for the *reason you expect*, otherwise it's not testing what you think.

### Step 3 — GREEN: implement the minimum

Write the simplest real code that makes the test pass. Do not over-engineer. Do not add features the test doesn't require.

**Simplest does NOT mean faking.** Returning a hardcoded `1.37` to make a FoS test pass is not simple — it's a stub, and it will be caught. Simplest means: solve the actual problem with the least code that genuinely solves it.

### Step 4 — run the test

It should now pass. If it doesn't, the bug is in your implementation, not the test (unless the test was wrong — in which case fix the test first, rerun to re-RED, then fix the code).

### Step 5 — REFACTOR

Now that you have a green test, clean up. Rename variables, extract helpers, remove duplication. Re-run the test after each change. If it fails, you broke something; undo and retry.

### Step 6 — repeat for the next criterion

## What a test must do

1. **Fail before your code exists.** If a new test passes without any implementation, it's not testing the behavior.
2. **Assert a specific observable behavior.** `assert result is not None` is rarely enough.
3. **Run fast.** Most tests should take <1 second. Long-running benchmarks belong in marked slow tests, not the default run.
4. **Be deterministic.** Same inputs → same pass/fail. No network, no wall-clock dependencies, no RNG without a seed.
5. **Be independent.** Other tests must not affect this one; other tests must not depend on this one.
6. **Read like documentation.** A new engineer should understand the requirement from the test name + assertion.

## What goes in tests vs source

| File | Allowed | Not allowed |
|---|---|---|
| `tests/*.py` | `unittest.mock`, `Mock`, fixtures, hypothesis, parametrize | Heavy implementation logic (belongs in src) |
| `src/**/*.py` | Real implementation code | `Mock`, `mock_*`, `stub_`, `fake_` classes, `NotImplementedError`, `TODO/FIXME/XXX` placeholders |

Bob3's AST checker scans `src/` specifically for stub/mock patterns. If you put `Mock()` in production code, your feature will be marked `needs_human`.

## Numerical / scientific tests — extra discipline

For tests that assert numerical results (V&V benchmarks, error norms, convergence rates), always:

- State the reference value and its source in the docstring.
- Assert a relative tolerance, not exact equality.
- Include a `pytest.approx` or explicit `abs(x - ref)/ref < tol` comparison.
- For convergence-rate tests, use at least 4 mesh refinement levels.

```python
def test_mms_convergence_p1_elements():
    """MMS with polynomial solution, P1 elements, L2 norm should converge as O(h^2)."""
    errors = [run_mms_on_mesh(n) for n in (8, 16, 32, 64)]
    rates = [np.log2(errors[i]/errors[i+1]) for i in range(len(errors)-1)]
    for rate in rates:
        assert 1.8 < rate < 2.2, f"P1 convergence rate {rate:.2f} outside [1.8, 2.2]"
```

## Before declaring a feature done

For every new or modified function, there is a test that:
- Exercises at least the happy path
- Exercises at least one edge case
- Would fail if the function's core behavior regressed

Run the full suite (`pytest`) before committing. One new passing test and ten silently-broken existing tests is a net regression.
