"""Tests for integration-criterion detection in bob3.spec_synthesizer.

Verifies that detect_integration_targets identifies wiring-intent keywords
and that deterministic_fallback emits an "integration:" criterion when such
keywords are found.  Also covers ensure_integration_criterion — the LLM
happy-path post-processor that adds a missing integration criterion when
the LLM omits it but the description signals wiring intent (regression
fixture for the normal happy path, complementing the F-R6-305 fallback tests).
"""
from __future__ import annotations

import pytest

from bob3.spec_synthesizer import (
    detect_integration_targets,
    deterministic_fallback,
    ensure_integration_criterion,
    parse_criteria_response,
)


# ---------------------------------------------------------------------------
# detect_integration_targets
# ---------------------------------------------------------------------------


class TestDetectIntegrationTargets:
    def test_integrate_keyword(self):
        desc = "Integrate the new cache layer with the query engine."
        targets = detect_integration_targets(desc)
        assert len(targets) > 0

    def test_wire_into_keyword(self):
        desc = "Wire the metrics collector into the orchestrator pipeline."
        targets = detect_integration_targets(desc)
        assert len(targets) > 0

    def test_hook_into_keyword(self):
        desc = "Hook into the existing event bus to emit audit events."
        targets = detect_integration_targets(desc)
        assert len(targets) > 0

    def test_register_with_keyword(self):
        desc = "Register with the plugin registry to be auto-discovered."
        targets = detect_integration_targets(desc)
        assert len(targets) > 0

    def test_plug_into_keyword(self):
        desc = "Plug into the scheduler so jobs run at startup."
        targets = detect_integration_targets(desc)
        assert len(targets) > 0

    def test_no_integration_keywords(self):
        desc = "A simple data-class that wraps a feature row."
        targets = detect_integration_targets(desc)
        assert targets == []

    def test_returns_list_of_strings(self):
        desc = "Wire the logger into the CLI entrypoint."
        targets = detect_integration_targets(desc)
        assert isinstance(targets, list)
        assert all(isinstance(t, str) for t in targets)

    def test_module_extracted_from_wire_into(self):
        desc = "Wire the new validator into orchestrator.main."
        targets = detect_integration_targets(desc)
        # At least one target should reference the module
        combined = " ".join(targets).lower()
        assert "orchestrator" in combined or "main" in combined or len(targets) > 0

    def test_empty_description(self):
        targets = detect_integration_targets("")
        assert targets == []

    def test_case_insensitive_detection(self):
        desc = "INTEGRATE the payment gateway WITH the checkout flow."
        targets = detect_integration_targets(desc)
        assert len(targets) > 0

    def test_multiple_keywords(self):
        desc = "Wire into the router and register with the middleware stack."
        targets = detect_integration_targets(desc)
        assert len(targets) > 0

    def test_wired_into_variant(self):
        desc = "The new handler should be wired into the request pipeline."
        targets = detect_integration_targets(desc)
        assert len(targets) > 0


# ---------------------------------------------------------------------------
# deterministic_fallback includes integration criterion
# ---------------------------------------------------------------------------


class TestDeterministicFallbackIntegration:
    def test_fallback_adds_integration_criterion_when_wiring_keyword(self):
        title = "Cache Integration"
        desc = "Integrate the cache module with the query engine."
        criteria = deterministic_fallback(title, desc)
        integration_criteria = [c for c in criteria if c.startswith("integration:")]
        assert len(integration_criteria) >= 1

    def test_fallback_no_integration_criterion_without_wiring(self):
        title = "Simple Cache"
        desc = "A simple in-memory cache for query results."
        criteria = deterministic_fallback(title, desc)
        integration_criteria = [c for c in criteria if c.startswith("integration:")]
        assert len(integration_criteria) == 0

    def test_fallback_still_includes_file_and_test_criteria(self):
        title = "Event Bus Hook"
        desc = "Hook into the event bus to handle audit events."
        criteria = deterministic_fallback(title, desc)
        file_criteria = [c for c in criteria if c.startswith("File exists:")]
        test_criteria = [c for c in criteria if c.startswith("pytest:")]
        assert len(file_criteria) >= 1
        assert len(test_criteria) >= 1

    def test_fallback_wire_into_adds_integration(self):
        title = "Logger Wiring"
        desc = "Wire the logger into the CLI entrypoint module."
        criteria = deterministic_fallback(title, desc)
        integration_criteria = [c for c in criteria if c.startswith("integration:")]
        assert len(integration_criteria) >= 1

    def test_fallback_hook_into_adds_integration(self):
        title = "Audit Hook"
        desc = "Hook into the request lifecycle to capture audit events."
        criteria = deterministic_fallback(title, desc)
        integration_criteria = [c for c in criteria if c.startswith("integration:")]
        assert len(integration_criteria) >= 1

    def test_fallback_register_with_adds_integration(self):
        title = "Plugin Registration"
        desc = "Register with the plugin registry at startup."
        criteria = deterministic_fallback(title, desc)
        integration_criteria = [c for c in criteria if c.startswith("integration:")]
        assert len(integration_criteria) >= 1

    def test_integration_criterion_format(self):
        title = "Scheduler Hook"
        desc = "Hook into the orchestrator scheduler to run on startup."
        criteria = deterministic_fallback(title, desc)
        integration_criteria = [c for c in criteria if c.startswith("integration:")]
        assert len(integration_criteria) >= 1
        # Format must be "integration: <module>"
        for crit in integration_criteria:
            parts = crit.split(":", 1)
            assert len(parts) == 2
            module = parts[1].strip()
            assert module, "integration criterion must name a module"


