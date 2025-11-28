#!/bin/bash
#
# Test Runner for Tom Basso Portfolio Manager
# ===========================================
# Runs all tests with coverage reporting
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Tom Basso Portfolio Manager - Test Suite${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if pytest installed
if ! python -m pytest --version > /dev/null 2>&1; then
    echo -e "${YELLOW}Installing test dependencies...${NC}"
    pip install -r requirements.txt
fi

# Run unit tests
echo -e "${YELLOW}[1/3]${NC} Running Unit Tests..."
python -m pytest tests/unit/ -v

echo ""

# Run integration tests
echo -e "${YELLOW}[2/3]${NC} Running Integration Tests..."
python -m pytest tests/integration/ -v

echo ""

# Run all tests with coverage
echo -e "${YELLOW}[3/3]${NC} Running All Tests with Coverage..."
python -m pytest tests/ -v --cov=core --cov=backtest --cov-report=html --cov-report=term-missing

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ All Tests Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Coverage report: htmlcov/index.html"
echo ""
echo "Test Summary:"
python -m pytest tests/ --co -q | wc -l | xargs echo "  Total tests:"

echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Open htmlcov/index.html to view coverage"
echo "  2. Run specific test: pytest tests/unit/test_position_sizer.py -v"
echo "  3. Run with debugging: pytest tests/ -v -s"

