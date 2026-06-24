# Adversarial review — bob's red-team loop

Most build orchestrators trust their sub-agents. When a sub-agent
says "done", the orchestrator runs whatever tests the spec asked
for, and if those pass, it ships. That's a thin defense: agents
optimise for "make the verifier happy", not for "produce correct
code".

Bob has a **second** defense — adversarial review — that runs
*before* the verification checklist, *finds bugs the verifier
wouldn't*, and *accumulates them across runs* so the same class of
bug doesn't recur on the next spec. This doc walks the full loop.

> All code references are to files in this repo unless noted.

---

## The four moving parts

```
┌─────────────────────────────────────────────────────────┐
│  Skill: adversarial-self-review                         │
│    → applied by every sub-agent before it claims done   │
│    → finds bugs by red-teaming its own diff             │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  reviews/findings.yaml                                  │
│    → version-controlled bug registry, R<round>-<n> ids  │
│    → tagged by recurring pattern, severity, status      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  RecurringPattern detection                             │
│    → tags that fire N times across rounds get aggregated│
│    → high N raises severity for the next instance       │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Skill: checking-review-registry                        │
│    → applied by every sub-agent BEFORE writing code     │
│    → "has this bug been reported here before?"          │
│    → past findings inform new implementation choices    │
└─────────────────────────────────────────────────────────┘
```

The output of one stage feeds the input of the next; the system
gets sharper with each spec it builds.

---

## 1. The adversarial-self-review skill

Source: [`src/bob/skills/adversarial-self-review/SKILL.md`](../src/bob/skills/adversarial-self-review/SKILL.md).