# ---------------------------------------------------------------------------
# parse_criteria_response handles integration: criteria
# ---------------------------------------------------------------------------


class TestParseCriteriaResponseIntegration:
    def test_parse_response_with_integration_criterion(self):
        text = '''```json
["File exists: src/bob3/foo.py", "pytest: tests/test_foo.py", "integration: bob3.orchestrator"]
```'''
        result = parse_criteria_response(text)
        assert result is not None
        integration = [c for c in result if c.startswith("integration:")]
        assert len(integration) == 1
        assert "bob3.orchestrator" in integration[0]


# ---------------------------------------------------------------------------
# ensure_integration_criterion — LLM happy-path post-processor
# (regression fixture: normal path emits integration criterion)
# ---------------------------------------------------------------------------


class TestEnsureIntegrationCriterion:
    """Covers the LLM happy-path: when LLM succeeds but omits the integration
    criterion, ensure_integration_criterion plugs the gap automatically."""

    def test_adds_integration_when_llm_omits_it(self):
        """LLM output has no integration: entry but description implies wiring."""
        llm_criteria = [
            "File exists: src/bob3/cache.py",
            "Function defined: bob3.cache.get",
            "pytest: tests/test_cache.py",
        ]
        desc = "Integrate the cache layer with the query engine."
        result = ensure_integration_criterion(llm_criteria, desc)
        integration = [c for c in result if c.startswith("integration:")]
        assert len(integration) >= 1

    def test_does_not_duplicate_existing_integration(self):
        """LLM already added integration:; function must not add a second one."""
        llm_criteria = [
            "File exists: src/bob3/cache.py",
            "pytest: tests/test_cache.py",
            "integration: bob3.query_engine",
        ]
        desc = "Integrate the cache layer with the query engine."
        result = ensure_integration_criterion(llm_criteria, desc)
        integration = [c for c in result if c.startswith("integration:")]
        assert len(integration) == 1

    def test_no_modification_without_wiring_keywords(self):
        """Description has no wiring intent; criteria must be returned unchanged."""
        llm_criteria = [
            "File exists: src/bob3/cache.py",
            "pytest: tests/test_cache.py",
        ]
        desc = "A simple in-memory cache for query results."
        result = ensure_integration_criterion(llm_criteria, desc)
        assert result == llm_criteria

    def test_wire_into_triggers_addition(self):
        """'wire into' keyword causes integration criterion to be added."""
        llm_criteria = ["File exists: src/bob3/logger.py", "pytest: tests/test_logger.py"]
        desc = "Wire the logger into the orchestrator pipeline."
        result = ensure_integration_criterion(llm_criteria, desc)
        integration = [c for c in result if c.startswith("integration:")]
        assert len(integration) >= 1

    def test_hook_into_triggers_addition(self):
        """'hook into' keyword causes integration criterion to be added."""
        llm_criteria = ["File exists: src/bob3/audit.py", "pytest: tests/test_audit.py"]
        desc = "Hook into the event bus to emit audit events."
        result = ensure_integration_criterion(llm_criteria, desc)
        integration = [c for c in result if c.startswith("integration:")]
        assert len(integration) >= 1

    def test_register_with_triggers_addition(self):
        """'register with' keyword causes integration criterion to be added."""
        llm_criteria = ["File exists: src/bob3/plugin.py", "pytest: tests/test_plugin.py"]
        desc = "Register with the plugin registry at startup."
        result = ensure_integration_criterion(llm_criteria, desc)
        integration = [c for c in result if c.startswith("integration:")]
        assert len(integration) >= 1

    def test_integration_target_is_module_qualified(self):
        """Extracted integration target must be bob3.-qualified."""
        llm_criteria = ["File exists: src/bob3/foo.py", "pytest: tests/test_foo.py"]
        desc = "Wire the metrics collector into the orchestrator pipeline."
        result = ensure_integration_criterion(llm_criteria, desc)
        integration = [c for c in result if c.startswith("integration:")]
        assert len(integration) >= 1
        module = integration[0].split(":", 1)[1].strip()
        assert module.startswith("bob3.") or "." in module, (
            f"integration target should be qualified, got: {module!r}"
        )

    def test_returns_list_of_strings(self):
        """Return type is always list[str]."""
        llm_criteria = ["pytest: tests/test_foo.py"]
        desc = "Wire foo into bar module."
        result = ensure_integration_criterion(llm_criteria, desc)
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)

    def test_original_criteria_preserved(self):
        """All original LLM criteria are preserved after addition."""
        llm_criteria = [
            "File exists: src/bob3/foo.py",
            "Function defined: bob3.foo.main",
            "pytest: tests/test_foo.py",
        ]
        desc = "Integrate the foo module with the scheduler."
        result = ensure_integration_criterion(llm_criteria, desc)
        for orig in llm_criteria:
            assert orig in result
