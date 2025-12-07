#!/bin/bash
# ============================================
# Setup PM with Existing Position & Go Live
# ============================================
# 
# This script:
# 1. Starts PM in analyzer mode
# 2. Injects your existing Gold Mini position
# 3. Verifies the state
# 4. Switches to live mode
#
# Prerequisites:
# - OpenAlgo running and connected to Zerodha
# - Broker login completed
# ============================================

set -e  # Exit on error

# Configuration - UPDATE THESE VALUES
EQUITY=5000000          # Your current equity (₹50L)
ENTRY_PRICE=129925      # Your Gold Mini entry price
STOP_PRICE=129621.66    # Your Tom Basso stop (1× ATR)
LOTS=3                  # Number of lots you have
ATR=303.34              # Current ATR value

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

cd "$(dirname "$0")"

echo -e "${GREEN}=== Portfolio Manager Live Setup ===${NC}"
echo ""

# Step 1: Check OpenAlgo
echo -e "${YELLOW}Step 1: Checking OpenAlgo...${NC}"
if curl -s http://127.0.0.1:5000/api/v1/ping | grep -q "status"; then
    echo -e "${GREEN}✓ OpenAlgo is running${NC}"
else
    echo -e "${RED}✗ OpenAlgo is NOT running!${NC}"
    echo "Please start OpenAlgo first:"
    echo "  cd ~/openalgo && uv run app.py"
    exit 1
fi

# Step 2: Ensure analyzer mode
echo ""
echo -e "${YELLOW}Step 2: Setting analyzer mode for position injection...${NC}"
if grep -q '"execution_mode": "live"' openalgo_config.json 2>/dev/null; then
    sed -i '' 's/"execution_mode": "live"/"execution_mode": "analyzer"/' openalgo_config.json
    echo -e "${GREEN}✓ Switched to analyzer mode${NC}"
else
    echo -e "${GREEN}✓ Already in analyzer mode${NC}"
fi

# Step 3: Start PM
echo ""
echo -e "${YELLOW}Step 3: Starting Portfolio Manager...${NC}"
source venv/bin/activate 2>/dev/null || true
lsof -ti:5002 | xargs kill -9 2>/dev/null || true
sleep 2

nohup python3 portfolio_manager.py live \
    --broker zerodha \
    --api-key "$(python3 -c "import json; print(json.load(open('openalgo_config.json'))['openalgo_api_key'])")" \
    --capital $EQUITY \
    > pm.log 2>&1 &

sleep 5

if curl -s http://127.0.0.1:5002/health | grep -q "healthy"; then
    echo -e "${GREEN}✓ PM started successfully${NC}"
else
    echo -e "${RED}✗ PM failed to start. Check pm.log${NC}"
    exit 1
fi

# Step 4: Inject existing position
echo ""
echo -e "${YELLOW}Step 4: Injecting existing Gold Mini position...${NC}"
UTC_NOW=$(TZ=UTC date +"%Y-%m-%dT%H:%M:%SZ")

RESPONSE=$(curl -s -X POST http://127.0.0.1:5002/webhook \
    -H "Content-Type: application/json" \
    -d "{
        \"type\": \"BASE_ENTRY\",
        \"instrument\": \"GOLD_MINI\",
        \"position\": \"Long_1\",
        \"price\": $ENTRY_PRICE,
        \"stop\": $STOP_PRICE,
        \"lots\": $LOTS,
        \"atr\": $ATR,
        \"er\": 0.89,
        \"supertrend\": $STOP_PRICE,
        \"roc\": 0.93,
        \"timestamp\": \"$UTC_NOW\"
    }")

if echo "$RESPONSE" | grep -q '"status":"processed"'; then
    echo -e "${GREEN}✓ Position injected successfully${NC}"
    echo "  Entry: $ENTRY_PRICE"
    echo "  Stop: $STOP_PRICE"
    echo "  Lots: $(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['lots'])")"
else
    echo -e "${RED}✗ Failed to inject position${NC}"
    echo "$RESPONSE"
    exit 1
fi

# Step 5: Verify state
echo ""
echo -e "${YELLOW}Step 5: Verifying portfolio state...${NC}"
curl -s http://127.0.0.1:5002/analyzer/orders | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"  Mode: {data.get('mode', 'unknown')}\")
print(f\"  Orders: {data.get('total_orders', 0)}\")
if data.get('orders'):
    for o in data['orders']:
        print(f\"  → {o.get('symbol','?')} {o.get('action','?')} {o.get('quantity','?')} @ {o.get('price','?')}\")
"

# Step 6: Ready for live mode
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}✓ Position injected in analyzer mode!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${YELLOW}To switch to LIVE mode:${NC}"
echo ""
echo "1. Stop PM:"
echo "   lsof -ti:5002 | xargs kill -9"
echo ""
echo "2. Edit openalgo_config.json:"
echo "   Change \"execution_mode\": \"analyzer\" → \"execution_mode\": \"live\""
echo ""
echo "3. Restart PM:"
echo "   python3 portfolio_manager.py live --broker zerodha --api-key YOUR_KEY --capital $EQUITY"
echo ""
echo -e "${RED}⚠️  WARNING: In live mode, PM WILL execute real orders!${NC}"
echo ""



