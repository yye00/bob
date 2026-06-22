# Bob3 Greenfield Gap Analysis

**Source:** Knowledge Share #2 — "The Disposable Architecture: AI-Driven Development in Greenfield Projects"
**Author:** Yaakoub Elkhamra | April 2026
**Date:** 2026-05-14
**Scope:** Gaps between greenfield best practices presented in KS#2 and Bob3's current implementation

---

## Executive Summary

Bob3 implements many of the harness engineering principles from Knowledge Share #2 — graduated failure recovery, acceptance criteria DSL, semantic memory, calibration tracking, DAG dependencies, and adversarial self-review. However, 10 significant gaps remain. The two most critical: **Bob3 has no independent evaluator agent** (the sub-agent grades its own homework) and **zero security scanning** (the exact vulnerability profile warned about in Act IV).

---

## What Bob3 Already Does Well

| KS#2 Principle | Bob3 Implementation | Status |
|---|---|---|
| Harness > Model | Bob3 IS the harness. Default model is Sonnet (cheaper). | Aligned |
| Acceptance Criteria as Contracts | DSL with 4 eval types: file exists, function defined, pytest, python expression | Aligned |
| Hashimoto-Osmani: every mistake becomes an instruction | Review findings registry (`reviews/findings.yaml`); queried pre-implementation; recurring patterns (>=3) trigger structural fixes | Aligned |
| Graduated Failure Recovery | 8-stage pipeline: spawn retries, verification, confidence decay, RCA, decomposition, research, needs_human | Aligned |
| DAG Dependencies | SQLite-backed feature dependency graph, topological ordering, cascade on completion/rollback | Aligned |
| Confidence Calibration | `(task_class, confidence_bucket) -> empirical_pass_rate` with drift alerts | Aligned |
| Resume After Interruption | SIGINT/SIGTERM checkpoint -> `interrupted` state -> auto-resume | Aligned |
| No Blind Retries | RCA sub-agent with IRON LAW: no fixes without root causes, enforced at parser level | Aligned |

---

## Gap #1: No Independent Evaluator Agent (P0)

### The Principle (KS#2 Act V)

The Planner-Generator-Evaluator pattern uses an evaluator that "tests like a real user: clicking buttons, filling forms, checking visual output via Playwright screenshots."

Blind Spot Warning: "The coder agent is grading its own homework -- there is no independent verification loop."

### Current State

Bob3 uses a two-agent pattern: orchestrator + implementation sub-agent. The adversarial self-review skill runs **inside the same sub-agent** — it is literally grading its own homework. The mechanical verifier (AST checks, pytest, file existence, acceptance criteria) catches structural issues but cannot assess whether the feature works as intended from a user's perspective.

### What's Missing

- Independent LLM agent that evaluates the implementation against the spec
- Playwright/browser-based testing for UI features
- Sprint contract negotiation between generator and evaluator
- GAN-inspired adversarial loop (generator proposes, evaluator rejects, iterate)

### Proposed Fix

Add a post-implementation evaluator sub-agent that:
1. Receives the feature spec + acceptance criteria (same as implementation agent)
2. Has NO access to the implementation agent's prompt or reasoning
3. Reviews the diff, runs the code, tests user-facing behavior
4. Returns a structured verdict: PASS / FAIL with specific feedback
5. On FAIL, the implementation agent gets the feedback and iterates

For UI features, the evaluator should use Playwright to interact with the running application.

### Effort: High
### Impact: High — prevents the "tests pass but feature doesn't work" failure mode

---

## Gap #2: Zero Security Scanning (P0)

### The Principle (KS#2 Act IV)

"Security Scan from Commit Zero. Not after launch. Not before launch. From the first commit."

KS#2 cites:
- 91.5% of vibe-coded apps contain at least one vulnerability traceable to AI hallucination
- 2.74x more XSS vulnerabilities in AI-authored PRs vs human-written
- Slopsquatting: ~20% of AI-generated code references packages that don't exist
- Rules file backdoor: hidden Unicode in config files makes AI generate backdoored code

