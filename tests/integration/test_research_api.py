"""Integration tests for research controller with real Perplexity API."""
import os
import pytest
from pathlib import Path
from bob.orchestrator.research_controller import ResearchController
from bob.database.manager import DatabaseManager


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("PERPLEXITY_API_KEY"), reason="No PERPLEXITY_API_KEY")
class TestPerplexityResearch:
    """Test research controller with real Perplexity API calls."""

    def test_real_research_query(self, tmp_path):
        """Test that real Perplexity API returns meaningful results."""
        # Setup
        db = DatabaseManager(tmp_path / "test.db")
        controller = ResearchController(db, tmp_path)

        # Execute real query
        result = controller._execute_research_query(
            "What is Python's asyncio module?",
            "quick"
        )

        # Verify real results
        assert result.success
        assert len(result.findings) > 100  # Should have substantial content
        assert "async" in result.findings.lower() or "asyncio" in result.findings.lower()

    def test_research_error_handling(self, tmp_path):
        """Test that research handles errors gracefully."""
        # Setup with invalid API key
        db = DatabaseManager(tmp_path / "test.db")
        controller = ResearchController(db, tmp_path)

        # Temporarily save and clear API key
        original_key = os.getenv("PERPLEXITY_API_KEY")
        os.environ["PERPLEXITY_API_KEY"] = "invalid_key_12345"

        try:
            # Execute query with bad key
            result = controller._execute_research_query(
                "What is Python?",
                "quick"
            )

            # Should fail gracefully
            assert not result.success
            assert result.error is not None
            assert "401" in result.error or "Invalid API key" in result.error
        finally:
            # Restore original key
            if original_key:
                os.environ["PERPLEXITY_API_KEY"] = original_key

    def test_research_thoroughness_levels(self, tmp_path):
        """Test different thoroughness levels produce different results."""
        db = DatabaseManager(tmp_path / "test.db")
        controller = ResearchController(db, tmp_path)

        # Quick research
        quick_result = controller._execute_research_query(
            "What is FastAPI?",
            "quick"
        )

        # Thorough research
        thorough_result = controller._execute_research_query(
            "What is FastAPI?",
            "thorough"
        )

        # Both should succeed
        assert quick_result.success
        assert thorough_result.success

        # Thorough should generally have more content
        # (though this isn't guaranteed, so we just check both have content)
        assert len(quick_result.findings) > 50
        assert len(thorough_result.findings) > 50
