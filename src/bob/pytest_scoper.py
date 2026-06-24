"""Per-feature pytest scoping (F-R6-301).

The enhanced-verification pytest snapshot in earlier rounds always ran the
entire test suite (200+ files) for every feature, blowing past even 1800 s
timeouts. Most features only touch a handful of source files, so we can
instead run just the tests that exercise those files (plus their transitive
importers) and fall back to the full suite when scoping is unsafe.

The scoping algorithm is intentionally simple and dependency-free:

1. Compute the set of changed source modules from the diff.
2. Walk the *importer* graph up to ``max_depth`` levels (modules that
   ``from bob.foo import …`` or ``import bob.foo``).
3. For each module in the closure, find tests under ``tests/`` that mention
   the module (import or string reference).
4. Apply safety fallbacks:
   * Critical-path changes (orchestrator/, superpowers.py,
     enhanced_verification.py, evaluator.py) → return ``None`` so the caller
     runs the full suite.
   * Fewer than 3 test files discovered → return ``None`` (likely an
     indexing miss; better to run the full suite than to silently skip
     coverage).

The public entry point is :func:`scope_tests_for_diff`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

# Files / directories whose changes always trigger a full pytest run. The
# verifier itself, the orchestrator loop, and the evaluator agent touch
# nearly every other module transitively; trying to scope tests for them
# would either run almost the whole suite anyway or, worse, miss coverage.
_CRITICAL_PATH_BASENAMES = frozenset({
    "superpowers.py",
    "enhanced_verification.py",
    "evaluator.py",
})
_CRITICAL_PATH_DIR_PARTS = (
    ("src", "bob", "orchestrator"),
)


def _is_critical_path(rel_path: str) -> bool:
    """Return True if a change to ``rel_path`` should force the full suite."""
    parts = tuple(Path(rel_path).parts)
    # Directory match — any file under src/bob/orchestrator/...
    for crit_dir in _CRITICAL_PATH_DIR_PARTS:
        if len(parts) >= len(crit_dir) and parts[: len(crit_dir)] == crit_dir:
            return True
    # Basename match — superpowers/enhanced_verification/evaluator anywhere
    # under src/bob/.
    if (
        len(parts) >= 3
        and parts[0] == "src"
        and parts[1] == "bob"
        and parts[-1] in _CRITICAL_PATH_BASENAMES
    ):
        return True
    return False


def _module_for_source(rel_path: str) -> str | None:
    """Convert ``src/bob/foo.py`` → ``bob.foo``.

    Returns ``None`` for paths outside ``src/bob/`` or non-Python files.
    """
    p = Path(rel_path)
    parts = p.parts
    if len(parts) < 3 or parts[0] != "src" or parts[1] != "bob":
        return None
    if p.suffix != ".py":
        return None
    # Strip "src/" prefix and ".py" suffix, join with dots.
    mod_parts = list(parts[1:])  # drop "src"
    last = mod_parts[-1]
    if last == "__init__.py":
        mod_parts = mod_parts[:-1]
    else:
        mod_parts[-1] = last[:-3]  # strip .py
    if not mod_parts:
        return None
    return ".".join(mod_parts)


def _all_source_files(src_root: Path) -> list[Path]:
    """Enumerate every ``.py`` file under ``src/bob/`` (recursive)."""
    if not src_root.is_dir():
        return []
    return sorted(src_root.rglob("*.py"))


def _all_test_files(tests_root: Path) -> list[Path]:
    """Enumerate every ``test_*.py`` file under ``tests/`` (recursive)."""
    if not tests_root.is_dir():
        return []
    return sorted(tests_root.rglob("test_*.py"))


def _importers_of(
    module: str,
    src_files: list[Path],
    src_root: Path,
) -> set[str]:
    """Return modules under ``src/bob/`` whose source mentions ``module``.

    We string-match both ``from bob.foo`` and ``import bob.foo`` so that
    aliasing (``import bob.foo as f``) and submodule imports
    (``from bob.foo.bar import …``) are both detected. The patterns are
    word-bounded on the right so ``bob.foo`` does not match ``bob.foobar``.
    """
    # Word-boundary on the right: next char must not be a name char.
    # Allow . (submodule) and space/newline/( etc. as terminators.
    pat = re.compile(
        r"(?:^|\s)(?:from|import)\s+" + re.escape(module) + r"(?![A-Za-z0-9_])",
        re.MULTILINE,
    )
    found: set[str] = set()
    for path in src_files:
        rel = path.relative_to(src_root.parent.parent).as_posix()  # repo-rel
        importer_mod = _module_for_source(rel)
        if importer_mod is None or importer_mod == module:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pat.search(text):
            found.add(importer_mod)
    return found


def _transitive_importer_closure(
    seed_modules: Iterable[str],
    src_files: list[Path],
    src_root: Path,
    max_depth: int,
) -> set[str]:
    """Compute the transitive set of modules that import any seed module."""
    closure: set[str] = set(seed_modules)
    frontier: set[str] = set(seed_modules)
    depth = 0
    while frontier and depth < max_depth:
        next_frontier: set[str] = set()
        for mod in frontier:
            for importer in _importers_of(mod, src_files, src_root):
                if importer not in closure:
                    closure.add(importer)
                    next_frontier.add(importer)
        frontier = next_frontier
        depth += 1
    return closure


def _tests_mentioning(
    modules: Iterable[str],
    test_files: list[Path],
) -> set[str]:
    """Return test files (repo-relative posix paths) that mention any module.

    A "mention" is any occurrence of the dotted module name in the test
    source. This catches both ``from bob.foo import …`` and
    ``import bob.foo`` plus indirect references (string node-ids,
    docstrings) which usually still indicate the test exercises that
    module.
    """
    mods = list(modules)
    if not mods:
        return set()
    # Build one big alternation, word-bounded on the right.
    pat = re.compile(
        r"(?:" + "|".join(re.escape(m) for m in mods) + r")(?![A-Za-z0-9_])"
    )
    hits: set[str] = set()
    for path in test_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pat.search(text):
            # Use parts after the tests/ root for a stable repo-relative key.
            hits.add(path.as_posix())
    return hits


def scope_tests_for_diff(
    changed_files: list[str],
    repo_root: Path,
    max_depth: int = 5,
) -> list[str] | None:
    """Compute the set of pytest files relevant to ``changed_files``.

    Args:
        changed_files: Repo-relative paths (e.g. ``"src/bob/foo.py"``)
            of files changed in the current diff.
        repo_root: Filesystem path to the repository root (the directory
            containing ``src/`` and ``tests/``).
        max_depth: Maximum BFS depth for the transitive importer closure.
            Defaults to 5 to bound runaway expansion.

    Returns:
        A sorted list of test file paths (repo-relative posix form) that
        should be run for this diff, or ``None`` when the caller should
        fall back to the full pytest suite. ``None`` is returned when:

        * Any changed file is on the critical path (orchestrator/,
          superpowers.py, enhanced_verification.py, evaluator.py).
        * Fewer than 3 test files are discovered (likely an indexing miss).
        * ``repo_root`` does not contain ``src/bob/`` or ``tests/``.
    """
    repo_root = Path(repo_root)
    src_root = repo_root / "src" / "bob"
    tests_root = repo_root / "tests"
    if not src_root.is_dir() or not tests_root.is_dir():
        return None

    # Critical-path bail-out — even a single such change forces the full
    # suite, before we do any further work.
    for rel in changed_files:
        if _is_critical_path(rel):
            return None

    # Map changed source files → seed modules. Files outside src/bob/
    # (docs, configs, tests themselves) are ignored at seeding time —
    # tests that change are picked up directly below.
    seed_modules: set[str] = set()
    for rel in changed_files:
        mod = _module_for_source(rel)
        if mod is not None:
            seed_modules.add(mod)

    src_files = _all_source_files(src_root)
    test_files = _all_test_files(tests_root)

    closure = _transitive_importer_closure(
        seed_modules, src_files, src_root, max_depth=max_depth
    )

    selected_tests = _tests_mentioning(closure, test_files)

    # If a test file itself was changed, always include it. Use the
    # repo-relative posix form so it matches the keys we already produce.
    for rel in changed_files:
        p = Path(rel)
        if (
            len(p.parts) >= 1
            and p.parts[0] == "tests"
            and p.suffix == ".py"
            and p.name.startswith("test_")
        ):
            abs_path = repo_root / p
            if abs_path.is_file():
                selected_tests.add(abs_path.as_posix())

    if len(selected_tests) < 3:
        # Likely an indexing miss (e.g. a new module nobody imports yet,
        # or a docs-only diff). The caller should run the full suite so
        # we don't silently skip coverage.
        return None

    return sorted(selected_tests)


def derive_scope_for_feature(
    acceptance_criteria: list[str],
    repo_root: Path,
    max_depth: int = 5,
) -> list[str] | None:
    """Derive the pytest scope for a feature from its acceptance criteria.

    This is the acceptance-criteria-oriented counterpart to
    :func:`scope_tests_for_diff`. Instead of a list of changed files from a
    diff, it takes the feature's acceptance criteria and extracts seed modules
    by parsing ``pytest:``, ``File exists:``, ``Function defined:``, and
    ``integration:`` criterion forms.

    The derived seed modules are passed through the same transitive importer
    closure and test-file selection logic as :func:`scope_tests_for_diff`, so
    the safety fallbacks (critical-path bail-out, fewer-than-3-tests guard)
    apply identically.

    Args:
        acceptance_criteria: List of criterion strings as stored in the
            feature record, e.g.
            ``["File exists: src/bob/foo.py",
               "Function defined: bob.foo.bar",
               "pytest: tests/test_foo.py"]``.
        repo_root: Filesystem path to the repository root (the directory
            containing ``src/`` and ``tests/``).
        max_depth: Maximum BFS depth for the transitive importer closure.

    Returns:
        A sorted list of test file paths (repo-relative posix form) to run,
        or ``None`` when the caller should fall back to the full suite.
    """
    repo_root = Path(repo_root)
    src_root = repo_root / "src" / "bob"
    tests_root = repo_root / "tests"
    if not src_root.is_dir() or not tests_root.is_dir():
        return None

    seed_modules: set[str] = set()
    explicit_tests: set[str] = set()

    for criterion in acceptance_criteria:
        stripped = criterion.strip()
        lower = stripped.lower()

        # pytest: tests/test_foo.py  or  pytest: tests/test_foo.py::test_bar
        if lower.startswith("pytest:"):
            expr = stripped[len("pytest:"):].strip()
            # Extract just the file portion (before ::)
            test_path = expr.split("::")[0].strip()
            abs_test = repo_root / test_path
            if abs_test.is_file():
                explicit_tests.add(abs_test.as_posix())
            # Also seed from the module the test references (filename heuristic)
            p = Path(test_path)
            if p.name.startswith("test_") and p.suffix == ".py":
                # test_foo_bar.py → try bob.foo_bar as seed
                mod_guess = "bob." + p.stem[len("test_"):]
                seed_modules.add(mod_guess)
            continue

        # File exists: src/bob/foo.py
        match = re.search(r"file exists?:\s*(.+)", stripped, re.IGNORECASE)
        if match:
            rel = match.group(1).strip()
            mod = _module_for_source(rel)
            if mod is not None:
                seed_modules.add(mod)
            continue

        # Function defined: bob.foo.bar  or  bob.foo.ClassName
        match = re.search(r"function defined:\s*(.+)", stripped, re.IGNORECASE)
        if match:
            dotted = match.group(1).strip()
            # Module is everything up to the last component
            parts = dotted.rsplit(".", 1)
            if len(parts) == 2:
                seed_modules.add(parts[0])
            continue

        # integration: bob.some_module
        match = re.search(r"integration:\s*(.+)", stripped, re.IGNORECASE)
        if match:
            target = match.group(1).strip()
            seed_modules.add(target)
            continue

    # Filter out critical-path seeds to avoid triggering the bail-out
    # on the seed itself (the changed-files bail-out already handles that
    # for diff-based calls; here we only want the explicit-test inclusion
    # path, not a full-suite mandate, for criteria pointing at critical modules).
    non_critical_seeds = {
        m for m in seed_modules
        if not _is_critical_path(
            "src/" + m.replace(".", "/") + ".py"
        )
    }

    src_files = _all_source_files(src_root)
    test_files = _all_test_files(tests_root)

    closure = _transitive_importer_closure(
        non_critical_seeds, src_files, src_root, max_depth=max_depth
    )

    selected_tests: set[str] = _tests_mentioning(closure, test_files)
    selected_tests |= explicit_tests

    if len(selected_tests) < 3:
        return None

    return sorted(selected_tests)
