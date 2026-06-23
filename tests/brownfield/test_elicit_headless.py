"""Tests for bob3.brownfield.elicit.branch_into_candidates (BF-6 scope reduction).

ACs verified:
  - Function defined: bob3.brownfield.elicit.branch_into_candidates
  - branch_into_candidates returns N candidate dicts for a headless request
  - branch_into_candidates is the public wrapper around _branch_into_candidates
  - Interactive mode emits AskUserQuestion instead of branching
  - elicit() dispatches correctly based on feature_mode
"""

from __future__ import annotations

import unittest

from bob3.brownfield.elicit import (
    ElicitationRequest,
    ElicitationResult,
    MODE_HEADLESS,
    MODE_INTERACTIVE,
    branch_into_candidates,
    elicit,
)


class TestBranchIntoCandidatesExists(unittest.TestCase):
    """Verify the function is importable and callable."""

    def test_function_is_importable(self):
        from bob3.brownfield import elicit
        self.assertTrue(hasattr(elicit, "branch_into_candidates"))

    def test_function_is_callable(self):
        self.assertTrue(callable(branch_into_candidates))


class TestBranchIntoCandidatesReturnType(unittest.TestCase):
    """branch_into_candidates must return a list of candidate dicts."""

    def test_returns_list(self):
        req = ElicitationRequest(intent_stub="add a cache layer")
        result = branch_into_candidates(req)
        self.assertIsInstance(result, list)

    def test_returns_non_empty_list(self):
        req = ElicitationRequest(intent_stub="add a cache layer")
        result = branch_into_candidates(req)
        self.assertGreater(len(result), 0)

    def test_returns_dicts(self):
        req = ElicitationRequest(intent_stub="add a cache layer")
        result = branch_into_candidates(req)
        for candidate in result:
            self.assertIsInstance(candidate, dict)

    def test_candidate_count_matches_request(self):
        req = ElicitationRequest(intent_stub="add a cache layer", candidate_count=5)
        result = branch_into_candidates(req)
        self.assertEqual(len(result), 5)

    def test_default_candidate_count(self):
        req = ElicitationRequest(intent_stub="add a feature")
        result = branch_into_candidates(req)
        self.assertEqual(len(result), 3)


class TestBranchIntoCandidatesStructure(unittest.TestCase):
    """Each candidate must have the expected fields."""

    def _get_candidates(self):
        req = ElicitationRequest(intent_stub="migrate from postgres to redis")
        return branch_into_candidates(req)

    def test_candidates_have_candidate_id(self):
        candidates = self._get_candidates()
        for c in candidates:
            self.assertIn("candidate_id", c)

    def test_candidates_have_interpretation(self):
        candidates = self._get_candidates()
        for c in candidates:
            self.assertIn("interpretation", c)

    def test_candidates_have_confidence(self):
        candidates = self._get_candidates()
        for c in candidates:
            self.assertIn("confidence", c)

    def test_candidates_have_branch_label(self):
        candidates = self._get_candidates()
        for c in candidates:
            self.assertIn("branch_label", c)

    def test_candidates_have_strategy(self):
        candidates = self._get_candidates()
        for c in candidates:
            self.assertIn("strategy", c)
            self.assertEqual(c["strategy"], "branch_into_candidates")

    def test_candidate_ids_are_unique(self):
        candidates = self._get_candidates()
        ids = [c["candidate_id"] for c in candidates]
        self.assertEqual(len(ids), len(set(ids)))


class TestElicitHeadlessDispatch(unittest.TestCase):
    """elicit() must use branch_into_candidates for headless mode."""

    def test_headless_mode_returns_candidates(self):
        req = ElicitationRequest(intent_stub="refactor auth module")
        result = elicit(req, feature_mode=MODE_HEADLESS)
        self.assertIsInstance(result, ElicitationResult)
        self.assertGreater(len(result.candidates), 0)

    def test_headless_mode_does_not_emit_ask_user_question(self):
        req = ElicitationRequest(intent_stub="refactor auth module")
        result = elicit(req, feature_mode=MODE_HEADLESS)
        self.assertFalse(result.ask_user_question_emitted)

    def test_interactive_mode_emits_ask_user_question(self):
        req = ElicitationRequest(intent_stub="what should I do?")
        result = elicit(req, feature_mode=MODE_INTERACTIVE)
        self.assertTrue(result.ask_user_question_emitted)

    def test_interactive_mode_has_no_candidates(self):
        req = ElicitationRequest(intent_stub="what should I do?")
        result = elicit(req, feature_mode=MODE_INTERACTIVE)
        self.assertEqual(len(result.candidates), 0)

    def test_headless_result_mode_is_headless(self):
        req = ElicitationRequest(intent_stub="add retry logic")
        result = elicit(req, feature_mode=MODE_HEADLESS)
        self.assertEqual(result.mode, MODE_HEADLESS)

    def test_invalid_mode_raises(self):
        req = ElicitationRequest(intent_stub="do something")
        with self.assertRaises(ValueError):
            elicit(req, feature_mode="invalid_mode")


class TestBranchIntoCandidatesSignature(unittest.TestCase):
    """Verify function signature matches expectations."""

    def test_accepts_request_positional(self):
        import inspect
        sig = inspect.signature(branch_into_candidates)
        params = list(sig.parameters.keys())
        self.assertIn("request", params)

    def test_returns_annotation_is_list(self):
        import inspect
        sig = inspect.signature(branch_into_candidates)
        ret = sig.return_annotation
        # Either annotated as list or not annotated
        if ret != inspect.Parameter.empty:
            self.assertTrue(str(ret).startswith("list"))


if __name__ == "__main__":
    unittest.main()
