---
name: implementing-acceptance-criteria
description: Use when starting a bob feature. Acceptance criteria are contracts your implementation must satisfy to be marked complete. This skill covers how bob verifies them and how to make each criterion concretely testable.
---

# Implementing acceptance criteria in bob

Every feature in a bob spec has an `acceptance_criteria` list. These are NOT aspirational goals — bob's enhanced verification layer parses them and evaluates each one against your implementation. If they don't pass, your feature is marked `needs_human` and the cascade of dependent features does not unlock.

## How criteria are classified

Bob reads each criterion string and routes it to one of several check families:

| Pattern in criterion | Check type | Passes when |
|---|---|---|
| `"pytest: <node-id>"` | Executable pytest | `python -m pytest <node-id>` exits 0 *and* reports a passed test |
| `"python: <expression>"` | Executable python | `python -c "<expression>"` exits 0 |
| `"File exists: <path>"` or `"<path> is created"` | File existence | The file exists in the workspace |
| `"Function <name> is defined"` or `"Class <name> exists"` | Symbol definition | AST finds the named symbol |
| `"<symbol> accepts <args>"` | Signature | AST signature matches |
| `"L2 error < <num>"`, `"matches analytical within <num>%"` | Numerical tolerance | A test asserts the numerical bound |
| `"returns value in range [<a>, <b>]"` | Range | Test asserts bounds |
| `"pytest runs X tests"` or `"N tests pass"` | Test count | `pytest --collect-only` / run output matches |
| Other phrasing | Falls through to generic check — **which now returns False by default** | — |

The generic fall-through used to soft-pass and was an exploit path. It now rejects: **if a criterion's phrasing is vague, you must make it concrete OR add a verifiable test that asserts the behavior.**

## Prefer executable criteria

Whenever a criterion can be expressed as code, use the `pytest:` or `python:`
forms. They run real subprocesses inside the feature workspace and the
verification layer trusts the exit code instead of trying to interpret
English. This is the most reliable way to make a criterion provably pass.

Examples:

- `"pytest: tests/test_bishop_benchmark.py::test_homogeneous_slope"` — runs
  exactly that pytest node id and passes only if pytest exits 0 with at
  least one collected passing test. This rules out the
  "no tests collected" silent-success failure mode.
- `"python: from mymodule import compute; assert abs(compute() - 1.37) < 0.02"`
  — runs the inline expression with `python -c`. Useful for cheap
  numerical assertions that don't deserve their own pytest file.
- `"python: import json, pathlib; data = json.loads(pathlib.Path('out.json').read_text()); assert data['ok']"`
  — quick file/sanity probes.

Operational notes:

- **Workspace is the cwd.** The executor invokes `python` with
  `cwd=<feature workspace>`, so relative paths and imports resolve against
  the workspace root, just like a user running pytest in their checkout.
- **Per-criterion timeout.** Each executable criterion is killed after
  `BOB_CRITERION_EXEC_TIMEOUT` seconds (default 60). A runaway expression
  fails the criterion with a `timed out` detail string instead of hanging
  the whole verification pipeline.
- **Failure surfaces details.** When an executable criterion fails, the
  validator records the exit code plus the tail of stdout/stderr in the
  evidence so the next agent can debug without re-running anything.
- **No `shell=True`.** Both helpers invoke `python` via an explicit argv
  list. Don't wrap your criterion in shell pipes — express what you need
  directly in the python or pytest expression.
- **`python:` is for SIMPLE assertions only.** The form is intended for
  one-line numerical or sanity checks (`assert abs(compute() - 1.37) <
  0.02`, `assert json.dumps({"a":1}) == '{"a": 1}'`). Anything more
  complex — multi-step setup, file I/O, networking, subprocess, dynamic
  imports — belongs in a real test file invoked via `pytest:`. The
  allowlist below is deliberately strict so that writing complex logic
  inline is uncomfortable on purpose; rewriting as `pytest:` is the
  intended fix.
- **`python:` has an import/operation allowlist.** Because `python: <expr>`
  runs arbitrary Python in the workspace, the AST of the expression is
  scanned before execution and refused if it uses any banned operation.
  Banned categories (current as of the F124 hardening pass):
    - **Banned modules** (top-level imports and `from <mod> import ...`):
      `subprocess`, `socket`, `urllib`, `http`, `requests`, `ftplib`,
      `telnetlib`, `smtplib`, `shutil`, `ctypes`, `multiprocessing`,
      `pty`, `pickle`, `marshal`, `importlib`, `runpy`, `pkgutil`,
      `builtins`. `importlib`/`runpy`/`pkgutil` close the dynamic-import
      escape (e.g. `importlib.import_module("os")`); `builtins` closes
      the `import builtins; builtins.open(...)` / `builtins.__import__(...)`
      bypass.
    - **Banned call names** (refused regardless of argument values):
      `eval`, `exec`, `compile`, `__import__`, `getattr`, `setattr`,
      `delattr`, `globals`, `locals`, `vars`, `open`. `getattr`/`setattr`
      are banned even with constant args because the attacker can
      construct any string at runtime; `globals`/`locals`/`vars` return
      mutable namespaces. **`open` is banned outright** — both write
      modes (which can rewrite arbitrary files) and read modes (which
      can leak secrets via paths like `/proc/self/environ`,
      `/etc/passwd`, `~/.ssh/id_*`). If your criterion needs filesystem
      access, use `pytest:` and let pytest's `tmp_path` fixture give you
      an isolated workspace.
    - **Banned attribute names** (refused on access, with or without a
      call): `system`, `popen`, `spawn*`, `exec*`, `remove`, `unlink`,
      `rmdir`, `removedirs`, `rmtree`, `environ`, `putenv`, `chmod`,
      `chown`, `kill`, `killpg`, `fork`, `forkpty`, plus the dunder
      escape-path attributes `__class__`, `__bases__`, `__subclasses__`,
      `__mro__`, `mro`, `__dict__`, `__globals__`, `__builtins__`,
      `__init_subclass__`, `__getattribute__`, `__getattr__`. The dunder
      set blocks the classic
      `().__class__.__bases__[0].__subclasses__()` sandbox-escape walk.
      The same matcher refuses `obj.open(...)` and `builtins.open(...)`
      via the banned-call-name set (`open` is in both lists, by intent).
  Refusal reports `"Refused: criterion uses banned operation '<op>'"`.

