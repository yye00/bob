"""Workflow memory — spec-attempt-outcome traces (F-R4-138).

Persists full spec-attempt-outcome traces in a case-based retrieval
store backed by SQLite. When a new spec arrives, retrieves the k nearest
past traces (cosine similarity on spec embeddings) and formats them for
injection as context into the planning phase.

Public API
----------
SpecTrace                      - dataclass representing one stored trace
WorkflowMemoryStore            - case-based retrieval store (SQLite-backed)
    .record_trace(...)         - persist a spec-attempt-outcome trace
    .retrieve_similar(spec, k) - retrieve k nearest traces by cosine sim
    .format_context(traces)    - format traces for prompt injection
build_planning_context(spec, k, store) - one-shot helper for the planner
"""

from __future__ import annotations

import math
import re
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SpecTrace:
    """A single recorded spec-attempt-outcome trace.

    Attributes:
        trace_id:    Unique identifier for this trace.
        spec_text:   Full specification text that was attempted.
        outcome:     One of "completed", "failed", "needs_human".
        feature_id:  Feature ID associated with this trace (optional).
        feature_name: Human-readable feature name (optional).
        attempt_summary: Short description of what was attempted.
        error_details:   Failure details or blockers encountered (optional).
        cost_usd:        Cost in USD of the attempt (optional).
        duration_ms:     Wall-clock duration in milliseconds (optional).
        created_at:      ISO 8601 timestamp when the trace was stored.
    """

    trace_id: str
    spec_text: str
    outcome: str
    feature_id: str | None = None
    feature_name: str | None = None
    attempt_summary: str = ""
    error_details: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    similarity: float | None = None  # populated by retrieve_similar


