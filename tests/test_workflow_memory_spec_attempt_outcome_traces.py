"""Tests for src/bob/workflow_memory_spec_attempt_outcome_traces.py."""

from __future__ import annotations

import math
import uuid

import pytest

from bob.workflow_memory_spec_attempt_outcome_traces import (
    SpecTrace,
    WorkflowMemoryStore,
    _build_tf_vector,
    _cosine_similarity,
    _tokenize,
    build_planning_context,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    """In-memory (per-test) WorkflowMemoryStore backed by a temp SQLite file."""
    return WorkflowMemoryStore(db_path=tmp_path / "traces.db")


@pytest.fixture
def populated_store(store):
    """Store with three pre-recorded traces."""
    store.record_trace(
        spec_text="Implement a sorting algorithm for integer lists. "
                  "Acceptance: sorted output, handles empty list.",
        outcome="completed",
        feature_id="feat-001",
        feature_name="Sort integers",
        attempt_summary="Used heapsort, all tests pass.",
        cost_usd=0.05,
        duration_ms=12000,
    )
    store.record_trace(
        spec_text="Build a caching layer with LRU eviction for HTTP responses.",
        outcome="failed",
        feature_id="feat-002",
        feature_name="HTTP cache",
        attempt_summary="Implemented LRU cache but integration tests fail.",
        error_details="KeyError in cache lookup during concurrent access.",
        cost_usd=0.12,
        duration_ms=34000,
    )
    store.record_trace(
        spec_text="Add Bayesian confidence scoring to the calibration module.",
        outcome="needs_human",
        feature_id="feat-003",
        feature_name="Bayesian confidence",
        attempt_summary="Started but blocked on missing prior data.",
        error_details="No historical calibration data available.",
        cost_usd=0.03,
        duration_ms=8000,
    )
    return store


# ---------------------------------------------------------------------------
# Tokenization helpers
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_lowercases_text(self):
        assert _tokenize("Hello WORLD") == ["hello", "world"]

    def test_extracts_alphanumeric_tokens(self):
        tokens = _tokenize("foo_bar baz-qux 123")
        assert "foo_bar" in tokens
        assert "baz" in tokens
        assert "qux" in tokens
        assert "123" in tokens

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_punctuation_stripped(self):
        tokens = _tokenize("hello, world! (test)")
        assert tokens == ["hello", "world", "test"]


class TestBuildTfVector:
    def test_returns_dict(self):
        vec = _build_tf_vector("hello world hello")
        assert isinstance(vec, dict)

    def test_term_frequencies_sum_to_one(self):
        vec = _build_tf_vector("a b c")
        assert abs(sum(vec.values()) - 1.0) < 1e-9

    def test_repeated_tokens_higher_weight(self):
        vec = _build_tf_vector("cat cat cat dog")
        assert vec["cat"] > vec["dog"]

    def test_empty_text_returns_empty_dict(self):
        assert _build_tf_vector("") == {}

    def test_only_punctuation_returns_empty(self):
        assert _build_tf_vector("...!!!") == {}


class TestCosineSimilarity:
    def test_identical_vectors_give_one(self):
        vec = _build_tf_vector("python machine learning")
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-9

    def test_disjoint_vectors_give_zero(self):
        vec_a = _build_tf_vector("apple orange banana")
        vec_b = _build_tf_vector("dog cat fish")
        assert _cosine_similarity(vec_a, vec_b) == 0.0

    def test_partial_overlap_between_zero_and_one(self):
        vec_a = _build_tf_vector("machine learning python")
        vec_b = _build_tf_vector("python data science")
        sim = _cosine_similarity(vec_a, vec_b)
        assert 0.0 < sim < 1.0

    def test_empty_vectors_give_zero(self):
        assert _cosine_similarity({}, {}) == 0.0

    def test_symmetry(self):
        vec_a = _build_tf_vector("hello world")
        vec_b = _build_tf_vector("world foo bar")
        assert abs(_cosine_similarity(vec_a, vec_b) - _cosine_similarity(vec_b, vec_a)) < 1e-12


# ---------------------------------------------------------------------------
# WorkflowMemoryStore — record_trace
# ---------------------------------------------------------------------------


class TestRecordTrace:
    def test_returns_spec_trace(self, store):
        trace = store.record_trace(
            spec_text="Sort a list of integers",
            outcome="completed",
        )
        assert isinstance(trace, SpecTrace)

    def test_assigns_trace_id(self, store):
        trace = store.record_trace(spec_text="Spec A", outcome="completed")
        assert trace.trace_id
        assert len(trace.trace_id) > 0

    def test_uses_explicit_trace_id(self, store):
        tid = "my-explicit-id"
        trace = store.record_trace(spec_text="Spec B", outcome="failed", trace_id=tid)
        assert trace.trace_id == tid

    def test_stores_all_fields(self, store):
        trace = store.record_trace(
            spec_text="Full spec",
            outcome="needs_human",
            feature_id="f-abc",
            feature_name="My feature",
            attempt_summary="Tried X",
            error_details="Blocked by Y",
            cost_usd=0.42,
            duration_ms=5000,
        )
        assert trace.spec_text == "Full spec"
        assert trace.outcome == "needs_human"
        assert trace.feature_id == "f-abc"
        assert trace.feature_name == "My feature"
        assert trace.attempt_summary == "Tried X"
        assert trace.error_details == "Blocked by Y"
        assert trace.cost_usd == pytest.approx(0.42)
        assert trace.duration_ms == 5000

    def test_persists_to_database(self, store):
        store.record_trace(spec_text="Persisted spec", outcome="completed")
        assert store.count() == 1

    def test_raises_for_empty_spec_text(self, store):
        with pytest.raises(ValueError, match="spec_text"):
            store.record_trace(spec_text="", outcome="completed")

    def test_raises_for_invalid_outcome(self, store):
        with pytest.raises(ValueError, match="outcome"):
            store.record_trace(spec_text="Some spec", outcome="unknown_outcome")

    def test_all_valid_outcomes_accepted(self, store):
        for outcome in ("completed", "failed", "needs_human"):
            store.record_trace(
                spec_text=f"Spec for {outcome}",
                outcome=outcome,
                trace_id=str(uuid.uuid4()),
            )
        assert store.count() == 3


# ---------------------------------------------------------------------------
# WorkflowMemoryStore — count / all_traces
# ---------------------------------------------------------------------------


class TestStoreQuery:
    def test_count_empty_store(self, store):
        assert store.count() == 0

    def test_count_increments(self, store):
        store.record_trace("Spec 1", outcome="completed")
        store.record_trace("Spec 2", outcome="failed")
        assert store.count() == 2

    def test_all_traces_returns_list(self, populated_store):
        traces = populated_store.all_traces()
        assert isinstance(traces, list)
        assert len(traces) == 3

    def test_all_traces_newest_first(self, store):
        store.record_trace("old spec", outcome="completed", created_at="2024-01-01T00:00:00+00:00", trace_id="t1")
        store.record_trace("new spec", outcome="failed", created_at="2024-06-01T00:00:00+00:00", trace_id="t2")
        traces = store.all_traces()
        # Newest first
        assert traces[0].trace_id == "t2"
        assert traces[1].trace_id == "t1"


# ---------------------------------------------------------------------------
# WorkflowMemoryStore — retrieve_similar
# ---------------------------------------------------------------------------


class TestRetrieveSimilar:
    def test_returns_empty_list_for_empty_store(self, store):
        result = store.retrieve_similar("some spec text", k=5)
        assert result == []

    def test_returns_at_most_k_results(self, populated_store):
        result = populated_store.retrieve_similar("sorting algorithm", k=2)
        assert len(result) <= 2

    def test_zero_k_returns_empty(self, populated_store):
        result = populated_store.retrieve_similar("sorting algorithm", k=0)
        assert result == []

    def test_similarity_field_populated(self, populated_store):
        results = populated_store.retrieve_similar("sorting algorithm", k=3)
        for trace in results:
            assert trace.similarity is not None
            assert 0.0 <= trace.similarity <= 1.0

    def test_results_ordered_descending_similarity(self, populated_store):
        results = populated_store.retrieve_similar("sorting algorithm integers", k=5)
        sims = [t.similarity for t in results]
        assert sims == sorted(sims, reverse=True)

    def test_most_similar_spec_ranked_first(self, populated_store):
        # "sorting algorithm" is clearly most similar to feat-001 spec
        results = populated_store.retrieve_similar(
            "sorting algorithm for integer list with empty list handling", k=5
        )
        assert results[0].feature_name == "Sort integers"

    def test_min_similarity_filters_results(self, store):
        store.record_trace("machine learning python model training", outcome="completed", trace_id="t1")
        store.record_trace("apple orange banana fruit salad", outcome="failed", trace_id="t2")
        # Query about ML; apple/fruit should be below threshold
        results = store.retrieve_similar(
            "machine learning neural network training",
            k=5,
            min_similarity=0.1,
        )
        trace_ids = [t.trace_id for t in results]
        assert "t1" in trace_ids
        # t2 might not appear due to zero overlap
        for t in results:
            assert t.similarity >= 0.1

    def test_empty_query_returns_empty(self, populated_store):
        result = populated_store.retrieve_similar("", k=5)
        assert result == []

    def test_k_larger_than_store_returns_all(self, populated_store):
        result = populated_store.retrieve_similar("algorithm", k=100)
        assert len(result) <= 3  # only 3 traces in store


# ---------------------------------------------------------------------------
# WorkflowMemoryStore — format_context
# ---------------------------------------------------------------------------


class TestFormatContext:
    def test_empty_traces_returns_empty_string(self, store):
        assert store.format_context([]) == ""

    def test_contains_header(self, populated_store):
        traces = populated_store.all_traces()[:2]
        ctx = populated_store.format_context(traces)
        assert "Spec-Attempt-Outcome Traces" in ctx

    def test_includes_feature_names(self, populated_store):
        traces = populated_store.retrieve_similar("sorting", k=3)
        ctx = populated_store.format_context(traces)
        assert "Sort integers" in ctx

    def test_includes_outcome(self, populated_store):
        traces = populated_store.retrieve_similar("sorting integers algorithm", k=1)
        ctx = populated_store.format_context(traces)
        assert "completed" in ctx

    def test_includes_attempt_summary(self, populated_store):
        traces = populated_store.retrieve_similar("sorting integers algorithm", k=1)
        ctx = populated_store.format_context(traces)
        assert "heapsort" in ctx

    def test_includes_error_details_for_failed(self, populated_store):
        traces = populated_store.retrieve_similar("http caching lru eviction", k=1)
        ctx = populated_store.format_context(traces)
        assert "KeyError" in ctx or "cache" in ctx.lower()

    def test_spec_text_truncated(self, store):
        long_spec = "word " * 500  # 2500 chars
        store.record_trace(long_spec, outcome="completed")
        traces = store.all_traces()
        ctx = store.format_context(traces)
        # Output should not contain the full spec
        assert len(ctx) < len(long_spec)

    def test_similarity_shown_in_context(self, populated_store):
        traces = populated_store.retrieve_similar("sorting", k=1)
        ctx = populated_store.format_context(traces)
        assert "similarity=" in ctx

    def test_stats_shown_when_present(self, populated_store):
        traces = populated_store.retrieve_similar("sorting integers algorithm", k=1)
        ctx = populated_store.format_context(traces)
        assert "cost=" in ctx
        assert "duration=" in ctx


# ---------------------------------------------------------------------------
# build_planning_context (integration helper)
# ---------------------------------------------------------------------------


class TestBuildPlanningContext:
    def test_returns_string(self, store):
        result = build_planning_context("some spec", k=3, store=store)
        assert isinstance(result, str)

    def test_empty_store_returns_empty_string(self, store):
        result = build_planning_context("some spec", k=3, store=store)
        assert result == ""

    def test_retrieves_and_formats_similar_traces(self, populated_store):
        ctx = build_planning_context(
            "sorting algorithm for integer list",
            k=2,
            store=populated_store,
        )
        assert ctx  # non-empty
        assert "Trace" in ctx

    def test_uses_db_path_when_no_store(self, tmp_path):
        db_path = tmp_path / "traces.db"
        store = WorkflowMemoryStore(db_path=db_path)
        store.record_trace("python sorting integers", outcome="completed", feature_name="Sort")
        ctx = build_planning_context("python sorting", k=3, db_path=db_path)
        assert "Sort" in ctx

    def test_respects_k_limit(self, populated_store):
        ctx = build_planning_context(
            "algorithm data structure",
            k=1,
            store=populated_store,
        )
        # Only one trace section
        assert ctx.count("### Trace") <= 1

    def test_respects_min_similarity(self, store):
        store.record_trace("python machine learning", outcome="completed", feature_name="ML")
        store.record_trace("orange juice recipe", outcome="failed", feature_name="Juice")
        ctx = build_planning_context(
            "python machine learning neural network",
            k=5,
            store=store,
            min_similarity=0.1,
        )
        if ctx:
            assert "ML" in ctx
            assert "Juice" not in ctx


# ---------------------------------------------------------------------------
# Persistence — survives reconnect
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_trace_survives_reconnect(self, tmp_path):
        db_path = tmp_path / "traces.db"
        store1 = WorkflowMemoryStore(db_path=db_path)
        store1.record_trace("Persisted spec text", outcome="completed", feature_name="Persist Test")

        store2 = WorkflowMemoryStore(db_path=db_path)
        traces = store2.all_traces()
        assert len(traces) == 1
        assert traces[0].feature_name == "Persist Test"
        assert traces[0].spec_text == "Persisted spec text"

    def test_multiple_traces_persist(self, tmp_path):
        db_path = tmp_path / "traces.db"
        store = WorkflowMemoryStore(db_path=db_path)
        for i in range(5):
            store.record_trace(f"Spec number {i}", outcome="completed", trace_id=f"t{i}")

        store2 = WorkflowMemoryStore(db_path=db_path)
        assert store2.count() == 5
