---
name: researching-unknowns
description: Use when stuck on a feature due to a knowledge gap — unfamiliar library API, unknown domain concept, conflicting documentation, or numerical method whose details you don't fully remember. Bob sub-agents have Perplexity MCP tools for web-grounded research; use them instead of guessing.
---

# Researching unknowns

You are a capable engineer but not omniscient. When a feature requires knowledge you don't have, the wrong move is to guess. The right move is to research.

Bob provides Perplexity MCP tools for web-grounded research that return live, cited results. Use them.

## When to research

Research when you encounter:

- A **library API** you're not sure about — especially fast-moving ones (dolfinx, jax, torch). Docs can be stale or version-mismatched.
- A **domain concept** named in the feature but not explained (e.g., "Mohr-Coulomb yield criterion with non-associated flow", "Generalized Hoek-Brown criterion")
- A **numerical method** whose details you need precisely (quadrature rules, time-integration schemes, stability conditions)
- **Benchmarks** or **published values** that a V&V feature must compare against
- **File formats** you haven't encountered (EGRID, UNRST, VTK variants)
- **Conflicting information** in what you already know (e.g., two different formulations of the same equation)

Do NOT research when:
- The answer is in memory — `memory_search` first
- The answer is in the codebase — grep first
- The answer is in a standard library you already know
- The question is a design choice, not a knowledge gap — use `brainstorming-approaches` instead

## The tools

| Tool | When |
|---|---|
| `perplexity_search(query)` | Quick lookup — URL, fact, recent news. Lightweight. |
| `perplexity_ask(question)` | Short answer with citations. Best for direct questions. |
| `perplexity_research(question)` | Deep multi-source research, 30+ seconds. Use for gnarly questions where one source won't do. |
| `perplexity_reason(question)` | Step-by-step reasoning over multiple sources. Best for "why does X behave this way" questions. |

## How to ask

**Bad query:** `"how does bishop method work"` — too broad, returns introductory material

**Better query:** `"Bishop simplified method factor of safety convergence tolerance typical iteration count"` — specific, returns useful results

**Best query:** `"Bishop simplified slope stability iterative solution F = f(F) implicit equation initial guess convergence criteria"` — targets the exact subproblem you're stuck on

Include:
- The specific technique name
- The sub-problem you're facing
- Keywords that distinguish your context (domain, scale, regime)

## Domain-specific research workflow

For scientific computing / engineering features, a typical sequence:

1. `memory_search("<domain term>", pool="facts")` — does bob already know this?
2. If no: `perplexity_ask("concise explanation of <term> in context of <feature>")`
3. If the answer raises more questions: `perplexity_research("<followup>")` for depth
4. Record what you learned: `memory_add(pool="facts")` so the next agent doesn't re-research

Example chain:

```
memory_search("Mandel problem Mandel-Cryer effect", pool="facts")
→ no hits

perplexity_ask("Mandel problem in poroelasticity: what is the Mandel-Cryer effect and why does pore pressure initially rise before dissipating")
→ explanation with citation to Cheng, Detournay

perplexity_research("Mandel problem analytical solution series expansion eigenvalue equation implementation")
→ detailed math with references

memory_add(
    content="Mandel's problem: 2D poroelastic benchmark. Key phenomenon is Mandel-Cryer effect where center pore pressure initially rises ABOVE applied load due to coupling between stress redistribution (fast) and fluid drainage (slow). The analytical solution requires solving tan(α_n) = α_n*(1-ν)/(ν_u-ν) for eigenvalues α_n. See Cheng 'Poroelasticity' ch. 7 for derivation.",
    pool="facts",
    metadata={"feature_id": "F021", "topic": "mandel-problem"}
)
```

## Verifying what you learn

Web results can be wrong, especially for niche technical content. Cross-check:

- **For formulas**: prefer primary sources (textbooks, peer-reviewed papers) over tutorials and blogs
- **For library APIs**: prefer the library's own docs or source code over third-party tutorials — they drift
- **For numerical values**: find at least two independent sources

When you cite a result in code comments or memory, note the source:

```python
# Biot coefficient for typical sandstones: 0.7-0.9 (Wang, "Theory of Linear
# Poroelasticity", 2000, Table 4.1). Using α=0.8 as default.
DEFAULT_BIOT = 0.8
```

## When research leaves you stuck

If you've done diligent research and still can't resolve the ambiguity:

1. Record the unresolved question in memory:
   ```python
   memory_add(
       content="Feature F015 requires thermal diffusivity for the cap rock. Spec says 'typical shale' but published values range 5e-7 to 3e-6 m²/s (factor of 6 spread). Need user input — using 1e-6 for now.",
       pool="context",
       metadata={"feature_id": "F015", "needs_clarification": True},
   )
   ```

2. Make your best-informed choice and document the uncertainty in a code comment.

3. Move on. Don't stall. Mark the feature with a refinement note if one is needed.

## Don't research in place of thinking

Research fills gaps; it does not replace engineering judgment. Don't burn 30 minutes on `perplexity_research` for something you can reason through in 5 minutes. Research when you don't know; think when you do.