# ---------------------------------------------------------------------------
# Embedding helpers (TF-IDF-style bag-of-words, no external ML libs)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_IDF_SMOOTHING = 1  # add-one smoothing for IDF denominator


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _term_frequencies(tokens: list[str]) -> Counter:
    return Counter(tokens)


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between two sparse TF-weighted vectors."""
    shared = set(vec_a) & set(vec_b)
    if not shared:
        return 0.0
    dot = sum(vec_a[t] * vec_b[t] for t in shared)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _build_tf_vector(text: str) -> dict[str, float]:
    tokens = _tokenize(text)
    if not tokens:
        return {}
    counts = _term_frequencies(tokens)
    total = len(tokens)
    return {term: count / total for term, count in counts.items()}


# ---------------------------------------------------------------------------
# SQLite schema for the trace store
# ---------------------------------------------------------------------------

_CREATE_TRACES_TABLE = """
CREATE TABLE IF NOT EXISTS workflow_traces (
    trace_id        TEXT PRIMARY KEY,
    spec_text       TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    feature_id      TEXT,
    feature_name    TEXT,
    attempt_summary TEXT NOT NULL DEFAULT '',
    error_details   TEXT,
    cost_usd        REAL,
    duration_ms     INTEGER,
    created_at      TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# WorkflowMemoryStore
# ---------------------------------------------------------------------------


class WorkflowMemoryStore:
    """Case-based retrieval store for spec-attempt-outcome traces.

    Uses SQLite for persistence and TF-weighted cosine similarity for
    nearest-neighbour retrieval. The store is safe to use from a single
    process; SQLite WAL mode is enabled for concurrent readers.

    Parameters
    ----------
    db_path:
        Path to the SQLite file.  Defaults to ``workflow_traces.db`` in
        the current working directory.  Use ``:memory:`` for in-process
        testing.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.cwd() / "workflow_traces.db"
        self._db_path = str(db_path)
        self._init_db()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TRACES_TABLE)
            conn.commit()

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def record_trace(
        self,
        spec_text: str,
        outcome: str,
        *,
        feature_id: str | None = None,
        feature_name: str | None = None,
        attempt_summary: str = "",
        error_details: str | None = None,
        cost_usd: float | None = None,
        duration_ms: int | None = None,
        trace_id: str | None = None,
        created_at: str | None = None,
    ) -> SpecTrace:
        """Persist a spec-attempt-outcome trace and return the stored record.

        Parameters
        ----------
        spec_text:
            Full specification text (description + acceptance criteria).
        outcome:
            Result of the attempt: ``"completed"``, ``"failed"``, or
            ``"needs_human"``.
        feature_id:
            Optional feature UUID from the features table.
        feature_name:
            Human-readable feature name.
        attempt_summary:
            Short summary of what was attempted / implemented.
        error_details:
            Failure message, blocked reason, or verification failure text.
        cost_usd:
            Cost in USD for this attempt.
        duration_ms:
            Wall-clock duration in milliseconds.
        trace_id:
            Explicit trace ID (auto-generated if not provided).
        created_at:
            ISO 8601 timestamp (defaults to now).
        """
        if not spec_text:
            raise ValueError("spec_text must not be empty")
        valid_outcomes = {"completed", "failed", "needs_human"}
        if outcome not in valid_outcomes:
            raise ValueError(
                f"outcome must be one of {sorted(valid_outcomes)!r}, got {outcome!r}"
            )

        tid = trace_id or str(uuid.uuid4())
        ts = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

        trace = SpecTrace(
            trace_id=tid,
            spec_text=spec_text,
            outcome=outcome,
            feature_id=feature_id,
            feature_name=feature_name,
            attempt_summary=attempt_summary,
            error_details=error_details,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            created_at=ts,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workflow_traces
                  (trace_id, spec_text, outcome, feature_id, feature_name,
                   attempt_summary, error_details, cost_usd, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    trace.spec_text,
                    trace.outcome,
                    trace.feature_id,
                    trace.feature_name,
                    trace.attempt_summary,
                    trace.error_details,
                    trace.cost_usd,
                    trace.duration_ms,
                    trace.created_at,
                ),
            )
            conn.commit()

        return trace

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def _row_to_trace(self, row: sqlite3.Row) -> SpecTrace:
        return SpecTrace(
            trace_id=row["trace_id"],
            spec_text=row["spec_text"],
            outcome=row["outcome"],
            feature_id=row["feature_id"],
            feature_name=row["feature_name"],
            attempt_summary=row["attempt_summary"] or "",
            error_details=row["error_details"],
            cost_usd=row["cost_usd"],
            duration_ms=row["duration_ms"],
            created_at=row["created_at"],
        )

    def retrieve_similar(
        self,
        query_spec: str,
        k: int = 5,
        *,
        min_similarity: float = 0.0,
    ) -> list[SpecTrace]:
        """Return the k most similar past traces to *query_spec*.

        Similarity is computed as cosine similarity between TF-weighted
        bag-of-words vectors of the spec texts.  Traces are returned in
        descending similarity order.

        Parameters
        ----------
        query_spec:
            The new specification text to match against stored traces.
        k:
            Maximum number of traces to return.
        min_similarity:
            Minimum similarity threshold; traces below this are excluded.

        Returns
        -------
        List of :class:`SpecTrace` with the ``similarity`` field populated.
        """
        if k <= 0:
            return []

        query_vec = _build_tf_vector(query_spec)
        if not query_vec:
            return []

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_traces ORDER BY created_at DESC"
            ).fetchall()

        scored: list[tuple[float, SpecTrace]] = []
        for row in rows:
            trace = self._row_to_trace(row)
            doc_vec = _build_tf_vector(trace.spec_text)
            sim = _cosine_similarity(query_vec, doc_vec)
            if sim >= min_similarity:
                trace.similarity = round(sim, 4)
                scored.append((sim, trace))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:k]]

    def all_traces(self) -> list[SpecTrace]:
        """Return all stored traces ordered by creation time (newest first)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_traces ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_trace(row) for row in rows]

    def count(self) -> int:
        """Return the total number of stored traces."""
        with self._connect() as conn:
            result = conn.execute("SELECT COUNT(*) FROM workflow_traces").fetchone()
            return result[0]

    # ------------------------------------------------------------------
    # Context formatting
    # ------------------------------------------------------------------

    def format_context(self, traces: Sequence[SpecTrace]) -> str:
        """Format retrieved traces as a prompt-injection context block.

        Produces a Markdown-formatted block that a planning agent can
        consume directly. Includes spec excerpts, outcomes, and key
        lessons from past attempts.

        Parameters
        ----------
        traces:
            Ordered list of traces (most similar first).

        Returns
        -------
        A string ready for injection into the planning prompt.  Returns
        an empty string when *traces* is empty.
        """
        if not traces:
            return ""

        parts = [
            "## Similar Past Spec-Attempt-Outcome Traces",
            "",
            "The following traces from previous similar features are provided "
            "to inform the planning phase. Study them for reusable patterns, "
            "known pitfalls, and outcome signals.",
            "",
        ]

        for i, trace in enumerate(traces, start=1):
            sim_str = f" (similarity={trace.similarity:.3f})" if trace.similarity is not None else ""
            name = trace.feature_name or trace.feature_id or "unknown"
            parts.append(f"### Trace {i}: {name}{sim_str}")
            parts.append("")

            # Spec excerpt — cap at 400 chars to avoid prompt bloat
            spec_excerpt = trace.spec_text[:400]
            if len(trace.spec_text) > 400:
                spec_excerpt += "…"
            parts.append(f"**Spec:** {spec_excerpt}")
            parts.append("")

            parts.append(f"**Outcome:** `{trace.outcome}`")
            parts.append("")

            if trace.attempt_summary:
                parts.append(f"**What was attempted:** {trace.attempt_summary}")
                parts.append("")

            if trace.error_details:
                err_excerpt = trace.error_details[:300]
                if len(trace.error_details) > 300:
                    err_excerpt += "…"
                parts.append(f"**Failure / blockers:** {err_excerpt}")
                parts.append("")

            if trace.cost_usd is not None or trace.duration_ms is not None:
                stats = []
                if trace.cost_usd is not None:
                    stats.append(f"cost=${trace.cost_usd:.4f}")
                if trace.duration_ms is not None:
                    stats.append(f"duration={trace.duration_ms}ms")
                parts.append(f"**Stats:** {', '.join(stats)}")
                parts.append("")

        return "\n".join(parts).rstrip()


# ---------------------------------------------------------------------------
# Convenience helper for orchestrator / planning phase
# ---------------------------------------------------------------------------


def build_planning_context(
    spec_text: str,
    k: int = 5,
    store: WorkflowMemoryStore | None = None,
    *,
    db_path: str | Path | None = None,
    min_similarity: float = 0.0,
) -> str:
    """Retrieve k similar past traces and format them for prompt injection.

    This is the primary entry point for the planning phase.  Provide
    either a pre-built *store* or a *db_path* for a fresh connection.

    Parameters
    ----------
    spec_text:
        The new feature specification text.
    k:
        Number of similar traces to retrieve.
    store:
        Pre-built :class:`WorkflowMemoryStore` (used in tests / if the
        orchestrator already holds a store reference).
    db_path:
        Path to the SQLite database; passed through to
        :class:`WorkflowMemoryStore` when *store* is ``None``.
    min_similarity:
        Minimum cosine similarity threshold.

    Returns
    -------
    Formatted context string, or empty string if no similar traces exist.
    """
    if store is None:
        store = WorkflowMemoryStore(db_path=db_path)

    traces = store.retrieve_similar(spec_text, k=k, min_similarity=min_similarity)
    return store.format_context(traces)
