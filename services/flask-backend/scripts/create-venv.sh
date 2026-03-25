#!/bin/bash
# Create Python virtual environment for flask-backend service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"

echo "🐍 Creating virtual environment for flask-backend..."

cd "$SERVICE_DIR"

# Remove existing venv if present
if [ -d ".venv" ]; then
    echo "Removing existing .venv..."
    rm -rf .venv
fi

# Create new venv
python3 -m venv .venv

# Activate and install dependencies
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Virtual environment created successfully!"
echo ""
echo "To activate, run:"
echo "  source $SERVICE_DIR/.venv/bin/activate"
echo ""
echo "Or use direnv (recommended):"
echo "  cd $SERVICE_DIR && direnv allow"
