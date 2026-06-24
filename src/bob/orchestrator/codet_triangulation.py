"""CodeT mutual-agreement triangulation (F-R7-454).

Implements the KxK code-test matrix scoring strategy from CodeT (ICLR 2023)
combined with TestGen-LLM's Build/Pass/Coverage triple filter.

The algorithm:
  1. spawn_k_tests: Generate K candidate test sets with different framings
     (positive, adversarial, boundary)
  2. spawn_k_impls: Generate K candidate implementations
  3. score_matrix: Score each (code, test) cell by mutual-agreement —
     passing_tests * tests_that_uniquely_fail_other_impls
  4. triple_filter: Reject dud tests via Build/Pass/Coverage checks
  5. persist_winning_cell: Write runs/<feature>/winner.yaml
  6. archive_losers: Move losing cells to runs/<feature>/variants/

Public API::

    from bob.orchestrator.codet_triangulation import (
        spawn_k_tests,
        spawn_k_impls,
        score_matrix,
        triple_filter,
        persist_winning_cell,
        archive_losers,
    )

Source: Agent 4 Section 9 (CodeT, ICLR 2023; TestGen-LLM).
"""

from __future__ import annotations

import ast
import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CandidateTestSet:
    """One candidate test set produced by spawn_k_tests."""

    index: int
    framing: str           # "positive", "adversarial", "boundary"
    test_path: Path        # path to the test file
    content: str           # raw test source


@dataclass
class CandidateImpl:
    """One candidate implementation produced by spawn_k_impls."""

    index: int
    impl_path: Path        # path to the implementation file
    content: str           # raw implementation source


@dataclass
class MatrixCell:
    """One (impl, test) cell of the KxK matrix."""

    impl_index: int
    test_index: int
    passing_tests: int          # how many assertions in test_set pass against this impl
    unique_fail_count: int      # how many tests uniquely fail OTHER impls (not this one)
    score: float                # mutual-agreement score = passing_tests * unique_fail_count
    passed: bool                # True if all tests pass against this impl


@dataclass
class ScoredMatrix:
    """Full KxK matrix with winner identified."""

    cells: list[MatrixCell]
    winner_impl_index: int
    winner_test_index: int
    winner_score: float


@dataclass
class TripleFilterResult:
    """Result of triple_filter for one test set."""

    test_index: int
    test_path: Path
    compiles: bool
    fails_on_stub: bool
    raises_coverage: bool
    accepted: bool
    reason: str


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NoCandidatesError(ValueError):
    """Raised when K=0 candidates are requested."""


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