### Current State

Bob3's 8-point verification checklist checks **correctness** (stubs, tests, files, acceptance criteria) but has **zero security checks**:
- No SAST (static application security testing)
- No dependency auditing (e.g., `pip-audit`, `npm audit`)
- No OWASP Top 10 scanning
- No package name validation against known hallucinated/malicious packages
- No secrets detection (hardcoded API keys, credentials)

### Proposed Fix

Add security verification as check #9 in the verification pipeline:
1. **Dependency audit:** validate all imported packages exist on PyPI/npm and aren't known-malicious
2. **Secrets scan:** grep for API keys, tokens, passwords in source (use patterns like `trufflehog` or `detect-secrets`)
3. **SAST basics:** ban `eval()`, `exec()`, `subprocess.call(shell=True)`, SQL string concatenation
4. **Slopsquatting check:** verify every `import` and `require` resolves to a real package

### Effort: Medium
### Impact: High — Bob3 is building code with the exact vulnerability profile the talk warns about

---

## Gap #3: No CLAUDE.md Generation for Target Projects (P1)

### The Principle (KS#2 Greenfield Checklist #1)

"Write the CLAUDE.md Before the Code. In greenfield, it's a blueprint, not a map. Prescribe your architecture, conventions, constraints, and 'never do' list before generating a single line. One hour saves one hundred."

### Current State

Bob3 installs 9 bundled skills into sub-agent workspaces but does NOT generate a project-level `CLAUDE.md` encoding:
- Architecture decisions for the target project
- Coding conventions and style rules
- "Never do" constraints specific to the domain
- File organization patterns
- Test conventions

Sub-agents have no persistent project-level guide document. Each session rediscovers conventions from existing code rather than reading a prescriptive blueprint.

### Proposed Fix

Add a `CLAUDE.md` generation phase during `bob3 init`:
1. Parse the YAML spec for project-level conventions, architecture constraints, language/framework choices
2. Generate an initial `CLAUDE.md` with: architecture decisions, file layout, naming conventions, test patterns, dependency rules, "never do" list
3. Update `CLAUDE.md` during the run loop when the memory system discovers new conventions or recurring issues
4. Every sub-agent gets this as part of its workspace setup

### Effort: Low-Medium
### Impact: High — prevents convention drift across sub-agent sessions

---

## Gap #4: No Parallel Execution via Worktrees (P1)

### The Principle (KS#2 Act V)

"`claude --worktree feature-name` for independent tasks in parallel."
Boris runs 3-5 worktrees simultaneously, producing 20-30 PRs/day.
"Worktrees parallelize execution. Harnesses parallelize thinking."

### Current State

Bob3 is strictly sequential — one feature at a time. From the architecture analysis: "No Concurrent Feature Execution — Sequential-by-design." SQLite single-writer is cited as justification.

The DAG already knows which features have no dependency edges between them, but this information is unused for parallelization.

### What's Missing

- Parallel sub-agent execution for independent features
- Git worktree isolation per feature
- Concurrent budget tracking (SQLite single-writer is solvable with WAL mode or a separate budget service)
- Merge conflict detection/resolution when parallel features touch the same files

### Proposed Fix

1. Query the DAG for independent ready features (no shared dependency edges)
2. Spawn each into its own git worktree: `git worktree add .worktrees/feature-N branch-N`
3. Run sub-agents concurrently (bounded by `BOB3_MAX_PARALLEL_FEATURES`, default 3)
4. Use SQLite WAL mode for concurrent reads; serialize writes through a queue
5. Merge worktrees back to main after verification passes
6. Detect merge conflicts; if conflicted, serialize those features

### Effort: High
### Impact: High — 3-5x throughput for projects with independent features

---

## Gap #5: No Compounding Learnings into Project Docs (P1)

### The Principle (KS#2 Act V)

"Tag `@.claude` on PRs to add learnings. Each session improves all future sessions. Shared CLAUDE.md updated multiple times weekly."

### Current State

