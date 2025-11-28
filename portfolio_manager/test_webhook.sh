#!/bin/bash

# ============================================================================
# Test Webhook with Sample TradingView Signals
# ============================================================================
# This script sends test signals to your webhook endpoint to verify
# that the portfolio manager is processing them correctly.
#
# Usage:
#   ./test_webhook.sh [signal_type]
#
# Signal types: base_entry, pyramid, exit
# ============================================================================

set -e

WEBHOOK_URL="${WEBHOOK_URL:-https://webhook.shankarvasudevan.com/webhook}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "============================================================================"
echo "Testing Portfolio Manager Webhook"
echo "============================================================================"
echo ""
echo "Webhook URL: $WEBHOOK_URL"
echo ""

# Get current timestamp in ISO 8601 format
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Function to send a signal and show response
send_signal() {
    local signal_name=$1
    local json_payload=$2
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📤 Sending: $signal_name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Payload:"
    echo "$json_payload" | jq '.' 2>/dev/null || echo "$json_payload"
    echo ""
    
    echo "Response:"
    RESPONSE=$(curl -s -X POST "$WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d "$json_payload" \
        -w "\nHTTP_STATUS:%{http_code}")
    
    HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
    BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')
    
    if [ "$HTTP_STATUS" = "200" ]; then
        echo -e "${GREEN}✅ HTTP $HTTP_STATUS${NC}"
    else
        echo -e "${RED}❌ HTTP $HTTP_STATUS${NC}"
    fi
    
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    echo ""
    echo ""
}

# Test 1: BASE_ENTRY for Bank Nifty
test_base_entry_bn() {
    local json=$(cat <<EOF
{
  "type": "BASE_ENTRY",
  "instrument": "BANK_NIFTY",
  "position": "Long_1",
  "price": 52000,
  "stop": 51650,
  "lots": 5,
  "atr": 350,
  "er": 0.82,
  "supertrend": 51650,
  "roc": 2.5,
  "timestamp": "$TIMESTAMP"
}
EOF
)
    send_signal "BASE_ENTRY (Bank Nifty)" "$json"
}

# Test 2: BASE_ENTRY for Gold Mini
test_base_entry_gold() {
    local json=$(cat <<EOF
{
  "type": "BASE_ENTRY",
  "instrument": "GOLD_MINI",
  "position": "Long_1",
  "price": 72000,
  "stop": 71500,
  "lots": 3,
  "atr": 500,
  "er": 0.75,
  "supertrend": 71500,
  "roc": 1.8,
  "timestamp": "$TIMESTAMP"
}
EOF
)
    send_signal "BASE_ENTRY (Gold Mini)" "$json"
}

# Test 3: PYRAMID for Bank Nifty
test_pyramid_bn() {
    local json=$(cat <<EOF
{
  "type": "PYRAMID",
  "instrument": "BANK_NIFTY",
  "position": "Long_2",
  "price": 52200,
  "stop": 51800,
  "lots": 3,
  "atr": 360,
  "er": 0.85,
  "supertrend": 51800,
  "roc": 2.8,
  "timestamp": "$TIMESTAMP"
}
EOF
)
    send_signal "PYRAMID (Bank Nifty - Long_2)" "$json"
}

# Test 4: EXIT signal
test_exit() {
    local json=$(cat <<EOF
{
  "type": "EXIT",
  "instrument": "BANK_NIFTY",
  "position": "Long_1",
  "price": 52500,
  "stop": 0,
  "lots": 0,
  "atr": 350,
  "er": 0.82,
  "supertrend": 51650,
  "reason": "Stop Loss Hit",
  "timestamp": "$TIMESTAMP"
}
EOF
)
    send_signal "EXIT (Bank Nifty - Stop Loss)" "$json"
}

# Test 5: EXIT ALL
test_exit_all() {
    local json=$(cat <<EOF
{
  "type": "EXIT",
  "instrument": "BANK_NIFTY",
  "position": "ALL",
  "price": 52500,
  "stop": 0,
  "lots": 0,
  "atr": 350,
  "er": 0.82,
  "supertrend": 51650,
  "reason": "Manual Exit",
  "timestamp": "$TIMESTAMP"
}
EOF
)
    send_signal "EXIT ALL (Bank Nifty)" "$json"
}

# Main execution
SIGNAL_TYPE=${1:-all}

case "$SIGNAL_TYPE" in
    base_entry|entry)
        test_base_entry_bn
        ;;
    pyramid)
        test_pyramid_bn
        ;;
    exit)
        test_exit
        ;;
    exit_all)
        test_exit_all
        ;;
    gold)
        test_base_entry_gold
        ;;
    all|*)
        echo "Running all tests..."
        echo ""
        test_base_entry_bn
        sleep 2
        test_pyramid_bn
        sleep 2
        test_base_entry_gold
        ;;
esac

echo "============================================================================"
echo "✅ Testing Complete"
echo "============================================================================"
echo ""
echo "To check portfolio manager logs:"
echo "  tail -f portfolio_manager.log"
echo ""
echo "To check webhook validation logs:"
echo "  tail -f webhook_validation.log"
echo ""
echo "To check webhook errors:"
echo "  tail -f webhook_errors.log"
echo ""

