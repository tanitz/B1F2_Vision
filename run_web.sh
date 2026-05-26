#!/bin/bash

cd "$(dirname "${BASH_SOURCE[0]}")"

echo "========================================"
echo "Quality Inspection Dashboard (Web)"
echo "========================================"
echo ""

# Activate virtual environment
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

echo "Starting web server at http://localhost:8080"
flet run --web --host localhost --port 8080 main.py