Bob3's memory system persists learnings across runs (semantic memory via mem0ai/Qdrant), but those learnings never flow back into the target project's documentation. If someone else (or a different tool) works on the project Bob3 built, all learnings are invisible.

### Proposed Fix

1. After each feature completion, extract key learnings from memory that are project-specific
2. Append discovered conventions, gotchas, and patterns to the project's `CLAUDE.md`
3. On recurring patterns (>=3 in registry), promote to a "Known Issues" or "Architecture Decisions" section
4. Learnings become part of the project artifact, not just Bob3's internal state

### Effort: Low
### Impact: Medium — makes Bob3-built projects self-documenting

---

## Gap #6: No Pre-Implementation Plan Review (P2)

### The Principle (KS#2 Act V — Fowler's Guides and Sensors)

Guides (Feedforward): Steer before acting. Computational: system prompts, CLAUDE.md, constraints. Inferential: LLM asks "Is this plan safe?"
Sensors (Feedback): Correct after acting. Computational: linters, type checkers, test suites. Inferential: LLM asks "Does this PR match spec?"

### Current State

Bob3 has strong sensors (verification checklist, AST checks, test suites, regression detection) but weak guides. The orientation prompt tells the sub-agent WHAT to build but there's no pre-implementation check asking "is this approach sound before you start coding?"

### Proposed Fix

Add an optional planning phase per feature:
1. Sub-agent first outputs a plan (files to create/modify, approach, risks)
2. Plan reviewed by a lightweight LLM call: does it match the spec? does it conflict with existing architecture? does it repeat a known anti-pattern from the registry?
3. If plan is rejected, sub-agent revises before writing code
4. Gate on feature risk level: skip for low-risk, require for high-risk features

### Effort: Medium
### Impact: Medium — prevents wasted sub-agent runs on doomed approaches

---

## Gap #7: No "Build It Twice" Exploration Phase (P2)

### The Principle (KS#2 Greenfield Checklist #2)

"Day 1-2: vibe code it, explore the problem space. Then stop. Assess. Design the real architecture on paper. Build 2: AI as accelerator, not architect. The two-day investment saves two months of refactoring."

### Current State

Bob3 builds once and iterates through failures. The research sub-agent partially fills this gap (exploring unknowns before implementing), but there's no deliberate exploration/throwaway phase where the system prototypes to learn the problem space before committing to architecture.

### Proposed Fix

Add an optional `--explore-first` flag to `bob3 run`:
1. Phase 1: Build a minimal prototype of the first N features (e.g., foundation layer) in a throwaway branch
2. Phase 2: Analyze what was learned — common patterns, unexpected complexity, dependency issues
3. Phase 3: Update the spec and CLAUDE.md based on learnings, then build for real
4. The throwaway branch is deleted after analysis

### Effort: Medium
### Impact: Medium — most valuable for novel domains where the spec is speculative

---

## Gap #8: No Scaffolding Tagging (Durable vs. Ephemeral) (P2)

### The Principle (KS#2 Act III)

"Tag every scaffold component with the limitation it addresses."
Boris: "Every new model release, we delete a bunch of code."
"Every harness component encodes an assumption about what the model can't do. When the model improves, the component dies."

### Current State

No tagging system. When a model upgrade ships (e.g., Opus 4.6 absorbing sprint complexity), there's no way to audit which parts of Bob3's scaffolding are now redundant. The orientation prompt, progress notes format, and prompt engineering tricks may already be unnecessary.

### Proposed Fix

1. Add `# SCAFFOLDING: <limitation>` comments to compensatory code
2. Track in a `SCAFFOLDING.md` manifest: component, limitation it addresses, model version it was added for
3. On model upgrade, review manifest: test with each scaffold disabled to see if the model now handles it natively
4. Example entries:
   - `orientation.py:L15-L40` — "Model doesn't reliably orient itself in workspace" — Added for Sonnet 4.5
   - `progress_notes` — "Model doesn't persist learnings across sessions" — Added for Sonnet 4.5
   - `F106 IRON LAW parser` — "Model proposes fixes without root causes" — Added for Sonnet 4.5

