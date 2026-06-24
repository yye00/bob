---
name: checking-review-registry
description: Use before reporting any code-review finding. Bob maintains a persistent registry of every adversarial-review finding at reviews/findings.yaml. Search it before flagging an issue to (1) avoid duplicate reports, (2) detect recurring patterns, (3) link related findings.
---

# Checking the review registry

Bob keeps a structured, version-controlled record of every adversarial-review finding at `reviews/findings.yaml`. Before you flag a new issue, search the registry. After you confirm something is genuinely new, contribute back.

> **Note: skills are bob-managed.** Every skill under `<workspace>/.claude/skills/` whose name matches a bundled bob skill is owned by bob — the orchestrator audits these symlinks before each sub-agent spawn (`bob.skills_installer.verify_skills_integrity`) and will force-replace any entry that has been turned into a real directory or repointed to a path outside the current bob install. User customizations should use **unique skill names** that do not collide with bundled skill names; otherwise they will be wiped on the next sub-agent spawn.

## When to consult

- **Before writing a new finding.** Search by file path, tag, or keyword. Was this exact bug already reported? Has a related anti-pattern been seen elsewhere?
- **When you observe a recurring theme.** If you find a `broad-except-swallow` issue, the registry's `recurring_patterns` section will tell you this is the third such instance — that's a stronger signal than reporting it as a one-off.
- **When deciding severity.** A pattern that has recurred N times deserves higher severity than one seen once.

## How to search

The registry is `reviews/findings.yaml`. The Python module `bob.reviews` provides programmatic access:

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

You can also `grep` the YAML file directly:

```bash
grep -i "subprocess" reviews/findings.yaml
grep -A 2 "tag: signal-safety" reviews/findings.yaml
```

## Existing taxonomy

The registry has 8+ recurring-pattern tags worth checking:

| Tag | What it captures |
|---|---|
| `refactor-debt` | Stale call sites or strings after a renaming/restructuring refactor |
| `non-atomic-counter` | Two trackings of the same value drifting out of sync |
| `allowlist-gap` | Sandbox built from ban-list with bypassable holes |
| `broad-except-swallow` | `except Exception:` + permissive default hiding bugs |
| `state-machine-ordering` | Multi-step state transition writes success state before validation |
| `subprocess-pitfalls` | timeout + PIPE issues, grandchild leaks, deadlocks |
| `signal-safety` | POSIX signal handler doing non-reentrant I/O |
| `dead-code-tested-path` | Tests verify a code path production never executes |

When you encounter what looks like a new finding, ask: **does it match any of these tags?** If yes, link it via `related:` and use the same tag.

## When you find something new

1. Verify it's genuinely new by searching the registry
2. Verify it's a real bug (high confidence — the registry only accepts findings reviewers stand behind)
3. Add it via the registry module:

```python
from bob.reviews import load_registry, add_finding, save_registry

reg = load_registry()
new_finding = add_finding(
    reg,
    round_prefix="R4",
    title="Short, factual title",
    pattern="One-line characterization of the anti-pattern",
    files=["src/bob/some_module.py"],
    severity="high",  # critical / high / medium / low
    status="open",
    tags=["existing-tag-from-recurring-patterns", "new-specific-tag"],
    related=["R2-020"],  # IDs of related prior findings
    notes="What's broken, what should happen instead, why it matters.",
)
save_registry(reg)
```

The function auto-assigns the next sequential ID for the round.

## When fixing a finding

After you fix an issue, mark it fixed in the registry:

```python
from bob.reviews import load_registry, mark_fixed, save_registry

reg = load_registry()
mark_fixed(reg, "R3-007", commit="<sha>")
save_registry(reg)
```

Include the fix commit so future archaeologists can see the diff.

## Promoting a recurring pattern

If a tag now has 2+ findings, consider adding a `recurring_patterns` entry to `findings.yaml`. The summary should explain (a) what the anti-pattern is and (b) what defense lets you avoid it next time.

## Why this matters

Bugs cluster. The same architectural mistake gets reintroduced after a refactor, or the same anti-pattern shows up in three modules because the engineer copy-pasted. The registry surfaces these clusters explicitly — not as a backlog, but as a *radar* for what to look at first when reviewing new code.

A reviewer who consults the registry can:
- Catch a `broad-except-swallow` recurrence in 30 seconds (search by tag, see the existing 3 instances, find the 4th)
- Avoid wasting cycles on a finding the last reviewer already filed
- Detect that a "fixed" issue actually came back in a different form
