"""Tests for bob.brownfield.search_subagent (Feature 5c5826d3).

Tests the WarpGrep search sub-agent pattern:
  - SearchResult dataclass
  - spawn_search_subagent function
  - should_use_search_subagent overflow detection
  - search_results_to_edit_sites conversion
  - Score and grouping logic
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bob.brownfield.search_subagent import (
    LOCALIZER_OVERFLOW_THRESHOLD,
    MAX_CANDIDATES,
    MIN_CANDIDATES,
    SearchResult,
    _grep_candidates,
    _group_matches_into_spans,
    _score_match,
    search_results_to_edit_sites,
    should_use_search_subagent,
    spawn_search_subagent,
)


# ---------------------------------------------------------------------------
# SearchResult tests
# ---------------------------------------------------------------------------


class TestSearchResult:
    def test_to_dict_roundtrip(self):
        sr = SearchResult(
            path="src/bob/foo.py",
            start_line=10,
            end_line=25,
            confidence=0.85,
            rationale_snippet="def foo_function():",
        )
        d = sr.to_dict()
        assert d["path"] == "src/bob/foo.py"
        assert d["start_line"] == 10
        assert d["end_line"] == 25
        assert d["confidence"] == 0.85
        assert d["rationale_snippet"] == "def foo_function():"

    def test_from_dict_roundtrip(self):
        d = {
            "path": "src/bob/bar.py",
            "start_line": 5,
            "end_line": 30,
            "confidence": 0.72,
            "rationale_snippet": "class MyClass:",
        }
        sr = SearchResult.from_dict(d)
        assert sr.path == "src/bob/bar.py"
        assert sr.start_line == 5
        assert sr.end_line == 30
        assert sr.confidence == 0.72
        assert sr.rationale_snippet == "class MyClass:"

    def test_from_dict_missing_optional_fields(self):
        d = {
            "path": "src/foo.py",
            "start_line": 1,
            "end_line": 10,
        }
        sr = SearchResult.from_dict(d)
        assert sr.confidence == 0.5  # default
        assert sr.rationale_snippet == ""  # default

    def test_to_dict_contains_all_schema_fields(self):
        sr = SearchResult(
            path="x.py", start_line=1, end_line=5, confidence=0.1, rationale_snippet=""
        )
        d = sr.to_dict()
        assert set(d.keys()) == {"path", "start_line", "end_line", "confidence", "rationale_snippet"}

    def test_confidence_preserved_as_float(self):
        sr = SearchResult.from_dict({"path": "f.py", "start_line": 1, "end_line": 2, "confidence": "0.9"})
        assert isinstance(sr.confidence, float)
        assert sr.confidence == 0.9

    def test_line_numbers_preserved_as_int(self):
        sr = SearchResult.from_dict({"path": "f.py", "start_line": "5", "end_line": "15"})
        assert isinstance(sr.start_line, int)
        assert isinstance(sr.end_line, int)


# ---------------------------------------------------------------------------
# Score match tests
# ---------------------------------------------------------------------------


class TestScoreMatch:
    def test_keyword_in_text_boosts_score(self):
        match = {"path": "src/foo.py", "line_number": 10, "text": "def spawn_agent():"}
        intent = {"capability": "spawn agent", "target_subsystem": "orchestrator", "keywords": ["spawn"]}
        score = _score_match(match, intent, ["spawn"])
        assert score > 0.0

    def test_no_keywords_zero_score(self):
        match = {"path": "src/foo.py", "line_number": 10, "text": "x = 1"}
        intent = {"capability": "something", "target_subsystem": "other", "keywords": []}
        score = _score_match(match, intent, ["zzzznotpresent"])
        assert score == 0.0

    def test_function_definition_gets_boost(self):
        match_def = {"path": "src/foo.py", "line_number": 1, "text": "def my_func():"}
        match_other = {"path": "src/foo.py", "line_number": 2, "text": "x = my_func()"}
        intent = {"capability": "my func", "target_subsystem": "", "keywords": ["my"]}
        score_def = _score_match(match_def, intent, ["my"])
        score_other = _score_match(match_other, intent, ["my"])
        assert score_def >= score_other

    def test_score_capped_at_1(self):
        match = {
            "path": "src/target_sub/target_sub.py",
            "line_number": 1,
            "text": "def spawn spawn spawn target_sub capability_thing():",
        }
        intent = {
            "capability": "spawn target sub capability thing",
            "target_subsystem": "target_sub",
            "keywords": ["spawn", "target_sub"],
        }
        score = _score_match(match, intent, ["spawn", "target_sub"])
        assert score <= 1.0


# ---------------------------------------------------------------------------
# Group matches into spans tests
# ---------------------------------------------------------------------------


class TestGroupMatchesIntoSpans:
    def _make_matches(self, count: int) -> list[dict[str, Any]]:
        return [
            {"path": f"src/file_{i}.py", "line_number": (i + 1) * 20, "text": f"def func_{i}():"}
            for i in range(count)
        ]

    def test_returns_up_to_max_candidates(self):
        matches = self._make_matches(20)
        intent = {"capability": "func", "target_subsystem": "", "keywords": ["func"]}
        results = _group_matches_into_spans(matches, intent, ["func"], max_candidates=5)
        assert len(results) <= 5

    def test_returns_empty_for_no_matches(self):
        results = _group_matches_into_spans([], {}, [])
        assert results == []

    def test_results_are_search_result_instances(self):
        matches = self._make_matches(3)
        intent = {"capability": "func", "target_subsystem": "", "keywords": ["func"]}
        results = _group_matches_into_spans(matches, intent, ["func"])
        for r in results:
            assert isinstance(r, SearchResult)

    def test_start_line_less_than_end_line(self):
        matches = [{"path": "src/f.py", "line_number": 50, "text": "def foo(): pass"}]
        intent = {"capability": "foo", "target_subsystem": "", "keywords": ["foo"]}
        results = _group_matches_into_spans(matches, intent, ["foo"])
        for r in results:
            assert r.start_line <= r.end_line

    def test_start_line_ge_1(self):
        matches = [{"path": "src/f.py", "line_number": 1, "text": "def foo():"}]
        intent = {"capability": "foo", "target_subsystem": "", "keywords": ["foo"]}
        results = _group_matches_into_spans(matches, intent, ["foo"])
        for r in results:
            assert r.start_line >= 1


# ---------------------------------------------------------------------------
# spawn_search_subagent tests
# ---------------------------------------------------------------------------


class TestSpawnSearchSubagent:
    def _intent(self, capability="test_func", keywords=None, target=""):
        return {
            "capability": capability,
            "target_subsystem": target,
            "keywords": keywords or [],
        }

    def test_returns_list(self, tmp_path):
        # Create a fake Python file with searchable content
        (tmp_path / "foo.py").write_text("def test_func():\n    pass\n")
        results = spawn_search_subagent(
            self._intent("test_func", ["test_func"]),
            workspace=tmp_path,
        )
        assert isinstance(results, list)

    def test_returns_search_results(self, tmp_path):
        (tmp_path / "foo.py").write_text("def my_target_function():\n    pass\n")
        results = spawn_search_subagent(
            self._intent("my target function", ["my_target_function"]),
            workspace=tmp_path,
        )
        for r in results:
            assert isinstance(r, SearchResult)

    def test_empty_keywords_returns_empty(self, tmp_path):
        results = spawn_search_subagent({"capability": "", "target_subsystem": "", "keywords": []}, workspace=tmp_path)
        assert results == []

    def test_no_matches_returns_empty(self, tmp_path):
        (tmp_path / "foo.py").write_text("x = 1\n")
        results = spawn_search_subagent(
            self._intent("zzzzznotfound", ["zzzzznotfound"]),
            workspace=tmp_path,
        )
        assert results == []

    def test_keyword_override(self, tmp_path):
        (tmp_path / "bar.py").write_text("def special_keyword_here():\n    pass\n")
        results = spawn_search_subagent(
            self._intent("something else"),
            workspace=tmp_path,
            keywords=["special_keyword_here"],
        )
        assert isinstance(results, list)

    def test_max_candidates_respected(self, tmp_path):
        # Create many matching files
        for i in range(20):
            (tmp_path / f"file_{i}.py").write_text(f"def myfunction_{i}():\n    myfunction_base()\n")
        results = spawn_search_subagent(
            self._intent("myfunction_base", ["myfunction_base"]),
            workspace=tmp_path,
            max_candidates=3,
        )
        assert len(results) <= 3

    def test_confidence_in_valid_range(self, tmp_path):
        (tmp_path / "foo.py").write_text("def search_target():\n    pass\n")
        results = spawn_search_subagent(
            self._intent("search target", ["search_target"]),
            workspace=tmp_path,
        )
        for r in results:
            assert 0.0 <= r.confidence <= 1.0

    def test_keywords_extracted_from_intent_capability(self, tmp_path):
        (tmp_path / "foo.py").write_text("def localize_feature():\n    pass\n")
        intent = {"capability": "localize feature", "target_subsystem": "", "keywords": []}
        results = spawn_search_subagent(intent, workspace=tmp_path)
        # Should still work even without explicit keywords
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# should_use_search_subagent tests
# ---------------------------------------------------------------------------


class TestShouldUseSearchSubagent:
    def test_below_threshold_returns_false(self):
        symbols = [{"name": f"sym_{i}"} for i in range(LOCALIZER_OVERFLOW_THRESHOLD)]
        assert not should_use_search_subagent(symbols)

    def test_above_threshold_returns_true(self):
        symbols = [{"name": f"sym_{i}"} for i in range(LOCALIZER_OVERFLOW_THRESHOLD + 1)]
        assert should_use_search_subagent(symbols)

    def test_exactly_threshold_returns_false(self):
        symbols = [{"name": f"sym_{i}"} for i in range(LOCALIZER_OVERFLOW_THRESHOLD)]
        assert not should_use_search_subagent(symbols)

    def test_empty_list_returns_false(self):
        assert not should_use_search_subagent([])

    def test_threshold_is_20(self):
        assert LOCALIZER_OVERFLOW_THRESHOLD == 20


# ---------------------------------------------------------------------------
# search_results_to_edit_sites tests
# ---------------------------------------------------------------------------


class TestSearchResultsToEditSites:
    def test_converts_to_edit_site_format(self):
        results = [
            SearchResult(path="src/foo.py", start_line=10, end_line=25, confidence=0.8, rationale_snippet=""),
            SearchResult(path="src/bar.py", start_line=1, end_line=5, confidence=0.6, rationale_snippet=""),
        ]
        sites = search_results_to_edit_sites(results)
        assert len(sites) == 2
        assert sites[0]["path"] == "src/foo.py"
        assert sites[0]["start_line"] == 10
        assert sites[0]["end_line"] == 25
        assert "scope" in sites[0]
        assert "name" in sites[0]

    def test_empty_input_returns_empty_list(self):
        assert search_results_to_edit_sites([]) == []

    def test_scope_is_function(self):
        results = [SearchResult(path="x.py", start_line=1, end_line=5, confidence=0.5, rationale_snippet="")]
        sites = search_results_to_edit_sites(results)
        assert sites[0]["scope"] == "function"

    def test_edit_site_has_required_keys(self):
        results = [SearchResult(path="x.py", start_line=1, end_line=5, confidence=0.5, rationale_snippet="")]
        sites = search_results_to_edit_sites(results)
        required = {"path", "start_line", "end_line", "scope", "name"}
        assert set(sites[0].keys()) >= required
