#!/bin/bash
# Quick Start Script for Manual Testing
# Run this to start Test Scenario 1

echo "🧪 Starting Manual Test - Scenario 1: Normal Recovery"
echo "================================================"
echo ""
echo "Prerequisites check:"

# Check PostgreSQL
if psql -U pm_user -d portfolio_manager -c "SELECT 1;" >/dev/null 2>&1; then
    echo "✅ PostgreSQL: Connected"
else
    echo "❌ PostgreSQL: Not accessible"
    echo "   Fix: brew services start postgresql@14"
    exit 1
fi

# Check database_config.json
if [ -f "database_config.json" ]; then
    echo "✅ Database config: Found"
else
    echo "❌ Database config: Missing"
    echo "   Fix: cp database_config.json.example database_config.json"
    exit 1
fi

# Clean test data
echo ""
echo "Cleaning previous test data..."
psql -U pm_user -d portfolio_manager <<SQL >/dev/null 2>&1
DELETE FROM portfolio_positions WHERE position_id LIKE 'BANKNIFTY%';
DELETE FROM portfolio_state WHERE id = 1;
DELETE FROM pyramiding_state;
DELETE FROM signal_log;
SQL

echo "✅ Test data cleaned"
echo ""
echo "================================================"
echo "Ready to start! Follow the guide in MANUAL_TESTING_GUIDE.md"
echo "================================================"
echo ""
echo "Step 1: Start the application"
echo "Command:"
echo "  python3 portfolio_manager.py live --db-config database_config.json --broker mock --api-key TEST"
