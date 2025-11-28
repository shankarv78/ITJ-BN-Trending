#!/bin/bash

# ============================================================================
# Check Portfolio Manager Processing Status
# ============================================================================
# This script helps you monitor and verify that the portfolio manager
# is processing webhook signals correctly.
#
# Usage:
#   ./check_processing.sh [option]
#
# Options:
#   logs      - Show recent logs
#   stats     - Show webhook statistics
#   positions - Show current positions
#   all       - Show everything (default)
# ============================================================================

set -e

WEBHOOK_URL="${WEBHOOK_URL:-https://webhook.shankarvasudevan.com/webhook}"
PORT=5002

echo "============================================================================"
echo "Portfolio Manager Processing Status"
echo "============================================================================"
echo ""

OPTION=${1:-all}

# Check if portfolio manager is running
if lsof -Pi :${PORT} -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "✅ Portfolio manager is running on port $PORT"
else
    echo "❌ Portfolio manager is NOT running on port $PORT"
    echo "   Start it with: python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY"
    exit 1
fi

echo ""

# Function to show logs
show_logs() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 Recent Portfolio Manager Logs (last 20 lines)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    if [ -f "portfolio_manager.log" ]; then
        tail -20 portfolio_manager.log
    else
        echo "⚠️  Log file not found: portfolio_manager.log"
    fi
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 Recent Webhook Validation Logs (last 10 lines)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    if [ -f "webhook_validation.log" ]; then
        tail -10 webhook_validation.log
    else
        echo "⚠️  Log file not found: webhook_validation.log"
    fi
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 Recent Webhook Errors (last 10 lines)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    if [ -f "webhook_errors.log" ]; then
        tail -10 webhook_errors.log
    else
        echo "✅ No errors logged (or log file not found)"
    fi
    echo ""
}

# Function to show stats
show_stats() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Webhook Statistics"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    STATS_RESPONSE=$(curl -s "$WEBHOOK_URL/stats" 2>/dev/null || echo "{}")
    
    if echo "$STATS_RESPONSE" | grep -q "webhook"; then
        echo "$STATS_RESPONSE" | jq '.' 2>/dev/null || echo "$STATS_RESPONSE"
    else
        echo "⚠️  Could not fetch statistics"
        echo "   Make sure the webhook endpoint is accessible"
    fi
    echo ""
}

# Function to show positions
show_positions() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "💼 Current Positions"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Note: Positions are stored in the portfolio manager's internal state."
    echo "To see positions, check the portfolio_manager.log for position updates."
    echo ""
    if [ -f "portfolio_manager.log" ]; then
        echo "Recent position-related log entries:"
        grep -i "position\|entry\|exit\|pyramid" portfolio_manager.log | tail -10 || echo "No position entries found"
    fi
    echo ""
}

# Function to show real-time monitoring
show_realtime() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "👀 Real-time Log Monitoring"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "To monitor logs in real-time, run:"
    echo "  tail -f portfolio_manager.log"
    echo ""
    echo "Or watch all logs:"
    echo "  tail -f portfolio_manager.log webhook_validation.log webhook_errors.log"
    echo ""
    echo "Press Ctrl+C to stop monitoring"
    echo ""
}

# Execute based on option
case "$OPTION" in
    logs)
        show_logs
        ;;
    stats)
        show_stats
        ;;
    positions)
        show_positions
        ;;
    realtime|monitor)
        show_realtime
        tail -f portfolio_manager.log webhook_validation.log webhook_errors.log 2>/dev/null || tail -f portfolio_manager.log
        ;;
    all|*)
        show_logs
        show_stats
        show_positions
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "💡 Quick Commands"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "Monitor logs in real-time:"
        echo "  ./check_processing.sh realtime"
        echo ""
        echo "View only logs:"
        echo "  ./check_processing.sh logs"
        echo ""
        echo "View statistics:"
        echo "  ./check_processing.sh stats"
        echo ""
        echo "Test webhook:"
        echo "  ./test_webhook.sh"
        echo ""
        ;;
esac

