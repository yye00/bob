# Integration Tests

This directory contains integration tests that make real API calls to external services.

## Requirements

These tests require:
- API keys configured as environment variables
- Network connectivity
- Test dependencies installed

### Required API Keys

- `PERPLEXITY_API_KEY` - For research API tests
- `ANTHROPIC_API_KEY` - For Claude orchestration tests

## Installation

Install test dependencies:

```bash
pip install -r requirements-dev.txt
```

## Running Tests

### Run all integration tests

```bash
pytest tests/integration/ -v
```

### Run specific test file

```bash
# Research API tests
pytest tests/integration/test_research_api.py -v

# Orchestration API tests
pytest tests/integration/test_orchestration_api.py -v
```

### Run with API key check

Tests will be automatically skipped if the required API keys are not set:

```bash
# This will skip tests if keys are missing
pytest tests/integration/ -v -m integration
```

### Run without integration tests

To run only unit tests (skip integration):

```bash
pytest -v -m "not integration"
```

## Test Structure

- `test_research_api.py` - Tests for ResearchController with real Perplexity API
- `test_orchestration_api.py` - Tests for Orchestrator with real Claude API

## Notes

- Integration tests are marked with `@pytest.mark.integration`
- Tests are automatically skipped if API keys are not available
- Tests use temporary directories for isolation
- All tests clean up after themselves
