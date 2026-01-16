#!/bin/bash
set -e

echo "========================================="
echo "BOB (Build Orchestration Bot) - Setup"
echo "========================================="
echo ""

# Detect Python version
PYTHON_CMD=""
if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
elif command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3.10 &> /dev/null; then
    PYTHON_CMD="python3.10"
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if (( $(echo "$PYTHON_VERSION >= 3.10" | bc -l) )); then
        PYTHON_CMD="python3"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ Error: Python 3.10 or higher is required"
    echo "Please install Python 3.10+ and try again"
    exit 1
fi

echo "✓ Found Python: $($PYTHON_CMD --version)"
echo ""

# Check for virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip -q
echo "✓ pip upgraded"
echo ""

# Install dependencies
echo "Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt -q
    echo "✓ Dependencies installed from requirements.txt"
else
    echo "⚠️  No requirements.txt found - installing basic dependencies"
    pip install click pyyaml jinja2 rich aiosqlite anthropic -q
    echo "✓ Basic dependencies installed"
fi
echo ""

# Check for API keys
echo "Checking environment variables..."
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠️  WARNING: ANTHROPIC_API_KEY not set"
    echo "   Set it with: export ANTHROPIC_API_KEY=your_key_here"
else
    echo "✓ ANTHROPIC_API_KEY is set"
fi

if [ -z "$PERPLEXITY_API_KEY" ]; then
    echo "ℹ️  PERPLEXITY_API_KEY not set (optional for research features)"
else
    echo "✓ PERPLEXITY_API_KEY is set"
fi
echo ""

# Initialize BOB if not already initialized
if [ ! -d "$HOME/.bob" ]; then
    echo "Initializing BOB..."
    mkdir -p "$HOME/.bob/plugins"
    mkdir -p "$HOME/.bob/cache"

    # Create default config if it doesn't exist
    if [ ! -f "$HOME/.bob/config.yaml" ]; then
        cat > "$HOME/.bob/config.yaml" << 'EOF'
# BOB Global Configuration

# Default model settings
models:
  default: claude-sonnet-4-5-20250929
  escalation: claude-opus-4-5-20251101

# API configuration
api:
  anthropic_api_key: ${ANTHROPIC_API_KEY}
  perplexity_api_key: ${PERPLEXITY_API_KEY}

# Database
database:
  type: sqlite
  path: ~/.bob/bob.db

# Logging
logging:
  level: INFO
  format: json

# Cost limits
limits:
  max_cost_per_project: 100.0  # USD
  max_cost_per_session: 5.0
  warn_at_percent: 80

# Escalation defaults (from autonomous-coding)
escalation:
  max_attempts_per_model: 3
  models:
    tier1: claude-sonnet-4-5-20250929
    tier2: claude-opus-4-5-20251101
EOF
        echo "✓ Created default config at ~/.bob/config.yaml"
    fi

    echo "✓ BOB initialized at ~/.bob/"
else
    echo "✓ BOB already initialized at ~/.bob/"
fi
echo ""

echo "========================================="
echo "✅ Setup Complete!"
echo "========================================="
echo ""
echo "BOB is ready to use. Here's what you can do:"
echo ""
echo "1. Set your API keys (if not already set):"
echo "   export ANTHROPIC_API_KEY=your_key_here"
echo "   export PERPLEXITY_API_KEY=your_key_here  # Optional"
echo ""
echo "2. Stay in this virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "3. Create your first project:"
echo "   python -m bob.cli project create my-app --spec spec.yaml"
echo ""
echo "4. Run the agent:"
echo "   python -m bob.cli run --project my-app"
echo ""
echo "For more information, see README.md"
echo ""