### Effort: Low
### Impact: Medium — prevents scaffolding debt accumulation

---

## Gap #9: Progress Notes Should Be Structured (P3)

### The Principle (KS#2 Act V)

"Structured state files. Never markdown."
"JSON breaks loudly. Markdown breaks silently."
"JSON for feature tracking -- the model is less likely to overwrite JSON than markdown."

### Current State

Core state in SQLite (good — better than JSON). But inter-agent communication uses `claude-progress.txt` (unstructured plain text). Progress notes — the primary session continuity mechanism — are vulnerable to accidental corruption or overwrite by a sub-agent.

### Proposed Fix

1. Switch `claude-progress.txt` to `claude-progress.json` with structured entries
2. Each entry: timestamp, feature_id, phase, status, notes
3. Validate JSON after each sub-agent run; restore from backup if corrupted
4. Keep the 10-entry cap; structured format makes truncation clean (pop oldest)

### Effort: Low
### Impact: Low-Medium — prevents silent progress corruption

---

## Gap #10: No Playwright-Based UI Verification (P3)

### The Principle (KS#2 Act V)

"The evaluator tests like a real user: clicking buttons, filling forms, checking visual output via Playwright screenshots. It's the difference between a developer running unit tests and a QA engineer testing the actual application."

### Current State

Puppeteer is opt-in per feature via `enable_puppeteer` flag in the spec, but:
- It's provided as an MCP tool for the implementation agent, not an evaluator
- There's no automated visual verification loop
- No screenshot comparison or visual regression testing
- For the Swedish Circle app (PyQt6 GUI), the visual testing was done manually (30 min human polish)

### Proposed Fix

This is largely subsumed by Gap #1 (Independent Evaluator). If the evaluator agent is implemented with Playwright capabilities:
1. Evaluator launches the app (web or desktop via xvfb)
2. Takes screenshots at key interaction points
3. Compares against expected behavior described in acceptance criteria
4. Reports visual regressions alongside functional test results

### Effort: Medium (additive to Gap #1 evaluator work)
### Impact: Medium for GUI projects, N/A for library/backend work

---

## Implementation Roadmap

### Phase 1 — Critical Gaps (P0)
1. **Independent Evaluator Agent** — New evaluator sub-agent type with separate prompt, no access to implementation agent's reasoning, structured pass/fail verdict
2. **Security Verification** — Add check #9 to verification pipeline: dependency audit, secrets scan, SAST basics, slopsquatting check

### Phase 2 — High-Value Improvements (P1)
3. **CLAUDE.md Generation** — Generate during init, update during run loop, installed to every sub-agent workspace
4. **Parallel Execution** — Worktree-based parallel feature implementation for independent DAG nodes
5. **Compounding Learnings** — Flow memory learnings back into project CLAUDE.md

### Phase 3 — Quality Refinements (P2)
6. **Pre-Implementation Plan Review** — Inferential guide: LLM reviews plan before coding starts
7. **Build It Twice** — Optional exploration phase with throwaway prototype
8. **Scaffolding Tagging** — Manifest tracking which scaffolding compensates for which model limitation

### Phase 4 — Polish (P3)
9. **Structured Progress Notes** — JSON instead of plain text for inter-session continuity
10. **Playwright UI Verification** — Extend evaluator with browser-based testing (depends on #1)

---

## References

- Knowledge Share #2: "The Disposable Architecture" — Yaakoub Elkhamra, April 2026
- Anthropic Engineering: "Effective Harnesses for Long-Running Agents"
- Anthropic Engineering: "Harness Design for Long-Running Application Development"
- Bockeler/martinfowler.com: "Harness Engineering" (Guides and Sensors)
- Hashimoto (HashiCorp): Agent = Model + Harness
- Osmani: "Every line in AGENTS.md should trace back to a specific failure"
- Bob3 Architecture: `docs/architecture.md`, `docs/failure_handling.md`, `docs/adversarial_review.md`
