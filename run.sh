#!/bin/bash

cd "$(dirname "${BASH_SOURCE[0]}")"

echo "========================================"
echo "Quality Inspection Dashboard"
echo "========================================"
echo ""

# Create virtual environment if not exists
if ! python3 -c "import ensurepip" 2>/dev/null; then
    echo ""
    echo "ERROR: python3-venv not installed. Run:"
    echo "  sudo apt install -y python3.12-venv python3-pip"
    echo ""
    return 1 2>/dev/null || exit 1
fi

if [ ! -f ".venv/bin/activate" ]; then
    echo "Creating virtual environment..."
    rm -rf .venv
    python3 -m venv .venv
    source .venv/bin/activate
    echo "Installing dependencies..."
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo "Starting application..."
python3 main.py
