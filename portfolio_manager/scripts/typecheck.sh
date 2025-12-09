#!/bin/bash
# Type checking script for Portfolio Manager
# Usage: ./scripts/typecheck.sh [--strict]

set -e

cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "Running mypy type checker..."
echo "================================"

if [ "$1" == "--strict" ]; then
    echo "Mode: STRICT (will show all errors)"
    mypy --explicit-package-bases \
         --strict \
         --ignore-missing-imports \
         core/ live/ brokers/
else
    echo "Mode: GRADUAL (using pyproject.toml config)"
    mypy --explicit-package-bases core/ live/ brokers/
fi

echo ""
echo "================================"
echo "Type checking complete!"