This skill is auto-installed into every sub-agent's workspace at
spawn time (see [the skills system](architecture.md#skills) below)
and the agent is instructed to apply it **before declaring a feature
complete**. The skill switches the agent's mode from "make it work"
to "how would I exploit this".

### The mindset shift

The skill prompt asks the agent to pretend to be a hostile reviewer:

> Pretend you are a hostile reviewer who:
> - Suspects you cheated
> - Knows every acceptance criterion you had
> - Has a stake in finding fault
> - Will get credit for every real bug they find

That framing matters. "Did I implement this correctly?" produces
weak self-checks. "How would I cheat my way past this verifier?"
produces real ones.

### The checklist

The skill walks through six classes of bug:

1. **Pattern-matching to make tests green** — would I arrive at
   the same code if I deleted my implementation and re-derived from
   the criteria? Or did I work backwards from "what makes the test
   pass"? The latter means the test is testing the implementation,
   not the requirement.

2. **Test–implementation coupling** — would my tests still pass if
   someone else reimplemented this correctly but differently
   (different control flow, same observable behavior)? If they
   inspect internal state or mock internals, they're coupled.

3. **Edge cases I didn't write tests for** — empty, None, zero,
   negative, NaN, Inf, very-large, malformed. Does the code behave
   sensibly or blow up with a confusing error?

4. **Bug-hiding `try/except`** — for each `except` in the diff:
   am I catching `Exception` broadly? Logging at DEBUG and
   returning a default? Could this mask a real bug?

5. **Concurrency / ordering bugs** — read-modify-write on shared
   state, SELECT-then-UPDATE without a transaction, TOCTOU races,
   dependence on `os.listdir` order, dict iteration order.

6. **Verifier-gaming** — could a hostile implementation pass the
   bob verifier without solving the problem? `touch` files to
   bump mtime; write one `pass`-equivalent that escapes the AST
   stub detector; hardcode return values to satisfy assertions.

The skill explicitly closes with "if you find a real bug, fix it
before you declare done" — not "file it and move on". The point
is to *prevent* the verifier from having to catch it.

### What this catches that the verifier doesn't

The verifier is mechanical: AST checks, pytest exit codes,
acceptance-criterion evaluators. It cannot see semantic intent.
Adversarial review catches:

- Tests that pass on every implementation (`assert True`-style
  assertions, mock-and-assert-call-count patterns)
- Hardcoded return values that satisfy criteria without computing
- Edge cases the spec didn't think to require but that should
  obviously be handled
- Try/except blocks swallowing the very bug the test was meant to
  catch
- Implementation–test coupling (a refactor would break the tests
  for non-real reasons)
- Verifier gaming (rare in practice, but the skill names it
  explicitly so the agent doesn't drift into it)

These are all cases where "tests pass" is technically true but
"code is correct" is false. The skill is the gap-closer.

---

## 2. The findings registry

Source: [`reviews/findings.yaml`](../reviews/findings.yaml) +
[`src/bob/reviews.py`](../src/bob/reviews.py).

Every finding gets a structured row in the registry:

```yaml
- id: R10-014
  title: handle_execution_result skips verification on is_error=True
  pattern: dead-code-tested-path
  files:
    - src/bob/orchestrator/run_loop.py
  severity: critical
  status: fixed
  tags:
    - dead-code-tested-path
    - false-negative
  fixed_in: pending-r10-014-verify-on-error
  fixed_at: '2026-05-02'
  notes: 'A sub-agent that wrote correct files but errored on its
    last turn was being marked needs_human despite the work being
    on disk. Fix: run the verification checklist on every termination
    path, not only on success.'
```

Field-by-field:

| Field | Purpose |
|---|---|
| `id` | `R<round>-<n>`, where round is a sequential review pass |
| `title` | One-line summary |
| `pattern` | Free-text root-cause class |
| `files` | Source files implicated |
| `severity` | `low` / `medium` / `high` / `critical` |
| `status` | `open` / `fixed` / `wontfix` |
| `tags` | Standardised pattern tags (see [taxonomy](#standard-tags)) |
| `fixed_in` | Branch / commit reference |
| `fixed_at` | ISO date |
| `related` | Other finding ids this one is connected to |
| `notes` | Reproducer + fix description |

The registry is **version-controlled** — every change to
`findings.yaml` is a real diff in git, so the history of reviews
is itself reviewable.

### Filing a finding

Programmatic API in `bob.reviews`:

```python
from bob.reviews import (
    load_registry, save_registry, add_finding, mark_fixed,
)

reg = load_registry()
reg = add_finding(
    reg,
    title="Cost counter is non-atomic across worker callbacks",
    pattern="non-atomic-counter",
    files=["src/bob/orchestrator/run_loop.py"],
    severity="high",
    tags=["non-atomic-counter", "race"],
    notes=(
        "Three concurrent callbacks each read self.total_cost, "
        "compute total + delta, and write back. Last writer wins; "
        "intermediate increments are lost. Use _increment_cost as "
        "the canonical writer instead."
    ),
)
save_registry(reg)
```

The `id` is auto-assigned by `next_finding_id(reg, "R10")`.

Sub-agents file findings the same way; they're given the snippet
above as part of the adversarial-self-review skill prompt.

---

## 3. RecurringPattern detection

Source: [`src/bob/reviews.py`](../src/bob/reviews.py) — the
`RecurringPattern` dataclass and the `recurring_patterns:` block
at the bottom of `findings.yaml`.

When the same `tag` shows up across multiple findings, it gets
aggregated:

```yaml
recurring_patterns:
  - tag: doc-drift
    occurrences:
      - R3-011
      - R4-001
      - R4-003
      - R4-004
      ...
    summary: 'User-facing docs (README, CLI error messages) keep
      falling out of sync with code: missing prerequisites,
      missing env vars, capability claims that no code path
      implements...'
```

The signal: a one-off `doc-drift` finding is a paper cut; sixteen
of them across four review rounds is **structural** — the project
needs a doc-test or a CI check that grep's for capability claims
in the README and verifies a code path exists. The recurring
pattern moves the conversation from "fix this finding" to "fix the
class of finding".

### Standard tags

Tags are not a closed set, but the skill encourages reusing the
existing taxonomy where it fits. Common tags from the registry:

- `non-atomic-counter` — read-modify-write on a shared counter
- `broad-except-swallow` — bare `except` hiding real exceptions
- `dead-code-tested-path` — code with passing tests but no production caller
- `allowlist-gap` — security check that misses a category of input
- `signal-safety` — non-async-signal-safe work in a signal handler
- `tunable-defaults` — a fixed-default tunable that doesn't fit the workload
- `false-negative` — verifier rejects valid work
- `regression` — a fix that broke a previously-working path
- `doc-drift` — README / docstring claims a behavior the code doesn't have
- `setup-friction` — fresh-clone setup keeps breaking
- `refactor-debt` — old names persisting after a rename

When you file a finding with a tag that has an existing
`recurring_patterns` entry, the skill instructs you to:

1. Add your finding's id to that pattern's `occurrences` list.
2. Update the summary if your case shifts the pattern's shape.

The CLI's `bob show-reviews --tag <tag>` surfaces the full
occurrence list and the summary so you can see the pattern at a
glance.

---

## 4. The checking-review-registry skill

Source:
[`src/bob/skills/checking-review-registry/SKILL.md`](../src/bob/skills/checking-review-registry/SKILL.md).

This is the *other* half of the loop. Where adversarial-self-review
runs *post*-implementation to find new bugs, checking-review-registry
runs *pre*-implementation to learn from old ones.

The skill instructs the sub-agent to consult the registry **before
writing any new code in a file** the registry already has findings
on:

```python
from bob.reviews import load_registry

reg = load_registry()

# By file path (substring match)
reg.search(files_glob="orchestrator/run_loop.py")

# By tag
reg.search(tag="allowlist-gap")

# By keyword in title/pattern/notes
reg.search(query="cascade")

# Combine: open critical issues in a file
reg.search(status="open", severity="critical", files_glob="cli.py")

# Look up a known recurring pattern
reg.patterns_for_tag("non-atomic-counter")
```

Or via shell:

```bash
grep -i "subprocess" reviews/findings.yaml
grep -A 2 "tag: signal-safety" reviews/findings.yaml
bob show-reviews --tag signal-safety --status open
```

When the registry returns findings on the file the agent is about
to modify, the agent is expected to *read them* — and avoid
recreating those exact bugs. This is the most underrated piece
of the loop: most "lessons learned" systems don't get queried at
the moment they'd be useful. Bob's skills system makes querying
the default behavior.

---

## 5. The CLI surface — `bob show-reviews`

Source: [`src/bob/cli.py:1723`](../src/bob/cli.py).

```bash
bob show-reviews                    # full registry
bob show-reviews --summary          # status + severity counts
bob show-reviews --status open      # only open findings
bob show-reviews --severity critical
bob show-reviews --tag non-atomic-counter
bob show-reviews --file-glob 'orchestrator/*.py'
bob show-reviews --query "cascade"
```

Filters compose. The output is human-readable text intended for
operators triaging a build. Sub-agents call this same command via
Bash to surface relevant findings into their context window.

---

## 6. The full loop in action

Concrete example from the swedish-circle build (see
[`swedish_circle_example.md`](swedish_circle_example.md)):

1. Sub-agent implements F010 (Abramson V&V tests).
2. **Pre-impl**: skill runs `reg.search(files_glob="tests/test_vv_*.py")` —
   no prior findings, proceeds.
3. **Implementation**: writes `tests/test_vv_abramson.py`. Tests pass
   on first run.
4. **Post-impl**: adversarial-self-review skill runs the six-point
   checklist. Catches nothing — the tests assert on numerical
   relationships that any correct implementation must satisfy
   (Bishop FoS within 2% of 1.37, Fellenius < Bishop by 5–15%).
5. Verifier passes; feature marked completed.

Compare with F012 / F006 / F008 where adversarial review *should*
have caught issues but didn't — the swedish-circle case study's
"Post-build polish" section documents these honestly. The skill
instructions had a verifier-gaming bullet, but the reviewer didn't
exercise it on the GUI io path. That gap is now part of the skill's
own evidence that the checklist needs strengthening on the
`fictional-attribute-name` pattern. (Filed as a future improvement;
not in the registry yet because it needs more occurrences.)

---

## 7. How adversarial review interacts with the rest of bob

- **Failure handling** ([`failure_handling.md`](failure_handling.md)):
  the RCA agent's `blame_target` taxonomy overlaps with adversarial
  tags. RCA findings can be promoted into the registry when they
  identify a recurring pattern.
- **Skills system**: adversarial-self-review and
  checking-review-registry are two of nine bundled skills, both
  installed automatically into every sub-agent workspace.
- **Memory** (`bob.memory`): findings filed during a run can
  also be added to the `lessons` pool so semantic-search recall
  surfaces them in future sessions, not just text-search of the
  YAML.
- **Verification checklist**: the verifier and adversarial review
  are *complementary*. The verifier is fast, mechanical, and
  catches a fixed set of patterns. Adversarial review is slow,
  semantic, and catches everything else — including bugs in the
  verifier itself (R10-014, R10-018, R10-021 were all
  verifier-correctness findings).

---

## 8. Operating tips

- **Run `bob show-reviews --summary` periodically.** A growing
  count of `open critical` findings is a smell: the recovery
  loop is shedding bugs faster than they're being fixed.
- **Promote a recurring pattern to a structural fix when N ≥ 3.**
  Three instances of `non-atomic-counter` is the signal to delete
  the un-protected counter altogether (which is what R6 did with
  `self.total_cost`).
- **Keep findings small and focused.** "F009 doesn't work" is not
  a finding; "F009's confidence assessor reads the latest
  `evidence_artifacts` row but doesn't filter by current attempt,
  so it picks up evidence from the previous failure" is.
- **Tag aggressively.** Every finding should have at least one
  reusable tag, even if it's the only occurrence so far. Tags are
  cheap; without them, recurring-pattern detection can't fire.
