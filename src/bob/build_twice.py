"""Build-twice nondeterminism detector (Gap #7).

After a feature passes verification, re-run the implementation sub-agent from
the same spec with a different seed (seed+1).  Compare the two implementations:
AST-normalize both, compute token-level diff, flag if >30% divergence.

Controlled by BOB_BUILD_TWICE env var (default False).
Log nondeterminism events to .bob/progress.jsonl and reviews/findings.yaml.
"""
from __future__ import annotations

import ast
import difflib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

_DIVERGENCE_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class NondeterminismReport:
    """Result of comparing two builds of the same feature."""

    feature_id: str
    divergence_ratio: float
    flagged: bool
    seed_a: int
    seed_b: int
    details: str = ""


# ---------------------------------------------------------------------------
# AST normalization
# ---------------------------------------------------------------------------


class _NameNormalizer(ast.NodeTransformer):
    """Replace all Name/arg/FunctionDef/ClassDef identifiers with stable tokens."""

    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._counter = 0

    def _token(self, name: str) -> str:
        if name not in self._map:
            self._map[name] = f"_v{self._counter}"
            self._counter += 1
        return self._map[name]

    def visit_Name(self, node: ast.Name) -> ast.Name:
        node.id = self._token(node.id)
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = self._token(node.arg)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.name = self._token(node.name)
        # Strip docstring
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:]
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        node.name = self._token(node.name)
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:]
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.name = self._token(node.name)
        # Strip class docstring
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:]
        self.generic_visit(node)
        return node


def ast_normalize(code: str) -> str:
    """Return a normalized string representation of *code*'s AST.

    - Strips comments (handled by the parser itself)
    - Strips docstrings
    - Renames all identifiers to stable anonymous tokens
    - Returns ``ast.dump`` of the normalized tree

    Falls back to the original source on any syntax error.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    normalizer = _NameNormalizer()
    normalized = normalizer.visit(tree)
    ast.fix_missing_locations(normalized)
    return ast.dump(normalized)


# ---------------------------------------------------------------------------
# Token-level diff ratio
# ---------------------------------------------------------------------------


def token_diff_ratio(text_a: str, text_b: str) -> float:
    """Compute the fraction of tokens that differ between *text_a* and *text_b*.

    Tokens are whitespace-split words.  Returns a value in [0.0, 1.0] where
    0.0 means identical and 1.0 means no tokens in common.
    """
    tokens_a = text_a.split()
    tokens_b = text_b.split()
    if not tokens_a and not tokens_b:
        return 0.0
    matcher = difflib.SequenceMatcher(None, tokens_a, tokens_b, autojunk=False)
    # ratio() = 2 * matching / total; divergence = 1 - ratio
    return 1.0 - matcher.ratio()


# ---------------------------------------------------------------------------
# Environment flag
# ---------------------------------------------------------------------------


def is_build_twice_enabled() -> bool:
    """Return True when BOB_BUILD_TWICE env var is set to a truthy value."""
    val = os.environ.get("BOB_BUILD_TWICE", "").strip().lower()
    return val in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


def _emit_progress_event(workspace: Path, feature_id: str, payload: dict) -> None:
    """Append a nondeterminism_detected event to .bob/progress.jsonl."""
    progress_path = workspace / ".bob" / "progress.jsonl"
    try:
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event_type": "nondeterminism_detected",
            "feature_id": feature_id,
            "payload": payload,
        }
        with progress_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Could not write progress event: %s", exc)


def _append_findings_yaml(workspace: Path, feature_id: str, divergence_ratio: float) -> None:
    """Append a nondeterminism finding to reviews/findings.yaml if accessible."""
    try:
        from bob.reviews import (
            load_registry,
            save_registry,
            add_finding,
            next_finding_id,
        )

        try:
            registry = load_registry()
        except FileNotFoundError:
            logger.debug("reviews/findings.yaml not found — skipping finding append")
            return

        add_finding(
            registry,
            round_prefix="R2",
            title=f"Nondeterminism detected: feature {feature_id}",
            pattern="build-twice divergence > 30%",
            files=["src/bob/build_twice.py"],
            severity="medium",
            status="open",
            tags=["nondeterminism", "build-twice"],
            notes=(
                f"feature_id={feature_id} divergence_ratio={divergence_ratio:.3f} "
                f"(threshold=0.30)"
            ),
        )
        save_registry(registry)
    except Exception as exc:
        logger.warning("Could not append to findings.yaml: %s", exc)


# ---------------------------------------------------------------------------
# Core comparison
# ---------------------------------------------------------------------------


def _collect_python_source(directory: Path) -> str:
    """Concatenate all *.py files in *directory* (recursively, sorted by path)."""
    parts: list[str] = []
    for py_file in sorted(directory.rglob("*.py")):
        try:
            parts.append(py_file.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    return "\n".join(parts)


def compare_builds(
    feature_id: str,
    workspace: Path,
    *,
    build_a_dir: str = "build_a",
    build_b_dir: str = "build_b",
    seed_a: int = 0,
    seed_b: int = 1,
) -> NondeterminismReport:
    """Compare two builds of *feature_id* and return a NondeterminismReport.

    Parameters
    ----------
    feature_id:
        The feature being compared.
    workspace:
        Root directory under which *build_a_dir* and *build_b_dir* live.
    build_a_dir / build_b_dir:
        Sub-directory names (relative to *workspace*) holding each build's
        Python source files.
    seed_a / seed_b:
        Seeds used to produce each build (for record-keeping).

    Returns
    -------
    NondeterminismReport
        ``flagged=True`` when ``divergence_ratio > 0.30``.
    """
    dir_a = workspace / build_a_dir
    dir_b = workspace / build_b_dir

    src_a = _collect_python_source(dir_a)
    src_b = _collect_python_source(dir_b)

    if not src_a and not src_b:
        return NondeterminismReport(
            feature_id=feature_id,
            divergence_ratio=0.0,
            flagged=False,
            seed_a=seed_a,
            seed_b=seed_b,
            details="Both builds contained no Python source files.",
        )

    norm_a = ast_normalize(src_a) if src_a else ""
    norm_b = ast_normalize(src_b) if src_b else ""

    ratio = token_diff_ratio(norm_a, norm_b)
    flagged = ratio > _DIVERGENCE_THRESHOLD

    details = (
        f"divergence_ratio={ratio:.4f} threshold={_DIVERGENCE_THRESHOLD} "
        f"flagged={flagged}"
    )

    if flagged:
        payload = {
            "feature_id": feature_id,
            "divergence_ratio": ratio,
            "seed_a": seed_a,
            "seed_b": seed_b,
        }
        _emit_progress_event(workspace, feature_id, payload)
        _append_findings_yaml(workspace, feature_id, ratio)

    logger.info("build-twice %s: %s", feature_id, details)

    return NondeterminismReport(
        feature_id=feature_id,
        divergence_ratio=ratio,
        flagged=flagged,
        seed_a=seed_a,
        seed_b=seed_b,
        details=details,
    )
