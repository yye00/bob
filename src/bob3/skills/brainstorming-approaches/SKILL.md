---
name: brainstorming-approaches
description: Use at the start of any non-trivial feature, before writing code. When a feature has multiple valid implementation approaches, think through 2-3 alternatives with trade-offs before picking one. Prevents committing to the first idea when a better one was one minute away.
---

# Brainstorming approaches

Before writing code for a non-trivial feature, propose 2-3 implementation approaches and pick one with explicit reasoning.

This is especially important in scientific computing features (numerical methods, algorithm choices) where the first approach you think of often has trade-offs that a different approach avoids — and realizing this after you've written the code wastes time.

## When to use this skill

- Feature has >3 acceptance criteria or >100 lines of estimated implementation
- Feature mentions a well-known technique with known variants (e.g., "Bishop method" has Simplified, Modified, Corrected)
- Feature description uses phrases like "efficient", "robust", "handles X" — these require design choices
- The domain has competing standards (e.g., mesh formats, numerical quadrature schemes, integration orders)
- You're about to make a structural decision (where files live, how modules interact)

## The process

### 1. State the core requirement in one sentence

Force yourself to compress what the feature is asking for into 15 words or fewer. If you can't, you don't understand the feature yet — go read the spec again and do `memory_search` for related context.

Example: *"Compute factor of safety for a 2D slope using Bishop's Simplified method on circular slip surfaces."*

### 2. List 2-3 plausible approaches

For each, write:
- **Approach**: one-line description
- **Pros**: what it does well
- **Cons**: what it gives up
- **Cost**: rough LOC / time / dependencies

Example (slip-surface search):

**A. Grid search over circle centers**
- Pros: Simple, embarrassingly parallel, predictable runtime
- Cons: Can miss minimum if grid is coarse; wasteful when minimum is local
- Cost: ~100 LOC, uses numpy only

**B. Local optimization from initial guess**
- Pros: Efficient near a good starting point
- Cons: Requires a starting point; can fall into local minimum
- Cost: ~80 LOC, needs scipy.optimize

**C. Hybrid: coarse grid → refine winners with local opt**
- Pros: Robust + efficient
- Cons: Two moving parts; more code to test
- Cost: ~150 LOC, uses numpy + scipy.optimize

### 3. Pick and justify

State which approach you're taking and why. Be explicit about the trade-off you're accepting.

*"I'm going with A (grid search) because acceptance criterion F017 requires an FoS contour plot as output, which the grid gives me naturally. C would be faster for finding the minimum but doesn't produce the contour without extra work. B alone is rejected because the feature must also handle cases where we don't have a good starting guess."*

### 4. Record non-trivial trade-offs in memory

If the decision involved a real domain trade-off (not just "A is simpler"), record it:

```python
memory_add(
    content="For bob3 slope stability, chose Bishop grid-search over hybrid local-opt because F017 acceptance criterion requires FoS contour output. If F017 is ever relaxed, revisit — hybrid is ~3x faster for deep critical surfaces.",
    pool="lessons",
    metadata={"feature_id": "F017", "decision": "search-algorithm"},
)
```

This lets future agents understand *why* the code looks the way it does.

## Anti-patterns

### Over-brainstorming trivial features
A feature that creates one file with a known format doesn't need three approaches. Use judgment. The skill description says "non-trivial" — if the work is obvious, just do it.

### Paralysis by analysis
Spend at most 10-15 minutes on this step for a typical feature. If you're still weighing trade-offs after that, pick one and start. You'll learn more by implementing than by deliberating.

### Choosing by novelty
Don't pick approach X because it's "more interesting." Pick the one that best fits the criteria and constraints. Boring is often correct.

### Choosing without understanding the domain
If the feature requires domain knowledge you lack (e.g., "use the Newmark-beta method with γ=0.5, β=0.25 for numerical stability"), do NOT guess. Use `researching-unknowns` skill to look it up, or `memory_search("newmark-beta")` to see if a past agent already learned it.

## Multi-criteria decisions

When the feature has competing requirements, make the trade-offs explicit:

| Criterion | Approach A | Approach B | Approach C |
|---|---|---|---|
| Performance | ✓✓ | ✗ | ✓ |
| Simplicity | ✗ | ✓✓ | ✓ |
| Robustness | ✓ | ✗ | ✓✓ |
| Meets F017 contour req | ✓✓ | ✗ | ✓✓ |

Now you can see that **C** dominates **A** on robustness and simplicity without losing the contour output, and dominates **B** on everything.

## Handoff to implementation

Once you've chosen, move to:
- `test-driven-development` — write tests first
- `implementing-acceptance-criteria` — each criterion becomes a test
- `no-stubs-no-mocks` — implement real code

If during implementation you discover the chosen approach won't work, STOP and re-brainstorm. Don't stubbornly push through a dead end.
