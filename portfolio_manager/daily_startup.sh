#!/bin/bash
# ============================================
# 🚀 DAILY STARTUP SCRIPT
# ============================================
#
# Run this every trading day to:
# 1. Start all services
# 2. Verify pipeline
# 3. Sync positions from broker
#
# Usage:
#   ./daily_startup.sh              # Start and verify
#   ./daily_startup.sh --sync       # Also sync positions from broker
#
# ============================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OPENALGO_DIR="$HOME/openalgo"
PM_PORT=5002
OPENALGO_PORT=5000
# NOTE: Capital/equity is loaded from database (READ-ONLY)
# Use /capital/inject API with admin password to modify capital

cd "$SCRIPT_DIR"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         🚀 DAILY TRADING STARTUP                          ║${NC}"
echo -e "${BOLD}║         $(date '+%A, %B %d %Y')                   ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================
# STEP 1: Check Prerequisites
# ============================================
echo -e "${BLUE}━━━ Step 1: Prerequisites ━━━${NC}"

# Check config
if [ ! -f "openalgo_config.json" ]; then
    echo -e "${RED}✗ openalgo_config.json not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Config file found${NC}"

# Get execution mode
EXEC_MODE=$(python3 -c "import json; print(json.load(open('openalgo_config.json'))['execution_mode'])")
BROKER=$(python3 -c "import json; print(json.load(open('openalgo_config.json'))['broker'])")
echo -e "${YELLOW}  Mode: $EXEC_MODE | Broker: $BROKER${NC}"

if [ "$EXEC_MODE" == "live" ]; then
    echo -e "${RED}⚠️  WARNING: LIVE MODE - REAL ORDERS WILL BE PLACED!${NC}"
    read -p "Continue? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# ============================================
# STEP 2: Start OpenAlgo (if not running)
# ============================================
echo ""
echo -e "${BLUE}━━━ Step 2: OpenAlgo ━━━${NC}"

if curl -s http://127.0.0.1:$OPENALGO_PORT/api/v1/ping | grep -q "status" 2>/dev/null; then
    echo -e "${GREEN}✓ OpenAlgo already running${NC}"
else
    echo -e "${YELLOW}Starting OpenAlgo...${NC}"
    if [ -d "$OPENALGO_DIR" ]; then
        cd "$OPENALGO_DIR"
        FLASK_PORT=$OPENALGO_PORT HOST_SERVER="http://127.0.0.1:$OPENALGO_PORT" \
            nohup uv run app.py > "$OPENALGO_DIR/log/openalgo.log" 2>&1 &
        cd "$SCRIPT_DIR"

        # Wait for startup
        for i in {1..30}; do
            if curl -s http://127.0.0.1:$OPENALGO_PORT/api/v1/ping | grep -q "status" 2>/dev/null; then
                echo -e "${GREEN}✓ OpenAlgo started${NC}"
                break
            fi
            sleep 1
            echo -n "."
        done
    else
        echo -e "${RED}✗ OpenAlgo directory not found: $OPENALGO_DIR${NC}"
        echo "  Please start OpenAlgo manually: cd ~/openalgo && uv run app.py"
    fi
fi

# ============================================
# STEP 3: Start Portfolio Manager (if not running)
# ============================================
echo ""
echo -e "${BLUE}━━━ Step 3: Portfolio Manager ━━━${NC}"

if curl -s http://127.0.0.1:$PM_PORT/health | grep -q "healthy" 2>/dev/null; then
    echo -e "${GREEN}✓ Portfolio Manager already running${NC}"
else
    echo -e "${YELLOW}Starting Portfolio Manager...${NC}"

    # Activate venv if exists
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    fi

    # Get API key from config
    API_KEY=$(python3 -c "import json; print(json.load(open('openalgo_config.json'))['openalgo_api_key'])")

    # Start PM (MUST include --db-config for persistence!)
    # NOTE: No --capital flag - PM loads capital from database (READ-ONLY)
    nohup python3 portfolio_manager.py live \
        --broker "$BROKER" \
        --api-key "$API_KEY" \
        --db-config db_config.json \
        > pm.log 2>&1 &

    # Wait for startup
    for i in {1..15}; do
        if curl -s http://127.0.0.1:$PM_PORT/health | grep -q "healthy" 2>/dev/null; then
            echo -e "${GREEN}✓ Portfolio Manager started${NC}"
            break
        fi
        sleep 1
        echo -n "."
    done
fi

# ============================================
# STEP 4: Verify Pipeline
# ============================================
echo ""
echo -e "${BLUE}━━━ Step 4: Pipeline Verification ━━━${NC}"
python3 verify_pipeline.py

# ============================================
# STEP 5: Sync Positions (optional)
# ============================================
if [[ "$1" == "--sync" ]]; then
    echo ""
    echo -e "${BLUE}━━━ Step 5: Position Sync ━━━${NC}"
    python3 sync_from_broker.py --inject
fi

# ============================================
# Summary
# ============================================
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║                    STARTUP COMPLETE                       ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}PM Dashboard:${NC}  http://127.0.0.1:$PM_PORT/health"
echo -e "  ${GREEN}PM Webhook:${NC}    http://127.0.0.1:$PM_PORT/webhook"
echo -e "  ${GREEN}OpenAlgo:${NC}      http://127.0.0.1:$OPENALGO_PORT"
echo ""
echo -e "  ${YELLOW}Logs:${NC}"
echo -e "    tail -f pm.log"
echo -e "    tail -f ~/openalgo/log/openalgo.log"
echo ""
if [ "$EXEC_MODE" == "live" ]; then
    echo -e "  ${RED}⚠️  LIVE MODE ACTIVE - Trading enabled${NC}"
else
    echo -e "  ${BLUE}ℹ️  Analyzer mode - Orders simulated${NC}"
fi
echo ""