### Why this is restricted

The allowlist is **not a sandbox**. Python sandboxing is fundamentally
unsolved — given enough effort, an expression can probably escape any
ban set we install. The goal is much narrower: **prevent a single
careless or malicious line from doing damage with no effort at all**.
Concretely, this layer exists to:

1. **Stop trivially exploitable specs.** A spec author who writes
   `python: import os; os.system("rm -rf ~")` should be refused before
   the subprocess runs, not after.
2. **Make footguns visible.** If your criterion needs `subprocess` or
   `urllib`, that's a strong signal you should be using `pytest:` with
   a real test file that has setup/teardown and a clear failure mode.
3. **Force the right form for the job.** `python:` is for one-line
   assertions; `pytest:` is for everything else. The allowlist nudges
   spec authors toward the form that matches their use case.

If a benign criterion is rejected, **rewrite it as a `pytest:` node**
pointing at a small `tests/test_criterion.py`. That is the documented
escape hatch and is almost always cleaner anyway — pytest gives you
fixtures, isolation, and clear failure reporting that an inline
expression cannot.

## How to write criteria-driven code

1. **Read every criterion before writing any code.** Each one is a testable claim you must satisfy.

2. **For each criterion, decide how it's verified.** Possible mechanisms:
   - The criterion names a file → create the file with real content
   - The criterion names a function → implement the function with correct behavior
   - The criterion states a numerical bound → write a test that asserts the bound and make it pass
   - The criterion is vague → **rewrite it or make a concrete test for it**. Do not leave it vague.

3. **Write the test FIRST for criteria with measurable outcomes.** See `test-driven-development` skill. The test encodes your interpretation of the criterion.

4. **Implement until the test passes.** Not "until it looks right."

5. **Run the full test suite.** If a new test passes but an existing test now fails, you've regressed something — fix it before declaring done.

## Example: turning a criterion into code

**Spec criterion:** `"Bishop Simplified FoS within 2% of published value (1.37)"`

Bad: write a Bishop solver, run it, eyeball that the answer "looks close," declare done.

Good:

```python
# tests/test_bishop_benchmark.py
def test_bishop_simplified_homogeneous_slope_abramson():
    """Abramson et al. homogeneous slope, H=10m, 2H:1V, c=20kPa, phi=20deg."""
    slope = build_abramson_slope()
    fos = bishop_simplified(slope, search="grid")
    published_fos = 1.37
    rel_err = abs(fos - published_fos) / published_fos
    assert rel_err < 0.02, f"FoS {fos:.3f} vs published {published_fos}: {rel_err*100:.1f}% error"
```

The test encodes the criterion as a numerical assertion. Your implementation must make it pass. If it passes, the criterion passes. If you fake the Bishop solver to return 1.37 just to make the test green, the `no-stubs-no-mocks` skill (and the AST stub detector) will catch you.

## What to do with ambiguous criteria

Spec criteria sometimes arrive vague: *"Implementation is correct"*, *"Code is clean"*, *"Handles edge cases"*. These are not verifiable as written.

Your options, in order of preference:

1. **Decompose into specific criteria.** Replace *"Handles edge cases"* with specific cases you identified: *"Returns None when input is empty"*, *"Raises ValueError on negative depth"*, etc. Write a test for each.

2. **Record the interpretation in memory.** If you're pinning down what "correct" means based on the spec description and your domain knowledge, `memory_add` a lesson explaining the interpretation so future agents see the same reading.

3. **Flag it back through bob's feature-refinement mechanism.** If a criterion is truly unverifiable and you can't disambiguate, do not fake-pass it — mark the feature for refinement.

## The enhanced verification layer

Bob's `enhanced_verification.py` runs alongside the structural checks (files exist, no stubs, test files present). It extracts the acceptance criteria from the feature row and runs each through `_check_criterion`. Results become evidence artifacts stored in the DB.

**Your deliverable is the set of criteria, made real.** Everything else is scaffolding.

## Before declaring done

For each criterion in the feature:
- [ ] I have a test that encodes this criterion
- [ ] The test fails without my implementation
- [ ] The test passes with my implementation
- [ ] The test asserts the actual requirement, not something easier to check
- [ ] My implementation is real (not a stub returning the expected value)

If any box is unchecked, you're not done.