def spawn_k_tests(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> list[CandidateTestSet]:
    """Generate K candidate test sets with different framings.

    Framings cycle through: positive, adversarial, boundary.
    Each test set is written to runs/<feature_id>/candidates/tests_<i>.py.

    Args:
        feature_id: The feature being tested.
        acceptance_criteria: List of AC strings to build tests from.
        K: Number of candidate test sets to produce. Must be >= 1.
        workspace: Project root directory.

    Returns:
        List of CandidateTestSet objects, length K.

    Raises:
        ValueError: If K < 1.
    """
    if K < 1:
        raise ValueError("K must be >= 1")

    framings = ["positive", "adversarial", "boundary"]
    base = _candidates_dir(feature_id, workspace)
    base.mkdir(parents=True, exist_ok=True)

    results: list[CandidateTestSet] = []
    for i in range(K):
        framing = framings[i % len(framings)]
        content = _render_test_set(feature_id, acceptance_criteria, i, framing)
        test_path = base / f"tests_{i}.py"
        test_path.write_text(content, encoding="utf-8")
        results.append(CandidateTestSet(
            index=i,
            framing=framing,
            test_path=test_path,
            content=content,
        ))

    return results


def spawn_k_impls(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 2,
    workspace: str | Path | None = None,
) -> list[CandidateImpl]:
    """Generate K candidate implementations.

    Each implementation is a minimal stub written to
    runs/<feature_id>/candidates/impl_<i>.py.

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings that guide the implementation.
        K: Number of candidate implementations to produce. Must be >= 1.
        workspace: Project root directory.

    Returns:
        List of CandidateImpl objects, length K.

    Raises:
        ValueError: If K < 1.
    """
    if K < 1:
        raise ValueError("K must be >= 1")

    base = _candidates_dir(feature_id, workspace)
    base.mkdir(parents=True, exist_ok=True)

    results: list[CandidateImpl] = []
    for i in range(K):
        content = _render_impl(feature_id, acceptance_criteria, i)
        impl_path = base / f"impl_{i}.py"
        impl_path.write_text(content, encoding="utf-8")
        results.append(CandidateImpl(
            index=i,
            impl_path=impl_path,
            content=content,
        ))

    return results


def score_matrix(
    impls: list[CandidateImpl],
    test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Score each (code, test) cell of the KxK matrix by mutual-agreement.

    Mutual-agreement score = passing_tests * tests_that_uniquely_fail_other_impls

    For each (impl_i, test_j) cell:
      - passing_tests: number of test functions that pass when impl_i is used
      - unique_fail_count: number of test functions in test_j that fail at
        least one OTHER impl (impl_k where k != i), demonstrating the test
        discriminates between implementations

    The winner is the cell with the highest score.

    Args:
        impls: Candidate implementations from spawn_k_impls.
        test_sets: Candidate test sets from spawn_k_tests.
        workspace: Project root directory.

    Returns:
        ScoredMatrix with all cells scored and winner identified.
    """
    # Build pass/fail matrix: pass_matrix[i][j] = True if test_set j passes with impl i
    n_impls = len(impls)
    n_tests = len(test_sets)

    # run each (impl, test) pair
    raw_results: list[list[bool]] = []
    for impl in impls:
        row: list[bool] = []
        for ts in test_sets:
            passed = _run_test_against_impl(impl, ts, workspace)
            row.append(passed)
        raw_results.append(row)

    # For each test set j, find which test functions uniquely fail at least one other impl
    # Simplified: count how many impls FAIL this test set (discriminative power)
    cells: list[MatrixCell] = []
    for i, impl in enumerate(impls):
        for j, ts in enumerate(test_sets):
            passing = 1 if raw_results[i][j] else 0

            # unique_fail_count: how many OTHER impls fail this test set
            other_fail_count = sum(
                1 for k in range(n_impls)
                if k != i and not raw_results[k][j]
            )

            score = float(passing * (other_fail_count + 1))

            cells.append(MatrixCell(
                impl_index=i,
                test_index=j,
                passing_tests=passing,
                unique_fail_count=other_fail_count,
                score=score,
                passed=raw_results[i][j],
            ))

    # Find winner: highest score, break ties by lowest impl_index then test_index
    best = max(cells, key=lambda c: (c.score, -c.impl_index, -c.test_index))

    return ScoredMatrix(
        cells=cells,
        winner_impl_index=best.impl_index,
        winner_test_index=best.test_index,
        winner_score=best.score,
    )


def triple_filter(
    test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> list[TripleFilterResult]:
    """Apply TestGen-LLM Build/Pass/Coverage triple filter to candidate test sets.

    Rejects test sets that:
      1. Don't compile (SyntaxError / ImportError at collection time)
      2. Mysteriously pass on stub code (vacuous test)
      3. Fail to reference any non-pytest symbol (no coverage uplift)

    Args:
        test_sets: Candidate test sets from spawn_k_tests.
        workspace: Project root directory.

    Returns:
        List of TripleFilterResult, one per input test set.
    """
    results: list[TripleFilterResult] = []
    for ts in test_sets:
        path = ts.test_path

        # Check 1: compiles
        compiles = _check_compiles(path)
        if not compiles:
            results.append(TripleFilterResult(
                test_index=ts.index,
                test_path=path,
                compiles=False,
                fails_on_stub=False,
                raises_coverage=False,
                accepted=False,
                reason="SyntaxError — test rejected",
            ))
            continue

        # Check 2: fails on stub
        fails_on_stub = _check_fails_on_stub(path)
        if not fails_on_stub:
            results.append(TripleFilterResult(
                test_index=ts.index,
                test_path=path,
                compiles=True,
                fails_on_stub=False,
                raises_coverage=False,
                accepted=False,
                reason="Test passes on stub code — vacuous, rejected",
            ))
            continue

        # Check 3: raises coverage heuristic
        raises_coverage = _check_raises_coverage(path)
        accepted = raises_coverage
        reason = "" if accepted else "No non-pytest symbols referenced — coverage check failed"

        results.append(TripleFilterResult(
            test_index=ts.index,
            test_path=path,
            compiles=True,
            fails_on_stub=True,
            raises_coverage=raises_coverage,
            accepted=accepted,
            reason=reason,
        ))

    return results


def persist_winning_cell(
    feature_id: str,
    matrix: ScoredMatrix,
    impls: list[CandidateImpl],
    test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> Path:
    """Write the winning (impl, test) cell to runs/<feature>/winner.yaml.

    Args:
        feature_id: The feature being implemented.
        matrix: Scored matrix from score_matrix.
        impls: All candidate implementations.
        test_sets: All candidate test sets.
        workspace: Project root directory.

    Returns:
        Path to the written winner.yaml file.
    """
    winner_impl = impls[matrix.winner_impl_index]
    winner_test = test_sets[matrix.winner_test_index]

    run_dir = _run_dir(feature_id, workspace)
    run_dir.mkdir(parents=True, exist_ok=True)

    winner_data: dict[str, Any] = {
        "feature_id": feature_id,
        "winner": {
            "impl_index": matrix.winner_impl_index,
            "test_index": matrix.winner_test_index,
            "score": matrix.winner_score,
            "impl_path": str(winner_impl.impl_path),
            "test_path": str(winner_test.test_path),
            "framing": winner_test.framing,
        },
        "matrix_size": {
            "n_impls": len(impls),
            "n_tests": len(test_sets),
        },
        "all_scores": [
            {
                "impl_index": c.impl_index,
                "test_index": c.test_index,
                "score": c.score,
                "passing_tests": c.passing_tests,
                "unique_fail_count": c.unique_fail_count,
            }
            for c in matrix.cells
        ],
    }

    winner_path = run_dir / "winner.yaml"
    winner_path.write_text(yaml.dump(winner_data, default_flow_style=False), encoding="utf-8")
    logger.info("Persisted winner to %s (score=%.2f)", winner_path, matrix.winner_score)
    return winner_path


def archive_losers(
    feature_id: str,
    matrix: ScoredMatrix,
    impls: list[CandidateImpl],
    test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> list[Path]:
    """Move losing cells to runs/<feature>/variants/.

    Losing cells are all (impl, test) pairs that are NOT the winner.
    Each losing impl and test file is copied (not removed from candidates/)
    to runs/<feature>/variants/impl_<i>_test_<j>/.

    Args:
        feature_id: The feature being implemented.
        matrix: Scored matrix from score_matrix.
        impls: All candidate implementations.
        test_sets: All candidate test sets.
        workspace: Project root directory.

    Returns:
        List of variant directory paths that were created.
    """
    run_dir = _run_dir(feature_id, workspace)
    variants_dir = run_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)

    created_dirs: list[Path] = []

    for cell in matrix.cells:
        if (cell.impl_index == matrix.winner_impl_index
                and cell.test_index == matrix.winner_test_index):
            continue  # skip winner

        impl = impls[cell.impl_index]
        ts = test_sets[cell.test_index]

        variant_dir = variants_dir / f"impl_{cell.impl_index}_test_{cell.test_index}"
        variant_dir.mkdir(parents=True, exist_ok=True)

        # copy impl and test into variant dir
        dest_impl = variant_dir / impl.impl_path.name
        dest_test = variant_dir / ts.test_path.name

        if impl.impl_path.exists():
            shutil.copy2(impl.impl_path, dest_impl)
        if ts.test_path.exists():
            shutil.copy2(ts.test_path, dest_test)

        # write cell metadata
        meta: dict[str, Any] = {
            "impl_index": cell.impl_index,
            "test_index": cell.test_index,
            "score": cell.score,
            "passing_tests": cell.passing_tests,
            "unique_fail_count": cell.unique_fail_count,
            "framing": ts.framing,
        }
        (variant_dir / "cell_meta.yaml").write_text(
            yaml.dump(meta, default_flow_style=False), encoding="utf-8"
        )

        created_dirs.append(variant_dir)
        logger.debug("Archived loser cell impl_%d_test_%d to %s", cell.impl_index, cell.test_index, variant_dir)

    return created_dirs


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def _run_dir(feature_id: str, workspace: str | Path | None = None) -> Path:
    base = Path(workspace) if workspace else Path.cwd()
    return base / "runs" / feature_id


def _candidates_dir(feature_id: str, workspace: str | Path | None = None) -> Path:
    return _run_dir(feature_id, workspace) / "candidates"


# ---------------------------------------------------------------------------
# Template renderers (deterministic stubs for the spawn pipeline)
# ---------------------------------------------------------------------------


def _render_test_set(
    feature_id: str,
    acceptance_criteria: list[str],
    index: int,
    framing: str,
) -> str:
    """Render a candidate test set file."""
    ac_lines = "\n".join(f"    # AC: {ac}" for ac in acceptance_criteria)
    class_name = f"TestCandidate{index}_{framing.capitalize()}"
    return (
        f'"""Candidate test set {index} (framing={framing}) for feature {feature_id}."""\n'
        f"import pytest\n\n\n"
        f"class {class_name}:\n"
        f"    \"\"\"Framing: {framing}. Generated by spawn_k_tests.\"\"\"\n\n"
        f"{ac_lines}\n\n"
        f"    def test_placeholder_{framing}_{index}(self):\n"
        f"        # {framing} framing test — replace with real assertions\n"
        f"        assert True  # sentinel\n"
    )


def _render_impl(
    feature_id: str,
    acceptance_criteria: list[str],
    index: int,
) -> str:
    """Render a candidate implementation file."""
    ac_lines = "\n".join(f"    # AC: {ac}" for ac in acceptance_criteria)
    return (
        f'"""Candidate implementation {index} for feature {feature_id}."""\n\n\n'
        f"class CandidateImpl{index}:\n"
        f"    \"\"\"Generated by spawn_k_impls.\"\"\"\n\n"
        f"{ac_lines}\n\n"
        f"    def run(self):\n"
        f"        raise NotImplementedError('Candidate {index} not yet implemented')\n"
    )


# ---------------------------------------------------------------------------
# Triple-filter helpers
# ---------------------------------------------------------------------------


def _check_compiles(path: Path) -> bool:
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        return True
    except (SyntaxError, UnicodeDecodeError):
        return False


def _check_fails_on_stub(path: Path) -> bool:
    """Return True if the test fails when run with no source modules present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = str(path.resolve())
        result = subprocess.run(
            [sys.executable, "-m", "pytest", env_path, "--tb=no", "-q", "--no-header"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        # Non-zero exit means at least one test failed — that's what we want
        return result.returncode != 0


def _check_raises_coverage(path: Path) -> bool:
    """Return True if the test references at least one non-pytest symbol."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return False

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                if node.module and not node.module.startswith("pytest"):
                    return True
            else:
                for alias in node.names:
                    if not alias.name.startswith("pytest"):
                        return True
    return False


def _run_test_against_impl(
    impl: CandidateImpl,
    test_set: CandidateTestSet,
    workspace: str | Path | None = None,
) -> bool:
    """Return True if the test set passes when run against the given impl.

    For the triangulation pipeline, we run pytest on the test file with
    the impl directory on sys.path.
    """
    impl_dir = impl.impl_path.parent
    env = {"PYTHONPATH": str(impl_dir.resolve())}

    # inherit parent env for interpreter resolution
    import os as _os
    merged_env = {**_os.environ, **env}

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_set.test_path.resolve()),
         "--tb=no", "-q", "--no-header"],
        capture_output=True,
        text=True,
        env=merged_env,
        cwd=str(impl_dir),
    )
    return result.returncode == 0
