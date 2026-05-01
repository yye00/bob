---
name: using-bob3-memory
description: Use when starting any feature implementation, when encountering a bug, or when a past decision is relevant. Bob3 ships with semantic memory (mem0 + FastEmbed + Qdrant) exposed as MCP tools. Searching lessons before implementing prevents repeating past mistakes; recording lessons after solving bugs helps future agents.
---

# Using bob3 memory

Bob3 gives every sub-agent access to a persistent, semantic memory store backed by mem0 + FastEmbed + Qdrant. The memory is shared across all agents and all features, so what you learn here helps the next one.

## Tools available to you

All exposed via MCP under the `bob3-memory` server:

| Tool | Purpose |
|---|---|
| `memory_search(query, pool=None, limit=10)` | Semantic search; top results ranked by similarity |
| `memory_add(content, pool, metadata={})` | Store a new memory |
| `memory_record_feedback(memory_id, success)` | Mark a retrieved memory as helpful/unhelpful |
| `memory_get(memory_id)` | Fetch a specific memory |
| `memory_archive(memory_id)` | Hide a memory from future searches |
| `memory_get_stats()` | Pool/status counts |
| `memory_list_pools()` | Valid pool names |

## Memory pools

Four pools. Choose deliberately:

| Pool | What belongs | Example |
|---|---|---|
| `lessons` | Hard-won insights from bugs, failures, tricky debugging | "Feature F006 must not call subprocess — the claude-code-sdk must be used directly. Violating this caused a 6-hour debugging session." |
| `facts` | Technical invariants about the project, APIs, or libraries | "OPM Flow writes `.EGRID` for grid geometry and `.UNRST` for restart pressures" |
| `preferences` | User/project conventions | "User prefers terse responses; no trailing summaries" |
| `context` | Session or short-lived state | "Currently debugging a stress-tensor sign error in the Kirsch benchmark" |

If you don't specify a pool, bob3 auto-classifies by keyword. Auto-classification is coarse — prefer to specify.

## When to search (almost always)

**At the start of every feature**, search for prior context:

```python
memory_search("<feature name or key concept>", pool="lessons", limit=5)
memory_search("<feature name>", pool="facts", limit=5)
memory_search("<feature name>", pool="context", limit=3)
```

If you hit a bug:

```python
memory_search("<error message or symptom>", pool="lessons", limit=10)
```

If an acceptance criterion uses domain terminology you're unsure about:

```python
memory_search("<domain term>", pool="facts", limit=10)
```

## When to record (after success *and* after failure)

**After a non-trivial bug fix**, record the lesson:

```python
memory_add(
    content="When using Gmsh to mesh intersecting faults, the boolean fragment operation must be applied BEFORE setting mesh size fields, otherwise the size fields apply to the pre-fragment geometry and mesh generation fails silently. Always: (1) geometry, (2) boolean ops, (3) size fields, (4) generate.",
    pool="lessons",
    metadata={"feature_id": "F012", "category": "mesh-generation"},
)
```

**After you solve a nonobvious integration**, record a fact:

```python
memory_add(
    content="DOLFINx v0.9 requires `dolfinx.fem.petsc.assemble_matrix` (note the `.petsc.` namespace); earlier docs reference the name without `.petsc.` which no longer exists.",
    pool="facts",
    metadata={"library": "dolfinx", "version": "0.9"},
)
```

**After the user corrects you twice on the same thing**, record a preference:

```python
memory_add(
    content="For this project, V&V features must compare against analytical solutions with explicit tolerances, not just 'close enough' visual checks.",
    pool="preferences",
)
```

## When to give feedback on retrieved memories

If you searched memory and one of the results actually helped, tell the system:

```python
memory_record_feedback(memory_id="abc-123", success=True)
```

If a retrieved memory was wrong or misleading:

```python
memory_record_feedback(memory_id="abc-123", success=False)
```

This feeds into the memory's usefulness score and lets bob3 demote bad memories over time.

## Anti-patterns

- **Don't store ephemeral state** in memory (e.g., "right now I'm on line 42 of foo.py"). Use the feature's progress notes instead.
- **Don't duplicate what's in the code**. If the information lives in a source file or docstring, point to it rather than copying.
- **Don't write memories that are too vague** to be retrievable. "Be careful with faults" is useless; "Fault facet tags must be assigned AFTER `dolfinx.io.gmshio.model_to_mesh` returns, because the function renumbers cells and the old tags become invalid" is useful.
- **Don't skip the search step**. The 10 seconds you save not searching will cost you an hour when you rediscover a solved problem.

## Concrete workflow

```
1. Read the feature description and acceptance criteria.
2. memory_search("<feature name>", pool="lessons") → read top 3-5 results
3. memory_search("<key domain term>", pool="facts") → read top 3-5 results
4. Implement the feature (following test-driven-development and no-stubs-no-mocks skills).
5. If you hit a bug:
   a. memory_search("<error>", pool="lessons")
   b. If no match, try perplexity_research for deep research
   c. After solving, memory_add(content=<the lesson>, pool="lessons")
6. Before declaring done, use the adversarial-self-review skill.
```
