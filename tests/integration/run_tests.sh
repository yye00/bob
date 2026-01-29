#!/bin/bash
# Integration test runner script

echo "=== BOB Integration Tests ==="
echo ""

# Check for API keys
missing_keys=()
if [ -z "$PERPLEXITY_API_KEY" ]; then
    missing_keys+=("PERPLEXITY_API_KEY")
fi
if [ -z "$ANTHROPIC_API_KEY" ]; then
    missing_keys+=("ANTHROPIC_API_KEY")
fi

if [ ${#missing_keys[@]} -gt 0 ]; then
    echo "⚠️  Warning: Missing API keys: ${missing_keys[*]}"
    echo "   Tests requiring these keys will be skipped."
    echo ""
fi

# Run tests
echo "Running integration tests..."
echo ""

pytest tests/integration/ -v -m integration "$@"
