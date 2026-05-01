---
name: no-stubs-no-mocks
description: Use when implementing any feature. Enforces writing real, working code — not stubs, placeholders, NotImplementedError, or mocks in production paths. Bob3's AST-based verifier will flag these and mark the feature needs_human; prevention beats cleanup.
---

# No Stubs. No Mocks. No Placeholders.

You are building real software. Bob3 runs an AST-based stub detector on your source files as part of verification. If it finds placeholder patterns, the feature is marked `needs_human`, your work gets rolled back, and a lesson is written to memory for the next agent.

## What will get flagged

**In production source files** (anything under `src/`):

- `def foo(): pass` — function body is just `pass`
- `def foo(): ...` — function body is just Ellipsis
- `def foo(): raise NotImplementedError(...)` — deferred implementation
- `def foo(): return None  # TODO` — TODO markers paired with trivial returns
- `def foo(): return {}` — empty return where the function name implies computation (e.g., `compute_*`, `calculate_*`, `solve_*`, `find_*`)
- `from unittest.mock import Mock` in production source
- `mock_*` variables or instances used outside `tests/`
- `class FakeXxx:` or `class StubXxx:` in `src/`

**Comments that signal abandonment:**

- `# TODO: implement this`
- `# FIXME`
- `# XXX`
- `# placeholder`
- `# stub`

**What is OK:**

- `pass` inside an `except Exception: pass` block *when intentional* — still prefer logging
- `...` as type annotation default (`def f(x: int = ...)`)
- Mocks in test files (`tests/`)
- Abstract methods properly marked with `@abstractmethod` on an ABC

## The discipline

1. **If you can't implement the whole feature in this session**, don't stub the rest. Instead:
   - Finish one complete sub-piece
   - Mark the feature for decomposition (write a lesson to memory using `memory_add` with pool=`lessons`)
   - Report what you finished and what remains
   - Do NOT leave half-finished functions

2. **If you need a dependency that doesn't exist yet**, implement it or document a real blocker. Don't mock your way past it.

3. **If acceptance criteria mention "the function should return X"**, write the function that actually computes X. Do not return a hardcoded X just to pass a test — that's cheating the verifier (and when the next test hits it with different inputs, everything falls over).

4. **Before committing, grep your own work**:
   ```bash
   grep -rn "NotImplementedError\|TODO\|FIXME\|XXX\|def [a-z_]*():\s*pass\b" src/
   ```
   If this returns hits in your new code, fix them before declaring done.

## Why this matters

Bob3 spends real money (Claude tokens) running sub-agents. A stub that passes test assertions but doesn't do the work wastes that investment: the calling code later breaks in a hard-to-diagnose way, bob3's regression detection flags it weeks later, and a human has to untangle it.

Worse, stubs corrupt bob3-memory: future agents search lessons and find the pattern "Feature X was completed" when it wasn't, reinforcing bad behavior.

**If you don't know how to implement something, say so. Use `memory_search` to check for prior lessons. Use the Perplexity MCP (`mcp__plugin_perplexity_perplexity__perplexity_research`) to research. But do not fake it.**
